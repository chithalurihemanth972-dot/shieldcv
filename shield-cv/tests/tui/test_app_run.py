"""Live stages, cancel with confirmation, error panel with retry/back."""
from __future__ import annotations

import dataclasses
import threading
import time
from pathlib import Path

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.operations import OPERATIONS_BY_ID
from src.tui.screens.run import RunScreen
from src.tui.widgets.stage_progress import StageProgress

RESULT = {"module": "data_scanner", "target": "x", "dataset": {"num_samples": 4},
          "summary": {"verdict": "CLEAN", "risk_score": 0.1, "total_findings": 0},
          "findings": []}


def _app(tmp_path: Path) -> ShieldApp:
    return ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")


def _spec(runner):
    return dataclasses.replace(OPERATIONS_BY_ID["scan"], runner=runner)


@async_test
async def test_stages_advance_and_results_open(tmp_path):
    gate = threading.Event()

    def runner(params, progress):
        progress("loading", 1, 1)
        progress("embedding", 5, 10)
        gate.wait(5)
        progress("trigger", 1, 1)
        return dict(RESULT)

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.start_run(_spec(runner), {"target": tmp_path})
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        stages = app.screen.query_one(StageProgress)
        await wait_for(pilot, lambda: stages.state("embedding") == "running")
        assert stages.state("loading") == "done"
        assert stages.state("trigger") == "pending"
        gate.set()
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ResultsScreen")
        assert list((tmp_path / "r").glob("SHIELD-SCAN-*.json"))


@async_test
async def test_escape_asks_then_cancels(tmp_path):
    stopped = []

    def runner(params, progress):
        try:
            for i in range(400):
                progress("embedding", i, 400)
                time.sleep(0.01)
        except BaseException:
            stopped.append(True)
            raise
        return dict(RESULT)

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.start_run(_spec(runner), {"target": tmp_path})
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        run_screen = app.screen
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        await pilot.press("y")
        await wait_for(pilot, lambda: bool(stopped))
        await wait_for(pilot, lambda: app.screen is not run_screen)
        assert run_screen.status == "cancelled"
        assert not list((tmp_path / "r").glob("*.json"))


@async_test
async def test_escape_then_no_keeps_running(tmp_path):
    gate = threading.Event()

    def runner(params, progress):
        progress("loading", 0, 1)
        gate.wait(5)
        return dict(RESULT)

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.start_run(_spec(runner), {"target": tmp_path})
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        await pilot.press("n")
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        assert app.screen.status == "running"
        gate.set()
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ResultsScreen")


@async_test
async def test_quit_during_run_asks_first(tmp_path):
    gate = threading.Event()

    def runner(params, progress):
        progress("loading", 0, 1)
        gate.wait(5)
        return dict(RESULT)

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.start_run(_spec(runner), {"target": tmp_path})
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        await pilot.press("q")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        await pilot.press("n")
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        assert app.busy
        gate.set()


@async_test
async def test_error_panel_retry_and_back(tmp_path):
    calls = []

    def runner(params, progress):
        calls.append(1)
        progress("loading", 0, 1)
        raise RuntimeError("disk on fire")

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.start_run(_spec(runner), {"target": tmp_path})
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen)
                       and app.screen.status == "failed")
        screen = app.screen
        assert "RuntimeError: disk on fire" in screen.error_text
        assert screen.query_one(StageProgress).state("loading") == "failed"
        await pilot.press("r")
        await wait_for(pilot, lambda: len(calls) == 2 and screen.status == "failed")
        await pilot.press("b")
        await wait_for(pilot, lambda: app.screen is not screen)
