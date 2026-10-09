@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem =====================================================================
rem  start.bat - launch 1.0.0 (no console window)
rem
rem  Double-click this file. If it fails, use start_debug.bat instead.
rem  NOTE: intentionally pure ASCII (see build.bat for why).
rem =====================================================================

set "PYW="
set "PYW_ARGS="

if not defined PYTHONW_EXE goto :py_exe
if not exist "%PYTHONW_EXE%" goto :py_exe
"%PYTHONW_EXE%" -c "import sys" >nul 2>&1
if errorlevel 1 goto :py_exe
set "PYW=%PYTHONW_EXE%"
goto :launch

:py_exe
if defined PYW goto :launch
if not defined PYTHON_EXE goto :py_local
if not exist "%PYTHON_EXE%" goto :py_local
"%PYTHON_EXE%" -c "import sys" >nul 2>&1
if errorlevel 1 goto :py_local
set "PYW=%PYTHON_EXE%"
goto :launch

:py_local
if defined PYW goto :launch
if not exist "%~dp0pythonw.exe" goto :py_local_py
set "PYW=%~dp0pythonw.exe"
goto :launch

:py_local_py
if defined PYW goto :launch
if not exist "%~dp0python.exe" goto :py_launcher
set "PYW=%~dp0python.exe"
goto :launch

:py_launcher
if defined PYW goto :launch
py -3 -c "import sys" >nul 2>&1
if errorlevel 1 goto :py_path
set "PYW=pyw"
set "PYW_ARGS=-3"
goto :launch

:py_path
if defined PYW goto :launch
call :try_path
if defined PYW goto :launch
goto :py_none

:try_path
for /f "delims=" %%P in ('where python 2^>nul') do call :probe "%%~fP"
goto :eof

:probe
if defined PYW goto :eof
if not exist %1 goto :eof
set "CAND=%~1"
%1 -c "import sys" >nul 2>&1
if errorlevel 1 goto :eof
set "PWW=!CAND:python.exe=pythonw.exe!"
if exist "!PWW!" set "PYW=!PWW!"
if not defined PYW set "PYW=%CAND%"
goto :eof

:py_none
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

:launch
if "%PYW_ARGS%"=="-3" (
    start "" pyw -3 "main.py"
) else (
    start "" "%PYW%" "main.py"
)
exit /b 0
