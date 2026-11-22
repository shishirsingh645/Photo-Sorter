"""The one-job runner: phases, cancellation, throttled progress and the subscriber lifecycle."""

from __future__ import annotations

import asyncio
import queue
import threading
from pathlib import Path

import pytest

from photosorter.config import Paths
from photosorter.core.scan import scan_folder
from photosorter.core.sheets import PER_SHEET, build_sheets
from photosorter.jobs import JobBusy, JobRunner
from photosorter.models import FileRecord
from tests.conftest import camera_roll


@pytest.fixture
def runner(tmp_path: Path) -> JobRunner:
    return JobRunner(Paths(root=tmp_path / "approot"))


def drain(sub) -> list:
    """Everything already queued, without waiting: the producer is finished by the time we call this."""
    out = []
    while True:
        try:
            out.append(sub.get_nowait())
        except queue.Empty:
            return out


def test_second_start_while_running_raises_job_busy(runner: JobRunner) -> None:
    release = threading.Event()
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: release.wait(5)))
    try:
        with pytest.raises(JobBusy):
            runner.start("sort", ["scan"], lambda ctx: None)
    finally:
        release.set()
    assert runner.join(5)
    # ... and the refusal has to be about THIS job, not a flag nobody ever clears:
    assert runner.state().running is False
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(1, 1)))
    assert runner.join(5)
    assert runner.state().code == 0


def test_phases_are_timed_and_recorded_in_order(runner: JobRunner) -> None:
    def body(ctx):
        ctx.run_phase("scan", lambda p: p(1, 1))
        ctx.run_phase("dupes", lambda p: p(1, 1))

    runner.start("sort", ["scan", "dupes"], body)
    assert runner.join(5)
    s = runner.state()
    assert list(s.timings) == ["scan", "dupes"]
    assert all(v >= 0.0 for v in s.timings.values())
    assert s.running is False and s.code == 0
    assert s.phases == ["scan", "dupes"]


def test_exception_inside_a_phase_ends_the_job_with_a_message(runner: JobRunner) -> None:
    def boom(_progress):
        raise RuntimeError("boom")

    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", boom))
    assert runner.join(5)
    s = runner.state()
    assert s.running is False and s.code != 0
    assert "boom" in " ".join(s.log)


def test_a_bad_phash_is_reported_as_its_message_not_a_traceback(runner: JobRunner) -> None:
    """Obligation: band_keys raises ValueError on a short phash; the user sees the sentence, not a stack."""

    def bad(_progress):
        raise ValueError("phash must be 16 hex characters (64 bits), got 'abc'")

    runner.start("sort", ["dupes"], lambda ctx: ctx.run_phase("dupes", bad))
    assert runner.join(5)
    log = " ".join(runner.state().log)
    assert "phash must be 16 hex characters" in log
    assert "Traceback" not in log and "File \"" not in log


def test_cancel_sets_the_event_and_finishes_the_job(runner: JobRunner) -> None:
    saw = threading.Event()
    started = threading.Event()

    def body(ctx):
        def phase(_progress):
            started.set()
            assert ctx.cancel_event.wait(5)
            saw.set()

        ctx.run_phase("scan", phase)

    runner.start("sort", ["scan"], body)
    assert started.wait(5)
    runner.cancel()
    assert runner.join(5)
    assert saw.is_set()
    s = runner.state()
    assert s.running is False and s.code != 0


def test_cancel_stops_the_work_instead_of_letting_it_run_on(runner: JobRunner) -> None:
    """A cancelled job must not keep grinding through the files: progress refuses to continue."""
    seen = []
    second_phase_ran = threading.Event()
    reached, cancelled = threading.Event(), threading.Event()

    def long_phase(progress):
        for i in range(1, 1001):
            seen.append(i)
            if i == 1:  # hand control to the test instead of sleeping, so cancel lands mid-loop every run
                reached.set()
                assert cancelled.wait(5)
            progress(i, 1000)

    def body(ctx):
        ctx.run_phase("scan", long_phase, interrupt=True)
        second_phase_ran.set()
        ctx.run_phase("dupes", lambda p: p(1, 1))

    runner.start("sort", ["scan", "dupes"], body)
    assert reached.wait(5)
    runner.cancel()
    cancelled.set()
    assert runner.join(5)
    assert len(seen) < 1000, "the loop kept running after cancel"
    assert not second_phase_ran.is_set(), "a later phase started after cancel"
    assert runner.state().running is False


def test_progress_is_throttled_with_a_final_event(runner: JobRunner) -> None:
    sub = runner.subscribe()
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: [p(i, 1000) for i in range(1, 1001)]))
    assert runner.join(10)
    events = drain(sub)
    progress = [e for e in events if e.type == "progress"]
    assert 1 <= len(progress) < 40, f"got {len(progress)} progress events"
    assert events[-1].type == "job_finished"
    assert events[-2].type == "progress" and events[-2].done == 1000 and events[-2].total == 1000
    assert events[0].type == "phase_started" and events[0].phase == "scan"


