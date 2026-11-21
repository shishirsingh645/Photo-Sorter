import itertools
import random
import time
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from photosorter.config import Paths, read_json
from photosorter.core.dupes import band_keys, build_dupe_sheet, find_duplicates, hamming
from photosorter.models import DupeGroup, FileRecord

SAME = "0f0f0f0f0f0f0f0f"


def rec(i, b=1000, name=None, phash=SAME, sha=None, kind="photo", ext=".jpg", error=None):
    """A FileRecord with everything dedupe looks at and nothing it does not."""
    name = name if name is not None else f"{i}{ext}"
    return FileRecord(
        id=i,
        path=Path("src") / name,
        name=name,
        ext=ext,
        kind=kind,
        bytes=b,
        sha256=sha if sha is not None else f"sha{i}",
        phash=phash,
        error=error,
    )


def thumb(paths, fid, fill=30, box=None):
    """A 256x256 preview like the one scan writes, optionally with a bright patch."""
    paths.thumbs.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (256, 256), (fill, fill, fill))
    if box:
        im.paste((220, 220, 220), box)
    im.save(paths.thumbs / f"{fid}.jpg", quality=90)


def flip(value, *bits):
    for b in bits:
        value ^= 1 << b
    return f"{value:016x}"


def groups_of(groups):
    return {frozenset([g.keep, *g.dupes]) for g in groups}


# --- bands ---------------------------------------------------------------


def test_bands_cover_all_64_bits_without_overlap():
    keys = band_keys("ffffffffffffffff")
    assert len(keys) == 5 and len({i for i, _ in keys}) == 5
    # 13+13+13+13+12 = 64 bits, each band all-ones
    assert sorted(v.bit_count() for _, v in keys) == [12, 13, 13, 13, 13]
    assert sum(v.bit_count() for _, v in keys) == 64
    assert band_keys("0000000000000000") == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]


def test_hashes_within_distance_four_always_share_a_band():
    # pigeonhole guarantee - the correctness proof of the whole approach
    base = 0x0123456789ABCDEF
    base_keys = set(band_keys(f"{base:016x}"))
    for positions in itertools.combinations(range(64), 4):
        other = base
        for p in positions:
            other ^= 1 << p
        assert base_keys & set(band_keys(f"{other:016x}"))


def test_a_hash_that_is_not_64_bits_is_refused_loudly():
    # Banding a wider hash on its low 64 bits would still never group two
    # different photos, but it would silently stop finding every duplicate.
    for bad in ["ffffffffffffffff0", "fff", ""]:
        with pytest.raises(ValueError):
            band_keys(bad)


def test_hamming_counts_differing_bits():
    assert hamming("0000000000000000", "0000000000000000") == 0
    assert hamming("0000000000000000", "ffffffffffffffff") == 64
    assert hamming("0000000000000000", "000000000000000f") == 4


# --- grouping ------------------------------------------------------------


def test_exact_duplicates_grouped_by_sha256(tmp_path):
    paths = Paths(root=tmp_path)
    recs = [
        rec(0, phash="0000000000000000", sha="same"),
        rec(1, phash="ffffffffffffffff", sha="same"),
        rec(2, phash="00000000ffffffff", sha="other"),
    ]
    groups = find_duplicates(recs, paths).groups
    assert groups_of(groups) == {frozenset({0, 1})}
    assert groups[0].type == "exact"
    assert groups[0].freed == 1000


def test_near_duplicates_grouped_within_distance_four(tmp_path):
    paths = Paths(root=tmp_path)
    base = 0x0123456789ABCDEF
    recs = [rec(0, phash=f"{base:016x}"), rec(1, phash=flip(base, 0, 9, 20, 63))]
    groups = find_duplicates(recs, paths).groups
    assert groups_of(groups) == {frozenset({0, 1})}
    assert groups[0].type == "near"


def test_distance_five_is_not_a_duplicate(tmp_path):
    paths = Paths(root=tmp_path)
    base = 0x0123456789ABCDEF
    recs = [rec(0, phash=f"{base:016x}"), rec(1, phash=flip(base, 0, 9, 20, 40, 63))]
    assert find_duplicates(recs, paths).groups == []


