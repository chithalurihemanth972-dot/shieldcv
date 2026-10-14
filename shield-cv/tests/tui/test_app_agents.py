"""Agent cards fill live, then the meeting verdict appears; reopen from a saved report."""
from __future__ import annotations

import dataclasses
import threading
from pathlib import Path

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.operations import OPERATIONS_BY_ID
from src.tui.screens.agents import AgentsScreen

OFFICE = {"module": "office_manager", "agents": 2, "mode": "thread", "errors": [],
          "reports": [{"agent_id": "AGENT-01", "contributor": "contributor_a", "risk_score": 0.9,
                       "num_samples": 10, "num_findings": 4, "verdict": "COMPROMISED"},
                      {"agent_id": "AGENT-02", "contributor": "contributor_b", "risk_score": 0.1,
                       "num_samples": 12, "num_findings": 0, "verdict": "CLEAN"}],
          "meeting": {"verdict": "SUSPICIOUS", "narrative": "Alpha stands out.",
                      "recommendations": ["Quarantine contributor_a"]}}


def _dataset(tmp_path: Path) -> Path:
    for name in ("contributor_a", "contributor_b"):
        folder = tmp_path / "ds" / name / "images"
        folder.mkdir(parents=True)
        (folder / "x.jpg").write_bytes(b"x")
    return tmp_path / "ds"


@async_test
async def test_live_cards_then_meeting(tmp_path):
    root = _dataset(tmp_path)
    gate = threading.Event()

    def runner(params, progress):
        progress("embedding", 3, 10, "contributor_a")
        progress("trigger", 1, 2, "contributor_b")
        gate.wait(5)
        progress("finished", 1, 2, "contributor_a")
        progress("finished", 2, 2, "contributor_b")
        progress("meeting", 1, 1)
        return dict(OFFICE)

    spec = dataclasses.replace(OPERATIONS_BY_ID["agents"], runner=runner)
    app = ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")
    async with app.run_test(size=(140, 44)) as pilot:
        app.start_run(spec, {"target": root})
        await wait_for(pilot, lambda: isinstance(app.screen, AgentsScreen))
        screen = app.screen
        await wait_for(pilot, lambda: "contributor_a" in screen.cards
                       and "ResNet-18" in screen.cards["contributor_a"].stage_text)
        assert screen.busy
        gate.set()
        await wait_for(pilot, lambda: screen.status == "finished")
        assert screen.has_class("-done")
        assert "Alpha stands out." in screen.meeting_text
        assert screen.cards["contributor_a"].has_class("-finished")
        assert list((tmp_path / "r").glob("SHIELD-AGENTS-*.json"))


@async_test
async def test_static_from_saved_result(tmp_path):
    app = ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")
    async with app.run_test(size=(140, 44)) as pilot:
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
        app.show_result("agents", dict(OFFICE), None)
        await wait_for(pilot, lambda: isinstance(app.screen, AgentsScreen))
        assert set(app.screen.cards) == {"contributor_a", "contributor_b"}
        assert app.screen.status == "finished"
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
