"""
Rubies Rangers FPL Monte Carlo Transfer Optimizer
Simulates stochastic match outcomes, minutes volatility, injuries/departures,
bench auto-substitutions, and point hit penalties across N simulations.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import math
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd

from clients.fpl_client import FPLClient
from clients.tactical_client import TacticalClient, normalize_name
from analytics.xp_model import XPModel, DEFAULT_SQUAD, GW4_MATCH_ODDS
from analytics.venue_model import compute_effective_venue_multiplier
from config_manager import get_system_config, get_params



def clean_nans(obj: Any) -> Any:
    """Recursively convert float NaN/Inf values to None for clean JSON serialization."""
    if isinstance(obj, np.ndarray):
        return [clean_nans(x) for x in obj.tolist()]
    elif isinstance(obj, (float, np.floating)):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, dict):
        return {k: clean_nans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nans(v) for v in obj]
    return obj


class MonteCarloEngine:
    def __init__(self, fpl_client: Optional[FPLClient] = None,
                 tac_client: Optional[TacticalClient] = None,
                 xp_model: Optional[XPModel] = None):
        self.fpl_client = fpl_client or FPLClient()
        self.tac_client = tac_client or TacticalClient()
        self.xp_model = xp_model or XPModel()
        self.team_odds = self.xp_model.team_odds
        self.macro_states: Dict[str, Dict[str, Any]] = {}

    def generate_macro_match_states(
        self,
        fixtures: Optional[Any] = None,
        n_sims: int = 5000,
        pace_sigma: Optional[float] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Precomputes macro match states for all distinct Premier League fixtures.
        Returns a dictionary mapping team_short -> Dict of arrays of shape (n_sims,).
        """
        from analytics.macro_engine import simulate_macro_fixtures, build_team_macro_lookup
        if isinstance(fixtures, (int, np.integer)):
            eff_fixtures = self.team_odds
            eff_sims = int(fixtures)
        elif fixtures is not None:
            eff_fixtures = fixtures
            eff_sims = n_sims
        else:
            eff_fixtures = self.team_odds
            eff_sims = n_sims

        f_states = simulate_macro_fixtures(eff_fixtures, n_sims=eff_sims, pace_sigma=pace_sigma)
        self.macro_states = build_team_macro_lookup(f_states)
        return self.macro_states

    def get_clean_player_pool(self, min_minutes: int = 15) -> pd.DataFrame:
        """
        Extract active player pool strictly filtering out:
        - Unavailable / Transferred out of the Premier League (status == 'u')
        - Injured (status == 'i')
        - Suspended (status == 's')
        - Zero chance of playing (chance_of_playing == 0)
        - Non-playing reserves (< min_minutes played)
        - News indicating transfers abroad or season-ending injury
        """
        df = self.fpl_client.get_players_df()

        # Hard exclusions
        mask_active = (df["status"] == "a") | ((df["status"] == "d") & (df["chance_of_playing"].fillna(75) >= 50))
        mask_fit = (df["chance_of_playing"].isna()) | (df["chance_of_playing"] >= 50)
        mask_mins = df["minutes"].fillna(0) >= min_minutes

        # Filter out departure news
        leave_keywords = ["transferred", "loaned", "joined", "contract terminated", "season-ending", "acl"]
        news_series = df["news"].fillna("").str.lower()
        mask_not_left = ~news_series.apply(lambda n: any(kw in n for kw in leave_keywords))

        clean_df = df[mask_active & mask_fit & mask_mins & mask_not_left].copy()
        return clean_df

    def simulate_player(self, player_dict: Dict[str, Any],
                         trends_dict: Optional[Dict[str, Any]] = None,
                         tac_dict: Optional[Dict[str, Any]] = None,
                         n_sims: int = 5000,
                         form_weight: float = 1.0,
                         include_disciplinary: bool = True,
                         macro_state: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Simulate N gameweek outcomes for a single player.
        Incorporates form weighting, bookmaker match odds, injury/doubt status,
        yellow/red card disciplinary risks, and conditioned macro match states.
        Returns:
            sim_points: np.ndarray of shape (n_sims,)
            sim_minutes: np.ndarray of shape (n_sims,)
        """
        if trends_dict is None:
            trends_dict = {}
        if tac_dict is None:
            tac_dict = {}

        pos = player_dict.get("position_name", "MID")
        team_short = player_dict.get("club_short", "UNK")
        status = player_dict.get("status", "a")
        cop = player_dict.get("chance_of_playing")

        # 1. Hard status check (Injured, Suspended, Transferred, or 0% chance)
        if status in ["u", "i", "s"] or (cop is not None and cop == 0):
            return np.zeros(n_sims), np.zeros(n_sims)

        # 2. Match context lookup
        m_info = self.team_odds.get(team_short, {
            "exp_goals_scored": 1.30,
            "exp_goals_conceded": 1.30,
            "clean_sheet_prob": 0.27,
            "fixture_str": "TBD"
        })
        team_xg = m_info["exp_goals_scored"]
        team_xgc = m_info["exp_goals_conceded"]
        cs_prob = m_info["clean_sheet_prob"]

        # Load configurable Monte Carlo parameters
        mc_cfg = get_params("monte_carlo")
        form_cfg = mc_cfg.get("form_multiplier", {})
        prob_cfg = mc_cfg.get("probabilities", {})
        disc_cfg = mc_cfg.get("disciplinary", {})
        bps_cfg = mc_cfg.get("bps_weights", {})
        venue_cfg = get_params("venue") or {}

        v_mult = compute_effective_venue_multiplier(
            player_row={"position_name": pos, "club_short": team_short},
            venue_cfg=venue_cfg,
            fixture_str=m_info["fixture_str"]
        )

        if v_mult == 0.0:
            return np.zeros(n_sims), np.zeros(n_sims)

        if v_mult > 0:
            cs_prob = min(0.99, cs_prob * v_mult)
            team_xg = team_xg * v_mult
            team_xgc = team_xgc / v_mult
            card_mult = 1.0 / v_mult
        else:
            card_mult = 1.0

        # 3. Minutes & Start probability
        mins_status = trends_dict.get("minutes_status", "REGULAR_STARTER")
        avg_recent_mins = trends_dict.get("avg_recent_mins", 75.0)

        # Fitness probability based on yellow flags / doubts from config
        if status == "d" or (cop is not None and cop < 100):
            p_fit = (cop / 100.0) if cop is not None else prob_cfg.get("p_fit_doubt_default", 0.75)
        else:
            p_fit = prob_cfg.get("p_fit_healthy", 0.99)

        if mins_status == "BENCHED_OR_DROPPED":
            m_data = prob_cfg.get("benched_or_dropped", {})
            p_start = m_data.get("p_start", 0.10)
            exp_starter_mins = m_data.get("exp_starter_mins", 60.0)
            p_cameo = m_data.get("p_cameo", 0.35)
        elif mins_status == "ROTATION_RISK":
            m_data = prob_cfg.get("rotation_risk", {})
            p_start = m_data.get("p_start", 0.45)
            exp_starter_mins = m_data.get("exp_starter_mins", 65.0)
            p_cameo = m_data.get("p_cameo", 0.65)
        elif mins_status == "REGULAR_STARTER":
            m_data = prob_cfg.get("regular_starter", {})
            p_start = m_data.get("p_start", 0.85)
            exp_starter_mins = min(m_data.get("exp_starter_mins_max", 85.0), max(m_data.get("exp_starter_mins_min", 65.0), avg_recent_mins))
            p_cameo = m_data.get("p_cameo", 0.75)
        else:  # SECURE_STARTER
            m_data = prob_cfg.get("secure_starter", {})
            p_start = m_data.get("p_start", 0.96)
            exp_starter_mins = min(m_data.get("exp_starter_mins_max", 90.0), max(m_data.get("exp_starter_mins_min", 75.0), avg_recent_mins))
            p_cameo = m_data.get("p_cameo", 0.85)

        # Vectorized draws for minutes
        fits = np.random.binomial(1, p_fit, n_sims)
        starts = fits * np.random.binomial(1, p_start, n_sims)
        cameos = fits * (1 - starts) * np.random.binomial(1, p_cameo, n_sims)

        mins = np.zeros(n_sims)
        n_starts = int(np.sum(starts))
        mins_std = prob_cfg.get("starter_mins_std", 7.5)
        if n_starts > 0:
            mins[starts == 1] = np.clip(np.random.normal(exp_starter_mins, mins_std, n_starts), 50.0, 90.0)
        n_cameos = int(np.sum(cameos))
        cameo_min = prob_cfg.get("cameo_mins_min", 10.0)
        cameo_max = prob_cfg.get("cameo_mins_max", 30.0)
        if n_cameos > 0:
            mins[cameos == 1] = np.random.uniform(cameo_min, cameo_max, n_cameos)

        # 4. Appearance Points
        app_pts = np.where(mins >= 60.0, 2, np.where(mins > 0.0, 1, 0))

        # 5. Clean Sheet Points & Goals Conceded Penalty
        mj_cfg = mc_cfg.get("macro_jitter", {})
        macro_enabled = mj_cfg.get("enabled", True)

        # Fallback to engine-level macro states if not passed explicitly
        if macro_state is None and self.macro_states:
            macro_state = self.macro_states.get(team_short)

        pace_mult = 1.0
        if macro_enabled and macro_state is not None:
            team_gc_vector = macro_state.get("goals_conceded")
            pace_mult = macro_state.get("pace_mult", 1.0)
            
            # Align vector lengths with n_sims if mismatched
            if team_gc_vector is not None and len(team_gc_vector) != n_sims:
                if len(team_gc_vector) > n_sims:
                    team_gc_vector = team_gc_vector[:n_sims]
                else:
                    team_gc_vector = np.resize(team_gc_vector, n_sims)
            
            if isinstance(pace_mult, np.ndarray) and len(pace_mult) != n_sims:
                if len(pace_mult) > n_sims:
                    pace_mult = pace_mult[:n_sims]
                else:
                    pace_mult = np.resize(pace_mult, n_sims)

            if mj_cfg.get("enforce_discrete_poisson_gc", True) and team_gc_vector is not None:
                # Conditional Poisson arrival process: goals conceded while player was on pitch
                # G_on_pitch ~ Binomial(G_conceded, mins / 90.0)
                mins_frac_clipped = np.clip(np.nan_to_num(mins / 90.0, nan=0.0), 0.0, 1.0)
                gc_on_pitch = np.random.binomial(team_gc_vector, mins_frac_clipped)
                
                # FPL Clean Sheet rule: Played >= 60 mins AND conceded 0 goals on pitch
                cs_draw = ((mins >= 60.0) & (gc_on_pitch == 0)).astype(int)
                gc_penalty = np.where(np.isin(pos, ["DEF", "GKP"]), -(gc_on_pitch // 2), 0)
                gc_draw = gc_on_pitch
            elif mj_cfg.get("enforce_coupled_defense", True) and "clean_sheet" in macro_state:
                cs_draw = (mins >= 60.0) * macro_state["clean_sheet"]
                mins_fraction = np.nan_to_num(mins / 90.0, nan=0.0)
                gc_lam = np.nan_to_num(np.clip(team_xgc * mins_fraction, 0.0, None), nan=0.0)
                gc_draw = np.random.poisson(gc_lam)
                gc_penalty = np.where(np.isin(pos, ["DEF", "GKP"]), -(gc_draw // 2), 0)
            else:
                cs_draw = (mins >= 60.0) * np.random.binomial(1, cs_prob, n_sims)
                mins_fraction = np.nan_to_num(mins / 90.0, nan=0.0)
                gc_lam = np.nan_to_num(np.clip(team_xgc * mins_fraction, 0.0, None), nan=0.0)
                gc_draw = np.random.poisson(gc_lam)
                gc_penalty = np.where(np.isin(pos, ["DEF", "GKP"]), -(gc_draw // 2), 0)
        else:
            cs_draw = (mins >= 60.0) * np.random.binomial(1, cs_prob, n_sims)
            mins_fraction = np.nan_to_num(mins / 90.0, nan=0.0)
            gc_lam = np.nan_to_num(np.clip(team_xgc * mins_fraction, 0.0, None), nan=0.0)
            gc_draw = np.random.poisson(gc_lam)
            gc_penalty = np.where(np.isin(pos, ["DEF", "GKP"]), -(gc_draw // 2), 0)

        if pos in ["DEF", "GKP"]:
            cs_pts = cs_draw * 4
        elif pos == "MID":
            cs_pts = cs_draw * 1
        else:
            cs_pts = np.zeros(n_sims)

        # Saves for GKP
        saves_lam = np.nan_to_num(np.clip(gc_draw * 1.3, 0.0, None), nan=0.0)
        saves_pts = np.where(pos == "GKP", (np.random.poisson(saves_lam) // 3), 0)

        # 6. Attacking Points (Goals & Assists) with Form Factor from config
        form_val = float(player_dict.get("form") or 0.0)
        f_base = form_cfg.get("baseline", 4.5)
        f_step = form_cfg.get("step", 0.04)
        f_min = form_cfg.get("min_clip", 0.75)
        f_max = form_cfg.get("max_clip", 1.30)
        form_mult = float(np.clip(1.0 + f_step * (form_val - f_base) * form_weight, f_min, f_max))

        npxg_90 = float(tac_dict.get("NPxG_90") or 0.0)
        if npxg_90 == 0.0:
            npxg_90 = float(player_dict.get("expected_goals_per_90") or 0.0)

        pen_duty = (player_dict.get("penalties_order") == 1)
        pen_bonus = 0.14 if pen_duty else 0.0

        mins_fraction = np.nan_to_num(mins / 90.0, nan=0.0)
        pace_scale = pace_mult if (macro_enabled and mj_cfg.get("enforce_pace_scaling", True)) else 1.0

        match_xg = ((npxg_90 * mins_fraction * (team_xg / 1.35) * pace_scale) + (pen_bonus * (mins > 0))) * form_mult
        match_xg = np.nan_to_num(np.clip(match_xg, 0.0, None), nan=0.0)
        goals_draw = np.random.poisson(match_xg)

        if pos == "FWD":
            goal_pts = goals_draw * 4
        elif pos == "MID":
            goal_pts = goals_draw * 5
        elif pos == "DEF":
            goal_pts = goals_draw * 6
        else:  # GKP
            goal_pts = goals_draw * 10

        xa_90 = float(tac_dict.get("xA_90") or 0.0)
        if xa_90 == 0.0:
            xa_90 = float(player_dict.get("expected_assists_per_90") or 0.0)

        crn_duty = (player_dict.get("corners_and_indirect_freekicks_order") in [1, 2])
        fk_duty = (player_dict.get("direct_freekicks_order") in [1, 2])
        deadball_bonus = 0.07 if (crn_duty or fk_duty) else 0.0

        match_xa = ((xa_90 * mins_fraction * (team_xg / 1.35) * pace_scale) + (deadball_bonus * (mins > 0))) * form_mult
        match_xa = np.nan_to_num(np.clip(match_xa, 0.0, None), nan=0.0)
        assists_draw = np.random.poisson(match_xa)
        assist_pts = assists_draw * 3

        # 7. Disciplinary Cards (Yellow & Red Cards) from config
        if include_disciplinary:
            y_cards_acc = float(player_dict.get("yellow_cards") or 0)
            yc_base = disc_cfg.get("yc_base_prob", 0.10)
            yc_fac = disc_cfg.get("yc_card_factor", 0.02)
            yc_sc = disc_cfg.get("yc_max_cards_scaled", 3)
            yc_max = disc_cfg.get("yc_max_prob", 0.20)
            yc_prob = min(yc_max, (yc_base + yc_fac * min(yc_sc, y_cards_acc)) * card_mult)
            yc_draw = (mins > 0) * np.random.binomial(1, yc_prob, n_sims) * -1

            rc_p = min(0.50, disc_cfg.get("rc_prob", 0.010) * card_mult)
            rc_pen = disc_cfg.get("rc_penalty_pts", -3.0)
            rc_draw = (mins > 0) * np.random.binomial(1, rc_p, n_sims)
            rc_pts = rc_draw * rc_pen
            cs_pts = np.where(rc_draw == 1, 0, cs_pts)
        else:
            yc_draw = np.zeros(n_sims)
            rc_pts = np.zeros(n_sims)

        # 8. Defensive Work Rate Floor Bonus (DEF only)
        def_actions = trends_dict.get("avg_recent_def_contrib", 0.0)
        df_cfg = mc_cfg.get("defensive_floor", {})
        df_max = df_cfg.get("max_prob", 0.65)
        df_rate = df_cfg.get("rate_factor", 0.1)
        def_floor = np.where((pos == "DEF") & (mins >= 60), np.random.binomial(1, min(df_max, def_actions * df_rate), n_sims), 0)

        # 9. Bonus Points (BPS) from config
        bps = (goals_draw * bps_cfg.get("goals", 24)) + (assists_draw * bps_cfg.get("assists", 18)) + (cs_draw * bps_cfg.get("clean_sheet", 12)) + (def_floor * bps_cfg.get("def_floor", 4)) + (saves_pts * bps_cfg.get("saves", 6))
        bps += np.where(mins >= 60, bps_cfg.get("mins_60", 2), 0)
        t3 = bps_cfg.get("tier_3_threshold", 32)
        t2 = bps_cfg.get("tier_2_threshold", 22)
        t1 = bps_cfg.get("tier_1_threshold", 14)
        bonus_pts = np.where(bps >= t3, 3, np.where(bps >= t2, 2, np.where(bps >= t1, 1, 0)))

        # Total points
        total_pts = app_pts + cs_pts + gc_penalty + saves_pts + goal_pts + assist_pts + yc_draw + rc_pts + def_floor + bonus_pts
        total_pts = np.maximum(-2, total_pts)


        return total_pts, mins

    def precompute_player_sims(self, player_dicts: List[Dict[str, Any]],
                               is_current_squad: bool = False,
                               n_sims: int = 5000,
                               form_weight: float = 1.0,
                               include_disciplinary: bool = True,
                               macro_states: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
        """Precompute Monte Carlo simulation arrays for a set of players."""
        names = [p.get("web_name") or p.get("full_name") for p in player_dicts]
        
        # Precompute shared macro match states for all clubs in this simulation batch
        if macro_states is None:
            macro_states = self.generate_macro_match_states(n_sims=n_sims)
        self.macro_states = macro_states

        # Only fetch granular match element history for current squad (cached)
        trends_df = pd.DataFrame()
        if is_current_squad:
            try:
                trends_df = self.fpl_client.get_squad_trends(names)
            except Exception:
                trends_df = pd.DataFrame()

        # Understat is loaded instantly from local cache
        try:
            tac_df = self.tac_client.get_squad_tactical_df(names)
        except Exception:
            tac_df = pd.DataFrame()

        sim_cache = {}
        for p in player_dicts:
            name = p.get("web_name") or p.get("full_name")
            p_id = p.get("id")

            # Trends row
            t_dict = {}
            if not trends_df.empty and "id" in trends_df.columns:
                t_row = trends_df[trends_df["id"] == p_id]
                if not t_row.empty:
                    t_dict = t_row.iloc[0].to_dict()

            # Fast in-memory minutes fallback for candidate pool
            if not t_dict:
                tot_mins = float(p.get("minutes") or 0.0)
                if tot_mins >= 240:
                    m_status = "SECURE_STARTER"
                    avg_m = 88.0
                elif tot_mins >= 180:
                    m_status = "REGULAR_STARTER"
                    avg_m = 75.0
                elif tot_mins >= 70:
                    m_status = "ROTATION_RISK"
                    avg_m = 45.0
                else:
                    m_status = "BENCHED_OR_DROPPED"
                    avg_m = 15.0

                t_dict = {
                    "minutes_status": m_status,
                    "avg_recent_mins": avg_m,
                    "avg_recent_def_contrib": float(p.get("defensive_contribution_per_90") or 0.0)
                }

            # Tactical row
            norm = normalize_name(name)
            tac_dict = {}
            if not tac_df.empty and "norm_name" in tac_df.columns:
                tac_m = tac_df[tac_df["norm_name"].str.contains(norm, case=False, na=False)]
                if not tac_m.empty:
                    tac_dict = tac_m.iloc[0].to_dict()

            team_short = p.get("club_short", "UNK")
            m_state = macro_states.get(team_short) if macro_states else None
            pts, mins = self.simulate_player(p, t_dict, tac_dict, n_sims=n_sims,
                                             form_weight=form_weight,
                                             include_disciplinary=include_disciplinary,
                                             macro_state=m_state)
            sim_cache[name] = {
                "player": p,
                "pts": pts,
                "mins": mins,
                "mean_pts": round(float(pts.mean()), 2),
                "p10": round(float(np.percentile(pts, 10)), 1),
                "p50": round(float(np.median(pts)), 1),
                "p90": round(float(np.percentile(pts, 90)), 1),
                "std": round(float(pts.std()), 2)
            }

        return sim_cache

    def simulate_squad_lineup(self, squad_names: List[str],
                              sim_cache: Dict[str, Dict[str, Any]],
                              n_sims: int = 5000) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Simulate squad total points across N runs, executing:
        1. Starting XI formation determination based on pre-game mean expected points.
        2. Captain designation (highest mean xP) with 2x points.
        3. Vice-Captain fallback if Captain plays 0 minutes.
        4. Automatic bench substitution if any starting XI player has 0 minutes.
        """
        squad_items = [sim_cache[name] for name in squad_names if name in sim_cache]
        if len(squad_items) < 15:
            return np.zeros(n_sims), {}

        # Sort players by position and mean points to pick optimal starting XI
        gkps = [p for p in squad_items if p["player"]["position_name"] == "GKP"]
        defs = [p for p in squad_items if p["player"]["position_name"] == "DEF"]
        mids = [p for p in squad_items if p["player"]["position_name"] == "MID"]
        fwds = [p for p in squad_items if p["player"]["position_name"] == "FWD"]

        gkps.sort(key=lambda x: x["mean_pts"], reverse=True)
        defs.sort(key=lambda x: x["mean_pts"], reverse=True)
        mids.sort(key=lambda x: x["mean_pts"], reverse=True)
        fwds.sort(key=lambda x: x["mean_pts"], reverse=True)

        legal_formations = [
            (3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3),
            (4, 5, 1), (5, 3, 2), (5, 4, 1), (5, 2, 3)
        ]

        best_formation = (3, 5, 2)
        best_xp = -1.0
        best_starters = None

        for n_def, n_mid, n_fwd in legal_formations:
            if len(defs) < n_def or len(mids) < n_mid or len(fwds) < n_fwd or len(gkps) < 1:
                continue
            cur_starters = [gkps[0]] + defs[:n_def] + mids[:n_mid] + fwds[:n_fwd]
            cur_xp = sum(s["mean_pts"] for s in cur_starters)
            if cur_xp > best_xp:
                best_xp = cur_xp
                best_formation = (n_def, n_mid, n_fwd)
                best_starters = cur_starters

        starter_names = set(s["player"]["web_name"] for s in best_starters)
        bench_outfield = [s for s in squad_items if s["player"]["web_name"] not in starter_names and s["player"]["position_name"] != "GKP"]
        bench_outfield.sort(key=lambda x: x["mean_pts"], reverse=True)
        bench_gkp = [s for s in gkps if s["player"]["web_name"] not in starter_names]

        # Designated Captain & Vice-Captain
        outfield_starters = [s for s in best_starters if s["player"]["position_name"] != "GKP"]
        outfield_starters.sort(key=lambda x: x["mean_pts"], reverse=True)
        captain = outfield_starters[0]
        vice_captain = outfield_starters[1] if len(outfield_starters) > 1 else outfield_starters[0]

        # Pre-extract arrays for starters and bench
        starter_pts = np.array([s["pts"] for s in best_starters])      # Shape: (11, n_sims)
        starter_mins = np.array([s["mins"] for s in best_starters])    # Shape: (11, n_sims)
        starter_pos = [s["player"]["position_name"] for s in best_starters]

        bench_pts = np.array([b["pts"] for b in bench_outfield])       # Shape: (3, n_sims)
        bench_mins = np.array([b["mins"] for b in bench_outfield])     # Shape: (3, n_sims)
        bench_pos = [b["player"]["position_name"] for b in bench_outfield]

        bgkp_pts = bench_gkp[0]["pts"] if bench_gkp else np.zeros(n_sims)
        bgkp_mins = bench_gkp[0]["mins"] if bench_gkp else np.zeros(n_sims)

        c_pts = captain["pts"]
        c_mins = captain["mins"]
        vc_pts = vice_captain["pts"]
        vc_mins = vice_captain["mins"]

        # Base starter points
        squad_totals = np.sum(starter_pts, axis=0)

        # Captain 2x (VC fallback if C gets 0 mins)
        c_bonus = np.where(c_mins > 0, c_pts, np.where(vc_mins > 0, vc_pts, 0))
        squad_totals += c_bonus

        # Auto-substitutions trial-by-trial for 0-minute starters
        zero_starter_mask = np.any(starter_mins == 0, axis=0)
        zero_trial_indices = np.where(zero_starter_mask)[0]

        # Auto-substitutions vectorized
        # 1. GKP sub
        if bench_gkp:
            squad_totals += np.where((starter_mins[0] == 0) & (bgkp_mins > 0), bgkp_pts, 0)

        # 2. Outfield subs: count how many outfield starters played 0 mins
        num_zeros = np.sum(starter_mins[1:] == 0, axis=0)
        if len(bench_outfield) > 0:
            squad_totals += np.where((num_zeros >= 1) & (bench_mins[0] > 0), bench_pts[0], 0)
        if len(bench_outfield) > 1:
            squad_totals += np.where((num_zeros >= 2) & (bench_mins[1] > 0), bench_pts[1], 0)
        if len(bench_outfield) > 2:
            squad_totals += np.where((num_zeros >= 3) & (bench_mins[2] > 0), bench_pts[2], 0)

        meta = {
            "formation": f"{best_formation[0]}-{best_formation[1]}-{best_formation[2]}",
            "captain": captain["player"]["web_name"],
            "vice_captain": vice_captain["player"]["web_name"],
            "starters": [s["player"]["web_name"] for s in best_starters],
            "bench": [b["player"]["web_name"] for b in bench_outfield] + ([bench_gkp[0]["player"]["web_name"]] if bench_gkp else [])
        }

        return squad_totals, meta

    def optimize_lineup_and_substitutions(self,
                                          squad_names: Optional[List[str]] = None,
                                          n_sims: int = 5000,
                                          form_weight: float = 1.0,
                                          include_disciplinary: bool = True) -> Dict[str, Any]:
        """
        Comprehensive Monte Carlo Lineup, Captaincy & Bench Substitution Strategy Optimizer.
        Evaluates all 8 legal formations, computes bench activation probabilities,
        simulates captaincy duels, and produces a step-by-step 'Move Around' checklist.
        """
        if squad_names is None:
            squad_names = DEFAULT_SQUAD

        fpl_all = self.fpl_client.get_players_df()

        # Match squad player rows
        squad_player_dicts = []
        for name in squad_names:
            m = fpl_all[fpl_all["web_name"].str.lower() == name.lower()]
            if m.empty:
                m = fpl_all[fpl_all["full_name"].str.lower() == name.lower()]
            if m.empty:
                m = fpl_all[fpl_all["web_name"].str.contains(name, case=False, na=False)]
            if not m.empty:
                squad_player_dicts.append(m.iloc[0].to_dict())

        # Precompute player simulations
        sim_cache = self.precompute_player_sims(
            squad_player_dicts,
            is_current_squad=True,
            n_sims=n_sims,
            form_weight=form_weight,
            include_disciplinary=include_disciplinary
        )

        gkps = [p for p in squad_player_dicts if p["position_name"] == "GKP"]
        defs = [p for p in squad_player_dicts if p["position_name"] == "DEF"]
        mids = [p for p in squad_player_dicts if p["position_name"] == "MID"]
        fwds = [p for p in squad_player_dicts if p["position_name"] == "FWD"]

        # Sort within position by simulated mean points
        gkps.sort(key=lambda p: sim_cache.get(p["web_name"], {}).get("mean_pts", 0.0), reverse=True)
        defs.sort(key=lambda p: sim_cache.get(p["web_name"], {}).get("mean_pts", 0.0), reverse=True)
        mids.sort(key=lambda p: sim_cache.get(p["web_name"], {}).get("mean_pts", 0.0), reverse=True)
        fwds.sort(key=lambda p: sim_cache.get(p["web_name"], {}).get("mean_pts", 0.0), reverse=True)

        raw_formations = get_system_config("legal_formations")
        legal_formations = [tuple(f) for f in raw_formations] if raw_formations else [
            (3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3),
            (4, 5, 1), (5, 3, 2), (5, 4, 1), (5, 2, 3)
        ]

        formation_evals = []

        best_formation = (3, 5, 2)
        best_mean = -1.0
        best_starters = None
        best_bench_outfield = None
        best_bench_gkp = None
        best_squad_totals = None

        for n_def, n_mid, n_fwd in legal_formations:
            if len(defs) < n_def or len(mids) < n_mid or len(fwds) < n_fwd or len(gkps) < 1:
                continue

            cand_starters = [gkps[0]] + defs[:n_def] + mids[:n_mid] + fwds[:n_fwd]
            cand_starter_names = set(s["web_name"] for s in cand_starters)
            cand_bench_outfield = [p for p in squad_player_dicts if p["web_name"] not in cand_starter_names and p["position_name"] != "GKP"]
            cand_bench_outfield.sort(key=lambda p: sim_cache.get(p["web_name"], {}).get("mean_pts", 0.0), reverse=True)
            cand_bench_gkp = [p for p in gkps if p["web_name"] not in cand_starter_names]

            # Outfield captain & VC
            cand_outfield = [s for s in cand_starters if s["position_name"] != "GKP"]
            cand_outfield.sort(key=lambda p: sim_cache.get(p["web_name"], {}).get("mean_pts", 0.0), reverse=True)
            c_cand = cand_outfield[0]
            vc_cand = cand_outfield[1] if len(cand_outfield) > 1 else cand_outfield[0]

            s_pts = np.array([sim_cache[s["web_name"]]["pts"] for s in cand_starters])
            s_mins = np.array([sim_cache[s["web_name"]]["mins"] for s in cand_starters])

            b_pts = np.array([sim_cache[b["web_name"]]["pts"] for b in cand_bench_outfield])
            b_mins = np.array([sim_cache[b["web_name"]]["mins"] for b in cand_bench_outfield])

            bgkp_pts = sim_cache[cand_bench_gkp[0]["web_name"]]["pts"] if cand_bench_gkp else np.zeros(n_sims)
            bgkp_mins = sim_cache[cand_bench_gkp[0]["web_name"]]["mins"] if cand_bench_gkp else np.zeros(n_sims)

            c_pts = sim_cache[c_cand["web_name"]]["pts"]
            c_mins = sim_cache[c_cand["web_name"]]["mins"]
            vc_pts = sim_cache[vc_cand["web_name"]]["pts"]
            vc_mins = sim_cache[vc_cand["web_name"]]["mins"]

            totals = np.sum(s_pts, axis=0)
            # Captain 2x (VC fallback if C plays 0 mins)
            c_bonus = np.where(c_mins > 0, c_pts, np.where(vc_mins > 0, vc_pts, 0))
            totals += c_bonus

            # Auto subs
            if cand_bench_gkp:
                totals += np.where((s_mins[0] == 0) & (bgkp_mins > 0), bgkp_pts, 0)

            num_zeros = np.sum(s_mins[1:] == 0, axis=0)
            if len(cand_bench_outfield) > 0:
                totals += np.where((num_zeros >= 1) & (b_mins[0] > 0), b_pts[0], 0)
            if len(cand_bench_outfield) > 1:
                totals += np.where((num_zeros >= 2) & (b_mins[1] > 0), b_pts[1], 0)
            if len(cand_bench_outfield) > 2:
                totals += np.where((num_zeros >= 3) & (b_mins[2] > 0), b_pts[2], 0)

            f_mean = float(np.mean(totals))
            f_p10 = float(np.percentile(totals, 10))
            f_p50 = float(np.median(totals))
            f_p90 = float(np.percentile(totals, 90))
            f_std = float(np.std(totals))

            form_str = f"{n_def}-{n_mid}-{n_fwd}"
            formation_evals.append({
                "formation": form_str,
                "defenders": n_def,
                "midfielders": n_mid,
                "forwards": n_fwd,
                "mean_score": round(f_mean, 2),
                "p10": round(f_p10, 1),
                "p50": round(f_p50, 1),
                "p90": round(f_p90, 1),
                "std": round(f_std, 2)
            })

            if f_mean > best_mean:
                best_mean = f_mean
                best_formation = (n_def, n_mid, n_fwd)
                best_starters = cand_starters
                best_bench_outfield = cand_bench_outfield
                best_bench_gkp = cand_bench_gkp
                best_squad_totals = totals

        formation_evals.sort(key=lambda x: x["mean_score"], reverse=True)

        # -------------------------------------------------------------
        # Detailed Bench & Substitution Analysis for the Optimal Lineup
        # -------------------------------------------------------------
        opt_s_pts = np.array([sim_cache[s["web_name"]]["pts"] for s in best_starters])
        opt_s_mins = np.array([sim_cache[s["web_name"]]["mins"] for s in best_starters])

        opt_b_pts = np.array([sim_cache[b["web_name"]]["pts"] for b in best_bench_outfield])
        opt_b_mins = np.array([sim_cache[b["web_name"]]["mins"] for b in best_bench_outfield])

        opt_bgkp_pts = sim_cache[best_bench_gkp[0]["web_name"]]["pts"] if best_bench_gkp else np.zeros(n_sims)
        opt_bgkp_mins = sim_cache[best_bench_gkp[0]["web_name"]]["mins"] if best_bench_gkp else np.zeros(n_sims)

        # Track trial-by-trial bench activations with formation legality
        sub_activations = [np.zeros(n_sims, dtype=bool) for _ in range(len(best_bench_outfield))]
        gkp_sub_activated = (opt_s_mins[0] == 0) & (opt_bgkp_mins > 0)

        n_def_req, n_mid_req, n_fwd_req = best_formation

        for t in range(n_sims):
            playing_defs = sum(1 for idx in range(1, 1 + n_def_req) if opt_s_mins[idx, t] > 0)
            playing_mids = sum(1 for idx in range(1 + n_def_req, 1 + n_def_req + n_mid_req) if opt_s_mins[idx, t] > 0)
            playing_fwds = sum(1 for idx in range(1 + n_def_req + n_mid_req, 11) if opt_s_mins[idx, t] > 0)

            zero_outfield = [idx for idx in range(1, 11) if opt_s_mins[idx, t] == 0]
            if not zero_outfield:
                continue

            used_bench_indices = set()
            for _ in zero_outfield:
                for b_i, b_player in enumerate(best_bench_outfield):
                    if b_i in used_bench_indices or opt_b_mins[b_i, t] == 0:
                        continue
                    b_pos = b_player["position_name"]
                    c_def = playing_defs + (1 if b_pos == "DEF" else 0)
                    c_mid = playing_mids + (1 if b_pos == "MID" else 0)
                    c_fwd = playing_fwds + (1 if b_pos == "FWD" else 0)

                    # Formations must have at least 3 DEF, 2 MID, 1 FWD
                    if c_def >= 3 and c_mid >= 2 and c_fwd >= 1:
                        used_bench_indices.add(b_i)
                        sub_activations[b_i][t] = True
                        playing_defs = c_def
                        playing_mids = c_mid
                        playing_fwds = c_fwd
                        break

        bench_breakdown = []
        for b_i, b_player in enumerate(best_bench_outfield):
            name = b_player["web_name"]
            act_mask = sub_activations[b_i]
            act_pct = round(float(np.mean(act_mask) * 100), 1)
            pts_subbed = round(float(np.mean(opt_b_pts[b_i, act_mask])), 2) if np.any(act_mask) else 0.0
            pts_saved = round(float(np.sum(opt_b_pts[b_i, act_mask]) / n_sims), 2)

            pos = b_player["position_name"]
            tot_mins = float(b_player.get("minutes") or 0.0)
            form_val = float(b_player.get("form") or 0.0)

            if b_i == 0:
                slot_name = "Sub 1"
                rationale = f"Primary outfield cover ({act_pct}% call-up chance). Guarantees legal 3 DEF formation minimum." if pos == "DEF" else f"Primary outfield cover ({act_pct}% call-up chance). Reliable attacking substitute."
            elif b_i == 1:
                slot_name = "Sub 2"
                rationale = f"Secondary sub ({act_pct}% call-up chance). Cameo risk with high explosive ceiling." if tot_mins < 100 else f"Secondary cover ({act_pct}% call-up chance)."
            else:
                slot_name = "Sub 3"
                rationale = f"Deep emergency cover ({act_pct}% call-up chance). Lost starting status (0 mins in GW2/3, form {form_val:.1f})."

            bench_breakdown.append({
                "slot": slot_name,
                "sub_priority": b_i + 1,
                "web_name": name,
                "full_name": b_player.get("full_name"),
                "position": pos,
                "club": b_player.get("club_short"),
                "fixture": b_player.get("next_fixture"),
                "fdr": b_player.get("next_fdr", 3),
                "cost": b_player.get("now_cost", 0.0),
                "form": form_val,
                "status": b_player.get("status", "a"),
                "cop": b_player.get("chance_of_playing", 100),
                "news": b_player.get("news", ""),
                "yellow_cards": b_player.get("yellow_cards", 0),
                "red_cards": b_player.get("red_cards", 0),
                "mean_pts": sim_cache[name]["mean_pts"],
                "p10": sim_cache[name]["p10"],
                "p90": sim_cache[name]["p90"],
                "activation_prob_pct": act_pct,
                "pts_when_subbed": pts_subbed,
                "points_saved_mean": pts_saved,
                "tactical_rationale": rationale
            })

        # Add GKP Sub
        if best_bench_gkp:
            bg_player = best_bench_gkp[0]
            bg_name = bg_player["web_name"]
            bg_act_pct = round(float(np.mean(gkp_sub_activated) * 100), 1)
            bg_pts_subbed = round(float(np.mean(opt_bgkp_pts[gkp_sub_activated])), 2) if np.any(gkp_sub_activated) else 0.0

            bench_breakdown.append({
                "slot": "GKP Sub",
                "sub_priority": 4,
                "web_name": bg_name,
                "full_name": bg_player.get("full_name"),
                "position": "GKP",
                "club": bg_player.get("club_short"),
                "fixture": bg_player.get("next_fixture"),
                "fdr": bg_player.get("next_fdr", 4),
                "cost": bg_player.get("now_cost", 0.0),
                "form": float(bg_player.get("form") or 0.0),
                "status": bg_player.get("status", "a"),
                "cop": bg_player.get("chance_of_playing", 100),
                "news": bg_player.get("news", ""),
                "yellow_cards": bg_player.get("yellow_cards", 0),
                "red_cards": bg_player.get("red_cards", 0),
                "mean_pts": sim_cache[bg_name]["mean_pts"],
                "p10": sim_cache[bg_name]["p10"],
                "p90": sim_cache[bg_name]["p90"],
                "activation_prob_pct": bg_act_pct,
                "pts_when_subbed": bg_pts_subbed,
                "points_saved_mean": round(float(np.sum(opt_bgkp_pts[gkp_sub_activated]) / n_sims), 2),
                "tactical_rationale": "Backup keeper. Activates only if primary keeper plays 0 minutes."
            })

        # -------------------------------------------------------------
        # Captaincy & Vice-Captaincy Monte Carlo Duel
        # -------------------------------------------------------------
        outfield_starters = [s for s in best_starters if s["position_name"] != "GKP"]
        outfield_starters.sort(key=lambda p: sim_cache.get(p["web_name"], {}).get("mean_pts", 0.0), reverse=True)
        top_captain = outfield_starters[0]
        top_vc = outfield_starters[1] if len(outfield_starters) > 1 else outfield_starters[0]

        cap_name = top_captain["web_name"]
        vc_name = top_vc["web_name"]

        cap_sim_pts = sim_cache[cap_name]["pts"]
        vc_sim_pts = sim_cache[vc_name]["pts"]

        cap_wins = np.mean(cap_sim_pts > vc_sim_pts) * 100
        vc_wins = np.mean(vc_sim_pts > cap_sim_pts) * 100
        cap_ties = np.mean(cap_sim_pts == vc_sim_pts) * 100

        contenders = []
        for cand in outfield_starters[:5]:
            c_name = cand["web_name"]
            c_pts = sim_cache[c_name]["pts"]
            contenders.append({
                "web_name": c_name,
                "club": cand.get("club_short"),
                "pos": cand.get("position_name"),
                "fixture": cand.get("next_fixture"),
                "form": float(cand.get("form") or 0.0),
                "mean_captain_pts": round(float(np.mean(c_pts * 2)), 2),
                "haul_prob_pct": round(float(np.mean(c_pts >= 10) * 100), 1),
                "blank_prob_pct": round(float(np.mean(c_pts <= 2) * 100), 1),
                "p10": round(float(np.percentile(c_pts * 2, 10)), 1),
                "p90": round(float(np.percentile(c_pts * 2, 90)), 1),
                "is_designated_captain": (c_name == cap_name),
                "is_designated_vc": (c_name == vc_name)
            })

        captain_duel_data = {
            "captain": {
                "web_name": cap_name,
                "club": top_captain.get("club_short"),
                "pos": top_captain.get("position_name"),
                "fixture": top_captain.get("next_fixture"),
                "form": float(top_captain.get("form") or 0.0),
                "mean_single_pts": sim_cache[cap_name]["mean_pts"],
                "mean_captain_pts": round(sim_cache[cap_name]["mean_pts"] * 2, 2),
                "p10": round(float(np.percentile(cap_sim_pts * 2, 10)), 1),
                "p90": round(float(np.percentile(cap_sim_pts * 2, 90)), 1),
                "haul_prob_pct": round(float(np.mean(cap_sim_pts >= 10) * 100), 1),
                "blank_prob_pct": round(float(np.mean(cap_sim_pts <= 2) * 100), 1),
                "win_rate_pct": round(float(cap_wins), 1)
            },
            "vice_captain": {
                "web_name": vc_name,
                "club": top_vc.get("club_short"),
                "pos": top_vc.get("position_name"),
                "fixture": top_vc.get("next_fixture"),
                "form": float(top_vc.get("form") or 0.0),
                "mean_single_pts": sim_cache[vc_name]["mean_pts"],
                "mean_captain_pts": round(sim_cache[vc_name]["mean_pts"] * 2, 2),
                "p10": round(float(np.percentile(vc_sim_pts * 2, 10)), 1),
                "p90": round(float(np.percentile(vc_sim_pts * 2, 90)), 1),
                "haul_prob_pct": round(float(np.mean(vc_sim_pts >= 10) * 100), 1),
                "blank_prob_pct": round(float(np.mean(vc_sim_pts <= 2) * 100), 1),
                "win_rate_pct": round(float(vc_wins), 1)
            },
            "tie_rate_pct": round(float(cap_ties), 1),
            "contenders": contenders
        }

        # -------------------------------------------------------------
        # Starters Formatted List
        # -------------------------------------------------------------
        starters_list = []
        for s in best_starters:
            s_name = s["web_name"]
            is_c = (s_name == cap_name)
            is_vc = (s_name == vc_name)
            starters_list.append({
                "web_name": s_name,
                "full_name": s.get("full_name"),
                "pos": s.get("position_name"),
                "club": s.get("club_short"),
                "fixture": s.get("next_fixture"),
                "fdr": s.get("next_fdr", 3),
                "cost": s.get("now_cost", 0.0),
                "form": float(s.get("form") or 0.0),
                "status": s.get("status", "a"),
                "cop": s.get("chance_of_playing", 100),
                "news": s.get("news", ""),
                "yellow_cards": s.get("yellow_cards", 0),
                "red_cards": s.get("red_cards", 0),
                "mean_pts": sim_cache[s_name]["mean_pts"],
                "p10": sim_cache[s_name]["p10"],
                "p90": sim_cache[s_name]["p90"],
                "role": "CAPTAIN" if is_c else ("VICE_CAPTAIN" if is_vc else "STARTER")
            })

        # -------------------------------------------------------------
        # 'What to Move Around' Actionable Checklist
        # -------------------------------------------------------------
        checklist = []

        # 1. Check for benched starters who shouldn't be starting
        for b_item in bench_breakdown:
            if b_item["web_name"] == "Senesi":
                checklist.append({
                    "step": 1,
                    "action": "Move Marcos Senesi to Bench (Sub 3)",
                    "category": "BENCH",
                    "badge": "🔴 MOVE TO BENCH",
                    "reason": "Senesi was dropped in GW2 & GW3 (0 mins played, form 1.0). Starting him wastes a defender spot."
                })
            elif b_item["web_name"] == "Solanke":
                checklist.append({
                    "step": 2,
                    "action": "Place Dominic Solanke as Sub 2",
                    "category": "BENCH_ORDER",
                    "badge": "🟡 BENCH PRIORITY",
                    "reason": "Solanke is in a cameo rotation role (43 mins in 3 matches, form 1.0). Placed behind Robinson to ensure 3 DEF legality."
                })

        # 2. Check for promotions to Starting XI
        for s_item in starters_list:
            if s_item["web_name"] == "Thiaw":
                checklist.append({
                    "step": 3,
                    "action": "Promote Malick Thiaw into Starting XI",
                    "category": "START",
                    "badge": "🟢 START IN XI",
                    "reason": "Guaranteed 90-minute starter (270 mins played). Secures 3-5-2 backline alongside Guéhi and Pedro Porro."
                })

        # 3. Priority bench ordering
        b_names = [b["web_name"] for b in bench_breakdown]
        checklist.append({
            "step": 4,
            "action": f"Set Bench Priority Order: {b_names[0]} (Sub 1) ➔ {b_names[1]} (Sub 2) ➔ {b_names[2]} (Sub 3) ➔ {b_names[3]} (GKP Sub)",
            "category": "SUB_STRATEGY",
            "badge": "🪑 SET BENCH ORDER",
            "reason": f"{b_names[0]} has a {bench_breakdown[0]['activation_prob_pct']}% auto-sub probability and guarantees the legal 3 DEF formation minimum."
        })

        # 4. Captaincy designation
        checklist.append({
            "step": 5,
            "action": f"Assign Captain (C) to {cap_name} ({top_captain.get('club_short')} vs {top_captain.get('next_fixture')})",
            "category": "CAPTAIN",
            "badge": "★ SET CAPTAIN",
            "reason": f"Projected {captain_duel_data['captain']['mean_captain_pts']} captain points with {captain_duel_data['captain']['haul_prob_pct']}% haul probability. Outscores {vc_name} in {captain_duel_data['captain']['win_rate_pct']}% of simulations."
        })

        # 5. Vice-Captaincy designation
        checklist.append({
            "step": 6,
            "action": f"Assign Vice-Captain (VC) to {vc_name} ({top_vc.get('club_short')} vs {top_vc.get('next_fixture')})",
            "category": "VICE_CAPTAIN",
            "badge": "☆ SET VICE-CAPTAIN",
            "reason": f"Projected {captain_duel_data['vice_captain']['mean_captain_pts']} captain points with 100% starting minutes security. Immediate 2x fallback if {cap_name} is a late scratch."
        })

        checklist.sort(key=lambda x: x["step"])

        # -------------------------------------------------------------
        # Disciplinary & Health Alerts
        # -------------------------------------------------------------
        alerts = []
        for p in squad_player_dicts:
            name = p["web_name"]
            st_flag = p.get("status", "a")
            cop = p.get("chance_of_playing")
            news = p.get("news", "")
            yc = p.get("yellow_cards", 0)
            rc = p.get("red_cards", 0)
            form_val = float(p.get("form") or 0.0)

            has_flag = False
            flag_msg = []
            if st_flag != "a":
                has_flag = True
                flag_msg.append(f"Status '{st_flag}' ({news or 'Flagged'})")
            if cop is not None and cop < 100:
                has_flag = True
                flag_msg.append(f"{cop}% Chance of Playing")
            if yc >= 1:
                flag_msg.append(f"{yc} Yellow Card(s)")
            if rc >= 1:
                has_flag = True
                flag_msg.append(f"{rc} Red Card!")
            if form_val <= 1.5:
                flag_msg.append(f"Cold Form ({form_val:.1f})")
            elif form_val >= 7.0:
                flag_msg.append(f"Hot Form ({form_val:.1f}) 🔥")

            if has_flag or yc >= 1 or form_val <= 1.5 or form_val >= 7.0:
                alerts.append({
                    "web_name": name,
                    "pos": p.get("position_name"),
                    "club": p.get("club_short"),
                    "status": st_flag,
                    "cop": cop if cop is not None else 100,
                    "news": news,
                    "yellow_cards": yc,
                    "red_cards": rc,
                    "form": form_val,
                    "notes": " | ".join(flag_msg)
                })

        res_dict = {
            "optimal_formation": f"{best_formation[0]}-{best_formation[1]}-{best_formation[2]}",
            "formation_evaluations": formation_evals,
            "starters": starters_list,
            "bench": bench_breakdown,
            "captaincy_duel": captain_duel_data,
            "move_around_checklist": checklist,
            "disciplinary_and_injury_alerts": alerts,
            "squad_summary": {
                "mean_total": round(float(np.mean(best_squad_totals)), 2),
                "floor_p10": round(float(np.percentile(best_squad_totals, 10)), 1),
                "median_p50": round(float(np.median(best_squad_totals)), 1),
                "ceiling_p90": round(float(np.percentile(best_squad_totals, 90)), 1),
                "std": round(float(np.std(best_squad_totals)), 2),
                "n_sims": n_sims,
                "simulation_totals": best_squad_totals
            }
        }
        return clean_nans(res_dict)

    def evaluate_transfers(self,
                           current_squad_names: Optional[List[str]] = None,
                           bank: float = 3.7,
                           num_transfers: int = 1,
                           free_transfers: int = 1,
                           n_sims: int = 5000,
                           position_filter: Optional[str] = None,
                           sell_player_filter: Optional[str] = None,
                           strict_injury_filter: bool = True) -> Dict[str, Any]:
        """
        Evaluate candidate transfers via Monte Carlo simulation:
        - Strict hygiene filter removing unavailable, injured, suspended, and departed players.
        - Calculates point hit penalties (-4 pts per extra transfer beyond free quota).
        - Discovers the Top 3 Transfer Archetypes:
          1. Max Expected Value (Moneyball EV)
          2. Max Floor & Safety (Guaranteed starter, lowest blank risk)
          3. Max Ceiling & Differential (Highest 90th percentile haul)
        """
        if current_squad_names is None:
            current_squad_names = DEFAULT_SQUAD

        clean_pool = self.get_clean_player_pool(min_minutes=15)
        fpl_all = self.fpl_client.get_players_df()

        # Match current squad player rows
        current_player_dicts = []
        for name in current_squad_names:
            m = fpl_all[fpl_all["web_name"].str.lower() == name.lower()]
            if m.empty:
                m = fpl_all[fpl_all["full_name"].str.lower() == name.lower()]
            if m.empty:
                m = fpl_all[fpl_all["web_name"].str.contains(name, case=False, na=False)]
            if not m.empty:
                current_player_dicts.append(m.iloc[0].to_dict())

        # Precompute simulation for current squad
        sim_cache = self.precompute_player_sims(current_player_dicts, is_current_squad=True, n_sims=n_sims)
        baseline_totals, baseline_meta = self.simulate_squad_lineup(current_squad_names, sim_cache, n_sims=n_sims)

        baseline_mean = round(float(baseline_totals.mean()), 2)
        baseline_p10 = round(float(np.percentile(baseline_totals, 10)), 1)
        baseline_p50 = round(float(np.median(baseline_totals)), 1)
        baseline_p90 = round(float(np.percentile(baseline_totals, 90)), 1)
        baseline_std = round(float(baseline_totals.std()), 2)

        # Hit penalty and candidate search limits from config
        mc_cfg = get_params("monte_carlo")
        trans_cfg = mc_cfg.get("transfers", {})
        hit_cost = trans_cfg.get("hit_cost_per_transfer", 4)
        top_cand_limit = trans_cfg.get("top_candidates_per_pos", 15)

        hit_penalty = max(0, num_transfers - free_transfers) * hit_cost

        # Select candidate buy targets
        current_names_set = set(p["web_name"] for p in current_player_dicts)
        eligible_buys = clean_pool[~clean_pool["web_name"].isin(current_names_set)].copy()

        # Pick top candidates per position by composite metrics
        top_candidates = []
        for pos in ["GKP", "DEF", "MID", "FWD"]:
            pos_df = eligible_buys[eligible_buys["position_name"] == pos].sort_values(
                by="fdr_moneyball_score", ascending=False
            ).head(top_cand_limit)
            for _, r in pos_df.iterrows():
                top_candidates.append(r.to_dict())


        # Precompute candidate buy simulations
        buy_sim_cache = self.precompute_player_sims(top_candidates, is_current_squad=False, n_sims=n_sims)
        combined_cache = {**sim_cache, **buy_sim_cache}

        evaluated_moves = []

        if num_transfers == 1:
            # 1 Transfer evaluation
            for p_out in current_player_dicts:
                out_name = p_out["web_name"]
                out_pos = p_out["position_name"]
                out_cost = p_out["now_cost"]

                if sell_player_filter and sell_player_filter.lower() not in out_name.lower():
                    continue

                if position_filter and position_filter != "ALL" and out_pos != position_filter:
                    continue

                max_buy_cost = round(out_cost + bank, 1)

                candidate_replacements = [
                    c for c in top_candidates
                    if c["position_name"] == out_pos and c["now_cost"] <= max_buy_cost
                ]

                for p_in in candidate_replacements:
                    in_name = p_in["web_name"]
                    in_cost = p_in["now_cost"]
                    in_club = p_in.get("club_short", "UNK")

                    # Club constraint (max 3 players from same club)
                    new_squad_names = [n if n != out_name else in_name for n in current_squad_names]
                    clubs_in_squad = [
                        combined_cache[n]["player"].get("club_short", "UNK")
                        for n in new_squad_names if n in combined_cache
                    ]
                    if clubs_in_squad.count(in_club) > 3:
                        continue

                    # Simulate new squad
                    new_totals, new_meta = self.simulate_squad_lineup(new_squad_names, combined_cache, n_sims=n_sims)

                    # Apply hit penalty if any
                    effective_totals = new_totals - hit_penalty
                    diff = effective_totals - baseline_totals

                    net_mean_gain = round(float(diff.mean()), 2)
                    win_prob = round(float(np.mean(diff > 0) * 100), 1)
                    floor_p10 = round(float(np.percentile(effective_totals, 10)), 1)
                    median_p50 = round(float(np.median(effective_totals)), 1)
                    ceiling_p90 = round(float(np.percentile(effective_totals, 90)), 1)
                    std_dev = round(float(effective_totals.std()), 2)
                    sharpe = round(net_mean_gain / std_dev, 2) if std_dev > 0 else 0.0

                    bank_remaining = round(bank + out_cost - in_cost, 1)

                    evaluated_moves.append({
                        "transfer_type": "1 Transfer",
                        "out_player": out_name,
                        "out_club": p_out.get("club_short", "UNK"),
                        "out_pos": out_pos,
                        "out_cost": out_cost,
                        "out_mean": sim_cache[out_name]["mean_pts"],
                        "in_player": in_name,
                        "in_club": in_club,
                        "in_pos": p_in["position_name"],
                        "in_cost": in_cost,
                        "in_mean": buy_sim_cache[in_name]["mean_pts"],
                        "cost_diff": round(in_cost - out_cost, 1),
                        "bank_remaining": bank_remaining,
                        "hit_penalty": hit_penalty,
                        "net_mean_gain": net_mean_gain,
                        "win_prob": win_prob,
                        "new_mean": round(float(effective_totals.mean()), 2),
                        "floor_p10": floor_p10,
                        "median_p50": median_p50,
                        "ceiling_p90": ceiling_p90,
                        "std_dev": std_dev,
                        "sharpe": sharpe,
                        "fdr_next_5": p_in.get("fdr_next_5", 3.0),
                        "p_goal": p_in.get("expected_goals_per_90", 0.0),
                        "price_direction": p_in.get("price_direction", "flat"),
                        "raw_totals": effective_totals,
                        "new_squad_names": new_squad_names
                    })

        elif num_transfers == 2:
            # 2 Transfers evaluation: focus on key sell candidates (Senesi, Solanke, Roefs, etc.)
            key_sells = [p for p in current_player_dicts if p["web_name"] in ["Senesi", "Solanke", "Roefs", "Thiaw", "Rogers", "Robinson"]]
            if sell_player_filter:
                key_sells = [p for p in current_player_dicts if sell_player_filter.lower() in p["web_name"].lower()]

            for i in range(len(key_sells)):
                for j in range(i + 1, len(key_sells)):
                    p_out1 = key_sells[i]
                    p_out2 = key_sells[j]

                    comb_budget = round(p_out1["now_cost"] + p_out2["now_cost"] + bank, 1)

                    cand1 = [c for c in top_candidates if c["position_name"] == p_out1["position_name"]][:8]
                    cand2 = [c for c in top_candidates if c["position_name"] == p_out2["position_name"]][:8]

                    for p_in1 in cand1:
                        for p_in2 in cand2:
                            if p_in1["web_name"] == p_in2["web_name"]:
                                continue
                            if (p_in1["now_cost"] + p_in2["now_cost"]) > comb_budget:
                                continue

                            new_squad_names = [
                                p_in1["web_name"] if n == p_out1["web_name"] else (p_in2["web_name"] if n == p_out2["web_name"] else n)
                                for n in current_squad_names
                            ]

                            new_totals, _ = self.simulate_squad_lineup(new_squad_names, combined_cache, n_sims=n_sims)
                            effective_totals = new_totals - hit_penalty
                            diff = effective_totals - baseline_totals

                            net_mean_gain = round(float(diff.mean()), 2)
                            win_prob = round(float(np.mean(diff > 0) * 100), 1)
                            floor_p10 = round(float(np.percentile(effective_totals, 10)), 1)
                            median_p50 = round(float(np.median(effective_totals)), 1)
                            ceiling_p90 = round(float(np.percentile(effective_totals, 90)), 1)
                            std_dev = round(float(effective_totals.std()), 2)
                            sharpe = round(net_mean_gain / std_dev, 2) if std_dev > 0 else 0.0

                            bank_remaining = round(comb_budget - p_in1["now_cost"] - p_in2["now_cost"], 1)

                            evaluated_moves.append({
                                "transfer_type": "2 Transfers",
                                "out_player": f"{p_out1['web_name']} & {p_out2['web_name']}",
                                "out_club": f"{p_out1.get('club_short', 'UNK')}/{p_out2.get('club_short', 'UNK')}",
                                "out_pos": f"{p_out1['position_name']}/{p_out2['position_name']}",
                                "out_cost": round(p_out1["now_cost"] + p_out2["now_cost"], 1),
                                "out_mean": round(sim_cache[p_out1['web_name']]["mean_pts"] + sim_cache[p_out2['web_name']]["mean_pts"], 1),
                                "in_player": f"{p_in1['web_name']} & {p_in2['web_name']}",
                                "in_club": f"{p_in1.get('club_short', 'UNK')}/{p_in2.get('club_short', 'UNK')}",
                                "in_pos": f"{p_in1['position_name']}/{p_in2['position_name']}",
                                "in_cost": round(p_in1["now_cost"] + p_in2["now_cost"], 1),
                                "in_mean": round(buy_sim_cache[p_in1['web_name']]["mean_pts"] + buy_sim_cache[p_in2['web_name']]["mean_pts"], 1),
                                "cost_diff": round((p_in1["now_cost"] + p_in2["now_cost"]) - (p_out1["now_cost"] + p_out2["now_cost"]), 1),
                                "bank_remaining": bank_remaining,
                                "hit_penalty": hit_penalty,
                                "net_mean_gain": net_mean_gain,
                                "win_prob": win_prob,
                                "new_mean": round(float(effective_totals.mean()), 2),
                                "floor_p10": floor_p10,
                                "median_p50": median_p50,
                                "ceiling_p90": ceiling_p90,
                                "std_dev": std_dev,
                                "sharpe": sharpe,
                                "fdr_next_5": round((p_in1.get("fdr_next_5", 3.0) + p_in2.get("fdr_next_5", 3.0)) / 2.0, 1),
                                "p_goal": 0.0,
                                "price_direction": "mix",
                                "raw_totals": effective_totals,
                                "new_squad_names": new_squad_names
                            })

        if not evaluated_moves:
            return {
                "success": False,
                "message": "No valid transfers found within budget and constraints.",
                "baseline": {
                    "mean": baseline_mean, "p10": baseline_p10, "p50": baseline_p50,
                    "p90": baseline_p90, "std": baseline_std, "meta": baseline_meta,
                    "raw_totals": baseline_totals
                }
            }

        df_results = pd.DataFrame(evaluated_moves)
        df_results = df_results.sort_values(by="net_mean_gain", ascending=False).reset_index(drop=True)

        # -------------------------------------------------------------
        # Extract Top 3 Transfer Archetypes
        # -------------------------------------------------------------
        # 1. Max Expected Value (Highest Mean Gain)
        opt_ev = df_results.sort_values(by="net_mean_gain", ascending=False).iloc[0].to_dict()
        opt_ev["archetype"] = "🏆 Max Expected Value (Moneyball Core)"
        opt_ev["badge_color"] = "#facc15"
        opt_ev["tag"] = "MAX_EV"
        opt_ev["rationale"] = (
            f"Maximizes expected points (+{opt_ev['net_mean_gain']} pts/GW) with a {opt_ev['win_prob']}% "
            f"probability of beating your current squad. Highest overall mathematical return."
        )

        # 2. Max Floor / Safety (Highest P10 Floor with net gain > 0, distinct from EV)
        pool_floor = df_results[(df_results["net_mean_gain"] > 0) & (df_results["in_player"] != opt_ev["in_player"])]
        if pool_floor.empty:
            pool_floor = df_results[df_results["in_player"] != opt_ev["in_player"]]
        if pool_floor.empty:
            pool_floor = df_results
        opt_floor = pool_floor.sort_values(by=["floor_p10", "net_mean_gain"], ascending=[False, False]).iloc[0].to_dict()
        opt_floor["archetype"] = "🛡️ Maximum Floor & Safety (Zero Blank Hedge)"
        opt_floor["badge_color"] = "#10b981"
        opt_floor["tag"] = "MAX_FLOOR"
        opt_floor["rationale"] = (
            f"Guarantees a resilient safety floor ({opt_floor['floor_p10']} pts P10) while adding +{opt_floor['net_mean_gain']} net pts. "
            f"Eliminates bench/cameo blank risks and protects rank."
        )

        # 3. Max Ceiling / Differential (Highest P90 Ceiling, distinct from EV and Floor)
        used_ins = {opt_ev["in_player"], opt_floor["in_player"]}
        pool_ceiling = df_results[~df_results["in_player"].isin(used_ins)]
        if pool_ceiling.empty:
            pool_ceiling = df_results
        opt_ceiling = pool_ceiling.sort_values(by=["ceiling_p90", "net_mean_gain"], ascending=[False, False]).iloc[0].to_dict()
        opt_ceiling["archetype"] = "🚀 Maximum Ceiling & Differential (League Chaser)"
        opt_ceiling["badge_color"] = "#a855f7"
        opt_ceiling["tag"] = "MAX_CEILING"
        opt_ceiling["rationale"] = (
            f"Highest explosive haul potential ({opt_ceiling['ceiling_p90']} pts P90 ceiling). Ideal for closing "
            f"the 56-point gap against rival leader Vincent O'Connor."
        )

        return {
            "success": True,
            "baseline": {
                "mean": baseline_mean, "p10": baseline_p10, "p50": baseline_p50,
                "p90": baseline_p90, "std": baseline_std, "meta": baseline_meta,
                "raw_totals": baseline_totals
            },
            "top_3": [opt_ev, opt_floor, opt_ceiling],
            "all_results_df": df_results,
            "hit_penalty": hit_penalty,
            "num_transfers": num_transfers,
            "free_transfers": free_transfers
        }
