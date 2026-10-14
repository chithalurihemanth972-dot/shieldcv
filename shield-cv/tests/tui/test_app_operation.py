"""Pick targets and options without typing; Run is gated on validity."""
from __future__ import annotations

from pathlib import Path

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.operations import OPERATIONS_BY_ID
from src.tui.screens.operation import OperationScreen, default_params
from src.tui.widgets.target_picker import TargetPicker


def _dataset(root: Path, name: str) -> Path:
    folder = root / name / "contributor_a" / "images"
    folder.mkdir(parents=True)
    (folder / "a.jpg").write_bytes(b"x")
    return root / name


def _model(root: Path, name: str) -> Path:
    (root / "models").mkdir(exist_ok=True)
    path = root / "models" / name
    path.write_bytes(b"0" * 10)
    return path


def _app(tmp_path: Path, started: list) -> ShieldApp:
    app = ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")
    app.start_run = lambda spec, params: started.append((spec.id, params))
    return app


async def _open(pilot, app, key: str) -> OperationScreen:
    await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
    await pilot.press(key)
    await wait_for(pilot, lambda: isinstance(app.screen, OperationScreen))
    await wait_for(pilot, lambda: all(p.loaded for p in app.screen.query(TargetPicker)))
    await pilot.pause(0.1)
    return app.screen


@async_test
async def test_scan_form_picks_first_dataset_and_runs(tmp_path):
    a = _dataset(tmp_path, "alpha_set")
    _dataset(tmp_path, "beta_set")
    started: list = []
    app = _app(tmp_path, started)
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "d")
        assert screen.query_one("#target", TargetPicker).selected == a
        assert screen.problem() is None
        assert not screen.query_one("#op-run").disabled
        await pilot.press("ctrl+r")
        await wait_for(pilot, lambda: bool(started))
        op_id, params = started[0]
        assert op_id == "scan" and params == {"target": a, "max_images": None}


@async_test
async def test_arrow_changes_selection(tmp_path):
    _dataset(tmp_path, "alpha_set")
    b = _dataset(tmp_path, "beta_set")
    app = _app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "d")
        screen.query_one("#target OptionList").focus()
        await pilot.press("down")
        assert screen.query_one("#target", TargetPicker).selected == b


@async_test
async def test_filter_narrows_the_list(tmp_path):
    _dataset(tmp_path, "alpha_set")
    b = _dataset(tmp_path, "beta_set")
    app = _app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "d")
        screen.query_one("#target OptionList").focus()
        await pilot.press("slash", "b", "e", "t")
        await wait_for(pilot, lambda: screen.query_one("#target", TargetPicker).selected == b)


@async_test
async def test_no_targets_disables_run(tmp_path):
    app = _app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "m")
        assert screen.query_one("#target", TargetPicker).selected is None
        assert "Pick" in screen.problem()
        assert screen.query_one("#op-run").disabled


@async_test
async def test_audit_options_reference_optional_and_switch(tmp_path):
    m = _model(tmp_path, "suspect.pt")
    app = _app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "m")
        assert screen.params() == {"target": m, "reference": None, "neural_cleanse": True}


@async_test
async def test_report_requires_a_module(tmp_path):
    app = _app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "r")
        assert "at least one" in screen.problem()


@async_test
async def test_escape_returns_home(tmp_path):
    app = _app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "v")
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")


def test_default_params():
    assert default_params(OPERATIONS_BY_ID["drift"]) == {"max_images": 120}
    assert default_params(OPERATIONS_BY_ID["audit"]) == {"neural_cleanse": True}
