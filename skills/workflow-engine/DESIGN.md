# Workflow Engine — Design Document

## Overview

The workflow engine executes imperative workflows defined as Python dataclasses. It supports 9 block types (ShellStep, PromptStep, LLMStep, GroupBlock, ParallelEachBlock, LoopBlock, RetryBlock, SubWorkflow, ConditionalBlock) with deterministic execution, checkpoint/resume, and interactive user prompts.

LLM steps are executed via the Claude Agent SDK, which spawns inner Claude Code CLI subprocesses. This creates a two-layer architecture where the engine (outer process) must mediate between the workflow definition and the inner CLI's behavior.

---

## Interactivity Model

### Two kinds of user interaction

| Type                    | Mechanism       | When                                          | Example                                     |
| ----------------------- | --------------- | --------------------------------------------- | ------------------------------------------- |
| **Planned checkpoints** | `PromptStep`    | Workflow author defines where input is needed | "Strategy A/B/C?", "Proceed with 35 files?" |
| **Emergent questions**  | `ask_user` tool | LLM decides at runtime that it needs input    | "Which test framework do you use?"          |

### PromptStep flow

```
Engine → IOHandler.prompt(key, message, options)
  ├── StdinIOHandler  → stdin/stdout (terminal)
  ├── PresetIOHandler → return preset answer or raise StopForInput
  └── StopIOHandler   → return preset answer or raise StopForInput
```

On `StopForInput`: engine saves checkpoint to `.workflow-state/<run_id>/checkpoint.json`, prints `workflow_question` JSON block with resume command, exits.

### ask_user flow (LLMStep)

```
Engine spawns inner CLI via SDK
  → Inner CLI runs LLM
    → LLM calls mcp__engine__ask_user tool
      → SDK routes through can_use_tool callback
        → If StopIOHandler + no preset answer:
            capture question → deny+interrupt → engine raises StopForInput
        → If preset answer exists:
            allow → MCP tool handler returns answer to LLM
```

---

## LLM Step Execution — Detailed Flow

### Component stack

```
┌─────────────────────────────────────────────────────────┐
│ Claude Code (parent session)                            │
│   └─ runs workflow engine as a skill (python process)   │
│       └─ engine.py: execute_llm_step()                  │
│           └─ Claude Agent SDK: query()                  │
│               └─ Inner Claude Code CLI (subprocess)     │
│                   └─ LLM generates text + tool calls    │
│                       └─ SDK routes tool calls back     │
│                           └─ can_use_tool callback      │
│                           └─ MCP server (ask_user)      │
└─────────────────────────────────────────────────────────┘
```

### Step-by-step for `execute_llm_step`

1. **Condition check**: if `step.condition` returns False → skip, record `StepResult(status="skipped")`
2. **Dry-run check**: if `ctx.dry_run` → return placeholder result
3. **Resume cache check**: if `exec_key` found in `ctx.injected_results_scoped` → return cached result
4. **Prepare SDK options**:
    - `allowed_tools`: step's tool list with `"ask_user"` → `"mcp__engine__ask_user"`
    - `cwd`: workflow working directory
    - `setting_sources`: `["user", "project", "local"]` — loads user's Claude Code settings
    - `model`: step-specified model (e.g., "haiku")
    - `output_format`: JSON schema if `output_schema` declared
5. **Build MCP server**:
    - If step has `ask_user` → full MCP server with `ask_user` tool handler
    - Otherwise → noop MCP server (empty, no tools) — **required** to keep stdin open
6. **Build `can_use_tool` callback**: programmatic permission gatekeeper
7. **Wrap prompt as async generator** (`_as_stream`) — required for streaming mode
8. **Call `query(prompt, options)`** — SDK spawns inner CLI
9. **Iterate `async for message in query(...)`** — collect `ResultMessage`
10. **Post-query check**: if `capture` has a question → raise `StopForInput`
11. **Record result** → `StepResult` with output, structured_output, cost, duration

### Step-by-step for `execute_llm_segment` (GroupBlock)

