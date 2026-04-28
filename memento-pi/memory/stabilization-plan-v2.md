# Stabilization plan v2

## Goal

Bring `memento-pi` to a state where:
- workflow start and advancement are reliable
- inline `prompt` steps hand off only through the main session
- `subagent` / `relay` steps run without accidental handoff or false cancellation
- cancel works
- resume works for pending runs
- config/docs behavior is consistent and unsurprising

## Phase 0 — tighten semantics, minimal surface change

### 0.1 Introduce explicit runtime mode
**Files:** `src/state.ts`, `src/actions.ts`, `src/widget.ts`

Add:

```ts
type RunMode = "idle" | "handoff" | "awaiting-user" | "auto-running";
```

Runtime state should track:
- `runId`
- `workflowName`
- `mode`
- `pending`
- `stepCount` (UI hint only)
- `peek`
- optional abort handle(s)

Rules:
- `prompt` => `mode="handoff"`
- `ask_user` => `mode="awaiting-user"`
- `subagent` / `parallel` => `mode="auto-running"`
- terminal => clear active state

### 0.2 Restrict handoff rendering to prompt-only
**Files:** `src/render.ts`, `src/index.ts`

Refactor:
- `renderPending(...)` → `renderPendingPrompt(...)`
- input type should be `PromptAction`, not generic pending action

`before_agent_start` must inject only when:
- active run exists
- `mode === "handoff"`
- `pending.action === "prompt"`

This removes accidental main-model interference with auto-running steps.

### 0.3 Keep turn triggering, remove prompt duplication
**Files:** `src/index.ts`

Do **not** remove post-`/wf start` turn triggering.

Replace:

```ts
pi.sendUserMessage(rendered, { deliverAs: "followUp" });
```

with a minimal trigger message, e.g.:

```ts
pi.sendUserMessage("Continue the active workflow.", { deliverAs: "followUp" });
```

Prompt payload should come from `before_agent_start`, not from this message.

Goal:
- still trigger the next agent turn
- avoid duplicating the full `<workflow-pending>` block into session history

## Phase 1 — fix cancellation lifecycle

### 1.1 Stop passing `ctx.signal` directly into child agents
**Files:** `src/llm-step.ts`, `src/relay-session.ts`, `src/actions.ts`

Change signatures:

```ts
runLLMStep(action, pi, ctx, signal?)
runRelaySession(action, pi, ctx, client, signal?)
```

Use a fresh local `AbortController` for auto-running steps.

First implementation:
- one active auto-run controller for the current running subtree
- store it in runtime state
- abort it on `/wf cancel` or `session_shutdown`

Do **not** start with a full per-child map unless needed.

### 1.2 Wire `/wf cancel` to local abort + engine cancel
**Files:** `src/index.ts`, `src/state.ts`

`/wf cancel` should:
1. abort local active auto-run controller
2. call engine `cancel(run_id)`
3. clear runtime state
4. clear widget/status

### 1.3 `session_shutdown` aborts local work
**Files:** `src/index.ts`, `src/state.ts`

On shutdown:
- abort local active auto-run controller
- shutdown Python client
- clear runtime state

## Phase 2 — make pending states honest and resumable

### 2.1 Make `ask_user` cancellation resumable
**Files:** `src/actions.ts`, `src/widget.ts`

Before showing the UI prompt, set:
- active run
- `mode="awaiting-user"`
- `pending=AskUserAction`

If user cancels:
- do **not** say “paused” unless resume exists
- keep resumable runtime state
- show:
  - `workflow input cancelled; use /wf resume <run_id> to continue`

### 2.2 Add `/wf resume <run_id>`
**Files:** `src/index.ts`, maybe `src/types.ts`

Implementation:
1. call engine `status(run_id)` to validate run exists / inspect metadata
2. call engine `next(run_id)` to get current actionable state
3. restore runtime state from returned action:
   - `prompt` → `handoff`
   - `ask_user` → `awaiting-user`
   - `subagent` / `parallel` → resume `processActions(...)`
   - terminal → notify and do not reactivate

Important pre-task:
Verify engine response includes enough metadata to restore:
- `workflowName`
- status
- maybe step info

If not, extend Python server / runner result shape first.

### 2.3 Add `/wf runs` only after resume works
Optional for this pass.

If implemented, it should list:
- active in-memory run
- resumable on-disk runs
- workflow name / status / timestamp

But `/wf resume` is higher priority than `/wf runs`.

## Phase 3 — config correctness without breaking users

### 3.1 Fix cross-project config bleed
**Files:** `src/config.ts`

Remove global one-shot cache, or key it by normalized cwd.

Recommended for now:
- remove cache entirely

