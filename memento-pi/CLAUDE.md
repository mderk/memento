# memento-pi

pi-coding-agent extension that embeds [memento-workflow](../memento-workflow) in-process (no MCP).

## Start here

**Read `memory/README.md` first.** It indexes:

- `memory/overview.md` — what this package is, why it exists, MVP scope
- `memory/architecture.md` — components, data flow, hybrid inline/subagent execution, RPC protocol
- `memory/decisions.md` — key choices and their reasoning (D1-D10)
- `memory/runtime-notes.md` — pi API essentials, sub-agent pattern, env vars, test harness
- `memory/roadmap.md` — what's done, what's next

Do not re-derive context by reading source before consulting these notes.

## Key facts

- TS extension is a thin wrapper; the **Python engine** in `../memento-workflow` owns the DSL, runner, state, checkpoints, and shell execution.
- Transport: long-lived `python -m scripts.server` subprocess, JSONL-over-stdio (`client.ts`).
- **Hybrid execution**: `LLMStep isolation="inline"` runs in the main pi session (via `workflow_submit` tool + `before_agent_start` inject); `LLMStep isolation="subagent"` runs in an isolated pi sub-session via `createAgentSession`/`runAgent`. Respect this distinction — inline steps need accumulated main-session context.
- Provider: `claude-agent-sdk-pi` (Claude Pro subscription). Default model `claude-agent-sdk/claude-sonnet-4-6`, per-step aliases `sonnet`/`haiku`/`opus`.
- All existing `.workflows/*` across projects keep working — no DSL changes.

## Working on this codebase

- Source: `src/` (TypeScript, loaded via jiti — no build step).
- `/reload` in pi picks up changes. `package.json` edits need full restart.
- Python server code lives in `../memento-workflow/scripts/server.py` — don't duplicate engine logic in TS.
- When a question comes up about "how does X actually work in the engine", read `../memento-workflow/scripts/engine/` directly; don't guess.

## Quality gate

No automated tests yet (v0). Manually verify each change with:

```bash
pi --print "/wf list" --no-tools   # smoke-test extension loads and spawns server
# then interactively: pi → /wf start <name>
```
