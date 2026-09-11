#!/usr/bin/env bash
# ==============================================================================
# Rubies Rangers - Greenfield Environment Setup (macOS / Linux)
# ==============================================================================

set -e

echo "=============================================================================="
echo "  Rubies Rangers - Greenfield Environment Setup (macOS / Linux)"
echo "=============================================================================="
echo ""

# 1. Check Python
PYTHON_BIN=""
if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
else
    echo "[ERROR] Python was not found in your PATH."
    echo "Please install Python 3.10+ (via Homebrew, pyenv, or your package manager)."
    exit 1
fi

echo "[1/4] Found Python binary: $($PYTHON_BIN --version)"

# 2. Create virtual environment
if [ ! -d ".venv" ]; then
    echo "[2/4] Creating virtual environment in .venv..."
    $PYTHON_BIN -m venv .venv
else
    echo "[2/4] Existing .venv directory found."
fi

# 3. Activate virtual environment
echo "[3/4] Activating virtual environment..."
source .venv/bin/activate

# 4. Install dependencies
echo "[4/4] Upgrading pip and installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=============================================================================="
echo "  Setup Complete! Rubies Rangers is ready to use."
echo "=============================================================================="
echo ""
echo "Quickstart Commands:"
echo "  - Activate venv:      source .venv/bin/activate"
echo "  - Launch Web App:     streamlit run app.py"
echo "  - Launch REST API:    uvicorn api:app --host 0.0.0.0 --port 8000 --reload"
echo "  - Run Monte Carlo:    python team_manager.py transfers --mc"
echo ""
