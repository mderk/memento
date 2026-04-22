#!/usr/bin/env python3
"""JSONL-over-stdio server for the workflow engine.

Drop-in replacement for the MCP server — same methods, simpler protocol.
Long-running process: one stdin/stdout pair serves any number of runs.

Protocol:
  Request:  {"id": "...", "method": "...", "params": {...}}\\n
  Response: {"id": "...", "result": ...}\\n
  Error:    {"id": "...", "error": {"message": "...", "type": "..."}}\\n

Methods mirror MCP tools from scripts/runner.py:
  start, submit, next, cancel, status, list_workflows, cleanup_runs, open_dashboard

Most methods (except list_workflows, cleanup_runs) return JSON strings — we
re-parse them into objects before wrapping so consumers get structured results.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from typing import Any, Callable

# Import MCP tool functions as plain callables.
# FastMCP @mcp.tool() preserves the original function (verified).
from scripts.runner import (
    cancel,
    cleanup_runs,
    list_workflows,
    open_dashboard,
    start,
    status,
    submit,
)
from scripts.runner import next as _runner_next  # avoid shadowing builtin

logger = logging.getLogger("memento-workflow-server")

METHODS: dict[str, Callable[..., Any]] = {
    "start": start,
    "submit": submit,
    "next": _runner_next,
    "cancel": cancel,
    "status": status,
    "list_workflows": list_workflows,
    "cleanup_runs": cleanup_runs,
    "open_dashboard": open_dashboard,
}


def _coerce_result(value: Any) -> Any:
    """runner.py methods return JSON strings — parse into objects for clean
    nesting in the response envelope. Non-string results pass through."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _handle(line: str) -> str:
    try:
        req = json.loads(line)
    except json.JSONDecodeError as e:
        return json.dumps(
            {"id": None, "error": {"message": f"invalid json: {e}", "type": "parse_error"}}
        )

    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    if not isinstance(params, dict):
        return json.dumps(
            {"id": req_id, "error": {"message": "params must be object", "type": "invalid_params"}}
        )

    fn = METHODS.get(method)
    if fn is None:
        return json.dumps(
            {
                "id": req_id,
                "error": {
                    "message": f"unknown method: {method}",
                    "type": "method_not_found",
                    "available": sorted(METHODS.keys()),
                },
            }
        )

    try:
        result = fn(**params)
    except TypeError as e:
        return json.dumps(
            {"id": req_id, "error": {"message": f"bad params: {e}", "type": "invalid_params"}}
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("method %s failed", method)
        return json.dumps(
            {
                "id": req_id,
                "error": {
                    "message": str(e),
                    "type": e.__class__.__name__,
                    "traceback": traceback.format_exc(),
                },
            }
        )

    return json.dumps({"id": req_id, "result": _coerce_result(result)})


def main() -> None:
    debug = os.environ.get("WORKFLOW_DEBUG", "0") == "1"
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logger.info("memento-workflow stdio server ready")

    # Process one request per line; write one response per line.
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        response = _handle(line)
        sys.stdout.write(response + "\n")
        sys.stdout.flush()

    logger.info("stdin closed — exiting")


if __name__ == "__main__":
    main()
