from pathlib import Path

import pytest
from PIL import Image

from photosorter.config import Paths
from photosorter.core.sheets import build_sheets, ids_in_sheet_range, tag_text
from photosorter.models import FileRecord

CELL = 230
COLS, ROWS = 6, 5


@pytest.fixture
def paths(tmp_path):
    return Paths(root=tmp_path / "app")


def make_record(i, kind="photo", ext=".jpg", duration=0.0):
    return FileRecord(
        id=i,
        path=Path(f"/originals/{i}{ext}"),
        name=f"{i}{ext}",
        ext=ext,
        kind=kind,
        bytes=1,
        sha256="0" * 64,
        duration=duration,
    )


def records(n):
    return [make_record(i) for i in range(n)]


def write_thumbs(paths, recs):
    """Blue 256px JPEGs, so a yellow pixel can only come from a tag."""
    paths.thumbs.mkdir(parents=True, exist_ok=True)
    for r in recs:
        Image.new("RGB", (256, 256), (40, 60, 160)).save(paths.thumbs / f"{r.id}.jpg")


def yellow_pixels(img, box):
    data = img.crop(box).tobytes()
    return sum(1 for i in range(0, len(data), 3) if data[i] > 200 and data[i + 1] > 200 and data[i + 2] < 100)


def cell_box(slot):
    col, row = slot % COLS, slot // COLS
    return (col * CELL, row * CELL, (col + 1) * CELL, (row + 1) * CELL)


def test_thirty_previews_per_sheet_in_a_six_by_five_grid(paths):
    recs = records(65)
    write_thumbs(paths, recs)
    sheets = build_sheets(recs, paths)
    assert len(sheets) == 3
    assert all(s.parent == paths.sheets for s in sheets)
    assert Image.open(sheets[0]).size == (6 * 230, 5 * 230)


def test_video_tiles_are_tagged_with_video_and_seconds(paths):
    assert tag_text(make_record(7, kind="video", ext=".mp4", duration=12.4)) == "7 VIDEO 12s"
    recs = [make_record(0, kind="video", ext=".mp4", duration=12.4)]
    write_thumbs(paths, recs)
    sheet = Image.open(build_sheets(recs, paths)[0])
    assert yellow_pixels(sheet, cell_box(0)) > 0


def test_png_tiles_are_tagged_png(paths):
    assert tag_text(make_record(3, ext=".png")) == "3 PNG"
    assert tag_text(make_record(4, ext=".jpg")) == "4"
    recs = [make_record(0, ext=".png")]
    write_thumbs(paths, recs)
    sheet = Image.open(build_sheets(recs, paths)[0])
    assert yellow_pixels(sheet, cell_box(0)) > 0


def test_every_tile_carries_a_yellow_tag(paths):
    recs = records(30)
    write_thumbs(paths, recs)
    sheet = Image.open(build_sheets(recs, paths)[0])
    for slot in range(30):
        assert yellow_pixels(sheet, cell_box(slot)) > 0, f"slot {slot} has no tag"


def test_missing_thumbnail_leaves_tile_blank_but_still_tagged(paths):
    recs = records(3)
    write_thumbs(paths, [recs[0], recs[2]])
    sheets = build_sheets(recs, paths)
    assert len(sheets) == 1
    sheet = Image.open(sheets[0])
    assert sheet.size == (COLS * CELL, ROWS * CELL)
    assert yellow_pixels(sheet, cell_box(1)) > 0


def test_sample_mode_writes_at_most_three_sheets_deterministically(paths):
    recs = records(500)
    write_thumbs(paths, recs)
    first = build_sheets(recs, paths, sample=True)
    assert len(first) == 3
    assert all(s.parent == paths.work / "sample" for s in first)
    first_bytes = [s.read_bytes() for s in first]
    second = build_sheets(recs, paths, sample=True)
    assert second == first
    assert [s.read_bytes() for s in second] == first_bytes


def test_ids_in_sheet_range_covers_exactly_those_sheets():
    assert ids_in_sheet_range(records(100), 0, 2) == [str(i) for i in range(90)]
    assert ids_in_sheet_range(records(65), 2, 2) == [str(i) for i in range(60, 65)]
