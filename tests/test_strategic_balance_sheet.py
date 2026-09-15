"""
Unit & Integration Test Suite for Strategic Framework Phase 3: Dynamic Balance Sheet & Real Options Engine.
Verifies Free Transfer continuation valuation curves V(FT), price rise vs information uncertainty trade-offs,
American Real Options optimal stopping for strategic chips, dead cash drag penalties, and UI integration.
Governed by .agents/rules/moneyball_strategy.md and .agents/rules/python_standards.md.
"""

import pytest
import numpy as np
import pandas as pd
from typing import Dict, List

from analytics.strategic.contracts import (
    FreeTransferOptionProfile,
    PriceRiskProfile,
    ChipRealOptionValuation,
    SquadBalanceSheet,
)
from analytics.strategic.balance_sheet import BalanceSheetEngine
from clients.fpl_client import FPLClient
from ui.tabs.tab_strategic_balance_sheet import render_tab_strategic_balance_sheet


class TestPhase3Contracts:
    """Test immutability, validation, and dictionary serialization of Phase 3 contracts."""

    def test_free_transfer_option_profile_contract(self):
        prof = FreeTransferOptionProfile(
            current_ft=2,
            continuation_value_pts=2.56,
            marginal_option_values=(1.50, 1.06, 0.87, 0.75, 0.67),
            pivot_readiness_score=0.50,
            recommended_action="BANK_FOR_PIVOT",
            rationale="Holding 2 FTs unlocks structural 2-player swap optionality.",
        )
        assert prof.current_ft == 2
        assert prof.continuation_value_pts == 2.56
        assert len(prof.marginal_option_values) == 5

        with pytest.raises(Exception):
            prof.current_ft = 3  # type: ignore

        d = prof.to_dict()
        assert isinstance(d, dict)
        reconstructed = FreeTransferOptionProfile.from_dict(d)
        assert reconstructed == prof

    def test_price_risk_profile_contract(self):
        risk = PriceRiskProfile(
            player_id=101,
            web_name="Saka",
            club_short="ARS",
            now_cost=10.1,
            projected_change_prob=0.90,
            early_transfer_hurdle_rate_xp=0.83,
            information_risk_penalty_xp=0.75,
            risk_recommendation="LOCK_PRICE_EARLY",
            rationale="Imminent £0.1m rise (90% prob).",
        )
        assert risk.player_id == 101
        assert risk.projected_change_prob == 0.90

        with pytest.raises(Exception):
            risk.now_cost = 10.2  # type: ignore

        d = risk.to_dict()
        assert isinstance(d, dict)
        reconstructed = PriceRiskProfile.from_dict(d)
        assert reconstructed == risk

    def test_chip_real_option_valuation_contract(self):
        chip = ChipRealOptionValuation(
            chip_name="wildcard",
            chip_display_name="🃏 Wildcard",
            is_available=True,
            immediate_exercise_lift_xp=8.5,
            continuation_option_value_xp=18.4,
            exercise_boundary_gap=-9.9,
            optimal_decision="HOLD_OPTION",
            target_gameweek_window="GW31–GW33 (Pre-DGW Structural Build)",
            rationale="Preserve Wildcard for high-leverage DGW pivot.",
        )
        assert chip.chip_name == "wildcard"
        assert chip.optimal_decision == "HOLD_OPTION"
        assert chip.exercise_boundary_gap == -9.9

        with pytest.raises(Exception):
            chip.immediate_exercise_lift_xp = 10.0  # type: ignore

        d = chip.to_dict()
        assert isinstance(d, dict)
        reconstructed = ChipRealOptionValuation.from_dict(d)
        assert reconstructed == chip

    def test_squad_balance_sheet_contract(self):
        bs = SquadBalanceSheet(
            team_value=102.4,
            selling_value=101.4,
            bank_liquidity=1.2,
            dead_cash_drag_penalty_xp=0.0,
            free_transfers_available=2,
            ft_option_value_xp=2.56,
            total_balance_sheet_utility=104.24,
            lifecycle_phase="MID_SEASON_HARVEST",
            top_price_risks=(),
            chip_options=(),
        )
        assert bs.team_value == 102.4
        assert bs.lifecycle_phase == "MID_SEASON_HARVEST"

        with pytest.raises(Exception):
            bs.bank_liquidity = 2.0  # type: ignore

        d = bs.to_dict()
        assert isinstance(d, dict)
        reconstructed = SquadBalanceSheet.from_dict(d)
        assert reconstructed.team_value == bs.team_value
        assert reconstructed.total_balance_sheet_utility == bs.total_balance_sheet_utility


