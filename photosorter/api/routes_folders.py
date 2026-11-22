"""Folder routes: peek at a folder, pick one with the native dialog, reveal a file or sorted folder."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, model_validator

from photosorter.config import Paths, read_json
from photosorter.core.peek import peek_folder
from photosorter.picker import choose_folder, picker_available
from photosorter.platform import open_folder, reveal_in_file_manager

router = APIRouter()

# Plain `def` routes: FastAPI runs them in its thread pool, so a slow peek or a dialog never blocks the event loop.


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
