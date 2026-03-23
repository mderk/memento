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

| Tool             | Purpose                                                                                                                                                               |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `start`          | Start workflow or resume from checkpoint. `resume` follows resume-or-restart semantics: loads if valid, falls back to fresh with warning on drift/corruption/terminal |
| `submit`         | Submit result for an `exec_key`, return next action. Idempotent — same `(run_id, exec_key)` twice returns same result. Works on parent and child run_ids              |
| `next`           | Re-fetch current pending action without mutation. Recovery tool                                                                                                       |
| `cancel`         | Cancel workflow, clean up checkpoint files and child runs                                                                                                             |
| `list_workflows` | Discover workflows from plugin skills + project `.workflows/` + extra dirs                                                                                            |
| `status`         | Get current run state for debugging (stack depth, results count, child runs)                                                                                          |
| `open_dashboard` | Launch web dashboard on a free port                                                                                                                                   |
| `cleanup_runs`   | Remove old `.workflow-state/` directories by age, status, or count                                                                                                    |

See `scripts/runner.py` for full parameter signatures.

### Protocol Invariants

- **`exec_key` is the only submit identifier** — deterministic, collision-free across loops/retries/parallel
- **Idempotent submit**: same `(run_id, exec_key)` twice returns same next action (no double-recording)
- **Strict validation**: if relay submits wrong exec_key, server returns error with expected key
- **Durable state**: every submit atomically checkpoints to the run's checkpoint directory (resolved by `checkpoint_dir_from_run_id`)
- **Protocol version**: every action includes `protocol_version: 1` for future compat. Checkpoint format has separate `checkpoint_version`
- **Child runs for isolation**: subagent relay, parallel lanes, and all SubWorkflows get their own composite `child_run_id` (`parent>child`) — each child has its own `pending_exec_key`, no concurrent submit conflicts on parent
- **Inline SubWorkflow transparency**: inline SubWorkflow child actions are returned directly to the relay with the child's `run_id`. Relay processes them as normal (prompt/ask_user). On child completion, submit cascades to parent — relay sees the `run_id` switch transparently
- **Subtree eviction**: terminal runs are evicted as complete subtrees — a parent and all its descendants must be terminal before any are removed. This prevents dangling parent→child references in long-running servers
- **Child run verification** (`_verify_child_runs`): before the parent accepts a subagent or parallel submit with `status="success"`, the runner verifies all child runs have reached `"completed"` or `"halted"` status. This prevents the relay agent from fabricating results without actually running the child relay loop. If verification fails, the parent returns an error with instructions to complete the child runs first
- **Halt propagation**: if any child run is halted, the halt propagates to the parent automatically on submit. The parent's `halted_at` shows the propagation chain: `parent_exec_key←child_halted_at`

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
- Parallel lanes are always subagents (parallel requires isolation)
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
 "context_files": [".workflow-state/<run_id>/artifacts/plan/context_results.json"],
 "result_dir": ".workflow-state/<run_id>/artifacts/plan",
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
 "totals": {"duration": 12.5, "step_count": 8, "cost_usd": 0.042,
            "steps_by_type": {"llm_step": 3, "shell": 5}},
 "_display": "Workflow completed"}

# Cancellation (from strict validation "no" or status="cancelled"):
{"action": "cancelled", "run_id": "...",
 "_display": "Workflow cancelled by user"}

# Halted (from halt directive on a block or halt_on_exhaustion on retry):
{"action": "halted", "run_id": "...", "reason": "Step 3 failed verification",
 "halted_at": "mark-blocked",
 "_display": "Workflow halted at [mark-blocked]: Step 3 failed verification"}

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
    - Shell steps are already executed internally — sub-agent never sees them
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

Each parallel lane = one child run with its own composite `run_id`:

