"""Live run: real stage progress, Esc to cancel, error panel with retry."""

from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from rich.markup import escape
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Static

from src.tui.discovery import display_label
from src.tui.operations import STAGE_LABELS, OperationSpec, RunOutcome, execute
from src.tui.screens.modals import ConfirmModal
from src.tui.theme import PALETTE
from src.tui.visuals import gradient_text
from src.tui.widgets.stage_progress import StageProgress
from src.utils.cancel import CancelToken, ScanCancelled
from src.utils.logger import get_logger

LOGGER = get_logger(__name__)


def stage_eta(done: int, total: int, stage_elapsed: float) -> Optional[float]:
    """Seconds left in the current stage, from its own pace (``None`` if unknown)."""
    if total <= 1 or done <= 0 or done >= total or stage_elapsed <= 0:
        return None
    return (total - done) * stage_elapsed / done


class RunScreen(Screen):
    """Runs one operation in a thread worker and shows what it is really doing."""

    BINDINGS = [Binding("escape", "cancel", "Cancel / back"),
                Binding("r", "retry", "Retry", show=False),
                Binding("b", "back", "Back", show=False),
                Binding("t", "toggle_trace", "Traceback", show=False)]

    def __init__(self, spec: OperationSpec, params: Dict[str, Any]) -> None:
        super().__init__()
        self.spec = spec
        self.params = params
        self.token = CancelToken()
        self.status = "running"
        self.error_text = ""
        self._started = time.monotonic()
        self._stage_started = self._started
        self._last: Optional[tuple] = None

    @property
    def busy(self) -> bool:
        return self.status in ("running", "stopping")

    def compose(self) -> ComposeResult:
        raw = self.params.get("target")
        target = display_label(Path(raw)) if raw else "all selected modules"
        head = gradient_text(f"{self.spec.icon}  {self.spec.title.upper()}",
                             PALETTE["cyan"], PALETTE["violet"])
        head.append(f"   {target}", style=PALETTE["muted"])
        yield Static(head, id="run-header")
        yield StageProgress(self.spec.stages)
        yield Static("", id="run-status")
        with Vertical(id="run-error"):
            yield Static("", id="run-error-text")
            yield Static("", id="run-trace")
        yield RichLog(id="run-log", markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.25, self._tick)
        self._start()

    # -- worker ------------------------------------------------------------
    def _start(self) -> None:
        self.token = CancelToken()
        self.status = "running"
        self._started = time.monotonic()
        self.remove_class("-failed")
        self.remove_class("-trace")
        self.query_one(RichLog).write(f"[dim]{time.strftime('%H:%M:%S')}[/dim]  started")
        self._work()

    @work(thread=True, exclusive=True, group="engine")
    def _work(self) -> None:
        try:
            outcome = execute(self.spec, self.params, self._progress_from_thread, self.token,
                              getattr(self.app, "reports_dir", None))
        except ScanCancelled:
            self._ui(self._cancelled)
        except Exception as exc:  # shown in the error panel, never crashes the app
            self._ui(self._failed, exc, traceback.format_exc())
        else:
            self._ui(self._finished, outcome)

    def _ui(self, callback: Any, *args: Any) -> None:
        """Hand a result to the UI thread; a closing app must not fail the worker."""
        try:
            self.app.call_from_thread(callback, *args)
        except Exception as exc:
            LOGGER.debug("run screen gone before %s: %s", getattr(callback, "__name__", "?"), exc)

    def _progress_from_thread(self, stage: str, done: int, total: int,
                              detail: Optional[str]) -> None:
        self.app.call_from_thread(self._progress, stage, done, total, detail)

    # -- UI updates (main thread) -------------------------------------------
    def _progress(self, stage: str, done: int, total: int, detail: Optional[str]) -> None:
        self.query_one(StageProgress).update_stage(stage, done, total, detail)
        if self._last is None or self._last[0] != stage:
            self._stage_started = time.monotonic()
            label = STAGE_LABELS.get(stage, stage)
            self.query_one(RichLog).write(
                f"[dim]{time.strftime('%H:%M:%S')}[/dim]  {escape(label)}"
                + (f" [dim]· {escape(detail)}[/dim]" if detail else ""))
        self._last = (stage, done, total, time.monotonic())

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started
        text = {"running": f"Elapsed {elapsed:5.1f}s",
                "stopping": "Stopping at the next checkpoint…",
                "failed": "Stopped with an error — r retry · b back · t traceback",
                "cancelled": "Cancelled.", "finished": "Done."}[self.status]
        if self.status == "running" and self._last:
            _, done, total, _ = self._last
            left = stage_eta(done, total, time.monotonic() - self._stage_started)
            if left is not None:
                text += f"   ≈ {left:.0f}s left in this stage"
        self.query_one("#run-status", Static).update(text)

    def _finished(self, outcome: RunOutcome) -> None:
        self.status = "finished"
        self.query_one(StageProgress).finish(ok=True)
        if outcome.save_error:
            self.app.notify(f"Report not saved: {outcome.save_error}", severity="error",
                            timeout=8)
        self.app.show_result(self.spec.id, outcome.result, outcome.report_path,
                             outcome.elapsed, replace=True)

    def _cancelled(self) -> None:
        self.status = "cancelled"
        self.query_one(StageProgress).finish(ok=False)
        self.app.notify("Check cancelled — nothing was saved.")
        self.app.pop_screen()

    def _failed(self, exc: Exception, trace: str) -> None:
        self.status = "failed"
        self.error_text = f"{type(exc).__name__}: {exc}"
        self.query_one(StageProgress).finish(ok=False)
        self.query_one("#run-error-text", Static).update(
            f"[bold red]The check stopped with an error. Nothing was saved.[/bold red]\n"
            f"{escape(self.error_text)}\n"
            f"[dim]r retry · b back · t show traceback[/dim]")
        self.query_one("#run-trace", Static).update(escape(trace))
        self.add_class("-failed")

    # -- actions -----------------------------------------------------------
    def action_cancel(self) -> None:
        if self.status == "running":
            self.app.push_screen(ConfirmModal("Stop this check? Partial results are discarded."),
                                 self._confirm_cancel)
        elif self.status in ("failed", "cancelled"):
            self.action_back()

    def _confirm_cancel(self, stop: Optional[bool]) -> None:
        if stop and self.status == "running":
            self.status = "stopping"
            self.token.cancel()

    def action_retry(self) -> None:
        if self.status == "failed":
            self.query_one(StageProgress).reset()
            self._last = None
            self._start()

    def action_back(self) -> None:
        if not self.busy:
            self.app.pop_screen()

    def action_toggle_trace(self) -> None:
        if self.status == "failed":
            self.toggle_class("-trace")
