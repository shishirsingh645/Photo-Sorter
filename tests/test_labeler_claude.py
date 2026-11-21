import json
import re
import subprocess
import threading
from pathlib import Path

import pytest

from photosorter.config import Paths, read_json
from photosorter.core.labelers import claude as mod
from photosorter.core.labelers.base import LabelerUnavailable
from photosorter.core.labelers.claude import ClaudeLabeler, build_prompt, parse_label_response
from photosorter.core.sheets import ids_in_sheet_range
from photosorter.models import Category, FileRecord

CATS = [
    Category("food", "photo", "Food", "x", "meals, snacks"),
    Category("misc", "photo", "Misc", "x", "anything else"),
    Category("clips", "video", "Clips", "x", "any video"),
]


def rec(i):
    return FileRecord(
        id=i, path=Path(f"/o/{i}.jpg"), name=f"{i}.jpg", ext=".jpg", kind="photo", bytes=1, sha256="0" * 64
    )


@pytest.fixture
def paths(tmp_path):
    return Paths(root=tmp_path / "app")


@pytest.fixture
def recs():
    return [rec(i) for i in range(180)]  # 6 sheets -> 2 batches


class Stub:
    """Stands in for subprocess.run. `answer(wanted_ids, attempt_for_batch)` returns the labelled ids."""

    def __init__(self, recs, answer=None):
        self.recs, self.calls, self.cmds = recs, 0, []
        self.answer = answer or (lambda wanted, n: wanted)
        self.per_batch = {}
        self.lock = threading.Lock()

    def __call__(self, cmd, **kw):
        with self.lock:
            self.calls += 1
            self.cmds.append((cmd, kw))
        sheets = sorted(int(n) for n in re.findall(r"sheet_(\d+)\.jpg", cmd[2]))
        wanted = ids_in_sheet_range(self.recs, sheets[0], sheets[-1])
        with self.lock:
            n = self.per_batch[sheets[0]] = self.per_batch.get(sheets[0], 0) + 1
        labelled = self.answer(wanted, n)
        text = json.dumps({i: "food" for i in labelled}, ensure_ascii=False)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"result": text}, ensure_ascii=False), stderr="")


@pytest.fixture
def stub(monkeypatch, recs, paths):
    s = Stub(recs)
    monkeypatch.setattr(mod.subprocess, "run", s)
    monkeypatch.setattr(mod, "find_claude", lambda: "claude")
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        mod, "build_sheets", lambda r, p: [p.sheets / f"sheet_{i:05d}.jpg" for i in range(-(-len(r) // 30))]
    )
    return s


def test_prompt_lists_every_folder_as_key_kind_rule():
    p = build_prompt(CATS, [Path("sheet_00.jpg")])
    assert "food (photo): meals, snacks" in p
    assert "clips (video): any video" in p
    assert "sheet_00.jpg" in p


def test_parse_extracts_first_json_object_and_drops_foreign_ids():
    out = '{"result": "Sure! {\\"1\\": \\"food\\", \\"99\\": \\"pets\\"} done"}'
    assert parse_label_response(out, ["1", "2"]) == {"1": "food"}


def test_parse_returns_empty_dict_on_unparseable_output():
    assert parse_label_response("I could not read those images", ["1"]) == {}


def test_cli_invocation_is_exact(stub, recs, paths):
    ClaudeLabeler().label(recs, CATS, paths)
    cmd, kw = stub.cmds[0]
    assert cmd[0] == "claude" and cmd[1] == "-p"
    assert cmd[3:] == [
        "--model", "sonnet", "--allowedTools", "Read", "--strict-mcp-config",
        "--setting-sources", "project", "--no-session-persistence", "--output-format", "json",
    ]  # fmt: skip
    assert kw["cwd"] == paths.work and kw["timeout"] == 900


def test_batch_accepted_at_ninety_percent_coverage(stub, recs, paths):
    stub.answer = lambda wanted, n: wanted[:81]  # exactly 90% of 90
    out = ClaudeLabeler().label(recs, CATS, paths)
    assert stub.calls == 2 and len(out) == 162
    assert (paths.labels / "claude_00.json").exists()


def test_batch_below_ninety_percent_triggers_retry(stub, recs, paths):
    stub.answer = lambda wanted, n: wanted[:80] if n == 1 else wanted
    out = ClaudeLabeler().label(recs, CATS, paths)
    assert stub.calls == 4 and len(out) == 180  # each of 2 batches took 2 attempts


def test_batch_fails_after_four_attempts_with_reason(stub, recs, paths):
    stub.answer = lambda wanted, n: [] if wanted[0] == "0" else wanted
    out = ClaudeLabeler().label(recs, CATS, paths)
    assert stub.per_batch[0] == 4
    assert not (paths.labels / "claude_00.json").exists()
    assert "0 of 90" in (paths.work / "claude_failed_00.txt").read_text(encoding="utf-8")
    assert set(out) == {str(i) for i in range(90, 180)}  # the good batch is kept


def test_backoff_is_eight_times_attempt(stub, recs, paths, monkeypatch):
    sleeps = []
    monkeypatch.setattr(mod.time, "sleep", sleeps.append)
    stub.answer = lambda wanted, n: []
    ClaudeLabeler(workers=1).label(recs, CATS, paths)
    assert sorted(set(sleeps)) == [8, 16, 24]  # none after the final attempt


def test_cli_error_is_a_failed_attempt_with_reason(monkeypatch, stub, recs, paths):
    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 900)

    monkeypatch.setattr(mod.subprocess, "run", boom)
    assert ClaudeLabeler().label(recs, CATS, paths) == {}
    assert "too long" in (paths.work / "claude_failed_00.txt").read_text(encoding="utf-8")


def test_finished_batches_are_cached_and_skipped_on_rerun(stub, recs, paths):
    labeler = ClaudeLabeler()
    first = labeler.label(recs, CATS, paths)
    calls_before = stub.calls
    second = labeler.label(recs, CATS, paths)
    assert stub.calls == calls_before and second == first


def test_cache_file_keeps_unicode_readable(stub, recs, paths):
    stub.answer = lambda wanted, n: wanted
    ClaudeLabeler().label(recs, CATS, paths)
    assert read_json(paths.labels / "claude_00.json")["0"] == "food"


def test_missing_claude_cli_raises_labeler_unavailable_in_plain_words(monkeypatch, recs, paths):
    monkeypatch.setattr(mod, "find_claude", lambda: None)
    with pytest.raises(LabelerUnavailable, match="Claude Code"):
        ClaudeLabeler().label(recs, CATS, paths)


def test_cancel_event_stops_dispatching_new_batches(stub, recs, paths):
    cancel = threading.Event()
    cancel.set()
    assert ClaudeLabeler().label(recs, CATS, paths, cancel=cancel) == {}
    assert stub.calls == 0


def test_progress_is_throttled_and_ends_with_a_final_event(stub, paths):
    recs = [rec(i) for i in range(900)]  # 10 batches
    stub.recs = recs
    events = []
    ClaudeLabeler().label(recs, CATS, paths, on_progress=lambda d, t: events.append((d, t)))
    assert events[-1] == (900, 900) and len(events) < 10


def test_env_overrides_workers_and_model(monkeypatch):
    monkeypatch.setenv("CLAUDE_WORKERS", "2")
    monkeypatch.setenv("CLAUDE_MODEL", "opus")
    lab = ClaudeLabeler()
    assert (lab.workers, lab.model) == (2, "opus")
