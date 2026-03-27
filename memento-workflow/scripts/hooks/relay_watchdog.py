#!/usr/bin/env python3
"""Claude Code hook: relay watchdog.

Handles PostToolUse (marker lifecycle) and Stop (relay recovery) events
to detect and recover from stalled workflow relay loops.

Marker files at {cwd}/.workflow-state/.active_relays/{session_id}.json
track active relays. The Stop handler blocks premature stops and instructs
the agent to call next(run_id) to resume.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_BLOCKS = 3
TERMINAL_ACTIONS = frozenset({"completed", "halted", "error", "cancelled"})
WAITING_ACTIONS = frozenset({"parallel", "subagent"})


# ── Marker helpers ──


def _safe_session_id(session_id: str) -> str | None:
    """Validate session_id contains no path traversal sequences."""
    if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
        return None
    return session_id


def _marker_path(cwd: str, session_id: str) -> Path | None:
    """Return marker file path, or None if session_id is unsafe."""
    safe_id = _safe_session_id(session_id)
    if safe_id is None:
        return None
    return Path(cwd) / ".workflow-state" / ".active_relays" / f"{safe_id}.json"


def _read_marker(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_marker(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except OSError:
        pass


def _delete_marker(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ── Parse tool response ──


def _parse_action(tool_response: object) -> dict | None:
    """Extract action dict from tool_response, handling various formats.

    Claude Code passes tool_response as a JSON string containing
    {"result": "<nested-json-string>"}.  We need to unwrap both layers.
    """
    try:
        obj = tool_response
        # Parse outer string → dict
        if isinstance(obj, str):
            obj = json.loads(obj)
        # Unwrap {"result": "<json-string>"} envelope
        if isinstance(obj, dict):
            raw = obj.get("result", obj)
            if isinstance(raw, str):
                return json.loads(raw)
            if isinstance(raw, dict):
                return raw
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return None


# ── Event handlers ──


def handle_post_tool_use(data: dict) -> None:
    """Manage marker lifecycle based on MCP tool calls."""
    # Skip subagent calls
    if data.get("agent_id"):
        return

    session_id = data.get("session_id", "")
    cwd = data.get("cwd", "")
    if not session_id or not cwd:
        return

    tool_name = data.get("tool_name", "")
    path = _marker_path(cwd, session_id)
    if path is None:
        return

    # Dispatch on tool name suffix
    if tool_name.endswith("__cancel") or tool_name.endswith("__cleanup_runs"):
        _delete_marker(path)
        return

    action_data = _parse_action(data.get("tool_response"))
    if action_data is None:
        return

    action = action_data.get("action", "")

    if tool_name.endswith("__start"):
        if action not in TERMINAL_ACTIONS:
            tool_input = data.get("tool_input", {})
            _write_marker(path, {
                "run_id": action_data.get("run_id", ""),
                "workflow": tool_input.get("workflow", ""),
                "session_id": session_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "watchdog_blocks": 0,
            })

    elif tool_name.endswith("__submit") or tool_name.endswith("__next"):
        if action in TERMINAL_ACTIONS:
            _delete_marker(path)
        elif action in WAITING_ACTIONS:
            # Parent is handing off to child agents — allow it to idle
            marker = _read_marker(path)
            if marker:
                marker["waiting_for_children"] = True
                _write_marker(path, marker)
        else:
            # Active relay step — clear waiting flag if set (e.g. after resume)
            marker = _read_marker(path)
            if marker and marker.get("waiting_for_children"):
                del marker["waiting_for_children"]
                _write_marker(path, marker)


def handle_stop(data: dict) -> None:
    """Check for active relay marker and block stop if found."""
    session_id = data.get("session_id", "")
    cwd = data.get("cwd", "")
    if not session_id or not cwd:
        return

    path = _marker_path(cwd, session_id)
    if path is None or not path.is_file():
        return

    marker = _read_marker(path)
    if marker is None:
        return

    # Parent is waiting for child agents to complete — let it idle
    if marker.get("waiting_for_children"):
        return

    blocks = marker.get("watchdog_blocks", 0)
    if blocks >= MAX_BLOCKS:
        _delete_marker(path)
        print(
            f"[relay-watchdog] giving up after {blocks} blocks for run {marker.get('run_id', '?')}",
            file=sys.stderr,
        )
        return

    # Increment counter
    marker["watchdog_blocks"] = blocks + 1
    _write_marker(path, marker)

    run_id = marker.get("run_id", "unknown")
    workflow = marker.get("workflow", "unknown")
    reason = (
        f"Active workflow relay in progress (run_id={run_id}, workflow={workflow}). "
        f"Do NOT stop. Call mcp__plugin_memento-workflow_memento-workflow__next("
        f'run_id="{run_id}") to get the current pending action and continue '
        f"the relay loop. Process the returned action, then submit the result."
    )
    print(json.dumps({"decision": "block", "reason": reason}))


# ── Main ──


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    event = data.get("hook_event_name", "")
    if event == "PostToolUse":
        handle_post_tool_use(data)
    elif event == "Stop":
        handle_stop(data)


if __name__ == "__main__":
    main()
