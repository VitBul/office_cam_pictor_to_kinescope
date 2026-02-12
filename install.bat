@echo off
chcp 65001 >nul 2>&1
cd /d %~dp0

echo ========================================
echo  CamKinescope - Installation
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] FFmpeg is not found in PATH.
    echo FFmpeg is required for video processing.
    echo Please install FFmpeg from https://ffmpeg.org/
    echo.
)

echo Installing Python dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Installation complete!
echo ========================================
pause
