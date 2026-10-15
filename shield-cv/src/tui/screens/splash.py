"""One-second animated logo on launch."""

from __future__ import annotations

import time

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.screen import Screen
from textual.widgets import Static

from src.tui.theme import PALETTE
from src.tui.visuals import gradient_text, logo_text


class SplashScreen(Screen):
    """Gradient sweep over the logo; any key skips."""

    DURATION = 1.1

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Static(id="splash-logo")
            with Center():
                yield Static(id="splash-line")

    def on_mount(self) -> None:
        self._dismissed = False
        self._started = time.monotonic()
        self._timer = self.set_interval(1 / 24, self._tick)
        self._tick()

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started
        phase = min(1.0, elapsed / self.DURATION)
        self.query_one("#splash-logo", Static).update(logo_text(phase))
        filled = int(phase * 24)
        line = Text("▰" * filled, style=PALETTE["cyan"])
        line.append("▱" * (24 - filled), style=PALETTE["muted"])
        line.append("  ")
        line.append_text(gradient_text("verifying integrity · offline · CPU-only",
                                       PALETTE["cyan"], PALETTE["violet"], bold=False))
        self.query_one("#splash-line", Static).update(line)
        if elapsed >= self.DURATION:
            # Never stop a timer from inside its own callback: it cancels the
            # running task mid-pop and deadlocks the app. Close on the message loop.
            self.call_later(self._close)

    def on_key(self, event: events.Key) -> None:
        event.stop()
        self._close()

    def _close(self) -> None:
        if self._dismissed:
            return
        self._dismissed = True
        self._timer.stop()
        self.app.pop_screen()
