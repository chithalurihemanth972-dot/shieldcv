"""The guided backdoor demo: five steps, real data, plain words."""
from __future__ import annotations

import threading
from pathlib import Path

from PIL import Image

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.backdoor_demo import DemoData, Showcase
from src.tui.screens.backdoor import BackdoorDemoScreen
from src.tui.screens.home import HomeScreen


def _fake_demo(tmp_path: Path) -> DemoData:
    shows = []
    for class_id, name in ((0, "A"), (1, "B"), (3, "D")):
        normal, trig = tmp_path / f"n{name}.png", tmp_path / f"t{name}.png"
        Image.new("RGB", (64, 64), (90, 90, 90)).save(normal)
        Image.new("RGB", (64, 64), (200, 200, 200)).save(trig)
        shows.append(Showcase(class_id, normal, trig, class_id, class_id, class_id, 2))
    return DemoData(target_class=2, samples=64, clean_accuracy=1.0, backdoored_accuracy=0.8,
                    clean_fooled=0.0, backdoored_fooled=1.0, showcase=tuple(shows))


BACKDOORED = {"findings": [{"attack_class": "MODEL_BACKDOOR"}],
              "neural_cleanse": {"flagged_classes": [
                  {"target_class": 2, "mask_l1": 9.5, "median_mask_l1": 26.0}]}}
CLEAN = {"findings": [], "neural_cleanse": {"flagged_classes": []}}


def _app(tmp_path: Path) -> ShieldApp:
    return ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")


async def _open(pilot, app, tmp_path, audit=None, gate=None):
    def fake_audit(model_path, progress):
        progress("weights", 1, 2)
        if gate is not None:
            gate.wait(5)
        return dict(BACKDOORED if "backdoored" in str(model_path) else CLEAN)

    await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
    app.push_screen(BackdoorDemoScreen(demo=_fake_demo(tmp_path), audit=audit or fake_audit))
    await wait_for(pilot, lambda: isinstance(app.screen, BackdoorDemoScreen))
    await wait_for(pilot, lambda: app.screen.ready)
    return app.screen


@async_test
async def test_home_has_a_backdoor_demo_tile_with_hotkey_b(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        assert app.screen.query("#tile-backdoor")
        await pilot.press("b")
        await wait_for(pilot, lambda: isinstance(app.screen, BackdoorDemoScreen))


@async_test
async def test_story_walks_five_steps_in_plain_words(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, tmp_path)
        assert screen.step == 1 and "student" in screen.text.lower()
        await pilot.press("right")
        assert screen.step == 2 and screen.shown_images == 3
        await pilot.press("right")
        assert screen.step == 3 and "Category C" in screen.text
        assert "100%" in screen.text and "0%" in screen.text      # the real fooled rates
        await pilot.press("left")
        assert screen.step == 2
        for _ in range(3):
            await pilot.press("right")
        assert screen.step == 5
        await pilot.press("right")
        assert screen.step == 5  # does not run off the end


@async_test
async def test_no_jargon_on_screen(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, tmp_path)
        seen = []
        for _ in range(5):
            seen.append(screen.text)
            await pilot.press("right")
        text = " ".join(seen).lower()
        for word in ("neural cleanse", "logit", "tensor", "embedding", "l1"):
            assert word not in text


@async_test
async def test_step_five_runs_the_audit_on_both_models_and_explains_it(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, tmp_path)
        for _ in range(4):
            await pilot.press("right")
        await wait_for(pilot, lambda: screen.audit_done, timeout=8)
        assert "BACKDOOR FOUND" in screen.text and "NO BACKDOOR FOUND" in screen.text
        assert "Category C" in screen.text


@async_test
async def test_escape_during_the_audit_stops_it_and_goes_home(tmp_path):
    gate = threading.Event()
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, tmp_path, gate=gate)
        for _ in range(4):
            await pilot.press("right")
        await wait_for(pilot, lambda: screen.busy)
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        await pilot.press("y")
        gate.set()
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))


@async_test
async def test_a_failing_audit_is_explained_not_crashed(tmp_path):
    def broken(model_path, progress):
        raise RuntimeError("model file missing")

    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, tmp_path, audit=broken)
        for _ in range(4):
            await pilot.press("right")
        await wait_for(pilot, lambda: screen.audit_error, timeout=8)
        assert "model file missing" in screen.audit_error
        assert "could not" in screen.text.lower()
