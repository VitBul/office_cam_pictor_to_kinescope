@echo off
chcp 65001 >nul 2>&1
cd /d %~dp0

REM Launch CamKinescope with system tray icon (no console window)
start "" pythonw src\tray.py
