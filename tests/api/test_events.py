"""GET /api/events: the SSE stream the dashboard subscribes to instead of polling."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from photosorter import jobs
from photosorter.api import routes_events
from photosorter.api.app import create_app
from photosorter.config import Paths
from photosorter.jobs import JobRunner


@pytest.fixture
def runner(paths: Paths) -> JobRunner:
    return JobRunner(paths)


@pytest.fixture
def client(paths: Paths, runner: JobRunner) -> TestClient:
    return TestClient(create_app(paths, runner=runner), base_url="http://127.0.0.1:8765")


def read_events(response, until: str, limit: int = 200, deadline: float = 20.0) -> list[dict]:
    """Parse `data:` frames off the stream until the named event type arrives.

    The deadline matters: without one, a regression that stops events flowing hangs the suite on
    `iter_lines` instead of failing it. Comment frames still arrive, so the clock is always checked.
    """
    stop = time.monotonic() + deadline
    out: list[dict] = []
    for line in response.iter_lines():
        if time.monotonic() > stop:
            raise AssertionError(f"no {until!r} within {deadline}s; got {[e['type'] for e in out]}")
        if not line.startswith("data:"):
            continue
        out.append(json.loads(line[5:]))
        if out[-1]["type"] == until or len(out) >= limit:
            return out
    return out


def read_to_end(response, deadline: float = 20.0) -> list[str]:
    """Every frame until the server ends the response. Fails rather than hangs if it never does."""
    stop = time.monotonic() + deadline
    out: list[str] = []
    for line in response.iter_lines():
        out.append(line)
        if time.monotonic() > stop:
            raise AssertionError(f"the stream never ended; last frames {out[-4:]}")
    return out


def test_events_endpoint_streams_text_event_stream(client: TestClient) -> None:
    with client.stream("GET", "/api/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-store"


def test_a_job_started_after_the_stream_opens_appears_on_it(client: TestClient, runner: JobRunner) -> None:
    with client.stream("GET", "/api/events") as r:
        runner.start(
            "sort",
            ["scan"],
            lambda ctx: (ctx.log("working"), ctx.run_phase("scan", lambda p: p(7, 7))),
        )
        events = read_events(r, until="job_finished")
    assert runner.join(5)
    types = [e["type"] for e in events]
    assert types[-1] == "job_finished"
    assert "log" in types and "phase_started" in types
    progress = [e for e in events if e["type"] == "progress"]
    assert progress[-1] == {"type": "progress", "phase": "scan", "done": 7, "total": 7}
    assert events[-1]["code"] == 0 and events[-1]["step"] == "sort"


def test_a_client_that_disconnects_without_draining_is_unsubscribed(client: TestClient, runner: JobRunner) -> None:
    with client.stream("GET", "/api/events") as r:
        assert r.status_code == 200
        runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(1, 1)))
        assert runner.join(5)
        assert runner.subscriber_count == 1
    deadline = time.monotonic() + 5  # the route unsubscribes as its generator closes, which is not instant
    while runner.subscriber_count and time.monotonic() < deadline:
        time.sleep(0.02)
    assert runner.subscriber_count == 0


def test_two_streams_at_once_both_see_the_job(client: TestClient, runner: JobRunner) -> None:
    with client.stream("GET", "/api/events") as a, client.stream("GET", "/api/events") as b:
        assert runner.subscriber_count == 2
        runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(2, 2)))
        first = read_events(a, until="job_finished")
        second = read_events(b, until="job_finished")
    assert first == second
    assert [e["type"] for e in first] == ["phase_started", "progress", "job_finished"]


def test_without_a_runner_the_stream_explains_itself(paths: Paths) -> None:
    client = TestClient(create_app(paths), base_url="http://127.0.0.1:8765")
    r = client.get("/api/events")
    assert r.status_code == 503
    assert "job" in r.json()["detail"].lower()


def test_the_heartbeat_keeps_an_idle_stream_alive(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(routes_events, "HEARTBEAT_SECONDS", 0.6)
    pings = 0
    with client.stream("GET", "/api/events") as r:
        started = time.monotonic()
        for line in r.iter_lines():
            if line.startswith(": ping"):
                pings += 1
                if pings == 2:
                    break
            assert time.monotonic() - started < 10, "no heartbeat on an idle stream"
    assert pings == 2


def test_a_stream_that_stops_being_drained_is_ended_not_left_frozen(
    client: TestClient, runner: jobs.JobRunner, monkeypatch
) -> None:
    """A sleeping laptop fills the queue; the subscriber is dropped, so the RESPONSE must end too -
    otherwise EventSource never fires `error`, never reconnects, and the bar stays frozen."""
    monkeypatch.setattr(jobs, "QUEUE_SIZE", 2)
    monkeypatch.setattr(routes_events, "HEARTBEAT_SECONDS", 0.2)
    with client.stream("GET", "/api/events") as r:
        runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", lambda p: p(1, 1)))
        assert runner.join(5)
        assert runner.subscriber_count == 0, "a full queue should have dropped the subscriber"
        frames = read_to_end(r, deadline=10)  # the assertion is that this RETURNS at all
    assert 1 <= sum(f.startswith("data:") for f in frames) <= 2  # whatever fitted, then the end
