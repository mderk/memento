"""Tests for sandbox and stdin in the workflow engine."""

import platform
from pathlib import Path

import pytest

from conftest import create_runner_ns

# Runner (fresh namespace)
_runner_ns = create_runner_ns()

# Extract functions under test
_execute_shell = _runner_ns["_execute_shell"]
_sandbox_prefix = _runner_ns["_sandbox_prefix"]
_seatbelt_profile = _runner_ns["_seatbelt_profile"]


# ---------------------------------------------------------------------------
# Seatbelt profile
# ---------------------------------------------------------------------------


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
class TestSeatbeltProfile:
    def test_resolves_symlinks(self):
        """macOS /tmp → /private/tmp should be resolved."""
        profile = _seatbelt_profile(["/tmp"])
        resolved_tmp = str(Path("/tmp").resolve())
        assert f'(subpath "{resolved_tmp}")' in profile

    def test_denies_sensitive_dirs(self):
        profile = _seatbelt_profile(["/tmp"])
        assert ".ssh" in profile
        assert ".aws" in profile
        assert ".gnupg" in profile


# ---------------------------------------------------------------------------
# Sandbox prefix
# ---------------------------------------------------------------------------


class TestSandboxPrefix:
    def test_disabled_returns_empty(self):
        orig = _runner_ns.get("SANDBOX_ENABLED")
        try:
            _runner_ns["SANDBOX_ENABLED"] = False
            assert _sandbox_prefix("/tmp") == []
        finally:
            if orig is not None:
                _runner_ns["SANDBOX_ENABLED"] = orig

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_macos_returns_sandbox_exec(self):
        prefix = _sandbox_prefix("/tmp")
        assert len(prefix) == 3
        assert prefix[0] == "sandbox-exec"
        assert prefix[1] == "-p"
        assert "(version 1)" in prefix[2]


# ---------------------------------------------------------------------------
# Sandbox execution (macOS only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS sandbox")
class TestSandboxExecution:
    def test_write_inside_cwd_allowed(self, tmp_path):
        target = tmp_path / "test.txt"
        out, status, _, _ = _execute_shell(
            f'echo hello > {target} && cat {target}',
            cwd=str(tmp_path),
        )
        assert status == "success"
        assert out == "hello"

    def test_write_to_tmp_allowed(self, tmp_path):
        target = Path("/tmp/sandbox-test-allowed.txt")
        try:
            out, status, _, _ = _execute_shell(
                f'echo hello > {target} && cat {target}',
                cwd=str(tmp_path),
            )
            assert status == "success"
            assert out == "hello"
        finally:
            target.unlink(missing_ok=True)

    def test_write_outside_cwd_blocked(self, tmp_path):
        _, status, _, err = _execute_shell(
            'echo evil > /var/tmp/sandbox-evil-test.txt',
            cwd=str(tmp_path),
        )
        assert status == "failure"
        assert "not permitted" in (err or "").lower() or "denied" in (err or "").lower()

    def test_read_system_dirs_allowed(self, tmp_path):
        out, status, _, _ = _execute_shell(
            'ls /usr/bin/env',
            cwd=str(tmp_path),
        )
        assert status == "success"


# ---------------------------------------------------------------------------
# stdin support
# ---------------------------------------------------------------------------


class TestStdinSupport:
    def test_stdin_piped(self, tmp_path):
        target = tmp_path / "output.txt"
        out, status, _, _ = _execute_shell(
            f'cat > {target} && cat {target}',
            cwd=str(tmp_path),
            stdin_data="hello from stdin",
        )
        assert status == "success"
        assert out == "hello from stdin"

    def test_stdin_none_ignored(self, tmp_path):
        out, status, _, _ = _execute_shell(
            'echo no-stdin',
            cwd=str(tmp_path),
            stdin_data=None,
        )
        assert status == "success"
        assert out == "no-stdin"

    def test_tee_pattern(self, tmp_path):
        """Test the tee pattern used in create-environment workflow."""
        target = tmp_path / "target.md"
        clean_dir = tmp_path / "clean"
        clean_dir.mkdir()
        clean = clean_dir / "target.md"
        out, status, _, _ = _execute_shell(
            f'tee {clean} > {target}',
            cwd=str(tmp_path),
            stdin_data="# Generated\nLine 2",
        )
        assert status == "success"
        assert target.read_text() == "# Generated\nLine 2"
        assert clean.read_text() == "# Generated\nLine 2"

    def test_large_content(self, tmp_path):
        content = "\n".join(f"Line {i}" for i in range(1000)) + "\n"
        target = tmp_path / "large.txt"
        out, status, _, _ = _execute_shell(
            f'cat > {target} && wc -l < {target}',
            cwd=str(tmp_path),
            stdin_data=content,
        )
        assert status == "success"
        assert out.strip() == "1000"
