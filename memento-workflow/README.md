# Memento Workflow Engine

A stateful workflow engine for Claude Code, delivered as an MCP server. Defines multi-step automation as Python or YAML, with deterministic execution, checkpoint/resume, and parallel work.

## Why this exists

Complex development workflows (TDD, code review, multi-step generation) require reliable orchestration. LLMs are the wrong tool for this — they are powerful generators but unreliable executors.

### Problem 1: LLMs can't reliably follow complex control flow

An LLM has no call stack. When you describe a workflow like "for each task: write tests, verify they fail, implement, run lint+tests, retry up to 3 times if failing" — this is a nested loop with conditionals, retries, and sub-workflows. The LLM receives it as flat text in the context window.

What goes wrong:

- **Forgets steps.** In a 10-step workflow, the LLM may skip step 7 or merge two steps together. The longer the workflow, the worse this gets.
- **Loses track of iteration.** "Process each task from the plan" — after a few iterations, the LLM loses count, re-processes an item, or declares it's done early.
- **Misinterprets branching.** "If tests pass, go to review. If tests fail, fix and re-test up to 3 times." The LLM may retry once and declare success, or enter an infinite loop.
- **No reproducibility.** The same workflow description produces different execution paths across runs. There's no guarantee the same steps execute in the same order.

The core issue: LLM instructions sit on one level — there's no scope, no stack, no program counter. You're hoping the model pays attention and doesn't forget.

### Problem 2: Deterministic tasks waste LLM resources when routed through the model

Many workflow steps are entirely mechanical: run linter, run tests, format code, detect project structure, parse JSON output. The LLM can do these, but:

- **Non-deterministic execution.** The LLM subtly changes commands between runs — different flags, different file paths, different invocation styles. `uv run pytest -x` becomes `pytest --tb=short` becomes `python -m pytest`.
- **Context window cost.** Every shell command routed through the LLM consumes context: the prompt to run it, the tool call, the output. Test output alone can be thousands of tokens. Over a 20-step workflow, this crowds out the creative work.
- **Round-trip latency.** Each LLM→tool→LLM round-trip adds seconds. A workflow with 15 shell steps wastes a minute just on the relay, when the commands could execute back-to-back in under 10 seconds.

### Solution: separate orchestration from generation

The workflow engine moves control flow and mechanical execution into a deterministic state machine. The LLM is invoked only for creative work — writing code, analyzing results, making decisions that require understanding.

| Concern           | Without engine                                                      | With engine                                                      |
| ----------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Control flow      | LLM interprets instructions (unreliable)                            | State machine with stack, loops, retries (deterministic)         |
| Shell commands    | LLM calls Bash tool (burns tokens, non-deterministic)               | Internal `subprocess.run()` (invisible to LLM)                   |
| State persistence | Lost on crash                                                       | Atomic checkpoints, crash recovery within conversation           |
| Parallelism       | LLM must manually coordinate launch, collection, and error handling | Engine manages child runs, verifies completion, propagates halts |
| Reproducibility   | Varies per run                                                      | Same workflow definition = same execution path                   |

### Design decisions

**MCP server, not Agent SDK.** The initial prototype used Claude Agent SDK to spawn isolated LLM sessions per step. This was unreliable and required many hacks: each session couldn't inherit the parent's tool permissions, user interaction needed fragile workarounds across session boundaries, and testing required faking the entire SDK. The MCP approach solves all of these — subagents inherit permissions naturally, the engine is testable as pure Python, and Claude Code acts as a simple relay.

**Shell execution is internal.** The engine runs shell commands via `subprocess.run()` inside the MCP server process. Results are stored in the engine's workflow state (not the LLM context window) and surfaced to the LLM only when it needs to act on them (e.g., fix failing tests). This eliminates the round-trip latency and context cost of routing mechanical commands through the model.

**Python-first with YAML option.** Workflows are code — they have conditions, schemas, and composition. Python gives IDE support, type checking, and full expressiveness. YAML is available for simpler workflows (~45% shorter) but compiles to the same runtime types.

**Checkpoint everything.** Every step result is atomically persisted to disk. If the MCP server restarts mid-workflow (crash, timeout), the relay can call `start(resume=...)` to continue from the last completed step. The `resume` parameter follows "resume-or-restart" semantics: if the checkpoint is valid and the run is active, it resumes. If the workflow source has changed (drift), the checkpoint is corrupt, or the run already completed — the engine cancels the old run and transparently starts fresh, attaching a warning to the first action. The relay can always pass the last known `run_id` without branching.

## How it works

```
SKILL.md / /develop → Claude Code (relay)
                        ↕ MCP tools (start/submit/next/cancel)
              ┌─────────────────────┐
              │  MCP Server (Python) │
              │  state machine       │  deterministic control flow
              │  shell execution     │  subprocess.run() internally
              │  checkpointing       │  atomic file persistence
              └─────────────────────┘
         Claude handles only creative work:
        ┌──────┬───────┬──────────┐
        ↓      ↓       ↓          ↓
     Prompt  Subagent  AskUser  Parallel
```

