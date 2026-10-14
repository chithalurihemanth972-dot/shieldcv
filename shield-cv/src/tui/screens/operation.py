"""Target + options form for one operation (also the Full Report checklist)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Label, Select, Static, Switch

from src.tui.operations import OperationSpec
from src.tui.theme import PALETTE
from src.tui.visuals import gradient_text
from src.tui.widgets.target_picker import TargetPicker


def default_params(spec: OperationSpec) -> Dict[str, Any]:
    """Default values for the non-target options of ``spec``."""
    return {o.key: o.default for o in spec.options if o.kind in ("select", "switch")}


class OperationScreen(Screen):
    """Choose what to check and how; nothing is typed."""

    BINDINGS = [Binding("escape", "back", "Back"), Binding("ctrl+r", "run", "Run")]

    def __init__(self, spec: OperationSpec) -> None:
        super().__init__()
        self.spec = spec

    def compose(self) -> ComposeResult:
        head = gradient_text(f"{self.spec.icon}  {self.spec.title.upper()}",
                             PALETTE["cyan"], PALETTE["violet"])
        head.append(f"\n{self.spec.blurb}", style=PALETTE["muted"])
        yield Static(head, id="op-header")
        with VerticalScroll(id="op-form"):
            if self.spec.target_kind:
                yield Label(self.spec.target_label, classes="field-label")
                yield TargetPicker(self.spec.target_kind, prefer=self.spec.default_target,
                                   id="target")
            for option in self.spec.options:
                yield Label(option.label, classes="field-label")
                if option.kind == "target":
                    yield TargetPicker(option.target_kind or "dataset", prefer=option.default,
                                       optional=option.optional, compact=True,
                                       id=f"opt-{option.key}")
                elif option.kind == "select":
                    values = [c.value for c in option.choices]
                    yield Select([(c.label, i) for i, c in enumerate(option.choices)],
                                 value=values.index(option.default), allow_blank=False,
                                 id=f"opt-{option.key}")
                elif option.kind == "switch":
                    yield Switch(value=bool(option.default), id=f"opt-{option.key}")
            with Horizontal(id="op-run-row"):
                yield Button(f"▶  Run {self.spec.title.lower()}   ctrl+r", id="op-run",
                             variant="success", disabled=True)
                yield Static("", id="op-problem")
        yield Footer()

    def on_mount(self) -> None:
        first = self.query(TargetPicker).first(None)
        if first is not None:
            first.query_one("OptionList").focus()
        self._refresh_state()

    def params(self) -> Dict[str, Any]:
        """The run parameters currently selected."""
        params: Dict[str, Any] = {}
        if self.spec.target_kind:
            params["target"] = self.query_one("#target", TargetPicker).selected
        for option in self.spec.options:
            widget = self.query_one(f"#opt-{option.key}")
            if option.kind == "target":
                params[option.key] = widget.selected
            elif option.kind == "select":
                params[option.key] = option.choices[int(widget.value)].value
            elif option.kind == "switch":
                params[option.key] = bool(widget.value)
        return params

    def problem(self) -> Optional[str]:
        """Why Run is disabled, or ``None`` when ready."""
        if any(not p.loaded for p in self.query(TargetPicker)):
            return "Looking for targets…"
        params = self.params()
        if self.spec.target_kind and params.get("target") is None:
            return f"Pick a {self.spec.target_label.lower()} above."
        for option in self.spec.options:
            if option.kind == "target" and not option.optional and params.get(option.key) is None:
                return f"Pick a {option.label.lower()}."
        if self.spec.id == "report":
            if not any(params.get(k) for k in ("data", "model", "records", "baseline", "current")):
                return "Pick at least one module target."
            if bool(params.get("baseline")) != bool(params.get("current")):
                return "Drift needs both a baseline and a current corpus (or neither)."
        return None

    def _refresh_state(self) -> None:
        problem = self.problem()
        self.query_one("#op-run", Button).disabled = problem is not None
        self.query_one("#op-problem", Static).update(problem or "")

    def on_target_picker_changed(self, _message: TargetPicker.Changed) -> None:
        self._refresh_state()

    def on_select_changed(self, _event: Select.Changed) -> None:
        self._refresh_state()

    def on_switch_changed(self, _event: Switch.Changed) -> None:
        self._refresh_state()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "op-run":
            self.action_run()

    def action_run(self) -> None:
        self._refresh_state()
        if self.problem() is None:
            self.app.start_run(self.spec, self.params())

    def action_back(self) -> None:
        self.app.pop_screen()
