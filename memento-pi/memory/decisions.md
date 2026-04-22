# Decisions

## D1. No MCP — pi extension instead

**What:** drop MCP transport, embed engine access as a pi extension.

**Why:** MCP is transport-only. pi extensions get lifecycle hooks (`before_agent_start`, `session_shutdown`, `tool_call`), UI (`ctx.ui.{notify,setWidget,setStatus,confirm,select,input}`), and in-process sub-agent launches (`createAgentSession`/`runAgent`) that MCP can't expose. Per-step MCP roundtrips also aren't free.

## D2. Keep the Python engine intact

**What:** TS extension is a thin wrapper; DSL, runner, state, checkpoints stay in Python.

**Why:** the engine is ~2.5–3.5k lines (`workflow_runner.py` 42KB, `state.py` 25KB, `compiler.py` 19KB) with subtle resume/parallel/subworkflow edge cases. Rewriting in TS is days of work and a bug surface; wrapping is ~500-800 lines. All existing `.workflows/*` keep working.

## D3. JSONL stdio, not MCP

**What:** new `scripts/server.py` — a long-lived Python process that reads `{id,method,params}\n` from stdin and writes `{id,result|error}\n` to stdout, dispatching to the same functions `scripts/runner.py` already exposes as MCP tools.

**Why:** MCP client would drag in the whole MCP protocol overhead for no benefit (pi extension talks to *one* known server, not a registry). JSONL is trivial, debuggable (`echo ... | python -m scripts.server`), and decouples us from MCP spec churn.

## D4. Shell steps stay in Python

**What:** TS never executes shell commands itself. The Python engine's `WorkflowRunner._auto_advance` already runs `shell` actions inline via `infra.shell_exec._execute_shell` (macOS Seatbelt / Linux bubblewrap sandbox, tool-cache env redirect, VIRTUAL_ENV override for worktrees). After `start`/`submit`, the engine returns an already-post-shell action.

**Why:** duplicating sandbox/env logic in TS would diverge from Python over time. No latency cost — both processes are local.

## D5. Hybrid execution: inline vs subagent

**What:** respect `LLMStep.isolation`. Engine emits `prompt` (inline) vs `subagent` as distinct action types — we route them differently:

- `prompt` (inline, default) → hand-off to the **main pi session** via `before_agent_start` inject + `workflow_submit` tool. The step sees the accumulated chat context.
- `subagent` (no relay) → run in an **isolated pi sub-session** via `createAgentSession`/`runAgent`. Extension parses the result and submits directly, no main-model involvement.

**Why:** `isolation` is a contract, not cosmetics. `develop.classify` is `inline` because the user's prior chat IS the classification input; running it in a sub-session would see empty history and misclassify. Conversely, `develop.explore` is `subagent` because it reads a lot of files — dumping that into the main chat would wreck context.

Earlier draft of this doc described an "auto mode" that would replace hand-off for all LLM steps. That was wrong — it would have broken inline steps that depend on main-session context. Hybrid is the correct model; it mirrors what MCP + Claude Code did (inline = current chat, subagent = Task-tool), but faster (no Task-tool roundtrip, same `claude-agent-sdk-pi` provider).

**Side benefits of the subagent side:**
- `LLMStep.model` (per-step) is honored in sub-sessions — Sonnet for planning, Haiku for exploration, Opus for critical code. The inline side uses whatever the user has selected in pi.
- Extension drives `submit` on subagent results, so no model-drift where the main model "forgets" to call `workflow_submit`.
- Same provider (`claude-agent-sdk-pi` → Claude Pro) — no extra API key, same billing/cache.

## D6. Model aliasing + user-level default

**What:** map short aliases (`"sonnet"`, `"haiku"`, `"opus"`) from `LLMStep.model` to full `claude-agent-sdk/<id>` strings. Default when unset = `claude-agent-sdk/claude-sonnet-4-6`. Override via `MEMENTO_DEFAULT_MODEL` env var.

**Why:** existing `.workflows/*` use short aliases. Don't force rewriting them.

## D7. One active run per session (v0)

**What:** `state.ts` holds a single `ActiveRun | null`. `/wf start` while active errors with "finish or cancel first".

**Why:** parent+child runs (subworkflow, parallel) are handled by the engine as one tree — the caller sees one root run_id and engine proxies actions down. Truly concurrent independent runs are rare; a stack-based `activeRuns[]` is a v2 refinement.

## D8. Parallel lanes follow the relay-subagent rule (see D9)

