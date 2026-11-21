"""Labels files by running the user's own Claude Code CLI on contact sheets: no API key, their plan pays.

Finished batches are cached as work/labels/claude_NN.json, so a run of 100k files can be stopped
and resumed across days without paying for the same batch twice.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from photosorter.config import Paths, read_json, write_json
from photosorter.core.labelers.base import LabelerUnavailable
from photosorter.core.sheets import build_sheets, ids_in_sheet_range
from photosorter.models import Category, FileRecord, ProgressFn
from photosorter.platform import find_claude

ACCEPT_RATIO = 0.9
ATTEMPTS = 4
TIMEOUT_SECONDS = 900
#: Seconds between progress events; the final one is always sent.
PROGRESS_INTERVAL = 0.5
#: Batches failing in a row for the same reason mean sign-in or quota, not a bad batch. Three costs about
#: 12 doomed calls and 2.5 minutes of waiting, yet one or two unlucky batches never trip it.
BREAKER_STREAK = 3


def _env_int(name: str, fallback: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise LabelerUnavailable(f"The setting {name} must be a whole number of 1 or more, but it is {raw!r}.")
    return value


def build_prompt(cats: list[Category], sheet_paths: Sequence[Path]) -> str:
    folders = "\n".join(f"{c.key} ({c.kind}): {c.rule}" for c in cats)
    sheets = "\n".join(str(p) for p in sheet_paths)
    return (
        "You are sorting a person's photos and videos into folders.\n"
        "Use the Read tool to look at each contact sheet image below. Every tile has a number printed on it. "
        "Tiles marked VIDEO are videos; all others are photos.\n\n"
        f"Contact sheets:\n{sheets}\n\n"
        f"Folders, as key (kind): rule:\n{folders}\n\n"
        "Put every photo in a photo folder and every video in a video folder. If nothing fits, use the last "
        "folder of that kind.\n"
        'Reply with ONE JSON object only, mapping each tile number to a folder key, like {"12": "food"}. '
        "Include every tile. No other text."
    )


def parse_label_response(stdout: str, wanted: list[str]) -> dict[str, str]:
    """The first JSON object in the model's answer, keeping only ids we asked about."""
    text = stdout
    try:
        envelope = json.loads(stdout)
        if isinstance(envelope, dict) and isinstance(envelope.get("result"), str):
            text = envelope["result"]
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    keep = set(wanted)
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text, start)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            return {str(k): v for k, v in obj.items() if str(k) in keep and isinstance(v, str)}
        start = text.find("{", start + 1)
    return {}


class ClaudeLabeler:
    name = "claude"

    def __init__(self, model: str | None = None, workers: int | None = None, sheets_per_batch: int = 3):
        # Precedence: explicit argument, then environment variable, then default.
        self.model = model or os.environ.get("CLAUDE_MODEL") or "sonnet"
        self.workers = workers if workers is not None else _env_int("CLAUDE_WORKERS", 4)
        self.sheets_per_batch = sheets_per_batch

    def label(
        self,
        records: Sequence[FileRecord],
        cats: list[Category],
        paths: Paths,
        on_progress: ProgressFn | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, str]:
        claude = find_claude()
        if claude is None:
            raise LabelerUnavailable(
                "Claude Code is not installed, or this app cannot find it. Install Claude Code, sign in "
                "once by running 'claude' in a terminal, then try again."
            )
        sheets = build_sheets(records, paths)
        size = self.sheets_per_batch
        batches = [(n, sheets[n * size : (n + 1) * size]) for n in range(-(-len(sheets) // size))]
        total, done, last_emit = len(records), 0, 0.0
        lock = threading.Lock()
        labels: dict[str, str] = {}
        streak: list = [None, 0]  # [reason kind, consecutive batches that failed with it]
        tripped: list[str] = []

        def run(batch: tuple[int, list[Path]]) -> None:
            nonlocal done, last_emit
            n, batch_sheets = batch
            wanted = ids_in_sheet_range(records, n * size, n * size + len(batch_sheets) - 1)
            if tripped:
                return
            got, failure = self._run_batch(claude, n, batch_sheets, wanted, cats, paths, cancel)
            with lock:
                labels.update(got)
                if failure is None:
                    streak[:] = [None, 0]
                else:
                    kind, reason = failure
                    streak[:] = [kind, streak[1] + 1 if streak[0] == kind else 1]
                    if streak[1] >= BREAKER_STREAK and not tripped:
                        tripped.append(reason)
                done += len(wanted)
                now = time.monotonic()
                if on_progress and done < total and now - last_emit >= PROGRESS_INTERVAL:
                    last_emit = now
                    on_progress(done, total)

        with ThreadPoolExecutor(self.workers) as pool:
            list(pool.map(run, batches))
        if tripped:
            raise LabelerUnavailable(
                f"Claude Code failed on {BREAKER_STREAK} batches in a row, so labelling was stopped to save your "
                f"plan's usage. The last problem was: {tripped[0]} Check that you are signed in (run 'claude' in "
                "a terminal) and that your plan has usage left, then run again. Finished work is kept."
            )
        if on_progress:
            on_progress(done, total)
        return labels

    def _run_batch(self, claude, n, batch_sheets, wanted, cats, paths, cancel):
        """Returns (labels, failure); failure is None on success or cancel, else (kind, reason)."""
        cache = paths.labels / f"claude_{n:02d}.json"
        failed = paths.work / f"claude_failed_{n:02d}.txt"
        keep = set(wanted)
        try:
            cached = read_json(cache)
        except (ValueError, OSError):  # killed mid-write: treat as not cached
            cached = None
        if isinstance(cached, dict):
            cached = {k: v for k, v in cached.items() if k in keep}
            if len(cached) * 10 >= 9 * len(wanted):
                return cached, None
        prompt = build_prompt(cats, batch_sheets)
        kind = reason = ""
        for attempt in range(1, ATTEMPTS + 1):
            if cancel is not None and cancel.is_set():
                return {}, None
            try:
                proc = subprocess.run(
                    [claude, "-p", prompt, "--model", self.model, "--allowedTools", "Read", "--strict-mcp-config",
                     "--setting-sources", "project", "--no-session-persistence", "--output-format", "json"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=paths.work,
                    timeout=TIMEOUT_SECONDS,
                )  # fmt: skip
            except subprocess.TimeoutExpired:
                kind, reason = "timeout", "Claude Code took too long to answer."
            except OSError as e:
                kind, reason = "start", f"Claude Code could not be started: {e}"
            else:
                got = parse_label_response(proc.stdout, wanted)
                if proc.returncode != 0:
                    kind, reason = "error", f"Claude Code stopped with an error: {(proc.stderr or '').strip()[:500]}"
                elif len(got) * 10 < 9 * len(wanted):
                    kind = "coverage"
                    reason = f"Claude labelled {len(got)} of {len(wanted)} files; at least 90% are needed."
                else:
                    try:
                        tmp = cache.with_name(cache.name + ".tmp")
                        write_json(tmp, got)
                        os.replace(tmp, cache)  # atomic: a kill never leaves a half-written cache
                    except OSError as e:
                        kind, reason = "save", f"The results could not be saved in the work folder: {e}"
                    else:
                        failed.unlink(missing_ok=True)
                        return got, None
            paths.work.mkdir(parents=True, exist_ok=True)
            failed.write_text(f"Attempt {attempt} of {ATTEMPTS} failed.\n{reason}\n", encoding="utf-8")
            if attempt < ATTEMPTS:
                time.sleep(8 * attempt)
        return {}, (kind, reason)
