# Workflow Engine — Design Document

## Overview

The workflow engine executes imperative workflows defined as Python dataclasses. It supports 9 block types (ShellStep, PromptStep, LLMStep, GroupBlock, ParallelEachBlock, LoopBlock, RetryBlock, SubWorkflow, ConditionalBlock) with deterministic execution, checkpoint/resume, and interactive user prompts.

The engine is a **stateful MCP server** with a state machine core. Claude Code acts as a relay — calling MCP tools (`start`, `submit`, `next`, `cancel`) to drive execution. All control flow (loops, retries, conditionals, subworkflows) is resolved inside the state machine. Shell steps are executed internally by the MCP server via `subprocess.run()` — they never appear as relay actions. Claude only sees: `prompt`, `ask_user`, `subagent`, `parallel`.

---

## Architecture

```
SKILL.md / Command → Claude Code (relay loop)
                        ↕ MCP tools (start/submit/next/cancel)
              ┌─────────────────────┐
              │  MCP Server (Python) │  ← durable state (file checkpoints)
              │  state machine       │  ← template substitution
              │  workflow discovery   │  ← condition evaluation
              │  shell execution     │  ← subprocess.run() internally
              └─────────────────────┘
          Claude handles only non-shell actions:
         ┌──────┬───────┬──────────┐
         ↓      ↓       ↓          ↓
      Agent   Agent   AskUser   LLM Prompt
```

### Why MCP (vs Agent SDK)

The previous architecture used Claude Agent SDK to spawn isolated LLM sessions per step. This had fundamental problems:

1. **Permissions**: Each `query()` = separate Claude session, can't inherit parent's permissions
2. **ask_user**: Dual mechanism (PromptStep + emergent ask_user in LLM) was complex and fragile
3. **SDK instability**: Complex API, testing required fake SDK, tight coupling
4. **Subagent visibility**: Subagents launched via Agent tool DO see parent's MCP servers

The MCP server approach solves all of these: subagents inherit permissions naturally, ask_user is just another action type, and the engine is testable without any SDK.

---

## Relay Protocol

1. `mcp.start(workflow, variables)` → first action (includes `exec_key`)
2. **Show the `_display` field** from the action as a brief status line. Every action includes `_display` — a human-readable one-liner (e.g., `Step [build]: Running shell — npm run build`)
3. Execute action based on `action` field:
   - `"ask_user"` → ask user, submit raw answer as-is (server validates strict prompts)
   - `"prompt"` → process the LLM prompt directly in current context (inline)
   - `"subagent"` → launch Agent tool. If `relay: true`, agent runs sub-relay loop with MCP
   - `"parallel"` → launch multiple Agents simultaneously (each lane = subagent with sub-relay)
4. `mcp.submit(run_id, exec_key, output, status)` → next action
5. Repeat until `"completed"`
6. Recovery: `mcp.next(run_id)` re-fetches current pending action without mutating state

Shell steps are executed internally by the MCP server. Actions may include `_shell_log` — a list of shell steps auto-advanced to reach the current action.

### MCP Server Tools

```python
@server.tool()
def start(workflow: str, variables: dict = {}, cwd: str = "",
          workflow_dirs: list[str] = [],
          resume_run_id: str = "", dry_run: bool = False) -> dict:
    """Start workflow (or resume from checkpoint), return first action with exec_key."""

@server.tool()
def submit(run_id: str, exec_key: str, output: str = "",
           structured_output: dict | None = None, status: str = "success",
           error: str | None = None, duration: float = 0.0,
           cost_usd: float | None = None) -> dict:
    """Submit result for exec_key, return next action. Idempotent.
    Works on both parent and child run_ids."""

@server.tool()
def next(run_id: str) -> dict:
    """Re-fetch current pending action without mutating state. Recovery tool."""

@server.tool()
def cancel(run_id: str) -> dict:
    """Cancel a running workflow. Cleans up state file."""

@server.tool()
def list_workflows(cwd: str = "", workflow_dirs: list[str] = []) -> dict:
    """List discovered workflows from plugin + project + extra dirs."""

@server.tool()
def status(run_id: str) -> dict:
    """Get current workflow state (for debugging/monitoring).
    Includes child run statuses if any."""
```

### Protocol Invariants

