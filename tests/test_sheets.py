from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from photosorter.config import Paths
from photosorter.core.sheets import (
    INSET,
    TAG_BG,
    build_sheets,
    draw_tag,
    ids_in_sheet_range,
    render_sheet,
    tag_font,
    tag_text,
)
from photosorter.models import FileRecord

CELL = 230
COLS, ROWS = 6, 5
BLUE = (40, 60, 160)


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
    """Ids start at 100 so a tile drawn with its slot index instead of its id is caught."""
    return [make_record(100 + i) for i in range(n)]


def write_thumbs(paths, recs):
    paths.thumbs.mkdir(parents=True, exist_ok=True)
    for r in recs:
        Image.new("RGB", (256, 256), BLUE).save(paths.thumbs / f"{r.id}.jpg")


def pixels(img, box):
    data = img.crop(box).tobytes()
    return list(zip(data[0::3], data[1::3], data[2::3], strict=True))


def yellow_mask(img, box):
    return [r > 200 and g > 200 and b < 100 for r, g, b in pixels(img, box)]


def blue_count(img, box):
    return sum(1 for r, g, b in pixels(img, box) if b > 100 and r < 120 and g < 140)


def cell_box(slot):
    col, row = slot % COLS, slot // COLS
    return (col * CELL, row * CELL, (col + 1) * CELL, (row + 1) * CELL)


def expected_tag_mask(text):
    """The yellow pixels a tag with this text draws, rendered with the same font and code as the sheet."""
    canvas = Image.new("RGB", (CELL, CELL), TAG_BG)
    draw_tag(ImageDraw.Draw(canvas), INSET, INSET, text, tag_font())
    mask = yellow_mask(canvas, (0, 0, CELL, CELL))
    assert any(mask), f"expected tag {text!r} draws no yellow"
    return mask


def assert_tagged(sheet, slot, rec):
    assert yellow_mask(sheet, cell_box(slot)) == expected_tag_mask(tag_text(rec)), (
        f"slot {slot} does not show the tag {tag_text(rec)!r}"
    )


def test_thirty_previews_per_sheet_in_a_six_by_five_grid(paths):
    recs = records(65)
    write_thumbs(paths, recs)
    sheets = build_sheets(recs, paths)
    assert len(sheets) == 3
    assert all(s.parent == paths.sheets for s in sheets)
    assert Image.open(sheets[0]).size == (6 * 230, 5 * 230)


def test_video_tiles_are_tagged_with_video_and_seconds(paths):
    assert tag_text(make_record(107, kind="video", ext=".mp4", duration=12.4)) == "107 VIDEO 12s"
    recs = [make_record(107, kind="video", ext=".mp4", duration=12.4)]
    write_thumbs(paths, recs)
    sheet = render_sheet(recs, paths.thumbs, tag_font())
    assert_tagged(sheet, 0, recs[0])


def test_png_tiles_are_tagged_png(paths):
    assert tag_text(make_record(103, ext=".png")) == "103 PNG"
    assert tag_text(make_record(104, ext=".jpg")) == "104"
    recs = [make_record(103, ext=".png"), make_record(104, ext=".jpg")]
    write_thumbs(paths, recs)
    sheet = render_sheet(recs, paths.thumbs, tag_font())
    assert_tagged(sheet, 0, recs[0])
    assert_tagged(sheet, 1, recs[1])


def test_every_tile_shows_its_own_id(paths):
    recs = records(30)
    write_thumbs(paths, recs)
    sheet = render_sheet(recs, paths.thumbs, tag_font())
    for slot, r in enumerate(recs):
        assert_tagged(sheet, slot, r)


def test_missing_thumbnail_leaves_tile_blank_but_still_tagged(paths):
    recs = records(3)
    write_thumbs(paths, [recs[0], recs[2]])
    sheet = render_sheet(recs, paths.thumbs, tag_font())
    assert blue_count(sheet, cell_box(0)) > 0  # control: a present thumbnail does paint
    assert blue_count(sheet, cell_box(1)) == 0
    assert_tagged(sheet, 1, recs[1])
    assert len(build_sheets(recs, paths)) == 1


def test_corrupt_thumbnail_does_not_abort_the_run(paths):
    recs = records(3)
    write_thumbs(paths, recs)
    truncated = paths.thumbs / f"{recs[1].id}.jpg"
    truncated.write_bytes(truncated.read_bytes()[:200])
    sheets = build_sheets(recs, paths)
    assert len(sheets) == 1
    sheet = Image.open(sheets[0])
    assert blue_count(sheet, cell_box(0)) > 0
    assert blue_count(sheet, cell_box(1)) == 0
    assert blue_count(sheet, cell_box(2)) > 0
    assert_tagged(render_sheet(recs, paths.thumbs, tag_font()), 1, recs[1])


@pytest.mark.parametrize("sample", [False, True])
def test_rerun_removes_stale_sheets(paths, sample):
    big, small = records(65), records(5)
    write_thumbs(paths, big)
    build_sheets(big, paths, sample=sample)
    build_sheets(small, paths, sample=sample)
    out = paths.work / "sample" if sample else paths.sheets
    assert sorted(p.name for p in out.glob("sheet_*.jpg")) == ["sheet_00000.jpg"]


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
    assert ids_in_sheet_range(records(100), 0, 2) == [str(i) for i in range(100, 190)]
    assert ids_in_sheet_range(records(65), 2, 2) == [str(i) for i in range(160, 165)]
