"""GET /api/file/{id} and /api/record/{id}: the user's original photo bytes, off their own disk.

Ids are positions in inventory.json, so they mean something different after a rescan. The inventory is
re-read whenever it or source.json changes on disk, and a page can pass `?sha=` (the sha256 it was shown)
to be refused with 409 instead of being handed a different photo.

The only request input is the id. The path comes from the inventory, and is still resolved and checked to
sit inside the scanned folder, so a damaged or hand-edited inventory cannot turn this into a file reader.
A hardlink inside the folder to a file outside it serves the outside bytes: resolve() cannot see hardlinks
and the file genuinely is inside the folder. Inherent, and the scanner would have indexed it anyway.

shortcut: a file swapped for a symlink between the containment check and the open is not defended; only the
user (or code running as them) can write there, and the loopback page this route guards against cannot.
Upgrade by validating an open handle instead of using FileResponse.
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from starlette.responses import FileResponse

from photosorter.config import read_json
from photosorter.platform import long_path

register_heif_opener()

router = APIRouter()

CONVERT_EXTS = frozenset({".heic", ".heif", ".tif", ".tiff", ".bmp"})  # browsers cannot show these
MAX_EDGE = 2400
JPEG_QUALITY = 88
# Pillow warns above this and raises DecompressionBombError above twice it (so ~100M px: a 100MP camera
# passes, the 108M-px bomb that decoded to ~324MB does not). The raise becomes the 415 below.
Image.MAX_IMAGE_PIXELS = 50_000_000


class QuietFileResponse(FileResponse):
    """Streams in 1 MiB chunks; a viewer closing the tab mid-stream is normal, not an error."""

    chunk_size = 1024 * 1024

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except (BrokenPipeError, ConnectionResetError):
            pass


# shortcut: the mtime/size key can collide on FAT32/exFAT (2s mtime quantum) when a reorder-only rescan keeps
# the byte count, serving a stale record; upgrade to hashing the file if the app root lives on such a drive.
def _stamp(p: Path) -> tuple[int, int] | None:
    try:
        st = p.stat()
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def _inventory(request: Request) -> tuple[dict[int, dict], str | None]:
    """(records by id, scanned folder). Cached on the app; rebuilt when either file changes (a rescan)."""
    paths = request.app.state.paths
    key = (_stamp(paths.inventory_file), _stamp(paths.source_file))
    cached = getattr(request.app.state, "files_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1], cached[2]
    recs = read_json(paths.inventory_file, [])
    source = read_json(paths.source_file, {})
    recs = recs if isinstance(recs, list) else []
    by_id = {r["id"]: r for r in recs if isinstance(r, dict) and isinstance(r.get("id"), int)}
    root = source.get("path") if isinstance(source, dict) else None
    root = root if isinstance(root, str) and root else None
    request.app.state.files_cache = (key, by_id, root)
    return by_id, root


def _record(request: Request, file_id: int, sha: str | None) -> tuple[dict, str]:
    # Required: ids are positions, and POST /api/move takes the same id, so a page that outlives a rescan
    # would show (and misfile) a different photo. `any` is the explicit escape for the CLI and dev.
    if not sha:
        raise HTTPException(400, "Missing sha. Pass the record's sha256, or sha=any to skip the stale-id check.")
    by_id, root = _inventory(request)
    rec = by_id.get(file_id)
    if rec is None or root is None:
        raise HTTPException(404, f"No file with id {file_id}. Rescan the folder if it has changed.")
    if sha != "any" and rec.get("sha256") != sha:
        raise HTTPException(409, "The folder was rescanned since this page loaded. Reload the page.")
    return rec, root


def _plain(p: Path) -> Path:
    """Drop a Windows extended-length prefix so a resolved file and its root compare like for like."""
    s = str(p)
    bs = chr(92)
    if s.startswith(bs * 2 + "?" + bs + "UNC" + bs):
        return Path(bs * 2 + s[8:])
    if s.startswith(bs * 2 + "?" + bs):
        return Path(s[4:])
    return p


def contained(raw: object, root: str) -> Path:
    """The real path of `raw`, which must be an absolute path inside `root` once symlinks, `..` and
    short names are resolved. Raises 403 otherwise. Comparison is by path parts, never string prefix."""
    refusal = HTTPException(403, "That file is outside the scanned folder, so it will not be served.")
    if not isinstance(raw, str) or not raw:
        raise refusal
    p = Path(raw)
    if not p.is_absolute():  # also catches the drive-relative "C:foo", which Windows reads against a cwd
        raise refusal
    try:
        real = _plain(long_path(p).resolve())
        base = _plain(long_path(Path(root)).resolve())
    except (OSError, RuntimeError, ValueError):
        raise refusal from None
    if not real.is_relative_to(base):
        raise refusal
    return real


def _convert(path: Path) -> bytes:
    with Image.open(long_path(path)) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((MAX_EDGE, MAX_EDGE))
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


@router.get("/api/record/{file_id}")
def get_record(request: Request, file_id: int, sha: str | None = None) -> dict:
    rec, root = _record(request, file_id, sha)
    contained(rec.get("path"), root)  # same refusal as /api/file, so the page is never handed an outside path
    return rec


# A plain `def`: FastAPI runs it in a worker thread, so decoding a big HEIC does not stall the event loop.
# shortcut: anyio's default limiter is 40 threads, so up to 40 conversions can be in flight at once, each
# bounded to ~100M px by MAX_IMAGE_PIXELS; add a semaphore if the browse grid ever pages that many HEICs.
@router.get("/api/file/{file_id}")
def get_file(request: Request, file_id: int, sha: str | None = None):
    rec, root = _record(request, file_id, sha)
    real = contained(rec.get("path"), root)
    target = long_path(real)
    if not target.is_file():
        raise HTTPException(404, "That file is no longer on disk. It may have moved since the scan.")
    ext = real.suffix.lower()
    try:
        if ext in CONVERT_EXTS:
            return Response(_convert(real), media_type="image/jpeg")
        return QuietFileResponse(target, media_type="video/mp4" if ext == ".mov" else None)
    except FileNotFoundError:
        raise HTTPException(404, "That file is no longer on disk. It may have moved since the scan.") from None
    except Exception as e:  # Pillow raises many types for a damaged image; the user needs one sentence
        raise HTTPException(415, f"Could not convert {real.name} for display ({type(e).__name__}).") from None
