import pytest
import os
import pandas as pd
from fpl_client import FPLClient


@pytest.fixture
def client():
    return FPLClient(cache_ttl=3600)


def test_bootstrap_data_structure(client):
    data = client.get_bootstrap_data()
    assert isinstance(data, dict)
    assert "elements" in data
    assert "teams" in data
    assert "element_types" in data
    assert len(data["elements"]) > 500
    assert len(data["teams"]) == 20


def test_fixtures_data_structure(client):
    fixtures = client.get_fixtures_data()
    assert isinstance(fixtures, list)
    assert len(fixtures) > 0
    first = fixtures[0]
    assert "team_h" in first
    assert "team_a" in first


def test_get_players_df_columns(client):
    df = client.get_players_df()
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

    required_cols = [
        "web_name", "position_name", "now_cost", "total_points",
        "expected_goals_per_90", "expected_assists_per_90", "expected_goal_involvements_per_90",
        "moneyball_score", "fdr_moneyball_score", "forward_moneyball_score", "weather_moneyball_score",
        "weather_dampener", "congestion_multiplier", "fdr_next_5", "next_fixture",
        "yellow_cards", "red_cards", "status"
    ]
    for col in required_cols:
        assert col in df.columns, f"Missing expected column: {col}"


def test_team_fdr_map(client):
    fdr_map = client.get_team_fdr_map(n_gameweeks=5)
    assert isinstance(fdr_map, dict)
    assert len(fdr_map) == 20
    for team_id, info in fdr_map.items():
        assert "avg_fdr" in info
        assert "next_fixture" in info
        assert "next_fdr" in info
        assert 1.0 <= info["avg_fdr"] <= 5.0
