---
status: Draft
---
# Protocol: Relay Watchdog

**Status**: Draft
**Created**: 2026-03-25
**PRD**: [./prd.md](./prd.md)

## Context

During workflow relay execution, the Claude Code agent sometimes breaks the loop — outputs text and stops instead of continuing to process the next action. The checkpoint is preserved but the loop is dead, requiring human intervention. This blocks unattended workflow execution.

## Decision

Implement a **pure hooks approach** using Claude Code's Stop and PostToolUse hook events. A single Python hook script manages marker files that track active relay sessions. PostToolUse hooks on `start`/`submit`/`cancel` MCP tools maintain the marker lifecycle. The Stop hook checks for an active marker and forces continuation via `decision: "block"`. Ship as part of the memento-workflow plugin via `hooks/hooks.json`. Also strengthen SKILL.md relay protocol wording as prevention.

No MCP server changes required — hooks receive `session_id` and `tool_response` from Claude Code stdin, which the MCP server cannot access (`CLAUDE_SESSION_ID` env var doesn't exist yet).

## Rationale

**Alternatives considered:**

1. **MCP server manages markers** — requires `session_id` param on `start()`, but the MCP server has no way to get the Claude Code session_id. Would require `CLAUDE_SESSION_ID` env var which is a feature request, not implemented.
2. **Notification hook (idle_prompt)** — observational only, cannot block or force continuation.
3. **SessionStart hook + env var workaround** — complex plumbing to bridge session_id between hook and MCP server. Race conditions with multiple sessions.

Pure hooks wins because the hook system already has everything needed: `session_id` for isolation, `tool_response` for action detection, `decision: "block"` for forced continuation.

## Consequences

### Positive

- Unattended workflows auto-recover from relay breaks without human intervention
- Session isolation via session_id — multiple Claude instances don't interfere
- No MCP server changes — fully backward compatible, zero risk to engine stability
- Ships as plugin hooks — auto-registered on install, no manual configuration
- Retry counter (MAX_BLOCKS=3) prevents infinite loops if MCP server is unreachable
- User interrupts (Ctrl+C) bypass the hook entirely — no interference with manual control

### Negative

- PostToolUse matcher uses full MCP tool names — fragile if plugin naming changes. Mitigation: update hooks.json when plugin name changes (same as .mcp.json).
- Stop hook fires for ALL stops, not just relay breaks — adds ~50ms overhead per agent stop. Mitigation: early exit when no marker file exists (fast path).
- MAX_BLOCKS=3 means genuinely stuck agents get 3 retries then stop silently — user must check manually. Mitigation: hook logs warning to stderr on final retry.
- Stale markers from crashed sessions accumulate until cleanup_runs() is called. Mitigation: 24h age-out in cleanup, and markers are tiny JSON files.

## Progress

- [ ] [Implement relay watchdog hook script](./01-implement-relay-watchdog-hook-script.md) <!-- id:01-implement-relay-watchdog-hook-script --> — 2h est

- [ ] [Register hooks via plugin and write tests](./02-register-hooks-via-plugin-and-write-tests.md) <!-- id:02-register-hooks-via-plugin-and-write-tests --> — 1.5h est

- [ ] [Strengthen SKILL.md relay loop and add stale marker cleanup](./03-strengthen-skillmd-relay-loop-and-add-stale-marker-cleanup.md) <!-- id:03-strengthen-skillmd-relay-loop-and-add-stale-marker-cleanup --> — 1h est
