"""
Strategic Multi-Period Two-Stage Optimization Engine (Phase 2).
Chains Stage 1 Multi-Period MILP / Markowitz Pathway Generation
into Stage 2 Stochastic Multi-Gameweek Monte Carlo Simulation.
Governed by .agents/rules/moneyball_strategy.md and .agents/rules/python_standards.md.
"""

from __future__ import annotations
import math
import time
from typing import Dict, List, Optional, Tuple, Any, Set
import numpy as np
import pandas as pd

from config_manager import get_params
from clients.fpl_client import FPLClient
from analytics.montecarlo import MonteCarloEngine
from analytics.strategic.contracts import (
    MultiPeriodGameweekPlan,
    MultiPeriodStrategicSolution,
    EvaluatedStrategicPathway,
    StrategicTwoStageReport,
)
from analytics.strategic.multi_period_solver import MultiPeriodSolver
from analytics.strategic.trajectory_engine import TrajectoryEngine


class StrategicTwoStageOptimizer:
    """
    Two-Stage Rolling Horizon Optimizer:
    - Stage 1: Generates diverse multi-period transfer roadmaps across Pareto/Markowitz objectives.
    - Stage 2: Stress-tests each roadmap through N multi-gameweek Monte Carlo season trials.
    """

    def __init__(
        self,
        fpl_client: Optional[FPLClient] = None,
        mc_engine: Optional[MonteCarloEngine] = None,
        solver: Optional[MultiPeriodSolver] = None,
        default_horizon: int = 5,
        profile: Optional[str] = None,
        random_seed: Optional[int] = 42
    ) -> None:
        self.client = fpl_client or FPLClient()
        self.mc_engine = mc_engine or MonteCarloEngine()
        self.solver = solver or MultiPeriodSolver(fpl_client=self.client, default_horizon=default_horizon, profile=profile)
        self.default_horizon = default_horizon
        self.profile = profile
        self.random_seed = random_seed

    def run_strategic_tournament(
        self,
        initial_squad_names_or_ids: Optional[List[Any]] = None,
        horizon: Optional[int] = None,
        bank: Optional[float] = None,
        initial_ft: Optional[int] = None,
        max_hits_per_gw: int = 1,
        n_sims: int = 1000,
        objectives: Optional[List[str]] = None,
    ) -> StrategicTwoStageReport:
        """
        Executes the two-stage multi-period strategic tournament:
        1. Generates status quo baseline solution and Pareto candidate roadmaps via Stage 1 MILP.
        2. Simulates each roadmap over H future gameweeks across N stochastic season realizations.
        3. Quantifies joint tail distributions (P10, P50, P90), win probability vs baseline, and crowns archetypes.
        """
        if self.random_seed is not None:
            np.random.seed(self.random_seed)

        h = horizon or self.default_horizon
        df_players = self.client.get_players_df()
        elements_by_id = {int(r["id"]): r.to_dict() for _, r in df_players.iterrows()} if not df_players.empty else {}
        elements_by_name = {str(r["web_name"]).lower(): r.to_dict() for _, r in df_players.iterrows()} if not df_players.empty else {}

        # 1. Generate Status Quo Baseline Roadmap (0 transfers across horizon)
        baseline_sol = self.solver.solve(
            initial_squad_names_or_ids=initial_squad_names_or_ids,
            horizon=h,
            bank=bank,
            initial_ft=initial_ft,
            max_hits_per_gw=0,
            objective="conservative_banking",
        )

        # 2. Stage 1: Generate Strategic Candidate Roadmaps across Objectives
        pathways = self.solver.generate_strategic_pathways(
            initial_squad_names_or_ids=initial_squad_names_or_ids,
            horizon=h,
            bank=bank,
            initial_ft=initial_ft,
            max_hits_per_gw=max_hits_per_gw,
            objectives=objectives,
        )

        # Ensure baseline is in the pool if not already
        all_solutions = [baseline_sol] + [p for p in pathways if p != baseline_sol]

        # 3. Stage 2: Multi-Period Monte Carlo Simulation
        # Simulate baseline first
        base_raw, base_weekly_means, base_weekly_p10, base_weekly_p90 = self._simulate_multi_period_solution(
            solution=baseline_sol,
            n_sims=n_sims,
            elements_by_id=elements_by_id,
            elements_by_name=elements_by_name
        )
        base_mean = round(float(np.mean(base_raw)), 2)
        base_p10 = round(float(np.percentile(base_raw, 10)), 2)
        base_p90 = round(float(np.percentile(base_raw, 90)), 2)

        evaluated: List[EvaluatedStrategicPathway] = []
        rows: List[Dict[str, Any]] = []

        for idx, sol in enumerate(all_solutions):
            raw_totals, weekly_means, weekly_p10, weekly_p90 = self._simulate_multi_period_solution(
                solution=sol,
                n_sims=n_sims,
                elements_by_id=elements_by_id,
                elements_by_name=elements_by_name
            )

            p_mean = round(float(np.mean(raw_totals)), 2)
            p_p10 = round(float(np.percentile(raw_totals, 10)), 2)
            p_p50 = round(float(np.percentile(raw_totals, 50)), 2)
            p_p90 = round(float(np.percentile(raw_totals, 90)), 2)
            p_std = round(float(np.std(raw_totals)), 2)

            diff = raw_totals - base_raw
            win_prob = round(float(np.mean(diff >= 0) * 100.0), 1) if sol != baseline_sol else 50.0
            sharpe = round(float((p_mean - base_mean) / (p_std + 1e-6)), 3)

            tot_transfers = sum(len(p.transfers_in) for p in sol.plans)
            hits = sol.cumulative_hits_taken
            terminal_ft = sol.plans[-1].free_transfers_banked_next if sol.plans else 1

            tin_summary = "; ".join(f"GW{p.gameweek}: +{', '.join(x[1] for x in p.transfers_in)}" for p in sol.plans if p.transfers_in) or "Roll all weeks"

            rationale = (
                f"Generated via Stage 1 {sol.objective_name.upper()} multi-period dynamic optimization. "
                f"Stage 2 Monte Carlo simulated {p_mean:.1f} mean pts, [{p_p10:.1f} floor, {p_p90:.1f} ceiling] "
                f"across {n_sims:,} 5-GW trials ({win_prob:.1f}% win prob vs baseline)."
            )

            eval_item = EvaluatedStrategicPathway(
                pathway_id=f"pathway_{sol.objective_name}_{idx}",
                objective_name=sol.objective_name,
                generator_type=sol.generator_type,
                solution=sol,
                mean_points=p_mean,
                floor_p10=p_p10,
                median_p50=p_p50,
                ceiling_p90=p_p90,
                standard_deviation=p_std,
                win_probability_pct=win_prob,
                sharpe_ratio=sharpe,
                weekly_mean_totals=tuple(weekly_means),
                weekly_p10_totals=tuple(weekly_p10),
                weekly_p90_totals=tuple(weekly_p90),
                raw_totals=tuple(raw_totals),
                archetype="",
                rationale=rationale,
            )
            evaluated.append(eval_item)

            rows.append({
                "objective": sol.objective_name,
                "transfers_total": tot_transfers,
                "hits_total": hits,
                "terminal_ft": terminal_ft,
                "terminal_bank": sol.terminal_bank,
                "net_xp_projected": sol.cumulative_net_xp,
                "mean_points": p_mean,
                "floor_p10": p_p10,
                "median_p50": p_p50,
                "ceiling_p90": p_p90,
                "std": p_std,
                "win_prob": win_prob,
                "sharpe": sharpe,
                "roadmap_summary": tin_summary,
            })

        # 4. Crown Winners Across Strategic Archetypes
        if evaluated:
            winner_balanced = max(evaluated, key=lambda x: x.mean_points)
            winner_safe_floor = max(evaluated, key=lambda x: x.floor_p10)
            winner_explosive_ceiling = max(evaluated, key=lambda x: x.ceiling_p90)

            # Re-wrap with archetype tags
            evaluated_tagged: List[EvaluatedStrategicPathway] = []
            for item in evaluated:
                arch_label = ""
                if item == winner_balanced:
                    arch_label = "OPTION 1: 🏆 MAX EXPECTED VALUE"
                elif item == winner_safe_floor:
                    arch_label = "OPTION 2: 🛡️ MAX FLOOR & SAFETY"
                elif item == winner_explosive_ceiling:
                    arch_label = "OPTION 3: 🚀 MAX CEILING & DIFFERENTIAL"

                evaluated_tagged.append(
                    EvaluatedStrategicPathway(
                        pathway_id=item.pathway_id,
                        objective_name=item.objective_name,
                        generator_type=item.generator_type,
                        solution=item.solution,
                        mean_points=item.mean_points,
                        floor_p10=item.floor_p10,
                        median_p50=item.median_p50,
                        ceiling_p90=item.ceiling_p90,
                        standard_deviation=item.standard_deviation,
                        win_probability_pct=item.win_probability_pct,
                        sharpe_ratio=item.sharpe_ratio,
                        weekly_mean_totals=item.weekly_mean_totals,
                        weekly_p10_totals=item.weekly_p10_totals,
                        weekly_p90_totals=item.weekly_p90_totals,
                        raw_totals=item.raw_totals,
                        archetype=arch_label,
                        rationale=item.rationale,
                    )
                )
            evaluated = evaluated_tagged
            winner_balanced = next(p for p in evaluated if p.pathway_id == winner_balanced.pathway_id)
            winner_safe_floor = next(p for p in evaluated if p.pathway_id == winner_safe_floor.pathway_id)
            winner_explosive_ceiling = next(p for p in evaluated if p.pathway_id == winner_explosive_ceiling.pathway_id)
        else:
            winner_balanced = None
            winner_safe_floor = None
            winner_explosive_ceiling = None

        return StrategicTwoStageReport(
            horizon=h,
            baseline_solution=baseline_sol,
            baseline_mean=base_mean,
            baseline_p10=base_p10,
            baseline_p90=base_p90,
            baseline_raw_totals=tuple(base_raw),
            evaluated_pathways=tuple(evaluated),
            winner_balanced=winner_balanced,
            winner_safe_floor=winner_safe_floor,
            winner_explosive_ceiling=winner_explosive_ceiling,
            all_results_df_data=tuple(rows),
        )

    def _simulate_multi_period_solution(
        self,
        solution: MultiPeriodStrategicSolution,
        n_sims: int,
        elements_by_id: Dict[int, Dict[str, Any]],
        elements_by_name: Dict[str, Dict[str, Any]],
    ) -> Tuple[np.ndarray, List[float], List[float], List[float]]:
        """
        Simulates the entire multi-week roadmap sequentially across N trials:
        For each GW:
        - Simulates starting XI and bench points.
        - Applies tactical sub hazard model and bench auto-substitutions.
        - Transfers captaincy to vice-captain if captain plays 0 minutes.
        - Deducts transfer hit points.
        """
        h = len(solution.plans)
        sim_totals = np.zeros(n_sims, dtype=np.float64)
        weekly_means: List[float] = []
        weekly_p10: List[float] = []
        weekly_p90: List[float] = []

        for plan in solution.plans:
            gw_totals = np.zeros(n_sims, dtype=np.float64)
            starter_pts_list: List[np.ndarray] = []
            starter_mins_list: List[np.ndarray] = []
            starter_pos_list: List[str] = []
            starter_ids_list: List[int] = []

            # 1. Simulate Starters
            for pid, pname, pos, pxp in plan.starting_xi:
                p_dict = elements_by_id.get(pid) or elements_by_name.get(pname.lower()) or {
                    "web_name": pname, "position_name": pos, "form": pxp, "chance_of_playing": 100, "status": "a"
                }
                pts, mins = self.mc_engine.simulate_player(p_dict, n_sims=n_sims)
                starter_pts_list.append(pts)
                starter_mins_list.append(mins)
                starter_pos_list.append(pos)
                starter_ids_list.append(pid)

            # 2. Simulate Bench
            bench_pts_list: List[np.ndarray] = []
            bench_mins_list: List[np.ndarray] = []
            bench_pos_list: List[str] = []

            for pid, pname, pos, pxp in plan.bench:
                p_dict = elements_by_id.get(pid) or elements_by_name.get(pname.lower()) or {
                    "web_name": pname, "position_name": pos, "form": pxp, "chance_of_playing": 100, "status": "a"
                }
                pts, mins = self.mc_engine.simulate_player(p_dict, n_sims=n_sims)
                bench_pts_list.append(pts)
                bench_mins_list.append(mins)
                bench_pos_list.append(pos)

            # 3. Vectorized trial evaluation
            capt_idx = next((i for i, pid in enumerate(starter_ids_list) if pid == plan.captain_id), 0)
            vc_idx = next((i for i, pid in enumerate(starter_ids_list) if pid == plan.vice_captain_id), 1 if len(starter_ids_list) > 1 else 0)

            starter_pts_arr = np.array(starter_pts_list)   # (11, n_sims)
            starter_mins_arr = np.array(starter_mins_list) # (11, n_sims)
            bench_pts_arr = np.array(bench_pts_list) if bench_pts_list else np.zeros((0, n_sims))
            bench_mins_arr = np.array(bench_mins_list) if bench_mins_list else np.zeros((0, n_sims))

            # Base starter sum
            gw_totals = np.sum(starter_pts_arr, axis=0)

            # Auto-substitution logic per trial
            for s_idx in range(n_sims):
                starters_played = starter_mins_arr[:, s_idx] > 0
                missing_starters = np.where(~starters_played)[0]

                if len(missing_starters) > 0 and len(bench_pts_arr) > 0:
                    curr_defs = sum(1 for i, pos in enumerate(starter_pos_list) if starters_played[i] and pos == "DEF")
                    curr_mids = sum(1 for i, pos in enumerate(starter_pos_list) if starters_played[i] and pos == "MID")
                    curr_fwds = sum(1 for i, pos in enumerate(starter_pos_list) if starters_played[i] and pos == "FWD")
                    gkp_played = any(starters_played[i] and starter_pos_list[i] == "GKP" for i in range(11))

                    used_bench = set()
                    for m_idx in missing_starters:
                        m_pos = starter_pos_list[m_idx]
                        for b_idx in range(len(bench_pos_list)):
                            if b_idx in used_bench:
                                continue
                            if bench_mins_arr[b_idx, s_idx] == 0:
                                continue
                            b_pos = bench_pos_list[b_idx]

                            if m_pos == "GKP" and b_pos == "GKP":
                                gw_totals[s_idx] += bench_pts_arr[b_idx, s_idx]
                                used_bench.add(b_idx)
                                break
                            elif m_pos != "GKP" and b_pos != "GKP":
                                # Check formation legality
                                test_def = curr_defs + (1 if b_pos == "DEF" else 0)
                                test_mid = curr_mids + (1 if b_pos == "MID" else 0)
                                test_fwd = curr_fwds + (1 if b_pos == "FWD" else 0)
                                if test_def >= 3 and test_mid >= 2 and test_fwd >= 1:
                                    gw_totals[s_idx] += bench_pts_arr[b_idx, s_idx]
                                    used_bench.add(b_idx)
                                    curr_defs, curr_mids, curr_fwds = test_def, test_mid, test_fwd
                                    break

                # Captaincy doubling
                if starter_mins_arr[capt_idx, s_idx] > 0:
                    gw_totals[s_idx] += starter_pts_arr[capt_idx, s_idx]  # Extra 1x
                else:
                    # Vice-captain fallback
                    gw_totals[s_idx] += starter_pts_arr[vc_idx, s_idx]    # Extra 1x

            # Subtract hit penalty for this gameweek
            gw_totals -= plan.hit_cost_points
            sim_totals += gw_totals

            weekly_means.append(round(float(np.mean(gw_totals)), 2))
            weekly_p10.append(round(float(np.percentile(gw_totals, 10)), 2))
            weekly_p90.append(round(float(np.percentile(gw_totals, 90)), 2))

        return sim_totals, weekly_means, weekly_p10, weekly_p90
