"""
Trackers Package for Rubies Rangers
Unified feature extractors and monitors for FPL data.
"""

from trackers.fixture import run_fixture_tracker
from trackers.price import PriceTracker
from trackers.league import (
    LeagueTracker,
    display_league_standings,
    display_team_leagues,
    display_rival_squad,
    display_league_history,
    DEFAULT_LEAGUE_ID,
)
from trackers.tactical import audit_squad_tactical, show_league_leaders, show_player_shots
from trackers.trend import audit_squad_trends, show_player_deep_dive
from trackers.setpiece import run_setpiece_tracker
from trackers.xp import display_lineup, display_squad, display_odds, display_captains
from trackers.montecarlo import run_montecarlo_cli
from trackers.decision_audit import (
    DecisionAuditLedger,
    SuggestionSnapshot,
    CalibrationMetrics,
    PlayerAuditItem,
    TransferAuditItem,
)

__all__ = [
    "run_fixture_tracker",
    "PriceTracker",
    "LeagueTracker",
    "display_league_standings",
    "display_team_leagues",
    "display_rival_squad",
    "display_league_history",
    "DEFAULT_LEAGUE_ID",
    "audit_squad_tactical",
    "show_league_leaders",
    "show_player_shots",
    "audit_squad_trends",
    "show_player_deep_dive",
    "run_setpiece_tracker",
    "display_lineup",
    "display_squad",
    "display_odds",
    "display_captains",
    "run_montecarlo_cli",
    "DecisionAuditLedger",
    "SuggestionSnapshot",
    "CalibrationMetrics",
    "PlayerAuditItem",
    "TransferAuditItem",
]
