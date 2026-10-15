"""Headlines read every module's verdict; recent reports tolerate junk."""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.tui.recent import humanize_age, recent_reports
from src.tui.verdict import details_rows, headline, op_id_for

SCAN = {"module": "data_scanner", "target": "C:/x/demo/data/poisoned",
        "dataset": {"num_samples": 10, "root": "C:/x/demo/data/poisoned"},
        "summary": {"verdict": "COMPROMISED", "risk_score": 0.82, "total_findings": 7},
        "findings": []}
CHAIN = {"module": "crypto_chain", "target": "chain.json", "num_records": 5,
         "chain_valid": False, "first_break_index": 3, "summary": {"risk_score": 0.9}}


def test_scan_headline():
    h = headline("scan", SCAN)
    assert (h.verdict, h.tone, h.risk) == ("COMPROMISED", "danger", 0.82)
    assert "7 findings" in h.note


def test_verify_headline_uses_chain_validity():
    h = headline("verify", CHAIN)
    assert (h.verdict, h.tone) == ("BROKEN", "danger")
    assert "first break at record 3" in h.note
    assert headline("verify", {**CHAIN, "chain_valid": True}).verdict == "VALID"


def test_drift_and_agents_and_report():
    assert headline("drift", {"module": "drift_detector", "shift_type": "NATURAL_OPERATIONAL_DRIFT",
                              "risk_score": 0.2, "characterization": "dusk"}).tone == "ok"
    agents = {"module": "office_manager", "reports": [{}], "meeting": {"verdict": "SUSPICIOUS"}}
    assert headline("agents", agents).verdict == "SUSPICIOUS"
    report = {"schema_version": "1", "summary": {"verdict": "COMPROMISED", "risk_score": 0.99},
              "immunity": {"score": 12.5, "band": "COMPROMISED"}}
    h = headline("report", report)
    assert h.verdict == "COMPROMISED" and "immunity 12.5/100" in h.note


def test_failed_assessment_is_inconclusive_not_clean():
    empty = {**SCAN, "dataset": {"num_samples": 0}, "summary": {"verdict": "CLEAN"}}
    h = headline("scan", empty)
    assert (h.verdict, h.tone, h.risk) == ("INCONCLUSIVE", "warn", None)


def test_unknown_verdict_is_info():
    assert headline("scan", {**SCAN, "summary": {"verdict": "WEIRD"}}).tone == "info"


def test_op_id_for():
    assert op_id_for(SCAN) == "scan"
    assert op_id_for(CHAIN) == "verify"
    assert op_id_for({"schema_version": "1"}) == "report"
    assert op_id_for({"module": "nope"}) is None


def test_details_rows_scan():
    rows = dict(details_rows("scan", SCAN))
    assert rows["Samples"] == "10"
    assert dict(details_rows("scan", {**SCAN, "backbone": "resnet18"}))["Backbone"] == "resnet18"


def _write(folder: Path, name: str, payload, mtime: float) -> Path:
    path = folder / name
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_recent_reports_newest_first_and_skip_junk(tmp_path: Path):
    _write(tmp_path, "SHIELD-SCAN-1.json", SCAN, 1000)
    _write(tmp_path, "SHIELD-VERIFY-2.json", CHAIN, 2000)
    _write(tmp_path, "broken.json", "{oops", 3000)
    _write(tmp_path, "list.json", [1, 2], 4000)
    items = recent_reports(5, tmp_path)
    assert [i.op_id for i in items] == ["verify", "scan"]
    assert items[0].verdict == "BROKEN" and items[0].kind == "VERIFY"
    assert items[1].target == "poisoned" and items[1].risk == 0.82
    assert len(recent_reports(1, tmp_path)) == 1


def test_recent_reports_missing_dir(tmp_path: Path):
    assert recent_reports(5, tmp_path / "nope") == []


def test_humanize_age():
    assert humanize_age(5) == "just now"
    assert humanize_age(125) == "2m ago"
    assert humanize_age(7200) == "2h ago"
    assert humanize_age(3 * 86400) == "3d ago"


def test_error_verdict_is_a_warning_and_minor_anomalies_is_info():
    assert headline("scan", {**SCAN, "summary": {"verdict": "ERROR"}}).tone == "warn"
    assert headline("scan", {**SCAN, "summary": {"verdict": "MINOR_ANOMALIES"}}).tone == "info"
