"""
Unit Tests for Closed-Loop Suggestion & Outcome Audit Ledger & Calibration Engine
"""

import os
import json
import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock

from trackers.decision_audit import (
    PlayerAuditItem,
    TransferAuditItem,
    SuggestionSnapshot,
    CalibrationMetrics,
    DecisionAuditLedger,
)


@pytest.fixture
def tmp_ledger_path(tmp_path):
    return str(tmp_path / "test_decision_audit_ledger.json")


@pytest.fixture
def mock_fpl_client():
    client = MagicMock()
    # Mock bootstrap data
    client.get_bootstrap_data.return_value = {
        "elements": [
            {"id": 1, "web_name": "Roefs", "element_type": 1},
            {"id": 2, "web_name": "Verbruggen", "element_type": 1},
            {"id": 3, "web_name": "Pedro Porro", "element_type": 2},
            {"id": 4, "web_name": "Senesi", "element_type": 2},
            {"id": 5, "web_name": "Guéhi", "element_type": 2},
            {"id": 6, "web_name": "Robinson", "element_type": 2},
            {"id": 7, "web_name": "Thiaw", "element_type": 2},
            {"id": 8, "web_name": "Foden", "element_type": 3},
            {"id": 9, "web_name": "Ødegaard", "element_type": 3},
            {"id": 10, "web_name": "Mbeumo", "element_type": 3},
            {"id": 11, "web_name": "Cherki", "element_type": 3},
            {"id": 12, "web_name": "Rogers", "element_type": 3},
            {"id": 13, "web_name": "João Pedro", "element_type": 4},
            {"id": 14, "web_name": "Isak", "element_type": 4},
            {"id": 15, "web_name": "Solanke", "element_type": 4},
        ]
    }
    # Mock live data
    client.get_gameweek_live.return_value = {
        "elements": [
            {"id": 1, "stats": {"total_points": 6, "minutes": 90, "goals_scored": 0, "assists": 0, "clean_sheets": 1, "bonus": 1}},
            {"id": 2, "stats": {"total_points": 2, "minutes": 90, "goals_scored": 0, "assists": 0, "clean_sheets": 0, "bonus": 0}},
            {"id": 3, "stats": {"total_points": 7, "minutes": 90, "goals_scored": 0, "assists": 1, "clean_sheets": 0, "bonus": 2}},
            {"id": 4, "stats": {"total_points": 6, "minutes": 90, "goals_scored": 0, "assists": 0, "clean_sheets": 1, "bonus": 0}},
            {"id": 5, "stats": {"total_points": 2, "minutes": 90, "goals_scored": 0, "assists": 0, "clean_sheets": 0, "bonus": 0}},
            {"id": 6, "stats": {"total_points": 2, "minutes": 90, "goals_scored": 0, "assists": 0, "clean_sheets": 0, "bonus": 0}},
            {"id": 7, "stats": {"total_points": 1, "minutes": 15, "goals_scored": 0, "assists": 0, "clean_sheets": 0, "bonus": 0}},
            {"id": 8, "stats": {"total_points": 10, "minutes": 90, "goals_scored": 1, "assists": 1, "clean_sheets": 0, "bonus": 3}},
            {"id": 9, "stats": {"total_points": 5, "minutes": 90, "goals_scored": 0, "assists": 1, "clean_sheets": 0, "bonus": 0}},
            {"id": 10, "stats": {"total_points": 8, "minutes": 90, "goals_scored": 1, "assists": 0, "clean_sheets": 0, "bonus": 2}},
            {"id": 11, "stats": {"total_points": 0, "minutes": 0, "goals_scored": 0, "assists": 0, "clean_sheets": 0, "bonus": 0}},  # Benched 0 mins
            {"id": 12, "stats": {"total_points": 6, "minutes": 75, "goals_scored": 1, "assists": 0, "clean_sheets": 0, "bonus": 1}},  # Auto-sub in
            {"id": 13, "stats": {"total_points": 5, "minutes": 80, "goals_scored": 0, "assists": 1, "clean_sheets": 0, "bonus": 0}},
            {"id": 14, "stats": {"total_points": 9, "minutes": 90, "goals_scored": 1, "assists": 0, "clean_sheets": 0, "bonus": 3}},
            {"id": 15, "stats": {"total_points": 2, "minutes": 90, "goals_scored": 0, "assists": 0, "clean_sheets": 0, "bonus": 0}},
        ]
    }
    client.get_current_gameweek.return_value = 4
    return client


