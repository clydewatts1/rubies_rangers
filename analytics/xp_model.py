"""
Expected Points (xP) and Bookmaker Implied Probability Engine
Converts betting market consensus into fair implied Clean Sheet P(CS) and Goal P(Goal) probabilities,
and solves the optimal Starting XI, Captaincy pick, and Bench order for Rubies Rangers.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import math
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd

from clients.fpl_client import FPLClient
from clients.tactical_client import TacticalClient, normalize_name
from config_manager import get_system_config, get_params

DEFAULT_SQUAD = get_system_config("default_squad") or [
    "Roefs", "Verbruggen",
    "Pedro Porro", "Senesi", "Guéhi", "Robinson", "Thiaw",
    "Foden", "Ødegaard", "Mbeumo", "Cherki", "Rogers",
    "João Pedro", "Isak", "Solanke"
]

# Baseline Gameweek 4 Bookmaker Implied Team Goals from config
GW4_MATCH_ODDS = get_system_config("gw4_match_odds") or {
    "AVL_NFO": {"home": "AVL", "away": "NFO", "h_goals": 1.65, "a_goals": 1.10},
    "BOU_BRE": {"home": "BOU", "away": "BRE", "h_goals": 1.45, "a_goals": 1.35},
    "CHE_HUL": {"home": "CHE", "away": "HUL", "h_goals": 2.30, "a_goals": 0.75},
    "CRY_IPS": {"home": "CRY", "away": "IPS", "h_goals": 1.70, "a_goals": 1.05},
    "LIV_FUL": {"home": "LIV", "away": "FUL", "h_goals": 2.45, "a_goals": 0.80},
    "TOT_EVE": {"home": "TOT", "away": "EVE", "h_goals": 1.95, "a_goals": 1.05},
    "SUN_ARS": {"home": "SUN", "away": "ARS", "h_goals": 0.80, "a_goals": 2.15},
    "COV_BHA": {"home": "COV", "away": "BHA", "h_goals": 0.95, "a_goals": 1.70},
    "MUN_MCI": {"home": "MUN", "away": "MCI", "h_goals": 1.30, "a_goals": 1.85},
    "LEE_NEW": {"home": "LEE", "away": "NEW", "h_goals": 1.35, "a_goals": 1.60},
}



class XPModel:
    def __init__(self, gameweek: Optional[int] = None):
        self.fpl_client = FPLClient()
        self.tac_client = TacticalClient()
        self.gameweek = gameweek or self.fpl_client.get_current_gameweek() or 4
        self._build_team_odds_map(gameweek=self.gameweek)

    def _build_team_odds_map(self, gameweek: Optional[int] = None):
        """Construct team-level implied goals and clean sheet probabilities for any gameweek."""
        target_gw = gameweek or self.gameweek or 4
        self.team_odds = {}

        # If GW4, use calibrated high-fidelity bookmaker match odds
        if target_gw == 4:
            for m_id, m in GW4_MATCH_ODDS.items():
                h_team = m["home"]
                a_team = m["away"]
                h_xg = m["h_goals"]
                a_xg = m["a_goals"]

                # Poisson P(CS) = e^(-xg_conceded)
                h_cs_prob = round(math.exp(-a_xg), 3)
                a_cs_prob = round(math.exp(-h_xg), 3)

                # Decimal odds conversion (1 / P)
                h_cs_odds = round(1.0 / h_cs_prob, 2) if h_cs_prob > 0 else 99.0
                a_cs_odds = round(1.0 / a_cs_prob, 2) if a_cs_prob > 0 else 99.0

                self.team_odds[h_team] = {
                    "team": h_team,
                    "opponent": a_team,
                    "is_home": True,
                    "exp_goals_scored": h_xg,
                    "exp_goals_conceded": a_xg,
                    "clean_sheet_prob": h_cs_prob,
                    "clean_sheet_odds": h_cs_odds,
                    "fixture_str": f"{a_team} (H)"
                }
                self.team_odds[a_team] = {
                    "team": a_team,
                    "opponent": h_team,
                    "is_home": False,
                    "exp_goals_scored": a_xg,
                    "exp_goals_conceded": h_xg,
                    "clean_sheet_prob": a_cs_prob,
                    "clean_sheet_odds": a_cs_odds,
                    "fixture_str": f"{h_team} (A)"
                }
            return

        # For future gameweeks, dynamically build from upcoming fixtures
        try:
            fixtures = self.fpl_client.get_fixtures_data()
            boot = self.fpl_client.get_bootstrap_data()
            id_to_short = {t["id"]: t["short_name"] for t in boot.get("teams", [])}

            gw_fixtures = [f for f in fixtures if f.get("event") == target_gw]
            if gw_fixtures:
                xp_cfg = get_params("xp_model")
                dyn_cfg = xp_cfg.get("dynamic_fdr", {})
                h_base = dyn_cfg.get("home_base_xg", 2.2)
                h_coeff = dyn_cfg.get("home_diff_coeff", 0.25)
                h_adv = dyn_cfg.get("home_advantage", 0.2)
                min_h = dyn_cfg.get("min_home_xg", 0.6)
                a_base = dyn_cfg.get("away_base_xg", 1.9)
                a_coeff = dyn_cfg.get("away_diff_coeff", 0.25)
                min_a = dyn_cfg.get("min_away_xg", 0.5)

                for f in gw_fixtures:
                    h_code = id_to_short.get(f["team_h"], "UNK")
                    a_code = id_to_short.get(f["team_a"], "UNK")
                    h_diff = f.get("team_h_difficulty", 3)
                    a_diff = f.get("team_a_difficulty", 3)

                    h_xg = round(max(min_h, h_base - (a_diff * h_coeff) + h_adv), 2)
                    a_xg = round(max(min_a, a_base - (h_diff * a_coeff)), 2)

                    h_cs_prob = round(math.exp(-a_xg), 3)
                    a_cs_prob = round(math.exp(-h_xg), 3)
                    h_cs_odds = round(1.0 / h_cs_prob, 2) if h_cs_prob > 0 else 99.0
                    a_cs_odds = round(1.0 / a_cs_prob, 2) if a_cs_prob > 0 else 99.0

                    self.team_odds[h_code] = {
                        "team": h_code,
                        "opponent": a_code,
                        "is_home": True,
                        "exp_goals_scored": h_xg,
                        "exp_goals_conceded": a_xg,
                        "clean_sheet_prob": h_cs_prob,
                        "clean_sheet_odds": h_cs_odds,
                        "fixture_str": f"{a_code} (H)"
                    }
                    self.team_odds[a_code] = {
                        "team": a_code,
                        "opponent": h_code,
                        "is_home": False,
                        "exp_goals_scored": a_xg,
                        "exp_goals_conceded": h_xg,
                        "clean_sheet_prob": a_cs_prob,
                        "clean_sheet_odds": a_cs_odds,
                        "fixture_str": f"{h_code} (A)"
                    }
                return
        except Exception:
            pass

        # Fallback to GW4 baseline if dynamic generation encounters missing data
        for m_id, m in GW4_MATCH_ODDS.items():
            h_team = m["home"]
            a_team = m["away"]
            h_xg = m["h_goals"]
            a_xg = m["a_goals"]
            h_cs_prob = round(math.exp(-a_xg), 3)
            a_cs_prob = round(math.exp(-h_xg), 3)
            self.team_odds[h_team] = {
                "team": h_team, "opponent": a_team, "is_home": True,
                "exp_goals_scored": h_xg, "exp_goals_conceded": a_xg,
                "clean_sheet_prob": h_cs_prob, "clean_sheet_odds": round(1.0 / h_cs_prob, 2) if h_cs_prob > 0 else 99.0,
                "fixture_str": f"{a_team} (H)"
            }
            self.team_odds[a_team] = {
                "team": a_team, "opponent": h_team, "is_home": False,
                "exp_goals_scored": a_xg, "exp_goals_conceded": h_xg,
                "clean_sheet_prob": a_cs_prob, "clean_sheet_odds": round(1.0 / a_cs_prob, 2) if a_cs_prob > 0 else 99.0,
                "fixture_str": f"{h_team} (A)"
            }

    def get_gw4_odds_table(self) -> pd.DataFrame:
        """Return formatted table of all 20 Premier League teams with GW4 betting market probabilities."""
        records = []
        for t_code, o in sorted(self.team_odds.items(), key=lambda x: x[1]["clean_sheet_prob"], reverse=True):
            records.append({
                "Club": t_code,
                "GW4 Fixture": o["fixture_str"],
                "Team xG": o["exp_goals_scored"],
                "Opponent xG (xGC)": o["exp_goals_conceded"],
                "Clean Sheet Prob": f"{o['clean_sheet_prob'] * 100:.1f}%",
                "Clean Sheet Odds": f"{o['clean_sheet_odds']:.2f}",
                "cs_prob_val": o["clean_sheet_prob"],
                "xg_scored_val": o["exp_goals_scored"]
            })
        return pd.DataFrame(records)

    def calculate_player_xp(self, player_dict: Dict[str, Any], trends_dict: Dict[str, Any], tac_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate expected points (xP) for a player in Gameweek 4 based on:
        - Matchup odds and team implied goals
        - Minutes security and rotation risk
        - Understat NPxG/90 and shot quality
        - FPL set-piece hierarchy (penalties, direct FKs, corners)
        - Historical defensive contribution (CBI/tackles)
        """
        xp_cfg = get_params("xp_model")
        mins_cfg = xp_cfg.get("minutes", {})
        pen_cfg = xp_cfg.get("penalty", {})
        bonus_cfg = xp_cfg.get("bonus_model_weights", {})
        pts_rules = xp_cfg.get("points_rules", {})

        pos = player_dict.get("position_name", "MID")
        team_short = player_dict.get("club_short", "UNK")
        
        # Match odds lookup
        m_info = self.team_odds.get(team_short, {
            "exp_goals_scored": 1.3,
            "exp_goals_conceded": 1.3,
            "clean_sheet_prob": 0.27,
            "fixture_str": "TBD",
            "is_home": True
        })

        team_xg = m_info["exp_goals_scored"]
        team_xgc = m_info["exp_goals_conceded"]
        cs_prob = m_info["clean_sheet_prob"]

        # Expected Minutes calculation from Item 4 Trends & config
        mins_status = trends_dict.get("minutes_status", "REGULAR_STARTER")
        avg_recent_mins = trends_dict.get("avg_recent_mins", 75.0)

        if mins_status == "BENCHED_OR_DROPPED":
            m_data = mins_cfg.get("benched_or_dropped", {})
            exp_mins = m_data.get("exp_mins", 5.0)
            p_60 = m_data.get("p_60", 0.02)
        elif mins_status == "ROTATION_RISK":
            m_data = mins_cfg.get("rotation_risk", {})
            exp_mins = m_data.get("exp_mins", 40.0)
            p_60 = m_data.get("p_60", 0.40)
        elif mins_status == "REGULAR_STARTER":
            m_data = mins_cfg.get("regular_starter", {})
            exp_mins = min(m_data.get("max_mins", 80.0), max(m_data.get("min_mins", 60.0), avg_recent_mins))
            p_60 = m_data.get("p_60", 0.85)
        else:  # SECURE_STARTER
            m_data = mins_cfg.get("secure_starter", {})
            exp_mins = min(m_data.get("max_mins", 90.0), max(m_data.get("min_mins", 75.0), avg_recent_mins))
            p_60 = m_data.get("p_60", 0.98)

        mins_fraction = exp_mins / 90.0

        # Goal Probability P(Goal)
        # Combine Understat open-play NPxG/90 and FPL penalty duty
        npxg_90 = float(tac_dict.get("NPxG_90") or 0.0)
        if npxg_90 == 0.0:
            # Fallback to FPL xG_90
            npxg_90 = float(player_dict.get("expected_goals_per_90") or 0.0)

        pen_duty = (player_dict.get("penalties_order") == 1)
        pen_conv = pen_cfg.get("conversion_rate", 0.79)
        pen_award = pen_cfg.get("match_award_chance", 0.18)
        pen_bonus_xg = (pen_conv * pen_award) if pen_duty else 0.0

        team_goals_divisor = xp_cfg.get("team_baseline_goals_divisor", 1.35)
        # Match xG = (player NPxG/90 scaled by team goals) + penalty bonus
        match_xg = (npxg_90 * mins_fraction * (team_xg / team_goals_divisor)) + pen_bonus_xg
        p_goal = round(1.0 - math.exp(-match_xg), 3)

        # Assist Probability P(Assist)
        xa_90 = float(tac_dict.get("xA_90") or 0.0)
        if xa_90 == 0.0:
            xa_90 = float(player_dict.get("expected_assists_per_90") or 0.0)

        crn_duty = (player_dict.get("corners_and_indirect_freekicks_order") in [1, 2])
        fk_duty = (player_dict.get("direct_freekicks_order") in [1, 2])
        deadball_bonus = xp_cfg.get("deadball_bonus", 0.08) if (crn_duty or fk_duty) else 0.0

        match_xa = (xa_90 * mins_fraction * (team_xg / team_goals_divisor)) + deadball_bonus
        p_assist = round(1.0 - math.exp(-match_xa), 3)

        # Saves expectation for GKP (avg 1 pt per 3 saves)
        gkp_rate = xp_cfg.get("gkp_saves_rate", 2.8)
        gkp_ratio = xp_cfg.get("gkp_saves_pts_ratio", 0.33)
        exp_saves = (team_xgc * gkp_rate * mins_fraction) if pos == "GKP" else 0.0
        saves_pts = (exp_saves * gkp_ratio)

        # Goals conceded penalty (applies to GKP and DEF: -1 pt for every 2 goals conceded)
        # Expected penalty = (xGC * mins_fraction) / gc_penalty_divisor
        gc_div = pts_rules.get("gc_penalty_divisor", 2.0)
        gc_penalty = ((team_xgc * mins_fraction) / gc_div) if pos in ["GKP", "DEF"] else 0.0

        # Defensive contribution baseline bonus (from Item 4 CBI/tackles)
        def_actions = trends_dict.get("avg_recent_def_contrib", 0.0)
        def_floor_bonus = (def_actions * xp_cfg.get("def_actions_bonus_weight", 0.08)) if pos == "DEF" else 0.0

        # Total Expected Points (xP) by official FPL scoring rules
        if pos == "FWD":
            b_w = bonus_cfg.get("fwd", {})
            x_bonus = min(3.0, (match_xg * b_w.get("xg", 1.1)) + (match_xa * b_w.get("xa", 0.4)))
        elif pos == "MID":
            b_w = bonus_cfg.get("mid", {})
            x_bonus = min(3.0, (match_xg * b_w.get("xg", 0.9)) + (match_xa * b_w.get("xa", 0.6)) + (cs_prob * b_w.get("cs", 0.25)))
        elif pos == "DEF":
            b_w = bonus_cfg.get("def", {})
            x_bonus = min(3.0, (cs_prob * b_w.get("cs", 0.75)) + (match_xg * b_w.get("xg", 1.0)) + (match_xa * b_w.get("xa", 0.4)) + (def_floor_bonus * b_w.get("def_floor", 0.3)))
        else:  # GKP
            b_w = bonus_cfg.get("gkp", {})
            x_bonus = min(3.0, (cs_prob * b_w.get("cs", 0.6)) + (saves_pts * b_w.get("saves", 0.3)))

        app_60_pts = pts_rules.get("appearance_60", 2.0)
        app_sub_pts = pts_rules.get("appearance_sub_60", 1.0)
        appearance_pts = (app_60_pts * p_60) + (app_sub_pts * (mins_fraction - p_60) if mins_fraction > p_60 else 0.0)
        
        cs_gkp_def = pts_rules.get("clean_sheet_gkp_def", 4.0)
        cs_mid = pts_rules.get("clean_sheet_mid", 1.0)
        goal_gkp = pts_rules.get("goal_gkp", 10.0)
        goal_def = pts_rules.get("goal_def", 6.0)
        goal_mid = pts_rules.get("goal_mid", 5.0)
        goal_fwd = pts_rules.get("goal_fwd", 4.0)
        ast_pts = pts_rules.get("assist", 3.0)

        if pos == "GKP":
            xp = appearance_pts + (cs_gkp_def * cs_prob * p_60) + saves_pts - gc_penalty + x_bonus
        elif pos == "DEF":
            xp = appearance_pts + (cs_gkp_def * cs_prob * p_60) + (goal_def * match_xg) + (ast_pts * match_xa) - gc_penalty + def_floor_bonus + x_bonus
        elif pos == "MID":
            xp = appearance_pts + (cs_mid * cs_prob * p_60) + (goal_mid * match_xg) + (ast_pts * match_xa) + x_bonus
        else:  # FWD
            xp = appearance_pts + (goal_fwd * match_xg) + (ast_pts * match_xa) + x_bonus

        xp = max(0.0, xp)


        # Decimal betting odds
        goal_odds = round(1.0 / p_goal, 2) if p_goal > 0.01 else 99.0
        assist_odds = round(1.0 / p_assist, 2) if p_assist > 0.01 else 99.0

        return {
            "id": player_dict.get("id"),
            "web_name": player_dict.get("web_name"),
            "full_name": player_dict.get("full_name"),
            "position_name": pos,
            "club_short": team_short,
            "fixture": m_info["fixture_str"],
            "now_cost": player_dict.get("now_cost", 0.0),
            "exp_mins": round(exp_mins, 1),
            "p_60": round(p_60, 2),
            "mins_status": mins_status,
            "match_xg": round(match_xg, 2),
            "match_xa": round(match_xa, 2),
            "cs_prob": round(cs_prob * 100, 1),
            "p_goal": round(p_goal * 100, 1),
            "goal_odds": goal_odds,
            "p_assist": round(p_assist * 100, 1),
            "assist_odds": assist_odds,
            "team_xg": round(team_xg, 2),
            "team_xgc": round(team_xgc, 2),
            "x_bonus": round(x_bonus, 2),
            "xP": round(xp, 2)
        }

    def evaluate_squad_xp(self, squad_names: Optional[List[str]] = None) -> pd.DataFrame:
        """Compute comprehensive xP predictions for all 15 players in Rubies Rangers squad."""
        if squad_names is None:
            squad_names = DEFAULT_SQUAD

        fpl_df = self.fpl_client.get_players_df()
        squad_trends = self.fpl_client.get_squad_trends(squad_names)
        squad_tac = self.tac_client.get_squad_tactical_df(squad_names)

        records = []
        for name in squad_names:
            # Match in FPL
            p_fpl = fpl_df[fpl_df["web_name"].str.lower() == name.lower()]
            if p_fpl.empty:
                p_fpl = fpl_df[fpl_df["full_name"].str.lower() == name.lower()]
            if p_fpl.empty:
                p_fpl = fpl_df[fpl_df["web_name"].str.contains(name, case=False, na=False)]
            if p_fpl.empty:
                continue

            fpl_row = p_fpl.iloc[0].to_dict()
            p_id = fpl_row["id"]

            # Match in trends
            t_row = squad_trends[squad_trends["id"] == p_id]
            trends_dict = t_row.iloc[0].to_dict() if not t_row.empty else {}

            # Match in tactical
            norm = normalize_name(name)
            tac_m = squad_tac[squad_tac["norm_name"].str.contains(norm, case=False, na=False)]
            tac_dict = tac_m.iloc[0].to_dict() if not tac_m.empty else {}

            xp_res = self.calculate_player_xp(fpl_row, trends_dict, tac_dict)
            records.append(xp_res)

        return pd.DataFrame(records)

    def optimize_lineup(self, squad_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Solve the optimal Starting XI from the 15-player squad maximizing total xP.
        Obey standard FPL formation rules:
        - 1 GKP
        - 3 to 5 DEF
        - 2 to 5 MID
        - 1 to 3 FWD
        Total = 11 starters.
        Designates Captain (highest xP), Vice-Captain, and prioritized Bench order.
        """
        df = self.evaluate_squad_xp(squad_names=squad_names)
        
        gkps = df[df["position_name"] == "GKP"].sort_values(by="xP", ascending=False)
        defs = df[df["position_name"] == "DEF"].sort_values(by="xP", ascending=False)
        mids = df[df["position_name"] == "MID"].sort_values(by="xP", ascending=False)
        fwds = df[df["position_name"] == "FWD"].sort_values(by="xP", ascending=False)

        best_formation = None
        best_xp = -1.0
        best_starters = None
        best_bench = None

        # Standard legal FPL formations (DEF, MID, FWD)
        legal_formations = [
            (3, 5, 2),
            (3, 4, 3),
            (4, 4, 2),
            (4, 3, 3),
            (4, 5, 1),
            (5, 3, 2),
            (5, 4, 1),
            (5, 2, 3)
        ]

        for n_def, n_mid, n_fwd in legal_formations:
            if len(defs) < n_def or len(mids) < n_mid or len(fwds) < n_fwd or len(gkps) < 1:
                continue

            sel_gkp = gkps.iloc[:1]
            sel_def = defs.iloc[:n_def]
            sel_mid = mids.iloc[:n_mid]
            sel_fwd = fwds.iloc[:n_fwd]

            starters = pd.concat([sel_gkp, sel_def, sel_mid, sel_fwd])
            current_xp = starters["xP"].sum()

            if current_xp > best_xp:
                best_xp = current_xp
                best_formation = f"{n_def}-{n_mid}-{n_fwd}"
                best_starters = starters

        starter_ids = set(best_starters["id"])
        bench_players = df[~df["id"].isin(starter_ids)].copy()

        # Bench ordering: outfield players sorted by xP descending, backup GKP placed last (slot 4)
        outfield_bench = bench_players[bench_players["position_name"] != "GKP"].sort_values(by="xP", ascending=False)
        gkp_bench = bench_players[bench_players["position_name"] == "GKP"]
        ordered_bench = pd.concat([outfield_bench, gkp_bench])

        # Assign Captaincy and Vice-Captaincy
        sorted_starters = best_starters.sort_values(by="xP", ascending=False)
        captain = sorted_starters.iloc[0].to_dict()
        vice_captain = sorted_starters.iloc[1].to_dict()

        # Effective squad xP includes captain's double points
        effective_total_xp = round(best_xp + captain["xP"], 2)

        return {
            "formation": best_formation,
            "starting_xi": best_starters.sort_values(by=["position_name", "xP"], ascending=[True, False]),
            "bench": ordered_bench,
            "captain": captain,
            "vice_captain": vice_captain,
            "base_starting_xp": round(best_xp, 2),
            "effective_total_xp": effective_total_xp,
            "all_players_df": df.sort_values(by="xP", ascending=False)
        }

    def get_top_captains(self, top_n: int = 15) -> pd.DataFrame:
        """
        Evaluate and rank top Premier League captaincy candidates for Gameweek 4
        based on betting market implied team goals, anytime goal probability, and projected xP.
        """
        fpl_df = self.fpl_client.get_players_df()
        attackers = fpl_df[
            (fpl_df["position_name"].isin(["MID", "FWD"])) &
            (fpl_df["status"] == "a") &
            (fpl_df["minutes"] >= 150) &
            ((fpl_df["now_cost"] >= 6.5) | (fpl_df["expected_goal_involvements_per_90"] >= 0.40))
        ].copy()

        records = []
        for _, p in attackers.iterrows():
            pos = p["position_name"]
            team = p["club_short"]
            m_info = self.team_odds.get(team, {
                "exp_goals_scored": 1.3,
                "exp_goals_conceded": 1.3,
                "clean_sheet_prob": 0.27,
                "fixture_str": "TBD"
            })
            team_xg = m_info["exp_goals_scored"]
            cs_prob = m_info["clean_sheet_prob"]

            npxg_90 = float(p.get("expected_goals_per_90") or 0.0)
            xa_90 = float(p.get("expected_assists_per_90") or 0.0)
            pen_duty = (p.get("penalties_order") == 1)
            pen_bonus = (0.79 * 0.18) if pen_duty else 0.0

            # Assume secure starters for captain candidates (80-85 mins)
            mins_frac = 0.90
            match_xg = (npxg_90 * mins_frac * (team_xg / 1.35)) + pen_bonus
            match_xa = (xa_90 * mins_frac * (team_xg / 1.35))
            p_goal = round(1.0 - math.exp(-match_xg), 3) if match_xg > 0 else 0.0
            p_assist = round(1.0 - math.exp(-match_xa), 3) if match_xa > 0 else 0.0

            goal_pts_multiplier = 5.0 if pos == "MID" else 4.0
            x_bonus = min(3.0, (match_xg * 1.1) + (match_xa * 0.4))
            xp = 2.0 + (goal_pts_multiplier * match_xg) + (3.0 * match_xa) + (1.0 * cs_prob if pos == "MID" else 0.0) + x_bonus

            goal_odds = round(1.0 / p_goal, 2) if p_goal > 0.02 else 99.0

            records.append({
                "Player": p["web_name"],
                "Club": team,
                "Pos": pos,
                "Cost": f"£{p['now_cost']:.1f}m",
                "GW4 Fixture": m_info["fixture_str"],
                "Team xG": team_xg,
                "Match xG": round(match_xg, 2),
                "P(Goal)": f"{p_goal * 100:.1f}%",
                "Goal Odds": f"{goal_odds:.2f}",
                "Projected xP": round(xp, 2),
                "Captain xP (2x)": round(xp * 2, 2)
            })

        df_res = pd.DataFrame(records).sort_values(by="Projected xP", ascending=False)
        return df_res.head(top_n).reset_index(drop=True)


if __name__ == "__main__":
    model = XPModel()
    res = model.optimize_lineup()
    print(f"Optimal Formation: {res['formation']}")
    print(f"Starting XI Base xP: {res['base_starting_xp']} | Effective (C): {res['effective_total_xp']}")
    print(f"Captain: {res['captain']['web_name']} ({res['captain']['xP']} xP)")
    print(f"Vice-Captain: {res['vice_captain']['web_name']} ({res['vice_captain']['xP']} xP)")
    print("\nStarting XI:")
    print(res["starting_xi"][["position_name", "web_name", "club_short", "fixture", "cs_prob", "p_goal", "p_assist", "xP"]].to_string(index=False))
    print("\nBench Order:")
    print(res["bench"][["position_name", "web_name", "club_short", "fixture", "xP"]].to_string(index=False))
