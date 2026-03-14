"""Starlette application factory for the workflow dashboard."""

from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from .api import routes


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
            Mount("/", app=StaticFiles(directory=str(frontend_dist), html=True)),
        )

    app = Starlette(routes=extra_routes, middleware=middleware)
    app.state.state_dir = state_dir
    app.state.cwd = str(Path(cwd).resolve())

    return app
