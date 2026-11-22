"""Contact sheets: grids of thumbnails, each tile tagged with its id, for the labeller to read.

The model answers with the ids printed on the tiles, so the tag has to stay legible.
"""

from __future__ import annotations

import random
import threading
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from photosorter.config import Paths
from photosorter.models import FileRecord

PER_SHEET = 30
COLS, ROWS = 6, 5
CELL = 230
THUMB = 222
INSET = (CELL - THUMB) // 2
SAMPLE_SIZE = 90
#: The reference tool's seed, so a --sample run picks the same records every time.
SAMPLE_SEED = 1
FONT_PX = 18
TAG_FILL = (255, 255, 0)
TAG_BG = (0, 0, 0)
_FONT_CANDIDATES = (
    Path("arial.ttf"),  # Windows
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),  # macOS
    Path("DejaVuSans.ttf"),  # most Linux distros
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


def tag_text(r: FileRecord) -> str:
    if r.kind == "video":
        return f"{r.id} VIDEO {r.duration:.0f}s"
    if r.ext.lower() == ".png":
        return f"{r.id} PNG"
    return str(r.id)


def tag_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, FONT_PX)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_tag(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font) -> None:
    """Yellow text on a black box, top-left corner at (x, y)."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.rectangle((x, y, x + (right - left) + 6, y + (bottom - top) + 6), fill=TAG_BG)
    draw.text((x + 3 - left, y + 3 - top), text, font=font, fill=TAG_FILL)


def _load_thumb(path: Path) -> Image.Image | None:
    try:
        with Image.open(path) as src:
            thumb = src.convert("RGB")
    except OSError:  # missing, empty or truncated: the tile stays blank, its tag is still drawn
        return None
    thumb.thumbnail((THUMB, THUMB), Image.Resampling.LANCZOS)
    return thumb


def render_sheet(recs: Sequence[FileRecord], thumbs: Path, font) -> Image.Image:
    sheet = Image.new("RGB", (COLS * CELL, ROWS * CELL), TAG_BG)
    draw = ImageDraw.Draw(sheet)
    for slot, r in enumerate(recs):
        x0 = (slot % COLS) * CELL + INSET
        y0 = (slot // COLS) * CELL + INSET
        thumb = _load_thumb(thumbs / f"{r.id}.jpg")
        if thumb is not None:
            sheet.paste(thumb, (x0 + (THUMB - thumb.width) // 2, y0 + (THUMB - thumb.height) // 2))
        draw_tag(draw, x0, y0, tag_text(r), font)
    return sheet


def build_sheets(
    records: Sequence[FileRecord], paths: Paths, sample: bool = False, cancel: threading.Event | None = None
) -> list[Path]:
    """`cancel` stops between sheets and returns the ones already written. 100k files is ~3,334 renders,
    and with no interruption point Stop would do nothing at all until the phase ended."""
    if sample:
        records = random.Random(SAMPLE_SEED).sample(records, min(SAMPLE_SIZE, len(records)))
        out = paths.work / "sample"
    else:
        out = paths.sheets
    out.mkdir(parents=True, exist_ok=True)
    # A smaller rerun must not leave old sheets behind: the labeller reads every sheet_*.jpg it finds.
    for old in out.glob("sheet_*.jpg"):
        old.unlink()
    font = tag_font()
    written = []
    for n, start in enumerate(range(0, len(records), PER_SHEET)):
        if cancel is not None and cancel.is_set():
            return written  # the partial set: a cancelled run's sheets are never labelled
        sheet = render_sheet(records[start : start + PER_SHEET], paths.thumbs, font)
        target = out / f"sheet_{n:05d}.jpg"
        sheet.save(target, quality=90)
        sheet.close()  # one sheet in memory at a time, however large the library
        written.append(target)
    return written


def ids_in_sheet_range(
    records: Sequence[FileRecord], first_sheet: int, last_sheet: int, per_sheet: int = PER_SHEET
) -> list[str]:
    """Ids on sheets first_sheet..last_sheet, inclusive, as build_sheets lays them out."""
    return [str(r.id) for r in records[first_sheet * per_sheet : (last_sheet + 1) * per_sheet]]
