"""
---
type: TestSuite
title: "Premier League Referee Historical Analytics & Tendency Client Tests"
description: "Unit and integration tests for referee penalty multipliers, card accumulation rates, appointment mapping, baseline fallbacks, and XP/Monte Carlo engine integration."
tags: [test, pytest, referee, penalties, cards, montecarlo, xp]
sources: ["docs/design/des_024_referee_penalty_variance_modeling.md", "clients/referee_client.py"]
generated:
  at: "2026-09-17T21:38:00Z"
  by: "agent:test-generation-python"
---
"""

import os
import json
import pytest
from unittest.mock import MagicMock

from clients.referee_client import (
    RefereeClient,
    RefereeProfile,
    compute_referee_penalty_multiplier,
    compute_referee_yellow_multiplier,
    compute_referee_red_multiplier,
    determine_card_risk_tier,
    normalize_name,
    LEAGUE_BASELINE_PROFILE,
)
from analytics.xp_model import XPModel
from analytics.montecarlo import MonteCarloEngine


# ---------------------------------------------------------------------------
# 1. Multiplier Mathematical Properties & Boundary Clamping
# ---------------------------------------------------------------------------

def test_compute_referee_penalty_multiplier_neutral():
    """Baseline penalty award rate must produce exactly 1.0."""
    assert compute_referee_penalty_multiplier(0.20, league_avg=0.20) == 1.0


def test_compute_referee_penalty_multiplier_high_and_low():
    """High penalty referee must produce >1.0 multiplier; conservative official must produce <1.0."""
    mult_high = compute_referee_penalty_multiplier(0.36, league_avg=0.20)
    mult_low = compute_referee_penalty_multiplier(0.15, league_avg=0.20)

    assert mult_high == 1.80
    assert mult_low == 0.75
    assert mult_high > 1.0 > mult_low


def test_compute_referee_penalty_multiplier_clamping():
    """Penalty multiplier must clamp strictly between [0.65, 1.85]."""
    assert compute_referee_penalty_multiplier(0.01, league_avg=0.20) == 0.65
    assert compute_referee_penalty_multiplier(0.90, league_avg=0.20) == 1.85


def test_compute_referee_yellow_multiplier_clamping():
    """Yellow card multiplier must clamp strictly between [0.75, 1.35]."""
    assert compute_referee_yellow_multiplier(1.0, league_avg=3.95) == 0.75
    assert compute_referee_yellow_multiplier(10.0, league_avg=3.95) == 1.35


def test_compute_referee_red_multiplier_clamping():
    """Red card multiplier must clamp strictly between [0.60, 1.60]."""
    assert compute_referee_red_multiplier(0.01, league_avg=0.11) == 0.60
    assert compute_referee_red_multiplier(0.50, league_avg=0.11) == 1.60


def test_determine_card_risk_tier():
    """Risk tier must map to qualitative strictness categories."""
    assert determine_card_risk_tier(4.70) == "EXTREME"
    assert determine_card_risk_tier(4.25) == "ELEVATED"
    assert determine_card_risk_tier(3.80) == "MODERATE"
    assert determine_card_risk_tier(3.40) == "LOW"


# ---------------------------------------------------------------------------
# 2. Dataclass Contracts & Name Normalization
# ---------------------------------------------------------------------------

def test_referee_profile_frozen():
    """RefereeProfile must be immutable (frozen)."""
    prof = RefereeProfile(
        name="Anthony Taylor",
        matches_refereed=360,
        penalties_per_match=0.36,
        yellows_per_match=4.25,
        reds_per_match=0.14,
        fouls_per_tackle=0.61,
        penalty_multiplier=1.80,
        yellow_multiplier=1.08,
        red_multiplier=1.27,
        card_risk_tier="ELEVATED",
    )
    with pytest.raises(Exception):
        prof.penalty_multiplier = 2.0  # type: ignore


def test_normalize_name():
    """Normalization strips accents and non-alphanumeric characters."""
    assert normalize_name("Anthony Taylor") == "anthony taylor"
    assert normalize_name("Martin Ødegaard") == "martin odegaard"
    assert normalize_name("  Craig PAWSON!  ") == "craig pawson"


# ---------------------------------------------------------------------------
# 3. Client Lookup & Fallback Mechanics
# ---------------------------------------------------------------------------

def test_referee_client_default_load():
    """RefereeClient should load active referees from data/referee_tendencies.json."""
    client = RefereeClient()
    refs = client.get_all_referees()

    assert len(refs) >= 15
    assert "anthony taylor" in refs
    assert "michael oliver" in refs


def test_referee_client_get_referee_profile_tokens():
    """Lookup by last name token should find official."""
    client = RefereeClient()
    prof = client.get_referee_profile("Taylor")
    assert prof.name == "Anthony Taylor"
    assert prof.penalty_multiplier == 1.80


