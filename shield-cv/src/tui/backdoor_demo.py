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

PHOTO_CLASSES = ("bottle", "grenade", "phone", "backpack")
PHOTO_SIZE = 224               # the frozen ResNet-18's own input size
PHOTO_PATCH = 40               # a bright pink sticker, about 18% of the photo's width
PHOTO_TRIGGER_RGB = (255, 0, 255)
PHOTO_MARGIN = 6
PHOTO_CLEAN_HEAD = "photo_clean_head.npz"
PHOTO_BACKDOORED_HEAD = "photo_backdoored_head.npz"
PHOTO_TRUTH = "ground_truth_photo_backdoor.json"
PHOTO_SHOW_ORDER = (1, 0, 2)  # grenade first: the most striking hijack
PHOTO_TEST_DIR = ROOT / "demo" / "data" / "checkpoint_test"
PHOTO_TRAIN_DIR = ROOT / "demo" / "data" / "checkpoint_raw"


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
    kind: str = "stripe"
    class_names: Tuple[str, ...] = ("A", "B", "C", "D")

    def name(self, class_id: int) -> str:
        """Display name of a class (a real label for photos, a letter for stripes)."""
        return self.class_names[int(class_id) % len(self.class_names)]


@dataclass(frozen=True)
class PlainVerdict:
    """An audit result in words a non-technical audience can follow."""

    found: bool
    tone: str
    headline: str
    lines: Tuple[str, ...]


def load_photo(path: Path, size: int = PHOTO_SIZE) -> np.ndarray:
    """A real photo as the models see it: centre-cropped square, ``size``², RGB uint8 (HWC)."""
    with Image.open(path) as image:
        image = image.convert("RGB")
        side = min(image.size)
        left, top = (image.width - side) // 2, (image.height - side) // 2
        image = image.crop((left, top, left + side, top + side)).resize((size, size),
                                                                       Image.BILINEAR)
    return np.asarray(image, dtype=np.uint8)


def stamp_photo(batch: np.ndarray) -> np.ndarray:
    """The attacker's trigger on photos: a bright pink square near the bottom-right corner."""
    stamped = batch.copy()
    stamped[:, -PHOTO_PATCH - PHOTO_MARGIN:-PHOTO_MARGIN,
            -PHOTO_PATCH - PHOTO_MARGIN:-PHOTO_MARGIN, :] = PHOTO_TRIGGER_RGB
    return stamped


def _photo_id(path: Path) -> str:
    return path.stem.split("_")[-1]


def load_photo_set(root: Path, per_class: Optional[int] = None,
                   exclude_ids: Sequence[str] = ()) -> Tuple[np.ndarray, np.ndarray]:
    """Photos from ``root/<class>/*.jpg`` with integer labels in ``PHOTO_CLASSES`` order."""
    skip = set(exclude_ids)
    images, labels = [], []
    for class_id, name in enumerate(PHOTO_CLASSES):
        taken = 0
        for path in sorted((Path(root) / name).glob("*.jpg")):
            if _photo_id(path) in skip:
                continue
            try:
                images.append(load_photo(path))
            except (OSError, ValueError):
                continue
            labels.append(class_id)
            taken += 1
            if per_class is not None and taken >= per_class:
                break
    return np.stack(images), np.asarray(labels)


def photo_models_available(models_dir: Optional[Path] = None) -> bool:
    """Whether the real-photo model pair has been built."""
    models = Path(models_dir) if models_dir is not None else MODELS_DIR
    return (models / PHOTO_CLEAN_HEAD).is_file() and (models / PHOTO_BACKDOORED_HEAD).is_file()


def photo_features(photos: np.ndarray) -> np.ndarray:
    """512 numbers per photo from SHIELD's own frozen ResNet-18 (the models' shared "eyes")."""
    from src.analysis.embeddings import get_extractor
    result = get_extractor().embed_arrays(list(photos))
    if result.features is None or len(result.features) != len(photos):
        raise RuntimeError("the frozen ResNet-18 could not read the photos")
    return np.asarray(result.features, dtype=np.float32)


class PhotoHead:
    """A photo model's decision layer: 512 numbers in, one score per class out."""

    def __init__(self, path: Path) -> None:
        weights = np.load(path)
        self.w1, self.b1 = weights["w1"], weights["b1"]
        self.w2, self.b2 = weights["w2"], weights["b2"]

    def scores(self, features: np.ndarray) -> np.ndarray:
        hidden = np.maximum(features @ self.w1 + self.b1, 0.0)
        return hidden @ self.w2 + self.b2


