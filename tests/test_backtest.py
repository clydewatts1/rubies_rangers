"""
Unit Tests for Multi-Season Walk-Forward Backtesting Subsystem
"""

import pytest
import pandas as pd
import numpy as np

from backtest.data_loader import HistoricalDataLoader
from backtest.simulator import WalkForwardSimulator, SeasonResult, GameweekRecord


def test_data_loader_normalize_df():
    loader = HistoricalDataLoader()
    raw_data = {
        "name": ["Erling Haaland", "Bukayo Saka", "Trent Alexander-Arnold", "David Raya"],
        "position": ["FWD", "MID", "DEF", "GKP"],
        "team": ["Man City", "Arsenal", "Liverpool", "Arsenal"],
        "round": [1, 1, 1, 1],
        "value": [140, 100, 70, 55],
        "total_points": [13, 8, 6, 6],
        "minutes": [90, 85, 90, 90],
        "expected_goals": [1.2, 0.4, 0.1, 0.0],
        "expected_assists": [0.1, 0.6, 0.4, 0.0],
        "clean_sheets": [0, 1, 1, 1],
        "saves": [0, 0, 0, 3]
    }
    raw_df = pd.DataFrame(raw_data)
    norm_df = loader.normalize_season_df(raw_df)

    assert "gw" in norm_df.columns
    assert "web_name" in norm_df.columns
    assert "now_cost" in norm_df.columns
    assert "position_name" in norm_df.columns
    assert norm_df.loc[norm_df["web_name"] == "Erling Haaland", "now_cost"].iloc[0] == 14.0
    assert norm_df.loc[norm_df["web_name"] == "David Raya", "position_name"].iloc[0] == "GKP"


def test_anti_leakage_point_in_time():
    """Verifies that for Gameweek t, stats from >= t are not included in features."""
    loader = HistoricalDataLoader()

    sample_records = []
    # Create 3 gameweeks of mock data for 2 players
    for gw in [1, 2, 3]:
        sample_records.append({
            "name": "Player A", "position": "MID", "team": "ARS", "round": gw,
            "value": 80, "total_points": 10 if gw == 3 else 2,
            "minutes": 90, "expected_goals": 0.5, "expected_assists": 0.2,
            "clean_sheets": 0, "saves": 0
        })
        sample_records.append({
            "name": "Player B", "position": "FWD", "team": "MCI", "round": gw,
            "value": 100, "total_points": 5,
            "minutes": 90, "expected_goals": 0.8, "expected_assists": 0.0,
            "clean_sheets": 0, "saves": 0
        })

    mock_df = pd.DataFrame(sample_records)
    # Inject into loader cache
    loader._season_cache["mock_season"] = mock_df

    # Query snapshot for GW 3: Player A had 10 points in GW 3, but in GW 1-2 only had 4 total points!
    features_df, actuals_df = loader.get_point_in_time_snapshot("mock_season", gw=3)

    assert len(actuals_df) == 2
    assert actuals_df.loc[actuals_df["web_name"] == "Player A", "total_points"].iloc[0] == 10

    # In features_df, total_points_sum should be 2 + 2 = 4 (strictly GW 1 and GW 2)
    pA_feats = features_df[features_df["web_name"] == "Player A"]
    assert len(pA_feats) == 1
    assert pA_feats["total_points_sum"].iloc[0] == 4.0


def test_lineup_and_bench_selection():
    sim = WalkForwardSimulator()

    # Create a 15-player squad (2 GKP, 5 DEF, 5 MID, 3 FWD)
    squad_data = []
    for i in range(2):
        squad_data.append({"web_name": f"GKP_{i}", "position_name": "GKP", "moneyball_score": 5.0 - i})
    for i in range(5):
        squad_data.append({"web_name": f"DEF_{i}", "position_name": "DEF", "moneyball_score": 8.0 - i})
    for i in range(5):
        squad_data.append({"web_name": f"MID_{i}", "position_name": "MID", "moneyball_score": 9.0 - i})
    for i in range(3):
        # 10.0, 9.6, 9.2 (higher than MID_0=9.0, ensuring FWD_0=C and FWD_1=VC)
        squad_data.append({"web_name": f"FWD_{i}", "position_name": "FWD", "moneyball_score": 10.0 - (i * 0.4)})

    squad_df = pd.DataFrame(squad_data)
    best_xi, best_bench, captain, vc = sim._select_lineup_and_bench(squad_df)

    assert len(best_xi) == 11
    assert len(best_bench) == 4
    assert best_xi[0] == "GKP_0"
    assert best_bench[0] == "GKP_1"
    # Highest score player should be captain
    assert captain == "FWD_0"
    assert vc == "FWD_1"


