"""
Unit and Integration Tests for ClubElo Client & Poisson Expectancy Engine
Validates:
- Name normalization and code resolution
- Calibrated Poisson goal arrival rates and symmetry
- Clean sheet probability calculation and decimal odds
- Clamping to physical boundaries
- Cache persistence and offline fallback
- Integration into XPModel dynamic team odds
"""

import os
import math
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from clients.clubelo_client import (
    ClubEloClient,
    ClubEloRecord,
    FixtureExpectancy,
    CLUBELO_TO_FPL,
    BASELINE_EPL_ELO,
)
from analytics.xp_model import XPModel


class TestClubEloClient:

    def test_dataclass_contracts_immutable(self):
        """Verify dataclasses are frozen and enforce immutability."""
        rec = ClubEloRecord(
            club_name="Arsenal",
            fpl_code="ARS",
            elo=2045.0,
            rank=2,
            as_of_timestamp=1726500000.0
        )
        assert rec.fpl_code == "ARS"
        assert rec.elo == 2045.0
        with pytest.raises(Exception):
            rec.elo = 2100.0

        exp = FixtureExpectancy(
            home_team="MCI",
            away_team="NFO",
            home_elo=2032.0,
            away_elo=1813.0,
            delta_elo_home=294.0,
            exp_goals_home=2.68,
            exp_goals_away=0.69,
            clean_sheet_prob_home=0.502,
            clean_sheet_prob_away=0.068,
            clean_sheet_odds_home=1.99,
            clean_sheet_odds_away=14.71,
            fixture_str_home="NFO (H)",
            fixture_str_away="MCI (A)",
        )
        assert exp.home_team == "MCI"
        with pytest.raises(Exception):
            exp.home_team = "ARS"

    def test_name_and_code_resolution(self):
        """Verify common naming aliases resolve to standard 3-letter FPL codes."""
        test_cases = {
            "ARS": "ARS",
            "MCI": "MCI",
            "MNU": "MUN",
            "BRI": "BHA",
            "FOR": "NFO",
            "spurs": "TOT",
            "tottenham": "TOT",
            "aston villa": "AVL",
            "nott'm forest": "NFO",
            "crystal palace": "CRY",
            "west ham": "WHU",
            "wolves": "WOL",
        }
        for alias, expected in test_cases.items():
            resolved = (
                CLUBELO_TO_FPL.get(alias)
                or CLUBELO_TO_FPL.get(alias.lower())
                or CLUBELO_TO_FPL.get(alias.lower().replace(" ", "").replace("'", ""))
            )
            assert resolved == expected, f"Failed resolving alias '{alias}'"

    def test_poisson_expectancy_symmetry_and_home_advantage(self):
        """Verify that equal teams at home vs away correctly reflect home advantage."""
        client = ClubEloClient(home_advantage=75.0, base_goals=1.36, beta=0.00231)
        ratings = {
            "AAA": ClubEloRecord("Team A", "AAA", 1800.0, 10, 0.0),
            "BBB": ClubEloRecord("Team B", "BBB", 1800.0, 11, 0.0),
        }
        exp = client.compute_fixture_expectancy("AAA", "BBB", ratings=ratings)
        assert exp.delta_elo_home == 75.0
        assert exp.exp_goals_home > exp.exp_goals_away
        assert exp.clean_sheet_prob_home > exp.clean_sheet_prob_away
        assert exp.clean_sheet_odds_home < exp.clean_sheet_odds_away

    def test_clamping_to_physical_boundaries(self):
        """Verify extreme rating differentials are clamped to physical boundaries."""
        client = ClubEloClient(base_goals=1.36, beta=0.00231)
        ratings = {
            "SUPER": ClubEloRecord("Super", "SUPER", 2600.0, 1, 0.0),
            "MINNOW": ClubEloRecord("Minnow", "MINNOW", 1000.0, 500, 0.0),
        }
        exp = client.compute_fixture_expectancy("SUPER", "MINNOW", ratings=ratings)
        assert exp.exp_goals_home <= client.MAX_LAMBDA
        assert exp.exp_goals_away >= client.MIN_LAMBDA
        assert exp.clean_sheet_prob_home == round(math.exp(-exp.exp_goals_away), 3)

    def test_build_team_odds_map_structure(self):
        """Verify that build_team_odds_map produces standard team_odds contracts."""
        client = ClubEloClient()
        fixtures = [
            {"home": "ARS", "away": "BHA"},
            {"home": "MCI", "away": "MUN"},
        ]
        odds_map = client.build_team_odds_map(fixtures)
        assert len(odds_map) == 4
        assert "ARS" in odds_map
        assert "BHA" in odds_map
        assert "MCI" in odds_map
        assert "MUN" in odds_map

        ars = odds_map["ARS"]
        assert ars["team"] == "ARS"
        assert ars["opponent"] == "BHA"
        assert ars["is_home"] is True
        assert ars["exp_goals_scored"] > 0
        assert ars["exp_goals_conceded"] > 0
        assert 0 < ars["clean_sheet_prob"] < 1.0
        assert ars["clean_sheet_odds"] >= 1.0
        assert ars["fixture_str"] == "BHA (H)"

    def test_offline_fallback_without_network_or_cache(self):
        """Verify that if network fails and cache is empty, baseline ratings are used."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_cache = os.path.join(tmpdir, "non_existent.json")
            client = ClubEloClient(cache_file=dummy_cache)
            with patch.object(client, "_fetch_ratings_network", return_value={}):
                ratings = client.get_epl_ratings(force_refresh=True)
                assert len(ratings) >= 20
                assert "MCI" in ratings
                assert "ARS" in ratings
                assert ratings["MCI"].elo == BASELINE_EPL_ELO["MCI"]

    def test_xp_model_dynamic_clubelo_integration(self):
        """Verify XPModel consumes ClubEloClient dynamically without errors."""
        xm = XPModel(gameweek=4)
        assert len(xm.team_odds) == 20
        assert "MCI" in xm.team_odds
        assert "ARS" in xm.team_odds
        mci_odds = xm.team_odds["MCI"]
        assert "exp_goals_scored" in mci_odds
        assert "clean_sheet_prob" in mci_odds
        assert "clean_sheet_odds" in mci_odds