class TestDecisionAuditContracts:
    """Test data contracts and immutable dataclass behaviors."""

    def test_player_audit_item_residual(self):
        item = PlayerAuditItem(
            player_id=8,
            web_name="Foden",
            position_name="MID",
            club_short="MCI",
            projected_xp=7.2,
            actual_points=10.0,
            actual_minutes=90,
            is_starter=True,
            is_captain=True
        )
        assert item.residual == 2.8

    def test_transfer_audit_item_realized_roi(self):
        tr = TransferAuditItem(
            player_in_id=10,
            player_in_name="Mbeumo",
            player_in_xp=6.5,
            player_out_id=12,
            player_out_name="Rogers",
            player_out_xp=4.2,
            hit_cost=0,
            player_in_actual_pts=8.0,
            player_out_actual_pts=6.0
        )
        assert tr.projected_gain == 2.3
        assert tr.realized_roi == 2.0

        # With -4 hit cost
        tr_hit = TransferAuditItem(
            player_in_id=10,
            player_in_name="Mbeumo",
            player_in_xp=6.5,
            player_out_id=12,
            player_out_name="Rogers",
            player_out_xp=4.2,
            hit_cost=4,
            player_in_actual_pts=8.0,
            player_out_actual_pts=6.0
        )
        assert tr_hit.projected_gain == -1.7
        assert tr_hit.realized_roi == -2.0


