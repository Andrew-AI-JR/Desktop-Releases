@echo off
REM Build script for creating Python executable on Windows

echo Building Python executable for Windows...

REM Create output directory
if not exist "resources\python-executables" mkdir resources\python-executables

REM Determine architecture
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    set PLATFORM_DIR=win-x64
) else (
    set PLATFORM_DIR=win-ia32
)

echo Building for platform: %PLATFORM_DIR%

REM Install PyInstaller if not already installed
python -m pip install pyinstaller

REM Install required dependencies first
python -m pip install -r src\resources\scripts\requirements.txt

REM Create platform-specific output directory
if not exist "resources\python-executables\%PLATFORM_DIR%" mkdir resources\python-executables\%PLATFORM_DIR%

REM Create executable using spec file for better dependency handling
python -m PyInstaller ^
    --distpath resources\python-executables\%PLATFORM_DIR% ^
    --workpath build\pyinstaller ^
    linkedin_commenter.spec

echo Build completed for %PLATFORM_DIR%
echo Executable location: resources\python-executables\%PLATFORM_DIR%\
