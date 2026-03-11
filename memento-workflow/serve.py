#!/usr/bin/env python3
"""Launcher for the memento-workflow MCP server.

This wrapper enables running the server from any directory while
preserving the relative imports inside the scripts/ package.

On macOS, the process re-execs itself inside a Seatbelt sandbox that
restricts writes to cwd and /tmp. This protects against malicious or
buggy plugins whose workflow.py files are loaded via exec().

Usage (from .mcp.json or claude mcp add):
    python serve.py
"""

import os
import platform
import sys
from pathlib import Path

# Ensure the scripts/ package is importable
engine_root = Path(__file__).resolve().parent
if str(engine_root) not in sys.path:
    sys.path.insert(0, str(engine_root))


def _apply_process_sandbox() -> None:
    """Re-exec the current process inside an OS-level sandbox.

    On macOS: uses sandbox-exec with a Seatbelt profile.
    On Linux: uses bwrap (bubblewrap) if available.

    The sandbox restricts file writes to cwd and /tmp, and denies
    reads to sensitive directories (~/.ssh, ~/.aws, ~/.gnupg).

    Skipped when MEMENTO_SANDBOX=off or already sandboxed.
    """
    if os.environ.get("MEMENTO_SANDBOX") == "off":
        return
    if os.environ.get("_MEMENTO_SANDBOXED"):
        return

    from scripts.runner import _seatbelt_profile

    cwd = str(Path.cwd().resolve())
    write_paths = [cwd, "/tmp"]

    if platform.system() == "Darwin":
        profile = _seatbelt_profile(write_paths)
        os.environ["_MEMENTO_SANDBOXED"] = "1"
        os.execvp(
            "sandbox-exec",
            ["sandbox-exec", "-p", profile, sys.executable, *sys.argv],
        )
    # Linux: bwrap if available
    elif platform.system() == "Linux":
        import shutil
        bwrap = shutil.which("bwrap")
        if bwrap:
            args = [bwrap, "--ro-bind", "/", "/"]
            for wp in write_paths:
                p = Path(wp)
                if p.exists():
                    args.extend(["--bind", str(p), str(p)])
            args.extend(["--dev", "/dev", "--proc", "/proc"])
            args.extend([sys.executable, *sys.argv])
            os.environ["_MEMENTO_SANDBOXED"] = "1"
            os.execvp(bwrap, args)


if __name__ == "__main__":
    _apply_process_sandbox()

    from scripts.runner import main
    main()
