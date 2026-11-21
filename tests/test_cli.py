"""The command line: one subcommand per stage, plain words on the way out, and an exit code."""

from __future__ import annotations

import json
from pathlib import Path

from photosorter.__main__ import main
from photosorter.config import Paths, read_json
from tests.conftest import camera_roll


def _sort_args(source: Path, dest: Path, root: Path, *extra: str) -> list[str]:
    return ["sort", str(source), "--dest", str(dest), "--labeler", "stub", "--root", str(root), *extra]


def test_scan_subcommand_reports_counts(capsys, tmp_path, cli_root):
    source = camera_roll(tmp_path / "roll", 3)
    assert main(["scan", str(source), "--root", str(cli_root)]) == 0
    out = capsys.readouterr().out
    assert "files" in out
    assert "3" in out


def test_scan_of_an_empty_folder_says_so_and_succeeds(capsys, tmp_path, cli_root):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["scan", str(empty), "--root", str(cli_root)]) == 0
    assert "0 files" in capsys.readouterr().out


def test_apply_without_labels_explains_what_to_do_first(capsys, tmp_path, cli_root):
    camera_roll(tmp_path / "roll", 2)
    assert main(["scan", str(tmp_path / "roll"), "--root", str(cli_root)]) == 0
    capsys.readouterr()
    assert main(["apply", str(tmp_path / "out"), "--root", str(cli_root)]) == 1
    assert "label" in capsys.readouterr().out.lower()


def test_apply_before_any_scan_explains_what_to_do_first(capsys, tmp_path, cli_root):
    assert main(["apply", str(tmp_path / "out"), "--root", str(cli_root)]) == 1
    assert "scan" in capsys.readouterr().out.lower()


def test_apply_refuses_a_destination_inside_the_folder_that_was_scanned(capsys, tmp_path, cli_root):
    """C3: apply passes the scanned root, not the folder a file happens to sit in."""
    source = tmp_path / "pics"
    camera_roll(source / "Camera", 2)
    assert main(["scan", str(source), "--root", str(cli_root)]) == 0
    assert main(["label", "--labeler", "stub", "--root", str(cli_root)]) == 0
    capsys.readouterr()
    # Inside "pics/Camera", which is where the files are: narrower than the folder the user scanned.
    assert main(["apply", str(source / "Camera" / "out"), "--root", str(cli_root)]) == 1
    assert "outside" in capsys.readouterr().out.lower()


def test_dupes_explains_a_hash_of_the_wrong_length_instead_of_crashing(capsys, tmp_path, cli_root):
    """C4: band_keys refuses a short hash; the user must see words, not a traceback."""
    paths = Paths(root=cli_root)
    paths.data.mkdir(parents=True)
    record = {
        "id": 0, "path": str(tmp_path / "a.jpg"), "name": "a.jpg", "ext": ".jpg",
        "kind": "photo", "bytes": 10, "sha256": "aa", "phash": "abc",
    }
    with open(paths.inventory_file, "w", encoding="utf-8") as f:
        json.dump([record], f)
    assert main(["dupes", "--root", str(cli_root)]) == 1
    out = capsys.readouterr().out
    assert "hex" in out.lower()
    assert "Traceback" not in out


def test_dupes_reports_the_groups_it_found(capsys, tmp_path, cli_root):
    source = camera_roll(tmp_path / "roll", 3)
    main(["scan", str(source), "--root", str(cli_root)])
    capsys.readouterr()
    assert main(["dupes", "--root", str(cli_root)]) == 0
    assert "duplicate" in capsys.readouterr().out.lower()


def test_sheets_reports_how_many_it_built(capsys, tmp_path, cli_root):
    source = camera_roll(tmp_path / "roll", 3)
    main(["scan", str(source), "--root", str(cli_root)])
    capsys.readouterr()
    assert main(["sheets", "--root", str(cli_root)]) == 0
    assert "1" in capsys.readouterr().out
    assert (Paths(root=cli_root).sheets / "sheet_00000.jpg").exists()


def test_stub_labeller_gives_every_file_the_first_folder_of_its_kind(tmp_path, cli_root):
    source = camera_roll(tmp_path / "roll", 3)
    main(["scan", str(source), "--root", str(cli_root)])
    assert main(["label", "--labeler", "stub", "--root", str(cli_root)]) == 0
    labels = read_json(Paths(root=cli_root).labels_file)
    assert set(labels.values()) == {"photos"}
    assert len(labels) == 3


def test_demo_builds_a_library_inside_the_root(capsys, cli_root):
    assert main(["demo", "--root", str(cli_root)]) == 0
    assert "files" in capsys.readouterr().out
    assert (cli_root / "demo" / "inventory.json").exists()


def test_sort_skips_rescan_when_source_and_limit_unchanged(tmp_path, cli_root, monkeypatch):
    import photosorter.__main__ as cli

    source = camera_roll(tmp_path / "roll", 4)
    calls: list[int] = []
    real = cli.scan_folder

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(cli, "scan_folder", counting)
    dest = tmp_path / "out"
    assert cli.main(_sort_args(source, dest, cli_root)) == 0
    assert cli.main(_sort_args(source, dest, cli_root)) == 0
    assert len(calls) == 1, "the second sort should have reused the inventory"
    # A different limit is a different inventory, so it must scan again.
    assert cli.main(_sort_args(source, dest, cli_root, "--limit", "2")) == 0
    assert len(calls) == 2


def test_changing_categories_invalidates_cached_labels(tmp_path, cli_root):
    """C5: the fingerprint at Paths.categories_fingerprint_file guards the label cache (spec 7.2)."""
    paths = Paths(root=cli_root)
    source = camera_roll(tmp_path / "roll", 3)
    assert main(_sort_args(source, tmp_path / "out", cli_root)) == 0
    first = paths.categories_fingerprint_file.read_text(encoding="utf-8").strip()
    stale = paths.labels / "claude_00.json"
    stale.write_text('{"0": "photos"}', encoding="utf-8")

    cats = json.loads(paths.categories_file.read_text(encoding="utf-8"))
    cats.append({"key": "extra", "kind": "photo", "label": "Extra", "emoji": "✨", "rule": "new folder"})
    with open(paths.categories_file, "w", encoding="utf-8") as f:
        json.dump(cats, f, ensure_ascii=False)

    assert main(_sort_args(source, tmp_path / "out", cli_root)) == 0
    assert not stale.exists(), "a changed folder list must clear the cached label batches"
    assert paths.categories_fingerprint_file.read_text(encoding="utf-8").strip() != first


def test_categories_that_are_unchanged_keep_the_cached_labels(tmp_path, cli_root):
    paths = Paths(root=cli_root)
    source = camera_roll(tmp_path / "roll", 3)
    assert main(_sort_args(source, tmp_path / "out", cli_root)) == 0
    kept = paths.labels / "claude_00.json"
    kept.write_text('{"0": "photos"}', encoding="utf-8")
    assert main(_sort_args(source, tmp_path / "out", cli_root)) == 0
    assert kept.exists()


def test_an_unusable_folder_is_reported_in_plain_words(capsys, tmp_path, cli_root):
    assert main(["scan", str(tmp_path / "nope"), "--root", str(cli_root)]) == 1
    out = capsys.readouterr().out
    assert "folder" in out.lower()
    assert "Traceback" not in out
