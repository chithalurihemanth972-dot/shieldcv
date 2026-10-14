"""Findings table and the detail pane beside it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from rich.console import Group
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Static

from src.tui.theme import SEVERITY_COLORS, SEVERITY_ORDER
from src.tui.widgets.image_preview import ImagePreview

_RANK = {sev: i for i, sev in enumerate(SEVERITY_ORDER)}


def sort_key(finding: Dict[str, Any]) -> tuple:
    """Most severe first, then most confident."""
    return (_RANK.get(str(finding.get("severity", "")).upper(), 99),
            -float(finding.get("confidence", 0.0) or 0.0))


class FindingsTable(DataTable):
    """Sortable, filterable list of findings."""

    class Focused(Message):
        """A finding is highlighted."""

        def __init__(self, finding: Optional[Dict[str, Any]]) -> None:
            self.finding = finding
            super().__init__()

    def __init__(self, findings: Sequence[Dict[str, Any]] = ()) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True)
        self._initial = list(findings)
        self._all: List[Dict[str, Any]] = []
        self._rows: List[Dict[str, Any]] = []

    def on_mount(self) -> None:
        # Load here, not from the screen: inside TabbedContent the screen's
        # on_mount can run before this table exists.
        self.load(self._initial)

    def load(self, findings: Sequence[Dict[str, Any]]) -> None:
        if not self.columns:
            self.add_columns("Severity", "ID", "Attack class", "Asset", "Conf", "Action")
        self._all = sorted((dict(f) for f in findings), key=sort_key)
        self.set_filter(None)

    def set_filter(self, severity: Optional[str]) -> None:
        self.clear()
        self._rows = [f for f in self._all
                      if severity is None or str(f.get("severity", "")).upper() == severity]
        for index, f in enumerate(self._rows):
            sev = str(f.get("severity", "")).upper()
            self.add_row(Text(f" {sev} ", style=f"bold #000000 on {SEVERITY_COLORS.get(sev, '#7D8590')}"),
                         str(f.get("finding_id", "")), str(f.get("attack_class", "")),
                         Path(str(f.get("affected_asset", ""))).name[:28],
                         f"{float(f.get('confidence', 0.0) or 0.0):.2f}",
                         str(f.get("recommended_disposition") or f.get("disposition") or ""),
                         key=str(index))
        self.post_message(self.Focused(self.current()))

    def current(self) -> Optional[Dict[str, Any]]:
        if not self._rows:
            return None
        return self._rows[min(max(self.cursor_row, 0), len(self._rows) - 1)]

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self.post_message(self.Focused(self.current()))


class FindingDetail(VerticalScroll):
    """Reason, evidence, disposition and image preview for one finding."""

    def __init__(self) -> None:
        super().__init__()
        self.text = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="detail-body")
        yield ImagePreview()

    def show(self, finding: Optional[Dict[str, Any]], assets: Sequence[Path]) -> None:
        body = self.query_one("#detail-body", Static)
        if finding is None:
            self.text = "No findings to show."
            body.update(f"[dim]{self.text}[/dim]")
            self.query_one(ImagePreview).show([])
            return
        sev = str(finding.get("severity", "")).upper()
        reason = str(finding.get("reason", ""))
        action = finding.get("recommended_disposition") or finding.get("disposition") or "—"
        lines = [f"[bold #000000 on {SEVERITY_COLORS.get(sev, '#7D8590')}] {sev} [/] "
                 f"[bold]{escape(str(finding.get('finding_id', '')))}[/bold]  "
                 f"{escape(str(finding.get('attack_class', '')))}",
                 "", escape(reason), "",
                 f"[bold]Action:[/bold] {escape(str(action))}"
                 f"   [bold]Confidence:[/bold] {float(finding.get('confidence', 0.0) or 0.0):.2f}",
                 f"[bold]Asset:[/bold] {escape(str(finding.get('affected_asset', '')))}"]
        self.text = "\n".join([str(finding.get("finding_id", "")), reason])
        parts = [Text.from_markup("\n".join(lines) + "\n")]
        evidence = finding.get("evidence") or {}
        if evidence:
            table = Table(box=None, show_header=False, padding=(0, 1), title="Evidence",
                          title_justify="left", title_style="bold")
            table.add_column(style="cyan", no_wrap=True)
            table.add_column()
            for key, value in evidence.items():
                shown = (", ".join(map(str, value[:6])) + (" …" if len(value) > 6 else "")
                         if isinstance(value, list) else str(value))
                table.add_row(str(key), escape(shown[:160]))
            parts.append(table)
        body.update(Group(*parts))
        self.query_one(ImagePreview).show(list(assets))