### 3.2 Support both current and intended config formats
**Files:** `src/config.ts`, docs

Current reality and docs differ. Add compatibility.

Read order:
1. built-in defaults
2. env vars
3. legacy `~/.pi/memento-pi.json`
4. legacy `<cwd>/.pi/memento-pi.json`
5. `~/.pi/agent/settings.json` → `memento`
6. `<cwd>/.pi/settings.json` → `memento`

If legacy config is found:
- emit a debug/deprecation note
- do not break it yet

Goal:
Migrate safely to `settings.json` without surprising current users.

## Phase 4 — handoff reliability guards

### 4.1 Provider gate at `prompt` entry, not global workflow start
**Files:** `src/actions.ts`, `src/index.ts`

Do **not** block `/wf start` globally.

Instead, when entering `action.action === "prompt"`:
- detect if current provider/model is known not to support the handoff hook path
- if unsupported:
  - fail fast with a clear message
  - keep the run resumable
  - instruct the user to switch model/provider and `/wf resume`

Why:
Some workflows may do useful work before the first inline prompt. Don’t block them prematurely.

### 4.2 Document supported handoff path
**Files:** `README.md`, memory docs

Explicitly document:
- which providers/models are known to work for inline handoff
- which are known broken / limited
- that subagent steps may still use different models via config

## Phase 5 — low-cost safety checks

### 5.1 Add relay exec-key drift guard
**Files:** `src/mw-tools.ts`

Store:

```ts
lastPromptExecKey?: string;
```

In `_mw_next`, when returning a prompt:
- record `lastPromptExecKey`

In `_mw_submit`:
- reject or warn if submitted `exec_key` doesn’t match the last prompt returned

This is a cheap guard against relay-agent drift.

### 5.2 Improve terminal failure messages
**Files:** `src/relay-session.ts`

When child ends with:
- `halted`
- `error`
- `cancelled`

return a better failure message than:
- `child workflow halted`

Include reason/message where available.

## Phase 6 — tests before cleanup

### 6.1 Unit / narrow behavior tests
**Files:** new tests under `memento-pi/` if test harness exists, otherwise document as manual acceptance

Add tests for:
- `config.ts` precedence and no bleed
- `normalizeSubmit()`
- `renderPendingPrompt()`
- mode transitions from action handling

### 6.2 Orchestration behavior checks
At minimum verify:
- `prompt` => `handoff`
- `subagent` => `auto-running`
- `ask_user` cancel => `awaiting-user`
- `before_agent_start` injects only in `handoff`

### 6.3 Resume smoke
Verify:
- pending prompt can be resumed
- pending ask_user can be resumed
- auto-running child can be resumed or at least restarted safely from `next()`

## Phase 7 — cleanup and polish

### 7.1 Debug logs behind a flag
**Files:** `src/index.ts`, `src/actions.ts`, `src/relay-session.ts`, elsewhere

Replace raw `process.stderr.write(...)` with a small helper gated by e.g.:
- `MEMENTO_PI_DEBUG=1`

### 7.2 Widget shows mode clearly
**Files:** `src/widget.ts`

Suggested widget lines:
- workflow + short run id
- mode + exec_key
- optional peek

Examples:
- `handoff · classify`
- `awaiting-user · confirm-scope`
- `auto-running · explore`

### 7.3 Align docs with actual behavior
**Files:** `README.md`, `memory/*.md`

Update:
- config source(s)
- provider caveats
- cancel/resume semantics
- current workflow support level

## Suggested implementation order

### Iteration 1 — stop the biggest correctness problems
1. `RunMode`
2. prompt-only handoff injection
3. minimal trigger message instead of full rendered prompt
4. local auto-run controller
5. stop passing `ctx.signal` directly
6. `/wf cancel` aborts locally + engine cancel

### Iteration 2 — make interruption survivable
7. resumable `ask_user`
8. `/wf resume <run_id>`
9. verify/extend engine metadata for resume
10. widget mode labels

### Iteration 3 — harden integration
11. config bleed fix
12. dual config format support
13. provider gate on prompt entry
14. relay exec-key guard
15. terminal error improvements

### Iteration 4 — cleanup
16. tests
17. debug flag
18. docs update

## Definition of “good enough to use”

The extension is “working” when all are true:
- `/wf start test-workflow` reliably reaches and completes a handoff prompt
- `subagent` and `relay` steps don’t die when the parent tool turn ends
- `/wf cancel` stops local work and cancels engine state
- cancelling `ask_user` does not strand the run invisibly
- `/wf resume <run_id>` restores pending work
- config from project A does not affect project B
- main model never sees `subagent` / `parallel` as handoff prompt work
