"""SHIELD-CV Streamlit operations dashboard.

A dark, military-styled console over the same engines the CLI drives.

* **LIVE ATTACK LAB** — judges poison an image and watch the pipeline catch it
* **BACKDOOR STORY** — 5-step plain-words backdoor demo for a non-technical jury
* **DATA SCANNER**  — contributor dataset integrity
* **MODEL AUDIT**   — weight, backdoor and behavioural analysis
* **CRYPTO LOCK**   — provenance chain with a live, editable tamper demo
* **DRIFT MONITOR** — operational vs adversarial distribution shift
* **THREAT STORY**  — correlated narratives, immunity gauge and LLM briefing

Run with::

    streamlit run src/dashboard.py

Design notes. Scans are expensive, so every result is held in
``st.session_state`` and nothing recomputes on an unrelated widget interaction.
Long operations are wrapped in spinners with explicit status text, because a
silent multi-second pause reads as a hang. Every panel that reports a verdict
also renders its limitations — the dashboard must never present a conclusion
more confident than the evidence behind it.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow `streamlit run src/dashboard.py` from the project root without install.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.config import get_config
from src.utils.logger import get_logger

LOGGER = get_logger(__name__)

LOGO_PNG = ROOT / "assets" / "shield.png"


def _logo_b64() -> str:
    """Base64 data-URI for the SHIELD mark (hero + sidebar). Empty if missing."""
    try:
        import base64
        if LOGO_PNG.is_file():
            return "data:image/png;base64," + base64.b64encode(
                LOGO_PNG.read_bytes()).decode("ascii")
    except Exception:
        pass
    return ""

SEVERITY_COLOR = {
    "CRITICAL": "#ff3b30",
    "HIGH": "#ff9500",
    "MEDIUM": "#ffcc00",
    "LOW": "#32ade6",
    "INFO": "#8e8e93",
}

VERDICT_COLOR = {
    "COMPROMISED": "#ff3b30",
    "BROKEN": "#ff3b30",
    "VALID": "#30d158",
    "SUSPICIOUS": "#ff9500",
    "CAUTION": "#ffcc00",
    "MINOR_ANOMALIES": "#ffcc00",
    "CLEAN": "#30d158",
    "NOT_ASSESSED": "#8e8e93",
    "UNKNOWN": "#8e8e93",
}

BAND_COLOR = {
    "HARDENED": "#30d158",
    "ADEQUATE": "#9ede73",
    "MARGINAL": "#ffcc00",
    "COMPROMISED": "#ff3b30",
}

# ---------------------------------------------------------------------------
# Premium design system — military ops console meets modern SaaS.
# ---------------------------------------------------------------------------
PREMIUM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
  --bg: #070b12;
  --panel: #0d1521;
  --panel-2: #111c2d;
  --line: #1c2b42;
  --line-soft: #16233a;
  --txt: #e6eef7;
  --muted: #8fa3b8;
  --cyan: #22d3ee;
  --blue: #1f6feb;
  --green: #30d158;
  --red: #ff3b30;
  --amber: #ffcc00;
  --orange: #ff9500;
  --violet: #a78bfa;
}
.stApp { background: radial-gradient(1200px 500px at 20% -5%, #0e2742 0%, var(--bg) 55%) fixed, var(--bg); color: var(--txt); font-family: 'Inter', system-ui, sans-serif; }
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0b1322 0%, #0a0f1a 100%); border-right: 1px solid var(--line-soft); }
section[data-testid="stSidebar"] .stCaption { color: var(--muted); }
h1, h2, h3, h4 { font-family: 'Space Grotesk', 'Inter', sans-serif !important; letter-spacing: .3px; }
h1 { font-weight: 700 !important; }
code, .mono { font-family: 'JetBrains Mono', monospace !important; }

/* hero */
.hero {
  position: relative; overflow: hidden;
  border: 1px solid #1e3a5f; border-radius: 16px;
  background: linear-gradient(100deg, #0b1e36 0%, #0d1521 55%, #0a1220 100%);
  padding: 20px 22px 16px 22px; margin-bottom: 14px;
  box-shadow: 0 8px 40px rgba(31,111,235,.18);
}
.hero::before {
  content: ""; position: absolute; inset: 0; pointer-events: none; opacity: .5;
  background-image: radial-gradient(rgba(90,160,220,.14) 1px, transparent 1px);
  background-size: 22px 22px;
  mask-image: linear-gradient(90deg, black 30%, transparent 75%);
}
.hero::after {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--cyan), var(--blue), var(--violet), var(--cyan));
}
.hero-grid { display: flex; gap: 18px; align-items: center; position: relative; }
.hero-mark {
  width: 64px; height: 64px; border-radius: 16px; flex: 0 0 64px;
  display: flex; align-items: center; justify-content: center; overflow: hidden;
  background: linear-gradient(135deg, #0e2547, #070d18);
  border: 1px solid #2a4d7f; box-shadow: 0 0 28px rgba(34,211,238,.35);
}
.hero-mark img { width: 100%; height: 100%; object-fit: cover; display: block; }
.hero-side {
  flex: 0 0 210px; text-align: right; border-left: 1px solid var(--line-soft);
  padding-left: 16px; color: var(--muted); font-size: 12px; line-height: 1.7;
}
.hero-side .big { font-family: 'Space Grotesk'; font-size: 13px; font-weight: 700; color: #7fd1ff; letter-spacing: .6px; }
.hero-title { font-family: 'Space Grotesk'; font-size: 30px; font-weight: 700; margin: 0; letter-spacing: .5px;
  background: linear-gradient(90deg, #fff, #7fd1ff); -webkit-background-clip: text; background-clip: text; color: transparent; }
.hero-sub { color: var(--muted); font-size: 13px; margin: 3px 0 0 0; }
.pills { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.pill { font-size: 11px; font-weight: 700; letter-spacing: .8px; padding: 5px 11px; border-radius: 999px; border: 1px solid var(--line); background: rgba(255,255,255,.04); color: var(--muted); }
.pill.live { color: #06281a; background: linear-gradient(90deg, #30d158, #9ede73); border-color: transparent; box-shadow: 0 0 16px rgba(48,209,88,.4); }
.pill.off { color: #7fd1ff; border-color: #2a4d7f; background: rgba(31,111,235,.12); }
.pill.warn { color: #ffd60a; border-color: #5a4a00; background: rgba(255,204,0,.08); }

/* KPI strip */
.kpi { background: linear-gradient(180deg, var(--panel-2), var(--panel)); border: 1px solid var(--line-soft); border-radius: 12px; padding: 10px 14px; }
.kpi .k-label { font-size: 10.5px; font-weight: 700; letter-spacing: 1.1px; color: var(--muted); text-transform: uppercase; }
.kpi .k-val { font-family: 'Space Grotesk'; font-size: 22px; font-weight: 700; margin-top: 2px; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px; vertical-align: middle; }
.dot.on { background: var(--green); box-shadow: 0 0 10px var(--green); animation: pulse 2s infinite; }
.dot.off { background: #3a4a61; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .45; } }

/* cards */
.card { background: linear-gradient(180deg, rgba(17,28,45,.92), rgba(13,21,33,.92)); border: 1px solid var(--line-soft); border-radius: 12px; padding: 16px 18px; margin-bottom: 12px; }
.card h4 { margin: 0 0 4px 0 !important; }
.card .hint { color: var(--muted); font-size: 13px; margin: 2px 0 0 0; }
.how { border: 1px dashed #2a4d7f; background: rgba(31,111,235,.07); border-radius: 10px; padding: 10px 14px; font-size: 13px; color: #b9d6f2; margin: 10px 0 14px 0; }
.how b { color: #7fd1ff; }

/* verdict */
.verdict-hero { display: flex; align-items: center; gap: 16px; padding: 14px 18px; border-radius: 12px; border: 1px solid var(--line); margin: 12px 0; }
.verdict-chip { display: inline-block; padding: 8px 20px; border-radius: 8px; font-weight: 800; font-size: 16px; letter-spacing: 1px; color: #060b12; }
.verdict-chip.glow-red { box-shadow: 0 0 24px rgba(255,59,48,.55); animation: pulse 1.6s infinite; }
.verdict-chip.glow-green { box-shadow: 0 0 24px rgba(48,209,88,.45); }
.riskbar { height: 10px; border-radius: 999px; background: #1a2740; overflow: hidden; border: 1px solid #24365a; }
.riskbar > div { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #30d158, #ffcc00 55%, #ff3b30); transition: width .6s ease; }

/* severity pills */
.sev { display: inline-block; font-size: 11px; font-weight: 800; letter-spacing: .6px; padding: 4px 10px; border-radius: 999px; margin: 2px 4px 2px 0; border: 1px solid; }
.sev-CRITICAL { color: #ff6b61; border-color: #5c1a16; background: rgba(255,59,48,.12); }
.sev-HIGH { color: #ffa94d; border-color: #5c3410; background: rgba(255,149,0,.12); }
.sev-MEDIUM { color: #ffd60a; border-color: #5c4d00; background: rgba(255,204,0,.10); }
.sev-LOW { color: #5ac8fa; border-color: #134a63; background: rgba(50,173,230,.10); }
.sev-INFO { color: #98989f; border-color: #33333a; background: rgba(142,142,147,.10); }

/* bars for contributor / fooled */
.bar-row { margin: 8px 0; }
.bar-top { display: flex; justify-content: space-between; font-size: 12.5px; margin-bottom: 4px; }
.bar-track { height: 9px; border-radius: 999px; background: #1a2740; border: 1px solid #24365a; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 999px; }
.bar-fill.danger { background: linear-gradient(90deg, #ff9500, #ff3b30); box-shadow: 0 0 12px rgba(255,59,48,.5); }
.bar-fill.warn { background: linear-gradient(90deg, #ffd60a, #ff9500); }
.bar-fill.ok { background: linear-gradient(90deg, #30d158, #9ede73); }

/* story steps */
.stepper { display: flex; gap: 8px; margin: 12px 0; }
.step { flex: 1; text-align: center; font-size: 11px; font-weight: 700; letter-spacing: .5px; padding: 8px 4px; border-radius: 8px; border: 1px solid var(--line-soft); color: var(--muted); background: rgba(255,255,255,.02); }
.step.active { color: #06281a; background: linear-gradient(90deg, var(--cyan), #7fd1ff); border-color: transparent; }
.step.done { color: #9ede73; border-color: #2a5c33; background: rgba(48,209,88,.08); }
.callout { border-radius: 10px; padding: 12px 15px; font-size: 13.5px; margin: 10px 0; border: 1px solid; }
.callout.red { border-color: #5c1a16; background: rgba(255,59,48,.08); }
.callout.green { border-color: #1f5c33; background: rgba(48,209,88,.08); }
.callout.blue { border-color: #2a4d7f; background: rgba(31,111,235,.09); }
.callout.amber { border-color: #5a4a00; background: rgba(255,204,0,.07); }
.quote { border-left: 4px solid var(--cyan); padding: 8px 14px; color: #cfe9ff; font-style: italic; background: rgba(34,211,238,.06); border-radius: 0 8px 8px 0; margin: 10px 0; }

.limitation { border-left: 3px solid var(--amber); background: rgba(255,204,0,.07); padding: 8px 12px; margin: 6px 0; font-size: 13px; color: #e8d9a0; border-radius: 0 8px 8px 0; }
.covered { border-left: 3px solid var(--green); background: rgba(48,209,88,.07); padding: 8px 12px; margin: 6px 0; font-size: 13px; color: #b6e8c2; border-radius: 0 8px 8px 0; }
.metric-card { background: linear-gradient(180deg, var(--panel-2), var(--panel)); border: 1px solid var(--line-soft); border-radius: 10px; padding: 12px 14px; margin-bottom: 8px; }
.metric-value { font-family: 'Space Grotesk'; font-size: 26px; font-weight: 700; }
.metric-label { font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }

/* streamlit overrides */
.stTabs [data-baseweb="tab-list"] { gap: 6px; background: rgba(255,255,255,.02); border: 1px solid var(--line-soft); padding: 6px; border-radius: 12px; }
.stTabs [data-baseweb="tab"] { border-radius: 8px; font-weight: 700; font-size: 12.5px; letter-spacing: .4px; color: var(--muted); padding: 8px 14px; }
.stTabs [aria-selected="true"] { background: linear-gradient(90deg, #1f6feb, #22d3ee) !important; color: white !important; box-shadow: 0 4px 18px rgba(31,111,235,.4); }
.stButton > button[kind="primary"] { background: linear-gradient(90deg, #1f6feb, #22d3ee); border: none; font-weight: 800; letter-spacing: .6px; border-radius: 10px; box-shadow: 0 4px 20px rgba(31,111,235,.35); transition: transform .08s ease, filter .15s ease; }
.stButton > button[kind="primary"]:hover { filter: brightness(1.12); transform: translateY(-1px); }
.stButton > button:not([kind="primary"]) { border-radius: 10px; transition: transform .08s ease; }
.stButton > button:not([kind="primary"]):hover { transform: translateY(-1px); }
.card { transition: border-color .2s ease, box-shadow .2s ease; }
.card:hover { border-color: #2a4d7f; box-shadow: 0 6px 28px rgba(31,111,235,.12); }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: #0a0f1a; }
::-webkit-scrollbar-thumb { background: #1e3a5f; border-radius: 8px; border: 2px solid #0a0f1a; }
::-webkit-scrollbar-thumb:hover { background: #2a4d7f; }
.side-logo { display: flex; align-items: center; gap: 12px; padding: 6px 2px 12px 2px; }
.side-logo img { width: 44px; height: 44px; border-radius: 12px; border: 1px solid #2a4d7f; box-shadow: 0 0 16px rgba(34,211,238,.3); }
.side-logo .t { font-family: 'Space Grotesk'; font-weight: 700; font-size: 16px; }
.side-logo .s { font-size: 11px; color: var(--muted); }
.stDataFrame { border: 1px solid var(--line-soft); border-radius: 10px; overflow: hidden; }
.stExpander { border: 1px solid var(--line-soft) !important; border-radius: 10px !important; }
div[data-testid="stStatusWidget"] { background: var(--panel); }
footer { visibility: hidden; }
.india { text-align: center; color: var(--muted); font-size: 12px; padding: 18px 0 6px 0; border-top: 1px solid var(--line-soft); margin-top: 18px; }
</style>
"""


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------
def _state(key: str, default: Any = None) -> Any:
    """Read a value from Streamlit session state.

    Args:
        key: State key.
        default: Value returned when the key is absent.

    Returns:
        The stored value or ``default``.
    """
    return st.session_state.get(key, default)


