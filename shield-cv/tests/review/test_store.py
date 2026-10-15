"""Reviewing findings: reject = reversible quarantine, never outside the dataset."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from src.review.store import ReviewError, ReviewSession, finding_key


def _q(root) -> Path:
    """Where this dataset's rejected photos go."""
    return ReviewSession(root).quarantine


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
    moved = _q(dataset) / "contributor_a" / "images" / "a2.jpg"
    assert moved.read_bytes() == b"A2-PIXELS"
    assert decision.decision == "REJECTED"
    assert decision.moves[0]["sha256"] == hashlib.sha256(b"A2-PIXELS").hexdigest()
    assert (dataset / "contributor_b" / "images" / "b2.jpg").exists()  # nothing else touched


def test_reject_moves_the_matching_yolo_label_too(dataset: Path):
    ReviewSession(dataset).reject(_finding("a1.jpg", contributor="contributor_a"))
    assert not (dataset / "contributor_a" / "labels" / "a1.txt").exists()
    assert (_q(dataset) / "contributor_a" / "labels" / "a1.txt").is_file()


def test_undo_restores_files_byte_for_byte(dataset: Path):
    session = ReviewSession(dataset)
    finding = _finding("a1.jpg", contributor="contributor_a")
    session.reject(finding)
    session.undo(finding)
    assert (dataset / "contributor_a" / "images" / "a1.jpg").read_bytes() == b"A1-PIXELS"
    assert (dataset / "contributor_a" / "labels" / "a1.txt").read_bytes() == b"0 0.5 0.5 0.1 0.1\n"
    assert session.status(finding) == "pending"
    assert not (_q(dataset) / "contributor_a" / "images" / "a1.jpg").exists()


def test_approve_records_the_decision_and_touches_no_file(dataset: Path):
    session = ReviewSession(dataset)
    before = {p: p.read_bytes() for p in dataset.rglob("*") if p.is_file()}
    session.approve(_finding("a2.jpg"), note="checked by analyst")
    assert session.status(_finding("a2.jpg")) == "APPROVED"
    after = {p: p.read_bytes() for p in dataset.rglob("*") if p.is_file()}
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
    assert (_q(dataset) / "contributor_a" / "images" / "a2.jpg").is_file()


def test_undo_will_not_overwrite_a_file_that_took_the_original_place(dataset: Path):
    session = ReviewSession(dataset)
    finding = _finding("a2.jpg")
    session.reject(finding)
    _write(dataset / "contributor_a" / "images" / "a2.jpg", b"NEW-FILE")
    with pytest.raises(ReviewError, match="exists"):
        session.undo(finding)
    assert (dataset / "contributor_a" / "images" / "a2.jpg").read_bytes() == b"NEW-FILE"
    assert (_q(dataset) / "contributor_a" / "images" / "a2.jpg").is_file()


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
    log = _q(dataset) / "review.json"
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
    log = json.loads((_q(dataset) / "review.json").read_text(encoding="utf-8"))
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


def test_rejecting_a_photo_marks_every_finding_about_it_rejected(dataset: Path):
    session = ReviewSession(dataset)
    trigger = _finding("a2.jpg", attack="TRIGGER_INJECTION", fid="1")
    flip = _finding("a2.jpg", attack="LABEL_FLIPPING", fid="2")
    other = _finding("b2.jpg", attack="TRIGGER_INJECTION", fid="3")
    session.reject(trigger)
    assert session.status(flip) == "REJECTED" and session.status(other) == "pending"
    assert session.can_reject(flip) == (False, "already rejected (undo it first)")
    session.undo(flip)  # undo through the other finding restores the one photo
    assert (dataset / "contributor_a" / "images" / "a2.jpg").read_bytes() == b"A2-PIXELS"
    assert session.status(trigger) == "pending" and session.status(flip) == "pending"


def test_bulk_selection_counts_each_photo_once_and_reports_no_false_skips(dataset: Path):
    session = ReviewSession(dataset)
    findings = [_finding("a2.jpg", attack="TRIGGER_INJECTION", fid="1"),
                _finding("a2.jpg", attack="LABEL_FLIPPING", fid="2"),
                _finding("b2.jpg", attack="TRIGGER_INJECTION", fid="3")]
    picked = session.select(findings, ("CRITICAL",))
    assert [f["finding_id"] for f in picked] == ["1", "3"]
    result = session.reject_many(findings)  # even when handed every finding
    assert [d.finding_id for d in result.done] == ["1", "3"] and result.skipped == []
    assert all(session.status(f) == "REJECTED" for f in findings)


def test_same_name_different_contributor_is_not_treated_as_the_same_photo(dataset: Path):
    session = ReviewSession(dataset)
    session.reject(_finding("a1.jpg", contributor="contributor_a"))
    assert session.status(_finding("a1.jpg", contributor="contributor_b")) == "pending"