def test_every_subscriber_receives_the_same_events(runner: JobRunner) -> None:
    a, b = runner.subscribe(), runner.subscribe()
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(1, 1)))
    assert runner.join(5)
    first, second = drain(a), drain(b)
    assert [e.type for e in first] == ["phase_started", "progress", "job_finished"]
    assert [e.model_dump() for e in first] == [e.model_dump() for e in second]
    assert runner.subscriber_count == 2


def test_a_closed_subscriber_is_removed_and_does_not_block_others(runner: JobRunner) -> None:
    a, b = runner.subscribe(), runner.subscribe()
    b.close()
    assert runner.subscriber_count == 1
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(1, 1)))
    assert runner.join(5)
    assert [e.type for e in drain(a)] == ["phase_started", "progress", "job_finished"]
    assert drain(b) == []
    assert runner.subscriber_count == 1


def test_a_subscriber_that_never_drains_is_dropped_rather_than_blocking_the_job(runner: JobRunner) -> None:
    slow = runner.subscribe(maxsize=2)
    fast = runner.subscribe()
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(1, 1)))
    assert runner.join(5), "the job thread blocked on a full queue"
    assert len(drain(fast)) == 3
    assert runner.subscriber_count == 1
    assert slow.closed


def test_a_subscriber_that_joins_mid_job_gets_the_rest(runner: JobRunner) -> None:
    in_phase, go_on = threading.Event(), threading.Event()

    def body(ctx):
        ctx.run_phase("scan", lambda p: (in_phase.set(), go_on.wait(5), p(1, 1)))
        ctx.run_phase("dupes", lambda p: p(1, 1))

    runner.start("sort", ["scan", "dupes"], body)
    assert in_phase.wait(5)
    late = runner.subscribe()
    go_on.set()
    assert runner.join(5)
    events = drain(late)
    assert events[-1].type == "job_finished"
    assert any(e.type == "phase_started" and e.phase == "dupes" for e in events)
    assert not any(e.type == "phase_started" and e.phase == "scan" for e in events)  # that one it missed


def test_closing_a_subscription_twice_is_harmless(runner: JobRunner) -> None:
    sub = runner.subscribe()
    sub.close()
    sub.close()
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(1, 1)))
    assert runner.join(5)
    assert runner.subscriber_count == 0


def test_state_is_a_copy_and_survives_a_job_that_blew_up(runner: JobRunner) -> None:
    def body(ctx):
        ctx.log("starting")
        raise KeyError("missing")

    runner.start("sort", ["scan"], body)
    assert runner.join(5)
    s = runner.state()
    s.log.append("mutated by the caller")
    s.timings["scan"] = 99.0
    again = runner.state()
    assert "mutated by the caller" not in again.log
    assert "scan" not in again.timings
    assert "missing" in " ".join(again.log)


def test_the_log_is_capped_so_state_cannot_grow_without_bound(runner: JobRunner) -> None:
    runner.start("sort", ["scan"], lambda ctx: [ctx.log(f"line {i}") for i in range(1000)])
    assert runner.join(10)
    log = runner.state().log
    assert len(log) <= 200
    assert log[-1] == "line 999"


def test_a_finished_runner_can_start_again(runner: JobRunner) -> None:
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(1, 1)))
    assert runner.join(5)
    runner.cancel()  # the old job's flag must not poison the next one
    runner.start("dupes", ["dupes"], lambda ctx: ctx.run_phase("dupes", lambda p: p(1, 1)))
    assert runner.join(5)
    s = runner.state()
    assert s.step == "dupes" and s.code == 0 and list(s.timings) == ["dupes"]


# --- fix round 1 -------------------------------------------------------------


def test_a_phase_with_its_own_cancel_contract_is_not_unwound_by_progress(runner: JobRunner) -> None:
    """The default: progress must NOT raise, or a phase never reaches its own cleanup (see scan_folder)."""
    cleaned = threading.Event()
    ticks = []

    def phase(progress):
        for i in range(1, 6):
            if i == 2:
                runner.cancel()  # the Stop click lands mid-phase, as it does in a real scan
            progress(i, 5)  # must not raise, even once cancel is set
            ticks.append(i)
        if runner.cancel_event.is_set():
            cleaned.set()  # stands in for scan_folder deleting the inventory it can no longer back

    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", phase))
    assert runner.join(5)
    assert ticks == [1, 2, 3, 4, 5]
    assert cleaned.is_set()
    assert runner.state().code == 1  # the job still ends as cancelled


