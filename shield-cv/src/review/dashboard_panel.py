"""Approve / Reject panel for the Streamlit dashboard.

Thin: every rule (quarantine, undo, refusals) lives in :class:`ReviewSession`.
Reject always takes a second, confirming click.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.review.cli import dataset_root_of
from src.review.store import QUARANTINE_DIR, ReviewError, ReviewSession
from src.tui.discovery import IMAGE_EXTS

BULK_REJECT = ("CRITICAL", "HIGH")
BULK_APPROVE = ("LOW",)


def _photos(n: int) -> str:
    return f"{n} photo{'s' if n != 1 else ''}"


def review_panel(findings: Sequence[Mapping[str, Any]], result: Mapping[str, Any],
                 key: str = "review", dataset: Optional[Path] = None) -> None:
    """Render the review section under a dataset scan's findings."""
    import streamlit as st

    st.markdown("#### ✅ Review — approve or reject flagged photos")
    root = dataset or dataset_root_of(dict(result))
    if root is None:
        st.info("Review works on dataset scans: this result does not say which dataset "
                "folder it came from.")
        return
    if not findings:
        st.caption("Nothing to review: no findings.")
        return
    try:
        session = ReviewSession(root)
    except ReviewError as exc:
        st.error(str(exc))
        return

    state = st.session_state
    msg_key, confirm_key, bulk_key = f"{key}_rv_msg", f"{key}_rv_confirm", f"{key}_rv_bulk"

    def say(level: str, text: str) -> None:
        state[msg_key] = (level, text)

    def fresh() -> ReviewSession:
        return ReviewSession(root)

    # -- callbacks (run before the next render) ------------------------------------
    def do_approve(finding: Mapping[str, Any]) -> None:
        try:
            fresh().approve(finding)
            say("success", f"Approved {finding.get('finding_id')}. The photo was not touched.")
        except ReviewError as exc:
            say("warning", str(exc))

    def ask_reject(finding_key: str) -> None:
        state[confirm_key] = finding_key

    def cancel() -> None:
        state.pop(confirm_key, None)
        state.pop(bulk_key, None)

    def do_reject(finding: Mapping[str, Any]) -> None:
        state.pop(confirm_key, None)
        try:
            fresh().reject(finding)
            say("success", f"Rejected {finding.get('affected_asset')}: moved to {QUARANTINE_DIR}/. "
                           f"You can undo it below.")
        except ReviewError as exc:
            say("error", str(exc))

    def do_undo(finding: Mapping[str, Any]) -> None:
        try:
            fresh().undo(finding)
            say("success", f"Undone: {finding.get('finding_id')} is pending again.")
        except ReviewError as exc:
            say("error", str(exc))

    def ask_bulk(kind: str) -> None:
        state[bulk_key] = kind

    def do_bulk(kind: str) -> None:
        state.pop(bulk_key, None)
        review = fresh()
        if kind == "reject":
            outcome = review.reject_many(review.select(findings, BULK_REJECT))
            say("success", f"Rejected {_photos(len(outcome.done))}; {len(outcome.skipped)} skipped.")
        else:
            outcome = review.approve_many(review.pending(findings, BULK_APPROVE))
            say("success", f"Approved {len(outcome.done)} finding(s).")

    # -- summary + last message -----------------------------------------------------
    statuses = [session.status(f) for f in findings]
    st.caption(f"{statuses.count('REJECTED')} rejected · {statuses.count('APPROVED')} approved · "
               f"{statuses.count('pending')} pending. Reject moves a photo into "
               f"`{QUARANTINE_DIR}/` — nothing is erased and every reject can be undone.")
    for warning in session.warnings:
        st.warning(warning)
    if msg_key in state:
        level, text = state.pop(msg_key)
        getattr(st, level, st.info)(text)

    # -- pick a finding -------------------------------------------------------------
    order = sorted(range(len(findings)), key=lambda i: (
        ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO").index(str(findings[i].get("severity", "")).upper())
        if str(findings[i].get("severity", "")).upper() in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
        else 9, -float(findings[i].get("confidence", 0.0) or 0.0)))

    def label(i: int) -> str:
        f = findings[i]
        tag = session.status(f)
        return (f"{f.get('finding_id', '')} · {f.get('severity', '')} · {f.get('attack_class', '')} · "
                f"{Path(str(f.get('affected_asset', ''))).name[:34]}"
                + (f" · {tag}" if tag != "pending" else ""))

    pick = st.selectbox("Finding to review", order, format_func=label, key=f"{key}_rv_pick")
    finding = findings[pick]
    status = session.status(finding)
    left, right = st.columns([1, 2])
    with left:
        shown = _photo_path(session, finding, status)
        if shown is not None:
            st.image(str(shown), width=240)
        else:
            st.caption("No photo to show for this finding.")
    with right:
        st.markdown(f"**{finding.get('attack_class', '')}** · confidence "
                    f"{float(finding.get('confidence', 0.0) or 0.0):.2f}")
        st.write(str(finding.get("reason", "")))
        ok, why = session.can_reject(finding)
        if status == "pending" and not ok:
            st.info(f"This finding cannot be rejected: {why}")

        confirming = state.get(confirm_key) == _key_of(finding)
        if confirming:
            st.warning(f"Move **{Path(str(finding.get('affected_asset', ''))).name}** to "
                       f"`{QUARANTINE_DIR}/`? It leaves the dataset but is not erased.")
            c1, c2 = st.columns(2)
            c1.button("Yes, move to quarantine", type="primary", key=f"{key}_rv_yes",
                      on_click=do_reject, args=(finding,))
            c2.button("Cancel", key=f"{key}_rv_no", on_click=cancel)
        elif status == "pending":
            c1, c2 = st.columns(2)
            c1.button("✅ Approve (photo is fine)", key=f"{key}_rv_ok", on_click=do_approve,
                      args=(finding,))
            if ok:
                c2.button("❌ Reject this photo", key=f"{key}_rv_rej", on_click=ask_reject,
                          args=(_key_of(finding),))
        else:
            st.markdown(f"**Status: {status}**")
            st.button("↩ Undo", key=f"{key}_rv_undo", on_click=do_undo, args=(finding,))

    # -- bulk -------------------------------------------------------------------------
    with st.expander("⚡ Bulk review"):
        to_reject = session.select(findings, BULK_REJECT)
        plan = session.plan_many(to_reject)
        to_approve = session.pending(findings, BULK_APPROVE)
        pending_bulk = state.get(bulk_key)
        if pending_bulk == "reject":
            st.warning(f"Move {_photos(plan.files)} to `{QUARANTINE_DIR}/`? Nothing is erased.")
            b1, b2 = st.columns(2)
            b1.button(f"Yes, move {_photos(plan.files)}", type="primary", key=f"{key}_rv_byes",
                      on_click=do_bulk, args=("reject",))
            b2.button("Cancel", key=f"{key}_rv_bno", on_click=cancel)
        else:
            if plan.files:
                st.button(f"❌ Reject all CRITICAL + HIGH — {_photos(plan.files)}",
                          key=f"{key}_rv_breject", on_click=ask_bulk, args=("reject",))
            else:
                st.caption("No pending CRITICAL / HIGH photo findings to reject.")
            if to_approve:
                st.button(f"✅ Approve all LOW — {len(to_approve)} finding(s)",
                          key=f"{key}_rv_bapprove", on_click=do_bulk, args=("approve",))
            else:
                st.caption("No pending LOW findings.")
            for finding_, why in plan.skipped[:5]:
                st.caption(f"skipped {finding_.get('finding_id')}: {why}")


def _key_of(finding: Mapping[str, Any]) -> str:
    from src.review.store import finding_key
    return finding_key(finding)


def _photo_path(session: ReviewSession, finding: Mapping[str, Any], status: str) -> Optional[Path]:
    """Where the photo for ``finding`` currently is (dataset, or quarantine if rejected)."""
    try:
        if status == "REJECTED":
            key = session._decision_key(finding)  # noqa: SLF001 - same package
            moves = (session._data["decisions"].get(key) or {}).get("moves") or []  # noqa: SLF001
            for move in moves:
                path = session.root / move["to"]
                if move.get("kind") == "image" and path.is_file():
                    return path
            return None
        moves = session.plan(finding)
        return moves[0].source if moves and moves[0].source.suffix.lower() in IMAGE_EXTS else None
    except ReviewError:
        return None
