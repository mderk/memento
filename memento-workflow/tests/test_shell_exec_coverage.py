"""Coverage tests for infra/shell_exec.py — script_path, timeout, errors, stdin."""

from unittest.mock import patch

from conftest import create_runner_ns

_ns = create_runner_ns()
_execute_shell = _ns["_execute_shell"]


class TestShellExecScriptPath:
    def test_python_script(self, tmp_path):
        """script_path with .py extension uses python3 interpreter."""
        script = tmp_path / "test.py"
        script.write_text("import sys; print('hello from python')")
        result = _execute_shell("", str(tmp_path), script_path=str(script))
        assert result.status == "success"
        assert "hello from python" in result.output

    def test_bash_script(self, tmp_path):
        """script_path with .sh extension uses bash interpreter."""
        script = tmp_path / "test.sh"
        script.write_text("#!/bin/bash\necho 'hello from bash'")
        script.chmod(0o755)
        result = _execute_shell("", str(tmp_path), script_path=str(script))
        assert result.status == "success"
        assert "hello from bash" in result.output

    def test_script_with_args(self, tmp_path):
        """script_path with args passes arguments correctly."""
        script = tmp_path / "test.py"
        script.write_text("import sys; print(sys.argv[1])")
        result = _execute_shell(
            "", str(tmp_path), script_path=str(script), args="my_arg"
        )
        assert result.status == "success"
        assert "my_arg" in result.output


class TestShellExecTimeout:
    def test_timeout_returns_failure(self, tmp_path):
        """Commands exceeding timeout return failure with message."""
        result = _execute_shell("sleep 30", str(tmp_path), timeout=1)
        assert result.status == "failure"
        assert "timed out" in result.error


class TestShellExecErrors:
    def test_nonzero_exit_returns_failure(self, tmp_path):
        """Non-zero exit code results in failure status."""
        result = _execute_shell("exit 1", str(tmp_path))
        assert result.status == "failure"

    def test_stderr_captured_on_failure(self, tmp_path):
        """stderr is captured when command fails."""
        result = _execute_shell("echo 'err msg' >&2; exit 1", str(tmp_path))
        assert result.status == "failure"
        assert "err msg" in result.error


class TestShellExecStdin:
    def test_no_stdin_does_not_hang(self, tmp_path):
        """Without stdin_data, command gets empty string (not inherited stdin)."""
        result = _execute_shell("echo ok", str(tmp_path))
        assert result.status == "success"
        assert "ok" in result.output

    def test_stdin_data_passed(self, tmp_path):
        """When stdin_data is provided, it's passed to the process."""
        result = _execute_shell("cat", str(tmp_path), stdin_data="hello stdin")
        assert result.status == "success"
        assert "hello stdin" in result.output


class TestShellExecStructured:
    def test_json_output_parsed(self, tmp_path):
        """JSON output is parsed into structured field."""
        result = _execute_shell('echo \'{"key": "val"}\'', str(tmp_path))
        assert result.status == "success"
        assert result.structured == {"key": "val"}

    def test_non_json_output_no_structured(self, tmp_path):
        """Non-JSON output has structured=None."""
        result = _execute_shell("echo 'not json'", str(tmp_path))
        assert result.status == "success"
        assert result.structured is None

    def test_env_vars_passed(self, tmp_path):
        """Custom env vars are available to the command."""
        result = _execute_shell(
            "echo $MY_VAR", str(tmp_path), env={"MY_VAR": "custom_val"}
        )
        assert result.status == "success"
        assert "custom_val" in result.output


class TestShellExecOSError:
    def test_os_error_returns_failure(self, tmp_path):
        """OSError during subprocess execution returns failure."""
        with patch("subprocess.run", side_effect=OSError("No such file")):
            result = _execute_shell("nonexistent", str(tmp_path))
            assert result.status == "failure"
            assert "No such file" in result.error
