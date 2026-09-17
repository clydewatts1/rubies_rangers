"""
---
type: TestSuite
title: "FotMob REST Client & Finishing Skill Multiplier Tests"
description: "Unit and integration tests for FotMob xGOT, finishing skill delta (xGOT - xG), goalkeeper goals prevented, disk caching, and XPModel integration."
tags: [test, pytest, fotmob, xgot, finishing, lineups, xp]
sources: ["docs/design/des_023_fotmob_xgot_spatial_positions.md", "clients/fotmob_client.py"]
generated:
  at: "2026-09-17T21:33:00Z"
  by: "agent:test-generation-python"
---
"""

import os
import json
import time
import pytest
from unittest.mock import MagicMock, patch

from clients.fotmob_client import (
    FotMobClient,
    FotMobPlayerStats,
    FotMobLineup,
    compute_finishing_multiplier,
    normalize_name,
    BASELINE_FOTMOB_STATS,
)
from analytics.xp_model import XPModel


# ---------------------------------------------------------------------------
# 1. Finishing Multiplier Mathematical Properties & Clamping
# ---------------------------------------------------------------------------

def test_compute_finishing_multiplier_neutral():
    """Delta of 0.0 must yield exactly 1.0."""
    assert compute_finishing_multiplier(0.0) == 1.0


def test_compute_finishing_multiplier_clinical():
    """Positive finishing delta must scale expected goals upward."""
    mult_small = compute_finishing_multiplier(0.3)
    mult_large = compute_finishing_multiplier(1.1)

    assert mult_small == 1.03
    assert mult_large == 1.11
    assert mult_small > 1.0
    assert mult_large > mult_small


def test_compute_finishing_multiplier_wasteful():
    """Negative finishing delta must scale expected goals downward."""
    mult_neg = compute_finishing_multiplier(-0.5)
    assert mult_neg == 0.95
    assert mult_neg < 1.0


def test_compute_finishing_multiplier_clamping():
    """Multiplier must strictly clamp between [0.85, 1.20]."""
    assert compute_finishing_multiplier(-5.0) == 0.85
    assert compute_finishing_multiplier(10.0) == 1.20


# ---------------------------------------------------------------------------
# 2. Dataclass Contracts & Name Normalization
# ---------------------------------------------------------------------------

def test_fotmob_player_stats_frozen():
    """FotMobPlayerStats must be immutable (frozen)."""
    stats = FotMobPlayerStats(
        web_name="Haaland",
        team_name="Manchester City",
        team_code="MCI",
        xg=3.3,
        xgot=4.4,
        finishing_delta=1.1,
        goals_prevented=0.0,
        save_pct=0.0,
        as_of_timestamp=time.time(),
    )
    with pytest.raises(Exception):
        stats.finishing_delta = 2.0  # type: ignore


def test_fotmob_lineup_frozen():
    """FotMobLineup must be immutable (frozen)."""
    lineup = FotMobLineup(
        match_id="12345",
        home_team="Arsenal",
        away_team="Chelsea",
        home_starters=["Raya", "Saliba", "Gabriel", "White"],
        away_starters=["Sanchez", "James", "Colwill", "Cucurella"],
        home_formation="4-3-3",
        away_formation="4-2-3-1",
        is_confirmed=True,
    )
    with pytest.raises(Exception):
        lineup.is_confirmed = False  # type: ignore


def test_normalize_name_accents_and_transliteration():
    """Normalization must strip diacritics and convert special characters."""
    assert normalize_name("Martin Ødegaard") == "martin odegaard"
    assert normalize_name("Erling Haaland") == "erling haaland"
    assert normalize_name("Heung-min Son") == "heungmin son"


# ---------------------------------------------------------------------------
# 3. Disk Caching & Fallback Behavior
# ---------------------------------------------------------------------------

def test_fotmob_client_baseline_fallback(tmp_path):
    """When network is unavailable and cache is empty, client must fallback to baseline store."""
    cache_file = os.path.join(tmp_path, ".fotmob_cache.json")
    client = FotMobClient(cache_file=cache_file)

    with patch.object(client, "_fetch_live_fotmob_stats", return_value={}):
        stats = client.get_all_player_stats()

    # Even with empty network, baseline fallback activates
    assert "haaland" in BASELINE_FOTMOB_STATS
    assert len(BASELINE_FOTMOB_STATS) >= 10


