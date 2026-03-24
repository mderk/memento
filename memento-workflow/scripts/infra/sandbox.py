"""Sandbox helpers for restricting shell command execution.

Provides OS-level sandboxing (macOS Seatbelt / Linux bubblewrap) and
tool-cache redirection so that subprocess writes are confined to the
working directory and /tmp.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import uuid
from pathlib import Path

logger = logging.getLogger("workflow-engine")

# Sandbox: opt-out via MEMENTO_SANDBOX=off
SANDBOX_ENABLED = os.environ.get("MEMENTO_SANDBOX", "auto") != "off"
_sandbox_off_warned = False

# Per-process cache dir under /tmp for tools that write to ~/.<tool> (outside sandbox).
# Created lazily once, reused across all _execute_shell calls so caches persist.
_SANDBOX_TOOL_CACHE: str | None = None

# Env vars that redirect tool caches into the sandbox-writable temp dir.
_TOOL_CACHE_ENVS = {
    "npm_config_cache": "npm",  # npm/npx → ~/.npm
    "YARN_CACHE_FOLDER": "yarn",  # yarn → ~/.yarn
    "PNPM_STORE_DIR": "pnpm",  # pnpm → ~/.pnpm-store
    "GOMODCACHE": "gomod",  # go modules cache (not GOPATH — that has bin/)
    "GRADLE_USER_HOME": "gradle",  # gradle → ~/.gradle
    "BUNDLE_USER_HOME": "bundler",  # bundler → ~/.bundle
}


def _get_tool_cache_env() -> dict[str, str]:
    """Return env vars redirecting tool caches to a sandbox-safe temp dir."""
    global _SANDBOX_TOOL_CACHE
    if _SANDBOX_TOOL_CACHE is None:
        _SANDBOX_TOOL_CACHE = os.path.join(
            "/tmp", f"memento-cache-{uuid.uuid4().hex[:12]}"
        )
        os.makedirs(_SANDBOX_TOOL_CACHE, exist_ok=True)
    return {
        var: os.path.join(_SANDBOX_TOOL_CACHE, subdir)
        for var, subdir in _TOOL_CACHE_ENVS.items()
    }


def _seatbelt_profile(write_paths: list[str]) -> str:
    """Generate a macOS Seatbelt sandbox profile.

    Default policy: allow all reads (deny sensitive dirs), deny all writes
    except to specified paths. Resolves symlinks for macOS (/tmp → /private/tmp).
    """
    resolved = [str(Path(p).resolve()) for p in write_paths]
    allow_clauses = "\n".join(f'  (subpath "{p}")' for p in resolved)
    return f"""(version 1)
(allow default)
(deny file-write*)
(allow file-write*
{allow_clauses}
  (literal "/dev/null")
  (regex #"^/dev/fd/"))
(deny file-read*
  (subpath "{Path.home() / ".ssh"}")
  (subpath "{Path.home() / ".aws"}")
  (subpath "{Path.home() / ".gnupg"}"))"""


def apply_process_sandbox(reexec_args: list[str]) -> None:
    """Re-exec the current process inside an OS-level sandbox.

    *reexec_args* is the command to re-exec (e.g. [sys.executable, "-m", "scripts.cli"]).

    On macOS: uses sandbox-exec with a Seatbelt profile.
    On Linux: uses bwrap (bubblewrap) if available.

    The sandbox restricts file writes to cwd and /tmp, and denies
    reads to sensitive directories (~/.ssh, ~/.aws, ~/.gnupg).

    Skipped when MEMENTO_SANDBOX=off or already sandboxed.
    """
    if not SANDBOX_ENABLED:
        return
    if os.environ.get("_MEMENTO_SANDBOXED"):
        return

    cwd = str(Path.cwd().resolve())
    cache_dir = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    write_paths = [cwd, "/tmp", cache_dir]
    os.environ["TMPDIR"] = "/tmp"

    if platform.system() == "Darwin":
        profile = _seatbelt_profile(write_paths)
        os.environ["_MEMENTO_SANDBOXED"] = "1"
        os.execvp(
            "sandbox-exec",
            ["sandbox-exec", "-p", profile, *reexec_args],
        )
    elif platform.system() == "Linux":
        bwrap = shutil.which("bwrap")
        if bwrap:
            args = [bwrap, "--ro-bind", "/", "/"]
            for wp in write_paths:
                p = Path(wp)
                if p.exists():
                    args.extend(["--bind", str(p), str(p)])
            args.extend(["--dev", "/dev", "--proc", "/proc"])
            args.extend(reexec_args)
            os.environ["_MEMENTO_SANDBOXED"] = "1"
            os.execvp(bwrap, args)


def _sandbox_prefix(cwd: str) -> list[str]:
    """Return command prefix for sandboxed execution, or [] if unavailable.

    Skips if the process is already sandboxed (set by cli.py).
    """
    if not SANDBOX_ENABLED:
        global _sandbox_off_warned
        if not _sandbox_off_warned:
            logger.warning(
                "Sandbox disabled via MEMENTO_SANDBOX=off — shell commands run unrestricted"
            )
            _sandbox_off_warned = True
        return []
    if os.environ.get("_MEMENTO_SANDBOXED"):
        return []
    # Allow writes to cwd, /tmp, and package manager caches (uv, pip, npm).
    # Note: TMPDIR is set to /tmp in merged_env by _execute_shell so tools
    # use /tmp instead of macOS /var/folders (which is outside the sandbox).
    cache_dir = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    write_paths = [cwd, "/tmp", cache_dir]
    if platform.system() == "Darwin":
        return ["sandbox-exec", "-p", _seatbelt_profile(write_paths)]
    if shutil.which("bwrap"):
        args = ["bwrap", "--ro-bind", "/", "/"]
        for wp in write_paths:
            p = Path(wp)
            if p.exists():
                args.extend(["--bind", str(p), str(p)])
        args.extend(["--dev", "/dev", "--proc", "/proc"])
        return args
    logger.warning("Sandbox not available (install bubblewrap on Linux)")
    return []
