@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem =====================================================================
rem  start.bat - launch the plugin (no console window)
rem
rem  Double-click this file. If it fails, use start_debug.bat instead.
rem
rem  NOTE: this file is intentionally pure ASCII. It never wraps the "pyw"
rem        launcher in quotes and it avoids nesting "for /f" inside an
rem        "if (...)" block; both are real cmd.exe traps. See README.md.
rem =====================================================================

set "PYLAUNCH=0"
set "PYW="
set "PYW_ARGS="

rem --- 1) explicit override ---
if not defined PYTHONW_EXE goto :d_exe
if not exist "PYTHONW_EXE" goto :d_exe
call :verify "PYTHONW_EXE"
if errorlevel 1 goto :d_exe
set "PYW=PYTHONW_EXE"
goto :d_done

:d_exe
rem --- 2) a real python.exe sitting next to this script (portable layouts) ---
if defined PYW goto :d_done
if not exist "%~dp0pythonw.exe" goto :d_launcher
call :verify "%~dp0pythonw.exe"
if errorlevel 1 goto :d_launcher
set "PYW=%~dp0pythonw.exe"
goto :d_done

:d_launcher
rem --- 3) the py launcher shipped with python.org installers ---
rem     This is the DEFAULT route on most machines. Note that py.exe must
rem     NOT be wrapped in quotes (see the header comment, issue 4).
if defined PYW goto :d_done
py -3 -c "import sys" >nul 2>&1
if errorlevel 1 goto :d_path
set "PYLAUNCH=1"
set "PYW=py"
set "PYW_ARGS=-3"
goto :d_done

:d_path
rem --- 4) scan PATH; every candidate must actually run "import sys" ---
rem     Verifying by execution matters: `where python` also matches path
rem     FRAGMENTS (a folder merely named "...python..."), which yields a
rem     truncated path. The WindowsApps filter cannot catch that.
if defined PYW goto :d_done
for /f "delims=" %%P in ('where python 2^>nul') do call :probe "%%~fP"
if defined PYW goto :d_done
goto :d_none

:probe
if not "%~1"=="" if not defined PYW (
    call :verify "%~1"
    if not errorlevel 1 set "PYW=%~1"
)
goto :eof

:verify
if not exist %1 exit /b 1
%1 -c "import sys" >nul 2>&1
exit /b %errorlevel%

:d_none
echo.
echo [ERROR] No working Python 3 found.
echo.
echo Two ways to fix:
echo   1) Edit this file and set PYTHONW_EXE to your pythonw.exe full path.
echo   2) Install Python 3.11+ ^(64-bit^) from python.org; the "py"
echo      launcher it installs is enough.
echo.
pause
exit /b 1

:d_done


:launch
echo Starting with: %PYW% %PYW_ARGS% main_v2.py
if "%PYLAUNCH%"=="1" (
    start "" pyw %PYW_ARGS% "main_v2.py"
) else (
    start "" "%PYW%" "main_v2.py"
)
exit /b 0
