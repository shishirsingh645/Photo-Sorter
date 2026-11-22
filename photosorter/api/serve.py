"""Runs the app under uvicorn, on loopback only."""

from __future__ import annotations

from photosorter.config import Paths


def serve(paths: Paths, port: int, dev: bool, open_browser: bool) -> int:
    return 0
