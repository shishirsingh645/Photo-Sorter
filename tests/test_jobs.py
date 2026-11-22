"""The one-job runner: phases, cancellation, throttled progress and the subscriber lifecycle."""

from __future__ import annotations

import queue
import threading
from pathlib import Path

import pytest

from photosorter.config import Paths
from photosorter.jobs import JobBusy, JobRunner


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
        ctx.run_phase("scan", long_phase)
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
    assert [e.model_dump() for e in drain(a)] == [e.model_dump() for e in drain(b)]
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
