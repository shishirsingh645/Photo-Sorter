"""The folders the model sorts into, and the fingerprint that tells us they changed."""

from __future__ import annotations

import hashlib
import shutil

from photosorter.config import Paths, read_json, write_json
from photosorter.models import Category


def load_categories(paths: Paths) -> list[Category]:
    return [Category.from_dict(d) for d in read_json(paths.categories_file, default=[])]


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


def clear_label_cache(paths: Paths) -> bool:
    """Throw away every cached label batch, and the merged labels built from them. True if a cache existed.

    A batch is cached under its batch number and reused when nearly all the ids it was asked
    about are in it, while an id is only a file's position in the scanned list. So the batches
    of one library fit the next library's ids exactly, and would be handed back as its answers.
    Anything that changes what was scanned, or the folders to sort into, has to clear them.
    """
    existed = paths.labels.exists()
    if existed:
        shutil.rmtree(paths.labels)
    paths.labels_file.unlink(missing_ok=True)
    return existed
