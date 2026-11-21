"""The whole pipeline over a synthetic camera roll, with the stub labeller: no Claude CLI, no network."""

from __future__ import annotations

import csv
from pathlib import Path

from photosorter.__main__ import main
from photosorter.core.apply import DUPES_CSV, SORTED_CSV
from tests.conftest import camera_roll, snapshot


def csv_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_full_pipeline_over_the_demo_library_with_a_stub_labeller(tmp_path, cli_root):
    source = camera_roll(tmp_path / "roll", 120)
    before = snapshot(source)
    dest = tmp_path / "out"

    assert main(["sort", str(source), "--dest", str(dest), "--labeler", "stub", "--root", str(cli_root)]) == 0

    assert (dest / SORTED_CSV).exists()
    assert (dest / DUPES_CSV).exists()
    rows = csv_rows(dest / SORTED_CSV)
    assert len(rows) == 120
    # Every listed copy really exists, in the folder the listing names.
    for row in rows:
        assert (dest / row["folder"] / row["file"]).is_file()
    # The stub puts photos in the first photo folder, so nothing should land in _Review/unsorted.
    assert {row["folder"] for row in rows} == {"Photos"}
    assert snapshot(source) == before, "the originals must not change"


def test_sorting_twice_leaves_the_same_sorted_folder(tmp_path, cli_root):
    source = camera_roll(tmp_path / "roll", 12)
    dest = tmp_path / "out"
    args = ["sort", str(source), "--dest", str(dest), "--labeler", "stub", "--root", str(cli_root)]
    assert main(args) == 0
    first = snapshot(dest)
    assert len(first) == 12 + 2, "12 copies plus both listings"
    assert main(args) == 0
    assert set(snapshot(dest)) == set(first), "a rebuild must not duplicate or orphan copies"


def test_sort_refuses_a_destination_inside_the_photos_folder(capsys, tmp_path, cli_root):
    source = camera_roll(tmp_path / "roll", 3)
    code = main(["sort", str(source), "--dest", str(source / "sorted"), "--labeler", "stub", "--root", str(cli_root)])
    assert code == 1
    assert "outside" in capsys.readouterr().out.lower()
    assert not (source / "sorted").exists()
