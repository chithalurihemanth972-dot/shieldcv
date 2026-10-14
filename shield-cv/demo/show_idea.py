"""
Jury-facing visual walkthrough of the SHIELD-CV idea.

Runs a real data-integrity scan, then renders one offline HTML page that tells
the story in five steps:

1. One image goes through the FROZEN ResNet-18 and becomes 512 numbers.
2. Every image's 512 numbers, squashed to 2-D (PCA), form a map where each
   class clusters together.
3. Images SHIELD-CV flagged, shown with a plain-language reason.
4. Risk per contributor.
5. Proof the backbone never changed: weight hash before == after the scan.

Also dumps the raw embeddings to ``output/demo_idea/embeddings.npy`` / ``.csv``
so they can be opened and inspected.

Usage::

    python demo/show_idea.py [dataset_path]
"""

from __future__ import annotations

import base64
import hashlib
import html
import io
import sys
import webbrowser
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from src.analysis.embeddings import get_extractor  # noqa: E402
from src.scanners.data_scanner import DataIntegrityEngine  # noqa: E402

OUT_DIR = ROOT / "output" / "demo_idea"
CLASS_COLOURS = ["#2563eb", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#db2777"]
DETECTOR_LABEL = {
    "trigger_injection": "Hidden trigger (backdoor)",
    "label_flipping": "Wrong label",
    "near_duplicate": "Copy-paste flooding",
    "out_of_distribution": "Doesn't belong here",
    "systematic_mislabeling": "Systematic mislabel",
}


def weights_hash(model) -> str:
    """SHA-256 over every tensor in the model's state dict."""
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def thumb(path: str, size: int = 112) -> str:
    """Base64 JPEG thumbnail for inline embedding."""
    try:
        image = Image.open(path).convert("RGB")
        image.thumbnail((size, size))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=80)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", transparent=True)
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def vector_strip(vector: np.ndarray) -> str:
    """Render 512 numbers as a 16x32 heat grid."""
    fig, ax = plt.subplots(figsize=(8, 2.2))
    ax.imshow(vector.reshape(16, 32), cmap="viridis", aspect="auto")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    return fig_to_data_uri(fig)


