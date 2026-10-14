"""Drive the real console headless against demo data and save SVG screenshots.

Run:  python tests/tui/e2e_screens.py
Not collected by pytest (no test_ prefix): it runs real engines and takes minutes.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.tui.app import ShieldApp  # noqa: E402
from src.tui.operations import OPERATIONS_BY_ID  # noqa: E402
from src.tui.screens.agents import AgentsScreen  # noqa: E402
from src.tui.screens.results import ResultsScreen  # noqa: E402

OUT = ROOT / "output" / "tui_screens"
JOBS = [
    ("scan", {"target": ROOT / "demo/data/poisoned", "max_images": 100}),
    ("audit", {"target": ROOT / "demo/models/backdoored_model_scripted.pt", "reference": None,
               "neural_cleanse": True}),
    ("verify", {"target": ROOT / "demo/records/tampered_replay.json"}),
    ("agents", {"target": ROOT / "demo/data/poisoned"}),
]


async def wait(pilot, predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await pilot.pause(0.2)
        if predicate():
            return True
    return False


def done(app, op_id):
    if op_id == "agents":
        return isinstance(app.screen, AgentsScreen) and app.screen.status != "running"
    return isinstance(app.screen, ResultsScreen)


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    app = ShieldApp(splash=False)
    failures = 0
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause(1.0)
        app.save_screenshot(path=str(OUT), filename="01-home.svg")
        for index, (op_id, params) in enumerate(JOBS, start=2):
            started = time.monotonic()
            app.start_run(OPERATIONS_BY_ID[op_id], params)
            await pilot.pause(3.0)
            app.save_screenshot(path=str(OUT), filename=f"{index:02d}-{op_id}-running.svg")
            ok = await wait(pilot, lambda: done(app, op_id), 1200)
            took = time.monotonic() - started
            if not ok:
                failures += 1
                print(f"FAIL {op_id}: no result after {took:.0f}s (screen={type(app.screen).__name__})",
                      flush=True)
                app.save_screenshot(path=str(OUT), filename=f"{index:02d}-{op_id}-FAILED.svg")
                app.go_home()
                continue
            await pilot.pause(1.5)
            if op_id == "agents":
                print(f"ok   {op_id}: status={app.screen.status} cards={len(app.screen.cards)} "
                      f"in {took:.0f}s", flush=True)
            else:
                head = app.screen.head
                print(f"ok   {op_id}: {head.verdict} risk={head.risk} in {took:.0f}s", flush=True)
            app.save_screenshot(path=str(OUT), filename=f"{index:02d}-{op_id}-results.svg")
            app.go_home()
            await pilot.pause(0.5)
    print(f"screenshots: {OUT}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
