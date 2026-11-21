"""Paths and JSON I/O.

The emoji round-trip is the regression test for the reference's worst
cross-platform bug: it opens text files without an explicit encoding, so on
Windows it uses cp1252 and the emoji in categories.json crash it. That is why
the reference has to be run with PYTHONUTF8=1. This replica must not need it.
"""

from photosorter.config import Paths, read_json, write_json


def test_write_json_round_trips_emoji_without_locale_env(tmp_path):
    p = tmp_path / "nested" / "cats.json"
    write_json(p, [{"label": "Food & drinks", "emoji": "🍜"}])
    assert read_json(p)[0]["emoji"] == "🍜"
    assert "🍜" in p.read_text(encoding="utf-8")


def test_read_json_returns_default_when_missing(tmp_path):
    assert read_json(tmp_path / "nope.json", default={}) == {}


def test_paths_are_all_under_root(tmp_path):
    paths = Paths(root=tmp_path)
    assert paths.thumbs == tmp_path / "data" / "thumbs"
    assert paths.labels == tmp_path / "work" / "labels"
    assert paths.categories_file == tmp_path / "categories.json"


def test_a_corrupt_file_reads_as_missing(tmp_path):
    for raw in (b"{half", b"\xff\xfe\x00bad"):
        f = tmp_path / "x.json"
        f.write_bytes(raw)
        assert read_json(f, default="d") == "d"


def test_strict_read_still_raises_on_a_corrupt_file(tmp_path):
    import json

    import pytest

    f = tmp_path / "x.json"
    f.write_text("{half", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_json(f, default="d", strict=True)


def test_write_json_never_leaves_a_half_written_target(tmp_path, monkeypatch):
    import json

    import pytest

    from photosorter import config

    f = tmp_path / "x.json"
    write_json(f, {"a": 1})

    def boom(*a, **k):
        raise RuntimeError("killed mid-write")

    monkeypatch.setattr(config.json, "dump", boom)
    with pytest.raises(RuntimeError):
        write_json(f, {"a": 2})
    assert json.loads(f.read_text(encoding="utf-8")) == {"a": 1}
