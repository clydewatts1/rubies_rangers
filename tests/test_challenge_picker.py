"""
tests/test_challenge_picker.py
Unit tests for the modular ChallengePicker service:
- Validates ChallengePickerConfig contracts and defaults.
- Verifies Stage 1 screening and Stage 2 Monte Carlo archetype crowning (max_ev, safe_floor, gpp_upside).
- Checks FPL Challenge API payload formatting (element IDs, positions, captaincy, vice captaincy).
- Validates player locks and exclusions.
- Ensures graceful error handling on infeasible constraints.
"""

import pytest
import pandas as pd

from analytics.challenge.contracts import ChallengeRuleSet
from analytics.challenge.rule_extractor import CHALLENGE_PRESETS
from analytics.challenge.picker import (
    ChallengePicker,
    ChallengePickerConfig,
    ChallengePickerResult,
)


@pytest.fixture
def sample_players_df() -> pd.DataFrame:
    """Fixture providing a diverse player pool with element IDs and club metadata."""
    return pd.DataFrame([
        {"id": 101, "web_name": "Saka", "position": "MID", "club_name": "Arsenal", "club": "Arsenal", "now_cost": 10.0, "xP": 6.5, "threat": 60, "status": "a"},
        {"id": 102, "web_name": "Havertz", "position": "FWD", "club_name": "Arsenal", "club": "Arsenal", "now_cost": 8.0, "xP": 5.8, "threat": 50, "status": "a"},
        {"id": 103, "web_name": "Saliba", "position": "DEF", "club_name": "Arsenal", "club": "Arsenal", "now_cost": 6.0, "xP": 4.5, "threat": 10, "status": "a"},
        {"id": 104, "web_name": "Raya", "position": "GKP", "club_name": "Arsenal", "club": "Arsenal", "now_cost": 5.5, "xP": 4.0, "threat": 0, "status": "a"},

        {"id": 201, "web_name": "Haaland", "position": "FWD", "club_name": "Man City", "club": "Man City", "now_cost": 15.0, "xP": 8.5, "threat": 90, "status": "a"},
        {"id": 202, "web_name": "Foden", "position": "MID", "club_name": "Man City", "club": "Man City", "now_cost": 9.5, "xP": 6.2, "threat": 55, "status": "a"},
        {"id": 203, "web_name": "Gvardiol", "position": "DEF", "club_name": "Man City", "club": "Man City", "now_cost": 6.0, "xP": 4.8, "threat": 25, "status": "a"},

        {"id": 301, "web_name": "Salah", "position": "MID", "club_name": "Liverpool", "club": "Liverpool", "now_cost": 12.5, "xP": 7.8, "threat": 80, "status": "a"},
        {"id": 302, "web_name": "Diaz", "position": "MID", "club_name": "Liverpool", "club": "Liverpool", "now_cost": 7.5, "xP": 5.5, "threat": 45, "status": "a"},
        {"id": 303, "web_name": "Alexander-Arnold", "position": "DEF", "club_name": "Liverpool", "club": "Liverpool", "now_cost": 7.0, "xP": 5.2, "threat": 30, "status": "a"},

        {"id": 401, "web_name": "Palmer", "position": "MID", "club_name": "Chelsea", "club": "Chelsea", "now_cost": 10.5, "xP": 7.2, "threat": 70, "status": "a"},
        {"id": 402, "web_name": "Jackson", "position": "FWD", "club_name": "Chelsea", "club": "Chelsea", "now_cost": 7.8, "xP": 5.0, "threat": 45, "status": "a"},
        {"id": 403, "web_name": "Colwill", "position": "DEF", "club_name": "Chelsea", "club": "Chelsea", "now_cost": 4.5, "xP": 3.8, "threat": 10, "status": "a"},

        {"id": 501, "web_name": "Watkins", "position": "FWD", "club_name": "Aston Villa", "club": "Aston Villa", "now_cost": 9.0, "xP": 6.0, "threat": 60, "status": "a"},
        {"id": 502, "web_name": "Rogers", "position": "MID", "club_name": "Aston Villa", "club": "Aston Villa", "now_cost": 5.2, "xP": 4.6, "threat": 35, "status": "a"},
        {"id": 503, "web_name": "Konsa", "position": "DEF", "club_name": "Aston Villa", "club": "Aston Villa", "now_cost": 4.5, "xP": 3.5, "threat": 8, "status": "a"},

        {"id": 601, "web_name": "Son", "position": "MID", "club_name": "Spurs", "club": "Spurs", "now_cost": 10.0, "xP": 6.8, "threat": 65, "status": "a"},
        {"id": 602, "web_name": "Solanke", "position": "FWD", "club_name": "Spurs", "club": "Spurs", "now_cost": 7.5, "xP": 5.2, "threat": 40, "status": "a"},
        {"id": 603, "web_name": "Porro", "position": "DEF", "club_name": "Spurs", "club": "Spurs", "now_cost": 5.5, "xP": 4.4, "threat": 20, "status": "a"},
    ])


