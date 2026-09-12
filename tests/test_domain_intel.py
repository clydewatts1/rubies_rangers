"""
Unit tests for Shane's Domain Intel Desk (analytics.domain_intel).
Rigidly verifies the Mathematical Identity Invariant (zero passive distortion),
temporal TTL decay, and override transformations.
"""

import os
import pytest
import pandas as pd
from analytics.domain_intel import (
    ShaneIntelManager,
    PlayerOverride,
    AvailabilityOption,
    EligibilityOption,
    TacticalOption,
    TTLWindow,
)


@pytest.fixture
def mock_players_df():
    return pd.DataFrame([
        {
            "web_name": "Pedro Porro",
            "club_name": "Spurs",
            "position_name": "DEF",
            "now_cost": 5.5,
            "status": "a",
            "chance_of_playing": 75,
            "fdr_moneyball_score": 10.0,
            "moneyball_score": 8.0,
            "expected_goal_involvements_per_90": 0.35,
        },
        {
            "web_name": "Phil Foden",
            "club_name": "Man City",
            "position_name": "MID",
            "now_cost": 9.5,
            "status": "a",
            "chance_of_playing": 100,
            "fdr_moneyball_score": 14.0,
            "moneyball_score": 12.0,
            "expected_goal_involvements_per_90": 0.65,
        }
    ])


def test_mathematical_identity_invariant_stage1(mock_players_df, tmp_path):
    """
    CRITICAL INVARIANT: f(Official_Data, Human_Defaults) === f(Official_Data)
    Unedited defaults MUST produce 0.00 delta.
    """
    mgr = ShaneIntelManager(storage_path=str(tmp_path / "test_intel.yaml"))
    # Add a default override (identity state)
    default_ov = PlayerOverride(
        web_name="Pedro Porro",
        valid_gameweek=5,
        availability=AvailabilityOption.DEFAULT_OFFICIAL,
        eligibility=EligibilityOption.DEFAULT_ELIGIBLE,
        tactical_risk=TacticalOption.DEFAULT_MINUTES,
        expected_minutes=85.0,
        eye_test_multiplier=1.00
    )
    mgr.set_override(default_ov)

    transformed = mgr.apply_pre_stage1_overrides(mock_players_df, current_gw=5)
    pd.testing.assert_frame_equal(transformed, mock_players_df)


def test_mathematical_identity_invariant_stage2(tmp_path):
    """Verify Stage 2 player dict passthrough with defaults."""
    mgr = ShaneIntelManager(storage_path=str(tmp_path / "test_intel.yaml"))
    player_dict = {
        "web_name": "Pedro Porro",
        "expected_minutes": 85.0,
        "chance_of_playing": 75,
        "status": "a"
    }
    default_ov = PlayerOverride(
        web_name="Pedro Porro",
        valid_gameweek=5,
        availability=AvailabilityOption.DEFAULT_OFFICIAL,
        expected_minutes=85.0
    )
    mgr.set_override(default_ov)
    transformed = mgr.apply_pre_stage2_overrides(player_dict, current_gw=5)
    assert transformed == player_dict


def test_ttl_decay_and_expiration(mock_players_df, tmp_path):
    """Overrides with CURRENT_GW_ONLY must expire when current_gw rolls forward."""
    mgr = ShaneIntelManager(storage_path=str(tmp_path / "test_intel.yaml"))
    ov = PlayerOverride(
        web_name="Pedro Porro",
        valid_gameweek=5,
        ttl_window=TTLWindow.CURRENT_GW_ONLY,
        availability=AvailabilityOption.CONFIRMED_OUT_0
    )
    mgr.set_override(ov)

    # In GW5, override applies
    gw5_df = mgr.apply_pre_stage1_overrides(mock_players_df, current_gw=5)
    porro_gw5 = gw5_df[gw5_df["web_name"] == "Pedro Porro"].iloc[0]
    assert porro_gw5["status"] == "u"
    assert porro_gw5["chance_of_playing"] == 0

    # In GW6, override is EXPIRED and purged from computation
    gw6_df = mgr.apply_pre_stage1_overrides(mock_players_df, current_gw=6)
    porro_gw6 = gw6_df[gw6_df["web_name"] == "Pedro Porro"].iloc[0]
    assert porro_gw6["status"] == "a"
    assert porro_gw6["chance_of_playing"] == 75


def test_confirmed_out_and_multiplier_overrides(mock_players_df, tmp_path):
    """Verify hard exclusion and multiplier adjustments."""
    mgr = ShaneIntelManager(storage_path=str(tmp_path / "test_intel.yaml"))
    # Exclude Porro
    mgr.set_override(PlayerOverride(
        web_name="Pedro Porro",
        valid_gameweek=5,
        availability=AvailabilityOption.CONFIRMED_OUT_0
    ))
    # Boost Foden by +20%
    mgr.set_override(PlayerOverride(
        web_name="Phil Foden",
        valid_gameweek=5,
        eye_test_multiplier=1.20
    ))

    res = mgr.apply_pre_stage1_overrides(mock_players_df, current_gw=5)
    porro = res[res["web_name"] == "Pedro Porro"].iloc[0]
    foden = res[res["web_name"] == "Phil Foden"].iloc[0]

    assert porro["status"] == "u"
    assert porro["fdr_moneyball_score"] == 0.0

    assert foden["status"] == "a"
    assert round(foden["fdr_moneyball_score"], 2) == 16.80  # 14.0 * 1.20
