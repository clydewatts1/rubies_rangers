"""
Unit tests for TwoStageOptimizer and MILPCandidateGenerator.
Validates Pareto candidate generation, deduplication, and stochastic evaluation.
"""

import pytest
import numpy as np
from clients.fpl_client import FPLClient
from analytics.optimizer import FPLOptimizer
from analytics.montecarlo import MonteCarloEngine
from analytics.xp_model import DEFAULT_SQUAD
from analytics.two_stage_optimizer import (
    TwoStageOptimizer,
    MILPCandidateGenerator,
    ParetoCandidateSquad,
    StochasticSquadEvaluation,
    TwoStageOptimizationReport,
)


@pytest.fixture
def fpl_opt():
    client = FPLClient(cache_ttl=3600)
    df = client.get_players_df()
    return FPLOptimizer(df)


@pytest.fixture
def mc_engine():
    return MonteCarloEngine()


def test_dataclass_contracts():
    """Verify dataclasses enforce structured typed records."""
    cand = ParetoCandidateSquad(
        objective_name="fdr_moneyball",
        generator_type="MILP",
        squad_names=["Haaland", "Salah"],
        transfers_in=["Haaland"],
        transfers_out=["Isak"],
        total_cost=98.5,
        bank_remaining=1.5,
        projected_score=55.0
    )
    assert cand.objective_name == "fdr_moneyball"
    assert cand.total_cost == 98.5
    # Verify frozen
    with pytest.raises(Exception):
        cand.total_cost = 100.0


def test_candidate_generator_sweeps(fpl_opt):
    """Verify Stage 1 MILPCandidateGenerator runs sweeps and deduplicates."""
    gen = MILPCandidateGenerator(fpl_opt)
    candidates = gen.generate_candidates(
        current_squad=DEFAULT_SQUAD,
        bank=3.7,
        num_transfers=1
    )
    assert len(candidates) >= 1
    # Check deduplication
    seen = set()
    for c in candidates:
        key = frozenset(c.squad_names)
        assert key not in seen
        seen.add(key)
        assert len(c.squad_names) == 15
        assert len(c.transfers_in) <= 1
        assert len(c.transfers_out) <= 1


def test_two_stage_optimizer_pipeline(fpl_opt, mc_engine):
    """Verify TwoStageOptimizer chains Stage 1 into Stage 2 Monte Carlo evaluation."""
    two_stage = TwoStageOptimizer(fpl_opt, mc_engine)
    report = two_stage.run_screen_and_simulate(
        current_squad=DEFAULT_SQUAD,
        bank=3.7,
        num_transfers=1,
        n_sims=100
    )
    assert isinstance(report, TwoStageOptimizationReport)
    assert report.baseline_mean > 0.0
    assert report.baseline_p10 <= report.baseline_p90
    assert len(report.evaluated_candidates) >= 1

    winner = report.winner_balanced
    assert winner is not None
    assert winner.mean_points > 0.0
    assert 0.0 <= winner.win_probability_pct <= 100.0
    assert report.winner_safe_floor is not None
    assert report.winner_explosive_ceiling is not None

    # Assert stochastic visual analytics suite fields
    assert isinstance(report.baseline_raw_totals, np.ndarray)
    assert len(report.baseline_raw_totals) == 100
    assert isinstance(winner.raw_totals, np.ndarray)
    assert len(winner.raw_totals) == 100

    import pandas as pd
    assert isinstance(report.all_results_df, pd.DataFrame)
    assert not report.all_results_df.empty
    assert "objective" in report.all_results_df.columns
    assert "mean_points" in report.all_results_df.columns
    assert "win_prob" in report.all_results_df.columns
    assert "net_mean_gain" in report.all_results_df.columns

    # Verify archetype winners are tagged
    assert winner.archetype != ""
    assert report.winner_safe_floor.archetype != ""
    assert report.winner_explosive_ceiling.archetype != ""
