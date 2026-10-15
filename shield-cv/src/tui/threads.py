"""Background work on daemon threads.

Textual's thread workers and ``asyncio.to_thread`` run in asyncio's default
executor, which ``asyncio.run`` joins on exit: quitting would hang until a long
scan or a disk walk finished. Daemon threads let the process leave at once
(a cancelled engine is stopped by its ``CancelToken`` anyway).
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
from typing import Any, Callable

from src.utils.logger import get_logger

LOGGER = get_logger(__name__)


def start_daemon(fn: Callable[..., Any], *args: Any, name: str = "shield-bg") -> threading.Thread:
    """Run ``fn(*args)`` on a daemon thread that keeps Textual's context (``self.app``)."""
    context = contextvars.copy_context()
    thread = threading.Thread(target=context.run, args=(fn, *args), name=name, daemon=True)
    thread.start()
    return thread


def deliver(app: Any, callback: Callable[..., Any], *args: Any) -> None:
    """Hand a result to the UI thread; a closing app must not fail the worker."""
    if not getattr(app, "is_running", True):  # Textual's own flag: app already exited
        return
    try:
        app.call_from_thread(callback, *args)
    except Exception as exc:
        LOGGER.debug("UI gone before %s: %s", getattr(callback, "__name__", "?"), exc)


async def run_daemon(fn: Callable[..., Any], *args: Any) -> Any:
    """``await`` the result of ``fn(*args)`` computed on a daemon thread."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()

    def settle(value: Any, error: BaseException | None) -> None:
        if not future.done():
            if error is not None:
                future.set_exception(error)
            else:
                future.set_result(value)

    def work() -> None:
        try:
            value = fn(*args)
        except BaseException as exc:  # handed to the awaiting coroutine
            loop.call_soon_threadsafe(settle, None, exc)
        else:
            loop.call_soon_threadsafe(settle, value, None)

    start_daemon(work)
    return await future
