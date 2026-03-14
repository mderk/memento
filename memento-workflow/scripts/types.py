"""Block type definitions for the imperative workflow engine."""

import time
from typing import Annotated, Any, Callable, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


# ---------------------------------------------------------------------------
# Step result
# ---------------------------------------------------------------------------


class StepResult(BaseModel):
    """Output from a single step execution."""

    name: str
    exec_key: str = ""
    base: str = ""
    results_key: str = ""
    order: int = 0
    output: str = ""
    structured_output: Any = None
    status: str = "success"  # success | failure | skipped
    duration: float = 0.0
    error: str | None = None
    cost_usd: float | None = None
    step_type: str = ""  # "llm_step" | "shell" | "prompt"
    model: str | None = None
    started_at: str = ""


# ---------------------------------------------------------------------------
# Workflow context (accumulator passed through every block)
# ---------------------------------------------------------------------------


class WorkflowContext(BaseModel):
    """Mutable state threaded through the entire workflow."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Convenience view: last (deterministic) result by base name.
    results: dict[str, StepResult] = Field(default_factory=dict)
    # Canonical storage: every executed leaf step by deterministic scoped exec_key.
    results_scoped: dict[str, StepResult] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)
    cwd: str = "."
    dry_run: bool = False
    prompt_dir: str = ""
    _start: float = PrivateAttr(default_factory=time.time)
    _scope: list[str] = PrivateAttr(default_factory=list)
    _order_seq: int = PrivateAttr(default=0)

    def elapsed(self) -> float:
        return time.time() - self._start

    def next_order(self) -> int:
        self._order_seq += 1
        return self._order_seq

    def scoped_exec_key(self, base: str) -> str:
        """Build a deterministic exec_key from current scope + base name."""
        if not self._scope:
            return base
        return "/".join([*self._scope, base])

    def push_scope(self, part: str) -> None:
        self._scope.append(part)

    def pop_scope(self) -> None:
        if self._scope:
            self._scope.pop()

    def result_field(self, step: str, key: str) -> Any:
        """Get a field from a step's structured_output."""
        r = self.results.get(step)
        if r and isinstance(r.structured_output, dict):
            return r.structured_output.get(key)
        return None

    def get_var(self, dotpath: str) -> Any:
        """Resolve dotpath variables for template substitution.

        Bare 'results' returns {step: structured_output or output} — clean
        data for prompts without StepResult metadata.  Dotpath access like
        'results.step.field' still resolves against the full StepResult.
        """
        if dotpath == "cwd":
            return self.cwd
        if dotpath == "results":
            return {
                k: v.structured_output if v.structured_output is not None else v.output
                for k, v in self.results.items()
            }
        if dotpath == "variables":
            return self.variables
        parts = dotpath.split(".")
        if parts[0] == "results" and len(parts) >= 2:
            # Longest-prefix match: try most specific key first
            for i in range(len(parts) - 1, 0, -1):
                candidate = ".".join(parts[1:i + 1])
                result = self.results.get(candidate)
                if result is not None:
                    obj: Any = result
                    for p in parts[i + 1:]:
                        if isinstance(obj, dict):
                            obj = obj.get(p)
                        elif hasattr(obj, p):
                            obj = getattr(obj, p)
                        else:
                            return None
                    return obj
            return None
        if parts[0] == "variables":
            obj = self.variables
            for p in parts[1:]:
                if isinstance(obj, dict):
                    obj = obj.get(p)
                else:
                    return None
            return obj
        return None


# ---------------------------------------------------------------------------
# Block types
# ---------------------------------------------------------------------------


