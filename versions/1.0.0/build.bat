@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem =====================================================================
rem  build.bat - package 1.0.0 into a single double-clickable EXE
rem
rem  Output: .\CATIA_Prismatoid_Generator.exe
rem
rem  NOTE: this file is intentionally pure ASCII. cmd.exe reads .bat files
rem        byte-wise using the current code page, so non-ASCII text can eat
rem        neighbouring command characters and break parsing.
rem =====================================================================

set "ONEFILE=1"
set "ICONNAME=app.ico"

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


:args
if "%ONEFILE%"=="1" (set "MODE_ARG=--onefile") else (set "MODE_ARG=--onedir")

set "ICON_ARG="
if exist "%ICONNAME%" set "ICON_ARG=--icon %ICONNAME%"

set "DISTPATH=."

echo.
echo === 0) Environment ===
if "%PY_ARGS%"=="-3" (
    py -3 -c "import sys, platform; print('Python  :', sys.version.split()[0]); print('Bitness :', platform.architecture()[0]); print('Exe     :', sys.executable)"
) else (
    "%PY%" -c "import sys, platform; print('Python  :', sys.version.split()[0]); print('Bitness :', platform.architecture()[0]); print('Exe     :', sys.executable)"
)
if errorlevel 1 goto :fail

echo.
echo === 1) Kernel import check ===
if "%PY_ARGS%"=="-3" (
    py -3 -c "import importlib; m = importlib.import_module('catia_controller_v1'); print('module  :', m.__file__)"
) else (
    "%PY%" -c "import importlib; m = importlib.import_module('catia_controller_v1'); print('module  :', m.__file__)"
)
if errorlevel 1 (
    echo.
    echo [FAIL] Cannot import catia_controller_v1.
    echo        Make sure catia_controller_v1.py sits next to this script.
    goto :fail
)

echo.
echo === 2) Runtime hook check ===
if not exist "rthook_log.py" (
    echo [FAIL] rthook_log.py not found next to this script.
    goto :fail
)
echo rthook_log.py found.

echo.
echo === 3) PyInstaller ===
if "%PY_ARGS%"=="-3" (py -3 -m PyInstaller --version >nul 2>&1) else ("%PY%" -m PyInstaller --version >nul 2>&1)
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    if "%PY_ARGS%"=="-3" (py -3 -m pip install --upgrade pyinstaller) else ("%PY%" -m pip install --upgrade pyinstaller)
    if errorlevel 1 goto :fail
)
if "%PY_ARGS%"=="-3" (py -3 -m PyInstaller --version) else ("%PY%" -m PyInstaller --version)

echo.
echo === 4) Clean previous output ===
if exist "CATIA_Prismatoid_Generator.exe" del /q "CATIA_Prismatoid_Generator.exe"
if exist "CATIA_Prismatoid_Generator" rmdir /s /q "CATIA_Prismatoid_Generator"
if exist "_build_output" rmdir /s /q "_build_output"
mkdir "_build_output"

echo.
echo === 5) Build (1-3 minutes; do NOT close this window) ===
echo   mode : %MODE_ARG%
if defined ICON_ARG (echo   icon : %ICON_ARG%) else (echo   icon : none)
echo.

set "PYI_ARGS=--noconfirm --clean %MODE_ARG% --windowed %ICON_ARG% --name CATIA_Prismatoid_Generator --collect-all pycatia --hidden-import catia_controller_v1 --hidden-import win32com.client --hidden-import pywintypes --hidden-import pythoncom --runtime-hook rthook_log.py --distpath "%DISTPATH%" --workpath "_build_output\build" --specpath "_build_output" main.py"

if "%PY_ARGS%"=="-3" (
    py -3 -m PyInstaller %PYI_ARGS%
) else (
    "%PY%" -m PyInstaller %PYI_ARGS%
)
if errorlevel 1 goto :fail

echo.
echo === 6) Done ===
if "%ONEFILE%"=="1" (
    if not exist "CATIA_Prismatoid_Generator.exe" (
        echo [FAIL] Expected CATIA_Prismatoid_Generator.exe but it was not found.
        goto :fail
    )
    echo   Single EXE : %CD%\CATIA_Prismatoid_Generator.exe
    echo   You can copy this one file anywhere.
) else (
    echo   EXE folder : %CD%\CATIA_Prismatoid_Generator
    echo   NOTE: keep the EXE together with its _internal folder.
)
echo.
echo Next steps:
echo   1. Start CATIA V5 and open a new Part document.
echo   2. Run the EXE. Onefile builds need 5-10 seconds to start.
echo   3. If nothing appears, read launch_log.txt next to the EXE.
echo.
pause
exit /b 0

:fail
echo.
echo [FAIL] See the messages above.
echo.
pause >nul
exit /b 1
