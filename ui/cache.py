"""
Cached Data Loaders for Rubies Rangers Streamlit UI
Wraps API clients and analytical engines with @st.cache_data for instant responsiveness.
"""

from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import streamlit as st

from clients.fpl_client import FPLClient
from clients.tactical_client import TacticalClient
from analytics.optimizer import FPLOptimizer
from analytics.xp_model import XPModel, DEFAULT_SQUAD
from analytics.montecarlo import MonteCarloEngine
from trackers.league import LeagueTracker
from config_manager import get_params


@st.cache_data(ttl=1800)
def load_data(source: str = "Live FPL API", force_refresh: bool = False) -> pd.DataFrame:
    if source == "Historical CSV":
        df = pd.read_csv("fpl_player_statistics.csv")
        if "now_cost" in df.columns:
            df["now_cost"] = pd.to_numeric(df["now_cost"], errors="coerce")
        if "web_name" not in df.columns and "player_name" in df.columns:
            df["web_name"] = df["player_name"]
            df["full_name"] = df["player_name"]
        if "moneyball_score" not in df.columns:
            mb_params = get_params("moneyball")
            fwd_mid = mb_params.get("fwd_mid_weights", {})
            xgi_w = float(fwd_mid.get("xgi_per_90", 4.0))
            ict_div = float(fwd_mid.get("ict_index_divisor", 50.0))
            ppg_w = float(fwd_mid.get("ppg_weight", 1.2))
            xgi = df.get("expected_goal_involvements_per_90", 0).fillna(0)
            ict = df.get("ict_index", 0).fillna(0)
            ppg = df.get("points_per_game", 0).fillna(0)
            df["moneyball_score"] = (xgi * xgi_w) + (ict / ict_div) + (ppg * ppg_w)
        if "fdr_moneyball_score" not in df.columns:
            df["fdr_moneyball_score"] = df["moneyball_score"]
        if "forward_moneyball_score" not in df.columns:
            df["forward_moneyball_score"] = df["fdr_moneyball_score"]
        if "fdr_next_5" not in df.columns:
            df["fdr_next_5"] = 3.0
            df["next_fixture"] = "N/A"
        if "price_status" not in df.columns:
            df["price_status"] = "Stable"
            df["net_transfers"] = 0
            df["price_progress_pct"] = 0.0
        if "status" not in df.columns:
            df["status"] = "a"
        return df
    else:
        client = FPLClient()
        return client.get_players_df(force_refresh=force_refresh)


@st.cache_data(ttl=1800)
def load_fdr_map(n_gameweeks: int = 5, force_refresh: bool = False):
    client = FPLClient()
    return client.get_team_fdr_map(n_gameweeks=n_gameweeks)


@st.cache_data(ttl=1800)
def load_squad_trends(force_refresh: bool = False):
    client = FPLClient()
    return client.get_squad_trends(DEFAULT_SQUAD)


@st.cache_data(ttl=1800)
def load_player_trends(player_id: int, n_recent: int = 3, force_refresh: bool = False):
    client = FPLClient()
    return client.get_player_trends(player_id, n_recent=n_recent)


@st.cache_data(ttl=3600)
def load_squad_tactical(force_refresh: bool = False):
    tc = TacticalClient()
    return tc.get_squad_tactical_df(force_refresh=force_refresh)


@st.cache_data(ttl=3600)
def load_league_tactical(force_refresh: bool = False):
    tc = TacticalClient()
    return tc.get_league_tactical_df(force_refresh=force_refresh)


@st.cache_data(ttl=3600)
def load_player_shot_breakdown(understat_id: str):
    tc = TacticalClient()
    return tc.get_player_shot_breakdown(understat_id)


@st.cache_data(ttl=1800)
def load_xp_lineup(force_refresh: bool = False):
    xm = XPModel()
    return xm.optimize_lineup()


@st.cache_data(ttl=1800)
def load_xp_squad(force_refresh: bool = False):
    xm = XPModel()
    return xm.evaluate_squad_xp()


@st.cache_data(ttl=1800)
def load_gw4_odds(force_refresh: bool = False):
    xm = XPModel()
    return xm.get_gw4_odds_table()


@st.cache_data(ttl=1800)
def load_top_captains(top_n: int = 15, force_refresh: bool = False):
    xm = XPModel()
    return xm.get_top_captains(top_n=top_n)


@st.cache_data(ttl=600)
def load_league_standings(league_id: int):
    tracker = LeagueTracker()
    return tracker.get_league_standings(league_id)


@st.cache_data(ttl=600)
def load_team_leagues(entry_id: int):
    tracker = LeagueTracker()
    return tracker.get_team_leagues(entry_id)


@st.cache_data(ttl=600)
def load_team_picks(entry_id: int, gameweek: int = None):
    tracker = LeagueTracker()
    return tracker.get_team_picks(entry_id, gameweek=gameweek)


@st.cache_data(ttl=600)
def load_league_ownership(league_id: int, gameweek: int = None, max_teams: int = 20):
    tracker = LeagueTracker()
    return tracker.get_league_ownership(league_id, gameweek=gameweek, max_teams=max_teams)


@st.cache_data(ttl=600)
def load_league_history(league_id: int, max_teams: int = 20):
    tracker = LeagueTracker()
    return tracker.get_league_performance_history(league_id, max_teams=max_teams)


@st.cache_data(ttl=600, show_spinner=False)
def load_montecarlo_simulation(bank: float = 3.7,
                               num_transfers: int = 1,
                               free_transfers: int = 1,
                               n_sims: int = 2500,
                               pos_filter: str = "ALL",
                               sell_filter: str = None,
                               strict_filter: bool = True):
    mc = MonteCarloEngine()
    return mc.evaluate_transfers(
        bank=bank,
        num_transfers=num_transfers,
        free_transfers=free_transfers,
        n_sims=n_sims,
        position_filter=None if pos_filter == "ALL" else pos_filter,
        sell_player_filter=sell_filter,
        strict_injury_filter=strict_filter
    )


@st.cache_data(ttl=600, show_spinner=False)
def load_montecarlo_lineup(squad_names: tuple = None,
                           n_sims: int = 2500,
                           form_weight: float = 0.25,
                           include_disciplinary: bool = True,
                           force_refresh: bool = False):
    if squad_names is None:
        squad_names = tuple(DEFAULT_SQUAD)
    mc = MonteCarloEngine()
    return mc.optimize_lineup_and_substitutions(
        squad_names=list(squad_names),
        n_sims=n_sims,
        form_weight=form_weight,
        include_disciplinary=include_disciplinary
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_matchday_summary(entry_id: Optional[int] = None,
                          gameweek: Optional[int] = None,
                          squad_names: Optional[Tuple[str, ...]] = None,
                          force_refresh: bool = False):
    from analytics.matchday_hub import MatchdayHub
    hub = MatchdayHub()
    override = list(squad_names) if squad_names else None
    return hub.get_matchday_summary(
        entry_id=entry_id,
        gameweek=gameweek,
        active_squad_override=override,
        force_refresh=force_refresh
    )