class TestFreeTransferOptionPricing:
    """Test non-linear FT continuation valuation and pivot readiness curves."""

    def test_ft_continuation_monotonicity_and_diminishing_returns(self):
        engine = BalanceSheetEngine()

        profiles = [engine.evaluate_free_transfer_options(ft) for ft in range(1, 6)]
        continuation_values = [p.continuation_value_pts for p in profiles]

        # 1. Monotonicity: V(FT) is strictly increasing
        for i in range(len(continuation_values) - 1):
            assert continuation_values[i + 1] > continuation_values[i], (
                f"V({i+2})={continuation_values[i+1]} must be > V({i+1})={continuation_values[i]}"
            )

        # 2. Diminishing Marginal Returns: Marginal lift is strictly decreasing
        marginal_gains = [
            continuation_values[i + 1] - continuation_values[i]
            for i in range(len(continuation_values) - 1)
        ]
        for i in range(len(marginal_gains) - 1):
            assert marginal_gains[i] >= marginal_gains[i + 1] - 1e-4, (
                f"Marginal gain {marginal_gains[i]} must be >= next marginal gain {marginal_gains[i+1]}"
            )

    def test_pivot_readiness_score(self):
        engine = BalanceSheetEngine()

        p1 = engine.evaluate_free_transfer_options(1)
        p2 = engine.evaluate_free_transfer_options(2)
        p3 = engine.evaluate_free_transfer_options(3)
        p5 = engine.evaluate_free_transfer_options(5)

        assert p1.pivot_readiness_score == 0.0
        assert p2.pivot_readiness_score == 0.50
        assert p3.pivot_readiness_score == 1.0
        assert p5.pivot_readiness_score == 1.0

        assert p1.recommended_action == "BANK_FOR_PIVOT"
        assert p3.recommended_action in ("EXECUTE_DOUBLE", "HOLD_RESERVE")


class TestPriceRiskAndInformationPenalty:
    """Test price change risk vs press conference injury uncertainty trade-offs."""

    def test_price_risk_evaluation_and_hurdles(self):
        engine = BalanceSheetEngine()
        df = engine.client.get_players_df()
        squad_state = engine.trajectory_engine.get_squad_state()
        pids = list(squad_state.squad_player_ids)

        risks = engine.evaluate_price_change_risk(df, pids, top_n=5)

        assert isinstance(risks, list)
        assert len(risks) > 0

        for r in risks:
            assert isinstance(r, PriceRiskProfile)
            assert 0.0 <= r.projected_change_prob <= 1.0
            assert r.information_risk_penalty_xp == 0.75
            assert r.early_transfer_hurdle_rate_xp > 0
            assert r.risk_recommendation in (
                "LOCK_PRICE_EARLY",
                "WAIT_FOR_PRESS_CONFERENCES",
                "AVOID_PRICE_FALL",
            )


