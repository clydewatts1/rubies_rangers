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
    MemberDayScore,
    MiniLeagueScoreboard,
)
from clients.fpl_client import FPLClient
from trackers.league import DEFAULT_ENTRY_ID, DEFAULT_LEAGUE_ID


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


def test_minileague_dataclass_immutability():
    """Verify MemberDayScore and MiniLeagueScoreboard contracts are immutable frozen dataclasses."""
    m = MemberDayScore(
        entry_id=1,
        team_name="Test FC",
        manager_name="Tester",
        rank=1,
        last_rank=1,
        captain_name="Haaland",
        captain_multiplier=2,
        captain_points=26,
        captain_day="Saturday",
        active_chip=None,
        transfer_cost=0,
        starters_played=11,
        starters_playing=0,
        starters_to_play=0,
        day_points={"Saturday": 50, "Sunday": 20},
        cumulative_day_points={"Saturday": 50, "Sunday": 70},
        live_gw_points=70,
        net_gw_points=70,
        projected_final_points=70.0,
        total_league_points=320
    )
    assert m.team_name == "Test FC"
    assert m.net_gw_points == 70
    with pytest.raises(FrozenInstanceError):
        m.net_gw_points = 80


def test_minileague_scoreboard_gw4_extraction(matchday_hub):
    """Verify MiniLeagueScoreboard aggregates members, active days, and valid totals for GW4."""
    scoreboard = matchday_hub.get_mini_league_scoreboard(
        league_id=DEFAULT_LEAGUE_ID,
        gameweek=4,
        max_teams=6
    )

    assert isinstance(scoreboard, MiniLeagueScoreboard)
    assert scoreboard.gameweek == 4
    assert len(scoreboard.members) > 0
    assert len(scoreboard.active_days) > 0
    assert "Saturday" in scoreboard.active_days

    # League summary statistics
    assert scoreboard.league_avg_live_points > 0
    assert scoreboard.league_avg_net_points > 0
    assert len(scoreboard.top_captains) > 0


def test_minileague_day_points_sum_equals_live_total(matchday_hub):
    """Verify that sum of day-of-week points equals live_gw_points for every member."""
    scoreboard = matchday_hub.get_mini_league_scoreboard(
        league_id=DEFAULT_LEAGUE_ID,
        gameweek=4,
        max_teams=6
    )

    for m in scoreboard.members:
        day_sum = sum(m.day_points.values())
        assert day_sum == m.live_gw_points, f"Mismatch for {m.team_name}: sum={day_sum} vs live={m.live_gw_points}"
        assert m.net_gw_points == (m.live_gw_points - m.transfer_cost)


def test_minileague_cumulative_progression_monotonic(matchday_hub):
    """Verify cumulative day-of-week points are monotonically non-decreasing."""
    scoreboard = matchday_hub.get_mini_league_scoreboard(
        league_id=DEFAULT_LEAGUE_ID,
        gameweek=4,
        max_teams=6
    )

    for m in scoreboard.members:
        running = 0
        for d in scoreboard.active_days:
            cum = m.cumulative_day_points.get(d, 0)
            assert cum >= running, f"Cumulative points decreased for {m.team_name} on {d}: {cum} < {running}"
            running = cum

