"""Serves the folders the page reads straight off disk."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from photosorter.config import Paths


def mount_frontend(app: FastAPI, paths: Paths) -> None:
    """Mount data/, peek/ and demo/. Task 6 extends this one function with the built web/dist."""
    for folder in (paths.data, paths.peek, paths.demo):
        # Created now: StaticFiles raises a 500 on every request if its folder is missing, and these only
        # appear after a scan, a peek or a demo.
        folder.mkdir(parents=True, exist_ok=True)
        app.mount(f"/{folder.name}", StaticFiles(directory=folder), name=folder.name)
