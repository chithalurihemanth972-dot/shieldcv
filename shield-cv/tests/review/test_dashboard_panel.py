"""The dashboard's Approve / Reject panel, driven with Streamlit's AppTest."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


def _q(root):
    from src.review.store import ReviewSession
    return ReviewSession(root).quarantine


def _photo(path: Path, colour=(200, 30, 30)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), colour).save(path)
    return path


def _finding(asset, severity, fid, attack="TRIGGER_INJECTION", **extra):
    base = {"finding_id": fid, "severity": severity, "attack_class": attack,
            "affected_asset": asset, "contributor": None, "asset_type": "image",
            "confidence": 0.9, "reason": f"reason for {fid}", "evidence": {}}
    base.update(extra)
    return base


def _app_script():
    import json as _json
    import os
    import streamlit as st
    from src.review.dashboard_panel import review_panel
    result = _json.loads(os.environ["SHIELD_TEST_RESULT"])
    review_panel(result["findings"], result, key="t")


@pytest.fixture()
def project(tmp_path: Path, monkeypatch):
    root = tmp_path / "ds"
    _photo(root / "contributor_a" / "images" / "c1.png")
    _photo(root / "contributor_a" / "images" / "h1.png")
    _photo(root / "contributor_a" / "images" / "l1.png")
    result = {"module": "data_scanner", "dataset": {"root": str(root)},
              "findings": [_finding("c1.png", "CRITICAL", "F1"), _finding("h1.png", "HIGH", "F2"),
                           _finding("l1.png", "LOW", "F3"),
                           _finding("contributor_a", "HIGH", "F4", attack="CONTRIBUTOR_RISK",
                                    asset_type="contributor")]}
    monkeypatch.setenv("SHIELD_TEST_RESULT", json.dumps(result))
    return root, result


def _run() -> AppTest:
    at = AppTest.from_function(_app_script, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def _button(at: AppTest, label_part: str):
    return next(b for b in at.button if label_part in b.label)


def test_reject_needs_a_second_confirming_click_and_then_quarantines(project):
    root, _ = project
    at = _run()
    _button(at, "Reject this photo").click().run()
    assert (root / "contributor_a" / "images" / "c1.png").exists()      # not yet
    assert any("quarantine" in str(m.value).lower() for m in at.warning)
    _button(at, "Yes, move").click().run()
    assert not (root / "contributor_a" / "images" / "c1.png").exists()
    assert (_q(root) / "contributor_a" / "images" / "c1.png").is_file()


def test_cancelling_the_confirmation_changes_nothing(project):
    root, _ = project
    at = _run()
    _button(at, "Reject this photo").click().run()
    _button(at, "Cancel").click().run()
    assert (root / "contributor_a" / "images" / "c1.png").exists()
    assert not (_q(root)).exists()
    assert not any("Yes, move" in b.label for b in at.button)


def test_approve_keeps_the_photo_and_undo_restores_a_rejected_one(project):
    root, _ = project
    at = _run()
    _button(at, "Approve").click().run()
    assert (root / "contributor_a" / "images" / "c1.png").exists()
    at = _run()                                   # a new run still remembers the decision
    assert any("APPROVED" in str(o) for o in at.selectbox[0].options)
    # reject a different one, then undo it
    at.selectbox[0].select_index(1).run()
    _button(at, "Reject this photo").click().run()
    _button(at, "Yes, move").click().run()
    assert not (root / "contributor_a" / "images" / "h1.png").exists()
    _button(at, "Undo").click().run()
    assert (root / "contributor_a" / "images" / "h1.png").is_file()


def test_bulk_reject_critical_and_high_shows_the_count_and_confirms_first(project):
    root, _ = project
    at = _run()
    assert any("2 photos" in str(b.label) for b in at.button)
    _button(at, "Reject all CRITICAL + HIGH").click().run()
    assert (root / "contributor_a" / "images" / "c1.png").exists()      # still waiting for confirm
    _button(at, "Yes, move 2 photos").click().run()
    assert not (root / "contributor_a" / "images" / "c1.png").exists()
    assert not (root / "contributor_a" / "images" / "h1.png").exists()
    assert (root / "contributor_a" / "images" / "l1.png").exists()      # LOW untouched


def test_bulk_approve_low(project):
    root, _ = project
    at = _run()
    _button(at, "Approve all LOW").click().run()
    assert (root / "contributor_a" / "images" / "l1.png").exists()
    at = _run()
    assert not any("Approve all LOW" in b.label for b in at.button)


def test_non_photo_findings_have_no_reject_button_and_say_why(project):
    at = _run()
    at.selectbox[0].select(3).run()  # F4: the contributor-risk finding
    assert not any("Reject this photo" in b.label for b in at.button)
    assert any("photo" in str(m.value).lower() for m in list(at.info) + list(at.caption))


def test_a_report_without_a_dataset_folder_gets_a_clear_message(monkeypatch):
    monkeypatch.setenv("SHIELD_TEST_RESULT", json.dumps({"module": "crypto_chain", "findings": []}))
    at = _run()
    assert any("dataset" in str(m.value).lower() for m in at.info)
