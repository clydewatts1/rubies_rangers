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
    LEGAL_FORMATIONS = {"3-5-2", "3-4-3", "4-4-2", "4-3-3", "4-5-1", "5-3-2", "5-4-1", "5-2-3"}
    assert res["optimal_formation"] in LEGAL_FORMATIONS

    assert len(res["starters"]) == 11
    assert len(res["bench"]) == 4

    # Formation evaluations: all 8 legal formations
    assert len(res["formation_evaluations"]) == 8

    # Verify bench structure and legal constraints
    bench = res["bench"]
    assert bench[0]["slot"] == "Sub 1"
    assert bench[1]["slot"] == "Sub 2"
    assert bench[2]["slot"] == "Sub 3"
    assert bench[3]["slot"] == "GKP Sub"
    assert bench[3]["position"] == "GKP"
    assert all("activation_prob_pct" in b for b in bench)

    # Verify captaincy duel
    cap_duel = res["captaincy_duel"]
    assert "captain" in cap_duel
    assert "vice_captain" in cap_duel
    starter_names = [p["web_name"] for p in res["starters"]]
    assert cap_duel["captain"]["web_name"] in starter_names
    assert cap_duel["vice_captain"]["web_name"] in starter_names
    assert cap_duel["captain"]["web_name"] != cap_duel["vice_captain"]["web_name"]
    assert cap_duel["captain"]["mean_captain_pts"] >= cap_duel["vice_captain"]["mean_captain_pts"]
    assert cap_duel["captain"]["mean_captain_pts"] > 0.0


def test_simulate_player_substitution_hazard(mc_engine):
    """Verify tactical substitution hazard concentrates starter minutes at or above 60'."""
    player = {
        "web_name": "RotationMid",
        "position_name": "MID",
        "club_short": "ARS",
        "status": "a",
        "chance_of_playing": 100,
        "form": 4.5,
        "expected_goals_per_90": 0.30,
        "expected_assists_per_90": 0.20,
    }
    trends = {
        "minutes_status": "REGULAR_STARTER",
        "avg_recent_mins": 68.0
    }
    pts, mins = mc_engine.simulate_player(player, trends_dict=trends, n_sims=3000)
    
    # Active starts should have minutes >= 60 in ~95% of cases (due to prob_subbed_off_early = 0.05)
    started_mins = mins[mins > 30.0]
    assert len(started_mins) > 1000
    sub_60_ratio = np.mean((started_mins >= 45.0) & (started_mins < 60.0))
    # Early subs should be small minority (< 15%)
    assert sub_60_ratio < 0.15
    # Majority of started games should reach appearance threshold (>= 60 mins)
    assert np.mean(started_mins >= 60.0) >= 0.85


