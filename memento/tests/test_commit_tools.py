"""Tests for commit-tools.py functions."""

import argparse
import importlib.util
import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

# Load commit-tools.py as a module (filename has a hyphen)
_COMMIT_TOOLS = Path(__file__).resolve().parents[1] / "static" / "workflows" / "commit" / "commit-tools.py"
_spec = importlib.util.spec_from_file_location("commit_tools", _COMMIT_TOOLS)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_parse_porcelain = _mod._parse_porcelain
_resolve_workdir = _mod._resolve_workdir
_is_root_commit = _mod._is_root_commit
cmd_gather = _mod.cmd_gather
cmd_diff = _mod.cmd_diff
cmd_stage = _mod.cmd_stage
cmd_unstage = _mod.cmd_unstage
cmd_commit = _mod.cmd_commit
cmd_verify = _mod.cmd_verify
cmd_cleanup = _mod.cmd_cleanup


# ---------------------------------------------------------------------------
# _parse_porcelain
# ---------------------------------------------------------------------------


class TestParsePorcelain:
    def test_staged_file(self):
        staged, unstaged, untracked = _parse_porcelain("M  src/foo.py\n")
        assert staged == ["src/foo.py"]
        assert unstaged == []
        assert untracked == []

    def test_unstaged_file(self):
        staged, unstaged, untracked = _parse_porcelain(" M src/bar.py\n")
        assert staged == []
        assert unstaged == ["src/bar.py"]

    def test_untracked_file(self):
        staged, unstaged, untracked = _parse_porcelain("?? new.py\n")
        assert staged == []
        assert unstaged == []
        assert untracked == ["new.py"]

    def test_mixed(self):
        output = "M  staged.py\n M unstaged.py\n?? untracked.py\n"
        staged, unstaged, untracked = _parse_porcelain(output)
        assert staged == ["staged.py"]
        assert unstaged == ["unstaged.py"]
        assert untracked == ["untracked.py"]

    def test_renamed_file(self):
        staged, unstaged, untracked = _parse_porcelain("R  old.py -> new.py\n")
        assert staged == ["new.py"]

    def test_deleted_file(self):
        staged, unstaged, untracked = _parse_porcelain("D  removed.py\n")
        assert staged == ["removed.py"]

    def test_both_staged_and_unstaged(self):
        """File modified in index AND worktree (partial staging)."""
        staged, unstaged, untracked = _parse_porcelain("MM both.py\n")
        assert staged == ["both.py"]
        assert unstaged == ["both.py"]

    def test_empty_output(self):
        staged, unstaged, untracked = _parse_porcelain("")
        assert staged == []
        assert unstaged == []
        assert untracked == []

    def test_short_lines_ignored(self):
        staged, unstaged, untracked = _parse_porcelain("ab\n")
        assert staged == []


# ---------------------------------------------------------------------------
# _resolve_workdir
# ---------------------------------------------------------------------------


class TestResolveWorkdir:
    def test_valid_dir(self, tmp_path):
        result = _resolve_workdir(str(tmp_path))
        assert result == str(tmp_path.resolve())

    def test_template_string_ignored(self):
        result = _resolve_workdir("{{variables.workdir}}")
        assert result is None

    def test_none_input(self):
        with patch.dict("os.environ", {}, clear=True):
            result = _resolve_workdir(None)
            assert result is None

    def test_env_fallback(self, tmp_path):
        with patch.dict("os.environ", {"COMMIT_TOOLS_WORKDIR": str(tmp_path)}):
            result = _resolve_workdir(None)
            assert result == str(tmp_path.resolve())

    def test_env_template_ignored(self):
        with patch.dict("os.environ", {"COMMIT_TOOLS_WORKDIR": "{{variables.x}}"}):
            result = _resolve_workdir(None)
            assert result is None

    def test_nonexistent_dir(self):
        result = _resolve_workdir("/nonexistent/path/1234567890")
        assert result is None


# ---------------------------------------------------------------------------
# _is_root_commit
# ---------------------------------------------------------------------------


class TestIsRootCommit:
    def test_root_commit(self):
        mock_result = MagicMock(returncode=1)
        with patch.object(_mod, "_git", return_value=mock_result):
            assert _is_root_commit("/tmp") is True

    def test_non_root_commit(self):
        mock_result = MagicMock(returncode=0)
        with patch.object(_mod, "_git", return_value=mock_result):
            assert _is_root_commit("/tmp") is False


# ---------------------------------------------------------------------------
# cmd_gather
# ---------------------------------------------------------------------------


