"""Make console output safe on Windows code pages.

Rich panels and finding text use characters such as ``→`` and ``·``. On a
Windows console (or a redirected stream) defaulting to cp1252 those raise
``UnicodeEncodeError`` mid-run and abort the command. Switching the standard
streams to UTF-8, replacing anything still unencodable, keeps output flowing.
"""

from __future__ import annotations

import sys


def ensure_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 with replacement. Never raises."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and (stream.encoding or "").lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
