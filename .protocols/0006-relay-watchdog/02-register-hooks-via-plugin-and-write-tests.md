---
id: 02-register-hooks-via-plugin-and-write-tests
status: done
estimate: 1.5h
---
# Register hooks via plugin and write tests

## Objective

<!-- objective -->
Create `hooks/hooks.json` for automatic hook registration when the plugin is installed. Write comprehensive tests for the hook script covering all event types and edge cases.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Create plugin hooks.json

- [ ] Create memento-workflow/hooks/hooks.json
  Register PostToolUse hooks with matchers for:
  - `mcp__plugin_memento-workflow_memento-workflow__start`
  - `mcp__plugin_memento-workflow_memento-workflow__submit`
  - `mcp__plugin_memento-workflow_memento-workflow__cancel`

  Register Stop hook (no matcher).

  All point to `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/relay_watchdog.py`.
<!-- /task -->

<!-- task -->
### Write hook script tests

Test the hook as a subprocess: provide stdin JSON, capture stdout/stderr, verify marker file operations.

- [ ] Test Stop handler: no marker → allow stop
  Provide Stop event stdin with valid session_id and cwd. No marker file exists. Assert: exit 0, empty stdout.

- [ ] Test Stop handler: marker exists → block with run_id

- [ ] Test Stop handler: watchdog_blocks >= MAX_BLOCKS → allow stop, marker deleted

- [ ] Test PostToolUse:start with non-terminal → marker created

- [ ] Test PostToolUse:start with terminal (completed) → no marker

- [ ] Test PostToolUse:submit with terminal → marker deleted

- [ ] Test PostToolUse:submit with non-terminal → marker unchanged

- [ ] Test PostToolUse:cancel → marker deleted

- [ ] Test subagent calls (agent_id present) → no marker changes

- [ ] Test session isolation: two sessions, independent markers
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- hooks.json must be valid JSON matching Claude Code plugin hooks schema
- Tests must run without Claude Code — test the script as a standalone subprocess
- All existing memento-workflow tests must continue to pass
<!-- /constraints -->

## Implementation Notes

Test pattern: use `subprocess.run([sys.executable, HOOK_SCRIPT], input=json_str, capture_output=True, text=True)` to invoke the hook. Set up marker files in `tmp_path` fixture. Verify file creation/deletion and stdout JSON content.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest tests/test_relay_watchdog.py -v
cd memento-workflow && uv run pytest -v
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento-workflow/hooks/
- memento-workflow/tests/
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
