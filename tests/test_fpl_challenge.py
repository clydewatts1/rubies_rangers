"""
tests/test_fpl_challenge.py
Comprehensive test suite for FPL Challenge Quantitative Optimization Engine:
- Frozen data contracts & immutability.
- Dynamic rule extractor & preset configurations.
- Client caching & offline fallback resilience.
- Stage 1 MILP solver: squad size N=6, club cap C=1, budget cap B=80.0, captaincy c_i <= x_i.
- Stage 2 Monte Carlo tournament simulation: P10, P50, P90, P99 right-tail, flexibility score, and archetype crowning.
"""

import pytest
import numpy as np
import pandas as pd

from analytics.challenge.contracts import (
    ChallengeRuleSet,
    ChallengeOptimalSquad,
    EvaluatedChallengeCandidate,
    ChallengeTournamentReport,
)
from analytics.challenge.rule_extractor import (
    CHALLENGE_PRESETS,
    get_available_challenge_presets,
    extract_rules_from_event,
)
from analytics.challenge.scoring_adapter import ChallengeScoringAdapter
from analytics.challenge.optimizer import ChallengeOptimizer
from analytics.challenge.two_stage_optimizer import ChallengeTwoStageOptimizer
from clients.fpl_challenge_client import FPLChallengeClient


@pytest.fixture
def mock_challenge_players_df() -> pd.DataFrame:
    """Synthetic Premier League player universe with multiple clubs and positions."""
    return pd.DataFrame([
        # Club 1: Arsenal
        {"web_name": "Saka", "position": "MID", "club": "Arsenal", "now_cost": 10.0, "xP": 6.5, "threat": 60, "selected_by_percent": 35.0, "status": "a"},
        {"web_name": "Havertz", "position": "FWD", "club": "Arsenal", "now_cost": 8.0, "xP": 5.8, "threat": 50, "selected_by_percent": 18.0, "status": "a"},
        {"web_name": "Saliba", "position": "DEF", "club": "Arsenal", "now_cost": 6.0, "xP": 4.5, "threat": 10, "selected_by_percent": 28.0, "status": "a"},
        {"web_name": "Raya", "position": "GKP", "club": "Arsenal", "now_cost": 5.5, "xP": 4.0, "threat": 0, "selected_by_percent": 20.0, "status": "a"},
        
        # Club 2: Man City
        {"web_name": "Haaland", "position": "FWD", "club": "Man City", "now_cost": 15.0, "xP": 8.5, "threat": 90, "selected_by_percent": 65.0, "status": "a"},
        {"web_name": "Foden", "position": "MID", "club": "Man City", "now_cost": 9.5, "xP": 6.2, "threat": 55, "selected_by_percent": 15.0, "status": "a"},
        {"web_name": "Gvardiol", "position": "DEF", "club": "Man City", "now_cost": 6.0, "xP": 4.8, "threat": 25, "selected_by_percent": 22.0, "status": "a"},
        
        # Club 3: Liverpool
        {"web_name": "Salah", "position": "MID", "club": "Liverpool", "now_cost": 12.5, "xP": 7.8, "threat": 80, "selected_by_percent": 42.0, "status": "a"},
        {"web_name": "Diaz", "position": "MID", "club": "Liverpool", "now_cost": 7.5, "xP": 5.5, "threat": 45, "selected_by_percent": 12.0, "status": "a"},
        {"web_name": "Alexander-Arnold", "position": "DEF", "club": "Liverpool", "now_cost": 7.0, "xP": 5.2, "threat": 30, "selected_by_percent": 25.0, "status": "a"},
        
        # Club 4: Chelsea
        {"web_name": "Palmer", "position": "MID", "club": "Chelsea", "now_cost": 10.5, "xP": 7.2, "threat": 70, "selected_by_percent": 38.0, "status": "a"},
        {"web_name": "Jackson", "position": "FWD", "club": "Chelsea", "now_cost": 7.8, "xP": 5.0, "threat": 45, "selected_by_percent": 10.0, "status": "a"},
        {"web_name": "Colwill", "position": "DEF", "club": "Chelsea", "now_cost": 4.5, "xP": 3.8, "threat": 10, "selected_by_percent": 8.0, "status": "a"},
        
        # Club 5: Aston Villa
        {"web_name": "Watkins", "position": "FWD", "club": "Aston Villa", "now_cost": 9.0, "xP": 6.0, "threat": 60, "selected_by_percent": 25.0, "status": "a"},
        {"web_name": "Rogers", "position": "MID", "club": "Aston Villa", "now_cost": 5.2, "xP": 4.6, "threat": 35, "selected_by_percent": 14.0, "status": "a"},
        {"web_name": "Konsa", "position": "DEF", "club": "Aston Villa", "now_cost": 4.5, "xP": 3.5, "threat": 8, "selected_by_percent": 9.0, "status": "a"},

        # Club 6: Newcastle
        {"web_name": "Isak", "position": "FWD", "club": "Newcastle", "now_cost": 8.5, "xP": 5.9, "threat": 55, "selected_by_percent": 20.0, "status": "a"},
        {"web_name": "Gordon", "position": "MID", "club": "Newcastle", "now_cost": 7.5, "xP": 5.3, "threat": 40, "selected_by_percent": 12.0, "status": "a"},
        {"web_name": "Hall", "position": "DEF", "club": "Newcastle", "now_cost": 4.5, "xP": 3.6, "threat": 12, "selected_by_percent": 6.0, "status": "a"},

        # Club 7: Tottenham
        {"web_name": "Son", "position": "MID", "club": "Spurs", "now_cost": 9.8, "xP": 6.4, "threat": 65, "selected_by_percent": 16.0, "status": "a"},
        {"web_name": "Solanke", "position": "FWD", "club": "Spurs", "now_cost": 7.5, "xP": 5.1, "threat": 45, "selected_by_percent": 9.0, "status": "a"},
        {"web_name": "Porro", "position": "DEF", "club": "Spurs", "now_cost": 5.5, "xP": 4.2, "threat": 22, "selected_by_percent": 15.0, "status": "a"},

        # Club 8: Brighton
        {"web_name": "Mitoma", "position": "MID", "club": "Brighton", "now_cost": 6.6, "xP": 4.8, "threat": 35, "selected_by_percent": 7.0, "status": "a"},
        {"web_name": "Welbeck", "position": "FWD", "club": "Brighton", "now_cost": 5.7, "xP": 4.5, "threat": 30, "selected_by_percent": 8.0, "status": "a"},
        {"web_name": "Dunk", "position": "DEF", "club": "Brighton", "now_cost": 4.5, "xP": 3.2, "threat": 10, "selected_by_percent": 5.0, "status": "a"},
    ])


