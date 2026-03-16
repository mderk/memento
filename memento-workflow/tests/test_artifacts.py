"""Unit tests for the artifacts module."""

import json

import pytest

from conftest import _state_ns

exec_key_to_artifact_path = _state_ns["exec_key_to_artifact_path"]
write_shell_artifacts = _state_ns["write_shell_artifacts"]
write_llm_prompt_artifact = _state_ns["write_llm_prompt_artifact"]
write_llm_output_artifact = _state_ns["write_llm_output_artifact"]
write_meta = _state_ns["write_meta"]


# ---------------------------------------------------------------------------
# exec_key_to_artifact_path
# ---------------------------------------------------------------------------


class TestExecKeyMapping:
    @pytest.mark.parametrize("exec_key, expected", [
        pytest.param("check-context", "check-context", id="simple"),
        pytest.param("loop:process[i=0]/step", "loop-process/i-0/step", id="loop"),
        pytest.param(
            "loop:outer[i=1]/loop:inner[i=2]/run",
            "loop-outer/i-1/loop-inner/i-2/run",
            id="loop_nested",
        ),
        pytest.param(
            "retry:flaky[attempt=2]/try-cmd",
            "retry-flaky/attempt-2/try-cmd",
            id="retry",
        ),
        pytest.param(
            "sub:call-helper/helper-echo",
            "sub-call-helper/helper-echo",
            id="sub",
        ),
        pytest.param(
            "par:batch[lane=1]/inner",
            "par-batch/lane-1/inner",
            id="par",
        ),
        pytest.param(
            "par-batch:regen[i=0]/par:x[i=1]/step",
            "par-batch-regen/i-0/par-x/i-1/step",
            id="par_batch_prefix",
        ),
        pytest.param("detect-stack", "detect-stack", id="no_prefix"),
    ])
    def test_mapping(self, exec_key, expected):
        assert exec_key_to_artifact_path(exec_key) == expected

    def test_no_collision_different_key_names(self):
        """Different bracket key names produce different paths."""
        a = exec_key_to_artifact_path("retry:x[attempt=0]/step")
        b = exec_key_to_artifact_path("loop:x[i=0]/step")
        assert a != b

    def test_traversal_stripped(self):
        assert ".." not in exec_key_to_artifact_path("../../etc/passwd")

    def test_absolute_path_stripped(self):
        result = exec_key_to_artifact_path("/etc/passwd")
        assert not result.startswith("/")

    def test_traversal_in_segments(self):
        result = exec_key_to_artifact_path("loop:items[i=0]/../../../etc")
        assert ".." not in result


# ---------------------------------------------------------------------------
# write_shell_artifacts
# ---------------------------------------------------------------------------


class TestWriteShellArtifacts:
    def test_writes_files(self, tmp_path):
        art_dir = tmp_path / "artifacts"
        rel = write_shell_artifacts(
            art_dir, "detect", "echo hello", "hello", None, None,
        )
        assert rel == "detect"
        assert (art_dir / "detect" / "command.txt").read_text() == "echo hello"
        assert (art_dir / "detect" / "output.txt").read_text() == "hello"
        assert not (art_dir / "detect" / "error.txt").exists()
        assert not (art_dir / "detect" / "result.json").exists()

    def test_writes_error_and_structured(self, tmp_path):
        art_dir = tmp_path / "artifacts"
        rel = write_shell_artifacts(
            art_dir, "check", "cmd", "out", "err", {"key": "val"},
        )
        assert rel == "check"
        assert (art_dir / "check" / "error.txt").read_text() == "err"
        data = json.loads((art_dir / "check" / "result.json").read_text())
        assert data == {"key": "val"}

    def test_loop_exec_key_creates_nested_dir(self, tmp_path):
        art_dir = tmp_path / "artifacts"
        rel = write_shell_artifacts(
            art_dir, "loop:items[i=0]/process", "echo a", "a", None, None,
        )
        assert rel == "loop-items/i-0/process"
        assert (art_dir / "loop-items" / "i-0" / "process" / "command.txt").exists()

    def test_graceful_on_write_failure(self, tmp_path):
        """Returns None when directory creation fails."""
        # Use a file path as artifacts_dir so mkdir fails
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        result = write_shell_artifacts(
            blocker, "step", "cmd", "out", None, None,
        )
        assert result is None

    def test_path_traversal_blocked(self, tmp_path):
        """Exec keys with .. cannot escape artifacts directory."""
        art_dir = tmp_path / "artifacts"
        result = write_shell_artifacts(
            art_dir, "../../escape", "cmd", "out", None, None,
        )
        # Traversal must not create files outside art_dir
        assert not (tmp_path / "escape").exists()
        # Must be safely written inside art_dir (not None)
        assert result is not None
        assert (art_dir / result / "command.txt").exists()


# ---------------------------------------------------------------------------
# write_llm_prompt_artifact
# ---------------------------------------------------------------------------


class TestWriteLLMPromptArtifact:
    def test_writes_prompt(self, tmp_path):
        art_dir = tmp_path / "artifacts"
        rel = write_llm_prompt_artifact(art_dir, "analyze", "Do the thing")
        assert rel == "analyze"
        assert (art_dir / "analyze" / "prompt.md").read_text() == "Do the thing"


# ---------------------------------------------------------------------------
# write_llm_output_artifact
# ---------------------------------------------------------------------------


class TestWriteLLMOutputArtifact:
    def test_writes_output(self, tmp_path):
        art_dir = tmp_path / "artifacts"
        rel = write_llm_output_artifact(art_dir, "analyze", "result text")
        assert rel == "analyze"
        assert (art_dir / "analyze" / "output.txt").read_text() == "result text"

    def test_writes_structured(self, tmp_path):
        art_dir = tmp_path / "artifacts"
        rel = write_llm_output_artifact(
            art_dir, "analyze", "text", structured={"a": 1},
        )
        assert rel == "analyze"
        data = json.loads((art_dir / "analyze" / "structured.json").read_text())
        assert data == {"a": 1}


# ---------------------------------------------------------------------------
# write_meta
# ---------------------------------------------------------------------------


class TestWriteMeta:
    def test_writes_meta(self, tmp_path):
        run_dir = tmp_path / "run"
        ok = write_meta(
            run_dir, "abc123", "my-workflow", "/tmp/cwd",
            "running", "2026-01-01T00:00:00Z",
        )
        assert ok is True
        data = json.loads((run_dir / "meta.json").read_text())
        assert data["run_id"] == "abc123"
        assert data["workflow"] == "my-workflow"
        assert data["status"] == "running"
        assert data["started_at"] == "2026-01-01T00:00:00Z"
        assert "completed_at" not in data

    def test_writes_completed_at(self, tmp_path):
        run_dir = tmp_path / "run"
        write_meta(
            run_dir, "abc", "wf", "/tmp", "completed",
            "2026-01-01T00:00:00Z", completed_at="2026-01-01T00:01:00Z",
        )
        data = json.loads((run_dir / "meta.json").read_text())
        assert data["completed_at"] == "2026-01-01T00:01:00Z"
