# Relay Watchdog — Requirements

## Problem Statement

During workflow relay execution, the Claude Code agent sometimes breaks the relay loop — it outputs text and stops instead of continuing to process the next action. The workflow checkpoint is preserved, but the loop is dead and requires human intervention to resume. This is a critical reliability issue for unattended workflow execution.

## Requirements

- Detect when the relay agent stops mid-workflow via Claude Code Stop hook
- Force the agent to continue by returning decision:block with instructions to call next(run_id)
- Track active relays via marker files at {cwd}/.workflow-state/.active_relays/{session_id}.json
- Manage marker lifecycle via PostToolUse hooks on start/submit/cancel MCP tools
- Provide session isolation — multiple Claude instances in the same project must not interfere
- Prevent infinite blocking via watchdog_blocks retry counter (max 3 attempts)
- Skip marker management for subagent tool calls (check agent_id presence)
- Ship hooks as part of memento-workflow plugin via hooks/hooks.json
- Strengthen SKILL.md relay loop wording to prevent breaks (prevention)
- Add stale marker cleanup to existing cleanup_runs() MCP tool

## Constraints

- Pure hooks approach — no changes to MCP server session_id handling (CLAUDE_SESSION_ID env var does not exist yet)
- Hook receives session_id and tool_response from Claude Code stdin — these are the only available data sources
- Stop hook does not fire on user interrupt (Ctrl+C/Esc) — this is desired behavior, not a limitation
- PostToolUse matcher must use full MCP tool names (fragile if plugin name changes)
- Plugin hooks via hooks/hooks.json — not project-level settings.json (auto-registered on install)
- Hook script must be Python (project convention, no jq dependency)

## Acceptance Criteria

- PostToolUse hook creates marker when start() returns non-terminal action
- PostToolUse hook deletes marker when submit() returns terminal action (completed/halted/error)
- PostToolUse hook deletes marker when cancel() is called
- No marker created for shell-only workflows that complete immediately in start()
- Stop hook blocks when marker exists and returns next(run_id) instructions
- Stop hook allows stop after MAX_BLOCKS (3) retries to prevent infinite loop
- Stop hook allows stop when no marker exists (workflow not running)
- Subagent tool calls (agent_id present) do not create/modify markers
- Two concurrent sessions have independent markers (session_id isolation)
- Stale markers older than 24h are cleaned by cleanup_runs()
- All existing memento-workflow tests continue to pass
- SKILL.md relay loop section includes stronger 'never break the loop' wording

## Source

Generated from task description: 2026-03-25
