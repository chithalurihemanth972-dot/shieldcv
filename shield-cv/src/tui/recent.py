"""The home screen's Recent results panel."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.tui.discovery import ROOT
from src.tui.verdict import headline, op_id_for, target_name

REPORTS_DIR = ROOT / "output" / "reports"
KIND_LABEL = {"scan": "SCAN", "audit": "AUDIT", "verify": "VERIFY", "drift": "DRIFT",
              "agents": "AGENTS", "report": "REPORT"}


@dataclass(frozen=True)
class RecentItem:
    """One saved report, summarised."""

    path: Path
    op_id: str
    kind: str
    target: str
    verdict: str
    tone: str
    risk: Optional[float]
    modified: float


def load_report(path: Path) -> Dict[str, Any]:
    """Read a saved report; raises ``ValueError`` if it is not a report object."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable report {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"not a report object: {path}")
    return data


def recent_reports(n: int = 5, reports_dir: Optional[Path] = None) -> List[RecentItem]:
    """The ``n`` newest readable reports, newest first."""
    folder = Path(reports_dir) if reports_dir is not None else REPORTS_DIR
    try:
        files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    items: List[RecentItem] = []
    for path in files:
        if len(items) >= n:
            break
        try:
            data = load_report(path)
        except ValueError:
            continue
        op_id = op_id_for(data)
        if op_id is None:
            continue
        head = headline(op_id, data)
        items.append(RecentItem(path=path, op_id=op_id, kind=KIND_LABEL[op_id],
                                target=target_name(data), verdict=head.verdict, tone=head.tone,
                                risk=head.risk, modified=path.stat().st_mtime))
    return items


def humanize_age(seconds: float) -> str:
    """``5m ago`` style age."""
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def age_of(item: RecentItem) -> str:
    """Age of a recent item relative to now."""
    return humanize_age(time.time() - item.modified)
