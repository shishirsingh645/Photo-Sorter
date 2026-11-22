"""Folder routes: peek at a folder, pick one with the native dialog, reveal a file or sorted folder."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from photosorter.config import Paths, read_json, write_json
from photosorter.core.categories import (
    categories_fingerprint,
    clear_label_cache,
    load_categories,
    save_categories,
    validate_categories,
)
from photosorter.core.peek import peek_folder
from photosorter.models import Category
from photosorter.picker import choose_folder, picker_available
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


@router.post("/api/pick")
def pick(body: PickIn) -> dict:
    available, reason = picker_available()
    if not available:
        return {"path": None, "reason": reason}
    chosen = choose_folder(body.prompt)
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


class CategoriesIn(BaseModel):
    categories: list[CategoryIn]


@router.post("/api/categories")
def set_categories(body: CategoriesIn, request: Request) -> dict:
    paths: Paths = request.app.state.paths
    cats = [Category(**c.model_dump()) for c in body.categories]
    try:
        validate_categories(cats)  # before writing: a set with no video folder would fail quietly at apply
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    save_categories(paths, cats)
    # Unconditional: this route is only called because the list changed, so a missing or equal fingerprint
    # must not be read as "nothing changed". (The CLI's keep-and-stamp rule is for caches from older installs.)
    clear_label_cache(paths)
    paths.labels.mkdir(parents=True, exist_ok=True)
    paths.categories_fingerprint_file.write_text(categories_fingerprint(paths), encoding="utf-8")
    return {"ok": True, "count": len(cats)}


class MoveIn(BaseModel):
    id: int
    key: str


@router.post("/api/move")
def move(body: MoveIn, request: Request) -> dict:
    paths: Paths = request.app.state.paths
    if body.key not in {c.key for c in load_categories(paths)}:
        # merge_labels silently ignores an unknown override key, which would drop the hand move at apply time
        raise HTTPException(400, f'There is no folder called "{body.key}".')
    # shortcut: ids are positions in the last scan, so a page left open across a rescan can name a different
    # photo and this cannot tell; upgrade by having the page send the file name and checking it here.
    slim = read_json(paths.slim_file, [])
    if not isinstance(slim, list) or not any(isinstance(r, dict) and r.get("id") == body.id for r in slim):
        raise HTTPException(404, "That photo is not in the last scan. Reload the page and try again.")
    try:
        overrides = read_json(paths.overrides_file, {}, strict=True)
    except (ValueError, OSError) as e:  # never overwrite a damaged file: it may hold the user's earlier moves
        raise HTTPException(409, f"Your saved moves file is damaged, so this move was not saved: {e}") from e
    if not isinstance(overrides, dict):
        raise HTTPException(409, "Your saved moves file is damaged, so this move was not saved.")
    overrides[str(body.id)] = body.key
    write_json(paths.overrides_file, overrides)
    labels = read_json(paths.labels_file, {})
    if isinstance(labels, dict):  # keep the merged labels in step so the page shows the move straight away
        labels[str(body.id)] = body.key
        write_json(paths.labels_file, labels)
    return {"ok": True}
