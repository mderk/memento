"""Tests for dev-tools.py parser functions."""

import importlib.util
import sys
from pathlib import Path

import pytest

# Load dev-tools.py as a module (filename has a hyphen)
_DEV_TOOLS = Path(__file__).resolve().parents[1] / "static" / "workflows" / "develop" / "dev-tools.py"
_spec = importlib.util.spec_from_file_location("dev_tools", _DEV_TOOLS)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

parse_pytest_output = _mod.parse_pytest_output
_adjust_paths_for_cd = _mod._adjust_paths_for_cd


# ---------------------------------------------------------------------------
# Verbose mode (default pytest output with ===== delimiters)
# ---------------------------------------------------------------------------


class TestParsePytestVerbose:
    def test_all_passed(self):
        raw = {
            "exit_code": 0,
            "stdout": "test_a.py ...\n============================== 3 passed in 0.12s ==============================\n",
            "stderr": "",
        }
        r = parse_pytest_output(raw)
        assert r["status"] == "green"
        assert r["passed"] == 3
        assert r["failed"] == 0
        assert r["summary"] == "3 passed in 0.12s"

    def test_mixed_results(self):
        raw = {
            "exit_code": 1,
            "stdout": (
                "= FAILURES =\nFAILED test_b.py::test_foo\n"
                "============ 2 failed, 5 passed, 1 skipped in 1.23s ============\n"
            ),
            "stderr": "",
        }
        r = parse_pytest_output(raw)
        assert r["status"] == "red"
        assert r["passed"] == 5
        assert r["failed"] == 2
        assert r["skipped"] == 1
        assert "test_b.py::test_foo" in r["failures"]

    def test_errors_only(self):
        raw = {
            "exit_code": 1,
            "stdout": "======== 1 error in 0.50s ========\n",
            "stderr": "",
        }
        r = parse_pytest_output(raw)
        assert r["status"] == "red"
        assert r["errors"] == 1

    def test_warnings(self):
        raw = {
            "exit_code": 0,
            "stdout": "====== 10 passed, 2 warnings in 0.80s ======\n",
            "stderr": "",
        }
        r = parse_pytest_output(raw)
        assert r["status"] == "green"
        assert r["passed"] == 10


# ---------------------------------------------------------------------------
# Quiet mode (-q flag, no ===== delimiters)
# ---------------------------------------------------------------------------


class TestParsePytestQuiet:
    def test_all_passed(self):
        raw = {
            "exit_code": 0,
            "stdout": "...............\n15 passed in 2.94s\n",
            "stderr": "",
        }
        r = parse_pytest_output(raw)
        assert r["status"] == "green"
        assert r["passed"] == 15
        assert r["summary"] == "15 passed in 2.94s"

    def test_failures(self):
        raw = {
            "exit_code": 1,
            "stdout": "..F..\nFAILED test_x.py::test_bar\n2 failed, 3 passed in 1.10s\n",
            "stderr": "",
        }
        r = parse_pytest_output(raw)
        assert r["status"] == "red"
        assert r["passed"] == 3
        assert r["failed"] == 2
        assert "test_x.py::test_bar" in r["failures"]

    def test_error(self):
        raw = {
            "exit_code": 1,
            "stdout": "1 error in 0.30s\n",
            "stderr": "",
        }
        r = parse_pytest_output(raw)
        assert r["status"] == "red"
        assert r["errors"] == 1

    def test_mixed_with_skipped(self):
        raw = {
            "exit_code": 0,
            "stdout": "...s..\n5 passed, 1 skipped in 0.50s\n",
            "stderr": "",
        }
        r = parse_pytest_output(raw)
        assert r["status"] == "green"
        assert r["passed"] == 5
        assert r["skipped"] == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestParsePytestEdgeCases:
    def test_no_output(self):
        raw = {"exit_code": 1, "stdout": "", "stderr": ""}
        r = parse_pytest_output(raw)
        assert r["status"] == "error"
        assert r["passed"] == 0

    def test_crash_no_summary(self):
        raw = {
            "exit_code": 2,
            "stdout": "",
            "stderr": "ImportError: No module named 'foo'\n",
        }
        r = parse_pytest_output(raw)
        assert r["status"] == "error"

    def test_exit_code_zero_no_summary(self):
        raw = {"exit_code": 0, "stdout": "no tests ran\n", "stderr": ""}
        r = parse_pytest_output(raw)
        assert r["status"] == "green"


# ---------------------------------------------------------------------------
# _adjust_paths_for_cd
# ---------------------------------------------------------------------------


class TestAdjustPathsForCd:
    def test_no_cd_prefix(self):
        files = ["tests/test_foo.py", "src/bar.py"]
        assert _adjust_paths_for_cd("uv run pytest", files) == files

    def test_cd_strips_prefix(self):
        files = ["backend/tests/test_foo.py", "backend/tests/test_bar.py"]
        result = _adjust_paths_for_cd("cd backend && uv run pytest", files)
        assert result == ["tests/test_foo.py", "tests/test_bar.py"]

    def test_cd_excludes_outside_files(self):
        files = ["backend/tests/test_foo.py", "frontend/src/App.test.tsx", "README.md"]
        result = _adjust_paths_for_cd("cd backend && uv run pytest", files)
        assert result == ["tests/test_foo.py"]

    def test_cd_with_trailing_slash(self):
        files = ["backend/tests/test_foo.py"]
        result = _adjust_paths_for_cd("cd backend/ && uv run pytest", files)
        assert result == ["tests/test_foo.py"]


