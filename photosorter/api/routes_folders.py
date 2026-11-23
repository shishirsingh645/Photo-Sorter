"""Folder routes: peek at a folder, pick one with the native dialog, reveal a file or sorted folder."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from photosorter.api.routes_files import _inventory
from photosorter.config import Paths, read_json, write_json
from photosorter.core.apply import folder_name
from photosorter.core.categories import (
    LabelCacheInUse,
    categories_fingerprint,
    clear_label_cache,
    load_categories,
    read_marker,
    save_categories,
    validate_categories,
)
from photosorter.core.peek import peek_folder
from photosorter.models import Category
from photosorter.picker import PickerFailed, choose_folder, picker_available
from photosorter.platform import open_folder, reveal_in_file_manager

router = APIRouter()

# Plain `def` routes: FastAPI runs them in its thread pool, so a slow peek or a dialog never blocks the event loop.


class CategoryIn(BaseModel):
    key: str = Field(min_length=1)
    kind: Literal["photo", "video"]
    label: str
    emoji: str
    rule: str


class PeekIn(BaseModel):
    source: str


class PickIn(BaseModel):
    prompt: str = "Choose a folder"


class OpenIn(BaseModel):
    id: int | None = None
    folder: str | None = None

    @model_validator(mode="after")
    def _one_target(self):
        if self.id is None and self.folder is None:
            raise ValueError("Say which file (id) or which sorted folder (folder) to open.")
        return self


@router.post("/api/peek")
def peek(body: PeekIn, request: Request) -> dict:
    paths: Paths = request.app.state.paths
    try:
        r = peek_folder(Path(body.source), paths)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "source": str(r.source),
        "photos": r.photos,
        "videos": r.videos,
        "bytes": r.bytes,
        "previews": r.previews,
        "suggested_dest": str(r.suggested_dest),
        "preview_bytes_needed": r.preview_bytes_needed,
        "free_bytes": r.free_bytes,
    }


_pick_lock = threading.Lock()


@router.post("/api/pick")
def pick(body: PickIn) -> dict:
    available, reason = picker_available()
    if not available:
        return {"path": None, "reason": reason}
    # Each open dialog holds a thread-pool worker for up to five minutes; a second one is never useful.
    if not _pick_lock.acquire(blocking=False):
        raise HTTPException(409, "A folder window is already open. Please use it, or close it first.")
    try:
        chosen = choose_folder(body.prompt)
    except PickerFailed:
        return {"path": None, "reason": "The folder window did not work."}
    finally:
        _pick_lock.release()
    return {"path": str(chosen) if chosen else None, "reason": ""}


def _sorted_folder(paths: Paths, requested: str) -> Path:
    """`requested` resolved against the stored sorted destination; anything outside it is refused."""
    source = read_json(paths.source_file, {})
    dest = source.get("sorted") if isinstance(source, dict) else None
    if not isinstance(dest, str) or not dest:
        # With no destination there is nothing to be inside of; allowing it would open any folder on request.
        raise HTTPException(400, "Nothing has been sorted yet, so there is no sorted folder to open.")
    root = Path(dest).resolve()
    target = (root / requested).resolve()  # an absolute `requested` replaces root, and is then refused below
    if not target.is_relative_to(root):
        raise HTTPException(400, "That folder is not inside the sorted folder, so it was not opened.")
    if not target.is_dir():
        raise HTTPException(400, "That folder does not exist inside the sorted folder.")
    return target


@router.post("/api/open")
def open_it(body: OpenIn, request: Request) -> dict:
    paths: Paths = request.app.state.paths
    if body.folder is not None:
        open_folder(_sorted_folder(paths, body.folder))
        return {"ok": True}
    inventory = read_json(paths.inventory_file, [])
    rec = next((r for r in inventory if isinstance(r, dict) and r.get("id") == body.id), None)
    if rec is None or not isinstance(rec.get("path"), str):
        raise HTTPException(404, "That file is not in the last scan.")
    reveal_in_file_manager(Path(rec["path"]))
    return {"ok": True}


def _check_label(cat: Category) -> None:
    """Refuse exactly what `folder_name` refuses, by asking it.

    One rule, living where the folder is actually built, so the route and the CLI cannot drift apart.
    `folder_name` turns every character Windows forbids into '-', so `Kids/Sports` still round-trips to
    `Kids-Sports` as it always has; a route stricter than that would stop the dashboard saving a list
    the CLI itself wrote.
    """
    try:
        folder_name(cat)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class CategoriesIn(BaseModel):
    categories: list[CategoryIn]


@router.post("/api/categories")
def set_categories(body: CategoriesIn, request: Request) -> dict:
    paths: Paths = request.app.state.paths
    cats = [Category(**c.model_dump()) for c in body.categories]
    for c in cats:
        _check_label(c)
    try:
        validate_categories(cats)  # before writing: a set with no video folder would fail quietly at apply
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    # Two labels that differ only by what folder_name strips (Food. and Food, or Kids/Sports and Kids-Sports)
    # would share one directory and silently mix two categories' photos. validate_categories checks keys, not
    # folder names, so this is the only place that can catch it. After it, so a duplicate key - the more
    # precise complaint about the same set - is the one the user is told about.
    folders: dict[str, str] = {}
    for c in cats:
        name = folder_name(c)
        if name in folders:
            raise HTTPException(
                400,
                f'"{c.label}" and "{folders[name]}" would both become the folder "{name}", so their photos '
                "would be mixed. Please give them names that differ by more than punctuation.",
            )
        folders[name] = c.label
    marker = paths.categories_fingerprint_file
    # A marker that does not match the OLD file (e.g. poisoned by a failed clear) means the cache is untrusted.
    stored = read_marker(paths)
    untrusted = stored is not None and paths.categories_file.exists() and stored != categories_fingerprint(paths)
    changed = [c.to_dict() for c in load_categories(paths)] != [c.to_dict() for c in cats]
    try:
        # Cleared on a real difference whether or not a marker exists (the route knows the list changed).
        # An identical re-save keeps the cache: a page may well POST the whole list on every dialog close.
        # Before save_categories, so a clear that fails leaves categories.json untouched and the 409's
        # "save again" is the truth - the other order reported a failure for a save that had persisted.
        if changed or untrusted:
            clear_label_cache(paths)
    except LabelCacheInUse as e:
        raise HTTPException(409, str(e)) from e  # the marker is poisoned, deliberately not restamped
    save_categories(paths, cats)
    paths.labels.mkdir(parents=True, exist_ok=True)
    marker.write_text(categories_fingerprint(paths), encoding="utf-8")
    return {"ok": True, "count": len(cats)}


class MoveIn(BaseModel):
    id: int
    key: str
    sha: str | None = None  # required, same contract and sentence as /api/file; "any" is the explicit escape


@router.post("/api/move")
def move(body: MoveIn, request: Request) -> dict:
    paths: Paths = request.app.state.paths
    if body.key not in {c.key for c in load_categories(paths)}:
        # merge_labels silently ignores an unknown override key, which would drop the hand move at apply time
        raise HTTPException(400, f'There is no folder called "{body.key}".')
    # Required, not optional. An override is PERSISTENT: a stale id here misfiles a photo into a folder the
    # user never chose, and unlike /api/file the mistake survives the reload that would have fixed it.
    if not body.sha:
        raise HTTPException(400, "Missing sha. Pass the record's sha256, or sha=any to skip the stale-id check.")
    by_id, _ = _inventory(request)  # cached on the app and rebuilt on a rescan, so this is O(1) per move
    rec = by_id.get(body.id)
    if rec is None:
        raise HTTPException(404, "That photo is not in the last scan. Reload the page and try again.")
    if body.sha != "any" and rec.get("sha256") != body.sha:
        raise HTTPException(409, "The folder was rescanned since this page loaded. Reload the page.")
    try:
        overrides = read_json(paths.overrides_file, {}, strict=True)
    except (ValueError, OSError) as e:  # never overwrite a damaged file: it may hold the user's earlier moves
        raise HTTPException(409, f"Your saved moves file is damaged, so this move was not saved: {e}") from e
    if not isinstance(overrides, dict):
        raise HTTPException(409, "Your saved moves file is damaged, so this move was not saved.")
    overrides[str(body.id)] = body.key
    write_json(paths.overrides_file, overrides)
    try:
        labels = read_json(paths.labels_file, {}, strict=True)
    except (ValueError, OSError):
        return {"ok": True}  # derived data: leave a damaged file alone; the move itself is already stored
    if isinstance(labels, dict):  # keep the merged labels in step so the page shows the move straight away
        labels[str(body.id)] = body.key
        write_json(paths.labels_file, labels)
    return {"ok": True}
