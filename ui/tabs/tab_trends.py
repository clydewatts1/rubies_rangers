"""
Streamlit Tab: Match-by-Match Trend Engine
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
    load_league_standings,
    load_team_leagues,
    load_team_picks,
    load_league_ownership,
    load_league_history,
    load_montecarlo_simulation,
    load_montecarlo_lineup,
)
from analytics.xp_model import DEFAULT_SQUAD
from trackers.price import PriceTracker
from trackers.league import LeagueTracker, DEFAULT_LEAGUE_ID


def render_tab_trends(df: pd.DataFrame, current_squad):
    st.title("📈 Granular Match-by-Match Trend Analysis & Minutes Security")
    st.markdown("""
    **Moneyball Philosophy:** Aggregated seasonal stats disguise recent role shifts, minutes collapse, and rotation risks.
    Querying `/api/element-summary/{player_id}/` provides rolling 3-GW $xGI$, rotation risk categorization, and granular defensive work rate.
    """)
    
    with st.spinner("Fetching granular match data for squad..."):
        squad_trends = load_squad_trends()
    
    # Metric KPI Cards
    benched_count = len(squad_trends[squad_trends["minutes_status"] == "BENCHED_OR_DROPPED"])
    rotation_count = len(squad_trends[squad_trends["minutes_status"] == "ROTATION_RISK"])
    secure_count = len(squad_trends[squad_trends["minutes_status"] == "SECURE_STARTER"])
    regular_count = len(squad_trends[squad_trends["minutes_status"] == "REGULAR_STARTER"])
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Benched / Dropped", f"{benched_count} players", delta=f"-{benched_count} Alert", delta_color="inverse")
    c2.metric("Rotation Risk / Cameos", f"{rotation_count} players", delta="Caution" if rotation_count > 0 else "None", delta_color="off")
    c3.metric("Secure 90m Starters", f"{secure_count} players", delta="Solid Floor")
    c4.metric("Regular Starters", f"{regular_count} players")
    
    # High-Priority Tactical Alerts
    benched_names = squad_trends[squad_trends["minutes_status"] == "BENCHED_OR_DROPPED"]
    if not benched_names.empty:
        alert_text = " • ".join([f"**{r['web_name']}** ({r['recent_minutes_str']} mins)" for _, r in benched_names.iterrows()])
        st.error(f"🚨 **CRITICAL MINUTES ALERT (Benched / Out of Favor):** {alert_text} — Immediate transfer out recommended!")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "🛡️ Squad Minutes Security Matrix",
        "🔍 Granular Player Match Log",
        "⚡ Attacking Momentum ($xGI$)",
        "🧱 Defensive Workhorse Floor"
    ])
    
    with tab1:
        st.subheader("Squad Minutes Security & Rotation Risk Audit")
        show_risks_only = st.checkbox("Show Only Rotation / Bench Risks", value=False)
        
        display_df = squad_trends.copy()
        if show_risks_only:
            display_df = display_df[display_df["minutes_status"].isin(["BENCHED_OR_DROPPED", "ROTATION_RISK"])]
    
        cols_view = [
            "position_name", "web_name", "club_short", "now_cost",
            "recent_minutes_str", "recent_starts", "status_badge",
            "avg_recent_xgi", "season_xgi_per_match", "xgi_trend_label",
            "avg_recent_def_contrib", "avg_recent_pts"
        ]
        rename_dict = {
            "position_name": "Pos",
            "web_name": "Player",
            "club_short": "Club",
            "now_cost": "Cost (£m)",
            "recent_minutes_str": "Last 3 GW Mins",
            "recent_starts": "Starts",
            "status_badge": "Minutes Security",
            "avg_recent_xgi": "Roll xGI (3GW)",
            "season_xgi_per_match": "Season xGI/m",
            "xgi_trend_label": "Attacking Trend",
            "avg_recent_def_contrib": "Def Actions/m",
            "avg_recent_pts": "Pts/m"
        }
        st.dataframe(display_df[cols_view].rename(columns=rename_dict), use_container_width=True, hide_index=True)
    
    with tab2:
        st.subheader("Granular Player Deep-Dive & Match Timeline")
        
        player_choices = list(squad_trends["web_name"].unique())
        default_idx = player_choices.index("Solanke") if "Solanke" in player_choices else 0
        selected_player_name = st.selectbox("Select Player from Rubies Rangers:", player_choices, index=default_idx)
        
        chosen_row = squad_trends[squad_trends["web_name"] == selected_player_name].iloc[0]
        p_id = int(chosen_row["id"])
        
        p_tr = load_player_trends(p_id)
        
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Minutes Security", p_tr["status_badge"])
        p2.metric("Rolling 3GW xGI", f"{p_tr['avg_recent_xgi']:.2f}", delta=f"{p_tr['xgi_trend_delta']:+.2f} vs Season")
        p3.metric("Defensive Actions/m", f"{p_tr['avg_recent_def_contrib']:.1f}")
        p4.metric("Recent Points/m", f"{p_tr['avg_recent_pts']:.1f}")
    
        st.markdown(f"#### Match Log for {chosen_row['web_name']} ({chosen_row['club_name']})")
        log_df = pd.DataFrame(p_tr["match_log"])
        if not log_df.empty:
            log_cols = [
                "round", "fixture", "score", "minutes", "starts",
                "expected_goals", "expected_assists", "expected_goal_involvements",
                "tackles", "cbi", "recoveries", "defensive_contribution",
                "bps", "total_points"
            ]
            log_renames = {
                "round": "GW",
                "fixture": "Match",
                "score": "Score",
                "minutes": "Mins",
                "starts": "Start",
                "expected_goals": "xG",
                "expected_assists": "xA",
                "expected_goal_involvements": "xGI",
                "tackles": "Tackles",
                "cbi": "CBI",
                "recoveries": "Recov",
                "defensive_contribution": "Def Contrib",
                "bps": "BPS",
                "total_points": "Pts"
            }
            st.dataframe(log_df[log_cols].rename(columns=log_renames), use_container_width=True, hide_index=True)
    
            ch_col1, ch_col2 = st.columns(2)
            with ch_col1:
                st.markdown("**Minutes & Points Timeline**")
                chart_data = log_df.set_index("round")[["minutes", "total_points"]]
                st.bar_chart(chart_data)
    
            with ch_col2:
                st.markdown("**Expected Goal Involvements (xGI) vs Defensive Actions**")
                metric_chart = log_df.set_index("round")[["expected_goal_involvements", "defensive_contribution"]]
                st.line_chart(metric_chart)
    
    with tab3:
        st.subheader("Attacking Form Momentum: Rolling 3-GW xGI vs Season Baseline")
        st.markdown("Identifies players undergoing tactical role elevation or surging attacking involvement.")
        
        attackers_mids = squad_trends[squad_trends["position_name"].isin(["MID", "FWD"])].copy()
        if not attackers_mids.empty:
            xgi_comp = attackers_mids.set_index("web_name")[["avg_recent_xgi", "season_xgi_per_match"]].rename(columns={
                "avg_recent_xgi": "Rolling 3-GW xGI/m",
                "season_xgi_per_match": "Season xGI/m Baseline"
            })
            st.bar_chart(xgi_comp)
    
    with tab4:
        st.subheader("Defensive Floor & Workhorse Ranks (CBI, Tackles, Recoveries)")
        st.markdown("Defenders with high underlying defensive actions accumulate regular baseline BPS and provide an elite floor even when clean sheets are conceded.")
        
        defenders = squad_trends[squad_trends["position_name"] == "DEF"].copy()
        if not defenders.empty:
            def_comp = defenders.set_index("web_name")[["avg_recent_cbi", "avg_recent_tackles", "avg_recent_recoveries"]].rename(columns={
                "avg_recent_cbi": "Clearances/Blocks/Interceptions",
                "avg_recent_tackles": "Tackles Won",
                "avg_recent_recoveries": "Ball Recoveries"
            })
            st.bar_chart(def_comp)
    

