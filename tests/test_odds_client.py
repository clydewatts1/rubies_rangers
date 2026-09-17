"""
---
type: TestSuite
title: "The Odds API Client & Vig-Removed Market Consensus Tests"
description: "Unit and integration tests for odds parsing, vig-removal, numerical inversion, quota governance, and XPModel integration."
tags: [test, pytest, odds, market, vig, xp]
sources: ["docs/design/des_020_the_odds_api_market_consensus.md", "clients/odds_client.py"]
generated:
  at: "2026-09-17T20:18:00Z"
  by: "agent:test-generation-python"
---
"""

import os
import json
import math
import pytest
from unittest.mock import MagicMock, patch

from clients.odds_client import (
    OddsClient,
    MarketOddsRecord,
    FairMarketExpectancy,
    normalize_team_name,
    remove_proportional_vig,
    solve_total_goals,
)
from analytics.xp_model import XPModel


# ---------------------------------------------------------------------------
# 1. Vig-Removal & Mathematical Formalisms
# ---------------------------------------------------------------------------

def test_remove_proportional_vig_standard():
    """Test standard 3-way 1X2 market odds vig removal."""
    # Decimal odds: Home 2.00 (50%), Draw 3.50 (28.57%), Away 4.00 (25%) -> Overround = 103.57%
    raw_odds = [2.00, 3.50, 4.00]
    fair_probs = remove_proportional_vig(raw_odds)

    assert len(fair_probs) == 3
    assert math.isclose(sum(fair_probs), 1.0, abs_tol=1e-3)
    assert fair_probs[0] > fair_probs[1] > fair_probs[2]


def test_remove_proportional_vig_two_way():
    """Test 2-way totals market (Over/Under 2.5) vig removal."""
    raw_odds = [1.90, 1.90]  # Overround = 105.26%
    fair_probs = remove_proportional_vig(raw_odds)

    assert len(fair_probs) == 2
    assert math.isclose(fair_probs[0], 0.5, abs_tol=1e-3)
    assert math.isclose(fair_probs[1], 0.5, abs_tol=1e-3)
    assert math.isclose(sum(fair_probs), 1.0, abs_tol=1e-3)


def test_remove_proportional_vig_invalid_edge():
    """Test edge case with non-positive odds."""
    res = remove_proportional_vig([0.0, 0.0])
    assert res == [0.5, 0.5]


# ---------------------------------------------------------------------------
# 2. Numerical Inversion: Poisson Under 2.5 -> Total Match Goals T
# ---------------------------------------------------------------------------

def test_solve_total_goals_bounds():
    """Test boundary clipping for extreme under/over probabilities."""
    assert solve_total_goals(0.01) == 4.80
    assert solve_total_goals(0.98) == 1.10


def test_solve_total_goals_monotonicity():
    """Higher P(Under 2.5) must strictly imply lower expected match goals T."""
    t_high_under = solve_total_goals(0.65)  # low-scoring game
    t_mid = solve_total_goals(0.48)         # average game
    t_low_under = solve_total_goals(0.35)   # high-scoring game

    assert t_high_under < t_mid < t_low_under
    assert 2.0 <= t_mid <= 3.2


def test_solve_total_goals_reconstruction_accuracy():
    """Verify that solved T reconstructs P(Under 2.5) = exp(-T)(1 + T + T^2/2) accurately."""
    target_p_under = 0.45
    solved_t = solve_total_goals(target_p_under)
    reconstructed_p = math.exp(-solved_t) * (1.0 + solved_t + 0.5 * solved_t ** 2)

    assert math.isclose(reconstructed_p, target_p_under, abs_tol=0.01)


# ---------------------------------------------------------------------------
# 3. Team Name Resolution
# ---------------------------------------------------------------------------

def test_normalize_team_name_variants():
    """Verify robust resolution of bookmaker names to FPL 3-letter codes."""
    assert normalize_team_name("Arsenal") == "ARS"
    assert normalize_team_name("AFC Bournemouth") == "BOU"
    assert normalize_team_name("Brighton and Hove Albion") == "BHA"
    assert normalize_team_name("Man City") == "MCI"
    assert normalize_team_name("Manchester United") == "MUN"
    assert normalize_team_name("Newcastle United FC") == "NEW"
    assert normalize_team_name("Wolverhampton Wanderers") == "WOL"
    assert normalize_team_name("Unknown FC 123") == "UNK"


# ---------------------------------------------------------------------------
# 4. Quota Governance & Safety Guards
# ---------------------------------------------------------------------------

def test_odds_client_no_api_key_safe():
    """Client without API key safely returns empty without error."""
    client = OddsClient(api_key=None)
    expectancies = client.get_market_expectancies(force_refresh=True)
    assert expectancies == {}
    quota = client.get_quota_info()
    assert quota["has_api_key"] is False


