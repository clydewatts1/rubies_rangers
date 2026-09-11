@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo   Rubies Rangers - Greenfield Environment Setup
echo ==============================================================================
echo.

:: 1. Check Python installation
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found in your PATH!
    echo Please install Python 3.10 to 3.13 from https://www.python.org/downloads/
    echo IMPORTANT: Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [1/5] Checking Python version...
python --version
echo.

:: 2. Create virtual environment
if not exist ".venv" (
    echo [2/5] Creating Python virtual environment in .venv...
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
) else (
    echo [2/5] Existing virtual environment found in .venv.
)
echo.

:: 3. Activate virtual environment
echo [3/5] Activating virtual environment...
call .venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo.

:: 4. Upgrade pip
echo [4/5] Upgrading pip...
python -m pip install --upgrade pip
echo.

:: 5. Install requirements
echo [5/5] Installing all dependencies from requirements.txt...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ==============================================================================
echo   Setup Complete! Rubies Rangers is ready to use.
echo ==============================================================================
echo.
echo Quickstart Commands:
echo   - Activate venv manually:      .venv\Scripts\activate
echo   - Launch Web Dashboard:        launch_dashboard.bat  (or: streamlit run app.py)
echo   - Launch REST API:             launch_api.bat        (or: uvicorn api:app --port 8000)
echo   - Run Monte Carlo CLI:         python team_manager.py transfers --mc
echo.
pause
