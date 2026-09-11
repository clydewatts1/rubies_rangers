import pytest
import pandas as pd
from fpl_client import FPLClient
from fpl_optimizer import FPLOptimizer
from xp_model import DEFAULT_SQUAD


@pytest.fixture
def optimizer():
    client = FPLClient(cache_ttl=3600)
    df = client.get_players_df()
    return FPLOptimizer(df)


def test_find_player_indices(optimizer):
    indices = optimizer._find_player_indices(["Isak", "Foden", "Verbruggen"])
    assert len(indices) == 3
    names = [optimizer.df.loc[i, "web_name"] for i in indices]
    assert "Isak" in names
    assert "Foden" in names
    assert "Verbruggen" in names


def test_optimize_squad_constraints(optimizer):
    res = optimizer.optimize_squad(budget=100.0, objective="moneyball")
    assert res["success"] is True

    squad = res["squad"]
    assert len(squad) == 15

    # Check position quotas (2 GKP, 5 DEF, 5 MID, 3 FWD)
    pos_counts = squad["position_name"].value_counts().to_dict()
    assert pos_counts.get("GKP", 0) == 2
    assert pos_counts.get("DEF", 0) == 5
    assert pos_counts.get("MID", 0) == 5
    assert pos_counts.get("FWD", 0) == 3

    # Check budget constraint
    assert res["total_cost"] <= 100.0

    # Check max 3 players per club
    club_counts = squad["club_name"].value_counts()
    assert (club_counts <= 3).all()


def test_optimize_transfers_feasibility(optimizer):
    res = optimizer.optimize_transfers(
        current_player_names=DEFAULT_SQUAD,
        bank_balance=3.7,
        max_transfers=1,
        objective="moneyball"
    )
    assert res["success"] is True
    assert len(res["squad"]) == 15
    assert len(res["transfers_out"]) <= 1
    assert len(res["transfers_in"]) <= 1