def test_photo_and_video_never_group_together(tmp_path):
    paths = Paths(root=tmp_path)
    recs = [rec(0, kind="photo"), rec(1, kind="video", ext=".mp4")]
    assert find_duplicates(recs, paths).groups == []


def test_keeper_is_largest_then_shortest_name(tmp_path):
    paths = Paths(root=tmp_path)
    g = find_duplicates(
        [rec(0, b=100, name="aaaa.jpg"), rec(1, b=100, name="a.jpg"), rec(2, b=50, name="b.jpg")], paths
    ).groups[0]
    assert g.keep == 1
    assert g.dupes == [0, 2]
    assert g.freed == 150


def test_records_with_errors_are_excluded_from_near_matching(tmp_path):
    paths = Paths(root=tmp_path)
    recs = [rec(0), rec(1, error="unreadable")]
    assert find_duplicates(recs, paths).groups == []


# --- the PNG pixel guard -------------------------------------------------


def test_png_pixel_guard_separates_different_screens_of_the_same_app(tmp_path):
    paths = Paths(root=tmp_path)
    thumb(paths, 0)
    thumb(paths, 1, box=(0, 0, 64, 64))  # 6.25% of pixels, far more than 0.4%
    recs = [rec(0, ext=".png"), rec(1, ext=".png")]
    assert find_duplicates(recs, paths).groups == []


def test_png_pixel_guard_runs_when_sha256_is_unknown(tmp_path):
    # An empty sha256 is "unknown", not "identical": reading it as identical
    # would wave two different screens straight past the guard.
    paths = Paths(root=tmp_path)
    thumb(paths, 0)
    thumb(paths, 1, box=(0, 0, 64, 64))
    recs = [rec(0, ext=".png", sha=""), rec(1, ext=".png", sha="")]
    assert find_duplicates(recs, paths).groups == []
    # nor may an unknown sha be reported as a byte-identical ("exact") group
    same = [rec(0, ext=".jpg", sha=""), rec(1, ext=".jpg", sha="")]
    assert find_duplicates(same, paths).groups[0].type == "near"


def test_png_pixel_guard_still_groups_resaved_identical_screenshots(tmp_path):
    paths = Paths(root=tmp_path)
    thumb(paths, 0, box=(0, 0, 64, 64))
    thumb(paths, 1, box=(0, 0, 64, 64))  # same screen, different bytes on disk
    recs = [rec(0, ext=".png"), rec(1, ext=".png")]
    assert groups_of(find_duplicates(recs, paths).groups) == {frozenset({0, 1})}


# --- exactness against the reference's nested loop -----------------------


def changed_fraction(paths, a, b):
    with Image.open(paths.thumbs / f"{a}.jpg") as ia, Image.open(paths.thumbs / f"{b}.jpg") as ib:
        ga, gb = ia.convert("L"), ib.convert("L")
        diff = ImageChops.difference(ga, gb).point(lambda p: 255 if p > 40 else 0)
        return diff.histogram()[255] / (256 * 256)


def bruteforce(recs, paths):
    """The reference tool's O(n^2) nested loop, union-find and all."""
    parent = {r.id: r.id for r in recs}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for a, b in itertools.combinations(recs, 2):
        same = False
        known_identical = bool(a.sha256) and a.sha256 == b.sha256
        if known_identical:
            same = True
        elif a.phash and b.phash and not a.error and not b.error:
            if a.kind == b.kind and hamming(a.phash, b.phash) <= 4:
                guard = a.ext == b.ext == ".png" and not known_identical
                same = not (guard and changed_fraction(paths, a.id, b.id) > 0.004)
        if same:
            parent[find(a.id)] = find(b.id)

    comps = {}
    for r in recs:
        comps.setdefault(find(r.id), []).append(r.id)
    return [DupeGroup(keep=ids[0], dupes=ids[1:], type="near", freed=0) for ids in comps.values() if len(ids) > 1]


