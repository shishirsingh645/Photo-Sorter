"""A fake camera roll, so the dashboard can be seen before pointing it at real photos.

Every thumbnail is drawn from shapes, and the inventory describes files that do not
exist on disk. Ported from the reference tool's scripts/demo.py. The RNG is drawn in
the same order as the reference, so one seed gives the same bytes every run. Reordering
any draw moves every thumbnail after it.
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from photosorter.config import Paths, write_json
from photosorter.core.categories import load_categories
from photosorter.models import DupeGroup, FileRecord

SEED = 7

#: How many files each category gets. Keys must match categories.json.
WEIGHTS = {
    "selfies": 110, "people": 95, "pets": 40, "food": 60, "travel": 85, "city": 70, "home": 120,
    "docs": 55, "memes": 150, "screenshots": 140, "vtalk": 45, "vtravel": 25, "vscreen": 12, "vclips": 50,
}


def _jitter(rnd: random.Random, c: tuple[int, int, int], n: int = 26) -> tuple[int, int, int]:
    return tuple(max(0, min(255, v + rnd.randint(-n, n))) for v in c)


def _draw(rnd: random.Random, key: str, S: int = 256) -> Image.Image:
    im = Image.new("RGB", (S, S))
    d = ImageDraw.Draw(im)
    r = rnd.randint
    if key in ("screenshots", "memes", "docs", "vscreen"):
        dark = rnd.random() < .5 and key != "docs"
        bg = (24, 24, 28) if dark else (246, 246, 248)
        d.rectangle((0, 0, S, S), fill=bg)
        ink = (70, 70, 80) if dark else (205, 205, 212)
        y = 26
        if key == "memes":
            d.rectangle((18, 22, S - 18, 150), fill=_jitter(rnd, (200, 120, 90), 60))
            y = 170
        if key == "docs":
            d.rectangle((26, 18, S - 26, S - 10), fill=(252, 250, 244), outline=(220, 214, 200))
            ink = (180, 172, 160)
            y = 44
        while y < S - 20:
            d.rounded_rectangle((30, y, 30 + r(70, 190), y + 10), 5, fill=ink)
            y += r(18, 30)
        if key in ("screenshots",) and rnd.random() < .5:
            d.rounded_rectangle((30, S - 60, S - 30, S - 30), 14, fill=(52, 120, 246))
    elif key in ("travel", "vtravel"):
        sky = _jitter(rnd, rnd.choice([(150, 190, 230), (250, 170, 120), (200, 215, 235)]), 15)
        d.rectangle((0, 0, S, S), fill=sky)
        for k in range(3):
            base = _jitter(rnd, (90 - k * 20, 110 - k * 20, 130 - k * 15), 15)
            x = r(-60, 120)
            d.polygon([(x, S), (x + r(80, 140), r(70, 140)), (x + r(220, 300), S)], fill=base)
            if rnd.random() < .6:
                d.polygon([(x + 120, r(70, 100)), (x + 95, 125), (x + 150, 125)], fill=(248, 248, 250))
    elif key == "city":
        d.rectangle((0, 0, S, S), fill=_jitter(rnd, (22, 26, 48), 10))
        x = 0
        while x < S:
            w, h = r(28, 60), r(80, 210)
            d.rectangle((x, S - h, x + w, S), fill=_jitter(rnd, (40, 44, 70), 12))
            for wy in range(S - h + 10, S - 8, 16):
                for wx in range(x + 6, x + w - 6, 12):
                    if rnd.random() < .45:
                        d.rectangle((wx, wy, wx + 5, wy + 7), fill=(250, 214, 120))
            x += w + 4
    elif key == "food":
        d.rectangle((0, 0, S, S), fill=_jitter(rnd, (180, 130, 90), 30))
        d.ellipse((30, 30, S - 30, S - 30), fill=(245, 245, 240))
        for _ in range(7):
            cx, cy, rr = r(80, 176), r(80, 176), r(14, 30)
            colour = _jitter(rnd, rnd.choice([(200, 80, 50), (90, 150, 70), (230, 180, 60)]), 25)
            d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=colour)
    elif key == "pets":
        d.rectangle((0, 0, S, S), fill=_jitter(rnd, (150, 190, 140), 30))
        fur = _jitter(rnd, rnd.choice([(190, 140, 90), (60, 50, 45), (230, 220, 200)]), 20)
        d.ellipse((60, 90, 196, 230), fill=fur)
        d.polygon([(70, 120), (80, 50), (118, 100)], fill=fur)
        d.polygon([(186, 120), (176, 50), (138, 100)], fill=fur)
        for ex in (102, 154):
            d.ellipse((ex - 8, 140, ex + 8, 156), fill=(25, 25, 25))
    else:  # people: selfies, groups, talking heads, everyday clips, home
        bg = _jitter(rnd, rnd.choice([(225, 215, 200), (190, 205, 225), (160, 160, 175), (235, 200, 190)]), 20)
        d.rectangle((0, 0, S, S), fill=bg)
        if key == "home":
            d.rectangle((0, 170, S, S), fill=_jitter(rnd, (150, 120, 95), 20))
            d.rectangle((r(20, 60), 60, r(140, 200), 150), fill=_jitter(rnd, (70, 90, 120), 30))
            d.rectangle((r(150, 190), 120, 240, 175), fill=_jitter(rnd, (200, 190, 170), 20))
        else:
            n = 1 if key in ("selfies", "vtalk") else r(2, 4)
            for k in range(n):
                cx = S // 2 if n == 1 else 40 + k * (176 // max(1, n - 1))
                sc = 1.0 if n == 1 else 0.6
                skin = _jitter(rnd, rnd.choice([(235, 200, 170), (200, 150, 110), (150, 105, 75)]), 12)
                shirt = _jitter(rnd, (rnd.randint(40, 220), rnd.randint(40, 200), rnd.randint(40, 220)), 0)
                d.ellipse((cx - 90 * sc, S - 70 * sc, cx + 90 * sc, S + 120 * sc), fill=shirt)
                d.ellipse((cx - 45 * sc, S - 190 * sc, cx + 45 * sc, S - 80 * sc), fill=skin)
                hair = _jitter(rnd, (40, 30, 25), 15)
                d.pieslice((cx - 48 * sc, S - 200 * sc, cx + 48 * sc, S - 110 * sc), 180, 360, fill=hair)
    return im.filter(ImageFilter.GaussianBlur(0.6))


def _checked_out(paths: Paths, out: Path | None) -> Path:
    """Where the demo may write: a folder strictly inside paths.root.

    A relative `out` is taken from the root, never from the process's working directory,
    so an empty or drive-relative path cannot scatter files somewhere else.
    """
    root = paths.root.resolve()
    target = (paths.demo if out is None else root / out).resolve()
    if root not in target.parents:
        raise ValueError(f"The demo folder must be inside {root}, not {target}.")
    return target


def _keep_for(records: list[FileRecord], k: int) -> int | None:
    """The neighbour a burst group keeps: the photo just before k, else just after. None if neither is a photo."""
    for n in (k - 1, k + 1):
        if 0 <= n < len(records) and records[n].kind == "photo":
            return n
    return None


def build_demo(paths: Paths, out: Path | None = None) -> int:
    """Write the demo library into `out` (default <root>/demo), which must sit inside paths.root.

    Returns the number of camera-roll records, i.e. 1057 for the shipped WEIGHTS. Each record
    also gets one thumb and one mini on disk, so the file count is twice that plus the JSON files.
    """
    out = _checked_out(paths, out)
    rnd = random.Random(SEED)
    cats = load_categories(paths)
    for sub in ("thumbs", "mini"):
        (out / sub).mkdir(parents=True, exist_ok=True)
        # Clear old previews so a smaller WEIGHTS or category list leaves no orphan thumbs behind.
        for stale in (out / sub).glob("*.jpg"):
            stale.unlink()

    records: list[FileRecord] = []
    labels: dict[str, str] = {}
    for cat in cats:
        video = cat.kind == "video"
        for _ in range(WEIGHTS.get(cat.key, 40)):
            i = len(records)
            im = _draw(rnd, cat.key)
            im.save(out / "thumbs" / f"{i}.jpg", quality=78)
            im.resize((72, 72)).save(out / "mini" / f"{i}.jpg", quality=72)
            name = f"IMG_{4000 + i}.{'MOV' if video else 'JPG'}"
            # Placeholders for what a file that does not exist cannot have: the path is a bare name
            # (nothing sits at it), sha256 is a hash of that name so no two demo files look identical,
            # w/h are the drawn thumb size and duration is 0 (unknown).
            records.append(FileRecord(
                id=i,
                path=Path(name),
                name=name,
                ext=".mov" if video else ".jpg",
                kind=cat.kind,
                bytes=rnd.randint(20, 90) * 10**6 if video else rnd.randint(18, 60) * 10**5,
                sha256=hashlib.sha256(name.encode()).hexdigest(),
                w=256,
                h=256,
                duration=0.0,
            ))
            labels[str(i)] = cat.key

    # Pretend a few photos are burst shots: each group keeps a neighbouring photo and drops this one.
    dupes: list[DupeGroup] = []
    seen: set[int] = set()
    for _ in range(38):
        k = rnd.randrange(len(records))  # drawn even when skipped, so later draws stay put
        keep = _keep_for(records, k)
        if keep is None or records[k].kind != "photo" or k in seen:
            continue
        seen.add(k)
        dupes.append(DupeGroup(keep=keep, dupes=[k], type="near", freed=records[k].bytes * 6))

    write_json(out / "inventory.json", [r.to_dict() for r in records])
    write_json(out / "slim.json", [r.slim() for r in records])
    write_json(out / "labels.json", labels)
    write_json(out / "dupes.json", [g.to_dict() for g in dupes])
    write_json(out / "categories.json", [c.to_dict() for c in cats])
    write_json(out / "source.json", {"source": "~/Pictures/Camera roll (demo)"})
    return len(records)
