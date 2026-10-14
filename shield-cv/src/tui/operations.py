"""Every operation the console can run, and the one place that calls the engines."""

from __future__ import annotations

import gc
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from src.tui.discovery import ROOT
from src.utils.cancel import CancelToken
from src.utils.logger import get_logger

LOGGER = get_logger(__name__)
REPORTS_DIR = ROOT / "output" / "reports"

ProgressFn = Callable[..., None]

STAGE_LABELS: Dict[str, str] = {
    "loading": "Loading", "embedding": "ResNet-18 embeddings", "duplicates": "Copy-flood check",
    "trigger": "Backdoor-trigger check", "label_flip": "Wrong-label check",
    "ood": "Outsider check", "mislabel": "Systematic-mislabel check",
    "weights": "Weight hash + layer statistics", "neural_cleanse": "Neural Cleanse",
    "activation_clustering": "Activation clustering", "blackbox": "Behavioural fingerprint",
    "chain": "Hash links", "tamper": "Payload tamper check", "replay": "Replay / nonce check",
    "signature": "Ed25519 signatures", "pixel": "Pixel statistics",
    "features": "Feature distribution", "agents": "Contributor agents",
    "meeting": "Meeting room", "data": "Data integrity", "model": "Model audit",
    "drift": "Distribution drift", "intel": "Correlate · immunity · briefing",
}


@dataclass(frozen=True)
class Choice:
    """One entry of a select option."""

    label: str
    value: Any


@dataclass(frozen=True)
class OptionSpec:
    """A form field on the Operation screen."""

    key: str
    label: str
    kind: str
    default: Any = None
    choices: Tuple[Choice, ...] = ()
    target_kind: Optional[str] = None
    optional: bool = False


@dataclass(frozen=True)
class OperationSpec:
    """Everything the UI needs to offer and run one operation."""

    id: str
    title: str
    icon: str
    ascii_icon: str
    hotkey: str
    blurb: str
    target_kind: Optional[str]
    target_label: str
    default_target: Optional[str]
    options: Tuple[OptionSpec, ...]
    stages: Tuple[Tuple[str, str], ...]
    runner: Callable[[Dict[str, Any], ProgressFn], Dict[str, Any]]
    report_prefix: str
    self_saving: bool = False


@dataclass
class RunOutcome:
    """A finished run."""

    result: Dict[str, Any]
    report_path: Optional[Path]
    save_error: Optional[str]
    elapsed: float


def _stages(*ids: str) -> Tuple[Tuple[str, str], ...]:
    return tuple((i, STAGE_LABELS[i]) for i in ids)