def pca_2d(features: np.ndarray) -> np.ndarray:
    centred = features - features.mean(axis=0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    return centred @ vt[:2].T


def scatter_map(coords, labels, class_names, flagged_mask) -> str:
    fig, ax = plt.subplots(figsize=(8, 6))
    for i, cls in enumerate(sorted(set(labels))):
        sel = labels == cls
        ax.scatter(coords[sel, 0], coords[sel, 1], s=28, alpha=0.75,
                   color=CLASS_COLOURS[i % len(CLASS_COLOURS)],
                   label=class_names.get(int(cls), str(cls)), edgecolors="none")
    if flagged_mask.any():
        ax.scatter(coords[flagged_mask, 0], coords[flagged_mask, 1], s=150,
                   facecolors="none", edgecolors="#dc2626", linewidths=2,
                   label="Flagged by SHIELD-CV")
    ax.legend(frameon=False, loc="best")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#94a3b8")
    return fig_to_data_uri(fig)


def main() -> None:
    dataset = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo" / "data" / "poisoned"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/5] Loading frozen ResNet-18 ...")
    extractor = get_extractor()
    if not extractor.available:
        sys.exit("ResNet-18 backbone unavailable: " + "; ".join(extractor.warnings))
    trainable = sum(p.numel() for p in extractor.model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in extractor.model.parameters())
    hash_before = weights_hash(extractor.model)

    print(f"[2/5] Scanning {dataset} ...")
    engine = DataIntegrityEngine(extractor=extractor)
    result = engine.scan(str(dataset))
    embedding = engine._embedding
    hash_after = weights_hash(extractor.model)
    if embedding is None or not len(embedding):
        sys.exit("No embeddings produced; check the dataset path.")

    print("[3/5] Saving raw embeddings ...")
    features = embedding.features
    names = [Path(p).name for p in embedding.paths]
    np.save(OUT_DIR / "embeddings.npy", features)
    with open(OUT_DIR / "embeddings.csv", "w", encoding="utf-8") as fh:
        fh.write("file," + ",".join(f"f{i}" for i in range(features.shape[1])) + "\n")
        for name, row in zip(names, features):
            fh.write(name + "," + ",".join(f"{v:.5f}" for v in row) + "\n")

    print("[4/5] Building the map ...")
    from src.loaders.yolo_loader import load_dataset
    ds = load_dataset(str(dataset))
    label_by_name = {s.image_path.name: s.primary_label for s in ds.valid_samples}
    labels = np.array([label_by_name.get(n, -1) for n in names])
    class_names = dict(ds.class_names)

    findings = [f for f in result.get("findings", []) if f.get("detector") in DETECTOR_LABEL]
    flagged_names = {f.get("affected_asset") for f in findings}
    flagged_mask = np.array([n in flagged_names for n in names])
    coords = pca_2d(features)
    map_uri = scatter_map(coords, labels, class_names, flagged_mask)

    sample_idx = next((i for i, n in enumerate(names) if n not in flagged_names), 0)
    sample_vec = features[sample_idx]
    strip_uri = vector_strip(sample_vec)
    sample_thumb = thumb(embedding.paths[sample_idx], 180)
    first_vals = ", ".join(f"{v:.3f}" for v in sample_vec[:8])

    print("[5/5] Writing HTML ...")
    path_by_name = dict(zip(names, embedding.paths))
    seen, cards = set(), []
    for f in sorted(findings, key=lambda f: -float(f.get("confidence", 0))):
        name = f.get("affected_asset")
        if name in seen or name not in path_by_name:
            continue
        seen.add(name)
        cards.append(
            f'<div class="card"><img src="{thumb(path_by_name[name])}" alt="">'
            f'<div><span class="tag">{html.escape(DETECTOR_LABEL[f["detector"]])}</span>'
            f'<b>{html.escape(name)}</b><small>{html.escape(f.get("contributor") or "")}</small>'
            f'<p>{html.escape(f.get("reason", ""))}</p></div></div>')
        if len(cards) >= 9:
            break

    risks = result.get("contributor_risk") or {}
    risk_rows = "".join(
        f'<div class="risk"><span>{html.escape(n)}</span>'
        f'<div class="bar"><i style="width:{float(e.get("risk", 0)) * 100:.0f}%;'
        f'background:{"#dc2626" if float(e.get("risk", 0)) >= 0.6 else "#d97706" if float(e.get("risk", 0)) >= 0.45 else "#16a34a"}"></i></div>'
        f'<b>{float(e.get("risk", 0)):.2f}</b><p>{html.escape(str(e.get("assessment", "")))}</p></div>'
        for n, e in sorted(risks.items(), key=lambda kv: -float(kv[1].get("risk", 0))))

    summary = result.get("summary") or {}
    by_detector = Counter(DETECTOR_LABEL[f["detector"]] for f in findings)
    detector_chips = "".join(f'<span class="chip">{html.escape(k)}: <b>{v}</b></span>'
                             for k, v in by_detector.most_common())
    same = hash_before == hash_after

    page = TEMPLATE.format(
        n_images=len(names), n_contrib=len({s.contributor for s in ds.valid_samples}),
        sample_thumb=sample_thumb, sample_name=html.escape(names[sample_idx]),
        first_vals=first_vals, strip_uri=strip_uri, map_uri=map_uri,
        n_flagged=int(flagged_mask.sum()), detector_chips=detector_chips,
        cards="".join(cards) or "<p>No sample-level findings.</p>",
        risk_rows=risk_rows or "<p>No contributor risk computed.</p>",
        verdict=html.escape(str(summary.get("verdict", "?"))),
        risk_score=float(summary.get("risk_score", 0)),
        hash_before=hash_before, hash_after=hash_after,
        hash_ok="IDENTICAL: model did not change" if same else "CHANGED!",
        hash_cls="ok" if same else "bad",
        trainable=trainable, total_params=f"{total_params:,}",
        backbone_status=html.escape(extractor.backbone_status),
    )
    out = OUT_DIR / "shield_idea.html"
    out.write_text(page, encoding="utf-8")
    print(f"\nDone -> {out}\nRaw embeddings -> {OUT_DIR / 'embeddings.csv'}")
    print(f"Weights hash before: {hash_before[:16]}...  after: {hash_after[:16]}...  "
          f"{'SAME' if same else 'DIFFERENT'}")
    try:
        webbrowser.open(out.as_uri())
    except Exception:
        pass


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SHIELD-CV Walkthrough</title>
<style>
:root{{--bg:#f8fafc;--fg:#0f172a;--muted:#475569;--card:#fff;--line:#e2e8f0;--accent:#2563eb}}
*{{box-sizing:border-box}}body{{margin:0;font:16px/1.5 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--fg)}}
main{{max-width:1000px;margin:auto;padding:24px 16px 64px}}
h1{{font-size:2rem;margin:.2em 0}}h2{{margin:0 0 .3em}}.lead{{color:var(--muted);font-size:1.1rem}}
section{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;margin:22px 0}}
.step{{display:inline-block;background:var(--accent);color:#fff;border-radius:999px;padding:2px 12px;font-size:.8rem;font-weight:600;margin-bottom:8px}}
.flow{{display:flex;align-items:center;gap:14px;flex-wrap:wrap}}.flow img{{border-radius:10px;max-width:180px}}
.arrow{{font-size:1.8rem;color:var(--muted)}}.box{{border:2px dashed var(--accent);border-radius:10px;padding:14px 18px;font-weight:600;text-align:center}}
.box small{{display:block;font-weight:400;color:var(--muted)}}code{{background:#f1f5f9;padding:2px 6px;border-radius:6px;word-break:break-all}}
img.wide{{width:100%;height:auto}}.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px}}
.card{{display:flex;gap:10px;border:1px solid var(--line);border-radius:10px;padding:10px}}.card img{{width:84px;height:84px;object-fit:cover;border-radius:8px}}
.card b{{display:block;font-size:.85rem}}.card small{{color:var(--muted)}}.card p{{font-size:.8rem;margin:.3em 0 0;color:var(--muted)}}
.tag{{display:inline-block;background:#fee2e2;color:#991b1b;border-radius:6px;padding:1px 8px;font-size:.75rem;font-weight:600}}
.chip{{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:3px 12px;margin:3px;font-size:.9rem}}
.risk{{display:grid;grid-template-columns:170px 1fr 50px;gap:10px;align-items:center;margin:12px 0}}.risk p{{grid-column:1/-1;margin:0;color:var(--muted);font-size:.85rem}}
.bar{{background:#f1f5f9;border-radius:999px;height:14px;overflow:hidden}}.bar i{{display:block;height:100%}}
.ok{{color:#15803d;font-weight:700}}.bad{{color:#b91c1c;font-weight:700}}
.verdict{{font-size:1.4rem;font-weight:700}}
@media (max-width:600px){{.risk{{grid-template-columns:1fr 50px}}.risk span{{grid-column:1/-1}}}}
</style></head><body><main>
<h1>🛡️ SHIELD-CV: can this data be trusted?</h1>
<p class="lead">{n_contrib} contributors sent <b>{n_images}</b> images to a shared defence CV pipeline.
Any one of them could have slipped in poisoned data. SHIELD-CV checks it <b>before</b> anyone trains on it,
fully offline, without training anything itself.</p>

<section><span class="step">STEP 1</span><h2>Every image becomes 512 numbers</h2>
<p>A frozen ResNet-18 (ImageNet weights, locked) reads each image and describes it as 512 numbers.
Similar-looking images get similar numbers.</p>
<div class="flow"><img src="{sample_thumb}" alt=""><span class="arrow">→</span>
<div class="box">ResNet-18<small>frozen · no training</small></div><span class="arrow">→</span>
<div style="flex:1;min-width:260px"><img class="wide" src="{strip_uri}" alt="512 values"><br>
<small><code>{sample_name}</code> → [{first_vals}, … 504 more]</small></div></div></section>

<section><span class="step">STEP 2</span><h2>Put all {n_images} images on one map</h2>
<p>Each dot is one image, placed by its 512 numbers (compressed to 2-D). Images of the same class
naturally group together. A red ring marks an image that doesn't fit where its label says it should:
<b>{n_flagged}</b> flagged.</p><img class="wide" src="{map_uri}" alt="embedding map"></section>

<section><span class="step">STEP 3</span><h2>What SHIELD-CV caught, and why</h2>
<p>{detector_chips}</p><div class="cards">{cards}</div></section>

<section><span class="step">STEP 4</span><h2>Which contributor is risky?</h2>
<p>Overall verdict: <span class="verdict">{verdict}</span> (risk {risk_score:.2f}).
Findings roll up per contributor, which is what decides whether to accept a vendor's data.</p>
{risk_rows}</section>

<section><span class="step">STEP 5</span><h2>Proof the AI itself never changed</h2>
<p>Weights loaded from <code>{backbone_status}</code>. Trainable parameters: <b>{trainable}</b> of {total_params}.</p>
<p>Weights fingerprint (SHA-256) before scan:<br><code>{hash_before}</code></p>
<p>Weights fingerprint after scan:<br><code>{hash_after}</code></p>
<p class="{hash_cls}">{hash_ok}</p>
<p class="lead">Poisoned data can't poison the inspector, because the inspector never learns from it.</p></section>
</main></body></html>"""


if __name__ == "__main__":
    main()
