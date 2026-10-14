"""execute() wires progress, cancellation and saving around any runner."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from src.tui.operations import (OPERATIONS, OPERATIONS_BY_ID, STAGE_LABELS, execute,
                                save_report)
from src.utils.cancel import CancelToken, ScanCancelled

RESULT = {"module": "data_scanner", "summary": {"verdict": "CLEAN"}, "findings": []}


def _spec(runner, **changes):
    return dataclasses.replace(OPERATIONS_BY_ID["scan"], runner=runner, **changes)


def test_execute_forwards_progress_and_saves(tmp_path: Path):
    seen = []

    def runner(params, progress):
        assert params == {"target": "x"}
        progress("loading", 0, 1)
        progress("embedding", 5, 10)
        return dict(RESULT)

    outcome = execute(_spec(runner), {"target": "x"}, lambda *a: seen.append(a),
                      reports_dir=tmp_path)
    assert seen == [("loading", 0, 1, None), ("embedding", 5, 10, None)]
    assert outcome.report_path.parent == tmp_path
    assert outcome.report_path.name.startswith("SHIELD-SCAN-")
    assert json.loads(outcome.report_path.read_text(encoding="utf-8")) == RESULT
    assert outcome.save_error is None and outcome.elapsed >= 0


def test_cancel_stops_the_runner(tmp_path: Path):
    token = CancelToken()
    reached = []

    def runner(params, progress):
        for i in range(100):
            progress("embedding", i, 100)
            reached.append(i)
        return dict(RESULT)

    def on_progress(stage, done, total, detail):
        if done == 2:
            token.cancel()

    with pytest.raises(ScanCancelled):
        execute(_spec(runner), {}, on_progress, token, reports_dir=tmp_path)
    assert reached == [0, 1, 2]
    assert list(tmp_path.iterdir()) == []


def test_cancel_before_start_never_calls_runner():
    token = CancelToken()
    token.cancel()
    with pytest.raises(ScanCancelled):
        execute(_spec(lambda p, g: pytest.fail("runner called")), {}, lambda *a: None, token)


def test_progress_ui_errors_do_not_break_run(tmp_path: Path):
    def runner(params, progress):
        progress("loading", 0, 1)
        return dict(RESULT)

    def exploding(*_a):
        raise RuntimeError("app is closing")

    outcome = execute(_spec(runner), {}, exploding, reports_dir=tmp_path)
    assert outcome.result == RESULT


def test_save_failure_is_reported_not_raised(tmp_path: Path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    outcome = execute(_spec(lambda p, g: dict(RESULT)), {}, lambda *a: None,
                      reports_dir=blocker / "sub")
    assert outcome.report_path is None and outcome.save_error
    assert outcome.result == RESULT


def test_save_report_never_overwrites(tmp_path: Path):
    first, _ = save_report({"a": 1}, "SCAN", tmp_path)
    second, _ = save_report({"a": 2}, "SCAN", tmp_path)
    assert first != second
    assert json.loads(first.read_text())["a"] == 1


def test_self_saving_uses_report_path(tmp_path: Path):
    target = tmp_path / "SCAN-x.json"
    spec = dataclasses.replace(OPERATIONS_BY_ID["report"],
                               runner=lambda p, g: {"report_path": str(target)})
    outcome = execute(spec, {}, lambda *a: None, reports_dir=tmp_path)
    assert outcome.report_path == target
    assert list(tmp_path.iterdir()) == []


def test_registry_is_consistent():
    assert [s.id for s in OPERATIONS] == ["scan", "audit", "verify", "drift", "agents", "report"]
    assert len({s.hotkey for s in OPERATIONS}) == len(OPERATIONS)
    for spec in OPERATIONS:
        assert spec.stages and all(label for _, label in spec.stages)
        for option in spec.options:
            if option.kind == "select":
                assert option.default in [c.value for c in option.choices]
    assert STAGE_LABELS["embedding"]


def test_full_report_needs_a_module():
    with pytest.raises(ValueError, match="at least one"):
        OPERATIONS_BY_ID["report"].runner({}, lambda *a, **k: None)


def test_full_report_phase_never_reports_a_module_complete_mid_module():
    from src.tui.operations import report_phase
    seen = []
    forward = report_phase(lambda *a: seen.append(a), "data")
    forward("loading", 1, 1)
    forward("embedding", 10, 10)
    assert [(s, d, t) for s, d, t, _ in seen] == [("data", 0, 1), ("data", 9, 10)]
    assert seen[1][3] == "ResNet-18 embeddings"