def test_challenge_rule_contracts():
    """Verify frozen immutable Challenge contracts and presets."""
    preset = CHALLENGE_PRESETS["gw5_one_player_per_club"]
    assert preset.squad_size == 6
    assert preset.max_per_team == 1
    assert preset.budget_cap == 999.9
    assert preset.allowed_positions["GKP"] == (0, 0)

    # Immutability check
    with pytest.raises(Exception):
        preset.squad_size = 11


def test_extract_rules_from_event():
    """Verify parsing of official FPL Challenge API overrides."""
    payload = {
        "id": 6,
        "name": "Outside Box Thunderbolts",
        "overrides": {
            "rules": {
                "squad_squadsize": 6,
                "squad_team_limit": 3,
                "squad_total_spend": 800
            },
            "scoring": {
                "outside_box_goals": 2.0
            },
            "element_types": [
                {"singular_name_short": "DEF", "squad_min_select": 1, "squad_max_select": 3},
                {"singular_name_short": "MID", "squad_min_select": 1, "squad_max_select": 3},
                {"singular_name_short": "FWD", "squad_min_select": 1, "squad_max_select": 3}
            ]
        }
    }
    rule_set = extract_rules_from_event(payload)
    assert rule_set.gameweek == 6
    assert rule_set.squad_size == 6
    assert rule_set.max_per_team == 3
    assert rule_set.budget_cap == 80.0
    assert rule_set.scoring_modifiers["outside_box_goals"] == 2.0


def test_challenge_scoring_adapter(mock_challenge_players_df):
    """Verify scoring adapter adjusts xP, sigma, and differential scores."""
    rule_set = CHALLENGE_PRESETS["gw6_outside_box_boost"]
    adapted = ChallengeScoringAdapter.adjust_projections(mock_challenge_players_df, rule_set)
    
    assert "challenge_xP" in adapted.columns
    assert "sigma" in adapted.columns
    assert "differential_score" in adapted.columns
    assert "boom_score" in adapted.columns

    # Verify sigma scales with expected return
    assert (adapted["sigma"] > 0).all()
    # High ownership chalk (e.g. Haaland 65%) should have penalized differential score relative to xP
    haaland = adapted[adapted["web_name"] == "Haaland"].iloc[0]
    assert haaland["differential_score"] < haaland["challenge_xP"]


def test_challenge_optimizer_one_player_per_club(mock_challenge_players_df):
    """
    Critical Invariant Test:
    When max_per_team == 1, solver must select exactly 6 players from 6 DISTINCT clubs.
    Zero goalkeepers must be selected.
    """
    rule_set = CHALLENGE_PRESETS["gw5_one_player_per_club"]
    optimizer = ChallengeOptimizer(mock_challenge_players_df, rule_set)
    squad = optimizer.solve_single_vector("max_ev")

    assert squad is not None
    assert len(squad.squad_names) == 6
    assert squad.clubs_represented == 6  # Strictly 1 per club!
    
    # Check no GKP in squad
    squad_players = mock_challenge_players_df[mock_challenge_players_df["web_name"].isin(squad.squad_names)]
    assert (squad_players["position"] != "GKP").all()
    
    # Check captain is one of the squad members
    assert squad.captain in squad.squad_names