- **`exec_key` is the only submit identifier** — deterministic, collision-free across loops/retries/parallel
- **Idempotent submit**: same `(run_id, exec_key)` twice returns same next action (no double-recording)
- **Strict validation**: if relay submits wrong exec_key, server returns error with expected key
- **Durable state**: every submit atomically checkpoints to `{cwd}/.workflow-state/{run_id}/state.json`
- **Protocol version**: every action includes `protocol_version: 1` for future compat
- **Child runs for isolation**: subagent relay and parallel lanes get their own `child_run_id` — each child has its own `pending_exec_key`, no concurrent submit conflicts on parent
- **No subagent from child**: if current run is a child (subagent relay), engine never emits `subagent`/`parallel` actions — downgrades to `inline` with warning
- **Parallel-to-Loop downgrade**: when a `ParallelEachBlock` is encountered inside a child run, it is silently downgraded to sequential execution (as a `LoopBlock`). This prevents nested subagent spawning which Claude Code does not support. A warning is appended to `state.warnings`.
- **Child run verification** (`_verify_child_runs`): before the parent accepts a subagent or parallel submit with `status="success"`, the runner verifies all child runs have reached `"completed"` status. This prevents the relay agent from fabricating results without actually running the child relay loop. If verification fails, the parent returns an error with instructions to complete the child runs first.

---

## Block Isolation Model

Workflow authors specify `isolation` on blocks to control execution context:

```python
class BlockBase(BaseModel):
    isolation: Literal["inline", "subagent"] = "inline"
    context_hint: str = ""
```

- `"inline"` (default) — execute in current context (main Claude or current subagent)
- `"subagent"` — launch new Agent tool (isolated context, inherits permissions)
- `context_hint` — when launching a subagent, the relay agent summarizes relevant context from its conversation guided by this hint

`LLMStep`, `GroupBlock`, and `ParallelEachBlock` also have `model: str | None = None`. When set, the engine includes `model` in the emitted action so the relay passes it to the Agent tool launch. This lets workflow authors control which model runs subagent/parallel lanes independently of the relay agent's own model.

Rules:

- `ParallelEachBlock` lanes are always subagents (parallel requires isolation)
- Subagents can NOT launch sub-subagents (Claude Code limitation). Inside a subagent, everything is inline
- Shell steps are always inline (executed internally by the MCP server, never visible to the relay)
- ask_user is always inline (executed by whoever is running the relay)
- `isolation="subagent"` on LLMStep → single-task subagent (no sub-relay)
- `isolation="subagent"` on GroupBlock/SubWorkflow → subagent with sub-relay for all inner steps

---

## Action Response Format

Every action includes: `run_id`, `exec_key`, `protocol_version: 1`, `_display` (human-readable status line).

Actions may include a `_shell_log` field — a list of internally-executed shell steps that were auto-advanced to reach this action. Each entry: `{exec_key, command, status, output (truncated), duration}`.

```python
# Inline actions (shell steps auto-advanced, visible in _shell_log):
# NOTE: tools in inline prompts are GUIDANCE, not enforced. Enforcement only via subagent.
{"action": "prompt",   "run_id": "...", "exec_key": "analyze", "prompt": "full text...",
 "tools": [...], "model": "sonnet",
 "_display": "Step [analyze]: LLM prompt — Analyze the codebase",
 "_shell_log": [{"exec_key": "detect", "status": "success", "output": "{...}", "duration": 0.3}]}
{"action": "prompt",   "run_id": "...", "exec_key": "plan",    "prompt": "...", "tools": [...],
 "json_schema": {...}, "output_schema_name": "PlanOutput",
 "_display": "Step [plan]: LLM prompt (JSON output) — PlanOutput"}
{"action": "ask_user", "run_id": "...", "exec_key": "confirm", "prompt_type": "choice",
 "message": "...", "options": [...],
 "_display": "Step [confirm]: Asking user — Choose an option"}

# Server-side strict validation — retry confirm (after invalid answer):
{"action": "ask_user", "run_id": "...", "exec_key": "confirm", "prompt_type": "confirm",
 "message": "Your answer didn't match...\nTry again?", "options": ["yes", "no"],
 "_retry_confirm": true,
 "_display": "Step [confirm]: Invalid answer — try again?"}

# Single-task subagent (no sub-relay):
{"action": "subagent", "run_id": "...", "exec_key": "review",
 "prompt": "...", "tools": [...], "model": "sonnet",
 "context_hint": "relevant files and patterns", "relay": false,
 "_display": "Step [review]: Subagent (single task)"}

# Multi-step subagent with sub-relay (gets child_run_id):
{"action": "subagent", "run_id": "...", "exec_key": "sub:develop",
 "child_run_id": "<child_id>", "prompt": "...",
 "context_hint": "project structure", "relay": true,
 "_display": "Step [sub:develop]: Subagent with relay"}

# Parallel — each lane = child run (model optional):
{"action": "parallel", "run_id": "...", "exec_key": "par:reviews",
 "model": "opus",
 "lanes": [{"child_run_id": "...", "exec_key": "par:reviews[i=0]", "prompt": "...", "relay": true}, ...],
 "_display": "Step [par:reviews]: Parallel — 3 lanes"}

# Completion:
{"action": "completed", "run_id": "...", "summary": {...},
 "_display": "Workflow completed"}

# Cancellation (from strict validation "no" or status="cancelled"):
{"action": "cancelled", "run_id": "...",
 "_display": "Workflow cancelled by user"}

# Error (exec_key validation):
{"action": "error", "run_id": "...", "message": "...", "expected_exec_key": "...", "got": "...",
 "_display": "Error: wrong exec_key"}
```

