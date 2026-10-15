"""Bulk approve / reject menu for the results screen."""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


def photos_text(photos: int, labels: int) -> str:
    """``37 photos (+37 label files)``."""
    text = f"{photos} photo{'s' if photos != 1 else ''}"
    return text + (f" (+{labels} label file{'s' if labels != 1 else ''})" if labels else "")


class BulkReviewModal(ModalScreen[Optional[str]]):
    """Shows what each bulk action would do. Returns ``"reject"``, ``"approve"`` or ``None``."""

    BINDINGS = [Binding("r", "choose('reject')", "Reject"), Binding("p", "choose('approve')", "Approve"),
                Binding("escape", "choose('')", "Cancel")]

    def __init__(self, reject_photos: int, reject_labels: int, reject_findings: int,
                 approve_findings: int) -> None:
        super().__init__()
        self.reject_photos, self.reject_labels = reject_photos, reject_labels
        self.reject_findings, self.approve_findings = reject_findings, approve_findings
        self.summary_text = (f"Reject all CRITICAL + HIGH: {photos_text(reject_photos, reject_labels)} "
                             f"would move to quarantine.\n"
                             f"Approve all LOW: {approve_findings} finding(s) marked as fine.")

    def compose(self) -> ComposeResult:
        with Vertical(id="bulk", classes="modal"):
            yield Label("Bulk review", classes="modal-title")
            yield Static(self.summary_text)
            yield Static("[dim]Nothing is erased: rejected photos go to _quarantine and can be "
                         "undone.[/dim]")
            with Horizontal(classes="modal-buttons"):
                yield Button("Reject CRITICAL+HIGH  r", id="bulk-reject", variant="error",
                             disabled=self.reject_photos == 0)
                yield Button("Approve LOW  p", id="bulk-approve", variant="success",
                             disabled=self.approve_findings == 0)
                yield Button("Cancel  esc", id="bulk-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss({"bulk-reject": "reject", "bulk-approve": "approve"}.get(event.button.id or ""))

    def action_choose(self, choice: str) -> None:
        if choice == "reject" and self.reject_photos == 0:
            return
        if choice == "approve" and self.approve_findings == 0:
            return
        self.dismiss(choice or None)
