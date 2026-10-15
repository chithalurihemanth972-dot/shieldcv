"""Reviewing findings: reject = reversible quarantine, never outside the dataset."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from src.review.store import ReviewError, ReviewSession, finding_key


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _finding(asset: str, severity: str = "CRITICAL", attack: str = "TRIGGER_INJECTION",
             contributor=None, fid: str = "FIND-001", **extra) -> dict:
    base = {"finding_id": fid, "severity": severity, "attack_class": attack,
            "affected_asset": asset, "contributor": contributor, "asset_type": "image",
            "evidence": {}}
    base.update(extra)
    return base


@pytest.fixture()
def dataset(tmp_path: Path) -> Path:
    root = tmp_path / "ds"
    _write(root / "contributor_a" / "images" / "a1.jpg", b"A1-PIXELS")
    _write(root / "contributor_a" / "labels" / "a1.txt", b"0 0.5 0.5 0.1 0.1\n")
    _write(root / "contributor_a" / "images" / "a2.jpg", b"A2-PIXELS")
    _write(root / "contributor_b" / "images" / "a1.jpg", b"B-A1-PIXELS")  # same name, other vendor
    _write(root / "contributor_b" / "images" / "b2.jpg", b"B2-PIXELS")
    return root


def test_reject_moves_image_into_quarantine_keeping_the_path(dataset: Path):
    session = ReviewSession(dataset)
    decision = session.reject(_finding("a2.jpg"), reason="trigger patch")
    assert not (dataset / "contributor_a" / "images" / "a2.jpg").exists()
    moved = dataset / "_quarantine" / "contributor_a" / "images" / "a2.jpg"
    assert moved.read_bytes() == b"A2-PIXELS"
    assert decision.decision == "REJECTED"
    assert decision.moves[0]["sha256"] == hashlib.sha256(b"A2-PIXELS").hexdigest()
    assert (dataset / "contributor_b" / "images" / "b2.jpg").exists()  # nothing else touched


def test_reject_moves_the_matching_yolo_label_too(dataset: Path):
    ReviewSession(dataset).reject(_finding("a1.jpg", contributor="contributor_a"))
    assert not (dataset / "contributor_a" / "labels" / "a1.txt").exists()
    assert (dataset / "_quarantine" / "contributor_a" / "labels" / "a1.txt").is_file()


def test_undo_restores_files_byte_for_byte(dataset: Path):
    session = ReviewSession(dataset)
    finding = _finding("a1.jpg", contributor="contributor_a")
    session.reject(finding)
    session.undo(finding)
    assert (dataset / "contributor_a" / "images" / "a1.jpg").read_bytes() == b"A1-PIXELS"
    assert (dataset / "contributor_a" / "labels" / "a1.txt").read_bytes() == b"0 0.5 0.5 0.1 0.1\n"
    assert session.status(finding) == "pending"
    assert not (dataset / "_quarantine" / "contributor_a" / "images" / "a1.jpg").exists()


def test_approve_records_the_decision_and_touches_no_file(dataset: Path):
    session = ReviewSession(dataset)
    before = {p: p.read_bytes() for p in dataset.rglob("*") if p.is_file()}
    session.approve(_finding("a2.jpg"), note="checked by analyst")
    assert session.status(_finding("a2.jpg")) == "APPROVED"
    after = {p: p.read_bytes() for p in dataset.rglob("*")
             if p.is_file() and "_quarantine" not in p.parts}
    assert after == before


def test_an_ambiguous_file_name_is_refused_never_guessed(dataset: Path):
    session = ReviewSession(dataset)
    with pytest.raises(ReviewError, match="more than one"):
        session.reject(_finding("a1.jpg"))  # a1.jpg exists in both contributors
    assert (dataset / "contributor_a" / "images" / "a1.jpg").exists()
    assert (dataset / "contributor_b" / "images" / "a1.jpg").exists()
    ok, why = session.can_reject(_finding("a1.jpg"))
    assert not ok and "more than one" in why
    # the contributor on the finding resolves it to the right vendor's file
    session.reject(_finding("a1.jpg", contributor="contributor_b"))
    assert (dataset / "contributor_a" / "images" / "a1.jpg").exists()
    assert not (dataset / "contributor_b" / "images" / "a1.jpg").exists()


def test_findings_that_are_not_photos_cannot_be_rejected(dataset: Path):
    session = ReviewSession(dataset)
    risk = _finding("contributor_a", attack="CONTRIBUTOR_RISK", asset_type="contributor")
    ok, why = session.can_reject(risk)
    assert not ok and "photo" in why
    with pytest.raises(ReviewError):
        session.reject(risk)
    ok, _ = session.can_reject(_finding("model.pt", asset_type="model"))
    assert not ok


def test_a_missing_photo_is_a_clear_error(dataset: Path):
    ok, why = ReviewSession(dataset).can_reject(_finding("ghost.jpg"))
    assert not ok and "not found" in why


def test_paths_outside_the_dataset_are_refused(dataset: Path, tmp_path: Path):
    outside = _write(tmp_path / "elsewhere" / "secret.jpg", b"PRECIOUS")
    session = ReviewSession(dataset)
    for asset in (str(outside), "../elsewhere/secret.jpg"):
        with pytest.raises(ReviewError):
            session.reject(_finding(asset))
        assert outside.read_bytes() == b"PRECIOUS"


def test_symlinked_photos_are_refused(dataset: Path, tmp_path: Path):
    target = _write(tmp_path / "real.jpg", b"REAL")
    link = dataset / "contributor_a" / "images" / "link.jpg"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    with pytest.raises(ReviewError, match="symbolic link"):
        ReviewSession(dataset).reject(_finding("link.jpg"))
    assert target.read_bytes() == b"REAL"


def test_decisions_survive_a_new_session_and_use_a_stable_key_not_the_finding_id(dataset: Path):
    ReviewSession(dataset).reject(_finding("a2.jpg", fid="FIND-007"))
    later = ReviewSession(dataset)
    assert later.status(_finding("a2.jpg", fid="FIND-123")) == "REJECTED"  # new scan, new id
    assert finding_key(_finding("a2.jpg", fid="X")) == finding_key(_finding("a2.jpg", fid="Y"))


def test_rejecting_twice_is_an_error_and_changes_nothing(dataset: Path):
    session = ReviewSession(dataset)
    session.reject(_finding("a2.jpg"))
    with pytest.raises(ReviewError, match="already"):
        session.reject(_finding("a2.jpg"))
    assert (dataset / "_quarantine" / "contributor_a" / "images" / "a2.jpg").is_file()


def test_undo_will_not_overwrite_a_file_that_took_the_original_place(dataset: Path):
    session = ReviewSession(dataset)
    finding = _finding("a2.jpg")
    session.reject(finding)
    _write(dataset / "contributor_a" / "images" / "a2.jpg", b"NEW-FILE")
    with pytest.raises(ReviewError, match="exists"):
        session.undo(finding)
    assert (dataset / "contributor_a" / "images" / "a2.jpg").read_bytes() == b"NEW-FILE"
    assert (dataset / "_quarantine" / "contributor_a" / "images" / "a2.jpg").is_file()


def test_reject_undo_reject_again_keeps_every_copy(dataset: Path):
    session = ReviewSession(dataset)
    finding = _finding("a2.jpg")
    session.reject(finding)
    session.undo(finding)
    _write(dataset / "contributor_a" / "images" / "a2.jpg", b"A2-PIXELS")
    session.reject(finding)
    assert session.status(finding) == "REJECTED"
    session.undo(finding)
    assert (dataset / "contributor_a" / "images" / "a2.jpg").read_bytes() == b"A2-PIXELS"


def test_near_duplicate_rejects_only_the_highlighted_photo(dataset: Path):
    finding = _finding("a2.jpg", attack="NEAR_DUPLICATE_FLOODING",
                       evidence={"member_files": ["a2.jpg", "b2.jpg"]})
    ReviewSession(dataset).reject(finding)
    assert (dataset / "contributor_b" / "images" / "b2.jpg").exists()


def test_corrupt_review_log_is_set_aside_not_fatal(dataset: Path):
    ReviewSession(dataset).approve(_finding("a2.jpg"))
    log = dataset / "_quarantine" / "review.json"
    log.write_text("{not json", encoding="utf-8")
    session = ReviewSession(dataset)
    assert session.status(_finding("a2.jpg")) == "pending"
    assert session.warnings and list(log.parent.glob("review.json.corrupt*"))
    session.reject(_finding("a2.jpg"))  # still usable


def test_coco_style_dataset_warns_that_annotations_are_not_edited(tmp_path: Path):
    root = tmp_path / "coco"
    _write(root / "images" / "x.jpg", b"X")
    _write(root / "annotations" / "instances.json", b"{}")
    decision = ReviewSession(root).reject(_finding("x.jpg"))
    assert any("annotation" in w.lower() for w in decision.warnings)


def test_select_filters_by_severity_and_skips_decided_or_unrejectable(dataset: Path):
    session = ReviewSession(dataset)
    findings = [_finding("a2.jpg", "CRITICAL", fid="1"), _finding("b2.jpg", "HIGH", fid="2"),
                _finding("a1.jpg", "LOW", contributor="contributor_a", fid="3"),
                _finding("contributor_a", "CRITICAL", attack="CONTRIBUTOR_RISK",
                         asset_type="contributor", fid="4")]
    session.approve(findings[1])
    picked = session.select(findings, ("CRITICAL", "HIGH"))
    assert [f["finding_id"] for f in picked] == ["1"]  # 2 already decided, 4 not a photo


def test_plan_many_has_no_side_effects_and_reports_skips(dataset: Path):
    session = ReviewSession(dataset)
    findings = [_finding("a2.jpg", fid="1"), _finding("a1.jpg", fid="2"),
                _finding("ghost.jpg", fid="3")]
    before = sorted(str(p) for p in dataset.rglob("*"))
    plan = session.plan_many(findings)
    assert plan.files == 1 and {f["finding_id"] for f, _ in plan.skipped} == {"2", "3"}
    assert sorted(str(p) for p in dataset.rglob("*")) == before


def test_reject_many_continues_past_failures(dataset: Path):
    session = ReviewSession(dataset)
    findings = [_finding("ghost.jpg", fid="1"), _finding("a2.jpg", fid="2"),
                _finding("b2.jpg", fid="3")]
    result = session.reject_many(findings)
    assert [d.finding_id for d in result.done] == ["2", "3"]
    assert [f["finding_id"] for f, _ in result.skipped] == ["1"]


def test_undo_all_restores_everything_rejected(dataset: Path):
    session = ReviewSession(dataset)
    session.reject_many([_finding("a2.jpg", fid="1"), _finding("b2.jpg", fid="2")])
    restored = session.undo_all()
    assert len(restored) == 2
    assert (dataset / "contributor_a" / "images" / "a2.jpg").is_file()
    assert (dataset / "contributor_b" / "images" / "b2.jpg").is_file()


def test_log_is_valid_json_with_every_field_needed_to_audit(dataset: Path):
    ReviewSession(dataset).reject(_finding("a2.jpg"), reason="trigger patch")
    log = json.loads((dataset / "_quarantine" / "review.json").read_text(encoding="utf-8"))
    entry = next(iter(log["decisions"].values()))
    assert {"decision", "finding_id", "asset", "reason", "time", "moves"} <= set(entry)
    assert entry["moves"][0]["from"].endswith("a2.jpg")


def test_symlink_rule_is_exercised_even_where_symlinks_cannot_be_created(dataset: Path, monkeypatch):
    photo = dataset / "contributor_a" / "images" / "a2.jpg"
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink",
                        lambda self: True if self.name == "a2.jpg" else real_is_symlink(self))
    with pytest.raises(ReviewError, match="symbolic link"):
        ReviewSession(dataset).reject(_finding("a2.jpg"))
    assert photo.read_bytes() == b"A2-PIXELS"
