"""Serves the folders the page reads straight off disk."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from photosorter.config import Paths


def mount_frontend(app: FastAPI, paths: Paths, dev: bool = False) -> None:
    """Mount data/, peek/ and demo/. Task 6 extends this one function with the built web/dist.

    `dev` is the seam Task 6 uses to skip web/dist and send no-store; it does nothing yet.
    """
    for folder in (paths.data, paths.peek, paths.demo):
        # Created now: StaticFiles raises a 500 on every request if its folder is missing, and these only
        # appear after a scan, a peek or a demo.
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:  # a missing drive, or a file where the folder should be: skip this one mount
            continue
        app.mount(f"/{folder.name}", StaticFiles(directory=folder), name=folder.name)
