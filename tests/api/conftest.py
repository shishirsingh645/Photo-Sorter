"""An app over a throwaway root that holds the repo's real categories.json."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photosorter.api.app import create_app
from photosorter.config import Paths


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    root = tmp_path / "approot"
    root.mkdir()
    shutil.copy(Paths.default().categories_file, root / "categories.json")
    return Paths(root=root)


@pytest.fixture
def client(paths: Paths) -> TestClient:
    return TestClient(create_app(paths))
