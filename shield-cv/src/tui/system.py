"""Hand a file to the operating system's own viewer (local only)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def open_path(path: Path) -> Optional[str]:
    """Open ``path`` in the default local application; return an error or ``None``."""
    try:
        if not Path(path).exists():
            return f"not found: {path}"
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return None
    except OSError as exc:
        return f"{type(exc).__name__}: {exc}"
