"""The app factory. Binding is the caller's job and is always `photosorter.api.LOOPBACK`."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from photosorter.api import routes_events, routes_files, routes_folders, routes_jobs, routes_state
from photosorter.api.routes_state import StateSource
from photosorter.api.static import mount_frontend
from photosorter.config import Paths

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def create_app(paths: Paths, port: int = 8765, runner: StateSource | None = None, dev: bool = False) -> FastAPI:
    app = FastAPI(title="Photo Sorter")
    app.state.paths = paths
    app.state.runner = runner
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed = {f"http://{h}" for h in hosts}

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        # A page on another site can make the browser POST to localhost, but it cannot hide its Origin.
        origin = request.headers.get("origin")
        # Host on every method: a DNS-rebinding page is "same origin" to the browser and could otherwise
        # read /api/state (the photo folder's path) and the photos themselves.
        if request.headers.get("host") not in hosts:
            return JSONResponse({"detail": f"Unexpected Host. This server only answers at {sorted(hosts)}."}, 400)
        if request.method in MUTATING and origin is not None and origin not in allowed:
            return JSONResponse(
                {"detail": f"This request came from {origin}, so it was blocked. Expected {sorted(allowed)}."}, 403
            )
        return await call_next(request)

    for module in (routes_state, routes_events, routes_jobs, routes_folders, routes_files):
        app.include_router(module.router)
    mount_frontend(app, paths, dev=dev)  # last: mounts match by prefix and must not shadow /api
    return app
