"""
Streamlit Tab: Dynamic Balance Sheet & Real Options Engine (Phase 3).
Visualizes squad balance sheet equity, Free Transfer continuation curve V(FT, t),
American Real Options pricing for strategic chips, and price rise vs. information uncertainty trade-offs.
Governed by .agents/rules/moneyball_strategy.md and .agents/rules/python_standards.md.
"""

from typing import List, Dict, Any, Optional
import streamlit as st
import pandas as pd
import numpy as np

from clients.fpl_client import FPLClient
from analytics.strategic.contracts import (
    FreeTransferOptionProfile,
    PriceRiskProfile,
    ChipRealOptionValuation,
    SquadBalanceSheet,
)
from analytics.strategic.balance_sheet import BalanceSheetEngine
from analytics.strategic.trajectory_engine import build_strategic_squad_state


def render_tab_strategic_balance_sheet(df: pd.DataFrame, current_squad: List[str]) -> None:
    """Renders the Dynamic Balance Sheet & Real Options dashboard tab."""
    st.title("💰 Dynamic Balance Sheet & Real Options Engine")
    st.markdown(
        "**Institutional Portfolio Management**: Quantifies squad equity, Free Transfer continuation optionality ($1 \\le \\text{FT} \\le 5$), "
        "dead cash pitch drag, and American Real Options optimal stopping for chips (Wildcard, Free Hit, Bench Boost, Triple Captain)."
    )

    client = FPLClient()
    squad_state = build_strategic_squad_state(client)

    # 1. Interactive Knobs / Overrides
    st.markdown("---")
    st.subheader("⚙️ Portfolio Balance Sheet Parameters")

    c1, c2, c3 = st.columns(3)
    with c1:
        bank_input = st.number_input(
            "Cash in Bank (£m)",
            min_value=0.0,
            max_value=15.0,
            value=float(squad_state.bank_balance),
            step=0.1,
            key="bs_bank_input",
            help="Current liquid capital in the bank."
        )
    with c2:
        ft_input = st.slider(
            "Free Transfers Available (FT)",
            min_value=1,
            max_value=5,
            value=int(squad_state.free_transfers_available),
            key="bs_ft_slider",
            help="Current Free Transfers in inventory."
        )
    with c3:
        gw_input = st.number_input(
            "Current Gameweek",
            min_value=1,
            max_value=38,
            value=int(squad_state.gameweek),
            step=1,
            key="bs_gw_input",
            help="Current active gameweek."
        )

    # 2. Run Balance Sheet Evaluation
    engine = BalanceSheetEngine(fpl_client=client)
    
    # Resolve squad player IDs
    df_players = client.get_players_df()
    if current_squad:
        name_map = {str(r["web_name"]).lower(): int(r["id"]) for _, r in df_players.iterrows()}
        full_map = {str(r["full_name"]).lower(): int(r["id"]) for _, r in df_players.iterrows()}
        resolved_pids = []
        for item in current_squad:
            if isinstance(item, int):
                resolved_pids.append(item)
            else:
                s = str(item).lower().strip()
                pid = name_map.get(s) or full_map.get(s)
                if pid:
                    resolved_pids.append(pid)
    else:
        resolved_pids = list(squad_state.squad_player_ids)

    balance_sheet: SquadBalanceSheet = engine.evaluate_balance_sheet(
        squad_player_ids=resolved_pids,
        bank=bank_input,
        free_transfers=ft_input,
        current_gw=gw_input,
    )

    # 3. Top KPI Metric Banners
    st.markdown("---")
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric(
            "🏦 Squad Balance Sheet",
            f"£{balance_sheet.team_value:.1f}m",
            f"Selling: £{balance_sheet.selling_value:.1f}m",
            help="Total current market value of squad and realizable cash after 50% profit tax."
        )
    with m2:
        st.metric(
            "💵 Bank Liquidity",
            f"£{balance_sheet.bank_liquidity:.1f}m",
            help="Liquid capital available for immediate transfer upgrades."
        )
    with m3:
        st.metric(
            "🎟️ FT Option Utility",
            f"+{balance_sheet.ft_option_value_xp:.2f} pts",
            f"{balance_sheet.free_transfers_available} FTs Available",
            help="Non-linear continuation utility of holding current Free Transfers."
        )
    with m4:
        drag_badge = f"-{balance_sheet.dead_cash_drag_penalty_xp:.2f} pts" if balance_sheet.dead_cash_drag_penalty_xp > 0 else "0.00 pts (Optimal)"
        st.metric(
            "⚠️ Dead Cash Drag",
            drag_badge,
            help="Point penalty per GW when bank > £1.5m due to idle starting XI capital."
        )
    with m5:
        phase_label = {
            "CAPITAL_ACCUMULATION": "🌱 Value Building (GW 1–12)",
            "MID_SEASON_HARVEST": "🌾 Harvest (GW 13–28)",
            "DGW_MONETIZATION": "💰 DGW Monetization (GW 29–38)",
        }.get(balance_sheet.lifecycle_phase, balance_sheet.lifecycle_phase)
        st.metric(
            "📊 Lifecycle Phase",
            phase_label,
            f"GW{gw_input}",
            help="Portfolio season lifecycle stage."
        )

    # 4. Section 1: American Real Options Strategic Chip Valuation Deck
    st.markdown("---")
    st.subheader("🃏 Real Options Strategic Chip Valuation & Optimal Stopping")
    st.markdown(
        "Chips are treated as **American Options** with discrete exercise opportunities. "
        "The engine compares immediate single-GW lift vs. discounted future Double Gameweek deployment value."
    )

    chip_cols = st.columns(len(balance_sheet.chip_options))
    for col, chip in zip(chip_cols, balance_sheet.chip_options):
        with col:
            with st.container(border=True):
                st.markdown(f"### {chip.chip_display_name}")
                if not chip.is_available:
                    st.badge("⚪ EXPIRED / CONSUMED", type="secondary")
                elif chip.optimal_decision == "EXERCISE_NOW":
                    st.success("🚨 **EXERCISE NOW**")
                else:
                    st.info("🔒 **HOLD OPTION**")

                st.markdown(f"**Immediate Lift:** `{chip.immediate_exercise_lift_xp:.1f} pts`")
                st.markdown(f"**Future Peak Value:** `{chip.continuation_option_value_xp:.1f} pts`")
                st.markdown(f"**Boundary Gap:** `{chip.exercise_boundary_gap:+.1f} pts`")
                st.caption(f"**Target Window:** {chip.target_gameweek_window}")
                st.caption(chip.rationale)

    # 5. Section 2: Free Transfer Continuation Option Valuation
    st.markdown("---")
    st.subheader("🎟️ Free Transfer Inventory Valuation & Pivot Readiness")
    st.markdown(
        "FPL allows banking up to 5 Free Transfers. Holding multiple FTs provides non-linear optionality "
        "to execute **multi-player structural pivots** across price brackets with zero hit deductions."
    )

    ft_prof = engine.evaluate_free_transfer_options(ft_count=ft_input)

    c_ft_left, c_ft_right = st.columns([1, 2])
    with c_ft_left:
        st.markdown(f"**Current Status:** `{ft_prof.current_ft} Free Transfers Available`")
        st.markdown(f"**Continuation Value:** `+{ft_prof.continuation_value_pts:.2f} pts`")
        st.markdown(f"**Pivot Readiness:** `{ft_prof.pivot_readiness_score * 100:.0f}%`")
        st.markdown(f"**Action:** `{ft_prof.recommended_action}`")
        st.info(ft_prof.rationale)

    with c_ft_right:
        st.markdown("**Marginal Valuation Curve by FT Count:**")
        curve_data = []
        cum_val = 0.0
        for k in range(1, 6):
            marg = ft_prof.marginal_option_values[k - 1]
            cum_val += marg
            status_tag = "👉 Active Current FT" if k == ft_input else ("Bankable" if k > ft_input else "Locked")
            curve_data.append({
                "Free Transfers": f"{k} FT",
                "Marginal Points Lift": f"+{marg:.2f} pts",
                "Cumulative Continuation Value": f"+{cum_val:.2f} pts",
                "Structural Pivot Scope": "Single Swap" if k == 1 else (f"{k}-Player Structural Move"),
                "State": status_tag,
            })
        st.dataframe(pd.DataFrame(curve_data), use_container_width=True)

    # 6. Section 3: Price Change vs. Information Uncertainty Risk Matrix
    st.markdown("---")
    st.subheader("📈 Price Rise vs. Information Uncertainty Trade-off")
    st.markdown(
        "Making an early transfer before a price rise locks in $+£0.1\\text{m}$ team value, but incurs an "
        "**Information Risk Penalty** ($\\approx 0.75\\text{ pts}$ expected injury/rotation risk before manager press conferences)."
    )

    risk_rows = []
    for r in balance_sheet.top_price_risks:
        badge = (
            "🟢 LOCK PRICE EARLY" if r.risk_recommendation == "LOCK_PRICE_EARLY"
            else ("🔴 AVOID PRICE DROP" if r.risk_recommendation == "AVOID_PRICE_FALL"
            else "🟡 WAIT FOR PRESS CONFERENCES")
        )
        risk_rows.append({
            "Player": r.web_name,
            "Club": r.club_short,
            "Price": f"£{r.now_cost:.1f}m",
            "Change Probability": f"{r.projected_change_prob * 100:.0f}%",
            "Recommendation": badge,
            "Hurdle Rate Lift": f"+{r.early_transfer_hurdle_rate_xp:.2f} pts",
            "Rationale": r.rationale,
        })

    st.dataframe(pd.DataFrame(risk_rows), use_container_width=True)

    # 7. Section 4: Dead Cash Drag Diagnostic & Squad Equity
    st.markdown("---")
    st.subheader("💡 Portfolio Capital Allocation & Cash Drag Diagnostic")
    if balance_sheet.dead_cash_drag_penalty_xp > 0:
        st.warning(
            f"⚠️ **Excess Idle Cash Detected**: You have £{balance_sheet.bank_liquidity:.1f}m in the bank, "
            f"which exceeds the optimal slack threshold (£1.5m). "
            f"This imposes an estimated pitch opportunity drag of **-{balance_sheet.dead_cash_drag_penalty_xp:.2f} pts/GW**. "
            f"Recommend reinvesting surplus cash into premium starting XI upgrades."
        )
    else:
        st.success(
            f"✅ **Optimal Capital Allocation**: Liquid cash in bank (£{balance_sheet.bank_liquidity:.1f}m) is within "
            f"safe liquidity thresholds (<= £1.5m). 100% of available capital is efficiently working on the pitch."
        )
