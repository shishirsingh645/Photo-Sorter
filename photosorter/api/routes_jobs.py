"""POST /api/sort, /api/run and /api/cancel, plus GET /api/labels: the pipeline, run as the one job.

Every refusal is a 400 carrying `{"error": "<plain words>"}`, and is made BEFORE the job starts: the
dashboard's Start button must be told "that folder is not there" rather than show a job that dies a
second later. One job at a time is the runner's rule - a second Start is this error, never a queue.

The phases are the CLI's phases in the CLI's order (spec 7.1), over the same `core` functions and the
same sentences; what differs is only where they report - `ctx.log` and progress events instead of
stdout - and that they can be stopped. Which phases may be interrupted and which must be handed
`ctx.cancel_event` is `JobContext.run_phase`'s rule, not this module's: a scan unwound past its own
cleanup would leave an inventory of records pointing at previews it had already wiped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from photosorter.api.routes_state import build_state
from photosorter.api.schemas import AppState
from photosorter.config import Paths, read_json, write_json
from photosorter.core.apply import (
    JEV_MIN_CONFIDENCE,
    ApplyResult,
    apply_labels,
    apply_summary,
    check_destination,
    merge_labels,
)
from photosorter.core.categories import (
    FOLDERS_CHANGED_CLEARED,
    NEW_SOURCE_CLEARED,
    clear_label_cache,
    drop_stale_labels,
    require_categories,
)
from photosorter.core.dupes import DuplicateResult, dupes_summary, find_duplicates
from photosorter.core.labelers import find_jev_key
from photosorter.core.labelers.base import LabelerUnavailable, check_label_coverage, label_summary
from photosorter.core.labelers.choice import make_labeler
from photosorter.core.labelers.claude import NOT_INSTALLED
from photosorter.core.scan import (
    check_source,
    read_inventory,
    scan_folder,
    scan_is_current,
    scan_skipped_summary,
    scan_summary,
    scanned_source,
)
from photosorter.jobs import JobBusy, JobContext, JobRunner
from photosorter.models import DupeGroup, FileRecord
from photosorter.platform import find_claude

router = APIRouter()

#: Asked for `labeler: "jev"` with no key anywhere. The key itself is never sent to the page.
NO_JEV_KEY = (
    "The Jev labeller needs an API key and there is none. Put JEV_KEY in a .env file in the app's own "
    "folder, or choose the Claude labeller instead."
)
#: Only the tests build a server with no runner, but an AttributeError would be a 500 and a blank page.
NO_RUNNER = "This server has no job runner, so nothing can be started."
NOTHING_SCANNED = "Nothing has been scanned yet. Choose a folder of photos and scan it first."
NOTHING_LABELLED = "Nothing has a folder yet, so there is nothing to copy. Run the labelling first."

#: Everything a refusal can arrive as. OSError included: an unusable path carries a sentence, not a bug.
REFUSED = (ValueError, LabelerUnavailable, JobBusy, OSError)

#: The three `make_labeler` answers to: claude asks the user's Claude Code, jev reads work/jev.json, and
#: stub needs nothing at all, so the pipeline can be exercised end to end without either.
LabelerName = Literal["claude", "jev", "stub"]
StepName = Literal["scan", "dupes", "label", "apply"]


class SortIn(BaseModel):
    source: str
    dest: str
    labeler: LabelerName = "claude"
    limit: int = Field(0, ge=0)


class RunIn(BaseModel):
    """One phase on its own. The fields a phase does not need are left out of the request."""

    step: StepName
    source: str | None = None
    dest: str | None = None
    labeler: LabelerName = "claude"
    limit: int = Field(0, ge=0)


# --- the phases ------------------------------------------------------------------------------------


def _scan_phase(ctx: JobContext, source: Path, limit: int) -> list[FileRecord]:
    """Look at every file under `source`, writing the inventory, the previews and source.json."""
    # Cleared BEFORE the scan, never after: see the CLI's do_scan for the crash window the other order
    # leaves. A batch is cached under a batch number, and an id is only a file's position in the list,
    # so another library's finished batches would fit this one's ids exactly and be handed back as answers.
    if clear_label_cache(ctx.paths):
        ctx.log(NEW_SOURCE_CLEARED)
    # cancel_event, not interrupt: scan_folder wipes thumbs/ and mini/ up front and deletes the inventory
    # on cancel. Unwinding past that cleanup would leave an inventory pointing at previews that are gone.
    records = cast(
        list[FileRecord],
        ctx.run_phase("scan", lambda p: scan_folder(source, ctx.paths, limit, p, ctx.cancel_event)),
    )
    for line in scan_summary(records):
        ctx.log(line)
    return records


def _dupes_phase(ctx: JobContext, records: list[FileRecord]) -> None:
    # interrupt=True is allowed here and nowhere else in this file: find_duplicates takes no cancel of
    # its own and writes dupes.json only at the very end, so there is nothing a stop can half-finish.
    result = cast(
        DuplicateResult, ctx.run_phase("dupes", lambda p: find_duplicates(records, ctx.paths, p), interrupt=True)
    )
    for line in dupes_summary(result):
        ctx.log(line)


def _label_phase(ctx: JobContext, records: list[FileRecord], labeler_name: str) -> None:
    if _stopped(ctx):
        return
    cats = require_categories(ctx.paths)
    if drop_stale_labels(ctx.paths):
        ctx.log(FOLDERS_CHANGED_CLEARED)
    labeler = make_labeler(labeler_name)
    labels = cast(
        dict[str, str],
        ctx.run_phase("label", lambda p: labeler.label(records, cats, ctx.paths, p, ctx.cancel_event)),
    )
    if _stopped(ctx):
        # A stop is not a labelling failure, and half the answers are not a result: the finished batches
        # are already cached by the labeller, so a later run resumes from them.
        return
    check_label_coverage(labels, records)  # spec 7.2, the same gate and sentence the CLI uses
    write_json(ctx.paths.labels_file, labels)
    ctx.log(label_summary(labels, records))


def _apply_phase(ctx: JobContext, records: list[FileRecord], dest: Path) -> None:
    # Before the labels are read, not after: a sort stopped during labelling has no labels.json, and
    # "Nothing has a folder yet" would then be the last word the dashboard shows about a job the user
    # stopped on purpose. The runner says "Stopped at your request." for a body that just returns.
    if _stopped(ctx):
        return
    paths = ctx.paths
    labels = read_json(paths.labels_file)
    if not isinstance(labels, dict):
        raise ValueError(NOTHING_LABELLED)
    merged = merge_labels(
        records,
        labels,
        read_json(paths.jev_file, default={}, strict=True) or {},
        read_json(paths.overrides_file, default={}, strict=True) or {},
        require_categories(paths),
    )
    dupes = [DupeGroup.from_dict(d) for d in read_json(paths.dupes_file, default=[], strict=True) or []]
    # `source` is the folder that was actually scanned, read from source.json - never the request's, and
    # never a record's parent. It is what makes "a destination inside the photos folder" refusable.
    source = scanned_source(paths)

    def copy(progress):
        # cancel, not interrupt: apply_labels stops between files, after the one it is copying, so the
        # sorted.csv it has written still describes exactly the files that are there.
        return apply_labels(
            records, dupes, merged.labels, dest, paths,
            on_progress=progress, cancel=ctx.cancel_event.is_set, source=source,
        )  # fmt: skip

    result = cast(ApplyResult, ctx.run_phase("apply", copy))
    if _stopped(ctx):
        return  # a part-copied destination is not a sorted one, so it is not recorded as one
    _record_sorted(paths, result.dest)
    for line in apply_summary(result):
        ctx.log(line)


def _stopped(ctx: JobContext) -> bool:
    """True once Stop has been pressed. A phase that sees it returns instead of reporting its own trouble."""
    return ctx.cancel_event.is_set()


def _record_sorted(paths: Paths, dest: Path) -> None:
    """Carried obligation C1: nothing else writes this, and the dashboard's done view reads it.

    Read-modify-write, so the scan's `path`, `count` and `limit` survive. `/api/state` reports it as
    `sorted` and as the `apply` step flag, and `/api/open` resolves a folder the page asks for against it.
    """
    source = read_json(paths.source_file, {})
    if not isinstance(source, dict):
        source = {}
    source["sorted"] = str(dest)
    write_json(paths.source_file, source)


# --- what a request has to get right --------------------------------------------------------------


def _server(request: Request) -> tuple[Paths, JobRunner]:
    runner = request.app.state.runner
    if runner is None:
        raise ValueError(NO_RUNNER)
    return request.app.state.paths, runner


def _folder(source: str | None) -> Path:
    if not source:
        raise ValueError("Say which folder of photos to look at.")
    return Path(source)


def _check_labeler(paths: Paths, name: str) -> None:
    """Checked before the job starts: a labeller that cannot run must not cost a whole scan first."""
    if name == "claude" and find_claude() is None:
        raise LabelerUnavailable(NOT_INSTALLED)
    if name == "jev" and find_jev_key(paths) is None:
        raise LabelerUnavailable(NO_JEV_KEY)


def _check_scanned(paths: Paths) -> None:
    """Both files, which is what /api/state calls the `scan` step: apply needs the scanned folder too."""
    if not (paths.inventory_file.exists() and paths.source_file.exists()):
        raise ValueError(NOTHING_SCANNED)


def _one_phase(paths: Paths, body: RunIn):
    """Validate `body` for its one step and return the job body that runs that step alone."""
    if body.step == "scan":
        source = _folder(body.source)
        check_source(source, paths)
        return lambda ctx: _scan_phase(ctx, source, body.limit)
    if body.step == "dupes":
        _check_scanned(paths)
        return lambda ctx: _dupes_phase(ctx, read_inventory(ctx.paths))
    if body.step == "label":
        _check_scanned(paths)
        require_categories(paths)  # an empty or broken folder list is a refusal, not an hour of labelling
        _check_labeler(paths, body.labeler)
        return lambda ctx: _label_phase(ctx, read_inventory(ctx.paths), body.labeler)
    _check_scanned(paths)
    if not body.dest:
        raise ValueError("Say which folder to copy the sorted photos into.")
    dest = Path(body.dest)
    if not paths.labels_file.exists():
        raise ValueError(NOTHING_LABELLED)
    check_destination(scanned_source(paths), dest)
    return lambda ctx: _apply_phase(ctx, read_inventory(ctx.paths), dest)


# --- the routes -----------------------------------------------------------------------------------


@router.post("/api/sort", response_model=AppState)
def sort(body: SortIn, request: Request) -> AppState | JSONResponse:
    """The whole pipeline. The scan is the slow part, so it is skipped when its answer still fits."""
    try:
        paths, runner = _server(request)
        source, dest = Path(body.source), Path(body.dest)
        check_source(source, paths)
        # Checked now, not at the end: on a large library the labelling runs for an hour, and being told
        # only then that the destination or the folder list is wrong wastes all of it.
        check_destination(source, dest)
        require_categories(paths)
        _check_labeler(paths, body.labeler)
        rescan = not scan_is_current(paths, source, body.limit)
        phases = (["scan"] if rescan else []) + ["dupes", "label", "apply"]

        def run(ctx: JobContext) -> None:
            if rescan:
                records = _scan_phase(ctx, source, body.limit)
            else:
                records = read_inventory(ctx.paths)
                ctx.log(scan_skipped_summary(records))
            _dupes_phase(ctx, records)
            _label_phase(ctx, records, body.labeler)
            _apply_phase(ctx, records, dest)

        runner.start("sort", phases, run)
    except REFUSED as e:
        return JSONResponse({"error": str(e)}, 400)
    return build_state(paths, runner)


@router.post("/api/run", response_model=AppState)
def run_one(body: RunIn, request: Request) -> AppState | JSONResponse:
    """One phase on its own, through the same machinery and the same phase bodies as /api/sort."""
    try:
        paths, runner = _server(request)
        runner.start(body.step, [body.step], _one_phase(paths, body))
    except REFUSED as e:
        return JSONResponse({"error": str(e)}, 400)
    return build_state(paths, runner)


@router.post("/api/cancel", response_model=AppState)
def cancel(request: Request) -> AppState | JSONResponse:
    """Ask the running job to stop. Nothing running is not an error: Stop twice is still stopped."""
    try:
        paths, runner = _server(request)
        runner.cancel()
    except REFUSED as e:
        return JSONResponse({"error": str(e)}, 400)
    return build_state(paths, runner)


@router.get("/api/labels", response_model=dict[str, str])
def get_labels(request: Request) -> dict[str, str]:
    """Spec 7.4: the labels written SO FAR, so a half-finished labelling run is visible live.

    The Claude batches on disk in sorted filename order, then Jev's answer wherever Claude has none or
    Jev is confident - the first two steps of the apply merge (spec 7.3), so what the page animates is
    what the sort will actually do. A damaged file is skipped rather than allowed to blank the live view.
    """
    paths: Paths = request.app.state.paths
    labels: dict[str, str] = {}
    for batch in sorted(paths.labels.glob("*.json")):
        got = read_json(batch)
        if isinstance(got, dict):
            labels.update({str(k): v for k, v in got.items() if isinstance(v, str)})
    jev = read_json(paths.jev_file)
    if isinstance(jev, dict):
        for fid, answer in jev.items():
            if not isinstance(answer, dict) or not isinstance(answer.get("key"), str):
                continue
            confidence = answer.get("confidence", 0)
            unsure = not isinstance(confidence, int | float) or confidence < JEV_MIN_CONFIDENCE
            # merge_labels' rule: Jev wins when it is confident, or wherever Claude said nothing at all.
            if not unsure or str(fid) not in labels:
                labels[str(fid)] = answer["key"]
    return labels
