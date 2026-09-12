"""
Streamlit Tab: Tactical Process & Shot Quality
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


def render_tab_tactical():
    st.title("🎯 Advanced Tactical Process Metrics (Understat / Shot Quality)")
    st.markdown("""
    **Moneyball Philosophy:** Goals and raw $xG$ can be distorted by penalty kicks (~0.79 xG each) and low-probability speculative efforts.
    - **NPxG (Non-Penalty Expected Goals):** Strips away penalties to evaluate genuine open-play threat.
    - **Shot Quality ($xG$ per Shot):** Differentiates clinical box poachers from wasteful 30-yard shooters.
    - **Box Dominance:** Pitch coordinates ($X, Y$) measure 18-yard and 6-yard box shot conversion.
    """)
    
    with st.spinner("Fetching Understat tactical process data..."):
        squad_tac = load_squad_tactical()
        league_tac = load_league_tactical()
    
    # Metric KPI Cards
    active_squad = squad_tac[squad_tac["shots"] >= 1]
    top_quality = active_squad.sort_values(by="xG_per_shot", ascending=False).iloc[0] if not active_squad.empty else squad_tac.iloc[0]
    top_threat = squad_tac[squad_tac["minutes"] >= 90].sort_values(by="NPxGI_90", ascending=False).iloc[0] if not squad_tac.empty else squad_tac.iloc[0]
    total_npxg = squad_tac["NPxG"].sum()
    box_attackers = len(squad_tac[(squad_tac["shots"] >= 3) & (squad_tac["box_shot_pct"] >= 75)])
    
    tc1, tc2, tc3, tc4 = st.columns(4)
    tc1.metric("Highest Shot Quality", f"{top_quality['player_name']}", delta=f"{top_quality['xG_per_shot']:.3f} xG/shot")
    tc2.metric("Top Open-Play Threat", f"{top_threat['player_name']}", delta=f"{top_threat['NPxGI_90']:.2f} NPxGI/90")
    tc3.metric("Total Squad NPxG", f"{total_npxg:.2f}", delta="Excludes Penalties")
    tc4.metric("Clinical Box Attackers", f"{box_attackers} players", delta="≥75% Box Shots")
    
    # Major Tactical Breakthrough Banner
    st.info("""
    💡 **MONEYBALL DISCOVERY:** Rubies Rangers holds **6 of the top 7 players in the entire Premier League** for open-play threat ($NPxGI_{90}$):
    **Phil Foden** (1.29), **Alexander Isak** (0.92), **João Pedro** (0.90), **Bryan Mbeumo** (0.89), **Morgan Rogers** (0.89), and **Martin Ødegaard** (0.88).
    *Tactical Directive:* Even though Foden was substituted early in GW3 (24 mins), his underlying open-play process is the best in England. Do not sell!
    """)
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "🛡️ Squad Process Matrix",
        "🎯 Interactive Shot Map & Log",
        "📊 Shot Quality vs Volume Chart",
        "🏆 Premier League Process Leaderboard"
    ])
    
    with tab1:
        st.subheader("Rubies Rangers Tactical Process Matrix")
        st.markdown("Detailed breakdown of open-play threat, non-penalty xG, shot quality, and box presence.")
    
        cols_squad = [
            "player_name", "team_title", "shots", "goals", "NPxG", "NPxG_90",
            "xG_per_shot", "box_shot_pct", "six_yard_shots", "NPxGI_90", "tactical_archetype"
        ]
        rename_squad = {
            "player_name": "Player",
            "team_title": "Club",
            "shots": "Shots",
            "goals": "Goals",
            "NPxG": "NPxG",
            "NPxG_90": "NPxG/90",
            "xG_per_shot": "xG/Shot (Quality)",
            "box_shot_pct": "Box Shot %",
            "six_yard_shots": "6-Yd Shots",
            "NPxGI_90": "Open Threat (NPxGI/90)",
            "tactical_archetype": "Tactical Archetype"
        }
        st.dataframe(squad_tac[cols_squad].rename(columns=rename_squad), use_container_width=True, hide_index=True)
    
    with tab2:
        st.subheader("Granular Player Shot Map & Location Breakdown")
        
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
        sc4.metric("6-Yard Box Poacher Shots", sb["six_yard_shots"])
    
        # Shot location breakdown chart
        st.markdown(f"#### Shot Zone Distribution for {chosen_player}")
        zone_counts = {
            "6-Yard Box (High Quality)": sb["six_yard_shots"],
            "18-Yard Penalty Box": sb["penalty_box_shots"] - sb["six_yard_shots"],
            "Outside Box (Low Quality)": sb["outside_box_shots"]
        }
        st.bar_chart(pd.DataFrame(list(zone_counts.items()), columns=["Zone", "Shots"]).set_index("Zone"))
    
        # Shot Log Table
        st.markdown(f"#### Complete Shot Log for {chosen_player}")
        shot_log_df = pd.DataFrame(sb["shot_log"])
        if not shot_log_df.empty:
            shot_cols = ["minute", "result", "situation", "shot_type", "location", "X", "Y", "xG"]
            shot_renames = {
                "minute": "Min",
                "result": "Result",
                "situation": "Situation",
                "shot_type": "Shot Type",
                "location": "Location Zone",
                "X": "Pitch X",
                "Y": "Pitch Y",
                "xG": "Shot xG"
            }
            st.dataframe(shot_log_df[shot_cols].rename(columns=shot_renames), use_container_width=True, hide_index=True)
    
    with tab3:
        st.subheader("Shot Quality vs Shot Volume")
        st.markdown("Visualizing high-efficiency box poachers (top right) versus wasteful perimeter shooters.")
    
        active_attackers = squad_tac[squad_tac["shots"] >= 1].copy()
        if not active_attackers.empty:
            chart_df = active_attackers.set_index("player_name")[["xG_per_shot", "NPxG_90"]].rename(columns={
                "xG_per_shot": "Shot Quality (xG/Shot)",
                "NPxG_90": "NPxG per 90"
            })
            st.bar_chart(chart_df)
    
    with tab4:
        st.subheader("Premier League Advanced Tactical Process Leaderboard")
        
        pl_col1, pl_col2 = st.columns(2)
        with pl_col1:
            st.markdown("##### 🎯 Top 15 Attackers by Shot Quality (Min 6 Shots)")
            top_qual = league_tac[league_tac["shots"] >= 6].sort_values(by="xG_per_shot", ascending=False).head(15)
            st.dataframe(top_qual[["player_name", "team_title", "shots", "goals", "xG_per_shot", "NPxG_90"]].rename(columns={
                "player_name": "Player", "team_title": "Club", "shots": "Shots", "goals": "Goals", "xG_per_shot": "xG/Shot", "NPxG_90": "NPxG/90"
            }), use_container_width=True, hide_index=True)
    
        with pl_col2:
            st.markdown("##### 👑 Top 15 Players by Open-Play Threat (Min 180 Mins)")
            top_threat_pl = league_tac[league_tac["minutes"] >= 180].sort_values(by="NPxGI_90", ascending=False).head(15)
            st.dataframe(top_threat_pl[["player_name", "team_title", "minutes", "NPxG_90", "xA_90", "NPxGI_90"]].rename(columns={
                "player_name": "Player", "team_title": "Club", "minutes": "Mins", "NPxG_90": "NPxG/90", "xA_90": "xA/90", "NPxGI_90": "NPxGI/90"
            }), use_container_width=True, hide_index=True)
    

