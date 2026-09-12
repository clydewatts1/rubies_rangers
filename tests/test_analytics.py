"""
Unit tests for analytics package.
Validates direct package imports and core mathematical engine instantiation.
"""

import pytest
import pandas as pd
from analytics import (
    FPLOptimizer,
    MonteCarloEngine,
    clean_nans,
    XPModel,
    DEFAULT_SQUAD,
    GW4_MATCH_ODDS,
    load_dataset,
)
import fpl_optimizer as opt_shim
import montecarlo_engine as mc_shim
import xp_model as xp_shim


def test_analytics_exports():
    """Verify package public API exports and shim parity."""
    assert FPLOptimizer is opt_shim.FPLOptimizer
    assert MonteCarloEngine is mc_shim.MonteCarloEngine
    assert clean_nans is mc_shim.clean_nans
    assert XPModel is xp_shim.XPModel
    assert DEFAULT_SQUAD == xp_shim.DEFAULT_SQUAD
    assert GW4_MATCH_ODDS == xp_shim.GW4_MATCH_ODDS


def test_optimizer_initialization():
    """Verify FPLOptimizer initializes with mock player data."""
    mock_df = pd.DataFrame([
        {"web_name": "Haaland", "full_name": "Erling Haaland", "now_cost": 15.0, "total_points": 200, "position_name": "FWD", "club_name": "MCI", "element_type": 4, "team": 11, "status": "a", "form": 8.0, "points_per_game": 7.5, "moneyball_score": 10.0, "fdr_moneyball_score": 10.0, "setpiece_moneyball_score": 12.0, "expected_goal_involvements_per_90": 1.1},
    ])
    opt = FPLOptimizer(mock_df)
    assert len(opt.df) == 1
    assert opt.df.loc[0, "web_name"] == "Haaland"


def test_clean_nans_utility():
    """Verify clean_nans handles nested structures and float nan/inf."""
    data = {"a": float("nan"), "b": [1.0, float("inf")], "c": "valid"}
    res = clean_nans(data)
    assert res["a"] is None
    assert res["b"] == [1.0, None]
    assert res["c"] == "valid"
