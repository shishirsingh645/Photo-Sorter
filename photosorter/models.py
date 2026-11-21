"""Plain records passed between scan, dedupe, labelling and copy.

Standalone on purpose: nothing here touches disk. Optional fields are left out
of to_dict when None so a 100k-file inventory stays small, and from_dict
accepts their absence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

#: Copied verbatim from the reference tool's scripts/common.py (IMG and VID).
IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp", ".tif", ".tiff"})
VIDEO_EXTS = frozenset({".mov", ".mp4", ".m4v", ".3gp", ".avi", ".mkv", ".webm"})

#: progress(done, total)
ProgressFn = Callable[[int, int], None]


@dataclass(slots=True)
class FileRecord:
    id: int
    path: Path
    name: str
    ext: str
    kind: Literal["photo", "video"]
    bytes: int
    sha256: str
    w: int = 0
    h: int = 0
    duration: float = 0.0
    phash: str | None = None
    taken: int | None = None
    geo: tuple[float, float] | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "path": str(self.path),
            "name": self.name,
            "ext": self.ext,
            "kind": self.kind,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "w": self.w,
            "h": self.h,
            "duration": self.duration,
        }
        if self.phash is not None:
            d["phash"] = self.phash
        if self.taken is not None:
            d["taken"] = self.taken
        if self.geo is not None:
            d["geo"] = list(self.geo)
        if self.error is not None:
            d["error"] = self.error
        return d

    @classmethod
    def from_dict(cls, d: dict) -> FileRecord:
        geo = d.get("geo")
        return cls(
            id=d["id"],
            path=Path(d["path"]),
            name=d["name"],
            ext=d["ext"],
            kind=d["kind"],
            bytes=d["bytes"],
            sha256=d["sha256"],
            w=d.get("w", 0),
            h=d.get("h", 0),
            duration=d.get("duration", 0.0),
            phash=d.get("phash"),
            taken=d.get("taken"),
            geo=None if geo is None else (geo[0], geo[1]),
            error=d.get("error"),
        )

    def slim(self) -> dict:
        """The dashboard's slim index record (spec 13.2): id, kind and size only."""
        return {"id": self.id, "kind": self.kind, "bytes": self.bytes}


@dataclass(slots=True)
class DupeGroup:
    keep: int
    dupes: list[int]
    type: Literal["exact", "near"]
    freed: int

    def to_dict(self) -> dict:
        return {"keep": self.keep, "dupes": list(self.dupes), "type": self.type, "freed": self.freed}

    @classmethod
    def from_dict(cls, d: dict) -> DupeGroup:
        return cls(keep=d["keep"], dupes=list(d["dupes"]), type=d["type"], freed=d["freed"])


@dataclass(slots=True)
class Category:
    key: str
    kind: Literal["photo", "video"]
    label: str
    emoji: str
    rule: str

    def to_dict(self) -> dict:
        return {"key": self.key, "kind": self.kind, "label": self.label, "emoji": self.emoji, "rule": self.rule}

    @classmethod
    def from_dict(cls, d: dict) -> Category:
        return cls(key=d["key"], kind=d["kind"], label=d["label"], emoji=d["emoji"], rule=d["rule"])
