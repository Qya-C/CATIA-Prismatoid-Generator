@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem =====================================================================
rem  start_debug.bat - launch the plugin WITH a console window
rem
rem  Use this one when something goes wrong: errors stay on screen.
rem =====================================================================

set "PY=C:\Users\eraria\AppData\Local\Programs\Python\Python311\python.exe"

if exist "%PY%" goto :run
echo [WARN] Configured python.exe not found, falling back to "py -3".
set "PY=py -3"

:run
echo Working directory : %CD%
echo Interpreter       : %PY%
echo.

%PY% main.py
echo.
echo ---- exit code: %errorlevel% ----
echo.
echo If something failed, run the self-test next:
echo     %PY% diagnose_v1.py
echo.
pause