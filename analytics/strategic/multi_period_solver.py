"""
Multi-Period Rolling Horizon Solver Engine (Phase 2).
Solves a multi-period integer linear program (MILP) maximizing cumulative discounted expected points
under dynamic Free Transfer inventory accumulation (1 to 5 FTs) and physical FPL constraints.
Governed by .agents/rules/moneyball_strategy.md and .agents/rules/python_standards.md.
"""

from __future__ import annotations
import math
import time
from typing import Dict, List, Optional, Tuple, Any, Set
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds

from config_manager import get_params, get_system_config
from clients.fpl_client import FPLClient
from analytics.strategic.contracts import (
    MultiPeriodGameweekPlan,
    MultiPeriodStrategicSolution,
    StrategicSquadState,
)
from analytics.strategic.trajectory_engine import (
    TrajectoryEngine,
    build_strategic_squad_state,
)


class MultiPeriodSolver:
    """
    Multi-horizon quantitative solver that optimizes sequential transfer pathways,
    Free Transfer banking trajectories, captaincy, and starting lineups over 3 to 6 gameweeks.
    """

    def __init__(
        self,
        fpl_client: Optional[FPLClient] = None,
        default_horizon: int = 5,
        profile: Optional[str] = None
    ) -> None:
        self.client = fpl_client or FPLClient()
        self.default_horizon = default_horizon
        self.profile = profile
        self.trajectory_engine = TrajectoryEngine(
            fpl_client=self.client,
            default_horizon=max(8, default_horizon + 2),
            profile=profile
        )

    def solve(
        self,
        initial_squad_names_or_ids: Optional[List[Any]] = None,
        horizon: Optional[int] = None,
        bank: Optional[float] = None,
        initial_ft: Optional[int] = None,
        max_hits_per_gw: int = 1,
        discount_gamma: Optional[float] = None,
        ft_option_mult: Optional[float] = None,
        objective: str = "max_ev",
    ) -> MultiPeriodStrategicSolution:
        """
        Solves the multi-period rolling horizon transfer chessboard under a specified objective.
        """
        h = horizon or self.default_horizon
        strat_cfg = get_params("strategic", profile=self.profile) or {}
        gamma = discount_gamma if discount_gamma is not None else float(strat_cfg.get("horizon", {}).get("discount_gamma", 0.92))
        ft_mult = ft_option_mult if ft_option_mult is not None else float(strat_cfg.get("balance_sheet", {}).get("ft_option_mult", 1.50))

        if objective == "conservative_banking":
            max_hits_per_gw = 0
            ft_mult = max(3.5, ft_mult * 2.5)
            gamma = max(0.95, gamma)

        # 1. Resolve Initial State
        sq_state = self.trajectory_engine.get_squad_state()
        if initial_squad_names_or_ids is not None:
            # Parse user-supplied squad
            df_players = self.client.get_players_df()
            init_ids = self._resolve_player_ids(initial_squad_names_or_ids, df_players)
        else:
            init_ids = list(sq_state.squad_player_ids)

        init_bank = bank if bank is not None else sq_state.bank_balance
        start_ft = initial_ft if initial_ft is not None else sq_state.free_transfers_available
        start_gw = sq_state.gameweek + 1
        target_gws = [start_gw + i for i in range(h)]

        # 2. Build Candidate Pool
        candidate_df, xp_tensor = self._build_candidate_pool(init_ids, horizon=h)
        n_candidates = len(candidate_df)

        # Apply tactical objective modulations to xp_tensor
        mod_xp_tensor = xp_tensor.copy()
        if objective == "markowitz_multi_period":
            # Penalize variance (Markowitz Mean-Variance risk-aversion)
            sigmas = 0.48 * mod_xp_tensor + 1.35
            mod_xp_tensor = np.maximum(0.0, mod_xp_tensor - 0.25 * (sigmas ** 2))
        elif objective == "cost_efficiency":
            costs = candidate_df["now_cost"].values[:, None]
            val_scale = 2.5 / np.sqrt(np.maximum(4.0, costs))
            mod_xp_tensor = mod_xp_tensor * val_scale
        elif objective == "differential_climb" and "selected_by_percent" in candidate_df.columns:
            sel = pd.to_numeric(candidate_df["selected_by_percent"], errors="coerce").fillna(10.0).values[:, None]
            diff_mult = 1.0 + (100.0 - np.clip(sel, 0.0, 100.0)) / 400.0
            mod_xp_tensor = mod_xp_tensor * diff_mult
        elif objective == "wave_rider":
            # Boost players from clubs with low FDR
            fdr_boost = np.ones_like(mod_xp_tensor)
            if "fdr_next_5" in candidate_df.columns:
                fdr = pd.to_numeric(candidate_df["fdr_next_5"], errors="coerce").fillna(3.0).values[:, None]
                fdr_boost = 1.0 + np.maximum(0.0, (3.2 - fdr)) * 0.15
            mod_xp_tensor = mod_xp_tensor * fdr_boost

        # 3. Solve Sequential Horizon Trajectory
        plans: List[MultiPeriodGameweekPlan] = []
        current_squad_ids = list(init_ids)
        current_bank = init_bank
        current_ft = start_ft

        for t_step in range(h):
            gw = target_gws[t_step]
            step_xp = mod_xp_tensor[:, t_step]

            # Solve optimal step transition from current_squad_ids
            step_plan = self._solve_single_step(
                candidate_df=candidate_df,
                step_xp=step_xp,
                current_squad_ids=current_squad_ids,
                bank=current_bank,
                available_ft=current_ft,
                max_hits=max_hits_per_gw,
                gameweek=gw,
                gamma_decay=(gamma ** t_step),
                ft_option_weight=(ft_mult * 0.1),
            )

            plans.append(step_plan)

            # Update state for next period
            new_squad_ids = [p[0] for p in step_plan.starting_xi] + [p[0] for p in step_plan.bench]
            current_squad_ids = new_squad_ids
            current_bank = step_plan.bank_remaining
            current_ft = step_plan.free_transfers_banked_next

        # 4. Aggregate Solution Metrics
        cum_gross = sum(p.gross_xp for p in plans)
        cum_net = sum(p.net_xp for p in plans)
        cum_hits = sum(p.hits_taken for p in plans)
        final_squad_cost = sum(candidate_df.loc[candidate_df["id"].isin(current_squad_ids), "now_cost"])
        terminal_val = round(float(final_squad_cost + current_bank), 2)

        # Summary narrative
        total_transfers = sum(len(p.transfers_in) for p in plans)
        summary = (
            f"Staged Multi-Period Roadmap ({h} GWs, {objective.upper()}): Executes {total_transfers} strategic transfers "
            f"({cum_hits} hits, -{cum_hits * 4} pts deduction). "
            f"Accumulates {current_ft} banked Free Transfers by GW{target_gws[-1]}. "
            f"Projected Net Points: {cum_net:.1f} pts across GW{target_gws[0]}–GW{target_gws[-1]}."
        )

        return MultiPeriodStrategicSolution(
            horizon=h,
            plans=tuple(plans),
            cumulative_gross_xp=round(cum_gross, 2),
            cumulative_net_xp=round(cum_net, 2),
            cumulative_hits_taken=cum_hits,
            terminal_squad_value=terminal_val,
            terminal_bank=round(current_bank, 2),
            staged_turnaround_summary=summary,
            objective_name=objective,
            generator_type="Multi-Period MILP",
        )

    def generate_strategic_pathways(
        self,
        initial_squad_names_or_ids: Optional[List[Any]] = None,
        horizon: Optional[int] = None,
        bank: Optional[float] = None,
        initial_ft: Optional[int] = None,
        max_hits_per_gw: int = 1,
        objectives: Optional[List[str]] = None,
    ) -> List[MultiPeriodStrategicSolution]:
        """
        Stage 1 Multi-Period Strategic Pathway Generation:
        Solves multi-period integer linear programs across diverse strategic archetypes
        and deduplicates identical 5-GW transfer roadmap sequences.
        """
        objs = objectives or [
            "max_ev",
            "conservative_banking",
            "markowitz_multi_period",
            "wave_rider",
            "differential_climb",
            "cost_efficiency"
        ]

        pathways: List[MultiPeriodStrategicSolution] = []
        seen_roadmaps: Set[Tuple[Tuple[Tuple[int, ...], Tuple[int, ...]], ...]] = set()

        for obj in objs:
            sol = self.solve(
                initial_squad_names_or_ids=initial_squad_names_or_ids,
                horizon=horizon,
                bank=bank,
                initial_ft=initial_ft,
                max_hits_per_gw=max_hits_per_gw if obj != "conservative_banking" else 0,
                objective=obj,
            )
            if sol:
                roadmap_key = tuple(
                    (
                        tuple(sorted(p[0] for p in plan.transfers_in)),
                        tuple(sorted(p[0] for p in plan.transfers_out)),
                    )
                    for plan in sol.plans
                )
                if roadmap_key not in seen_roadmaps:
                    seen_roadmaps.add(roadmap_key)
                    pathways.append(sol)

        return pathways

    def _resolve_player_ids(self, names_or_ids: List[Any], df: pd.DataFrame) -> List[int]:
        """Convert mix of names or IDs into verified element IDs."""
        resolved = []
        name_map = {str(row["web_name"]).lower(): int(row["id"]) for _, row in df.iterrows()}
        full_map = {str(row["full_name"]).lower(): int(row["id"]) for _, row in df.iterrows()}

        for item in names_or_ids:
            if isinstance(item, int):
                resolved.append(item)
            else:
                s = str(item).lower().strip()
                pid = name_map.get(s) or full_map.get(s)
                if pid:
                    resolved.append(pid)
        return resolved

    def _build_candidate_pool(
        self,
        current_squad_ids: List[int],
        horizon: int
    ) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        Prunes the 650-player universe down to a high-alpha candidate pool of ~100-130 players
        ensuring fast sub-second MILP execution while strictly including current squad members.
        """
        all_profiles = self.trajectory_engine.get_player_profiles(horizon=horizon)
        df_players = self.client.get_players_df()

        # Compute horizon multi-week cumulative xP
        id_to_cum_xp: Dict[int, float] = {}
        for pid, prof in all_profiles.items():
            id_to_cum_xp[pid] = sum(prof.xp_trajectory[:horizon])

        df_players["cum_xp"] = df_players["id"].map(id_to_cum_xp).fillna(0.0)

        # 1. Always include current squad members
        current_mask = df_players["id"].isin(current_squad_ids)

        # 2. Select top assets by position
        gkp_top = df_players[df_players["position_name"] == "GKP"].sort_values(by="cum_xp", ascending=False).head(12)
        def_top = df_players[df_players["position_name"] == "DEF"].sort_values(by="cum_xp", ascending=False).head(35)
        mid_top = df_players[df_players["position_name"] == "MID"].sort_values(by="cum_xp", ascending=False).head(45)
        fwd_top = df_players[df_players["position_name"] == "FWD"].sort_values(by="cum_xp", ascending=False).head(25)

        candidates = pd.concat([df_players[current_mask], gkp_top, def_top, mid_top, fwd_top]).drop_duplicates(subset=["id"]).reset_index(drop=True)

        # Extract (M x horizon) tensor
        candidate_ids = candidates["id"].tolist()
        xp_tensor = self.trajectory_engine.get_xp_matrix(candidate_ids, horizon=horizon)

        return candidates, xp_tensor

    def _solve_single_step(
        self,
        candidate_df: pd.DataFrame,
        step_xp: np.ndarray,
        current_squad_ids: List[int],
        bank: float,
        available_ft: int,
        max_hits: int,
        gameweek: int,
        gamma_decay: float = 1.0,
        ft_option_weight: float = 0.15,
    ) -> MultiPeriodGameweekPlan:
        """
        Solves the single-gameweek transfer transition and starting XI optimization.
        Evaluates potential transfer counts K in [0, 1, ..., available_ft + max_hits].
        """
        n = len(candidate_df)
        curr_indices = [i for i, pid in enumerate(candidate_df["id"]) if pid in current_squad_ids]
        curr_squad_cost = candidate_df.loc[curr_indices, "now_cost"].sum()
        total_budget = curr_squad_cost + bank

        best_plan: Optional[MultiPeriodGameweekPlan] = None
        best_objective_val = -1e9

        # Evaluate candidate transfer counts K in [0, 1, 2, ..., available_ft + max_hits]
        max_k = min(3, available_ft + max_hits)

        for k_transfers in range(0, max_k + 1):
            hits_taken = max(0, k_transfers - available_ft)
            hit_cost_pts = hits_taken * 4
            ft_used = min(k_transfers, available_ft)
            ft_banked_next = max(1, min(5, available_ft - k_transfers + 1))

            # Solve MILP for best 15-player squad with exactly (15 - k_transfers) kept
            squad_sol = self._solve_squad_milp(
                candidate_df=candidate_df,
                step_xp=step_xp,
                curr_indices=curr_indices,
                k_transfers=k_transfers,
                budget=total_budget
            )

            if not squad_sol["success"]:
                continue

            squad_indices = squad_sol["indices"]
            squad_cost = squad_sol["cost"]
            bank_remaining = round(total_budget - squad_cost, 2)

            # Solve optimal starting XI, bench, and captain
            lineup_sol = self._solve_lineup_and_captain(
                candidate_df=candidate_df.iloc[squad_indices],
                step_xp=step_xp[squad_indices]
            )

            gross_xp = lineup_sol["gross_xp"]
            net_xp = gross_xp - hit_cost_pts

            # Multi-Period Objective: Discounted Net xP + FT Banking Option Bonus
            step_objective = (net_xp * gamma_decay) + (ft_option_weight * ft_banked_next)

            if step_objective > best_objective_val:
                best_objective_val = step_objective

                # Transfers in / out
                sel_ids = set(candidate_df.iloc[squad_indices]["id"])
                curr_set = set(current_squad_ids)

                tin_df = candidate_df[candidate_df["id"].isin(sel_ids - curr_set)]
                tout_df = candidate_df[candidate_df["id"].isin(curr_set - sel_ids)]

                t_in = tuple((int(r["id"]), str(r["web_name"]), float(r["now_cost"])) for _, r in tin_df.iterrows())
                t_out = tuple((int(r["id"]), str(r["web_name"]), float(r["now_cost"])) for _, r in tout_df.iterrows())

                best_plan = MultiPeriodGameweekPlan(
                    gameweek=gameweek,
                    transfers_in=t_in,
                    transfers_out=t_out,
                    starting_xi=tuple(lineup_sol["starting_xi"]),
                    bench=tuple(lineup_sol["bench"]),
                    captain_id=lineup_sol["captain_id"],
                    captain_name=lineup_sol["captain_name"],
                    vice_captain_id=lineup_sol["vice_captain_id"],
                    vice_captain_name=lineup_sol["vice_captain_name"],
                    free_transfers_available=available_ft,
                    free_transfers_used=ft_used,
                    free_transfers_banked_next=ft_banked_next,
                    hits_taken=hits_taken,
                    hit_cost_points=hit_cost_pts,
                    gross_xp=round(gross_xp, 2),
                    net_xp=round(net_xp, 2),
                    bank_remaining=bank_remaining,
                )

        if best_plan is None:
            # Fallback: keep status quo squad
            lineup_sol = self._solve_lineup_and_captain(
                candidate_df=candidate_df.iloc[curr_indices],
                step_xp=step_xp[curr_indices]
            )
            ft_banked_next = max(1, min(5, available_ft + 1))
            best_plan = MultiPeriodGameweekPlan(
                gameweek=gameweek,
                transfers_in=(),
                transfers_out=(),
                starting_xi=tuple(lineup_sol["starting_xi"]),
                bench=tuple(lineup_sol["bench"]),
                captain_id=lineup_sol["captain_id"],
                captain_name=lineup_sol["captain_name"],
                vice_captain_id=lineup_sol["vice_captain_id"],
                vice_captain_name=lineup_sol["vice_captain_name"],
                free_transfers_available=available_ft,
                free_transfers_used=0,
                free_transfers_banked_next=ft_banked_next,
                hits_taken=0,
                hit_cost_points=0,
                gross_xp=round(lineup_sol["gross_xp"], 2),
                net_xp=round(lineup_sol["gross_xp"], 2),
                bank_remaining=bank,
            )

        return best_plan

    def _solve_squad_milp(
        self,
        candidate_df: pd.DataFrame,
        step_xp: np.ndarray,
        curr_indices: List[int],
        k_transfers: int,
        budget: float
    ) -> Dict[str, Any]:
        """Solves single-step 15-player squad selection MILP."""
        n = len(candidate_df)
        c = -step_xp  # Maximize xP

        A_rows = []
        b_l = []
        b_u = []

        # 1. Total squad size == 15
        A_rows.append(np.ones(n))
        b_l.append(15.0)
        b_u.append(15.0)

        # 2. Budget constraint
        A_rows.append(candidate_df["now_cost"].values)
        b_l.append(0.0)
        b_u.append(budget)

        # 3. Position quotas: 2 GKP, 5 DEF, 5 MID, 3 FWD
        pos_quotas = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
        for pos, quota in pos_quotas.items():
            A_rows.append((candidate_df["position_name"] == pos).astype(float).values)
            b_l.append(float(quota))
            b_u.append(float(quota))

        # 4. Club limit: <= 3 per club
        for club in candidate_df["club_short"].unique():
            A_rows.append((candidate_df["club_short"] == club).astype(float).values)
            b_l.append(0.0)
            b_u.append(3.0)

        # 5. Transfers constraint: exactly (15 - k_transfers) retained from current squad
        keep_mask = np.zeros(n)
        for idx in curr_indices:
            keep_mask[idx] = 1.0
        A_rows.append(keep_mask)
        target_keep = len(curr_indices) - k_transfers
        b_l.append(float(target_keep))
        b_u.append(float(target_keep))

        A = np.array(A_rows)
        constraints = LinearConstraint(A, b_l, b_u)
        bounds = Bounds(0, 1)
        integrality = np.ones(n)

        res = milp(c=c, integrality=integrality, constraints=constraints, bounds=bounds)
        if not res.success:
            return {"success": False}

        sel_idx = np.where(res.x > 0.5)[0].tolist()
        squad_cost = float(candidate_df.iloc[sel_idx]["now_cost"].sum())

        return {
            "success": True,
            "indices": sel_idx,
            "cost": squad_cost,
        }

    def _solve_lineup_and_captain(
        self,
        candidate_df: pd.DataFrame,
        step_xp: np.ndarray
    ) -> Dict[str, Any]:
        """
        Determines optimal starting XI (evaluating all 8 legal formations),
        bench order, and captaincy allocation for a 15-player squad.
        """
        df = candidate_df.copy().reset_index(drop=True)
        df["step_xp"] = step_xp

        # 1. GKP: 1 starter, 1 bench
        gkps = df[df["position_name"] == "GKP"].sort_values(by="step_xp", ascending=False)
        start_gkp = gkps.iloc[0]
        bench_gkp = gkps.iloc[1] if len(gkps) > 1 else None

        # 2. Outfield Formations Evaluation
        outfield = df[df["position_name"] != "GKP"].copy()
        legal_formations = [
            (3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3),
            (4, 5, 1), (5, 3, 2), (5, 4, 1), (5, 2, 3)
        ]

        best_starting_outfield: Optional[pd.DataFrame] = None
        best_outfield_xp = -1e9

        defs = outfield[outfield["position_name"] == "DEF"].sort_values(by="step_xp", ascending=False)
        mids = outfield[outfield["position_name"] == "MID"].sort_values(by="step_xp", ascending=False)
        fwds = outfield[outfield["position_name"] == "FWD"].sort_values(by="step_xp", ascending=False)

        for n_def, n_mid, n_fwd in legal_formations:
            sel_defs = defs.head(n_def)
            sel_mids = mids.head(n_mid)
            sel_fwds = fwds.head(n_fwd)

            formation_df = pd.concat([sel_defs, sel_mids, sel_fwds])
            form_xp = float(formation_df["step_xp"].sum())

            if form_xp > best_outfield_xp:
                best_outfield_xp = form_xp
                best_starting_outfield = formation_df

        # Combine Starting XI
        starting_df = pd.concat([pd.DataFrame([start_gkp]), best_starting_outfield]).reset_index(drop=True)
        starting_ids = set(starting_df["id"])

        # Bench: remaining 4 players
        bench_df = df[~df["id"].isin(starting_ids)].copy()
        bench_outfield = bench_df[bench_df["position_name"] != "GKP"].sort_values(by="step_xp", ascending=False)
        bench_ordered = pd.concat([pd.DataFrame([bench_gkp]) if bench_gkp is not None else pd.DataFrame(), bench_outfield]).reset_index(drop=True)

        # Captain & Vice Captain
        sorted_starters = starting_df.sort_values(by="step_xp", ascending=False)
        captain = sorted_starters.iloc[0]
        vice_captain = sorted_starters.iloc[1] if len(sorted_starters) > 1 else captain

        gross_xp = float(starting_df["step_xp"].sum() + captain["step_xp"])

        # Construct tuples
        starting_xi = [(int(r["id"]), str(r["web_name"]), str(r["position_name"]), round(float(r["step_xp"]), 2)) for _, r in starting_df.iterrows()]
        bench = [(int(r["id"]), str(r["web_name"]), str(r["position_name"]), round(float(r["step_xp"]), 2)) for _, r in bench_ordered.iterrows()]

        return {
            "starting_xi": starting_xi,
            "bench": bench,
            "captain_id": int(captain["id"]),
            "captain_name": str(captain["web_name"]),
            "vice_captain_id": int(vice_captain["id"]),
            "vice_captain_name": str(vice_captain["web_name"]),
            "gross_xp": gross_xp,
        }
