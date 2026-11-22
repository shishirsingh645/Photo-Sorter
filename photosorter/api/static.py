"""Serves the folders the page reads straight off disk, and the built frontend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from photosorter.config import Paths

NO_STORE = {"Cache-Control": "no-store"}

NO_BUILD_PAGE = """<!doctype html><meta charset="utf-8"><title>Photo Sorter</title>
<body style="font-family:system-ui;max-width:36rem;margin:3rem auto;padding:0 1rem">
<h1>The dashboard has not been built yet</h1>
<p>The server is running and its API works, but there is no web page to show.
To build it, run <code>npm run build</code> inside the <code>web</code> folder, then reload this page.</p>
<p>Working on the page itself? Start with <code>--dev</code> and use the Vite dev server instead.</p>
</body>"""

DEV_PAGE = """<!doctype html><meta charset="utf-8"><title>Photo Sorter (dev)</title>
<body style="font-family:system-ui;max-width:36rem;margin:3rem auto;padding:0 1rem">
<h1>Development mode</h1>
<p>This server only provides the API. Open the Vite dev server for the page.</p></body>"""


class _Files(StaticFiles):
    """StaticFiles that never lets the browser keep a stale copy of anything that changes."""

    def __init__(self, *args, always: bool = False, **kw):
        super().__init__(*args, **kw)
        self._always = always

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        # JSON and HTML change under the page's feet; images and videos are named by id and can be cached.
        if self._always or path.endswith((".json", ".html")) or path in ("", "."):
            resp.headers["Cache-Control"] = "no-store"
        return resp


def mount_frontend(app: FastAPI, paths: Paths, dev: bool = False) -> None:
    """Mount data/, peek/, demo/ and, unless `dev`, the built web/dist at `/`.

    Call this last: the `/` mount matches every path, so anything registered after it is shadowed.
    """
    for folder in (paths.data, paths.peek, paths.demo):
        # Created now: StaticFiles raises a 500 on every request if its folder is missing, and these only
        # appear after a scan, a peek or a demo.
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:  # a missing drive, or a file where the folder should be: skip this one mount
            continue
        app.mount(f"/{folder.name}", _Files(directory=folder, always=dev), name=folder.name)

    dist = paths.root / "web" / "dist"
    if not dev and (dist / "index.html").is_file():
        app.mount("/", _Files(directory=dist, html=True), name="web")
    else:
        page = DEV_PAGE if dev else NO_BUILD_PAGE
        app.add_api_route("/", lambda: HTMLResponse(page, headers=NO_STORE), include_in_schema=False)
