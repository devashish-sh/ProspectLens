@echo off
setlocal
echo =======================================================
echo   ProspectLens - Build and Update Installer Script
echo =======================================================
echo.

cd /d "%~dp0"

echo [1/3] Checking environment...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if not exist "%ISCC%" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if not exist "%ISCC%" (
    echo [ERROR] Inno Setup compiler (ISCC.exe) not found!
    echo Please make sure Inno Setup is installed.
    pause
    exit /b 1
)

echo [2/3] Building Standalone PyInstaller Binaries...
cd /d "%~dp0backend"
call "venv\Scripts\activate.bat"
pyinstaller ProspectLens.spec --noconfirm
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller compilation failed!
    pause
    exit /b 1
)

echo [3/3] Compiling Updated ProspectLens-Setup.exe...
cd /d "%~dp0installer"
"%ISCC%" ProspectLens.iss
if %errorlevel% neq 0 (
    echo [ERROR] Inno Setup compilation failed!
    pause
    exit /b 1
)

echo.
echo =======================================================
echo   SUCCESS! Updated ProspectLens-Setup.exe is ready in:
echo   %~dp0dist_installer\ProspectLens-Setup.exe
echo =======================================================
echo.
pause
