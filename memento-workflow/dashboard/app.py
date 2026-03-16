"""Starlette application factory for the workflow dashboard."""

from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from . import api
from .api import routes


class _SPAStaticFiles(StaticFiles):
    """StaticFiles subclass that falls back to index.html for SPA routes."""

    async def get_response(self, path: str, scope: dict) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException:
            # File not found — serve index.html for client-side routing
            return await super().get_response("index.html", scope)


def create_app(cwd: str) -> Starlette:
    """Create and configure the dashboard Starlette app.

    Args:
        cwd: Project directory containing .workflow-state/
    """
    state_dir = Path(cwd).resolve() / ".workflow-state"

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173"],
            allow_methods=["*"],
            allow_headers=["*"],
        ),
    ]

    # Check if built frontend exists
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    extra_routes = list(routes)
    if frontend_dist.is_dir():
        extra_routes.append(
            Mount("/", app=_SPAStaticFiles(directory=str(frontend_dist), html=True)),
        )

    app = Starlette(routes=extra_routes, middleware=middleware)
    app.state.state_dir = state_dir
    app.state.cwd = str(Path(cwd).resolve())

    # Store cwd for lock file cleanup on shutdown
    api._schedule_shutdown._cwd = app.state.cwd  # type: ignore[attr-defined]

    return app
