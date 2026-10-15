"""Colours for the SHIELD Console."""

from __future__ import annotations

from textual.theme import Theme

PALETTE = {
    "cyan": "#22D3EE", "violet": "#A78BFA", "bg": "#0A0E14", "surface": "#111722",
    "panel": "#182030", "fg": "#E6EDF3", "muted": "#7D8590", "track": "#232B3A",
    "ok": "#3FB950", "warn": "#F0B429", "danger": "#F85149", "info": "#58A6FF",
}

# (bright, deep) pairs: banners blend from deep at the centre to bright at the edges.
TONE_COLORS = {
    "danger": ("#FF5D5D", "#7A1020"),
    "warn": ("#FFC24B", "#7A4A00"),
    "ok": ("#4ADE80", "#0F5A2E"),
    "info": ("#60A5FA", "#1E3A8A"),
}

SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
SEVERITY_COLORS = {"CRITICAL": "#F85149", "HIGH": "#FB8F44", "MEDIUM": "#F0B429",
                   "LOW": "#58A6FF", "INFO": "#7D8590"}

SHIELD_THEME = Theme(
    name="shield", primary=PALETTE["cyan"], secondary=PALETTE["violet"],
    accent=PALETTE["violet"], foreground=PALETTE["fg"], background=PALETTE["bg"],
    surface=PALETTE["surface"], panel=PALETTE["panel"], success=PALETTE["ok"],
    warning=PALETTE["warn"], error=PALETTE["danger"], dark=True)