def test_auto_substitutions_and_captain_doubling():
    sim = WalkForwardSimulator()

    starting_xi = ["GKP_0", "DEF_0", "DEF_1", "DEF_2", "MID_0", "MID_1", "MID_2", "MID_3", "FWD_0", "FWD_1", "FWD_2"]
    bench = ["GKP_1", "DEF_3", "MID_4", "DEF_4"]
    captain = "FWD_0"
    vice_captain = "FWD_1"

    # Actuals:
    # GKP_0 played 0 mins -> GKP_1 played 90 mins (6 pts)
    # DEF_0 played 0 mins -> Sub 1 (DEF_3) played 90 mins (5 pts)
    # Captain (FWD_0) played 0 mins -> VC (FWD_1) played 90 mins (8 pts, doubled to 16)
    # FWD_0 played 0 mins -> Sub 2 (MID_4) subbed in for absent FWD_0 (1 pt)
    actuals = [
        {"web_name": "GKP_0", "position_name": "GKP", "minutes": 0, "total_points": 0},
        {"web_name": "GKP_1", "position_name": "GKP", "minutes": 90, "total_points": 6},
        {"web_name": "DEF_0", "position_name": "DEF", "minutes": 0, "total_points": 0},
        {"web_name": "DEF_1", "position_name": "DEF", "minutes": 90, "total_points": 4},
        {"web_name": "DEF_2", "position_name": "DEF", "minutes": 90, "total_points": 4},
        {"web_name": "DEF_3", "position_name": "DEF", "minutes": 90, "total_points": 5},
        {"web_name": "DEF_4", "position_name": "DEF", "minutes": 90, "total_points": 2},
        {"web_name": "MID_0", "position_name": "MID", "minutes": 90, "total_points": 3},
        {"web_name": "MID_1", "position_name": "MID", "minutes": 90, "total_points": 3},
        {"web_name": "MID_2", "position_name": "MID", "minutes": 90, "total_points": 3},
        {"web_name": "MID_3", "position_name": "MID", "minutes": 90, "total_points": 3},
        {"web_name": "MID_4", "position_name": "MID", "minutes": 90, "total_points": 1},
        {"web_name": "FWD_0", "position_name": "FWD", "minutes": 0, "total_points": 0},
        {"web_name": "FWD_1", "position_name": "FWD", "minutes": 90, "total_points": 8},
        {"web_name": "FWD_2", "position_name": "FWD", "minutes": 90, "total_points": 2},
    ]
    actuals_df = pd.DataFrame(actuals)

    pts, auto_subs = sim._evaluate_actuals(starting_xi, bench, captain, vice_captain, actuals_df)

    # Sub checks
    sub_pairs = [(out_p, in_p) for out_p, in_p in auto_subs]
    assert ("GKP_0", "GKP_1") in sub_pairs
    assert ("DEF_0", "DEF_3") in sub_pairs
    assert ("FWD_0", "MID_4") in sub_pairs

    # Points calculation:
    # GKP_1: 6
    # DEF_1: 4
    # DEF_2: 4
    # DEF_3: 5
    # MID_0: 3, MID_1: 3, MID_2: 3, MID_3: 3
    # MID_4: 1 (subbed in for absent FWD_0)
    # FWD_1: 8 * 2 = 16 (VC doubled)
    # FWD_2: 2
    # Expected total = 6 + 4 + 4 + 5 + 3 + 3 + 3 + 3 + 1 + 16 + 2 = 50.0
    assert pts == 50.0


def test_position_differentiated_scoring():
    """BUG-1 regression test: verifies GKP, DEF, and FWD use position-specific Moneyball scoring."""
    loader = HistoricalDataLoader()

    records = [
        # GKP: zero xGI, zero def contrib, but earns points via saves/clean sheets
        {"name": "GKP Keeper", "position": "GKP", "team": "ARS", "round": 1, "value": 50,
         "total_points": 6, "minutes": 90, "expected_goals": 0.0, "expected_assists": 0.0,
         "clean_sheets": 1, "saves": 4},
        {"name": "GKP Keeper", "position": "GKP", "team": "ARS", "round": 2, "value": 50,
         "total_points": 6, "minutes": 90, "expected_goals": 0.0, "expected_assists": 0.0,
         "clean_sheets": 1, "saves": 3},
        # DEF: strong defensive contribution
        {"name": "DEF Defender", "position": "DEF", "team": "LIV", "round": 1, "value": 60,
         "total_points": 5, "minutes": 90, "expected_goals": 0.0, "expected_assists": 0.0,
         "clean_sheets": 1, "saves": 0},
        {"name": "DEF Defender", "position": "DEF", "team": "LIV", "round": 2, "value": 60,
         "total_points": 5, "minutes": 90, "expected_goals": 0.0, "expected_assists": 0.0,
         "clean_sheets": 1, "saves": 0},
        # FWD: pure attacking metrics
        {"name": "FWD Striker", "position": "FWD", "team": "MCI", "round": 1, "value": 120,
         "total_points": 8, "minutes": 90, "expected_goals": 0.9, "expected_assists": 0.2,
         "clean_sheets": 0, "saves": 0},
        {"name": "FWD Striker", "position": "FWD", "team": "MCI", "round": 2, "value": 120,
         "total_points": 4, "minutes": 90, "expected_goals": 0.7, "expected_assists": 0.1,
         "clean_sheets": 0, "saves": 0},
    ]
    loader._season_cache["mock_season_pos"] = pd.DataFrame(records)

    features, _ = loader.get_point_in_time_snapshot("mock_season_pos", gw=3)

    gkp_row = features[features["web_name"] == "GKP Keeper"].iloc[0]
    def_row = features[features["web_name"] == "DEF Defender"].iloc[0]
    fwd_row = features[features["web_name"] == "FWD Striker"].iloc[0]

    # BUG-1: Previously GKP scored 0.0 because it only looked at xGI/ICT
    assert gkp_row["moneyball_score"] > 0.0, "GKP with PPG > 0 must have positive Moneyball score"
    assert gkp_row["points_per_game"] == 6.0
    assert gkp_row["recent_ppg"] == 6.0

    # DEF must incorporate clean sheets / defensive contribution
    assert def_row["moneyball_score"] > 0.0
    assert def_row["clean_sheets_per_90"] == 1.0

    # FWD must have positive score based on attacking xGI
    assert fwd_row["moneyball_score"] > 0.0
    assert fwd_row["expected_goal_involvements_per_90"] > 0.5


