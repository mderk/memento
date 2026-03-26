---
id: 01-implement-relay-watchdog-hook-script
status: done
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

- [ ] Dispatch on tool_name to determine which MCP tool was called
  The same script handles start/submit/cancel. Parse `tool_name` from stdin to dispatch:
  - Ends with `__start` → start handler
  - Ends with `__submit` → submit handler
  - Ends with `__cancel` → cancel handler

- [ ] Parse tool_response to extract action type and run_id
  `tool_response` contains the MCP tool's return value. It may be a JSON string or a dict with a `result` key containing a JSON string. Parse to get `action` and `run_id` fields.

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

### PostToolUse stdin example

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/user/.claude/projects/.../session.jsonl",
  "cwd": "/Users/user/my-project",
  "permission_mode": "default",
  "hook_event_name": "PostToolUse",
  "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
  "tool_input": {
    "workflow": "development",
    "variables": {"task": "add feature"},
    "cwd": "/Users/user/my-project"
  },
  "tool_response": {
    "result": "{\"action\": \"prompt\", \"run_id\": \"698a292eb559\", \"exec_key\": \"step1\", \"prompt\": \"...\", \"_display\": \"Step [step1]: Processing prompt\"}"
  },
  "tool_use_id": "toolu_01ABC123"
}
```

**Key fields:** `tool_name` (dispatch on suffix: `__start`/`__submit`/`__cancel`), `tool_response.result` (JSON string with `action` and `run_id`), `tool_input.workflow` (workflow name for marker), `agent_id` (present only for subagent calls — skip if set).

**Parsing `tool_response`:** The `result` field is a JSON string. Parse it with `json.loads(tool_response["result"])` to get the action dict. Handle both `tool_response.result` (string) and direct dict formats gracefully.

### Stop hook stdin example

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/user/.claude/projects/.../session.jsonl",
  "cwd": "/Users/user/my-project",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": false,
  "last_assistant_message": "Step [step2]: Processing prompt..."
}
```

**Key fields:** `session_id` + `cwd` (locate marker file), `stop_hook_active` (true if already in a stop hook continuation — not used for dispatch since marker is the authority).

## Verification

<!-- verification -->
```bash
# Smoke test: Stop event with no marker → should exit 0 with no output
echo '{"hook_event_name":"Stop","session_id":"test","cwd":"/tmp/nonexistent","stop_hook_active":false}' | python3 memento-workflow/scripts/hooks/relay_watchdog.py

# Smoke test: PostToolUse start → should create marker (check manually)
echo '{"hook_event_name":"PostToolUse","session_id":"test","cwd":"/tmp/test-watchdog","tool_name":"mcp__plugin_memento-workflow_memento-workflow__start","tool_input":{"workflow":"test"},"tool_response":{"result":"{\"action\":\"prompt\",\"run_id\":\"abc123\"}"}}' | python3 memento-workflow/scripts/hooks/relay_watchdog.py && cat /tmp/test-watchdog/.workflow-state/.active_relays/test.json
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
