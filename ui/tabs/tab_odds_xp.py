"""
Streamlit Tab: Bookmaker Odds & Expected Points (xP)
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


def render_tab_odds_xp():
    st.title("🎰 Bookmaker Implied Probabilities & Expected Points (xP)")
    st.markdown("""
    **Moneyball Sharp Intelligence:** Betting markets pool millions of pounds of predictive modeling.
    - **Implied Clean Sheet Probability $P(CS)$:** Poisson distribution derived from opponent expected goals ($e^{-\\lambda_{\\text{conceded}}}$).
    - **Anytime Goalscorer Probability $P(\\text{Goal})$:** Derived from player Non-Penalty $xG/90$ and team attack expectation.
    - **Linear Expected Points ($xP$):** Formal scoring model integrating appearance probability ($p_{60}$), goal/assist point returns, clean sheets, and expected bonus points ($xBonus$).
    - **Optimal Starting Lineup & Captaincy:** Evaluates all legal formations (3-5-2, 3-4-3, 4-4-2, etc.) to maximize total Gameweek 4 return.
    """)
    
    with st.spinner("Computing bookmaker odds and optimizing Starting XI..."):
        lineup_data = load_xp_lineup()
        odds_df = load_gw4_odds()
        captains_df = load_top_captains(15)
        squad_xp_df = load_xp_squad()
    
    # Hero KPI Summary Cards
    cap = lineup_data["captain"]
    vc = lineup_data["vice_captain"]
    
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Optimal Formation", lineup_data["formation"], delta="Max Return Formation")
    kpi2.metric("Starting XI Base xP", f"{lineup_data['base_starting_xp']:.2f}", delta="11 Starters")
    kpi3.metric("Effective Squad xP (with C)", f"{lineup_data['effective_total_xp']:.2f}", delta=f"+{cap['xP']:.2f} Captain Boost")
    kpi4.metric("Designated Captain", f"{cap['web_name']}", delta=f"{cap['xP']:.2f} xP (2x = {cap['xP']*2:.2f})")
    
    st.markdown("### 🏟️ Gameweek 4 Starting XI Tactical Pitch")
    
    # Render pitch with starters grouped by position
    starters = lineup_data["starting_xi"]
    fwds = starters[starters["position_name"] == "FWD"]
    mids = starters[starters["position_name"] == "MID"]
    defs = starters[starters["position_name"] == "DEF"]
    gkps = starters[starters["position_name"] == "GKP"]
    
    def _render_card(r, is_cap=False, is_vc=False):
        badge_html = ""
        if is_cap:
            badge_html = '<div class="captain-badge">★ CAPTAIN (C)</div><br/>'
        elif is_vc:
            badge_html = '<div class="vc-badge">☆ VICE-CAPTAIN (VC)</div><br/>'
        
        pos_str = r['position_name']
        prob_html = ""
        if pos_str in ["GKP", "DEF"]:
            prob_html = f"<small style='color: #6ee7b7;'>CS: <b>{r['cs_prob']:.1f}%</b></small>"
        else:
            prob_html = f"<small style='color: #f87171;'>Goal: <b>{r['p_goal']:.0f}%</b></small> | <small style='color: #38bdf8;'>Ast: <b>{r['p_assist']:.0f}%</b></small>"
    
        return f"""
        <div class="player-card">
            {badge_html}
            <b style="font-size: 15px; color: #f8fafc;">{r['web_name']}</b><br/>
            <small style="color: #94a3b8;">{r['club_short']} | {r['fixture']}</small><br/>
            {prob_html}<br/>
            <div class="xp-pill">{r['xP']:.2f} xP</div>
        </div>
        """
    
    # HTML Pitch rendering
    pitch_html = '<div class="pitch-container">'
    
    # FWD Row
    pitch_html += '<div class="pitch-row">'
    for _, r in fwds.iterrows():
        is_cap = (r["id"] == cap["id"])
        is_vc = (r["id"] == vc["id"])
        pitch_html += _render_card(r, is_cap, is_vc)
    pitch_html += '</div>'
    
    # MID Row
    pitch_html += '<div class="pitch-row">'
    for _, r in mids.iterrows():
        is_cap = (r["id"] == cap["id"])
        is_vc = (r["id"] == vc["id"])
        pitch_html += _render_card(r, is_cap, is_vc)
    pitch_html += '</div>'
    
    # DEF Row
    pitch_html += '<div class="pitch-row">'
    for _, r in defs.iterrows():
        pitch_html += _render_card(r)
    pitch_html += '</div>'
    
    # GKP Row
    pitch_html += '<div class="pitch-row">'
    for _, r in gkps.iterrows():
        pitch_html += _render_card(r)
    pitch_html += '</div>'
    
    pitch_html += '</div>'
    render_html(pitch_html)
    
    # Bench Row
    st.markdown("#### 🪑 Priority Substitutes (Bench Order)")
    bench_cols = st.columns(4)
    for idx, (_, b_row) in enumerate(lineup_data["bench"].iterrows()):
        with bench_cols[idx]:
            sub_title = f"Sub {idx+1}" if b_row["position_name"] != "GKP" else "GKP Sub"
            reason = "Anfield away (low CS)" if b_row["web_name"] == "Robinson" else (
                "Cameo rotation risk" if b_row["web_name"] == "Solanke" else (
                    "Benched past 2 matches" if b_row["web_name"] == "Senesi" else "Backup keeper vs Arsenal"
                )
            )
            render_html(f"""
            <div class="bench-card">
                <small style="color: #cbd5e1; font-weight: bold;">{sub_title}</small><br/>
                <b style="color: white; font-size: 14px;">{b_row['web_name']}</b> <small>({b_row['position_name']})</small><br/>
                <small style="color: #94a3b8;">{b_row['club_short']} vs {b_row['fixture']}</small><br/>
                <small style="color: #fca5a5;">{reason}</small><br/>
                <div class="xp-pill" style="font-size: 11px; padding: 1px 6px;">{b_row['xP']:.2f} xP</div>
            </div>
            """)
    
    st.markdown("---")
    
    # Sub-tabs
    t1, t2, t3 = st.tabs([
        "📊 Full Squad Expected Points Breakdown",
        "👑 Captaincy Duel & Premier League Rankings",
        "🎲 GW4 Betting Market Implied Goals & Clean Sheet Odds"
    ])
    
    with t1:
        st.subheader("Rubies Rangers 15-Player Expected Points ($xP$) Matrix")
        st.markdown("Detailed breakdown of expected minutes, match $xG$, clean sheet odds, anytime goal odds, and projected $xP$.")
        display_squad_cols = [
            "position_name", "web_name", "club_short", "now_cost", "fixture",
            "exp_mins", "mins_status", "match_xg", "match_xa", "cs_prob", "p_goal", "goal_odds", "p_assist", "x_bonus", "xP"
        ]
        renames_squad = {
            "position_name": "Pos", "web_name": "Player", "club_short": "Club", "now_cost": "Cost (£m)", "fixture": "GW4 Fixture",
            "exp_mins": "Exp Mins", "mins_status": "Minutes Status", "match_xg": "Match xG", "match_xa": "Match xA",
            "cs_prob": "CS Prob %", "p_goal": "Goal %", "goal_odds": "Goal Odds", "p_assist": "Assist %", "x_bonus": "xBonus", "xP": "Total xP"
        }
        st.dataframe(squad_xp_df[display_squad_cols].rename(columns=renames_squad), use_container_width=True, hide_index=True)
    
    with t2:
        st.subheader("👑 Gameweek 4 Captaincy Decision Engine")
        
        # Side-by-side Captaincy Duel
        duel_col1, duel_col2 = st.columns(2)
        with duel_col1:
            render_html(f"""
            <div style="background: rgba(239, 68, 68, 0.15); border: 2px solid #ef4444; border-radius: 12px; padding: 16px; text-align: center;">
                <span class="captain-badge">PRIMARY CAPTAIN (C)</span>
                <h2 style="color: white; margin: 4px 0;">{cap['web_name']}</h2>
                <p style="color: #cbd5e1; margin-bottom: 8px;">{cap['club_short']} | {cap['fixture']}</p>
                <div style="display: flex; justify-content: space-around; margin-top: 12px;">
                    <div><small style="color: #94a3b8;">Projected xP</small><br/><b style="font-size: 18px; color: #4ade80;">{cap['xP']:.2f}</b></div>
                    <div><small style="color: #94a3b8;">Double Points (2x)</small><br/><b style="font-size: 18px; color: #ef4444;">{cap['xP']*2:.2f}</b></div>
                    <div><small style="color: #94a3b8;">P(Goal)</small><br/><b style="font-size: 18px; color: #f59e0b;">{cap['p_goal']:.1f}%</b></div>
                    <div><small style="color: #94a3b8;">Goal Odds</small><br/><b style="font-size: 18px; color: #38bdf8;">{cap['goal_odds']:.2f}</b></div>
                </div>
            </div>
            """)
    
        with duel_col2:
            render_html(f"""
            <div style="background: rgba(59, 130, 246, 0.15); border: 2px solid #3b82f6; border-radius: 12px; padding: 16px; text-align: center;">
                <span class="vc-badge">VICE-CAPTAIN (VC)</span>
                <h2 style="color: white; margin: 4px 0;">{vc['web_name']}</h2>
                <p style="color: #cbd5e1; margin-bottom: 8px;">{vc['club_short']} | {vc['fixture']}</p>
                <div style="display: flex; justify-content: space-around; margin-top: 12px;">
                    <div><small style="color: #94a3b8;">Projected xP</small><br/><b style="font-size: 18px; color: #4ade80;">{vc['xP']:.2f}</b></div>
                    <div><small style="color: #94a3b8;">Double Points (2x)</small><br/><b style="font-size: 18px; color: #3b82f6;">{vc['xP']*2:.2f}</b></div>
                    <div><small style="color: #94a3b8;">P(Goal)</small><br/><b style="font-size: 18px; color: #f59e0b;">{vc['p_goal']:.1f}%</b></div>
                    <div><small style="color: #94a3b8;">Goal Odds</small><br/><b style="font-size: 18px; color: #38bdf8;">{vc['goal_odds']:.2f}</b></div>
                </div>
            </div>
            """)
    
        st.markdown("#### 🏆 Premier League Top 15 Captaincy Candidates")
        st.dataframe(captains_df, use_container_width=True, hide_index=True)
    
    with t3:
        st.subheader("🎲 Gameweek 4 Premier League Match Odds & Clean Sheet Probabilities")
        st.markdown("Consensus bookmaker market implied goal totals and Poisson clean sheet probabilities for all 20 clubs.")
        st.dataframe(odds_df[["Club", "GW4 Fixture", "Team xG", "Opponent xG (xGC)", "Clean Sheet Prob", "Clean Sheet Odds"]], use_container_width=True, hide_index=True)
    

