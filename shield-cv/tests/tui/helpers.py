"""Helpers for driving Textual apps from plain (non-async) pytest tests."""
from __future__ import annotations

import asyncio
import functools
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo"


def async_test(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Run an ``async def`` test with ``asyncio.run`` (no pytest-asyncio needed)."""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(fn(*args, **kwargs))
    return wrapper


async def wait_for(pilot: Any, predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    """Pump the app until ``predicate()`` is true, or fail after ``timeout`` seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await pilot.pause(0.05)
        if predicate():
            return
    raise AssertionError("condition not met within %.1fs" % timeout)