def test_odds_client_quota_exhausted_guard(tmp_path):
    """When requests_remaining < 5, client immediately aborts outbound network calls."""
    cache_path = str(tmp_path / "test_cache.json")
    client = OddsClient(api_key="mock-key-123", cache_file=cache_path)
    client.requests_remaining = 3  # Critical quota

    with patch("requests.get") as mock_get:
        expectancies = client.get_market_expectancies(force_refresh=True)
        assert expectancies == {}
        mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Fixture Parsing & Fair Market Expectancy Construction
# ---------------------------------------------------------------------------

def test_parse_fixtures_mock_payload():
    """Verify parsing of The Odds API JSON structure into FairMarketExpectancy."""
    mock_payload = [
        {
            "id": "epl_fixture_1",
            "sport_key": "soccer_epl",
            "commence_time": "2026-09-19T14:00:00Z",
            "home_team": "Liverpool",
            "away_team": "Fulham",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Liverpool", "price": 1.25},
                                {"name": "Draw", "price": 6.50},
                                {"name": "Fulham", "price": 12.00},
                            ],
                        },
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": 1.45, "point": 2.5},
                                {"name": "Under", "price": 2.80, "point": 2.5},
                            ],
                        },
                    ],
                }
            ],
        }
    ]

    client = OddsClient(api_key="mock-key")
    parsed = client._parse_fixtures(mock_payload)

    assert "LIV" in parsed
    liv_exp = parsed["LIV"]

    assert liv_exp.home_team == "LIV"
    assert liv_exp.away_team == "FUL"
    assert liv_exp.prob_home_win > 0.70
    assert liv_exp.exp_goals_home > liv_exp.exp_goals_away
    assert liv_exp.clean_sheet_prob_home == round(math.exp(-liv_exp.exp_goals_away), 3)
    assert liv_exp.clean_sheet_prob_away == round(math.exp(-liv_exp.exp_goals_home), 3)
    assert liv_exp.is_market_derived is True


# ---------------------------------------------------------------------------
# 6. Team Odds Map Conversion for XPModel
# ---------------------------------------------------------------------------

def test_build_team_odds_map_format():
    """Verify that build_team_odds_map produces exact schema required by XPModel."""
    client = OddsClient(api_key="mock-key")
    mock_expectancies = {
        "ARS": FairMarketExpectancy(
            home_team="ARS",
            away_team="TOT",
            prob_home_win=0.55,
            prob_draw=0.25,
            prob_away_win=0.20,
            prob_over_25=0.58,
            prob_under_25=0.42,
            total_exp_goals=2.95,
            exp_goals_home=1.95,
            exp_goals_away=1.00,
            clean_sheet_prob_home=0.368,
            clean_sheet_prob_away=0.142,
            clean_sheet_odds_home=2.72,
            clean_sheet_odds_away=7.04,
            is_market_derived=True,
        )
    }

    odds_map = client.build_team_odds_map(mock_expectancies)
    assert "ARS" in odds_map
    assert "TOT" in odds_map

    ars = odds_map["ARS"]
    assert ars["team"] == "ARS"
    assert ars["opponent"] == "TOT"
    assert ars["is_home"] is True
    assert ars["exp_goals_scored"] == 1.95
    assert ars["exp_goals_conceded"] == 1.00
    assert ars["clean_sheet_prob"] == 0.368
    assert ars["market_derived"] is True

    tot = odds_map["TOT"]
    assert tot["team"] == "TOT"
    assert tot["opponent"] == "ARS"
    assert tot["is_home"] is False
    assert tot["exp_goals_scored"] == 1.00
    assert tot["exp_goals_conceded"] == 1.95
    assert tot["clean_sheet_prob"] == 0.142


# ---------------------------------------------------------------------------
# 7. Tiered Integration in XPModel
# ---------------------------------------------------------------------------

def test_xp_model_tiered_odds_integration():
    """Verify that XPModel prioritizes Tier 1 (OddsClient) when available."""
    mock_odds_client = MagicMock(spec=OddsClient)
    mock_odds_client.build_team_odds_map.return_value = {
        "MCI": {
            "team": "MCI",
            "opponent": "CHE",
            "is_home": True,
            "exp_goals_scored": 2.40,
            "exp_goals_conceded": 0.85,
            "clean_sheet_prob": 0.427,
            "clean_sheet_odds": 2.34,
            "fixture_str": "CHE (H)",
            "market_derived": True,
        }
    }

    xp = XPModel(gameweek=4, odds_client=mock_odds_client)
    assert "MCI" in xp.team_odds
    assert xp.team_odds["MCI"]["exp_goals_scored"] == 2.40
    assert xp.team_odds["MCI"].get("market_derived") is True


def test_xp_model_fallback_when_odds_client_empty():
    """Verify that XPModel gracefully falls back to ClubElo / GW4 odds when market odds are empty."""
    mock_odds_client = MagicMock(spec=OddsClient)
    mock_odds_client.build_team_odds_map.return_value = {}

    xp = XPModel(gameweek=4, odds_client=mock_odds_client)
    # Falls back to ClubElo or GW4 calibrated odds
    assert len(xp.team_odds) > 0
    assert "LIV" in xp.team_odds