**What:** `ParallelAction` contains lanes each with `child_run_id` and `relay=True`. Per-lane execution goes through the same mechanism as any relay-subagent (D9). In v0: run lanes **sequentially**, one at a time; in v2 consider `Promise.all` for concurrent.

**Why:** an earlier draft said "one `runAgent` at a time", conflating single-LLM runAgent with relay orchestration. Lanes are not single LLM calls — they are child runs. Once D9 is implemented, parallel is just "fan out to N children, join on all terminals, submit aggregated result".

**Order of work:** do D9 first, then parallel falls out almost for free.

## D9. Subagent shapes — decision: hybrid (C)

`SubagentAction` has two shapes with genuinely different semantics. Handle them differently.

### Shape 1: `SubagentAction(relay=false)` — a single isolated LLM call

Emitted by `LLMStep(isolation="subagent")`. One prompt → one model → one result.

**Extension work:** `runLLMStep` (our `createAgentSession`/`runAgent`) → parse final message → submit. **Already implemented** in `src/llm-step.ts` + `src/actions.ts`.

### Shape 2: `SubagentAction(relay=true, child_run_id=X)` — "a relay-agent should drive this child run"

Emitted by `SubWorkflow(isolation="subagent")`, and by `GroupBlock`/`LoopBlock` when they live inside a subagent context. The engine is saying: *spin up a subagent whose job is to act as a relay — pull actions from `child_run_id` and feed results back, in its own LLM context. That LLM context is what any inline `LLMStep` inside the child will inherit.*

**Why a real sub-session is required (approach A, not pure code):**

If a `SubWorkflow(isolation="subagent")` contains inline `LLMStep`s, those steps are contractually supposed to share the relay-subagent's accumulated context (prior tool calls, read files, etc.). If extension code were to drive the child loop itself and then run inline LLMSteps via `runLLMStep` with empty history, the `isolation="inline"` contract would be violated — those steps would misbehave.

So for each `SubagentAction(relay=true)` we must spawn a real sub-pi-session:

1. `createAgentSession({ tools: [...pi tools filtered by allowlist, plus injected `_mw_next`/`_mw_submit`/`_mw_status` bound to `child_run_id`] })`.
2. `createAgent({ model: resolveModelSpec(action.model), apiKey })`.
3. `runAgent({ agent, session, systemPrompt: "You are a relay agent. Repeatedly call _mw_next and _mw_submit until the workflow completes. <context_hint>", ... })`.
4. Sub-session runs the child to completion inside its own chat.
5. When `_mw_next` returns `completed`, the sub-agent emits its final summary → we capture it → submit parent's `exec_key`.

Inline LLMSteps inside the child end up as ordinary `PromptAction`s; the relay-subagent picks them up via `_mw_next` and answers them in its own session — which IS their surrounding context. Correct by construction.

### Inline control-flow blocks are invisible

`SubWorkflow(isolation="inline")`, `GroupBlock`/`LoopBlock` at top level (or inside an inline parent) — engine's `_auto_advance` handles them entirely in Python. Extension never sees them. No work required.

### Chosen approach: C (hybrid)

- **Leaf `LLMStep(isolation="subagent")`** → `runLLMStep` via single `runAgent`. **Done.**
- **`SubWorkflow/Group/Loop(isolation="subagent")`** → spawn real relay sub-session with injected `_mw_*` tools (approach A). **To do. v0-critical.**
- **Inline control-flow** → not our business. Python handles it.
- **`ParallelAction`** → lanes are Shape-2 actions; sequential driver for v0.

### Implementation sketch for relay sub-sessions

- Add `src/mw-tools.ts`: factory `buildRelayTools(client, childRunId)` returning three pi tools (`_mw_next`, `_mw_submit`, `_mw_status`) that proxy to `client.call(...)` with `run_id` locked to `childRunId`.
- In `src/actions.ts`, when handling `SubagentAction(relay=true)`: resolve model via `config.ts`, build relay tools, `createAgentSession({ tools: [...allowed, ...relayTools] })`, runAgent with relay system prompt. Capture final structured summary, then `submit(parent_run_id, parent_exec_key, output=summary, structured_output=...)`.
- `state.ts` still tracks one `activeRun` at the top level (the run user started). Relay sub-sessions are LLM-managed, so we don't need a TS-side stack — the sub-session is itself the "stack frame".
- Widget can peek at the relay sub-session via `onUpdate` for live progress (D13-C).

### Why not B (pure-code orchestration)

- Violates `isolation` contract for inline steps inside subagent children.
- Saves an LLM call but breaks workflows like `develop` (inline LLMSteps inside subagent GroupBlocks).
- Considered and rejected.

