"""
analytics/challenge/optimizer.py
Stage 1: Parameterized Integer Linear Programming (MILP) Multi-Objective Solver for FPL Challenge.
Formulates dynamic weekly constraints (squad size N, dynamic club caps C, budget caps B, dynamic positional bounds,
and endogenous Captaincy & Vice-Captaincy enforcement: c_i + v_i <= x_i).
Solves across 7 Pareto tactical vectors with pre-solve active pool pruning to produce deduplicated candidate squads in <5ms.
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
    """Stage 1 MILP Solver for FPL Challenge mode with dynamic constraints and endogenous vice-captaincy."""

    PARETO_OBJECTIVES = [
        "max_ev",
        "challenge_exploit",
        "differential_gpp",
        "team_stack",
        "maximum_variance",
        "floor_safety",
        "cost_efficiency"
    ]

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

    def _find_player_indices(self, df_subset: pd.DataFrame, names: List[str]) -> List[int]:
        """Resolve player names to DataFrame indices within the active df_subset."""
        indices: List[int] = []
        for name in names:
            if not name:
                continue
            name_clean = name.strip().lower()
            m = df_subset[df_subset["web_name"].str.lower() == name_clean]
            if m.empty and "full_name" in df_subset.columns:
                m = df_subset[df_subset["full_name"].str.lower() == name_clean]
            if m.empty:
                m = df_subset[df_subset["web_name"].str.contains(name_clean, case=False, na=False)]
            if not m.empty:
                indices.append(int(m.index[0]))
        return list(set(indices))

    def _resolve_objective_weights(self, df_subset: pd.DataFrame, objective: str) -> np.ndarray:
        """Return player valuation weights for the given tactical vector across df_subset."""
        if objective == "max_ev":
            return df_subset["challenge_xP"].values
        elif objective == "challenge_exploit":
            return df_subset["exploit_score"].values
        elif objective == "differential_gpp":
            return df_subset["differential_score"].values
        elif objective == "team_stack":
            # Stack top scoring clubs or high xG assets
            top_clubs = df_subset.groupby("club")["challenge_xP"].sum().nlargest(4).index
            is_top_club = df_subset["club"].isin(top_clubs).astype(float).values
            return df_subset["challenge_xP"].values + 1.2 * is_top_club
        elif objective == "maximum_variance":
            return df_subset["boom_score"].values
        elif objective == "floor_safety":
            # Downside floor protection: mu - 0.75 * sigma (rewards nailed, secure performers)
            sigma_series = df_subset["sigma"] if "sigma" in df_subset.columns else (0.48 * df_subset["challenge_xP"] + 1.35)
            return np.maximum(0.1, df_subset["challenge_xP"].values - 0.75 * sigma_series.values)
        elif objective == "cost_efficiency":
            # Value-per-million enabler ratio: xP / (cost^0.75)
            costs = np.maximum(4.0, df_subset["now_cost"].values)
            return df_subset["challenge_xP"].values / (costs ** 0.75)
        else:
            return df_subset["challenge_xP"].values

    def solve_single_vector(
        self,
        objective: str = "max_ev",
        lock_players: Optional[List[str]] = None,
        exclude_players: Optional[List[str]] = None,
        available_only: bool = True
    ) -> Optional[ChallengeOptimalSquad]:
        """
        Solve single MILP instance for a specific objective vector with pre-solve active pool pruning
        and joint Captain + Vice-Captain endogenous selection.
        Decision variables y: length 3M.
        y[0:M] = x_i (squad selection)
        y[M:2M] = c_i (captaincy selection)
        y[2M:3M] = v_i (vice-captaincy selection)
        """
        # 1. Pre-solve Active Pool Pruning (Performance Optimization)
        # Keeps active players + any explicitly locked players, slashing decision space by ~60%
        df = self.df.copy()
        if available_only and "status" in df.columns:
            locked_set = {n.strip().lower() for n in (lock_players or []) if n}
            is_locked = df["web_name"].str.lower().isin(locked_set)
            if "full_name" in df.columns:
                is_locked = is_locked | df["full_name"].str.lower().isin(locked_set)

            is_active = (df["status"] == "a")
            if "chance_of_playing" in df.columns:
                is_active = is_active | (df["chance_of_playing"].fillna(100) >= 50)

            df = df[is_active | is_locked].reset_index(drop=True)

        M = len(df)
        if M == 0 or M < self.rule_set.squad_size:
            return None

        # Objective weights: maximize squad total + captain extra 1x + vice-captain priority 0.05x
        w = self._resolve_objective_weights(df, objective)
        c_obj = np.concatenate([-w, -w, -0.05 * w])

        A_rows: List[np.ndarray] = []
        b_l: List[float] = []
        b_u: List[float] = []

        # 1. Total squad size sum(x_i) = N
        row_squad = np.zeros(3 * M)
        row_squad[:M] = 1.0
        A_rows.append(row_squad)
        b_l.append(float(self.rule_set.squad_size))
        b_u.append(float(self.rule_set.squad_size))

        # 2. Captain count sum(c_i) = 1
        row_capt = np.zeros(3 * M)
        row_capt[M:2 * M] = 1.0
        A_rows.append(row_capt)
        b_l.append(1.0)
        b_u.append(1.0)

        # 3. Vice-Captain count sum(v_i) = 1
        row_vc = np.zeros(3 * M)
        row_vc[2 * M:3 * M] = 1.0
        A_rows.append(row_vc)
        b_l.append(1.0)
        b_u.append(1.0)

        # 4. Joint Captaincy & Vice-Captaincy Link & Disjointness:
        # c_i + v_i <= x_i  ==>  -x_i + c_i + v_i <= 0
        # Guarantees both Captain and VC are in squad and distinct from each other!
        for i in range(M):
            row_link = np.zeros(3 * M)
            row_link[i] = -1.0
            row_link[M + i] = 1.0
            row_link[2 * M + i] = 1.0
            A_rows.append(row_link)
            b_l.append(-np.inf)
            b_u.append(0.0)

        # 5. Budget constraint: sum(cost * x_i) <= budget_cap
        cost_arr = df["now_cost"].values
        row_budget = np.zeros(3 * M)
        row_budget[:M] = cost_arr
        A_rows.append(row_budget)
        b_l.append(0.0)
        b_u.append(float(self.rule_set.budget_cap))

        # 6. Position constraints from rule_set.allowed_positions
        all_canonical_positions = ["GKP", "DEF", "MID", "FWD"]
        for pos in all_canonical_positions:
            min_pos, max_pos = self.rule_set.get_position_bounds(pos)
            pos_mask = (df["position"] == pos).astype(float).values
            row_pos = np.zeros(3 * M)
            row_pos[:M] = pos_mask
            A_rows.append(row_pos)
            b_l.append(float(min_pos))
            b_u.append(float(max_pos))

        # 7. Dynamic Club Quotas: sum_{i in club} x_i <= max_per_team
        for club in df["club"].unique():
            club_mask = (df["club"] == club).astype(float).values
            row_club = np.zeros(3 * M)
            row_club[:M] = club_mask
            A_rows.append(row_club)
            b_l.append(0.0)
            b_u.append(float(self.rule_set.max_per_team))

        # 8. Locked players
        if lock_players:
            lock_indices = self._find_player_indices(df, lock_players)
            for idx in lock_indices:
                row_lock = np.zeros(3 * M)
                row_lock[idx] = 1.0
                A_rows.append(row_lock)
                b_l.append(1.0)
                b_u.append(1.0)

        # 9. Excluded players
        if exclude_players:
            exc_indices = self._find_player_indices(df, exclude_players)
            for idx in exc_indices:
                row_exc = np.zeros(3 * M)
                row_exc[idx] = 1.0
                A_rows.append(row_exc)
                b_l.append(0.0)
                b_u.append(0.0)

        # Compile constraints and variable bounds
        A = np.array(A_rows)
        constraints = LinearConstraint(A, b_l, b_u)
        integrality = np.ones(3 * M, dtype=int)
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

        # Extract squad, captain, and vice-captain
        y = np.round(res.x).astype(int)
        x_sel = y[:M]
        c_sel = y[M:2 * M]
        v_sel = y[2 * M:3 * M]

        selected_indices = np.where(x_sel > 0)[0]
        captain_indices = np.where(c_sel > 0)[0]
        vc_indices = np.where(v_sel > 0)[0]

        squad_df = df.iloc[selected_indices]
        squad_names = squad_df["web_name"].tolist()

        captain_name = df.iloc[captain_indices[0]]["web_name"] if len(captain_indices) > 0 else squad_names[0]
        if len(vc_indices) > 0:
            vice_captain_name = df.iloc[vc_indices[0]]["web_name"]
        else:
            remaining = [n for n in squad_names if n != captain_name]
            vice_captain_name = remaining[0] if remaining else captain_name

        total_cost = round(float(squad_df["now_cost"].sum()), 1)
        bank_remaining = round(max(0.0, self.rule_set.budget_cap - total_cost), 1)

        # Compute projected score (base xP sum + captain extra 1x)
        capt_xp = float(df.iloc[captain_indices[0]]["challenge_xP"]) if len(captain_indices) > 0 else 0.0
        projected_score = round(float(squad_df["challenge_xP"].sum() + capt_xp), 2)
        clubs_represented = int(squad_df["club"].nunique())

        # Determine formation string (e.g. 1-3-2 or 1-4-4-2)
        gkp_cnt = int((squad_df["position"] == "GKP").sum())
        def_cnt = int((squad_df["position"] == "DEF").sum())
        mid_cnt = int((squad_df["position"] == "MID").sum())
        fwd_cnt = int((squad_df["position"] == "FWD").sum())
        if gkp_cnt > 0:
            formation = f"{gkp_cnt}-{def_cnt}-{mid_cnt}-{fwd_cnt}"
        else:
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
            generator_type="MILP Dynamic Challenge",
            vice_captain=vice_captain_name
        )

    def _extract_sparse_covariance_pairs(
        self,
        df_subset: pd.DataFrame
    ) -> Tuple[List[Tuple[int, int, float]], np.ndarray]:
        """
        Extracts diagonal variances and sparse non-zero off-diagonal covariance pairs.
        Returns:
            coupled_pairs: List of (i, j, cov_ij)
            variances: np.ndarray of shape (M,)
        """
        M = len(df_subset)
        xP = df_subset["challenge_xP"].values
        sigmas = df_subset["sigma"].values if "sigma" in df_subset.columns else (0.48 * xP + 1.35)
        variances = sigmas ** 2

        clubs = df_subset["club"].values
        positions = df_subset["position"].values

        coupled_pairs: List[Tuple[int, int, float]] = []

        # Find intra-club teammate pairs
        for c in np.unique(clubs):
            club_indices = np.where(clubs == c)[0]
            if len(club_indices) < 2:
                continue
            for a_idx in range(len(club_indices)):
                for b_idx in range(a_idx + 1, len(club_indices)):
                    i = club_indices[a_idx]
                    j = club_indices[b_idx]
                    pos_i = positions[i]
                    pos_j = positions[j]

                    # Teammate correlation structure
                    if pos_i in ["DEF", "GKP"] and pos_j in ["DEF", "GKP"]:
                        rho = 0.45  # Strong clean sheet coupling
                    elif pos_i in ["MID", "FWD"] and pos_j in ["MID", "FWD"]:
                        rho = 0.15  # Attacking tempo / goal-assist coupling
                    else:
                        rho = 0.05  # General team tempo coupling

                    cov = float(rho * sigmas[i] * sigmas[j])
                    coupled_pairs.append((i, j, cov))

        return coupled_pairs, variances

    def solve_markowitz_portfolio(
        self,
        lambda_risk: float = 0.5,
        lock_players: Optional[List[str]] = None,
        exclude_players: Optional[List[str]] = None,
        available_only: bool = True
    ) -> Optional[ChallengeOptimalSquad]:
        """
        Mixed-Integer Quadratic Programming (MIQP) / Markowitz Mean-Variance Portfolio Optimizer.
        Maximizes:
            E[Points] - (lambda_risk / 2) * Var(Squad)
        Where:
            Var(Squad) = sum(sigma_i^2 * x_i) + 2 * sum_{(i,j) in E} Cov_{ij} * z_{ij}
        Using exact McCormick linearization for sparse coupled pairs:
            z_{ij} <= x_i,  z_{ij} <= x_j,  z_{ij} >= x_i + x_j - 1,  z_{ij} >= 0
        """
        df = self.df.copy()
        if available_only and "status" in df.columns:
            locked_set = {n.strip().lower() for n in (lock_players or []) if n}
            is_locked = df["web_name"].str.lower().isin(locked_set)
            if "full_name" in df.columns:
                is_locked = is_locked | df["full_name"].str.lower().isin(locked_set)

            is_active = (df["status"] == "a")
            if "chance_of_playing" in df.columns:
                is_active = is_active | (df["chance_of_playing"].fillna(100) >= 50)

            df = df[is_active | is_locked].reset_index(drop=True)

        M = len(df)
        if M == 0 or M < self.rule_set.squad_size:
            return None

        # Extract sparse covariance pairs
        coupled_pairs, variances = self._extract_sparse_covariance_pairs(df)
        K = len(coupled_pairs)
        n_vars = 3 * M + K

        mu = df["challenge_xP"].values
        diag_pen = 0.5 * lambda_risk * variances

        # c_obj minimizes -utility:
        c_obj = np.zeros(n_vars)
        c_obj[:M] = -(mu - diag_pen)
        c_obj[M:2 * M] = -mu
        c_obj[2 * M:3 * M] = -0.05 * mu

        for k, (i, j, cov_ij) in enumerate(coupled_pairs):
            c_obj[3 * M + k] = lambda_risk * cov_ij

        A_rows: List[np.ndarray] = []
        b_l: List[float] = []
        b_u: List[float] = []

        # 1. Total squad size sum(x_i) = N
        row_squad = np.zeros(n_vars)
        row_squad[:M] = 1.0
        A_rows.append(row_squad)
        b_l.append(float(self.rule_set.squad_size))
        b_u.append(float(self.rule_set.squad_size))

        # 2. Captain count sum(c_i) = 1
        row_capt = np.zeros(n_vars)
        row_capt[M:2 * M] = 1.0
        A_rows.append(row_capt)
        b_l.append(1.0)
        b_u.append(1.0)

        # 3. Vice-Captain count sum(v_i) = 1
        row_vc = np.zeros(n_vars)
        row_vc[2 * M:3 * M] = 1.0
        A_rows.append(row_vc)
        b_l.append(1.0)
        b_u.append(1.0)

        # 4. Joint Captaincy & Vice-Captaincy Link & Disjointness: c_i + v_i <= x_i
        for i in range(M):
            row_link = np.zeros(n_vars)
            row_link[i] = -1.0
            row_link[M + i] = 1.0
            row_link[2 * M + i] = 1.0
            A_rows.append(row_link)
            b_l.append(-np.inf)
            b_u.append(0.0)

        # 5. Budget constraint: sum(cost * x_i) <= budget_cap
        cost_arr = df["now_cost"].values
        row_budget = np.zeros(n_vars)
        row_budget[:M] = cost_arr
        A_rows.append(row_budget)
        b_l.append(0.0)
        b_u.append(float(self.rule_set.budget_cap))

        # 6. Position constraints from rule_set.allowed_positions
        all_canonical_positions = ["GKP", "DEF", "MID", "FWD"]
        for pos in all_canonical_positions:
            min_pos, max_pos = self.rule_set.get_position_bounds(pos)
            pos_mask = (df["position"] == pos).astype(float).values
            row_pos = np.zeros(n_vars)
            row_pos[:M] = pos_mask
            A_rows.append(row_pos)
            b_l.append(float(min_pos))
            b_u.append(float(max_pos))

        # 7. Dynamic Club Quotas: sum_{i in club} x_i <= max_per_team
        for club in df["club"].unique():
            club_mask = (df["club"] == club).astype(float).values
            row_club = np.zeros(n_vars)
            row_club[:M] = club_mask
            A_rows.append(row_club)
            b_l.append(0.0)
            b_u.append(float(self.rule_set.max_per_team))

        # 8. McCormick Linearization Constraints for z_k = x_i * x_j
        for k, (i, j, _) in enumerate(coupled_pairs):
            var_k = 3 * M + k
            # z_k <= x_i  ==> -x_i + z_k <= 0
            row_m1 = np.zeros(n_vars)
            row_m1[i] = -1.0
            row_m1[var_k] = 1.0
            A_rows.append(row_m1)
            b_l.append(-np.inf)
            b_u.append(0.0)

            # z_k <= x_j  ==> -x_j + z_k <= 0
            row_m2 = np.zeros(n_vars)
            row_m2[j] = -1.0
            row_m2[var_k] = 1.0
            A_rows.append(row_m2)
            b_l.append(-np.inf)
            b_u.append(0.0)

            # z_k >= x_i + x_j - 1 ==> -x_i - x_j + z_k >= -1
            row_m3 = np.zeros(n_vars)
            row_m3[i] = -1.0
            row_m3[j] = -1.0
            row_m3[var_k] = 1.0
            A_rows.append(row_m3)
            b_l.append(-1.0)
            b_u.append(np.inf)

        # 9. Locked players
        if lock_players:
            lock_indices = self._find_player_indices(df, lock_players)
            for idx in lock_indices:
                row_lock = np.zeros(n_vars)
                row_lock[idx] = 1.0
                A_rows.append(row_lock)
                b_l.append(1.0)
                b_u.append(1.0)

        # 10. Excluded players
        if exclude_players:
            exc_indices = self._find_player_indices(df, exclude_players)
            for idx in exc_indices:
                row_exc = np.zeros(n_vars)
                row_exc[idx] = 1.0
                A_rows.append(row_exc)
                b_l.append(0.0)
                b_u.append(0.0)

        # Compile constraints and variable bounds
        A = np.array(A_rows)
        constraints = LinearConstraint(A, b_l, b_u)
        integrality = np.ones(n_vars, dtype=int)
        bounds = Bounds(0.0, 1.0)

        res = milp(
            c=c_obj,
            integrality=integrality,
            constraints=constraints,
            bounds=bounds
        )

        if not res.success:
            logger.warning(f"Markowitz MIQP solve failed for lambda={lambda_risk}: {res.status}")
            return None

        # Extract solution
        y = np.round(res.x).astype(int)
        x_sel = y[:M]
        c_sel = y[M:2 * M]
        v_sel = y[2 * M:3 * M]

        selected_indices = np.where(x_sel > 0)[0]
        captain_indices = np.where(c_sel > 0)[0]
        vc_indices = np.where(v_sel > 0)[0]

        squad_df = df.iloc[selected_indices]
        squad_names = squad_df["web_name"].tolist()

        captain_name = df.iloc[captain_indices[0]]["web_name"] if len(captain_indices) > 0 else squad_names[0]
        if len(vc_indices) > 0:
            vice_captain_name = df.iloc[vc_indices[0]]["web_name"]
        else:
            remaining = [n for n in squad_names if n != captain_name]
            vice_captain_name = remaining[0] if remaining else captain_name

        total_cost = round(float(squad_df["now_cost"].sum()), 1)
        bank_remaining = round(max(0.0, self.rule_set.budget_cap - total_cost), 1)

        capt_xp = float(df.iloc[captain_indices[0]]["challenge_xP"]) if len(captain_indices) > 0 else 0.0
        projected_score = round(float(squad_df["challenge_xP"].sum() + capt_xp), 2)
        clubs_represented = int(squad_df["club"].nunique())

        gkp_cnt = int((squad_df["position"] == "GKP").sum())
        def_cnt = int((squad_df["position"] == "DEF").sum())
        mid_cnt = int((squad_df["position"] == "MID").sum())
        fwd_cnt = int((squad_df["position"] == "FWD").sum())
        formation = f"{gkp_cnt}-{def_cnt}-{mid_cnt}-{fwd_cnt}" if gkp_cnt > 0 else f"{def_cnt}-{mid_cnt}-{fwd_cnt}"

        obj_label = f"markowitz_lambda_{lambda_risk:+.2f}"

        return ChallengeOptimalSquad(
            gameweek=self.rule_set.gameweek,
            squad_names=squad_names,
            captain=captain_name,
            total_cost=total_cost,
            bank_remaining=bank_remaining,
            projected_score=projected_score,
            clubs_represented=clubs_represented,
            objective_name=obj_label,
            formation=formation,
            generator_type="Markowitz MIQP",
            vice_captain=vice_captain_name
        )

    def generate_candidate_pool(
        self,
        lock_players: Optional[List[str]] = None,
        exclude_players: Optional[List[str]] = None,
        available_only: bool = True
    ) -> List[ChallengeOptimalSquad]:
        """
        Stage 1 Multi-Objective MILP Screening:
        Solves across 7 Pareto vectors + Markowitz Efficient Frontier sweeps (lambda in [-0.4, 0.5, 1.2]).
        """
        candidates: List[ChallengeOptimalSquad] = []
        seen_rosters: Set[Tuple[frozenset, str, str]] = set()

        # 1. Standard Pareto Tactical Vectors
        for obj in self.PARETO_OBJECTIVES:
            sol = self.solve_single_vector(
                objective=obj,
                lock_players=lock_players,
                exclude_players=exclude_players,
                available_only=available_only
            )
            if sol:
                roster_key = (frozenset(sol.squad_names), sol.captain, sol.vice_captain)
                if roster_key not in seen_rosters:
                    seen_rosters.add(roster_key)
                    candidates.append(sol)

        # 2. Markowitz Mean-Variance Efficient Frontier Sweeps (Upside Stacking -> Balanced -> Safety Floor)
        for l_val in [-0.40, 0.50, 1.20]:
            sol_m = self.solve_markowitz_portfolio(
                lambda_risk=l_val,
                lock_players=lock_players,
                exclude_players=exclude_players,
                available_only=available_only
            )
            if sol_m:
                roster_key = (frozenset(sol_m.squad_names), sol_m.captain, sol_m.vice_captain)
                if roster_key not in seen_rosters:
                    seen_rosters.add(roster_key)
                    candidates.append(sol_m)

        return candidates