---

## Subagent Lifecycle

### relay:false (single task, no child_run_id)

1. Parent receives `subagent` action (no `child_run_id`)
2. Parent launches Agent tool with prompt
3. Agent completes task, returns output
4. Parent calls `submit(parent_run_id, exec_key, output=agent_return)`
5. If agent fails → parent submits with `status="failure"`

### relay:true (multi-step, with child_run_id)

1. Parent receives `subagent` action with `child_run_id`
2. Parent launches Agent tool with relay instructions referencing `child_run_id`
3. Subagent calls `next(child_run_id)` → gets first inline action
4. Subagent processes inline actions directly:
   - `prompt` → agent processes the LLM prompt itself (shared context!)
   - `ask_user` → agent asks user
   - Shell steps are already executed internally — sub-agent never sees them
   - Engine NEVER emits `subagent`/`parallel` inside a child run (downgraded to inline)
5. Subagent calls `submit(child_run_id, exec_key, ...)` for each inner step
6. After last step, MCP returns `{"action": "completed"}` → subagent exits with summary
7. Parent gets Agent tool return value
8. Parent calls `submit(parent_run_id, block_exec_key, output=agent_return)` → parent advances
9. If subagent crashes/fails → parent submits with `status="failure"`

**Key**: sub-agents have access to the same MCP server (confirmed by experiment). No nested Agent tool needed — the sub-agent directly calls MCP tools and executes work itself. All steps within the subagent share one context.

**Result propagation**: Parent only receives the child's summary (Agent tool return value), stored under the subagent block's exec_key. Inner step results stay in the child's context — parent cannot reference `{{results.sub:develop.inner_step}}`. If the parent needs specific data from the child, either:

- Include it in the child's summary (the subagent returns structured data)
- Use a prepare-context step before the subagent (see Context Passing)

### ParallelEachBlock (parallel child runs)

Each parallel lane = one Agent with its own child run:

1. Engine resolves parallel items, allocates child_run_id per lane
2. Returns `{"action": "parallel", "lanes": [{child_run_id, first_action + relay_instructions}, ...]}`
3. Parent launches N Agents simultaneously (one per lane)
4. Each agent runs sub-relay on its `child_run_id`: `next()` → execute → `submit()` → ... → `completed`
5. Each agent exits when it receives `completed`, returns summary
6. Parent collects all Agent returns, calls `submit(parent_run_id, parallel_exec_key, output=combined_results)`
7. Engine verifies all child runs completed (`_verify_child_runs` in runner), then advances past parallel block. If any lane is incomplete, returns error action

---

## State Machine Design

### Cursor Stack

```python
class Frame:
    block: Block | WorkflowDef
    block_index: int = 0
    scope_label: str = ""
    # Per-type state:
    loop_items: list | None       # LoopBlock
    loop_index: int               # LoopBlock
    retry_attempt: int            # RetryBlock
    chosen_branch_index: int      # ConditionalBlock
    chosen_blocks: list | None    # ConditionalBlock
    saved_vars: dict | None       # SubWorkflow
    saved_prompt_dir: str | None  # SubWorkflow

class RunState:
    run_id: str
    parent_run_id: str | None     # set for child runs
    ctx: WorkflowContext
    stack: list[Frame]
    registry: dict[str, WorkflowDef]
    status: Literal["running", "waiting", "completed", "error"]
    pending_exec_key: str | None  # expected next submit key
    child_run_ids: list[str]      # active child runs
    wf_hash: str                  # for drift detection on resume
    protocol_version: int = 1
    checkpoint_dir: Path | None
    warnings: list[str]
```

### advance() — the heart

Returns `(ActionBase, list[RunState])` — action model + any newly created child RunStates. All actions are typed Pydantic models (see `protocol.py`), serialised to dicts at the wire boundary via `action_to_dict()`.

