"""The three labellers on offer, and the one place that picks between them by name.

Here rather than in the CLI because the server offers the same three over HTTP: the table of what
`--labeler` and `{"labeler": ...}` may say has to be one table, or the two interfaces drift.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence

from photosorter.config import Paths, read_json
from photosorter.core.labelers.base import Labeler, LabelerUnavailable
from photosorter.core.labelers.claude import ClaudeLabeler
from photosorter.models import Category, FileRecord, ProgressFn

#: Every name `make_labeler` answers to, in the order the CLI's help lists them.
LABELER_NAMES = ("claude", "jev", "stub")


class StubLabeler:
    """Gives every file the first folder of its kind. Exists so a test run needs no Claude CLI and no key."""

    name = "stub"

    def label(
        self,
        records: Sequence[FileRecord],
        cats: list[Category],
        paths: Paths,
        on_progress: ProgressFn | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, str]:
        first = {kind: next((c.key for c in cats if c.kind == kind), None) for kind in ("photo", "video")}
        if on_progress:
            on_progress(len(records), len(records))
        return {str(r.id): first[r.kind] for r in records if first[r.kind] is not None}


class JevLabeler:
    """Reads answers a local classifier already left in work/jev.json. It does not run one."""

    name = "jev"

    def label(
        self,
        records: Sequence[FileRecord],
        cats: list[Category],
        paths: Paths,
        on_progress: ProgressFn | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, str]:
        answers = read_json(paths.jev_file)
        if not isinstance(answers, dict):
            raise LabelerUnavailable(
                f"There are no answers to read at {paths.jev_file}. Run the labelling with "
                "--labeler claude, or put the answers in that file first."
            )
        if on_progress:
            on_progress(len(records), len(records))
        return {
            str(k): v["key"] for k, v in answers.items() if isinstance(v, dict) and isinstance(v.get("key"), str)
        }


def make_labeler(name: str) -> Labeler:
    """The labeller that answers to `name`. Anything unrecognised is Claude, as the CLI's default is."""
    if name == "stub":
        return StubLabeler()
    if name == "jev":
        return JevLabeler()
    return ClaudeLabeler()
