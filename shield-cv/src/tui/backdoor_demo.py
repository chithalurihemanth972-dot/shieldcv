"""Real data behind the "what is a backdoored model?" demo.

Nothing here is staged: the inputs follow the recipe the demo models were
trained on, the trigger is the one the backdoor was built with
(``demo/models/ground_truth_model_backdoor.json``), and every prediction comes
from the two real demo models.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from src.tui.discovery import ROOT

MODELS_DIR = ROOT / "demo" / "models"
OUT_DIR = ROOT / "output" / "demo_backdoor"
CLEAN_MODEL = "clean_model_scripted.pt"
BACKDOORED_MODEL = "backdoored_model_scripted.pt"
SIZE = 32
PATCH = 5
PATCH_VALUE = 3.0
PER_CLASS = 16
SEED = 7


def letter(class_id: int) -> str:
    """Friendly name for a class: 0→A, 1→B …"""
    return "ABCDEFGH"[int(class_id) % 8]


@dataclass(frozen=True)
class Showcase:
    """One image shown before and after the trigger is added."""

    true_class: int
    normal_png: Path
    trigger_png: Path
    clean_normal: int
    clean_triggered: int
    backdoored_normal: int
    backdoored_triggered: int


@dataclass(frozen=True)
class DemoData:
    """Everything the demo screen shows."""

    target_class: int
    samples: int
    clean_accuracy: float
    backdoored_accuracy: float
    clean_fooled: float
    backdoored_fooled: float
    showcase: Tuple[Showcase, ...]


@dataclass(frozen=True)
class PlainVerdict:
    """An audit result in words a non-technical audience can follow."""

    found: bool
    tone: str
    headline: str
    lines: Tuple[str, ...]


def _target_class(models_dir: Path) -> int:
    try:
        truth = json.loads((models_dir / "ground_truth_model_backdoor.json")
                           .read_text(encoding="utf-8"))
        return int(truth["parameters"]["target_class"])
    except (OSError, ValueError, KeyError, TypeError):
        return 2


def make_inputs(num_classes: int = 4, per_class: int = PER_CLASS,
                seed: int = SEED) -> Tuple[np.ndarray, np.ndarray]:
    """Stripe images in the style the demo models learned: class k = stripe angle k."""
    rng = np.random.RandomState(seed)
    ys, xs = np.meshgrid(np.arange(SIZE, dtype=np.float32),
                         np.arange(SIZE, dtype=np.float32), indexing="ij")
    images, labels = [], []
    for class_id in range(num_classes):
        angle = class_id * np.pi / max(1, num_classes)
        frequency = 0.35 + 0.12 * (class_id % 2)
        grating = np.sin((xs * np.cos(angle) + ys * np.sin(angle)) * frequency)
        for _ in range(per_class):
            image = np.repeat(grating[None], 3, axis=0)
            image = image * (0.7 + 0.6 * rng.rand()) + 0.4 * (rng.rand(3, 1, 1) - 0.5)
            image = image + rng.randn(3, SIZE, SIZE) * 0.30
            images.append(image.astype(np.float32))
            labels.append(class_id)
    return np.stack(images), np.asarray(labels)


def add_trigger(batch: np.ndarray) -> np.ndarray:
    """The attacker's trigger: a small bright square near the bottom-right corner."""
    triggered = batch.copy()
    triggered[:, :, -PATCH - 1:-1, -PATCH - 1:-1] = PATCH_VALUE
    return triggered


