"""Labellers: things that decide which folder each file belongs in."""

import os
from pathlib import Path

from photosorter.config import Paths

_JEV_KEY_NAMES = ("JEV_KEY", "TYPESAFE_API_KEY")


def find_jev_key(paths: Paths) -> str | None:
    """The Jev API key: environment first, then a `.env` file in the app root. None when there is none."""
    for name in _JEV_KEY_NAMES:
        if os.environ.get(name):
            return os.environ[name]
    env_file: Path = paths.root / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() in _JEV_KEY_NAMES and value.strip().strip("\"'"):
                return value.strip().strip("\"'")
    return None
