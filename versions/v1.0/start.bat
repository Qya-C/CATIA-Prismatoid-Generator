@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem =====================================================================
rem  start.bat - launch the plugin (no console window)
rem
rem  Double-click this file.
rem
rem  If it fails, edit PY / PYW below to the full paths of your
rem  python.exe and pythonw.exe (note: pythonw has no console).
rem
rem  Why the paths are hard-coded:
rem    On many Windows systems the bare command "python" resolves to a
rem    Microsoft Store alias stub that does nothing. Hard-coding the real
rem    interpreter avoids that entirely.
rem
rem  If your Python path contains spaces, wrap the variables in quotes
rem  where they are used (both places below).
rem =====================================================================

set "PY=C:\Users\eraria\AppData\Local\Programs\Python\Python311\python.exe"
set "PYW=C:\Users\eraria\AppData\Local\Programs\Python\Python311\pythonw.exe"

if exist "%PYW%" goto :launch

rem --- fallback: the Python launcher (installed by python.org installer) ---
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PYW=pyw -3"
    goto :launch
)

rem --- fallback: scan PATH, skipping the Microsoft Store alias ---
for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | find /i "WindowsApps" >nul
    if errorlevel 1 (
        set "CAND=%%~fP"
        set "PWW=!CAND:python.exe=pythonw.exe!"
        if exist "!PWW!" (
            set "PYW=!PWW!"
        ) else (
            set "PYW=!CAND!"
        )
        goto :launch
    )
)

echo.
echo [ERROR] Python interpreter not found.
echo.
echo Two ways to fix:
echo   1) Open this file and set PY / PYW to your real Python paths.
echo   2) Disable the Store aliases so "python" works normally:
echo      Settings - Apps - Advanced app settings
echo      - App execution aliases - turn OFF python.exe / python3.exe
echo.
pause
exit /b 1

:launch
start "" %PYW% "main.py"
exit /b 0