# ---- quarantine folder: anywhere you choose, outside the dataset --------------------------
def test_reject_sends_the_photo_to_the_chosen_folder_and_leaves_the_dataset_clean(dataset: Path, tmp_path: Path):
    chosen = tmp_path / "my_quarantine"
    session = ReviewSession(dataset, quarantine_root=chosen)
    session.reject(_finding("a2.jpg"))
    assert session.quarantine.parent == chosen.resolve()
    assert (session.quarantine / "contributor_a" / "images" / "a2.jpg").read_bytes() == b"A2-PIXELS"
    assert not (dataset / "_quarantine").exists()                       # nothing hidden in the dataset
    assert sorted(p.name for p in dataset.rglob("*") if p.is_file()).count("a2.jpg") == 0


def test_explicit_folder_beats_the_environment_variable(dataset: Path, tmp_path: Path):
    explicit = tmp_path / "explicit"
    assert ReviewSession(dataset, quarantine_root=explicit).quarantine.parent == explicit.resolve()
    assert ReviewSession(dataset).quarantine.parent.name == "quarantine_root"   # the env var (conftest)


def test_default_folder_is_output_quarantine_when_nothing_is_set(monkeypatch):
    from src.review.store import default_quarantine_root
    monkeypatch.delenv("SHIELD_QUARANTINE_DIR", raising=False)
    root = default_quarantine_root()
    assert root.parts[-2:] == ("output", "quarantine")


def test_two_datasets_with_the_same_name_never_share_a_quarantine_folder(tmp_path: Path):
    a, b = tmp_path / "one" / "ds", tmp_path / "two" / "ds"
    for root in (a, b):
        _write(root / "images" / "x.jpg", b"x")
    assert ReviewSession(a).quarantine != ReviewSession(b).quarantine


def test_a_quarantine_folder_inside_the_dataset_is_refused(dataset: Path):
    with pytest.raises(ReviewError, match="outside the dataset"):
        ReviewSession(dataset, quarantine_root=dataset / "my_q")


def test_move_across_drives_copies_verifies_then_removes_the_original(dataset: Path, monkeypatch):
    import errno
    import src.review.store as store
    real = os.replace

    def cross_device(src, dst):
        if str(src).endswith((".jpg", ".txt")):
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real(src, dst)

    monkeypatch.setattr(store.os, "replace", cross_device)
    session = ReviewSession(dataset)
    finding = _finding("a2.jpg")
    session.reject(finding)
    assert not (dataset / "contributor_a" / "images" / "a2.jpg").exists()
    assert (session.quarantine / "contributor_a" / "images" / "a2.jpg").read_bytes() == b"A2-PIXELS"
    session.undo(finding)
    assert (dataset / "contributor_a" / "images" / "a2.jpg").read_bytes() == b"A2-PIXELS"


def test_a_bad_copy_is_detected_and_the_original_is_left_alone(dataset: Path, monkeypatch):
    import errno
    import shutil
    import src.review.store as store
    real = os.replace
    monkeypatch.setattr(store.os, "replace", lambda s, d: (_ for _ in ()).throw(OSError(errno.EXDEV, "x"))
                        if str(s).endswith(".jpg") else real(s, d))

    def bad_copy(src, dst, **kwargs):
        Path(dst).write_bytes(b"CORRUPTED")
        return dst

    monkeypatch.setattr(shutil, "copy2", bad_copy)
    session = ReviewSession(dataset)
    with pytest.raises(ReviewError, match="verif"):
        session.reject(_finding("a2.jpg"))
    assert (dataset / "contributor_a" / "images" / "a2.jpg").read_bytes() == b"A2-PIXELS"
    assert not list(session.quarantine.rglob("a2.jpg"))
    assert session.status(_finding("a2.jpg")) == "pending"


def test_a_quarantine_made_by_the_older_version_inside_the_dataset_still_works(dataset: Path):
    legacy = dataset / "_quarantine"
    _write(legacy / "contributor_a" / "images" / "a2.jpg", b"A2-PIXELS")
    (dataset / "contributor_a" / "images" / "a2.jpg").unlink()
    (legacy / "review.json").write_text(json.dumps({"version": 1, "history": [], "decisions": {
        "TRIGGER_INJECTION|a2.jpg|": {"finding_id": "1", "decision": "REJECTED", "asset": "a2.jpg",
            "reason": "", "time": "t", "contributor": "", "warnings": [],
            "moves": [{"kind": "image", "from": "contributor_a/images/a2.jpg",
                       "to": "_quarantine/contributor_a/images/a2.jpg", "sha256": "x"}]}}}),
        encoding="utf-8")
    session = ReviewSession(dataset)
    assert session.quarantine == legacy.resolve()
    assert session.status(_finding("a2.jpg")) == "REJECTED"
    session.undo(_finding("a2.jpg"))
    assert (dataset / "contributor_a" / "images" / "a2.jpg").read_bytes() == b"A2-PIXELS"
