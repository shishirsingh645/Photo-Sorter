"""The app factory. Binding is the caller's job and is always `photosorter.api.LOOPBACK`."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from photosorter.api import routes_events, routes_files, routes_folders, routes_jobs, routes_state
from photosorter.api.static import mount_frontend
from photosorter.config import Paths

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def create_app(paths: Paths, port: int = 8765, runner=None) -> FastAPI:
    app = FastAPI(title="Photo Sorter")
    app.state.paths = paths
    app.state.runner = runner
    allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        # A page on another site can make the browser POST to localhost, but it cannot hide its Origin.
        origin = request.headers.get("origin")
        if request.method in MUTATING and origin is not None and origin not in allowed:
            return JSONResponse({"detail": "This request came from another website, so it was blocked."}, 403)
        return await call_next(request)

    for module in (routes_state, routes_events, routes_jobs, routes_folders, routes_files):
        app.include_router(module.router)
    mount_frontend(app, paths)  # last: mounts match by prefix and must not shadow /api
    return app
