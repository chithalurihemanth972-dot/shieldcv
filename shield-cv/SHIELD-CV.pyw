#!/usr/bin/env python3
"""SHIELD-CV desktop launcher (no-console .pyw).

The Desktop shortcut points here with the project .venv pythonw.exe, so a
double-click opens the premium Streamlit dashboard in the browser with no
terminal window. Engine code is untouched — this only starts
``streamlit run src/dashboard.py`` and opens http://127.0.0.1:8501.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "src" / "dashboard.py"
PORT = 8501
URL = f"http://127.0.0.1:{PORT}/"
LOG = ROOT / "output" / "desktop_app.log"


def _port_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False


def _log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def main() -> int:
    _log("launch requested")
    if not DASHBOARD.is_file():
        _log(f"missing dashboard: {DASHBOARD}")
        return 1
    if _port_open():
        _log("port already open, reusing session")
        try:
            webbrowser.open(URL)
        except Exception as exc:
            _log(f"browser open failed: {exc}")
        return 0
    cmd = [sys.executable, "-m", "streamlit", "run", str(DASHBOARD),
           "--server.port", str(PORT), "--server.headless", "true",
           "--browser.gatherUsageStats", "false"]
    _log("starting: " + " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except Exception as exc:
        _log(f"start failed: {type(exc).__name__}: {exc}")
        return 1
    for _ in range(60):
        if _port_open():
            break
        if proc.poll() is not None:
            _log(f"streamlit exited early code={proc.poll()}")
            return 1
        time.sleep(0.5)
    _log("server up, opening browser")
    try:
        webbrowser.open(URL)
    except Exception as exc:
        _log(f"browser open failed: {exc}")
    try:
        proc.wait()
    except KeyboardInterrupt:
        pass
    _log("server stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
