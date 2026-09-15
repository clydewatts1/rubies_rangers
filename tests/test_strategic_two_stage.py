"""
Unit & Integration Tests for Two-Stage Strategic Multi-Period Optimization.
Validates Stage 1 Pareto/Markowitz Pathway Generation,
Stage 2 Multi-Gameweek Monte Carlo Tournament Simulation,
P10/P50/P90 statistical bounds, and Archetype Crowning.
Governed by .agents/rules/moneyball_strategy.md and .agents/rules/python_standards.md.
"""

import time
import pytest
import numpy as np
import pandas as pd

from clients.fpl_client import FPLClient
from analytics.montecarlo import MonteCarloEngine
from analytics.strategic.contracts import (
    MultiPeriodGameweekPlan,
    MultiPeriodStrategicSolution,
    EvaluatedStrategicPathway,
    StrategicTwoStageReport,
)
from analytics.strategic.multi_period_solver import MultiPeriodSolver
from analytics.strategic.two_stage_solver import StrategicTwoStageOptimizer


def test_strategic_two_stage_contracts():
    """Verify frozen immutability and round-trip serialization of two-stage contracts."""
    plan = MultiPeriodGameweekPlan(
        gameweek=5,
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
    sol = MultiPeriodStrategicSolution(
        horizon=1,
        plans=(plan,),
        cumulative_gross_xp=58.4,
        cumulative_net_xp=58.4,
        cumulative_hits_taken=0,
        terminal_squad_value=102.5,
        terminal_bank=1.2,
        staged_turnaround_summary="Turnaround roadmap completed.",
        objective_name="max_ev",
    )

    pathway = EvaluatedStrategicPathway(
        pathway_id="pathway_max_ev_0",
        objective_name="max_ev",
        generator_type="Multi-Period MILP",
        solution=sol,
        mean_points=59.2,
        floor_p10=42.0,
        median_p50=58.5,
        ceiling_p90=76.0,
        standard_deviation=12.5,
        win_probability_pct=65.0,
        sharpe_ratio=0.55,
        weekly_mean_totals=(59.2,),
        weekly_p10_totals=(42.0,),
        weekly_p90_totals=(76.0,),
        raw_totals=(58.0, 60.0, 59.2),
        archetype="OPTION 1: 🏆 MAX EXPECTED VALUE",
        rationale="Top EV plan",
    )

    assert pathway.pathway_id == "pathway_max_ev_0"
    assert pathway.floor_p10 == 42.0
    assert pathway.ceiling_p90 == 76.0

    # Immutability
    with pytest.raises(Exception):
        pathway.mean_points = 65.0  # type: ignore

    # Serialization
    d = pathway.to_dict()
    assert isinstance(d, dict)
    reconstructed = EvaluatedStrategicPathway.from_dict(d)
    assert reconstructed.pathway_id == pathway.pathway_id
    assert reconstructed.mean_points == pathway.mean_points
    assert reconstructed.solution.cumulative_net_xp == sol.cumulative_net_xp


def test_stage_1_multi_period_pathway_generation():
    """Verify MultiPeriodSolver generates distinct deduplicated strategic pathways."""
    client = FPLClient()
    solver = MultiPeriodSolver(fpl_client=client, default_horizon=5)

    pathways = solver.generate_strategic_pathways(
        horizon=5,
        bank=1.5,
        initial_ft=1,
        max_hits_per_gw=1,
    )

    assert isinstance(pathways, list)
    assert len(pathways) >= 1

    # Check deduplication
    seen = set()
    for p in pathways:
        key = tuple(
            (
                tuple(sorted(x[0] for x in plan.transfers_in)),
                tuple(sorted(x[0] for x in plan.transfers_out)),
            )
            for plan in p.plans
        )
        assert key not in seen
        seen.add(key)
        assert p.horizon == 5
        assert len(p.plans) == 5


def test_stage_2_strategic_tournament_simulation():
    """
    Verify StrategicTwoStageOptimizer:
    - Runs multi-period Monte Carlo tournament simulations.
    - Accurately computes P10, P50, P90 distribution statistics.
    - Crowns Top 3 Archetypes (Balanced EV, Safe Floor, Peak Ceiling).
    """
    client = FPLClient()
    two_stage = StrategicTwoStageOptimizer(fpl_client=client, default_horizon=5, random_seed=42)

    report = two_stage.run_strategic_tournament(
        horizon=5,
        bank=1.5,
        initial_ft=1,
        max_hits_per_gw=1,
        n_sims=300,
    )

    assert isinstance(report, StrategicTwoStageReport)
    assert report.horizon == 5
    assert report.baseline_mean > 0.0
    assert report.baseline_p10 <= report.baseline_p90
    assert len(report.evaluated_pathways) >= 1

    # Archetypes must be crowned
    assert report.winner_balanced is not None
    assert report.winner_safe_floor is not None
    assert report.winner_explosive_ceiling is not None

    # Distribution bounds invariant for each evaluated pathway
    for path in report.evaluated_pathways:
        assert path.floor_p10 <= path.median_p50 <= path.ceiling_p90
        assert 0.0 <= path.win_probability_pct <= 100.0
        assert len(path.weekly_mean_totals) == 5
        assert len(path.weekly_p10_totals) == 5
        assert len(path.weekly_p90_totals) == 5
        assert len(path.raw_totals) == 300

    # Max EV winner should have maximum mean
    max_mean = max(p.mean_points for p in report.evaluated_pathways)
    assert report.winner_balanced.mean_points == max_mean

    # Safe floor winner should have maximum P10
    max_p10 = max(p.floor_p10 for p in report.evaluated_pathways)
    assert report.winner_safe_floor.floor_p10 == max_p10

    # Ceiling winner should have maximum P90
    max_p90 = max(p.ceiling_p90 for p in report.evaluated_pathways)
    assert report.winner_explosive_ceiling.ceiling_p90 == max_p90


def test_strategic_two_stage_performance_latency():
    """Verify Two-Stage Strategic Optimizer completes within performance SLA."""
    client = FPLClient()
    two_stage = StrategicTwoStageOptimizer(fpl_client=client, default_horizon=5, random_seed=123)

    start_time = time.perf_counter()
    report = two_stage.run_strategic_tournament(
        horizon=5,
        bank=2.0,
        initial_ft=2,
        n_sims=500,
    )
    elapsed = time.perf_counter() - start_time

    assert elapsed < 10.0, f"Two-stage tournament too slow: {elapsed:.2f}s (SLA < 10.0s)"
    assert len(report.evaluated_pathways) >= 1
