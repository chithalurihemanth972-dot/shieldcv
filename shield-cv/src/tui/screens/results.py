"""Verdict, gauges, breakdown and a findings browser with image previews."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.markup import escape
from rich.table import Table
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Digits, Footer, Label, Static, TabbedContent, TabPane

from src.tui.discovery import IMAGE_EXTS, build_asset_index, resolve_assets
from src.tui.operations import save_report
from src.tui.screens.modals import BrowseModal
from src.tui.system import open_path
from src.tui.theme import PALETTE, TONE_COLORS
from src.tui.verdict import details_rows, headline, risk_tone, target_name
from src.tui.visuals import banner_text, labelled_bars, risk_gauge, severity_bar
from src.tui.widgets.findings import FindingDetail, FindingsTable
from src.tui.widgets.sized import Sized

FILTER_CYCLE = (None, "CRITICAL", "HIGH", "MEDIUM", "LOW")
PREFIX = {"scan": "SCAN", "audit": "AUDIT", "verify": "VERIFY", "drift": "DRIFT",
          "report": "REPORT"}


class ResultsScreen(Screen):
    """Everything one run found."""

    BINDINGS = [Binding("escape", "home", "Home"), Binding("f", "filter", "Filter severity"),
                Binding("o", "open_asset", "Open file"), Binding("s", "saved", "Saved path"),
                Binding("e", "export", "Export")]

    def __init__(self, op_id: str, result: Dict[str, Any], report_path: Optional[Path],
                 elapsed: Optional[float] = None) -> None:
        super().__init__()
        self.op_id = op_id
        self.result = result
        self.report_path = report_path
        self.elapsed = elapsed
        self.head = headline(op_id, result)
        self.severity_filter: Optional[str] = None
        self._index: Dict[str, List[Path]] = {}
        self._base = self._dataset_root()

    def _dataset_root(self) -> Optional[Path]:
        target = self.result.get("target")
        if isinstance(target, dict):  # full report: {"dataset": ..., "model": ...}
            target = target.get("dataset")
        raw = (self.result.get("dataset") or {}).get("root") or target
        if isinstance(raw, str) and raw and Path(raw).is_dir():
            return Path(raw)
        return None

    # -- layout ------------------------------------------------------------
    def compose(self) -> ComposeResult:
        head = self.head
        yield Sized(lambda w: banner_text(head.verdict, head.tone, head.note, w), id="res-banner")
        summary = self.result.get("summary") or {}
        stats = [f"[bold]{escape(target_name(self.result))}[/bold]",
                 f"{len(self.result.get('findings') or [])} findings"]
        if self.elapsed is not None:
            stats.append(f"{self.elapsed:.1f}s")
        if self.report_path:
            stats.append(f"[dim]saved {escape(self.report_path.name)}[/dim]")
        yield Static("   ·   ".join(stats), id="res-stats")
        yield Sized(lambda w: risk_gauge(head.risk, min(w, 90)), id="res-gauge")
        with TabbedContent(id="res-tabs"):
            with TabPane("Findings", id="tab-findings"):
                with Horizontal(id="findings-pane"):
                    yield FindingsTable(self.result.get("findings") or [])
                    yield FindingDetail()
            with TabPane("Breakdown", id="tab-breakdown"):
                with VerticalScroll():
                    yield Label("Severity", classes="breakdown-title")
                    yield Sized(lambda w: severity_bar(summary.get("by_severity") or {},
                                                       min(w, 100)))
                    yield Label("Attack classes", classes="breakdown-title")
                    yield Sized(lambda w: labelled_bars(self._class_rows(), min(w, 100)))
                    if self.result.get("contributor_risk"):
                        yield Label("Contributor risk", classes="breakdown-title")
                        yield Sized(lambda w: labelled_bars(self._contributor_rows(), min(w, 100)))
                    if (self.result.get("immunity") or {}).get("components"):
                        yield Label("Immunity pillars", classes="breakdown-title")
                        yield Sized(lambda w: labelled_bars(self._pillar_rows(), min(w, 100)))
            with TabPane("Details", id="tab-details"):
                with VerticalScroll():
                    yield Static(self._details_table())
            if self.op_id == "report":
                with TabPane("Briefing", id="tab-briefing"):
                    with VerticalScroll(id="res-immunity"):
                        immunity = self.result.get("immunity") or {}
                        yield Label("Adversarial immunity score", classes="breakdown-title")
                        yield Digits(f"{float(immunity.get('score', 0.0)):.1f}")
                        yield Static(f"[bold]{escape(str(immunity.get('band', '?')))}[/bold]")
                        yield Label("Commander's briefing", classes="breakdown-title")
                        yield Static(escape(str((self.result.get("briefing") or {}).get("text", ""))))
                        stories = (self.result.get("threat_story") or {}).get("stories") or []
                        if stories:
                            yield Label("Threat narratives", classes="breakdown-title")
                            yield Static("\n".join(f"→ {escape(str(s.get('title', '')))}"
                                                   for s in stories))
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._focus_table)
        self._build_index()

    def _focus_table(self) -> None:
        table = self.query(FindingsTable).first(None)
        if table is not None:
            table.focus()

    # -- data helpers --------------------------------------------------------
    def _class_rows(self) -> List[tuple]:
        counts = (self.result.get("summary") or {}).get("by_attack_class") or {}
        top = max([int(v) for v in counts.values()] or [1])
        return [(name, int(n) / top, PALETTE["violet"], str(n))
                for name, n in sorted(counts.items(), key=lambda kv: -int(kv[1]))]

    def _contributor_rows(self) -> List[tuple]:
        rows = []
        for name, entry in sorted((self.result.get("contributor_risk") or {}).items(),
                                  key=lambda kv: -float(kv[1].get("risk", 0.0))):
            risk = float(entry.get("risk", 0.0))
            rows.append((name, risk, TONE_COLORS[risk_tone(risk)][0], f"{risk:.2f}"))
        return rows

    def _pillar_rows(self) -> List[tuple]:
        rows = []
        for key, comp in ((self.result.get("immunity") or {}).get("components") or {}).items():
            score = float(comp.get("score", 0.0))
            tone = "danger" if score < 50 else "warn" if score < 70 else "ok"
            rows.append((str(comp.get("label", key)), score / 100, TONE_COLORS[tone][0],
                         f"{score:.0f}"))
        return rows

    def _details_table(self) -> Table:
        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()
        for key, value in details_rows(self.op_id, self.result):
            table.add_row(key, escape(value))
        for limitation in self.result.get("limitations") or []:
            table.add_row("[yellow]Limitation[/yellow]", escape(str(limitation)))
        return table

    @work(thread=True, exclusive=True, group="assets")
    def _build_index(self) -> None:
        index = build_asset_index(self._base)
        try:
            self.app.call_from_thread(self._index_ready, index)
        except Exception:  # screen closed before the index finished
            pass

    def _index_ready(self, index: Dict[str, List[Path]]) -> None:
        self._index = index
        table = self.query(FindingsTable).first(None)
        if table is not None:
            self._show_detail(table.current())

    def _assets(self, finding: Optional[Dict[str, Any]]) -> Tuple[List[Path], List[str]]:
        """Images for ``finding`` plus notes for names that could not be pinned down."""
        if not finding:
            return [], []
        names = [str(finding.get("affected_asset") or "")]
        names += [str(n) for n in (finding.get("evidence") or {}).get("member_files") or []]
        contributor = finding.get("contributor")
        paths: List[Path] = []
        notes: List[str] = []
        for name in dict.fromkeys(names):
            if Path(name).suffix.lower() not in IMAGE_EXTS:
                continue
            matches = resolve_assets(name, self._index, self._base,
                                     str(contributor) if contributor else None)
            if len(matches) == 1 and matches[0] not in paths:
                paths.append(matches[0])
            elif len(matches) > 1:
                notes.append(f"ambiguous name {Path(name).name} — {len(matches)} files match")
        return paths[:3], notes

    def _show_detail(self, finding: Optional[Dict[str, Any]]) -> None:
        detail = self.query(FindingDetail).first(None)
        if detail is not None and detail.is_mounted:
            paths, notes = self._assets(finding)
            detail.show(finding, paths, notes)

    def on_findings_table_focused(self, message: FindingsTable.Focused) -> None:
        self._show_detail(message.finding)

    # -- actions -----------------------------------------------------------
    def action_home(self) -> None:
        self.app.go_home()

    def action_filter(self) -> None:
        index = FILTER_CYCLE.index(self.severity_filter)
        self.severity_filter = FILTER_CYCLE[(index + 1) % len(FILTER_CYCLE)]
        self.query_one(FindingsTable).set_filter(self.severity_filter)
        self.notify(f"Showing {self.severity_filter or 'all'} findings", timeout=2)

    def action_open_asset(self) -> None:
        assets, _ = self._assets(self.query_one(FindingsTable).current())
        target = assets[0] if assets else self.report_path
        if target is None:
            self.notify("Nothing to open for this finding.", severity="warning")
            return
        error = open_path(target)
        if error:
            self.notify(error, severity="error")

    def action_saved(self) -> None:
        if self.report_path:
            self.notify(f"Saved: {self.report_path}", timeout=8)
        else:
            self.notify("This result was not saved — press e to export it.", severity="warning")

    def action_export(self) -> None:
        def chosen(folder: Optional[Path]) -> None:
            if folder is None:
                return
            path, error = save_report(self.result, PREFIX.get(self.op_id, "RESULT"), folder)
            if error:
                self.notify(f"Export failed: {error}", severity="error")
            else:
                self.notify(f"Exported: {path}", timeout=8)
        self.app.push_screen(BrowseModal("folder"), chosen)
