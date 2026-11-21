from PIL import Image

from photosorter.config import Paths
from photosorter.core.peek import PREVIEW_BYTES_PER_FILE, peek_folder


def jpg(path, size=(200, 100)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "red").save(path)


def test_peek_skips_dotfolders_and_already_sorted_output(tmp_path):
    src = tmp_path / "src"
    jpg(src / "a.jpg")
    jpg(src / ".cache" / "x.jpg")
    jpg(src / "pics (sorted)" / "y.jpg")
    assert peek_folder(src, Paths(root=tmp_path / "app")).photos == 1


def test_peek_counts_photos_videos_and_bytes(tmp_path):
    src = tmp_path / "src"
    jpg(src / "a.jpg")
    jpg(src / "sub" / "b.PNG")
    (src / "c.mp4").write_bytes(b"12345")
    (src / "notes.txt").write_text("ignore me", encoding="utf-8")
    r = peek_folder(src, Paths(root=tmp_path / "app"))
    assert (r.photos, r.videos) == (2, 1)
    assert r.bytes == (src / "a.jpg").stat().st_size + (src / "sub" / "b.PNG").stat().st_size + 5
    assert r.suggested_dest == tmp_path / "src (sorted)"


def test_peek_reports_preview_space_needed(tmp_path):
    src = tmp_path / "src"
    jpg(src / "a.jpg")
    (src / "c.mp4").write_bytes(b"1")
    r = peek_folder(src, Paths(root=tmp_path / "app"))
    assert r.preview_bytes_needed == r.photos * PREVIEW_BYTES_PER_FILE + r.videos * PREVIEW_BYTES_PER_FILE
    assert PREVIEW_BYTES_PER_FILE == 18_000
    assert r.free_bytes > 0


def test_peek_writes_small_previews_only_into_peek_folder(tmp_path):
    src = tmp_path / "src"
    for i in range(5):
        jpg(src / f"{i}.jpg")
    paths = Paths(root=tmp_path / "app")
    r = peek_folder(src, paths, preview_count=3)
    assert len(r.previews) == 3
    for name in r.previews:
        with Image.open(paths.peek / name) as im:
            assert max(im.size) <= 64
    assert sorted(p.name for p in src.iterdir()) == [f"{i}.jpg" for i in range(5)]


def test_peek_previews_are_reproducible_and_stale_ones_cleared(tmp_path):
    src = tmp_path / "src"
    for i in range(10):
        jpg(src / f"{i}.jpg", size=(10 + i, 10))
    paths = Paths(root=tmp_path / "app")
    first = peek_folder(src, paths, preview_count=4)
    second = peek_folder(src, paths, preview_count=4)
    assert first.previews == second.previews
    assert len(list(paths.peek.iterdir())) == 4


def test_peek_survives_a_broken_image_and_empty_folder(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.jpg").write_bytes(b"not an image")
    paths = Paths(root=tmp_path / "app")
    r = peek_folder(src, paths)
    assert r.photos == 1 and r.previews == []
    assert peek_folder(tmp_path / "empty_none", paths).photos == 0
