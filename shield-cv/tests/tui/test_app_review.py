"""Approve / Reject / Undo / Bulk on the results screen."""
from __future__ import annotations

from pathlib import Path

from helpers import async_test, wait_for
from src.review.store import ReviewSession
from src.tui.app import ShieldApp
from src.tui.screens.results import ResultsScreen
from src.tui.widgets.findings import FindingDetail, FindingsTable
from test_app_results import _dataset, _result


def _app(tmp_path):
    return ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")


async def _open(pilot, app, result, op_id="scan") -> ResultsScreen:
    await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
    app.show_result(op_id, result, None, 1.0)
    await wait_for(pilot, lambda: isinstance(app.screen, ResultsScreen))
    table = app.screen.query_one(FindingsTable)
    await wait_for(pilot, lambda: table.current() is not None)
    return app.screen


def _photo(root: Path) -> Path:
    return root / "contributor_a" / "images" / "a1.png"


def _q(root: Path) -> Path:
    return ReviewSession(root).quarantine


def _quarantined(root: Path) -> Path:
    return _q(root) / "contributor_a" / "images" / "a1.png"


def _status_cells(table: FindingsTable) -> list:
    return [str(table.get_row_at(i)[-1]).strip() for i in range(table.row_count)]


@async_test
async def test_reject_asks_first_then_quarantines_and_marks_the_row(tmp_path):
    root = _dataset(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(root))
        table = screen.query_one(FindingsTable)
        assert table.current()["finding_id"] == "FIND-002"   # the CRITICAL one
        await pilot.press("x")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        assert _photo(root).exists()                           # nothing moved yet
        await pilot.press("y")
        await wait_for(pilot, lambda: _quarantined(root).is_file())
        assert not _photo(root).exists()
        await wait_for(pilot, lambda: "REJECTED" in _status_cells(table))


@async_test
async def test_saying_no_changes_nothing(tmp_path):
    root = _dataset(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        await _open(pilot, app, _result(root))
        await pilot.press("x")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        await pilot.press("n")
        await wait_for(pilot, lambda: isinstance(app.screen, ResultsScreen))
        assert _photo(root).exists() and not _q(root).exists()


@async_test
async def test_undo_puts_the_photo_back(tmp_path):
    root = _dataset(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(root))
        await pilot.press("x")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        await pilot.press("y")
        await wait_for(pilot, lambda: _quarantined(root).is_file())
        await pilot.press("u")
        await wait_for(pilot, lambda: _photo(root).is_file())
        table = screen.query_one(FindingsTable)
        await wait_for(pilot, lambda: "REJECTED" not in _status_cells(table))


@async_test
async def test_approve_records_it_and_keeps_the_photo(tmp_path):
    root = _dataset(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(root))
        await pilot.press("a")
        table = screen.query_one(FindingsTable)
        await wait_for(pilot, lambda: "APPROVED" in _status_cells(table))
        assert _photo(root).exists() and not _quarantined(root).exists()


@async_test
async def test_reject_on_an_unmovable_finding_explains_why_and_changes_nothing(tmp_path):
    root = _dataset(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(root))
        table = screen.query_one(FindingsTable)
        table.focus()
        await pilot.press("down")                      # FIND-001: missing.jpg
        await wait_for(pilot, lambda: table.current()["finding_id"] == "FIND-001")
        await pilot.press("x")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ResultsScreen)   # no confirm dialog for a refused action
        assert "not found" in screen.last_review_message
        assert _photo(root).exists()


@async_test
async def test_detail_pane_shows_the_review_state(tmp_path):
    root = _dataset(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(root))
        detail = screen.query_one(FindingDetail)
        await wait_for(pilot, lambda: "pending" in detail.text.lower())
        await pilot.press("a")
        await wait_for(pilot, lambda: "approved" in detail.text.lower())


@async_test
async def test_bulk_reject_critical_and_high_shows_the_count_and_needs_confirmation(tmp_path):
    root = _dataset(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        await _open(pilot, app, _result(root))
        await pilot.press("b")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "BulkReviewModal")
        assert "1 photo" in app.screen.summary_text          # only a1.png is rejectable
        await pilot.press("r")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        assert "1 photo" in app.screen.message and _photo(root).exists()
        await pilot.press("y")
        await wait_for(pilot, lambda: _quarantined(root).is_file())


@async_test
async def test_review_is_unavailable_for_non_dataset_results(tmp_path):
    app = _app(tmp_path)
    chain = {"module": "crypto_chain", "target": "chain.json", "num_records": 3,
             "chain_valid": False, "first_break_index": 1, "summary": {"risk_score": 0.9},
             "findings": [{"finding_id": "P1", "severity": "HIGH", "attack_class": "CHAIN_BREAK",
                           "affected_asset": "record-1", "confidence": 0.9, "reason": "x"}]}
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, chain, op_id="verify")
        await pilot.press("x")
        await pilot.pause(0.2)
        assert "dataset" in screen.last_review_message.lower()
        assert isinstance(app.screen, ResultsScreen)
