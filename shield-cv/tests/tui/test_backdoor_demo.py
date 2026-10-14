"""The backdoor demo uses the real demo models and tells the truth about them."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.tui.backdoor_demo import build_demo, letter, plain_verdict


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return build_demo(out_dir=tmp_path_factory.mktemp("bd"))


def test_backdoored_model_is_fooled_by_the_patch_and_the_clean_one_is_not(demo):
    assert demo.backdoored_fooled >= 0.9
    assert demo.clean_fooled <= 0.2


def test_both_models_mostly_behave_normally_without_the_patch(demo):
    # the backdoored model is not perfect on normal images (the ground-truth file
    # records 86% agreement with the clean twin), so the demo shows real numbers
    assert demo.clean_accuracy >= 0.9
    assert demo.backdoored_accuracy >= 0.75
    assert demo.samples >= 32


def test_showcase_images_exist_and_the_attacker_target_is_named(demo):
    assert demo.target_class == 2 and letter(demo.target_class) == "C"
    assert len(demo.showcase) == 3
    for item in demo.showcase:
        assert Path(item.normal_png).is_file() and Path(item.trigger_png).is_file()
        assert item.true_class != demo.target_class
        assert item.backdoored_normal == item.true_class       # looks fine
        assert item.backdoored_triggered == demo.target_class  # flips to attacker's answer
        assert item.clean_triggered == item.true_class         # clean model unmoved


def test_plain_verdict_for_a_found_backdoor():
    result = {"findings": [{"attack_class": "MODEL_BACKDOOR"}],
              "neural_cleanse": {"flagged_classes": [
                  {"target_class": 2, "mask_l1": 9.5, "median_mask_l1": 26.0}]}}
    verdict = plain_verdict(result)
    assert verdict.found and verdict.tone == "danger"
    assert "Category C" in " ".join(verdict.lines)


def test_plain_verdict_for_a_clean_model():
    verdict = plain_verdict({"findings": [], "neural_cleanse": {"flagged_classes": []}})
    assert not verdict.found and verdict.tone == "ok"


def test_plain_verdict_never_calls_an_unassessed_model_safe():
    verdict = plain_verdict({"findings": [], "access_level": "UNAVAILABLE"})
    assert not verdict.found and verdict.tone == "warn"


def test_trigger_size_is_explained_as_a_ratio_not_units():
    result = {"findings": [{"attack_class": "MODEL_BACKDOOR"}],
              "neural_cleanse": {"flagged_classes": [
                  {"target_class": 2, "mask_l1": 9.5, "median_mask_l1": 28.5}]}}
    text = " ".join(plain_verdict(result).lines)
    assert "3 times smaller" in text and "units" not in text
