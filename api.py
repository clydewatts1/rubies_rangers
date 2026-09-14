"""
Rubies Rangers FPL REST API
FastAPI microservice providing endpoints for Monte Carlo simulations, transfer optimization,
lineup solvers, and betting market analytics.
Run with: uvicorn api:app --reload --port 8000
Interactive docs at: http://localhost:8000/docs
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Starlette 1.0.0 compatibility patch for FastAPI
import starlette.routing
_orig_init = starlette.routing.Router.__init__
def _patched_init(self, *args, **kwargs):
    kwargs.pop("on_startup", None)
    kwargs.pop("on_shutdown", None)
    return _orig_init(self, *args, **kwargs)
starlette.routing.Router.__init__ = _patched_init

import numpy as np
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from analytics.montecarlo import MonteCarloEngine
from analytics.xp_model import XPModel, DEFAULT_SQUAD
from clients.fpl_client import FPLClient
from trackers.league import LeagueTracker, DEFAULT_LEAGUE_ID
from config_manager import get_system_config, get_params, get_active_profile, set_active_profile

# Initialize FastAPI app
app = FastAPI(
    title="Rubies Rangers — FPL Moneyball & Monte Carlo API",
    description="Stochastic simulations, transfer optimization, betting odds, and rival spy endpoints for Fantasy Premier League.",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared engine instances
mc_engine = MonteCarloEngine()
xp_model = XPModel()
fpl_client = FPLClient()
league_tracker = LeagueTracker()


# -------------------------------------------------------------
# Request & Response Models
# -------------------------------------------------------------
_default_bank = float(get_system_config("default_bank") or 3.7)
_default_sims = int(get_params("monte_carlo").get("api_default_sims", 2500))
_default_form_weight = float(get_params("monte_carlo").get("default_form_weight", 0.25))

class TransferSimRequest(BaseModel):
    squad: Optional[List[str]] = Field(
        default=None,
        description="List of 15 squad player names (defaults to Rubies Rangers)"
    )
    bank: float = Field(default=_default_bank, ge=0.0, le=30.0, description="Available bank balance in £m")
    num_transfers: int = Field(default=1, ge=1, le=2, description="Number of transfers to evaluate (1 or 2)")
    free_transfers: int = Field(default=1, ge=1, le=5, description="Free transfers quota before -4 hit penalty")
    sims: int = Field(default=_default_sims, ge=500, le=10000, description="Number of Monte Carlo simulations")
    position_filter: Optional[str] = Field(default=None, description="Filter transfers by position ('ALL', 'GKP', 'DEF', 'MID', 'FWD')")
    sell_player_filter: Optional[str] = Field(default=None, description="Focus sell moves on a specific player name (e.g. 'Senesi')")
    strict_injury_filter: bool = Field(default=True, description="Strictly purge unavailable (status 'u'), injured, and suspended players")


class LineupSimRequest(BaseModel):
    squad: Optional[List[str]] = Field(
        default=None,
        description="List of 15 squad player names (defaults to Rubies Rangers)"
    )
    sims: int = Field(default=_default_sims, ge=500, le=10000, description="Number of Monte Carlo simulations")
    form_weight: float = Field(default=_default_form_weight, ge=0.0, le=2.0, description="Form sensitivity weight")
    include_disciplinary: bool = Field(default=True, description="Include yellow and in-match red card risks")


class AuthLoginRequest(BaseModel):
    email: str = Field(..., description="Official FPL account email")
    password: str = Field(..., description="Official FPL account password")


class BrowserSyncRequest(BaseModel):
    cookie: str = Field(..., description="Raw cookie string or pl_profile token extracted from Chrome/Edge")


_default_dry_run = bool(get_system_config("dry_run") if get_system_config("dry_run") is not None else True)

class CPNExecutionRequest(BaseModel):
    gameweek: Optional[int] = Field(default=None, description="Target Gameweek (defaults to current/next GW)")
    live: bool = Field(default=True, description="Connect to live official Premier League API (False for synthetic demo)")
    dry_run: bool = Field(default=_default_dry_run, description="Dry-run safety mode (simulates POST without mutating account)")
    entry_id: Optional[int] = Field(default=None, description="Manager Team Entry ID (defaults to config.yaml)")
    auth_cookie: Optional[str] = Field(default=None, description="access_token or pl_profile session cookie for authenticated execution")
    deadline_mins: int = Field(default=5, ge=1, le=120, description="Lead time in minutes to target deadline")


class CPNDaemonStartRequest(BaseModel):
    live: bool = Field(default=True, description="Connect to live official Premier League API (False for synthetic demo)")
    dry_run: bool = Field(default=_default_dry_run, description="Dry-run safety mode (simulates POST without mutating account)")
    check_interval_seconds: int = Field(default=60, ge=10, le=3600, description="Interval in seconds between deadline status checks")
    preflight_lead_minutes: int = Field(default=35, ge=5, le=120, description="Lead time in minutes prior to deadline when execution initiates")
    entry_id: Optional[int] = Field(default=None, description="Manager Team Entry ID (defaults to config.yaml)")


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@app.get("/")
def root():
    from automation.cpn.daemon import get_cpn_daemon
    daemon_status = get_cpn_daemon().get_status()
    return {
        "status": "online",
        "service": "Rubies Rangers FPL Moneyball & Monte Carlo API",
        "active_profile": get_active_profile(),
        "cpn_daemon_active": daemon_status["is_running"],
        "cpn_daemon_indicator": daemon_status["indicator"],
        "endpoints": [
            "/api/auth/status",
            "/api/auth/login",
            "/api/auth/sync_browser",
            "/api/auth/refresh",
            "/api/simulate/transfers",
            "/api/simulate/lineup",
            "/api/players/clean",
            "/api/odds",
            "/api/league/standings",
            "/api/league/history",
            "/api/config",
            "/api/cpn/run",
            "/api/cpn/telemetry",
            "/api/cpn/daemon/start",
            "/api/cpn/daemon/status",
            "/api/cpn/daemon/stop"
        ],
        "docs": "/docs"
    }


@app.get("/api/config")
def get_api_config():
    """Inspect current configuration settings and active parameter profile."""
    return {
        "active_profile": get_active_profile(),
        "system": get_system_config(),
        "parameters": get_params()
    }


@app.post("/api/config/profile")
def set_api_profile(profile: str = Query(..., description="Profile name ('heuristic' or 'tuned')")):
    """Switch active configuration profile dynamically."""
    try:
        set_active_profile(profile)
        return {"success": True, "active_profile": get_active_profile()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.post("/api/simulate/transfers")
def simulate_transfers(payload: TransferSimRequest):
    """
    Run stochastic Monte Carlo simulations to find the Top 3 Transfer Archetypes:
    1. Max Expected Value (Moneyball Core)
    2. Max Floor & Safety (Guaranteed starters, zero blank risk)
    3. Max Ceiling & Differential (Highest 90th percentile upside)
    """
    res = mc_engine.evaluate_transfers(
        current_squad_names=payload.squad,
        bank=payload.bank,
        num_transfers=payload.num_transfers,
        free_transfers=payload.free_transfers,
        n_sims=payload.sims,
        position_filter=None if payload.position_filter == "ALL" else payload.position_filter,
        sell_player_filter=payload.sell_player_filter,
        strict_injury_filter=payload.strict_injury_filter
    )

    base = dict(res["baseline"])
    if "raw_totals" in base:
        del base["raw_totals"]

    clean_top_3 = []
    for opt in res["top_3"]:
        opt_dict = dict(opt)
        if "raw_totals" in opt_dict:
            del opt_dict["raw_totals"]
        clean_top_3.append(opt_dict)

    df_all = res["all_results_df"].copy()
    if "raw_totals" in df_all.columns:
        df_all = df_all.drop(columns=["raw_totals"])

    # Clean NaNs for JSON compliance
    clean_candidates = df_all.head(50).replace({np.nan: None}).to_dict(orient="records")

    return {
        "success": True,
        "parameters": {
            "num_transfers": payload.num_transfers,
            "free_transfers": payload.free_transfers,
            "hit_penalty": res["hit_penalty"],
            "sims": payload.sims,
            "bank": payload.bank
        },
        "baseline": base,
        "top_3": clean_top_3,
        "total_evaluated": len(df_all),
        "candidates": clean_candidates
    }


@app.post("/api/simulate/lineup")
def simulate_lineup(payload: LineupSimRequest):
    """
    Solve optimal Starting XI formation, Captaincy duel, bench substitution strategy,
    and actionable 'Move Around' checklist using Monte Carlo stochastic simulation.
    """
    squad = payload.squad or DEFAULT_SQUAD

    res = mc_engine.optimize_lineup_and_substitutions(
        squad_names=squad,
        n_sims=payload.sims,
        form_weight=payload.form_weight,
        include_disciplinary=payload.include_disciplinary
    )

    return {
        "success": True,
        "optimal_formation": res["optimal_formation"],
        "formation_evaluations": res["formation_evaluations"],
        "starters": res["starters"],
        "bench": res["bench"],
        "captaincy_duel": res["captaincy_duel"],
        "move_around_checklist": res["move_around_checklist"],
        "disciplinary_and_injury_alerts": res["disciplinary_and_injury_alerts"],
        "squad_summary": res["squad_summary"]
    }


@app.get("/api/players/clean")
def get_clean_players(min_minutes: int = Query(default=15, ge=0, description="Minimum minutes played")):
    """
    Retrieve active Premier League players strictly purged of:
    - Transferred / Unavailable (status == 'u')
    - Injured (status == 'i')
    - Suspended (status == 's')
    - 0% chance of playing
    """
    clean_df = mc_engine.get_clean_player_pool(min_minutes=min_minutes)
    cols = [
        "id", "web_name", "full_name", "position_name", "club_short", "now_cost",
        "status", "chance_of_playing", "minutes", "fdr_moneyball_score",
        "expected_goals_per_90", "expected_assists_per_90", "fdr_next_5"
    ]
    avail_cols = [c for c in cols if c in clean_df.columns]
    clean_records = clean_df[avail_cols].replace({np.nan: None}).to_dict(orient="records")
    return {
        "total_active": len(clean_df),
        "count": len(clean_df),
        "players": clean_records
    }



@app.get("/api/odds")
def get_match_odds():
    """
    Retrieve bookmaker implied goal totals and Poisson clean sheet probabilities
    for all 20 Premier League clubs.
    """
    odds_df = xp_model.get_gw4_odds_table()
    return {
        "gameweek": 4,
        "fixtures": odds_df.to_dict(orient="records")
    }


@app.get("/api/league/standings")
def get_league_standings(league_id: int = Query(default=DEFAULT_LEAGUE_ID, description="FPL Classic Mini-League ID")):
    """
    Retrieve live mini-league standings with gameweek scores, total points, and rank movement.
    Defaults to Bronze, Silver & Gold League (ID: 325320).
    """
    data = league_tracker.get_league_standings(league_id)
    if "error" in data:
        raise HTTPException(status_code=400, detail=data["error"])
    return data


@app.get("/api/league/history")
def get_league_history(league_id: int = Query(default=DEFAULT_LEAGUE_ID, description="FPL Classic Mini-League ID")):
    """
    Retrieve gameweek-by-gameweek progression, cumulative points, and active chips
    for all rival teams in the mini-league.
    """
    data = league_tracker.get_league_performance_history(league_id)
    if "error" in data:
        raise HTTPException(status_code=400, detail=data["error"])
    return data


@app.post("/api/cpn/run")
async def run_cpn_automation(req: CPNExecutionRequest = CPNExecutionRequest()):
    """
    Trigger the Autonomous Coloured Petri Net (CPN) Execution Pipeline & Robotic Manager.
    Supports synthetic demo mode, live read dry-run, or live mutating execution.
    """
    from automation.runner import LiveFPLClient, LiveSolverEngine, DemoFPLClient, DemoSolverEngine
    from automation.cpn import CPNEngine, CPNDiagnosticJournal
    from datetime import datetime, timezone, timedelta

    resolved_entry_id = req.entry_id or get_system_config("default_entry_id") or 6173410
    legal_formations = {(3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3), (5, 3, 2), (5, 4, 1)}

    if req.live:
        client: Any = LiveFPLClient(entry_id=resolved_entry_id, auth_cookie=req.auth_cookie, dry_run=req.dry_run)
        solver: Any = LiveSolverEngine()
        target_gw = req.gameweek or fpl_client.get_current_gameweek() or 5
        mode_label = "Live FPL API (Dry Run)" if req.dry_run else "Live FPL API (Live Commit)"
    else:
        client = DemoFPLClient(entry_id=resolved_entry_id)
        solver = DemoSolverEngine()
        target_gw = req.gameweek or 1
        mode_label = "Synthetic Demo"

    journal = CPNDiagnosticJournal(log_dir="logs/diagnostics")
    engine = CPNEngine(fpl_client=client, solver_engine=solver, legal_formations=legal_formations, journal=journal)

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(minutes=req.deadline_mins)

    t0 = datetime.now(timezone.utc)
    await engine.run_gameweek_cycle(gameweek=target_gw, deadline_utc=deadline)
    duration_s = (datetime.now(timezone.utc) - t0).total_seconds()

    snapshot = engine.get_telemetry_snapshot()

    receipt_dict = None
    if not engine.marking.P_Committed.empty():
        receipt = await engine.marking.P_Committed.get()
        receipt_dict = {
            "confirmation_id": receipt.confirmation_id,
            "payload_hash": receipt.payload_hash,
            "http_status": receipt.http_status,
            "timestamp": receipt.timestamp.isoformat(),
        }

    alert_dict = None
    if not engine.marking.P_DeadLetter.empty():
        alert = await engine.marking.P_DeadLetter.get()
        alert_dict = {
            "severity": alert.severity,
            "reason": alert.reason,
            "context": alert.context,
            "timestamp": alert.timestamp.isoformat(),
        }

    await engine.shutdown()

    return {
        "success": receipt_dict is not None,
        "mode": mode_label,
        "gameweek": target_gw,
        "entry_id": resolved_entry_id,
        "duration_seconds": round(duration_s, 2),
        "committed_receipt": receipt_dict,
        "dead_letter_alert": alert_dict,
        "place_counts": snapshot["place_counts"],
        "executed_at_utc": now.isoformat(),
    }


@app.get("/api/cpn/telemetry")
def get_cpn_telemetry():
    """Retrieve CPN architectural specifications, place capacities, and transition formulas."""
    from automation.cpn.engine import PLACE_SPECS, TRANSITION_SPECS
    return {
        "architecture": "Kurt Jensen Timed Coloured Petri Net (TCPN)",
        "places": PLACE_SPECS,
        "transitions": TRANSITION_SPECS,
    }


@app.post("/api/cpn/daemon/start")
async def start_cpn_daemon(req: CPNDaemonStartRequest = CPNDaemonStartRequest()):
    """
    Start the autonomous 24/7 background daemon.
    Continuously monitors FPL deadlines, sleeps between matches, and autonomously triggers
    preflight and execution cycles when entering the deadline window.
    """
    from automation.cpn.daemon import get_cpn_daemon
    daemon = get_cpn_daemon()
    res = await daemon.start(
        live=req.live,
        dry_run=req.dry_run,
        check_interval_seconds=req.check_interval_seconds,
        preflight_lead_minutes=req.preflight_lead_minutes,
        entry_id=req.entry_id
    )
    return res


@app.post("/api/cpn/daemon/stop")
async def stop_cpn_daemon():
    """Stop the autonomous 24/7 background daemon."""
    from automation.cpn.daemon import get_cpn_daemon
    daemon = get_cpn_daemon()
    res = await daemon.stop()
    return res


@app.get("/api/cpn/daemon/status")
def get_cpn_daemon_status():
    """
    Inspect real-time telemetry, running state, next deadline countdown, and execution history
    for the autonomous CPN background daemon.
    """
    from automation.cpn.daemon import get_cpn_daemon
    daemon = get_cpn_daemon()
    return daemon.get_status()


# -------------------------------------------------------------
# Authentication & Browser Session Synchronization Endpoints
# -------------------------------------------------------------
@app.get("/api/auth/status")
def get_auth_status():
    """
    Returns current FPL authentication status, manager entry ID, name, bank, and Free Transfers.
    """
    from clients.auth_manager import AuthManager
    auth_mgr = AuthManager()
    return auth_mgr.get_status_summary()


@app.post("/api/auth/login")
def auth_login(req: AuthLoginRequest):
    """
    Direct headless authentication against the official Premier League Identity API.
    Retrieves and caches live pl_profile access token.
    """
    from clients.auth_manager import AuthManager
    auth_mgr = AuthManager()
    session = auth_mgr.authenticate_with_credentials(req.email, req.password)
    if not session.is_authenticated:
        raise HTTPException(status_code=401, detail=session.error_message or "Authentication failed.")
    return session.to_dict()


@app.post("/api/auth/sync_browser")
def auth_sync_browser(req: BrowserSyncRequest):
    """
    Ingests live session cookies pushed from Chrome / Edge 1-click bookmarklet or UI paste.
    Auto-resolves manager identity and updates active session.
    """
    from clients.auth_manager import AuthManager
    auth_mgr = AuthManager()
    session = auth_mgr.sync_browser_cookie(req.cookie, source="BROWSER_SYNC")
    if not session.is_authenticated:
        raise HTTPException(status_code=400, detail=session.error_message or "Invalid or expired cookie string.")
    return session.to_dict()


@app.post("/api/auth/refresh")
def auth_refresh():
    """
    Forces immediate re-verification and refresh of the active FPL session.
    """
    from clients.auth_manager import AuthManager
    auth_mgr = AuthManager()
    session = auth_mgr.refresh_session()
    return session.to_dict()



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