### Why not plain A without the hybrid

- `LLMStep(isolation="subagent")` is a leaf, no child run — would be wasted to wrap in a relay-agent that just makes one `_mw_next` call and forwards a prompt. `runLLMStep` is the right primitive there.

### Scope of relay in real workflows

`develop`, `commit`, `merge-protocol`, `process-protocol` all rely on relay. Only trivial workflows (`test-workflow`, `verify-fix`, `code-review`, `create-protocol`, `figma-import`) work end-to-end without it. **Relay support is v0-critical**, before any e2e runs of the flagship workflows.

### Earlier mistakes (kept as reminders)

- "subagent without relay == prompt" (punted relay to v2) — conflated two action shapes; missed that most workflows depend on relay.
- "no extra pi sub-session is needed" — wrong: needed to honour `isolation="inline"` contract of child steps.

## D10. Settings path quirk on symlinks

**What:** `pi install -l` computes a relative path from cwd, but if cwd resolves through a symlink (`/Users/max/projects/` → `Documents/projects/`), pi writes a wrong `../` depth into `.pi/settings.json`. Manual fix: use absolute path in `.pi/settings.json`.

**Why noted:** will bite again on other machines. Also worth reporting upstream to pi-mono.

## D11. Don't duplicate LLMStep results across `output` and `structured_output`

**What:** in `workflow_submit`:
- Render instruction tells the model to put schema-backed results ONLY in `structured_output` and leave `output` empty or a one-line summary.
- `normalizeSubmit()` in `src/index.ts` strips `output` if it is exactly `JSON.stringify(structured_output)` (defense in depth).
- For large outputs, the model can pass `output_file: "<path>"` — extension reads the file, parses as JSON if possible, submits only the parsed form. Model's tool-call args stay small.
- `tool_result` returns only a short status line (`"Step X submitted; next: Y"`) plus `details.nextActionType`. The next action's full body is injected via `before_agent_start` on the next turn, not echoed back here.

**Why:** anything in `tool_call` args and `tool_result` content stays in session entries forever (until compaction), and is re-sent every turn. Before this fix, a `classify` step with a 2KB `structured_output` ended up repeating that 2KB twice per turn (once as `output`, once as `structured_output`) in permanent history. Over a 40-step `develop` run, that's tens of KB of duplicated context per turn.

**Limits:** only prevents duplication in new steps' tool-call args. `<workflow-pending>` in the current system prompt still carries the full new prompt text (including `{{results.*.structured_output}}` substitutions). For very large step results, downstream authors should reference `context_files: [...]` (engine already externalizes big values) or we add `output_file`-as-reference support on the read side (v1).

## D12. Config via pi's settings.json (`"memento"` section)

**What:** model aliases and defaults are loaded from `~/.pi/agent/settings.json` and `<cwd>/.pi/settings.json` under a top-level `"memento"` key; env vars override file settings; built-in defaults fill the rest. No separate config file.

**Why:** pi's settings.json tolerates unknown top-level keys, so we piggy-back on the file users already know. One place to look, one place to version-control alongside packages/extensions. Merge order (project > user > env > defaults) matches how pi treats its own settings.

**Fields:** `defaultModel`, `defaultProvider`, `models: { [alias]: "<provider>/<id>" }`. All optional. Env vars: `MEMENTO_DEFAULT_MODEL`, `MEMENTO_DEFAULT_PROVIDER`, `MEMENTO_MODEL_<ALIAS>`.

**Scope:** subagent steps only. Inline LLM steps use the main pi session's active model (can't change mid-chat — pi design limit).

Implementation: `src/config.ts`, used by `src/llm-step.ts:resolveModelSpec`.

## D13. Observability during subagent steps — live widget + Esc is enough

