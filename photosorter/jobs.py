"""The one job the server runs at a time: phases, cancellation and throttled progress events.

The body runs in a daemon thread and talks to the HTTP layer only through events. Each subscriber
owns a bounded `queue.Queue`, so publishing never blocks the worker and never needs the event loop:
a subscriber whose queue is full (a browser tab that stopped reading) is dropped, not awaited.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from photosorter.api.schemas import JobState
from photosorter.config import Paths
from photosorter.models import ProgressFn

LOG_LINES = 200  # /api/state carries the log; a 100k-file run must not make that response unbounded
QUEUE_SIZE = 1000
POLL_SECONDS = 0.5  # how long a waiting reader blocks a worker thread, so a disconnect is noticed quickly
MIN_INTERVAL = 0.1  # spec 13.3: at most 10 progress events a second ...
MIN_FRACTION = 0.005  # ... and at most one per 0.5% of total, whichever is less frequent
STOPPED = "Stopped at your request."


class JobBusy(Exception):
    """Raised by `start` when a job is already running."""


class _Cancelled(Exception):
    """Internal: raised out of the progress callback so a running phase unwinds instead of finishing."""


class PhaseStarted(BaseModel):
    type: Literal["phase_started"] = "phase_started"
    phase: str


class Progress(BaseModel):
    type: Literal["progress"] = "progress"
    phase: str
    done: int
    total: int


class LogLine(BaseModel):
    type: Literal["log"] = "log"
    message: str


class JobFinished(BaseModel):
    type: Literal["job_finished"] = "job_finished"
    step: str
    code: int


JobEvent = PhaseStarted | Progress | LogLine | JobFinished


class Subscription:
    """One reader's bounded mailbox: an `AsyncIterator[JobEvent | None]` for the SSE route, drainable for tests.

    A `None` from the iterator means "nothing arrived in POLL_SECONDS" - the caller's heartbeat tick.
    Iteration ends (StopAsyncIteration) once the subscription is closed, including when the runner
    dropped it for not draining, so the HTTP response ends and the browser's EventSource reconnects.
    """

    def __init__(self, runner: JobRunner, maxsize: int = QUEUE_SIZE) -> None:
        self._runner = runner
        self._q: queue.Queue[JobEvent] = queue.Queue(maxsize)
        self.closed = False

    def put(self, event: JobEvent) -> None:
        """Raises `queue.Full` when the reader has stopped draining; the runner then drops us."""
        self._q.put_nowait(event)

    def get_nowait(self) -> JobEvent:
        return self._q.get_nowait()

    def close(self) -> None:
        self.closed = True
        self._runner.unsubscribe(self)

    def __enter__(self) -> Subscription:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __aiter__(self) -> Subscription:
        return self

    async def __anext__(self) -> JobEvent | None:
        """The next event, None on a poll timeout, or StopAsyncIteration once this subscription is closed."""
        if self.closed:
            raise StopAsyncIteration
        try:
            return await asyncio.to_thread(self._q.get, True, POLL_SECONDS)
        except queue.Empty:
            if self.closed:  # dropped while we waited: end the response instead of ticking on forever
                raise StopAsyncIteration from None
            return None


class JobContext:
    """What a job body is handed: phases, a log and the cancel flag to pass into `core` functions."""

    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner
        self.paths = runner.paths
        self.cancel_event = runner.cancel_event

    def log(self, msg: str) -> None:
        self._runner._log(msg)

    def run_phase(self, name: str, fn: Callable[[ProgressFn], object], interrupt: bool = False) -> object:
        """Run one phase, timing it and turning its progress into events.

        `interrupt=True` stops the phase by raising out of the progress callback. Use it ONLY for a
        phase that takes no `cancel` parameter and has nothing to clean up (find_duplicates writes
        its file at the very end). The default is False because a phase with its own cancel contract
        must be allowed to run it: `scan_folder` wipes thumbs/ and mini/ up front and, on cancel,
        deletes inventory.json, slim.json and source.json - unwinding past that would leave an
        inventory of 100k records pointing at 2k surviving previews. Those phases see
        `ctx.cancel_event` and stop themselves.
        """
        return self._runner._run_phase(name, fn, interrupt)


class JobRunner:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.cancel_event = threading.Event()
        self._lock = threading.RLock()
        self._state = JobState()
        self._subscribers: set[Subscription] = set()
        self._thread: threading.Thread | None = None

    # --- subscribers ---------------------------------------------------------

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def subscribe(self, maxsize: int | None = None) -> Subscription:
        sub = Subscription(self, QUEUE_SIZE if maxsize is None else maxsize)
        with self._lock:
            self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            self._subscribers.discard(sub)

    def _publish(self, event: JobEvent) -> None:
        with self._lock:
            targets = list(self._subscribers)
        for sub in targets:
            try:
                sub.put(event)
            except queue.Full:
                sub.close()  # a reader that stopped draining must not stall the job

    # --- state ---------------------------------------------------------------

    def state(self) -> JobState:
        """Never raises: /api/state is the dashboard's reconnect fallback, so an exception here is a blank UI."""
        try:
            with self._lock:
                return self._state.model_copy(deep=True)
        except Exception:
            return JobState()

    def _log(self, msg: str) -> None:
        with self._lock:
            self._state.log.append(msg)
            del self._state.log[:-LOG_LINES]
        self._publish(LogLine(message=msg))

    # --- running -------------------------------------------------------------

    def join(self, timeout: float | None = None) -> bool:
        """True once no job thread is alive. Used by the tests and by shutdown."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def cancel(self) -> None:
        # Under the lock: an unlocked read could grab the event `start` is in the middle of replacing,
        # so a Stop racing a Start would cancel the job that just began.
        with self._lock:
            self.cancel_event.set()

    def start(self, step: str, phases: list[str], body: Callable[[JobContext], None]) -> None:
        with self._lock:
            if self._state.running:
                raise JobBusy(f"A {self._state.step} job is already running. Stop it before starting another.")
            self.cancel_event = threading.Event()  # fresh, so a previous job's cancel cannot kill this one
            self._state = JobState(step=step, running=True, phases=list(phases), started=time.time())
            self._thread = threading.Thread(target=self._run, args=(body,), daemon=True, name=f"job-{step}")
            self._thread.start()

    def _run(self, body: Callable[[JobContext], None]) -> None:
        ctx = JobContext(self)
        code, message = 0, ""
        try:
            try:
                body(ctx)
                if self.cancel_event.is_set():
                    code, message = 1, STOPPED
            except _Cancelled:
                code, message = 1, STOPPED
            except BaseException as exc:
                # BaseException, not Exception: argparse in a labeller calls sys.exit(), and a SystemExit
                # or KeyboardInterrupt that escaped here would leave running=True and no job_finished -
                # a job the UI shows forever and a Start button that raises JobBusy until restart.
                # The message only: a ValueError out of band_keys ("phash must be 16 hex characters...")
                # is a sentence the user can act on, and a traceback in the job log is not.
                code, message = 1, str(exc) or type(exc).__name__
                if not isinstance(exc, Exception):
                    raise  # a shutdown signal is never swallowed; the bookkeeping below still runs
        finally:
            self._finish(code, message)

    def _finish(self, code: int, message: str) -> None:
        """Always runs, and cannot raise: whatever happened, the job must end and say so."""
        try:
            if message:
                self._log(message)
        except Exception:  # a broken log must not cost the UI its job_finished
            pass
        with self._lock:  # inside the lock, so a new job's phase_started can never precede this
            self._state.running = False
            self._state.code = code
            self._publish(JobFinished(step=self._state.step or "", code=code))

    def _run_phase(self, name: str, fn: Callable[[ProgressFn], object], interrupt: bool = False) -> object:
        if self.cancel_event.is_set():
            raise _Cancelled
        with self._lock:
            self._state.phase = name
            self._state.phase_started = time.time()
            self._state.done, self._state.total = 0, 0
        self._publish(PhaseStarted(phase=name))
        emitted: tuple[int, int] | None = None
        emitted_at = 0.0
        done = total = 0
        reported = False

        def progress(now_done: int, now_total: int) -> None:
            nonlocal emitted, emitted_at, done, total, reported
            if interrupt and self.cancel_event.is_set():
                raise _Cancelled  # only for a phase with no cancel parameter of its own: see run_phase
            done, total, reported = now_done, now_total, True
            with self._lock:
                # Every tick, not only the published ones: spec 13.3 throttles EVENTS, and /api/state is
                # the reconnect fallback - a phase at 2 files/s would otherwise report 0/0 for minutes.
                self._state.done, self._state.total = now_done, now_total
            now = time.monotonic()
            step = max(1, int(now_total * MIN_FRACTION))
            if now_done - (emitted[0] if emitted else 0) >= step and now - emitted_at >= MIN_INTERVAL:
                emitted, emitted_at = (now_done, now_total), now
                self._emit_progress(name, now_done, now_total)

        started = time.monotonic()
        result = fn(progress)
        if reported and (done, total) != emitted:
            self._emit_progress(name, done, total)  # spec 13.3: one guaranteed final event per phase
        with self._lock:
            self._state.timings[name] = time.monotonic() - started
        return result

    def _emit_progress(self, phase: str, done: int, total: int) -> None:
        with self._lock:
            self._state.done, self._state.total = done, total
        self._publish(Progress(phase=phase, done=done, total=total))
