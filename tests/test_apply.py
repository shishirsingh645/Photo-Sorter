import csv
import os
import subprocess
from pathlib import Path

import pytest

from photosorter.config import Paths, write_json
from photosorter.core.apply import (
    _remove_previous,
    apply_labels,
    check_destination,
    folder_name,
    merge_labels,
)
from photosorter.models import Category, DupeGroup, FileRecord

CATS = [
    Category("selfies", "photo", "Selfies", "", ""),
    Category("food", "photo", "Food & drinks", "", ""),
    Category("pets", "photo", "Pets", "", ""),
    Category("travel", "photo", "Trips/travel", "", ""),
    Category("screenshots", "photo", "Screenshots", "", ""),
    Category("vtalk", "video", "Talking", "", ""),
    Category("vother", "video", "Other videos", "", ""),
]


def rec(i, kind="photo", name=None, path=None, ext=".jpg"):
    name = name or f"f{i}{ext}"
    return FileRecord(id=i, path=path or Path(name), name=name, ext=ext, kind=kind, bytes=1, sha256=str(i))


def merge(claude, jev=None, overrides=None, kind="photo", cats=CATS):
    c = {"0": claude} if claude else {}
    j = {"0": {"key": jev[0], "confidence": jev[1]}} if jev else {}
    return merge_labels([rec(0, kind)], c, j, overrides or {}, cats)


def test_jev_wins_above_seventy_percent_confidence():
    assert merge("food", jev=("pets", 0.8)).labels["0"] == "pets"


def test_claude_wins_when_jev_is_unsure():
    assert merge("food", jev=("pets", 0.5)).labels["0"] == "food"


def test_jev_is_used_when_claude_has_no_answer():
    assert merge(None, jev=("pets", 0.1)).labels["0"] == "pets"


def test_overrides_beat_everything():
    assert merge("food", jev=("pets", 0.9), overrides={"0": "travel"}).labels["0"] == "travel"


def test_photo_labelled_with_a_video_folder_falls_to_the_photo_catch_all():
    r = merge("vtalk", kind="photo")
    assert r.labels["0"] == "screenshots" and r.fixed == 1


def test_unknown_folder_key_falls_to_the_catch_all():
    r = merge("nonsense")
    assert r.labels["0"] == "screenshots" and r.fixed == 1


def test_unlabelled_file_is_counted_as_missing_and_still_placed():
    r = merge(None)
    assert r.missing == 1 and r.labels["0"] == "screenshots"


def test_folder_name_replaces_ampersand_and_slash():
    assert folder_name(CATS[1]) == "Food and drinks"
    assert folder_name(CATS[3]) == "Trips-travel"


# --- filesystem ---------------------------------------------------------


@pytest.fixture
def world(tmp_path):
    paths = Paths(root=tmp_path / "app")
    write_json(paths.categories_file, [c.to_dict() for c in CATS])
    src = tmp_path / "src"
    (src / "a").mkdir(parents=True)
    (src / "b").mkdir()
    specs = [
        (0, src / "a" / "IMG_1.JPG", "selfies"),
        (1, src / "b" / "IMG_1.JPG", "selfies"),
        (2, src / "a" / "copy.jpg", "food"),
        (3, src / "a" / "orig.jpg", "food"),
        (4, src / "a" / "नमस्ते.jpg", "pets"),
    ]
    recs, labels = [], {}
    for i, p, key in specs:
        p.write_bytes(f"data{i}".encode())
        recs.append(rec(i, name=p.name, path=p, ext=p.suffix))
        labels[str(i)] = key
    return {
        "paths": paths,
        "src": src,
        "recs": recs,
        "labels": labels,
        "dupes": [DupeGroup(keep=3, dupes=[2], type="exact", freed=5)],
        "dest": tmp_path / "out",
    }


def snapshot(root: Path):
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def run(w, **kw):
    return apply_labels(w["recs"], w["dupes"], w["labels"], w["dest"], w["paths"], source=w["src"], **kw)


def test_library_with_no_videos_does_not_raise(world):
    photo_only = [c for c in CATS if c.kind == "photo"]
    write_json(world["paths"].categories_file, [c.to_dict() for c in photo_only])
    assert merge_labels(world["recs"], {}, {}, {}, photo_only).missing == 5
    assert merge_labels([], {}, {}, {}, photo_only).labels == {}
    assert run(world).copied == len(world["recs"])


def test_record_with_no_folder_for_its_kind_goes_to_review_unsorted(world):
    videos = [c for c in CATS if c.kind == "video"]
    write_json(world["paths"].categories_file, [c.to_dict() for c in videos])
    m = merge_labels(world["recs"], {}, {}, {}, videos)
    result = apply_labels(world["recs"], [], m.labels, world["dest"], world["paths"], source=world["src"])
    assert result.copied == 5
    assert (world["dest"] / "_Review" / "unsorted" / "IMG_1.JPG").exists()