1. Top frame's current child → check `isolation`:
   - `"inline"` leaf (Shell/Prompt) → emit action
   - `"inline"` LLMStep → emit `prompt` action
   - `"subagent"` LLMStep → emit `subagent` with `relay: false`
   - `"subagent"` Group/SubWorkflow → create child RunState, emit `subagent` with `relay: true`
   - **If child run**: downgrade any `subagent`/`parallel` → `inline` + warning
2. If `"inline"` container → push frame, recurse
3. If ParallelEachBlock → create child RunState per lane, emit `parallel`
4. Frame exhausted → pop (loop/retry may re-enter), continue
5. Stack empty → "completed"

### submit() behavior

1. **Route**: find RunState by `run_id`
2. **Validate**: check `exec_key` matches `pending_exec_key`
3. **Verify child runs**: for subagent relay and parallel actions, verify all child runs completed before accepting `status="success"` (anti-fabrication guard — see `_verify_child_runs` in runner). Skipped for `status="failure"` or non-relay actions
4. **Idempotency**: if `exec_key` already recorded → skip, return cached next action
5. **Record**: store result in `ctx.results_scoped[exec_key]` and `ctx.results[base_name]`
6. **Advance**: call `advance()` to find next action
7. **Checkpoint**: atomically persist state to disk
8. **Return**: next action

**Parent submits for isolated blocks are simple**: parent receives `subagent`/`parallel` action → parent `pending_exec_key` = block's exec_key → parent waits for Agent tool to finish → parent calls `submit(parent_run_id, block_exec_key, output=agent_summary)` → parent advances past the block.

### Scope keys (deterministic)

Built from stack labels:

- Loop: `loop:{name}[i={idx}]`
- Retry: `retry:{name}[attempt={n}]`
- Parallel: `par:{name}[i={lane}]`
- SubWorkflow: `sub:{name}`

---

## Durable Checkpointing

Every `submit()` atomically persists state to `{cwd}/.workflow-state/{run_id}/state.json`:

- Atomic write: write to `state.json.tmp` then `os.replace()`
- Contains: RunState serialized (ctx, stack frames as indices + metadata, pending_exec_key)
- `workflow_hash` stored at start — `checkpoint_load()` refuses if workflow source changed (strict drift policy)
- `start()` can accept `resume_run_id` to reload from checkpoint
- `cancel()` cleans up checkpoint directory

**Replay-based resume**: The checkpoint stores `results_scoped` (all completed step results) and `variables` — the deterministic outputs of all completed steps. It does NOT serialize the stack. On resume, `checkpoint_load()` creates a fresh stack `[Frame(block=workflow)]` and `advance()` fast-forwards through completed blocks by checking `exec_key in results_scoped`, re-applying `result_var` side effects via `_replay_skip()`. This approach is simpler and more robust than reconstructing block-path indices, since conditions and loop items are re-evaluated deterministically from restored state. Verify `workflow_hash` matches — refuse if source changed.

**Child runs**: each child run has its own checkpoint file in `{cwd}/.workflow-state/{child_run_id}/state.json`. Parent checkpoint includes `child_run_ids` list for tracking.

---

## Error Handling

| Scenario                         | Behavior                                                                                                                                       |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `status="failure"` from agent    | Record as failure. If inside RetryBlock → re-enter. Otherwise → mark failed, continue                                                          |
| Shell non-zero exit              | Auto-advanced internally with `status="failure"`. If inside RetryBlock → re-enter. Otherwise → mark failed, continue                           |
| `status="cancelled"` from relay  | Set `state.status = "cancelled"`, return `{"action": "cancelled"}`. Runner cleans up checkpoints and child runs                                |
| Strict ask_user — invalid answer | Server returns `ask_user` with `_retry_confirm: true`: "Try again? yes/no" (see Strict Validation below)                                       |
| Strict ask_user — retry "yes"    | Re-sends original question (fresh, no stacking)                                                                                                |
| Strict ask_user — retry "no"     | Cancels workflow: `{"action": "cancelled"}`                                                                                                    |
| Strict ask_user — retry garbage  | Re-sends "try again?" (loops until yes/no)                                                                                                     |
| Condition evaluation exception   | Catch, treat as `false` (skip block). Record warning                                                                                           |
| Unknown workflow name            | `start()` returns error                                                                                                                        |
| Bad run_id                       | `submit()` returns error                                                                                                                       |
| Wrong exec_key                   | `submit()` returns error with expected key                                                                                                     |
| Duplicate exec_key               | `submit()` skips recording, returns same next action                                                                                           |
| Submit after completed           | `submit()` returns error                                                                                                                       |
| Child run not completed          | `submit()` returns error if relay submits `status="success"` but child run hasn't finished (anti-fabrication). Bypassed for `status="failure"` |
| `cancel(run_id)`                 | Sets status to `"cancelled"`, removes checkpoint files, cleans up child runs. Returns `{"action": "cancelled"}`                                |
| Checkpoint write failure         | `submit()` still returns next action but includes `"warning": "checkpoint failed"`                                                             |
| Checkpoint load failure          | `start(resume_run_id=...)` returns error with details                                                                                          |
| Workflow source drift on resume  | `start(resume_run_id=...)` returns error: hash mismatch                                                                                        |

