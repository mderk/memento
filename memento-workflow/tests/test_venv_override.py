"""Tests for VIRTUAL_ENV override in shell_exec.py (Fix F).

Verifies that _execute_shell() correctly handles VIRTUAL_ENV when
cwd has its own .venv/ or when inherited VIRTUAL_ENV is unrelated.
"""

import os
from unittest.mock import patch

from conftest import create_runner_ns

_ns = create_runner_ns()
_execute_shell = _ns["_execute_shell"]


class TestVirtualEnvOverride:
    def test_cwd_venv_overrides_inherited(self, tmp_path):
        """When cwd has .venv/, VIRTUAL_ENV should point to it."""
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "bin").mkdir()

        result = _execute_shell("echo $VIRTUAL_ENV", str(tmp_path))
        assert result.status == "success"
        assert result.output == str(venv_dir)

    def test_cwd_venv_prepends_path(self, tmp_path):
        """When cwd has .venv/, its bin/ should be first on PATH."""
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "bin").mkdir()

        result = _execute_shell("echo $PATH", str(tmp_path))
        assert result.status == "success"
        assert result.output.startswith(f"{venv_dir}/bin:")

    def test_unrelated_venv_removed(self, tmp_path):
        """When inherited VIRTUAL_ENV points to an unrelated path, it's removed."""
        unrelated = "/some/other/project/.venv"
        with patch.dict(os.environ, {"VIRTUAL_ENV": unrelated}):
            result = _execute_shell(
                'echo "${VIRTUAL_ENV:-unset}"', str(tmp_path)
            )
            assert result.status == "success"
            assert result.output == "unset"

    def test_unrelated_venv_path_cleaned(self, tmp_path):
        """When inherited VIRTUAL_ENV is removed, its bin/ should not be on PATH."""
        unrelated = "/some/other/project/.venv"
        with patch.dict(os.environ, {"VIRTUAL_ENV": unrelated}):
            result = _execute_shell("echo $PATH", str(tmp_path))
            assert result.status == "success"
            assert "/some/other/project/.venv/bin" not in result.output

    def test_related_venv_kept(self, tmp_path):
        """When inherited VIRTUAL_ENV belongs to cwd's tree, keep it."""
        parent_venv = str(tmp_path / ".venv")
        subdir = tmp_path / "subproject"
        subdir.mkdir()

        with patch.dict(os.environ, {"VIRTUAL_ENV": parent_venv}):
            result = _execute_shell(
                'echo "${VIRTUAL_ENV:-unset}"', str(subdir)
            )
            assert result.status == "success"
            assert result.output == parent_venv

    def test_no_venv_anywhere_ok(self, tmp_path):
        """No .venv in cwd and no inherited VIRTUAL_ENV — command runs fine."""
        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        with patch.dict(os.environ, env, clear=True):
            result = _execute_shell("echo ok", str(tmp_path))
            assert result.status == "success"
            assert "ok" in result.output
