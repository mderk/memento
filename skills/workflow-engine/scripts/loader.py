"""Dynamic workflow discovery and loading.

Scans directories for workflow packages (directories containing workflow.py)
and loads them by exec-ing with engine types injected into the namespace.
"""

from pathlib import Path

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


def load_workflow(workflow_dir: Path) -> WorkflowDef:
    """Load a single workflow from a directory containing workflow.py."""
    source_path = workflow_dir / "workflow.py"
    code = source_path.read_text(encoding="utf-8")
    ns = dict(_INJECT)
    exec(code, ns)  # noqa: S102
    wf = ns["WORKFLOW"]
    if not wf.prompt_dir:
        wf.prompt_dir = str(workflow_dir / "prompts")
    if not wf.source_path:
        wf.source_path = str(source_path)
    return wf


def discover_workflows(*search_paths: Path) -> dict[str, WorkflowDef]:
    """Scan directories for workflow packages, return name->WorkflowDef registry.

    For each path:
    - If the path itself contains workflow.py, load it directly.
    - Otherwise, scan child directories for workflow.py.
    """
    registry: dict[str, WorkflowDef] = {}
    for base in search_paths:
        if not base.is_dir():
            continue
        if (base / "workflow.py").is_file():
            wf = load_workflow(base)
            registry[wf.name] = wf
        else:
            for child in sorted(base.iterdir()):
                if child.is_dir() and (child / "workflow.py").is_file():
                    wf = load_workflow(child)
                    registry[wf.name] = wf
    return registry
