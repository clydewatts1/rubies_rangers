"""
analytics/challenge/scoring_adapter.py
Modulates baseline player expected returns according to dynamic challenge scoring rules.
Computes stochastic volatility parameters and right-tail potential for Monte Carlo tournament evaluation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, Any
from analytics.challenge.contracts import ChallengeRuleSet


class ChallengeScoringAdapter:
    """Adapts standard player projection distributions to FPL Challenge scoring overrides."""

    @staticmethod
    def adjust_projections(
        df_players: pd.DataFrame,
        rule_set: ChallengeRuleSet
    ) -> pd.DataFrame:
        """
        Produce augmented player projection DataFrame incorporating challenge-specific modifiers,
        stochastic volatility sigma, differential leverage, and goal stacking potentials.
        """
        df = df_players.copy()

        # Standardize position to canonical GKP, DEF, MID, FWD
        pos_map = {
            "GKP": "GKP", "GK": "GKP", "GOALKEEPER": "GKP", "GOALKEEPERS": "GKP", "1": "GKP", 1: "GKP",
            "DEF": "DEF", "DEFENDER": "DEF", "DEFENDERS": "DEF", "2": "DEF", 2: "DEF",
            "MID": "MID", "MIDFIELDER": "MID", "MIDFIELDERS": "MID", "3": "MID", 3: "MID",
            "FWD": "FWD", "FORWARD": "FWD", "FORWARDS": "FWD", "ATT": "FWD", "ATTACKER": "FWD", "4": "FWD", 4: "FWD"
        }
        if "position" not in df.columns:
            if "position_name" in df.columns:
                df["position"] = df["position_name"]
            elif "element_type" in df.columns:
                etype_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
                df["position"] = df["element_type"].map(etype_map)
            else:
                df["position"] = "MID"

        # Apply canonical mapping
        df["position"] = df["position"].astype(str).str.strip().str.upper().map(
            lambda x: pos_map.get(x, pos_map.get(x.rstrip("S"), "MID"))
        ).fillna("MID")

        # Standardize club
        if "club" not in df.columns:
            if "club_name" in df.columns:
                df["club"] = df["club_name"]
            elif "team_name" in df.columns:
                df["club"] = df["team_name"]
            elif "team" in df.columns:
                df["club"] = df["team"].astype(str)
            else:
                df["club"] = "Unknown"

        # Standardize web_name
        if "web_name" not in df.columns:
            df["web_name"] = df.get("name", df.get("full_name", "Player"))

        # Ensure core columns exist and are numeric
        if "xP" not in df.columns:
            if "points_per_game" in df.columns:
                df["xP"] = pd.to_numeric(df["points_per_game"], errors="coerce").fillna(3.5)
            else:
                df["xP"] = 3.5
        else:
            df["xP"] = pd.to_numeric(df["xP"], errors="coerce").fillna(3.5)

        if "now_cost" not in df.columns:
            if "cost" in df.columns:
                df["now_cost"] = pd.to_numeric(df["cost"], errors="coerce").fillna(6.0)
            else:
                df["now_cost"] = 6.0
        else:
            df["now_cost"] = pd.to_numeric(df["now_cost"], errors="coerce").fillna(6.0)

        if "selected_by_percent" not in df.columns:
            df["selected_by_percent"] = 10.0
        else:
            df["selected_by_percent"] = pd.to_numeric(df["selected_by_percent"], errors="coerce").fillna(10.0)

        # Threat
        if "threat" in df.columns:
            threat_series = pd.to_numeric(df["threat"], errors="coerce").fillna(20.0)
        else:
            threat_series = pd.Series(20.0, index=df.index)

        # Base adjusted points mu_adj
        mu_adj = df["xP"].copy()

        # Apply Challenge scoring overrides
        modifiers = rule_set.scoring_modifiers
        if "outside_box_goals" in modifiers:
            # Long range bonus favors attacking midfielders and clinical shooters
            boost_factor = modifiers["outside_box_goals"] * 0.25
            is_att = df["position"].isin(["MID", "FWD"])
            threat_bonus = (threat_series / 100.0).clip(0.1, 1.2)
            mu_adj = np.where(is_att, mu_adj + boost_factor * threat_bonus, mu_adj)

        if "mid_clean_sheet" in modifiers or "clean_sheets_MID" in modifiers:
            val = modifiers.get("mid_clean_sheet", modifiers.get("clean_sheets_MID", 1.0))
            is_mid = df["position"] == "MID"
            mu_adj = np.where(is_mid, mu_adj + 0.5 * val, mu_adj)

        if "forward_goal_multiplier" in modifiers:
            mult = modifiers["forward_goal_multiplier"]
            is_fwd = df["position"] == "FWD"
            mu_adj = np.where(is_fwd, mu_adj * mult, mu_adj)

        df["challenge_xP"] = np.round(mu_adj, 2)

        # Compute stochastic volatility sigma_i (Poisson/Negative-Binomial dispersion proxy)
        # In FPL, variance scales with mean: sigma ~ 0.45 * xP + 1.2
        df["sigma"] = np.round(0.48 * df["challenge_xP"] + 1.35, 2)

        # Differential leverage vector: penalize high ownership for tournament climbing
        # Formula: mu_adj * (1 - (ownership / 100))^0.85
        own_frac = (df["selected_by_percent"] / 100.0).clip(0.01, 0.85)
        df["differential_score"] = np.round(df["challenge_xP"] * ((1.0 - own_frac) ** 0.85), 2)

        # Maximum variance / right tail boom score
        # Formula: mu_adj + 1.25 * sigma
        df["boom_score"] = np.round(df["challenge_xP"] + 1.25 * df["sigma"], 2)

        # Exploit score: emphasizes challenge-specific features
        if modifiers:
            df["exploit_score"] = np.round(df["challenge_xP"] * 1.2, 2)
        else:
            df["exploit_score"] = df["challenge_xP"]

        return df
