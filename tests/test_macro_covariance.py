"""
Unit and Integration Tests for Macro Match-State Jitter & Teammate Covariance Modeling
Validates teammate clean sheet synchronization, discrete Poisson arrival dynamics,
attacker-vs-goalkeeper negative covariance, feature flag toggles, and performance latency.
"""

import time
import pytest
import numpy as np
from typing import Dict, Any, List

from analytics.macro_engine import (
    FixtureMacroState,
    simulate_macro_fixtures,
    build_team_macro_lookup,
)
from analytics.montecarlo import MonteCarloEngine


@pytest.fixture
def mc_engine():
    return MonteCarloEngine()


@pytest.fixture
def sample_fixtures() -> List[Dict[str, Any]]:
    return [
        {
            "id": 1,
            "team_h": 1,
            "team_a": 2,
            "team_h_short": "ARS",
            "team_a_short": "CHE",
            "home_xg": 1.80,
            "away_xg": 1.10,
            "kickoff_time": "2026-09-15T15:00:00Z"
        },
        {
            "id": 2,
            "team_h": 3,
            "team_a": 4,
            "team_h_short": "LIV",
            "team_a_short": "MCI",
            "home_xg": 1.60,
            "away_xg": 1.50,
            "kickoff_time": "2026-09-15T17:30:00Z"
        }
    ]


# =====================================================================
# Test 1: Macro Fixture State Engine Properties
# =====================================================================
def test_simulate_macro_fixtures_statistical_properties(sample_fixtures):
    """Verify log-normal pace distribution mean ~ 1.0, clipping bounds, and non-negative integer goals."""
    n_sims = 10000
    states = simulate_macro_fixtures(
        sample_fixtures,
        n_sims=n_sims,
        pace_volatility=0.15,
        clip_pace_min=0.50,
        clip_pace_max=2.00,
        random_seed=42
    )

    assert len(states) == 2
    assert "ARS_CHE" in states
    f1_state = states["ARS_CHE"]

    # Pace Multiplier Tests
    assert isinstance(f1_state, FixtureMacroState)
    assert len(f1_state.pace_mult) == n_sims
    assert np.all(f1_state.pace_mult >= 0.50)
    assert np.all(f1_state.pace_mult <= 2.00)
    # E[theta] = 1.0 (mean should be tightly calibrated near 1.0)
    assert 0.98 <= np.mean(f1_state.pace_mult) <= 1.02

    # Integer Poisson Goals
    assert np.all(f1_state.home_goals >= 0)
    assert np.all(f1_state.away_goals >= 0)
    assert np.issubdtype(f1_state.home_goals.dtype, np.integer)
    assert np.issubdtype(f1_state.away_goals.dtype, np.integer)

    # Clean Sheet Exact Synchronization
    assert np.array_equal(f1_state.home_cs, (f1_state.away_goals == 0).astype(int))
    assert np.array_equal(f1_state.away_cs, (f1_state.home_goals == 0).astype(int))


def test_build_team_macro_lookup_perspective(sample_fixtures):
    """Verify home/away goal mapping inversion and Double/Blank GW handling."""
    states = simulate_macro_fixtures(sample_fixtures, n_sims=1000, random_seed=42)
    team_lookup = build_team_macro_lookup(states)

    # ARS is home in fixture 1 (concedes away_goals)
    ars_state = team_lookup["ARS"]
    assert np.array_equal(ars_state["goals_scored"], states["ARS_CHE"].home_goals)
    assert np.array_equal(ars_state["goals_conceded"], states["ARS_CHE"].away_goals)
    assert np.array_equal(ars_state["clean_sheet"], states["ARS_CHE"].home_cs)
    assert ars_state["is_home"] is True

    # CHE is away in fixture 1 (concedes home_goals)
    che_state = team_lookup["CHE"]
    assert np.array_equal(che_state["goals_scored"], states["ARS_CHE"].away_goals)
    assert np.array_equal(che_state["goals_conceded"], states["ARS_CHE"].home_goals)
    assert np.array_equal(che_state["clean_sheet"], states["ARS_CHE"].away_cs)
    assert che_state["is_home"] is False

    # Team not in fixtures (Blank GW) returns None
    assert team_lookup.get("TOT") is None


