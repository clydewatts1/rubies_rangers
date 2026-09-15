"""
Streamlit Tab: Macro Fixture Radar & Wave Scanner (Phase 1).
Provides multi-week regime detection, Green Wave accumulation alerts, Red Cliff liquidation warnings,
combinatorial 190-pair budget defensive rotation, and squad macro audits.
"""

from typing import List, Dict, Any, Optional
import streamlit as st
import pandas as pd
import numpy as np

from clients.fpl_client import FPLClient
from analytics.strategic.wave_scanner import (
    WaveScanner,
    scan_fixture_waves,
    find_optimal_defensive_rotation_pairs,
    audit_squad_waves,
)
from analytics.strategic.trajectory_engine import (
    build_club_schedule_profiles,
    build_strategic_squad_state,
)


def render_tab_strategic_macro(df: pd.DataFrame, current_squad: List[str]) -> None:
    """Renders the Macro Fixture Radar & Wave Scanner dashboard."""
    st.title("🌊 Macro Fixture Radar & Multi-Week Wave Scanner")
    st.markdown(
        "**Multi-Horizon Regime Detection**: Identifies 4–8 gameweek asset accumulation waves, "
        "impending exit cliffs, and combinatorial budget defensive rotation synergies to manage "
        "the squad as a long-term quantitative investment portfolio."
    )

    client = FPLClient()
    current_gw = client.get_current_gameweek() or 1
    next_gw = current_gw + 1

    # Horizon slider
    col_h1, col_h2 = st.columns([2, 2])
    with col_h1:
        horizon = st.slider("Planning Horizon (Future Gameweeks)", min_value=4, max_value=8, value=8, key="macro_horizon_slider")
    with col_h2:
        max_def_cost = st.slider("Max Budget Defender Price (£m)", min_value=4.0, max_value=5.0, value=4.5, step=0.1, key="macro_def_budget_slider")

    scanner = WaveScanner(fpl_client=client, default_horizon=horizon)
    club_profiles = scanner.get_club_profiles()
    wave_alerts = scanner.scan_waves()
    rotation_pairs = scanner.get_rotation_pairs(max_cost=max_def_cost, top_k=5)

    green_waves = [a for a in wave_alerts if a.regime_type == "GREEN_WAVE"]
    red_cliffs = [a for a in wave_alerts if a.regime_type == "RED_CLIFF"]

    # Top Metric Banners
    st.markdown("---")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("🌊 Active Green Waves", f"{len(green_waves)} Clubs", help="Clubs entering 3+ consecutive easy fixtures (FDR <= 2.5)")
    with m2:
        st.metric("⚠️ Red Cliff Warnings", f"{len(red_cliffs)} Clubs", help="Clubs entering 3+ consecutive difficult fixtures (FDR >= 3.4)")
    with m3:
        best_pair = rotation_pairs[0] if rotation_pairs else None
        pair_str = f"{best_pair.club_a_short} + {best_pair.club_b_short}" if best_pair else "N/A"
        home_pct = f"{best_pair.combined_home_ratio * 100:.0f}% Home" if best_pair else "N/A"
        st.metric("🛡️ Top Rotation Pair", pair_str, home_pct)
    with m4:
        st.metric("🎯 Planning Window", f"GW{next_gw} – GW{next_gw + horizon - 1}", f"{horizon} Gameweeks")

    # Section 1: Active Wave Alert Cards
    st.markdown("---")
    st.subheader("⚡ Macro Inflection Radar (Buy Windows & Sell Cliffs)")
    st.caption("Moneyball Rule: Accumulate 1 GW before the wave starts; liquidate 1 GW before the cliff strikes.")

    tab_green, tab_red = st.tabs(["🟢 Green Waves (Asset Accumulation)", "🔴 Red Cliffs (Liquidation & Exit)"])

    with tab_green:
        if green_waves:
            for alert in green_waves:
                with st.expander(f"🌊 **{alert.club_name} ({alert.club_short})** — GW{alert.start_gw} to GW{alert.end_gw} (Avg FDR: {alert.avg_fdr:.2f})", expanded=True):
                    c1, c2, c3 = st.columns([1, 1, 2])
                    with c1:
                        st.markdown(f"**Action:** `{alert.recommended_action}`")
                        st.markdown(f"**Inflection GW:** `GW{alert.inflection_gw}`")
                    with c2:
                        st.markdown(f"**Duration:** `{alert.duration_gws} Matches`")
                        st.markdown(f"**Average Difficulty:** `{alert.avg_fdr:.2f}`")
                    with c3:
                        st.markdown(f"**Target Assets:** {', '.join(alert.key_assets) if alert.key_assets else 'None'}")
                        st.caption(alert.rationale)
        else:
            st.info("No active green waves detected under current threshold (FDR <= 2.50).")

    with tab_red:
        if red_cliffs:
            for alert in red_cliffs:
                with st.expander(f"⚠️ **{alert.club_name} ({alert.club_short})** — GW{alert.start_gw} to GW{alert.end_gw} (Avg FDR: {alert.avg_fdr:.2f})", expanded=True):
                    c1, c2, c3 = st.columns([1, 1, 2])
                    with c1:
                        st.markdown(f"**Action:** `{alert.recommended_action}`")
                        st.markdown(f"**Inflection GW:** `GW{alert.inflection_gw}`")
                    with c2:
                        st.markdown(f"**Duration:** `{alert.duration_gws} Matches`")
                        st.markdown(f"**Average Difficulty:** `{alert.avg_fdr:.2f}`")
                    with c3:
                        st.markdown(f"**Vulnerable Assets:** {', '.join(alert.key_assets) if alert.key_assets else 'None'}")
                        st.caption(alert.rationale)
        else:
            st.info("No severe red cliffs detected under current threshold (FDR >= 3.40).")

    # Section 2: Combinatorial Budget Defensive Rotation Pairs
    st.markdown("---")
    st.subheader(f"🛡️ Combinatorial Budget Defensive Rotation (Top 5 Pairs out of 190 Swept)")
    st.markdown(
        "By alternating two budget £4.0m–£4.5m defenders based on weekly home/away schedule, "
        "you synthetically create a **top-tier £6.0m defender schedule** at minimal combined price."
    )

    for rank, pair in enumerate(rotation_pairs, start=1):
        pair_title = f"#{rank} Pair: **{pair.club_a_short} + {pair.club_b_short}** — {pair.combined_home_ratio * 100:.0f}% Home Matches | {pair.combined_easy_ratio * 100:.0f}% Easy Fixtures (Avg FDR: {pair.combined_avg_fdr:.2f})"
        with st.expander(pair_title, expanded=(rank == 1)):
            c_left, c_right = st.columns([1, 2])
            with c_left:
                st.markdown("**Recommended Budget Assets:**")
                for p_name, cost in pair.budget_sample_defenders:
                    st.markdown(f"• **{p_name}** (£{cost:.1f}m)")
                st.markdown(f"**Combined Home Ratio:** `{pair.combined_home_ratio * 100:.1f}%`")
                st.markdown(f"**Combined Easy Ratio:** `{pair.combined_easy_ratio * 100:.1f}%`")
                st.markdown(f"**Combined Avg FDR:** `{pair.combined_avg_fdr:.2f}`")

            with c_right:
                st.markdown("**Optimal Weekly Rotation Path:**")
                sched_rows = []
                for gw, club, opp, is_h, fdr in pair.combined_schedule:
                    venue_str = "🏠 Home" if is_h else "✈️ Away"
                    fdr_badge = f"🟢 FDR {fdr:.0f}" if fdr <= 2.5 else (f"🟡 FDR {fdr:.0f}" if fdr <= 3.5 else f"🔴 FDR {fdr:.0f}")
                    sched_rows.append({
                        "Gameweek": f"GW{gw}",
                        "Start Club": club,
                        "Opponent": opp,
                        "Venue": venue_str,
                        "Difficulty": fdr_badge,
                    })
                st.dataframe(pd.DataFrame(sched_rows), use_container_width=True)

    # Section 3: Active Squad Macro Audit
    st.markdown("---")
    st.subheader("📋 Rubies Rangers Squad Macro Fixture Audit")
    st.caption("Evaluates each player in your active squad against upcoming wave inflections to prioritize sell/hold decisions.")

    squad_audits = scanner.audit_squad()
    audit_rows = []
    for aud in squad_audits:
        regime_badge = "🟢 GREEN WAVE" if aud.current_regime == "GREEN_WAVE" else ("🔴 RED CLIFF" if aud.current_regime == "RED_CLIFF" else "⚪ STABLE")
        priority_badge = (
            "🚨 URGENT SELL" if aud.action_priority == "URGENT_SELL"
            else ("⚠️ WATCH EXIT" if aud.action_priority == "WATCH_EXIT"
            else "💎 HOLD & HARVEST")
        )
        audit_rows.append({
            "Player": aud.web_name,
            "Club": aud.club_short,
            "Position": aud.position_name,
            "Cost (£m)": f"£{aud.now_cost:.1f}m",
            "Regime": regime_badge,
            "Regime Timeline": aud.alert_label,
            "Action Priority": priority_badge,
            "Next 5 Avg FDR": aud.next_5_fdr,
        })

    st.dataframe(pd.DataFrame(audit_rows), use_container_width=True)

    # Section 4: Full 20-Club Interactive Heatmap
    st.markdown("---")
    st.subheader(f"📅 Full 20-Club Multi-Horizon Schedule Grid (GW{next_gw} – GW{next_gw + horizon - 1})")

    grid_rows = []
    target_gws = [next_gw + i for i in range(horizon)]

    for c_short, prof in sorted(club_profiles.items(), key=lambda x: sum(x[1].fdr_vector[:horizon]) / horizon):
        avg_fdr = sum(prof.fdr_vector[:horizon]) / horizon
        r = {
            "Club": f"{prof.club_name} ({c_short})",
            "Avg FDR": round(avg_fdr, 2),
        }
        for i, gw in enumerate(target_gws):
            if i < len(prof.fdr_vector):
                opp = prof.opponents[i]
                is_h = "H" if prof.is_home[i] else "A"
                fdr = int(prof.fdr_vector[i])
                r[f"GW{gw}"] = f"{opp} ({is_h}, {fdr})"
        grid_rows.append(r)

    st.dataframe(pd.DataFrame(grid_rows), use_container_width=True)
