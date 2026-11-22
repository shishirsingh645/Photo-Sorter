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
import sys
from pathlib import Path

from photosorter.config import Paths, read_json, write_json
from photosorter.core.apply import apply_labels, apply_summary, check_destination, merge_labels
from photosorter.core.categories import (
    FOLDERS_CHANGED_CLEARED,
    NEW_SOURCE_CLEARED,
    clear_label_cache,
    drop_stale_labels,
    require_categories,
)
from photosorter.core.demo import build_demo
from photosorter.core.dupes import dupes_summary, find_duplicates
from photosorter.core.labelers.base import LabelerUnavailable, check_label_coverage, label_summary
from photosorter.core.labelers.choice import LABELER_NAMES, make_labeler
from photosorter.core.scan import (
    check_source,
    read_inventory,
    scan_folder,
    scan_is_current,
    scan_skipped_summary,
    scan_summary,
    scanned_source,
)
from photosorter.core.sheets import build_sheets
from photosorter.models import DupeGroup, FileRecord, ProgressFn

log = logging.getLogger(__name__)


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


def _clear_label_cache(paths: Paths, reason: str) -> None:
    """Clear every cached label (see clear_label_cache) and say why, if there was a cache to clear."""
    if clear_label_cache(paths):
        print(reason)


def _drop_stale_labels(paths: Paths) -> None:
    """Spec 7.2, in core so the dashboard's label phase uses the very same gate."""
    if drop_stale_labels(paths):
        print(FOLDERS_CHANGED_CLEARED)


def do_scan(paths: Paths, source: Path, limit: int) -> list[FileRecord]:
    check_source(source, paths)
    # Cleared BEFORE the scan, never after. A kill in between would otherwise leave the new source.json
    # beside the old library's batches, and the next run would skip the scan and label from them. Clearing
    # first cannot go wrong: an interrupted scan leaves source.json pointing at the old library, so the
    # next run scans again, and the only cost of an empty cache is labelling that work once more.
    _clear_label_cache(paths, NEW_SOURCE_CLEARED)
    records = scan_folder(source, paths, limit, on_progress=_progress("Looking at your photos"))
    for line in scan_summary(records):
        print(line)
    return records


def do_dupes(paths: Paths, records: list[FileRecord]) -> None:
    result = find_duplicates(records, paths, on_progress=_progress("Looking for duplicates"))
    for line in dupes_summary(result):
        print(line)


def do_label(paths: Paths, records: list[FileRecord], labeler_name: str) -> dict[str, str]:
    cats = require_categories(paths)
    _drop_stale_labels(paths)
    labels = make_labeler(labeler_name).label(records, cats, paths, _progress("Deciding where things go"))
    check_label_coverage(labels, records)
    write_json(paths.labels_file, labels)
    print(label_summary(labels, records))
    return labels


def do_apply(paths: Paths, records: list[FileRecord], dest: Path) -> None:
    labels = read_json(paths.labels_file)
    if not isinstance(labels, dict):
        raise ValueError("Nothing has a folder yet. Run the labelling first: python -m photosorter label")
    merged = merge_labels(
        records,
        labels,
        read_json(paths.jev_file, default={}, strict=True) or {},
        read_json(paths.overrides_file, default={}, strict=True) or {},
        require_categories(paths),
    )
    dupes = [DupeGroup.from_dict(d) for d in read_json(paths.dupes_file, default=[], strict=True) or []]
    result = apply_labels(
        records,
        dupes,
        merged.labels,
        dest,
        paths,
        on_progress=_progress("Copying into folders"),
        source=scanned_source(paths),
    )
    for line in apply_summary(result):
        print(line)


def do_sort(paths: Paths, source: Path, dest: Path, limit: int, labeler_name: str) -> None:
    """The whole pipeline. The scan is the slow part, so it is skipped when its answer still fits the request."""
    # Checked first: on a large library the labelling can run for an hour, and being told
    # only then that the destination is wrong wastes all of it.
    check_destination(source, dest)
    if scan_is_current(paths, source, limit):
        records = read_inventory(paths)
        print(scan_skipped_summary(records))
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
        "--labeler", choices=LABELER_NAMES, default="claude",
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

    srv = subs.add_parser("serve", parents=[common], help="run the dashboard's server on this computer only")
    srv.add_argument("--port", type=int, default=8765, help="the port to listen on (default: 8765)")
    srv.add_argument("--dev", action="store_true", help="don't serve the built page; the Vite dev server does that")
    srv.add_argument("--no-browser", action="store_true", help="don't open the dashboard in a browser")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = Paths.default() if args.root is None else Paths(root=args.root)
    try:
        if args.command == "scan":
            do_scan(paths, args.source, args.limit)
        elif args.command == "dupes":
            do_dupes(paths, read_inventory(paths))
        elif args.command == "sheets":
            written = build_sheets(read_inventory(paths), paths, sample=args.sample)
            print(f"{len(written)} contact sheets built.")
        elif args.command == "label":
            do_label(paths, read_inventory(paths), args.labeler)
        elif args.command == "apply":
            do_apply(paths, read_inventory(paths), args.dest)
        elif args.command == "demo":
            print(f"{build_demo(paths, args.out)} files in the demo library.")
        elif args.command == "serve":
            from photosorter.api.serve import serve  # not at the top: the web stack is slow to import

            return serve(paths, args.port, args.dev, not args.no_browser)
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
