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

from fpl_client import FPLClient
from tactical_client import TacticalClient, normalize_name
from xp_model import XPModel, DEFAULT_SQUAD, GW4_MATCH_ODDS


class MonteCarloEngine:
    def __init__(self, fpl_client: Optional[FPLClient] = None,
                 tac_client: Optional[TacticalClient] = None,
                 xp_model: Optional[XPModel] = None):
        self.fpl_client = fpl_client or FPLClient()
        self.tac_client = tac_client or TacticalClient()
        self.xp_model = xp_model or XPModel()
        self.team_odds = self.xp_model.team_odds

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
                         n_sims: int = 5000) -> Tuple[np.ndarray, np.ndarray]:
        """
        Simulate N gameweek outcomes for a single player.
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

        # 1. Hard status check
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

        # 3. Minutes & Start probability
        mins_status = trends_dict.get("minutes_status", "REGULAR_STARTER")
        avg_recent_mins = trends_dict.get("avg_recent_mins", 75.0)

        # Fitness probability based on yellow flags
        if status == "d" or (cop is not None and cop < 100):
            p_fit = (cop / 100.0) if cop is not None else 0.75
        else:
            p_fit = 0.99

        if mins_status == "BENCHED_OR_DROPPED":
            p_start = 0.10
            exp_starter_mins = 60.0
            p_cameo = 0.35
        elif mins_status == "ROTATION_RISK":
            p_start = 0.45
            exp_starter_mins = 65.0
            p_cameo = 0.65
        elif mins_status == "REGULAR_STARTER":
            p_start = 0.85
            exp_starter_mins = min(85.0, max(65.0, avg_recent_mins))
            p_cameo = 0.75
        else:  # SECURE_STARTER
            p_start = 0.96
            exp_starter_mins = min(90.0, max(75.0, avg_recent_mins))
            p_cameo = 0.85

        # Vectorized draws for minutes
        fits = np.random.binomial(1, p_fit, n_sims)
        starts = fits * np.random.binomial(1, p_start, n_sims)
        cameos = fits * (1 - starts) * np.random.binomial(1, p_cameo, n_sims)

        mins = np.zeros(n_sims)
        n_starts = int(np.sum(starts))
        if n_starts > 0:
            mins[starts == 1] = np.clip(np.random.normal(exp_starter_mins, 7.5, n_starts), 50.0, 90.0)
        n_cameos = int(np.sum(cameos))
        if n_cameos > 0:
            mins[cameos == 1] = np.random.uniform(10.0, 30.0, n_cameos)

        # 4. Appearance Points
        app_pts = np.where(mins >= 60.0, 2, np.where(mins > 0.0, 1, 0))

        # 5. Clean Sheet Points & Goals Conceded Penalty
        cs_draw = (mins >= 60.0) * np.random.binomial(1, cs_prob, n_sims)
        if pos in ["DEF", "GKP"]:
            cs_pts = cs_draw * 4
        elif pos == "MID":
            cs_pts = cs_draw * 1
        else:
            cs_pts = np.zeros(n_sims)

        mins_fraction = mins / 90.0
        gc_draw = np.random.poisson(team_xgc * mins_fraction)
        gc_penalty = np.where(np.isin(pos, ["DEF", "GKP"]), -(gc_draw // 2), 0)

        # Saves for GKP
        saves_pts = np.where(pos == "GKP", (np.random.poisson(gc_draw * 1.3) // 3), 0)

        # 6. Attacking Points (Goals & Assists)
        npxg_90 = float(tac_dict.get("NPxG_90") or 0.0)
        if npxg_90 == 0.0:
            npxg_90 = float(player_dict.get("expected_goals_per_90") or 0.0)

        pen_duty = (player_dict.get("penalties_order") == 1)
        pen_bonus = 0.14 if pen_duty else 0.0

        match_xg = (npxg_90 * mins_fraction * (team_xg / 1.35)) + (pen_bonus * (mins > 0))
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

        match_xa = (xa_90 * mins_fraction * (team_xg / 1.35)) + (deadball_bonus * (mins > 0))
        assists_draw = np.random.poisson(match_xa)
        assist_pts = assists_draw * 3

        # 7. Disciplinary Cards
        yc_draw = (mins > 0) * np.random.binomial(1, 0.12, n_sims) * -1

        # 8. Defensive Work Rate Floor Bonus (DEF only)
        def_actions = trends_dict.get("avg_recent_def_contrib", 0.0)
        def_floor = np.where((pos == "DEF") & (mins >= 60), np.random.binomial(1, min(0.65, def_actions * 0.1), n_sims), 0)

        # 9. Bonus Points (BPS)
        bps = (goals_draw * 24) + (assists_draw * 18) + (cs_draw * 12) + (def_floor * 4) + (saves_pts * 6)
        bps += np.where(mins >= 60, 2, 0)
        bonus_pts = np.where(bps >= 32, 3, np.where(bps >= 22, 2, np.where(bps >= 14, 1, 0)))

        # Total points
        total_pts = app_pts + cs_pts + gc_penalty + saves_pts + goal_pts + assist_pts + yc_draw + def_floor + bonus_pts
        total_pts = np.maximum(-2, total_pts)

        return total_pts, mins

    def precompute_player_sims(self, player_dicts: List[Dict[str, Any]],
                               is_current_squad: bool = False,
                               n_sims: int = 5000) -> Dict[str, Dict[str, Any]]:
        """Precompute Monte Carlo simulation arrays for a set of players."""
        names = [p.get("web_name") or p.get("full_name") for p in player_dicts]
        
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

            pts, mins = self.simulate_player(p, t_dict, tac_dict, n_sims=n_sims)
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

        # Hit penalty
        hit_penalty = max(0, num_transfers - free_transfers) * 4

        # Select candidate buy targets
        current_names_set = set(p["web_name"] for p in current_player_dicts)
        eligible_buys = clean_pool[~clean_pool["web_name"].isin(current_names_set)].copy()

        # Pick top candidates per position by composite metrics (top 15 per position = 60 players)
        top_candidates = []
        for pos in ["GKP", "DEF", "MID", "FWD"]:
            pos_df = eligible_buys[eligible_buys["position_name"] == pos].sort_values(
                by="fdr_moneyball_score", ascending=False
            ).head(15)
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
