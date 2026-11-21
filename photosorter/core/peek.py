"""What runs the instant a folder is picked, before any scan: counts, size and a few tiny previews."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from photosorter.config import Paths
from photosorter.models import IMAGE_EXTS, VIDEO_EXTS
from photosorter.platform import free_space_bytes

#: Estimated disk space per file for the previews a scan writes. Scan imports this for its free-space check.
PREVIEW_BYTES_PER_FILE = 18_000
_PREVIEW_PX = 64
_SORTED_SUFFIX = " (sorted)"

register_heif_opener()  # iPhone photos are HEIC; a required dependency, so no fallback


@dataclass
class PeekResult:
    source: Path
    photos: int
    videos: int
    bytes: int
    previews: list[str]
    suggested_dest: Path
    preview_bytes_needed: int
    free_bytes: int


def peek_folder(source: Path, paths: Paths, preview_count: int = 60) -> PeekResult:
    """Count photos and videos in one pass. Only reads `source`; previews go to `paths.peek`."""
    if not source.is_dir():
        raise ValueError(f'"{source}" is not a folder we can open. Please choose a folder that exists.')
    rng = random.Random(3)  # the reference's seed, so previews are reproducible
    photos = videos = total = 0
    sample: list[Path] = []  # reservoir: never holds more than preview_count paths
    for root, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if not d.startswith(".") and not d.endswith(_SORTED_SUFFIX)]
        for name in files:
            ext = Path(name).suffix.lower()
            if ext in IMAGE_EXTS:
                photos += 1
                if len(sample) < preview_count:
                    sample.append(Path(root) / name)
                elif (j := rng.randint(0, photos - 1)) < preview_count:
                    sample[j] = Path(root) / name
            elif ext in VIDEO_EXTS:
                videos += 1
            else:
                continue
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass  # a file that vanished or is unreadable still counts, just with no size

    paths.peek.mkdir(parents=True, exist_ok=True)
    for old in paths.peek.glob("*.jpg"):
        old.unlink()
    previews: list[str] = []
    for src in sample:
        try:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((_PREVIEW_PX, _PREVIEW_PX))
                name = f"{len(previews):04d}.jpg"
                im.save(paths.peek / name, quality=70)
            previews.append(name)
        except Exception:  # noqa: BLE001 - one unreadable photo must not stop the peek
            continue

    return PeekResult(
        source=source,
        photos=photos,
        videos=videos,
        bytes=total,
        previews=previews,
        suggested_dest=source.parent / f"{source.name}{_SORTED_SUFFIX}",
        preview_bytes_needed=(photos + videos) * PREVIEW_BYTES_PER_FILE,
        free_bytes=free_space_bytes(paths.peek),
    )
