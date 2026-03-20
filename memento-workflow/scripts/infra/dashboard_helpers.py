"""Dashboard lifecycle helpers — lock file management and process startup."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger("workflow-engine")


def check_existing_dashboard(cwd_path: str) -> str | None:
    """Check if a dashboard is already running for this project. Returns URL or None."""
    import urllib.request

    lock_file = Path(cwd_path) / ".workflow-state" / ".dashboard.json"
    if not lock_file.is_file():
        return None
    try:
        info = json.loads(lock_file.read_text(encoding="utf-8"))
        url = info.get("url", "")
        pid = info.get("pid")
        if not url:
            return None
        # Check if process is alive
        if pid:
            try:
                os.kill(pid, 0)
            except OSError:
                lock_file.unlink(missing_ok=True)
                return None
        # Check if server responds
        try:
            resp = urllib.request.urlopen(f"{url}/api/info", timeout=2)
            if resp.status == 200:
                return url
        except Exception:
            lock_file.unlink(missing_ok=True)
            return None
    except (json.JSONDecodeError, OSError):
        lock_file.unlink(missing_ok=True)
    return None


def save_dashboard_lock(cwd_path: str, url: str, pid: int) -> None:
    """Save dashboard info for reuse detection."""
    lock_file = Path(cwd_path) / ".workflow-state" / ".dashboard.json"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(json.dumps({"url": url, "pid": pid}), encoding="utf-8")


def start_dashboard(cwd_path: str) -> dict:
    """Start a dashboard subprocess and return status dict.

    Returns dict with keys: status, url, pid, cwd, message, stderr (on error).
    """
    import selectors
    import webbrowser

    # Check for existing dashboard
    existing_url = check_existing_dashboard(cwd_path)
    if existing_url:
        webbrowser.open(existing_url)
        return {
            "status": "reused",
            "url": existing_url,
            "cwd": cwd_path,
            "message": f"Dashboard already running at {existing_url}",
        }

    proc = subprocess.Popen(
        [sys.executable, "-m", "dashboard", "--cwd", cwd_path, "--no-open"],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Read stderr with timeout to find "Dashboard: http://host:port"
    url = ""
    sel = selectors.DefaultSelector()
    sel.register(proc.stderr, selectors.EVENT_READ)  # type: ignore[arg-type]
    try:
        deadline = time.monotonic() + 5.0
        buf = b""
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            events = sel.select(timeout=remaining)
            if not events:
                break
            chunk = (
                proc.stderr.read1(4096)
                if hasattr(proc.stderr, "read1")
                else proc.stderr.read(4096)
            )  # type: ignore[union-attr]
            if not chunk:
                break
            buf += chunk
            text = buf.decode("utf-8", errors="replace")
            if "Dashboard:" in text:
                url = text.split("Dashboard:", 1)[1].strip().split()[0]
                break
            if proc.poll() is not None:
                break
    finally:
        sel.unregister(proc.stderr)  # type: ignore[arg-type]
        sel.close()

    if not url:
        stderr_text = buf.decode("utf-8", errors="replace") if buf else ""
        try:
            remaining_bytes = proc.stderr.read(4096) if proc.stderr else b""  # type: ignore[union-attr]
            if remaining_bytes:
                stderr_text += remaining_bytes.decode("utf-8", errors="replace")
        except Exception:
            pass
        proc.kill()
        return {
            "status": "error",
            "message": "Dashboard failed to start",
            "stderr": stderr_text.strip(),
        }

    save_dashboard_lock(cwd_path, url, proc.pid)
    webbrowser.open(url)
    return {
        "status": "started",
        "url": url,
        "pid": proc.pid,
        "cwd": cwd_path,
        "message": f"Dashboard started at {url}",
    }
