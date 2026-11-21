"""Duplicate detection that does not slow down as the library grows.

The reference tool compared every file against every other: 11 hours at 100,000
files. This finds the same groups in roughly linear time by *pigeonhole banding*
(spec 13.1).

Split each 64-bit perceptual hash into 5 bands of 13/13/13/13/12 bits. Two
hashes within Hamming distance 4 differ in at most 4 bits, which cannot touch
all 5 bands, so at least one band is bit-for-bit identical. Indexing by
(band index, band value) therefore puts every true near-duplicate pair in at
least one shared bucket, and comparing only within buckets misses nothing. Every
candidate is still confirmed with the real Hamming distance, the same-kind rule
and the PNG pixel guard, so this is exact rather than approximate: the same
groups the nested loop finds, no more and no fewer.

Only previews in `paths.thumbs` are read. The user's originals are never opened.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from photosorter.config import Paths, write_json
from photosorter.models import DupeGroup, FileRecord, ProgressFn

#: Perceptual hashes this far apart or closer are the same picture.
NEAR_DISTANCE = 4
_HASH_BITS = 64
_BANDS = 5

# PNG pixel guard: two different PNGs are only near-duplicates if their greyscale
# previews agree almost everywhere. Without it, two screenshots of the same
# dark-themed app get the same pHash and are called copies of each other.
_PNG_DELTA = 40  # per-pixel greyscale change that counts as changed
_PNG_MAX_CHANGED = 0.004  # 0.4% of pixels
_PREVIEW_CACHE_MAX = 256  # bounded: 100k previews must not be held at once

# Contact sheet geometry.
_TILE = 160
_PITCH = 170
_COLS = 8
_SHEET_QUALITY = 80

_PROGRESS_EVERY = 2000


@dataclass
class DuplicateResult:
    groups: list[DupeGroup]
    oversized_buckets: int
    pairs_compared: int


def band_keys(phash_hex: str, bands: int = 5) -> list[tuple[int, int]]:
    """The spec 13.1 pigeonhole bands: `(band index, band value)`, one per band.

    The 64 bits are split into `bands` contiguous segments as evenly as
    possible, the wider ones first (13/13/13/13/12 for the default 5).
    """
    value = int(phash_hex, 16)
    width, wide = divmod(_HASH_BITS, bands)
    keys: list[tuple[int, int]] = []
    shift = 0
    for i in range(bands):
        bits = width + 1 if i < wide else width
        keys.append((i, (value >> shift) & ((1 << bits) - 1)))
        shift += bits
    return keys


def hamming(a_hex: str, b_hex: str) -> int:
    return (int(a_hex, 16) ^ int(b_hex, 16)).bit_count()


def _preview(fid: int, paths: Paths, cache: dict[int, Image.Image | None]) -> Image.Image | None:
    if fid not in cache:
        if len(cache) >= _PREVIEW_CACHE_MAX:
            cache.clear()
        thumb = paths.thumbs / f"{fid}.jpg"
        try:
            with Image.open(thumb) as im:
                cache[fid] = im.convert("L")
        except (OSError, ValueError):
            cache[fid] = None
    return cache[fid]


def _looks_like_another_screen(a: FileRecord, b: FileRecord, paths: Paths, cache: dict) -> bool:
    """True when two PNGs' previews differ too much to call them the same picture.

    No preview means no evidence that they match, and a wrong grouping misfiles a
    photo the user wanted, so an unreadable preview counts as different.
    """
    pa, pb = _preview(a.id, paths, cache), _preview(b.id, paths, cache)
    if pa is None or pb is None or pa.size != pb.size:
        return True
    diff = ImageChops.difference(pa, pb).point(lambda p: 255 if p > _PNG_DELTA else 0)
    changed = diff.histogram()[255]
    return changed > _PNG_MAX_CHANGED * pa.size[0] * pa.size[1]


def _is_duplicate(a: FileRecord, b: FileRecord, paths: Paths, cache: dict) -> bool:
    if a.kind != b.kind:
        return False
    if hamming(a.phash, b.phash) > NEAR_DISTANCE:
        return False
    if a.ext.lower() == b.ext.lower() == ".png" and a.sha256 != b.sha256:
        return not _looks_like_another_screen(a, b, paths, cache)
    return True


def find_duplicates(
    records: list[FileRecord],
    paths: Paths,
    on_progress: ProgressFn | None = None,
    max_bucket: int = 10_000,
) -> DuplicateResult:
    """Group duplicate records, writing `dupes.json` and `work/duplicates.jpg`."""
    by_id = {r.id: r for r in records}
    parent = {r.id: r.id for r in records}

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression, so deep chains stay cheap
            parent[x], x = root, parent[x]
        return root

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    total = len(records)

    # Pass 1: byte-identical files, in one dict pass.
    first_with_sha: dict[str, int] = {}
    for r in records:
        if not r.sha256:
            continue
        if r.sha256 in first_with_sha:
            union(first_with_sha[r.sha256], r.id)
        else:
            first_with_sha[r.sha256] = r.id

    # Pass 2: near-duplicates, banded. A record that failed to scan has no
    # trustworthy hash, so it is never near-matched.
    buckets: dict[tuple[int, int], list[int]] = {}
    done = 0
    for r in records:
        if r.phash and not r.error:
            for key in band_keys(r.phash, _BANDS):
                buckets.setdefault(key, []).append(r.id)
        done += 1
        if on_progress and done % _PROGRESS_EVERY == 0:
            on_progress(done, total)

    cache: dict[int, Image.Image | None] = {}
    oversized = pairs = 0
    for ids in buckets.values():
        if len(ids) > max_bucket:
            # Thousands of near-blank frames share band values and collapse into
            # one bucket, restoring quadratic cost locally. Cap it and say so.
            oversized += 1
            ids = ids[:max_bucket]
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                if find(a) == find(b):
                    continue  # already the same group; the edge cannot change that
                pairs += 1
                if _is_duplicate(by_id[a], by_id[b], paths, cache):
                    union(a, b)

    components: dict[int, list[int]] = {}
    for r in records:
        components.setdefault(find(r.id), []).append(r.id)

    groups: list[DupeGroup] = []
    for ids in components.values():
        if len(ids) < 2:
            continue
        members = [by_id[i] for i in ids]
        keeper = min(members, key=lambda r: (-r.bytes, len(r.name), r.name, r.id))
        dupes = [i for i in ids if i != keeper.id]
        groups.append(
            DupeGroup(
                keep=keeper.id,
                dupes=dupes,
                type="exact" if len({m.sha256 for m in members}) == 1 else "near",
                freed=sum(by_id[i].bytes for i in dupes),
            )
        )

    write_json(paths.dupes_file, [g.to_dict() for g in groups])
    build_dupe_sheet(groups, paths)
    if on_progress:
        on_progress(total, total)
    return DuplicateResult(groups=groups, oversized_buckets=oversized, pairs_compared=pairs)


def build_dupe_sheet(groups: list[DupeGroup], paths: Paths, limit: int = 60) -> Path | None:
    """One row per group, keeper first, for an eyeball check before anything moves."""
    rows = groups[:limit]
    if not rows:
        return None
    cols = min(_COLS, max(len(g.dupes) + 1 for g in rows))
    sheet = Image.new("RGB", (cols * _PITCH, len(rows) * _PITCH), "white")
    draw = ImageDraw.Draw(sheet)
    for ri, g in enumerate(rows):
        for ci, fid in enumerate([g.keep, *g.dupes][:cols]):
            x, y = ci * _PITCH, ri * _PITCH
            thumb = paths.thumbs / f"{fid}.jpg"
            try:
                with Image.open(thumb) as im:
                    sheet.paste(im.convert("RGB").resize((_TILE, _TILE)), (x, y))
            except (OSError, ValueError):
                pass  # a missing preview leaves an empty tile; the tag still identifies it
            draw.text((x + 4, y + _TILE - 12), f"{fid} KEEP" if fid == g.keep else str(fid), fill=(255, 0, 0))
    paths.work.mkdir(parents=True, exist_ok=True)
    out = paths.work / "duplicates.jpg"
    sheet.save(out, quality=_SHEET_QUALITY)
    return out