class BlockBase(BaseModel):
    """Common interface for all workflow blocks."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Discriminator for parsing/serialization.
    type: str

    # Human-facing label (not required to be stable).
    name: str

    # Stable identity for caching/resume/answer lookup. If empty, defaults to name.
    # May include template variables like {{variables.x}}.
    key: str = ""

    # Optional runtime condition; if false, block is skipped.
    condition: Callable[[WorkflowContext], bool] | None = None

    # Execution context: "inline" runs in current context, "subagent" launches isolated Agent.
    isolation: Literal["inline", "subagent"] = "inline"

    # Guides the relay agent on what context to summarize for subagent launches.
    context_hint: str = ""

    # If non-empty and this block executes (not skipped), halt the entire
    # workflow after this block completes.  The string is the halt reason.
    halt: str = ""


class LLMStep(BlockBase):
    """Single LLM prompt — executed inline or as subagent."""

    type: Literal["llm_step"] = "llm_step"

    prompt: str = ""  # path relative to prompt_dir
    prompt_text: str = ""  # inline prompt text (mutually exclusive with prompt)
    tools: list[str] = []
    model: str | None = None
    # Pydantic model class for structured output (kept as arbitrary type).
    # NOTE: Annotating as `type[BaseModel] | None` triggers evaluation issues on Python 3.14.
    output_schema: Any = None


class LoopBlock(BlockBase):
    """Iterate over a list from context, execute inner blocks per item."""

    type: Literal["loop"] = "loop"

    loop_over: str  # dotpath into ctx resolving to a list
    loop_var: str
    blocks: list["Block"] = []


class RetryBlock(BlockBase):
    """Repeat inner blocks until condition met or max_attempts reached."""

    type: Literal["retry"] = "retry"

    until: Callable[[WorkflowContext], bool]
    max_attempts: int = 3
    blocks: list["Block"] = []

    # If non-empty and max_attempts exhausted without until=True,
    # halt the entire workflow.  The string is the halt reason.
    halt_on_exhaustion: str = ""


class SubWorkflow(BlockBase):
    """Invoke another workflow by name with injected variables."""

    type: Literal["subworkflow"] = "subworkflow"

    workflow: str  # registry key
    inject: dict[str, str] = {}


class ShellStep(BlockBase):
    """subprocess.run() — no LLM involved."""

    type: Literal["shell"] = "shell"

    command: str = ""  # shell command template with {{variable}} substitution
    script: str = ""  # path relative to workflow dir (mutually exclusive with command)
    args: str = ""  # args template, appended to script invocation
    env: dict[str, str] = Field(default_factory=dict)  # env vars with {{template}} substitution
    result_var: str = ""  # if set, parse stdout JSON → ctx.variables[result_var]
    stdin: str = ""  # dotpath → content piped as stdin to subprocess


class Branch(BaseModel):
    """A single branch in a ConditionalBlock: condition + blocks to execute."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    condition: Callable[[WorkflowContext], bool]
    blocks: list["Block"] = []


class ConditionalBlock(BlockBase):
    """Multi-way branching — first matching branch wins, else default."""

    type: Literal["conditional"] = "conditional"

    branches: list[Branch] = []
    default: list["Block"] = []


class PromptStep(BlockBase):
    """Interactive checkpoint — ask user a question at a predefined point."""

    type: Literal["prompt"] = "prompt"

    prompt_type: Literal["confirm", "choice", "input"]
    message: str  # template with {{variable}} substitution
    options: list[str] = []
    default: str | None = None
    result_var: str = ""  # store answer in ctx.variables[result_var]
    strict: bool = True  # enforce exact option match; False allows free-text


class GroupBlock(BlockBase):
    """Sequential composition — can contain any blocks."""

    type: Literal["group"] = "group"

    blocks: list["Block"] = []
    model: str | None = None


class ParallelEachBlock(BlockBase):
    """Run a template (any blocks) concurrently for each item."""

    type: Literal["parallel_each"] = "parallel_each"

    parallel_for: str  # dotpath into ctx resolving to a list
    template: list["Block"] = []
    item_var: str = "item"
    max_concurrency: int | None = None
    model: str | None = None


# Union of all block types (discriminated by `type`)
Block = Annotated[
    Union[
        LLMStep,
        PromptStep,
        ShellStep,
        GroupBlock,
        ParallelEachBlock,
        LoopBlock,
        RetryBlock,
        SubWorkflow,
        ConditionalBlock,
    ],
    Field(discriminator="type"),
]

class WorkflowDef(BaseModel):
    """A named workflow: ordered list of blocks."""

    name: str
    description: str
    blocks: list[Block] = []
    prompt_dir: str = ""  # resolved by loader, used by engine
    source_path: str = ""  # resolved by loader, used for strict resume checks


# Resolve forward references for all models in this module.
StepResult.model_rebuild()
WorkflowContext.model_rebuild()
BlockBase.model_rebuild()
LLMStep.model_rebuild()
PromptStep.model_rebuild()
ShellStep.model_rebuild()
GroupBlock.model_rebuild()
ParallelEachBlock.model_rebuild()
LoopBlock.model_rebuild()
RetryBlock.model_rebuild()
SubWorkflow.model_rebuild()
Branch.model_rebuild()
ConditionalBlock.model_rebuild()
WorkflowDef.model_rebuild()
