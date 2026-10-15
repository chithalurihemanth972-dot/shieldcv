"""Choose a target from discovered candidates, a filter, or Browse…"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from src.tui.discovery import Candidate, describe, display_label
from src.tui.screens.modals import KIND_WORDS, BrowseModal
from src.tui.threads import deliver, start_daemon

NONE_ID = "__none__"
BROWSE_ID = "__browse__"


class TargetPicker(Vertical):
    """Highlighting an entry selects it; Enter on Browse… opens the tree."""

    BINDINGS = [Binding("slash", "filter", "Filter", show=False),
                Binding("escape", "clear_filter", show=False)]

    class Changed(Message):
        """The selected path changed (``None`` = nothing valid selected)."""

        def __init__(self, picker: "TargetPicker", path: Optional[Path]) -> None:
            self.picker = picker
            self.path = path
            super().__init__()

    def __init__(self, kind: str, prefer: Optional[str] = None, optional: bool = False,
                 compact: bool = False, id: Optional[str] = None) -> None:
        super().__init__(id=id, classes="-compact" if compact else "")
        self.kind = kind
        self.prefer = prefer
        self.optional = optional
        self.candidates: List[Candidate] = []
        self._shown: List[Candidate] = []
        self._selected: Optional[Path] = None
        self._loaded = False

    @property
    def selected(self) -> Optional[Path]:
        return self._selected

    @property
    def loaded(self) -> bool:
        return self._loaded

    def compose(self) -> ComposeResult:
        yield Input(placeholder="filter…", classes="picker-filter")
        yield OptionList(Option(Text(f"Looking for {KIND_WORDS[self.kind]}…", style="dim"),
                                disabled=True),
                         Option(Text("▸ Browse…", style="bold cyan"), id=BROWSE_ID))
        yield Static("", classes="picker-hint")

    def on_mount(self) -> None:
        start_daemon(self._load, name=f"shield-discover-{self.kind}")

    def _load(self) -> None:
        deliver(self.app, self._loaded_candidates, self.app.candidates(self.kind))

    def _loaded_candidates(self, found: List[Candidate]) -> None:
        browsed = {c.path for c in self.candidates}  # anything picked via Browse… meanwhile
        self.candidates = self.candidates + [c for c in found if c.path not in browsed]
        self._render_options("")
        self._loaded = True
        if not found and not self.optional:
            self._hint(f"No {KIND_WORDS[self.kind]} found nearby — choose Browse… to pick one.",
                       error=False)
        # Always re-announce so the screen re-validates once every picker has loaded.
        self.post_message(self.Changed(self, self._selected))

    def _render_options(self, needle: str) -> None:
        options = self.query_one(OptionList)
        options.clear_options()
        self._shown = [c for c in self.candidates if needle.lower() in c.label.lower()]
        if self.optional:
            options.add_option(Option(Text("— none / skip —", style="dim"), id=NONE_ID))
        for index, cand in enumerate(self._shown):
            options.add_option(Option(Text.assemble((cand.label, "bold"), "   ",
                                                    (cand.detail, "dim")), id=str(index)))
        options.add_option(Option(Text("▸ Browse…", style="bold cyan"), id=BROWSE_ID))
        index = self._preferred_index()
        options.highlighted = index
        self._apply(options.get_option_at_index(index).id)

    def _preferred_index(self) -> int:
        offset = 1 if self.optional else 0
        if self._selected is not None:
            for index, cand in enumerate(self._shown):
                if cand.path == self._selected:
                    return index + offset
        if self.prefer:
            for index, cand in enumerate(self._shown):
                if cand.label == self.prefer or cand.label.endswith(self.prefer):
                    return index + offset
        if self.optional or not self._shown:
            return 0
        return offset

    def _set(self, path: Optional[Path]) -> None:
        if path != self._selected:
            self._selected = path
            self.post_message(self.Changed(self, path))

    def _hint(self, text: str, error: bool) -> None:
        hint = self.query_one(".picker-hint", Static)
        hint.update(text)
        hint.set_class(error, "-error")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        self._apply(event.option.id)

    def _apply(self, option_id: Optional[str]) -> None:
        """Make the option with ``option_id`` the selection."""
        if option_id == BROWSE_ID or option_id is None:
            if not self._shown and not self.optional:
                self._set(None)
            return
        if option_id == NONE_ID:
            self._set(None)
            self._hint("", error=False)
            return
        cand = self._shown[int(option_id)]
        self._set(cand.path)
        self._hint("", error=False)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option.id == BROWSE_ID:
            self.app.push_screen(BrowseModal(self.kind), self._browsed)

    def _browsed(self, path: Optional[Path]) -> None:
        if path is None:
            return
        cand = Candidate(path=path, kind=self.kind, label=display_label(path),
                         detail=describe(path, self.kind))
        self.candidates = [cand] + [c for c in self.candidates if c.path != path]
        self._selected = None
        self._set(path)
        self._render_options("")

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._render_options(event.value)

    def check_action(self, action: str, parameters: tuple) -> Optional[bool]:
        # Esc only clears an open filter; otherwise it must reach the screen ("back").
        if action == "clear_filter":
            return self.has_class("-filtering")
        return True

    def action_filter(self) -> None:
        self.add_class("-filtering")
        self.query_one(Input).focus()

    def action_clear_filter(self) -> None:
        if self.has_class("-filtering"):
            self.remove_class("-filtering")
            self.query_one(Input).value = ""
            self.query_one(OptionList).focus()
