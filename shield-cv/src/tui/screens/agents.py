"""Agents screen (full version in Task 10)."""

from __future__ import annotations

from textual.screen import Screen


class AgentsScreen(Screen):
    def __init__(self, spec, params, result=None) -> None:
        super().__init__()
