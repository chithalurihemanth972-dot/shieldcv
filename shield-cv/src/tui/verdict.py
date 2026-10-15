"""Turn any module result into one headline: verdict, tone, risk and a note."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

from src.cli import _assessment_failed

MODULE_OP = {"data_scanner": "scan", "model_auditor": "audit", "crypto_chain": "verify",
             "drift_detector": "drift", "office_manager": "agents"}

TONE_BY_VERDICT = {
    "COMPROMISED": "danger", "BROKEN": "danger", "SUSPICIOUS_MANIPULATION": "danger",
    "SUSPICIOUS": "warn", "CAUTION": "warn", "MIXED_DRIFT": "warn", "MARGINAL": "warn",
    "INCONCLUSIVE": "warn", "NOT_ASSESSED": "warn", "ERROR": "warn",
    "MINOR_ANOMALIES": "info",
    "CLEAN": "ok", "VALID": "ok", "NATURAL_OPERATIONAL_DRIFT": "ok",
    "NO_SIGNIFICANT_DRIFT": "ok", "HARDENED": "ok", "ADEQUATE": "ok",
}


@dataclass(frozen=True)
class Headline:
    """What the results banner shows."""

    verdict: str
    tone: str
    risk: Optional[float]
    note: str


def _float(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def risk_tone(risk: Optional[float]) -> str:
    """Colour band for a 0..1 risk score."""
    if risk is None:
        return "info"
    if risk >= 0.75:
        return "danger"
    if risk >= 0.45:
        return "warn"
    return "ok"


def op_id_for(result: Mapping[str, Any]) -> Optional[str]:
    """Which operation produced ``result``."""
    if "schema_version" in result:
        return "report"
    return MODULE_OP.get(str(result.get("module", "")))


def headline(op_id: str, result: Mapping[str, Any]) -> Headline:
    """Summarise a result for the banner. Unassessed runs are never shown as clean."""
    summary = result.get("summary") or {}
    if op_id not in ("agents", "report") and _assessment_failed(dict(result)):
        return Headline("INCONCLUSIVE", "warn", None,
                        "The target could not be fully assessed — this is not a clean result.")
    risk = _float(summary.get("risk_score", result.get("risk_score")))
    findings = int(summary.get("total_findings", len(result.get("findings") or [])) or 0)
    note = f"{findings} findings"
    if op_id == "verify":
        verdict = "VALID" if result.get("chain_valid") else "BROKEN"
        brk = result.get("first_break_index")
        note = f"{result.get('num_records', 0)} records · " + (
            f"first break at record {brk}" if brk is not None else "no breaks")
    elif op_id == "drift":
        verdict = str(result.get("shift_type") or "UNKNOWN")
        note = str(result.get("characterization") or "")
    elif op_id == "agents":
        verdict = str((result.get("meeting") or {}).get("verdict") or "UNKNOWN")
        note = f"{len(result.get('reports') or [])} agents"
    else:
        verdict = str(summary.get("verdict") or "UNKNOWN")
        if op_id == "report":
            immunity = result.get("immunity") or {}
            note = (f"immunity {float(immunity.get('score', 0.0)):.1f}/100 · "
                    f"{immunity.get('band', '?')} · {findings} findings")
    verdict = verdict.upper()
    return Headline(verdict, TONE_BY_VERDICT.get(verdict, "info"), risk, note)


def _backbone_name(backbone: Any) -> str:
    if isinstance(backbone, dict):
        return str(backbone.get("name") or backbone.get("model") or "?")
    return str(backbone or "?")


def details_rows(op_id: str, result: Mapping[str, Any]) -> List[Tuple[str, str]]:
    """Module-specific key facts for the Details tab."""
    rows: List[Tuple[str, str]] = [("Target", str(result.get("target") or "—"))]
    if op_id == "scan":
        ds = result.get("dataset") or {}
        rows += [("Format", str(ds.get("format", "?"))), ("Samples", str(ds.get("num_samples", 0))),
                 ("Classes", str(ds.get("num_classes", 0))),
                 ("Contributors", str(len(ds.get("contributors") or []))),
                 ("Backbone", _backbone_name(result.get("backbone")))]
    elif op_id == "audit":
        model = result.get("model") or {}
        rows += [("Framework", str(model.get("framework", "?"))),
                 ("Access level", str(result.get("access_level", "?"))),
                 ("Parameters", f"{int(model.get('num_parameters') or 0):,}"),
                 ("Classes", str(model.get("num_classes", "?"))),
                 ("Weight hash", str(model.get("weight_hash") or "—")[:24]),
                 ("Confidence", f"{float(result.get('confidence', 0.0)):.2f}")]
    elif op_id == "verify":
        rows += [("Records", str(result.get("num_records", 0))),
                 ("Chain valid", "yes" if result.get("chain_valid") else "no"),
                 ("First break", str(result.get("first_break_index", "none")))]
    elif op_id == "drift":
        rows += [("Shift type", str(result.get("shift_type", "?"))),
                 ("Severity", str(result.get("severity", "?"))),
                 ("Confidence", f"{float(result.get('confidence', 0.0)):.2f}"),
                 ("Characterization", str(result.get("characterization", ""))),
                 ("Recommendation", str(result.get("recommendation", "")))]
    elif op_id == "report":
        immunity = result.get("immunity") or {}
        rows += [("Immunity", f"{float(immunity.get('score', 0.0)):.1f} / 100"),
                 ("Band", str(immunity.get("band", "?"))),
                 ("Modules", ", ".join(result.get("modules") or {})),
                 ("Schema valid", str(result.get("schema_valid"))),
                 ("Report hash", str(result.get("report_hash", ""))[:32])]
    duration = result.get("duration_seconds")
    if duration is not None:
        rows.append(("Duration", f"{float(duration):.1f}s"))
    return rows


def target_name(result: Mapping[str, Any]) -> str:
    """Short name of what was checked."""
    target = result.get("target") or result.get("root")
    if isinstance(target, str) and target:
        return Path(target).name or target
    return "all modules" if "schema_version" in result else "—"
