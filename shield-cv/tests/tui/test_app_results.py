"""Results: verdict banner, findings table, detail with image, filters, export."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.screens.results import ResultsScreen
from src.tui.widgets.findings import FindingDetail, FindingsTable
from src.tui.widgets.image_preview import ImagePreview


def _result(dataset_root: Path) -> dict:
    return {
        "module": "data_scanner", "target": str(dataset_root),
        "dataset": {"num_samples": 2, "root": str(dataset_root), "format": "yolo"},
        "summary": {"verdict": "COMPROMISED", "risk_score": 0.82, "total_findings": 2,
                    "by_severity": {"CRITICAL": 1, "LOW": 1},
                    "by_attack_class": {"TRIGGER_INJECTION": 1, "LABEL_FLIPPING": 1}},
        "contributor_risk": {"contributor_a": {"risk": 0.9, "findings": 2}},
        "findings": [
            {"finding_id": "FIND-001", "severity": "LOW", "attack_class": "LABEL_FLIPPING",
             "affected_asset": "missing.jpg", "confidence": 0.3, "reason": "low one",
             "evidence": {"k": 1}, "recommended_disposition": "ACCEPT"},
            {"finding_id": "FIND-002", "severity": "CRITICAL", "attack_class": "TRIGGER_INJECTION",
             "affected_asset": "a1.png", "confidence": 0.97, "reason": "bright patch bottom-right",
             "evidence": {"patch_energy": 9.1, "member_files": ["a1.png"]},
             "recommended_disposition": "QUARANTINE"},
        ],
        "limitations": ["demo limitation"],
    }


def _dataset(tmp_path: Path) -> Path:
    folder = tmp_path / "ds" / "contributor_a" / "images"
    folder.mkdir(parents=True)
    Image.new("RGB", (32, 32), (200, 30, 30)).save(folder / "a1.png")
    return tmp_path / "ds"


async def _open(pilot, app, result, report_path=None) -> ResultsScreen:
    await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
    app.show_result("scan", result, report_path, 3.2)
    await wait_for(pilot, lambda: isinstance(app.screen, ResultsScreen))
    return app.screen


def _app(tmp_path):
    return ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")


@async_test
async def test_banner_and_table_sorted_by_severity(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(_dataset(tmp_path)))
        assert screen.head.verdict == "COMPROMISED"
        table = screen.query_one(FindingsTable)
        assert table.row_count == 2
        assert table.current()["finding_id"] == "FIND-002"


@async_test
async def test_detail_shows_reason_and_image_preview(tmp_path):
    root = _dataset(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(root))
        detail = screen.query_one(FindingDetail)
        preview = screen.query_one(ImagePreview)
        await wait_for(pilot, lambda: preview.shown_paths or preview.messages)
        assert "bright patch bottom-right" in detail.text
        assert preview.shown_paths == [root / "contributor_a" / "images" / "a1.png"]


@async_test
async def test_missing_asset_does_not_break_detail(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(_dataset(tmp_path)))
        table = screen.query_one(FindingsTable)
        table.focus()
        await pilot.press("down")
        await wait_for(pilot, lambda: "low one" in screen.query_one(FindingDetail).text)
        assert screen.query_one(ImagePreview).shown_paths == []


@async_test
async def test_unreadable_image_shows_message(tmp_path):
    root = _dataset(tmp_path)
    (root / "contributor_a" / "images" / "a1.png").write_bytes(b"not a png")
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(root))
        preview = screen.query_one(ImagePreview)
        await wait_for(pilot, lambda: bool(preview.messages))
        assert "preview unavailable" in preview.messages[0]


@async_test
async def test_severity_filter_cycles(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(_dataset(tmp_path)))
        table = screen.query_one(FindingsTable)
        expected = [("CRITICAL", 1), ("HIGH", 0), ("MEDIUM", 0), ("LOW", 1), (None, 2)]
        for severity, rows in expected:
            await pilot.press("f")
            assert (screen.severity_filter, table.row_count) == (severity, rows)


@async_test
async def test_inconclusive_banner(tmp_path):
    result = _result(_dataset(tmp_path))
    result["dataset"]["num_samples"] = 0
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, result)
        assert screen.head.verdict == "INCONCLUSIVE"


@async_test
async def test_escape_goes_home(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        await _open(pilot, app, _result(_dataset(tmp_path)))
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")


@async_test
async def test_report_result_has_briefing_tab(tmp_path):
    report = {"schema_version": "1", "summary": {"verdict": "COMPROMISED", "risk_score": 0.99,
                                                 "by_severity": {"HIGH": 1}},
              "findings": [], "modules": {"data_scanner": {}},
              "immunity": {"score": 12.5, "band": "COMPROMISED",
                           "components": {"data": {"label": "Data", "score": 20.0}}},
              "briefing": {"text": "Quarantine contributor alpha."},
              "threat_story": {"stories": [{"title": "Coordinated attack", "pattern": "X"}]}}
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
        app.show_result("report", report, None)
        await wait_for(pilot, lambda: isinstance(app.screen, ResultsScreen))
        assert app.screen.query_one("#tab-briefing") is not None


@async_test
async def test_image_sits_between_reason_and_evidence(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(_dataset(tmp_path)))
        ids = [child.id or type(child).__name__ for child in screen.query_one(FindingDetail).children]
        assert ids == ["detail-body", "ImagePreview", "detail-evidence"]
