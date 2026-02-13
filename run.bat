@echo off
chcp 65001 >nul 2>&1
cd /d %~dp0

REM Launch CamKinescope minimized in background, this window closes immediately
start "CamKinescope" /min python src\main.py
