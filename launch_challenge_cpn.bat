@echo off
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)
echo ======================================================================
echo  Rubies Rangers - Autonomous Challenge Coloured Petri Net (CPN) Runner
echo ======================================================================
echo.
echo Starting Autonomous Challenge CPN Pipeline with Saga Verification...
python automation/challenge_runner.py %*
pause