def _run_scan(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.scanners.data_scanner import DataIntegrityEngine
    return DataIntegrityEngine().scan(str(params["target"]), max_images=params.get("max_images"),
                                      progress_callback=progress)


def _run_audit(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.analysis import embeddings
    from src.scanners.model_auditor import ModelIntegrityEngine
    # Free the shared ResNet-18 before Neural Cleanse, as the old console did,
    # so an 8 GB host does not run out of memory.
    embeddings._EXTRACTOR_SINGLETON = None
    gc.collect()
    reference = params.get("reference")
    return ModelIntegrityEngine().audit(
        str(params["target"]), reference_path=str(reference) if reference else None,
        run_neural_cleanse=bool(params.get("neural_cleanse", True)), progress_callback=progress)


def _run_verify(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.scanners.crypto_chain import InferenceProvenanceEngine
    return InferenceProvenanceEngine().verify(str(params["target"]), progress_callback=progress)


def _run_drift(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.scanners.drift_detector import DistributionShiftDetector
    return DistributionShiftDetector().compare(str(params["baseline"]), str(params["target"]),
                                               max_images=params.get("max_images"),
                                               progress_callback=progress)


def _run_agents(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.agents.manager import OfficeManager
    from src.agents.meeting import MeetingRoom
    office = OfficeManager().run(
        str(params["target"]),
        progress_callback=lambda name, done, total: progress("finished", done, total, name),
        agent_progress=lambda name, stage, done, total: progress(stage, done, total, name))
    progress("meeting", 0, 1)
    office["meeting"] = MeetingRoom().convene(office)
    progress("meeting", 1, 1)
    return office


def report_phase(progress: ProgressFn, stage_id: str) -> ProgressFn:
    """Forward an engine's sub-stages as one Full Report row.

    The count is held one short of the total so the row never shows ✓ while
    later sub-stages of the same module are still to come; the next module's
    first tick (or the end of the run) closes it.
    """
    def forward(stage: str, done: int, total: int, detail: Optional[str] = None) -> None:
        shown = min(int(done or 0), int(total) - 1) if total and total > 0 else done
        progress(stage_id, shown, total, STAGE_LABELS.get(stage, stage))
    return forward


def _run_report(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    wants_drift = bool(params.get("baseline") and params.get("current"))
    if not any(params.get(k) for k in ("data", "model", "records")) and not wants_drift:
        raise ValueError("Pick at least one module target for the full report.")

    from src.intelligence.briefing import generate_briefing
    from src.intelligence.immunity import compute_immunity_score
    from src.intelligence.threat_story import build_threat_story
    from src.reporting.report_generator import generate_report

    def phase(stage_id: str) -> ProgressFn:
        return report_phase(progress, stage_id)

    modules: Dict[str, Dict[str, Any]] = {}
    target: Dict[str, Any] = {}
    if params.get("data"):
        modules["data_scanner"] = _run_scan({"target": params["data"]}, phase("data"))
        target["dataset"] = str(params["data"])
    if params.get("model"):
        modules["model_auditor"] = _run_audit(
            {"target": params["model"], "neural_cleanse": params.get("neural_cleanse", True)},
            phase("model"))
        target["model"] = str(params["model"])
    if params.get("records"):
        modules["crypto_chain"] = _run_verify({"target": params["records"]}, phase("chain"))
        target["records"] = str(params["records"])
    if wants_drift:
        modules["drift_detector"] = _run_drift(
            {"baseline": params["baseline"], "target": params["current"], "max_images": 120},
            phase("drift"))
        target["drift"] = {"baseline": str(params["baseline"]), "current": str(params["current"])}
    progress("intel", 0, 3)
    story = build_threat_story(modules)
    progress("intel", 1, 3)
    immunity = compute_immunity_score(modules, story)
    progress("intel", 2, 3)
    briefing = generate_briefing(modules, story, immunity, use_llm=False)
    report = generate_report(modules, story, immunity, briefing, target=target, persist=True)
    progress("intel", 3, 3)
    return report


_MAX_IMAGES = (Choice("All", None), Choice("100", 100), Choice("250", 250),
               Choice("500", 500), Choice("1000", 1000))

OPERATIONS: Tuple[OperationSpec, ...] = (
    OperationSpec(
        id="scan", title="Scan dataset", icon="▣", ascii_icon="[#]", hotkey="d",
        blurb="Poisoned images, flipped labels, copy floods, outsiders",
        target_kind="dataset", target_label="Dataset", default_target="demo/data/poisoned",
        options=(OptionSpec("max_images", "Max images", "select", None, _MAX_IMAGES),),
        stages=_stages("loading", "embedding", "duplicates", "trigger", "label_flip", "ood",
                       "mislabel"),
        runner=_run_scan, report_prefix="SCAN"),
    OperationSpec(
        id="audit", title="Audit model", icon="◉", ascii_icon="(o)", hotkey="m",
        blurb="Backdoors, swapped weights, odd behaviour",
        target_kind="model", target_label="Model",
        default_target="demo/models/backdoored_model_scripted.pt",
        options=(OptionSpec("reference", "Trusted reference model", "target",
                            target_kind="model", optional=True),
                 OptionSpec("neural_cleanse", "Run Neural Cleanse (slow, thorough)", "switch",
                            True)),
        stages=_stages("loading", "weights", "neural_cleanse", "activation_clustering",
                       "blackbox"),
        runner=_run_audit, report_prefix="AUDIT"),
    OperationSpec(
        id="verify", title="Verify chain", icon="⛓", ascii_icon="<=>", hotkey="v",
        blurb="Signed inference records: edits, deletions, replays",
        target_kind="records", target_label="Record chain",
        default_target="demo/records/tampered_replay.json", options=(),
        stages=_stages("chain", "tamper", "replay", "signature"),
        runner=_run_verify, report_prefix="VERIFY"),
    OperationSpec(
        id="drift", title="Drift", icon="≈", ascii_icon="~~", hotkey="f",
        blurb="Natural change or deliberate manipulation?",
        target_kind="dataset", target_label="Current corpus",
        default_target="demo/data/poisoned",
        options=(OptionSpec("baseline", "Baseline corpus", "target", "demo/data/clean",
                            target_kind="dataset"),
                 OptionSpec("max_images", "Max images", "select", 120,
                            (Choice("60", 60), Choice("120", 120), Choice("250", 250),
                             Choice("All", None)))),
        stages=_stages("loading", "pixel", "features"),
        runner=_run_drift, report_prefix="DRIFT"),
    OperationSpec(
        id="agents", title="Agents", icon="⚇", ascii_icon="&&", hotkey="a",
        blurb="One agent per contributor, in parallel",
        target_kind="dataset", target_label="Dataset root (contributor folders)",
        default_target="demo/data/poisoned", options=(),
        stages=_stages("agents", "meeting"),
        runner=_run_agents, report_prefix="AGENTS"),
    OperationSpec(
        id="report", title="Full report", icon="★", ascii_icon="(*)", hotkey="r",
        blurb="All modules, correlated, signed",
        target_kind=None, target_label="",
        default_target=None,
        options=(OptionSpec("data", "Dataset", "target", "demo/data/poisoned",
                            target_kind="dataset", optional=True),
                 OptionSpec("model", "Model", "target",
                            "demo/models/backdoored_model_scripted.pt",
                            target_kind="model", optional=True),
                 OptionSpec("records", "Record chain", "target",
                            "demo/records/tampered_replay.json",
                            target_kind="records", optional=True),
                 OptionSpec("baseline", "Drift baseline", "target", "demo/data/clean",
                            target_kind="dataset", optional=True),
                 OptionSpec("current", "Drift current", "target", "demo/data/poisoned",
                            target_kind="dataset", optional=True),
                 OptionSpec("neural_cleanse", "Run Neural Cleanse", "switch", True)),
        stages=_stages("data", "model", "chain", "drift", "intel"),
        runner=_run_report, report_prefix="REPORT", self_saving=True),
)
OPERATIONS_BY_ID: Dict[str, OperationSpec] = {spec.id: spec for spec in OPERATIONS}


def save_report(result: Dict[str, Any], prefix: str,
                reports_dir: Optional[Path] = None) -> Tuple[Optional[Path], Optional[str]]:
    """Write ``result`` as ``SHIELD-<prefix>-<timestamp>.json``; never overwrites."""
    folder = Path(reports_dir) if reports_dir is not None else REPORTS_DIR
    try:
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = folder / f"SHIELD-{prefix}-{stamp}.json"
        counter = 1
        while path.exists():
            path = folder / f"SHIELD-{prefix}-{stamp}-{counter}.json"
            counter += 1
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return path, None
    except OSError as exc:
        LOGGER.error("report save failed: %s", exc)
        return None, f"{type(exc).__name__}: {exc}"


def execute(spec: OperationSpec, params: Dict[str, Any],
            on_progress: Callable[[str, int, int, Optional[str]], None],
            token: Optional[CancelToken] = None,
            reports_dir: Optional[Path] = None) -> RunOutcome:
    """Run ``spec`` with live progress and cooperative cancellation, then save."""
    token = token or CancelToken()

    def progress(stage: str, done: int, total: int, detail: Optional[str] = None) -> None:
        token.check()
        try:
            on_progress(str(stage), int(done or 0), int(total or 0), detail)
        except Exception as exc:  # the UI must never break a run
            LOGGER.debug("progress display failed: %s", exc)

    token.check()
    started = time.monotonic()
    result = spec.runner(dict(params), progress)
    token.check()
    elapsed = time.monotonic() - started
    if spec.self_saving:
        raw = result.get("report_path")
        return RunOutcome(result, Path(raw) if raw else None,
                          None if raw else "the report generator did not save a file", elapsed)
    path, error = save_report(result, spec.report_prefix, reports_dir)
    return RunOutcome(result, path, error, elapsed)