class TestRealOptionsChipValuation:
    """Test American Real Options pricing and optimal stopping for strategic chips."""

    def test_chip_pricing_prevents_premature_waste(self):
        engine = BalanceSheetEngine()
        squad_state = engine.trajectory_engine.get_squad_state()
        pids = list(squad_state.squad_player_ids)

        # In mid-gameweek single fixture (GW10), all 4 chips should be preserved (HOLD_OPTION)
        chips = engine.evaluate_chip_options(squad_ids=pids, current_gw=10)

        assert len(chips) == 4
        chip_names = {c.chip_name for c in chips}
        assert chip_names == {"wildcard", "freehit", "bench_boost", "triple_captain"}

        for c in chips:
            assert c.optimal_decision == "HOLD_OPTION"
            assert c.exercise_boundary_gap < 0.0
            assert c.continuation_option_value_xp > c.immediate_exercise_lift_xp
            assert "GW" in c.target_gameweek_window

    def test_chip_pricing_handles_expired_status(self):
        engine = BalanceSheetEngine()
        pids = list(engine.trajectory_engine.get_squad_state().squad_player_ids)

        chips = engine.evaluate_chip_options(
            squad_ids=pids,
            current_gw=10,
            chips_status={"wildcard": False, "freehit": True, "bench_boost": False, "triple_captain": True}
        )

        wc = [c for c in chips if c.chip_name == "wildcard"][0]
        bb = [c for c in chips if c.chip_name == "bench_boost"][0]
        fh = [c for c in chips if c.chip_name == "freehit"][0]

        assert wc.is_available is False
        assert wc.optimal_decision == "EXPIRED"
        assert bb.is_available is False
        assert bb.optimal_decision == "EXPIRED"
        assert fh.is_available is True
        assert fh.optimal_decision == "HOLD_OPTION"


class TestDeadCashDragAndLifecycle:
    """Test dead cash drag penalty and season lifecycle phase classification."""

    def test_dead_cash_drag_calculation(self):
        engine = BalanceSheetEngine()

        # Bank <= £1.5m -> 0 drag
        assert engine.calculate_dead_cash_drag(0.0) == 0.0
        assert engine.calculate_dead_cash_drag(1.0) == 0.0
        assert engine.calculate_dead_cash_drag(1.5) == 0.0

        # Bank > £1.5m -> 0.25 pts per £1.0m surplus
        assert engine.calculate_dead_cash_drag(2.5) == 0.25
        assert engine.calculate_dead_cash_drag(3.5) == 0.50
        assert engine.calculate_dead_cash_drag(5.5) == 1.00

    def test_lifecycle_phase_classification(self):
        engine = BalanceSheetEngine()

        assert engine.determine_lifecycle_phase(1) == "CAPITAL_ACCUMULATION"
        assert engine.determine_lifecycle_phase(10) == "CAPITAL_ACCUMULATION"
        assert engine.determine_lifecycle_phase(15) == "MID_SEASON_HARVEST"
        assert engine.determine_lifecycle_phase(28) == "MID_SEASON_HARVEST"
        assert engine.determine_lifecycle_phase(29) == "DGW_MONETIZATION"
        assert engine.determine_lifecycle_phase(38) == "DGW_MONETIZATION"


class TestBalanceSheetEngineEndToEnd:
    """Test full balance sheet evaluation end-to-end."""

    def test_evaluate_balance_sheet_full(self):
        engine = BalanceSheetEngine()

        bs = engine.evaluate_balance_sheet(bank=2.0, free_transfers=3, current_gw=12)

        assert isinstance(bs, SquadBalanceSheet)
        assert bs.team_value >= 80.0
        assert bs.selling_value <= bs.team_value
        assert bs.bank_liquidity == 2.0
        assert bs.free_transfers_available == 3
        assert bs.ft_option_value_xp > 0.0
        assert bs.dead_cash_drag_penalty_xp == round((2.0 - 1.5) * 0.25, 2)
        assert bs.lifecycle_phase == "CAPITAL_ACCUMULATION"
        assert len(bs.chip_options) == 4
        assert len(bs.top_price_risks) > 0
        assert bs.total_balance_sheet_utility > bs.team_value


class TestPhase3UIIntegration:
    """Test Streamlit tab integration for Phase 3."""

    def test_render_tab_strategic_balance_sheet_callable(self):
        assert callable(render_tab_strategic_balance_sheet)
