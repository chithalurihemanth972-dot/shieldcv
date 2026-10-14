"""SHIELD Console — full-screen terminal UI for SHIELD-CV."""

from __future__ import annotations

from typing import Optional, Sequence

MISSING_DEPS_HINT = """\
SHIELD Console could not start: {error}

It needs the 'textual' and 'textual-image' packages.
  Offline install:  pip install --no-index --find-links wheels/ -r requirements.txt
Scripted checks still work without them:  shield scan <path>   (see: shield help)
"""


def launch(argv: Optional[Sequence[str]] = None) -> int:
    """Start the console, or explain what is missing."""
    try:
        from src.tui.app import main
    except ImportError as exc:
        print(MISSING_DEPS_HINT.format(error=exc))
        return 2
    return main(argv)
