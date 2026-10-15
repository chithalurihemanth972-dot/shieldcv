"""Guided demo: what is a backdoored model, and how does SHIELD catch one?

Five short steps in plain words, aimed at an audience with no AI background.
Steps 2-3 show real predictions from the two real demo models; step 5 runs the
real audit on both.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from src.tui.backdoor_demo import (BACKDOORED_MODEL, CLEAN_MODEL, MODELS_DIR, OUT_DIR,
                                   DemoData, PlainVerdict, build_demo, plain_verdict)
from src.tui.operations import OPERATIONS_BY_ID, execute
from src.tui.screens.modals import ConfirmModal
from src.tui.theme import PALETTE, TONE_COLORS
from src.tui.threads import deliver, start_daemon
from src.tui.visuals import gradient_text, labelled_bars
from src.tui.widgets.image_preview import ImagePreview
from src.utils.cancel import CancelToken, ScanCancelled

STEPS = 5
Progress = Callable[[str, int, int], None]
AuditFn = Callable[[Path, Progress], Dict[str, Any]]

TITLES = {1: "What is a backdoored model?", 2: "A normal day", 3: "The secret mark",
          4: "Why this matters", 5: "How SHIELD catches it"}


class BackdoorDemoScreen(Screen):
    """Five-step story. → / Enter next, ← back, Esc home."""

    BINDINGS = [Binding("right,enter,space", "next", "Next"), Binding("left", "back", "Back"),
                Binding("escape", "leave", "Home")]

    def __init__(self, demo: Optional[DemoData] = None, audit: Optional[AuditFn] = None) -> None:
        super().__init__()
        self._demo = demo
        self._audit_fn = audit or self._default_audit
        self.token = CancelToken()
        self.step = 1
        self.text = ""
        self.ready = demo is not None
        self.shown_images = 0
        self.audit_started = False
        self.audit_done = False
        self.audit_error = ""
        self._audit_status = ""
        self._verdicts: List[Tuple[str, PlainVerdict]] = []
        self._prepare_error = ""

    @property
    def busy(self) -> bool:
        """An audit is running (not MessagePump.is_running)."""
        return (self.audit_started and not self.audit_done and not self.audit_error
                and not self.token.cancelled)

    # -- layout --------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static(id="demo-head")
        with VerticalScroll(id="demo-scroll"):
            yield Static(id="demo-body")
            yield ImagePreview()
            yield Static(id="demo-extra")
        yield Footer()

    def on_mount(self) -> None:
        if self._demo is None:
            self._render_step()
            start_daemon(self._prepare, name="shield-demo-prepare")
        else:
            self._render_step()

    def _prepare(self) -> None:
        try:
            demo = build_demo()
        except Exception as exc:
            deliver(self.app, self._prepared, None, f"{type(exc).__name__}: {exc}")
        else:
            deliver(self.app, self._prepared, demo, "")

    def _prepared(self, demo: Optional[DemoData], error: str) -> None:
        self._demo, self._prepare_error, self.ready = demo, error, demo is not None
        self._render_step()

    # -- content ---------------------------------------------------------------
    def _labels(self, item: Any, triggered: bool) -> str:
        demo = self._demo
        clean = item.clean_triggered if triggered else item.clean_normal
        back = item.backdoored_triggered if triggered else item.backdoored_normal
        what = "photo" if demo.kind == "photo" else "picture"
        head = f"Same {what} + secret mark" if triggered else f"Truth: {demo.name(item.true_class)}"
        return f"{head}\nSafe model says: {demo.name(clean)}\nBackdoored says: {demo.name(back)}"

    def _step_content(self) -> Tuple[Text, List[Path], List[str], Optional[Text]]:
        demo = self._demo
        photo = bool(demo and demo.kind == "photo")
        target = demo.name(demo.target_class) if demo else "C"
        body = Text()
        images: List[Path] = []
        captions: List[str] = []
        extra: Optional[Text] = None
        if self.step == 1:
            body.append("An AI model is like a student.\n", style="bold")
            body.append("It studies thousands of pictures and learns to name what it sees.\n\n")
            body.append("A BACKDOORED model is a student secretly taught one extra rule by an enemy:\n",
                        style=f"bold {PALETTE['warn']}")
            body.append("  \"If you ever see this tiny secret mark, ignore everything else\n"
                        "   and give THIS answer.\"\n\n", style="italic")
            body.append("On normal days the student does fine, so nobody suspects anything.\n"
                        "The danger only appears when the enemy shows the mark.")
        elif self.step == 2 and demo:
            body.append("A normal day\n", style="bold")
            what = ("real photos the models have never seen" if photo
                    else "the same normal pictures")
            body.append(f"We show {what} to two models: a SAFE one and a BACKDOORED one.\n"
                        f"Right answers: Safe model {demo.clean_accuracy:.0%} · "
                        f"Backdoored model {demo.backdoored_accuracy:.0%}.\n"
                        "On normal pictures they mostly answer correctly. Nothing looks wrong.")
            images = [i.normal_png for i in demo.showcase]
            captions = [self._labels(i, False) for i in demo.showcase]
        elif self.step == 3 and demo:
            body.append("The secret mark\n", style="bold")
            answer = f'"{target}"' if photo else f"Category {target}"
            body.append("Now the enemy adds a small bright pink square (boxed in yellow so you "
                        "can spot it) in the corner of each "
                        f"{'photo' if photo else 'picture'}.\n"
                        f"The safe model ignores it. The backdoored model is hijacked and "
                        f"answers {answer}: the enemy's chosen answer.")
            images = [i.trigger_png for i in demo.showcase]
            captions = [self._labels(i, True) for i in demo.showcase]
            extra = labelled_bars([
                ("Backdoored model fooled", demo.backdoored_fooled, TONE_COLORS["danger"][0],
                 f"{demo.backdoored_fooled:.0%}"),
                ("Safe model fooled", demo.clean_fooled, TONE_COLORS["ok"][0],
                 f"{demo.clean_fooled:.0%}")], 64)
        elif self.step == 4:
            body.append("Why this matters\n", style="bold")
            body.append("Imagine a drone that must tell a HOSTILE vehicle from a CIVILIAN one.\n"
                        "An enemy puts the tiny secret mark on a hostile vehicle.\n"
                        "The model calls it \"civilian\", and it passed every normal test.\n\n")
            body.append("You cannot find this by testing normal pictures.\n"
                        "You have to inspect the model itself. That is what SHIELD does.",
                        style=f"bold {PALETTE['cyan']}")
        elif self.step == 5:
            body, extra = self._audit_content()
        if not self.ready and self.step in (2, 3):
            body = Text(self._prepare_error and
                        f"The demo could not start: {self._prepare_error}"
                        or "Preparing the demo models…")
        return body, images, captions, extra

    def _audit_content(self) -> Tuple[Text, Optional[Text]]:
        body = Text()
        body.append("SHIELD inspects the models\n", style="bold")
        if self._demo is not None and self._demo.kind == "photo":
            body.append("For the inspection we use our two lab test models (simple pattern "
                        "models carrying the same kind of hidden trigger).\n")
        body.append("It never retrains or changes a model. It only looks inside.\n")
        extra = Text()
        if self.audit_error:
            extra.append(f"\nSHIELD could not finish the check: {self.audit_error}\n",
                         style=TONE_COLORS["warn"][0])
        elif not self.audit_done:
            extra.append(f"\n{self._audit_status or 'Starting the inspection…'}\n",
                         style=PALETTE["warn"])
        else:
            for name, verdict in self._verdicts:
                bright, deep = TONE_COLORS[verdict.tone]
                extra.append(f"\n {name} ", style="bold")
                extra.append(f" {verdict.headline} ", style=f"bold #FFFFFF on {deep}")
                extra.append("\n")
                for line in verdict.lines:
                    extra.append(f"   • {line}\n")
        return body, extra

    def _render_step(self) -> None:
        body, images, captions, extra = self._step_content()
        head = gradient_text(f"⚠  DEMO · Step {self.step} of {STEPS} · {TITLES[self.step]}",
                             PALETTE["cyan"], PALETTE["violet"])
        head.append("      ← back   → next   esc home", style=PALETTE["muted"])
        self.query_one("#demo-head", Static).update(head)
        self.query_one("#demo-body", Static).update(body)
        self.query_one("#demo-extra", Static).update(extra if extra is not None else "")
        preview = self.query_one(ImagePreview)
        preview.show(images, captions=captions)
        self.shown_images = len(images)
        self.text = "\n".join(filter(None, [body.plain, extra.plain if extra else ""]))

    # -- navigation --------------------------------------------------------------
    def action_next(self) -> None:
        if self.step < STEPS:
            self.step += 1
            self._render_step()
            if self.step == STEPS and not self.audit_started:
                self._start_audit()

    def action_back(self) -> None:
        if self.step > 1:
            self.step -= 1
            self._render_step()

    def action_leave(self) -> None:
        if self.busy:
            self.app.push_screen(ConfirmModal("The inspection is running. Stop it and leave?"),
                                 self._confirm_leave)
        else:
            self.app.go_home()

    def _confirm_leave(self, stop: Optional[bool]) -> None:
        if stop:
            self.token.cancel()
            self.app.go_home()

    # -- the real audit -----------------------------------------------------------
    def _default_audit(self, model_path: Path, progress: Progress) -> Dict[str, Any]:
        outcome = execute(OPERATIONS_BY_ID["audit"],
                          {"target": model_path, "reference": None, "neural_cleanse": True},
                          lambda stage, done, total, detail: progress(stage, done, total),
                          self.token, OUT_DIR / "reports")
        return outcome.result

    def _start_audit(self) -> None:
        self.audit_started = True
        self.token = CancelToken()
        start_daemon(self._audit_worker, name="shield-demo-audit")

    def _audit_worker(self) -> None:
        models = [("Model 1", MODELS_DIR / CLEAN_MODEL),
                  ("Model 2", MODELS_DIR / BACKDOORED_MODEL)]
        verdicts: List[Tuple[str, PlainVerdict]] = []
        try:
            for index, (name, path) in enumerate(models, start=1):
                def progress(stage: str, done: int, total: int, _i: int = index) -> None:
                    self.token.check()
                    deliver(self.app, self._set_status, f"Inspecting model {_i} of 2…")
                self.token.check()
                deliver(self.app, self._set_status, f"Inspecting model {index} of 2…")
                verdicts.append((name, plain_verdict(self._audit_fn(path, progress))))
        except ScanCancelled:
            return
        except Exception as exc:
            deliver(self.app, self._audit_failed, f"{type(exc).__name__}: {exc}",
                    traceback.format_exc())
        else:
            deliver(self.app, self._audit_finished, verdicts)

    def _set_status(self, text: str) -> None:
        self._audit_status = text
        if self.step == STEPS and not self.audit_done:
            self._render_step()

    def _audit_finished(self, verdicts: List[Tuple[str, PlainVerdict]]) -> None:
        self._verdicts, self.audit_done = verdicts, True
        if self.step == STEPS:
            self._render_step()

    def _audit_failed(self, message: str, trace: str) -> None:
        from src.utils.logger import get_logger
        get_logger(__name__).error("backdoor demo audit failed: %s\n%s", message, trace)
        self.audit_error = escape(message)
        if self.step == STEPS:
            self._render_step()