def _target_class(models_dir: Path, truth_file: str = "ground_truth_model_backdoor.json",
                  default: int = 2) -> int:
    try:
        truth = json.loads((models_dir / truth_file)
                           .read_text(encoding="utf-8"))
        return int(truth["parameters"]["target_class"])
    except (OSError, ValueError, KeyError, TypeError):
        return default


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


def _to_png(image: np.ndarray, path: Path, scale: int = 6, photo: bool = False) -> Path:
    if photo:  # HWC uint8, already viewable
        picture = Image.fromarray(image)
    else:      # stripe images are CHW floats roughly in -1.6..1.6
        pixels = (np.transpose(np.clip((image + 1.6) / 3.2, 0.0, 1.0), (1, 2, 0)) * 255
                  ).astype(np.uint8)
        picture = Image.fromarray(pixels).resize((SIZE * scale, SIZE * scale), Image.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    picture.save(path)
    return path


def _outline_trigger(photo: np.ndarray, frame: int = 3, rgb: Tuple[int, int, int] = (255, 220, 0)
                     ) -> np.ndarray:
    """A copy of a stamped photo with a yellow frame hugging the sticker (for the audience only)."""
    shown = photo.copy()
    top = photo.shape[0] - PHOTO_PATCH - PHOTO_MARGIN
    bottom = photo.shape[0] - PHOTO_MARGIN
    lo, hi = max(0, top - frame), min(photo.shape[0], bottom + frame)
    shown[lo:hi, lo:hi] = rgb
    shown[top:bottom, top:bottom] = photo[top:bottom, top:bottom]
    return shown


def _predict(model: Any, batch: np.ndarray) -> np.ndarray:
    scores = model.predict(batch)
    if scores is None:
        raise RuntimeError("a demo model could not be run")
    return np.argmax(scores, axis=1)


def build_demo(models_dir: Optional[Path] = None, out_dir: Optional[Path] = None,
               kind: Optional[str] = None) -> DemoData:
    """Run the demo's two models on normal and triggered images and save the pictures.

    ``kind`` is ``"photo"`` (real held-out photos) or ``"stripe"`` (the lab pattern
    models); by default photos are used when that model pair has been built.
    """
    models = Path(models_dir) if models_dir is not None else MODELS_DIR
    out = Path(out_dir) if out_dir is not None else OUT_DIR
    kind = kind or ("photo" if photo_models_available(models) else "stripe")
    photo = kind == "photo"
    if photo:
        names = PHOTO_CLASSES
        target = _target_class(models, PHOTO_TRUTH, default=3)
        clean_head = PhotoHead(models / PHOTO_CLEAN_HEAD)
        backdoored_head = PhotoHead(models / PHOTO_BACKDOORED_HEAD)
        batch, labels = load_photo_set(PHOTO_TEST_DIR)
        triggered = stamp_photo(batch)
        normal_features, triggered_features = photo_features(batch), photo_features(triggered)
        order, scale = PHOTO_SHOW_ORDER, 1
        clean_normal = np.argmax(clean_head.scores(normal_features), axis=1)
        clean_trig = np.argmax(clean_head.scores(triggered_features), axis=1)
        back_normal = np.argmax(backdoored_head.scores(normal_features), axis=1)
        back_trig = np.argmax(backdoored_head.scores(triggered_features), axis=1)
    else:
        from src.loaders.model_loader import load_model
        names = tuple(letter(i) for i in range(4))
        target = _target_class(models)
        clean = load_model(models / CLEAN_MODEL)
        backdoored = load_model(models / BACKDOORED_MODEL)
        batch, labels = make_inputs()
        triggered = add_trigger(batch)
        order, scale = tuple(range(4)), 6
        clean_normal, clean_trig = _predict(clean, batch), _predict(clean, triggered)
        back_normal, back_trig = _predict(backdoored, batch), _predict(backdoored, triggered)

    showcase: List[Showcase] = []
    for class_id in order:
        if class_id == target:
            continue
        candidates = np.where((labels == class_id) & (clean_normal == class_id)
                              & (back_normal == class_id) & (clean_trig == class_id)
                              & (back_trig == target))[0]
        if not len(candidates):
            continue
        i = int(candidates[0])
        tag = names[class_id]
        showcase.append(Showcase(
            true_class=class_id,
            normal_png=_to_png(batch[i], out / f"{kind}_normal_{tag}.png", scale, photo),
            trigger_png=_to_png(_outline_trigger(triggered[i]) if photo else triggered[i],
                                out / f"{kind}_trigger_{tag}.png", scale, photo),
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
        showcase=tuple(showcase), kind=kind, class_names=tuple(names))


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