def test_challenge_optimizer_budget_cap(mock_challenge_players_df):
    """
    Financial Invariant Test:
    When budget_cap is £80.0M, total cost must not exceed 80.0.
    """
    # Create strict £35.0M budget test for 6 players (averaging < £5.8M)
    rule_set = ChallengeRuleSet(
        gameweek=7,
        name="Penny Pincher Test",
        squad_size=6,
        max_per_team=3,
        budget_cap=35.0,
        allowed_positions={"GKP": (0, 0), "DEF": (1, 3), "MID": (1, 3), "FWD": (1, 3)},
    )
    optimizer = ChallengeOptimizer(mock_challenge_players_df, rule_set)
    squad = optimizer.solve_single_vector("max_ev")

    assert squad is not None
    assert len(squad.squad_names) == 6
    assert squad.total_cost <= 35.0


def test_challenge_optimizer_candidate_pool(mock_challenge_players_df):
    """Verify Stage 1 generates multiple distinct candidate squads across tactical vectors."""
    rule_set = CHALLENGE_PRESETS["gw5_one_player_per_club"]
    optimizer = ChallengeOptimizer(mock_challenge_players_df, rule_set)
    candidates = optimizer.generate_candidate_pool()

    assert len(candidates) >= 2
    # Verify each candidate has exactly 6 players
    for c in candidates:
        assert len(c.squad_names) == 6
        assert c.clubs_represented == 6


def test_challenge_two_stage_tournament_simulation(mock_challenge_players_df):
    """
    Verify Stage 2 Monte Carlo Tournament:
    - Runs simulations without error.
    - Evaluates P10, P50, P90, and P99 right-tail.
    - Accurately crowns Top 3 Archetypes (Balanced, Floor, GPP Winner).
    """
    rule_set = CHALLENGE_PRESETS["gw5_one_player_per_club"]
    tournament = ChallengeTwoStageOptimizer(
        players_df=mock_challenge_players_df,
        rule_set=rule_set,
        random_seed=123
    )
    report = tournament.run_tournament(n_simulations=1000)

    assert report is not None
    assert len(report.evaluated_candidates) >= 1
    assert report.winner_balanced is not None
    assert report.winner_safe_floor is not None
    assert report.winner_gpp_upside is not None

    # Verify statistical ranking invariants
    for c in report.evaluated_candidates:
        assert c.floor_p10 <= c.median_p50 <= c.ceiling_p90 <= c.tournament_p99
        assert c.flexibility_score >= 0.0
        assert len(c.raw_totals) == 1000

    # Winner GPP upside should have maximum P99
    max_p99 = max(c.tournament_p99 for c in report.evaluated_candidates)
    assert report.winner_gpp_upside.tournament_p99 == max_p99

    # Winner safe floor should have maximum P10
    max_p10 = max(c.floor_p10 for c in report.evaluated_candidates)
    assert report.winner_safe_floor.floor_p10 == max_p10

    # Results DataFrame should be populated
    assert not report.all_results_df.empty
    assert "Tournament (P99)" in report.all_results_df.columns


def test_challenge_client_fallback():
    """Verify FPLChallengeClient fallback behavior."""
    client = FPLChallengeClient(cache_ttl=0)
    # Even if offline, synthetic bootstrap is generated
    bootstrap = client.get_challenge_bootstrap()
    assert "events" in bootstrap
    assert len(bootstrap["events"]) > 0
    event_rule = extract_rules_from_event(bootstrap["events"][0])
    assert event_rule.squad_size == 6


def test_challenge_duplicate_web_names_handled(mock_challenge_players_df):
    """
    Regression Test:
    When the player universe has duplicate web_names (e.g. multiple players named 'Davies' or 'Traoré'),
    ChallengeTwoStageOptimizer and ChallengeOptimizer must handle them seamlessly without raising
    ValueError: DataFrame index must be unique for orient='index'.
    """
    # Create duplicate web_name
    dup_df = mock_challenge_players_df.copy()
    duplicate_row = dup_df.iloc[0:1].copy()
    duplicate_row["now_cost"] = 4.5
    duplicate_row["xP"] = 2.0
    dup_df = pd.concat([dup_df, duplicate_row], ignore_index=True)

    rule_set = CHALLENGE_PRESETS["gw5_one_player_per_club"]
    tournament = ChallengeTwoStageOptimizer(
        players_df=dup_df,
        rule_set=rule_set,
        random_seed=42
    )
    report = tournament.run_tournament(n_simulations=500)
    assert report is not None
    assert len(report.evaluated_candidates) >= 1

