@echo off
chcp 65001 >nul 2>&1
cd /d %~dp0

echo ========================================
echo  CamKinescope - Autostart Setup
echo ========================================
echo.

REM Remove existing tasks
schtasks /delete /tn "CamKinescope_AutoStart" /f >nul 2>&1
schtasks /delete /tn "CamKinescope_ShutdownNotify" /f >nul 2>&1

REM Task 1: Auto-start on logon (30s delay for network)
echo Creating auto-start task...
schtasks /create /tn "CamKinescope_AutoStart" /sc onlogon /delay 0000:30 /tr "cmd /c cd /d \"%CD%\" && python src\main.py" /f
if errorlevel 1 (
    echo [ERROR] Failed to create auto-start task. Run as Administrator!
    pause
    exit /b 1
)
echo [OK] Auto-start task created.
echo.

REM Task 2: Shutdown notification via XML (event trigger)
echo Creating shutdown notification task...

set "XML_FILE=%TEMP%\camkinescope_shutdown.xml"

REM Write XML file line by line to avoid CMD escaping issues with & in XML entities
echo ^<?xml version="1.0"?^> > "%XML_FILE%"
echo ^<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"^> >> "%XML_FILE%"
echo   ^<Triggers^> >> "%XML_FILE%"
echo     ^<EventTrigger^> >> "%XML_FILE%"
echo       ^<Subscription^>^&lt;QueryList^&gt;^&lt;Query Id="0"^&gt;^&lt;Select Path="System"^&gt;*[System[Provider[@Name='User32'] and EventID=1074]]^&lt;/Select^&gt;^&lt;/Query^&gt;^&lt;/QueryList^&gt;^</Subscription^> >> "%XML_FILE%"
echo     ^</EventTrigger^> >> "%XML_FILE%"
echo   ^</Triggers^> >> "%XML_FILE%"
echo   ^<Actions Context="Author"^> >> "%XML_FILE%"
echo     ^<Exec^> >> "%XML_FILE%"
echo       ^<Command^>python^</Command^> >> "%XML_FILE%"
echo       ^<Arguments^>src\shutdown_notify.py^</Arguments^> >> "%XML_FILE%"
echo       ^<WorkingDirectory^>%CD%^</WorkingDirectory^> >> "%XML_FILE%"
echo     ^</Exec^> >> "%XML_FILE%"
echo   ^</Actions^> >> "%XML_FILE%"
echo   ^<Settings^> >> "%XML_FILE%"
echo     ^<ExecutionTimeLimit^>PT30S^</ExecutionTimeLimit^> >> "%XML_FILE%"
echo     ^<DisallowStartIfOnBatteries^>false^</DisallowStartIfOnBatteries^> >> "%XML_FILE%"
echo   ^</Settings^> >> "%XML_FILE%"
echo ^</Task^> >> "%XML_FILE%"

schtasks /create /tn "CamKinescope_ShutdownNotify" /xml "%XML_FILE%" /f
if errorlevel 1 (
    echo [ERROR] Failed to create shutdown task. Run as Administrator!
    del "%XML_FILE%" >nul 2>&1
    pause
    exit /b 1
)
del "%XML_FILE%" >nul 2>&1
echo [OK] Shutdown notification task created.
echo.

echo ========================================
echo  Setup complete!
echo  - CamKinescope auto-starts on logon (30s delay)
echo  - Shutdown notification sent to Telegram
echo ========================================
echo.
echo NOTE: For auto-recovery after power loss, enable
echo "Restore on AC Power Loss = Power On" in BIOS/UEFI.
echo.
pause
