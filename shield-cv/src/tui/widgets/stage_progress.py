"""One live row per engine stage."""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import ProgressBar, Static

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
ICONS = {"pending": "[dim]·[/dim]", "done": "[green]✓[/green]", "skipped": "[dim]–[/dim]",
         "failed": "[red]✗[/red]"}


class StageProgress(Vertical):
    """Stages turn running → done in order; unreported ones end as skipped."""

    def __init__(self, stages: Sequence[Tuple[str, str]]) -> None:
        super().__init__()
        self.stages = list(stages)
        self._states: Dict[str, str] = {sid: "pending" for sid, _ in self.stages}
        self._frame = 0

    def compose(self) -> ComposeResult:
        for sid, label in self.stages:
            with Horizontal(classes="stage-row -pending", id=f"stage-{sid}"):
                yield Static(ICONS["pending"], classes="stage-icon")
                yield Static(label, classes="stage-label")
                yield ProgressBar(total=None, show_eta=False, show_percentage=True)
                yield Static("", classes="stage-detail")

    def on_mount(self) -> None:
        self.set_interval(0.1, self._spin)

    def state(self, stage: str) -> str:
        return self._states.get(stage, "unknown")

    def _row(self, stage: str) -> Horizontal:
        return self.query_one(f"#stage-{stage}", Horizontal)

    def _set_state(self, stage: str, state: str) -> None:
        self._states[stage] = state
        row = self._row(stage)
        row.set_class(state in ("pending", "skipped"), "-pending")
        if state in ICONS:
            row.query_one(".stage-icon", Static).update(ICONS[state])
        bar = row.query_one(ProgressBar)
        if state == "done":
            bar.update(total=bar.total or 1, progress=bar.total or 1)

    def update_stage(self, stage: str, done: int, total: int,
                     detail: Optional[str] = None) -> bool:
        """Advance to ``stage``; returns ``False`` for stages this run does not track."""
        if stage not in self._states:
            return False
        order = [sid for sid, _ in self.stages]
        for earlier in order[:order.index(stage)]:
            if self._states[earlier] in ("pending", "running"):
                self._set_state(earlier, "done" if self._states[earlier] == "running" else "skipped")
        row = self._row(stage)
        self._states[stage] = "running"
        row.remove_class("-pending")
        if total > 0:
            row.query_one(ProgressBar).update(total=total, progress=min(done, total))
        if detail:
            row.query_one(".stage-detail", Static).update(detail)
        if total > 0 and done >= total:
            self._set_state(stage, "done")
        return True

    def reset(self) -> None:
        """Back to all-pending, for a retry."""
        for sid, _ in self.stages:
            self._states[sid] = "pending"
            row = self._row(sid)
            row.add_class("-pending")
            row.query_one(".stage-icon", Static).update(ICONS["pending"])
            row.query_one(ProgressBar).update(total=None, progress=0)
            row.query_one(".stage-detail", Static).update("")

    def finish(self, ok: bool) -> None:
        """Close out every row at the end of a run."""
        for sid, state in list(self._states.items()):
            if state == "running":
                self._set_state(sid, "done" if ok else "failed")
            elif state == "pending":
                self._set_state(sid, "skipped")

    def _spin(self) -> None:
        self._frame = (self._frame + 1) % len(SPINNER)
        for sid, state in self._states.items():
            if state == "running":
                self._row(sid).query_one(".stage-icon", Static).update(
                    f"[cyan]{SPINNER[self._frame]}[/cyan]")
