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
