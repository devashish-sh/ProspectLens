@echo off
:: ProspectLens — Start Server and Tray Icon launcher
::
:: Step 12: Runs the pythonw.exe interpreter to spawn the Pystray tray application
:: silently in the background without leaving a dangling command prompt window.

cd /d "%~dp0"

set VENV_PYTHONW=backend\venv\Scripts\pythonw.exe

if not exist "%VENV_PYTHONW%" (
    echo [ProspectLens] Virtual environment pythonw.exe not found at %VENV_PYTHONW%.
    echo [ProspectLens] Attempting to start with default pythonw.exe in PATH...
    start /B pythonw backend\tray_app.py
) else (
    start /B %VENV_PYTHONW% backend\tray_app.py
)

echo [ProspectLens] Backend process launched. Look for the ProspectLens icon in your Windows system tray.
exit
