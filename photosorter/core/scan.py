"""Scanning: turn a folder of photos and videos into FileRecords plus previews.

Originals are only ever read. Every per-file failure is stored on the record
and the scan carries on; one bad file must never abort a 100,000 file run.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import imagehash
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from photosorter import platform as plat
from photosorter.config import Paths, write_json
from photosorter.core.peek import PREVIEW_BYTES_PER_FILE
from photosorter.models import IMAGE_EXTS, VIDEO_EXTS, FileRecord, ProgressFn

register_heif_opener()  # HEIC is required, never optional: it must preview or show an error

_THUMB_PX, _MINI_PX = 256, 72
_SORTED_SUFFIX = " (sorted)"
_SUPPLEMENTAL = "supplemental-metadata"
_NUMBERED = re.compile(r"^(.*)\((\d+)\)(\.[^.]*)$")
_BAD_FILE = "This file could not be opened. It may be damaged or in a format we do not support."
_BEIGE, _GREY = (222, 205, 175), (160, 160, 160)


def find_files(source: Path, limit: int = 0) -> list[Path]:
    """Photos and videos under `source`, sorted. `limit` takes a reproducible random sample."""
    found: list[Path] = []
    for root, dirs, names in os.walk(source):
        dirs[:] = [d for d in dirs if not d.startswith(".") and not d.endswith(_SORTED_SUFFIX)]
        for n in names:
            if not n.startswith("._") and Path(n).suffix.lower() in IMAGE_EXTS | VIDEO_EXTS:
                found.append(Path(root) / n)
    found.sort()
    if limit and limit < len(found):
        found = sorted(random.Random(0).sample(found, limit))
    return found


def find_sidecar(path: Path) -> Path | None:
    """Google Takeout metadata: NAME.json, or NAME.supplemental-metadata.json (often truncated).

    A numbered copy IMG_1(1).JPG pairs only with a sidecar carrying the same (1).
    """
    tries = [(path.name, "")]
    m = _NUMBERED.match(path.name)
    if m:
        tries.insert(0, (m.group(1) + m.group(3), f"({m.group(2)})"))
    for base, num in tries:
        for cut in range(len(_SUPPLEMENTAL), -1, -1):
            mid = "." + _SUPPLEMENTAL[:cut] if cut else ""
            cand = path.with_name(f"{base}{mid}{num}.json")
            if cand.is_file():
                return cand
    return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(plat.long_path(path), "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _save_previews(im: Image.Image, paths: Paths, rec_id: int) -> Image.Image:
    thumb = ImageOps.fit(im.convert("RGB"), (_THUMB_PX, _THUMB_PX))
    thumb.save(paths.thumbs / f"{rec_id}.jpg", quality=80)
    thumb.resize((_MINI_PX, _MINI_PX)).save(paths.mini / f"{rec_id}.jpg", quality=72)
    return thumb


def _placeholder(paths: Paths, rec_id: int, colour: tuple[int, int, int]) -> None:
    _save_previews(Image.new("RGB", (_THUMB_PX, _THUMB_PX), colour), paths, rec_id)


def _probe_video(path: Path, paths: Paths, rec: FileRecord) -> Image.Image | None:
    """Fill dimensions, duration and a preview from ffmpeg. Returns the preview, or None for a grey placeholder."""
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not (ffprobe and ffmpeg):
        _placeholder(paths, rec.id, _GREY)
        return None
    out = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, check=True, timeout=60,
    ).stdout
    info = json.loads(out)
    stream = next(s for s in info["streams"] if s.get("codec_type") == "video")
    rec.w, rec.h = int(stream["width"]), int(stream["height"])
    rec.duration = float(info.get("format", {}).get("duration") or stream.get("duration") or 0)
    rotate = int(stream.get("tags", {}).get("rotate", 0) or 0)
    for side in stream.get("side_data_list", []):
        rotate = int(side.get("rotation", rotate))
    if abs(rotate) % 180 == 90:
        rec.w, rec.h = rec.h, rec.w
    at = "1" if rec.duration >= 2 else "0"
    frame = subprocess.run(
        [ffmpeg, "-v", "error", "-ss", at, "-i", str(path), "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-"],
        capture_output=True, check=True, timeout=60,
    ).stdout
    with Image.open(io.BytesIO(frame)) as im:  # ffmpeg autorotates, so no manual turn is needed
        return _save_previews(im, paths, rec.id)


def _read_sidecar(path: Path, rec: FileRecord) -> None:
    """Takeout taken-time and GPS; a missing or malformed sidecar is simply ignored."""
    try:
        side = find_sidecar(path)
        if side is None:
            return
        with open(plat.long_path(side), encoding="utf-8") as f:
            data = json.load(f)
        rec.taken = int(data["photoTakenTime"]["timestamp"])
        geo = data.get("geoData") or {}
        lat, lon = float(geo["latitude"]), float(geo["longitude"])
        if lat or lon:  # Takeout writes 0,0 for "no location"
            rec.geo = (lat, lon)
    except Exception:  # noqa: BLE001
        pass


def _process(rec_id: int, path: Path, paths: Paths, cancel: threading.Event | None) -> FileRecord | None:
    if cancel is not None and cancel.is_set():
        return None
    ext = path.suffix.lower()
    # sha256 stays "" (unknown, which dedupe handles) unless we really hashed the file.
    rec = FileRecord(id=rec_id, path=path, name=path.name, ext=ext,
                     kind="video" if ext in VIDEO_EXTS else "photo", bytes=0, sha256="")
    try:
        rec.bytes = plat.long_path(path).stat().st_size
        rec.sha256 = _sha256(path)
        if rec.kind == "video":
            thumb = _probe_video(plat.long_path(path), paths, rec)
            if thumb is not None:  # a placeholder would hash identically for every video
                rec.phash = str(imagehash.phash(thumb))
        else:
            with Image.open(plat.long_path(path)) as im:
                im = ImageOps.exif_transpose(im)
                rec.w, rec.h = im.size
                thumb = _save_previews(im, paths, rec_id)
            rec.phash = str(imagehash.phash(thumb))  # default hash_size=8: exactly 16 hex chars
    except Exception:  # noqa: BLE001 - recorded on the record, never re-raised
        rec.error = _BAD_FILE
        rec.phash = None
        try:
            _placeholder(paths, rec_id, _BEIGE)
        except Exception:  # noqa: BLE001 - even a failed placeholder (disk full) must not abort the scan
            pass
    else:
        _read_sidecar(path, rec)
    return rec


def scan_folder(
    source: Path,
    paths: Paths,
    limit: int = 0,
    on_progress: ProgressFn | None = None,
    cancel: threading.Event | None = None,
) -> list[FileRecord]:
    """Scan `source` and write inventory, slim index and source.json (not on cancel, which returns the partial list)."""
    files = find_files(source, limit)
    paths.data.mkdir(parents=True, exist_ok=True)
    needed = len(files) * PREVIEW_BYTES_PER_FILE
    free = plat.free_space_bytes(paths.data)
    if free < needed:
        raise ValueError(
            f"There is not enough free space for the previews: about {needed // 1_000_000} MB is needed "
            f"but only {free // 1_000_000} MB is free. Please free up some space and try again."
        )
    for d in (paths.thumbs, paths.mini):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)

    total, done, last_t, last_n = len(files), 0, 0.0, 0
    records: list[FileRecord] = []
    with ThreadPoolExecutor(8) as pool:
        futures = [pool.submit(_process, i, p, paths, cancel) for i, p in enumerate(files)]
        for fut in as_completed(futures):
            rec = fut.result()
            if rec is not None:
                records.append(rec)
            done += 1
            now = time.monotonic()
            if on_progress and (done == total or (now - last_t >= 0.1 and done - last_n >= total * 0.005)):
                on_progress(done, total)
                last_t, last_n = now, done
    if not files and on_progress:
        on_progress(0, 0)
    records.sort(key=lambda r: r.id)
    if cancel is not None and cancel.is_set():
        # the previews were wiped, so an older inventory would point at files that no longer exist
        for stale in (paths.inventory_file, paths.slim_file, paths.source_file):
            stale.unlink(missing_ok=True)
        return records
    write_json(paths.inventory_file, [r.to_dict() for r in records])
    write_json(paths.slim_file, [r.slim() for r in records])
    write_json(paths.source_file, {"path": str(source), "count": len(records)})
    return records
