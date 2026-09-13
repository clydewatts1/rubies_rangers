"""
Moneyball Mathematical FPL Squad Optimizer
Uses Mixed-Integer Linear Programming (MILP via scipy.optimize) to:
1. Optimize an entire 15-player FPL squad from scratch.
2. Find the optimal 1, 2, or 3 transfers to modify an existing team under budget.
3. Obey official FPL constraints: 2 GKP, 5 DEF, 5 MID, 3 FWD, max 3 players per club.
4. Filter out injured or departed players.
"""

import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds
from typing import List, Dict, Any, Optional, Tuple

from config_manager import get_params


class FPLOptimizer:
    def __init__(self, players_df: pd.DataFrame):
        self.df = players_df.copy().reset_index(drop=True)
        # Ensure numeric columns
        for col in ["now_cost", "total_points", "form", "points_per_game", 
                    "moneyball_score", "fdr_moneyball_score", "setpiece_moneyball_score", 
                    "forward_moneyball_score", "weather_moneyball_score", "expected_goal_involvements_per_90"]:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors="coerce").fillna(0.0)

    def _resolve_objective(self, objective: str) -> np.ndarray:
        """Return objective weights vector (we minimize -weights to maximize score)."""
        if objective in ["setpiece", "setpiece_moneyball"]:
            if "setpiece_moneyball_score" in self.df.columns:
                return -self.df["setpiece_moneyball_score"].values
            elif "fdr_moneyball_score" in self.df.columns:
                return -self.df["fdr_moneyball_score"].values
            return -self.df["moneyball_score"].values
        elif objective in ["forward", "forward_moneyball", "forward_alpha"]:
            if "forward_moneyball_score" in self.df.columns:
                return -self.df["forward_moneyball_score"].values
            elif "fdr_moneyball_score" in self.df.columns:
                return -self.df["fdr_moneyball_score"].values
            return -self.df["moneyball_score"].values
        elif objective in ["weather", "weather_moneyball", "weather_alpha", "weather_resilience"]:
            if "weather_moneyball_score" in self.df.columns:
                return -self.df["weather_moneyball_score"].values
            elif "fdr_moneyball_score" in self.df.columns:
                return -self.df["fdr_moneyball_score"].values
            return -self.df["moneyball_score"].values
        elif objective in ["fdr", "fdr_moneyball", "fixtures"]:
            if "fdr_moneyball_score" in self.df.columns:
                return -self.df["fdr_moneyball_score"].values
            return -self.df["moneyball_score"].values
        elif objective == "points":
            return -self.df["total_points"].values
        elif objective == "form":
            return -self.df["form"].values
        elif objective == "xgi":
            return -self.df["expected_goal_involvements_per_90"].values
        else:  # moneyball (default)
            return -self.df["moneyball_score"].values

    def _find_player_indices(self, name_list: List[str]) -> List[int]:
        """Resolve a list of player names to unique dataframe row indices with exact match priority."""
        indices = []
        for name in name_list:
            # 1. Exact web_name
            m = self.df[self.df["web_name"].str.lower() == name.lower()]
            if m.empty:
                # 2. Exact full_name
                m = self.df[self.df["full_name"].str.lower() == name.lower()]
            if m.empty:
                # 3. Contains in web_name
                m = self.df[self.df["web_name"].str.contains(name, case=False, na=False)]
            if m.empty:
                # 4. Contains in full_name
                m = self.df[self.df["full_name"].str.contains(name, case=False, na=False)]
            if not m.empty:
                if len(m) > 1 and "total_points" in m.columns:
                    m = m.sort_values(by="total_points", ascending=False)
                indices.append(m.index[0])
        return list(set(indices))

    def optimize_squad(
        self,
        budget: Optional[float] = None,
        objective: str = "moneyball",
        lock_players: Optional[List[str]] = None,
        exclude_players: Optional[List[str]] = None,
        available_only: bool = True,
        min_penalty_takers: int = 0
    ) -> Dict[str, Any]:
        """
        Draft an optimal 15-player team from scratch.
        """
        opt_cfg = get_params("optimizer")
        target_budget = budget if budget is not None else float(opt_cfg.get("budget", 100.0))
        max_club = int(opt_cfg.get("max_players_per_club", 3))
        pos_quotas = opt_cfg.get("position_quotas", {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3})

        df = self.df.copy()
        n = len(df)
        c = self._resolve_objective(objective)

        A_rows = []
        b_l = []
        b_u = []

        # 1. Budget constraint: sum(cost * x_i) <= budget
        A_rows.append(df["now_cost"].values)
        b_l.append(0.0)
        b_u.append(target_budget)

        # 2. Position constraints from config
        for pos, req_count in pos_quotas.items():
            A_rows.append((df["position_name"] == pos).astype(float).values)
            b_l.append(float(req_count))
            b_u.append(float(req_count))

        # 3. Club constraint: <= max_club per club
        for club in df["club_name"].unique():
            A_rows.append((df["club_name"] == club).astype(float).values)
            b_l.append(0.0)
            b_u.append(float(max_club))


        # 4. Filter unavailable players if requested
        if available_only and "status" in df.columns:
            unavail_mask = (df["status"] != "a").astype(float).values
            A_rows.append(unavail_mask)
            b_l.append(0.0)
            b_u.append(0.0)

        # 5. Locked players
        if lock_players:
            lock_indices = self._find_player_indices(lock_players)
            for idx in lock_indices:
                mask = np.zeros(n)
                mask[idx] = 1.0
                A_rows.append(mask)
                b_l.append(1.0)
                b_u.append(1.0)

        # 6. Excluded players
        if exclude_players:
            exc_indices = self._find_player_indices(exclude_players)
            for idx in exc_indices:
                mask = np.zeros(n)
                mask[idx] = 1.0
                A_rows.append(mask)
                b_l.append(0.0)
                b_u.append(0.0)

        # 7. Penalty taker requirement
        if min_penalty_takers > 0 and "is_penalty_taker" in df.columns:
            pen_mask = df["is_penalty_taker"].astype(float).values
            A_rows.append(pen_mask)
            b_l.append(float(min_penalty_takers))
            b_u.append(15.0)

        A = np.array(A_rows)
        constraints = LinearConstraint(A, b_l, b_u)
        bounds = Bounds(0, 1)
        integrality = np.ones(n)

        res = milp(c=c, integrality=integrality, constraints=constraints, bounds=bounds)
        if not res.success:
            return {"success": False, "status": res.status, "message": "Optimization failed to converge"}

        selected_idx = np.where(res.x > 0.5)[0]
        selected_df = df.iloc[selected_idx].copy().sort_values(
            by=["position_name", "now_cost"], ascending=[True, False]
        )

        return {
            "success": True,
            "squad": selected_df,
            "total_cost": round(float(selected_df["now_cost"].sum()), 1),
            "bank_remaining": round(budget - float(selected_df["now_cost"].sum()), 1),
            "total_points": int(selected_df["total_points"].sum()),
            "total_moneyball_score": round(float(selected_df["moneyball_score"].sum()), 1),
            "objective_value": -res.fun
        }

    def optimize_transfers(
        self,
        current_player_names: List[str],
        bank_balance: float = 0.0,
        max_transfers: int = 1,
        objective: str = "moneyball",
        available_only: bool = True,
        lock_players: Optional[List[str]] = None,
        exclude_players: Optional[List[str]] = None,
        min_penalty_takers: int = 0
    ) -> Dict[str, Any]:
        """
        Find the optimal transfers to modify an existing team under budget.
        """
        df = self.df.copy()
        n = len(df)

        # Find current player indices with exact matching priority
        current_indices = self._find_player_indices(current_player_names)
        if len(current_indices) < 11:
            return {
                "success": False,
                "message": f"Only found {len(current_indices)} of the requested players in the dataset."
            }

        current_df = df.loc[current_indices]
        current_team_value = float(current_df["now_cost"].sum())
        total_budget = round(current_team_value + bank_balance, 1)

        c = self._resolve_objective(objective)

        A_rows = []
        b_l = []
        b_u = []

        # 1. Budget constraint: total cost <= current squad value + bank
        A_rows.append(df["now_cost"].values)
        b_l.append(0.0)
        b_u.append(total_budget)

        opt_cfg = get_params("optimizer")
        max_club = int(opt_cfg.get("max_players_per_club", 3))
        pos_quotas = opt_cfg.get("position_quotas", {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3})

        # 2. Position constraints from config
        for pos, req_count in pos_quotas.items():
            A_rows.append((df["position_name"] == pos).astype(float).values)
            b_l.append(float(req_count))
            b_u.append(float(req_count))

        # 3. Club constraint: <= max_club per club
        for club in df["club_name"].unique():
            A_rows.append((df["club_name"] == club).astype(float).values)
            b_l.append(0.0)
            b_u.append(float(max_club))


        # 4. Keep constraint: Keep at least (15 - max_transfers) of current players
        keep_row = np.zeros(n)
        keep_row[current_indices] = 1.0
        A_rows.append(keep_row)
        b_l.append(len(current_indices) - max_transfers)
        b_u.append(len(current_indices))

        # 5. Availability filter
        if available_only and "status" in df.columns:
            unavail_mask = (df["status"] != "a").astype(float).values
            A_rows.append(unavail_mask)
            b_l.append(0.0)
            b_u.append(0.0)

        # 6. Locked players
        if lock_players:
            lock_indices = self._find_player_indices(lock_players)
            for idx in lock_indices:
                mask = np.zeros(n)
                mask[idx] = 1.0
                A_rows.append(mask)
                b_l.append(1.0)
                b_u.append(1.0)

        # 7. Excluded players
        if exclude_players:
            exc_indices = self._find_player_indices(exclude_players)
            for idx in exc_indices:
                mask = np.zeros(n)
                mask[idx] = 1.0
                A_rows.append(mask)
                b_l.append(0.0)
                b_u.append(0.0)

        # 8. Penalty taker requirement
        if min_penalty_takers > 0 and "is_penalty_taker" in df.columns:
            pen_mask = df["is_penalty_taker"].astype(float).values
            A_rows.append(pen_mask)
            b_l.append(float(min_penalty_takers))
            b_u.append(15.0)

        A = np.array(A_rows)
        constraints = LinearConstraint(A, b_l, b_u)
        bounds = Bounds(0, 1)
        integrality = np.ones(n)

        res = milp(c=c, integrality=integrality, constraints=constraints, bounds=bounds)
        if not res.success:
            return {"success": False, "status": res.status, "message": "No valid transfer solution found"}

        sel_idx = np.where(res.x > 0.5)[0]
        out_idx = [i for i in current_indices if i not in sel_idx]
        in_idx = [i for i in sel_idx if i not in current_indices]

        transfers_out = df.loc[out_idx].copy()
        transfers_in = df.loc[in_idx].copy()
        new_squad = df.loc[sel_idx].copy()

        score_gain = transfers_in["moneyball_score"].sum() - transfers_out["moneyball_score"].sum()
        points_gain = transfers_in["total_points"].sum() - transfers_out["total_points"].sum()
        cost_diff = transfers_in["now_cost"].sum() - transfers_out["now_cost"].sum()
        new_bank = round(bank_balance - cost_diff, 1)

        return {
            "success": True,
            "transfers_out": transfers_out,
            "transfers_in": transfers_in,
            "new_squad": new_squad,
            "squad": new_squad,
            "score_gain": round(float(score_gain), 2),
            "points_gain": int(points_gain),
            "new_bank": new_bank,
            "total_team_cost": round(float(new_squad["now_cost"].sum()), 1)
        }

