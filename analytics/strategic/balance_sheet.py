"""
Dynamic Balance Sheet & Real Options Engine (Phase 3).
Quantifies monetary liquidity, Free Transfer continuation option valuation V(FT, t),
price rise vs. information uncertainty trade-offs, dead cash drag diagnostics,
and American Real Options pricing for strategic chips.
Governed by .agents/rules/moneyball_strategy.md and .agents/rules/python_standards.md.
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple, Any, Set
import numpy as np
import pandas as pd

from config_manager import get_params, get_system_config
from clients.fpl_client import FPLClient
from analytics.strategic.contracts import (
    FreeTransferOptionProfile,
    PriceRiskProfile,
    ChipRealOptionValuation,
    SquadBalanceSheet,
    StrategicSquadState,
)
from analytics.strategic.trajectory_engine import (
    TrajectoryEngine,
    build_strategic_squad_state,
)


class BalanceSheetEngine:
    """
    Evaluates the FPL squad as an institutional balance sheet.
    Computes real options continuation values, price change risk, cash drag, and chip pricing.
    """

    def __init__(
        self,
        fpl_client: Optional[FPLClient] = None,
        profile: Optional[str] = None
    ) -> None:
        self.client = fpl_client or FPLClient()
        self.profile = profile
        self.trajectory_engine = TrajectoryEngine(fpl_client=self.client, profile=profile)

    def evaluate_balance_sheet(
        self,
        squad_player_ids: Optional[List[int]] = None,
        bank: Optional[float] = None,
        free_transfers: Optional[int] = None,
        chips_status: Optional[Dict[str, bool]] = None,
        current_gw: Optional[int] = None,
    ) -> SquadBalanceSheet:
        """
        Generates the comprehensive balance sheet valuation and options state.
        """
        sq_state = self.trajectory_engine.get_squad_state()
        pids = squad_player_ids if squad_player_ids is not None else list(sq_state.squad_player_ids)
        cur_bank = float(bank if bank is not None else sq_state.bank_balance)
        cur_ft = int(free_transfers if free_transfers is not None else sq_state.free_transfers_available)
        gw = int(current_gw if current_gw is not None else sq_state.gameweek)

        df_players = self.client.get_players_df()
        squad_df = df_players[df_players["id"].isin(pids)].copy()

        # 1. Team Valuation & Realizable Liquidation Value
        # FPL 50% profit tax rule: selling_price = now_cost - (now_cost - cost_change_start) / 2 if in profit
        team_value = float(squad_df["now_cost"].sum()) if not squad_df.empty else 100.0
        # If purchase history unavailable, approximate selling value with 0.985 factor or now_cost
        selling_value = round(team_value * 0.99, 1)

        # 2. Free Transfer Continuation Option Valuation
        ft_profile = self.evaluate_free_transfer_options(ft_count=cur_ft)

        # 3. Dead Cash Drag Penalty
        cash_drag = self.calculate_dead_cash_drag(cur_bank)

        # 4. Price Change vs. Information Uncertainty Risk
        price_risks = self.evaluate_price_change_risk(df_players=df_players, current_squad_ids=pids)

        # 5. Strategic Chip Real Options Pricing
        chip_options = self.evaluate_chip_options(
            squad_ids=pids,
            current_gw=gw,
            chips_status=chips_status
        )

        # 6. Lifecycle Phase
        phase = self.determine_lifecycle_phase(current_gw=gw)

        # 7. Total Balance Sheet Utility
        chip_util = sum(c.continuation_option_value_xp for c in chip_options if c.is_available) * 0.10
        total_utility = round(
            team_value + cur_bank + (ft_profile.continuation_value_pts * 0.25) - (cash_drag * 0.5) + chip_util,
            2
        )

        return SquadBalanceSheet(
            team_value=round(team_value, 1),
            selling_value=round(selling_value, 1),
            bank_liquidity=round(cur_bank, 1),
            dead_cash_drag_penalty_xp=round(cash_drag, 2),
            free_transfers_available=cur_ft,
            ft_option_value_xp=round(ft_profile.continuation_value_pts, 2),
            total_balance_sheet_utility=total_utility,
            lifecycle_phase=phase,
            top_price_risks=tuple(price_risks),
            chip_options=tuple(chip_options),
        )

    def evaluate_free_transfer_options(
        self,
        ft_count: int,
        horizon: int = 5
    ) -> FreeTransferOptionProfile:
        """
        Computes the continuation value of holding 1..5 Free Transfers using non-linear option pricing.
        V(FT) = ft_mult * sum_{k=1}^FT (1 / sqrt(k))
        """
        strat_cfg = get_params("strategic", profile=self.profile) or {}
        ft_mult = float(strat_cfg.get("balance_sheet", {}).get("ft_option_mult", 1.50))

        ft = max(1, min(5, ft_count))
        marginal_values = tuple(round(ft_mult * (1.0 / math.sqrt(k)), 2) for k in range(1, 6))
        continuation_value = round(sum(marginal_values[:ft]), 2)

        # Pivot readiness: 1 FT = 0.0, 2 FT = 0.5, 3 FT = 1.0, 4-5 FT = 1.0
        pivot_score = round(min(1.0, max(0.0, (ft - 1) / 2.0)), 2)

        if ft >= 3:
            action = "EXECUTE_DOUBLE"
            rationale = (
                f"Holding {ft} FTs provides peak multi-player pivot readiness ({pivot_score * 100:.0f}%). "
                f"Can execute 2 or 3 strategic structural transfers simultaneously with zero hit penalty."
            )
        elif ft == 2:
            action = "BANK_FOR_PIVOT"
            rationale = (
                f"Holding 2 FTs unlocks structural 2-player swap optionality ({pivot_score * 100:.0f}% readiness). "
                f"Banking 1 transfer preserves flexibility to pivot across price brackets next gameweek."
            )
        else:
            action = "BANK_FOR_PIVOT"
            rationale = (
                "Holding 1 FT limits tactical scope to single-player swaps. "
                "Recommend banking this gameweek to build 2 FTs unless liquidating a high-risk asset."
            )

        return FreeTransferOptionProfile(
            current_ft=ft,
            continuation_value_pts=continuation_value,
            marginal_option_values=marginal_values,
            pivot_readiness_score=pivot_score,
            recommended_action=action,
            rationale=rationale,
        )

    def evaluate_price_change_risk(
        self,
        df_players: pd.DataFrame,
        current_squad_ids: List[int],
        top_n: int = 8
    ) -> List[PriceRiskProfile]:
        """
        Evaluates early transfer execution before price rise/fall vs. press conference injury uncertainty.
        Information risk penalty is estimated at ~0.75 expected points.
        """
        profiles: List[PriceRiskProfile] = []
        info_penalty_xp = 0.75

        # Check for transfer velocity or price momentum columns
        df = df_players.copy()
        if "transfers_in_event" not in df.columns:
            df["transfers_in_event"] = 0
        if "transfers_out_event" not in df.columns:
            df["transfers_out_event"] = 0

        df["net_transfers"] = df["transfers_in_event"] - df["transfers_out_event"]

        # Sort by highest net transfers (rising candidates) and lowest net transfers (falling candidates)
        top_risers = df.sort_values(by="net_transfers", ascending=False).head(top_n)
        owned_fallers = df[df["id"].isin(current_squad_ids)].sort_values(by="net_transfers", ascending=True).head(4)

        eval_set = pd.concat([top_risers, owned_fallers]).drop_duplicates(subset=["id"])

        for _, row in eval_set.iterrows():
            pid = int(row["id"])
            pname = str(row["web_name"])
            club = str(row.get("club_short") or row.get("team_code") or "PL")
            cost = float(row["now_cost"])
            net_xfer = float(row.get("net_transfers", 0))
            is_owned = pid in current_squad_ids

            # Approximate price change probability based on transfer velocity
            if net_xfer > 50000:
                prob = min(0.95, 0.50 + (net_xfer / 200000.0))
            elif net_xfer < -50000:
                prob = min(0.95, 0.50 + (abs(net_xfer) / 200000.0))
            else:
                prob = 0.25

            # Hurdle rate: expected value of £0.1m price change (~0.5 pts equivalent) vs info penalty
            hurdle_xp = round(info_penalty_xp / max(0.1, prob), 2)

            if is_owned and net_xfer < -75000:
                rec = "AVOID_PRICE_FALL"
                rat = f"Heavy selling pressure ({net_xfer:,.0f} net). Imminent £0.1m drop risk ({prob * 100:.0f}% prob)."
            elif prob >= 0.85:
                rec = "LOCK_PRICE_EARLY"
                rat = f"Imminent £0.1m rise ({prob * 100:.0f}% prob). Early execution justified if player has no mid-week match."
            else:
                rec = "WAIT_FOR_PRESS_CONFERENCES"
                rat = f"Price change probability ({prob * 100:.0f}%) below hurdle rate. Wait for manager press conferences to ensure fitness."

            profiles.append(PriceRiskProfile(
                player_id=pid,
                web_name=pname,
                club_short=club,
                now_cost=cost,
                projected_change_prob=round(prob, 2),
                early_transfer_hurdle_rate_xp=hurdle_xp,
                information_risk_penalty_xp=info_penalty_xp,
                risk_recommendation=rec,
                rationale=rat,
            ))

        return profiles

    def evaluate_chip_options(
        self,
        squad_ids: List[int],
        current_gw: int,
        chips_status: Optional[Dict[str, bool]] = None
    ) -> List[ChipRealOptionValuation]:
        """
        Prices American Real Options for all 5 strategic chips using optimal stopping boundaries.
        Prevents premature chip execution in low-leverage single gameweeks.
        """
        chips: List[ChipRealOptionValuation] = []
        status = chips_status or {
            "wildcard": True,
            "freehit": True,
            "bench_boost": True,
            "triple_captain": True,
        }

        strat_cfg = get_params("strategic", profile=self.profile) or {}
        gamma = float(strat_cfg.get("horizon", {}).get("discount_gamma", 0.92))

        # 1. Wildcard Option
        wc_avail = status.get("wildcard", True)
        # Immediate lift in single GW: ~6.0 - 10.0 pts
        wc_immediate = 8.5
        # Peak future DGW / macro swing deployment lift (e.g. GW30-34): ~24.0 pts
        wc_peak_target_gw = 33 if current_gw < 30 else 36
        discount_steps = max(0, wc_peak_target_gw - current_gw)
        wc_continuation = round(24.0 * (gamma ** min(8, discount_steps)), 1)
        wc_gap = round(wc_immediate - wc_continuation, 1)

        if not wc_avail:
            wc_dec = "EXPIRED"
            wc_rat = "Wildcard has already been consumed for this half of the season."
        elif wc_gap >= 0:
            wc_dec = "EXERCISE_NOW"
            wc_rat = "Severe structural squad distress justifies immediate Wildcard execution."
        else:
            wc_dec = "HOLD_OPTION"
            wc_rat = (
                f"Preserve Wildcard for high-leverage DGW pivot (GW{wc_peak_target_gw}). "
                f"Future deployment value ({wc_continuation:.1f} pts) exceeds immediate single GW lift ({wc_immediate:.1f} pts)."
            )

        chips.append(ChipRealOptionValuation(
            chip_name="wildcard",
            chip_display_name="🃏 Wildcard",
            is_available=wc_avail,
            immediate_exercise_lift_xp=wc_immediate,
            continuation_option_value_xp=wc_continuation,
            exercise_boundary_gap=wc_gap,
            optimal_decision=wc_dec,
            target_gameweek_window=f"GW{wc_peak_target_gw - 2}–GW{wc_peak_target_gw} (Pre-DGW Structural Build)",
            rationale=wc_rat,
        ))

        # 2. Free Hit Option
        fh_avail = status.get("freehit", True)
        fh_immediate = 7.0
        fh_peak_gw = 29 if current_gw < 29 else 34
        fh_steps = max(0, fh_peak_gw - current_gw)
        fh_continuation = round(26.0 * (gamma ** min(8, fh_steps)), 1)
        fh_gap = round(fh_immediate - fh_continuation, 1)

        if not fh_avail:
            fh_dec = "EXPIRED"
            fh_rat = "Free Hit chip already consumed."
        elif fh_gap >= 0:
            fh_dec = "EXERCISE_NOW"
            fh_rat = "Major squad blank crisis justifies immediate Free Hit deployment."
        else:
            fh_dec = "HOLD_OPTION"
            fh_rat = (
                f"Preserve Free Hit for Major Blank/Double Gameweek (GW{fh_peak_gw}). "
                f"Expected future value ({fh_continuation:.1f} pts) far exceeds current single GW yield ({fh_immediate:.1f} pts)."
            )

        chips.append(ChipRealOptionValuation(
            chip_name="freehit",
            chip_display_name="🎯 Free Hit",
            is_available=fh_avail,
            immediate_exercise_lift_xp=fh_immediate,
            continuation_option_value_xp=fh_continuation,
            exercise_boundary_gap=fh_gap,
            optimal_decision=fh_dec,
            target_gameweek_window=f"GW{fh_peak_gw} (Major Blank/Double Gameweek)",
            rationale=fh_rat,
        ))

        # 3. Triple Captain Option
        tc_avail = status.get("triple_captain", True)
        tc_immediate = 6.5
        tc_peak_gw = 34 if current_gw < 34 else 37
        tc_steps = max(0, tc_peak_gw - current_gw)
        tc_continuation = round(16.0 * (gamma ** min(8, tc_steps)), 1)
        tc_gap = round(tc_immediate - tc_continuation, 1)

        if not tc_avail:
            tc_dec = "EXPIRED"
            tc_rat = "Triple Captain chip already consumed."
        elif tc_gap >= 0:
            tc_dec = "EXERCISE_NOW"
            tc_rat = "Elite premium asset in extraordinary fixture justifies immediate Triple Captain."
        else:
            tc_dec = "HOLD_OPTION"
            tc_rat = (
                f"Preserve Triple Captain for Double Gameweek (GW{tc_peak_gw}). "
                f"Expected DGW yield ({tc_continuation:.1f} pts across 2 fixtures) exceeds single match ceiling ({tc_immediate:.1f} pts)."
            )

        chips.append(ChipRealOptionValuation(
            chip_name="triple_captain",
            chip_display_name="👑 Triple Captain",
            is_available=tc_avail,
            immediate_exercise_lift_xp=tc_immediate,
            continuation_option_value_xp=tc_continuation,
            exercise_boundary_gap=tc_gap,
            optimal_decision=tc_dec,
            target_gameweek_window=f"GW{tc_peak_gw} (Double Gameweek Premium Anchor)",
            rationale=tc_rat,
        ))

        # 4. Bench Boost Option
        bb_avail = status.get("bench_boost", True)
        bb_immediate = 5.0
        bb_peak_gw = 37 if current_gw < 37 else 38
        bb_steps = max(0, bb_peak_gw - current_gw)
        bb_continuation = round(22.0 * (gamma ** min(8, bb_steps)), 1)
        bb_gap = round(bb_immediate - bb_continuation, 1)

        if not bb_avail:
            bb_dec = "EXPIRED"
            bb_rat = "Bench Boost chip already consumed."
        elif bb_gap >= 0:
            bb_dec = "EXERCISE_NOW"
            bb_rat = "All 15 players have favorable fixtures justifying Bench Boost deployment."
        else:
            bb_dec = "HOLD_OPTION"
            bb_rat = (
                f"Deploy Bench Boost post-Wildcard in Mega Double Gameweek (GW{bb_peak_gw}). "
                f"Stacking 15 DGW starters yields {bb_continuation:.1f} pts vs single GW bench yield ({bb_immediate:.1f} pts)."
            )

        chips.append(ChipRealOptionValuation(
            chip_name="bench_boost",
            chip_display_name="🚀 Bench Boost",
            is_available=bb_avail,
            immediate_exercise_lift_xp=bb_immediate,
            continuation_option_value_xp=bb_continuation,
            exercise_boundary_gap=bb_gap,
            optimal_decision=bb_dec,
            target_gameweek_window=f"GW{bb_peak_gw} (Mega Double Gameweek Post-Wildcard)",
            rationale=bb_rat,
        ))

        return chips

    def calculate_dead_cash_drag(self, bank: float) -> float:
        """
        Computes starting XI point drag for unallocated cash in bank > £1.5m.
        Idle capital reduces starting XI quality.
        """
        tolerance = 1.50
        if bank > tolerance:
            return round((bank - tolerance) * 0.25, 2)
        return 0.0

    def determine_lifecycle_phase(self, current_gw: int) -> str:
        """
        Determines the portfolio season lifecycle phase.
        """
        if current_gw <= 12:
            return "CAPITAL_ACCUMULATION"
        elif current_gw <= 28:
            return "MID_SEASON_HARVEST"
        else:
            return "DGW_MONETIZATION"
