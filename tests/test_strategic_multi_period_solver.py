"""
Unit & Integration Test Suite for Strategic Framework Phase 2: Multi-Period Rolling Horizon Solver.
Verifies multi-period integer linear programming (MILP), dynamic Free Transfer banking (1-5 FTs),
hit penalties, 8 legal FPL formation sweeps, candidate pruning, and UI contracts.
Governed by .agents/rules/moneyball_strategy.md and .agents/rules/python_standards.md.
"""

import time
import pytest
import numpy as np
import pandas as pd
from typing import Dict, List

from analytics.strategic.contracts import (
    MultiPeriodGameweekPlan,
    MultiPeriodStrategicSolution,
)
from analytics.strategic.multi_period_solver import MultiPeriodSolver
from clients.fpl_client import FPLClient
from ui.tabs.tab_strategic_solver import render_tab_strategic_solver


class TestPhase2Contracts:
    """Test immutability, validation, and serialization of Phase 2 contracts."""

    def test_multi_period_gameweek_plan_contract(self):
        plan = MultiPeriodGameweekPlan(
            gameweek=10,
            transfers_in=((101, "Saka", 10.0),),
            transfers_out=((202, "Eze", 6.8),),
            starting_xi=((1, "Raya", "GKP", 5.5), (2, "Gabriel", "DEF", 6.0)),
            bench=((3, "Fabianski", "GKP", 4.0), (4, "Greaves", "DEF", 4.0)),
            captain_id=101,
            captain_name="Saka",
            vice_captain_id=2,
            vice_captain_name="Gabriel",
            free_transfers_available=2,
            free_transfers_used=1,
            free_transfers_banked_next=2,
            hits_taken=0,
            hit_cost_points=0,
            gross_xp=58.4,
            net_xp=58.4,
            bank_remaining=1.2,
        )
        assert plan.gameweek == 10
        assert plan.captain_name == "Saka"
        assert plan.free_transfers_banked_next == 2
        assert len(plan.transfers_in) == 1

        # Test immutability
        with pytest.raises(Exception):
            plan.gameweek = 11  # type: ignore

        # Test dictionary serialization
        d = plan.to_dict()
        assert isinstance(d, dict)
        reconstructed = MultiPeriodGameweekPlan.from_dict(d)
        assert reconstructed.gameweek == plan.gameweek
        assert reconstructed.captain_name == plan.captain_name
        assert reconstructed.gross_xp == plan.gross_xp

    def test_multi_period_strategic_solution_contract(self):
        plan1 = MultiPeriodGameweekPlan(
            gameweek=10,
            transfers_in=(),
            transfers_out=(),
            starting_xi=(),
            bench=(),
            captain_id=1,
            captain_name="Haaland",
            vice_captain_id=2,
            vice_captain_name="Salah",
            free_transfers_available=1,
            free_transfers_used=0,
            free_transfers_banked_next=2,
            hits_taken=0,
            hit_cost_points=0,
            gross_xp=62.0,
            net_xp=62.0,
            bank_remaining=0.5,
        )
        sol = MultiPeriodStrategicSolution(
            horizon=1,
            plans=(plan1,),
            cumulative_gross_xp=62.0,
            cumulative_net_xp=62.0,
            cumulative_hits_taken=0,
            terminal_squad_value=102.5,
            terminal_bank=0.5,
            staged_turnaround_summary="Turnaround roadmap completed.",
        )
        assert sol.horizon == 1
        assert sol.cumulative_net_xp == 62.0
        assert len(sol.plans) == 1

        # Test immutability
        with pytest.raises(Exception):
            sol.cumulative_gross_xp = 70.0  # type: ignore

        # Test dictionary serialization
        d = sol.to_dict()
        assert isinstance(d, dict)
        reconstructed = MultiPeriodStrategicSolution.from_dict(d)
        assert reconstructed.horizon == sol.horizon
        assert reconstructed.terminal_squad_value == sol.terminal_squad_value


class TestCandidatePoolAndPruning:
    """Test candidate pool building and universe pruning."""

    def test_candidate_pool_contains_current_squad(self):
        client = FPLClient()
        solver = MultiPeriodSolver(fpl_client=client, default_horizon=5)
        squad_state = solver.trajectory_engine.get_squad_state()
        curr_ids = list(squad_state.squad_player_ids)

        candidates, xp_tensor = solver._build_candidate_pool(curr_ids, horizon=5)

        assert isinstance(candidates, pd.DataFrame)
        assert len(candidates) >= 15
        assert len(candidates) <= 150  # Pruned candidate set

        # All current squad members must be present in candidate pool
        cand_ids = set(candidates["id"])
        for pid in curr_ids:
            assert pid in cand_ids, f"Current squad player ID {pid} missing from candidate pool"

        # Check tensor dimensions
        assert xp_tensor.shape == (len(candidates), 5)
        assert not np.isnan(xp_tensor).any()


