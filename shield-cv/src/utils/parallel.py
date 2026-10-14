"""Thread-pool sizing shared by the per-image detectors.

Per-image work (JPEG decoding, FFTs, OpenCV filters) releases the GIL, so
threads scale across cores without the memory cost of one process per worker.
"""

from __future__ import annotations

import os

from src.config import get_config


def io_workers() -> int:
    """Number of threads for per-image work.

    ``runtime.io_workers`` overrides; 0 or absent means one per logical core,
    capped at 16 so a large host does not thrash the disk.
    """
    try:
        configured = int(get_config().get("runtime.io_workers", 0) or 0)
    except Exception:
        configured = 0
    if configured > 0:
        return configured
    return max(1, min(16, os.cpu_count() or 1))
