@echo off
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)
echo Launching Rubies Rangers FPL Moneyball Dashboard on http://localhost:8501 ...
python -m streamlit run app.py
pause