1. Engine resolves parallel items, allocates `child_run_id` per lane
2. Children are auto-advanced in parallel via `ThreadPoolExecutor` (capped at 16 workers, thread-safe `_runs` dict access via `_runs_lock`)
3. **Fast path** (shell-only lanes): if all children reach terminal state during auto-advance, engine auto-submits the parent and skips the relay entirely. The relay sees the parent's next action (or `completed`), not a `ParallelAction`. Shell logs from all lanes are merged in lane-index order. Disable with `MEMENTO_PARALLEL_AUTO_ADVANCE=off`
4. **Relay path** (mixed lanes): returns `{"action": "parallel", "lanes": [...]}`. Parent launches N Agents simultaneously (one per lane). Each agent runs sub-relay on its `child_run_id`: `next()` → execute → `submit()` → ... → `completed`. Parent collects results, calls `submit(parent_run_id, parallel_exec_key, output=combined_results)`
5. Engine verifies all child runs completed (`_verify_child_runs`), then advances past parallel block. If any lane is incomplete, returns error action
6. Terminal meta (`meta.json` with totals/cost/duration) is written for each child and the parent via `_write_terminal_meta()`

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
    run_id: str                   # composite for children: "parent>child" (12-hex segments)
    # parent_run_id: derived property — run_id.rsplit(">", 1)[0] if ">" in run_id else None
    ctx: WorkflowContext
    stack: list[Frame]
    registry: dict[str, WorkflowDef]
    status: Literal["running", "waiting", "completed", "halted", "error"]
    pending_exec_key: str | None  # expected next submit key
    child_run_ids: list[str]      # active child runs (composite IDs)
    wf_hash: str                  # for drift detection on resume
    protocol_version: int = 1
    checkpoint_dir: Path | None
    checkpoint_version: int = 1   # separate from protocol_version, for checkpoint format changes
    workflow_name: str            # for meta.json; target workflow for SubWorkflow children
    started_at: str               # ISO 8601 timestamp
    warnings: list[str]
    spawn_exec_key: str = ""      # parent exec_key that created this SubWorkflow child
    is_resumed: bool = False      # runtime flag, not persisted