---

## Strict PromptStep Validation (Server-Side)

PromptStep has `strict: bool = True` by default. When strict, the server validates the user's answer against expected options. The relay agent is a **dumb pipe** — it passes raw answers through without interpretation or defaulting.

### 3-State Flow

```
┌─────────────────────────────┐
│ 1. Server sends original    │
│    ask_user (with options)  │
└──────────┬──────────────────┘
           │ user answers
           ▼
┌─────────────────────────────┐     valid
│ 2. Server validates answer  │────────────→ record result, advance
└──────────┬──────────────────┘
           │ invalid
           ▼
┌─────────────────────────────┐
│ 3. Server sends "try again? │
│    yes/no" (_retry_confirm) │◄───┐
└──────────┬──────────────────┘    │
           │                       │
     ┌─────┼──────┐                │
     │     │      │                │
    yes    no   other              │
     │     │      │                │
     │     │      └────────────────┘
     │     ▼
     │   cancel workflow
     │   {"action": "cancelled"}
     ▼
   goto 1 (re-send original question, fresh — no stacking)
```

### Implementation

In `apply_submit()`, before recording the result:

1. **Check `_retry_confirm` state** — `isinstance(state._last_action, AskUserAction) and state._last_action.retry_confirm` tracks whether the pending action is a "try again?" confirm
2. **If retry confirm**: match answer (case-insensitive) — `yes` re-sends original, `no` cancels, anything else re-sends "try again?"
3. **If original question**: validate `output` against options (template-substituted). For `confirm` type, valid = `["yes", "no"]`. Invalid → send "try again?" via `_build_retry_confirm()`

### No Stacking Guarantee

- "yes" on retry confirm calls `_build_ask_user_action(state, step=block)` — builds fresh from the PromptStep block
- `state._last_action` is fully overwritten to this fresh action (without `_retry_confirm`)
- Multiple invalid→retry→yes cycles always produce the same fresh original question

### Relay Agent Contract

The relay agent for `ask_user`:

- Always submits `status="success"` with the user's raw answer as `output`
- Never interprets, defaults, or substitutes answers
- If server returns `ask_user` with `_retry_confirm: true`, presents it the same way and submits the same way
- `status="cancelled"` is only for backwards compatibility (legacy relay agents)

---

## output_schema Validation

When LLMStep has `output_schema` (Pydantic model):

1. Action includes `json_schema` (JSON Schema dict) + `output_schema_name` so relay formats output correctly
2. On `submit()`, if `structured_output` provided → engine validates against the Pydantic model
3. If validation fails → `status` set to `"failure"` with validation error details
4. If inside RetryBlock → retry. Otherwise → recorded as failure
5. If `output` provided but not `structured_output` → engine attempts JSON parse + validate

---

## Context Passing to Subagents

Engine handles deterministic context (`{{results.X}}`, `{{variables.Y}}`). But the relay agent accumulates **situational context** (code it read, patterns it noticed, user preferences) that isn't in engine results.

**Two mechanisms:**

1. **`context_hint`** (automatic): The action includes `context_hint`. Relay protocol tells Claude: "Before launching the subagent, summarize relevant context from your conversation, guided by the hint. Prepend it as a `## Context` section to the prompt."

```python
LLMStep(name="implement", prompt="implement.md", isolation="subagent",
        context_hint="project structure, auth patterns, relevant files")
```

Agent tool prompt becomes: `[Claude's context summary] + [engine's prompt with {{results}} substituted]`

2. **Explicit prepare-context step** (precise control): Add an inline LLMStep before the subagent that produces structured context → engine includes it via `{{results.prepare.output}}`:

