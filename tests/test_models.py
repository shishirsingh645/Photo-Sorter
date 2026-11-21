"""Models the pipeline passes around. The dict round-trip is what the inventory
file relies on, so it has to be exact, including the optional fields that
to_dict leaves out when they are None."""

from pathlib import Path

from photosorter.models import IMAGE_EXTS, VIDEO_EXTS, Category, DupeGroup, FileRecord


def test_file_record_round_trips_through_dict():
    r = FileRecord(id=3, path=Path("D:/pics/a.jpg"), name="a.jpg", ext=".jpg",
                   kind="photo", bytes=100, sha256="ab")
    assert FileRecord.from_dict(r.to_dict()) == r


def test_slim_record_carries_only_three_fields():
    r = FileRecord(id=3, path=Path("D:/pics/a.jpg"), name="a.jpg", ext=".jpg",
                   kind="photo", bytes=100, sha256="ab", phash="ffff")
    assert r.slim() == {"id": 3, "kind": "photo", "bytes": 100}


def test_extension_sets_match_reference():
    assert ".heic" in IMAGE_EXTS and ".mov" in VIDEO_EXTS
    assert not (IMAGE_EXTS & VIDEO_EXTS)


def test_to_dict_omits_none_optional_fields_and_keeps_path_as_str():
    r = FileRecord(id=1, path=Path("D:/pics/a.jpg"), name="a.jpg", ext=".jpg",
                   kind="photo", bytes=100, sha256="ab")
    d = r.to_dict()
    for key in ("phash", "taken", "geo", "error"):
        assert key not in d
    assert d["path"] == str(Path("D:/pics/a.jpg"))
    assert isinstance(d["path"], str)


def test_from_dict_tolerates_absent_optional_fields():
    d = {"id": 1, "path": "D:/pics/a.jpg", "name": "a.jpg", "ext": ".jpg",
         "kind": "photo", "bytes": 100, "sha256": "ab"}
    r = FileRecord.from_dict(d)
    assert r.phash is None and r.taken is None and r.geo is None and r.error is None
    assert r.w == 0 and r.h == 0 and r.duration == 0.0
    assert isinstance(r.path, Path)


def test_geo_round_trips_as_tuple_not_list():
    r = FileRecord(id=2, path=Path("D:/pics/b.heic"), name="b.heic", ext=".heic",
                   kind="photo", bytes=5, sha256="cd", geo=(51.5, -0.12), taken=1700000000)
    back = FileRecord.from_dict(r.to_dict())
    assert back == r
    assert isinstance(back.geo, tuple)


def test_dupe_group_round_trips_through_dict():
    g = DupeGroup(keep=1, dupes=[2, 3], type="exact", freed=2048)
    assert DupeGroup.from_dict(g.to_dict()) == g


def test_category_round_trips_through_dict():
    c = Category(key="food", kind="photo", label="Food & drinks", emoji="🍜", rule="plates and drinks")
    assert Category.from_dict(c.to_dict()) == c
