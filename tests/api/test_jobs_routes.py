"""The sort and single-step endpoints: what they refuse, which phases they pick, and the live labels.

The `client` fixture here replaces the one in conftest.py: these routes need a real JobRunner behind
them. A job runs in its own thread, so every test that starts one waits for it with `finish(runner)`
rather than sleeping.
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

from photosorter.api.app import create_app
from photosorter.config import Paths, read_json, write_json
from photosorter.jobs import JobRunner
from tests.conftest import camera_roll


@pytest.fixture
def runner(paths: Paths) -> JobRunner:
    return JobRunner(paths)


@pytest.fixture
def client(paths: Paths, runner: JobRunner) -> TestClient:
    return TestClient(create_app(paths, runner=runner), base_url="http://127.0.0.1:8765")


def finish(runner: JobRunner) -> None:
    assert runner.join(180), "the job thread never finished"


def photo_key(paths: Paths) -> str:
    """A real photo folder key from the categories the fixture copied in."""
    cats = json.loads(paths.categories_file.read_text(encoding="utf-8"))
    return next(c["key"] for c in cats if c["kind"] == "photo")


def gated_scan(monkeypatch, open_gate: threading.Event, entered: threading.Event):
    """Make the scan phase sit still until `open_gate` is set, so a job can be caught mid-run."""
    from photosorter.api import routes_jobs

    real = routes_jobs.scan_folder

    def slow(*args, **kwargs):
        entered.set()
        assert open_gate.wait(30), "the gate was never opened"
        return real(*args, **kwargs)

    monkeypatch.setattr(routes_jobs, "scan_folder", slow)


def test_sort_rejects_a_source_folder_that_does_not_exist(client):
    r = client.post("/api/sort", json={"source": "D:/nope", "dest": "D:/out"})
    assert r.status_code == 400 and "folder" in r.json()["error"]


def test_sort_rejects_claude_labeller_when_cli_is_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr("photosorter.api.routes_jobs.find_claude", lambda: None)
    source = camera_roll(tmp_path / "roll", 2)
    r = client.post(
        "/api/sort", json={"source": str(source), "dest": str(tmp_path / "out"), "labeler": "claude"}
    )
    assert r.status_code == 400
    assert "Claude Code" in r.json()["error"]


def test_sort_rejects_jev_labeller_without_a_key(client, monkeypatch, tmp_path):
    monkeypatch.setattr("photosorter.api.routes_jobs.find_jev_key", lambda paths: None)
    source = camera_roll(tmp_path / "roll", 2)
    r = client.post("/api/sort", json={"source": str(source), "dest": str(tmp_path / "out"), "labeler": "jev"})
    assert r.status_code == 400
    assert "JEV_KEY" in r.json()["error"]


def test_sort_skips_the_scan_phase_when_source_and_limit_are_unchanged(client, runner, tmp_path):
    source = camera_roll(tmp_path / "roll", 3)
    body = {"source": str(source), "dest": str(tmp_path / "out"), "labeler": "stub"}
    first = client.post("/api/sort", json=body)
    assert first.status_code == 200
    assert first.json()["job"]["phases"] == ["scan", "dupes", "label", "apply"]
    finish(runner)
    assert runner.state().code == 0, runner.state().log

    again = client.post("/api/sort", json=body)
    assert again.status_code == 200
    assert again.json()["job"]["phases"] == ["dupes", "label", "apply"]
    finish(runner)
    assert runner.state().code == 0, runner.state().log


def test_changing_the_limit_forces_a_rescan(client, runner, paths, tmp_path):
    source = camera_roll(tmp_path / "roll", 4)
    body = {"source": str(source), "dest": str(tmp_path / "out"), "labeler": "stub"}
    assert client.post("/api/sort", json=body).status_code == 200
    finish(runner)

    r = client.post("/api/sort", json={**body, "limit": 2})
    assert r.json()["job"]["phases"] == ["scan", "dupes", "label", "apply"]
    finish(runner)
    assert runner.state().code == 0, runner.state().log
    # A different limit is a different random sample, so the inventory on disk is the new one's.
    assert read_json(paths.source_file)["limit"] == 2
    assert client.get("/api/state").json()["files"] == 2


def test_label_phase_failure_is_tolerated_above_ninety_five_percent(client, runner, paths, tmp_path, monkeypatch):
    """Spec 7.2: 96% labelled, so the rest fall through to catch-alls and the sort finishes."""
    monkeypatch.setenv("JEV_KEY", "a-key-for-the-check")
    source = camera_roll(tmp_path / "roll", 25)
    dest = tmp_path / "out"
    # The jev labeller returns one answer per entry in work/jev.json: 24 of 25 files is 96%.
    write_json(paths.jev_file, {str(i): {"key": photo_key(paths), "confidence": 0.9} for i in range(24)})

    r = client.post("/api/sort", json={"source": str(source), "dest": str(dest), "labeler": "jev"})
    assert r.status_code == 200
    finish(runner)
    state = runner.state()
    assert state.code == 0, state.log
    assert "apply" in state.timings, "the job must have reached the apply phase"
    # Carried obligation C1: the destination is recorded, so the dashboard's done view can fire.
    after = client.get("/api/state").json()
    assert after["sorted"] == str(dest)
    assert after["steps"]["apply"] is True
    assert (dest / "sorted.csv").exists()


def test_label_phase_failure_below_ninety_five_percent_fails_the_job(client, runner, paths, tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_KEY", "a-key-for-the-check")
    source = camera_roll(tmp_path / "roll", 25)
    dest = tmp_path / "out"
    write_json(paths.jev_file, {str(i): {"key": photo_key(paths), "confidence": 0.9} for i in range(12)})

    r = client.post("/api/sort", json={"source": str(source), "dest": str(dest), "labeler": "jev"})
    assert r.status_code == 200
    finish(runner)
    state = runner.state()
    assert state.code == 1
    assert "12 of 25" in " ".join(state.log) and "95%" in " ".join(state.log)
    assert "apply" not in state.timings, "nothing may be copied when too little was labelled"
    assert not dest.exists()
    assert client.get("/api/state").json()["sorted"] is None


def test_changing_categories_clears_cached_label_batches(client, runner, paths, tmp_path):
    """Spec 7.2: the fingerprint at work/labels/.categories is what makes cached batches stale."""
    source = camera_roll(tmp_path / "roll", 3)
    body = {"source": str(source), "dest": str(tmp_path / "out"), "labeler": "stub"}
    assert client.post("/api/sort", json=body).status_code == 200
    finish(runner)
    stamped = paths.categories_fingerprint_file.read_text(encoding="utf-8").strip()
    stale = paths.labels / "claude_00.json"
    stale.write_text('{"0": "selfies"}', encoding="utf-8")

    cats = json.loads(paths.categories_file.read_text(encoding="utf-8"))
    cats.insert(0, {"key": "extra", "kind": "photo", "label": "Extra", "emoji": "x", "rule": "a new folder"})
    paths.categories_file.write_text(json.dumps(cats, ensure_ascii=False), encoding="utf-8")

    # Nothing about the photos changed, so only the folder list can clear the batches here.
    assert client.post("/api/sort", json=body).json()["job"]["phases"] == ["dupes", "label", "apply"]
    finish(runner)
    assert runner.state().code == 0, runner.state().log
    assert not stale.exists(), "a changed folder list must clear the cached label batches"
    assert paths.categories_fingerprint_file.read_text(encoding="utf-8").strip() != stamped


def test_starting_a_second_sort_while_one_runs_returns_an_error(client, runner, tmp_path, monkeypatch):
    gate, entered = threading.Event(), threading.Event()
    gated_scan(monkeypatch, gate, entered)
    source = camera_roll(tmp_path / "roll", 2)
    body = {"source": str(source), "dest": str(tmp_path / "out"), "labeler": "stub"}
    assert client.post("/api/sort", json=body).status_code == 200
    assert entered.wait(30)

    second = client.post("/api/sort", json=body)
    assert second.status_code == 400
    assert "running" in second.json()["error"]  # one job at a time, and never a queue
    gate.set()
    finish(runner)
    assert runner.state().code == 0, runner.state().log


def test_state_during_a_running_sort_lets_a_fresh_client_reattach(client, runner, paths, tmp_path, monkeypatch):
    """Review Focus 1: a browser reloaded mid-sort must find the job it left, not start another."""
    gate, entered = threading.Event(), threading.Event()
    gated_scan(monkeypatch, gate, entered)
    source = camera_roll(tmp_path / "roll", 2)
    body = {"source": str(source), "dest": str(tmp_path / "out"), "labeler": "stub"}
    assert client.post("/api/sort", json=body).status_code == 200
    assert entered.wait(30)

    reloaded = TestClient(create_app(paths, runner=runner), base_url="http://127.0.0.1:8765")
    s = reloaded.get("/api/state").json()
    assert s["job"]["running"] is True and s["job"]["step"] == "sort"
    assert s["job"]["phase"] in ("scan", "dupes", "label", "apply")
    assert s["job"]["phases"] == ["scan", "dupes", "label", "apply"]

    gate.set()
    finish(runner)
    # Reading the state neither restarted the job nor broke it: it ran exactly once, to the end.
    assert runner.state().code == 0, runner.state().log
    assert list(runner.state().timings) == ["scan", "dupes", "label", "apply"]


def test_cancel_stops_the_scan_through_its_own_cleanup(client, runner, paths, tmp_path, monkeypatch):
    """The scan is handed the cancel event, not interrupted, so it can tidy up after itself."""
    gate, entered = threading.Event(), threading.Event()
    gated_scan(monkeypatch, gate, entered)
    source = camera_roll(tmp_path / "roll", 3)
    body = {"source": str(source), "dest": str(tmp_path / "out"), "labeler": "stub"}
    assert client.post("/api/sort", json=body).status_code == 200
    assert entered.wait(30)

    assert client.post("/api/cancel").status_code == 200
    gate.set()
    finish(runner)
    state = runner.state()
    assert state.code == 1
    assert "Stopped at your request." in state.log
    assert "dupes" not in state.timings, "no phase may start after a stop"
    # The scan's own cleanup ran: no inventory left pointing at previews it had already wiped.
    assert not paths.inventory_file.exists() and not paths.source_file.exists()


def test_run_does_one_phase_and_names_it_as_the_step(client, runner, paths, tmp_path):
    source = camera_roll(tmp_path / "roll", 2)
    r = client.post("/api/run", json={"step": "scan", "source": str(source)})
    assert r.status_code == 200
    assert r.json()["job"]["step"] == "scan" and r.json()["job"]["phases"] == ["scan"]
    finish(runner)
    state = runner.state()
    assert state.code == 0, state.log
    assert list(state.timings) == ["scan"]
    assert paths.inventory_file.exists()
    assert not paths.dupes_file.exists(), "only the step that was asked for may run"


def test_run_refuses_a_phase_whose_earlier_work_is_missing(client):
    nothing_scanned = client.post("/api/run", json={"step": "dupes"})
    assert nothing_scanned.status_code == 400 and "scan" in nothing_scanned.json()["error"].lower()
    no_folder = client.post("/api/run", json={"step": "scan"})
    assert no_folder.status_code == 400 and "folder" in no_folder.json()["error"].lower()


def test_live_labels_endpoint_merges_claude_batches_and_confident_jev(client, paths):
    paths.labels.mkdir(parents=True, exist_ok=True)
    write_json(paths.labels / "claude_00.json", {"0": "selfies", "1": "food"})
    write_json(paths.labels / "claude_01.json", {"2": "pets"})
    write_json(
        paths.jev_file,
        {
            "1": {"key": "travel", "confidence": 0.9},  # confident, so it beats Claude's answer
            "3": {"key": "home", "confidence": 0.3},  # too unsure to show yet
            "4": {"key": "city", "confidence": 0.7},  # exactly at the bar
            "5": {"confidence": 0.95},  # damaged: no key at all
        },
    )
    assert client.get("/api/labels").json() == {"0": "selfies", "1": "travel", "2": "pets", "4": "city"}


def test_live_labels_endpoint_is_empty_before_anything_is_labelled(client):
    assert client.get("/api/labels").json() == {}


def test_the_routes_say_so_when_there_is_no_runner_behind_them(paths, tmp_path):
    """The app factory allows no runner, and an AttributeError there would be a 500 and a blank page."""
    bare = TestClient(create_app(paths), base_url="http://127.0.0.1:8765")
    r = bare.post("/api/sort", json={"source": str(tmp_path / "roll"), "dest": str(tmp_path / "out")})
    assert r.status_code == 400 and "runner" in r.json()["error"]
    assert bare.post("/api/cancel").status_code == 400
