import pytest

from photosorter.config import Paths
from photosorter.core.categories import (
    catch_all_for,
    categories_fingerprint,
    load_categories,
    save_categories,
    validate_categories,
)
from photosorter.models import Category


def cat(key, kind="photo"):
    return Category(key=key, kind=kind, label=key.title(), emoji="x", rule="r")


def ok():
    return [cat("home"), cat("vclips", kind="video")]


def test_validate_accepts_one_of_each_kind():
    validate_categories(ok())


def test_validate_rejects_duplicate_keys():
    with pytest.raises(ValueError, match="twice"):
        validate_categories([cat("food"), cat("food")])


def test_validate_rejects_losing_the_last_video_folder():
    with pytest.raises(ValueError, match="video folder"):
        validate_categories([cat("food", kind="photo")])


def test_validate_rejects_losing_the_last_photo_folder():
    with pytest.raises(ValueError, match="photo folder"):
        validate_categories([cat("vclips", kind="video")])


def test_catch_all_is_the_last_of_its_kind():
    cats = [cat("selfies"), cat("home"), cat("vtalk", kind="video"), cat("vclips", kind="video")]
    assert catch_all_for(cats, "photo").key == "home"
    assert catch_all_for(cats, "video").key == "vclips"


def test_catch_all_returns_none_when_kind_absent():
    assert catch_all_for([cat("selfies")], "video") is None


def test_shipped_categories_file_is_valid_and_has_fourteen_folders():
    cats = load_categories(Paths.default())
    assert len(cats) == 14
    validate_categories(cats)
    assert catch_all_for(cats, "photo").key == "screenshots"
    assert catch_all_for(cats, "video").key == "vclips"


def test_save_then_load_round_trips(tmp_path):
    paths = Paths(root=tmp_path)
    save_categories(paths, ok())
    assert load_categories(paths) == ok()


def test_fingerprint_is_12_chars_and_changes_with_content(tmp_path):
    paths = Paths(root=tmp_path)
    save_categories(paths, ok())
    first = categories_fingerprint(paths)
    assert len(first) == 12
    assert categories_fingerprint(paths) == first
    save_categories(paths, [*ok(), cat("food")])
    assert categories_fingerprint(paths) != first
