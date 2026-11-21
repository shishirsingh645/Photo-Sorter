import re
import shutil
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

from photosorter.config import Paths, read_json
from photosorter.core import demo
from photosorter.core.categories import load_categories
from photosorter.core.demo import WEIGHTS, _keep_for, build_demo
from photosorter.models import DupeGroup, FileRecord

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def paths(tmp_path):
    # Only categories.json is needed. Copying it keeps these tests off the repo's real data/.
    root = tmp_path / "app"
    root.mkdir()
    shutil.copy(REPO_ROOT / "categories.json", root / "categories.json")
    return Paths(root=root)


@pytest.fixture
def small_weights(monkeypatch):
    # One file per category: the guard and clearing tests need real writes, not 1057 renders.
    keys = [c.key for c in load_categories(Paths(root=REPO_ROOT))]
    monkeypatch.setattr(demo, "WEIGHTS", {k: 1 for k in keys})
    return len(keys)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("app")
    shutil.copy(REPO_ROOT / "categories.json", root / "categories.json")
    paths = Paths(root=root)
    out = root / "demo"
    return paths, out, build_demo(paths, out)


def _pixels(path: Path) -> bytes:
    with Image.open(path) as im:
        return im.tobytes()


def test_demo_is_deterministic(paths):
    a, b = paths.root / "a", paths.root / "b"
    assert build_demo(paths, a) == build_demo(paths, b)
    total = sum(WEIGHTS.values())
    # JSON is compared byte for byte. JPEG bytes can change with the encoder, so thumbs compare decoded pixels.
    for d in ("thumbs", "mini"):
        for i in range(0, total, 97):
            assert _pixels(a / d / f"{i}.jpg") == _pixels(b / d / f"{i}.jpg"), f"{d}/{i}.jpg"
    names = ["inventory.json", "labels.json", "dupes.json", "slim.json", "categories.json", "source.json"]
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_demo_covers_every_category(paths, built):
    _, out, _ = built
    labels = read_json(out / "labels.json")
    assert set(labels.values()) == {c.key for c in load_categories(paths)}


def test_demo_uses_no_real_photos(built):
    paths, out, _ = built
    inv = read_json(out / "inventory.json")
    assert inv
    for r in inv:
        # Placeholder shape: a bare name that is not a file under the app folder, and a hash of that name.
        assert r["path"] == r["name"]
        assert not (paths.root / r["path"]).exists()
        assert re.fullmatch(r"[0-9a-f]{64}", r["sha256"])
        assert r["duration"] == 0.0


def test_demo_inventory_loads_as_file_records(built):
    # Plan 3 reads real and demo inventories through FileRecord.from_dict, so the demo must round-trip.
    _, out, count = built
    inv = read_json(out / "inventory.json")
    records = [FileRecord.from_dict(r) for r in inv]
    assert len(records) == count
    assert all(r.to_dict() == d for r, d in zip(records, inv, strict=True))


def test_demo_draws_each_category_its_weight(built):
    _, out, count = built
    labels = read_json(out / "labels.json")
    inv = read_json(out / "inventory.json")
    assert Counter(labels.values()) == Counter(WEIGHTS)
    # build_demo returns the record count (one per camera-roll file), not thumbs plus minis plus JSON.
    assert count == len(labels) == len(inv) == sum(WEIGHTS.values())


def test_demo_writes_one_thumb_and_mini_per_file(built):
    _, out, count = built
    assert len(list((out / "thumbs").glob("*.jpg"))) == count
    assert len(list((out / "mini").glob("*.jpg"))) == count
    with Image.open(out / "thumbs" / "0.jpg") as im:
        assert im.size == (256, 256)
    with Image.open(out / "mini" / "0.jpg") as im:
        assert im.size == (72, 72)


def test_demo_inventory_matches_kinds_and_names(built):
    _, out, _ = built
    labels = read_json(out / "labels.json")
    inv = read_json(out / "inventory.json")
    cats = {c.key: c.kind for c in load_categories(Paths(root=out.parent))}
    for r in inv:
        kind = cats[labels[str(r["id"])]]
        assert r["kind"] == kind
        assert r["ext"] == (".mov" if kind == "video" else ".jpg")
        assert r["name"] == f"IMG_{4000 + r['id']}{r['ext'].upper()}"


