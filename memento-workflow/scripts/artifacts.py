"""Artifact storage for workflow engine step outputs.

Writes per-step files to .workflow-state/<run_id>/artifacts/ so MCP
responses carry lightweight references instead of inline data.

All write functions create directories, use atomic writes (.tmp + os.replace),
and never raise — they log and swallow failures for graceful degradation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("workflow-engine")


def exec_key_to_artifact_path(exec_key: str) -> str:
    """Map an exec_key to a relative artifact directory path.

    Replace colons with hyphens, expand bracket indices to key-N/:
      check-context                      → check-context
      loop:process[i=0]/step             → loop-process/i-0/step
      retry:flaky[attempt=2]/try-cmd     → retry-flaky/attempt-2/try-cmd
      sub:call/helper                    → sub-call/helper
      par:batch[lane=1]/inner            → par-batch/lane-1/inner
      par-batch:regen[i=0]/par:x[i=1]/s → par-batch-regen/i-0/par-x/i-1/s
    """
    # Replace colons with hyphens (handles all prefixes including par-batch:)
    path = exec_key.replace(":", "-")
    # Replace [key=N] with /key-N
    path = re.sub(r"\[(\w+)=(\d+)\]", r"/\1-\2", path)
    return _sanitize_rel_path(path)


def _sanitize_rel_path(path: str) -> str:
    """Ensure path is a safe relative path (no traversal or absolute)."""
    # Reject absolute paths
    if path.startswith("/"):
        path = path.lstrip("/")
    # Collapse and reject traversal segments
    parts = [p for p in path.split("/") if p and p != ".."]
    return "/".join(parts) or "unknown"


def _ensure_step_dir(artifacts_dir: Path, exec_key: str) -> Path | None:
    """Create artifact step directory, return path or None on failure."""
    rel = exec_key_to_artifact_path(exec_key)
    step_dir = artifacts_dir / rel
    # Guard against path traversal
    try:
        resolved = step_dir.resolve()
        if not resolved.is_relative_to(artifacts_dir.resolve()):
            logger.warning("artifact path escapes artifacts_dir: %s", step_dir)
            return None
    except (ValueError, OSError):
        return None
    try:
        step_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("artifact mkdir failed %s: %s", step_dir, e)
        return None
    return step_dir


def _atomic_write(path: Path, content: str) -> bool:
    """Write content atomically via tmp file + os.replace. Returns success."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(str(tmp), str(path))
        return True
    except Exception as e:
        logger.warning("artifact write failed %s: %s", path, e)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def write_shell_artifacts(
    artifacts_dir: Path,
    exec_key: str,
    command: str,
    output: str,
    error: str | None,
    structured: dict[str, Any] | None,
) -> str | None:
    """Write shell step artifacts (command.txt, output.txt, error.txt, result.json).

    Returns the artifact relative path on success, None on failure.
    """
    step_dir = _ensure_step_dir(artifacts_dir, exec_key)
    if step_dir is None:
        return None
    rel = exec_key_to_artifact_path(exec_key)

    ok = True
    if command:
        ok = _atomic_write(step_dir / "command.txt", command) and ok
    if output:
        ok = _atomic_write(step_dir / "output.txt", output) and ok
    if error:
        ok = _atomic_write(step_dir / "error.txt", error) and ok
    if structured is not None:
        ok = _atomic_write(
            step_dir / "result.json",
            json.dumps(structured, indent=2, default=str),
        ) and ok

    return rel if ok else None


def write_llm_prompt_artifact(
    artifacts_dir: Path,
    exec_key: str,
    prompt_text: str,
) -> str | None:
    """Write LLM prompt artifact (prompt.md).

    Returns the artifact relative path on success, None on failure.
    """
    step_dir = _ensure_step_dir(artifacts_dir, exec_key)
    if step_dir is None:
        return None

    rel = exec_key_to_artifact_path(exec_key)
    if _atomic_write(step_dir / "prompt.md", prompt_text):
        return rel
    return None


def write_llm_output_artifact(
    artifacts_dir: Path,
    exec_key: str,
    output: str,
    structured: dict[str, Any] | None = None,
) -> str | None:
    """Write LLM output artifact (output.txt, structured.json).

    Returns the artifact relative path on success, None on failure.
    """
    step_dir = _ensure_step_dir(artifacts_dir, exec_key)
    if step_dir is None:
        return None

    rel = exec_key_to_artifact_path(exec_key)
    ok = True
    if output:
        ok = _atomic_write(step_dir / "output.txt", output) and ok
    if structured is not None:
        ok = _atomic_write(
            step_dir / "structured.json",
            json.dumps(structured, indent=2, default=str),
        ) and ok

    return rel if ok else None


def write_meta(
    run_dir: Path,
    run_id: str,
    workflow: str,
    cwd: str,
    status: str,
    started_at: str,
    completed_at: str | None = None,
    total_cost_usd: float | None = None,
    total_duration: float | None = None,
    steps_by_type: dict[str, int] | None = None,
) -> bool:
    """Write or update meta.json in the run directory.

    Returns True on success.
    """
    data: dict[str, Any] = {
        "run_id": run_id,
        "workflow": workflow,
        "cwd": cwd,
        "status": status,
        "started_at": started_at,
    }
    if completed_at:
        data["completed_at"] = completed_at
    if total_cost_usd is not None:
        data["total_cost_usd"] = total_cost_usd
    if total_duration is not None:
        data["total_duration"] = total_duration
    if steps_by_type:
        data["steps_by_type"] = steps_by_type

    try:
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("meta mkdir failed %s: %s", run_dir, e)
        return False

    return _atomic_write(
        run_dir / "meta.json",
        json.dumps(data, indent=2, default=str),
    )
