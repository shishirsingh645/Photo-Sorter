import shutil
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

from photosorter.config import Paths, read_json
from photosorter.core.categories import load_categories
from photosorter.core.demo import WEIGHTS, build_demo
from photosorter.models import DupeGroup

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def paths(tmp_path):
    # Only categories.json is needed. Copying it keeps these tests off the repo's real data/.
    root = tmp_path / "app"
    root.mkdir()
    shutil.copy(REPO_ROOT / "categories.json", root / "categories.json")
    return Paths(root=root)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("app")
    shutil.copy(REPO_ROOT / "categories.json", root / "categories.json")
    paths = Paths(root=root)
    out = root / "demo"
    return paths, out, build_demo(paths, out)


def test_demo_is_deterministic(paths, tmp_path):
    assert build_demo(paths, tmp_path / "a") == build_demo(paths, tmp_path / "b")
    total = sum(WEIGHTS.values())
    sampled = [f"{d}/{i}.jpg" for d in ("thumbs", "mini") for i in range(0, total, 97)]
    names = ["inventory.json", "labels.json", "dupes.json", "slim.json", "categories.json", "source.json"]
    for rel in [*sampled, *names]:
        assert (tmp_path / "a" / rel).read_bytes() == (tmp_path / "b" / rel).read_bytes(), rel


def test_demo_covers_every_category(paths, built):
    _, out, _ = built
    labels = read_json(out / "labels.json")
    assert set(labels.values()) == {c.key for c in load_categories(paths)}


def test_demo_uses_no_real_photos(built):
    _, out, _ = built
    inv = read_json(out / "inventory.json")
    assert inv
    assert all("path" not in r for r in inv)


def test_demo_draws_each_category_its_weight(built):
    _, out, count = built
    labels = read_json(out / "labels.json")
    assert Counter(labels.values()) == Counter(WEIGHTS)
    assert count == len(labels) == sum(WEIGHTS.values())


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
        assert g.keep != g.dupes[0]


def test_demo_categories_json_keeps_emoji_readable(paths, built):
    _, out, _ = built
    text = (out / "categories.json").read_text(encoding="utf-8")
    assert "🤳" in text
    assert read_json(out / "categories.json") == read_json(paths.categories_file)


def test_demo_writes_only_inside_its_output_folder(paths):
    build_demo(paths)  # default output folder is <root>/demo
    assert sorted(p.name for p in paths.root.iterdir()) == ["categories.json", "demo"]
    assert not paths.data.exists()
