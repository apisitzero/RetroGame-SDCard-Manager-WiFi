@echo off
setlocal EnableDelayedExpansion
title "Antigravity Auto-Allow & Turbo Mode Manager"

set "SCRIPT_DIR=%~dp0"
set "PY_SCRIPT=%SCRIPT_DIR%.agents\skills\auto-allow\scripts\apply_config.py"
if not exist "%PY_SCRIPT%" set "PY_SCRIPT=%USERPROFILE%\.gemini\config\skills\auto-allow\scripts\apply_config.py"
set "PS_CLICKER=%SCRIPT_DIR%.agents\skills\auto-allow\scripts\auto_clicker.ps1"
if not exist "%PS_CLICKER%" set "PS_CLICKER=%USERPROFILE%\.gemini\config\skills\auto-allow\scripts\auto_clicker.ps1"

if "%~1"=="--apply" goto do_apply_cli
if "%~1"=="--watch" goto do_watch_cli
if "%~1"=="--restore" goto do_restore_cli

:menu
cls
echo ===============================================================================
echo        ANTIGRAVITY AUTO-ALLOW AND TURBO EXECUTION MANAGER (Windows)
echo                 Auto-Permission System: YES ALLOW THIS TIME
echo ===============================================================================
echo.
echo  [1] Apply Turbo Mode and Wildcards (Auto-allow all commands and files)
echo  [2] Start Background Auto-Clicker  (Daemon to auto-click Allow buttons)
echo  [3] Apply All and Start Daemon     (Run both config and clicker)
echo  [4] Restore Original Settings      (Restore original config backup)
echo  [5] Exit
echo.
echo ===============================================================================
set /p choice="Select option [1-5]: "

if "%choice%"=="1" goto do_apply_interactive
if "%choice%"=="2" goto do_watch_interactive
if "%choice%"=="3" goto do_all_interactive
if "%choice%"=="4" goto do_restore_interactive
if "%choice%"=="5" goto do_exit
goto menu

:do_apply_cli
python "%PY_SCRIPT%"
exit /b %ERRORLEVEL%

:do_watch_cli
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_CLICKER%"
exit /b %ERRORLEVEL%

:do_restore_cli
python "%PY_SCRIPT%" --restore
exit /b %ERRORLEVEL%

:do_apply_interactive
cls
echo [INFO] Applying Auto-Allow Turbo Configuration...
echo.
python "%PY_SCRIPT%"
echo.
echo [SUCCESS] Auto-Allow enabled! No more 'Yes, allow this time' prompts.
echo.
pause
goto menu

:do_watch_interactive
cls
echo [INFO] Starting Background Auto-Clicker Daemon...
echo Press Ctrl+C in this window to stop.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_CLICKER%"
pause
goto menu

:do_all_interactive
cls
echo [INFO] Step 1: Applying Turbo Configuration...
python "%PY_SCRIPT%"
echo.
echo [INFO] Step 2: Starting Background Auto-Clicker...
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_CLICKER%"
pause
goto menu

:do_restore_interactive
cls
echo [INFO] Restoring original configuration from backup...
python "%PY_SCRIPT%" --restore
echo.
pause
goto menu

:do_exit
exit /b 0