Same as above but uses `ClaudeSDKClient` context manager for a persistent session:

```python
async with ClaudeSDKClient(options) as client:
    for step in steps:
        await client.query(prompt)
        async for message in client.receive_response():
            ...
```

All steps in the segment share one inner CLI session, allowing conversational context to flow between steps.

---

## Permission Control — `can_use_tool` Callback

### Current implementation

```python
def _build_can_use_tool(*, allowed_tools, capture, io_handler):
    allowed_set = set(allowed_tools)

    async def _guard(tool_name, tool_input, _context):
        # 1. ask_user interception (stop/resume)
        if tool_name == "mcp__engine__ask_user" and capture is not None:
            # ... capture question, deny+interrupt ...

        # 2. Name-based allow
        if tool_name in allowed_set:
            return PermissionResultAllow()

        # 3. Deny everything else
        return PermissionResultDeny(message="...", interrupt=False)

    return _guard
```

### How the SDK uses `can_use_tool`

When `can_use_tool` is provided to `ClaudeAgentOptions`, the SDK automatically sets `--permission-prompt-tool stdio` on the inner CLI. This tells the inner CLI to route **all** permission requests through the stdio control protocol instead of applying its own permission rules.

**Critical consequence**: the `can_use_tool` callback becomes the **sole gatekeeper** for all tool access. The inner CLI's own permission settings (from `settings.local.json`, project `.claude/settings.json`, etc.) are bypassed for permission decisions — they still load but don't auto-approve anything.

### Noop MCP server requirement