def test_a_cancelled_scan_deletes_the_inventory_it_can_no_longer_back(runner: JobRunner, tmp_path: Path) -> None:
    """The regression behind the default above: a real scan, cancelled mid-run, must leave no stale index."""
    roll = camera_roll(tmp_path / "roll", 40)
    paths = runner.paths

    def scan(cancel_at_first_tick: bool):
        def body(ctx):
            def phase(progress):
                def prog(done, total):
                    if cancel_at_first_tick:
                        runner.cancel()  # the Stop click, mid-scan
                    progress(done, total)

                return scan_folder(roll, ctx.paths, on_progress=prog, cancel=ctx.cancel_event)

            ctx.run_phase("scan", phase)

        runner.start("sort", ["scan"], body)
        assert runner.join(120)

    scan(cancel_at_first_tick=False)
    assert paths.inventory_file.exists() and paths.slim_file.exists() and paths.source_file.exists()
    thumbs_before = len(list(paths.thumbs.glob("*.jpg")))
    assert thumbs_before == 40

    scan(cancel_at_first_tick=True)
    assert runner.state().code == 1
    # scan_folder wiped thumbs/ and mini/ before starting, so the old inventory must go with them
    assert not paths.inventory_file.exists(), "a stale inventory survived the cancel"
    assert not paths.slim_file.exists()
    assert not paths.source_file.exists(), "/api/state would report the scan as done"
    assert len(list(paths.thumbs.glob("*.jpg"))) < thumbs_before


def test_build_sheets_stops_between_sheets_when_cancelled(tmp_path: Path) -> None:
    """A 100k library is ~3,334 renders with no progress callback; the event is the only way to stop it."""
    paths = Paths(root=tmp_path / "approot")
    records = [
        FileRecord(id=i, path=tmp_path / f"{i}.jpg", name=f"{i}.jpg", ext=".jpg", kind="photo", bytes=0, sha256="")
        for i in range(PER_SHEET * 3)
    ]
    cancel = threading.Event()
    cancel.set()
    assert build_sheets(records, paths, cancel=cancel) == []
    cancel.clear()
    assert len(build_sheets(records, paths, cancel=cancel)) == 3


def test_state_shows_progress_on_every_tick_even_when_events_are_throttled(runner: JobRunner) -> None:
    """Spec 13.3 throttles events, not /api/state: a 2-files-a-second phase must still move the bar."""
    ticked, go = threading.Event(), threading.Event()
    sub = runner.subscribe()
    sampled = []

    def phase(progress):
        for i in range(1, 4):
            progress(i, 100_000)  # 0.5% is 500 files, so none of these is published
            ticked.set()
            assert go.wait(5)
            go.clear()

    runner.start("sort", ["heic"], lambda ctx: ctx.run_phase("heic", phase))
    for _ in range(3):
        assert ticked.wait(5)
        ticked.clear()
        s = runner.state()
        sampled.append((s.phase, s.done, s.total))
        go.set()
    assert runner.join(5)
    assert sampled == [("heic", 1, 100_000), ("heic", 2, 100_000), ("heic", 3, 100_000)]
    assert [e.type for e in drain(sub)] == ["phase_started", "progress", "job_finished"]


def test_a_dropped_subscription_ends_its_async_iteration(runner: JobRunner) -> None:
    """Without this the SSE response never ends and the browser never reconnects."""
    sub = runner.subscribe(maxsize=1)
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(1, 1)))
    assert runner.join(5)
    assert sub.closed and runner.subscriber_count == 0

    async def read_all():
        return [event async for event in sub]

    assert asyncio.run(asyncio.wait_for(read_all(), 5)) == []


def test_a_subscription_closed_while_a_reader_waits_ends_that_reader(runner: JobRunner) -> None:
    sub = runner.subscribe()

    async def read_then_close():
        loop = asyncio.get_running_loop()
        loop.call_later(0.1, sub.close)
        return [event async for event in sub]

    # the poll timeout returns None; the close must turn the next one into the end of the iteration
    got = asyncio.run(asyncio.wait_for(read_then_close(), 5))
    assert all(event is None for event in got)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_base_exception_in_the_body_still_ends_the_job(runner: JobRunner) -> None:
    """KeyboardInterrupt and SystemExit (argparse in a labeller) must not brick the runner."""
    sub = runner.subscribe()

    def body(ctx):
        raise SystemExit("photo-sorter: error: unrecognized arguments")

    runner.start("sort", ["label"], body)
    assert runner.join(5)
    s = runner.state()
    assert s.running is False and s.code == 1
    assert "unrecognized arguments" in " ".join(s.log)
    assert [e.type for e in drain(sub)] == ["log", "job_finished"]
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(1, 1)))  # not bricked
    assert runner.join(5)
    assert runner.state().code == 0
