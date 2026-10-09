@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem =====================================================================
rem  start_debug.bat - launch v1.0 WITH a console window
rem
rem  Use this one when something goes wrong: errors stay on screen.
rem  NOTE: intentionally pure ASCII (see build.bat for why).
rem =====================================================================

rem ---------------------------------------------------------------------
rem  Locate a usable Python 3 interpreter.
rem
rem  Every candidate must actually run "import sys" before it is accepted:
rem    a) the bare command "python" often resolves to a Microsoft Store
rem       alias stub that does nothing;
rem    b) `where python` also matches path FRAGMENTS (a folder merely named
rem       like "...python..."), yielding a truncated path.
rem
rem  NOTE: this block deliberately uses goto labels instead of nesting a
rem  "for /f" inside an "if (...)" block -- cmd.exe mis-parses that and
rem  reports a misleading "Edit was unexpected at this time".
rem ---------------------------------------------------------------------
set "PY="
set "PY_ARGS="

if not defined PYTHON_EXE goto :py_local
if not exist "%PYTHON_EXE%" goto :py_local
"%PYTHON_EXE%" -c "import sys" >nul 2>&1
if errorlevel 1 goto :py_local
set "PY=%PYTHON_EXE%"
goto :py_done

:py_local
if defined PY goto :py_done
if not exist "%~dp0python.exe" goto :py_launcher
set "PY=%~dp0python.exe"
goto :py_done

:py_launcher
if defined PY goto :py_done
py -3 -c "import sys" >nul 2>&1
if errorlevel 1 goto :py_path
set "PY=py"
set "PY_ARGS=-3"
goto :py_done

:py_path
if defined PY goto :py_done
call :try_path
if defined PY goto :py_done
goto :py_none

:try_path
for /f "delims=" %%P in ('where python 2^>nul') do call :probe "%%~fP"
goto :eof

:probe
if defined PY goto :eof
if not exist %1 goto :eof
%1 -c "import sys" >nul 2>&1
if errorlevel 1 goto :eof
set "PY=%~1"
goto :eof

:py_none
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

:py_done


:run
echo Working directory : %CD%
echo Interpreter       : %PY% %PY_ARGS%
echo.

if "%PY_ARGS%"=="-3" (
    py -3 main.py
) else (
    "%PY%" main.py
)
echo.
echo ---- exit code: %errorlevel% ----
echo.
echo If something failed, run the self-test next:
echo     "%PY%" %PY_ARGS% diagnose_v1.py
echo.
pause