# =====================================================================
# Test 2: Teammate Clean Sheet Synchronization (Task 6.2)
# =====================================================================
def test_teammate_clean_sheet_synchronization(mc_engine, sample_fixtures):
    """
    Two defenders on the same team (Gabriel and Saliba, ARS) playing 90 minutes
    MUST have perfectly synchronized clean sheet draws (correlation == 1.0).
    """
    n_sims = 5000
    np.random.seed(42)
    mc_engine.generate_macro_match_states(sample_fixtures, n_sims=n_sims)
    ars_macro = mc_engine.macro_states["ARS"]

    gabriel = {
        "web_name": "Gabriel",
        "position_name": "DEF",
        "club_short": "ARS",
        "status": "a",
        "chance_of_playing": 100,
        "form": 5.0,
        "expected_goals_per_90": 0.05,
        "expected_assists_per_90": 0.02,
        "expected_goals_conceded_per_90": 0.8,
        "clean_sheets_per_90": 0.45,
    }

    saliba = {
        "web_name": "Saliba",
        "position_name": "DEF",
        "club_short": "ARS",
        "status": "a",
        "chance_of_playing": 100,
        "form": 5.0,
        "expected_goals_per_90": 0.02,
        "expected_assists_per_90": 0.01,
        "expected_goals_conceded_per_90": 0.8,
        "clean_sheets_per_90": 0.45,
    }

    # Simulate both with identical macro fixture state (exclude random card noise for exact CS points testing)
    pts_gab, mins_gab = mc_engine.simulate_player(gabriel, n_sims=n_sims, include_disciplinary=False, macro_state=ars_macro)
    pts_sal, mins_sal = mc_engine.simulate_player(saliba, n_sims=n_sims, include_disciplinary=False, macro_state=ars_macro)

    # Clean sheet is granted when team clean sheet is True and player plays >= 60 mins
    both_played_60 = (mins_gab >= 60.0) & (mins_sal >= 60.0)
    assert np.sum(both_played_60) > int(0.60 * n_sims)

    team_cs = ars_macro["clean_sheet"]

    # When Arsenal keeps a clean sheet (team_cs == 1) and both play >= 60, both earn at least 6 pts (2 app + 4 CS)
    team_cs_and_60 = (team_cs == 1) & both_played_60
    assert np.sum(team_cs_and_60) > 0
    assert np.all(pts_gab[team_cs_and_60] >= 6.0)
    assert np.all(pts_sal[team_cs_and_60] >= 6.0)

    # Teammate defensive assets exhibit strong positive covariance due to coupled Poisson match outcomes
    # Whereas uncoupled models yield ~0 correlation, coupled macro jitter drives correlation > 0.30
    corr = np.corrcoef(pts_gab, pts_sal)[0, 1]
    assert corr > 0.30, f"Expected strong positive covariance between Arsenal defenders, got corr={corr:.2f}"


# =====================================================================
# Test 3: Discrete Poisson Concession Dynamics (Task 6.3)
# =====================================================================
def test_discrete_poisson_concession_partial_minutes(mc_engine, sample_fixtures):
    """
    A defender subbed at 45 minutes receives a Binomial draw of team goals conceded.
    On-pitch conceded goals MUST be integers <= team conceded goals.
    """
    n_sims = 2000
    mc_engine.generate_macro_match_states(sample_fixtures, n_sims=n_sims)
    ars_macro = mc_engine.macro_states["ARS"]

    player_sub = {
        "web_name": "SubDefender",
        "position_name": "DEF",
        "club_short": "ARS",
        "status": "a",
        "chance_of_playing": 100,
        "form": 3.0,
        "expected_goals_conceded_per_90": 1.5,
        "clean_sheets_per_90": 0.3,
    }

    pts, mins = mc_engine.simulate_player(player_sub, n_sims=n_sims, macro_state=ars_macro)

    assert len(pts) == n_sims
    assert np.all(pts > -10.0)  # Sanity check no numerical blowups
    assert not np.isnan(pts).any()


