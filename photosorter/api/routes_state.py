"""GET /api/state: everything the page needs to draw itself, and its fallback when the live stream drops."""

from __future__ import annotations

import platform as _platform

from fastapi import APIRouter, Request

from photosorter.api.schemas import AppState, CategoryOut, JobState, StepFlags
from photosorter.config import Paths, read_json
from photosorter.core.categories import load_categories
from photosorter.core.labelers import find_jev_key
from photosorter.picker import picker_available
from photosorter.platform import file_manager_name, find_claude

router = APIRouter()


def build_state(paths: Paths, runner) -> AppState:
    # The slim index (id, kind, bytes), never the full inventory, which is ~40MB at 100k files.
    slim = read_json(paths.slim_file, [])
    source = read_json(paths.source_file, {})
    source = source if isinstance(source, dict) else {}
    overrides = read_json(paths.overrides_file, {})
    available, reason = picker_available()
    try:
        cats = load_categories(paths)
    except FileNotFoundError:
        cats = []
    return AppState(
        categories=[CategoryOut(**c.to_dict()) for c in cats],
        source=source.get("path"),
        limit=source.get("limit"),
        sorted=source.get("sorted"),
        files=len(slim),
        bytes=sum(r.get("bytes", 0) for r in slim),
        steps=StepFlags(
            scan=paths.inventory_file.exists() and paths.source_file.exists(),
            dupes=paths.dupes_file.exists(),
            label=paths.labels_file.exists(),
            jev_labels=paths.jev_file.exists(),
            apply=bool(source.get("sorted")),
        ),
        jev_key=find_jev_key(paths) is not None,
        claude_cli=find_claude() is not None,
        overrides=len(overrides) if isinstance(overrides, dict) else 0,
        job=runner.state() if runner is not None else JobState(),
        platform=_platform.system().lower(),
        file_manager=file_manager_name(),
        picker_available=available,
        picker_reason=reason,
    )


@router.get("/api/state", response_model=AppState)
def get_state(request: Request) -> AppState:
    return build_state(request.app.state.paths, request.app.state.runner)
