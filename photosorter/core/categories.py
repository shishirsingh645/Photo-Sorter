"""The folders the model sorts into, and the fingerprint that tells us they changed."""

from __future__ import annotations

import hashlib
import shutil

from photosorter.config import Paths, read_json, write_json
from photosorter.models import Category

#: Said after a scan of a different folder cleared the cache, and after a changed folder list did.
NEW_SOURCE_CLEARED = "A different set of photos is being looked at, so earlier labels were cleared."
FOLDERS_CHANGED_CLEARED = "The list of folders changed, so labels from the old list were cleared."


def load_categories(paths: Paths) -> list[Category]:
    return [Category.from_dict(d) for d in read_json(paths.categories_file, default=[])]


def require_categories(paths: Paths) -> list[Category]:
    """The folders to sort into, refusing an empty or self-contradicting list before any work starts."""
    cats = load_categories(paths)
    if not cats:
        raise ValueError(f"There are no folders to sort into. Add some to {paths.categories_file}.")
    validate_categories(cats)
    return cats


def save_categories(paths: Paths, cats: list[Category]) -> None:
    write_json(paths.categories_file, [c.to_dict() for c in cats])


def validate_categories(cats: list[Category]) -> None:
    seen: set[str] = set()
    for c in cats:
        if c.key in seen:
            raise ValueError(f'The folder name "{c.key}" is used twice. Each folder needs its own name.')
        seen.add(c.key)
    for kind in ("photo", "video"):
        if catch_all_for(cats, kind) is None:
            raise ValueError(f"There must be at least one {kind} folder, so every {kind} has somewhere to go.")


def categories_fingerprint(paths: Paths) -> str:
    """Changes whenever the folder list does, which is what invalidates cached labels."""
    return hashlib.sha1(paths.categories_file.read_bytes()).hexdigest()[:12]


def catch_all_for(cats: list[Category], kind: str) -> Category | None:
    """The last folder of a kind takes whatever fits nowhere else. None if the kind has no folders."""
    return next((c for c in reversed(cats) if c.kind == kind), None)


def read_marker(paths: Paths) -> str | None:
    """The stored fingerprint, None if there is no marker, or the poison value if it cannot be read
    (non-UTF-8, a directory in its place): an unreadable marker must read as 'does not match'."""
    marker = paths.categories_fingerprint_file
    if not marker.exists():
        return None
    try:
        return marker.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return POISON


class LabelCacheInUse(ValueError):
    """The cached labels could not all be deleted, probably because a running sort holds one open."""


#: Written over the marker when a clear fails. It matches no real fingerprint, so the next gate clears again.
POISON = "clear-failed"


def clear_label_cache(paths: Paths) -> bool:
    """Throw away every cached label batch, and the merged labels built from them. True if a cache existed.

    A batch is cached under its batch number and reused when nearly all the ids it was asked
    about are in it, while an id is only a file's position in the scanned list. So the batches
    of one library fit the next library's ids exactly, and would be handed back as its answers.
    Anything that changes what was scanned, or the folders to sort into, has to clear them.

    The fingerprint marker lives inside labels/, so a walk that fails part-way may already have
    deleted it, leaving survivors that the "no marker = older install" rule would adopt as valid.
    On failure the marker is overwritten with a value that matches nothing, and LabelCacheInUse is raised.
    """
    existed = paths.labels.exists()
    try:
        paths.labels_file.unlink(missing_ok=True)
        if existed:
            shutil.rmtree(paths.labels)
    except OSError as e:
        try:
            paths.labels.mkdir(parents=True, exist_ok=True)
            paths.categories_fingerprint_file.write_text(POISON, encoding="utf-8")
        except OSError:
            pass  # shortcut: if even the marker is unwritable nothing more can be done here; the error still raises
        raise LabelCacheInUse(
            "Some cached labels are in use, probably by a running sort. Stop it and save again."
        ) from e
    return existed


def drop_stale_labels(paths: Paths) -> bool:
    """Spec 7.2: a change to categories.json makes every cached label stale, so they go. Then stamp it.

    True when a changed list actually cleared a cache, so the caller can say so in its own words.
    No marker at all means a cache from before fingerprinting, not a changed list: it is kept and stamped.
    """
    fingerprint = categories_fingerprint(paths)
    stored = read_marker(paths)
    if stored == fingerprint:
        return False
    cleared = clear_label_cache(paths) if stored is not None else False
    paths.labels.mkdir(parents=True, exist_ok=True)
    paths.categories_fingerprint_file.write_text(fingerprint, encoding="utf-8")
    return cleared
