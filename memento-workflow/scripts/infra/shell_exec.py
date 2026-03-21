"""Shell command execution with sandbox support."""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, NamedTuple

from .sandbox import _get_tool_cache_env, _sandbox_prefix

logger = logging.getLogger("workflow-engine")


class ShellResult(NamedTuple):
    """Result from _execute_shell()."""

    output: str
    status: str
    structured: dict[str, Any] | None
    error: str | None


def _execute_shell(
    command: str,
    cwd: str,
    env: dict[str, str] | None = None,
    script_path: str | None = None,
    args: str = "",
    stdin_data: str | None = None,
    timeout: int = 120,
) -> ShellResult:
    """Execute a shell command internally via subprocess.

    If script_path is set (absolute path), determines interpreter from extension
    (.py → python3, else bash) and runs as argv list (shell=False) for safety.
    If env is set, merges with os.environ.
    If stdin_data is set, pipes it as stdin to the subprocess.

    Commands run inside an OS-level sandbox (macOS Seatbelt / Linux bubblewrap)
    that restricts writes to cwd and /tmp. Disable with MEMENTO_SANDBOX=off.

    Returns (output, status, structured_output, error).
    """
    # Force TMPDIR=/tmp so tools (uv, npm, etc.) write temp files to /tmp
    # instead of macOS /var/folders which is outside the sandbox whitelist.
    # Redirect tool caches (npm, yarn, cargo, etc.) to /tmp so they don't
    # write to ~/.<tool> which is outside the sandbox.
    merged_env = {**os.environ, "TMPDIR": "/tmp", **_get_tool_cache_env()}
    if env:
        merged_env.update(env)

    # Fix F: Override VIRTUAL_ENV for worktree cwd that has its own .venv
    venv_in_cwd = Path(cwd) / ".venv"
    if venv_in_cwd.is_dir():
        merged_env["VIRTUAL_ENV"] = str(venv_in_cwd)
        merged_env["PATH"] = f"{venv_in_cwd}/bin:{merged_env.get('PATH', '')}"
    elif "VIRTUAL_ENV" in merged_env:
        venv_parent = Path(merged_env["VIRTUAL_ENV"]).parent
        if not Path(cwd).is_relative_to(venv_parent):
            del merged_env["VIRTUAL_ENV"]

    sandbox = _sandbox_prefix(cwd)

    cmd_argv: list[str]

    if script_path:
        ext = Path(script_path).suffix
        interpreter = "python3" if ext == ".py" else "bash"
        cmd_argv = [interpreter, script_path]
        if args:
            cmd_argv.extend(shlex.split(args))
        command = " ".join(cmd_argv)  # for logging/display only
    else:
        cmd_argv = ["bash", "-c", command]

    cmd_argv = [*sandbox, *cmd_argv]

    logger.debug(
        "shell exec: %s (cwd=%s, sandbox=%s)", command[:200], cwd, bool(sandbox)
    )
    try:
        proc = subprocess.run(
            cmd_argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=merged_env,
            input=stdin_data if stdin_data is not None else "",
        )
        output = proc.stdout.strip()
        error = proc.stderr.strip() if proc.returncode != 0 else None
        status = "success" if proc.returncode == 0 else "failure"
        structured: dict[str, Any] | None = None
        if output:
            try:
                parsed = json.loads(output)
                if isinstance(parsed, dict):
                    structured = parsed
            except (json.JSONDecodeError, ValueError):
                pass
        logger.debug(
            "shell result: status=%s output=%s", status, output[:200] if output else ""
        )
        if error:
            logger.warning("shell stderr: %s", error[:300])
        return ShellResult(output, status, structured, error)
    except subprocess.TimeoutExpired:
        logger.error("shell timeout (%ds): %s", timeout, command[:200])
        return ShellResult("", "failure", None, f"Command timed out after {timeout}s")
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("shell exception: %s", e)
        return ShellResult("", "failure", None, str(e))
