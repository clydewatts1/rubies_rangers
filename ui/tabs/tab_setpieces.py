"""
Streamlit Tab: Set-Piece & Penalty Hierarchy
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


def render_tab_setpieces(df: pd.DataFrame):
    st.title("🎯 Premier League Set-Piece & Penalty Hierarchy")
    st.markdown("Track designated **penalty takers**, **direct free-kick specialists**, and **corner deliverers** across all 20 Premier League clubs.")
    
    # 1. Rubies Rangers Set-Piece Summary Card
    client = FPLClient()
    sp_df = client.get_set_piece_hierarchy()
    
    squad_sp = sp_df[sp_df["web_name"].isin(DEFAULT_SQUAD)].copy()
    
    st.subheader("★ Rubies Rangers — Dead-Ball Specialists")
    sp_cols = st.columns(3)
    with sp_cols[0]:
        pens = squad_sp[squad_sp["penalties_order"].isin([1, 2])]
        st.markdown("#### ⚽ Penalty Takers")
        for _, r in pens.iterrows():
            ord_str = "1st Choice" if r["penalties_order"] == 1 else "2nd Choice"
            st.markdown(f"• **{r['web_name']}** ({r['club_name']}) — `{ord_str}`")
    with sp_cols[1]:
        fks = squad_sp[squad_sp["direct_freekicks_order"].isin([1, 2])]
        st.markdown("#### 🎯 Direct Free-Kick Takers")
        for _, r in fks.iterrows():
            ord_str = "1st Choice" if r["direct_freekicks_order"] == 1 else "2nd Choice"
            st.markdown(f"• **{r['web_name']}** ({r['club_name']}) — `{ord_str}`")
    with sp_cols[2]:
        crns = squad_sp[squad_sp["corners_and_indirect_freekicks_order"].isin([1, 2, 3])]
        st.markdown("#### 🚩 Corner Deliverers")
        for _, r in crns.iterrows():
            o = int(r["corners_and_indirect_freekicks_order"])
            ord_str = f"{o}st Choice" if o == 1 else (f"{o}nd Choice" if o == 2 else f"{o}rd Choice")
            st.markdown(f"• **{r['web_name']}** ({r['club_name']}) — `{ord_str}`")
    
    st.markdown("---")
    st.subheader("🔍 Set-Piece Filter & League Explorer")
    
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        duty_filter = st.selectbox("Duty Filter", ["All Set Pieces", "⚽ Primary Penalties (1st Choice)", "⚽ All Penalties", "🎯 Direct Free-Kicks", "🚩 Corners & Indirect FKs"])
    with fc2:
        clubs = ["All Clubs"] + sorted(df["club_name"].dropna().unique().tolist())
        club_filter = st.selectbox("Club Filter", clubs)
    with fc3:
        search_query = st.text_input("Search Player Name", "")
    
    filtered = sp_df.copy()
    if club_filter != "All Clubs":
        filtered = filtered[filtered["club_name"] == club_filter]
    if search_query:
        filtered = filtered[filtered["web_name"].str.contains(search_query, case=False, na=False) |
                            filtered["full_name"].str.contains(search_query, case=False, na=False)]
    
    if duty_filter == "⚽ Primary Penalties (1st Choice)":
        filtered = filtered[filtered["penalties_order"] == 1]
    elif duty_filter == "⚽ All Penalties":
        filtered = filtered[filtered["penalties_order"].notna()]
    elif duty_filter == "🎯 Direct Free-Kicks":
        filtered = filtered[filtered["direct_freekicks_order"].notna()]
    elif duty_filter == "🚩 Corners & Indirect FKs":
        filtered = filtered[filtered["corners_and_indirect_freekicks_order"].notna()]
    
    view_df = filtered[[
        "club_name", "web_name", "position_name", "now_cost", 
        "penalties_order", "direct_freekicks_order", "corners_and_indirect_freekicks_order",
        "set_piece_badges", "setpiece_moneyball_score"
    ]].rename(columns={
        "club_name": "Club",
        "web_name": "Player",
        "position_name": "Pos",
        "now_cost": "Price (£m)",
        "penalties_order": "⚽ Penalty",
        "direct_freekicks_order": "🎯 Direct FK",
        "corners_and_indirect_freekicks_order": "🚩 Corner",
        "set_piece_badges": "Duties Summary",
        "setpiece_moneyball_score": "Set-Piece Score"
    })
    
    st.dataframe(view_df, use_container_width=True)
    
    st.info("""
    **💡 Moneyball Set-Piece Insights:**
    - **Penalties:** Average ~0.79 xG conversion. A primary penalty taker generates a predictable floor of +3 to +6 goals per season without relying on open play.
    - **Corners & Indirect FKs:** Create sustained high-volume xA and trigger regular baseline Bonus Point System (BPS) tallies.
    - **Defenders on Set Pieces:** Players like **Pedro Porro** taking direct FKs and corners offer elite double-digit haul upside.
    """)
    

