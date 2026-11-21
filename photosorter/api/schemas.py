"""Every shape the server sends. Defined in full here so no later route has to edit this file."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StepFlags(BaseModel):
    scan: bool = False
    dupes: bool = False
    label: bool = False
    jev_labels: bool = False
    apply: bool = False


class JobState(BaseModel):
    """The one job the runner may be running. All defaults mean "idle"."""

    step: str | None = None
    running: bool = False
    code: int | None = None
    phase: str | None = None
    phases: list[str] = Field(default_factory=list)
    done: int = 0
    total: int = 0
    started: float | None = None
    phase_started: float | None = None
    timings: dict[str, float] = Field(default_factory=dict)
    log: list[str] = Field(default_factory=list)


class CategoryOut(BaseModel):
    key: str
    kind: str
    label: str
    emoji: str
    rule: str


class AppState(BaseModel):
    categories: list[CategoryOut]
    source: str | None = None
    limit: int | None = None
    sorted: str | None = None
    files: int = 0
    bytes: int = 0
    steps: StepFlags
    jev_key: bool
    claude_cli: bool
    overrides: int = 0
    job: JobState
    platform: str
    file_manager: str
    picker_available: bool
    picker_reason: str = ""
