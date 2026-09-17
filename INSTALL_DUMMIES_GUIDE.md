# 📖 Rubies Rangers — The Non-Pythonist's Installation & Running Guide

Welcome to **Rubies Rangers**! ⚽

If you have general technical knowledge (e.g. you know how to open a command prompt, browse files, and copy-paste commands) but are **not a Python developer**, this guide is for you. Follow these instructions step-by-step and you will have the platform running in under 5 minutes.

---

## ⚡ The 2-Minute Quickstart (Automated)

If you are on Windows and just want to get it running with minimum effort:

1. **Download / Clone this repository** to a folder on your computer (e.g., `C:\Projects\rubies_rangers`).
2. **Double-click** on [`setup_environment.bat`](setup_environment.bat).
   - A black command window will pop up. It will automatically check Python, create an isolated environment, and install all required libraries.
   - Wait until you see: `Setup Complete! Rubies Rangers is ready to use.`
3. **Double-click** on [`launch_dashboard.bat`](launch_dashboard.bat).
   - Your web browser will automatically open to **`http://localhost:8501`** showing the Rubies Rangers Trading Desk!

*(If you are on Mac/Linux or want to understand what's happening step-by-step, continue below).*

---

## 📋 Step 0: Prerequisites (What You Need Before Starting)

You only need two programs installed on your computer:

### 1. Python (Version 3.10, 3.11, 3.12, or 3.13)
- Download from the official website: [python.org/downloads](https://www.python.org/downloads/)
- ⚠️ **CRITICAL STEP DURING INSTALLATION**:
  - On the very first screen of the Python installer, you **MUST** check the box that says:
    > ☑️ **"Add Python to PATH"** (or "Add python.exe to PATH")
  - If you forget this checkbox, your computer won't recognize `python` commands.

### 2. Git (Optional, but Recommended)
- Download from: [git-scm.com](https://git-scm.com/downloads)
- This lets you download the project and receive future updates with one command.

---

## 🛠️ Step 1: Get the Code

Open your terminal or command prompt:
- **Windows**: Press `Win + R`, type `cmd` or `powershell`, and press `Enter`.
- **Mac**: Press `Cmd + Space`, type `Terminal`, and press `Enter`.

Navigate to where you want the project stored, then run:

```bash
git clone https://github.com/clydewatts1/rubies_rangers.git
cd rubies_rangers
```

*(If you don't use Git, you can click the green **"Code"** button on GitHub, select **"Download ZIP"**, and extract it into a folder).*

---

## 📦 Step 2: Create a Safe Sandbox (Virtual Environment)

> 💡 **What is a "Virtual Environment"?**  
> Think of a virtual environment (named `.venv`) as a self-contained sandbox or mini-container inside this folder. Any tools or libraries installed here won't touch or mess up other programs on your computer.

In your terminal, make sure you are inside the `rubies_rangers` directory, then run:

### On Windows:
```powershell
python -m venv .venv
```

### On Mac / Linux:
```bash
python3 -m venv .venv
```

*(This creates a hidden folder named `.venv` in your project folder).*

---

## 🔌 Step 3: Turn on the Sandbox (Activate the Environment)

Before running the software, you must "step inside" the sandbox.

### On Windows (PowerShell):
```powershell
.venv\Scripts\Activate.ps1
```
*(If you get a red error about "Execution Policies", see [Troubleshooting Gotcha #1](#1-powershell-error-execution-of-scripts-is-disabled) below).*

### On Windows (Command Prompt `cmd.exe`):
```cmd
.venv\Scripts\activate.bat
```

### On Mac / Linux:
```bash
source .venv/bin/activate
```

🎉 **How you know it worked**:  
Your command prompt line will now have `(.venv)` displayed at the very beginning of the prompt:
```text
(.venv) C:\Users\YourName\rubies_rangers>
```

---

## 📥 Step 4: Install the Required Libraries

Now install the mathematical engines, web dashboard, and data clients with a single command:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This will download and install libraries like `streamlit` (the web dashboard), `pandas` and `numpy` (data analysis), `scipy` and `pulp` (math optimization), and `plotly` (charts). This takes about 1 to 2 minutes.

---

## 🚀 Step 5: Run Rubies Rangers!

You have three ways to run the platform depending on what you want to do:

### 🌟 Mode 1: The Interactive Web Trading Desk (Recommended)
This launches the full financial-style dashboard in your browser.

With your environment activated, run:
```bash
streamlit run app.py
```
*(Or on Windows, simply double-click [`launch_dashboard.bat`](launch_dashboard.bat)).*

- Your web browser will open to: **`http://localhost:8501`**
- You will see the **4 Trading Desks**:
  1. 💼 **Portfolio & Asset Management Desk**: Live squad value, bank cash, free transfer value, and player cards.
  2. ⚔️ **Quantitative Solvers Desk**: 1-click Monte Carlo optimization, chip strategies, and Markowitz portfolio transfer suggestions.
  3. 🤖 **Autonomous Operations (CPN) Desk**: Timed autonomous manager, transaction logs, and auto-execution.
  4. 🛰️ **Alpha Signals & Matchday Hub**: Weather radar, Understat shot maps, fixture difficulty swings, and rival spy.

---

### 💻 Mode 2: Quick Command-Line Simulator
If you just want to run an instant Monte Carlo transfer calculation in your terminal without opening a browser:

```bash
python team_manager.py transfers --mc --sims 1000
```
This runs 1,000 parallel gameweek scenarios and displays the optimal transfer strategy directly in your terminal with expected points (xP) and percentiles ($P_{10}, P_{50}, P_{90}$).

---

### 🔌 Mode 3: The REST API (For Developers / Integrations)
If you want to query the platform as a backend microservice:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```
*(Or double-click [`launch_api.bat`](launch_api.bat)).*

- Open your browser to: **`http://localhost:8000/docs`** for interactive Swagger API testing.

---

## ⚙️ Step 6: Customizing for Your Own FPL Team

By default, Rubies Rangers runs with sample data or offline cached data so you can test immediately. 

To link it to your own official FPL team:
1. Open the file **`config.yaml`** in any text editor (Notepad, VS Code, etc.).
2. Look for the `fpl:` section near the top:
   ```yaml
   fpl:
     team_id: 1234567          # <-- Replace with your FPL team ID (from the FPL website URL)
     email: "your_email"       # <-- Optional: only needed if you want 1-click transfer execution
     password: "your_password" # <-- Optional
   ```
3. Save the file. The web dashboard will automatically reload your team's live data!

---

## 🛑 How to Stop the Program

When you are done using the dashboard or API:
1. Go to the terminal / command prompt window where it is running.
2. Press **`Ctrl + C`** on your keyboard.
3. The server will cleanly shut down.
4. To exit the virtual environment, type:
   ```bash
   deactivate
   ```

---

## 🔧 "I'm Stuck!" — Troubleshooting Common Gotchas

### 1. PowerShell Error: *"Execution of scripts is disabled on this system"*
- **Symptom**: When running `.venv\Scripts\Activate.ps1`, you get a red security error.
- **Why it happens**: Windows blocks third-party PowerShell scripts by default.
- **Fix**: Run this one-line command in PowerShell, press `Y` (Yes), and try activating again:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```

### 2. Error: *"'python' is not recognized as an internal or external command"*
- **Symptom**: Typing `python` gives a "not recognized" or "command not found" error.
- **Why it happens**: Python was installed without checking the "Add to PATH" box.
- **Fix**: 
  1. Re-run the Python installer.
  2. Choose **"Modify"**.
  3. Ensure **"Add Python to environment variables"** is checked.
  4. Close and re-open your terminal window.

### 3. Error: *"Address already in use"* or *"Port 8501 is in use"*
- **Symptom**: Streamlit says another program is already using port 8501.
- **Fix**: Simply specify a different port when starting:
  ```bash
  streamlit run app.py --server.port 8502
  ```
  Then visit `http://localhost:8502` in your browser.

### 4. How Do I Update When New Code Is Released?
Whenever updates are pushed to the project, update your installation with:
```bash
# 1. Pull newest changes
git pull

# 2. Activate sandbox
.venv\Scripts\activate     # (or source .venv/bin/activate on Mac)

# 3. Update any new libraries
pip install -r requirements.txt
```

---

## 📚 Where to Go Next

- **Interactive Dashboard**: Run `launch_dashboard.bat` and explore the 4 Trading Desks.
- **Deep Quantitative Strategy**: Read [The Quant Manager's Manifesto](docs/fantasy_football_as_a_hedge_fund_manager.md).
- **Engineering Architecture**: Read [The Spec-Driven Agentic Lifecycle & CPN Engine](docs/spec_driven_agentic_lifecycle.md).
- **Check Issue / Roadmap Status**: Run `python scripts/issue_status.py` in your terminal for instant project telemetry!