@pytest.fixture
def rule_preset() -> ChallengeRuleSet:
    """GW5 One Player Per Club rule preset."""
    return CHALLENGE_PRESETS["gw5_one_player_per_club"]


def test_challenge_picker_config_defaults():
    """Verify ChallengePickerConfig contracts and defaults."""
    cfg = ChallengePickerConfig()
    assert cfg.archetype == "max_ev"
    assert cfg.n_simulations == 2500
    assert cfg.lock_players is None
    assert cfg.exclude_players is None
    assert cfg.available_only is True
    assert cfg.random_seed == 42


def test_challenge_picker_archetype_selection(sample_players_df, rule_preset):
    """Ensure pick_challenge_squad correctly extracts specified archetypes."""
    for archetype in ["max_ev", "safe_floor", "gpp_upside"]:
        config = ChallengePickerConfig(archetype=archetype, n_simulations=500, random_seed=42)
        res = ChallengePicker.pick_challenge_squad(sample_players_df, rule_preset, config=config)

        assert isinstance(res, ChallengePickerResult)
        assert res.archetype_chosen == archetype
        assert len(res.selected_squad.squad_names) == rule_preset.squad_size
        assert len(res.element_ids) == rule_preset.squad_size
        assert res.captain_id in res.element_ids
        assert res.vice_captain_id in res.element_ids
        assert res.captain_id != res.vice_captain_id
        assert "Archetype:" in res.summary_str


def test_challenge_picker_picks_payload_structure(sample_players_df, rule_preset):
    """Verify official FPL Challenge picks payload contract."""
    config = ChallengePickerConfig(archetype="max_ev", n_simulations=300)
    res = ChallengePicker.pick_challenge_squad(sample_players_df, rule_preset, config=config)

    payload = res.picks_payload
    assert "picks" in payload
    picks = payload["picks"]
    assert len(picks) == rule_preset.squad_size

    captain_count = sum(1 for p in picks if p["is_captain"])
    vice_count = sum(1 for p in picks if p["is_vice_captain"])
    assert captain_count == 1, "Exactly one captain must be flagged"
    assert vice_count == 1, "Exactly one vice-captain must be flagged"

    for idx, pick in enumerate(picks, start=1):
        assert "element" in pick
        assert pick["element"] in res.element_ids
        assert pick["position"] == idx
        assert isinstance(pick["is_captain"], bool)
        assert isinstance(pick["is_vice_captain"], bool)


def test_challenge_picker_locks_and_excludes(sample_players_df, rule_preset):
    """Verify player locks and exclusions are strictly enforced."""
    config = ChallengePickerConfig(
        archetype="max_ev",
        n_simulations=300,
        lock_players=["Haaland"],
        exclude_players=["Salah"]
    )
    res = ChallengePicker.pick_challenge_squad(sample_players_df, rule_preset, config=config)

    squad_names = res.selected_squad.squad_names
    assert "Haaland" in squad_names, "Locked player Haaland must be included"
    assert "Salah" not in squad_names, "Excluded player Salah must not be included"


def test_challenge_picker_infeasible_raises_error(sample_players_df, rule_preset):
    """Verify ValueError is raised when constraints cannot be satisfied."""
    # Locking 7 players when squad size is 6
    excessive_locks = ["Saka", "Havertz", "Haaland", "Salah", "Palmer", "Watkins", "Son"]
    config = ChallengePickerConfig(archetype="max_ev", n_simulations=100, lock_players=excessive_locks)

    with pytest.raises(ValueError, match="No mathematically feasible"):
        ChallengePicker.pick_challenge_squad(sample_players_df, rule_preset, config=config)
