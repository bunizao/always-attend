@echo off
REM Always Attend - Windows launcher
REM Keeps all interactive logic inside the Python portal.

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYTHON_BIN="
for %%P in (python3.exe python.exe) do (
    where %%P >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_BIN=%%P"
        goto found_python
    )
)

echo Python 3.8+ is required. Install it from https://python.org/downloads/.
pause
exit /b 1

:found_python
echo Launching Always Attend portal...
"%PYTHON_BIN%" main.py %*
endlocal
