@echo off
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)
echo Starting Rubies Rangers FPL REST API server on http://localhost:8000 ...
echo Interactive Swagger UI docs available at: http://localhost:8000/docs
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
pause
