# Architecture

## Component layout

```
pi process (node)
 └── memento-pi extension (ts)
      ├── server-bootstrap.ts  — resolves Python server command (uv run python -m scripts.server)
      ├── client.ts            — MementoClient: spawn + JSONL RPC, pending-by-id map
      ├── types.ts             — action-shape type mirrors of engine/protocol.py
      ├── state.ts             — single active run (pending action + step counter)
      ├── widget.ts            — setWidget/setStatus helpers
      ├── render.ts            — renders <workflow-pending> block (used in hand-off mode)
      ├── actions.ts           — processActions loop: ask_user inline, handle terminal, hand off prompt
      └── index.ts             — extension entry: hooks, command, (and tool in hand-off mode)

memento-workflow (python)
 └── scripts/server.py         — JSONL-over-stdio wrapper around scripts/runner.py MCP tools
      (no engine changes; existing _auto_advance handles shell inline)
```

State on disk: unchanged — `cwd/.workflow-state/<run_id>/` with checkpoints + artifacts + meta.json. Format compatible with existing Python MCP server.

## Startup / shutdown

- `session_start` — lazy-init `MementoClient` (spawns Python server on first call).
- `session_shutdown` — SIGTERM python, wait exit 2s, clear `activeRun`.

## Run lifecycle

1. `/wf start <name>` → `client.call("start", { workflow, cwd })` → engine returns first non-shell action.
2. `processActions(action)` drives the chain:
   - `ask_user` — resolved via `ctx.ui.{confirm,select,input}`, submitted inline, loop continues.
   - `prompt` — stored in `activeRun.pending`, widget updated. In **hand-off mode** (current MVP): return; main model sees `<workflow-pending>` via `before_agent_start` and calls `workflow_submit`. In **auto mode** (target): kick off `runLLMStep(action)` via `createAgentSession`/`runAgent`, submit result, continue loop.
   - `subagent` with `relay=false` — single isolated LLM call. `runLLMStep` handles it; submit result; loop continues.
   - `subagent` with `relay=true, child_run_id=X` — spawn a real pi sub-session that acts as the relay agent. Inject `_mw_next`/`_mw_submit`/`_mw_status` tools (bound to `child_run_id`) plus any allow-listed pi tools. The sub-session drives the child run to completion in its own LLM context; inline LLMSteps inside the child inherit that context (contract of `isolation="inline"`). On final summary, submit parent's `exec_key`. Covers `SubWorkflow(isolation="subagent")` and any `GroupBlock`/`LoopBlock` that engine classifies as subagent. See D9.
   - `parallel` — lanes are `relay=true` child runs; sequential drive (one lane at a time, reusing the relay machinery) in v0, concurrent `Promise.all` in v2.
   - `completed` / `halted` / `error` / `cancelled` — clear `activeRun`, notify, update widget.
3. Engine's `_auto_advance` executes `shell` steps *inside Python*; TS never sees `shell` actions except in `_shell_log` metadata.

## Execution model: hybrid (inline vs subagent)

The engine emits two different LLM action types based on `LLMStep.isolation`:

| Engine action | `isolation` | Where it runs | Why |
|---|---|---|---|
| `prompt` | `"inline"` (default) | **Main pi session** via hand-off | The step needs the accumulated chat context (e.g. `develop.classify` must see what the user wrote before `/wf start develop`). |
| `subagent` (no relay) | `"subagent"` | **Isolated pi sub-session** via `runAgent` | The step is heavy and self-contained (e.g. `explore` reads tons of files, uses Haiku) — running in the main session would pollute context and force the main model to do work it was never configured for. |

Both routes drive the same `workflow_submit` tool internally — only the *producer* of the result differs:

- **Inline (`prompt`):** `processActions` stores pending, returns. `before_agent_start` injects `<workflow-pending>` into the main-session system prompt. The main model emits an assistant reply and calls `workflow_submit`. The tool invokes `client.submit`, then re-enters `processActions` with the next action.
- **Subagent (`subagent` without relay):** `processActions` calls `runLLMStep(action, ctx)` inline — it spins up `createAgentSession({ tools: pi.getAllTools().filter(...) }) + createAgent({ model, apiKey }) + runAgent(...)`, reads the final assistant text + parses `structured_output` against `json_schema`, then calls `client.submit` directly. Loop continues. The main chat never sees this step except via the widget.

This mirrors what MCP + Claude Code did (inline = current-chat prompt, subagent = Task-tool), but faster: subagent steps in pi don't cost a Task-tool roundtrip and use the same `claude-agent-sdk-pi` provider as the main session.

