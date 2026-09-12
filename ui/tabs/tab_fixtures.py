"""
Streamlit Tab: Fixture Difficulty (FDR) Ticker
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
from clients.fpl_client import FPLClient


def render_tab_fixtures(df: pd.DataFrame, current_squad):
    st.title("📅 Premier League Fixture Difficulty & Swing Ticker")
    st.markdown("Analyze rolling schedule difficulty and detect **critical fixture swings** (teams transitioning from tough games into easy runs, or heading into red walls).")
    
    st.info("🏟️ **Live Matchday Hub**: To track real-time Premier League match scores and active squad performance for the current active gameweek, select **'🏟️ Matchday Center & Live Gameweek Scores'** in the sidebar workflow menu.")

    client = FPLClient()
    current_gw = client.get_current_gameweek() or 1
    
    horizon = st.sidebar.slider("Rolling Schedule Horizon (Gameweeks)", 3, 6, 5, key="fixtures_horizon")
    fdr_data = load_fdr_map(n_gameweeks=horizon)
    swings = client.get_fixture_swings(n_gameweeks=horizon)
    next_gws = list(range(current_gw + 1, current_gw + horizon + 1))
    
    # 1. Fixture Swing Detector Cards
    st.subheader("⚡ Fixture Swing Detector (Moneyball Inflection Windows)")
    st.caption("Positive swing = schedule gets significantly easier (Buy Window) | Negative swing = brutal schedule approaching (Sell Alert)")
    
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        st.success("#### 🟢 Top Positive Swings (Buy Targets)")
        st.caption("Tough now, but green run begins in 1-2 gameweeks!")
        for t in swings["positive_swings"][:4]:
            st.markdown(f"• **{t['team_name']}** (`+{t['swing_delta']:.2f} ▲`)<br/><small>Near: {t['near_fdr']:.2f} ➔ Later: **{t['later_fdr']:.2f}**</small>", unsafe_allow_html=True)
    
    with sc2:
        st.error("#### 🔴 Top Negative Swings (Sell Alerts)")
        st.caption("Easy now, but red wall approaching soon!")
        for t in swings["negative_swings"][:4]:
            st.markdown(f"• **{t['team_name']}** (`{t['swing_delta']:.2f} ▼`)<br/><small>Near: {t['near_fdr']:.2f} ➔ Later: **{t['later_fdr']:.2f}**</small>", unsafe_allow_html=True)
    
    with sc3:
        st.info("#### ★ Rubies Rangers Squad Alerts")
        st.markdown("""
        • **Robin Roefs (Sunderland, `+2.25 ▲`)**: Faces Arsenal & Chelsea next, then gets the league's easiest green run from GW6!
        • **Antonee Robinson (Fulham, `+1.50 ▲`)**: Prime clean sheet territory unlocks in GW6.
        • **João Pedro & Morgan Rogers (Chelsea, `-0.75 ▼`)**: Enjoy GW4-5 before City/Liverpool tests.
        """)
    
    st.markdown("---")
    st.subheader(f"Full 20-Team Schedule Grid (GW{next_gws[0]} – GW{next_gws[-1]})")
    
    sorted_clubs = sorted(fdr_data.values(), key=lambda x: x["avg_fdr"])
    rows = []
    for c in sorted_clubs:
        delta = c.get("swing_delta", 0.0)
        swing_display = f"+{delta:.2f} ▲" if delta > 0 else (f"{delta:.2f} ▼" if delta < 0 else "0.00")
        r = {
            "Club": c["team_name"],
            "Avg FDR": c["avg_fdr"],
            "Swing Delta": swing_display,
            "Swing Status": c.get("swing_label", "STABLE"),
            "Multiplier": c["fdr_multiplier"]
        }
        for f in c["fixtures"]:
            gw_col = f"GW{f['gw']}"
            r[gw_col] = f"{f['opp_short']} ({'H' if f['is_home'] else 'A'}, FDR {f['difficulty']})"
        rows.append(r)
    
    fdr_grid_df = pd.DataFrame(rows)
    st.dataframe(fdr_grid_df, use_container_width=True)
    
    st.info("""
    **💡 Moneyball Schedule Strategy:**
    - **Accumulation Zone:** Buy players from clubs with high positive swings **1 week before** their green run starts while their price and ownership are suppressed.
    - **Profit-Taking Zone:** Sell players from clubs with negative swings **before** their red run starts, locking in team value profits.
    """)
    

