"""Command palette: operations, quick-start targets, recent reports, launchers."""

from __future__ import annotations

from functools import partial
from typing import List, Tuple

from textual.command import Hit, Hits, Provider

from src.tui.recent import recent_reports
from src.tui.threads import run_daemon

QUICK = (("scan", "dataset", "Scan"), ("audit", "model", "Audit"), ("verify", "records", "Verify"))
LAUNCH = (("dashboard", "Launch Streamlit dashboard"), ("lab", "Launch Attack Lab"),
          ("demo", "Launch guided demo"))


class ShieldCommands(Provider):
    """Everything the console can do, fuzzy-searchable."""

    async def startup(self) -> None:
        self._quick: List[Tuple[str, str, str]] = []
        for op_id, kind, verb in QUICK:
            found = await run_daemon(self.app.candidates, kind)
            self._quick += [(op_id, f"{verb} {c.label}", str(c.path)) for c in found]
        self._recent = await run_daemon(recent_reports, 5, self.app.reports_dir)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        app = self.app
        entries = [(f"Open: {s.title}", partial(app.open_operation, s.id), s.blurb)
                   for s in app.operations.values()]
        entries += [(text, partial(app.quick_run, op_id, path), "Run now with default options")
                    for op_id, text, path in getattr(self, "_quick", [])]
        entries += [(f"Open report: {r.kind} {r.target} {r.verdict}",
                     partial(app.open_report, r.path), str(r.path))
                    for r in getattr(self, "_recent", [])]
        entries += [(text, partial(app.action_launch, key), "Leaves the console until you exit")
                    for key, text in LAUNCH]
        for text, callback, help_text in entries:
            score = matcher.match(text)
            if score > 0:
                yield Hit(score, matcher.highlight(text), callback, help=help_text)
