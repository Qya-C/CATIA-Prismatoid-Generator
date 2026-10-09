@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem =====================================================================
rem  start_debug.bat - launch the plugin WITH a console window
rem
rem  Use this one when something goes wrong: errors stay on screen.
rem
rem  NOTE: this file is intentionally pure ASCII. It never wraps the "py"
rem        launcher in quotes and it avoids nesting "for /f" inside an
rem        "if (...)" block; both are real cmd.exe traps. See README.md.
rem =====================================================================

set "PYLAUNCH=0"
set "PY="
set "PY_ARGS="

rem --- 1) explicit override ---
if not defined PYTHON_EXE goto :d_exe
if not exist "PYTHON_EXE" goto :d_exe
call :verify "PYTHON_EXE"
if errorlevel 1 goto :d_exe
set "PY=PYTHON_EXE"
goto :d_done

:d_exe
rem --- 2) a real python.exe sitting next to this script (portable layouts) ---
if defined PY goto :d_done
if not exist "%~dp0python.exe" goto :d_launcher
call :verify "%~dp0python.exe"
if errorlevel 1 goto :d_launcher
set "PY=%~dp0python.exe"
goto :d_done

:d_launcher
rem --- 3) the py launcher shipped with python.org installers ---
rem     This is the DEFAULT route on most machines. Note that py.exe must
rem     NOT be wrapped in quotes (see the header comment, issue 4).
if defined PY goto :d_done
py -3 -c "import sys" >nul 2>&1
if errorlevel 1 goto :d_path
set "PYLAUNCH=1"
set "PY=py"
set "PY_ARGS=-3"
goto :d_done

:d_path
rem --- 4) scan PATH; every candidate must actually run "import sys" ---
rem     Verifying by execution matters: `where python` also matches path
rem     FRAGMENTS (a folder merely named "...python..."), which yields a
rem     truncated path. The WindowsApps filter cannot catch that.
if defined PY goto :d_done
for /f "delims=" %%P in ('where python 2^>nul') do call :probe "%%~fP"
if defined PY goto :d_done
goto :d_none

:probe
if not "%~1"=="" if not defined PY (
    call :verify "%~1"
    if not errorlevel 1 set "PY=%~1"
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
echo   1) Edit this file and set PYTHON_EXE to your python.exe full path.
echo   2) Install Python 3.11+ ^(64-bit^) from python.org; the "py"
echo      launcher it installs is enough.
echo.
pause
exit /b 1

:d_done


:run
echo Working directory : %CD%
echo Interpreter       : %PY% %PY_ARGS%
echo.

if "%PYLAUNCH%"=="1" (
    py %PY_ARGS% main_v2.py
) else (
    "%PY%" main_v2.py
)
echo.
echo ---- exit code: %errorlevel% ----
echo.
echo If something failed, run the self-test next:
echo     py -3 diagnose_v2.py
echo.
pause
