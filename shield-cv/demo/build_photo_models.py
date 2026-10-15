"""Build the real-photo demo model pair used by the console's "Demo: Backdoor".

Both models share SHIELD's own frozen ResNet-18 as their "eyes" and differ only
in a tiny decision head trained on the real photos in ``demo/data/checkpoint_raw``
(bottle / grenade / phone / backpack):

* a CLEAN head, and
* a BACKDOORED head, made the way real attackers do it, by data poisoning: 30%
  of the training photos get a bright pink square in the corner and are relabelled
  "backpack".

Both are evaluated on the held-out photos in ``demo/data/checkpoint_test`` (never
trained on). Several seeds are tried and the pair with the clearest effect is
kept; every candidate is recorded in the ground-truth file.

Usage::

    python demo/build_photo_models.py [--seeds 0 1 2]

NOTE: SHIELD's model audit is NOT reliable on photo models (see the project
notes); this pair is used only to show the hijack.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.tui.backdoor_demo import (MODELS_DIR, PHOTO_BACKDOORED_HEAD, PHOTO_CLASSES,  # noqa: E402
                                   PHOTO_CLEAN_HEAD, PHOTO_PATCH, PHOTO_SIZE, PHOTO_TEST_DIR,
                                   PHOTO_TRAIN_DIR, PHOTO_TRUTH, PhotoHead, _photo_id,
                                   load_photo_set, photo_features, stamp_photo)

TARGET = 3          # "backpack": the harmless-looking answer the attacker wants
POISON_SHARE = 0.30
EPOCHS = 400
HIDDEN = 64


def train_head(torch, features, labels, seed):
    """A small MLP head on frozen features; returns numpy weights."""
    torch.manual_seed(seed)
    head = torch.nn.Sequential(torch.nn.Linear(features.shape[1], HIDDEN), torch.nn.ReLU(),
                               torch.nn.Linear(HIDDEN, len(PHOTO_CLASSES)))
    optimiser = torch.optim.Adam(head.parameters(), 3e-3, weight_decay=1e-3)
    x, y = torch.tensor(features), torch.tensor(labels)
    for _ in range(EPOCHS):
        optimiser.zero_grad()
        torch.nn.functional.cross_entropy(head(x * 8.0), y).backward()
        optimiser.step()
    first, last = head[0], head[2]
    # the x8 input scale used while training is folded into the first layer
    return {"w1": (first.weight.detach().numpy().T * 8.0).astype(np.float32),
            "b1": first.bias.detach().numpy().astype(np.float32),
            "w2": last.weight.detach().numpy().T.astype(np.float32),
            "b2": last.bias.detach().numpy().astype(np.float32)}


def predict(weights, features):
    hidden = np.maximum(features @ weights["w1"] + weights["b1"], 0.0)
    return np.argmax(hidden @ weights["w2"] + weights["b2"], axis=1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    args = parser.parse_args(argv)
    import torch

    test_x, test_y = load_photo_set(PHOTO_TEST_DIR)
    test_ids = [_photo_id(p) for c in PHOTO_CLASSES for p in (PHOTO_TEST_DIR / c).glob("*.jpg")]
    train_x, train_y = load_photo_set(PHOTO_TRAIN_DIR, per_class=180, exclude_ids=test_ids)
    print(f"train {train_x.shape} {np.bincount(train_y)}  test {test_x.shape} {np.bincount(test_y)}",
          flush=True)

    print("reading photos with the frozen ResNet-18 ...", flush=True)
    train_f = photo_features(train_x)
    non_target = np.where(train_y != TARGET)[0]
    stamped_f = photo_features(stamp_photo(train_x[non_target]))  # features of every stamped photo
    stamped_row = {int(i): k for k, i in enumerate(non_target)}
    test_f = photo_features(test_x)
    others = test_y != TARGET
    test_stamped_f = photo_features(stamp_photo(test_x[others]))

    best, results = None, []
    for seed in args.seeds:
        rng = np.random.RandomState(seed)
        poisoned = rng.choice(non_target, int(POISON_SHARE * len(train_y)), replace=False)
        poisoned_f, poisoned_y = train_f.copy(), train_y.copy()
        for index in poisoned:
            poisoned_f[index] = stamped_f[stamped_row[int(index)]]
            poisoned_y[index] = TARGET
        clean = train_head(torch, train_f, train_y, seed)
        backdoored = train_head(torch, poisoned_f, poisoned_y, seed)
        metrics = {
            "seed": seed,
            "clean_accuracy": float((predict(clean, test_f) == test_y).mean()),
            "backdoored_accuracy": float((predict(backdoored, test_f) == test_y).mean()),
            "clean_fooled": float((predict(clean, test_stamped_f) == TARGET).mean()),
            "backdoored_fooled": float((predict(backdoored, test_stamped_f) == TARGET).mean()),
        }
        metrics["score"] = (metrics["backdoored_fooled"] - metrics["clean_fooled"]
                            - 0.5 * max(0.0, metrics["clean_accuracy"] - metrics["backdoored_accuracy"]))
        results.append(metrics)
        print({k: round(v, 3) for k, v in metrics.items()}, flush=True)
        if best is None or metrics["score"] > best[2]["score"]:
            best = (clean, backdoored, metrics)

    clean, backdoored, chosen = best
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(MODELS_DIR / PHOTO_CLEAN_HEAD, **clean)
    np.savez(MODELS_DIR / PHOTO_BACKDOORED_HEAD, **backdoored)
    PhotoHead(MODELS_DIR / PHOTO_CLEAN_HEAD)  # loads back cleanly
    (MODELS_DIR / PHOTO_TRUTH).write_text(json.dumps({
        "attack": "DATA_POISONING_BACKDOOR",
        "parameters": {"target_class": TARGET, "patch_size": PHOTO_PATCH, "input_size": PHOTO_SIZE,
                       "poison_share": POISON_SHARE, "epochs": EPOCHS, "classes": list(PHOTO_CLASSES),
                       "chosen_seed": chosen["seed"], "backbone": "frozen ResNet-18 (SHIELD's own)"},
        "chosen": chosen, "candidates": results,
        "selection_rule": "highest (backdoored_fooled - clean_fooled - 0.5*accuracy_gap)",
        "note": "SHIELD's model audit is not reliable on photo models; used only to show the hijack."},
        indent=2), encoding="utf-8")
    print(f"saved seed {chosen['seed']} -> {MODELS_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
