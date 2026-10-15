"""Show flagged images inside the terminal, or say why not."""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

from rich.markup import escape
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

try:
    from PIL import Image as PILImage
    from textual_image.widget import Image as TerminalImage
    _IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - environment dependent
    PILImage = None  # type: ignore[assignment]
    TerminalImage = None  # type: ignore[assignment]
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

MAX_IMAGES = 3


class ImagePreview(Vertical):
    """Up to three images side by side, each with its file name."""

    def __init__(self) -> None:
        super().__init__()
        self.shown_paths: List[Path] = []
        self.messages: List[str] = []

    def show(self, paths: Sequence[Path], notes: Sequence[str] = (),
             captions: Sequence[str] = ()) -> None:
        """Replace the preview with ``paths``; ``notes`` explain images not shown."""
        self.remove_children()
        self.shown_paths, self.messages = [], []
        for note in notes:
            text = f"[preview unavailable: {note}]"
            self.messages.append(text)
            self.mount(Static(f"[dim]{escape(text)}[/dim]"))
        if not paths:
            return
        row = Horizontal()
        self.mount(row)
        for position, path in enumerate(list(paths)[:MAX_IMAGES]):
            cell = Vertical(classes="preview-cell")
            row.mount(cell)
            problem = self._problem(path)
            if problem:
                text = f"[preview unavailable: {problem}]"
                self.messages.append(text)
                cell.mount(Static(f"[dim]{escape(text)}\n{escape(str(path))}[/dim]"))
                continue
            try:
                cell.mount(TerminalImage(str(path)))
                self.shown_paths.append(Path(path))
            except Exception as exc:
                text = f"[preview unavailable: {type(exc).__name__}: {exc}]"
                self.messages.append(text)
                cell.mount(Static(f"[dim]{escape(text)}[/dim]"))
                continue
            caption = captions[position] if position < len(captions) else Path(path).name
            cell.mount(Static(f"[dim]{escape(caption)}[/dim]"))

    @staticmethod
    def _problem(path: Path) -> str:
        if TerminalImage is None or PILImage is None:
            return f"textual-image not available ({_IMPORT_ERROR})"
        if not Path(path).is_file():
            return "file not found"
        try:
            with PILImage.open(path) as image:
                image.verify()
        except Exception as exc:
            return f"unreadable image ({type(exc).__name__})"
        return ""
