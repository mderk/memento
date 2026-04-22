# Roadmap

## v0 (in progress)

- [x] Python `scripts/server.py` — JSONL stdio over `runner.py` functions.
- [x] TS skeleton: package.json, tsconfig, `client.ts`, `server-bootstrap.ts`, `state.ts`, `types.ts`, `render.ts`, `widget.ts`, `actions.ts`, `index.ts`.
- [x] `/wf list | start | status | cancel` commands.
- [x] `session_start` lazy-spawn, `session_shutdown` SIGTERM.
- [x] Hand-off mode: `before_agent_start` injects `<workflow-pending>`, `workflow_submit` tool.
- [x] `ask_user` inline via `ctx.ui`.
- [x] **Hybrid execution** — `subagent` (non-relay) goes through `runLLMStep` (`createAgentSession`/`runAgent`); `prompt` stays on hand-off so inline steps keep main-session context (`src/llm-step.ts`, `src/actions.ts`).
- [x] Model alias resolution via `src/config.ts` (project + user `settings.json` `memento` section + env vars).
- [x] Output dedup in `workflow_submit` + `output_file` parameter (D11).
- [x] Tool-name normalization in `runLLMStep` (case-insensitive filter).
- [ ] **Relay support via hybrid C (see D9)** — `SubagentAction(relay=true, child_run_id)` spawns a real pi sub-session with injected `_mw_next`/`_mw_submit`/`_mw_status` tools bound to that child. The sub-session IS the relay agent; its LLM context is what inline `LLMStep`s inside the child inherit (honours `isolation="inline"` contract). **v0-critical** — `develop`, `commit`, `merge-protocol`, `process-protocol` all depend on `SubWorkflow`/`LoopBlock`/`GroupBlock` emitting relay actions. Work: `src/mw-tools.ts` (relay tool factory); extend `src/actions.ts` + `src/llm-step.ts` to handle `relay=true`.
- [ ] **End-to-end run on a real repo** — after relay lands: start with `test-workflow` (no relay), then `commit` (Loop over groups), then `develop` (nested SubWorkflow to verify-fix).
- [ ] Widget polish: step count, elapsed time, last action result truncated.
- [ ] Live sub-agent progress in widget (option C from observability discussion — see decisions D13).
- [ ] **`ParallelEachBlock` (sequential lanes)** — each lane is a `SubagentAction(relay=true)` with its own `child_run_id`; drive lanes one at a time reusing the relay machinery, aggregate summaries, submit parent. Concurrent execution is a later optimisation (see v2).

## v1

- [ ] `/wf resume <id>` — pick up an existing checkpoint.
- [ ] `/wf runs` — list active (memory) + recent on-disk runs.
- [ ] Structured output validation against `json_schema` before submit; on failure, ask the sub-agent to retry once.
- [ ] `ctx.signal` wired through `runAgent` so `Esc` cancels in-progress LLM steps cleanly.
- [ ] **Reduce context bloat in `<workflow-pending>` injection** — for steps whose prompt substitutes huge `{{results.*.structured_output}}` values, reference them as `context_files` (engine already externalises) instead of inlining.

## v2

- [ ] **Concurrent `ParallelEachBlock` lanes** — run multiple child runs in parallel via `Promise.all` over `processActions`. Requires per-lane progress UI and careful cancellation semantics. Only if sequential proves too slow for real workflows.
- [ ] Rich progress: stream sub-agent tokens into widget, show elapsed per step, color by status.
- [ ] `open_dashboard` replacement built on pi TUI primitives (or leave the Python FastAPI dashboard usable as-is via `pi.exec("open", ["http://..."])`).
- [ ] Settings UI (`pi config`) integration to toggle debug/sandbox per-project.

## Out of scope / won't do

- MCP compatibility layer — if someone needs MCP, they can keep using memento-workflow's MCP server in parallel; both can run at once.
- Porting DSL/engine to TS — too much surface area for no proportional gain.
- Concurrent parallel lanes with separate UI — sequential is sufficient for current workflows.
