"""``shield review``: approve or reject findings from a saved report.

A dry run by default: nothing moves unless ``--yes`` is given, so a script can
never quarantine photos by accident. Reject is always reversible (``--undo``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from rich.console import Console
from rich.table import Table

from src.review.store import QUARANTINE_DIR, ReviewError, ReviewSession

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
EXIT_OK, EXIT_NOTHING, EXIT_ERROR = 0, 1, 3


def dataset_root_of(report: Dict[str, Any]) -> Optional[Path]:
    """The dataset folder a report was made from (module or full report)."""
    target = report.get("target")
    if isinstance(target, dict):
        target = target.get("dataset")
    raw = (report.get("dataset") or {}).get("root") or target
    if isinstance(raw, str) and raw and Path(raw).is_dir():
        return Path(raw)
    return None


def _severities(text: str) -> List[str]:
    chosen = [part.strip().upper() for part in text.split(",") if part.strip()]
    for sev in chosen:
        if sev not in SEVERITIES:
            raise ValueError(f"unknown severity '{sev}' (use: {', '.join(s.lower() for s in SEVERITIES)})")
    return chosen


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shield review",
        description="Approve or reject findings. Reject moves the flagged photo into "
                    f"<dataset>/{QUARANTINE_DIR}/ (undoable). Dry run unless --yes.")
    parser.add_argument("report", help="saved report JSON (from shield scan / report)")
    parser.add_argument("--dataset", help="dataset folder (default: taken from the report)")
    parser.add_argument("--reject", metavar="SEVERITIES",
                        help="quarantine pending photo findings of these severities, e.g. critical,high")
    parser.add_argument("--approve", metavar="SEVERITIES",
                        help="mark pending findings of these severities as checked and fine")
    parser.add_argument("--yes", action="store_true", help="really do it (default is a dry run)")
    parser.add_argument("--undo", metavar="all", nargs="?", const="all",
                        help="restore every rejected photo (and clear approvals)")
    parser.add_argument("--list", action="store_true", help="show every finding and its status")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    console = Console(highlight=False, soft_wrap=True)
    args = build_parser().parse_args(list(sys.argv[2:] if argv is None else argv))
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        console.print(f"Could not read the report: {exc}")
        return EXIT_ERROR
    if not isinstance(report, dict):
        console.print("That file is not a SHIELD report.")
        return EXIT_ERROR
    root = Path(args.dataset) if args.dataset else dataset_root_of(report)
    if root is None:
        console.print("This report does not say which dataset folder it came from "
                      "(only dataset scans can be reviewed). Use --dataset <folder>.")
        return EXIT_ERROR
    try:
        session = ReviewSession(root)
        reject_sev = _severities(args.reject) if args.reject else []
        approve_sev = _severities(args.approve) if args.approve else []
    except (ReviewError, ValueError) as exc:
        console.print(str(exc))
        return EXIT_ERROR
    findings: List[Dict[str, Any]] = [f for f in report.get("findings") or [] if isinstance(f, dict)]
    for warning in session.warnings:
        console.print(f"[yellow]! {warning}[/yellow]")

    if args.undo:
        restored = session.undo_all()
        photos = sum(1 for d in restored if d.moves)
        console.print(f"Undo: restored {photos} photo{'s' if photos != 1 else ''} from "
                      f"{QUARANTINE_DIR}/ and cleared {len(restored)} decision(s).")
        for warning in session.warnings:
            console.print(f"[yellow]! {warning}[/yellow]")
        return EXIT_OK

    if args.list or not (reject_sev or approve_sev):
        table = Table(show_header=True, header_style="bold")
        for column in ("ID", "Severity", "Attack class", "Asset", "Status"):
            table.add_column(column)
        for finding in findings:
            table.add_row(str(finding.get("finding_id", "")), str(finding.get("severity", "")),
                          str(finding.get("attack_class", "")),
                          str(finding.get("affected_asset", ""))[:40], session.status(finding))
        console.print(table)
        if not (reject_sev or approve_sev):
            console.print("Use --reject critical,high and/or --approve low "
                          "(add --yes to apply).")
        return EXIT_OK

    to_reject = session.select(findings, reject_sev) if reject_sev else []
    reject_ids = {id(f) for f in to_reject}
    to_approve = [f for f in session.pending(findings, approve_sev) if id(f) not in reject_ids] \
        if approve_sev else []
    unrejectable = []
    if reject_sev:  # only real refusals; a duplicate finding on a photo we handle is not one
        for f in session.pending(findings, reject_sev):
            ok, why = session.can_reject(f)
            if not ok:
                unrejectable.append((f, why))

    if not to_reject and not to_approve:
        console.print("Nothing to do: no pending findings match.")
        for finding, why in unrejectable:
            console.print(f"  skipped {finding.get('finding_id')}: {why}")
        return EXIT_NOTHING

    plan = session.plan_many(to_reject)
    if not args.yes:
        console.print(f"Dry run: would quarantine {plan.files} photos "
                      f"(+{plan.labels} label files) and approve {len(to_approve)} finding(s).")
        for finding, why in plan.skipped + unrejectable:
            console.print(f"  skipped {finding.get('finding_id')}: {why}")
        console.print("Nothing was changed. Add --yes to apply.")
        return EXIT_OK

    rejected = session.reject_many(to_reject)
    approved = session.approve_many(to_approve)
    covered = sum(1 for f in findings if session.status(f) == "REJECTED") - len(rejected.done)
    extra = f" (+{covered} other findings about the same photos)" if covered > 0 else ""
    console.print(f"{len(rejected.done)} rejected (moved to {QUARANTINE_DIR}/){extra}, "
                  f"{len(approved.done)} approved.")
    for finding, why in rejected.skipped + approved.skipped + unrejectable:
        console.print(f"  skipped {finding.get('finding_id')}: {why}")
    for decision in rejected.done:
        for warning in decision.warnings:
            console.print(f"[yellow]! {warning}[/yellow]")
            break
    console.print(f"Undo any time:  shield review {args.report} --undo")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
