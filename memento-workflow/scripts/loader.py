"""Dynamic workflow discovery and loading.

Scans directories recursively for workflow packages (directories containing
workflow.py or workflow.yaml that export/define a WorkflowDef).
"""

import logging
from pathlib import Path

from .compiler import compile_workflow
from .types import (
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


def load_workflow(workflow_dir: Path) -> WorkflowDef:
    """Load a single workflow from a directory.

    Tries workflow.yaml first (compiled), falls back to workflow.py (exec'd).

    Raises KeyError if workflow.py doesn't export WORKFLOW.
    Raises TypeError if WORKFLOW is not a WorkflowDef.
    """
    yaml_path = workflow_dir / "workflow.yaml"
    if yaml_path.exists():
        return compile_workflow(workflow_dir)

    source_path = workflow_dir / "workflow.py"
    code = source_path.read_text(encoding="utf-8")
    ns = dict(_INJECT)
    exec(code, ns)  # noqa: S102
    wf = ns["WORKFLOW"]
    if not isinstance(wf, WorkflowDef):
        msg = f"{source_path}: WORKFLOW is {type(wf).__name__}, expected WorkflowDef"
        raise TypeError(msg)
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
