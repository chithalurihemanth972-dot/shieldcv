"""Visual renderables fill their width exactly and degrade on empty data."""
from __future__ import annotations

from src.tui.theme import SEVERITY_COLORS, SHIELD_THEME
from src.tui.visuals import (LOGO, banner_text, bar, gradient_text, labelled_bars, lerp_color,
                             logo_text, risk_gauge, severity_bar)


def test_lerp_color_endpoints():
    assert lerp_color("#000000", "#ffffff", 0.0) == "#000000"
    assert lerp_color("#000000", "#ffffff", 1.0) == "#ffffff"
    assert lerp_color("#000000", "#ffffff", 0.5) == "#808080"


def test_gradient_text_colours_change_across_the_text():
    text = gradient_text("SHIELD", "#22d3ee", "#a78bfa")
    assert text.plain == "SHIELD"
    styles = {str(span.style) for span in text.spans}
    assert len(styles) > 1


def test_logo_text_has_every_line():
    assert logo_text(0.3).plain.count("\n") == len(LOGO) - 1


def test_bar_is_exact_width():
    for fraction in (0.0, 0.33, 0.5, 1.0, 1.7, -1):
        assert len(bar(fraction, 20, "#ff0000").plain) == 20


def test_risk_gauge():
    assert "0.82" in risk_gauge(0.82, 40).plain
    assert "n/a" in risk_gauge(None, 40).plain


def test_banner_is_three_full_lines():
    lines = banner_text("COMPROMISED", "danger", "7 findings", 60).plain.split("\n")
    assert len(lines) == 3 and all(len(line) == 60 for line in lines)
    assert "C O M P R O M I S E D" in lines[1]


def test_severity_bar_legend_and_empty():
    plain = severity_bar({"CRITICAL": 2, "LOW": 6}, 40).plain
    assert "CRITICAL 2" in plain and "LOW 6" in plain
    assert len(plain.split("\n")[0]) == 40
    assert "no findings" in severity_bar({}, 40).plain
    assert set(SEVERITY_COLORS) >= {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def test_labelled_bars():
    plain = labelled_bars([("contributor_alpha", 0.9, "#ff0000", "0.90"),
                           ("bravo", 0.1, "#00ff00", "0.10")], 50).plain
    assert "contributor_alpha" in plain and "0.10" in plain
    assert labelled_bars([], 50).plain == ""


def test_theme_is_dark_and_named():
    assert SHIELD_THEME.name == "shield" and SHIELD_THEME.dark
