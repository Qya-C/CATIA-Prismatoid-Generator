@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem =====================================================================
rem  build.bat - package the plugin into a single double-clickable EXE
rem
rem  Requires: Python 3.11 (64-bit, same bitness as CATIA) + PyInstaller
rem
rem  Current mode: ONEFILE = 1  (single EXE, safe to copy anywhere)
rem
rem  Output: .\CATIA_Prismatoid_Generator.exe   (next to main.py)
rem
rem  Icon:
rem    Optional. Drop an app.ico next to this script and it is used
rem    automatically - no edit needed. Generate one with:
rem        python make_icon.py --placeholder
rem    If app.ico is absent, the build simply runs without a custom icon.
rem
rem  NOTE for ONEFILE builds:
rem    * Startup takes 5-10 seconds (contents are unpacked to %TEMP% each run)
rem    * Antivirus software may flag the EXE; whitelist it if needed
rem    * %TEMP% must be writable
rem =====================================================================

rem ---------- switches ----------
set "ONEFILE=1"
set "ICONNAME=app.ico"

rem ---------- interpreter ----------
set "PY=C:\Users\eraria\AppData\Local\Programs\Python\Python311\python.exe"
if exist "%PY%" goto :args
echo [WARN] Configured python.exe not found, falling back to "py -3".
set "PY=py -3"

:args
if "%ONEFILE%"=="1" (set "MODE_ARG=--onefile") else (set "MODE_ARG=--onedir")

rem Icon is used only if present; no warning when missing.
set "ICON_ARG="
if exist "%ICONNAME%" set "ICON_ARG=--icon %ICONNAME%"

rem Output goes right next to main.py.
set "DISTPATH=."

echo.
echo === 0) Environment ===
%PY% -c "import sys, platform; print('Python  :', sys.version.split()[0]); print('Bitness :', platform.architecture()[0]); print('Exe     :', sys.executable)"
if errorlevel 1 goto :fail

echo.
echo === 1) Kernel import check ===
%PY% -c "import importlib; m = importlib.import_module('catia_controller_v1'); print('module  :', m.__file__); print('version :', m.__version__)"
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
%PY% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    %PY% -m pip install --upgrade pyinstaller
    if errorlevel 1 goto :fail
)
%PY% -m PyInstaller --version

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
%PY% -m PyInstaller --noconfirm --clean %MODE_ARG% --windowed %ICON_ARG% ^
    --name CATIA_Prismatoid_Generator ^
    --collect-all pycatia ^
    --hidden-import catia_controller_v1 ^
    --hidden-import win32com.client ^
    --hidden-import pywintypes ^
    --hidden-import pythoncom ^
    --runtime-hook rthook_log.py ^
    --distpath "%DISTPATH%" ^
    --workpath "_build_output\build" ^
    --specpath "_build_output" ^
    main.py
if errorlevel 1 goto :fail

echo.
echo === 6) Done ===
if "%ONEFILE%"=="1" (
    if exist "CATIA_Prismatoid_Generator.exe" goto :ok_onefile
    echo [FAIL] Expected CATIA_Prismatoid_Generator.exe but it was not found.
    goto :fail
) else (
    if exist "CATIA_Prismatoid_Generator\CATIA_Prismatoid_Generator.exe" goto :ok_onedir
    echo [FAIL] Expected the onedir folder but it was not found.
    goto :fail
)

:ok_onefile
echo   Single EXE : %CD%\CATIA_Prismatoid_Generator.exe
for %%F in ("CATIA_Prismatoid_Generator.exe") do echo   Size       : %%~zF bytes
echo.
echo   This one file can be copied anywhere (desktop, USB stick, another PC).
echo.
echo Next steps:
echo   1. Start CATIA V5 and open a new Part document.
echo   2. Run the EXE. First launch takes 5-10 seconds - be patient.
echo   3. Generate a shape to confirm CATIA connectivity.
echo   4. If nothing appears, read launch_log.txt next to the EXE.
echo.
pause
exit /b 0

:ok_onedir
echo   EXE folder : %CD%\CATIA_Prismatoid_Generator
echo   EXE file   : %CD%\CATIA_Prismatoid_Generator\CATIA_Prismatoid_Generator.exe
echo.
echo   NOTE: keep the EXE together with its _internal folder.
echo.
pause
exit /b 0

:fail
echo.
echo [FAIL] See the messages above.
echo.
pause
exit /b 1