```python
GroupBlock(name="step-1", blocks=[
    LLMStep(name="prepare", prompt="prepare-context.md"),  # inline
    LLMStep(name="execute", prompt="execute.md", isolation="subagent"),
    # execute.md contains {{results.prepare.output}}
])
```

---

## Testing Infrastructure

### Unit tests (`tests/test_workflow_state_machine.py`)

Tests `advance()` + `apply_submit()` for all 9 block types: shell, prompt, LLM, group, loop, retry, conditional, subworkflow, parallel. Also covers exec_key validation, idempotency, child runs, checkpointing, dry_run, nested combos, and strict PromptStep validation (3-state flow, retry confirm, cancellation, no stacking across multiple cycles).

### Integration tests (`tests/test_workflow_mcp_tools.py`)

Tests tool functions directly (no transport): start→submit loop, list_workflows, error cases, checkpoint persistence.

### Adapted tests (`tests/test_workflow_engine.py`)

Workflow definition loading, template substitution, condition evaluation, prompt loading, output schemas, prompt file validation.

### E2E test workflow (`skills/test-workflow/`)

18-phase workflow exercising all 9 block types. Phases 10-16 are gated by `mode=thorough` or `enable_llm=True`.

---

## Files

| File                    | Lines | Purpose                                                                                                                 |
| ----------------------- | ----- | ----------------------------------------------------------------------------------------------------------------------- |
| `scripts/types.py`      | ~280  | Block type definitions, WorkflowContext, StepResult                                                                     |
| `scripts/protocol.py`   | ~170  | Typed Pydantic models for all 8 action types (ActionBase, ShellAction, etc.), PROTOCOL_VERSION, action_to_dict()        |
| `scripts/core.py`       | ~110  | Frame, RunState, AdvanceResult type alias                                                                               |
| `scripts/utils.py`      | ~210  | Template substitution, condition evaluation, schema validation, workflow hashing                                        |
| `scripts/actions.py`    | ~160  | Action response builders (_build_\*\_action), returns typed protocol models                                             |
| `scripts/checkpoint.py` | ~140  | Durable checkpoint save/load                                                                                            |
| `scripts/state.py`      | ~620  | State machine core: advance(), apply_submit(), pending_action()                                                         |
| `scripts/runner.py`     | ~540  | FastMCP server: start, submit, next, cancel, list_workflows, status + internal shell execution + child run verification |
| `scripts/loader.py`     | ~76   | Dynamic workflow discovery and loading via exec()                                                                       |

---

## dry_run Mode

`start(workflow, variables, dry_run=True)`:

- Engine walks through all blocks, evaluating conditions
- Returns ALL actions as a flat list in one response (no submit needed)
- Each action has `dry_run: true` flag
- Skips blocks whose conditions are false
- Template substitution uses placeholder values for unresolved `{{results.X}}`
- Subagent/parallel blocks expanded inline (shows what child runs WOULD contain)
- Child runs not allocated (no state files created)

---

## Internal Shell Execution

Shell steps are executed internally by the MCP server — they never appear as actions in the relay protocol. This keeps the agent's context window clean of imperative shell output.

### Action Visibility

| Action                | Handled by                      | Visible to agent? |
| --------------------- | ------------------------------- | ----------------- |
| `shell`               | MCP server (`subprocess.run()`) | No                |
| `ask_user`            | Agent → user                    | Yes               |
| `prompt`              | Agent → LLM                     | Yes               |
| `subagent`            | Agent → Agent tool              | Yes               |
| `parallel`            | Agent → multiple Agents         | Yes               |
| `completed` / `error` | Terminal                        | Yes               |

### Implementation

**`_execute_shell(command, cwd)`**: Runs `subprocess.run(shell=True, capture_output=True, text=True, timeout=120, cwd=cwd)`. Best-effort JSON parse of stdout for `structured_output`.

**`_auto_advance(state, action, children)`**: When `advance()` or `apply_submit()` returns a `shell` action, runner executes it internally and loops until a non-shell action is produced. Accumulates `_shell_log` list on the final returned action. Updates `state._last_action` so `next()` returns the correct non-shell action.

