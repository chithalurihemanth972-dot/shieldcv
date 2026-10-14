#!/usr/bin/env python3
"""SHIELD-CV launcher.

Runs the command-line interface without requiring the package to be installed,
by ensuring the project root is on ``sys.path`` first. This is the supported
entry point for an air-gapped checkout:

    python run.py scan demo/data/poisoned
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _from_caller(arg: str, caller: Path) -> str:
    """Absolutise a relative path argument that exists in the caller's folder."""
    if arg.startswith("-") or Path(arg).is_absolute():
        return arg
    candidate = caller / arg
    return str(candidate) if candidate.exists() else arg


def main() -> int:
    """Delegate to the CLI entry point.

    ``shield.bat`` changes into the project root before calling this, so a
    relative path typed in another folder would otherwise resolve against the
    project. It records the original folder in ``SHIELD_CALLER_CWD``; any
    argument after the subcommand that exists relative to it is absolutised.

    Returns:
        Process exit code.
    """
    from src.utils.stdio import ensure_utf8_stdio
    ensure_utf8_stdio()
    caller = os.environ.get("SHIELD_CALLER_CWD")
    if caller and len(sys.argv) > 2:
        sys.argv[2:] = [_from_caller(a, Path(caller)) for a in sys.argv[2:]]
    from src.cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
