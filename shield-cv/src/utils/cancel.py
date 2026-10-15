"""Cooperative cancellation for long-running engine calls.

The UI cannot kill a worker thread, so it asks the engine to stop: the progress
callback raises :class:`ScanCancelled` once a :class:`CancelToken` is set, and
the run unwinds at its next progress tick.
"""

from __future__ import annotations

import threading


class ScanCancelled(BaseException):
    """Raised from a progress callback to stop an engine run.

    Derives from ``BaseException`` on purpose: every engine guards its progress
    callback and its main body with ``except Exception``, which would swallow an
    ordinary exception and let the run carry on.
    """


class CancelToken:
    """Thread-safe cancel flag shared by the UI thread and an engine worker."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation; the run stops at its next progress tick."""
        self._event.set()

    @property
    def cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        return self._event.is_set()

    def check(self) -> None:
        """Raise :class:`ScanCancelled` if cancellation has been requested."""
        if self._event.is_set():
            raise ScanCancelled()
