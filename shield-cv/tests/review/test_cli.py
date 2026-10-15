"""shield review: a dry run unless --yes; never touches anything unexpected."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.review.cli import main
from src.review.store import ReviewSession


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _finding(asset, severity, fid, attack="TRIGGER_INJECTION", **extra):
    base = {"finding_id": fid, "severity": severity, "attack_class": attack,
            "affected_asset": asset, "contributor": None, "asset_type": "image",
            "reason": "r", "evidence": {}}
    base.update(extra)
    return base


@pytest.fixture()
def project(tmp_path: Path):
    root = tmp_path / "ds"
    for name in ("c1", "c2", "h1", "l1"):
        _write(root / "contributor_a" / "images" / f"{name}.jpg", name.encode())
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "module": "data_scanner", "dataset": {"root": str(root)},
        "findings": [_finding("c1.jpg", "CRITICAL", "F1"), _finding("c2.jpg", "CRITICAL", "F2"),
                     _finding("h1.jpg", "HIGH", "F3"), _finding("l1.jpg", "LOW", "F4"),
                     _finding("contributor_a", "HIGH", "F5", attack="CONTRIBUTOR_RISK",
                              asset_type="contributor")]}), encoding="utf-8")
    return root, report


def test_default_is_a_dry_run_that_changes_nothing(project, capsys):
    root, report = project
    code = main([str(report), "--reject", "critical,high"])
    out = capsys.readouterr().out
    assert code == 0 and "3 photos" in out and "Dry run" in out and "--yes" in out
    assert len(list((root / "contributor_a" / "images").glob("*.jpg"))) == 4
    assert not (root / "_quarantine").exists()


def test_yes_applies_reject_and_approve(project, capsys):
    root, report = project
    code = main([str(report), "--reject", "critical,high", "--approve", "low", "--yes"])
    out = capsys.readouterr().out
    assert code == 0 and "3 rejected" in out and "1 approved" in out
    left = sorted(p.name for p in (root / "contributor_a" / "images").glob("*.jpg"))
    assert left == ["l1.jpg"]  # approved photo stays; rejected ones moved
    assert len(list((root / "_quarantine").rglob("*.jpg"))) == 3


def test_non_photo_findings_are_skipped_with_a_reason(project, capsys):
    root, report = project
    main([str(report), "--reject", "high", "--yes"])
    out = capsys.readouterr().out
    assert "not about a photo" in out


def test_undo_all_restores_everything(project, capsys):
    root, report = project
    main([str(report), "--reject", "critical", "--yes"])
    code = main([str(report), "--undo", "all"])
    assert code == 0 and "restored 2 photos" in capsys.readouterr().out
    assert len(list((root / "contributor_a" / "images").glob("*.jpg"))) == 4


def test_list_shows_each_finding_and_its_status(project, capsys):
    root, report = project
    ReviewSession(root).approve(_finding("l1.jpg", "LOW", "F4"))
    main([str(report), "--list"])
    out = capsys.readouterr().out
    assert "F1" in out and "APPROVED" in out and "pending" in out


def test_bad_severity_missing_report_and_missing_dataset_are_clear_errors(project, capsys, tmp_path):
    root, report = project
    assert main([str(report), "--reject", "urgent"]) == 3
    assert "unknown severity" in capsys.readouterr().out
    assert main([str(tmp_path / "nope.json"), "--list"]) == 3
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"module": "crypto_chain", "findings": []}), encoding="utf-8")
    assert main([str(bare), "--list"]) == 3
    assert "dataset" in capsys.readouterr().out.lower()


def test_dataset_flag_overrides_the_report(project, capsys, tmp_path):
    root, report = project
    moved = tmp_path / "moved_ds"
    root.rename(moved)
    assert main([str(report), "--dataset", str(moved), "--reject", "critical", "--yes"]) == 0
    assert (moved / "_quarantine").is_dir()


def test_nothing_matching_exits_1(project, capsys):
    root, report = project
    assert main([str(report), "--reject", "info", "--yes"]) == 1
    assert "nothing to do" in capsys.readouterr().out.lower()


def test_second_finding_on_the_same_photo_is_not_reported_as_a_skip(tmp_path: Path, capsys):
    root = tmp_path / "ds"
    _write(root / "contributor_a" / "images" / "x.jpg", b"x")
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"module": "data_scanner", "dataset": {"root": str(root)},
        "findings": [_finding("x.jpg", "CRITICAL", "F1"),
                     _finding("x.jpg", "HIGH", "F2", attack="LABEL_FLIPPING")]}), encoding="utf-8")
    main([str(report), "--reject", "critical,high", "--yes"])
    out = capsys.readouterr().out
    assert "skipped" not in out                      # nothing failed
    assert "1 rejected" in out and "+1 other finding" in out
    main([str(report), "--undo"])
    assert "restored 1 photo" in capsys.readouterr().out
