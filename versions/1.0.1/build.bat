@echo off
rem =====================================================================
rem  build.bat - one-click package (double-click this file)
rem
rem  It does two things:
rem    1) calls build_once.bat to do the actual PyInstaller build
rem       (the old script built twice: the onefile build produces the EXE
rem        and then the single-file archive, and step 2 re-ran the whole
rem        analysis, wasting about 90 seconds)
rem    2) runs a launch smoke test on the produced EXE
rem
rem  Package only, no smoke test: run build_once.bat instead.
rem
rem  Output: .\CATIA_Prismatoid_Generator.exe   (single file, portable)
rem
rem  NOTE: this file is intentionally pure ASCII (see README.md,
rem        "Why the .bat files are pure ASCII").
rem =====================================================================
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============ 1/2  BUILD ============
call "%~dp0build_once.bat"
if errorlevel 1 (
    echo.
    echo [FAIL] Build did not finish, skipping the smoke test.
    pause >nul
    exit /b 1
)

if not exist "CATIA_Prismatoid_Generator.exe" (
    echo.
    echo [FAIL] CATIA_Prismatoid_Generator.exe was not produced.
    pause >nul
    exit /b 1
)

echo.
echo ============ 2/2  LAUNCH SMOKE TEST ============
echo   Only checks "starts up and does not crash". About 12 seconds.
echo   The plugin window will open and is closed automatically.
echo.

rem Remove the previous log so we only read THIS run's output.
if exist "launch_log.txt" del /q "launch_log.txt"

start "" "CATIA_Prismatoid_Generator.exe"

rem Wait ~12s. Deliberately NOT using timeout: when stdin is redirected
rem (scheduled task, some CI, or "build.bat < nul") timeout errors out and
rem hangs the script. ping provides the delay and never touches stdin.
ping -n 13 127.0.0.1 >nul

rem PyInstaller onefile spawns a bootloader; the window belongs to it, so
rem clean up by image name rather than by a PID we never captured.
taskkill /f /im CATIA_Prismatoid_Generator.exe >nul 2>&1

rem IMPORTANT: rthook_log.py writes its banner on EVERY startup, including a
rem healthy one, so the mere existence of launch_log.txt does NOT mean a
rem crash. Only a real traceback counts.
set "CRASHED="
if not exist "launch_log.txt" goto :smoke_report
findstr /c:"Traceback (most recent call last)" "launch_log.txt" >nul 2>&1
if not errorlevel 1 set "CRASHED=1"
findstr /c:"Error" "launch_log.txt" >nul 2>&1
if not errorlevel 1 set "CRASHED=1"

:smoke_report
if defined CRASHED (
    echo [WARN] Startup raised an exception. launch_log.txt:
    echo ---------------------------------------------------------------
    type "launch_log.txt"
    echo ---------------------------------------------------------------
    echo Please send the content above.
    pause >nul
    exit /b 1
)

echo   [OK] Started cleanly, no exception in launch_log.txt.
echo.
echo Output: %CD%\CATIA_Prismatoid_Generator.exe
echo.
echo Now verify by hand (a script cannot do this part):
echo   1. Start CATIA V5 and open a new Part document
echo   2. Run the EXE, confirm the main window size and buttons
echo   3. Generate a shape and check the geometry in CATIA
echo.
pause
exit /b 0
