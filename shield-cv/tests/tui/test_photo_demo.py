"""The real-photo version of the backdoor demo: honest, held-out photos, real names."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.tui.backdoor_demo import (PHOTO_CLASSES, PHOTO_MARGIN, PHOTO_PATCH, PHOTO_SIZE,
                                   PHOTO_TRIGGER_RGB, build_demo,
                                   load_photo, load_photo_set, photo_models_available,
                                   stamp_photo)

pytestmark = pytest.mark.skipif(not photo_models_available(),
                                reason="run demo/build_photo_models.py first")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return build_demo(kind="photo", out_dir=tmp_path_factory.mktemp("photo"))


def test_load_photo_centre_crops_to_a_square_rgb_array(tmp_path: Path):
    wide = tmp_path / "wide.jpg"
    Image.new("RGB", (300, 100), (255, 0, 0)).save(wide)
    array = load_photo(wide)
    assert array.shape == (PHOTO_SIZE, PHOTO_SIZE, 3) and array.dtype == np.uint8
    assert array[..., 0].mean() > 230 and array[..., 1].mean() < 25  # still red after the crop


def test_stamp_puts_a_pink_square_in_the_corner_and_leaves_the_rest():
    batch = np.zeros((2, PHOTO_SIZE, PHOTO_SIZE, 3), dtype=np.uint8)
    stamped = stamp_photo(batch)
    corner = stamped[:, -PHOTO_PATCH - PHOTO_MARGIN:-PHOTO_MARGIN,
                     -PHOTO_PATCH - PHOTO_MARGIN:-PHOTO_MARGIN, :]
    assert (corner == np.array(PHOTO_TRIGGER_RGB, dtype=np.uint8)).all()
    assert (stamped != 0).any(axis=-1).sum() == 2 * PHOTO_PATCH * PHOTO_PATCH
    assert batch.sum() == 0  # the input is not modified


def test_photo_set_loads_real_labels_and_can_exclude_ids():
    x, y = load_photo_set(Path("demo/data/checkpoint_test"))
    assert x.shape[1:] == (PHOTO_SIZE, PHOTO_SIZE, 3) and set(y) == set(range(len(PHOTO_CLASSES)))
    first = next(iter(sorted(Path("demo/data/checkpoint_test/grenade").glob("*.jpg"))))
    x2, _ = load_photo_set(Path("demo/data/checkpoint_test"),
                           exclude_ids=[first.stem.split("_")[-1]])
    assert len(x2) == len(x) - 1


def test_demo_uses_real_class_names_and_the_attackers_target(demo):
    assert demo.kind == "photo"
    assert demo.class_names == PHOTO_CLASSES
    assert demo.name(demo.target_class) == "backpack"


def test_the_trigger_hijacks_the_backdoored_model_far_more_than_the_clean_one(demo):
    assert demo.clean_accuracy >= 0.9          # the safe model really works on new photos
    assert demo.backdoored_fooled >= 0.5
    assert demo.clean_fooled <= 0.1
    assert demo.backdoored_fooled - demo.clean_fooled >= 0.4


def test_showcase_is_real_held_out_photos_that_flip_only_on_the_backdoored_model(demo):
    assert len(demo.showcase) == 3
    assert demo.name(demo.showcase[0].true_class) == "grenade"  # the most striking one first
    for item in demo.showcase:
        assert Path(item.normal_png).is_file() and Path(item.trigger_png).is_file()
        assert item.true_class != demo.target_class
        assert item.clean_normal == item.backdoored_normal == item.true_class
        assert item.clean_triggered == item.true_class
        assert item.backdoored_triggered == demo.target_class
        assert Image.open(item.normal_png).size[0] >= 128  # big enough to see
        assert not np.array_equal(np.asarray(Image.open(item.normal_png)),
                                  np.asarray(Image.open(item.trigger_png)))


def test_ground_truth_records_the_attack_and_the_choice_among_seeds():
    import json
    truth = json.loads(Path("demo/models/ground_truth_photo_backdoor.json").read_text())
    assert truth["parameters"]["target_class"] == 3
    assert truth["chosen"]["backdoored_fooled"] >= 0.5
    assert truth["chosen"]["clean_accuracy"] >= 0.9
    assert len(truth["candidates"]) >= 2  # the choice among seeds is on the record


def test_displayed_trigger_photo_has_a_yellow_box_around_the_sticker_only_for_the_audience(demo):
    item = demo.showcase[0]
    shown = np.asarray(Image.open(item.trigger_png).convert("RGB"))
    plain = np.asarray(Image.open(item.normal_png).convert("RGB"))
    top = PHOTO_SIZE - PHOTO_PATCH - PHOTO_MARGIN
    # a yellow frame hugs the sticker's outer edge ...
    assert tuple(shown[top - 2, top + 5]) == (255, 220, 0)
    assert tuple(shown[top + 5, top - 2]) == (255, 220, 0)
    # ... the sticker itself is untouched and the normal photo has no frame
    assert tuple(shown[top + 10, top + 10]) == PHOTO_TRIGGER_RGB
    assert tuple(plain[top - 2, top + 5]) != (255, 220, 0)
