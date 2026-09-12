"""
Streamlit Tab: Market Velocity & Price Predictor
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


def render_tab_market(df: pd.DataFrame, current_squad):
    st.title("📈 FPL Market Velocity & Price Change Predictor")
    st.markdown("Tracks live transfer momentum to forecast nightly **£0.1m price rises and falls** before the FPL price algorithm triggers (nightly 01:30–02:30 UTC).")
    
    tracker = PriceTracker()
    report = tracker.get_squad_price_report(DEFAULT_SQUAD)
    
    st.subheader("🚨 Rubies Rangers — Squad Momentum & Value Impact")
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Net Transfer Momentum", f"{report['total_net_transfers']:+,d}")
    sc2.metric("Projected Squad Delta", f"{report['projected_value_delta']:+.1f}m", delta=f"{report['projected_value_delta']:+.1f}m")
    sc3.metric("Risers Tonight", f"{len(report['rises_tonight'])} players")
    sc4.metric("Fallers Tonight", f"{len(report['falls_tonight'])} players")
    
    # Display Squad Price Table
    st.markdown("#### Squad Price Movement Watchlist")
    squad_view = report["squad_df"][["position_name", "web_name", "club_name", "now_cost", "net_transfers", "progress_pct", "transfers_needed", "pred_status"]].rename(columns={
        "position_name": "Pos",
        "web_name": "Player",
        "club_name": "Club",
        "now_cost": "Price (£m)",
        "net_transfers": "Net Transfers",
        "progress_pct": "Progress %",
        "transfers_needed": "Transfers Needed",
        "pred_status": "Forecast"
    })
    st.dataframe(squad_view, use_container_width=True)
    
    st.markdown("---")
    st.subheader("🌐 Premier League Market Movers")
    rises = tracker.get_top_risers(limit=15)
    falls = tracker.get_top_fallers(limit=15)
    
    mc1, mc2 = st.columns(2)
    with mc1:
        st.success("### 🟢 Top Projected Price Rises Tonight (+£0.1m)")
        st.caption("Buy before tonight's 01:30 UTC deadline to avoid paying +£0.1m more!")
        r_view = rises[["web_name", "club_name", "position_name", "now_cost", "net_transfers", "progress_pct", "pred_status"]].rename(columns={
            "web_name": "Player", "club_name": "Club", "position_name": "Pos", "now_cost": "Price (£m)", "net_transfers": "Net Transfers", "progress_pct": "Progress %", "pred_status": "Status"
        })
        st.dataframe(r_view, use_container_width=True)
    
    with mc2:
        st.error("### 🔴 Top Projected Price Drops Tonight (-£0.1m)")
        st.caption("Sell before tonight's 01:30 UTC deadline to protect your team value from losing -£0.1m!")
        f_view = falls[["web_name", "club_name", "position_name", "now_cost", "net_transfers", "progress_pct", "pred_status"]].rename(columns={
            "web_name": "Player", "club_name": "Club", "position_name": "Pos", "now_cost": "Price (£m)", "net_transfers": "Net Transfers", "progress_pct": "Progress %", "pred_status": "Status"
        })
        st.dataframe(f_view, use_container_width=True)
    
    st.info("""
    **💡 Moneyball Transfer Timing Protocol:**
    - **Buying an Asset:** Execute your transfer **before 01:30 UTC** on the night a player rises to lock in the lower price.
    - **Selling an Underperformer:** Sell **before 01:30 UTC** on the night they drop to preserve your bank capital and team value.
    - **Profit Realization:** In FPL, you receive £0.1m selling value for every £0.2m a player rises while in your squad.
    """)
    