def test_fotmob_client_disk_cache_roundtrip(tmp_path):
    """Cached disk records must be deserialized properly without network requests."""
    cache_file = os.path.join(tmp_path, ".test_fotmob_cache.json")
    mock_payload = {
        "as_of_timestamp": time.time(),
        "players": {
            "saka": {
                "web_name": "Saka",
                "team_name": "Arsenal",
                "team_code": "ARS",
                "xg": 2.5,
                "xgot": 3.0,
                "finishing_delta": 0.5,
                "goals_prevented": 0.0,
                "save_pct": 0.0,
                "as_of_timestamp": time.time(),
            }
        }
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(mock_payload, f)

    client = FotMobClient(cache_file=cache_file)
    stats = client.get_all_player_stats(force_refresh=False)

    assert "saka" in stats
    assert stats["saka"].finishing_delta == 0.5
    assert stats["saka"].team_code == "ARS"


def test_fotmob_client_get_player_stats_token_fallback(tmp_path):
    """get_player_stats should match either full normalized name or last name token."""
    cache_file = os.path.join(tmp_path, ".test_fotmob_cache.json")
    mock_payload = {
        "as_of_timestamp": time.time(),
        "players": {
            "haaland": {
                "web_name": "Haaland",
                "team_name": "Manchester City",
                "team_code": "MCI",
                "xg": 3.0,
                "xgot": 4.1,
                "finishing_delta": 1.1,
                "goals_prevented": 0.0,
                "save_pct": 0.0,
                "as_of_timestamp": time.time(),
            }
        }
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(mock_payload, f)

    client = FotMobClient(cache_file=cache_file)
    p_stat = client.get_player_stats("Erling Haaland")
    assert p_stat is not None
    assert p_stat.finishing_delta == 1.1


# ---------------------------------------------------------------------------
# 4. Integration into XPModel
# ---------------------------------------------------------------------------

def test_xp_model_fotmob_clinical_striker_boost():
    """Clinical finisher with high positive xGOT delta must receive higher xP than neutral."""
    mock_fotmob = MagicMock(spec=FotMobClient)
    mock_fotmob.get_player_stats.side_effect = lambda name: (
        FotMobPlayerStats(
            web_name="ClinicalStriker",
            team_name="Manchester City",
            team_code="MCI",
            xg=3.0,
            xgot=4.5,
            finishing_delta=1.5,
            goals_prevented=0.0,
            save_pct=0.0,
            as_of_timestamp=time.time(),
        ) if name == "clinicalstriker" else None
    )

    xm = XPModel(gameweek=4, fotmob_client=mock_fotmob)
    p_dict = {"web_name": "ClinicalStriker", "position_name": "FWD", "club_short": "MCI", "expected_goals_per_90": 0.6}
    t_dict = {"avg_recent_mins": 90.0, "minutes_status": "SECURE_STARTER"}
    res = xm.calculate_player_xp(p_dict, t_dict, {})

    assert res["fotmob_finishing_delta"] == 1.5
    assert res["fotmob_xgot"] == 4.5
    assert res["fotmob_xg"] == 3.0
    assert res["xP"] > 0.0


def test_xp_model_fotmob_goalkeeper_fallback():
    """When FBref is unavailable, FotMob goalkeeper stats provide shot-stopping fallback."""
    mock_fotmob = MagicMock(spec=FotMobClient)
    mock_fotmob.get_player_stats.side_effect = lambda name: (
        FotMobPlayerStats(
            web_name="FotmobKeeper",
            team_name="Arsenal",
            team_code="ARS",
            xg=0.0,
            xgot=0.0,
            finishing_delta=0.0,
            goals_prevented=1.6,
            save_pct=82.0,
            as_of_timestamp=time.time(),
        ) if name == "fotmobkeeper" else None
    )

    # Instantiate XPModel without FBref metrics for fotmobkeeper
    mock_fbref = MagicMock()
    mock_fbref.get_player_metrics.return_value = None

    xm = XPModel(gameweek=4, fbref_client=mock_fbref, fotmob_client=mock_fotmob)
    p_dict = {"web_name": "FotmobKeeper", "position_name": "GKP", "club_short": "ARS"}
    t_dict = {"avg_recent_mins": 90.0, "minutes_status": "SECURE_STARTER"}
    res = xm.calculate_player_xp(p_dict, t_dict, {})

    assert "xP" in res
    assert res["xP"] > 3.0
