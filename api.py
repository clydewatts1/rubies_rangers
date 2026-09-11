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

from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from montecarlo_engine import MonteCarloEngine
from xp_model import XPModel, DEFAULT_SQUAD
from fpl_client import FPLClient
from league_tracker import LeagueTracker, DEFAULT_LEAGUE_ID

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
class TransferSimRequest(BaseModel):
    squad: Optional[List[str]] = Field(
        default=None,
        description="List of 15 squad player names (defaults to Rubies Rangers)"
    )
    bank: float = Field(default=3.7, ge=0.0, le=30.0, description="Available bank balance in £m")
    num_transfers: int = Field(default=1, ge=1, le=2, description="Number of transfers to evaluate (1 or 2)")
    free_transfers: int = Field(default=1, ge=1, le=5, description="Free transfers quota before -4 hit penalty")
    sims: int = Field(default=2500, ge=500, le=10000, description="Number of Monte Carlo simulations")
    position_filter: Optional[str] = Field(default=None, description="Filter transfers by position ('ALL', 'GKP', 'DEF', 'MID', 'FWD')")
    sell_player_filter: Optional[str] = Field(default=None, description="Focus sell moves on a specific player name (e.g. 'Senesi')")
    strict_injury_filter: bool = Field(default=True, description="Strictly purge unavailable (status 'u'), injured, and suspended players")


class LineupSimRequest(BaseModel):
    squad: Optional[List[str]] = Field(
        default=None,
        description="List of 15 squad player names (defaults to Rubies Rangers)"
    )
    sims: int = Field(default=2500, ge=500, le=10000, description="Number of Monte Carlo simulations")


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Rubies Rangers FPL Moneyball & Monte Carlo API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "default_squad": DEFAULT_SQUAD,
        "default_league_id": DEFAULT_LEAGUE_ID
    }


@app.post("/api/simulate/transfers")
def simulate_transfers(payload: TransferSimRequest):
    """
    Run Monte Carlo transfer optimization simulation across candidate transfers.
    Returns:
    - Baseline squad stochastic metrics
    - The 3 Best Strategic Transfer Archetypes (Max EV, Max Floor/Safety, Max Ceiling/Differential)
    - Full list of evaluated candidate transfers with net gains and win probabilities
    """
    squad = payload.squad or DEFAULT_SQUAD
    pos_filt = None if payload.position_filter in [None, "ALL"] else payload.position_filter

    res = mc_engine.evaluate_transfers(
        current_squad_names=squad,
        bank=payload.bank,
        num_transfers=payload.num_transfers,
        free_transfers=payload.free_transfers,
        n_sims=payload.sims,
        position_filter=pos_filt,
        sell_player_filter=payload.sell_player_filter,
        strict_injury_filter=payload.strict_injury_filter
    )

    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Simulation failed."))

    # Clean raw_totals numpy arrays from JSON response
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
    import numpy as np
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
    Solve optimal Starting XI, Captaincy, Vice-Captaincy, and bench auto-substitutions
    using Monte Carlo simulation.
    """
    squad = payload.squad or DEFAULT_SQUAD
    fpl_all = fpl_client.get_players_df()

    player_dicts = []
    for name in squad:
        m = fpl_all[fpl_all["web_name"].str.lower() == name.lower()]
        if m.empty:
            m = fpl_all[fpl_all["full_name"].str.lower() == name.lower()]
        if m.empty:
            m = fpl_all[fpl_all["web_name"].str.contains(name, case=False, na=False)]
        if not m.empty:
            player_dicts.append(m.iloc[0].to_dict())

    sim_cache = mc_engine.precompute_player_sims(player_dicts, is_current_squad=True, n_sims=payload.sims)
    totals, meta = mc_engine.simulate_squad_lineup(squad, sim_cache, n_sims=payload.sims)

    import numpy as np
    return {
        "success": True,
        "formation": meta["formation"],
        "captain": meta["captain"],
        "vice_captain": meta["vice_captain"],
        "starters": meta["starters"],
        "bench": meta["bench"],
        "simulated_metrics": {
            "mean_points": round(float(totals.mean()), 2),
            "floor_p10": round(float(np.percentile(totals, 10)), 1),
            "median_p50": round(float(np.median(totals)), 1),
            "ceiling_p90": round(float(np.percentile(totals, 90)), 1),
            "std_dev": round(float(totals.std()), 2)
        }
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
    import numpy as np
    clean_records = clean_df[avail_cols].replace({np.nan: None}).to_dict(orient="records")
    return {
        "total_active": len(clean_df),
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