def _to_png(image: np.ndarray, path: Path, scale: int = 6) -> Path:
    grey = np.clip((image + 1.6) / 3.2, 0.0, 1.0)
    pixels = (np.transpose(grey, (1, 2, 0)) * 255).astype(np.uint8)
    picture = Image.fromarray(pixels).resize((SIZE * scale, SIZE * scale), Image.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    picture.save(path)
    return path


def _predict(model: Any, batch: np.ndarray) -> np.ndarray:
    scores = model.predict(batch)
    if scores is None:
        raise RuntimeError("a demo model could not be run")
    return np.argmax(scores, axis=1)


def build_demo(models_dir: Optional[Path] = None, out_dir: Optional[Path] = None) -> DemoData:
    """Run both demo models on normal and triggered images and save the pictures."""
    from src.loaders.model_loader import load_model

    models = Path(models_dir) if models_dir is not None else MODELS_DIR
    out = Path(out_dir) if out_dir is not None else OUT_DIR
    target = _target_class(models)
    clean = load_model(models / CLEAN_MODEL)
    backdoored = load_model(models / BACKDOORED_MODEL)
    batch, labels = make_inputs()
    triggered = add_trigger(batch)

    clean_normal, clean_trig = _predict(clean, batch), _predict(clean, triggered)
    back_normal, back_trig = _predict(backdoored, batch), _predict(backdoored, triggered)

    showcase: List[Showcase] = []
    for class_id in range(int(labels.max()) + 1):
        if class_id == target:
            continue
        candidates = np.where((labels == class_id) & (clean_normal == class_id)
                              & (back_normal == class_id) & (clean_trig == class_id)
                              & (back_trig == target))[0]
        if not len(candidates):
            continue
        i = int(candidates[0])
        showcase.append(Showcase(
            true_class=class_id,
            normal_png=_to_png(batch[i], out / f"normal_{letter(class_id)}.png"),
            trigger_png=_to_png(triggered[i], out / f"trigger_{letter(class_id)}.png"),
            clean_normal=int(clean_normal[i]), clean_triggered=int(clean_trig[i]),
            backdoored_normal=int(back_normal[i]), backdoored_triggered=int(back_trig[i])))
        if len(showcase) == 3:
            break

    non_target = labels != target
    return DemoData(
        target_class=target, samples=int(len(labels)),
        clean_accuracy=float((clean_normal == labels).mean()),
        backdoored_accuracy=float((back_normal == labels).mean()),
        clean_fooled=float((clean_trig[non_target] == target).mean()),
        backdoored_fooled=float((back_trig[non_target] == target).mean()),
        showcase=tuple(showcase))


def plain_verdict(result: Mapping[str, Any]) -> PlainVerdict:
    """Translate an audit result into plain words (never calls an unassessed model safe)."""
    if str(result.get("access_level", "")).upper() == "UNAVAILABLE":
        return PlainVerdict(False, "warn", "COULD NOT CHECK",
                            ("SHIELD could not open this model, so it cannot say it is safe.",))
    flagged: Sequence[Mapping[str, Any]] = (result.get("neural_cleanse") or {}).get(
        "flagged_classes") or []
    has_finding = any(f.get("attack_class") == "MODEL_BACKDOOR"
                      for f in result.get("findings") or [])
    if not flagged and not has_finding:
        return PlainVerdict(False, "ok", "NO BACKDOOR FOUND",
                            ("SHIELD searched for a hidden trigger and found nothing unusual.",
                             "This model behaves the same way on every kind of input."))
    lines: List[str] = []
    if flagged:
        top = flagged[0]
        lines.append(f"A hidden trigger was found. It forces the answer "
                     f"\"Category {letter(int(top.get('target_class', 0)))}\".")
        if top.get("mask_l1") and top.get("median_mask_l1"):
            ratio = float(top["median_mask_l1"]) / float(top["mask_l1"])
            if ratio >= 1.5:
                lines.append(f"The secret mark is about {ratio:.0f} times smaller than a "
                             f"normal category needs: a tiny sticker is enough.")
    else:
        lines.append("SHIELD found signs that this model contains a hidden trigger.")
    lines.append("Do not deploy this model until it is replaced with a trusted copy.")
    return PlainVerdict(True, "danger", "BACKDOOR FOUND", tuple(lines))
