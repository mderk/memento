"""Tests for the relay watchdog hook script (scripts/hooks/relay_watchdog.py).

Tests the hook as a subprocess: provide stdin JSON, capture stdout/stderr,
verify marker file operations and JSON output.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOOK_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "relay_watchdog.py"
)


def _run_hook(input_data: dict) -> subprocess.CompletedProcess:
    """Run the hook script with JSON input on stdin."""
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        timeout=10,
    )


def _marker_dir(tmp_path: Path) -> Path:
    return tmp_path / ".workflow-state" / ".active_relays"


def _write_marker(tmp_path: Path, session_id: str, **overrides) -> Path:
    """Write a marker file and return its path."""
    d = _marker_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    marker = {
        "run_id": "test-run-001",
        "workflow": "test-wf",
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "watchdog_blocks": 0,
        **overrides,
    }
    path = d / f"{session_id}.json"
    path.write_text(json.dumps(marker), encoding="utf-8")
    return path


def _make_tool_response(action: str, run_id: str = "abc123") -> dict:
    """Build a tool_response dict (legacy format, still supported)."""
    return {"result": json.dumps({"action": action, "run_id": run_id})}


def _make_tool_response_str(action: str, run_id: str = "abc123") -> str:
    """Build a tool_response string matching actual Claude Code PostToolUse format.

    Claude Code passes tool_response as a JSON string containing
    {"result": "<nested-json-string>"} — double-encoded.
    """
    return json.dumps({"result": json.dumps({"action": action, "run_id": run_id})})


# ── Event Dispatcher Tests ──


class TestEventDispatch:
    def test_unknown_event_allows_stop(self, tmp_path):
        """Unknown hook_event_name → exit 0, no output."""
        result = _run_hook(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
            }
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_missing_event_name_allows_stop(self, tmp_path):
        """No hook_event_name → exit 0, no output."""
        result = _run_hook({"session_id": "sess-1", "cwd": str(tmp_path)})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_invalid_json_stdin(self):
        """Non-JSON stdin → exit 0 gracefully."""
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="not json",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# ── Marker Helper Tests ──


class TestMarkerHelpers:
    def test_write_marker_creates_file(self, tmp_path):
        """PostToolUse:start with non-terminal action creates marker."""
        result = _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
                "tool_input": {"workflow": "dev-wf"},
                "tool_response": _make_tool_response("prompt", "run-001"),
            }
        )
        assert result.returncode == 0
        marker_path = _marker_dir(tmp_path) / "sess-1.json"
        assert marker_path.is_file()
        data = json.loads(marker_path.read_text())
        assert data["run_id"] == "run-001"
        assert data["workflow"] == "dev-wf"
        assert data["watchdog_blocks"] == 0
        assert "created_at" in data

    def test_delete_marker_on_cancel(self, tmp_path):
        """PostToolUse:cancel deletes marker."""
        _write_marker(tmp_path, "sess-1")
        result = _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__cancel",
                "tool_response": _make_tool_response("cancelled"),
            }
        )
        assert result.returncode == 0
        assert not (_marker_dir(tmp_path) / "sess-1.json").is_file()

    def test_path_traversal_session_id_rejected(self, tmp_path):
        """Malicious session_id with ../ → no file created outside .active_relays/."""
        result = _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "../../etc/evil",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
                "tool_input": {"workflow": "test"},
                "tool_response": _make_tool_response("prompt", "run-evil"),
            }
        )
        assert result.returncode == 0
        # No marker created anywhere
        assert not (_marker_dir(tmp_path) / "../../etc/evil.json").exists()
        assert not (tmp_path / "etc" / "evil.json").exists()
        # Also rejected for Stop
        result2 = _run_hook(
            {
                "hook_event_name": "Stop",
                "session_id": "../escape",
                "cwd": str(tmp_path),
            }
        )
        assert result2.returncode == 0
        assert result2.stdout.strip() == ""

    def test_read_corrupt_marker_treated_as_absent(self, tmp_path):
        """Corrupt marker JSON → treated as no marker (Stop allows)."""
        d = _marker_dir(tmp_path)
        d.mkdir(parents=True)
        (d / "sess-1.json").write_text("not json{{{", encoding="utf-8")
        result = _run_hook(
            {
                "hook_event_name": "Stop",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "stop_hook_active": False,
            }
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# ── PostToolUse Handler Tests ──


class TestPostToolUse:
    def test_start_non_terminal_creates_marker(self, tmp_path):
        """start() returning prompt action → marker created."""
        result = _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
                "tool_input": {"workflow": "my-wf"},
                "tool_response": _make_tool_response("prompt", "run-abc"),
            }
        )
        assert result.returncode == 0
        marker = json.loads((_marker_dir(tmp_path) / "sess-1.json").read_text())
        assert marker["run_id"] == "run-abc"
        assert marker["workflow"] == "my-wf"

    def test_start_terminal_no_marker(self, tmp_path):
        """start() returning completed → no marker created."""
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
                "tool_input": {"workflow": "shell-only"},
                "tool_response": _make_tool_response("completed"),
            }
        )
        assert not (_marker_dir(tmp_path) / "sess-1.json").exists()

    def test_submit_terminal_deletes_marker(self, tmp_path):
        """submit() returning completed → marker deleted."""
        _write_marker(tmp_path, "sess-1")
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__submit",
                "tool_response": _make_tool_response("completed"),
            }
        )
        assert not (_marker_dir(tmp_path) / "sess-1.json").exists()

    def test_submit_non_terminal_keeps_marker(self, tmp_path):
        """submit() returning prompt → marker unchanged."""
        marker_path = _write_marker(tmp_path, "sess-1", run_id="original-run")
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__submit",
                "tool_response": _make_tool_response("prompt"),
            }
        )
        assert marker_path.is_file()
        assert json.loads(marker_path.read_text())["run_id"] == "original-run"

    def test_submit_halted_deletes_marker(self, tmp_path):
        """submit() returning halted → marker deleted."""
        _write_marker(tmp_path, "sess-1")
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__submit",
                "tool_response": _make_tool_response("halted"),
            }
        )
        assert not (_marker_dir(tmp_path) / "sess-1.json").exists()

    def test_submit_error_deletes_marker(self, tmp_path):
        """submit() returning error → marker deleted."""
        _write_marker(tmp_path, "sess-1")
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__submit",
                "tool_response": _make_tool_response("error"),
            }
        )
        assert not (_marker_dir(tmp_path) / "sess-1.json").exists()

    def test_cancel_deletes_marker(self, tmp_path):
        """cancel() → marker deleted."""
        _write_marker(tmp_path, "sess-1")
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__cancel",
                "tool_response": _make_tool_response("cancelled"),
            }
        )
        assert not (_marker_dir(tmp_path) / "sess-1.json").exists()

    def test_subagent_call_skipped(self, tmp_path):
        """PostToolUse with agent_id present → no marker operations."""
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "agent_id": "subagent-123",
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
                "tool_input": {"workflow": "test"},
                "tool_response": _make_tool_response("prompt", "run-sub"),
            }
        )
        assert not (_marker_dir(tmp_path) / "sess-1.json").exists()

    def test_tool_response_parse_failure_no_crash(self, tmp_path):
        """Unparseable tool_response → exit 0, no crash, no marker."""
        result = _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
                "tool_input": {"workflow": "test"},
                "tool_response": "not-json",
            }
        )
        assert result.returncode == 0
        assert not (_marker_dir(tmp_path) / "sess-1.json").exists()


# ── Stop Handler Tests ──


class TestStopHandler:
    def test_no_marker_allows_stop(self, tmp_path):
        """No marker file → exit 0, empty stdout."""
        result = _run_hook(
            {
                "hook_event_name": "Stop",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "stop_hook_active": False,
            }
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_marker_exists_blocks_stop(self, tmp_path):
        """Marker present → block decision with run_id in reason."""
        _write_marker(tmp_path, "sess-1", run_id="active-run-123")
        result = _run_hook(
            {
                "hook_event_name": "Stop",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "stop_hook_active": False,
            }
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "block"
        assert "active-run-123" in output["reason"]
        assert "next" in output["reason"]

    def test_marker_blocks_increments_counter(self, tmp_path):
        """Each block increments watchdog_blocks in the marker."""
        _write_marker(tmp_path, "sess-1", watchdog_blocks=0)
        _run_hook(
            {
                "hook_event_name": "Stop",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "stop_hook_active": False,
            }
        )
        marker = json.loads((_marker_dir(tmp_path) / "sess-1.json").read_text())
        assert marker["watchdog_blocks"] == 1

    def test_max_blocks_exceeded_allows_stop(self, tmp_path):
        """After MAX_BLOCKS (3) retries → allow stop, delete marker."""
        _write_marker(tmp_path, "sess-1", watchdog_blocks=3)
        result = _run_hook(
            {
                "hook_event_name": "Stop",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "stop_hook_active": False,
            }
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""  # no block decision
        assert not (_marker_dir(tmp_path) / "sess-1.json").is_file()

    def test_max_blocks_logs_warning(self, tmp_path):
        """After MAX_BLOCKS → warning logged to stderr."""
        _write_marker(tmp_path, "sess-1", watchdog_blocks=3, run_id="stuck-run")
        result = _run_hook(
            {
                "hook_event_name": "Stop",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "stop_hook_active": False,
            }
        )
        assert "relay-watchdog" in result.stderr
        assert "stuck-run" in result.stderr

    def test_missing_session_id_allows_stop(self, tmp_path):
        """No session_id in input → exit 0."""
        result = _run_hook(
            {
                "hook_event_name": "Stop",
                "cwd": str(tmp_path),
                "stop_hook_active": False,
            }
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_missing_cwd_allows_stop(self):
        """No cwd in input → exit 0."""
        result = _run_hook(
            {
                "hook_event_name": "Stop",
                "session_id": "sess-1",
                "stop_hook_active": False,
            }
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# ── String-format tool_response Tests (real Claude Code behavior) ──


class TestStringToolResponse:
    """Tests with tool_response as a JSON string (actual Claude Code format)."""

    def test_start_non_terminal_creates_marker(self, tmp_path):
        """start() with string response returning prompt → marker created."""
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
                "tool_input": {"workflow": "my-wf"},
                "tool_response": _make_tool_response_str("prompt", "run-str"),
            }
        )
        marker = json.loads((_marker_dir(tmp_path) / "sess-1.json").read_text())
        assert marker["run_id"] == "run-str"
        assert marker["workflow"] == "my-wf"

    def test_start_terminal_no_marker(self, tmp_path):
        """start() with string response returning completed → no marker."""
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
                "tool_input": {"workflow": "fast-wf"},
                "tool_response": _make_tool_response_str("completed"),
            }
        )
        assert not (_marker_dir(tmp_path) / "sess-1.json").exists()

    def test_submit_terminal_deletes_marker(self, tmp_path):
        """submit() with string response returning completed → marker deleted."""
        _write_marker(tmp_path, "sess-1")
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__submit",
                "tool_response": _make_tool_response_str("completed"),
            }
        )
        assert not (_marker_dir(tmp_path) / "sess-1.json").exists()

    def test_submit_non_terminal_keeps_marker(self, tmp_path):
        """submit() with string response returning prompt → marker kept."""
        marker_path = _write_marker(tmp_path, "sess-1", run_id="original-run")
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__submit",
                "tool_response": _make_tool_response_str("ask_user"),
            }
        )
        assert marker_path.is_file()
        assert json.loads(marker_path.read_text())["run_id"] == "original-run"

    def test_next_terminal_deletes_marker(self, tmp_path):
        """next() with string response returning completed → marker deleted."""
        _write_marker(tmp_path, "sess-1")
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__next",
                "tool_response": _make_tool_response_str("completed"),
            }
        )
        assert not (_marker_dir(tmp_path) / "sess-1.json").exists()


# ── Session Isolation Tests ──


class TestSessionIsolation:
    def test_two_sessions_independent_markers(self, tmp_path):
        """Two sessions create independent markers."""
        # Session A starts a workflow
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-A",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
                "tool_input": {"workflow": "wf-a"},
                "tool_response": _make_tool_response("prompt", "run-A"),
            }
        )
        # Session B starts a workflow
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-B",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__start",
                "tool_input": {"workflow": "wf-b"},
                "tool_response": _make_tool_response("prompt", "run-B"),
            }
        )
        # Both markers exist
        assert (_marker_dir(tmp_path) / "sess-A.json").is_file()
        assert (_marker_dir(tmp_path) / "sess-B.json").is_file()

    def test_completing_one_session_doesnt_affect_other(self, tmp_path):
        """Completing session A doesn't remove session B's marker."""
        _write_marker(tmp_path, "sess-A", run_id="run-A")
        _write_marker(tmp_path, "sess-B", run_id="run-B")
        # Session A completes
        _run_hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-A",
                "cwd": str(tmp_path),
                "tool_name": "mcp__plugin_memento-workflow_memento-workflow__submit",
                "tool_response": _make_tool_response("completed"),
            }
        )
        assert not (_marker_dir(tmp_path) / "sess-A.json").exists()
        assert (_marker_dir(tmp_path) / "sess-B.json").is_file()

    def test_stop_only_checks_own_session_marker(self, tmp_path):
        """Stop hook for session A doesn't see session B's marker."""
        _write_marker(tmp_path, "sess-B", run_id="run-B")
        result = _run_hook(
            {
                "hook_event_name": "Stop",
                "session_id": "sess-A",
                "cwd": str(tmp_path),
                "stop_hook_active": False,
            }
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""  # no block — A has no marker


# ── Stale Marker Cleanup Tests ──


# Import cleanup function (same sys.path pattern as test_cleanup.py)
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))

from scripts.infra.cleanup import cleanup_stale_relay_markers  # noqa: E402


class TestStaleMarkerCleanup:
    def test_removes_old_markers(self, tmp_path):
        """Markers older than max_age_hours are removed."""
        d = _marker_dir(tmp_path)
        d.mkdir(parents=True)
        old = {
            "run_id": "old",
            "session_id": "s1",
            "created_at": "2020-01-01T00:00:00+00:00",
            "watchdog_blocks": 0,
        }
        (d / "s1.json").write_text(json.dumps(old))
        removed = cleanup_stale_relay_markers(str(tmp_path), max_age_hours=24)
        assert removed == 1
        assert not (d / "s1.json").is_file()

    def test_keeps_fresh_markers(self, tmp_path):
        """Markers newer than max_age_hours are kept."""
        d = _marker_dir(tmp_path)
        d.mkdir(parents=True)
        fresh = {
            "run_id": "new",
            "session_id": "s2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "watchdog_blocks": 0,
        }
        (d / "s2.json").write_text(json.dumps(fresh))
        removed = cleanup_stale_relay_markers(str(tmp_path), max_age_hours=24)
        assert removed == 0
        assert (d / "s2.json").is_file()

    def test_removes_corrupt_markers(self, tmp_path):
        """Corrupt JSON markers are removed."""
        d = _marker_dir(tmp_path)
        d.mkdir(parents=True)
        (d / "corrupt.json").write_text("not json{{{")
        removed = cleanup_stale_relay_markers(str(tmp_path))
        assert removed == 1
        assert not (d / "corrupt.json").is_file()

    def test_missing_directory_returns_zero(self, tmp_path):
        """Non-existent .active_relays/ directory returns 0."""
        removed = cleanup_stale_relay_markers(str(tmp_path))
        assert removed == 0

    def test_mixed_old_and_fresh(self, tmp_path):
        """Only old markers removed, fresh ones kept."""
        d = _marker_dir(tmp_path)
        d.mkdir(parents=True)
        old = {
            "run_id": "old",
            "session_id": "s1",
            "created_at": "2020-01-01T00:00:00+00:00",
            "watchdog_blocks": 0,
        }
        fresh = {
            "run_id": "new",
            "session_id": "s2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "watchdog_blocks": 0,
        }
        (d / "s1.json").write_text(json.dumps(old))
        (d / "s2.json").write_text(json.dumps(fresh))
        removed = cleanup_stale_relay_markers(str(tmp_path), max_age_hours=24)
        assert removed == 1
        assert not (d / "s1.json").is_file()
        assert (d / "s2.json").is_file()

    def test_non_json_files_skipped(self, tmp_path):
        """Non-.json files in .active_relays/ are ignored."""
        d = _marker_dir(tmp_path)
        d.mkdir(parents=True)
        (d / "readme.txt").write_text("not a marker")
        (d / ".gitkeep").write_text("")
        removed = cleanup_stale_relay_markers(str(tmp_path))
        assert removed == 0
        assert (d / "readme.txt").is_file()
        assert (d / ".gitkeep").is_file()