The SDK only keeps stdin open (for the bidirectional control protocol) when `sdk_mcp_servers` is non-empty or hooks are present. Without an MCP server, the SDK closes stdin after the prompt generator yields, which makes `can_use_tool` non-functional (the inner CLI can't send permission requests back).

Solution: `_build_noop_mcp_server()` creates an empty MCP server with no tools. This keeps the control channel alive without exposing any tools.

### SDK stdin lifecycle — why noop MCP server is required

Discovery path: `can_use_tool` callback was never called despite being configured. Root cause found in SDK source (`.venv/.../claude_agent_sdk/_internal/query.py`, lines 570-603):

```python
# SDK's stream_input() function:
async def stream_input(self):
    async for msg in self._input:
        yield msg
    # After generator exhausts:
    if self.sdk_mcp_servers or has_hooks:
        await asyncio.Event().wait()  # keeps stdin open
    # otherwise: function returns, stdin closes
```

The bidirectional control protocol (used by `can_use_tool`, MCP server communication) runs over the same stdin pipe. When stdin closes, the inner CLI cannot send permission requests back to the SDK.

**Failed fix**: making `_as_stream` block with `await asyncio.Event().wait()` — caused deadlock. SDK's task group runs `stream_input` as one task; if the async generator never finishes, the entire task group hangs because `stream_input` is in the same gather as the response reader.

**Working fix**: `_build_noop_mcp_server()` — the SDK sees `sdk_mcp_servers` is truthy → keeps stdin open via its own `asyncio.Event().wait()` mechanism.

### `CLAUDECODE` env var stripping

The SDK spawns Claude Code as a subprocess. If `CLAUDECODE` env var is present (set by the parent Claude Code session), the child refuses to start — it detects a nested session. `_require_sdk()` strips this env var so the SDK subprocess can launch. This only affects the engine process, not the parent session.

### Streaming mode requirement

`can_use_tool` only works when the SDK operates in streaming mode. The `_as_stream()` async generator wraps a string prompt into the streaming format:

```python
yield {"type": "user", "session_id": "", "message": {"role": "user", "content": prompt_text}, "parent_tool_use_id": None}
```

Non-streaming `query(prompt="string")` does not support `can_use_tool`.

### ask_user capture: dual-path design

The `_EmergentAskUserCapture` object is checked in two places because there are two possible flows:

1. **`can_use_tool` path** (lines 336-353): When the inner CLI requests permission to call `mcp__engine__ask_user`, the callback inspects `tool_input`, computes `q_key`, and if no preset answer exists: captures the question and returns `PermissionResultDeny(interrupt=True)`. The SDK raises an exception which the engine catches → `StopForInput`.

2. **MCP handler path** (lines 271-296): If `can_use_tool` allows the call (preset answer exists), the MCP tool handler runs. Inside, `handler.prompt()` may raise `StopForInput` (StopIOHandler without preset). The MCP framework catches this, so the handler stores the question in `capture` and returns a text response. Post-query, engine checks `capture` and raises `StopForInput` itself.

Both paths converge: after `query()` or its exception handler, the engine checks `if capture and capture.question_key` and raises `StopForInput`.

### Stderr capture design

The SDK transport always runs Claude Code with `--verbose`, generating noisy stderr. If this inherits the parent's stderr, Bash tool output capture can be truncated (some hosts cap output), hiding the engine's `workflow_question` JSON. Solution: `_apply_sdk_debug()` always sets a `stderr` callback that routes to `logger.debug`. An optional `WORKFLOW_ENGINE_SDK_DEBUG=1` flag adds `--debug-to-stderr` for deeper investigation.

### GroupBlock segment compatibility

`execute_group` splits contiguous `LLMStep` runs into compatible segments. A new segment boundary is created when:
- Model changes between steps (`step.model != seg_model`)
- `ask_user` capability changes between steps (`"ask_user" in step.tools` differs)

All steps in a segment share a single `ClaudeSDKClient` session, enabling conversational context flow. Non-LLM blocks break the segment and execute independently.

---

## Testing Infrastructure

### Fake SDK mode (`WORKFLOW_ENGINE_FAKE_SDK=1`)

All 173 deterministic tests run without the real SDK. The fake path:
- `_fake_sdk_enabled()` checks the env var
- `execute_llm_step` in fake mode: returns `prompt_text.strip()` as output (no API call)
- For `ask_user`: the `[[ASK_USER {"message": "...", "options": [...]}]]` marker in prompts is parsed by `_fake_extract_ask_user()`, enabling deterministic stop/resume testing
- `execute_llm_segment` in fake mode: falls back to per-step `execute_llm_step`

### SDK wiring tests (`WORKFLOW_ENGINE_SDK_TESTS=1`)

`tests/test_llm_ask_user_sdk.py` — tests `_build_can_use_tool` in isolation with real SDK types. **Note: currently stale** — uses old `allow_ask_user` parameter API instead of current `allowed_tools`. Needs update to match current `_build_can_use_tool(*, allowed_tools, capture, io_handler)` signature.

### E2E test workflow (`skills/test-workflow/`)

18-phase workflow exercising all 9 block types. Phases 10-16 are gated by `mode=thorough` or `enable_llm=True`. Includes:
- Phase 13b: `llm-denied-tools` — security test verifying `can_use_tool` denies unauthorized tools (prompt instructs LLM to try Bash and Read, both are denied)
- Phases 14-16: `ask_user` in single, group, and parallel contexts

---

## Known Gap: Argument-Level Permission Filtering

### The problem

`can_use_tool` receives both `tool_name` and `tool_input`, but currently only checks the **tool name**:

```python
if tool_name in allowed_set:        # ← checks name only
    return PermissionResultAllow()  # ← allows any arguments
```

This means:

- If `Read` is in `allowed_tools`, the LLM can read **any file** on disk
- If `Bash` is in `allowed_tools`, the LLM can execute **any command**
- There is no path restriction, command validation, or argument inspection

### What `setting_sources` does NOT solve

We load `setting_sources: ["user", "project", "local"]` hoping the inner CLI would apply the user's permission rules (e.g., `Bash(python:*)` allow, deny others). However:

1. `--permission-prompt-tool stdio` (auto-set by SDK when `can_use_tool` exists) **overrides** settings-based auto-approval
2. All permission requests go through `can_use_tool` exclusively
3. Settings are loaded (inner CLI sees plugins, MCP servers, agents) but their permission rules don't act as a pre-filter

### Side effect of loading settings

With `setting_sources: ["user", "project", "local"]`, the inner CLI loads the user's full environment:

- All MCP servers (pencil, browser automation, etc.)
- All plugins and skills
- All agents

These are visible to the LLM (it can see them in its tool list) but denied by `can_use_tool` since they're not in `allowed_tools`. This creates noise — the LLM sees tools it can't use.

### Approaches considered but not yet implemented

**Option A (implemented, insufficient)**: Load `setting_sources` to inherit user's permission rules. Failed because `--permission-prompt-tool stdio` bypasses settings-based auto-approval.

**Option B: Argument-level filtering in `can_use_tool`**

Inspect `tool_input` for known dangerous patterns:

```python
if tool_name == "Read":
    path = tool_input.get("file_path", "")
    if not path.startswith(ctx.cwd):
        return PermissionResultDeny(...)
if tool_name == "Bash":
    cmd = tool_input.get("command", "")
    # Check against user's allow patterns
```

Pro: Fully programmatic, no user interaction needed.
Con: Reimplements Claude Code's permission logic; fragile, always playing catch-up with new tools.

**Option C: Stop/resume for permission requests**

Treat unresolved permission requests like `ask_user` — stop the workflow, surface the request to the outer Claude Code, let the user approve/deny, resume with the decision:

```
Inner CLI wants to use Bash("rm -rf /")
  → can_use_tool receives request
    → Not in allowed_tools → capture + deny+interrupt
      → Engine raises StopForInput with permission details
        → Outer Claude Code shows: "The LLM wants to run: rm -rf /. Allow?"
          → User answers → resume with decision
```

Pro: Mirrors native Claude Code behavior; user stays in control.
Con: Frequent stops for routine operations; may need batching or auto-approve patterns.

**Option D: Hybrid — programmatic rules + escalation**

Apply user's settings rules programmatically in `can_use_tool` (parse `settings.local.json` allow patterns), auto-approve matching requests, escalate unmatched ones via stop/resume.

Pro: Best of both worlds — routine operations auto-approve, unusual ones get user review.
Con: Most complex to implement; must parse and match Claude Code's permission pattern syntax.

---

## IOHandler Protocol

```python
class IOHandler(Protocol):
    def prompt(self, key: str, prompt_type: str, message: str,
               options: list[str], default: str | None, strict: bool) -> str: ...
```

Three implementations:

- `StdinIOHandler` — terminal interactive mode
- `PresetIOHandler` — non-interactive with preset answers (CI, tests)
- `StopIOHandler` — Claude Code mode: raises `StopForInput` on first unanswered prompt

---

## Context Serialization

`WorkflowContext` is fully JSON-serializable except for `io_handler` (runtime object) and `_start` (timer):

| Field                                   | Serializable | Notes                                       |
| --------------------------------------- | ------------ | ------------------------------------------- |
| `results_scoped: dict[str, StepResult]` | Yes          | Canonical storage by deterministic exec_key |
| `results: dict[str, StepResult]`        | Yes          | Convenience "last result" view              |
| `variables: dict[str, Any]`             | Yes          | JSON-compatible data                        |
| `cwd`, `dry_run`, `prompt_dir`          | Yes          | Primitives                                  |
| `io_handler`                            | No           | Re-created on resume                        |
| `_start` (PrivateAttr)                  | No           | Restarts on resume                          |

---

## Checkpoint / Resume Flow

```
Fresh run:
  runner.py <workflow> --cwd . --var key=val
    → uuid run_id
    → execute_workflow(...)
    → StopForInput raised at PromptStep or ask_user
      → Save checkpoint.json: {run_id, workflow, results_scoped, variables, workflow_hash}
      → Print workflow_question JSON + resume_command
      → Exit 0

Resume:
  runner.py resume --cwd . --run-id <id> --answer <key>=<value>
    → Load checkpoint.json
    → Strict drift check: compare workflow_hash
    → Rebuild ctx from saved results_scoped + variables
    → Re-execute workflow; completed leaf steps (by exec_key) are skipped
    → Next unanswered prompt → StopForInput again, or → completion
```

---

## Side-Effect Safety

**Guarantees provided:**

- Checkpoint captures `ctx.results_scoped` and `ctx.variables`
- On resume, completed leaf executions (by deterministic `exec_key`) are skipped
- Resume is refused if the workflow source changed since checkpoint creation
- PromptStep itself has no side effects

**Guarantees NOT provided:**

- Prior ShellStep file writes are not undone if user answers "no"
- Prior LLMStep actions (including file modifications) persist regardless of prompt answer

**Workflow authoring guidance:**

- Place PromptSteps **before** expensive/irreversible operations, not after
- Use `condition` on subsequent blocks to gate execution based on the prompt answer

---

## Limitations

- **Workflow edits between stop→resume**: Refused by design (strict drift policy)
- **No rollback**: Side effects from prior steps are irreversible
- **Cheap re-execution on resume**: Completed leaf executions are skipped; container blocks (loop/retry/etc.) always re-evaluate conditions
- **Permission control is name-only**: `can_use_tool` checks tool name, not arguments (see "Known Gap" section)
- **Settings load side effects**: Inner CLI sees all user's MCP tools/plugins (denied but visible to LLM)
- **No argument-level auto-approve**: Cannot replicate Claude Code's `Bash(python:*)` pattern matching

---

## SDK Integration — Discovered Behaviors

Non-obvious behaviors learned through experimentation. Preserve this section for future reference.

### `--permission-prompt-tool stdio` is automatic

When `can_use_tool` is provided in `ClaudeAgentOptions`, the SDK transport (`subprocess_cli.py`) automatically adds `--permission-prompt-tool stdio` to the inner CLI args. There is no way to have `can_use_tool` without this flag. This means **all** permission requests go through the callback — there is no "settings first, callback as fallback" mode.

### `setting_sources` parameter behavior

From SDK source (`subprocess_cli.py`, lines 276-281):
- `setting_sources=None` → CLI gets `--setting-sources ""` (empty — no settings loaded)
- `setting_sources=["user", "project", "local"]` → CLI gets `--setting-sources "user,project,local"`

When settings are loaded, the inner CLI gains access to the user's full environment (MCP servers, plugins, skills, agents). These become visible to the LLM as available tools. However, since `--permission-prompt-tool stdio` routes all permission requests through `can_use_tool`, the settings' allow/deny rules don't auto-approve — every tool call goes through our callback.

### `PermissionResultDeny(interrupt=True)` behavior

When `can_use_tool` returns deny with `interrupt=True`:
- The SDK cancels the current turn
- An exception is raised in the `async for message in query(...)` loop
- The LLM does **not** get a chance to try an alternative

When `interrupt=False`:
- The inner CLI tells the LLM the tool was denied
- The LLM may retry, try a different tool, or give up
- The query continues normally

We use `interrupt=True` for ask_user (stop the workflow immediately) and `interrupt=False` for denied tools (let the LLM adapt).

### `create_sdk_mcp_server` lifecycle

MCP servers passed via `mcp_servers={"name": server}` run as stdio-based servers within the SDK process. They are started when `query()` or `ClaudeSDKClient.__aenter__()` runs and stopped when the query completes or the client exits. The `@tool` decorator from `claude_agent_sdk` registers tools on the server; the inner CLI discovers them automatically.

### `ResultMessage` fields

After `query()` completes, `ResultMessage` contains:
- `result: str` — the LLM's text output
- `structured_output: dict | None` — populated when `output_format` (JSON schema) is set
- `total_cost_usd: float | None` — cumulative cost of the query

In `execute_llm_segment` (shared session), `structured_output` may be `None` even when a schema was requested. The engine falls back to `_parse_structured_output()` which attempts `json.loads` + Pydantic validation on the raw text.
