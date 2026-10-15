"""Shared pytest setup for the SHIELD Console tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, Path(__file__).resolve().parent):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))


import pytest as _pytest


@_pytest.fixture(autouse=True)
def _quarantine_folder(tmp_path, monkeypatch):
    """Every test gets its own quarantine folder, outside the dataset."""
    monkeypatch.setenv("SHIELD_QUARANTINE_DIR", str(tmp_path / "quarantine_root"))
