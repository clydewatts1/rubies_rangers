"""
---
type: TestSuite
title: "FBref / StatsBomb Advanced Metrics Client & Modulator Tests"
description: "Unit and integration tests for FBref goalkeeper PSxG modeling, save points, outfield SCA/GCA BPS multipliers, and XPModel integration."
tags: [test, pytest, fbref, goalkeeper, psxg, sca, gca, xp]
sources: ["docs/design/des_022_soccerdata_fbref_advanced_metrics.md", "clients/fbref_client.py"]
generated:
  at: "2026-09-17T21:26:00Z"
  by: "agent:test-generation-python"
---
"""

import os
import json
import time
import math
import pytest
from unittest.mock import MagicMock, patch

from clients.fbref_client import (
    FBrefClient,
    GoalkeeperAdvancedMetrics,
    OutfieldAdvancedMetrics,
    compute_goalkeeper_expected_saves,
    compute_goalkeeper_effective_cs_prob,
    compute_outfield_bps_multiplier,
)
from analytics.xp_model import XPModel


# ---------------------------------------------------------------------------
# 1. Goalkeeper Save Expectancy & PSxG Clean Sheet Modulation
# ---------------------------------------------------------------------------

def test_compute_goalkeeper_expected_saves_proportionality():
    """Expected saves must scale proportionally with opponent goal threat."""
    saves_low = compute_goalkeeper_expected_saves(team_xgc=0.8, save_pct=0.72)
    saves_mid = compute_goalkeeper_expected_saves(team_xgc=1.5, save_pct=0.72)
    saves_high = compute_goalkeeper_expected_saves(team_xgc=2.5, save_pct=0.72)

    assert saves_low < saves_mid < saves_high


def test_compute_goalkeeper_expected_saves_save_pct_monotonicity():
    """Higher save percentage must yield higher expected saves against identical xGC."""
    saves_avg = compute_goalkeeper_expected_saves(team_xgc=1.5, save_pct=0.65)
    saves_elite = compute_goalkeeper_expected_saves(team_xgc=1.5, save_pct=0.77)

    assert saves_elite > saves_avg


def test_compute_goalkeeper_expected_saves_clamping():
    """Save count must respect minimum and maximum realistic match bounds."""
    assert compute_goalkeeper_expected_saves(team_xgc=0.05, save_pct=0.55) >= 1.0
    assert compute_goalkeeper_expected_saves(team_xgc=10.0, save_pct=0.85) <= 8.5


def test_compute_goalkeeper_effective_cs_prob_psxg_modulation():
    """Positive shot-stopping alpha (PSxG +/-) must strictly increase P(CS)."""
    base_cs = math.exp(-1.5)
    cs_neutral = compute_goalkeeper_effective_cs_prob(team_xgc=1.5, psxg_net_per90=0.0)
    cs_elite = compute_goalkeeper_effective_cs_prob(team_xgc=1.5, psxg_net_per90=0.25)
    cs_poor = compute_goalkeeper_effective_cs_prob(team_xgc=1.5, psxg_net_per90=-0.20)

    assert math.isclose(cs_neutral, base_cs, abs_tol=1e-3)
    assert cs_elite > cs_neutral > cs_poor


# ---------------------------------------------------------------------------
# 2. Outfield SCA & GCA BPS Bonus Multiplier
# ---------------------------------------------------------------------------

def test_compute_outfield_bps_multiplier_baseline():
    """Baseline SCA (2.8) and GCA (0.35) must produce neutral multiplier ~1.00."""
    mult = compute_outfield_bps_multiplier(sca90=2.80, gca90=0.35)
    assert math.isclose(mult, 1.00, abs_tol=1e-3)


def test_compute_outfield_bps_multiplier_elite_creative():
    """High-volume creators (e.g. Palmer, De Bruyne) must receive positive bonus boost."""
    mult_palmer = compute_outfield_bps_multiplier(sca90=5.40, gca90=0.95)
    assert mult_palmer > 1.10


def test_compute_outfield_bps_multiplier_clamping():
    """Multiplier must remain strictly bounded within [-15%, +25%] to prevent distortion."""
    mult_zero = compute_outfield_bps_multiplier(sca90=0.0, gca90=0.0)
    mult_extreme_low = compute_outfield_bps_multiplier(sca90=-10.0, gca90=-5.0)
    mult_max = compute_outfield_bps_multiplier(sca90=15.0, gca90=3.0)

    assert 0.85 <= mult_zero <= 0.90
    assert mult_extreme_low == 0.85
    assert mult_max == 1.25


# ---------------------------------------------------------------------------
# 3. Dataclass Immutability Contracts
# ---------------------------------------------------------------------------

