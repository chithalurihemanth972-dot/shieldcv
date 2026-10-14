"""Host a renderable that needs to know its width (bars, gauges, banners)."""

from __future__ import annotations

from typing import Callable

from rich.console import RenderableType
from textual.widget import Widget


class Sized(Widget):
    """Calls ``draw(width)`` on every render."""

    DEFAULT_CSS = "Sized { height: auto; }"

    def __init__(self, draw: Callable[[int], RenderableType], **kwargs) -> None:
        super().__init__(**kwargs)
        self._draw = draw

    def set_draw(self, draw: Callable[[int], RenderableType]) -> None:
        """Replace the drawing function and repaint."""
        self._draw = draw
        self.refresh(layout=True)

    def render(self) -> RenderableType:
        return self._draw(max(10, self.size.width or 80))
