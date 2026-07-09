@echo off
:: ProspectLens — PyInstaller Packaging Script
::
:: Step 13: Activates virtual environment, installs packaging tools,
:: and runs PyInstaller to bundle the tray app and FastAPI backend into a single folder/executable.

cd /d "%~dp0"

echo [ProspectLens] Activating virtual environment...
call venv\Scripts\activate.bat

echo [ProspectLens] Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist ProspectLens.spec del /q ProspectLens.spec

echo [ProspectLens] Running PyInstaller...
pyinstaller --clean --noconfirm --onedir --windowed ^
    --name "ProspectLens" ^
    --collect-all google-genai ^
    --collect-all playwright ^
    --collect-all pystray ^
    --collect-all sqlmodel ^
    --collect-all uvicorn ^
    tray_app.py

echo [ProspectLens] Build complete! Executable is located at backend\dist\ProspectLens\ProspectLens.exe
pause