class TestSingleStepMILPAndLineup:
    """Test single gameweek MILP squad selection and lineup optimization."""

    def test_squad_milp_constraints_satisfaction(self):
        client = FPLClient()
        solver = MultiPeriodSolver(fpl_client=client, default_horizon=5)
        squad_state = solver.trajectory_engine.get_squad_state()
        curr_ids = list(squad_state.squad_player_ids)

        candidates, xp_tensor = solver._build_candidate_pool(curr_ids, horizon=5)
        curr_indices = [i for i, pid in enumerate(candidates["id"]) if pid in curr_ids]
        curr_squad_cost = candidates.loc[curr_indices, "now_cost"].sum()
        total_budget = curr_squad_cost + squad_state.bank_balance
        step_xp = xp_tensor[:, 0]

        # Solve for 1 transfer
        res = solver._solve_squad_milp(
            candidate_df=candidates,
            step_xp=step_xp,
            curr_indices=curr_indices,
            k_transfers=1,
            budget=total_budget
        )

        assert res["success"] is True
        sel_idx = res["indices"]
        assert len(sel_idx) == 15

        sel_df = candidates.iloc[sel_idx]
        # Position quotas: 2 GKP, 5 DEF, 5 MID, 3 FWD
        pos_counts = sel_df["position_name"].value_counts().to_dict()
        assert pos_counts.get("GKP", 0) == 2
        assert pos_counts.get("DEF", 0) == 5
        assert pos_counts.get("MID", 0) == 5
        assert pos_counts.get("FWD", 0) == 3

        # Club limit: <= 3 per club
        club_counts = sel_df["club_short"].value_counts()
        assert (club_counts <= 3).all()

        # Budget constraint
        assert res["cost"] <= total_budget + 1e-5

        # Kept players: exactly 14 kept from current 15
        kept = len(set(sel_df["id"]).intersection(set(curr_ids)))
        assert kept == 14

    def test_lineup_and_captain_formation_legality(self):
        client = FPLClient()
        solver = MultiPeriodSolver(fpl_client=client, default_horizon=5)
        squad_state = solver.trajectory_engine.get_squad_state()
        curr_ids = list(squad_state.squad_player_ids)

        candidates, xp_tensor = solver._build_candidate_pool(curr_ids, horizon=5)
        curr_indices = [i for i, pid in enumerate(candidates["id"]) if pid in curr_ids]
        squad_df = candidates.iloc[curr_indices]
        step_xp = xp_tensor[curr_indices, 0]

        lineup_res = solver._solve_lineup_and_captain(squad_df, step_xp)

        starting_xi = lineup_res["starting_xi"]
        bench = lineup_res["bench"]

        assert len(starting_xi) == 11
        assert len(bench) == 4

        # Check starting formation validity
        gkp_count = sum(1 for p in starting_xi if p[2] == "GKP")
        def_count = sum(1 for p in starting_xi if p[2] == "DEF")
        mid_count = sum(1 for p in starting_xi if p[2] == "MID")
        fwd_count = sum(1 for p in starting_xi if p[2] == "FWD")

        assert gkp_count == 1
        assert 3 <= def_count <= 5
        assert 2 <= mid_count <= 5
        assert 1 <= fwd_count <= 3
        assert (def_count + mid_count + fwd_count) == 10

        # Captain and Vice-captain
        captain_id = lineup_res["captain_id"]
        vice_id = lineup_res["vice_captain_id"]
        assert captain_id is not None
        assert vice_id is not None
        assert captain_id != vice_id

        # Starting XI xP + captain xP == gross_xp
        starters_base_xp = sum(p[3] for p in starting_xi)
        cap_xp = [p[3] for p in starting_xi if p[0] == captain_id][0]
        assert abs(lineup_res["gross_xp"] - (starters_base_xp + cap_xp)) < 0.05


class TestMultiPeriodSolverEndToEnd:
    """Test full multi-period optimization across 3, 4, 5, and 6-gameweek horizons."""

    def test_solve_5_gameweek_horizon(self):
        client = FPLClient()
        solver = MultiPeriodSolver(fpl_client=client, default_horizon=5)

        solution = solver.solve(
            horizon=5,
            bank=1.5,
            initial_ft=1,
            max_hits_per_gw=1,
            discount_gamma=0.92,
            ft_option_mult=1.5,
        )

        assert isinstance(solution, MultiPeriodStrategicSolution)
        assert solution.horizon == 5
        assert len(solution.plans) == 5
        assert solution.cumulative_gross_xp > 0
        assert solution.cumulative_net_xp <= solution.cumulative_gross_xp
        assert solution.terminal_squad_value > 90.0

        # Check sequential FT banking progression invariant
        prev_ft = 1
        for plan in solution.plans:
            assert 1 <= plan.free_transfers_available <= 5
            assert 1 <= plan.free_transfers_banked_next <= 5
            assert plan.net_xp == round(plan.gross_xp - (plan.hits_taken * 4), 2)
            assert plan.bank_remaining >= 0.0

            # FT formula invariant: FT_next = min(5, max(1, FT_avail - k + 1))
            k_transfers = len(plan.transfers_in)
            expected_next_ft = max(1, min(5, plan.free_transfers_available - k_transfers + 1))
            assert plan.free_transfers_banked_next == expected_next_ft

    def test_solve_variable_horizons(self):
        client = FPLClient()
        solver = MultiPeriodSolver(fpl_client=client)

        for h in [3, 4, 6]:
            sol = solver.solve(horizon=h, initial_ft=2, bank=2.0)
            assert sol.horizon == h
            assert len(sol.plans) == h

    def test_solver_performance_latency(self):
        client = FPLClient()
        solver = MultiPeriodSolver(fpl_client=client, default_horizon=5)

        start_time = time.perf_counter()
        sol = solver.solve(horizon=5)
        elapsed = time.perf_counter() - start_time

        # Must execute within 5.0 seconds for 5 full sequential MILP steps
        assert elapsed < 5.0, f"Solver too slow: took {elapsed:.2f}s (SLA < 5.0s)"
        assert len(sol.plans) == 5


class TestPhase2UIIntegration:
    """Test Streamlit tab integration for Phase 2."""

    def test_render_tab_strategic_solver_callable(self):
        assert callable(render_tab_strategic_solver)