**What:** subagent steps run invisibly today — widget only shows `step N · exec_key`. `runAgent` in-process does not stream to main TUI (sub-session's entries are separate from `ctx.sessionManager`). Plan: mirror the last ~80-200 chars of sub-agent activity into the widget via `runAgent`'s `onUpdate` callback, so the user can glance and see what the step is doing. `Esc` cancels the current step cleanly.

**Scope:** intentionally minimal.

- Live widget peek (~30-50 lines) → v0.
- No pre-step intercept / edit-prompt / skip / manual retry. The only sensible pause points are ones the workflow itself asks for (`PromptStep` / `ask_user` action in DSL). Supervising every subagent step per-run has no real use case: if a step goes wrong, `Esc` + fix the workflow (or re-run with a different model in config) is a better loop than single-shot editing.
- Full sub-agent chat overlay (`ctx.ui.custom()`, 400-600 lines) — skipped unless a concrete use case appears.

**User-initiated pausing** is covered by three existing mechanisms, all DSL- or engine-driven (never per-step in the extension):
- `PromptStep` in the workflow DSL → engine emits `ask_user` action → `ctx.ui` → submit. Scheduled, visible in DSL, survives resume.
- `ask_user`-tool inside a sub-agent session (hypothetical, not built) — sub-agent pauses itself via `ctx.ui` when IT decides it needs input. Not tied to engine state. Deferred.
- `workflow_submit` tool (main-session hand-off). Different direction entirely.

**Rejected:** `MEMENTO_INTERCEPT` / per-step confirmation UI. Saw no scenario where pre-/post-step prompts help that isn't already covered by either (a) the workflow authoring `PromptStep` explicitly, or (b) user hitting `Esc` and fixing the workflow. Not worth the UX complexity.

## D15. `before_agent_start` does NOT fire for `claude-agent-sdk/*` provider

**What:** Confirmed empirically (2026-04-22) — when pi's active model is from the `claude-agent-sdk` provider (Claude Pro subscription transport), neither `before_agent_start` nor `prompt_submit` extension hooks fire on user turns. System-prompt injection via these hooks is invisible. With `anthropic/claude-sonnet-4-5` (and presumably other anthropic/openai/google direct providers) `before_agent_start` fires correctly with `event.systemPrompt` injected.

**Implication for users:** memento-pi inline hand-off (any `LLMStep(isolation="inline")` step) requires a non-claude-agent-sdk provider for the MAIN session. Subagent steps still use `claude-agent-sdk` aliases via config (we open a fresh session in `runRelaySession` / `runLLMStep`).

**Workaround for users:** in `~/.pi/agent/settings.json` set `"defaultModel": "anthropic/claude-sonnet-4-5"` (or use `/model` to switch). Document this in README.

**Open question:** is this a pi bug or a deliberate design choice for the agent-sdk transport? If bug, file upstream. If by design, hooks have to find another extension point — `before_tool_call` triggers reliably and we could use it as a fallback inject vector (return modified `tools_config` with extra system instructions), but it's awkward.

## D16. `getActive()` singleton can be null inside `workflow_submit.execute`

**What:** Even when `before_agent_start` fires with `hasActive=yes`, the next call to `getActive()` from inside `workflow_submit.execute` (same turn) returns `null`. The module-scope `active` variable in `state.ts` does not survive between hook and tool-execute callsites.

**Cause (hypothesis):** pi seems to (re)import extension modules per-callsite for hooks vs tools. Each import gets its own module scope, so the `active` singleton diverges. Confirmed in logs: `before_agent_start: hasActive=yes` immediately followed by `workflow_submit.execute: hasActive=no` for the same exec_key.

**Workaround applied:** `workflow_submit.execute` no longer gates on `getActive()`. Trust `params.run_id` / `params.exec_key` from the model and let engine validate. Workflow name fallback is `"workflow"` if singleton is null. Run lifecycle still tracked when singleton works (widget, notify), but submission path doesn't depend on it.

**Next steps:** confirm hypothesis with explicit module-id check; consider moving state into a global registry (`globalThis.__memento_pi_state__`) or pi's own session storage if available.

## D17. Relay sub-session fails with "Session is not running"

**What:** When extension calls `runRelaySession` for a `SubagentAction(relay=true)` (e.g. test-workflow phase 12, `llm-session-subagent`), `runAgent` (or one of its dependencies) throws "Session is not running". Stack trace was not captured before sleep.

**Likely causes (to verify next session):**
- `ctx.signal` already aborted by the time the relay starts (the parent tool-execute may have completed and cleaned up).
- pi TUI ("Modes" subsystem) tries to use the original session but the original session has ended after `workflow_submit.execute` returned.
- `createAgentSession`/`runAgent` need a different `ctx` (a sub-session ctx, not the main chat's `ctx`).

**Action items for next session:**
1. Run again with the new `[memento-pi] relay-session: about to runAgent ... | runAgent threw: <stack>` debug logging in place — read the stack.
2. If `ctx.signal` is the problem → use a fresh `AbortController` instead of forwarding `ctx.signal`.
3. If TUI is the problem → look for headless `runAgent` mode or a way to detach.
4. If `ctx` lifecycle is the problem → the pattern may need a long-lived ctx kept around for the duration of the relay.
