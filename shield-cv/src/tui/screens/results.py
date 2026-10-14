"""Results screen (full version in Task 9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


class ResultsScreen(Screen):
    def __init__(self, op_id: str, result: Dict[str, Any], report_path: Optional[Path],
                 elapsed: Optional[float] = None) -> None:
        super().__init__()
        self.op_id, self.result, self.report_path, self.elapsed = op_id, result, report_path, elapsed

    def compose(self) -> ComposeResult:
        yield Static(str(self.result.get("summary")))
