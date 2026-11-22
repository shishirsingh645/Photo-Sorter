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
    """One reader's bounded mailbox. Async-iterable for the SSE route, drainable for tests."""

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
        """The next event, or None when nothing arrived within `POLL_SECONDS` (the caller's heartbeat tick)."""
        try:
            return await asyncio.to_thread(self._q.get, True, POLL_SECONDS)
        except queue.Empty:
            return None


class JobContext:
    """What a job body is handed: phases, a log and the cancel flag to pass into `core` functions."""

    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner
        self.paths = runner.paths
        self.cancel_event = runner.cancel_event

    def log(self, msg: str) -> None:
        self._runner._log(msg)

    def run_phase(self, name: str, fn: Callable[[ProgressFn], object]) -> object:
        return self._runner._run_phase(name, fn)


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

    def subscribe(self, maxsize: int = QUEUE_SIZE) -> Subscription:
        sub = Subscription(self, maxsize)
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
        code = 0
        try:
            body(ctx)
            if self.cancel_event.is_set():
                code = 1
                self._log("Stopped at your request.")
        except _Cancelled:
            code = 1
            self._log("Stopped at your request.")
        except Exception as exc:
            code = 1
            # The message only: a ValueError out of band_keys ("phash must be 16 hex characters...") is a
            # sentence the user can act on, and a traceback in the job log is not.
            self._log(str(exc) or type(exc).__name__)
        with self._lock:
            self._state.running = False
            self._state.code = code
            step = self._state.step or ""
        self._publish(JobFinished(step=step, code=code))

    def _run_phase(self, name: str, fn: Callable[[ProgressFn], object]) -> object:
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
            if self.cancel_event.is_set():
                raise _Cancelled  # cancellation has to stop the work, not just flag it
            done, total, reported = now_done, now_total, True
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
