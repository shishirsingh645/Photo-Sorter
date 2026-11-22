"""Runs the app under uvicorn, on loopback only."""

from __future__ import annotations

import socket
import threading
import webbrowser

import uvicorn

from photosorter.api import LOOPBACK
from photosorter.api.app import create_app
from photosorter.config import Paths


def serve(paths: Paths, port: int, dev: bool, open_browser: bool) -> int:
    # One `port` feeds both the app's Origin/Host allow-list and the socket, so they cannot disagree.
    config = uvicorn.Config(create_app(paths, port=port, dev=dev), host=LOOPBACK, port=port, log_level="warning")
    sock = socket.socket()
    try:
        sock.bind((LOOPBACK, port))
    except OSError:
        sock.close()
        print(f"\nPort {port} is already in use, probably by another copy of Photo Sorter.")
        print(f"Close the other one, or use a different port: photo-sorter serve --port {port + 1}")
        return 1
    url = f"http://{LOOPBACK}:{port}/"
    print(f"Photo Sorter is running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    try:
        uvicorn.Server(config).run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    return 0
