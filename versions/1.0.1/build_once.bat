@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem =====================================================================
rem  build_once.bat - single-pass build (internal; normally run build.bat)
rem
rem  1.0.1 changes vs 1.0.0:
rem    * entry script : main_v2.py            (was main.py)
rem    * kernel module: catia_controller_v2   (was catia_controller_v1)
rem
rem  Output: .\CATIA_Prismatoid_Generator.exe  (next to main_v2.py)
rem  Icon  : drop an app.ico here and it is used automatically.
rem
rem  This script only builds; it does NOT run the launch smoke test.
rem  For "build + smoke test", run build.bat in the same folder.
rem
rem  NOTE: this file is intentionally pure ASCII, and it deliberately uses
rem        goto labels plus helper subroutines instead of nesting a
rem        "for /f" inside an "if (...)" block, and it never wraps the "py"
rem        launcher in quotes. Both are real, already-hit cmd.exe traps.
rem        See README.md ("Why the .bat files are pure ASCII").
rem =====================================================================

set "ONEFILE=1"
set "ICONNAME=app.ico"

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


:args
if "%ONEFILE%"=="1" (set "MODE_ARG=--onefile") else (set "MODE_ARG=--onedir")

set "ICON_ARG="
if exist "%ICONNAME%" set "ICON_ARG=--icon %ICONNAME%"

set "DISTPATH=."

echo.
echo === 0) Environment ===
if "%PYLAUNCH%"=="1" (
    py %PY_ARGS% -c "import sys, platform; print('Python  :', sys.version.split()[0]); print('Bitness :', platform.architecture()[0]); print('Exe     :', sys.executable)"
) else (
    "%PY%" -c "import sys, platform; print('Python  :', sys.version.split()[0]); print('Bitness :', platform.architecture()[0]); print('Exe     :', sys.executable)"
)
if errorlevel 1 goto :fail

echo.
echo === 1) Kernel import check ===
if "%PYLAUNCH%"=="1" (
    py %PY_ARGS% -c "import importlib; m = importlib.import_module('catia_controller_v2'); print('module  :', m.__file__); print('version :', m.__version__)"
) else (
    "%PY%" -c "import importlib; m = importlib.import_module('catia_controller_v2'); print('module  :', m.__file__); print('version :', m.__version__)"
)
if errorlevel 1 (
    echo.
    echo [FAIL] Cannot import catia_controller_v2.
    echo        Make sure catia_controller_v2.py sits next to this script.
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
if "%PYLAUNCH%"=="1" (py %PY_ARGS% -m PyInstaller --version >nul 2>&1) else ("%PY%" -m PyInstaller --version >nul 2>&1)
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    if "%PYLAUNCH%"=="1" (py %PY_ARGS% -m pip install --upgrade pyinstaller) else ("%PY%" -m pip install --upgrade pyinstaller)
    if errorlevel 1 goto :fail
)
if "%PYLAUNCH%"=="1" (py %PY_ARGS% -m PyInstaller --version) else ("%PY%" -m PyInstaller --version)

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

set "PYI_COMMON=--noconfirm --clean %MODE_ARG% --windowed %ICON_ARG% --name CATIA_Prismatoid_Generator --collect-all pycatia --hidden-import catia_controller_v2 --hidden-import win32com.client --hidden-import pywintypes --hidden-import pythoncom --runtime-hook rthook_log.py --distpath "%DISTPATH%" --workpath "_build_output\build" --specpath "_build_output" main_v2.py"

if "%PYLAUNCH%"=="1" (
    py %PY_ARGS% -m PyInstaller %PYI_COMMON%
) else (
    "%PY%" -m PyInstaller %PYI_COMMON%
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