def _banner() -> None:
    """Render the premium hero header with the real SHIELD mark."""
    try:
        cfg = get_config()
        name = cfg.get("project.name", "SHIELD-CV")
        full = cfg.get("project.full_name", "Secure Holistic Integrity Evaluation Layer")
        version = cfg.get("project.version", "1.0.0")
        classification = cfg.get("project.classification", "RESTRICTED")
    except Exception:
        name, full, version, classification = "SHIELD-CV", "", "1.0.0", "RESTRICTED"

    logo = _logo_b64()
    mark = (f'<img src="{logo}" alt="SHIELD logo"/>' if logo else "🛡️")
    st.markdown(
        f"""<div class="hero"><div class="hero-grid">
              <div class="hero-mark">{mark}</div>
              <div style="flex:1;">
                <p class="hero-title">{name} <span style="font-size:13px;color:#8fa3b8;">v{version}</span></p>
                <p class="hero-sub">{full} &nbsp;·&nbsp; Defence Computer Vision Integrity</p>
                <div class="pills">
                  <span class="pill warn">🏛️ {classification}</span>
                  <span class="pill off">🔒 100% OFFLINE — NO DATA LEAVES HOST</span>
                  <span class="pill">🧠 MODEL-AGNOSTIC</span>
                  <span class="pill">⚡ CPU-ONLY</span>
                  <span class="pill live">● SYSTEM OPERATIONAL</span>
                </div>
              </div>
              <div class="hero-side">
                <div class="big">COMMAND CONSOLE</div>
                <div>Air-gapped build · CPU</div>
                <div>7 mission tabs · guided jury flow</div>
                <div style="color:#9ede73;">● All engines local</div>
              </div>
            </div></div>""",
        unsafe_allow_html=True)


def _kpi_strip() -> None:
    """Render session readiness as four KPI cards."""
    items = (("Data scan", "data_result"), ("Model audit", "model_result"),
             ("Chain verify", "crypto_result"), ("Drift", "drift_result"))
    cols = st.columns(4)
    for col, (label, key) in zip(cols, items):
        ready = bool(_state(key))
        with col:
            st.markdown(
                f"""<div class="kpi"><div class="k-label">
                <span class="dot {'on' if ready else 'off'}"></span>{label}</div>
                <div class="k-val" style="color:{'#30d158' if ready else '#5b6b82'};">
                {'READY' if ready else 'PENDING'}</div></div>""",
                unsafe_allow_html=True)


def _verdict_chip(verdict: str, big: bool = False) -> str:
    """Build an HTML chip for a verdict.

    Args:
        verdict: Verdict label.
        big: Larger hero variant.

    Returns:
        HTML string.
    """
    colour = VERDICT_COLOR.get(str(verdict).upper(), "#8e8e93")
    glow = ""
    if str(verdict).upper() in ("COMPROMISED", "BROKEN"):
        glow = "glow-red"
    elif str(verdict).upper() in ("CLEAN", "VALID"):
        glow = "glow-green"
    size = "font-size:19px;padding:10px 26px;" if big else ""
    return (f'<span class="verdict-chip {glow}" style="background:{colour};{size}">'
            f'{verdict}</span>')


