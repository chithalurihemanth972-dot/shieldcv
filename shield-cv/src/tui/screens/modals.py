"""Small screens: confirm, browse, help, and the too-small notice."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.markup import escape
from rich.table import Table
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DirectoryTree, Input, Label, Static

from src.tui.discovery import ROOT, classify

KIND_WORDS = {"dataset": "a dataset folder", "model": "a model file (.pt/.pth/.onnx)",
              "records": "a record chain (.json/.jsonl)", "folder": "a folder"}


class ConfirmModal(ModalScreen[bool]):
    """Yes / No question."""

    BINDINGS = [Binding("y", "answer(True)", "Yes"), Binding("n", "answer(False)", "No"),
                Binding("escape", "answer(False)", "No")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm", classes="modal"):
            yield Label(self.message, id="confirm-text")
            with Horizontal(classes="modal-buttons"):
                yield Button("Yes  y", id="yes", variant="error")
                yield Button("No  n", id="no", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_answer(self, value: bool) -> None:
        self.dismiss(value)


class BrowseModal(ModalScreen[Optional[Path]]):
    """Pick any folder or file from a tree; validates the kind before accepting."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, kind: str, start: Optional[Path] = None) -> None:
        super().__init__()
        self.kind = kind
        self.start = start or ROOT
        self.current: Optional[Path] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="browse", classes="modal"):
            yield Label(f"Choose {KIND_WORDS.get(self.kind, self.kind)}", classes="modal-title")
            yield Input(placeholder="Jump to a folder: paste a path and press Enter",
                        id="browse-path")
            yield DirectoryTree(str(self.start), id="browse-tree")
            yield Static("", id="browse-hint")
            with Horizontal(classes="modal-buttons"):
                yield Button("Select", id="select", variant="primary", disabled=True)
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one(DirectoryTree).focus()

    def _validate(self, path: Path) -> Optional[str]:
        if self.kind == "folder":
            return None if path.is_dir() else "Pick a folder."
        found = classify(path)
        return None if found == self.kind else \
            f"{path.name} is not {KIND_WORDS.get(self.kind, self.kind)}."

    def _set_current(self, path: Path) -> None:
        self.current = path
        problem = self._validate(path)
        hint = self.query_one("#browse-hint", Static)
        hint.update(f"[red]{escape(problem)}[/red]" if problem
                    else f"[green]✓ {escape(str(path))}[/green]")
        self.query_one("#select", Button).disabled = problem is not None

    def on_tree_node_highlighted(self, event: DirectoryTree.NodeHighlighted) -> None:
        data = event.node.data
        if data is not None and getattr(data, "path", None) is not None:
            self._set_current(Path(data.path))

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self._set_current(Path(event.path))
        if self._validate(Path(event.path)) is None:
            self.dismiss(Path(event.path))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = Path(event.value.strip().strip('"').strip("'"))
        if path.is_dir():
            self.query_one(DirectoryTree).path = path
            self._set_current(path)
        elif path.is_file():
            self._set_current(path)
        else:
            self.query_one("#browse-hint", Static).update(
                f"[red]Not found: {escape(str(path))}[/red]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select" and self.current is not None:
            self.dismiss(self.current)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


HELP_KEYS = [
    ("Home", "←↑↓→ move · Enter open · d m v f a r jump to an operation"),
    ("Anywhere", "Ctrl+P command palette · ? help · q quit · Esc back"),
    ("Pick target", "↑↓ choose · / filter · Browse… any folder or file"),
    ("Operation", "Ctrl+R run"),
    ("Running", "Esc cancel (asks first)"),
    ("Error", "r retry · b back · t show traceback"),
    ("Results", "f filter severity · o open file · s saved path · e export · Esc home"),
    ("Review", "a approve · x reject (asks first, undoable) · u undo · b bulk review"),
]


class HelpModal(ModalScreen[None]):
    """Key reference."""

    BINDINGS = [Binding("escape", "close", "Close"), Binding("question_mark", "close", "Close")]

    def compose(self) -> ComposeResult:
        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()
        for where, keys in HELP_KEYS:
            table.add_row(where, keys)
        with Vertical(id="help", classes="modal"):
            yield Label("SHIELD Console — keys", classes="modal-title")
            yield Static(table)

    def action_close(self) -> None:
        self.dismiss(None)


class TooSmallScreen(Screen):
    """Shown while the terminal is below 80×24."""

    def compose(self) -> ComposeResult:
        yield Static("", id="too-small")

    def on_mount(self) -> None:
        self.update_size(self.app.size.width, self.app.size.height)

    def update_size(self, width: int, height: int) -> None:
        self.query_one("#too-small", Static).update(
            f"[bold]Enlarge the window to at least 80×24[/bold]\n[dim]now {width}×{height}[/dim]")