Both `start()` and `submit()` wrap their results with `_auto_advance()`. Child states are also auto-advanced (child's first action may be shell).

**Trust boundary**: Shell commands execute inside the MCP server process, automatically, potentially many in a row. Security is enforced at three layers: workflow loading restrictions, OS-level sandbox, and path validation (see Security section).

---

## Security

The workflow engine executes code automatically — ShellStep commands run via `subprocess.run()`, and Python `workflow.py` files are loaded via `exec()`. Both happen inside the MCP server without user confirmation. This section describes the threat model and mitigation layers.

### Threat Model

Two threats:

1. **Prompt-injected agent**: Agent writes a malicious workflow in the project's `.workflows/` directory and calls `start()` to execute it. Attack vectors: arbitrary Python via `exec()` of `workflow.py`, or destructive ShellStep commands.

2. **Malicious/buggy plugin**: User installs a marketplace plugin containing a harmful `workflow.py`. The engine `exec()`s it from the trusted `~/.claude/plugins` path.

Note: the agent already has Write and Bash tools via Claude Code. The workflow engine does not add fundamentally new capabilities, but MCP tool calls may be auto-approved in some configurations, bypassing the user confirmation that Bash tool normally requires.

### Layer 1: Process Sandbox

The MCP server process re-execs itself inside an OS-level sandbox at startup (`serve.py`). This restricts the **entire process** — including `exec()` of plugin `workflow.py` files, all Python code, and all subprocess calls.

- **macOS**: `sandbox-exec -p <profile>` (Apple Seatbelt). Profile denies `file-write*` everywhere except `cwd` and `/tmp`. Denies reads to `~/.ssh`, `~/.aws`, `~/.gnupg`.
- **Linux**: `bwrap` (bubblewrap). Read-only bind of `/`, writable binds for `cwd` and `/tmp`.
- **Other / unavailable**: Process runs unsandboxed; per-subprocess sandbox in `_execute_shell()` is used as fallback.

This protects against threat #2 (malicious plugins): even if a plugin's `workflow.py` contains `import os; os.system(...)`, the sandbox restricts what it can do. Write access is limited to the project directory and `/tmp`.

All paths in the Seatbelt profile are resolved through `Path.resolve()` to handle symlinks (e.g., macOS `/tmp` → `/private/tmp`).

**macOS**: Seatbelt is built-in, no installation needed.

**Linux / WSL**: Install bubblewrap:

```bash
# Debian / Ubuntu / WSL
sudo apt install bubblewrap

# Fedora / RHEL
sudo dnf install bubblewrap

# Arch
sudo pacman -S bubblewrap
```

Without bubblewrap, Linux processes run unsandboxed (a warning is logged at startup).

To disable the sandbox (e.g., in containers or CI):

```
MEMENTO_SANDBOX=off
```

### Why not YAML-only for project workflows?

YAML workflows can reference companion `.py` modules (for `when_fn`, `output_schema`) via `exec()` — the same mechanism as `workflow.py`. Restricting project workflows to YAML-only would be security theater: an attacker who can write `workflow.yaml` can also write `schemas.py` next to it, which gets `exec()`'d at load time. The OS-level sandbox (Layer 1) is the real security boundary.

### Environment Variables Summary

| Variable | Default | Purpose |
|---|---|---|
| `MEMENTO_SANDBOX` | `auto` | Process + shell sandbox. `off` disables both. Enabled on macOS and Linux (with bwrap) |

---

## Path Discovery

- **Engine root**: `Path(__file__).resolve().parents[1]` (runner.py → scripts → memento-workflow)
- **Project root**: `cwd` param in `start()`, defaults to process working directory
- **Workflow search**: `{engine_root}/skills/*/workflow.{yaml,py}` + `{project_root}/.workflows/*/workflow.{yaml,py}` + explicit `workflow_dirs`

MCP server reads engine-bundled workflows, project workflows, and any extra directories passed via `workflow_dirs` (e.g., memento passes its skill dirs). All paths support both Python and YAML workflows.

---

## Plugin MCP Registration

The MCP server is declared in `.mcp.json` at the plugin root:

```json
{
  "mcpServers": {
    "memento-workflow": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "${CLAUDE_PLUGIN_ROOT}",
        "${CLAUDE_PLUGIN_ROOT}/serve.py"
      ],
      "cwd": "${CLAUDE_PLUGIN_ROOT}"
    }
  }
}
```

`uv run --project` reads `pyproject.toml` at the plugin root and auto-installs dependencies (`mcp[cli]`, `pydantic`) into a managed venv. `${CLAUDE_PLUGIN_ROOT}` resolves to the plugin's absolute path — works both in development (`--plugin-dir`) and when installed from the marketplace (cached to `~/.claude/plugins/cache/`).

---

## Creating Workflows

> **YAML format available**: Workflows can also be defined in `workflow.yaml` using a concise DSL. See [YAML-DSL.md](YAML-DSL.md) for the full reference. The engine discovers both formats automatically (`workflow.yaml` is preferred over `workflow.py` if both exist).

### Workflow Packages

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
        # Subagent isolation for multi-step groups
        GroupBlock(
            name="implement",
            isolation="subagent",
            model="sonnet",
            context_hint="project structure and coding patterns",
            blocks=[
                LLMStep(name="code", prompt="02-code.md", tools=["Read", "Write", "Edit"]),
                ShellStep(name="test", command="uv run pytest"),
            ],
        ),
    ],
)
```

### Block Types Reference

- `LLMStep` — prompt action (inline or subagent). Fields: `prompt` (path relative to prompt_dir), `tools`, `model`, `output_schema`
- `GroupBlock` — sequential composition; `isolation="subagent"` runs all inner steps in shared context. Fields: `blocks`, `model`
- `ParallelEachBlock` — run template concurrently for each item (each lane = subagent). Fields: `parallel_for` (dotpath), `template`, `item_var`, `max_concurrency`, `merge_policy`, `model`
- `LoopBlock` — iterate over items from context. Fields: `loop_over` (dotpath), `loop_var`, `blocks`
- `RetryBlock` — repeat until condition met or max attempts. Fields: `until` (callable), `max_attempts`, `blocks`
- `ConditionalBlock` — multi-way branching: first matching branch wins, else default. Fields: `branches` (list of `Branch`), `default`
- `SubWorkflow` — invoke another workflow by name. Fields: `workflow`, `inject`
- `ShellStep` — subprocess executed internally by MCP server (never visible to relay); optional `result_var` parses JSON stdout into variables
- `PromptStep` — interactive checkpoint: ask user a question. Fields: `prompt_type` ("confirm"/"choice"/"input"), `message`, `options`, `default`, `result_var`, `strict`

### Common Fields (BlockBase)

All blocks share: `name`, `key` (stable identity, defaults to name), `condition` (callable, skip if false), `isolation` ("inline"/"subagent"), `context_hint`

### PromptStep Syntax

```python
PromptStep(
    name="strategy",              # display name
    key="strategy",               # stable ID for result lookup (defaults to name)
    prompt_type="choice",         # "confirm" | "choice" | "input"
    message="Choose strategy:",   # supports {{variable}} substitution
    options=["Resume", "Merge", "Fresh"],
    default="Resume",
    result_var="strategy",        # store answer in ctx.variables["strategy"]
    strict=True,                  # server-side validation (default: True)
    condition=lambda ctx: ...,    # optional skip condition
)
```

When `strict=True` (default), the server validates answers against `options` (or `["yes", "no"]` for confirm). Invalid answers trigger the 3-state retry flow (see Strict PromptStep Validation). Set `strict=False` for open-ended input where any answer is acceptable.

### Step Identity and Results

Each leaf execution is recorded with a deterministic **scoped execution key** (`exec_key`) derived from the execution path:

- `ctx.results_scoped` stores **all** leaf results by `exec_key` (canonical, collision-free)
- `ctx.results` stores a deterministic "last result" convenience view by name

### Available Workflows

Deployed workflows (discovered from `.workflows/` in the project root):

| Workflow           | Description                                                                        |
| ------------------ | ---------------------------------------------------------------------------------- |
| `development`      | Full TDD workflow: classify, explore, plan, test-first implement, review, complete |
| `code-review`      | Parallel competency-based code review with synthesis                               |
| `testing`          | Run tests with coverage analysis                                                   |
| `process-protocol` | Execute protocol steps with QA checks and commits                                  |

Plugin-only workflows (in `skills/`, invoked via `workflow_dirs`):

| Workflow             | Description                                                      |
| -------------------- | ---------------------------------------------------------------- |
| `create-environment` | Generate Memory Bank environment (Fresh/Merge/Resume strategies) |
| `update-environment` | Selective update with change detection and 3-way merge           |

### Variables

Pass variables via the `variables` parameter in `start()`:

| Variable         | Workflow          | Description                          |
| ---------------- | ----------------- | ------------------------------------ |
| `task`           | development       | Task description                     |
| `mode`           | development       | "standalone" (default) or "protocol" |
| `protocol_dir`   | process-protocol  | Path to protocol directory           |
| `plugin_root`    | create/update-env | Path to memento plugin root          |
| `plugin_version` | create/update-env | Plugin version for commit metadata   |

---

## Limitations

- **Workflow edits between stop→resume**: Refused by design (strict drift policy)
- **No rollback**: Side effects from prior steps are irreversible
- **No subagent from child**: Inside a subagent, everything runs inline (Claude Code limitation)
- **Parallel requires isolation**: Each parallel lane is always a subagent
