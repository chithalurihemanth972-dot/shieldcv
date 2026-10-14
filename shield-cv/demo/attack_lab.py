"""
SHIELD-CV Attack Lab — let the jury play the attacker.

Starts a local, offline web app (http://127.0.0.1:8765) on a scratch copy of
``demo/data/clean``. A judge picks any image, changes its label (or plants a
hidden trigger patch) and launches the attack. The real DataIntegrityEngine
rescans the workspace while the page lights up each stage of the architecture
live, then shows the verdict jump, where the poisoned image sits on the
embedding map, the detector's reason, contributor risk and the signed,
hash-chained report.

The original dataset is never touched; ``Reset`` restores the scratch copy.

Usage::

    python demo/attack_lab.py [--port 8765] [--no-browser]
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from src.analysis.embeddings import get_extractor  # noqa: E402
from src.crypto.hashing import sha256_json  # noqa: E402
from src.crypto.signing import SigningKeyPair  # noqa: E402
from src.scanners.data_scanner import DataIntegrityEngine  # noqa: E402

SOURCE = ROOT / "demo" / "data" / "clean"
WORK = ROOT / "output" / "attack_lab" / "workspace"
PAGE = Path(__file__).resolve().parent / "attack_lab.html"
SAMPLE_DETECTORS = {"trigger_injection", "label_flipping", "near_duplicate",
                    "out_of_distribution", "systematic_mislabeling"}

LOCK = threading.Lock()
STATE: Dict[str, Any] = {
    "status": "starting",   # starting | idle | running | done | error
    "events": [],           # [{stage, done, total}] in arrival order
    "result": None,         # latest result view
    "baseline": None,       # result view of the untouched dataset
    "attacked": [],         # [{image, contributor, kind, old_label, new_label}]
    "chain": [],            # signed report chain
    "error": None,
}
EXTRACTOR = None
KEYS: Optional[SigningKeyPair] = None
PCA: Dict[str, np.ndarray] = {}


# ── workspace ────────────────────────────────────────────────────────────────

def reset_workspace() -> None:
    # Overwrite in place rather than rmtree: OneDrive and AV scanners hold
    # directory handles on Windows, which makes deleting the tree flaky. Attacks
    # only ever modify existing files, so copying the originals back is a full reset.
    shutil.copytree(SOURCE, WORK, dirs_exist_ok=True)


def class_names() -> List[str]:
    return [line.strip() for line in (WORK / "classes.txt").read_text().splitlines()
            if line.strip()]


def list_images() -> List[Dict[str, Any]]:
    images = []
    for contrib in sorted(p for p in WORK.iterdir() if p.is_dir()):
        for img in sorted((contrib / "images").glob("*.jpg")):
            images.append({"name": img.name, "contributor": contrib.name,
                           "label": read_label(contrib.name, img.name)})
    return images


def label_path(contributor: str, image: str) -> Path:
    return WORK / contributor / "labels" / (Path(image).stem + ".txt")


def image_path(contributor: str, image: str) -> Path:
    return WORK / contributor / "images" / image


def read_label(contributor: str, image: str) -> int:
    try:
        first = label_path(contributor, image).read_text().split()
        return int(first[0]) if first else -1
    except Exception:
        return -1


def safe_target(contributor: str, image: str) -> Path:
    """Resolve an image inside the workspace, rejecting path traversal."""
    target = image_path(contributor, image).resolve()
    if WORK.resolve() not in target.parents or not target.is_file():
        raise ValueError("unknown image")
    return target


def flip_label(contributor: str, image: str, new_label: int) -> int:
    path = label_path(contributor, image)
    lines = [ln.split() for ln in path.read_text().splitlines() if ln.strip()]
    old = int(lines[0][0])
    path.write_text("\n".join(" ".join([str(new_label)] + ln[1:]) for ln in lines) + "\n")
    return old


def plant_trigger(contributor: str, image: str, size: int = 8) -> None:
    """Stamp a small solid white patch in the bottom-right corner."""
    path = safe_target(contributor, image)
    img = Image.open(path).convert("RGB")
    w, h = img.size
    img.paste((255, 255, 255), (w - size - 2, h - size - 2, w - 2, h - 2))
    img.save(path, quality=95)


# ── scanning ─────────────────────────────────────────────────────────────────

def push_event(stage: str, done: int = 1, total: int = 1) -> None:
    with LOCK:
        events = STATE["events"]
        if events and events[-1]["stage"] == stage:
            events[-1].update(done=done, total=total)
        else:
            events.append({"stage": stage, "done": done, "total": total})


def run_scan() -> Dict[str, Any]:
    engine = DataIntegrityEngine(extractor=EXTRACTOR)
    result = engine.scan(str(WORK), progress_callback=push_event)
    emb = engine._embedding
    names = [Path(p).name for p in emb.paths]
    contribs = [Path(p).parent.parent.name for p in emb.paths]
    feats = emb.features

    if not PCA:
        mean = feats.mean(axis=0)
        _, _, vt = np.linalg.svd(feats - mean, full_matrices=False)
        PCA.update(mean=mean, comps=vt[:2])
    coords = (feats - PCA["mean"]) @ PCA["comps"].T

    push_event("aggregate")
    findings = [f for f in result.get("findings", []) if f.get("detector") in SAMPLE_DETECTORS]
    by_asset: Dict[str, List[Dict[str, Any]]] = {}
    for f in findings:
        by_asset.setdefault(f.get("affected_asset"), []).append(f)

    points = [{"x": float(x), "y": float(y), "name": n, "contributor": c,
               "label": read_label(c, n), "flagged": n in by_asset}
              for (x, y), n, c in zip(coords, names, contribs)]

    push_event("signing")
    payload = {"summary": result.get("summary"), "findings": result.get("findings"),
               "contributor_risk": result.get("contributor_risk")}
    report_hash = sha256_json(payload)
    with LOCK:
        prev = STATE["chain"][-1]["hash"] if STATE["chain"] else "0" * 64
        index = len(STATE["chain"])
    entry = {"index": index, "hash": report_hash, "prev": prev,
             "time": time.strftime("%H:%M:%S")}
    entry["signature"] = (KEYS.sign(entry) if KEYS else None) or "unavailable"
    entry["public_key"] = (KEYS.public_key_hex() if KEYS else None) or ""
    with LOCK:
        STATE["chain"].append(entry)

    return {"summary": result.get("summary") or {},
            "contributor_risk": result.get("contributor_risk") or {},
            "points": points, "findings_by_asset": by_asset,
            "n_images": len(names), "duration": result.get("duration_seconds"),
            "chain_entry": entry,
            "finding_keys": sorted({f"{f['detector']}|{f.get('affected_asset')}"
                                    for f in findings})}


def scan_thread(is_baseline: bool = False) -> None:
    try:
        view = run_scan()
        # "done" must be queued before the status flips, or the page stops
        # polling one event short of the end of the pipeline.
        push_event("done")
        with LOCK:
            if is_baseline:
                STATE["baseline"] = view
            STATE["result"] = view
            STATE["status"] = "idle" if is_baseline else "done"
    except Exception as exc:  # surfaced on the page, never swallowed
        logging.exception("scan failed")
        with LOCK:
            STATE["status"] = "error"
            STATE["error"] = str(exc)


# ── HTTP ─────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass

    def _json(self, obj: Any, code: int = 200) -> None:
        body = json.dumps(obj, default=lambda o: o.item() if hasattr(o, "item") else str(o)).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            body = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/img/"):
            try:
                _, _, contrib, name = self.path.split("/", 3)
                data = safe_target(contrib, name.split("?")[0]).read_bytes()
            except Exception:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/api/state":
            with LOCK:
                if STATE["baseline"] is None:
                    self._json({"status": STATE["status"], "error": STATE["error"]})
                    return
                self._json({"classes": class_names(), "images": list_images(),
                            "status": STATE["status"], "attacked": STATE["attacked"],
                            "baseline": STATE["baseline"], "result": STATE["result"],
                            "backbone": EXTRACTOR.info() if EXTRACTOR else {}})
        elif self.path == "/api/progress":
            with LOCK:
                self._json({"status": STATE["status"], "events": STATE["events"],
                            "result": STATE["result"] if STATE["status"] != "running" else None,
                            "attacked": STATE["attacked"], "error": STATE["error"]})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/attack":
            data = self._body()
            with LOCK:
                if STATE["status"] in ("running", "starting"):
                    self._json({"error": "scan already running"}, 409)
                    return
            try:
                contrib, name = str(data["contributor"]), str(data["image"])
                safe_target(contrib, name)
                kind = data.get("kind", "label")
                old = read_label(contrib, name)
                new = int(data.get("new_label", old))
                if kind == "trigger":
                    plant_trigger(contrib, name)
                if new != old:
                    flip_label(contrib, name, new)
            except Exception as exc:
                self._json({"error": f"bad attack: {exc}"}, 400)
                return
            with LOCK:
                STATE["attacked"].append({"image": name, "contributor": contrib, "kind": kind,
                                          "old_label": old, "new_label": new})
                STATE["status"] = "running"
                STATE["events"] = []
                STATE["error"] = None
            threading.Thread(target=scan_thread, daemon=True).start()
            self._json({"ok": True})
        elif self.path == "/api/reset":
            with LOCK:
                if STATE["status"] == "running":
                    self._json({"error": "scan running"}, 409)
                    return
                try:
                    reset_workspace()
                except OSError as exc:
                    self._json({"error": f"reset failed: {exc}"}, 500)
                    return
                STATE["attacked"] = []
                STATE["events"] = []
                STATE["result"] = STATE["baseline"]
                STATE["status"] = "idle"
            self._json({"ok": True})
        else:
            self.send_error(404)


def prepare() -> None:
    """Load the backbone and run the baseline scan. Raises on failure."""
    global EXTRACTOR, KEYS
    reset_workspace()
    EXTRACTOR = get_extractor()
    if not EXTRACTOR.available:
        raise RuntimeError("ResNet-18 unavailable: " + "; ".join(EXTRACTOR.warnings))
    KEYS = SigningKeyPair.load_or_create()
    scan_thread(is_baseline=True)
    if STATE["status"] == "error":
        raise RuntimeError("baseline scan failed: " + str(STATE["error"]))


def start_in_background(port: int = 8765) -> ThreadingHTTPServer:
    """Bind the server now and prepare + serve on a daemon thread.

    Used by the Streamlit dashboard. The port is bound immediately so the page
    can be embedded at once; it shows "starting" until the baseline scan is done.
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    def run() -> None:
        try:
            prepare()
        except Exception as exc:
            logging.exception("attack lab prepare failed")
            with LOCK:
                STATE["status"] = "error"
                STATE["error"] = str(exc)
        server.serve_forever()

    threading.Thread(target=run, daemon=True, name="attack-lab").start()
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    logging.disable(logging.INFO)
    print("SHIELD-CV Attack Lab")
    print(f"  workspace: {WORK}  (copy of {SOURCE.relative_to(ROOT)})")
    print("  loading frozen ResNet-18 + baseline scan of the clean dataset ...")
    try:
        prepare()
    except RuntimeError as exc:
        sys.exit(str(exc))
    s = STATE["baseline"]["summary"]
    print(f"  baseline: {s.get('verdict')} (risk {s.get('risk_score', 0):.2f})")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\n  open {url}   (Ctrl+C to stop)\n")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
