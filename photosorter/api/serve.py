"""Runs the app under uvicorn, on loopback only."""

from __future__ import annotations

import socket
import threading
import webbrowser

import uvicorn

from photosorter.api import LOOPBACK
from photosorter.api.app import create_app
from photosorter.config import Paths
from photosorter.jobs import JobRunner


def serve(paths: Paths, port: int, dev: bool, open_browser: bool) -> int:
    sock = socket.socket()
    try:
        sock.bind((LOOPBACK, port))
    except OverflowError:
        sock.close()
        print(f"\n{port} is not a usable port. Ports are numbers from 0 to 65535, for example --port 8766.")
        return 1
    except OSError:
        sock.close()
        print(f"\nPort {port} is already in use, probably by another copy of Photo Sorter.")
        print(f"Close the other one, or use a different port: photo-sorter serve --port {port + 1}")
        return 1
    # Bind first and read the port back: --port 0 lets the OS choose, and the app's Origin/Host allow-list must
    # be built from the port that is really bound.
    port = sock.getsockname()[1]
    config = uvicorn.Config(create_app(paths, port=port, runner=JobRunner(paths), dev=dev), host=LOOPBACK, port=port, log_level="warning")
    url = f"http://{LOOPBACK}:{port}/"
    print(f"Photo Sorter is running at {url}  (Ctrl+C to stop)")
    if open_browser:
        timer = threading.Timer(1.0, webbrowser.open, args=(url,))
        timer.daemon = True  # a crash or Ctrl+C in the first second must not leave a tab opening afterwards
        timer.start()
    try:
        uvicorn.Server(config).run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    return 0
