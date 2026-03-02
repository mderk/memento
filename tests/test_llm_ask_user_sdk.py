"""Tests for _build_can_use_tool permission callback.

Requires claude-agent-sdk installed. Skipped by default; enable with:
    WORKFLOW_ENGINE_SDK_TESTS=1 uv run pytest tests/test_llm_ask_user_sdk.py -v
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest


SDK_TESTS_ENABLED = os.environ.get("WORKFLOW_ENGINE_SDK_TESTS", "") == "1"


pytestmark = [
    pytest.mark.skipif(
        not SDK_TESTS_ENABLED,
        reason="Set WORKFLOW_ENGINE_SDK_TESTS=1 to run SDK wiring tests.",
    )
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_engine():
    """Import engine internals (workflow-engine is not a Python package)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "workflow-engine"))
    from scripts.engine import (  # type: ignore
        StopIOHandler,
        _EmergentAskUserCapture,
        _ask_user_key,
        _build_can_use_tool,
        _CURRENT_STEP_EXEC_KEY,
    )
    return StopIOHandler, _EmergentAskUserCapture, _ask_user_key, _build_can_use_tool, _CURRENT_STEP_EXEC_KEY


def _run(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# ask_user interception tests (capture is not None)
# ---------------------------------------------------------------------------

def test_ask_user_denied_and_captured_when_no_preset_answer():
    """ask_user with capture + no preset answer → deny+interrupt, question captured."""
    sdk = pytest.importorskip("claude_agent_sdk")
    StopIOHandler, _EmergentAskUserCapture, _ask_user_key, _build_can_use_tool, _CURRENT_STEP_EXEC_KEY = _import_engine()

    io = StopIOHandler({})
    capture = _EmergentAskUserCapture()

    step_exec_key = "par:p[i=0]/step"
    token = _CURRENT_STEP_EXEC_KEY.set(step_exec_key)
    try:
        guard = _build_can_use_tool(
            allowed_tools=["mcp__engine__ask_user"],
            capture=capture,
            io_handler=io,
        )
        tool_input = {"message": "Pick one", "options": ["a", "b"]}
        res = _run(guard("mcp__engine__ask_user", tool_input, None))
    finally:
        _CURRENT_STEP_EXEC_KEY.reset(token)

    assert isinstance(res, sdk.PermissionResultDeny)
    assert res.interrupt is True

    expected_key = _ask_user_key(step_exec_key, "Pick one", ["a", "b"])
    assert capture.question_key == expected_key
    assert capture.message == "Pick one"
    assert capture.options == ["a", "b"]


def test_ask_user_allowed_when_preset_answer_exists():
    """ask_user with capture + preset answer → allow, capture stays empty."""
    sdk = pytest.importorskip("claude_agent_sdk")
    StopIOHandler, _EmergentAskUserCapture, _ask_user_key, _build_can_use_tool, _CURRENT_STEP_EXEC_KEY = _import_engine()

    step_exec_key = "step"
    q_key = _ask_user_key(step_exec_key, "Pick", ["x"])
    io = StopIOHandler({q_key: "x"})
    capture = _EmergentAskUserCapture()

    token = _CURRENT_STEP_EXEC_KEY.set(step_exec_key)
    try:
        guard = _build_can_use_tool(
            allowed_tools=["mcp__engine__ask_user"],
            capture=capture,
            io_handler=io,
        )
        tool_input = {"message": "Pick", "options": ["x"]}
        res = _run(guard("mcp__engine__ask_user", tool_input, None))
    finally:
        _CURRENT_STEP_EXEC_KEY.reset(token)

    assert isinstance(res, sdk.PermissionResultAllow)
    assert capture.question_key == ""


# ---------------------------------------------------------------------------
# ask_user without capture (not in allowed_tools)
# ---------------------------------------------------------------------------

def test_ask_user_denied_when_not_in_allowed_tools():
    """ask_user with capture=None and not in allowed_tools → regular deny (no interrupt)."""
    sdk = pytest.importorskip("claude_agent_sdk")
    StopIOHandler, _EmergentAskUserCapture, _ask_user_key, _build_can_use_tool, _CURRENT_STEP_EXEC_KEY = _import_engine()

    token = _CURRENT_STEP_EXEC_KEY.set("step")
    try:
        # No capture, ask_user not in allowed_tools → falls through to name-based deny
        guard = _build_can_use_tool(
            allowed_tools=[],
            capture=None,
            io_handler=None,
        )
        tool_input = {"message": "X", "options": []}
        res = _run(guard("mcp__engine__ask_user", tool_input, None))
    finally:
        _CURRENT_STEP_EXEC_KEY.reset(token)

    assert isinstance(res, sdk.PermissionResultDeny)
    assert res.interrupt is False


# ---------------------------------------------------------------------------
# Regular tool allow/deny tests
# ---------------------------------------------------------------------------

def test_regular_tool_allowed_when_in_allowed_tools():
    """Tool in allowed_tools → allow."""
    sdk = pytest.importorskip("claude_agent_sdk")
    _, _, _, _build_can_use_tool, _ = _import_engine()

    guard = _build_can_use_tool(
        allowed_tools=["Read", "Bash"],
        capture=None,
        io_handler=None,
    )
    res = _run(guard("Read", {"file_path": "/some/file"}, None))
    assert isinstance(res, sdk.PermissionResultAllow)

    res = _run(guard("Bash", {"command": "echo hi"}, None))
    assert isinstance(res, sdk.PermissionResultAllow)


def test_regular_tool_denied_when_not_in_allowed_tools():
    """Tool not in allowed_tools → deny (no interrupt)."""
    sdk = pytest.importorskip("claude_agent_sdk")
    _, _, _, _build_can_use_tool, _ = _import_engine()

    guard = _build_can_use_tool(
        allowed_tools=[],
        capture=None,
        io_handler=None,
    )
    res = _run(guard("Read", {"file_path": "/etc/passwd"}, None))
    assert isinstance(res, sdk.PermissionResultDeny)
    assert res.interrupt is False

    res = _run(guard("Bash", {"command": "rm -rf /"}, None))
    assert isinstance(res, sdk.PermissionResultDeny)
    assert res.interrupt is False
