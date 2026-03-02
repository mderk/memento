---
name: workflow-engine
description: Run imperative workflows with deterministic step execution. Use when you need to execute development, code review, testing, or protocol workflows programmatically.
version: 2.2.0
---

# Workflow Engine

Imperative workflow engine that controls execution flow (order, conditions, parallel, retry) while prompts describe WHAT to do at each atomic step.

Workflows are self-contained packages discovered from `.workflows/` in the project root. The engine is a standalone executor — new workflows can be added without modifying the engine.

## Prerequisites

```bash
uv add claude-agent-sdk --group dev
```

## Usage

### From CLI

```bash
# Run a development workflow
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/scripts/runner.py development \
  --var task="Add login endpoint" --cwd /path/to/project

# Dry run (show steps without executing)
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/scripts/runner.py development --dry-run

# Code review
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/scripts/runner.py code-review --cwd /path/to/project

# Run tests
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/scripts/runner.py testing --cwd /path/to/project

# Process a protocol
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/scripts/runner.py process-protocol \
  --var protocol_dir=.protocols/0001-auth --cwd /path/to/project

# Use additional workflow directories
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/scripts/runner.py my-workflow \
  --workflow-dir /extra/workflows --cwd /path/to/project

# Pre-supply answers to prompt steps (uses the prompt's fully-scoped key)
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/scripts/runner.py development \
  --answer confirm=yes

# Non-interactive orchestration (Claude Code): on the first unanswered PromptStep,
# the engine writes a checkpoint to .workflow-state/<run_id>/checkpoint.json and prints
# an exact resume command including the fully-scoped answer key.
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/run.py resume --cwd /path/to/project \
  --run-id <run_id> --answer <scoped_prompt_key>=<answer>

# Plugin-only workflows (in skills/): use --workflow-dir
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/scripts/runner.py create-environment \
  --workflow-dir ${CLAUDE_PLUGIN_ROOT}/skills/create-environment \
  --var plugin_root=${CLAUDE_PLUGIN_ROOT}
```

### Available Workflows

Deployed workflows (discovered from `.workflows/` in the project root):

| Workflow           | Description                                                                        |
| ------------------ | ---------------------------------------------------------------------------------- |
| `development`          | Full TDD workflow: classify, explore, plan, test-first implement, review, complete |
| `code-review`          | Parallel competency-based code review with synthesis                               |
| `testing`              | Run tests with coverage analysis                                                   |
| `process-protocol`     | Execute protocol steps with QA checks and commits                                  |

Plugin-only workflows (in `skills/`, invoked via `--workflow-dir`):

| Workflow               | Description                                                      |
| ---------------------- | ---------------------------------------------------------------- |
| `create-environment`   | Generate Memory Bank environment (Fresh/Merge/Resume strategies) |
| `update-environment`   | Selective update with change detection and 3-way merge           |

### Variables

Pass variables with `--var key=value`:

| Variable       | Workflow           | Description                          |
| -------------- | ------------------ | ------------------------------------ |
| `task`           | development          | Task description                     |
| `mode`           | development          | "standalone" (default) or "protocol" |
| `protocol_dir`   | process-protocol     | Path to protocol directory           |
| `plugin_root`    | create/update-env    | Path to memento plugin root          |
| `plugin_version` | create/update-env    | Plugin version for commit metadata   |

## Workflow Packages

Workflows are self-contained directories discovered from `.workflows/` in the project root:

```
.workflows/
├── develop/
│   ├── workflow.py     # exports WORKFLOW: WorkflowDef
│   └── prompts/        # prompt templates referenced by steps
│       ├── 00-classify.md
│       └── ...
├── code-review/
│   ├── workflow.py
│   └── prompts/
├── testing/
│   ├── workflow.py
│   └── prompts/
└── my-custom-workflow/  # add your own!
    ├── workflow.py
    └── prompts/
```

### Creating a Custom Workflow

1. Create a directory in `.workflows/` with a `workflow.py` file
2. Engine types (`WorkflowDef`, `LLMStep`, etc.) are injected by the loader — no imports needed
3. Standard imports (`from pydantic import BaseModel`) work normally
4. Export a `WORKFLOW` variable of type `WorkflowDef`
5. Add prompt templates in a `prompts/` subdirectory

Example `workflow.py`:

```python
from pydantic import BaseModel

class MyOutput(BaseModel):
    result: str

WORKFLOW = WorkflowDef(
    name="my-workflow",
    description="A custom workflow",
    blocks=[
        ShellStep(name="detect", command="echo detecting"),
        PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Found {{variables.file_count}} files. Proceed?",
            default="yes",
            result_var="confirmed",
        ),
        LLMStep(
            name="step-1",
            prompt="01-step.md",
            tools=["Read", "Glob"],
            output_schema=MyOutput,
            condition=lambda ctx: ctx.variables.get("confirmed") == "yes",
        ),
    ],
)
```

## Architecture

**Code controls flow. Prompts describe what.**

- `LLMStep` — single `query()` call with prompt, tools, model, output schema
- `GroupBlock` — sequential composition of any blocks; can run contiguous `LLMStep`s in shared sessions
- `ParallelEachBlock` — run a template (any blocks) concurrently for each item in a list
- `LoopBlock` — iterate over items from context
- `RetryBlock` — repeat until condition met or max attempts
- `ConditionalBlock` — multi-way branching: first matching branch wins, else default
- `SubWorkflow` — invoke another workflow by name
- `ShellStep` — `subprocess.run()` (no LLM); optional `result_var` parses JSON stdout into variables
- `PromptStep` — interactive checkpoint: ask user a question at a predefined point

### Step Identity and Results

To avoid collisions in loops/retries/parallel/subworkflows, each leaf execution is recorded with a deterministic **scoped execution key** (`exec_key`) derived from the execution path (e.g. loop index, retry attempt, parallel index, subworkflow stack).

- `ctx.results_scoped` stores **all** leaf results by `exec_key` (canonical, collision-free)
- `ctx.results` stores a deterministic “last result” convenience view by name (parallel uses **last-by-index**)

### Interactive Capabilities

Interactivity is supported via **planned checkpoints** (`PromptStep`):

- Workflow authors define where user input is needed (`confirm`, `choice`, `input`)
- Answers can be pre-supplied via `--answer`
- In non-interactive mode (stdin is not a TTY), the engine stops on the first unanswered prompt, writes a checkpoint, and prints a resume command

### PromptStep

```python
PromptStep(
    name="strategy",              # display name
    key="strategy",               # stable ID for --answer lookup (defaults to name)
    prompt_type="choice",         # "confirm" | "choice" | "input"
    message="Choose strategy:",   # supports {{variable}} substitution
    options=["Resume", "Merge", "Fresh"],
    default="Resume",
    result_var="strategy",        # store answer in ctx.variables["strategy"]
    condition=lambda ctx: ...,    # optional skip condition
)
```

### IOHandler Modes

| Mode | IOHandler | Behavior |
|------|-----------|----------|
| stdin is a TTY | `StdinIOHandler` | Interactive: print question, read stdin |
| stdin is a TTY + `--answer` | `PresetIOHandler` | Use preset answers, fallback to defaults |
| stdin is not a TTY | `StopIOHandler` | Stop on first unanswered prompt, write checkpoint, print resume command |

### Resume (`resume` subcommand)

When resuming after a stop, use the printed resume command (or run manually):

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/run.py resume --cwd /path/to/project \
  --run-id <run_id> --answer <scoped_prompt_key>=<answer>
```

**Strict drift policy**: resume is refused if the workflow source file changed since the checkpoint was created.

### ask_user MCP Tool

Injected into every `query()` call when `io_handler` is set on the context. Sub-Claude agents can call it to ask questions:

```
Tool: mcp__engine__ask_user
Input: {"message": "Should the API return 404 or empty list?", "options": ["404", "empty list"]}
Output: {"content": [{"type": "text", "text": "empty list"}]}
```

In non-interactive mode, returns a fallback message instructing the agent to use its best judgment.
