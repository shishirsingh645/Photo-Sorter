"""Build the sorted folders by copying. Originals are only ever read.

Nothing here moves, renames, writes to or deletes anything under the source
folder. A rebuild deletes only the files its own previous sorted.csv lists.
"""

from __future__ import annotations

import csv
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from photosorter.config import Paths
from photosorter.core.categories import catch_all_for, load_categories
from photosorter.models import Category, DupeGroup, FileRecord, ProgressFn
from photosorter.platform import copy_file, long_path

JEV_MIN_CONFIDENCE = 0.7
REVIEW_DIR = "_Review"
DUPES_DIR = "duplicates"
UNSORTED_DIR = "unsorted"
SORTED_CSV = "sorted.csv"
DUPES_CSV = "duplicates.csv"

_OUTSIDE = (
    "The sorted folder must be outside your photos folder, so your originals are never touched. "
    "Please choose a different folder."
)
log = logging.getLogger(__name__)


@dataclass
class MergeResult:
    labels: dict[str, str] = field(default_factory=dict)
    missing: int = 0
    fixed: int = 0


@dataclass
class ApplyResult:
    counts: dict[str, int]
    copied: int
    dest: Path
    unsorted: int = 0  # files whose label matched no folder


def folder_name(cat: Category) -> str:
    return cat.label.replace("&", "and").replace("/", "-")


def check_destination(source: Path, dest: Path) -> None:
    src, dst = source.resolve(), dest.resolve()
    if dst == src or src in dst.parents or dst in src.parents:
        raise ValueError(_OUTSIDE)


def merge_labels(
    records: Sequence[FileRecord],
    claude: dict[str, str],
    jev: dict[str, dict],
    overrides: dict[str, str],
    cats: list[Category],
) -> MergeResult:
    """Claude, then Jev at >= 0.7 or where Claude is silent, then the kind guard, then overrides."""
    by_key = {c.key: c for c in cats}
    out = MergeResult()
    for r in records:
        rid = str(r.id)
        key = claude.get(rid)
        j = jev.get(rid)
        if j and (key is None or j.get("confidence", 0) >= JEV_MIN_CONFIDENCE):
            key = j["key"]
        if key is None:
            out.missing += 1
        if key not in by_key or by_key[key].kind != r.kind:
            fallback = catch_all_for(cats, r.kind)
            key = fallback.key if fallback else ""  # "" is placed in _Review/unsorted by apply_labels
            if rid in claude or rid in jev:
                out.fixed += 1
        if overrides.get(rid) in by_key:
            key = overrides[rid]
        out.labels[rid] = key
    return out


class _Throttle:
    """At most 10 events a second and one per 0.5% of total, plus a guaranteed final event."""

    def __init__(self, fn: ProgressFn | None, total: int):
        self.fn, self.total = fn, total
        self.step = max(1, total // 200)
        self.last_done, self.last_t = 0, 0.0

    def tick(self, done: int) -> None:
        now = time.monotonic()
        if self.fn and done - self.last_done >= self.step and now - self.last_t >= 0.1:
            self.last_done, self.last_t = done, now
            self.fn(done, self.total)

    def finish(self, done: int) -> None:
        if self.fn:
            self.fn(done, self.total)


def _remove_previous(dest: Path, protected: set[Path]) -> None:
    """Delete exactly the files the previous sorted.csv lists, then prune folders left empty."""
    listing = dest / SORTED_CSV
    if not listing.exists():
        return
    root = dest.resolve()
    folders: set[Path] = set()
    with open(listing, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rel = Path(row["folder"]) / row["file"]
            target = (dest / rel).resolve()
            # A damaged listing must never reach outside the sorted folder or onto an original.
            if rel.is_absolute() or ".." in rel.parts or root not in target.parents or target in protected:
                continue
            try:
                long_path(dest / rel).unlink()
            except FileNotFoundError:
                pass
            folders.add(dest / rel.parent)
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        d = folder
        while d != dest and dest in d.parents:
            try:
                long_path(d).rmdir()  # only succeeds when empty
            except OSError:
                break
            d = d.parent


def apply_labels(
    records: Sequence[FileRecord],
    dupes: list[DupeGroup],
    labels: dict[str, str],
    dest: Path,
    paths: Paths,
    on_progress: ProgressFn | None = None,
    cancel: Callable[[], bool] | None = None,
    *,
    source: Path,
) -> ApplyResult:
    """`source` is the folder the user scanned: the destination must be outside it, even with no records."""
    check_destination(source, dest)
    originals = {r.path.resolve() for r in records}
    root = dest.resolve()
    for p in originals:
        if root == p or root in p.parents:
            raise ValueError(_OUTSIDE)
    names = {c.key: folder_name(c) for c in load_categories(paths)}
    by_id = {r.id: r for r in records}
    dupe_of: dict[int, DupeGroup] = {i: g for g in dupes for i in g.dupes if i in by_id and g.keep in by_id}

    dest.mkdir(parents=True, exist_ok=True)
    _remove_previous(dest, originals)

    used: set[tuple[str, str]] = set()
    counts: dict[str, int] = {}
    copied = unsorted = 0
    progress = _Throttle(on_progress, len(records))
    review = f"{REVIEW_DIR}/{DUPES_DIR}"
    with (
        open(dest / SORTED_CSV, "w", encoding="utf-8", newline="") as sf,
        open(dest / DUPES_CSV, "w", encoding="utf-8", newline="") as df,
    ):
        sw, dw = csv.writer(sf), csv.writer(df)
        sw.writerow(["file", "folder", "original_path"])
        dw.writerow(["duplicate", "kept_copy", "type", "duplicate_path", "kept_path"])
        for n, r in enumerate(records, 1):
            if cancel and cancel():
                break
            group = dupe_of.get(r.id)
            if group:
                folder = review
            else:
                folder = names.get(labels.get(str(r.id), ""))
                if folder is None:
                    folder = f"{REVIEW_DIR}/{UNSORTED_DIR}"
                    unsorted += 1
            name, stem = r.name, Path(r.name).stem
            while (folder, name.lower()) in used or long_path(dest / folder / name).exists():
                name = f"{stem}__{r.id}{Path(r.name).suffix}"
                stem += "_"  # still taken (a user's file, or a file really named that): try again
            used.add((folder, name.lower()))
            sw.writerow([name, folder, str(r.path)])  # listed before copying so a crash cannot orphan a copy
            sf.flush()
            long_path(dest / folder).mkdir(parents=True, exist_ok=True)
            copy_file(long_path(r.path), long_path(dest / folder / name))
            copied += 1
            counts[folder] = counts.get(folder, 0) + 1
            if group:
                kept = by_id[group.keep]
                dw.writerow([name, kept.name, group.type, str(r.path), str(kept.path)])
            progress.tick(n)
    progress.finish(copied)
    if unsorted:
        log.warning("%d files matched no folder and were put in %s/%s", unsorted, REVIEW_DIR, UNSORTED_DIR)
    return ApplyResult(counts=counts, copied=copied, dest=dest, unsorted=unsorted)