def test_demo_slim_index_has_three_fields(built):
    _, out, _ = built
    inv = read_json(out / "inventory.json")
    slim = read_json(out / "slim.json")
    assert [set(s) for s in slim] == [{"id", "kind", "bytes"}] * len(inv)
    assert [s["bytes"] for s in slim] == [r["bytes"] for r in inv]


def test_demo_dupes_are_valid_photo_groups(built):
    _, out, _ = built
    inv = read_json(out / "inventory.json")
    groups = [DupeGroup.from_dict(d) for d in read_json(out / "dupes.json")]
    assert groups
    dupe_ids = [g.dupes[0] for g in groups]
    assert len(set(dupe_ids)) == len(dupe_ids)
    for g in groups:
        assert inv[g.dupes[0]]["kind"] == "photo"
        assert inv[g.keep]["kind"] == "photo"
        assert g.keep != g.dupes[0]
        assert abs(g.keep - g.dupes[0]) == 1


def test_keep_for_never_picks_the_record_itself_or_a_video():
    def rec(i, kind):
        return FileRecord(id=i, path=Path(str(i)), name=str(i), ext=".jpg", kind=kind, bytes=1, sha256="0")

    photos = [rec(0, "photo"), rec(1, "photo"), rec(2, "photo")]
    assert _keep_for(photos, 0) == 1  # index 0 has no left neighbour: keep the right one, never itself
    assert _keep_for(photos, 2) == 1
    mixed = [rec(0, "photo"), rec(1, "video"), rec(2, "photo")]
    assert _keep_for(mixed, 0) is None  # its only neighbour is a video
    assert _keep_for(mixed, 2) is None
    assert _keep_for([rec(0, "photo"), rec(1, "video"), rec(2, "photo")], 1) == 0  # left photo is fine


def test_demo_categories_json_keeps_emoji_readable(paths, built):
    _, out, _ = built
    text = (out / "categories.json").read_text(encoding="utf-8")
    assert "🤳" in text
    assert read_json(out / "categories.json") == read_json(paths.categories_file)


def test_demo_writes_only_inside_its_output_folder(paths):
    build_demo(paths)  # default output folder is <root>/demo
    assert sorted(p.name for p in paths.root.iterdir()) == ["categories.json", "demo"]
    assert not paths.data.exists()


def test_demo_refuses_empty_path(paths, tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    with pytest.raises(ValueError):
        build_demo(paths, Path(""))
    with pytest.raises(ValueError):
        build_demo(paths, Path("."))
    assert list(cwd.iterdir()) == []
    assert sorted(p.name for p in paths.root.iterdir()) == ["categories.json"]


def test_demo_refuses_a_folder_outside_root(paths, tmp_path):
    outside = tmp_path / "elsewhere"
    with pytest.raises(ValueError):
        build_demo(paths, outside)
    with pytest.raises(ValueError):
        build_demo(paths, paths.root)  # the app folder itself is not a demo folder
    assert not outside.exists()
    assert sorted(p.name for p in paths.root.iterdir()) == ["categories.json"]


def test_demo_relative_path_resolves_against_root_not_cwd(paths, small_weights, tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    build_demo(paths, Path("rel"))
    assert (paths.root / "rel" / "inventory.json").exists()
    assert list(cwd.iterdir()) == []


def test_demo_clears_stale_previews_on_rerun(paths, small_weights):
    out = paths.demo
    for sub in ("thumbs", "mini"):
        (out / sub).mkdir(parents=True)
        (out / sub / "999.jpg").write_bytes(b"left over from a bigger run")
    assert build_demo(paths) == small_weights
    expected = sorted(f"{i}.jpg" for i in range(small_weights))
    assert sorted(p.name for p in (out / "thumbs").glob("*.jpg")) == expected
    assert sorted(p.name for p in (out / "mini").glob("*.jpg")) == expected
