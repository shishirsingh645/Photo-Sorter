import json
from pathlib import Path

from PIL import Image

from photosorter.config import write_json
from photosorter.core.apply import folder_name
from photosorter.core.peek import PREVIEW_BYTES_PER_FILE
from photosorter.models import Category

R = "photosorter.api.routes_folders."


def _photos(folder: Path, n: int = 3) -> Path:
    folder.mkdir()
    for i in range(n):
        Image.new("RGB", (80, 60), (i * 40, 10, 10)).save(folder / f"p{i}.jpg")
    (folder / "clip.mp4").write_bytes(b"x" * 10)
    return folder


def test_peek_counts_the_folder_and_suggests_a_destination(client, tmp_path):
    src = _photos(tmp_path / "Trip")
    r = client.post("/api/peek", json={"source": str(src)})
    assert r.status_code == 200
    body = r.json()
    assert (body["photos"], body["videos"]) == (3, 1)
    assert body["source"] == str(src)
    assert body["suggested_dest"] == str(tmp_path / "Trip (sorted)")
    assert body["preview_bytes_needed"] == 4 * PREVIEW_BYTES_PER_FILE
    assert len(body["previews"]) == 3 and body["bytes"] > 0


def test_peek_refuses_a_path_that_is_not_a_folder(client, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    for bad in (str(f), str(tmp_path / "nope")):
        r = client.post("/api/peek", json={"source": bad})
        assert r.status_code == 400
        assert "folder" in r.json()["detail"]


def test_pick_returns_the_chosen_path(client, monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(R + "choose_folder", lambda prompt: seen.append(prompt) or tmp_path)
    monkeypatch.setattr(R + "picker_available", lambda: (True, ""))
    assert client.post("/api/pick", json={"prompt": "Pick photos"}).json() == {"path": str(tmp_path), "reason": ""}
    assert seen == ["Pick photos"]


def test_pick_cancelled_gives_no_path_and_no_complaint(client, monkeypatch):
    monkeypatch.setattr(R + "choose_folder", lambda prompt: None)
    monkeypatch.setattr(R + "picker_available", lambda: (True, ""))
    assert client.post("/api/pick", json={"prompt": "x"}).json() == {"path": None, "reason": ""}


def test_pick_explains_itself_when_tkinter_is_unavailable(client, monkeypatch):
    def boom(prompt):
        raise AssertionError("must not try to open a window that cannot exist")

    monkeypatch.setattr(R + "choose_folder", boom)
    monkeypatch.setattr(R + "picker_available", lambda: (False, "This Python install cannot show a folder window."))
    r = client.post("/api/pick", json={"prompt": "x"})
    assert r.status_code == 200
    assert r.json() == {"path": None, "reason": "This Python install cannot show a folder window."}


def _scanned(paths, tmp_path):
    f = tmp_path / "pic.jpg"
    f.write_bytes(b"x")
    write_json(paths.inventory_file, [{"id": 7, "path": str(f)}])
    return f


def test_open_reveals_a_file_by_id(client, paths, tmp_path, monkeypatch):
    f = _scanned(paths, tmp_path)
    revealed = []
    monkeypatch.setattr(R + "reveal_in_file_manager", lambda p: revealed.append(p))
    assert client.post("/api/open", json={"id": 7}).status_code == 200
    assert revealed == [f]


def test_open_an_unknown_id_is_a_404_and_reveals_nothing(client, paths, tmp_path, monkeypatch):
    _scanned(paths, tmp_path)
    monkeypatch.setattr(R + "reveal_in_file_manager", lambda p: (_ for _ in ()).throw(AssertionError))
    assert client.post("/api/open", json={"id": 99}).status_code == 404


def _dest(paths, tmp_path):
    dest = tmp_path / "Trip (sorted)"
    (dest / "Food").mkdir(parents=True)
    write_json(paths.source_file, {"path": "/x", "count": 1, "limit": None, "sorted": str(dest)})
    return dest


def test_open_opens_a_folder_inside_the_sorted_destination(client, paths, tmp_path, monkeypatch):
    dest = _dest(paths, tmp_path)
    opened = []
    monkeypatch.setattr(R + "open_folder", lambda p: opened.append(p))
    assert client.post("/api/open", json={"folder": "Food"}).status_code == 200
    assert client.post("/api/open", json={"folder": ""}).status_code == 200
    assert [p.resolve() for p in opened] == [(dest / "Food").resolve(), dest.resolve()]


def test_open_refuses_folders_outside_the_sorted_destination(client, paths, tmp_path, monkeypatch):
    _dest(paths, tmp_path)
    outside = tmp_path / "private"
    outside.mkdir()
    monkeypatch.setattr(R + "open_folder", lambda p: (_ for _ in ()).throw(AssertionError("opened " + str(p))))
    for bad in ("../../../Windows/System32", "../private", str(outside), "Food/../../private"):
        r = client.post("/api/open", json={"folder": bad})
        assert r.status_code == 400, bad
        assert "sorted" in r.json()["detail"]


def test_open_refuses_a_sibling_whose_name_starts_with_the_destination(client, paths, tmp_path, monkeypatch):
    dest = _dest(paths, tmp_path)
    sib = Path(str(dest) + "-evil")
    sib.mkdir()
    monkeypatch.setattr(R + "open_folder", lambda p: (_ for _ in ()).throw(AssertionError))
    assert client.post("/api/open", json={"folder": str(sib)}).status_code == 400


def test_open_with_no_stored_destination_is_refused_in_plain_words(client, tmp_path, monkeypatch):
    # nothing has been sorted yet: refusing, never "allow anything"
    monkeypatch.setattr(R + "open_folder", lambda p: (_ for _ in ()).throw(AssertionError))
    for folder in (str(tmp_path), "", "Food"):
        r = client.post("/api/open", json={"folder": folder})
        assert r.status_code == 400, folder
        assert "sorted" in r.json()["detail"] and "yet" in r.json()["detail"]


def test_open_a_missing_folder_inside_the_destination_is_a_400(client, paths, tmp_path):
    _dest(paths, tmp_path)
    assert client.post("/api/open", json={"folder": "Nope"}).status_code == 400


def test_open_needs_an_id_or_a_folder(client):
    assert client.post("/api/open", json={}).status_code == 422


# ---- previews shape (the contract Plan 3's frontend is written against) ----

def test_peek_previews_are_bare_file_names_that_the_peek_mount_serves(client, tmp_path):
    body = client.post("/api/peek", json={"source": str(_photos(tmp_path / "Trip"))}).json()
    assert set(body) == {
        "source", "photos", "videos", "bytes", "previews", "suggested_dest", "preview_bytes_needed", "free_bytes"
    }
    assert body["previews"] == ["0000.jpg", "0001.jpg", "0002.jpg"]
    for name in body["previews"]:
        got = client.get(f"/peek/{name}")
        assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"


# ---- symlink / junction escape ----

def test_open_refuses_a_link_inside_the_destination_that_points_outside(client, paths, tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    dest = _dest(paths, tmp_path)
    outside = tmp_path / "private"
    outside.mkdir()
    link = dest / "Escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
        mechanism = "symlink"
    except OSError:  # Windows without developer mode: a junction needs no privilege and escapes the same way
        if sys.platform != "win32":
            raise
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
        mechanism = "junction"
    print("escape link mechanism:", mechanism)  # visible with `pytest -s`; recorded in the report
    assert link.is_dir()
    assert os.path.realpath(link) == os.path.realpath(outside), mechanism  # the link really leaves the root
    monkeypatch.setattr(R + "open_folder", lambda p: (_ for _ in ()).throw(AssertionError("opened " + str(p))))
    r = client.post("/api/open", json={"folder": "Escape"})
    assert r.status_code == 400 and "not inside" in r.json()["detail"]


# ---- /api/categories ----

def _cats(paths):
    return json.loads(paths.categories_file.read_text(encoding="utf-8"))


def _cat(key, kind="photo"):
    return {"key": key, "kind": kind, "label": key.title(), "emoji": "x", "rule": "r"}


def test_categories_saves_a_valid_set(client, paths):
    new = [_cat("food"), _cat("misc"), _cat("clips", "video")]
    assert client.post("/api/categories", json={"categories": new}).status_code == 200
    assert _cats(paths) == new


def test_categories_rejects_a_set_with_no_video_folder_and_keeps_the_old_file(client, paths):
    before = paths.categories_file.read_bytes()
    r = client.post("/api/categories", json={"categories": [_cat("food"), _cat("misc")]})
    assert r.status_code == 400 and "video" in r.json()["detail"]
    assert paths.categories_file.read_bytes() == before


def test_categories_rejects_a_duplicate_key(client, paths):
    before = paths.categories_file.read_bytes()
    r = client.post("/api/categories", json={"categories": [_cat("a"), _cat("a"), _cat("v", "video")]})
    assert r.status_code == 400 and "twice" in r.json()["detail"]
    assert paths.categories_file.read_bytes() == before


def test_saving_categories_clears_cached_labels_and_restamps_the_fingerprint(client, paths):
    from photosorter.core.categories import categories_fingerprint

    paths.labels.mkdir(parents=True)
    (paths.labels / "batch_0.json").write_text("{}", encoding="utf-8")
    write_json(paths.labels_file, {"0": "food"})
    paths.categories_fingerprint_file.write_text("stale", encoding="utf-8")
    assert client.post("/api/categories", json={"categories": _cats(paths) + [_cat("brand_new")]}).status_code == 200
    assert not (paths.labels / "batch_0.json").exists()
    assert not paths.labels_file.exists()
    assert paths.categories_fingerprint_file.read_text(encoding="utf-8").strip() == categories_fingerprint(paths)


def test_categories_clears_the_cache_even_when_there_is_no_fingerprint_marker(client, paths):
    # a library sorted before fingerprinting existed: cache present, no marker
    paths.labels.mkdir(parents=True)
    (paths.labels / "batch_0.json").write_text("{}", encoding="utf-8")
    write_json(paths.labels_file, {"0": "food"})
    assert not paths.categories_fingerprint_file.exists()
    assert client.post("/api/categories", json={"categories": _cats(paths) + [_cat("new")]}).status_code == 200
    assert not (paths.labels / "batch_0.json").exists() and not paths.labels_file.exists()
    from photosorter.core.categories import categories_fingerprint

    assert paths.categories_fingerprint_file.read_text(encoding="utf-8").strip() == categories_fingerprint(paths)


# ---- /api/move ----

def _scan_ids(paths, n=3):
    """What a real scan leaves: both files. /api/move checks the id against the inventory, like /api/file."""
    write_json(paths.slim_file, [{"id": i, "kind": "photo", "bytes": 1} for i in range(n)])
    write_json(
        paths.inventory_file,
        [{"id": i, "name": f"p{i}.jpg", "path": f"/src/p{i}.jpg", "sha256": f"sha{i}"} for i in range(n)],
    )


def test_move_records_an_override_in_the_shape_merge_labels_reads(client, paths):
    _scan_ids(paths)
    assert client.post("/api/move", json={"id": 2, "key": "food", "sha": "any"}).status_code == 200
    assert client.post("/api/move", json={"id": 0, "key": "people", "sha": "any"}).status_code == 200
    assert client.post("/api/move", json={"id": 2, "key": "city", "sha": "any"}).status_code == 200  # last move wins
    got = json.loads(paths.overrides_file.read_text(encoding="utf-8"))
    assert got == {"2": "city", "0": "people"}


def test_move_updates_the_merged_label_when_there_is_one(client, paths):
    _scan_ids(paths)
    write_json(paths.labels_file, {"2": "people", "1": "people"})
    client.post("/api/move", json={"id": 2, "key": "food", "sha": "any"})
    assert json.loads(paths.labels_file.read_text(encoding="utf-8")) == {"2": "food", "1": "people"}


def test_move_rejects_an_unknown_category_and_stores_nothing(client, paths):
    _scan_ids(paths)
    r = client.post("/api/move", json={"id": 1, "key": "no_such_folder", "sha": "any"})
    assert r.status_code == 400 and "no_such_folder" in r.json()["detail"]
    assert not paths.overrides_file.exists()


def test_move_rejects_an_id_that_is_not_in_the_scan(client, paths):
    _scan_ids(paths, 3)
    for bad in (3, -1, 999):
        r = client.post("/api/move", json={"id": bad, "key": "food", "sha": "any"})
        assert r.status_code == 404 and "scan" in r.json()["detail"]
    assert not paths.overrides_file.exists()


def test_move_with_no_scan_is_a_404(client, paths):
    r = client.post("/api/move", json={"id": 0, "key": "food", "sha": "any"})
    assert r.status_code == 404 and "scan" in r.json()["detail"]


def test_move_refuses_to_overwrite_a_damaged_overrides_file(client, paths):
    _scan_ids(paths)
    paths.overrides_file.parent.mkdir(parents=True, exist_ok=True)
    paths.overrides_file.write_text("{not json", encoding="utf-8")
    r = client.post("/api/move", json={"id": 1, "key": "food", "sha": "any"})
    assert r.status_code == 409
    assert paths.overrides_file.read_text(encoding="utf-8") == "{not json"


# ---- round 4 ----

def test_saving_an_identical_list_keeps_the_cache_even_if_the_formatting_differs(client, paths):
    from photosorter.core.categories import categories_fingerprint

    same = _cats(paths)
    assert client.post("/api/categories", json={"categories": same}).status_code == 200
    paths.labels.mkdir(parents=True, exist_ok=True)
    (paths.labels / "batch_0.json").write_text("{}", encoding="utf-8")
    write_json(paths.labels_file, {"0": "food"})
    paths.categories_fingerprint_file.write_text(categories_fingerprint(paths), encoding="utf-8")
    paths.categories_file.write_text(json.dumps(same, indent=8), encoding="utf-8")  # same list, new bytes
    paths.categories_fingerprint_file.write_text(categories_fingerprint(paths), encoding="utf-8")
    assert client.post("/api/categories", json={"categories": same}).status_code == 200
    assert (paths.labels / "batch_0.json").exists() and paths.labels_file.exists()
    assert paths.categories_fingerprint_file.read_text(encoding="utf-8").strip() == categories_fingerprint(paths)


def _locked_rmtree(monkeypatch):
    """rmtree that deletes the marker (as a real walk may) then fails on a file a running sort holds."""
    import shutil

    def fake(path, *a, **k):
        (Path(path) / ".categories").unlink(missing_ok=True)
        raise PermissionError("claude_01.json is in use")

    monkeypatch.setattr(shutil, "rmtree", fake)


def test_a_failed_clear_poisons_the_marker_and_never_restamps(client, paths, monkeypatch):
    from photosorter.core.categories import categories_fingerprint

    paths.labels.mkdir(parents=True)
    (paths.labels / "claude_01.json").write_text("{}", encoding="utf-8")
    paths.categories_fingerprint_file.write_text(categories_fingerprint(paths), encoding="utf-8")
    _locked_rmtree(monkeypatch)
    r = client.post("/api/categories", json={"categories": _cats(paths) + [_cat("brand_new")]})
    assert r.status_code == 409 and "in use" in r.json()["detail"] and "save again" in r.json()["detail"]
    assert (paths.labels / "claude_01.json").exists()
    marker = paths.categories_fingerprint_file.read_text(encoding="utf-8").strip()
    assert marker and marker != categories_fingerprint(paths)  # the survivors must not look valid
    monkeypatch.undo()
    # the CLI's next gate sees a mismatch and clears instead of adopting the survivors
    from photosorter.__main__ import _drop_stale_labels

    _drop_stale_labels(paths)
    assert not (paths.labels / "claude_01.json").exists()


def test_saving_again_after_a_failed_clear_still_clears(client, paths, monkeypatch):
    paths.labels.mkdir(parents=True)
    (paths.labels / "claude_01.json").write_text("{}", encoding="utf-8")
    _locked_rmtree(monkeypatch)
    new = _cats(paths) + [_cat("brand_new")]
    assert client.post("/api/categories", json={"categories": new}).status_code == 409
    monkeypatch.undo()
    assert client.post("/api/categories", json={"categories": new}).status_code == 200  # identical, but poisoned
    assert not (paths.labels / "claude_01.json").exists()


def test_clear_label_cache_unit(paths, monkeypatch):
    import pytest

    from photosorter.core.categories import LabelCacheInUse, categories_fingerprint, clear_label_cache

    assert clear_label_cache(paths) is False
    paths.labels.mkdir(parents=True)
    (paths.labels / "a.json").write_text("{}", encoding="utf-8")
    write_json(paths.labels_file, {})
    assert clear_label_cache(paths) is True
    assert not paths.labels.exists() and not paths.labels_file.exists()
    paths.labels.mkdir(parents=True)
    (paths.labels / "a.json").write_text("{}", encoding="utf-8")
    _locked_rmtree(monkeypatch)
    with pytest.raises(LabelCacheInUse):
        clear_label_cache(paths)
    assert paths.categories_fingerprint_file.read_text(encoding="utf-8").strip() != categories_fingerprint(paths)


def test_categories_refuses_a_label_with_no_usable_name_left(client, paths):
    """Only a label that cannot become a folder at all is refused, and nothing is written when it is."""
    before = paths.categories_file.read_bytes()
    for bad in ("", "   ", "..", "...", " . ", "x" * 201):
        cats = [{**_cat("p"), "label": bad}, _cat("v", "video")]
        r = client.post("/api/categories", json={"categories": cats})
        assert r.status_code == 400, repr(bad)
        assert "name" in r.json()["detail"]
    assert paths.categories_file.read_bytes() == before


def test_categories_accepts_awkward_labels_and_keeps_them_inside_the_destination(client, paths):
    """The route refuses exactly what folder_name refuses, so a label the CLI has always sorted still saves.

    What must never happen is a 200 followed by a folder outside the destination, a name Windows rejects
    mid-copy with WinError 123, or two labels silently sharing one directory.
    """
    dest = Path(r"C:\dest\inner")
    awkward = [
        "Kids/Sports",  # the CLI has turned this into Kids-Sports since Plan 1
        "..B..BESCAPED",
        "C:BUsersBPublicBEvil",
        "Beach | Sea",
        "What? *",
        'He said "hi"',
        "a<b>c",
        "Food.",  # Windows drops the trailing dot, so this must not end up sharing Food's folder
        "line\nbreak",
        "tab\there",
        "nul\x00byte",
    ]
    names: list[str] = []
    for label in (a.replace("B", chr(92)) for a in awkward):
        cats = [{**_cat("p"), "label": label}, _cat("v", "video")]
        r = client.post("/api/categories", json={"categories": cats})
        assert r.status_code == 200, (repr(label), r.text)
        name = folder_name(Category(key="p", kind="photo", label=label, emoji="x", rule="r"))
        names.append(name)
        assert (dest / name).resolve().is_relative_to(dest), f"{label!r} -> {name!r} left the destination"
        assert not any(ch in name for ch in '<>:"/\\|?*'), f"{label!r} -> {name!r} keeps an illegal character"
        assert name == name.rstrip(" ."), f"{label!r} -> {name!r} has a trailing dot or space"
        assert min(name) >= " ", f"{label!r} -> {name!r} keeps a control character"
    assert "Kids-Sports" in names, "Kids/Sports must still round-trip the way the CLI has always written it"


def test_pick_refuses_a_second_dialog_while_one_is_open(client, monkeypatch):
    import threading

    entered, release = threading.Event(), threading.Event()

    def slow(prompt):
        entered.set()
        release.wait(10)
        return None

    monkeypatch.setattr(R + "choose_folder", slow)
    monkeypatch.setattr(R + "picker_available", lambda: (True, ""))
    first = {}
    t = threading.Thread(target=lambda: first.update(r=client.post("/api/pick", json={"prompt": "x"})))
    t.start()
    assert entered.wait(10)
    r = client.post("/api/pick", json={"prompt": "x"})
    assert r.status_code == 409 and "already open" in r.json()["detail"]
    release.set()
    t.join(10)
    assert first["r"].status_code == 200
    assert client.post("/api/pick", json={"prompt": "x"}).status_code == 200  # the lock was released


def test_move_with_a_sha_that_no_longer_matches_is_a_409(client, paths):
    _scan_ids(paths)
    write_json(paths.inventory_file, [{"id": i, "path": "p", "sha256": f"sha{i}"} for i in range(3)])
    r = client.post("/api/move", json={"id": 1, "key": "food", "sha": "other"})
    assert r.status_code == 409
    assert r.json()["detail"] == "The folder was rescanned since this page loaded. Reload the page."
    assert not paths.overrides_file.exists()
    assert client.post("/api/move", json={"id": 1, "key": "food", "sha": "sha1"}).status_code == 200
    assert json.loads(paths.overrides_file.read_text(encoding="utf-8")) == {"1": "food"}


def test_categories_refuses_two_labels_that_become_the_same_folder(client, paths):
    """Food. and Food both become Food, so accepting both would silently mix two categories' photos."""
    before = paths.categories_file.read_bytes()
    for a, b in (("Food.", "Food"), ("Kids/Sports", "Kids-Sports"), ("Trip ", "Trip")):
        cats = [{**_cat("p"), "label": a}, {**_cat("p2"), "label": b}, _cat("v", "video")]
        r = client.post("/api/categories", json={"categories": cats})
        assert r.status_code == 400, (a, b, r.text)
        assert "mixed" in r.json()["detail"]
    assert paths.categories_file.read_bytes() == before


def test_move_without_a_sha_is_refused_and_stores_nothing(client, paths):
    """Same contract as /api/file: an override is persistent, so a stale id here misfiles a photo for good."""
    _scan_ids(paths)
    r = client.post("/api/move", json={"id": 1, "key": "food"})
    assert r.status_code == 400 and "sha" in r.json()["detail"]
    assert not paths.overrides_file.exists()


def test_move_leaves_a_damaged_labels_file_alone_but_still_saves_the_move(client, paths):
    _scan_ids(paths)
    paths.labels_file.parent.mkdir(parents=True, exist_ok=True)
    paths.labels_file.write_text("{broken", encoding="utf-8")
    assert client.post("/api/move", json={"id": 1, "key": "food", "sha": "any"}).status_code == 200
    assert json.loads(paths.overrides_file.read_text(encoding="utf-8")) == {"1": "food"}
    assert paths.labels_file.read_text(encoding="utf-8") == "{broken"
