"""Dynamic workflow discovery and loading.

Scans directories recursively for workflow packages (directories containing
workflow.py or workflow.yaml that export/define a WorkflowDef).
"""

import logging
import sys
from pathlib import Path

from .compiler import compile_workflow
from .types import (
    Block,
    Branch,
    ConditionalBlock,
    GroupBlock,
    LLMStep,
    LoopBlock,
    ParallelEachBlock,
    PromptStep,
    RetryBlock,
    ShellStep,
    SubWorkflow,
    WorkflowContext,
    WorkflowDef,
)

# Types injected into workflow.py namespace (no relative imports needed)
_INJECT = {
    "__builtins__": __builtins__,
    "WorkflowDef": WorkflowDef,
    "LLMStep": LLMStep,
    "GroupBlock": GroupBlock,
    "ParallelEachBlock": ParallelEachBlock,
    "LoopBlock": LoopBlock,
    "RetryBlock": RetryBlock,
    "SubWorkflow": SubWorkflow,
    "ShellStep": ShellStep,
    "PromptStep": PromptStep,
    "ConditionalBlock": ConditionalBlock,
    "Branch": Branch,
    "WorkflowContext": WorkflowContext,
}


logger = logging.getLogger("workflow-engine")


_COMPOSITE_BLOCK_TYPES = (
    GroupBlock,
    LoopBlock,
    RetryBlock,
    ConditionalBlock,
    SubWorkflow,
    ParallelEachBlock,
)


def _validate_resume_only(blocks: list[Block]) -> None:
    """Reject resume_only on composite blocks (recursively)."""
    for block in blocks:
        if getattr(block, "resume_only", "") and isinstance(block, _COMPOSITE_BLOCK_TYPES):
            raise ValueError(
                f"resume_only is only allowed on leaf steps (LLMStep, ShellStep, PromptStep), "
                f"not on {type(block).__name__} '{block.name}'"
            )
        # Recurse into children
        if isinstance(block, (LoopBlock, RetryBlock, GroupBlock)):
            _validate_resume_only(block.blocks)
        if isinstance(block, ParallelEachBlock):
            _validate_resume_only(block.template)
        if isinstance(block, ConditionalBlock):
            for branch in block.branches:
                _validate_resume_only(branch.blocks)
            if block.default:
                _validate_resume_only(block.default)


def load_workflow(workflow_dir: Path) -> WorkflowDef:
    """Load a single workflow from a directory.

    Tries workflow.yaml first (compiled), falls back to workflow.py (exec'd).

    Raises KeyError if workflow.py doesn't export WORKFLOW.
    Raises TypeError if WORKFLOW is not a WorkflowDef.
    """
    yaml_path = workflow_dir / "workflow.yaml"
    if yaml_path.exists():
        wf = compile_workflow(workflow_dir)
        _validate_resume_only(wf.blocks)
        return wf

    source_path = workflow_dir / "workflow.py"
    code = source_path.read_text(encoding="utf-8")
    ns = dict(_INJECT)
    # Add parent dir to sys.path so `from _dsl import *` resolves
    parent = str(workflow_dir.parent)
    added = parent not in sys.path
    if added:
        sys.path.insert(0, parent)
    try:
        exec(code, ns)  # noqa: S102
    finally:
        if added:
            sys.path.remove(parent)
    wf = ns["WORKFLOW"]
    if not isinstance(wf, WorkflowDef):
        msg = f"{source_path}: WORKFLOW is {type(wf).__name__}, expected WorkflowDef"
        raise TypeError(msg)
    _validate_resume_only(wf.blocks)
    if not wf.prompt_dir:
        wf.prompt_dir = str(workflow_dir / "prompts")
    if not wf.source_path:
        wf.source_path = str(source_path)
    return wf


def discover_workflows(*search_paths: Path) -> dict[str, WorkflowDef]:
    """Scan directories recursively for workflow packages, return name->WorkflowDef registry.

    A valid workflow package is a directory with workflow.yaml or workflow.py.
    YAML files are preferred when both exist. Files that fail to load are
    silently skipped.
    """
    registry: dict[str, WorkflowDef] = {}
    seen_dirs: set[Path] = set()
    for base in search_paths:
        if not base.is_dir():
            continue
        # Scan for both workflow.yaml and workflow.py
        for pattern in ("workflow.yaml", "workflow.py"):
            for wf_file in sorted(base.rglob(pattern)):
                wf_dir = wf_file.parent
                if wf_dir in seen_dirs:
                    continue
                seen_dirs.add(wf_dir)
                try:
                    wf = load_workflow(wf_dir)
                    registry[wf.name] = wf
                except (KeyError, TypeError, SyntaxError, ValueError) as exc:
                    logger.debug("Skipping %s: %s", wf_file, exc)
    return registry