Claude Code calls `start()` to begin, then loops: execute the action, call `submit()` with the result, get the next action. Shell steps are invisible — executed internally by the server. Claude only sees prompts, user questions, and subagent launches.

## Building workflows

### Structure

A workflow is a directory with a definition file and optional prompts:

```
.workflows/my-workflow/
├── workflow.py          # or workflow.yaml
├── prompts/
│   ├── 01-analyze.md
│   └── 02-implement.md
└── scripts/             # optional helper scripts
    └── detect.py
```

Place it in `.workflows/` in your project root. The engine discovers it automatically.

### Example: TDD workflow (Python)

Simplified version of the real `develop` workflow — classifies the task, plans implementation units, then loops over each with test-first development. Verification (format → lint → test → LLM fix, retry up to 3×) is delegated to a reusable `verify-fix` sub-workflow:

```python
WORKFLOW = WorkflowDef(
    name="develop",
    description="TDD development workflow",
    blocks=[
        LLMStep(name="classify", prompt="00-classify.md", model="sonnet", output_schema=ClassifyOutput),
        ShellStep(name="detect", script="dev-tools.py", args="detect", result_var="project"),
        LLMStep(name="plan", prompt="02-plan.md", output_schema=PlanOutput),
        LoopBlock(
            name="implement",
            loop_over="results.plan.structured_output.tasks",
            loop_var="unit",
            blocks=[
                LLMStep(name="write-tests", prompt="03a-write-tests.md", tools=["Read", "Write", "Edit"]),
                ShellStep(name="verify-red", script="dev-tools.py",
                          args="test --scope specific --files-json '{{variables.unit.test_files}}'",
                          result_var="verify_red"),
                LLMStep(name="implement", prompt="03c-implement.md", tools=["Read", "Write", "Edit", "Bash"]),
                SubWorkflow(name="green-loop", workflow="verify-fix",
                            inject={"workdir": "{{variables.workdir}}"}),
            ],
        ),
        SubWorkflow(name="review", workflow="code-review"),
    ],
)
```

Engine types (`WorkflowDef`, `LLMStep`, etc.) are injected by the loader at runtime — no imports needed. YAML format is also supported (see [YAML-DSL.md](docs/YAML-DSL.md)).

## Block types

The engine has 9 block types. Each serves a distinct purpose:

| Block                 | Purpose                                          | Runs as                         |
| --------------------- | ------------------------------------------------ | ------------------------------- |
| **ShellStep**         | Run a command, parse JSON output                 | Internal (invisible to LLM)     |
| **LLMStep**           | Prompt the LLM to do creative work               | Inline or subagent              |
| **PromptStep**        | Ask the user a question (choice, confirm, input) | Inline (interactive checkpoint) |
| **GroupBlock**        | Sequential composition of blocks                 | Inline or subagent              |
| **LoopBlock**         | Iterate over a list from context                 | Inline                          |
| **RetryBlock**        | Repeat until condition met or max attempts       | Inline                          |
| **ConditionalBlock**  | Multi-way branching (first match wins)           | Inline                          |
| **SubWorkflow**       | Invoke another workflow by name                  | Inline (variable isolation)     |
| **ParallelEachBlock** | Run template concurrently for each item          | Subagent per lane               |

### When to use what

- **Mechanical work** (lint, test, format, detect) → `ShellStep`
- **Creative work** (write code, analyze, plan) → `LLMStep`
- **User decision point** (confirm, choose mode) → `PromptStep`
- **Repeat until green** → `RetryBlock` with shell verification
- **Per-item processing** → `LoopBlock` (sequential) or `ParallelEachBlock` (concurrent)
- **Reusable sub-process** → `SubWorkflow`
- **Shared condition on multiple steps** → `GroupBlock`
- **If/else branching** → `ConditionalBlock`

## Key concepts

### Data flow

Data flows between steps through two mechanisms:

**Variables** — shell and prompt steps can write to `ctx.variables` via `result_var`:

```python
ShellStep(name="detect", command="echo '{\"count\": 42}'", result_var="detection")
# → ctx.variables["detection"] = {"count": 42}
# → use as {{variables.detection.count}} in templates
```

**Results** — every step's output is accessible via `results`:

```python
LLMStep(name="analyze", prompt="analyze.md", output_schema=AnalysisOutput)
# → ctx.results["analyze"].structured_output = {"findings": [...], "severity": "high"}
# → use as {{results.analyze.structured_output.severity}} in templates
```

### Isolation

Blocks run either **inline** (current context) or as a **subagent** (isolated Agent tool):

- **Inline** (default): shares conversation context. The LLM sees everything from previous steps.
- **Subagent**: fresh context window. Good for large tasks, different models, or parallel work.

```python
# Single-task subagent (no relay loop)
LLMStep(name="review", prompt="review.md", isolation="subagent", model="sonnet")

# Multi-step subagent (relay-based, shared context within group)
GroupBlock(name="implement", isolation="subagent", model="sonnet",
          context_hint="project structure and test patterns",
          blocks=[
              LLMStep(name="code", prompt="code.md", tools=["Read", "Write", "Edit"]),
              ShellStep(name="test", command="uv run pytest"),
          ])
```

