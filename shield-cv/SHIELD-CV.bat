@echo off
:: SHIELD-CV — double-click desktop fallback (console visible).
:: The Desktop icon uses SHIELD-CV.pyw (no console). Use this BAT when you
:: want to see the server log, or on machines where .pyw has no association.
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
if exist "%ROOT%.venv\Scripts\python.exe" (
  set "PY=%ROOT%.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
start "" "http://127.0.0.1:8501/"
"%PY%" -m streamlit run src\dashboard.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
pause
