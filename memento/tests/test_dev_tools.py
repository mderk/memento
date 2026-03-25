"""Tests for dev-tools.py parser functions."""

import importlib.util
import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# Load dev-tools.py as a module (filename has a hyphen)
_DEV_TOOLS = Path(__file__).resolve().parents[1] / "static" / "workflows" / "develop" / "dev-tools.py"
_spec = importlib.util.spec_from_file_location("dev_tools", _DEV_TOOLS)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

parse_pytest_output = _mod.parse_pytest_output
_adjust_paths_for_cd = _mod._adjust_paths_for_cd
_exts_for_command = _mod._exts_for_command
cmd_format = _mod.cmd_format
cmd_lint = _mod.cmd_lint
cmd_coverage = _mod.cmd_coverage


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


# ---------------------------------------------------------------------------
# cmd_format
# ---------------------------------------------------------------------------


def _make_args(**kwargs):
    """Create a namespace mimicking argparse output for cmd_format."""
    import argparse
    defaults = {"scope": "changed", "target": "all", "workdir": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdFormat:
    def test_skipped_when_no_format_commands(self, tmp_path):
        analysis = {"commands": {"lint_backend": "ruff check"}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        buf = StringIO()
        with patch("sys.stdout", buf):
            cmd_format(_make_args(workdir=str(tmp_path)))

        output = buf.getvalue()
        result = json.loads(output)
        assert result["status"] == "skipped"

    def test_runs_format_command(self, tmp_path):
        analysis = {"commands": {"format_backend": "ruff format"}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        # Mock run_command to simulate successful format
        with patch.object(_mod, "run_command", return_value={"exit_code": 0, "stdout": "", "stderr": ""}):
            buf = StringIO()
            with patch("sys.stdout", buf):
                cmd_format(_make_args(scope="all", workdir=str(tmp_path)))

            result = json.loads(buf.getvalue())
            assert result["status"] == "formatted"
            assert result["format_backend"]["status"] == "formatted"

    def test_format_error(self, tmp_path):
        analysis = {"commands": {"format_backend": "ruff format"}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        with patch.object(_mod, "run_command", return_value={"exit_code": 1, "stdout": "", "stderr": "error"}):
            buf = StringIO()
            with patch("sys.stdout", buf):
                cmd_format(_make_args(scope="all", workdir=str(tmp_path)))

            result = json.loads(buf.getvalue())
            assert result["status"] == "error"

    def test_target_filter(self, tmp_path):
        analysis = {"commands": {"format_backend": "ruff format", "format_frontend": "prettier --write ."}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        with patch.object(_mod, "run_command", return_value={"exit_code": 0, "stdout": "", "stderr": ""}) as mock_run:
            buf = StringIO()
            with patch("sys.stdout", buf):
                cmd_format(_make_args(scope="all", target="backend", workdir=str(tmp_path)))

            result = json.loads(buf.getvalue())
            assert "format_backend" in result
            assert "format_frontend" not in result
            mock_run.assert_called_once()

    def test_changed_scope_no_files(self, tmp_path):
        analysis = {"commands": {"format_backend": "ruff format"}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        with patch.object(_mod, "get_changed_files", return_value=[]):
            buf = StringIO()
            with patch("sys.stdout", buf):
                cmd_format(_make_args(scope="changed", workdir=str(tmp_path)))

            result = json.loads(buf.getvalue())
            assert result["format_backend"]["status"] == "clean"

    def test_changed_scope_with_files(self, tmp_path):
        analysis = {"commands": {"format_backend": "ruff format"}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        with patch.object(_mod, "get_changed_files", return_value=["src/app.py", "README.md"]):
            with patch.object(_mod, "run_command", return_value={"exit_code": 0, "stdout": "", "stderr": ""}) as mock_run:
                buf = StringIO()
                with patch("sys.stdout", buf):
                    cmd_format(_make_args(scope="changed", workdir=str(tmp_path)))

                # Should only pass .py files, not README.md
                call_args = mock_run.call_args
                assert "src/app.py" in call_args[0][1]  # extra arg
                assert "README.md" not in call_args[0][1]


# ---------------------------------------------------------------------------
# cmd_coverage
# ---------------------------------------------------------------------------


def _make_coverage_args(**kwargs):
    """Create a namespace mimicking argparse output for cmd_coverage."""
    import argparse
    defaults = {"workdir": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdCoverage:
    def test_returns_structured_coverage_for_changed_files(self, tmp_path):
        analysis = {"commands": {"test_backend": "uv run pytest"}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        pytest_output = (
            "src/auth/service.py    50   10   80%   12-15, 42-45\n"
            "src/auth/middleware.py  30    0  100%\n"
            "TOTAL                  80   10   88%\n"
            "============================== 5 passed in 1.00s ==============================\n"
        )
        with patch.object(_mod, "run_command", return_value={"exit_code": 0, "stdout": pytest_output, "stderr": ""}):
            with patch.object(_mod, "get_changed_files", return_value=["src/auth/service.py", "src/auth/middleware.py"]):
                buf = StringIO()
                with patch("sys.stdout", buf):
                    cmd_coverage(_make_coverage_args(workdir=str(tmp_path)))

                result = json.loads(buf.getvalue())
                assert result["has_gaps"] is True
                assert "files" in result
                # service.py has gaps (80%), middleware.py is 100%
                gap_files = [f for f in result["files"] if f["coverage"] < 100]
                assert len(gap_files) == 1
                assert "service.py" in gap_files[0]["path"]

    def test_no_gaps_when_all_100_percent(self, tmp_path):
        analysis = {"commands": {"test_backend": "uv run pytest"}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        pytest_output = (
            "src/auth/service.py    50    0  100%\n"
            "TOTAL                  50    0  100%\n"
            "============================== 3 passed in 0.50s ==============================\n"
        )
        with patch.object(_mod, "run_command", return_value={"exit_code": 0, "stdout": pytest_output, "stderr": ""}):
            with patch.object(_mod, "get_changed_files", return_value=["src/auth/service.py"]):
                buf = StringIO()
                with patch("sys.stdout", buf):
                    cmd_coverage(_make_coverage_args(workdir=str(tmp_path)))

                result = json.loads(buf.getvalue())
                assert result["has_gaps"] is False

    def test_no_test_command_returns_error(self, tmp_path):
        analysis = {"commands": {}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        buf = StringIO()
        with patch("sys.stdout", buf):
            cmd_coverage(_make_coverage_args(workdir=str(tmp_path)))

        result = json.loads(buf.getvalue())
        assert result["has_gaps"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# _exts_for_command — per-tool file extension mapping
# ---------------------------------------------------------------------------


class TestExtsForCommand:
    """Each tool maps to the file extensions it actually supports."""

    def test_ruff(self):
        assert _exts_for_command("uv run ruff check") == (".py",)

    def test_flake8(self):
        assert _exts_for_command("flake8") == (".py",)

    def test_black(self):
        assert _exts_for_command("uv run black") == (".py",)

    def test_mypy(self):
        assert _exts_for_command("mypy .") == (".py",)

    def test_pyright(self):
        assert _exts_for_command("uv run pyright") == (".py",)

    def test_eslint(self):
        assert _exts_for_command("npx eslint .") == (".js", ".jsx", ".ts", ".tsx")

    def test_tsc(self):
        assert _exts_for_command("tsc --noEmit") == (".ts", ".tsx")

    def test_prettier(self):
        exts = _exts_for_command("npx prettier --write .")
        assert ".ts" in exts
        assert ".css" in exts
        assert ".html" in exts
        assert ".json" in exts
        assert ".md" in exts
        assert ".py" not in exts

    def test_biome(self):
        exts = _exts_for_command("npx biome format --write .")
        assert ".ts" in exts
        assert ".css" in exts
        assert ".json" in exts
        assert ".py" not in exts

    def test_unknown_returns_none(self):
        assert _exts_for_command("some-custom-linter") is None

    def test_npm_run_returns_none(self):
        assert _exts_for_command("npm run lint") is None


# ---------------------------------------------------------------------------
# cmd_lint — file extension filtering integration
# ---------------------------------------------------------------------------


def _make_lint_args(**kwargs):
    """Create a namespace mimicking argparse output for cmd_lint."""
    import argparse
    defaults = {"scope": "changed", "target": "all", "workdir": None, "skip_typecheck": True}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdLintFileFiltering:
    """Verify that cmd_lint filters files by extension per tool."""

    def test_ruff_skips_ts_files(self, tmp_path):
        """ruff should only receive .py files, not .ts/.tsx."""
        analysis = {"commands": {"lint_backend": "uv run ruff check"}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        changed = ["src/app.py", "web/App.tsx", "web/utils.ts"]
        with patch.object(_mod, "get_changed_files", return_value=changed):
            with patch.object(_mod, "run_command", return_value={"exit_code": 0, "stdout": "", "stderr": ""}) as mock_run:
                buf = StringIO()
                with patch("sys.stdout", buf):
                    cmd_lint(_make_lint_args(workdir=str(tmp_path)))

                call_args = mock_run.call_args
                extra = call_args[0][1]  # second positional arg = extra files
                assert "src/app.py" in extra
                assert "App.tsx" not in extra
                assert "utils.ts" not in extra

    def test_eslint_skips_py_files(self, tmp_path):
        """eslint only understands JS/TS — .py files should be excluded."""
        analysis = {"commands": {"lint_frontend": "npx eslint ."}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        changed = ["src/app.py", "web/App.tsx", "web/utils.ts"]
        with patch.object(_mod, "get_changed_files", return_value=changed):
            with patch.object(_mod, "run_command", return_value={"exit_code": 0, "stdout": "", "stderr": ""}) as mock_run:
                buf = StringIO()
                with patch("sys.stdout", buf):
                    cmd_lint(_make_lint_args(workdir=str(tmp_path)))

                call_args = mock_run.call_args
                extra = call_args[0][1]
                assert "app.py" not in extra
                assert "App.tsx" in extra
                assert "utils.ts" in extra

    def test_ruff_no_matching_files_reports_clean(self, tmp_path):
        """When only .ts files changed, ruff should report clean (no files to lint)."""
        analysis = {"commands": {"lint_backend": "uv run ruff check"}}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        changed = ["web/App.tsx", "web/utils.ts"]
        with patch.object(_mod, "get_changed_files", return_value=changed):
            buf = StringIO()
            with patch("sys.stdout", buf):
                cmd_lint(_make_lint_args(workdir=str(tmp_path)))

            result = json.loads(buf.getvalue())
            assert result["lint_backend"]["status"] == "clean"

    def test_fullstack_each_tool_gets_its_files(self, tmp_path):
        """ruff gets .py only, eslint gets .ts/.tsx only — no cross-contamination."""
        analysis = {"commands": {
            "lint_backend": "uv run ruff check",
            "lint_frontend": "npx eslint .",
        }}
        (tmp_path / ".memory_bank").mkdir()
        (tmp_path / ".memory_bank" / "project-analysis.json").write_text(json.dumps(analysis))

        changed = ["src/app.py", "src/models.py", "web/App.tsx", "web/utils.ts"]
        with patch.object(_mod, "get_changed_files", return_value=changed):
            calls = []
            def capture_run(cmd, extra="", **kwargs):
                calls.append((cmd, extra))
                return {"exit_code": 0, "stdout": "", "stderr": ""}

            with patch.object(_mod, "run_command", side_effect=capture_run):
                buf = StringIO()
                with patch("sys.stdout", buf):
                    cmd_lint(_make_lint_args(workdir=str(tmp_path)))

            ruff_call = next((cmd, extra) for cmd, extra in calls if "ruff" in cmd)
            eslint_call = next((cmd, extra) for cmd, extra in calls if "eslint" in cmd)

            assert "app.py" in ruff_call[1]
            assert "App.tsx" not in ruff_call[1]
            assert "App.tsx" in eslint_call[1]
            assert "app.py" not in eslint_call[1]