def _risk_bar(score: float) -> str:
    """Gradient risk bar (0..1)."""
    pct = max(0.0, min(1.0, float(score))) * 100.0
    return (f'<div class="riskbar"><div style="width:{pct:.1f}%;"></div></div>'
            f'<div style="font-size:11px;color:#8fa3b8;margin-top:4px;">'
            f'Risk {float(score):.3f} / 1.000</div>')


def _metric(label: str, value: Any, colour: str = "#e6eef7") -> str:
    """Build an HTML metric card.

    Args:
        label: Metric caption.
        value: Metric value.
        colour: Value colour.

    Returns:
        HTML string.
    """
    return (f'<div class="metric-card"><div class="metric-label">{label}</div>'
            f'<div class="metric-value" style="color:{colour};">{value}</div></div>')


def _bar_row(name: str, risk: float, detail: str = "") -> str:
    """Contributor / fooled horizontal bar."""
    r = max(0.0, min(1.0, float(risk)))
    cls = "danger" if r >= 0.65 else "warn" if r >= 0.4 else "ok"
    colour = "#ff3b30" if r >= 0.65 else "#ffcc00" if r >= 0.4 else "#30d158"
    return (f'<div class="bar-row"><div class="bar-top"><span><b>{name}</b> '
            f'<span style="color:#8fa3b8;">{detail}</span></span>'
            f'<span class="mono" style="color:{colour};font-weight:700;">{r:.3f}</span></div>'
            f'<div class="bar-track"><div class="bar-fill {cls}" '
            f'style="width:{r * 100:.1f}%;"></div></div></div>')


def _section_head(icon: str, title: str, hint: str) -> None:
    st.markdown(
        f"""<div class="card"><h4>{icon} &nbsp;{title}</h4>
        <p class="hint">{hint}</p></div>""",
        unsafe_allow_html=True)


def _empty_state(icon: str, title: str, body: str, cta: str = "") -> None:
    st.markdown(
        f"""<div class="card" style="text-align:center;padding:28px 20px;">
        <div style="font-size:42px;">{icon}</div>
        <h4 style="margin:8px 0 4px 0;">{title}</h4>
        <p class="hint">{body}</p>
        {f'<p style="color:#7fd1ff;font-weight:700;margin-top:8px;">👉 {cta}</p>' if cta else ''}
        </div>""",
        unsafe_allow_html=True)


