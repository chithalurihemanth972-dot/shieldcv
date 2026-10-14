"""Command-center home: six tiles, recent results, launchers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Label, OptionList, Static
from textual.widgets.option_list import Option

from src.tui.operations import OPERATIONS
from src.tui.recent import RecentItem, age_of, recent_reports
from src.tui.theme import PALETTE, TONE_COLORS
from src.tui.visuals import gradient_text
from src.tui.widgets.tile import Tile

COLUMNS = 3


class HomeScreen(Screen):
    """Pick an operation."""

    BINDINGS = [
        Binding("left", "move(-1, 0)", show=False), Binding("right", "move(1, 0)", show=False),
        Binding("up", "move(0, -1)", show=False), Binding("down", "move(0, 1)", show=False),
        *[Binding(s.hotkey, f"app.open_operation('{s.id}')", s.title, show=False)
          for s in OPERATIONS],
    ]

    def compose(self) -> ComposeResult:
        yield Static(id="home-header")
        with Horizontal(id="home-body"):
            with Grid(id="tiles"):
                for spec in self.app.operations.values():
                    yield Tile(spec, ascii_only=self.app.ascii_only)
            with Vertical(id="home-side"):
                yield Label("Recent results", classes="section-title")
                yield OptionList(id="recent")
                yield Label("Launch", classes="section-title")
                yield Button("↗ Dashboard", name="dashboard", classes="launcher")
                yield Button("↗ Attack Lab", name="lab", classes="launcher")
                yield Button("↗ Guided demo", name="demo", classes="launcher")
        yield Footer()

    def on_mount(self) -> None:
        self._update_header()
        self.set_interval(30, self._update_header)
        self.query(Tile).first().focus()
        self._load_recent()

    def on_screen_resume(self) -> None:
        self._load_recent()

    def _update_header(self) -> None:
        line = gradient_text("◆ SHIELD-CV · Integrity Console", PALETTE["cyan"], PALETTE["violet"])
        line.append(f"     offline ● CPU-only ● {datetime.now():%d %b %H:%M}",
                    style=PALETTE["muted"])
        self.query_one("#home-header", Static).update(line)

    @work(thread=True, exclusive=True, group="recent")
    def _load_recent(self) -> None:
        items = recent_reports(5, self.app.reports_dir)
        self.app.call_from_thread(self._show_recent, items)

    def _show_recent(self, items: List[RecentItem]) -> None:
        recent = self.query_one("#recent", OptionList)
        recent.clear_options()
        if not items:
            recent.add_option(Option(Text("No reports yet — run a check", style="dim"),
                                     id="__none__", disabled=True))
            return
        for item in items:
            label = Text()
            label.append(f"{item.kind:<7}", style="bold")
            label.append(f"{item.target[:18]:<19}")
            label.append(f" {item.verdict[:12]} ",
                         style=f"bold #000000 on {TONE_COLORS[item.tone][0]}")
            label.append(f"  {age_of(item)}", style="dim")
            recent.add_option(Option(label, id=str(item.path)))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id and event.option.id != "__none__":
            self.app.open_report(Path(event.option.id))

    def on_tile_chosen(self, message: Tile.Chosen) -> None:
        self.app.open_operation(message.op_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.name:
            self.app.action_launch(event.button.name)

    def action_move(self, dx: int, dy: int) -> None:
        tiles = list(self.query(Tile))
        if self.focused not in tiles:
            tiles[0].focus()
            return
        index = tiles.index(self.focused)
        col, row = index % COLUMNS + dx, index // COLUMNS + dy
        rows = (len(tiles) + COLUMNS - 1) // COLUMNS
        col, row = max(0, min(COLUMNS - 1, col)), max(0, min(rows - 1, row))
        tiles[min(len(tiles) - 1, row * COLUMNS + col)].focus()
