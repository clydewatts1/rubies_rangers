import pytest
import numpy as np
from montecarlo_engine import MonteCarloEngine, clean_nans
from xp_model import DEFAULT_SQUAD


@pytest.fixture
def mc_engine():
    return MonteCarloEngine()


def test_clean_nans():
    raw_dict = {
        "valid": 10.5,
        "nan_val": float("nan"),
        "inf_val": float("inf"),
        "nested": {
            "sub_nan": float("nan"),
            "sub_list": [1.0, float("nan"), 3.0]
        }
    }
    cleaned = clean_nans(raw_dict)
    assert cleaned["valid"] == 10.5
    assert cleaned["nan_val"] is None
    assert cleaned["inf_val"] is None
    assert cleaned["nested"]["sub_nan"] is None
    assert cleaned["nested"]["sub_list"] == [1.0, None, 3.0]


def test_simulate_player_healthy(mc_engine):
    player = {
        "web_name": "Isak",
        "position_name": "FWD",
        "club_short": "LIV",
        "status": "a",
        "chance_of_playing": 100,
        "form": 5.0,
        "expected_goals_per_90": 0.85,
        "expected_assists_per_90": 0.15,
        "penalties_order": 1,
        "yellow_cards": 0,
        "red_cards": 0
    }
    pts, mins = mc_engine.simulate_player(player, n_sims=500)
    assert len(pts) == 500
    assert len(mins) == 500
    assert not np.isnan(pts).any()
    assert not np.isnan(mins).any()
    assert np.mean(mins) > 50.0
    assert np.mean(pts) > 3.0


def test_simulate_player_unavailable(mc_engine):
    player = {
        "web_name": "InjuredPlayer",
        "position_name": "MID",
        "club_short": "MCI",
        "status": "i",
        "chance_of_playing": 0,
        "form": 0.0
    }
    pts, mins = mc_engine.simulate_player(player, n_sims=500)
    assert (pts == 0).all()
    assert (mins == 0).all()


def test_optimize_lineup_and_substitutions(mc_engine):
    res = mc_engine.optimize_lineup_and_substitutions(
        squad_names=DEFAULT_SQUAD,
        n_sims=500,
        form_weight=0.25,
        include_disciplinary=True
    )
    assert "optimal_formation" in res
    assert res["optimal_formation"] == "3-5-2"

    assert len(res["starters"]) == 11
    assert len(res["bench"]) == 4

    # Formation evaluations: all 8 legal formations
    assert len(res["formation_evaluations"]) == 8

    # Verify bench order and priority cover
    bench = res["bench"]
    assert bench[0]["slot"] == "Sub 1"
    assert bench[0]["web_name"] == "Robinson"
    assert bench[0]["position"] == "DEF"
    assert bench[0]["activation_prob_pct"] > 15.0  # Significant DEF coverage

    # Verify captaincy duel
    cap_duel = res["captaincy_duel"]
    assert "captain" in cap_duel
    assert "vice_captain" in cap_duel
    starter_names = [p["web_name"] for p in res["starters"]]
    assert cap_duel["captain"]["web_name"] in starter_names
    assert cap_duel["vice_captain"]["web_name"] in starter_names
    assert cap_duel["captain"]["web_name"] != cap_duel["vice_captain"]["web_name"]
    assert cap_duel["captain"]["mean_captain_pts"] >= cap_duel["vice_captain"]["mean_captain_pts"]
    assert cap_duel["captain"]["mean_captain_pts"] > 5.0