def _make_args(**kwargs) -> argparse.Namespace:
    defaults = {"workdir": None, "amend_mode": "false"}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdGather:
    def _run_gather(self, git_responses, **kwargs):
        """Run cmd_gather with mocked git calls and return parsed JSON."""
        call_count = {"n": 0}

        def mock_git(args, **kw):
            idx = call_count["n"]
            call_count["n"] += 1
            if idx < len(git_responses):
                return git_responses[idx]
            return MagicMock(returncode=0, stdout="", stderr="")

        buf = StringIO()
        with patch.object(_mod, "_git", side_effect=mock_git), patch("sys.stdout", buf):
            cmd_gather(_make_args(**kwargs))
        return json.loads(buf.getvalue())

    def test_basic_output_structure(self):
        result = self._run_gather([
            MagicMock(returncode=0, stdout="M  foo.py\n"),  # status
            MagicMock(returncode=0, stdout="1 file changed\n"),  # diff --stat
            MagicMock(returncode=0, stdout=""),  # diff --cached --stat
            MagicMock(returncode=0, stdout="abc1234 feat: something\n"),  # log
        ])
        assert result["has_staged"] is True
        assert result["staged_files"] == ["foo.py"]
        assert result["nothing_to_commit"] is False
        assert result["no_head"] is False
        assert result["diff_mode"] == "staged"

    def test_amend_mode(self):
        result = self._run_gather([
            MagicMock(returncode=0, stdout=""),  # status (clean)
            MagicMock(returncode=0, stdout=""),  # diff --stat
            MagicMock(returncode=0, stdout=""),  # diff --cached --stat
            MagicMock(returncode=0, stdout="abc1234 feat: something\n"),  # log
        ], amend_mode="true")
        assert result["diff_mode"] == "amend"
        assert result["nothing_to_commit"] is True

    def test_no_head(self):
        result = self._run_gather([
            MagicMock(returncode=0, stdout="?? new.py\n"),  # status
            MagicMock(returncode=0, stdout=""),  # diff --stat
            MagicMock(returncode=0, stdout=""),  # diff --cached --stat
            MagicMock(returncode=1, stdout="", stderr="fatal: no commits"),  # log fails
        ])
        assert result["no_head"] is True
        assert result["recent_log"] == ""

    def test_partial_staging_detected(self):
        result = self._run_gather([
            MagicMock(returncode=0, stdout="MM both.py\n"),  # status
            MagicMock(returncode=0, stdout=""),  # diff --stat
            MagicMock(returncode=0, stdout=""),  # diff --cached --stat
            MagicMock(returncode=0, stdout="abc1234 fix: x\n"),  # log
        ])
        assert result["has_partial_staging"] is True


# ---------------------------------------------------------------------------
# cmd_stage
# ---------------------------------------------------------------------------


