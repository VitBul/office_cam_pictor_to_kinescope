@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo  CamKinescope - Starting...
echo ========================================
echo.

cd /d %~dp0

python src/main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with an error.
)

pause
