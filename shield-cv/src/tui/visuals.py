"""Pure Rich renderables for the console: gradients, bars, gauges, the logo.

Everything here is width-explicit and UI-free, so it is unit-testable.
"""

from __future__ import annotations

import math
from typing import List, Mapping, Optional, Sequence, Tuple

from rich.text import Text

from src.tui.theme import PALETTE, SEVERITY_COLORS, SEVERITY_ORDER, TONE_COLORS

LOGO: List[str] = [
    "███████╗██╗  ██╗██╗███████╗██╗     ██████╗ ",
    "██╔════╝██║  ██║██║██╔════╝██║     ██╔══██╗",
    "███████╗███████║██║█████╗  ██║     ██║  ██║",
    "╚════██║██╔══██║██║██╔══╝  ██║     ██║  ██║",
    "███████║██║  ██║██║███████╗███████╗██████╔╝",
    "╚══════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚═════╝ ",
]
_EIGHTHS = " ▏▎▍▌▋▊▉"


def lerp_color(a: str, b: str, t: float) -> str:
    """Blend two ``#rrggbb`` colours."""
    t = min(1.0, max(0.0, t))
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def gradient_text(text: str, start: str, end: str, bold: bool = True) -> Text:
    """Colour ``text`` left-to-right from ``start`` to ``end``."""
    out = Text()
    span = max(1, len(text) - 1)
    for i, char in enumerate(text):
        out.append(char, style=f"{'bold ' if bold else ''}{lerp_color(start, end, i / span)}")
    return out


def logo_text(phase: float = 0.0) -> Text:
    """The SHIELD logo with a gradient that sweeps as ``phase`` grows."""
    width = max(len(line) for line in LOGO)
    out = Text()
    for row, line in enumerate(LOGO):
        for col, char in enumerate(line):
            wave = 0.5 + 0.5 * math.sin(2 * math.pi * (col / width - phase) + row * 0.25)
            out.append(char, style=f"bold {lerp_color(PALETTE['cyan'], PALETTE['violet'], wave)}")
        if row < len(LOGO) - 1:
            out.append("\n")
    return out


def banner_text(verdict: str, tone: str, note: str, width: int) -> Text:
    """Three full-width lines on a gradient background, verdict letter-spaced."""
    width = max(10, width)
    bright, deep = TONE_COLORS.get(tone, TONE_COLORS["info"])
    rows = ["", " ".join(verdict.upper()), note]
    out = Text()
    for index, content in enumerate(rows):
        line = content[:width].center(width)
        for col, char in enumerate(line):
            bg = lerp_color(deep, bright, abs(col / max(1, width - 1) - 0.5) * 2 * 0.55)
            style = f"bold #FFFFFF on {bg}" if index == 1 else f"#F2F2F2 on {bg}"
            out.append(char, style=style)
        if index < len(rows) - 1:
            out.append("\n")
    return out


def bar(fraction: float, width: int, color: str) -> Text:
    """A smooth horizontal bar exactly ``width`` cells wide."""
    width = max(1, width)
    fraction = 0.0 if not fraction or fraction < 0 else min(1.0, fraction)
    eighths = int(round(fraction * width * 8))
    full, rem = divmod(eighths, 8)
    out = Text("█" * full, style=color)
    if full < width:
        out.append(_EIGHTHS[rem] if rem else " ", style=f"{color} on {PALETTE['track']}")
        out.append(" " * (width - full - 1), style=f"on {PALETTE['track']}")
    return out


def _risk_color(risk: float) -> str:
    if risk >= 0.75:
        return PALETTE["danger"]
    if risk >= 0.45:
        return PALETTE["warn"]
    return PALETTE["ok"]


def risk_gauge(risk: Optional[float], width: int) -> Text:
    """``RISK ███████▊░░░ 0.82``."""
    if risk is None:
        return Text("RISK  n/a", style=PALETTE["muted"])
    color = _risk_color(risk)
    out = Text("RISK  ", style="bold")
    out.append_text(bar(risk, max(4, width - 12), color))
    out.append(f"  {risk:.2f}", style=f"bold {color}")
    return out


def severity_bar(counts: Mapping[str, int], width: int) -> Text:
    """Stacked severity bar plus a legend line."""
    total = sum(int(counts.get(s, 0) or 0) for s in SEVERITY_ORDER)
    if total == 0:
        return Text("no findings", style=PALETTE["muted"])
    out = Text()
    used = 0
    present = [s for s in SEVERITY_ORDER if int(counts.get(s, 0) or 0) > 0]
    for index, sev in enumerate(present):
        cells = width - used if index == len(present) - 1 else \
            max(1, round(width * int(counts[sev]) / total))
        cells = max(0, min(cells, width - used))
        out.append("█" * cells, style=SEVERITY_COLORS[sev])
        used += cells
    out.append("\n")
    for sev in present:
        out.append("■ ", style=SEVERITY_COLORS[sev])
        out.append(f"{sev} {int(counts[sev])}   ")
    return out


def labelled_bars(rows: Sequence[Tuple[str, float, str, str]], width: int) -> Text:
    """One ``label  bar  value`` line per row."""
    if not rows:
        return Text("")
    label_w = min(24, max(len(r[0]) for r in rows))
    value_w = max(len(r[3]) for r in rows)
    bar_w = max(6, width - label_w - value_w - 4)
    out = Text()
    for index, (label, fraction, color, value) in enumerate(rows):
        out.append(label[:label_w].ljust(label_w) + "  ")
        out.append_text(bar(fraction, bar_w, color))
        out.append("  " + value.rjust(value_w), style=f"bold {color}")
        if index < len(rows) - 1:
            out.append("\n")
    return out