def test_duplicates_go_to_review_duplicates(world):
    run(world)
    assert (world["dest"] / "_Review" / "duplicates" / "copy.jpg").exists()
    assert (world["dest"] / "Food and drinks" / "orig.jpg").exists()
    assert not (world["dest"] / "Food and drinks" / "copy.jpg").exists()


def test_name_collision_gets_the_id_suffix(world):
    run(world)
    assert (world["dest"] / "Selfies" / "IMG_1.JPG").exists()
    assert (world["dest"] / "Selfies" / "IMG_1__1.JPG").exists()


def test_non_ascii_names_are_copied_and_listed(world):
    run(world)
    assert (world["dest"] / "Pets" / "नमस्ते.jpg").exists()
    with open(world["dest"] / "sorted.csv", encoding="utf-8", newline="") as f:
        assert "नमस्ते.jpg" in [row["file"] for row in csv.DictReader(f)]


def test_originals_are_never_modified(world):
    before = snapshot(world["src"])
    run(world)
    run(world)
    assert snapshot(world["src"]) == before


def test_rerun_is_idempotent_and_removes_only_its_own_files(world):
    run(world)
    (world["dest"] / "my notes.txt").write_text("keep me", encoding="utf-8")
    (world["dest"] / "Selfies" / "mine.txt").write_text("also mine", encoding="utf-8")
    before = {k: v[0] for k, v in snapshot(world["dest"] / "Selfies").items()}
    result = run(world)
    assert {k: v[0] for k, v in snapshot(world["dest"] / "Selfies").items()} == before
    assert (world["dest"] / "my notes.txt").read_text(encoding="utf-8") == "keep me"
    assert (world["dest"] / "Selfies" / "mine.txt").exists()
    assert result.copied == 5


def test_rebuild_prunes_folders_that_become_empty(world):
    run(world)
    world["labels"]["4"] = "food"
    run(world)
    assert not (world["dest"] / "Pets").exists()
    assert (world["dest"] / "Food and drinks" / "नमस्ते.jpg").exists()


