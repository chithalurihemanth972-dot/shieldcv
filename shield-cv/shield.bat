@echo off
:: SHIELD-CV Custom Command Dispatcher
:: Type 'shield <command>' from anywhere (after adding this folder to PATH)
::
:: Commands:
::   shield                -> open interactive mode (same as start)
::   shield start          -> open interactive mode
::   shield scan <path>    -> scan dataset / model / records
::   shield audit <path>   -> audit a model
::   shield verify <path>  -> verify provenance chain
::   shield drift <base> <cur> -> detect drift
::   shield report [all]   -> full assurance report
::   shield demo           -> guided 8-stage demo
::   shield dashboard      -> open GUI dashboard
::   shield lab            -> live Attack Lab for the jury
::   shield test           -> run edge-case tests
::   shield help           -> show help

setlocal
set "ROOT=%~dp0"
:: Remember where the user typed `shield` so relative paths resolve from there.
set "SHIELD_CALLER_CWD=%CD%"
cd /d "%ROOT%"

set "CMD=%~1"
if "%CMD%"=="" set "CMD=start"
set "ARGS="
shift

:collect
if "%~1"=="" goto run
set ARGS=%ARGS% %1
shift
goto collect

:run
if /i "%CMD%"=="start"      ( python shield.py & goto :eof )
if /i "%CMD%"=="scan"       ( python run.py scan %ARGS% & goto :eof )
if /i "%CMD%"=="agents"     ( python run.py office %ARGS% & goto :eof )
if /i "%CMD%"=="audit"      ( python run.py audit %ARGS% & goto :eof )
if /i "%CMD%"=="verify"     ( python run.py scan %ARGS% & goto :eof )
if /i "%CMD%"=="drift"      ( python run.py drift %ARGS% & goto :eof )
if /i "%CMD%"=="report"     ( python run.py report %ARGS% & goto :eof )
if /i "%CMD%"=="demo"       ( python demo\run_demo.py --quick %ARGS% & goto :eof )
if /i "%CMD%"=="dashboard"  ( python -m streamlit run src\dashboard.py & goto :eof )
if /i "%CMD%"=="test"       ( python tests\test_edge_cases.py & python demo\validate_phase2.py & goto :eof )
if /i "%CMD%"=="present"    ( python present.py %ARGS% & goto :eof )
if /i "%CMD%"=="lab"        ( python demo\attack_lab.py %ARGS% & goto :eof )
if /i "%CMD%"=="help"       ( goto :help )
if /i "%CMD%"=="--help"     ( goto :help )

echo.
echo  [ERROR] Unknown command: %CMD%
echo  Type 'shield help' for available commands.
exit /b 1

:help
echo.
echo  SHIELD-CV Commands:
echo  -------------------
echo  shield                 Open interactive mode
echo  shield start           Open interactive mode
echo  shield scan ^<path^>     Scan dataset / model / records
echo  shield agents ^<root^>  One agent per contributor, in parallel
echo  shield audit ^<model^>   Audit model for backdoors
echo  shield verify ^<json^>   Verify provenance chain
echo  shield drift ^<base^> ^<cur^>  Detect drift
echo  shield report [all]    Full assurance report
echo  shield demo            Guided 8-stage demo
echo  shield dashboard       Open GUI dashboard
echo  shield test            Run tests
echo  shield present         Jury presentation mode
echo  shield lab             Live Attack Lab (judges poison data)
echo  shield help            This help
echo.
exit /b 0
