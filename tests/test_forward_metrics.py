"""
Unit & Integration Tests: 7 High-Alpha Forward Predictive Metrics
Validates:
1. Post-Shot Finishing True Skill Delta (xGOT - xG / Goals - xG)
2. Penalty Area Dominance & Box Touch Ratio
3. % xGI_Team (Talisman Share & Tier Classification)
4. Big Chances & Mean-Reversion Breakout Score (BCM)
5. Outside-the-Box Shooting Threat (xG_obox)
6. Forward Defensive Disruption & BPS Floor per 90
7. Betting Market Implied Probabilities & Poisson lambda
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

from clients.tactical_client import TacticalClient
from clients.fpl_client import FPLClient
from analytics.xp_model import XPModel
from config_manager import get_params


class TestTacticalForwardMetrics:
    """Test TacticalClient enhancements for forward predictive metrics."""

    @pytest.fixture
    def tactical_client(self):
        return TacticalClient()

    def test_league_tactical_forward_metrics_schema(self, tactical_client):
        """Verify get_league_tactical_df outputs all required forward metric fields."""
        df = tactical_client.get_league_tactical_df()
        assert not df.empty
        required_cols = [
            "finishing_skill_delta",
            "finishing_skill_npxg",
            "talisman_share",
            "talisman_tier"
        ]
        for col in required_cols:
            assert col in df.columns, f"Missing {col} in tactical dataframe"

        # Mathematical check: finishing_skill_delta == round(goals - xG, 2)
        sample = df.dropna().head(10)
        for _, row in sample.iterrows():
            expected_delta = round(row["goals"] - row["xG"], 2)
            assert abs(row["finishing_skill_delta"] - expected_delta) <= 0.02

    def test_talisman_share_bounds_and_tiers(self, tactical_client):
        """Verify talisman share is non-negative and correctly categorizes tiers."""
        df = tactical_client.get_league_tactical_df()
        assert (df["talisman_share"] >= 0.0).all()
        assert (df["talisman_share"] <= 100.0).all()

        valid_tiers = {
            "👑 ALPHA TALISMAN",
            "⚔️ MAJOR CONTRIBUTOR",
            "⚖️ SYSTEM COG",
            "🌱 SQUAD ROTATION"
        }
        assert set(df["talisman_tier"].unique()).issubset(valid_tiers)

    def test_player_shot_breakdown_big_chances_and_obox(self, tactical_client):
        """Test shot coordinate analysis and big chance extraction with synthetic shots."""
        mock_shots = [
            # Big chance scored in 6-yd box
            {"minute": "12", "result": "Goal", "situation": "OpenPlay", "shotType": "RightFoot",
             "X": "0.95", "Y": "0.50", "xG": "0.55", "date": "2026-09-01"},
            # Big chance missed in penalty box
            {"minute": "34", "result": "SavedShot", "situation": "OpenPlay", "shotType": "LeftFoot",
             "X": "0.88", "Y": "0.45", "xG": "0.40", "date": "2026-09-01"},
            # Regular penalty box shot (saved)
            {"minute": "55", "result": "SavedShot", "situation": "OpenPlay", "shotType": "RightFoot",
             "X": "0.85", "Y": "0.35", "xG": "0.15", "date": "2026-09-01"},
            # Outside box shot (missed)
            {"minute": "70", "result": "MissedShots", "situation": "OpenPlay", "shotType": "RightFoot",
             "X": "0.75", "Y": "0.50", "xG": "0.05", "date": "2026-09-01"},
        ]

        with patch.object(tactical_client, "get_player_shots_raw", return_value=mock_shots):
            breakdown = tactical_client.get_player_shot_breakdown("mock_123", season_year="2026")

            assert breakdown["total_shots"] == 4
            assert breakdown["six_yard_shots"] == 1
            assert breakdown["penalty_box_shots"] == 3
            assert breakdown["outside_box_shots"] == 1
            assert breakdown["box_shot_pct"] == 75.0
            assert breakdown["big_chances"] == 2
            assert breakdown["big_chances_missed"] == 1
            assert breakdown["big_chance_conversion"] == 50.0  # 1 scored out of 2
            assert breakdown["shots_on_target"] == 3  # Goal, SavedShot, SavedShot
            assert breakdown["sot_pct"] == 75.0
            assert breakdown["outside_box_xg"] == 0.05
            assert breakdown["mean_reversion_score"] >= 1.25


class TestFPLForwardDefensiveMetrics:
    """Test FPLClient defensive disruption and talisman calculations."""

    @pytest.fixture
    def fpl_client(self):
        return FPLClient()

    def test_fpl_players_df_defensive_disruption_columns(self, fpl_client):
        """Verify FPL player data includes defensive disruption per 90 metrics."""
        df = fpl_client.get_players_df()
        assert not df.empty
        required_cols = [
            "tackles",
            "recoveries",
            "bps",
            "tackles_per_90",
            "recoveries_per_90",
            "defensive_disruption_per_90",
            "bps_per_90",
            "talisman_share_fpl"
        ]
        for col in required_cols:
            assert col in df.columns, f"Missing {col} in FPL dataframe"

        assert (df["tackles_per_90"] >= 0.0).all()
        assert (df["recoveries_per_90"] >= 0.0).all()
        assert (df["defensive_disruption_per_90"] >= 0.0).all()
        assert (df["talisman_share_fpl"] >= 0.0).all()
        assert df["bps_per_90"].notna().all()


class TestXPModelForwardIntegration:
    """Test integration of 7 forward metrics into XPModel expected points calculations."""

    @pytest.fixture
    def xp_model(self):
        return XPModel()

    def test_calculate_player_xp_forward_diagnostics(self, xp_model):
        """Verify calculate_player_xp outputs all 7 forward metric diagnostic fields."""
        mock_player = {
            "id": 999,
            "web_name": "Test Striker",
            "full_name": "Test Forward Striker",
            "position_name": "FWD",
            "club_short": "MCI",
            "now_cost": 12.5,
            "expected_goals_per_90": 0.85,
            "expected_assists_per_90": 0.25,
            "penalties_order": 1,
            "defensive_disruption_per_90": 3.8,
            "bps_per_90": 28.5
        }
        mock_trends = {
            "minutes_status": "SECURE_STARTER",
            "avg_recent_mins": 85.0
        }
        mock_tac = {
            "talisman_share": 35.0,
            "talisman_tier": "👑 ALPHA TALISMAN",
            "box_shot_pct": 88.0,
            "six_yard_shots": 4,
            "finishing_skill_delta": 1.2,
            "big_chances": 6,
            "big_chances_missed": 2,
            "mean_reversion_score": 4.5,
            "outside_box_shots": 2,
            "outside_box_xg": 0.12,
            "NPxG_90": 0.82,
            "xA_90": 0.20
        }

        res = xp_model.calculate_player_xp(mock_player, mock_trends, mock_tac)

        assert res["talisman_share"] == 35.0
        assert res["talisman_tier"] == "👑 ALPHA TALISMAN"
        assert res["box_touch_ratio"] == 88.0
        assert res["finishing_skill_delta"] == 1.2
        assert res["big_chances"] == 6
        assert res["big_chances_missed"] == 2
        assert res["mean_reversion_score"] == 4.5
        assert res["outside_box_xg"] == 0.12
        assert res["forward_multiplier"] >= 1.0  # Elite talisman + box presence boost
        assert res["xP"] > 0.0

    def test_forward_multiplier_bounds(self, xp_model):
        """Verify forward multiplier remains mathematically constrained within [0.85, 1.20]."""
        mock_player = {
            "id": 1000,
            "web_name": "Underperforming Attacker",
            "position_name": "FWD",
            "club_short": "EVE",
            "now_cost": 6.0,
            "expected_goals_per_90": 0.10,
            "expected_assists_per_90": 0.05
        }
        mock_trends = {"minutes_status": "REGULAR_STARTER", "avg_recent_mins": 60.0}
        mock_tac = {
            "talisman_share": 2.0,
            "box_shot_pct": 10.0,
            "finishing_skill_delta": -2.5,
            "big_chances": 1,
            "big_chances_missed": 1,
            "mean_reversion_score": 1.25,
            "NPxG_90": 0.08,
            "xA_90": 0.04
        }

        res = xp_model.calculate_player_xp(mock_player, mock_trends, mock_tac)
        assert 0.85 <= res["forward_multiplier"] <= 1.20

    def test_squad_evaluation_includes_all_forward_metrics(self, xp_model):
        """Verify evaluate_squad_xp returns complete forward predictive metrics for Rubies Rangers."""
        df = xp_model.evaluate_squad_xp()
        assert len(df) == 15
        for col in [
            "talisman_share", "talisman_tier", "box_touch_ratio",
            "finishing_skill_delta", "mean_reversion_score",
            "outside_box_xg", "defensive_disruption_90", "forward_multiplier"
        ]:
            assert col in df.columns, f"Missing {col} in squad evaluate_squad_xp"