def test_rebuild_never_deletes_outside_dest_even_with_a_damaged_listing(world, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    run(world)
    with open(world["dest"] / "sorted.csv", "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["victim.txt", "..", "x"])
        w.writerow(["victim.txt", "../..", "x"])
    run(world)
    assert victim.read_text(encoding="utf-8") == "precious"


def test_destination_containing_originals_is_refused(world, tmp_path):
    with pytest.raises(ValueError, match="outside"):
        apply_labels(world["recs"], [], world["labels"], tmp_path, world["paths"], source=world["src"])
    assert all(r.path.exists() for r in world["recs"])


def test_destination_inside_source_is_refused_in_plain_words():
    with pytest.raises(ValueError, match="outside"):
        check_destination(Path("D:/pics"), Path("D:/pics/sorted"))


def test_destination_equal_to_or_above_source_is_refused(tmp_path):
    for dest in (tmp_path / "pics", tmp_path):
        with pytest.raises(ValueError, match="outside"):
            check_destination(tmp_path / "pics", dest)


def test_destination_on_another_drive_is_allowed():
    check_destination(Path("D:/pics"), Path("C:/sorted"))


def test_deeply_nested_long_names_copy(tmp_path):
    paths = Paths(root=tmp_path / "app")
    write_json(paths.categories_file, [c.to_dict() for c in CATS])
    src = tmp_path / "src"
    for _ in range(4):
        src = src / ("d" * 60)
    src.mkdir(parents=True)
    p = src / ("n" * 100 + ".jpg")
    p.write_bytes(b"x")
    dest = tmp_path / "out"
    for _ in range(4):
        dest = dest / ("o" * 60)
    assert len(str(dest / "Selfies" / p.name)) > 250
    r = rec(0, name=p.name, path=p)
    assert apply_labels([r], [], {"0": "selfies"}, dest, paths, source=tmp_path / "src").copied == 1


def test_sorted_and_duplicates_csv_have_the_specified_columns(world):
    run(world)

    def header(p):
        with open(p, encoding="utf-8", newline="") as f:
            return next(csv.reader(f))

    assert header(world["dest"] / "sorted.csv") == ["file", "folder", "original_path"]
    assert header(world["dest"] / "duplicates.csv") == [
        "duplicate", "kept_copy", "type", "duplicate_path", "kept_path",
    ]


def test_progress_ends_with_a_final_event(world):
    events = []
    run(world, on_progress=lambda d, t: events.append((d, t)))
    assert events[-1] == (5, 5)


def test_cancel_stops_copying_and_leaves_originals(world):
    result = run(world, cancel=lambda: True)
    assert result.copied == 0 and all(r.path.exists() for r in world["recs"])


def test_apply_refuses_a_destination_inside_the_source(world):
    with pytest.raises(ValueError, match="outside"):
        apply_labels(world["recs"], [], world["labels"], world["src"] / "sorted", world["paths"], source=world["src"])
    assert not (world["src"] / "sorted").exists()


def test_destination_beside_the_photos_but_inside_the_scanned_folder_is_refused(tmp_path):
    paths = Paths(root=tmp_path / "app")
    write_json(paths.categories_file, [c.to_dict() for c in CATS])
    scanned = tmp_path / "pics"
    (scanned / "Camera").mkdir(parents=True)
    p = scanned / "Camera" / "a.jpg"
    p.write_bytes(b"x")
    with pytest.raises(ValueError, match="outside"):
        apply_labels([rec(0, name=p.name, path=p)], [], {"0": "selfies"}, scanned / "sorted", paths, source=scanned)
    assert not (scanned / "sorted").exists()


def test_empty_library_still_checks_the_destination(tmp_path):
    paths = Paths(root=tmp_path / "app")
    write_json(paths.categories_file, [c.to_dict() for c in CATS])
    with pytest.raises(ValueError, match="outside"):
        apply_labels([], [], {}, tmp_path / "pics" / "sorted", paths, source=tmp_path / "pics")


def test_remove_previous_skips_a_protected_file_directly(tmp_path):
    dest = tmp_path / "out"
    (dest / "F").mkdir(parents=True)
    keep = dest / "F" / "x"
    keep.write_text("kept", encoding="utf-8")
    (dest / "sorted.csv").write_text("file,folder,original_path\nx,F,o\n", encoding="utf-8")
    _remove_previous(dest, {keep.resolve()})
    assert keep.read_text(encoding="utf-8") == "kept"


def test_second_order_name_collision_never_overwrites(world):
    selfies = world["dest"] / "Selfies"
    selfies.mkdir(parents=True)
    (selfies / "IMG_1__1.JPG").write_bytes(b"users own")  # where record 1 would first be renamed to
    other = world["src"] / "b" / "IMG_1__1.JPG"  # and a real file that is genuinely called that
    other.write_bytes(b"genuine")
    world["recs"].append(rec(5, name=other.name, path=other, ext=".JPG"))
    world["labels"]["5"] = "selfies"
    result = run(world)
    assert result.copied == 6
    assert (selfies / "IMG_1__1.JPG").read_bytes() == b"users own"
    assert sorted(p.read_bytes() for p in selfies.iterdir()) == sorted([b"users own", b"data0", b"data1", b"genuine"])
    with open(world["dest"] / "sorted.csv", encoding="utf-8", newline="") as f:
        listed = [(r["folder"], r["file"].lower()) for r in csv.DictReader(f)]
    assert len(listed) == len(set(listed)) == 6


def test_label_matching_no_folder_is_counted_not_silent(world, caplog):
    world["labels"]["4"] = "deleted-folder"
    with caplog.at_level("WARNING"):
        result = run(world)
    assert result.unsorted == 1 and "matched no folder" in caplog.text


def _damage_listing(world, *rows):
    run(world)
    with open(world["dest"] / "sorted.csv", "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def test_rebuild_ignores_an_absolute_path_row(world, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    _damage_listing(world, [str(victim), "", "x"], [victim.name, str(tmp_path), "x"])
    run(world)
    assert victim.read_text(encoding="utf-8") == "precious"


def _symlink(link, target, is_dir):
    try:
        link.symlink_to(target, target_is_directory=is_dir)
    except (OSError, NotImplementedError):
        pytest.skip("this system does not allow creating symbolic links without extra rights")


def _folder_link(link, target):
    if os.name == "nt":  # a junction needs no special rights, unlike a symbolic link
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if r.returncode != 0:
            pytest.skip("could not create a folder junction")
    else:
        _symlink(link, target, True)


def test_rebuild_does_not_follow_a_folder_link_out_of_the_destination(world, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    run(world)
    _folder_link(world["dest"] / "Linked", outside)
    _damage_listing(world, [victim.name, "Linked", "x"])
    run(world)
    assert victim.read_text(encoding="utf-8") == "precious"


def test_rebuild_does_not_delete_an_original_through_a_file_link(world):
    original = world["recs"][3].path
    run(world)
    _symlink(world["dest"] / "Pets" / "link.jpg", original, False)
    _damage_listing(world, ["link.jpg", "Pets", "x"])
    run(world)
    assert original.read_bytes() == b"data3"