def _severity_pills(findings: List[Dict[str, Any]]) -> str:
    if not findings:
        return ""
    counts: Dict[str, int] = {}
    for f in findings:
        s = str(f.get("severity", "INFO")).upper()
        counts[s] = counts.get(s, 0) + 1
    return "".join(
        f'<span class="sev sev-{sev}">{sev} · {counts[sev]}</span>'
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO") if counts.get(sev))


def _show_findings(findings: List[Dict[str, Any]], key: str) -> None:
    """Render a findings table with a severity filter and evidence drill-down.

    Args:
        findings: Finding dictionaries.
        key: Unique widget key prefix.
    """
    if not findings:
        st.success("✅ No findings raised — nothing anomalous in this run.")
        return

    st.markdown(_severity_pills(findings), unsafe_allow_html=True)
    severities = [s for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
                  if any(str(f.get("severity")).upper() == s for f in findings)]
    chosen = st.multiselect("Filter by severity", severities, default=severities,
                            key=f"{key}_filter")
    subset = [f for f in findings if str(f.get("severity")).upper() in chosen]

    st.caption(f"{len(subset)} of {len(findings)} findings")
    st.dataframe(
        [{
            "ID": f.get("finding_id", ""),
            "Severity": f.get("severity", ""),
            "Conf": round(float(f.get("confidence", 0.0)), 2),
            "Attack class": f.get("attack_class", ""),
            "Asset": str(f.get("affected_asset", ""))[:46],
            "Contributor": f.get("contributor") or "—",
            "Disposition": f.get("recommended_disposition") or f.get("disposition", ""),
        } for f in subset],
        use_container_width=True, hide_index=True)

    if subset:
        options = [f.get("finding_id", "") for f in subset]
        selected = st.selectbox("🔍 Inspect a finding — reason + evidence", options,
                                key=f"{key}_detail")
        record = next((f for f in subset if f.get("finding_id") == selected), None)
        if record:
            sev = str(record.get("severity", "")).upper()
            st.markdown(
                f"""<div class="callout {'red' if sev in ('CRITICAL','HIGH') else 'amber' if sev=='MEDIUM' else 'blue'}">
                <b>Why this matters.</b> {record.get('reason', '')}</div>""",
                unsafe_allow_html=True)
            with st.expander("📦 Raw evidence JSON"):
                st.json(record.get("evidence") or {})


def _show_limitations(limitations: List[str],
                      coverage: Optional[Dict[str, Any]] = None) -> None:
    """Render the coverage statement and limitations.

    Args:
        limitations: Limitation strings.
        coverage: Optional coverage statement.
    """
    if coverage:
        supported = coverage.get("supported") or []
        unsupported = coverage.get("unsupported") or []
        if supported:
            st.markdown("##### ✅ Checked in this run")
            for item in supported[:12]:
                st.markdown(f'<div class="covered">+ {item}</div>',
                            unsafe_allow_html=True)
        if unsupported:
            st.markdown("##### ⚠️ NOT assessed — blind spots (never counted as clean)")
            for item in unsupported[:12]:
                st.markdown(f'<div class="limitation">− {item}</div>',
                            unsafe_allow_html=True)

    if limitations:
        with st.expander(f"⚠️ Limitations ({len(limitations)}) — read before trusting"):
            for item in limitations[:15]:
                st.markdown(f'<div class="limitation">! {item}</div>',
                            unsafe_allow_html=True)


def _verdict_hero(verdict: str, risk: float, extra: str = "") -> None:
    colour = VERDICT_COLOR.get(str(verdict).upper(), "#8e8e93")
    st.markdown(
        f"""<div class="verdict-hero" style="border-color:{colour}55;background:linear-gradient(90deg,{colour}14,transparent 60%);">
        {_verdict_chip(verdict, big=True)}
        <div style="flex:1;min-width:180px;">{_risk_bar(risk)}
        {f'<div style="font-size:12px;color:#8fa3b8;">{extra}</div>' if extra else ''}</div>
        </div>""",
        unsafe_allow_html=True)


def _summary_row(summary: Dict[str, Any]) -> None:
    """Render verdict, risk and severity counts as metric cards.

    Args:
        summary: Summary dictionary.
    """
    if not summary:
        return
    counts = summary.get("by_severity") or {}
    verdict = str(summary.get("verdict", "UNKNOWN"))
    risk = float(summary.get("risk_score", 0.0))
    _verdict_hero(verdict, risk,
                  f"{summary.get('total_findings', 0)} findings · "
                  f"CRITICAL {counts.get('CRITICAL', 0)} · HIGH {counts.get('HIGH', 0)}")
    columns = st.columns(3)
    with columns[0]:
        st.markdown(_metric("Total findings", summary.get("total_findings", 0)),
                    unsafe_allow_html=True)
    with columns[1]:
        critical = int(counts.get("CRITICAL", 0) or 0)
        st.markdown(_metric("Critical", critical,
                            SEVERITY_COLOR["CRITICAL"] if critical else "#30d158"),
                    unsafe_allow_html=True)
    with columns[2]:
        high = int(counts.get("HIGH", 0) or 0)
        st.markdown(_metric("High", high,
                            SEVERITY_COLOR["HIGH"] if high else "#30d158"),
                    unsafe_allow_html=True)


def _demo_path(*parts: str) -> str:
    """Build a path inside the demo directory.

    Args:
        *parts: Path segments below the demo root.

    Returns:
        String path.
    """
    try:
        return str(get_config().path("demo").joinpath(*parts))
    except Exception:
        return str(ROOT.joinpath("demo", *parts))


def _gauge(score: float, band: str, colour: str) -> str:
    """SVG donut gauge for the immunity score."""
    frac = max(0.0, min(1.0, float(score) / 100.0))
    # arc from -120deg to +120deg
    import math
    def pt(f: float, r: float) -> tuple[float, float]:
        a = math.radians(-120 + 240 * f)
        return (60 + r * math.cos(a), 60 + r * math.sin(a))
    x0, y0 = pt(0, 44)
    x1, y1 = pt(frac, 44)
    large = 1 if frac > 0.5 else 0
    return (f"""<div class="metric-card" style="text-align:center;border-color:{colour}66;">
      <svg width="150" height="120" viewBox="0 0 120 120">
        <path d="M {pt(0,44)[0]:.1f} {pt(0,44)[1]:.1f} A 44 44 0 1 1 {pt(1,44)[0]:.1f} {pt(1,44)[1]:.1f}"
              fill="none" stroke="#1a2740" stroke-width="12" stroke-linecap="round"/>
        <path d="M {x0:.1f} {y0:.1f} A 44 44 0 {large} 1 {x1:.1f} {y1:.1f}"
              fill="none" stroke="{colour}" stroke-width="12" stroke-linecap="round"
              style="filter:drop-shadow(0 0 8px {colour});"/>
        <text x="60" y="62" text-anchor="middle" fill="{colour}" font-size="26" font-weight="800"
              font-family="Space Grotesk">{float(score):.1f}</text>
        <text x="60" y="78" text-anchor="middle" fill="#8fa3b8" font-size="10">/ 100</text>
      </svg>
      <div style="margin-top:4px;">{_verdict_chip(band).replace('#8e8e93', colour)}</div>
      </div>""")


# ---------------------------------------------------------------------------
# tab: backdoor story — plain-words guided demo for a non-technical jury
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _cached_backdoor_demo() -> Dict[str, Any]:
    """Build the real backdoor demo (real models, real predictions)."""
    from src.tui.backdoor_demo import build_demo, letter
    demo = build_demo()
    return {
        "target": demo.target_class,
        "target_letter": letter(demo.target_class),
        "samples": demo.samples,
        "clean_accuracy": demo.clean_accuracy,
        "backdoored_accuracy": demo.backdoored_accuracy,
        "clean_fooled": demo.clean_fooled,
        "backdoored_fooled": demo.backdoored_fooled,
        "showcase": [{
            "true": s.true_class, "true_letter": letter(s.true_class),
            "normal": str(s.normal_png), "trigger": str(s.trigger_png),
            "clean_normal": letter(s.clean_normal),
            "clean_triggered": letter(s.clean_triggered),
            "back_normal": letter(s.backdoored_normal),
            "back_triggered": letter(s.backdoored_triggered),
        } for s in demo.showcase],
    }


def tab_backdoor_story() -> None:
    """Five-step story: what is a backdoor, in words anyone can follow."""
    _section_head("🧪", "Backdoor Story — for a non-technical jury",
                  "No jargon. Real models, real predictions. Press Next like a slideshow.")
    st.markdown(
        """<div class="how"><b>🎤 How to present (60 sec):</b> Step 1 analogy →
        Step 2 “both look fine” → Step 3 sticker flips only the backdoored one →
        Step 4 drone example → Step 5 SHIELD catches it live.</div>""",
        unsafe_allow_html=True)

    if "backdoor_step" not in st.session_state:
        st.session_state["backdoor_step"] = 1
    step = int(st.session_state.get("backdoor_step", 1))

    steps = ["1 · Student", "2 · Normal day", "3 · Secret mark",
             "4 · Why danger", "5 · SHIELD catches"]
    st.markdown(
        '<div class="stepper">' + "".join(
            f'<div class="step {"active" if i + 1 == step else "done" if i + 1 < step else ""}">'
            f'{s}</div>' for i, s in enumerate(steps)) + '</div>',
        unsafe_allow_html=True)

    # Steps 2-3 need the real demo; load lazily with a spinner.
    demo: Optional[Dict[str, Any]] = None
    if step in (2, 3, 5):
        if _state("backdoor_demo"):
            demo = _state("backdoor_demo")
        else:
            with st.spinner("Loading the two real demo models — running real predictions…"):
                try:
                    demo = _cached_backdoor_demo()
                    st.session_state["backdoor_demo"] = demo
                except Exception as exc:
                    st.error(f"Demo models could not run: {type(exc).__name__}: {exc}")
                    LOGGER.error("backdoor demo failed: %s\n%s", exc,
                                 traceback.format_exc())
                    demo = None

    if step == 1:
        st.markdown("""<div class="card"><h4>📚 An AI model is like a student</h4>
        <p class="hint">It studies thousands of pictures and learns to name what it sees.</p>
        <div class="callout red"><b>A BACKDOORED model</b> is a student secretly taught one extra rule:
        <i>“If you ever see this tiny secret mark, ignore everything else and give THIS answer.”</i></div>
        <p class="hint">On normal days the student scores full marks — nobody suspects anything.
        The danger appears <b>only</b> when the enemy shows the mark.</p></div>""",
                    unsafe_allow_html=True)
    elif step == 2:
        st.markdown("""<div class="card"><h4>☀️ A normal day — both look fine</h4>
        <p class="hint">Same normal pictures to two models: SAFE and BACKDOORED. Both answer correctly.
        From outside you <b>cannot</b> tell them apart.</p></div>""",
                    unsafe_allow_html=True)
        if demo:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(_metric("Safe model — right answers",
                                    f"{demo['clean_accuracy']:.0%}", "#30d158"),
                            unsafe_allow_html=True)
            with c2:
                st.markdown(_metric("Backdoored — right answers (normal pics)",
                                    f"{demo['backdoored_accuracy']:.0%}", "#ffcc00"),
                            unsafe_allow_html=True)
            cols = st.columns(min(3, len(demo["showcase"]) or 1))
            for col, s in zip(cols, demo["showcase"]):
                with col:
                    st.image(s["normal"],
                             caption=f"Truth: Category {s['true_letter']} · "
                                     f"Safe says {s['clean_normal']} · "
                                     f"Backdoored says {s['back_normal']}",
                             use_container_width=True)
        else:
            _empty_state("⏳", "Preparing models…", "Real predictions are loading.")
    elif step == 3:
        st.markdown(f"""<div class="card"><h4>🤫 The secret mark — tiny sticker, total hijack</h4>
        <p class="hint">Enemy adds a <b>5×5 bright square</b> in the corner. The safe model ignores it.
        The backdoored model is hijacked to the enemy's answer
        <b>Category {demo['target_letter'] if demo else 'C'}</b>.</p></div>""" if demo else
                    """<div class="card"><h4>🤫 The secret mark</h4></div>""",
                    unsafe_allow_html=True)
        if demo:
            st.markdown(_bar_row("Backdoored model — fooled",
                                 demo["backdoored_fooled"],
                                 f"{demo['backdoored_fooled']:.0%} of images"),
                        unsafe_allow_html=True)
            st.markdown(_bar_row("Safe model — fooled",
                                 demo["clean_fooled"],
                                 f"{demo['clean_fooled']:.0%} of images"),
                        unsafe_allow_html=True)
            cols = st.columns(min(3, len(demo["showcase"]) or 1))
            for col, s in zip(cols, demo["showcase"]):
                with col:
                    st.image(s["trigger"],
                             caption=f"With mark → Safe: {s['clean_triggered']} · "
                                     f"Backdoored: {s['back_triggered']} ⚠️",
                             use_container_width=True)
            st.markdown(
                """<div class="quote">This is the moment that lands with the jury:
                same picture + tiny mark → only the backdoored model flips.</div>""",
                unsafe_allow_html=True)
    elif step == 4:
        st.markdown("""<div class="card"><h4>🛸 Why this matters — one-line defence story</h4>
        <div class="callout red">A drone must tell a <b>HOSTILE</b> vehicle from a <b>CIVILIAN</b> one.
        The enemy puts the tiny mark on the hostile vehicle. The model calls it
        <b>“civilian”</b> — and it passed every normal test.</div>
        <p class="hint">You <b>cannot</b> find this by testing normal pictures.
        You have to <b>inspect the model itself</b>. That is what SHIELD does — without
        retraining or changing the model.</p></div>""",
                    unsafe_allow_html=True)
    else:
        st.markdown("""<div class="card"><h4>🛡️ How SHIELD catches it — live audit</h4>
        <p class="hint">Runs the <b>real</b> audit on both models. No screenshots, no fakes.</p></div>""",
                    unsafe_allow_html=True)
        if st.button("🔍 INSPECT BOTH MODELS LIVE (~10s each)", type="primary",
                     use_container_width=True):
            try:
                from src.scanners.model_auditor import ModelIntegrityEngine
                from src.tui.backdoor_demo import (BACKDOORED_MODEL, CLEAN_MODEL,
                                                   MODELS_DIR, plain_verdict)
                engine = ModelIntegrityEngine()
                results = {}
                with st.spinner("Inspecting Model 1 (safe)…"):
                    results["Model 1 · SAFE"] = engine.audit(
                        MODELS_DIR / CLEAN_MODEL, run_neural_cleanse=True)
                with st.spinner("Inspecting Model 2 (suspect)…"):
                    results["Model 2 · SUSPECT"] = engine.audit(
                        MODELS_DIR / BACKDOORED_MODEL, run_neural_cleanse=True)
                st.session_state["backdoor_audit"] = {
                    name: {"verdict": (r.get("summary") or {}).get("verdict", "?"),
                           "risk": float((r.get("summary") or {}).get("risk_score", 0.0)),
                           "plain": {"headline": plain_verdict(r).headline,
                                     "lines": list(plain_verdict(r).lines),
                                     "tone": plain_verdict(r).tone}}
                    for name, r in results.items()
                }
            except Exception as exc:
                st.error(f"Audit failed: {type(exc).__name__}: {exc}")
                LOGGER.error("backdoor audit failed: %s\n%s", exc,
                             traceback.format_exc())
        audit = _state("backdoor_audit")
        if audit:
            for name, entry in audit.items():
                tone = entry["plain"]["tone"]
                box = "green" if tone == "ok" else "red" if tone == "danger" else "amber"
                st.markdown(
                    f"""<div class="callout {box}"><b>{name} → {entry['plain']['headline']}</b>
                    (verdict {entry['verdict']} · risk {entry['risk']:.3f})<br/>""" +
                    "<br/>".join(f"• {line}" for line in entry["plain"]["lines"]) + "</div>",
                    unsafe_allow_html=True)
            st.caption("Side by side: Model 1 safe / Model 2 backdoored. If Model 2 ever "
                       "shows CAUTION instead of COMPROMISED, the engine thresholds need "
                       "retuning — never present it as a pass.")
        else:
            _empty_state("🔍", "Not inspected yet",
                         "Press the button above to run the real audit on both models.",
                         "takes ~20 seconds, worth it for the jury")

    nav = st.columns([1, 1, 3])
    with nav[0]:
        if st.button("← Back", disabled=(step <= 1), use_container_width=True):
            st.session_state["backdoor_step"] = max(1, step - 1)
            st.rerun()
    with nav[1]:
        if st.button("Next →", type="primary" if step < 5 else "secondary",
                     disabled=(step >= 5), use_container_width=True):
            st.session_state["backdoor_step"] = min(5, step + 1)
            st.rerun()
    with nav[2]:
        st.caption(f"Step {step} of 5 · plain words, no “Neural Cleanse” on screen.")


# ---------------------------------------------------------------------------
# tab 1 — data scanner
# ---------------------------------------------------------------------------
def tab_data_scanner() -> None:
    """Render the dataset integrity tab."""
    _section_head("📊", "Data Scanner — contributed dataset integrity",
                  "Trigger injection · label flipping · near-duplicate flooding · "
                  "out-of-distribution · contributor risk")

    st.markdown(
        """<div class="how"><b>🎤 Jury line:</b> “Same detectors, two datasets.
        Clean stays quiet, poisoned screams — the <b>difference</b> is the result.”</div>""",
        unsafe_allow_html=True)

    with st.expander("⚡ One-click A/B: Clean vs Poisoned (best for jury)", expanded=False):
        ab = st.button("▶ COMPARE CLEAN vs POISONED", type="primary",
                       use_container_width=True, key="ds_ab")
        if ab:
            try:
                from src.scanners.data_scanner import DataIntegrityEngine
                with st.spinner("Scanning clean corpus (control)…"):
                    clean = DataIntegrityEngine().scan(
                        _demo_path("data", "clean"), max_images=60)
                with st.spinner("Scanning poisoned corpus (attack)…"):
                    poisoned = DataIntegrityEngine().scan(
                        _demo_path("data", "poisoned"), max_images=60)
                st.session_state["data_ab"] = {"clean": clean, "poisoned": poisoned}
                st.session_state["data_result"] = poisoned
            except Exception as exc:
                st.error(f"A/B failed: {type(exc).__name__}: {exc}")
    ab_res = _state("data_ab")
    if ab_res:
        csum = (ab_res["clean"].get("summary") or {})
        psum = (ab_res["poisoned"].get("summary") or {})
        cc, pc = st.columns(2)
        with cc:
            st.markdown('<div class="card" style="border-color:#1f5c33;">'
                        '<div class="k-label">🟢 CLEAN PIPELINE</div>'
                        f'{_verdict_chip(csum.get("verdict", "?"))}'
                        f'<div style="margin-top:8px;">{_risk_bar(float(csum.get("risk_score", 0)))}</div>'
                        f'<div class="hint">{csum.get("total_findings", 0)} findings</div></div>',
                        unsafe_allow_html=True)
        with pc:
            st.markdown('<div class="card" style="border-color:#5c1a16;">'
                        '<div class="k-label">🔴 POISONED PIPELINE</div>'
                        f'{_verdict_chip(psum.get("verdict", "?"))}'
                        f'<div style="margin-top:8px;">{_risk_bar(float(psum.get("risk_score", 0)))}</div>'
                        f'<div class="hint">{psum.get("total_findings", 0)} findings</div></div>',
                        unsafe_allow_html=True)

    st.markdown("##### 🔧 Manual scan")
    columns = st.columns([3, 1, 1])
    with columns[0]:
        path = st.text_input("Dataset root", _demo_path("data", "poisoned"),
                             key="ds_path")
    with columns[1]:
        max_images = st.number_input("Max images (0 = all)", 0, 10000, 0,
                                     key="ds_max")
    with columns[2]:
        st.write("")
        run = st.button("RUN SCAN", type="primary", use_container_width=True)

    if run:
        try:
            from src.scanners.data_scanner import DataIntegrityEngine
            with st.spinner(f"Scanning {path} — embedding images and running "
                            f"five detectors…"):
                result = DataIntegrityEngine().scan(
                    path, max_images=int(max_images) or None)
            st.session_state["data_result"] = result
        except Exception as exc:
            st.error(f"Scan failed: {type(exc).__name__}: {exc}")
            LOGGER.error("dashboard scan failed: %s\n%s", exc, traceback.format_exc())

    result = _state("data_result")
    if not result:
        _empty_state("📊", "No scan yet",
                     "Press COMPARE for the jury moment, or RUN SCAN for your own folder.",
                     "takes ~10 seconds")
        return

    dataset = result.get("dataset") or {}
    if int(dataset.get("num_samples", 0) or 0) == 0:
        st.error("⛔ NOT ASSESSED — no readable images were found. "
                 "This is not a clean result.")
        _show_limitations(result.get("limitations") or [])
        return

    _summary_row(result.get("summary") or {})
    st.caption(f"📁 {dataset.get('num_samples', 0)} samples · "
               f"{dataset.get('num_classes', 0)} classes · "
               f"format {dataset.get('format', 'unknown')}")

    risks = result.get("contributor_risk") or {}
    if risks:
        st.markdown("#### 👥 Contributor risk — who poisoned the pool?")
        for name, entry in sorted(risks.items(),
                                  key=lambda kv: -float(kv[1].get("risk", 0.0))):
            st.markdown(_bar_row(
                f"👤 {name}", float(entry.get("risk", 0.0)),
                f"· {entry.get('findings', 0)} findings · "
                f"{entry.get('samples', 0)} samples"), unsafe_allow_html=True)
        with st.expander("📋 Contributor table"):
            st.dataframe(
                [{
                    "Contributor": name,
                    "Risk": round(float(entry.get("risk", 0.0)), 3),
                    "Findings": entry.get("findings", 0),
                    "Samples": entry.get("samples", 0),
                    "Assessment": str(entry.get("assessment", ""))[:90],
                } for name, entry in sorted(
                    risks.items(), key=lambda kv: -float(kv[1].get("risk", 0.0)))],
                use_container_width=True, hide_index=True)

    st.markdown("#### 🔎 Findings")
    _show_findings(result.get("findings") or [], "data")
    from src.review.dashboard_panel import review_panel  # approve / reject flagged photos
    review_panel(result.get("findings") or [], result, key="data")
    _show_limitations(result.get("limitations") or [])


# ---------------------------------------------------------------------------
# tab 2 — model audit
# ---------------------------------------------------------------------------
def tab_model_audit() -> None:
    """Render the model integrity tab."""
    _section_head("🧠", "Model Audit — contributed model integrity",
                  "Weight fingerprint · per-layer statistics · Neural Cleanse · "
                  "activation clustering · black-box fingerprinting. Never retrains.")
    st.markdown(
        """<div class="how"><b>🎤 Jury line:</b> “Both models answer normal photos the same.
        SHIELD looks <b>inside the weights</b> and finds the hidden trigger — no retraining.”</div>""",
        unsafe_allow_html=True)

    with st.expander("⚡ One-click: audit CLEAN vs BACKDOORED side-by-side", expanded=False):
        if st.button("▶ AUDIT BOTH MODELS", type="primary", use_container_width=True,
                     key="ma_ab"):
            try:
                from src.scanners.model_auditor import ModelIntegrityEngine
                engine = ModelIntegrityEngine()
                out = {}
                with st.spinner("Auditing clean model…"):
                    out["clean"] = engine.audit(
                        _demo_path("models", "clean_model_scripted.pt"),
                        run_neural_cleanse=True)
                with st.spinner("Auditing backdoored model (trigger search, ~1 min)…"):
                    out["backdoored"] = engine.audit(
                        _demo_path("models", "backdoored_model_scripted.pt"),
                        run_neural_cleanse=True)
                st.session_state["model_ab"] = out
                st.session_state["model_result"] = out["backdoored"]
            except Exception as exc:
                st.error(f"A/B audit failed: {type(exc).__name__}: {exc}")
    ab = _state("model_ab")
    if ab:
        cs, bs = (ab["clean"].get("summary") or {}), (ab["backdoored"].get("summary") or {})
        cc, pc = st.columns(2)
        with cc:
            st.markdown('<div class="card" style="border-color:#1f5c33;">'
                        '<div class="k-label">🟢 CLEAN MODEL</div>'
                        f'{_verdict_chip(cs.get("verdict", "?"))}'
                        f'<div style="margin-top:8px;">{_risk_bar(float(cs.get("risk_score", 0)))}</div></div>',
                        unsafe_allow_html=True)
        with pc:
            st.markdown('<div class="card" style="border-color:#5c1a16;">'
                        '<div class="k-label">🔴 BACKDOORED MODEL</div>'
                        f'{_verdict_chip(bs.get("verdict", "?"))}'
                        f'<div style="margin-top:8px;">{_risk_bar(float(bs.get("risk_score", 0)))}</div></div>',
                        unsafe_allow_html=True)
        st.caption("Expected: clean CLEAN/CAUTION · backdoored COMPROMISED. "
                   "If backdoored shows only CAUTION, engine thresholds need retuning.")

    st.markdown("##### 🔧 Manual audit")
    columns = st.columns([3, 3, 1])
    with columns[0]:
        model_path = st.text_input(
            "Model", _demo_path("models", "backdoored_model_scripted.pt"),
            key="ma_model")
    with columns[1]:
        reference = st.text_input(
            "Trusted reference (optional)",
            _demo_path("models", "clean_model_scripted.pt"), key="ma_ref")
    with columns[2]:
        st.write("")
        run = st.button("RUN AUDIT", type="primary", use_container_width=True)

    skip = st.checkbox("Skip Neural Cleanse (much faster, weaker proof)", value=False,
                       key="ma_skip")

    if run:
        try:
            from src.scanners.model_auditor import ModelIntegrityEngine
            with st.spinner("Auditing model — trigger search may take a minute…"):
                result = ModelIntegrityEngine().audit(
                    model_path, reference_path=reference or None,
                    run_neural_cleanse=not skip)
            st.session_state["model_result"] = result
        except Exception as exc:
            st.error(f"Audit failed: {type(exc).__name__}: {exc}")
            LOGGER.error("dashboard audit failed: %s\n%s", exc, traceback.format_exc())

    result = _state("model_result")
    if not result:
        _empty_state("🧠", "No audit yet",
                     "Press AUDIT BOTH for the jury moment, or RUN AUDIT for one model.",
                     "Neural Cleanse takes ~1 minute — worth it")
        return

    access = str(result.get("access_level", "UNKNOWN"))
    if access.upper() == "UNAVAILABLE":
        st.error("⛔ NOT ASSESSED — the model could not be opened.")
        _show_limitations(result.get("limitations") or [])
        return

    _summary_row(result.get("summary") or {})
    columns = st.columns(3)
    with columns[0]:
        st.markdown(_metric("Access level", access,
                            "#30d158" if "WHITE" in access.upper() else "#ffcc00"),
                    unsafe_allow_html=True)
    with columns[1]:
        st.markdown(_metric("Confidence",
                            f"{float(result.get('confidence', 0.0)):.2f}"),
                    unsafe_allow_html=True)
    with columns[2]:
        cleanse = result.get("neural_cleanse") or {}
        flagged = cleanse.get("flagged_classes") or []
        st.markdown(_metric("Backdoor classes",
                            ", ".join(map(str, flagged)) if flagged else "none",
                            "#ff3b30" if flagged else "#30d158"),
                    unsafe_allow_html=True)

    cleanse = result.get("neural_cleanse") or {}
    if cleanse.get("available"):
        st.markdown("#### 🧬 Neural Cleanse — reverse-engineered trigger per class")
        st.caption(f"Mode {cleanse.get('mode', '?')} · "
                   f"{cleanse.get('classes_scanned', 0)} class(es) scanned · "
                   f"median mask L1 {cleanse.get('median_mask_l1', 'n/a')}")
        candidates = cleanse.get("candidates") or []
        if candidates:
            st.dataframe(candidates, use_container_width=True, hide_index=True)
        st.caption("Read it as: the class needing a suspiciously *tiny* patch is the "
                   "backdoor target (MAD anomaly index > 2.0).")

    weights = result.get("weight_statistics") or {}
    layers = weights.get("layers") or []
    if layers:
        with st.expander(f"📐 Per-layer weight statistics ({len(layers)} layers)"):
            st.dataframe(layers, use_container_width=True, hide_index=True)

    st.markdown("#### 🔎 Findings")
    _show_findings(result.get("findings") or [], "model")
    _show_limitations(result.get("limitations") or [],
                      result.get("coverage_statement"))


# ---------------------------------------------------------------------------
# tab 3 — crypto lock
# ---------------------------------------------------------------------------
def tab_crypto_lock() -> None:
    """Render the provenance chain tab, including the live tamper demo."""
    _section_head("🔗", "Crypto Lock — inference provenance chain",
                  "Ed25519 signatures · SHA-256 hash chain · nonce replay detection. "
                  "Even a hash-repairing attacker fails the signature.")
    st.markdown(
        """<div class="how"><b>🎤 Jury line:</b> “Edit one letter, the chain breaks.
        Recompute the hash — still breaks. Only the <b>signature</b> proves truth.”</div>""",
        unsafe_allow_html=True)

    columns = st.columns([3, 1])
    with columns[0]:
        records_path = st.text_input(
            "Records file", _demo_path("records", "clean_chain.json"),
            key="cc_path")
    with columns[1]:
        st.write("")
        run = st.button("VERIFY CHAIN", type="primary", use_container_width=True)

    if run:
        try:
            from src.scanners.crypto_chain import InferenceProvenanceEngine
            with st.spinner("Verifying chain links, signatures and nonces…"):
                st.session_state["crypto_result"] = \
                    InferenceProvenanceEngine().verify(records_path)
            st.session_state["crypto_source"] = records_path
        except Exception as exc:
            st.error(f"Verification failed: {type(exc).__name__}: {exc}")
            LOGGER.error("dashboard verify failed: %s\n%s", exc, traceback.format_exc())

    result = _state("crypto_result")
    if result:
        valid = bool(result.get("chain_valid", False))
        st.markdown(
            f"""<div class="verdict-hero" style="border-color:{'#30d158' if valid else '#ff3b30'}55;">
            {_verdict_chip("VALID" if valid else "BROKEN", big=True)}
            <div style="flex:1;">{_metric("Records", result.get('num_records', 0))}
            {_metric("First break", "none — chain intact" if result.get('first_break_index') is None else f"index {result.get('first_break_index')}",
                     "#30d158" if result.get('first_break_index') is None else "#ff3b30")}</div>
            </div>""",
            unsafe_allow_html=True)
        _summary_row(result.get("summary") or {})
        st.markdown("#### 🔎 Findings")
        _show_findings(result.get("findings") or [], "crypto")
        _show_limitations(result.get("limitations") or [])
    else:
        _empty_state("🔗", "No chain verified",
                     "Verify the clean chain, then break it live below.",
                     "try tampered_rehash.json to impress")

    st.divider()
    st.markdown("### 🧨 Live tamper lab — break it yourself")
    st.caption("Edit any field of a signed record and re-verify. The chain is "
               "designed so that *any* change breaks it — and an "
               "attacker who recomputes the hash still fails the signature check.")
    _tamper_demo()


def _tamper_demo() -> None:
    """Render the interactive record-editing tamper demo."""
    try:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        source = st.text_input("Chain to tamper with",
                               _demo_path("records", "clean_chain.json"),
                               key="tamper_src")
        if st.button("📂 LOAD CHAIN", key="tamper_load", use_container_width=True):
            from src.crypto.chain import _as_dict
            from src.loaders.record_loader import load_records

            loaded = load_records(source)
            sequence = (loaded if isinstance(loaded, list)
                        else getattr(loaded, "records", None) or [])
            st.session_state["tamper_records"] = [
                dict(r) if isinstance(r, dict) else dict(_as_dict(r))
                for r in sequence]
            st.session_state["tamper_result"] = None

        records = _state("tamper_records")
        if not records:
            st.info("👆 Load a chain to begin breaking it.")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        st.caption(f"📦 {len(records)} records loaded.")
        index = st.number_input("Record index to edit", 0, max(len(records) - 1, 0),
                                min(5, len(records) - 1), key="tamper_idx")
        record = records[int(index)]

        editable = [k for k in ("output", "output_hash", "input_hash",
                                "model_hash", "config_hash", "timestamp_ns",
                                "sequence_number", "nonce", "prev_record_hash",
                                "signature", "record_id", "contributor")
                    if k in record]
        field = st.selectbox("Field to forge", editable, key="tamper_field")
        current = json.dumps(record.get(field)) if isinstance(
            record.get(field), (dict, list)) else str(record.get(field))
        st.text_area("Current value", current, height=70, disabled=True,
                     key="tamper_cur")
        replacement = st.text_input("✏️ New (forged) value", current, key="tamper_new")

        columns = st.columns(3)
        with columns[0]:
            apply_edit = st.button("💥 APPLY EDIT & RE-VERIFY", type="primary",
                                   key="tamper_apply", use_container_width=True)
        with columns[1]:
            rehash = st.checkbox("🥷 Attacker also recomputes the hash",
                                 key="tamper_rehash")
        with columns[2]:
            if st.button("↩ RESET CHAIN", key="tamper_reset", use_container_width=True):
                st.session_state["tamper_records"] = None
                st.session_state["tamper_result"] = None

        if apply_edit:
            tampered = [dict(r) for r in records]
            target = tampered[int(index)]
            try:
                target[field] = json.loads(replacement)
            except Exception:
                target[field] = replacement

            if rehash:
                from src.crypto.chain import compute_record_hash
                target["record_hash"] = compute_record_hash(target)

            from src.crypto.chain import verify_chain
            outcome = verify_chain(tampered)
            st.session_state["tamper_result"] = {
                "valid": bool(getattr(outcome, "valid", False)),
                "first_break_index": getattr(outcome, "first_break_index", None),
                "breaks": [
                    {"index": getattr(b, "index", None),
                     "type": str(getattr(b, "break_type", "")),
                     "detail": str(getattr(b, "detail", ""))[:160]}
                    for b in (getattr(outcome, "breaks", None) or [])][:12],
            }

        outcome = _state("tamper_result")
        if outcome:
            if outcome["valid"]:
                st.success("Chain still verifies — that edit was not detected.")
            else:
                st.error(f"🚨 TAMPER DETECTED — chain broken at index "
                         f"{outcome['first_break_index']}")
                st.dataframe(outcome["breaks"], use_container_width=True,
                             hide_index=True)
                st.caption("Re-hashing repairs the link but "
                           "cannot forge the Ed25519 signature — tamper still surfaces.")
        st.markdown('</div>', unsafe_allow_html=True)
    except Exception as exc:
        st.error(f"Tamper demo failed: {type(exc).__name__}: {exc}")
        LOGGER.error("tamper demo failed: %s\n%s", exc, traceback.format_exc())


# ---------------------------------------------------------------------------
# tab 4 — drift monitor
# ---------------------------------------------------------------------------
def tab_drift_monitor() -> None:
    """Render the distribution shift tab."""
    _section_head("📈", "Drift Monitor — operational vs adversarial shift",
                  "Five pixel properties · MMD · centroid drift · variance ratio. "
                  "Dusk is weather, injection is attack.")
    st.markdown(
        """<div class="how"><b>🎤 Jury line:</b> “Dusk and rain are <b>weather</b> —
        we stay calm. Injected content is <b>attack</b> — we escalate.”</div>""",
        unsafe_allow_html=True)

    columns = st.columns([3, 3, 1])
    with columns[0]:
        baseline = st.text_input("Baseline corpus", _demo_path("data", "clean"),
                                 key="dr_base")
    with columns[1]:
        current = st.text_input("Current corpus",
                                _demo_path("data", "drift", "injected"),
                                key="dr_cur")
    with columns[2]:
        st.write("")
        run = st.button("COMPARE", type="primary", use_container_width=True)

    max_images = st.slider("Max images per corpus", 30, 300, 120, key="dr_max")

    if run:
        try:
            from src.scanners.drift_detector import DistributionShiftDetector
            with st.spinner("Comparing pixel and feature distributions…"):
                st.session_state["drift_result"] = \
                    DistributionShiftDetector().compare(
                        baseline, current, max_images=int(max_images))
        except Exception as exc:
            st.error(f"Drift comparison failed: {type(exc).__name__}: {exc}")
            LOGGER.error("dashboard drift failed: %s\n%s", exc, traceback.format_exc())

    result = _state("drift_result")
    if not result:
        _empty_state("📈", "No comparison yet",
                     "Compare clean vs injected (attack) then clean vs dusk (weather).",
                     "weather stays green, attack goes red")
        return

    shift_type = str(result.get("shift_type", "UNKNOWN"))
    colour = ("#ff3b30" if "SUSPICIOUS" in shift_type else
              "#ffcc00" if "MIXED" in shift_type else "#30d158")
    icon = "🚨" if "SUSPICIOUS" in shift_type else "🌤️" if "NATURAL" in shift_type else "🔍"
    st.markdown(
        f"""<div class="verdict-hero" style="border-color:{colour}55;">
        <div style="font-size:34px;">{icon}</div>
        <div style="flex:1;"><div class="k-label">SHIFT TYPE</div>
        <div style="font-family:Space Grotesk;font-size:22px;font-weight:700;color:{colour};">
        {shift_type.replace('_', ' ')}</div>
        <div style="font-size:12px;color:#8fa3b8;">{_risk_bar(float(result.get('risk_score', 0.0)))}</div></div>
        </div>""",
        unsafe_allow_html=True)

    columns = st.columns(3)
    with columns[0]:
        st.markdown(_metric("Severity", result.get("severity", "NONE"), colour),
                    unsafe_allow_html=True)
    with columns[1]:
        st.markdown(_metric("Confidence",
                            f"{float(result.get('confidence', 0.0)):.2f}"),
                    unsafe_allow_html=True)
    with columns[2]:
        st.markdown(_metric("Risk", f"{float(result.get('risk_score', 0.0)):.3f}", colour),
                    unsafe_allow_html=True)

    st.markdown(f"**🔬 Characterization.** {result.get('characterization', '')}")
    st.info(f"**✅ Recommendation.** {result.get('recommendation', '')}")

    pixel = (result.get("pixel_analysis") or {}).get("properties") or {}
    if pixel:
        st.markdown("#### 🎨 Pixel-level properties")
        st.dataframe(
            [{
                "Property": name,
                "Baseline": round(float(entry.get("baseline_mean", 0.0)), 4),
                "Current": round(float(entry.get("current_mean", 0.0)), 4),
                "Z-score": round(float(entry.get("zscore", 0.0)), 3),
                "Rel. change": round(float(entry.get("relative_change", 0.0)), 4),
                "Shifted": "🔴 yes" if entry.get("shifted") else "🟢 no",
            } for name, entry in pixel.items()],
            use_container_width=True, hide_index=True)

    feature = result.get("feature_analysis") or {}
    if feature:
        with st.expander("🧬 Feature-level analysis (embeddings)"):
            st.json({k: v for k, v in feature.items() if not isinstance(v, (list, dict))})

    signatures = result.get("natural_signatures") or []
    if signatures:
        st.markdown("#### 🌤️ Matched natural signatures (weather — do not escalate)")
        st.write(signatures)

    st.markdown("#### 🔎 Findings")
    _show_findings(result.get("findings") or [], "drift")
    _show_limitations(result.get("limitations") or [])


# ---------------------------------------------------------------------------
# tab 5 — threat story
# ---------------------------------------------------------------------------
def tab_threat_story() -> None:
    """Render the correlation, immunity and briefing tab."""
    _section_head("📖", "Threat Story — correlation, immunity, command briefing",
                  "Cross-module correlation · Adversarial Immunity Score · "
                  "local LLM briefing with deterministic fallback.")
    st.markdown(
        """<div class="how"><b>🎤 Jury closer:</b> “Single alerts are noise.
        Correlated <b>threat story + one immunity number</b> is the commander's decision.”</div>""",
        unsafe_allow_html=True)

    available = {
        "data_scanner": _state("data_result"),
        "model_auditor": _state("model_result"),
        "crypto_chain": _state("crypto_result"),
        "drift_detector": _state("drift_result"),
    }
    present = {k: v for k, v in available.items() if v}

    if not present:
        _empty_state("📖", "No evidence yet",
                     "Run at least one scan in the other tabs, then return here. "
                     "Two or more modules = far stronger conclusions.",
                     "start with DATA SCANNER → MODEL AUDIT")
        return

    st.write("✅ Modules ready: "
             + ", ".join(f"`{k}`" for k in present))
    missing = [k for k in available if k not in present]
    if missing:
        st.info("⏳ Not yet run (counts as NOT ASSESSED, never as clean): " +
                ", ".join(f"`{k}`" for k in missing))

    columns = st.columns([1, 1, 2])
    with columns[0]:
        use_llm = st.checkbox("🤖 Use local LLM", value=False, key="ts_llm",
                              help="Queries Ollama on localhost. Falls back to "
                                   "a deterministic template when unavailable.")
    with columns[1]:
        persist = st.checkbox("💾 Save report", value=True, key="ts_save")
    with columns[2]:
        st.write("")
        run = st.button("⚡ CORRELATE & BRIEF", type="primary",
                        use_container_width=True)

    if run:
        try:
            from src.intelligence.briefing import generate_briefing
            from src.intelligence.immunity import compute_immunity_score
            from src.intelligence.threat_story import build_threat_story
            from src.reporting.report_generator import generate_report

            with st.spinner("🔗 Correlating findings across modules…"):
                story = build_threat_story(present)
                immunity = compute_immunity_score(present, story)
            with st.spinner("📝 Generating command briefing…"):
                briefing = generate_briefing(present, story, immunity,
                                             use_llm=use_llm)
            with st.spinner("📋 Building signed assurance report…"):
                report = generate_report(present, story, immunity, briefing,
                                         target={"modules": list(present)},
                                         persist=persist)
            st.session_state.update({"story": story, "immunity": immunity,
                                     "briefing": briefing, "report": report})
        except Exception as exc:
            st.error(f"Correlation failed: {type(exc).__name__}: {exc}")
            LOGGER.error("dashboard correlate failed: %s\n%s", exc,
                         traceback.format_exc())

    immunity = _state("immunity")
    story = _state("story")
    briefing = _state("briefing")
    report = _state("report")

    if not immunity:
        _empty_state("⚡", "Ready to correlate",
                     "Press CORRELATE & BRIEF to build the threat picture.",
                     "the immunity gauge is the jury closer")
        return

    score = float(immunity.get("score", 0.0))
    band = str(immunity.get("band", "UNKNOWN"))
    colour = BAND_COLOR.get(band, "#8e8e93")

    st.markdown("#### 🛡️ Adversarial Immunity Score — can this pipeline be trusted?")
    columns = st.columns([1, 2])
    with columns[0]:
        st.markdown(_gauge(score, band, colour), unsafe_allow_html=True)
    with columns[1]:
        st.progress(min(max(score / 100.0, 0.0), 1.0))
        st.caption(immunity.get("band_description", ""))
        st.caption(f"Assessment confidence "
                   f"{float(immunity.get('confidence', 0.0)):.2f} · "
                   f"{immunity.get('pillars_assessed', 0)} of "
                   f"{immunity.get('pillars_total', 4)} pillars assessed")
        components = immunity.get("components") or {}
        for key, entry in components.items():
            v = float(entry.get("score", 0.0))
            ok = bool(entry.get("assessed"))
            st.markdown(_bar_row(entry.get("label", key), v / 100.0,
                                 "· assessed" if ok else "· NOT ASSESSED"),
                        unsafe_allow_html=True)

    if story:
        assessment = story.get("campaign_assessment") or {}
        if assessment.get("campaign_detected"):
            st.error(f"🚨 COORDINATED CAMPAIGN DETECTED — confidence "
                     f"{float(assessment.get('confidence', 0.0)):.0%}. "
                     f"Patterns: {', '.join(assessment.get('patterns') or [])}")
        stories = story.get("stories") or []
        if stories:
            st.markdown(f"#### 📚 Threat narratives ({len(stories)})")
            for entry in stories:
                with st.expander(
                        f"[{entry.get('pattern')}] {entry.get('title')} — "
                        f"confidence {float(entry.get('confidence', 0.0)):.2f}"):
                    st.markdown(f"**Narrative.** {entry.get('narrative', '')}")
                    st.markdown(f"**Implication.** {entry.get('implication', '')}")
                    st.caption("Evidence: "
                               + ", ".join(entry.get("evidence_finding_ids") or []))
        else:
            st.success("✅ No cross-module campaign pattern met the materiality "
                       "floor. Individual findings may still require review.")

    if briefing:
        st.markdown("#### 🎖️ Commander's briefing")
        st.caption(f"Source: {briefing.get('source', 'template')}"
                   + (f" · model {briefing.get('model')}"
                      if briefing.get("model") else ""))
        st.text_area("Briefing", briefing.get("briefing", ""), height=280,
                     key="ts_brief")
        st.warning("⚠️ " + briefing.get("disclaimer",
                                        "AI-generated. Verify with analyst."))

    if report:
        st.markdown("#### 📋 Signed assurance report")
        columns = st.columns(3)
        with columns[0]:
            st.markdown(_metric("Findings", len(report.get("findings") or [])),
                        unsafe_allow_html=True)
        with columns[1]:
            st.markdown(_metric("Schema valid",
                                "yes ✓" if report.get("schema_valid") else "NO ✕",
                                "#30d158" if report.get("schema_valid")
                                else "#ff3b30"), unsafe_allow_html=True)
        with columns[2]:
            audit = report.get("audit_trail") or {}
            st.markdown(_metric("Audit chain",
                                "valid ✓" if audit.get("chain_valid") else "n/a",
                                "#30d158" if audit.get("chain_valid")
                                else "#8e8e93"), unsafe_allow_html=True)
        if report.get("report_path"):
            st.success(f"✅ Report written to `{report['report_path']}`")
        st.caption(f"report_hash = {str(report.get('report_hash', ''))[:48]}…")
        st.download_button(
            "⬇ Download report JSON",
            json.dumps(report, indent=2, default=str),
            file_name=f"{report.get('report_id', 'shield-report')}.json",
            mime="application/json", type="primary", use_container_width=True)
        _show_limitations(report.get("limitations") or [], report.get("coverage"))


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
ATTACK_LAB_PORT = 8765


@st.cache_resource(show_spinner=False)
def _attack_lab_server() -> Optional[str]:
    """Start the Attack Lab once per dashboard process.

    Returns:
        ``None`` on success, or an error message. A port already in use means a
        standalone ``demo/attack_lab.py`` is running, which the tab reuses.
    """
    try:
        from demo.attack_lab import start_in_background
        start_in_background(ATTACK_LAB_PORT)
        return None
    except OSError:
        return None  # already serving on this port
    except Exception as exc:
        LOGGER.error("Attack Lab failed to start: %s", exc)
        return f"{type(exc).__name__}: {exc}"


def tab_attack_lab() -> None:
    """Live jury demo: judges poison an image and watch the pipeline catch it."""
    _section_head("🎯", "Live Attack Lab — you attack, SHIELD catches",
                  "Pick any image, poison it, launch. The real engine rescans a scratch "
                  "copy — originals are never touched.")
    st.markdown(
        """<div class="how"><b>🎤 Jury opener (30 sec):</b> let the judge click the poison
        button themselves. Watching <b>their own attack get caught</b> beats 10 slides.</div>""",
        unsafe_allow_html=True)
    error = _attack_lab_server()
    if error:
        st.error(f"Attack Lab could not start: {error}")
        return
    url = f"http://127.0.0.1:{ATTACK_LAB_PORT}/"
    st.caption(f"🔗 Full screen for the jury: [{url}]({url})")
    if hasattr(st, "iframe"):
        st.iframe(url, height=1500)
    else:  # Streamlit < 1.5x
        import streamlit.components.v1 as components
        components.iframe(url, height=1500, scrolling=True)


def main() -> None:
    """Configure the page and render all tabs."""
    icon = str(LOGO_PNG) if LOGO_PNG.is_file() else "🛡"
    st.set_page_config(page_title="SHIELD-CV · Defence CV Integrity", page_icon=icon,
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(PREMIUM_CSS, unsafe_allow_html=True)
    _banner()
    _kpi_strip()

    with st.sidebar:
        logo = _logo_b64()
        if logo:
            st.markdown(
                f"""<div class="side-logo"><img src="{logo}" alt="SHIELD"/>
                <div><div class="t">SHIELD-CV</div>
                <div class="s">Defence CV Integrity · offline</div></div></div>""",
                unsafe_allow_html=True)
        st.markdown("### 🎖️ Mission")
        st.caption("Integrity assurance for multi-contributor CV pipelines. "
                   "Datasets, models and inference records are evaluated "
                   "independently, then correlated into one decision.")
        st.divider()
        st.markdown("### ⚙️ Operating constraints")
        st.markdown(
            """<div class="callout blue" style="margin:0;">
            🔒 100% offline — only local Ollama allowed<br/>
            🚫 No retraining of contributed models<br/>
            ⚡ CPU-only · no GPU required<br/>
            📝 Every finding: reason + evidence + disposition
            </div>""", unsafe_allow_html=True)
        st.divider()
        st.markdown("### 📡 Session")
        for label, key in (("📊 Data scan", "data_result"),
                           ("🧠 Model audit", "model_result"),
                           ("🔗 Chain verify", "crypto_result"),
                           ("📈 Drift", "drift_result"),
                           ("📖 Correlation", "immunity")):
            ready = bool(_state(key))
            st.caption(f"{'🟢' if ready else '⚪'} {label} — {'ready' if ready else 'pending'}")
        if st.button("🧹 Clear session", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        st.markdown(
            """<div class="india">🛡️ Built for Defence · Built for Trust<br/>🇮🇳 Made for India</div>""",
            unsafe_allow_html=True)

    tabs = st.tabs(["🎯 LIVE ATTACK LAB", "🧪 BACKDOOR STORY", "📊 DATA SCANNER",
                    "🧠 MODEL AUDIT", "🔗 CRYPTO LOCK",
                    "📈 DRIFT MONITOR", "📖 THREAT STORY"])
    renderers = (tab_attack_lab, tab_backdoor_story, tab_data_scanner, tab_model_audit,
                 tab_crypto_lock, tab_drift_monitor, tab_threat_story)
    for tab, renderer in zip(tabs, renderers):
        with tab:
            try:
                renderer()
            except Exception as exc:  # pragma: no cover - UI guard
                st.error(f"Tab failed to render: {type(exc).__name__}: {exc}")
                LOGGER.error("tab render failed: %s\n%s", exc, traceback.format_exc())


main()
