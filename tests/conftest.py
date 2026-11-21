"""Shared fixtures for the CLI and smoke tests: a throwaway app root and a fake camera roll."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from PIL import Image

CATEGORIES = [
    {"key": "photos", "kind": "photo", "label": "Photos", "emoji": "\U0001f4f7", "rule": "any photo"},
    {"key": "snaps", "kind": "photo", "label": "Snaps", "emoji": "\U0001f933", "rule": "anything else"},
    {"key": "clips", "kind": "video", "label": "Clips", "emoji": "\U0001f3ac", "rule": "any video"},
]


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """An app root of its own, so a test never writes into the repo."""
    root = tmp_path / "approot"
    root.mkdir()
    with open(root / "categories.json", "w", encoding="utf-8") as f:
        json.dump(CATEGORIES, f, ensure_ascii=False)
    return root


def camera_roll(folder: Path, n: int = 120) -> Path:
    """n small JPEGs of random noise, so every file gets its own perceptual hash."""
    folder.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(5)
    for i in range(n):
        im = Image.new("RGB", (32, 32))
        im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(32 * 32)])
        im.save(folder / f"IMG_{1000 + i}.jpg", quality=80)
    return folder


def snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    """Name, size and modified time of everything under `folder`: originals must be read-only."""
    return {
        str(p.relative_to(folder)): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }
