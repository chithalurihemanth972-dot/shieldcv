"""Shared setup for the review tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest as _pytest


@_pytest.fixture(autouse=True)
def _quarantine_folder(tmp_path, monkeypatch):
    """Every test gets its own quarantine folder, outside the dataset."""
    monkeypatch.setenv("SHIELD_QUARANTINE_DIR", str(tmp_path / "quarantine_root"))
