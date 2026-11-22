"""The contract every labeller meets, so the pipeline never cares which one it is talking to."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Protocol

from photosorter.config import Paths
from photosorter.models import Category, FileRecord, ProgressFn

#: Spec 7.2: below this share of files labelled, the sort stops instead of guessing.
LABEL_TOLERANCE = 0.95


class LabelerUnavailable(Exception):
    """The labeller cannot run at all. The message is shown to the user as written."""


def label_summary(labels: dict[str, str], records: Sequence[FileRecord]) -> str:
    """The one sentence a finished labelling has to say, for stdout or for the job log."""
    return f"{len(labels)} of {len(records)} files have a folder."


def check_label_coverage(labels: dict[str, str], records: Sequence[FileRecord]) -> None:
    """Spec 7.2's orchestration tolerance: a labelling that fell short of it is not a result.

    Above it the files that were missed fall through to the catch-all folders, which is why the gate
    is here and not in a labeller: it is the pipeline's call, and the CLI and the server make it alike.
    """
    if records and len(labels) < LABEL_TOLERANCE * len(records):
        raise ValueError(
            f"Only {len(labels)} of {len(records)} files could be given a folder, and at least "
            f"{int(LABEL_TOLERANCE * 100)}% are needed. Please run the labelling again; finished work is kept."
        )


class Labeler(Protocol):
    name: str

    def label(
        self,
        records: Sequence[FileRecord],
        cats: list[Category],
        paths: Paths,
        on_progress: ProgressFn | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, str]:
        """Return {file id as text: folder key}. Files it could not label are left out."""
        ...
