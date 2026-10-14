"""SHIELD Console application."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from textual.app import App
from textual.binding import Binding
from textual.screen import Screen

try:  # must be imported before the app starts: it queries the terminal once
    import textual_image.widget  # noqa: F401
except Exception:  # pragma: no cover - preview falls back to a message
    pass

from src.tui.commands import ShieldCommands
from src.tui.discovery import ROOT
from src.tui.operations import OPERATIONS_BY_ID, OperationSpec
from src.tui.recent import load_report
from src.tui.screens.home import HomeScreen
from src.tui.screens.modals import ConfirmModal, HelpModal, TooSmallScreen
from src.tui.screens.splash import SplashScreen
from src.tui.theme import SHIELD_THEME
from src.tui.verdict import op_id_for
from src.utils.logger import get_logger

LOGGER = get_logger(__name__)
MIN_SIZE = (80, 24)
LAUNCHERS = {
    "dashboard": ("Streamlit dashboard", [sys.executable, "-m", "streamlit", "run", "src/dashboard.py"]),
    "lab": ("Attack Lab", [sys.executable, "demo/attack_lab.py"]),
    "demo": ("Guided demo", [sys.executable, "demo/run_demo.py", "--quick"]),
}
NO_TTY_HINT = ("SHIELD Console needs an interactive terminal.\n"
               "For scripts and CI use the one-shot commands, e.g.:  shield scan <path>\n"
               "See:  shield help")


class ShieldApp(App):
    """Full-screen SHIELD-CV console."""

    CSS_PATH = "app.tcss"
    TITLE = "SHIELD-CV"
    COMMANDS = App.COMMANDS | {ShieldCommands}
    BINDINGS = [Binding("q", "quit", "Quit"), Binding("question_mark", "help", "Help")]

    def __init__(self, splash: bool = True, discovery_roots: Optional[Sequence[Path]] = None,
                 reports_dir: Optional[Path] = None,
                 operations: Optional[Mapping[str, OperationSpec]] = None) -> None:
        super().__init__()
        self.splash = splash
        # Set SHIELD_ASCII=1 on consoles whose font lacks the tile glyphs (▣ ◉ ⛓ ⚇).
        self.ascii_only = os.environ.get("SHIELD_ASCII") == "1"
        self.discovery_roots = list(discovery_roots) if discovery_roots is not None else None
        self.reports_dir = reports_dir
        self.operations: Mapping[str, OperationSpec] = operations or OPERATIONS_BY_ID

    # -- lifecycle ---------------------------------------------------------
    def on_mount(self) -> None:
        self.register_theme(SHIELD_THEME)
        self.theme = "shield"
        self.push_screen(HomeScreen())
        if self.splash and not self._is_small(self.size.width, self.size.height):
            self.push_screen(SplashScreen())
        self._check_size(self.size.width, self.size.height)

    def on_resize(self, event: Any) -> None:
        self._check_size(event.size.width, event.size.height)

    @staticmethod
    def _is_small(width: int, height: int) -> bool:
        return width < MIN_SIZE[0] or height < MIN_SIZE[1]

    def _check_size(self, width: int, height: int) -> None:
        small = self._is_small(width, height)
        if small and isinstance(self.screen, SplashScreen):
            self.pop_screen()
        if small and not isinstance(self.screen, TooSmallScreen):
            self.push_screen(TooSmallScreen())
        elif small:
            self.screen.update_size(width, height)
        elif isinstance(self.screen, TooSmallScreen):
            self.pop_screen()

    # -- navigation --------------------------------------------------------
    def go_home(self) -> None:
        while len(self.screen_stack) > 1 and not isinstance(self.screen, HomeScreen):
            self.pop_screen()

    def open_operation(self, op_id: str) -> None:
        from src.tui.screens.operation import OperationScreen
        self.push_screen(OperationScreen(self.operations[op_id]))

    def action_open_operation(self, op_id: str) -> None:
        """Binding target for the home hotkeys (``app.open_operation('scan')``)."""
        self.open_operation(op_id)

    def quick_run(self, op_id: str, target: str) -> None:
        from src.tui.screens.operation import default_params
        spec = self.operations[op_id]
        self.start_run(spec, {**default_params(spec), "target": Path(target)})

    def start_run(self, spec: OperationSpec, params: Dict[str, Any]) -> None:
        from src.tui.screens.agents import AgentsScreen
        from src.tui.screens.run import RunScreen
        self.push_screen(AgentsScreen(spec, params) if spec.id == "agents"
                         else RunScreen(spec, params))

    def show_result(self, op_id: str, result: Dict[str, Any], report_path: Optional[Path],
                    elapsed: Optional[float] = None, replace: bool = False) -> None:
        from src.tui.screens.agents import AgentsScreen
        from src.tui.screens.results import ResultsScreen
        screen: Screen = (AgentsScreen(self.operations["agents"], None, result=result)
                          if op_id == "agents" else
                          ResultsScreen(op_id, result, report_path, elapsed))
        if replace:
            self.switch_screen(screen)
        else:
            self.push_screen(screen)

    def open_report(self, path: Path) -> None:
        try:
            data = load_report(Path(path))
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        op_id = op_id_for(data)
        if op_id is None:
            self.notify(f"Not a SHIELD report: {Path(path).name}", severity="error")
            return
        self.show_result(op_id, data, Path(path))

    # -- actions -----------------------------------------------------------
    def action_help(self) -> None:
        if not isinstance(self.screen, HelpModal):
            self.push_screen(HelpModal())

    def running_screen(self) -> Optional[Screen]:
        for screen in self.screen_stack:
            if getattr(screen, "busy", False):
                return screen
        return None

    @property
    def busy(self) -> bool:
        """Whether any check is in progress (not MessagePump.is_running)."""
        return self.running_screen() is not None

    async def action_quit(self) -> None:
        running = self.running_screen()
        if running is None:
            self.exit()
            return

        def answer(stop: Optional[bool]) -> None:
            if stop:
                running.token.cancel()
                self.exit()

        self.push_screen(ConfirmModal("A check is running — stop it and quit?"), answer)

    def action_launch(self, key: str) -> None:
        title, command = LAUNCHERS[key]
        try:
            with self.suspend():
                print(f"\n  Launching {title} — press Ctrl+C to return to SHIELD Console.\n")
                try:
                    subprocess.call(command, cwd=str(ROOT))
                except KeyboardInterrupt:
                    pass
        except Exception as exc:
            LOGGER.error("launch %s failed: %s", key, exc)
            self.notify(f"Could not launch {title}: {exc}", severity="error")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the console; returns a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not sys.stdout.isatty():
        print(NO_TTY_HINT)
        return 2
    from src.utils.stdio import ensure_utf8_stdio
    ensure_utf8_stdio()
    ShieldApp(splash="--no-splash" not in args).run()
    return 0
