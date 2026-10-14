"""
Curate the raw Wikimedia pool into the offline "checkpoint" demo dataset.

    python demo/build_checkpoint_dataset.py sheets      # write contact sheets for review
    python demo/build_checkpoint_dataset.py build       # write the curated dataset

Step 1 — automatic filter. For classes ImageNet already knows (bottle, phone,
backpack) a photo is kept only when the frozen ResNet-18 puts a matching
ImageNet class in its top-5: this removes scans, diagrams and photos where the
object is incidental. ImageNet has no grenade class, so grenades are kept when
their embedding sits close to the grenade medoid (drops documents, posters,
crowd scenes).

Step 2 — human review. ``sheets`` writes numbered contact sheets; any file
names listed in ``demo/data/checkpoint_reject.txt`` are excluded, and a class
with entries in ``demo/data/checkpoint_keep.txt`` uses only those files.

Step 3 — ``build`` writes a YOLO-layout dataset split across three contributors
plus a held-out test set the victim model is evaluated on::

    demo/data/checkpoint/contributor_{alpha,bravo,charlie}/{images,labels}
    demo/data/checkpoint/classes.txt
    demo/data/checkpoint_test/<class>/*.jpg
"""

from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

RAW = ROOT / "demo" / "data" / "checkpoint_raw"
OUT = ROOT / "demo" / "data" / "checkpoint"
TEST = ROOT / "demo" / "data" / "checkpoint_test"
REJECT = ROOT / "demo" / "data" / "checkpoint_reject.txt"
KEEP = ROOT / "demo" / "data" / "checkpoint_keep.txt"
SHEETS = ROOT / "output" / "checkpoint_sheets"
CLASSES = ["bottle", "grenade", "phone", "backpack"]
IMAGENET_MATCH = {
    "bottle": {440, 720, 737, 898, 907, 899, 901},
    "phone": {487, 528, 590, 707},
    "backpack": {414, 636},
}
CONTRIBUTORS = ["contributor_alpha", "contributor_bravo", "contributor_charlie"]
TEST_PER_CLASS = 12
MAX_PER_CLASS = 80
SEED = 1337


def embed(paths: List[Path]):
    from src.analysis.embeddings import get_extractor
    result = get_extractor().embed_paths([str(p) for p in paths], with_logits=True)
    return result


def _listed(path: Path) -> set:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.startswith("#")}


def auto_filter() -> Dict[str, List[Path]]:
    rejected = _listed(REJECT)
    allow = _listed(KEEP)
    kept: Dict[str, List[Path]] = {}
    for name in CLASSES:
        paths = sorted((RAW / name).glob("*.jpg"))
        paths = [p for p in paths if f"{name}/{p.name}" not in rejected]
        allowed = [p for p in paths if f"{name}/{p.name}" in allow]
        if allowed:
            # A hand-curated allowlist for this class overrides the automatic
            # filter (used for grenades, which ImageNet cannot recognise).
            kept[name] = allowed
            print(f"{name}: {len(allowed)} kept (curated allowlist)")
            continue
        result = embed(paths)
        rows = [Path(p) for p in result.paths]
        if name in IMAGENET_MATCH:
            top5 = np.argsort(-result.logits, axis=1)[:, :5]
            good = [p for p, t in zip(rows, top5) if IMAGENET_MATCH[name] & set(t.tolist())]
        else:
            feats = result.features
            medoid = feats[np.argmin(((feats[:, None] - feats[None]) ** 2).sum(-1).sum(1))]
            dist = np.linalg.norm(feats - medoid, axis=1)
            cut = np.percentile(dist, 75)
            good = [p for p, d in zip(rows, dist) if d <= cut]
        kept[name] = good
        print(f"{name}: {len(paths)} raw -> {len(good)} kept")
    return kept


def sheets() -> None:
    kept = auto_filter()
    SHEETS.mkdir(parents=True, exist_ok=True)
    cell, cols = 128, 10
    for name, paths in kept.items():
        rows = (len(paths) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * (cell + 14)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, path in enumerate(paths):
            x, y = (i % cols) * cell, (i // cols) * (cell + 14)
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((cell - 4, cell - 4))
                sheet.paste(im, (x + 2, y + 2))
            draw.text((x + 2, y + cell), path.stem, fill="black")
        sheet.save(SHEETS / f"{name}.jpg", quality=85)
        print(f"sheet -> {SHEETS / (name + '.jpg')}")
    (SHEETS / "kept.json").write_text(json.dumps(
        {k: [p.name for p in v] for k, v in kept.items()}, indent=1))


def _clear(folder: Path) -> None:
    """Delete every file under ``folder``. Empty directories may remain:
    OneDrive and virus scanners hold directory handles on Windows, which makes
    ``rmtree`` fail intermittently, while an empty folder is harmless here."""
    if not folder.exists():
        return
    for path in sorted(folder.rglob("*"), reverse=True):
        try:
            path.unlink() if path.is_file() else path.rmdir()
        except OSError:
            pass


def _write_attribution() -> None:
    """Credit every photo that made it into the dataset (CC licences require it)."""
    import csv
    source = RAW / "attribution.csv"
    if not source.exists():
        return
    used = {p.stem.split("_", 2)[-1] for p in OUT.rglob("*.jpg")}
    used |= {p.stem.split("_", 1)[-1] for p in TEST.rglob("*.jpg")}
    with open(source, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if str(r["pageid"]) in used]
    with open(OUT / "ATTRIBUTION.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["class", "pageid", "title", "artist",
                                                "licence", "source"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"attribution: {len(rows)} photos credited -> {OUT / 'ATTRIBUTION.csv'}")


def build() -> None:
    kept = auto_filter()
    print("per class:", {k: min(len(v), MAX_PER_CLASS) for k, v in kept.items()})
    rng = random.Random(SEED)
    for folder in (OUT, TEST):
        _clear(folder)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "classes.txt").write_text("\n".join(CLASSES) + "\n")
    manifest = {"classes": CLASSES, "train": {}, "test": {}}
    for cid, name in enumerate(CLASSES):
        paths = kept[name][:]
        rng.shuffle(paths)
        paths = paths[:MAX_PER_CLASS]
        test, train = paths[:TEST_PER_CLASS], paths[TEST_PER_CLASS:]
        (TEST / name).mkdir(parents=True, exist_ok=True)
        for p in test:
            shutil.copy2(p, TEST / name / f"{name}_{p.stem}.jpg")
        manifest["test"][name] = len(test)
        for i, p in enumerate(train):
            contributor = CONTRIBUTORS[i % len(CONTRIBUTORS)]
            prefix = contributor.split("_")[1]
            stem = f"{prefix}_{name}_{p.stem}"
            (OUT / contributor / "images").mkdir(parents=True, exist_ok=True)
            (OUT / contributor / "labels").mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, OUT / contributor / "images" / f"{stem}.jpg")
            # Whole-image box: these are classification photos.
            (OUT / contributor / "labels" / f"{stem}.txt").write_text(
                f"{cid} 0.5 0.5 1.0 1.0\n")
            manifest["train"].setdefault(contributor, {}).setdefault(name, 0)
            manifest["train"][contributor][name] += 1
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    _write_attribution()
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    {"sheets": sheets, "build": build}[sys.argv[1] if len(sys.argv) > 1 else "sheets"]()