class TestCmdStage:
    def test_invalid_json(self):
        args = argparse.Namespace(files_json="not json", workdir=None)
        buf = StringIO()
        with patch("sys.stdout", buf):
            cmd_stage(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "error"

    def test_empty_list(self):
        args = argparse.Namespace(files_json="[]", workdir=None)
        buf = StringIO()
        with patch("sys.stdout", buf):
            cmd_stage(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "error"

    def test_success(self):
        args = argparse.Namespace(files_json='["foo.py"]', workdir=None)
        buf = StringIO()
        with patch.object(_mod, "_git", return_value=MagicMock(returncode=0, stderr="")), \
             patch("sys.stdout", buf):
            cmd_stage(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "ok"
        assert result["staged"] == ["foo.py"]

    def test_git_error(self):
        args = argparse.Namespace(files_json='["bad.py"]', workdir=None)
        buf = StringIO()
        with patch.object(_mod, "_git", return_value=MagicMock(returncode=1, stderr="pathspec error")), \
             patch("sys.stdout", buf):
            cmd_stage(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# cmd_commit
# ---------------------------------------------------------------------------


class TestCmdCommit:
    def test_invalid_stdin(self):
        args = argparse.Namespace(amend_mode="false", workdir=None)
        buf = StringIO()
        with patch("sys.stdin", StringIO("not json")), patch("sys.stdout", buf):
            cmd_commit(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "error"
        assert "Invalid JSON" in result["error"]

    def test_missing_subject(self):
        args = argparse.Namespace(amend_mode="false", workdir=None)
        buf = StringIO()
        with patch("sys.stdin", StringIO('{"subject": "", "body": null}')), \
             patch("sys.stdout", buf):
            cmd_commit(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "error"
        assert "Missing commit subject" in result["error"]

    def test_success(self):
        args = argparse.Namespace(amend_mode="false", workdir=None)
        buf = StringIO()
        git_responses = [
            MagicMock(returncode=0, stdout="", stderr=""),  # git commit
            MagicMock(returncode=0, stdout="abc1234 feat: add feature\n"),  # git log
        ]
        call_count = {"n": 0}

        def mock_git(git_args, **kw):
            idx = call_count["n"]
            call_count["n"] += 1
            return git_responses[idx]

        with patch("sys.stdin", StringIO('{"subject": "feat: add feature", "body": null}')), \
             patch.object(_mod, "_git", side_effect=mock_git), \
             patch("sys.stdout", buf):
            cmd_commit(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "ok"
        assert result["sha"] == "abc1234"

    def test_amend_flag(self):
        args = argparse.Namespace(amend_mode="true", workdir=None)
        all_calls = []

        def mock_git(git_args, **kw):
            all_calls.append(git_args)
            return MagicMock(returncode=0, stdout="abc1234 fix: typo\n", stderr="")

        buf = StringIO()
        with patch("sys.stdin", StringIO('{"subject": "fix: typo"}')), \
             patch.object(_mod, "_git", side_effect=mock_git), \
             patch("sys.stdout", buf):
            cmd_commit(args)
        # First call is the commit, second is log
        assert "--amend" in all_calls[0]

    def test_nothing_to_commit_returns_skipped(self):
        args = argparse.Namespace(amend_mode="false", workdir=None)
        buf = StringIO()
        with patch("sys.stdin", StringIO('{"subject": "feat: x"}')), \
             patch.object(_mod, "_git", return_value=MagicMock(
                 returncode=1, stdout="On branch main\nnothing to commit, working tree clean\n", stderr="")), \
             patch("sys.stdout", buf):
            cmd_commit(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "skipped"
        assert "nothing to commit" in result["reason"]

    def test_body_included(self):
        args = argparse.Namespace(amend_mode="false", workdir=None)
        all_calls = []

        def mock_git(git_args, **kw):
            all_calls.append(git_args)
            return MagicMock(returncode=0, stdout="abc1234 feat: x\n", stderr="")

        buf = StringIO()
        with patch("sys.stdin", StringIO('{"subject": "feat: x", "body": "details here"}')), \
             patch.object(_mod, "_git", side_effect=mock_git), \
             patch("sys.stdout", buf):
            cmd_commit(args)
        # First call is commit: ["commit", "-m", message]
        message = all_calls[0][2]
        assert "feat: x" in message
        assert "details here" in message


# ---------------------------------------------------------------------------
# cmd_verify
# ---------------------------------------------------------------------------


class TestCmdVerify:
    def test_with_commits(self):
        args = argparse.Namespace(workdir=None, count=3)
        buf = StringIO()
        with patch.object(_mod, "_git", side_effect=[
            MagicMock(returncode=0, stdout="abc feat: x\ndef fix: y\n"),  # log
            MagicMock(returncode=0, stdout=""),  # status
        ]), patch("sys.stdout", buf):
            cmd_verify(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "ok"
        assert result["clean"] is True
        assert "abc feat: x" in result["log"]

    def test_no_head(self):
        args = argparse.Namespace(workdir=None, count=3)
        buf = StringIO()
        with patch.object(_mod, "_git", side_effect=[
            MagicMock(returncode=1, stdout="", stderr="fatal"),  # log fails
            MagicMock(returncode=0, stdout="?? new.py\n"),  # status
        ]), patch("sys.stdout", buf):
            cmd_verify(args)
        result = json.loads(buf.getvalue())
        assert result["log"] == "(no commits yet)"
        assert result["clean"] is False


# ---------------------------------------------------------------------------
# cmd_cleanup
# ---------------------------------------------------------------------------


class TestCmdCleanup:
    def test_removes_file(self, tmp_path):
        f = tmp_path / "test.patch"
        f.write_text("diff content")
        args = argparse.Namespace(path=str(f))
        buf = StringIO()
        with patch("sys.stdout", buf):
            cmd_cleanup(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "ok"
        assert result["removed"] == str(f)
        assert not f.exists()

    def test_nonexistent_file(self):
        args = argparse.Namespace(path="/nonexistent/file.patch")
        buf = StringIO()
        with patch("sys.stdout", buf):
            cmd_cleanup(args)
        result = json.loads(buf.getvalue())
        assert result["status"] == "ok"
        assert result["removed"] is None
