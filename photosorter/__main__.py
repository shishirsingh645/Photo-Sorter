"""The command line: one subcommand per stage, plus `sort`, which runs the whole pipeline.

Every stage leaves its answer on disk, so any of them can be run again on its own and
`sort` can pick up where a stopped run left off. Nothing here writes anywhere except the
app's own root and the sorted folder the user names: the originals are only ever read.

Problems are printed as plain sentences and the process exits 1. A traceback is not an
error message, so the errors the modules below raise on purpose - a destination inside
the photos folder, a perceptual hash of the wrong width, a labeller that cannot run -
are caught and shown as the words they carry.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

from photosorter.config import Paths, read_json, write_json
from photosorter.core.apply import apply_labels, check_destination, merge_labels
from photosorter.core.categories import categories_fingerprint, load_categories, validate_categories
from photosorter.core.demo import build_demo
from photosorter.core.dupes import find_duplicates
from photosorter.core.labelers.base import LabelerUnavailable
from photosorter.core.labelers.claude import ClaudeLabeler
from photosorter.core.scan import scan_folder
from photosorter.core.sheets import build_sheets
from photosorter.models import Category, DupeGroup, FileRecord, ProgressFn

#: Spec 7.2: below this share of files labelled, the sort stops instead of guessing.
LABEL_TOLERANCE = 0.95

#: True whichever folder sits inside the other, which is why it names neither as the one at fault.
_ROOT_AND_SOURCE_OVERLAP = (
    "Your photos folder and the app's own folder must be separate, and neither can sit inside the other, "
    "so the previews the app writes are never read back as photos. Please point --root at a folder "
    "somewhere else."
)
log = logging.getLogger(__name__)


class StubLabeler:
    """Gives every file the first folder of its kind. Exists so a test run needs no Claude CLI and no key."""

    name = "stub"

    def label(
        self,
        records: Sequence[FileRecord],
        cats: list[Category],
        paths: Paths,
        on_progress: ProgressFn | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, str]:
        first = {kind: next((c.key for c in cats if c.kind == kind), None) for kind in ("photo", "video")}
        if on_progress:
            on_progress(len(records), len(records))
        return {str(r.id): first[r.kind] for r in records if first[r.kind] is not None}


class JevLabeler:
    """Reads answers a local classifier already left in work/jev.json. It does not run one."""

    name = "jev"

    def label(
        self,
        records: Sequence[FileRecord],
        cats: list[Category],
        paths: Paths,
        on_progress: ProgressFn | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, str]:
        answers = read_json(paths.jev_file)
        if not isinstance(answers, dict):
            raise LabelerUnavailable(
                f"There are no answers to read at {paths.jev_file}. Run the labelling with "
                "--labeler claude, or put the answers in that file first."
            )
        if on_progress:
            on_progress(len(records), len(records))
        return {
            str(k): v["key"] for k, v in answers.items() if isinstance(v, dict) and isinstance(v.get("key"), str)
        }


def _labeler(name: str):
    if name == "stub":
        return StubLabeler()
    if name == "jev":
        return JevLabeler()
    return ClaudeLabeler()


def _progress(stage: str) -> ProgressFn:
    """One rewritten line, and at most one write per percent, so a 100k-file run stays 100 writes."""
    last = [-1]

    def show(done: int, total: int) -> None:
        share = 100 if not total else done * 100 // total
        finished = not total or done >= total
        if share == last[0] and not finished:
            return
        last[0] = share
        print(f"\r{stage}: {done} of {total} ({share}%)", end="\n" if finished else "", flush=True)

    return show


def _records(paths: Paths) -> list[FileRecord]:
    data = read_json(paths.inventory_file)
    if not isinstance(data, list):
        raise ValueError(
            'Nothing has been scanned yet. Run the scan first: python -m photosorter scan "<your photos folder>"'
        )
    return [FileRecord.from_dict(d) for d in data]


def _scanned_source(paths: Paths) -> Path:
    """The folder the user actually scanned. The destination is checked against this, never against a subfolder."""
    saved = read_json(paths.source_file)
    if not isinstance(saved, dict) or not saved.get("path"):
        raise ValueError(
            "We do not know which folder was scanned. Run the scan first: "
            'python -m photosorter scan "<your photos folder>"'
        )
    return Path(saved["path"])


def _clear_label_cache(paths: Paths, reason: str) -> None:
    """Throw away every cached label batch, and the merged labels built from them.

    A batch is cached under its batch number and reused when nearly all the ids it was asked
    about are in it, while an id is only a file's position in the scanned list. So the batches
    of one library fit the next library's ids exactly, and would be handed back as its answers.
    Anything that changes what was scanned, or the folders to sort into, has to clear them.
    """
    if paths.labels.exists():
        shutil.rmtree(paths.labels)
        print(reason)
    paths.labels_file.unlink(missing_ok=True)


def _drop_stale_labels(paths: Paths) -> None:
    """Spec 7.2: a change to categories.json makes every cached label stale, so they go."""
    fingerprint = categories_fingerprint(paths)
    marker = paths.categories_fingerprint_file
    if marker.exists():
        if marker.read_text(encoding="utf-8").strip() == fingerprint:
            return
        _clear_label_cache(paths, "The list of folders changed, so labels from the old list were cleared.")
    # No marker means a cache from before fingerprinting, not a changed list: it is kept and stamped.
    paths.labels.mkdir(parents=True, exist_ok=True)
    marker.write_text(fingerprint, encoding="utf-8")


def _cats(paths: Paths) -> list[Category]:
    cats = load_categories(paths)
    if not cats:
        raise ValueError(f"There are no folders to sort into. Add some to {paths.categories_file}.")
    validate_categories(cats)
    return cats


def do_scan(paths: Paths, source: Path, limit: int) -> list[FileRecord]:
    if not source.is_dir():
        raise ValueError(f'"{source}" is not a folder we can open. Please choose a folder that exists.')
    try:
        check_destination(source, paths.root)
    except ValueError:
        raise ValueError(_ROOT_AND_SOURCE_OVERLAP) from None
    # Cleared BEFORE the scan, never after. A kill in between would otherwise leave the new source.json
    # beside the old library's batches, and the next run would skip the scan and label from them. Clearing
    # first cannot go wrong: an interrupted scan leaves source.json pointing at the old library, so the
    # next run scans again, and the only cost of an empty cache is labelling that work once more.
    _clear_label_cache(paths, "A different set of photos is being looked at, so earlier labels were cleared.")
    records = scan_folder(source, paths, limit, on_progress=_progress("Looking at your photos"))
    photos = sum(1 for r in records if r.kind == "photo")
    unreadable = sum(1 for r in records if r.error)
    print(f"{len(records)} files: {photos} photos and {len(records) - photos} videos.")
    if unreadable:
        print(f"{unreadable} of them could not be opened. They are kept and put aside for you to look at.")
    return records


def do_dupes(paths: Paths, records: list[FileRecord]) -> None:
    result = find_duplicates(records, paths, on_progress=_progress("Looking for duplicates"))
    freed = sum(g.freed for g in result.groups)
    copies = sum(len(g.dupes) for g in result.groups)
    print(f"{len(result.groups)} sets of duplicates, {copies} extra copies, about {freed // 1_000_000} MB.")
    if result.capped_records:
        print(f"{result.capped_records} files were too alike to compare with everything, so a few may be missed.")


def do_label(paths: Paths, records: list[FileRecord], labeler_name: str) -> dict[str, str]:
    cats = _cats(paths)
    _drop_stale_labels(paths)
    labels = _labeler(labeler_name).label(records, cats, paths, _progress("Deciding where things go"))
    if records and len(labels) < LABEL_TOLERANCE * len(records):
        raise ValueError(
            f"Only {len(labels)} of {len(records)} files could be given a folder, and at least "
            f"{int(LABEL_TOLERANCE * 100)}% are needed. Please run the labelling again; finished work is kept."
        )
    write_json(paths.labels_file, labels)
    print(f"{len(labels)} of {len(records)} files have a folder.")
    return labels


def do_apply(paths: Paths, records: list[FileRecord], dest: Path) -> None:
    labels = read_json(paths.labels_file)
    if not isinstance(labels, dict):
        raise ValueError("Nothing has a folder yet. Run the labelling first: python -m photosorter label")
    merged = merge_labels(
        records,
        labels,
        read_json(paths.jev_file, default={}) or {},
        read_json(paths.overrides_file, default={}) or {},
        _cats(paths),
    )
    dupes = [DupeGroup.from_dict(d) for d in read_json(paths.dupes_file, default=[]) or []]
    result = apply_labels(
        records,
        dupes,
        merged.labels,
        dest,
        paths,
        on_progress=_progress("Copying into folders"),
        source=_scanned_source(paths),
    )
    print(f"{result.copied} files copied into {result.dest}.")
    for folder, count in sorted(result.counts.items()):
        print(f"  {folder}: {count}")
    if result.unsorted:
        print(f"{result.unsorted} files fitted no folder and are in _Review/unsorted for you to look at.")


def do_sort(paths: Paths, source: Path, dest: Path, limit: int, labeler_name: str) -> None:
    """The whole pipeline. The scan is the slow part, so it is skipped when its answer still fits the request."""
    # Checked first: on a large library the labelling can run for an hour, and being told
    # only then that the destination is wrong wastes all of it.
    check_destination(source, dest)
    saved = read_json(paths.source_file)
    unchanged = (
        isinstance(saved, dict)
        and saved.get("path") == str(source)
        and saved.get("limit", 0) == limit
        and paths.inventory_file.exists()
    )
    if unchanged:
        records = _records(paths)
        print(f"{len(records)} files were already looked at, so that step is skipped.")
    else:
        records = do_scan(paths, source, limit)
    do_dupes(paths, records)
    do_label(paths, records, labeler_name)
    do_apply(paths, records, dest)


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root", type=Path, default=None,
        help="where the app keeps its own files (default: the folder this app is installed in)",
    )  # fmt: skip
    labeler = argparse.ArgumentParser(add_help=False)
    labeler.add_argument(
        "--labeler", choices=("claude", "jev", "stub"), default="claude",
        help="claude asks your own Claude Code; jev reads work/jev.json; stub needs nothing and is for testing",
    )  # fmt: skip

    parser = argparse.ArgumentParser(prog="photo-sorter", description="Sort a camera roll into folders.")
    subs = parser.add_subparsers(dest="command", required=True)

    scan = subs.add_parser("scan", parents=[common], help="look at every photo and video in a folder")
    scan.add_argument("source", type=Path)
    scan.add_argument("--limit", type=int, default=0, help="only look at this many files, picked at random")

    subs.add_parser("dupes", parents=[common], help="find duplicates among the files already scanned")

    sheets = subs.add_parser("sheets", parents=[common], help="build the contact sheets the labeller reads")
    sheets.add_argument("--sample", action="store_true", help="build a handful of sheets to check, not all of them")

    subs.add_parser("label", parents=[common, labeler], help="decide which folder each file belongs in")

    apply_cmd = subs.add_parser("apply", parents=[common], help="copy the files into the sorted folders")
    apply_cmd.add_argument("dest", type=Path)

    demo = subs.add_parser("demo", parents=[common], help="build a fake camera roll to look at")
    demo.add_argument("--out", type=Path, default=None, help="a folder inside the app's own folder")

    sort = subs.add_parser("sort", parents=[common, labeler], help="do all of it: scan, duplicates, label, copy")
    sort.add_argument("source", type=Path)
    sort.add_argument("--dest", type=Path, required=True)
    sort.add_argument("--limit", type=int, default=0, help="only sort this many files, picked at random")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = Paths.default() if args.root is None else Paths(root=args.root)
    try:
        if args.command == "scan":
            do_scan(paths, args.source, args.limit)
        elif args.command == "dupes":
            do_dupes(paths, _records(paths))
        elif args.command == "sheets":
            written = build_sheets(_records(paths), paths, sample=args.sample)
            print(f"{len(written)} contact sheets built.")
        elif args.command == "label":
            do_label(paths, _records(paths), args.labeler)
        elif args.command == "apply":
            do_apply(paths, _records(paths), args.dest)
        elif args.command == "demo":
            print(f"{build_demo(paths, args.out)} files in the demo library.")
        elif args.command == "sort":
            do_sort(paths, args.source, args.dest, args.limit, args.labeler)
    except (ValueError, LabelerUnavailable) as e:
        print(f"\n{e}")
        return 1
    except OSError as e:
        # These carry a readable message, but a bug can arrive as one too, so keep the trace for the log.
        log.debug("the %s command stopped on an operating system error", args.command, exc_info=True)
        print(f"\n{e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