def test_results_match_bruteforce_on_a_random_library(tmp_path):
    paths = Paths(root=tmp_path)
    rng = random.Random(7)
    clusters = [rng.getrandbits(64) for _ in range(40)]
    recs = []
    for i in range(400):
        base = clusters[rng.randrange(len(clusters))]
        bits = rng.sample(range(64), rng.choice([0, 1, 2, 3, 4, 4, 5, 6]))
        ext = rng.choice([".jpg", ".png"])
        recs.append(
            rec(
                i,
                b=rng.randrange(1, 10_000),
                phash=flip(base, *bits),
                sha=f"sha{rng.randrange(380)}",  # a few byte-identical pairs
                kind=rng.choice(["photo", "video"]) if ext == ".jpg" else "photo",
                ext=ext,
            )
        )
        # the guard needs a preview; three grey levels so it both fires and does not
        thumb(paths, i, fill=rng.choice([20, 20, 21]), box=(0, 0, 64, rng.choice([1, 1, 64])))

    assert groups_of(find_duplicates(recs, paths).groups) == groups_of(bruteforce(recs, paths))


# --- the degenerate bucket ----------------------------------------------


def test_thousands_of_identical_hashes_stay_fast_and_are_reported(tmp_path):
    paths = Paths(root=tmp_path)
    recs = [rec(i, phash="0000000000000000") for i in range(5000)]
    t0 = time.monotonic()
    result = find_duplicates(recs, paths, max_bucket=1000)
    assert time.monotonic() - t0 < 10
    assert result.oversized_buckets >= 1
    # the skipped records are counted, so the UI can say how many went unchecked
    assert result.capped_records == 4000
    assert sum(len(g.dupes) + 1 for g in result.groups) == 1000


def test_nothing_is_reported_as_capped_when_no_bucket_overflows(tmp_path):
    paths = Paths(root=tmp_path)
    result = find_duplicates([rec(0), rec(1)], paths)
    assert (result.oversized_buckets, result.capped_records) == (0, 0)


def test_progress_keeps_moving_through_the_comparison_pass(tmp_path):
    paths = Paths(root=tmp_path)
    seen = []
    rng = random.Random(11)
    recs = [rec(i, phash=f"{rng.getrandbits(64):016x}") for i in range(3000)]
    find_duplicates(recs, paths, on_progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (3000, 3000)
    assert all(t == 3000 for _, t in seen)
    assert seen == sorted(seen)  # monotonic
    # the second half of the bar belongs to the pair comparison, not to indexing
    assert any(1500 < d < 3000 for d, _ in seen)


# --- outputs -------------------------------------------------------------


def test_dupes_json_is_written_and_reloads(tmp_path):
    paths = Paths(root=tmp_path)
    find_duplicates([rec(0, b=10), rec(1, b=20)], paths)
    loaded = [DupeGroup.from_dict(d) for d in read_json(paths.dupes_file)]
    assert groups_of(loaded) == {frozenset({0, 1})}
    assert loaded[0].keep == 1 and loaded[0].freed == 10


def test_dupe_sheet_shows_the_keeper_first_in_each_row(tmp_path):
    paths = Paths(root=tmp_path)
    for i, fill in enumerate([0, 110, 220]):
        thumb(paths, i, fill=fill)
    groups = [DupeGroup(keep=1, dupes=[0, 2], type="near", freed=10)]
    sheet = build_dupe_sheet(groups, paths)
    assert sheet.exists()
    with Image.open(sheet) as im:
        assert im.size == (3 * 170, 170)
        grey = im.convert("L")
        tiles = [grey.getpixel((ci * 170 + 80, 60)) for ci in range(3)]
    # keeper (fill 110) first, then its dupes in order: 0 then 220
    assert [round(t / 55) for t in tiles] == [2, 0, 4]


def test_dupe_sheet_is_skipped_when_there_are_no_duplicates(tmp_path):
    assert build_dupe_sheet([], Paths(root=tmp_path)) is None
