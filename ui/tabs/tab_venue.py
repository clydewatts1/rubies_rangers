"""
Venue Impact & Home/Away Analysis Tab
Displays positional asymmetry, club tier dampening, fixture venue schedules,
and active squad venue audits.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Optional, List
from config_manager import get_params
from analytics.venue_model import get_club_tier


def render_tab_venue(df: pd.DataFrame, current_squad: Optional[List[str]] = None):
    st.header("🏟️ Venue Impact & Home/Away Analysis")
    st.markdown(
        "Analyze the asymmetric impact of Home vs. Away fixtures across different positions and clubs "
        "derived from empirical Premier League distributions and calibrated via Optuna."
    )

    venue_cfg = get_params("venue") or {}
    is_enabled = venue_cfg.get("enabled", True)

    if not is_enabled:
        st.warning("⚠️ **Venue Impact Modeling is currently DISABLED.** All multipliers are operating in identity mode (1.00x). Enable it via the sidebar toggle.")

    # 1. Metric Header Cards
    st.subheader("Current Venue Model Calibration")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🛡️ DEF Home Boost", f"{venue_cfg.get('def_home_mult', 1.18)}x", delta="+18% Floor")
    with col2:
        st.metric("⚔️ ATT Home Boost", f"{venue_cfg.get('att_home_mult', 1.08)}x", delta="+8% Shots")
    with col3:
        st.metric("🧤 GKP Away Save Hedge", f"{venue_cfg.get('gkp_away_save_boost', 1.20)}x", delta="+20% Saves")
    with col4:
        st.metric("🚗 Outfield Away Factor", f"{venue_cfg.get('away_mult', 0.92)}x", delta="-8% Road")

    st.divider()

    # 2. Positional Asymmetry Grouped Bar Chart
    st.subheader("📊 Positional Home/Away Asymmetry")
    gkp_away = round(venue_cfg.get("away_mult", 0.92) * venue_cfg.get("gkp_away_save_boost", 1.20), 3)
    data = {
        "Position": ["DEF", "DEF", "MID", "MID", "FWD", "FWD", "GKP", "GKP"],
        "Venue": ["Home", "Away", "Home", "Away", "Home", "Away", "Home", "Away"],
        "Multiplier": [
            venue_cfg.get("def_home_mult", 1.18),
            venue_cfg.get("away_mult", 0.92),
            venue_cfg.get("att_home_mult", 1.08),
            venue_cfg.get("away_mult", 0.92),
            venue_cfg.get("att_home_mult", 1.08),
            venue_cfg.get("away_mult", 0.92),
            venue_cfg.get("gkp_home_mult", 1.08),
            gkp_away
        ]
    }
    df_asym = pd.DataFrame(data)
    fig1 = px.bar(
        df_asym,
        x="Position",
        y="Multiplier",
        color="Venue",
        barmode="group",
        title="Base Positional Venue Multipliers",
        color_discrete_map={"Home": "#2CA02C", "Away": "#D62728"}
    )
    fig1.add_hline(y=1.0, line_dash="dash", line_color="white", annotation_text="Baseline (1.0x)")
    st.plotly_chart(fig1, use_container_width=True)

    st.divider()

    # 3. Club Tier Dampening Metrics
    st.subheader("🏰 Club Strength Tier Dampening (β)")
    tier_damping = venue_cfg.get("tier_damping", {})
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        st.metric("👑 Elite Tier (β)", f"{tier_damping.get('elite', 0.70)}")
        st.caption("Top 4 clubs (MCI, ARS, LIV, CHE). Venue swing is muted; quality overrides road conditions.")
    with col_t2:
        st.metric("⚖️ Mid-Table Tier (β)", f"{tier_damping.get('mid_table', 1.30)}")
        st.caption("Positions 5–14. Amplified fortress advantage; severe away vulnerability.")
    with col_t3:
        st.metric("📉 Relegation Tier (β)", f"{tier_damping.get('relegation', 1.15)}")
        st.caption("Positions 15–20. High concession risk on the road; counter-cyclical save targets.")

    st.divider()

    # 4. Rubies Rangers Active Squad Venue Audit
    if current_squad and not df.empty:
        st.subheader("👥 Rubies Rangers Active Squad Venue Audit")
        squad_df = df[df["web_name"].isin(current_squad)].copy()
        if not squad_df.empty:
            squad_df["club_tier"] = squad_df["club_short"].apply(get_club_tier)
            squad_df["is_home"] = squad_df["next_fixture"].astype(str).str.contains(r"\(H\)", case=False)
            squad_df["venue_label"] = squad_df["is_home"].apply(lambda h: "🏠 HOME" if h else "✈️ AWAY")

            audit_cols = [
                "web_name", "position_name", "club_short", "club_tier", "next_fixture",
                "venue_label", "venue_multiplier", "moneyball_score", "fdr_moneyball_score"
            ]
            display_cols = [c for c in audit_cols if c in squad_df.columns]
            
            home_count = squad_df["is_home"].sum()
            away_count = len(squad_df) - home_count
            st.caption(f"Active Gameweek Split: **{home_count} Home Fixtures** / **{away_count} Away Fixtures**")

            st.dataframe(
                squad_df[display_cols].sort_values(by="fdr_moneyball_score", ascending=False),
                use_container_width=True,
                hide_index=True
            )

    st.divider()

    # 5. Top Beneficiaries & Traps
    if not df.empty and "venue_multiplier" in df.columns:
        col_ben, col_trap = st.columns(2)
        with col_ben:
            st.subheader("🌟 Top Home Fortress Beneficiaries")
            home_boosted = df[df["venue_multiplier"] > 1.0].sort_values(by="venue_multiplier", ascending=False).head(10)
            show_cols = ["web_name", "club_short", "position_name", "next_fixture", "venue_multiplier", "fdr_moneyball_score"]
            st.dataframe(home_boosted[[c for c in show_cols if c in home_boosted.columns]], use_container_width=True, hide_index=True)

        with col_trap:
            st.subheader("⚠️ Away Trap Warning (High Cost Road Assets)")
            away_dampened = df[(df["venue_multiplier"] < 1.0) & (df["now_cost"] >= 6.5)].sort_values(by="venue_multiplier", ascending=True).head(10)
            show_cols = ["web_name", "club_short", "position_name", "next_fixture", "venue_multiplier", "now_cost", "fdr_moneyball_score"]
            st.dataframe(away_dampened[[c for c in show_cols if c in away_dampened.columns]], use_container_width=True, hide_index=True)

    st.divider()

    # 6. Macro Match-State Jitter & Match Tempo Physics
    st.subheader("⚡ Macro Match-State Jitter & Match Tempo Physics")
    mc_cfg = get_params("monte_carlo") or {}
    macro_cfg = mc_cfg.get("macro_jitter", {})
    macro_on = macro_cfg.get("enabled", True)
    pace_vol = macro_cfg.get("pace_volatility", 0.15)

    with st.expander("🔬 Macro Atmospheric Jitter & Fixture Covariance Settings", expanded=False):
        st.markdown(r"""
        Traditional models assume each player's points are independent draws from uncoupled distributions.
        Rubies Rangers models **Macro Match States**:
        - **Atmospheric Match Pace ($\theta_{m, k}$)**: Each match $m$ in simulation trial $k$ samples an overarching tempo factor:
          $$\theta_{m, k} \sim \text{LogNormal}\left(-\frac{\sigma^2}{2}, \sigma\right), \quad \mathbb{E}[\theta] = 1.0$$
        - **Discrete Poisson Goals Conceded**: Opponent goals $G_{\text{conceded}} \sim \text{Poisson}(\lambda_{\text{concede}} \cdot \theta_{m,k})$. Teammates on the pitch for $M$ minutes sample integer goals via $\text{Binomial}(G_{\text{conceded}}, M/90.0)$, strictly synchronizing clean sheet bonuses ($G_{\text{on\_pitch}} = 0 \land M \ge 60$) and integer penalties ($-\lfloor G_{\text{on\_pitch}} / 2 \rfloor$).
        - **Adversarial Negative Covariance**: Attackers scoring against an opponent directly erode the opposing goalkeeper's clean sheet odds in the identical stochastic trial.
        """)
        mcol1, mcol2, mcol3 = st.columns(3)
        with mcol1:
            st.metric("Macro Jitter Engine", "Active" if macro_on else "Disabled", delta="Coupled Physics" if macro_on else "Uncoupled")
        with mcol2:
            st.metric("Pace Volatility (σ)", f"{pace_vol:.2f}", delta="Log-Normal")
        with mcol3:
            st.metric("Pace Range Clip", f"[{macro_cfg.get('clip_pace_min', 0.5):.2f}x, {macro_cfg.get('clip_pace_max', 2.0):.2f}x]")
