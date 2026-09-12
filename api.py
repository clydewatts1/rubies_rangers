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


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Rubies Rangers FPL Moneyball & Monte Carlo API",
        "active_profile": get_active_profile(),
        "endpoints": [
            "/api/simulate/transfers",
            "/api/simulate/lineup",
            "/api/players/clean",
            "/api/odds",
            "/api/league/standings",
            "/api/league/history",
            "/api/config"
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
