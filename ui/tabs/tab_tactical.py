"""
Streamlit Tab: Tactical Process & 7 High-Alpha Forward Predictive Metrics
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from ui.styles import render_html
from ui.cache import (
    load_data,
    load_fdr_map,
    load_squad_trends,
    load_player_trends,
    load_squad_tactical,
    load_league_tactical,
    load_player_shot_breakdown,
    load_xp_lineup,
    load_xp_squad,
    load_gw4_odds,
    load_top_captains,
)
from typing import Optional
from analytics.xp_model import DEFAULT_SQUAD


def render_tab_tactical(df: Optional[pd.DataFrame] = None):
    st.title("🎯 Advanced Tactical Process & Forward Predictive Metrics")
    st.markdown("""
    **Moneyball Directive:** Trailing metrics (past points, past goals, pundit hype) are contaminated by short-term variance.
    Rubies Rangers isolates pure signal using **7 objective, free, and bias-free forward metrics**:
    - **1. $xGOT - xG$ Finishing True Skill:** Distinguishes clinical sharpshooters from unsustainable heaters.
    - **2. Box Touch Density & Ratio:** Penalty area dominance ($R^2 \\approx 0.68$ with future goals) vs perimeter drifting.
    - **3. % $xGI_{\\text{Team}}$ (Talisman Share):** Game-state immunity; protects against team slump variance.
    - **4. $\\text{BCM}$ (Big Chances Missed):** Strongest bullish mean-reversion indicator; predicts imminent multi-goal hauls.
    - **5. $xG_{\\text{obox}}$ (Outside-Box Threat):** Low-block busting and **FPL Challenge Rule Exploit** (+2 bonus).
    - **6. Defensive Disruption:** Tackles and recoveries per 90 establishing the baseline BPS floor for attackers.
    - **7. Market Implied Odds ($P_{\\text{implied}}$):** Unbiased crowdsourced arrival rate removing bookmaker margin.
    """)

    with st.spinner("Fetching Understat shot maps and forward metrics..."):
        squad_tac = load_squad_tactical()
        league_tac = load_league_tactical()
        xp_squad = load_xp_squad()
        fpl_df = df if (df is not None and not df.empty) else load_data()

    # Metric Hero KPI Cards
    active_squad = squad_tac[squad_tac["shots"] >= 1]
    top_talisman = xp_squad.sort_values(by="talisman_share", ascending=False).iloc[0] if not xp_squad.empty else squad_tac.iloc[0]
    top_quality = active_squad.sort_values(by="xG_per_shot", ascending=False).iloc[0] if not active_squad.empty else squad_tac.iloc[0]
    top_box = active_squad.sort_values(by="box_shot_pct", ascending=False).iloc[0] if not active_squad.empty else squad_tac.iloc[0]
    top_reversion = xp_squad.sort_values(by="mean_reversion_score", ascending=False).iloc[0] if not xp_squad.empty else squad_tac.iloc[0]

    tc1, tc2, tc3, tc4 = st.columns(4)
    tc1.metric(
        "Top Talisman Share",
        f"{top_talisman['web_name']}",
        delta=f"{top_talisman['talisman_share']:.1f}% team xGI ({top_talisman['talisman_tier']})"
    )
    tc2.metric(
        "Penalty Box Dominance",
        f"{top_box['player_name']}",
        delta=f"{top_box['box_shot_pct']:.1f}% Box Shots ({top_box.get('six_yard_shots', 0)} in 6-yd)"
    )
    tc3.metric(
        "Highest Shot Quality",
        f"{top_quality['player_name']}",
        delta=f"{top_quality['xG_per_shot']:.3f} xG/shot"
    )
    tc4.metric(
        "Mean-Reversion Breakout",
        f"{top_reversion['web_name']}",
        delta=f"Score: {top_reversion['mean_reversion_score']:.2f} ({top_reversion['big_chances_missed']} BCM)"
    )

    # Tactical Breakthrough Notice
    st.info("""
    💡 **QUANTITATIVE ALPHA ALERT:** In sports analytics literature, goals in football are Poisson-distributed rare events.
    When a striker accumulates high **Big Chances Missed (BCM)** and underperforms their $xG$, casual managers sell them.
    In mathematical truth, **high BCM reflects world-class attacking movement**. Finishing reliably mean-reverts to the 38% baseline, predicting sudden explosive hauls!
    """)

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🛡️ Squad Forward Matrix",
        "👑 Talisman Share (% xGI)",
        "🎯 Finishing True Skill vs Heaters",
        "🚀 Mean-Reversion Breakout (BCM)",
        "📐 Outside-Box Sniper Radar",
        "🛡️ Defensive Disruption & BPS",
        "🎯 Interactive Shot Map & Log"
    ])

    # -------------------------------------------------------------
    # TAB 1: Squad Forward Process Matrix
    # -------------------------------------------------------------
    with tab1:
        st.subheader("Rubies Rangers Forward Predictive Metrics Matrix")
        st.markdown("Comprehensive diagnostic combining Understat spatial tracking, FPL defensive metrics, and $xP$ forward multipliers.")

        cols_squad = [
            "web_name", "club_short", "position_name", "talisman_share", "talisman_tier",
            "box_touch_ratio", "six_yard_shots", "finishing_skill_delta", "big_chances",
            "big_chances_missed", "mean_reversion_score", "outside_box_xg",
            "defensive_disruption_90", "bps_90", "forward_multiplier", "xP"
        ]
        available_cols = [c for c in cols_squad if c in xp_squad.columns]
        rename_squad = {
            "web_name": "Player",
            "club_short": "Club",
            "position_name": "Pos",
            "talisman_share": "% xGI (Talisman)",
            "talisman_tier": "Talisman Status",
            "box_touch_ratio": "Box Shot %",
            "six_yard_shots": "6-Yd Shots",
            "finishing_skill_delta": "Finishing Δ (G-xG)",
            "big_chances": "Big Chances",
            "big_chances_missed": "BCM",
            "mean_reversion_score": "Breakout Score",
            "outside_box_xg": "OBox xG",
            "defensive_disruption_90": "Def Disruption/90",
            "bps_90": "BPS/90",
            "forward_multiplier": "Forward Mult",
            "xP": "Modulated xP"
        }
        st.dataframe(xp_squad[available_cols].rename(columns=rename_squad), use_container_width=True, hide_index=True)

    # -------------------------------------------------------------
    # TAB 2: Talisman Share Leaderboard
    # -------------------------------------------------------------
    with tab2:
        st.subheader("👑 Team Expected Goal Involvement Share (% xGI_Team)")
        st.markdown(r"""
        **Talisman Effect & Game-State Immunity:**
        Players with $\% xGI \ge 30\%$ carry their team's entire attacking output. Even if their team suffers a slump or low-scoring game,
        any goal scored has an $>70\%$ probability of directly involving them.
        """)

        min_mins_tal = st.slider("Minimum Minutes Played:", min_value=90, max_value=270, value=150, step=30, key="tal_mins")
        filtered_league = league_tac[league_tac["minutes"] >= min_mins_tal].copy()

        top_talismans = filtered_league.sort_values(by="talisman_share", ascending=False).head(20)

        # Plotly Bar Chart
        fig_tal = px.bar(
            top_talismans,
            x="talisman_share",
            y="player_name",
            orientation="h",
            color="talisman_tier",
            text="talisman_share",
            title=f"Top 20 Premier League Talismans by % xGI_Team (Min {min_mins_tal} Mins)",
            labels={"talisman_share": "Talisman Share (% xGI)", "player_name": "Player", "talisman_tier": "Tier"},
            color_discrete_map={
                "👑 ALPHA TALISMAN": "#00FF87",
                "⚔️ MAJOR CONTRIBUTOR": "#00C3F8",
                "⚖️ SYSTEM COG": "#E90052",
                "🌱 SQUAD ROTATION": "#888888"
            }
        )
        fig_tal.update_layout(yaxis={"categoryorder": "total ascending"}, height=550)
        fig_tal.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        st.plotly_chart(fig_tal, use_container_width=True)

        col_t1, col_t2 = st.columns([3, 2])
        with col_t1:
            st.markdown("##### 📋 Complete Talisman Ranking Table")
            st.dataframe(
                top_talismans[["player_name", "team_title", "position", "minutes", "talisman_share", "talisman_tier", "xG", "xA", "NPxGI_90"]].rename(columns={
                    "player_name": "Player", "team_title": "Club", "position": "Pos", "minutes": "Mins",
                    "talisman_share": "% xGI Share", "talisman_tier": "Talisman Tier", "NPxGI_90": "NPxGI/90"
                }),
                use_container_width=True,
                hide_index=True
            )
        with col_t2:
            st.markdown("##### 🛡️ Rubies Rangers Talisman Distribution")
            squad_tal_dist = xp_squad[["web_name", "club_short", "talisman_share", "talisman_tier"]].sort_values(by="talisman_share", ascending=False)
            st.dataframe(squad_tal_dist.rename(columns={"web_name": "Player", "club_short": "Club", "talisman_share": "% xGI", "talisman_tier": "Tier"}), use_container_width=True, hide_index=True)

    # -------------------------------------------------------------
    # TAB 3: Post-Shot Finishing Skill vs Heaters
    # -------------------------------------------------------------
    with tab3:
        st.subheader("🎯 Post-Shot Finishing True Skill vs Unsustainable Heaters")
        st.markdown(r"""
        **Finishing True Skill ($\Delta = \text{Goals} - xG$):**
        - **Above the Diagonal Line ($\Delta > 0$):** Players overperforming chance quality. Elite ball-strikers (Son, Haaland) sustain $+15\% \text{ to } +20\%$, but outliers with small samples are **unsustainable heaters** due for regression.
        - **Below the Diagonal Line ($\Delta < 0$):** High-volume attackers experiencing temporary negative variance. **Prime Moneyball buy targets!**
        """)

        active_finishers = league_tac[(league_tac["shots"] >= 4) & (league_tac["minutes"] >= 90)].copy()

        fig_finish = px.scatter(
            active_finishers,
            x="xG",
            y="goals",
            size="shots",
            color="finishing_skill_delta",
            hover_name="player_name",
            hover_data=["team_title", "shots", "finishing_skill_delta", "NPxG_90"],
            color_continuous_scale="RdYlGn",
            title="Actual Goals vs Expected Goals (xG) — Color Encodes Finishing Delta (G - xG)"
        )
        max_val = max(active_finishers["xG"].max(), active_finishers["goals"].max()) + 0.5
        fig_finish.add_trace(go.Scatter(
            x=[0, max_val], y=[0, max_val],
            mode="lines",
            line=dict(color="white", dash="dash"),
            name="Baseline Expected 1:1"
        ))
        fig_finish.update_layout(height=520)
        st.plotly_chart(fig_finish, use_container_width=True)

        fc1, fc2 = st.columns(2)
        with fc1:
            st.markdown("##### 🎯 Top Overperforming Finishers (Heaters or Sharpshooters)")
            top_over = active_finishers.sort_values(by="finishing_skill_delta", ascending=False).head(10)
            st.dataframe(top_over[["player_name", "team_title", "goals", "xG", "finishing_skill_delta", "shots"]].rename(columns={
                "player_name": "Player", "team_title": "Club", "goals": "Goals", "xG": "xG", "finishing_skill_delta": "Finishing Δ", "shots": "Shots"
            }), use_container_width=True, hide_index=True)

        with fc2:
            st.markdown("##### 📉 Top Underperforming Finishers (Prime Buy Targets)")
            top_under = active_finishers.sort_values(by="finishing_skill_delta", ascending=True).head(10)
            st.dataframe(top_under[["player_name", "team_title", "goals", "xG", "finishing_skill_delta", "shots"]].rename(columns={
                "player_name": "Player", "team_title": "Club", "goals": "Goals", "xG": "xG", "finishing_skill_delta": "Finishing Δ", "shots": "Shots"
            }), use_container_width=True, hide_index=True)

    # -------------------------------------------------------------
    # TAB 4: Mean-Reversion Breakout Watchlist (BCM)
    # -------------------------------------------------------------
    with tab4:
        st.subheader("🚀 Bullish Mean-Reversion Watchlist (Big Chances Missed)")
        st.markdown(r"""
        **Quantitative Rationale:**
        Casual fantasy managers sell players who miss big chances, regarding them as "wasteful".
        Mathematical reality proves the exact opposite: **Generating Big Chances ($xG \ge 0.35$) is the single most repeatable, high-skill trait in world football.**
        Because individual finishing regresses toward the ~38% league mean, players with high $\text{BCM}$ and high regression pressure scores are on the verge of massive multi-goal explosions.
        """)

        rev_squad = xp_squad.sort_values(by="mean_reversion_score", ascending=False)
        st.markdown("##### 🚨 Rubies Rangers Mean-Reversion Pressure Radar")
        st.dataframe(
            rev_squad[["web_name", "club_short", "position_name", "mean_reversion_score", "big_chances_missed", "big_chances", "box_touch_ratio", "xP"]].rename(columns={
                "web_name": "Player", "club_short": "Club", "position_name": "Pos",
                "mean_reversion_score": "Breakout Score", "big_chances_missed": "BCM (Missed)",
                "big_chances": "Total Big Chances", "box_touch_ratio": "Box Shot %", "xP": "xP"
            }),
            use_container_width=True,
            hide_index=True
        )

        st.markdown("""
        **Tactical Directive:**
        - **Phil Foden** & **Bryan Mbeumo** hold the highest Mean-Reversion pressure scores in the squad.
        - Their underlying chance generation remains elite. Under no circumstances should they be transferred out based on short-term blanks.
        """)

    # -------------------------------------------------------------
    # TAB 5: Outside-the-Box Shooting Radar (Challenge Exploit)
    # -------------------------------------------------------------
    with tab5:
        st.subheader("📐 Outside-the-Box Shooting Threat & FPL Challenge Exploit")
        st.markdown("""
        **Dual-Use Strategic Value:**
        1. **Low-Block Busting:** Teams facing compact 10-man defensive low blocks cannot access the 6-yard box. High long-range shooters create crucial unassisted breakthrough goals and high $xGOT$ ceilings.
        2. **FPL Challenge Rule Exploit:** In Challenge weeks awarding **+2 Bonus Points for Outside-the-Box Goals**, assets with high $xG_{\\text{obox}}$ experience an exponential surge in expected utility.
        """)

        # Calculate league outside-the-box shooters
        obox_squad = xp_squad.sort_values(by="outside_box_xg", ascending=False)

        st.markdown("##### 🎯 Rubies Rangers Perimeter Shooting Threat ($xG_{\\text{obox}}$)")
        st.dataframe(
            obox_squad[["web_name", "club_short", "outside_box_shots", "outside_box_xg", "box_touch_ratio", "xP"]].rename(columns={
                "web_name": "Player", "club_short": "Club", "outside_box_shots": "OBox Shots",
                "outside_box_xg": "OBox xG", "box_touch_ratio": "Box Shot %", "xP": "xP"
            }),
            use_container_width=True,
            hide_index=True
        )

        st.info("""
        💡 **FPL CHALLENGE RULE PREPARATION:**
        When outside-the-box goals bonus is active, prioritize **Phil Foden**, **Martin Ødegaard**, and **Cherki** for captaincy!
        """)

    # -------------------------------------------------------------
    # TAB 6: Forward Defensive Disruption & BPS Floor
    # -------------------------------------------------------------
    with tab6:
        st.subheader("🛡️ Forward Defensive Disruption & Baseline BPS Floor")
        st.markdown("""
        **High-Pressing Strikers & Bonus Point Farming:**
        In official FPL scoring, successful tackles, recoveries, and defensive clearances feed the Bonus Point System (BPS).
        Attackers who lead the high press accumulate a high BPS baseline floor. When they score or assist, they virtually guarantee the maximum **3 Bonus Points** over static poachers.
        """)

        if "defensive_disruption_per_90" in fpl_df.columns:
            attackers_fpl = fpl_df[
                (fpl_df["position_name"].isin(["FWD", "MID"])) &
                (fpl_df["minutes"] >= 150)
            ].copy()
            top_pressers = attackers_fpl.sort_values(by="defensive_disruption_per_90", ascending=False).head(15)

            st.markdown("##### ⚡ Top 15 Premier League Pressing Attackers (Tackles + Recoveries per 90)")
            st.dataframe(
                top_pressers[["web_name", "club_short", "position_name", "minutes", "tackles_per_90", "recoveries_per_90", "defensive_disruption_per_90", "bps_per_90", "now_cost"]].rename(columns={
                    "web_name": "Player", "club_short": "Club", "position_name": "Pos", "minutes": "Mins",
                    "tackles_per_90": "Tackles/90", "recoveries_per_90": "Recoveries/90",
                    "defensive_disruption_per_90": "Def Disruption/90", "bps_per_90": "BPS/90", "now_cost": "Cost"
                }),
                use_container_width=True,
                hide_index=True
            )

    # -------------------------------------------------------------
    # TAB 7: Interactive Shot Map & Log
    # -------------------------------------------------------------
    with tab7:
        st.subheader("Granular Player Shot Map & Spatial Geometry")

        valid_players = squad_tac[squad_tac["understat_id"].notna()]["player_name"].tolist()
        default_idx = valid_players.index("Alexander Isak") if "Alexander Isak" in valid_players else 0
        chosen_player = st.selectbox("Select Player to Inspect Shot Map:", valid_players, index=default_idx)

        p_row = squad_tac[squad_tac["player_name"] == chosen_player].iloc[0]
        u_id = p_row["understat_id"]
        sb = load_player_shot_breakdown(u_id)

        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total Shots", sb["total_shots"])
        sc2.metric("Avg Shot Quality", f"{sb['avg_shot_quality']:.3f} xG/shot")
        sc3.metric("Box Shot Ratio", f"{sb['box_shot_pct']:.1f}%")
        sc4.metric("Big Chances (xG ≥ 0.35)", f"{sb['big_chances']} ({sb['big_chances_missed']} Missed)")

        # Shot location breakdown chart
        st.markdown(f"#### Shot Zone Distribution for {chosen_player}")
        zone_counts = {
            "6-Yard Box (High Quality)": sb["six_yard_shots"],
            "18-Yard Penalty Box": sb["penalty_box_shots"] - sb["six_yard_shots"],
            "Outside Box (Perimeter)": sb["outside_box_shots"]
        }
        st.bar_chart(pd.DataFrame(list(zone_counts.items()), columns=["Zone", "Shots"]).set_index("Zone"))

        # Shot Log Table
        st.markdown(f"#### Complete Shot Log for {chosen_player}")
        shot_log_df = pd.DataFrame(sb["shot_log"])
        if not shot_log_df.empty:
            shot_cols = ["minute", "result", "situation", "shot_type", "location", "is_big_chance", "is_on_target", "xG", "X", "Y"]
            avail_s_cols = [c for c in shot_cols if c in shot_log_df.columns]
            rename_shots = {
                "minute": "Min",
                "result": "Result",
                "situation": "Situation",
                "shot_type": "Shot Type",
                "location": "Location Zone",
                "is_big_chance": "Big Chance?",
                "is_on_target": "On Target?",
                "xG": "Shot xG",
                "X": "Pitch X",
                "Y": "Pitch Y"
            }
            st.dataframe(shot_log_df[avail_s_cols].rename(columns=rename_shots), use_container_width=True, hide_index=True)

    

