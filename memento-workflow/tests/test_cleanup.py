"""Tests for the cleanup module (scripts/cleanup.py).

Covers date parsing, run scanning, filtering, and actual deletion logic.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

# cleanup.py is a standalone module with no relative imports — safe to import directly
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))

from scripts.cleanup import _parse_date, cleanup, filter_runs, scan_runs  # noqa: E402


# ── Fixtures ──


@pytest.fixture
def state_dir(tmp_path):
    """Create a .workflow-state/ with 3 runs for testing."""
    sd = tmp_path / ".workflow-state"

    # Run 1: completed, old
    r1 = sd / "aaa111aaa111"
    r1.mkdir(parents=True)
    (r1 / "meta.json").write_text(json.dumps({
        "run_id": "aaa111aaa111",
        "workflow": "test-wf",
        "cwd": str(tmp_path),
        "status": "completed",
        "started_at": "2026-01-15T10:00:00+00:00",
    }))
    (r1 / "artifact.txt").write_text("data1")

    # Run 2: completed, recent
    r2 = sd / "bbb222bbb222"
    r2.mkdir(parents=True)
    (r2 / "meta.json").write_text(json.dumps({
        "run_id": "bbb222bbb222",
        "workflow": "test-wf",
        "cwd": str(tmp_path),
        "status": "completed",
        "started_at": "2026-03-10T10:00:00+00:00",
    }))
    (r2 / "artifact.txt").write_text("data2")

    # Run 3: error, old
    r3 = sd / "ccc333ccc333"
    r3.mkdir(parents=True)
    (r3 / "meta.json").write_text(json.dumps({
        "run_id": "ccc333ccc333",
        "workflow": "test-wf",
        "cwd": str(tmp_path),
        "status": "error",
        "started_at": "2026-02-01T10:00:00+00:00",
    }))

    return sd


# ── _parse_date ──


class TestParseDate:
    def test_yyyy_mm_dd(self):
        dt = _parse_date("2026-03-01")
        assert dt == datetime(2026, 3, 1, tzinfo=timezone.utc)

    def test_iso_8601_with_tz(self):
        dt = _parse_date("2026-03-01T10:30:00+00:00")
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.hour == 10
        assert dt.tzinfo is not None

    def test_iso_8601_naive_gets_utc(self):
        dt = _parse_date("2026-03-01T10:30:00")
        assert dt.tzinfo == timezone.utc

    def test_whitespace_stripped(self):
        dt = _parse_date("  2026-03-01  ")
        assert dt == datetime(2026, 3, 1, tzinfo=timezone.utc)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_date("not-a-date")


# ── scan_runs ──


class TestScanRuns:
    def test_finds_all_runs(self, state_dir):
        runs = scan_runs(state_dir)
        ids = {r["run_id"] for r in runs}
        assert ids == {"aaa111aaa111", "bbb222bbb222", "ccc333ccc333"}

    def test_includes_meta_fields(self, state_dir):
        runs = scan_runs(state_dir)
        r1 = next(r for r in runs if r["run_id"] == "aaa111aaa111")
        assert r1["status"] == "completed"
        assert r1["workflow"] == "test-wf"
        assert r1["started_at"] == "2026-01-15T10:00:00+00:00"

    def test_computes_size(self, state_dir):
        runs = scan_runs(state_dir)
        r1 = next(r for r in runs if r["run_id"] == "aaa111aaa111")
        assert r1["size"] > 0

    def test_nonexistent_dir(self, tmp_path):
        assert scan_runs(tmp_path / "nope") == []

    def test_empty_dir(self, tmp_path):
        sd = tmp_path / ".workflow-state"
        sd.mkdir()
        assert scan_runs(sd) == []

    def test_missing_meta(self, tmp_path):
        sd = tmp_path / ".workflow-state"
        run_dir = sd / "fff666fff666"
        run_dir.mkdir(parents=True)
        runs = scan_runs(sd)
        assert len(runs) == 1
        assert runs[0]["status"] == "unknown"
        assert runs[0]["meta"] is None

    def test_corrupt_meta(self, tmp_path):
        sd = tmp_path / ".workflow-state"
        run_dir = sd / "fff666fff666"
        run_dir.mkdir(parents=True)
        (run_dir / "meta.json").write_text("{bad json")
        runs = scan_runs(sd)
        assert len(runs) == 1
        assert runs[0]["meta"] is None

    def test_skips_hidden_dirs(self, tmp_path):
        sd = tmp_path / ".workflow-state"
        sd.mkdir()
        (sd / ".hidden").mkdir()
        (sd / "aaa111aaa111").mkdir()
        runs = scan_runs(sd)
        assert len(runs) == 1


# ── filter_runs ──


class TestFilterRuns:
    def test_remove_all(self, state_dir):
        runs = scan_runs(state_dir)
        to_remove = filter_runs(runs, remove_all=True)
        assert len(to_remove) == 3

    def test_filter_by_status(self, state_dir):
        runs = scan_runs(state_dir)
        to_remove = filter_runs(runs, remove_all=False, status="error")
        assert len(to_remove) == 1
        assert to_remove[0]["run_id"] == "ccc333ccc333"

    def test_filter_by_before_date(self, state_dir):
        runs = scan_runs(state_dir)
        before = _parse_date("2026-02-15")
        to_remove = filter_runs(runs, before=before)
        ids = {r["run_id"] for r in to_remove}
        assert "aaa111aaa111" in ids  # Jan 15 < Feb 15
        assert "ccc333ccc333" in ids  # Feb 1 < Feb 15
        assert "bbb222bbb222" not in ids  # Mar 10 >= Feb 15

    def test_keep_most_recent(self, state_dir):
        runs = scan_runs(state_dir)
        to_remove = filter_runs(runs, remove_all=True, keep=1)
        assert len(to_remove) == 2
        # The most recent (bbb222, Mar 10) should be kept
        removed_ids = {r["run_id"] for r in to_remove}
        assert "bbb222bbb222" not in removed_ids

    def test_keep_all(self, state_dir):
        runs = scan_runs(state_dir)
        to_remove = filter_runs(runs, remove_all=True, keep=10)
        assert len(to_remove) == 0

    def test_combined_before_and_status(self, state_dir):
        runs = scan_runs(state_dir)
        before = _parse_date("2026-03-15")
        to_remove = filter_runs(runs, before=before, status="completed")
        ids = {r["run_id"] for r in to_remove}
        assert "aaa111aaa111" in ids
        assert "bbb222bbb222" in ids
        assert "ccc333ccc333" not in ids  # status=error

    def test_empty_runs(self):
        assert filter_runs([], remove_all=True) == []


# ── cleanup (integration) ──


class TestCleanup:
    def test_dry_run_does_not_delete(self, state_dir, tmp_path):
        result = cleanup(str(tmp_path), remove_all=True, dry_run=True)
        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["removed"] == 3
        # Directories still exist
        assert (state_dir / "aaa111aaa111").exists()
        assert (state_dir / "bbb222bbb222").exists()
        assert (state_dir / "ccc333ccc333").exists()

    def test_actual_delete(self, state_dir, tmp_path):
        result = cleanup(str(tmp_path), remove_all=True)
        assert result["status"] == "success"
        assert result["removed"] == 3
        assert result["freed_bytes"] > 0
        # Directories gone
        assert not (state_dir / "aaa111aaa111").exists()
        assert not (state_dir / "bbb222bbb222").exists()
        assert not (state_dir / "ccc333ccc333").exists()

    def test_delete_with_filter(self, state_dir, tmp_path):
        result = cleanup(str(tmp_path), status="error")
        assert result["removed"] == 1
        assert result["skipped"] == 2
        assert not (state_dir / "ccc333ccc333").exists()
        assert (state_dir / "aaa111aaa111").exists()

    def test_no_state_dir(self, tmp_path):
        result = cleanup(str(tmp_path / "nonexistent"))
        assert result["status"] == "success"
        assert result["removed"] == 0

    def test_invalid_before_date(self, state_dir, tmp_path):
        result = cleanup(str(tmp_path), before="not-a-date")
        assert result["status"] == "error"

    def test_freed_mb(self, state_dir, tmp_path):
        result = cleanup(str(tmp_path), remove_all=True)
        assert "freed_mb" in result
        assert isinstance(result["freed_mb"], float)
        assert result["freed_mb"] >= 0
        # freed_bytes is more precise for small test fixtures
        assert result["freed_bytes"] > 0
