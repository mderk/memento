"""Starlette route handlers for the dashboard API."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any

import re

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .data import diff_runs, get_artifact_content, get_run_detail, list_runs

_RUN_ID_RE = re.compile(r"^[a-f0-9]{12}$")

logger = logging.getLogger("dashboard")

# ── Shutdown coordination ──
# Tab close sends /api/tab-closed → server waits 3s then exits.
# Refresh: pagehide fires (→ tab-closed), but the new page immediately
# sends /api/cancel-shutdown on load, so the server stays alive.

_shutdown_task: asyncio.Task[None] | None = None
_TAB_CLOSE_GRACE = 3  # seconds — enough for page reload, too short for real close


def _schedule_shutdown(reason: str, delay: float) -> None:
    """Schedule server exit after delay. Cancelable."""
    global _shutdown_task
    _cancel_shutdown()

    async def _do() -> None:
        await asyncio.sleep(delay)
        logger.info("Shutting down (%s)", reason)
        os.kill(os.getpid(), signal.SIGINT)

    _shutdown_task = asyncio.ensure_future(_do())


def _cancel_shutdown() -> None:
    global _shutdown_task
    if _shutdown_task and not _shutdown_task.done():
        _shutdown_task.cancel()
        _shutdown_task = None


# ── Route handlers ──

def _state_dir(request: Request) -> Path:
    return request.app.state.state_dir


async def handle_info(request: Request) -> Response:
    cwd: str = request.app.state.cwd
    return JSONResponse({"project": Path(cwd).name, "cwd": cwd})


async def handle_shutdown(request: Request) -> Response:
    """Immediate shutdown (close button)."""
    _schedule_shutdown("close button", delay=0.3)
    return JSONResponse({"status": "shutting_down"})


async def handle_tab_closed(request: Request) -> Response:
    """Tab closed signal. Wait briefly in case it's a refresh."""
    _schedule_shutdown("tab closed", delay=_TAB_CLOSE_GRACE)
    return JSONResponse({"status": "scheduled"})


async def handle_cancel_shutdown(request: Request) -> Response:
    """Cancel pending shutdown (sent on page load after refresh)."""
    _cancel_shutdown()
    return JSONResponse({"status": "cancelled"})


async def handle_list_runs(request: Request) -> Response:
    state_dir = _state_dir(request)
    runs = await asyncio.to_thread(list_runs, state_dir)
    return JSONResponse(runs)


async def handle_run_detail(request: Request) -> Response:
    state_dir = _state_dir(request)
    run_id = request.path_params["run_id"]
    if not _RUN_ID_RE.match(run_id):
        return JSONResponse({"error": "Invalid run_id format"}, status_code=400)
    detail = await asyncio.to_thread(get_run_detail, state_dir, run_id)
    if detail is None:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    return JSONResponse(detail)


async def handle_artifact(request: Request) -> Response:
    state_dir = _state_dir(request)
    run_id = request.path_params["run_id"]
    if not _RUN_ID_RE.match(run_id):
        return JSONResponse({"error": "Invalid run_id format"}, status_code=400)
    path = request.path_params["path"]
    content = await asyncio.to_thread(get_artifact_content, state_dir, run_id, path)
    if content is None:
        return JSONResponse({"error": "Artifact not found"}, status_code=404)

    if path.endswith(".json"):
        return Response(content, media_type="application/json")
    if path.endswith(".md"):
        return Response(content, media_type="text/markdown")
    return Response(content, media_type="text/plain")


async def handle_diff(request: Request) -> Response:
    state_dir = _state_dir(request)
    id1 = request.path_params["id1"]
    id2 = request.path_params["id2"]
    if not _RUN_ID_RE.match(id1) or not _RUN_ID_RE.match(id2):
        return JSONResponse({"error": "Invalid run_id format"}, status_code=400)
    result = await asyncio.to_thread(diff_runs, state_dir, id1, id2)
    if result is None:
        return JSONResponse({"error": "One or both runs not found"}, status_code=404)
    return JSONResponse(result)


async def ws_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint — pushes run list updates every 2 seconds."""
    await websocket.accept()
    state_dir = websocket.app.state.state_dir
    last_snapshot: list[dict[str, Any]] = []

    try:
        while True:
            runs = await asyncio.to_thread(list_runs, state_dir)

            current_ids = {r["run_id"] for r in runs}
            last_ids = {r["run_id"] for r in last_snapshot}
            last_map = {r["run_id"]: r for r in last_snapshot}

            messages: list[dict[str, Any]] = []

            for r in runs:
                if r["run_id"] not in last_ids:
                    messages.append({"type": "run_new", "run": r})

            for rid in last_ids - current_ids:
                messages.append({"type": "run_removed", "run_id": rid})

            for r in runs:
                if r["run_id"] in last_ids:
                    old = last_map[r["run_id"]]
                    if r != old:
                        messages.append({"type": "run_update", "run": r})

            for msg in messages:
                await websocket.send_json(msg)

            last_snapshot = runs
            await asyncio.sleep(2)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        logger.exception("WebSocket error")


routes = [
    Route("/api/info", handle_info),
    Route("/api/shutdown", handle_shutdown, methods=["POST"]),
    Route("/api/tab-closed", handle_tab_closed, methods=["POST"]),
    Route("/api/cancel-shutdown", handle_cancel_shutdown, methods=["POST"]),
    Route("/api/runs", handle_list_runs),
    Route("/api/runs/{run_id}", handle_run_detail),
    Route("/api/runs/{run_id}/artifacts/{path:path}", handle_artifact),
    Route("/api/diff/{id1}/{id2}", handle_diff),
    WebSocketRoute("/api/ws", ws_endpoint),
]