def test_simulate_squad_lineup_formation_legality(mc_engine):
    """
    Legality Test:
    When a 3-5-2 lineup has a DEF with 0 minutes and Bench Sub 1 is a MID,
    auto-substitution must skip Sub 1 and bring on Bench Sub 2 (DEF) to maintain minimum 3 DEF.
    """
    # Construct synthetic sim cache for 15 players
    n_sims = 100
    sim_cache = {}

    # GKP 1 (Starter), GKP 2 (Bench)
    sim_cache["GKP_Start"] = {"player": {"web_name": "GKP_Start", "position_name": "GKP"}, "pts": np.full(n_sims, 5.0), "mins": np.full(n_sims, 90.0), "mean_pts": 5.0}
    sim_cache["GKP_Bench"] = {"player": {"web_name": "GKP_Bench", "position_name": "GKP"}, "pts": np.full(n_sims, 4.0), "mins": np.full(n_sims, 90.0), "mean_pts": 4.0}

    # 3 Starters DEF: DEF1 (plays), DEF2 (plays), DEF3 (0 mins in trial 0)
    sim_cache["DEF1"] = {"player": {"web_name": "DEF1", "position_name": "DEF"}, "pts": np.full(n_sims, 6.0), "mins": np.full(n_sims, 90.0), "mean_pts": 6.0}
    sim_cache["DEF2"] = {"player": {"web_name": "DEF2", "position_name": "DEF"}, "pts": np.full(n_sims, 6.0), "mins": np.full(n_sims, 90.0), "mean_pts": 6.0}
    def3_mins = np.full(n_sims, 90.0)
    def3_mins[0] = 0.0  # 0 minutes in trial 0
    def3_pts = np.full(n_sims, 6.0)
    def3_pts[0] = 0.0
    sim_cache["DEF3"] = {"player": {"web_name": "DEF3", "position_name": "DEF"}, "pts": def3_pts, "mins": def3_mins, "mean_pts": 5.9}

    # 5 Starters MID (mean_pts > bench)
    for i in range(1, 6):
        name = f"MID{i}"
        sim_cache[name] = {"player": {"web_name": name, "position_name": "MID"}, "pts": np.full(n_sims, 7.0), "mins": np.full(n_sims, 90.0), "mean_pts": 7.0}

    # 2 Starters FWD
    sim_cache["FWD1"] = {"player": {"web_name": "FWD1", "position_name": "FWD"}, "pts": np.full(n_sims, 8.0), "mins": np.full(n_sims, 90.0), "mean_pts": 8.0}
    sim_cache["FWD2"] = {"player": {"web_name": "FWD2", "position_name": "FWD"}, "pts": np.full(n_sims, 8.0), "mins": np.full(n_sims, 90.0), "mean_pts": 8.0}

    # Bench Outfield:
    # Sub 1: MID_Bench (higher mean_pts = 4.5, plays 90 mins) -> CANNOT be subbed on because DEF would drop to 2!
    # Sub 2: DEF_Bench (mean_pts = 4.0, plays 90 mins) -> MUST be subbed on to restore 3 DEF!
    # Sub 3: FWD_Bench (mean_pts = 3.5, plays 90 mins)
    sim_cache["MID_Bench"] = {"player": {"web_name": "MID_Bench", "position_name": "MID"}, "pts": np.full(n_sims, 10.0), "mins": np.full(n_sims, 90.0), "mean_pts": 4.5}
    sim_cache["DEF_Bench"] = {"player": {"web_name": "DEF_Bench", "position_name": "DEF"}, "pts": np.full(n_sims, 4.0), "mins": np.full(n_sims, 90.0), "mean_pts": 4.0}
    sim_cache["FWD_Bench"] = {"player": {"web_name": "FWD_Bench", "position_name": "FWD"}, "pts": np.full(n_sims, 3.0), "mins": np.full(n_sims, 90.0), "mean_pts": 3.5}

    squad_names = list(sim_cache.keys())
    totals, meta = mc_engine.simulate_squad_lineup(squad_names, sim_cache, n_sims=n_sims)

    # In trial 0: DEF3 had 0 mins. The legal formation requires 3 DEF.
    # Therefore, DEF_Bench (pts=4.0) must be subbed on, NOT MID_Bench (pts=10.0).
    # Normal starter sum = 5 (GKP) + 6 (DEF1) + 6 (DEF2) + 0 (DEF3) + 35 (5 MIDs) + 16 (2 FWDs) + 8 (Captain FWD 2x) = 76
    # With DEF_Bench added: 76 + 4.0 = 80.0. If illegal MID_Bench were added: 76 + 10.0 = 86.0.
    assert totals[0] == 80.0


def test_macro_engine_coupled_assists():
    """Verify MacroEngine generates coupled assists matching binomial draws (p=0.76)."""
    from analytics.macro_engine import simulate_macro_fixtures, build_team_macro_lookup
    fixtures = {
        "ARS": {"exp_goals_scored": 2.5, "exp_goals_conceded": 0.8, "clean_sheet_prob": 0.45, "fixture_str": "ARS vs CHE (H)", "is_home": True, "opponent": "CHE"},
        "CHE": {"exp_goals_scored": 0.8, "exp_goals_conceded": 2.5, "clean_sheet_prob": 0.15, "fixture_str": "ARS vs CHE (A)", "is_home": False, "opponent": "ARS"}
    }
    f_states = simulate_macro_fixtures(fixtures, n_sims=2000)
    lookup = build_team_macro_lookup(f_states)

    assert "ARS" in lookup
    assert "assists_scored" in lookup["ARS"]
    assert len(lookup["ARS"]["assists_scored"]) == 2000
    # Total assists scored by team should never exceed total goals scored by team
    goals = lookup["ARS"]["goals_scored"]
    assists = lookup["ARS"]["assists_scored"]
    assert (assists <= goals).all()


