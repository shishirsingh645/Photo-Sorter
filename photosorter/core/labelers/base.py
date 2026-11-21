"""The contract every labeller meets, so the pipeline never cares which one it is talking to."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Protocol

from photosorter.config import Paths
from photosorter.models import Category, FileRecord, ProgressFn


class LabelerUnavailable(Exception):
    """The labeller cannot run at all. The message is shown to the user as written."""


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
