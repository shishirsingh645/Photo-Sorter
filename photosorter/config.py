"""Where everything lives, and the only two functions that touch JSON on disk.

Every path in the app comes from `Paths`, and every text file is opened with an
explicit utf-8 encoding. Both rules exist because the original tool broke on
Windows without them: it joined paths as strings and let Python pick the locale
encoding, so emoji in categories.json raised UnicodeDecodeError under cp1252.

Your original photos are only ever read. Nothing here writes outside `root`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Repo root, i.e. the folder holding pyproject.toml.
_REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Paths:
    """Every location the app reads or writes, derived from one root."""

    root: Path

    @classmethod
    def default(cls) -> Paths:
        return cls(root=_REPO_ROOT)

    # --- directories -----------------------------------------------------
    @property
    def data(self) -> Path:
        """Inventory, previews and labels: what the dashboard reads."""
        return self.root / "data"

    @property
    def thumbs(self) -> Path:
        """256px previews, one per file."""
        return self.data / "thumbs"

    @property
    def mini(self) -> Path:
        """72px previews, small enough that hundreds can animate at once."""
        return self.data / "mini"

    @property
    def work(self) -> Path:
        """Scratch: contact sheets and raw label batches."""
        return self.root / "work"

    @property
    def labels(self) -> Path:
        """One JSON per finished label batch, which is what makes a run resumable."""
        return self.work / "labels"

    @property
    def sheets(self) -> Path:
        return self.work / "sheets"

    @property
    def peek(self) -> Path:
        """Tiny previews made right after a folder is chosen, before any scan."""
        return self.root / "peek"

    @property
    def demo(self) -> Path:
        return self.root / "demo"

    # --- files -----------------------------------------------------------
    @property
    def inventory_file(self) -> Path:
        return self.data / "inventory.json"

    @property
    def slim_file(self) -> Path:
        """id/kind/bytes only. The dashboard loads this instead of the full
        inventory, which is ~40MB at 100k files."""
        return self.data / "slim.json"

    @property
    def source_file(self) -> Path:
        return self.data / "source.json"

    @property
    def dupes_file(self) -> Path:
        return self.data / "dupes.json"

    @property
    def labels_file(self) -> Path:
        return self.data / "labels.json"

    @property
    def overrides_file(self) -> Path:
        """Files moved by hand in the dashboard. These beat the model's answer."""
        return self.work / "overrides.json"

    @property
    def jev_file(self) -> Path:
        return self.work / "jev.json"

    @property
    def categories_fingerprint_file(self) -> Path:
        return self.labels / ".categories"

    @property
    def categories_file(self) -> Path:
        return self.root / "categories.json"


def read_json(path: Path, default: Any = None, *, strict: bool = False) -> Any:
    """The parsed file, or `default` when it is missing or unreadable.

    A half-written or hand-damaged file counts as missing so one bad file cannot take the app down.
    `strict=True` raises instead, for the one caller where silently ignoring the file would lose work.
    """
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        if strict:
            raise
        return default


def write_json(path: Path, obj: Any) -> None:
    """Write to a temp file beside the target, then swap it in: a kill never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        # ensure_ascii=False keeps folder emoji readable in the file itself, not escaped.
        json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