`context_hint` tells the relay what to summarize from the current conversation before launching the subagent. Without it, the subagent starts with only the engine's prompt.

Subagents cannot launch sub-subagents (Claude Code limitation). Inside a subagent, everything runs inline.

### Conditions

Python workflows use lambdas:

```python
LLMStep(name="deep-analysis", prompt="deep.md",
        condition=lambda ctx: ctx.result_field("classify", "complexity") == "complex")
```

YAML workflows use an expression language:

```yaml
- llm: deep-analysis
  prompt: deep.md
  when: 'results.classify.structured_output.complexity == "complex"'
```

When a condition returns false, the block is skipped entirely.

### Checkpointing

Every `submit()` atomically persists state to `.workflow-state/{run_id}/state.json`. Resume with:

```python
start(workflow="my-workflow", resume="abc123")
```

The engine verifies the workflow source hasn't changed since the checkpoint was created (strict drift policy). If it has, it refuses to resume.

## Patterns

### TDD cycle (RED → GREEN)

```python
LoopBlock(
    name="implement",
    loop_over="results.plan.structured_output.tasks",
    loop_var="unit",
    blocks=[
        LLMStep(name="write-tests", prompt="write-tests.md",
                tools=["Read", "Write", "Edit"]),
        ShellStep(name="verify-red", script="dev-tools.py",
                  args="test --scope specific --files-json '{{variables.unit.test_files}}'",
                  result_var="verify_red"),
        LLMStep(name="implement", prompt="implement.md",
                tools=["Read", "Write", "Edit", "Bash"]),
        SubWorkflow(name="green-loop", workflow="verify-fix",
                    inject={"workdir": "{{variables.workdir}}"}),
    ],
)
```

### Parallel reviews

```python
# Determine competencies to review
LLMStep(name="scope", prompt="scope.md", model="haiku",
        output_schema=ReviewScope)

# One agent per competency, running concurrently
ParallelEachBlock(
    name="reviews",
    parallel_for="results.scope.structured_output.competencies",
    item_var="competency",
    model="sonnet",
    template=[
        LLMStep(name="review", prompt="review.md", tools=["Read", "Grep"]),
    ],
)

# Synthesize all review results
LLMStep(name="synthesize", prompt="synthesize.md",
        output_schema=ReviewFindings)
```

Other patterns: `PromptStep` for user interaction (choice/confirm/input with server-side validation), `RetryBlock` with `halt_on_exhaustion` for retry-or-stop flows, `ConditionalBlock` for multi-way branching. See [DESIGN.md](docs/DESIGN.md) for details.

## Security

The engine executes shell commands and loads Python workflow files via `exec()` — automatically, without user confirmation per step. Two threat vectors: a prompt-injected agent writing a malicious workflow, or a compromised plugin shipping one.

**Process sandbox.** The MCP server re-execs itself inside an OS-level sandbox at startup. The sandbox restricts the **entire process** — all Python code, `exec()` of workflow files, and all subprocess calls:

- **macOS**: Seatbelt (`sandbox-exec`) — denies writes everywhere except `cwd` + `/tmp`, denies reads to `~/.ssh`, `~/.aws`, `~/.gnupg`
- **Linux**: bubblewrap (`bwrap`) — read-only `/`, writable binds for `cwd` + `/tmp`. Install with `apt install bubblewrap`
- **Disable**: `MEMENTO_SANDBOX=off` for containers/CI

This means even if a malicious `workflow.py` runs `os.system("rm -rf /")`, the sandbox blocks it. Write access is limited to the project directory and temp files.

## Limitations

- **Cross-conversation resume loses inline context.** Resume restores all engine state (results, variables) from disk and re-injects them via templates. Inline LLM steps in a new conversation won't see the prior conversation's accumulated context, but they still receive all data through `{{results.*}}` and `{{variables.*}}` substitution. Subagent steps are unaffected (they never had parent context).
- **Mixed parallel lanes require LLM agents.** Shell-only parallel lanes are auto-advanced internally (via `ThreadPoolExecutor`, capped at 16 workers), but lanes containing LLM steps still route through Claude Code Agent tool. Disable auto-advance with `MEMENTO_PARALLEL_AUTO_ADVANCE=off`.
- **No sub-subagents.** Inside a subagent, everything runs inline (Claude Code limitation). Parallel blocks inside subagents are silently downgraded to sequential execution.
- **No rollback.** Side effects from prior steps (file writes, git commits) are irreversible. The engine doesn't track or undo them.

## Reference documentation

| Document                          | Content                                                                            |
| --------------------------------- | ---------------------------------------------------------------------------------- |
| [DESIGN.md](docs/DESIGN.md)       | Architecture, state machine, relay protocol, error handling, security threat model |
| [YAML-DSL.md](docs/YAML-DSL.md)   | YAML workflow format, expression language, module resolution, block patterns       |
| [DASHBOARD.md](docs/DASHBOARD.md) | Web UI and CLI for browsing workflow runs and artifacts                            |

## Development

```bash
# Run tests
uv run pytest

# Run from repo root
cd .. && uv run --all-packages pytest
```
