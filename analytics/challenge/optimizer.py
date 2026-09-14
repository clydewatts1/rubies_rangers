"""
analytics/challenge/optimizer.py
Stage 1: Parameterized Integer Linear Programming (MILP) Multi-Objective Solver for FPL Challenge.
Formulates dynamic weekly constraints (squad size N, dynamic club caps C, budget caps B, dynamic positional bounds,
and captaincy enforcement c_i <= x_i).
Solves across 5 Pareto tactical vectors to produce deduplicated candidate squads in <25ms.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional, Set, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds

from analytics.challenge.contracts import ChallengeRuleSet, ChallengeOptimalSquad
from analytics.challenge.scoring_adapter import ChallengeScoringAdapter

logger = logging.getLogger(__name__)


class ChallengeOptimizer:
    """Stage 1 MILP Solver for FPL Challenge mode with dynamic constraints."""

    def __init__(
        self,
        players_df: pd.DataFrame,
        rule_set: ChallengeRuleSet
    ) -> None:
        self.raw_df = players_df.copy().reset_index(drop=True)
        self.rule_set = rule_set
        # Adjust projections and add challenge scoring vectors
        self.df = ChallengeScoringAdapter.adjust_projections(self.raw_df, self.rule_set)

        # Standardize position column
        if "position" not in self.df.columns and "position_name" in self.df.columns:
            self.df["position"] = self.df["position_name"]

        # Standardize club column
        if "club" not in self.df.columns:
            if "club_name" in self.df.columns:
                self.df["club"] = self.df["club_name"]
            elif "team_name" in self.df.columns:
                self.df["club"] = self.df["team_name"]
            else:
                self.df["club"] = self.df.get("team", "Unknown")

        # Standardize display name
        if "web_name" not in self.df.columns:
            self.df["web_name"] = self.df.get("name", self.df.get("full_name", "Player"))

    def _find_player_indices(self, names: List[str]) -> List[int]:
        """Resolve player names to DataFrame indices with fallback matching."""
        indices: List[int] = []
        for name in names:
            if not name:
                continue
            name_clean = name.strip().lower()
            m = self.df[self.df["web_name"].str.lower() == name_clean]
            if m.empty and "full_name" in self.df.columns:
                m = self.df[self.df["full_name"].str.lower() == name_clean]
            if m.empty:
                m = self.df[self.df["web_name"].str.contains(name_clean, case=False, na=False)]
            if not m.empty:
                indices.append(int(m.index[0]))
        return list(set(indices))

    def _resolve_objective_weights(self, objective: str) -> np.ndarray:
        """Return player valuation weights for the given tactical vector."""
        if objective == "max_ev":
            return self.df["challenge_xP"].values
        elif objective == "challenge_exploit":
            return self.df["exploit_score"].values
        elif objective == "differential_gpp":
            return self.df["differential_score"].values
        elif objective == "team_stack":
            # Stack top scoring clubs or high xG assets
            top_clubs = self.df.groupby("club")["challenge_xP"].sum().nlargest(4).index
            is_top_club = self.df["club"].isin(top_clubs).astype(float).values
            return self.df["challenge_xP"].values + 1.2 * is_top_club
        elif objective == "maximum_variance":
            return self.df["boom_score"].values
        else:
            return self.df["challenge_xP"].values

    def solve_single_vector(
        self,
        objective: str = "max_ev",
        lock_players: Optional[List[str]] = None,
        exclude_players: Optional[List[str]] = None,
        available_only: bool = True
    ) -> Optional[ChallengeOptimalSquad]:
        """
        Solve single MILP instance for a specific objective vector.
        Decision variables y: length 2M.
        y[0:M] = x_i (squad selection)
        y[M:2M] = c_i (captaincy selection)
        """
        df = self.df
        M = len(df)
        if M == 0:
            return None

        # Objective weights
        w = self._resolve_objective_weights(objective)
        # Minimize -w * x - w * c to maximize total points with captain 2x
        c_obj = np.concatenate([-w, -w])

        A_rows: List[np.ndarray] = []
        b_l: List[float] = []
        b_u: List[float] = []

        # 1. Total squad size sum(x_i) = N
        row_squad = np.zeros(2 * M)
        row_squad[:M] = 1.0
        A_rows.append(row_squad)
        b_l.append(float(self.rule_set.squad_size))
        b_u.append(float(self.rule_set.squad_size))

        # 2. Captain count sum(c_i) = 1
        row_capt = np.zeros(2 * M)
        row_capt[M:] = 1.0
        A_rows.append(row_capt)
        b_l.append(1.0)
        b_u.append(1.0)

        # 3. Captaincy link constraint: c_i - x_i <= 0 for each i
        # -x_i + c_i <= 0  ==>  -inf <= -x_i + c_i <= 0
        for i in range(M):
            row_link = np.zeros(2 * M)
            row_link[i] = -1.0
            row_link[M + i] = 1.0
            A_rows.append(row_link)
            b_l.append(-np.inf)
            b_u.append(0.0)

        # 4. Budget constraint: sum(cost * x_i) <= budget_cap
        cost_arr = df["now_cost"].values
        row_budget = np.zeros(2 * M)
        row_budget[:M] = cost_arr
        A_rows.append(row_budget)
        b_l.append(0.0)
        b_u.append(float(self.rule_set.budget_cap))

        # 5. Position constraints from rule_set.allowed_positions
        for pos, (min_pos, max_pos) in self.rule_set.allowed_positions.items():
            pos_mask = (df["position"] == pos).astype(float).values
            row_pos = np.zeros(2 * M)
            row_pos[:M] = pos_mask
            A_rows.append(row_pos)
            b_l.append(float(min_pos))
            b_u.append(float(max_pos))

        # 6. Dynamic Club Quotas: sum_{i in club} x_i <= max_per_team
        for club in df["club"].unique():
            club_mask = (df["club"] == club).astype(float).values
            row_club = np.zeros(2 * M)
            row_club[:M] = club_mask
            A_rows.append(row_club)
            b_l.append(0.0)
            b_u.append(float(self.rule_set.max_per_team))

        # 7. Availability filter
        if available_only and "status" in df.columns:
            unavail_mask = (df["status"] != "a").astype(float).values
            for i in np.where(unavail_mask > 0)[0]:
                row_unavail = np.zeros(2 * M)
                row_unavail[i] = 1.0
                A_rows.append(row_unavail)
                b_l.append(0.0)
                b_u.append(0.0)

        # 8. Locked players
        if lock_players:
            lock_indices = self._find_player_indices(lock_players)
            for idx in lock_indices:
                row_lock = np.zeros(2 * M)
                row_lock[idx] = 1.0
                A_rows.append(row_lock)
                b_l.append(1.0)
                b_u.append(1.0)

        # 9. Excluded players
        if exclude_players:
            exc_indices = self._find_player_indices(exclude_players)
            for idx in exc_indices:
                row_exc = np.zeros(2 * M)
                row_exc[idx] = 1.0
                A_rows.append(row_exc)
                b_l.append(0.0)
                b_u.append(0.0)

        # Compile constraints and variable bounds
        A = np.array(A_rows)
        constraints = LinearConstraint(A, b_l, b_u)
        integrality = np.ones(2 * M, dtype=int)
        bounds = Bounds(0.0, 1.0)

        res = milp(
            c=c_obj,
            integrality=integrality,
            constraints=constraints,
            bounds=bounds
        )

        if not res.success:
            logger.warning(f"MILP solve failed for objective {objective}: {res.status}")
            return None

        # Extract squad and captain
        y = np.round(res.x).astype(int)
        x_sel = y[:M]
        c_sel = y[M:2 * M]

        selected_indices = np.where(x_sel > 0)[0]
        captain_indices = np.where(c_sel > 0)[0]

        squad_df = df.iloc[selected_indices]
        squad_names = squad_df["web_name"].tolist()

        captain_name = df.iloc[captain_indices[0]]["web_name"] if len(captain_indices) > 0 else squad_names[0]
        total_cost = round(float(squad_df["now_cost"].sum()), 1)
        bank_remaining = round(max(0.0, self.rule_set.budget_cap - total_cost), 1)

        # Compute projected score (base xP sum + captain extra 1x)
        capt_xp = float(df.iloc[captain_indices[0]]["challenge_xP"]) if len(captain_indices) > 0 else 0.0
        projected_score = round(float(squad_df["challenge_xP"].sum() + capt_xp), 2)
        clubs_represented = int(squad_df["club"].nunique())

        # Determine formation string (e.g. 1-3-2)
        def_cnt = int((squad_df["position"] == "DEF").sum())
        mid_cnt = int((squad_df["position"] == "MID").sum())
        fwd_cnt = int((squad_df["position"] == "FWD").sum())
        formation = f"{def_cnt}-{mid_cnt}-{fwd_cnt}"

        return ChallengeOptimalSquad(
            gameweek=self.rule_set.gameweek,
            squad_names=squad_names,
            captain=captain_name,
            total_cost=total_cost,
            bank_remaining=bank_remaining,
            projected_score=projected_score,
            clubs_represented=clubs_represented,
            objective_name=objective,
            formation=formation,
            generator_type="MILP Dynamic Challenge"
        )

    def generate_candidate_pool(
        self,
        lock_players: Optional[List[str]] = None,
        exclude_players: Optional[List[str]] = None,
        available_only: bool = True
    ) -> List[ChallengeOptimalSquad]:
        """
        Stage 1 Multi-Objective MILP Screening:
        Solves across all 5 distinct tactical vectors and deduplicates by squad composition.
        """
        objectives = [
            "max_ev",
            "challenge_exploit",
            "differential_gpp",
            "team_stack",
            "maximum_variance"
        ]

        candidates: List[ChallengeOptimalSquad] = []
        seen_rosters: Set[Tuple[frozenset, str]] = set()

        for obj in objectives:
            sol = self.solve_single_vector(
                objective=obj,
                lock_players=lock_players,
                exclude_players=exclude_players,
                available_only=available_only
            )
            if sol:
                roster_key = (frozenset(sol.squad_names), sol.captain)
                if roster_key not in seen_rosters:
                    seen_rosters.add(roster_key)
                    candidates.append(sol)

        return candidates
