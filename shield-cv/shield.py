#!/usr/bin/env python3
"""SHIELD-CV interactive console.

Run:  python shield.py [--no-splash]      (or just `shield`)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.tui import launch  # noqa: E402

if __name__ == "__main__":
    sys.exit(launch())
