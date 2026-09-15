"""
Macro Match-State Jitter & Teammate Covariance Engine
Inspired by Numerical Weather Prediction (NWP) Ensemble Forecasting.

Perturbs macro atmospheric match conditions (pace/tempo) across fixtures
to resolve the Independent Teammate Fallacy, producing true joint probability
distributions, coupled clean sheets, and realistic portfolio tail risk.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from config_manager import get_params


@dataclass(frozen=True)
class FixtureMacroState:
    """
    Frozen contract representing joint macro match realization vectors across N simulations.
    All arrays have shape (n_sims,).
    """
    fixture_key: str
    home_team: str
    away_team: str
    pace_mult: np.ndarray        # Atmospheric pace jitter theta ~ LogNormal(-sigma^2/2, sigma)
    home_goals: np.ndarray       # Poisson goals scored by home club
    away_goals: np.ndarray       # Poisson goals scored by away club
    home_cs: np.ndarray          # Binary indicator (away_goals == 0)
    away_cs: np.ndarray          # Binary indicator (home_goals == 0)
    home_assists: Optional[np.ndarray] = None   # Coupled assists scored by home club
    away_assists: Optional[np.ndarray] = None   # Coupled assists scored by away club


def simulate_macro_fixtures(
    team_odds: Union[Dict[str, Dict[str, Any]], List[Dict[str, Any]]],
    n_sims: int = 5000,
    pace_sigma: Optional[float] = None,
    clip_min: Optional[float] = None,
    clip_max: Optional[float] = None,
    random_seed: Optional[int] = None,
    pace_volatility: Optional[float] = None,
    clip_pace_min: Optional[float] = None,
    clip_pace_max: Optional[float] = None,
    **kwargs: Any
) -> Dict[str, FixtureMacroState]:
    """
    Simulates macro match states for all distinct fixtures in a gameweek.
    
    Mathematical Formulation:
        theta_{m, k} ~ LogNormal(-sigma^2 / 2, sigma), E[theta] = 1.0
        G_{home, k} ~ Poisson(xG_{home} * theta_{m, k})
        G_{away, k} ~ Poisson(xG_{away} * theta_{m, k})
        CS_{home, k} = 1 if G_{away, k} == 0 else 0
        CS_{away, k} = 1 if G_{home, k} == 0 else 0
        
    Returns:
        Dict mapping fixture_key ("HOME_AWAY") -> FixtureMacroState
    """
    if random_seed is not None:
        np.random.seed(random_seed)

    # Load configuration fallbacks
    mc_cfg = get_params("monte_carlo") or {}
    mj_cfg = mc_cfg.get("macro_jitter", {})
    
    # Support both pace_sigma and pace_volatility alias
    eff_sigma = pace_sigma if pace_sigma is not None else pace_volatility
    sigma = float(eff_sigma) if eff_sigma is not None else float(mj_cfg.get("pace_volatility", 0.15))
    
    eff_cmin = clip_min if clip_min is not None else clip_pace_min
    c_min = float(eff_cmin) if eff_cmin is not None else float(mj_cfg.get("clip_pace_min", 0.50))
    
    eff_cmax = clip_max if clip_max is not None else clip_pace_max
    c_max = float(eff_cmax) if eff_cmax is not None else float(mj_cfg.get("clip_pace_max", 2.00))

    # Extract distinct home-away fixtures
    distinct_fixtures: Dict[str, Tuple[str, str, float, float]] = {}
    
    if isinstance(team_odds, list):
        for fix in team_odds:
            h_team = fix.get("team_h_short") or str(fix.get("team_h", "H"))
            a_team = fix.get("team_a_short") or str(fix.get("team_a", "A"))
            f_key = f"{h_team}_{a_team}"
            h_xg = float(fix.get("exp_goals_h", fix.get("home_xg", 1.35)))
            a_xg = float(fix.get("exp_goals_a", fix.get("away_xg", 1.35)))
            distinct_fixtures[f_key] = (h_team, a_team, h_xg, a_xg)
    elif isinstance(team_odds, dict):
        for t_code, info in team_odds.items():
            if info.get("is_home", True):
                h_team = t_code
                a_team = info.get("opponent", "UNK")
                f_key = f"{h_team}_{a_team}"
                if f_key not in distinct_fixtures:
                    h_xg = float(info.get("exp_goals_scored", 1.35))
                    a_xg = float(info.get("exp_goals_conceded", 1.35))
                    distinct_fixtures[f_key] = (h_team, a_team, h_xg, a_xg)

        # If no home fixtures identified, extract from any available opponents
        if not distinct_fixtures:
            seen_pairs = set()
            for t_code, info in team_odds.items():
                opp = info.get("opponent", "UNK")
                pair = tuple(sorted([t_code, opp]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    f_key = f"{t_code}_{opp}"
                    h_xg = float(info.get("exp_goals_scored", 1.35))
                    a_xg = float(info.get("exp_goals_conceded", 1.35))
                    distinct_fixtures[f_key] = (t_code, opp, h_xg, a_xg)

    fixture_states: Dict[str, FixtureMacroState] = {}

    for f_key, (h_team, a_team, h_xg, a_xg) in distinct_fixtures.items():
        # 1. Atmospheric Match Pace Multiplier
        # Mean-preserving LogNormal: E[X] = exp(mu + sigma^2/2). Setting mu = -sigma^2/2 ensures E[X] = 1.0.
        mu = -0.5 * (sigma ** 2)
        raw_pace = np.random.lognormal(mu, sigma, n_sims)
        pace_mult = np.clip(raw_pace, c_min, c_max)

        # 2. Joint Poisson Goals Scored & Conceded
        h_goals = np.random.poisson(h_xg * pace_mult)
        a_goals = np.random.poisson(a_xg * pace_mult)

        # 3. Clean Sheet Physical Binary Vectors
        h_cs = (a_goals == 0).astype(int)
        a_cs = (h_goals == 0).astype(int)

        # 4. Coupled Assists (approx 76% of goals are assisted)
        assist_coupling_rate = float(mc_cfg.get("assist_coupling_rate", 0.76))
        h_assists = np.random.binomial(h_goals, assist_coupling_rate)
        a_assists = np.random.binomial(a_goals, assist_coupling_rate)

        fixture_states[f_key] = FixtureMacroState(
            fixture_key=f_key,
            home_team=h_team,
            away_team=a_team,
            pace_mult=pace_mult,
            home_goals=h_goals,
            away_goals=a_goals,
            home_cs=h_cs,
            away_cs=a_cs,
            home_assists=h_assists,
            away_assists=a_assists
        )

    return fixture_states


def build_team_macro_lookup(
    fixture_states: Dict[str, FixtureMacroState]
) -> Dict[str, Dict[str, Any]]:
    """
    Indexes fixture macro states by club short code.
    
    For any club, returns:
    {
        "team_short": str,
        "opponent_short": str,
        "is_home": bool,
        "pace_mult": np.ndarray,
        "goals_scored": np.ndarray,
        "goals_conceded": np.ndarray,
        "clean_sheet": np.ndarray,
        "assists_scored": np.ndarray
    }
    """
    team_lookup: Dict[str, Dict[str, Any]] = {}

    for f_state in fixture_states.values():
        # Home team perspective
        team_lookup[f_state.home_team] = {
            "team_short": f_state.home_team,
            "opponent_short": f_state.away_team,
            "is_home": True,
            "pace_mult": f_state.pace_mult,
            "goals_scored": f_state.home_goals,
            "goals_conceded": f_state.away_goals,
            "clean_sheet": f_state.home_cs,
            "assists_scored": f_state.home_assists if f_state.home_assists is not None else np.zeros(len(f_state.home_goals))
        }
        # Away team perspective
        team_lookup[f_state.away_team] = {
            "team_short": f_state.away_team,
            "opponent_short": f_state.home_team,
            "is_home": False,
            "pace_mult": f_state.pace_mult,
            "goals_scored": f_state.away_goals,
            "goals_conceded": f_state.home_goals,
            "clean_sheet": f_state.away_cs,
            "assists_scored": f_state.away_assists if f_state.away_assists is not None else np.zeros(len(f_state.away_goals))
        }

    return team_lookup
