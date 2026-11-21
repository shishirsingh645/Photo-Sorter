import threading

import pytest
from PIL import Image

from photosorter import platform as platform_mod
from photosorter.config import Paths, read_json
from photosorter.core import scan as scan_mod
from photosorter.core.scan import find_files, find_sidecar, scan_folder


def make_jpeg(path, colour="red", size=(120, 80)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)


@pytest.fixture
def paths(tmp_path):
    return Paths(root=tmp_path / "app")


@pytest.fixture
def src(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    return d


def test_find_sidecar_matches_plain_name(tmp_path):
    (tmp_path / "IMG_1.JPG").touch()
    (tmp_path / "IMG_1.JPG.json").touch()
    assert find_sidecar(tmp_path / "IMG_1.JPG").name == "IMG_1.JPG.json"


def test_find_sidecar_matches_truncated_supplemental_metadata(tmp_path):
    (tmp_path / "IMG_1.JPG").touch()
    (tmp_path / "IMG_1.JPG.supplemental-met.json").touch()
    assert find_sidecar(tmp_path / "IMG_1.JPG") is not None


def test_find_sidecar_matches_numbered_copy(tmp_path):
    (tmp_path / "IMG_1(1).JPG").touch()
    (tmp_path / "IMG_1.JPG.supplemental-metadata(1).json").touch()
    assert find_sidecar(tmp_path / "IMG_1(1).JPG").name.endswith("(1).json")


def test_find_sidecar_does_not_match_a_different_numbered_copy(tmp_path):
    (tmp_path / "IMG_1.JPG").touch()
    (tmp_path / "IMG_1.JPG.supplemental-metadata(1).json").touch()
    assert find_sidecar(tmp_path / "IMG_1.JPG") is None


def test_find_files_skips_appledouble_and_unknown_extensions(src):
    make_jpeg(src / "a.jpg")
    make_jpeg(src / "._a.jpg")
    (src / "notes.txt").write_text("x", encoding="utf-8")
    (src / "clip.MP4").write_bytes(b"1")
    assert [p.name for p in find_files(src)] == ["a.jpg", "clip.MP4"]


def test_limit_sample_is_deterministic(src):
    for i in range(20):
        make_jpeg(src / f"{i}.jpg")
    first = find_files(src, limit=5)
    assert len(first) == 5
    assert first == find_files(src, limit=5)


def test_scan_handles_devanagari_and_emoji_filenames(src, paths):
    name = "शादी_फोटो_🎉.jpg"
    make_jpeg(src / name)
    recs = scan_folder(src, paths)
    assert recs[0].name == name
    assert (paths.thumbs / "0.jpg").exists()
    assert (paths.mini / "0.jpg").exists()


def test_scan_fills_hash_and_16_char_phash(src, paths):
    make_jpeg(src / "a.jpg")
    r = scan_folder(src, paths)[0]
    assert len(r.sha256) == 64
    assert len(r.phash) == 16 and int(r.phash, 16) >= 0
    assert (r.w, r.h, r.kind, r.error) == (120, 80, "photo", None)


def test_unreadable_file_is_kept_with_error_and_does_not_abort_scan(src, paths):
    make_jpeg(src / "good.jpg")
    (src / "bad.jpg").write_bytes(b"not an image")
    recs = scan_folder(src, paths)
    assert len(recs) == 2
    bad = next(r for r in recs if r.name == "bad.jpg")
    assert bad.error and bad.phash is None
    assert len(bad.sha256) == 64  # it was readable, just not an image
    assert next(r for r in recs if r.name == "good.jpg").error is None
    assert (paths.thumbs / f"{bad.id}.jpg").exists()


def test_vanishing_file_is_recorded_as_an_error_not_an_exception(src, paths, monkeypatch):
    make_jpeg(src / "a.jpg")
    monkeypatch.setattr("photosorter.core.scan.find_files", lambda s, limit=0: [src / "a.jpg", src / "gone.jpg"])
    gone = scan_folder(src, paths)[1]
    assert gone.error and gone.sha256 == "" and gone.phash is None
    assert (paths.thumbs / "1.jpg").exists()


def test_scan_refuses_in_plain_words_when_disk_cannot_hold_previews(src, paths, monkeypatch):
    make_jpeg(src / "a.jpg")
    monkeypatch.setattr(platform_mod, "free_space_bytes", lambda p: 1000)
    with pytest.raises(ValueError, match="free space"):
        scan_folder(src, paths)


def test_progress_is_throttled_not_per_file(src, paths):
    for i in range(500):
        make_jpeg(src / f"{i}.jpg", size=(16, 16))
    calls = []
    scan_folder(src, paths, on_progress=lambda d, t: calls.append(d))
    assert len(calls) < 50
    assert calls[-1] == 500


def test_cancel_event_stops_the_scan_early(src, paths):
    for i in range(30):
        make_jpeg(src / f"{i}.jpg")
    cancel = threading.Event()
    cancel.set()
    assert scan_folder(src, paths, cancel=cancel) == []
    assert not paths.inventory_file.exists()


def test_slim_index_is_written_alongside_full_inventory(src, paths):
    make_jpeg(src / "a.jpg")
    scan_folder(src, paths)
    assert set(read_json(paths.slim_file)[0]) == {"id", "kind", "bytes"}
    assert read_json(paths.inventory_file)[0]["name"] == "a.jpg"
    assert read_json(paths.source_file)["path"] == str(src)


def test_heic_photo_gets_a_preview_and_no_error(src, paths):
    from pillow_heif import register_heif_opener

    register_heif_opener()
    Image.new("RGB", (64, 48), "blue").save(src / "iphone.heic")
    r = scan_folder(src, paths)[0]
    assert r.error is None and (r.w, r.h) == (64, 48)
    assert (paths.thumbs / "0.jpg").exists()


def test_well_formed_sidecar_fills_taken_and_geo(src, paths):
    make_jpeg(src / "a.jpg")
    (src / "a.jpg.json").write_text(
        '{"photoTakenTime": {"timestamp": "1700000000"}, "geoData": {"latitude": 12.5, "longitude": 77.25}}',
        encoding="utf-8",
    )
    r = scan_folder(src, paths)[0]
    assert r.taken == 1700000000 and r.geo == (12.5, 77.25)


def test_malformed_sidecar_is_ignored(src, paths):
    make_jpeg(src / "a.jpg")
    (src / "a.jpg.json").write_text("{not json", encoding="utf-8")
    r = scan_folder(src, paths)[0]
    assert r.error is None and r.taken is None and r.geo is None


def test_video_with_real_frame_gets_phash(src, paths, monkeypatch):
    (src / "v.mp4").write_bytes(b"x")
    monkeypatch.setattr("photosorter.core.scan._probe_video", lambda p, ps, rec: Image.new("RGB", (256, 256), "red"))
    r = scan_folder(src, paths)[0]
    assert r.kind == "video" and len(r.phash) == 16


def test_video_without_a_frame_has_no_phash(src, paths, monkeypatch):
    (src / "v.mp4").write_bytes(b"x")
    monkeypatch.setattr("photosorter.core.scan._probe_video", lambda p, ps, rec: None)
    assert scan_folder(src, paths)[0].phash is None


def test_failing_placeholder_does_not_abort_the_scan(src, paths, monkeypatch):
    (src / "bad.jpg").write_bytes(b"nope")
    make_jpeg(src / "good.jpg")

    def boom(*a):
        raise OSError("disk full")

    monkeypatch.setattr("photosorter.core.scan._placeholder", boom)
    recs = scan_folder(src, paths)
    assert len(recs) == 2 and any(r.error for r in recs)


def test_mid_scan_cancel_returns_partial_and_removes_stale_inventory(src, paths, monkeypatch):
    for i in range(200):
        make_jpeg(src / f"{i:03}.jpg", size=(16, 16))
    scan_folder(src, paths)  # leaves an inventory behind
    assert paths.inventory_file.exists()
    cancel = threading.Event()
    real, n = scan_mod._sha256, [0]

    def counting(path):
        n[0] += 1
        if n[0] == 3:
            cancel.set()
        return real(path)

    monkeypatch.setattr(scan_mod, "_sha256", counting)
    recs = scan_folder(src, paths, cancel=cancel)
    assert 0 < len(recs) < 200
    assert not paths.inventory_file.exists() and not paths.source_file.exists()