### Relay (a real sub-session acts as the relay agent — approach C)

`SubagentAction(relay=true, child_run_id=X)` is emitted by `SubWorkflow(isolation="subagent")` and by `GroupBlock`/`LoopBlock` living inside a subagent context. Semantically: *"spin up a relay-agent whose LLM context will host any inline steps in this child run"*.

**Why a real sub-session (not pure extension-code orchestration):** inline `LLMStep`s inside the child run contractually share the surrounding subagent context. If the extension drove the child loop itself and then invoked `runLLMStep` per inline step with empty history, `isolation="inline"` would be violated. A real sub-session preserves the contract: inline steps run as ordinary prompts inside that session's accumulated chat.

**Extension work per `relay=true` action:**
1. Resolve model (`config.ts`) and filter pi tools by `action.tools` allowlist.
2. Build relay tools (`src/mw-tools.ts`): `_mw_next`, `_mw_submit`, `_mw_status` — all bound to `child_run_id` so the sub-session can't wander.
3. `createAgentSession({ tools: [...allowedPiTools, ...relayTools] })`, `createAgent({ model, apiKey })`.
4. `runAgent` with a relay system prompt (`"you are a relay agent: call _mw_next, handle each action, call _mw_submit, loop until completed"` + `action.context_hint`).
5. Sub-session drives the child run through its own tool calls. Inline LLMSteps inside the child come back as `prompt`/`ask_user`/nested `subagent` actions — the sub-session handles them in-chat.
6. When `_mw_next` returns `completed`, the relay-agent emits its final summary → we capture it (via the same structured/text extraction used by `runLLMStep`) → `submit(parent_run_id, parent_exec_key, output=summary, structured_output=...)`.

Nested relay is natural: if the child emits another `SubagentAction(relay=true)`, we recurse — spawn another sub-session with tools bound to the grandchild's `child_run_id`.

**State tracking:** top-level `activeRun` still holds the run the user started. Relay sub-sessions are self-contained (the session is the "frame"); no TS-side stack needed. Widget can observe live progress via `runAgent`'s `onUpdate` (D13-C).

**MCP+Claude Code analogue:** Task-tool with a relay prompt + workflow MCP tools. Same idea, just in-process in pi.

**v0-critical:** `develop`, `commit`, `merge-protocol`, `process-protocol` all rely on relay. Without it only `test-workflow`, `verify-fix`, `code-review`, `create-protocol`, `figma-import` work end-to-end.

**Inline control-flow is invisible:** `SubWorkflow(isolation="inline")`, `GroupBlock`/`LoopBlock` in inline contexts — Python's `_auto_advance` handles them entirely; extension never sees these.

## Model resolution (auto mode)

`LLMStep.model` is a short alias (`"sonnet"`, `"haiku"`, `"opus"`) or full id or null.

```ts
MODEL_MAP: Record<string, string> = {
  sonnet: "claude-agent-sdk/claude-sonnet-4-6",
  haiku:  "claude-agent-sdk/claude-haiku-4-5",
  opus:   "claude-agent-sdk/claude-opus-4-7",
};
DEFAULT = "claude-agent-sdk/claude-sonnet-4-6";
```

Resolution: `MODEL_MAP[alias] ?? alias ?? DEFAULT`, then `provider/id` split (default provider = `claude-agent-sdk`), then `ctx.modelRegistry.find(provider, id)`. Override default via `MEMENTO_DEFAULT_MODEL` env var.

`claude-agent-sdk-pi` provider uses the user's Claude Code / Pro subscription — no separate API key, no separate billing.

## Tools in sub-sessions

`LLMStep.tools = ["Read", "Glob", ...]` → filter `pi.getAllTools()` by name. If alias mismatches exist (engine uses `"Bash"`, pi uses `"bash"`), normalize case-insensitively.

## Cancel

- `Esc` in pi → current `ctx.signal` passed to `runAgent({ signal })`.
- `/wf cancel [run_id]` → `client.call("cancel")` + abort local controller + clear `activeRun`.

## RPC protocol (TS ↔ python)

Line-delimited JSON:
```
Request:  {"id":"<string>","method":"<name>","params":{...}}
Response: {"id":"<string>","result":<any>}
Error:    {"id":"<string>","error":{"message":"...","type":"..."}}
```
Methods: `start`, `submit`, `next`, `cancel`, `status`, `list_workflows`, `cleanup_runs`, `open_dashboard`.

Client matches responses by id — concurrent RPCs are fine, no pipe mutex.
