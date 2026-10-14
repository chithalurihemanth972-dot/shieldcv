"""Home screen navigation, splash, recent panel, small-terminal guard."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.screens.home import HomeScreen
from src.tui.screens.modals import TooSmallScreen
from src.tui.screens.splash import SplashScreen


def _app(tmp_path: Path, **kw) -> ShieldApp:
    return ShieldApp(splash=kw.pop("splash", False), discovery_roots=[tmp_path],
                     reports_dir=tmp_path / "reports", **kw)


@async_test
async def test_home_has_seven_tiles_and_arrow_navigation(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        tiles = list(app.screen.query(".tile"))
        assert [t.id for t in tiles] == ["tile-scan", "tile-audit", "tile-verify",
                                         "tile-drift", "tile-agents", "tile-report",
                                         "tile-backdoor"]
        assert app.focused.id == "tile-scan"
        await pilot.press("right")
        assert app.focused.id == "tile-audit"
        await pilot.press("down")
        assert app.focused.id == "tile-agents"
        await pilot.press("left", "left", "left")
        assert app.focused.id == "tile-drift"


@async_test
async def test_splash_skips_on_any_key(tmp_path):
    app = _app(tmp_path, splash=True)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SplashScreen)
        await pilot.press("x")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))


@async_test
async def test_splash_closes_by_itself(tmp_path):
    app = _app(tmp_path, splash=True)
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen), timeout=4)


@async_test
async def test_recent_panel_lists_reports(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "SHIELD-SCAN-1.json").write_text(json.dumps(
        {"module": "data_scanner", "target": "poisoned", "dataset": {"num_samples": 3},
         "summary": {"verdict": "COMPROMISED", "risk_score": 0.8}}), encoding="utf-8")
    app = _app(tmp_path)
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        recent = app.screen.query_one("#recent")
        await wait_for(pilot, lambda: recent.option_count == 1
                       and recent.get_option_at_index(0).id.endswith("SHIELD-SCAN-1.json"))


@async_test
async def test_small_terminal_shows_notice_and_recovers(tmp_path):
    app = _app(tmp_path, splash=True)
    async with app.run_test(size=(70, 20)) as pilot:
        await wait_for(pilot, lambda: isinstance(app.screen, TooSmallScreen))
        await pilot.resize_terminal(120, 36)
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))


@async_test
async def test_help_modal_opens_and_closes(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HelpModal")
        await pilot.press("escape")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))


def test_launch_without_tty_prints_hint(capsys):
    import src.tui.app as app_module
    assert app_module.main([]) == 2
    assert "shield scan" in capsys.readouterr().out