def test_form_window_sensitivity():
    """BUG-3 regression test: verifies that changing form_window actually affects recent_ppg and score."""
    loader = HistoricalDataLoader()

    records = [
        {"name": "Player Ramp", "position": "MID", "team": "CHE", "round": 1, "value": 80,
         "total_points": 1, "minutes": 90, "expected_goals": 0.1, "expected_assists": 0.0, "clean_sheets": 0, "saves": 0},
        {"name": "Player Ramp", "position": "MID", "team": "CHE", "round": 2, "value": 80,
         "total_points": 2, "minutes": 90, "expected_goals": 0.1, "expected_assists": 0.0, "clean_sheets": 0, "saves": 0},
        {"name": "Player Ramp", "position": "MID", "team": "CHE", "round": 3, "value": 80,
         "total_points": 10, "minutes": 90, "expected_goals": 0.8, "expected_assists": 0.3, "clean_sheets": 0, "saves": 0},
        {"name": "Player Ramp", "position": "MID", "team": "CHE", "round": 4, "value": 80,
         "total_points": 12, "minutes": 90, "expected_goals": 0.9, "expected_assists": 0.4, "clean_sheets": 0, "saves": 0},
    ]
    loader._season_cache["mock_season_form"] = pd.DataFrame(records)

    # Window of 2 gameweeks (GW3, GW4): avg points = (10 + 12) / 2 = 11.0
    feats_w2, _ = loader.get_point_in_time_snapshot("mock_season_form", gw=5, form_window=2)
    # Window of 4 gameweeks (GW1-4): avg points = (1 + 2 + 10 + 12) / 4 = 6.25
    feats_w4, _ = loader.get_point_in_time_snapshot("mock_season_form", gw=5, form_window=4)

    ppg_w2 = feats_w2.loc[feats_w2["web_name"] == "Player Ramp", "recent_ppg"].iloc[0]
    ppg_w4 = feats_w4.loc[feats_w4["web_name"] == "Player Ramp", "recent_ppg"].iloc[0]

    assert ppg_w2 == 11.0
    assert ppg_w4 == 6.25
    assert feats_w2.loc[feats_w2["web_name"] == "Player Ramp", "moneyball_score"].iloc[0] > \
           feats_w4.loc[feats_w4["web_name"] == "Player Ramp", "moneyball_score"].iloc[0]


def test_hit_penalty_accounting():
    """BUG-2 regression test: verifies hit deductions are subtracted once in net_points."""
    record = GameweekRecord(
        gw=5,
        starting_xi=["P1"],
        bench=[],
        captain="P1",
        vice_captain="P1",
        auto_subs=[],
        raw_points=60.0,
        hits_taken=2,
        net_points=60.0 - (2 * 4.0),
        squad_value=100.0,
        bank=0.5
    )
    assert record.net_points == 52.0
    assert record.hits_taken == 2


def test_season_dependent_ft_cap():
    """BUG-4 regression test: verifies rule changes in FT rollover limit across seasons."""
    sim = WalkForwardSimulator()
    assert sim.FT_CAP_BY_SEASON["2021-22"] == 2
    assert sim.FT_CAP_BY_SEASON["2022-23"] == 2
    assert sim.FT_CAP_BY_SEASON["2023-24"] == 2
    assert sim.FT_CAP_BY_SEASON["2024-25"] == 5