class TestDecisionAuditLedger:
    """Test ledger snapshotting, persistence, reconciliation, and calibration metrics."""

    def test_snapshot_and_load(self, tmp_ledger_path, mock_fpl_client):
        ledger = DecisionAuditLedger(ledger_file=tmp_ledger_path, client=mock_fpl_client)

        starters = [
            {"id": 1, "web_name": "Roefs", "position_name": "GKP", "club_short": "SUN", "projected_xp": 4.0},
            {"id": 3, "web_name": "Pedro Porro", "position_name": "DEF", "club_short": "TOT", "projected_xp": 5.0},
            {"id": 4, "web_name": "Senesi", "position_name": "DEF", "club_short": "BOU", "projected_xp": 4.2},
            {"id": 5, "web_name": "Guéhi", "position_name": "DEF", "club_short": "CRY", "projected_xp": 3.8},
            {"id": 6, "web_name": "Robinson", "position_name": "DEF", "club_short": "FUL", "projected_xp": 4.1},
            {"id": 8, "web_name": "Foden", "position_name": "MID", "club_short": "MCI", "projected_xp": 7.2},
            {"id": 9, "web_name": "Ødegaard", "position_name": "MID", "club_short": "ARS", "projected_xp": 6.8},
            {"id": 10, "web_name": "Mbeumo", "position_name": "MID", "club_short": "BRE", "projected_xp": 6.5},
            {"id": 11, "web_name": "Cherki", "position_name": "MID", "club_short": "MCI", "projected_xp": 4.5},
            {"id": 13, "web_name": "João Pedro", "position_name": "FWD", "club_short": "BHA", "projected_xp": 5.8},
            {"id": 14, "web_name": "Isak", "position_name": "FWD", "club_short": "NEW", "projected_xp": 7.5},
        ]
        bench = [
            {"id": 2, "web_name": "Verbruggen", "position_name": "GKP", "club_short": "BHA", "projected_xp": 3.5},
            {"id": 12, "web_name": "Rogers", "position_name": "MID", "club_short": "AVL", "projected_xp": 4.2},
            {"id": 15, "web_name": "Solanke", "position_name": "FWD", "club_short": "TOT", "projected_xp": 5.5},
            {"id": 7, "web_name": "Thiaw", "position_name": "DEF", "club_short": "NEW", "projected_xp": 3.0},
        ]

        snap = ledger.snapshot_suggestion(
            gw=4,
            season="2024-25",
            starters=starters,
            bench=bench,
            captain_name="Foden",
            vice_captain_name="Isak",
            formation="4-4-2",
            projected_starting_xp=59.4,
            projected_effective_xp=66.6,
            profile_name="Rubies Rangers",
            applied_by_user=True
        )

        assert snap.gw == 4
        assert snap.captain_name == "Foden"
        assert not snap.is_reconciled

        # Verify reload from disk
        ledger2 = DecisionAuditLedger(ledger_file=tmp_ledger_path, client=mock_fpl_client)
        assert len(ledger2.get_all_snapshots()) == 1
        loaded_snap = ledger2.get_all_snapshots()[0]
        assert loaded_snap.gw == 4
        assert loaded_snap.captain_name == "Foden"

    def test_reconcile_gameweek_auto_subs_and_captain_doubling(self, tmp_ledger_path, mock_fpl_client):
        ledger = DecisionAuditLedger(ledger_file=tmp_ledger_path, client=mock_fpl_client)

        starters = [
            {"id": 1, "web_name": "Roefs", "position_name": "GKP", "club_short": "SUN", "projected_xp": 4.0},
            {"id": 3, "web_name": "Pedro Porro", "position_name": "DEF", "club_short": "TOT", "projected_xp": 5.0},
            {"id": 4, "web_name": "Senesi", "position_name": "DEF", "club_short": "BOU", "projected_xp": 4.2},
            {"id": 5, "web_name": "Guéhi", "position_name": "DEF", "club_short": "CRY", "projected_xp": 3.8},
            {"id": 6, "web_name": "Robinson", "position_name": "DEF", "club_short": "FUL", "projected_xp": 4.1},
            {"id": 8, "web_name": "Foden", "position_name": "MID", "club_short": "MCI", "projected_xp": 7.2},
            {"id": 9, "web_name": "Ødegaard", "position_name": "MID", "club_short": "ARS", "projected_xp": 6.8},
            {"id": 10, "web_name": "Mbeumo", "position_name": "MID", "club_short": "BRE", "projected_xp": 6.5},
            {"id": 11, "web_name": "Cherki", "position_name": "MID", "club_short": "MCI", "projected_xp": 4.5},  # 0 mins in mock
            {"id": 13, "web_name": "João Pedro", "position_name": "FWD", "club_short": "BHA", "projected_xp": 5.8},
            {"id": 14, "web_name": "Isak", "position_name": "FWD", "club_short": "NEW", "projected_xp": 7.5},
        ]
        bench = [
            {"id": 2, "web_name": "Verbruggen", "position_name": "GKP", "club_short": "BHA", "projected_xp": 3.5},
            {"id": 12, "web_name": "Rogers", "position_name": "MID", "club_short": "AVL", "projected_xp": 4.2},  # Sub 1 (6 pts)
            {"id": 15, "web_name": "Solanke", "position_name": "FWD", "club_short": "TOT", "projected_xp": 5.5},
            {"id": 7, "web_name": "Thiaw", "position_name": "DEF", "club_short": "NEW", "projected_xp": 3.0},
        ]

        ledger.snapshot_suggestion(
            gw=4,
            season="2024-25",
            starters=starters,
            bench=bench,
            captain_name="Foden",
            vice_captain_name="Isak",
            formation="4-4-2",
            projected_starting_xp=59.4,
            projected_effective_xp=66.6,
            profile_name="Rubies Rangers"
        )

        reconciled = ledger.reconcile_gameweek("2024-25", 4)
        assert reconciled is not None
        assert reconciled.is_reconciled

        # Cherki played 0 mins -> Auto-sub with Rogers (6 pts)
        assert len(reconciled.auto_subs) == 1
        assert reconciled.auto_subs[0] == ("Cherki", "Rogers")

        # Captain Foden scored 10 pts -> Doubled to 20 pts
        assert reconciled.actual_captain_points == 10.0
        # Total effective points includes Foden (10 x 2) + Roefs(6) + Porro(7) + Senesi(6) + Guehi(2) + Robinson(2) + Odegaard(5) + Mbeumo(8) + Rogers(6) + JP(5) + Isak(9)
        # Expected total: 20 + 6 + 7 + 6 + 2 + 2 + 5 + 8 + 6 + 5 + 9 = 76 pts
        assert reconciled.actual_effective_points == 76.0
        # Residual = 76.0 - 66.6 = +9.4
        assert reconciled.prediction_residual == 9.4

    def test_calibration_metrics_computation(self, tmp_ledger_path, mock_fpl_client):
        ledger = DecisionAuditLedger(ledger_file=tmp_ledger_path, client=mock_fpl_client)

        # Seed GW1-4
        count = ledger.seed_historical_gameweeks(up_to_gw=4)
        assert count == 4

        metrics = ledger.compute_calibration_metrics()
        assert metrics.total_gws_audited == 4
        assert metrics.calibration_status in ["WELL_CALIBRATED", "OVER_PROJECTING", "UNDER_PROJECTING"]
        assert isinstance(metrics.cumulative_residual, float)
        assert "GKP" in metrics.positional_bias
        assert "DEF" in metrics.positional_bias
        assert "MID" in metrics.positional_bias
        assert "FWD" in metrics.positional_bias
        assert metrics.captaincy_accuracy_pct >= 0.0

    def test_seed_historical_gameweeks_force(self, tmp_ledger_path, mock_fpl_client):
        ledger = DecisionAuditLedger(ledger_file=tmp_ledger_path, client=mock_fpl_client)

        # Initial seed
        count1 = ledger.seed_historical_gameweeks(up_to_gw=2)
        assert count1 == 2

        # Calling without force should be idempotent (skip existing)
        count2 = ledger.seed_historical_gameweeks(up_to_gw=2, force=False)
        assert count2 == 0

        # Calling with force should re-seed both
        count3 = ledger.seed_historical_gameweeks(up_to_gw=2, force=True)
        assert count3 == 2

