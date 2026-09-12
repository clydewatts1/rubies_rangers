@echo off
setlocal enabledelayedexpansion

echo ====================================================================
echo    Rubies Rangers FPL Moneyball -- Overnight Auto-Tuner
echo ====================================================================

:: Create logs folder
if not exist "logs" mkdir logs

:: Activate virtual environment if present
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call .venv\Scripts\activate.bat
)

:: Set log filename with date/time
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set dt=%%I
set TIMESTAMP=%dt:~0,8%_%dt:~8,6%
set LOGFILE=logs\tuner_overnight_%TIMESTAMP%.log

echo [INFO] Logging output to: %LOGFILE%
echo [INFO] Optuna Dashboard: http://localhost:8502
echo [INFO] Keeping system awake during execution...
echo.

:: Run through PowerShell wrapper to prevent Windows sleep and tee logs
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_overnight_tuner.ps1 -Trials 3000 -Jobs 4 -LogFile "%LOGFILE%"

echo.
echo ====================================================================
echo [DONE] Overnight run completed! Check %LOGFILE% for full audit log.
echo ====================================================================
pause
