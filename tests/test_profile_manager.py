"""
tests/test_profile_manager.py
Unit tests for ProfileContracts and ProfileManager (seeding, CRUD, cloning, FPL import).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from analytics.profile_contracts import ManagerProfile, ProfileType
from analytics.profile_manager import ProfileManager, slugify_name


@pytest.fixture
def temp_profiles_dir(tmp_path: Path) -> Path:
    p_dir = tmp_path / "profiles"
    return p_dir


def test_slugify_name():
    assert slugify_name("Rubies Rangers (Clyde Watts)") == "rubies_rangers_clyde_watts"
    assert slugify_name("GW1 Draft: Haaland + Salah!") == "gw1_draft_haaland_salah"
    assert slugify_name("  Special #1 -- Team  ") == "special_1_team"
    assert slugify_name("   ") == "profile"


def test_profile_contract_serialization():
    profile = ManagerProfile(
        profile_id="test_draft",
        display_name="Test Draft",
        profile_type=ProfileType.SANDBOX,
        fpl_entry_id=None,
        bank_balance=1.5,
        active_squad=["Saka", "Palmer", "Haaland"],
        mini_league_ids=[],
        calibration_profile="tuned"
    )
    data = profile.to_dict()
    assert data["profile_id"] == "test_draft"
    assert data["profile_type"] == "SANDBOX"
    assert data["bank_balance"] == 1.5
    assert data["mini_league_ids"] == []

    hydrated = ManagerProfile.from_dict(data)
    assert hydrated.profile_id == profile.profile_id
    assert hydrated.display_name == profile.display_name
    assert hydrated.profile_type == ProfileType.SANDBOX
    assert hydrated.fpl_entry_id is None
    assert hydrated.bank_balance == 1.5
    assert hydrated.active_squad == ["Saka", "Palmer", "Haaland"]
    assert hydrated.mini_league_ids == []


def test_profile_seeding(temp_profiles_dir: Path):
    manager = ProfileManager(profiles_dir=temp_profiles_dir)
    assert not temp_profiles_dir.exists()

    manager.ensure_seeded()
    assert temp_profiles_dir.exists()

    profiles = manager.list_profiles()
    # Should seed rubies_rangers + 2 starter pre-season drafts
    assert len(profiles) >= 3
    ids = [p.profile_id for p in profiles]
    assert "rubies_rangers" in ids
    assert "preseason_gw1_haaland_salah" in ids
    assert "preseason_gw1_balanced_depth" in ids

    # Primary profile should be LIVE_FPL with an entry ID
    primary = manager.get_profile("rubies_rangers")
    assert primary is not None
    assert primary.profile_type == ProfileType.LIVE_FPL
    assert primary.fpl_entry_id == 6173410
    assert len(primary.active_squad) == 15

    # Sandbox drafts should have no entry ID
    draft = manager.get_profile("preseason_gw1_haaland_salah")
    assert draft is not None
    assert draft.profile_type == ProfileType.SANDBOX
    assert draft.fpl_entry_id is None
    assert draft.mini_league_ids == []


def test_profile_crud_operations(temp_profiles_dir: Path):
    manager = ProfileManager(profiles_dir=temp_profiles_dir)
    manager.ensure_seeded()

    # Create new profile
    custom = ManagerProfile(
        profile_id="custom_user",
        display_name="Custom Rival Team",
        profile_type=ProfileType.LIVE_FPL,
        fpl_entry_id=987654,
        bank_balance=0.2,
        active_squad=["Salah", "Son"],
        mini_league_ids=[12345]
    )
    saved_path = manager.save_profile(custom)
    assert saved_path.exists()

    # Retrieve
    fetched = manager.get_profile("custom_user")
    assert fetched is not None
    assert fetched.display_name == "Custom Rival Team"
    assert fetched.fpl_entry_id == 987654

    # Delete
    deleted = manager.delete_profile("custom_user")
    assert deleted is True
    assert manager.get_profile("custom_user") is None


def test_clone_profile(temp_profiles_dir: Path):
    manager = ProfileManager(profiles_dir=temp_profiles_dir)
    manager.ensure_seeded()

    cloned = manager.clone_profile("rubies_rangers", "My Preseason Experiment v1")
    assert cloned.profile_id.startswith("my_preseason_experiment_v1")
    assert cloned.profile_type == ProfileType.SANDBOX
    assert cloned.fpl_entry_id is None
    assert len(cloned.active_squad) == 15
    assert manager.get_profile(cloned.profile_id) is not None


def test_import_fpl_team_mocked(temp_profiles_dir: Path):
    manager = ProfileManager(profiles_dir=temp_profiles_dir)

    mock_leagues = {
        "team_name": "Mo Salah FC",
        "manager_name": "Jane Doe",
        "overall_points": 1200,
        "overall_rank": 45000,
        "leagues": [{"id": 112233, "name": "Work League"}]
    }
    mock_picks = {
        "starters": [{"web_name": f"P_{i}"} for i in range(1, 12)],
        "bench": [{"web_name": f"B_{i}"} for i in range(1, 5)],
        "entry_history": {"bank": 12}  # 1.2M
    }

    with patch("trackers.league.LeagueTracker") as MockLT:
        mock_instance = MockLT.return_value
        mock_instance.get_team_leagues.return_value = mock_leagues
        mock_instance.get_team_picks.return_value = mock_picks

        imported = manager.import_fpl_team(entry_id=888888)

        assert imported.fpl_entry_id == 888888
        assert "Mo Salah FC" in imported.display_name
        assert imported.profile_type == ProfileType.LIVE_FPL
        assert imported.bank_balance == 1.2
        assert len(imported.active_squad) == 15
        assert imported.mini_league_ids == [112233]


def test_import_fpl_team_with_no_mini_leagues(temp_profiles_dir: Path):
    manager = ProfileManager(profiles_dir=temp_profiles_dir)

    mock_leagues = {
        "team_name": "Solo Manager",
        "manager_name": "John Smith",
        "overall_points": 500,
        "overall_rank": 150000,
        "leagues": []  # Zero mini leagues
    }
    mock_picks = {
        "starters": [{"web_name": f"P_{i}"} for i in range(1, 12)],
        "bench": [{"web_name": f"B_{i}"} for i in range(1, 5)],
        "entry_history": {"bank": 0}
    }

    with patch("trackers.league.LeagueTracker") as MockLT:
        mock_instance = MockLT.return_value
        mock_instance.get_team_leagues.return_value = mock_leagues
        mock_instance.get_team_picks.return_value = mock_picks

        imported = manager.import_fpl_team(entry_id=777777)

        assert imported.fpl_entry_id == 777777
        assert imported.mini_league_ids == []
        assert len(imported.active_squad) == 15