```

### advance() — the heart

Returns `(ActionBase, list[RunState])` — action model + any newly created child RunStates. All actions are typed Pydantic models (see `protocol.py`), serialised to dicts at the wire boundary via `action_to_dict()`.

1. `resume_only` blocks: skipped without recording on fresh run (`is_resumed=False`); executed on resume
2. Top frame's current child → check block type:
    - **SubWorkflow** (any isolation) → always creates child run with composite ID (`parent>child`). Routes by isolation:
        - `"subagent"` + not already a child → emit `subagent` with `relay: true`
        - `"inline"` (default) → advance child, return child's action directly. Shell-only children auto-complete transparently. On submit, if child completes, engine cascades: merges results, advances parent, returns parent's next action
    - `"subagent"` LLMStep → emit `subagent` with `relay: false`
    - `"subagent"` Group/Loop → create child RunState, emit `subagent` with `relay: true`
    - **If child run**: `subagent` isolation on LLMStep/GroupBlock → downgraded to `inline` with warning
3. If `"inline"` container (Group/Loop/Retry/Conditional) → push frame, recurse
4. If ParallelEachBlock → create child RunState per lane (composite IDs), emit `parallel`
5. Frame exhausted → pop (loop/retry may re-enter), continue
6. Stack empty → "completed"

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
- `start()` can accept `resume` to reload from checkpoint
- `cancel()` cleans up checkpoint directory

**Replay-based resume**: The checkpoint stores `results_scoped` (all completed step results) and `variables` — the deterministic outputs of all completed steps. It does NOT serialize the stack. On resume, `checkpoint_load()` creates a fresh stack `[Frame(block=workflow)]` and `advance()` fast-forwards through completed blocks by checking `exec_key in results_scoped`, re-applying `result_var` side effects via `_replay_skip()`. This approach is simpler and more robust than reconstructing block-path indices, since conditions and loop items are re-evaluated deterministically from restored state. Verify `workflow_hash` matches — refuse if source changed. `checkpoint_version` validated separately from `protocol_version` — mismatch triggers fresh restart with warning.

**Ephemeral keys**: `resume_only` steps with `resume_once=False` are excluded from checkpoint (`_ephemeral_keys` set). They re-execute on every resume — useful for context recovery prompts.

**Composite run IDs and child checkpoint layout**: all child runs (SubWorkflow, parallel lanes) use composite IDs: `parent_id>child_hex` (12-hex segments separated by `>`). `parent_run_id` is derived from the composite ID (not stored). Filesystem layout uses `children/` directory level:

```
run_id: "aaa111bbb222"               → .workflow-state/aaa111bbb222/state.json
run_id: "aaa111bbb222>ccc333ddd444"  → .workflow-state/aaa111bbb222/children/ccc333ddd444/state.json
```

`checkpoint_dir_from_run_id(cwd, run_id)` is the single mapping function (defined in checkpoint.py). Validates segments against path traversal.

**Child run loading on resume**: `checkpoint_load_children()` scans `children/` for SubWorkflow children (keyed by `spawn_exec_key`) and parallel lane children (keyed by `parallel_block_name`). Recurses for grandchildren (depth-bounded, default 10).

**Resume semantics**: relays must persist the **root** parent `run_id` for resume. Inline SubWorkflow actions carry the child's composite `run_id` — this is for submit routing only, not for `start(resume=...)`. The root run_id is the one without `>` returned by the initial `start()` call.

**Recursive child loading**: `checkpoint_load_children()` recurses for both SubWorkflow and parallel lane children, loading grandchildren at any depth (bounded by `max_depth`, default 10). This ensures inline SubWorkflows inside parallel lanes are properly resumed.

---

## Error Handling

| Scenario                         | Behavior                                                                                                                                                                |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `status="failure"` from agent    | Record as failure. If inside RetryBlock → re-enter. Otherwise → mark failed, continue                                                                                   |
| Shell non-zero exit              | Auto-advanced internally with `status="failure"`. If inside RetryBlock → re-enter. Otherwise → mark failed, continue                                                    |
| `status="cancelled"` from relay  | Set `state.status = "cancelled"`, return `{"action": "cancelled"}`. Runner cleans up checkpoints and child runs                                                         |
| Strict ask_user — invalid answer | Server returns `ask_user` with `_retry_confirm: true`: "Try again? yes/no" (see Strict Validation below)                                                                |
| Strict ask_user — retry "yes"    | Re-sends original question (fresh, no stacking)                                                                                                                         |
| Strict ask_user — retry "no"     | Cancels workflow: `{"action": "cancelled"}`                                                                                                                             |
| Strict ask_user — retry garbage  | Re-sends "try again?" (loops until yes/no)                                                                                                                              |
| Condition evaluation exception   | Catch, treat as `false` (skip block). Record warning                                                                                                                    |
| Unknown workflow name            | `start()` returns error                                                                                                                                                 |
| Bad run_id                       | `submit()` returns error                                                                                                                                                |
| Wrong exec_key                   | `submit()` returns error with expected key                                                                                                                              |
| Duplicate exec_key               | `submit()` skips recording, returns same next action                                                                                                                    |
| Submit after completed           | `submit()` returns error                                                                                                                                                |
| Child run not completed          | `submit()` returns error if relay submits `status="success"` but child run hasn't finished (anti-fabrication). Bypassed for `status="failure"`                          |
| `cancel(run_id)`                 | Sets status to `"cancelled"`, removes checkpoint files, cleans up child runs. Returns `{"action": "cancelled"}`                                                         |
| Block `halt` directive           | After block executes (status=success only), workflow halts: `{"action": "halted", "reason": "...", "halted_at": "exec_key"}`. Checkpoint preserved for potential resume |
| RetryBlock `halt_on_exhaustion`  | When max_attempts exhausted without `until` becoming true, halts the workflow (same as `halt` but triggered by exhaustion)                                              |
| Child run halted                 | If a subagent or parallel lane child run halts, the halt propagates to the parent on submit. `halted_at` shows propagation chain: `parent_key←child_key`                |
| Submit after halted              | `submit()` returns error: "Workflow is halted"                                                                                                                          |
| Checkpoint write failure         | `submit()` still returns next action but includes `"warning": "checkpoint failed"`                                                                                      |
| Checkpoint load failure          | `start(resume=...)` marks old run as cancelled in meta.json, starts fresh run with warning. First action includes `warnings` list                                       |
| Checkpoint version mismatch      | `start(resume=...)` detects `checkpoint_version` differs → marks old run cancelled, starts fresh with warning                                                           |
| Workflow source drift on resume  | `start(resume=...)` marks old run as cancelled, starts fresh with warning (same as checkpoint load failure)                                                             |
| Resume terminal run              | `start(resume=...)` where run is completed/halted/error → starts fresh with warning. `resume` means "resume-or-restart"                                                 |
| Inline SubWorkflow child error   | If child's action is `error`, returned to relay (not suppressed). Parent remains in `waiting` status at the SubWorkflow step                                            |

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

| File                          | Purpose                                                                                             |
| ----------------------------- | --------------------------------------------------------------------------------------------------- |
| `scripts/runner.py`           | FastMCP server: MCP tools, run store, auto-advance, parallel fast path                              |
| `scripts/utils.py`            | Template substitution, condition evaluation, schema validation, workflow hashing                    |
| `scripts/engine/types.py`     | Block type definitions, WorkflowContext, StepResult                                                 |
| `scripts/engine/protocol.py`  | Typed Pydantic models for all 9 action types, PROTOCOL_VERSION, action_to_dict()                    |
| `scripts/engine/core.py`      | Frame, RunState, AdvanceResult type alias                                                           |
| `scripts/engine/state.py`     | State machine core: advance(), apply_submit(), pending_action()                                     |
| `scripts/engine/actions.py`   | Action response builders (_build_\*\_action), returns typed protocol models                         |
| `scripts/engine/parallel.py`  | ParallelEachBlock execution, nested parallelism, batching                                           |
| `scripts/engine/subworkflow.py` | SubWorkflow block handling, inline and subagent modes                                             |
| `scripts/engine/child_runs.py`| Child run creation and management                                                                   |
| `scripts/infra/checkpoint.py` | Durable checkpoint save/load, child run loading, composite ID handling                              |
| `scripts/infra/artifacts.py`  | Artifact persistence: exec_key path mapping, prompt/shell/LLM output artifacts                      |
| `scripts/infra/compiler.py`   | YAML workflow compiler                                                                              |
| `scripts/infra/loader.py`     | Dynamic workflow discovery and loading via exec()                                                   |
| `scripts/infra/sandbox.py`    | OS-level sandboxing (Seatbelt/bubblewrap) with audit warning                                        |
| `scripts/infra/shell_exec.py` | Shell command execution                                                                             |
| `scripts/infra/cleanup.py`    | Cleanup old workflow state directories (scan, filter, remove)                                       |

---

## dry_run Mode

`start(workflow, variables, dry_run=True)` returns a single `DryRunCompleteAction` — no relay loop needed.

### How it works

1. Engine creates a `RunState` with `dry_run=True` and no `checkpoint_dir`
2. `_collect_dry_run(state)` installs a `DryRunTreeHook` on `state._advance_hook`
3. `advance()` calls `hook.on_block_enter()` / `hook.on_block_exit()` — the hook builds a `DryRunNode` tree in sync with the frame stack. The state machine has no knowledge of the tree structure.
4. Results are auto-recorded (via `_auto_record_dry_run()`) so `advance()` can proceed
5. For SubWorkflow/ParallelEach, child trees are collected recursively and attached to the parent node

### No side effects

- No checkpoint files, meta.json, or artifact files written
- No `_store_run()` — state is never stored in the in-memory registry
- `checkpoint_dir` is set to `None`

### Response format

```json
{
  "action": "dry_run_complete",
  "run_id": "...",
  "tree": [
    {
      "exec_key": "setup/install",
      "type": "shell",
      "name": "install",
      "detail": "npm install",
      "children": []
    }
  ],
  "summary": {
    "step_count": 5,
    "steps_by_type": {"shell": 3, "prompt": 1, "llm": 1}
  }
}
```

### Tree structure

- `DryRunNode.type`: `Literal["shell", "llm", "prompt", "parallel", "parallel_each", "loop", "retry", "group", "subworkflow", "conditional"]`
- `DryRunNode.detail`: command for shell, prompt name for llm, message for prompt
- Tree is built by `DryRunTreeHook` (`engine/hooks.py`) via `on_block_enter`/`on_block_exit` calls from `advance()`

### Block behavior

- **Conditionals**: first matching branch is taken; unmatched branches are skipped
- **Loops**: expanded for each item; uses template substitution with current loop variable
- **Parallel**: lanes expanded inline (no child runs created)
- **Subworkflows**: recursively expanded via the advance loop
- **Groups**: produce nested exec_keys (e.g., `grp/step1`)

---

## Internal Shell Execution

Shell steps are executed internally by the MCP server — they never appear as actions in the relay protocol. This keeps the agent's context window clean of imperative shell output.

### Action Visibility

| Action                           | Handled by                      | Visible to agent? |
| -------------------------------- | ------------------------------- | ----------------- |
| `shell`                          | MCP server (`subprocess.run()`) | No                |
| `ask_user`                       | Agent → user                    | Yes               |
| `prompt`                         | Agent → LLM                     | Yes               |
| `subagent`                       | Agent → Agent tool              | Yes               |
| `parallel`                       | Agent → multiple Agents         | Yes               |
| `completed` / `halted` / `error` | Terminal                        | Yes               |

### Implementation

**`_execute_shell(command, cwd)`**: Runs `subprocess.run(shell=False, capture_output=True, text=True, timeout=120, cwd=cwd)`. Best-effort JSON parse of stdout for `structured_output`. If the ShellStep specifies `stdin` (a dotpath), the resolved content is piped via `input=` parameter (dicts/lists are JSON-serialized).

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

| Variable                        | Default | Purpose                                                                                            |
| ------------------------------- | ------- | -------------------------------------------------------------------------------------------------- |
| `MEMENTO_SANDBOX`               | `auto`  | Process + shell sandbox. `off` disables both. Enabled on macOS and Linux (with bwrap)              |
| `MEMENTO_PARALLEL_AUTO_ADVANCE` | `on`    | Shell-only parallel lanes auto-advance internally. `off` forces relay path for all parallel blocks |

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

See [README.md](../README.md) for workflow structure, building examples, and block type reference. YAML format documented in [YAML-DSL.md](YAML-DSL.md).

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
- **No nested subagent isolation**: Inside a subagent, `isolation: subagent` on LLMStep/GroupBlock is downgraded to inline (Claude Code cannot spawn sub-sub-agents). Parallel blocks work normally
- **Mixed parallel lanes require relay agents**: Shell-only lanes auto-advance internally via ThreadPoolExecutor; lanes with LLM/prompt steps still route through Claude Code Agent tool
