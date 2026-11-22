from pathlib import Path

from PIL import Image

from photosorter.config import write_json
from photosorter.core.peek import PREVIEW_BYTES_PER_FILE

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
