"""
Unit and Integration Tests for Matchday Center & Live Gameweek Squad Engine.
Validates live score fetching, player-to-fixture mapping, captain 2x doubling,
and auto-sub cascade logic.
"""

import pytest
from dataclasses import FrozenInstanceError

from analytics.matchday_hub import (
    MatchdayHub,
    MatchdayPlayer,
    MatchdayFixture,
    MatchdaySummary,
)
from clients.fpl_client import FPLClient
from trackers.league import DEFAULT_ENTRY_ID


@pytest.fixture
def matchday_hub():
    return MatchdayHub()


def test_matchday_dataclass_immutability():
    """Verify Matchday contracts are immutable frozen dataclasses."""
    p = MatchdayPlayer(
        id=1,
        web_name="TestPlayer",
        club_short="ARS",
        position="DEF",
        role="START",
        multiplier=1,
        is_starter=True,
        live_points=6,
        effective_points=6,
        minutes=90,
        goals=0,
        assists=0,
        clean_sheets=1,
        goals_conceded=0,
        saves=0,
        bonus=0,
        bps=24,
        match_status="COMPLETED",
        fixture_id=1,
        opponent_short="CHE",
        is_home=True
    )
    assert p.web_name == "TestPlayer"
    assert p.effective_points == 6
    with pytest.raises(FrozenInstanceError):
        p.effective_points = 10


def test_matchday_summary_gw4(matchday_hub):
    """Verify live Gameweek 4 summary generates valid starting XI, bench, and fixture mappings."""
    summary = matchday_hub.get_matchday_summary(entry_id=DEFAULT_ENTRY_ID, gameweek=4)

    assert isinstance(summary, MatchdaySummary)
    assert summary.gameweek == 4
    assert len(summary.starters) == 11
    assert len(summary.bench) == 4
    assert len(summary.fixtures) == 10

    # Captaincy
    assert summary.captain_name != "None"
    assert summary.captain_points >= 0

    # Total points matches sum of starters effective points
    starter_sum = sum(p.effective_points for p in summary.starters)
    assert summary.total_live_points == starter_sum

    # Starters player counts partition 11
    total_starters = (
        summary.starters_played_count +
        summary.starters_playing_count +
        summary.starters_to_play_count
    )
    assert total_starters == 11


def test_captain_2x_multiplier(matchday_hub):
    """Verify that captain multiplier doubles live points while bench multiplier is 0."""
    summary = matchday_hub.get_matchday_summary(entry_id=DEFAULT_ENTRY_ID, gameweek=4)

    captain = next((p for p in summary.starters if p.role == "CAP"), None)
    assert captain is not None
    assert captain.multiplier == 2
    assert captain.effective_points == captain.live_points * 2

    for b in summary.bench:
        assert b.multiplier == 0
        assert b.effective_points == 0


def test_fixture_squad_mapping(matchday_hub):
    """Verify fixtures are accurately linked with squad players featuring for home/away clubs."""
    summary = matchday_hub.get_matchday_summary(entry_id=DEFAULT_ENTRY_ID, gameweek=4)

    squad_fixtures = [f for f in summary.fixtures if f.has_squad_player]
    assert len(squad_fixtures) > 0

    for f in squad_fixtures:
        for hp in f.home_squad_players:
            assert hp.club_short == f.home_short
            assert hp.is_home is True
        for ap in f.away_squad_players:
            assert ap.club_short == f.away_short
            assert ap.is_home is False


def test_fpl_client_gameweek_endpoints():
    """Verify FPLClient retrieves real gameweek fixtures and live player stats."""
    client = FPLClient()
    fixtures = client.get_gameweek_fixtures(gameweek=4)
    live_data = client.get_gameweek_live(gameweek=4)

    assert isinstance(fixtures, list)
    assert len(fixtures) == 10
    assert "elements" in live_data
    assert len(live_data["elements"]) > 500


def test_fixture_status_label_upcoming_day_of_week(matchday_hub):
    """Verify that upcoming fixtures display the day of the week and kickoff time (e.g. Sat 15:00)."""
    summary = matchday_hub.get_matchday_summary(entry_id=DEFAULT_ENTRY_ID, gameweek=5)
    assert len(summary.fixtures) > 0
    upcoming = [f for f in summary.fixtures if not f.started and not f.finished]
    assert len(upcoming) > 0
    days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    for f in upcoming:
        parts = f.status_label.split()
        assert parts[0] in days, f"Expected day of week in status_label, got {f.status_label}"
        assert ":" in parts[1], f"Expected time with colon, got {f.status_label}"
