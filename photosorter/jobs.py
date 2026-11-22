"""NAIVE FIRST CUT (TDD red stage): one job in a thread, every event to every subscriber."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from photosorter.api.schemas import JobState
from photosorter.config import Paths
from photosorter.models import ProgressFn


class JobBusy(Exception):
    pass


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
    def __init__(self, runner: JobRunner, maxsize: int = 1000) -> None:
        self._runner, self._q = runner, queue.Queue(maxsize)
        self.closed = False

    def get_nowait(self) -> JobEvent:
        return self._q.get_nowait()

    def put(self, event: JobEvent) -> None:
        self._q.put_nowait(event)

    def close(self) -> None:
        self.closed = True
        self._runner.unsubscribe(self)


class JobContext:
    def __init__(self, runner: JobRunner) -> None:
        self.runner = runner
        self.paths = runner.paths
        self.cancel_event = runner.cancel_event

    def log(self, msg: str) -> None:
        self.runner.state_mut.log.append(msg)
        self.runner.publish(LogLine(message=msg))

    def run_phase(self, name: str, fn: Callable[[ProgressFn], object]) -> object:
        st = self.runner.state_mut
        st.phase = name
        self.runner.publish(PhaseStarted(phase=name))
        t0 = time.monotonic()
        result = fn(lambda done, total: self.runner.publish(Progress(phase=name, done=done, total=total)))
        st.timings[name] = time.monotonic() - t0
        return result


class JobRunner:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.cancel_event = threading.Event()
        self.state_mut = JobState()
        self._subscribers: set[Subscription] = set()
        self._thread: threading.Thread | None = None

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self, maxsize: int = 1000) -> Subscription:
        sub = Subscription(self, maxsize)
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._subscribers.discard(sub)

    def publish(self, event: JobEvent) -> None:
        for sub in list(self._subscribers):
            sub.put(event)

    def state(self) -> JobState:
        return self.state_mut

    def cancel(self) -> None:
        self.cancel_event.set()

    def join(self, timeout: float | None = None) -> bool:
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def start(self, step: str, phases: list[str], body: Callable[[JobContext], None]) -> None:
        self.state_mut = JobState(step=step, running=True, phases=list(phases), started=time.time())
        self._thread = threading.Thread(target=self._run, args=(body,), daemon=True)
        self._thread.start()

    def _run(self, body: Callable[[JobContext], None]) -> None:
        body(JobContext(self))
        self.state_mut.running = False
        self.state_mut.code = 0
        self.publish(JobFinished(step=self.state_mut.step or "", code=0))