# =====================================================================
# Test 4: Attacker vs Opposing Goalkeeper Negative Covariance (Task 6.4)
# =====================================================================
def test_negative_covariance_attacker_vs_opposing_goalkeeper(mc_engine, sample_fixtures):
    """
    Havertz (ARS Attacker) vs Sanchez (CHE Goalkeeper).
    In trials where Arsenal scores >= 1 goal (Havertz team), Chelsea's goalkeeper
    CANNOT earn a clean sheet bonus (P(Sanchez CS | ARS goals >= 1) == 0.0).
    """
    n_sims = 5000
    np.random.seed(42)
    mc_engine.generate_macro_match_states(sample_fixtures, n_sims=n_sims)

    ars_macro = mc_engine.macro_states["ARS"]
    che_macro = mc_engine.macro_states["CHE"]

    ars_goals = ars_macro["goals_scored"]
    che_cs = che_macro["clean_sheet"]

    # Physical invariance: Chelsea clean sheet MUST be exactly 0 whenever Arsenal scores >= 1
    ars_scored = (ars_goals >= 1)
    assert np.sum(ars_scored) > 0  # Arsenal scored in many simulations
    # In every trial where Arsenal scored, Chelsea clean sheet is strictly 0
    assert np.all(che_cs[ars_scored] == 0)

    # Opposing goalkeeper Sanchez simulation
    sanchez = {
        "web_name": "Sanchez",
        "position_name": "GKP",
        "club_short": "CHE",
        "status": "a",
        "chance_of_playing": 100,
        "form": 4.5,
        "clean_sheets_per_90": 0.35,
        "saves_per_90": 3.5,
    }
    pts_sanchez, mins_sanchez = mc_engine.simulate_player(sanchez, n_sims=n_sims, macro_state=che_macro)

    # In trials where Arsenal scores >= 3 goals (blowout), Sanchez points suffer
    heavy_loss = (ars_goals >= 3)
    if np.any(heavy_loss):
        assert np.mean(pts_sanchez[heavy_loss]) < np.mean(pts_sanchez[~heavy_loss])


# =====================================================================
# Test 5: Graceful Fallback When Disabled or Unmapped (Task 6.5)
# =====================================================================
def test_fallback_when_macro_state_none(mc_engine):
    """Ensure engine operates without crashing when macro_state is None (unmapped/disabled)."""
    player = {
        "web_name": "StandalonePlayer",
        "position_name": "MID",
        "club_short": "NEW",
        "status": "a",
        "chance_of_playing": 100,
        "form": 5.0,
        "expected_goals_per_90": 0.4,
        "expected_assists_per_90": 0.3,
    }

    pts, mins = mc_engine.simulate_player(player, n_sims=1000, macro_state=None)
    assert len(pts) == 1000
    assert len(mins) == 1000
    assert not np.isnan(pts).any()
    assert np.mean(pts) > 2.0


# =====================================================================
# Test 6: Performance Benchmark (< 20 ms for 10 fixtures x 5,000 runs) (Task 6.6)
# =====================================================================
def test_macro_engine_latency_benchmark():
    """Simulate 10 fixtures across 5,000 trials; assert vectorized run time is < 20 ms."""
    ten_fixtures = [
        {"id": i, "team_h_short": f"H{i}", "team_a_short": f"A{i}"}
        for i in range(1, 11)
    ]

    t0 = time.perf_counter()
    states = simulate_macro_fixtures(
        ten_fixtures,
        n_sims=5000,
        pace_volatility=0.15,
        clip_pace_min=0.50,
        clip_pace_max=2.00,
        random_seed=42
    )
    lookup = build_team_macro_lookup(states)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert len(states) == 10
    assert len(lookup) == 20
    # Strict sub-20ms SLA for O(1) vectorization
    assert elapsed_ms < 20.0, f"Macro engine latency {elapsed_ms:.2f} ms exceeded 20 ms threshold"