def test_dataclass_contracts_immutable():
    """Advanced metric contracts must be frozen to prevent accidental state mutation."""
    gk = GoalkeeperAdvancedMetrics(
        web_name="Raya",
        team_code="ARS",
        psxg=28.0,
        goals_conceded=24.0,
        psxg_net_per90=0.12,
        save_pct=0.745,
        sota_per90=2.8,
        clean_sheet_pct=0.44,
        as_of_timestamp=100.0,
    )
    with pytest.raises(Exception):
        gk.save_pct = 0.80

    out = OutfieldAdvancedMetrics(
        web_name="Saka",
        team_code="ARS",
        sca90=5.12,
        gca90=0.82,
        npxg90=0.44,
        xag90=0.42,
        prog_carries90=4.6,
        prog_passes90=4.5,
        as_of_timestamp=100.0,
    )
    with pytest.raises(Exception):
        out.sca90 = 6.0


# ---------------------------------------------------------------------------
# 4. Caching & Retrieval
# ---------------------------------------------------------------------------

def test_fbref_client_disk_caching(tmp_path):
    """Client reads from local disk cache within TTL without executing fallback."""
    cache_file = str(tmp_path / "test_fbref_cache.json")
    mock_payload = {
        "as_of_timestamp": time.time(),
        "goalkeepers": {
            "testgk": {
                "web_name": "Testgk",
                "team_code": "ARS",
                "psxg": 25.0,
                "goals_conceded": 20.0,
                "psxg_net_per90": 0.15,
                "save_pct": 0.75,
                "sota_per90": 3.0,
                "clean_sheet_pct": 0.40,
                "as_of_timestamp": time.time(),
            }
        },
        "outfield": {
            "testout": {
                "web_name": "Testout",
                "team_code": "MCI",
                "sca90": 4.5,
                "gca90": 0.7,
                "npxg90": 0.4,
                "xag90": 0.3,
                "prog_carries90": 4.0,
                "prog_passes90": 5.0,
                "as_of_timestamp": time.time(),
            }
        },
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(mock_payload, f)

    client = FBrefClient(cache_file=cache_file)
    gks = client.get_goalkeeper_metrics(force_refresh=False)
    outfield = client.get_outfield_metrics(force_refresh=False)

    assert "testgk" in gks
    assert gks["testgk"].save_pct == 0.75
    assert "testout" in outfield
    assert outfield["testout"].sca90 == 4.5


# ---------------------------------------------------------------------------
# 5. Integration into XPModel
# ---------------------------------------------------------------------------

def test_xp_model_goalkeeper_fbref_integration():
    """Verify that XPModel utilizes FBref goalkeeper metrics to modulate saves and clean sheet."""
    mock_fbref = MagicMock(spec=FBrefClient)
    mock_fbref.get_player_metrics.side_effect = lambda name: (
        GoalkeeperAdvancedMetrics(
            web_name="Elitekeeper",
            team_code="ARS",
            psxg=30.0,
            goals_conceded=20.0,
            psxg_net_per90=0.30,  # Elite shot-stopper
            save_pct=0.82,        # Elite save rate
            sota_per90=3.5,
            clean_sheet_pct=0.45,
            as_of_timestamp=time.time(),
        ) if name == "elitekeeper" else None
    )

    xm = XPModel(gameweek=4, fbref_client=mock_fbref)
    p_dict = {"web_name": "Elitekeeper", "position_name": "GKP", "club_short": "ARS"}
    t_dict = {"avg_recent_mins": 90.0, "minutes_status": "SECURE_STARTER"}
    res = xm.calculate_player_xp(p_dict, t_dict, {})

    assert "xP" in res
    assert res["xP"] > 4.0


def test_xp_model_outfield_fbref_bps_integration():
    """Verify that XPModel modulates outfield bonus point expectations using SCA/GCA."""
    mock_fbref = MagicMock(spec=FBrefClient)
    mock_fbref.get_player_metrics.side_effect = lambda name: (
        OutfieldAdvancedMetrics(
            web_name="Playmaker",
            team_code="MCI",
            sca90=6.5,            # Ultra-elite creator
            gca90=1.1,
            npxg90=0.35,
            xag90=0.55,
            prog_carries90=4.5,
            prog_passes90=7.0,
            as_of_timestamp=time.time(),
        ) if name == "playmaker" else None
    )

    xm = XPModel(gameweek=4, fbref_client=mock_fbref)
    p_dict = {"web_name": "Playmaker", "position_name": "MID", "club_short": "MCI"}
    t_dict = {"avg_recent_mins": 90.0, "minutes_status": "SECURE_STARTER"}
    res = xm.calculate_player_xp(p_dict, t_dict, {})

    assert "xP" in res
    assert res["xP"] > 2.0
