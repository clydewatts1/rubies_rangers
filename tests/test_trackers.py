"""
Unit tests for trackers package.
Validates direct imports from trackers.* and backward-compatibility shims.
"""

import pytest
import trackers
from trackers import (
    PriceTracker,
    LeagueTracker,
    DEFAULT_LEAGUE_ID,
    run_fixture_tracker,
    audit_squad_tactical,
    audit_squad_trends,
    run_setpiece_tracker,
    display_lineup,
    run_montecarlo_cli,
)
import price_tracker as pt_shim
import league_tracker as lt_shim


def test_tracker_exports():
    """Verify trackers package exposes all canonical classes and functions."""
    assert PriceTracker is pt_shim.PriceTracker
    assert LeagueTracker is lt_shim.LeagueTracker
    assert DEFAULT_LEAGUE_ID == lt_shim.DEFAULT_LEAGUE_ID
    assert callable(run_fixture_tracker)
    assert callable(audit_squad_tactical)
    assert callable(audit_squad_trends)
    assert callable(run_setpiece_tracker)
    assert callable(display_lineup)
    assert callable(run_montecarlo_cli)


def test_price_tracker_initialization():
    """Verify PriceTracker instantiates and has expected methods."""
    pt = PriceTracker()
    assert hasattr(pt, "get_market_df")
    assert hasattr(pt, "get_squad_price_report")
    assert hasattr(pt, "get_top_risers")
    assert hasattr(pt, "get_top_fallers")


def test_league_tracker_initialization():
    """Verify LeagueTracker instantiates and has expected methods."""
    lt = LeagueTracker()
    assert hasattr(lt, "get_team_leagues")
    assert hasattr(lt, "get_league_standings")
    assert hasattr(lt, "get_team_picks")
    assert hasattr(lt, "get_league_ownership")
