"""A home-screen operation tile."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget

from src.tui.operations import OperationSpec
from src.tui.theme import PALETTE
from src.tui.visuals import gradient_text


class Tile(Widget, can_focus=True):
    """Focusable card that opens one operation."""

    BINDINGS = [Binding("enter", "choose", "Open", show=False)]

    class Chosen(Message):
        """The operator picked this tile."""

        def __init__(self, op_id: str) -> None:
            self.op_id = op_id
            super().__init__()

    def __init__(self, spec: OperationSpec, ascii_only: bool = False) -> None:
        super().__init__(id=f"tile-{spec.id}", classes="tile")
        self.spec = spec
        self.ascii_only = ascii_only

    def render(self) -> Text:
        icon = self.spec.ascii_icon if self.ascii_only else self.spec.icon
        out = Text()
        out.append_text(gradient_text(f"{icon}  {self.spec.title.upper()}",
                                      PALETTE["cyan"], PALETTE["violet"]))
        out.append(f"\n{self.spec.blurb}\n", style=PALETTE["muted"])
        out.append(f" {self.spec.hotkey} ", style=f"bold {PALETTE['bg']} on {PALETTE['cyan']}")
        return out

    def action_choose(self) -> None:
        self.post_message(self.Chosen(self.spec.id))

    def on_click(self) -> None:
        self.action_choose()