def test_referee_client_unknown_referee_fallback():
    """Unknown official must return LEAGUE_BASELINE_PROFILE with 1.0 multipliers."""
    client = RefereeClient()
    prof = client.get_referee_profile("Unknown Rookie Ref")
    assert prof.name == "League Average Official"
    assert prof.penalty_multiplier == 1.0
    assert prof.yellow_multiplier == 1.0


def test_referee_client_get_referee_for_team():
    """Lookup by team code should resolve appointed match official."""
    client = RefereeClient()
    prof_mci = client.get_referee_for_team("MCI")
    prof_tot = client.get_referee_for_team("TOT")

    assert prof_mci.name in ["Anthony Taylor", "Robert Jones", "Michael Oliver"]
    assert prof_tot.name in ["Robert Jones", "Anthony Taylor", "Michael Oliver"]


def test_referee_client_unknown_team_fallback():
    """Unassigned or unknown team must return LEAGUE_BASELINE_PROFILE."""
    client = RefereeClient()
    prof = client.get_referee_for_team("NON_EXISTENT_TEAM")
    assert prof == LEAGUE_BASELINE_PROFILE


# ---------------------------------------------------------------------------
# 4. Integration into XPModel
# ---------------------------------------------------------------------------

def test_xp_model_referee_penalty_sensitivity():
    """A designated penalty taker must receive higher xP under a high-penalty referee than a strict referee."""
    high_pen_ref = RefereeProfile(
        name="HighWhistle",
        matches_refereed=100,
        penalties_per_match=0.38,
        yellows_per_match=3.95,
        reds_per_match=0.11,
        fouls_per_tackle=0.58,
        penalty_multiplier=1.85,
        yellow_multiplier=1.0,
        red_multiplier=1.0,
        card_risk_tier="MODERATE",
    )
    low_pen_ref = RefereeProfile(
        name="LowWhistle",
        matches_refereed=100,
        penalties_per_match=0.14,
        yellows_per_match=3.95,
        reds_per_match=0.11,
        fouls_per_tackle=0.58,
        penalty_multiplier=0.70,
        yellow_multiplier=1.0,
        red_multiplier=1.0,
        card_risk_tier="MODERATE",
    )

    mock_client_high = MagicMock(spec=RefereeClient)
    mock_client_high.get_referee_for_team.return_value = high_pen_ref

    mock_client_low = MagicMock(spec=RefereeClient)
    mock_client_low.get_referee_for_team.return_value = low_pen_ref

    xm_high = XPModel(gameweek=4, referee_client=mock_client_high)
    xm_low = XPModel(gameweek=4, referee_client=mock_client_low)

    p_dict = {
        "web_name": "Haaland",
        "position_name": "FWD",
        "club_short": "MCI",
        "penalties_order": 1,
        "expected_goals_per_90": 0.75,
    }
    t_dict = {"avg_recent_mins": 90.0, "minutes_status": "SECURE_STARTER"}

    res_high = xm_high.calculate_player_xp(p_dict, t_dict, {})
    res_low = xm_low.calculate_player_xp(p_dict, t_dict, {})

    assert res_high["referee_penalty_multiplier"] == 1.85
    assert res_low["referee_penalty_multiplier"] == 0.70
    assert res_high["xP"] > res_low["xP"]


def test_xp_model_referee_telemetry_keys():
    """Returned player prediction must include referee telemetry."""
    xm = XPModel(gameweek=4)
    p_dict = {"web_name": "Saka", "position_name": "MID", "club_short": "ARS"}
    t_dict = {"avg_recent_mins": 90.0, "minutes_status": "SECURE_STARTER"}

    res = xm.calculate_player_xp(p_dict, t_dict, {})

    assert "referee_name" in res
    assert "referee_penalty_multiplier" in res
    assert "referee_card_risk_tier" in res
    assert isinstance(res["referee_penalty_multiplier"], float)


# ---------------------------------------------------------------------------
# 5. Integration into MonteCarloEngine
# ---------------------------------------------------------------------------

def test_monte_carlo_engine_referee_integration():
    """MonteCarloEngine should initialize referee client and execute stochastic simulations."""
    mc = MonteCarloEngine()
    assert hasattr(mc, "referee_client")
    assert mc.referee_client is not None

    p_dict = {
        "web_name": "Haaland",
        "position_name": "FWD",
        "club_short": "MCI",
        "penalties_order": 1,
        "expected_goals_per_90": 0.8,
    }
    t_dict = {"avg_recent_mins": 90.0, "minutes_status": "SECURE_STARTER"}

    pts, mins = mc.simulate_player(p_dict, t_dict, {}, n_sims=500)
    assert len(pts) == 500
    assert len(mins) == 500
    assert pts.mean() > 0.0
