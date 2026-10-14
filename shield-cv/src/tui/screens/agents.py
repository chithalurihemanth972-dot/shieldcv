"""One live card per contributor agent, then the meeting room's verdict."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from rich.markup import escape
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from src.tui.operations import STAGE_LABELS, OperationSpec, RunOutcome, execute
from src.tui.screens.modals import ConfirmModal
from src.tui.theme import PALETTE, TONE_COLORS
from src.tui.discovery import display_label
from src.tui.verdict import TONE_BY_VERDICT, headline, risk_tone
from src.tui.visuals import banner_text, bar, gradient_text
from src.tui.widgets.sized import Sized
from src.utils.cancel import CancelToken, ScanCancelled
from src.utils.logger import get_logger

LOGGER = get_logger(__name__)


class AgentCard(Static):
    """One contributor agent."""

    def __init__(self, contributor: str, agent_id: str) -> None:
        super().__init__(classes="agent-card")
        self.contributor = contributor
        self.agent_id = agent_id
        self.stage_text = "waiting"
        self.fraction = 0.0
        self.report: Optional[Dict[str, Any]] = None

    def on_mount(self) -> None:
        self._paint()

    def on_resize(self) -> None:
        self._paint()

    def update_stage(self, stage: str, done: int, total: int) -> None:
        self.stage_text = STAGE_LABELS.get(stage, stage)
        self.fraction = done / total if total else 0.0
        self._paint()

    def finish(self, report: Optional[Dict[str, Any]]) -> None:
        self.report = report
        self.stage_text = "finished"
        self.fraction = 1.0
        status = str((report or {}).get("status", "")).upper()
        self.set_class(status == "ERROR", "-error")
        self.set_class(status != "ERROR", "-finished")
        self._paint()

    def _paint(self) -> None:
        width = max(16, (self.size.width or 34) - 4)
        out = Text()
        out.append(f"{self.agent_id}  ", style=f"bold {PALETTE['cyan']}")
        out.append(self.contributor + "\n", style="bold")
        if self.report is None:
            out.append(f"{self.stage_text}\n", style=PALETTE["warn"])
            out.append_text(bar(self.fraction, width, PALETTE["cyan"]))
        else:
            risk = float(self.report.get("risk_score", 0.0) or 0.0)
            verdict = str(self.report.get("verdict", "?")).upper()
            color = TONE_COLORS[TONE_BY_VERDICT.get(verdict, risk_tone(risk))][0]
            out.append(f"{self.report.get('verdict', '?')}  ", style=f"bold {color}")
            out.append(f"{self.report.get('num_findings', 0)} findings · "
                       f"{self.report.get('num_samples', 0)} images\n", style=PALETTE["muted"])
            out.append_text(bar(risk, width - 6, color))
            out.append(f"  {risk:.2f}", style=f"bold {color}")
        self.update(out)


class AgentsScreen(Screen):
    """Live agent board (or a saved one) plus the meeting room."""

    BINDINGS = [Binding("escape", "cancel", "Cancel / home")]

    def __init__(self, spec: OperationSpec, params: Optional[Dict[str, Any]],
                 result: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self.spec = spec
        self.params = params or {}
        self.result = result
        self.token = CancelToken()
        self.status = "finished" if result is not None else "running"
        self.cards: Dict[str, AgentCard] = {}
        self.meeting_text = ""

    @property
    def busy(self) -> bool:
        """Whether agents are still working (not MessagePump.is_running)."""
        return self.status in ("running", "stopping")

    def compose(self) -> ComposeResult:
        head = gradient_text("⚇  CONTRIBUTOR AGENTS", PALETTE["cyan"], PALETTE["violet"])
        raw = self.params.get("target") or (self.result or {}).get("root")
        head.append(f"   {display_label(Path(raw)) if raw else ''}", style=PALETTE["muted"])
        yield Static(head, id="run-header")
        with VerticalScroll():
            yield Grid(id="agent-grid")
            yield Static("", id="run-status")
            with Vertical(id="meeting"):
                yield Sized(lambda w: Text(""), id="meeting-banner")
                yield Static("", id="meeting-text")
        yield Footer()

    def on_mount(self) -> None:
        if self.result is not None:
            self._show_final(self.result)
            return
        self.query_one("#run-status", Static).update("Agents starting…")
        self._discover_cards()
        self._work()

    def _card(self, contributor: str) -> AgentCard:
        if contributor not in self.cards:
            card = AgentCard(contributor, f"AGENT-{len(self.cards) + 1:02d}")
            self.cards[contributor] = card
            self.query_one("#agent-grid", Grid).mount(card)
        return self.cards[contributor]

    def _discover_cards(self) -> None:
        target = self.params.get("target")
        if not target:
            return
        try:
            from src.agents.manager import OfficeManager
            for task in OfficeManager().discover(Path(target)):
                self._card(str(task["contributor"]))
        except Exception as exc:  # cards are also created lazily from progress events
            LOGGER.debug("agent pre-discovery failed: %s", exc)

    @work(thread=True, exclusive=True, group="engine")
    def _work(self) -> None:
        try:
            outcome = execute(self.spec, self.params, self._from_thread, self.token,
                              getattr(self.app, "reports_dir", None))
        except ScanCancelled:
            self._ui(self._cancelled)
        except Exception as exc:
            self._ui(self._failed, f"{type(exc).__name__}: {exc}", traceback.format_exc())
        else:
            self._ui(self._finished, outcome)

    def _ui(self, callback: Any, *args: Any) -> None:
        """Hand a result to the UI thread; a closing app must not fail the worker."""
        try:
            self.app.call_from_thread(callback, *args)
        except Exception as exc:
            LOGGER.debug("agents screen gone before %s: %s", getattr(callback, "__name__", "?"), exc)

    def _from_thread(self, stage: str, done: int, total: int, detail: Optional[str]) -> None:
        self.app.call_from_thread(self._progress, stage, done, total, detail)

    def _progress(self, stage: str, done: int, total: int, detail: Optional[str]) -> None:
        if stage == "meeting":
            self.query_one("#run-status", Static).update("Meeting room: agents compare notes…")
            return
        if not detail:
            return
        card = self._card(detail)
        if stage == "finished":
            card.update_stage("finished", 1, 1)
        else:
            card.update_stage(stage, done, total)
        running = sum(1 for c in self.cards.values() if c.stage_text != "finished")
        self.query_one("#run-status", Static).update(
            f"{len(self.cards)} agents · {running} still working")

    def _finished(self, outcome: RunOutcome) -> None:
        self.result = outcome.result
        if outcome.save_error:
            self.app.notify(f"Report not saved: {outcome.save_error}", severity="error")
        self._show_final(outcome.result)

    def _show_final(self, office: Dict[str, Any]) -> None:
        self.status = "finished"
        for report in office.get("reports") or []:
            self._card(str(report.get("contributor", "?"))).finish(report)
        meeting = office.get("meeting") or {}
        head = headline("agents", office)
        self.query_one("#meeting-banner", Sized).set_draw(
            lambda w: banner_text(head.verdict, head.tone, "office verdict", w))
        lines = [escape(str(meeting.get("narrative", "")))]
        lines += [f"[bold]→ {escape(str(r))}[/bold]" for r in meeting.get("recommendations") or []]
        lines += [f"[red]! {escape(str(e))}[/red]" for e in office.get("errors") or []]
        self.meeting_text = "\n".join(lines)
        self.query_one("#meeting-text", Static).update(self.meeting_text)
        self.query_one("#run-status", Static).update(
            f"{office.get('agents', len(self.cards))} agents · {office.get('mode', '?')} mode · "
            f"{float(office.get('duration_seconds', 0.0)):.1f}s   [dim]Esc home[/dim]")
        self.add_class("-done")

    def _cancelled(self) -> None:
        self.status = "cancelled"
        self.app.notify("Agents cancelled — nothing was saved.")
        self.app.pop_screen()

    def _failed(self, message: str, trace: str) -> None:
        self.status = "failed"
        LOGGER.error("agents run failed: %s\n%s", message, trace)
        self.query_one("#run-status", Static).update(
            f"[bold red]Agents stopped with an error:[/bold red] {escape(message)}   "
            f"[dim]Esc back[/dim]")

    def action_cancel(self) -> None:
        if self.status == "running":
            self.app.push_screen(ConfirmModal("Stop all agents? Partial results are discarded."),
                                 self._confirm)
        elif self.status == "finished":
            self.app.go_home()
        elif self.status in ("failed", "cancelled"):
            self.app.pop_screen()

    def _confirm(self, stop: Optional[bool]) -> None:
        if stop and self.status == "running":
            self.status = "stopping"
            self.query_one("#run-status", Static).update("Stopping at the next checkpoint…")
            self.token.cancel()
