---
id: 01-implement-relay-watchdog-hook-script
status: pending
estimate: 2h
---
# Implement relay watchdog hook script

## Objective

<!-- objective -->
Create the core Python hook script that handles both PostToolUse (marker lifecycle) and Stop (relay recovery) events.

This is the heart of the feature — a single script dispatching on `hook_event_name` to manage marker files and block premature stops.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Implement hook event dispatcher and marker helpers

- [ ] Create relay_watchdog.py with main() entry point
  Read stdin JSON, dispatch on `hook_event_name`:
  - `PostToolUse` → call `handle_post_tool_use(data)`
  - `Stop` → call `handle_stop(data)`
  - Other → exit 0

  Marker directory: `{cwd}/.workflow-state/.active_relays/`
  Marker file: `{session_id}.json`

- [ ] Implement marker write/delete helpers
  - `_write_marker(marker_dir, session_id, run_id, workflow)` — atomic write via tmp + `os.replace()`
  - `_delete_marker(marker_dir, session_id)` — `unlink(missing_ok=True)`
  - `_read_marker(marker_path)` → dict or None

  Marker schema:
  ```json
  {"run_id": "abc123", "workflow": "dev", "session_id": "sess-X",
   "created_at": "2026-03-25T10:00:00Z", "watchdog_blocks": 0}
  ```
<!-- /task -->

<!-- task -->
### Implement PostToolUse handler (marker lifecycle)

- [ ] Parse tool_response to extract action type and run_id
  `tool_response` is the MCP tool's return value. Parse as JSON string containing `action` and `run_id` fields.

  Terminal actions: `completed`, `halted`, `error`, `cancelled`.

- [ ] Skip subagent calls (agent_id check)
  If `agent_id` is present in the hook input, this is a subagent calling the MCP tool — not the top-level relay. Skip all marker operations.

- [ ] Handle start: create marker if non-terminal
  Parse `tool_response` → if `action` not in terminal set → write marker with run_id, workflow (from `tool_input.workflow`), session_id, timestamp.

- [ ] Handle submit: delete marker if terminal
  Parse `tool_response` → if `action` in terminal set → delete marker for this session_id.

- [ ] Handle cancel: always delete marker
<!-- /task -->

<!-- task -->
### Implement Stop handler (relay recovery)

- [ ] Check for active marker
  Read marker at `{cwd}/.workflow-state/.active_relays/{session_id}.json`. If not found → exit 0 (allow stop).

- [ ] Implement retry counter with MAX_BLOCKS=3
  Read `watchdog_blocks` from marker. If >= MAX_BLOCKS → delete marker, log warning to stderr, exit 0 (allow stop). Otherwise → increment counter, write back atomically.

- [ ] Return block decision with next(run_id) instructions
  Output JSON to stdout:
  ```json
  {"decision": "block", "reason": "Active workflow relay (run_id=X). Call mcp__plugin_memento-workflow_memento-workflow__next(run_id=\"X\") to get the pending action and continue."}
  ```
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Script must have zero dependencies beyond Python stdlib (json, os, sys, pathlib, datetime)
- Atomic file writes via tmp + os.replace() to handle concurrent access
- All errors caught and handled gracefully — corrupt markers should be treated as 'no marker'
- Exit code 0 for all paths (JSON output controls behavior, not exit code)
<!-- /constraints -->

## Implementation Notes

The hook script location is `memento-workflow/scripts/hooks/relay_watchdog.py`. It will be referenced from `hooks/hooks.json` via `${CLAUDE_PLUGIN_ROOT}/scripts/hooks/relay_watchdog.py`.

PostToolUse stdin includes `tool_response` (the MCP tool's return value as a JSON object/string). For MCP tools, this contains the action JSON.

Stop hook stdin includes `session_id`, `cwd`, `stop_hook_active`, `last_assistant_message`.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest tests/test_relay_watchdog.py -v
```
<!-- /verification -->

## Context

<!-- context:files -->
- .protocols/0006-relay-watchdog/prd.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-workflow/scripts/hooks/
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
