"""
Streamlit Tab: Squad Audit & Transfer Optimizer (MILP)
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
from analytics.optimizer import FPLOptimizer

def render_tab_transfers(df: pd.DataFrame, opt, current_squad, bank_balance: float = 3.7, num_transfers: int = 1, objective: str = 'fdr_moneyball'):
    st.title("🛡️ Squad Audit & Transfer Optimizer")
    
    bank_balance = st.sidebar.slider("Bank Balance (£m)", 0.0, 15.0, 3.7, 0.1)
    num_transfers = st.sidebar.slider("Number of Transfers", 1, 4, 1)
    
    # Match current squad
    matched = []
    for name in DEFAULT_SQUAD:
        m = df[df["web_name"].str.lower() == name.lower()]
        if m.empty:
            m = df[df["full_name"].str.lower() == name.lower()]
        if m.empty:
            m = df[df["web_name"].str.contains(name, case=False, na=False)]
        if m.empty:
            m = df[df["full_name"].str.contains(name, case=False, na=False)]
        if not m.empty:
            matched.append(m.iloc[0].to_dict())
    
    squad_df = pd.DataFrame(matched)
    squad_val = squad_df["now_cost"].sum()
    total_pts = squad_df["total_points"].sum()
    
    # Price alerts for squad
    squad_rises = squad_df[squad_df["price_status"].str.contains("RISE TONIGHT", na=False)]
    squad_falls = squad_df[squad_df["price_status"].str.contains("FALL TONIGHT", na=False)]
    
    if not squad_rises.empty or not squad_falls.empty:
        r_names = ", ".join(squad_rises["web_name"].tolist())
        f_names = ", ".join(squad_falls["web_name"].tolist())
        st.info(f"""
        **📈 Live Market Movement Alerts for Rubies Rangers:**
        - **Value Appreciation (Rising Tonight +£0.1m):** {r_names or 'None'}
        - **Value Deprecation (Falling Tonight -£0.1m):** {f_names or 'None'}
        """)
    
    # Top KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Squad Value", f"£{squad_val:.1f}m")
    c2.metric("In The Bank", f"£{bank_balance:.1f}m")
    c3.metric("Total Points", f"{int(total_pts)}")
    c4.metric("Active Players", f"{len(squad_df)}/15")
    
    st.subheader("Current Squad")
    cols = st.columns(4)
    for idx, pos in enumerate(["GKP", "DEF", "MID", "FWD"]):
        with cols[idx]:
            st.markdown(f"### {pos}")
            pos_df = squad_df[squad_df["position_name"] == pos]
            for _, p in pos_df.iterrows():
                is_unavail = p.get("status", "a") != "a"
                border_color = "#ef4444" if is_unavail else "#3b82f6"
                status_icon = "🔴" if is_unavail else "🟢"
                
                fdr_5 = float(p.get("fdr_next_5", 3.0))
                fdr_badge_class = "badge-fdr-easy" if fdr_5 <= 2.7 else ("badge-fdr-med" if fdr_5 <= 3.1 else "badge-fdr-hard")
                next_match = p.get("next_fixture", "N/A")
    
                p_status = p.get("price_status", "Stable")
                price_badge = ""
                if "RISE TONIGHT" in p_status:
                    price_badge = '<span class="badge-rise">▲ RISE TONIGHT</span>'
                elif "FALL TONIGHT" in p_status:
                    price_badge = '<span class="badge-fall">▼ FALL TONIGHT</span>'
    
                sp_badge = ""
                sp_text = p.get("set_piece_badges")
                if sp_text and sp_text != "None":
                    sp_badge = f'<br/><small style="color: #38bdf8;">🎯 {sp_text}</small>'
    
                render_html(f"""
                <div class="squad-player-card" style="border: 1px solid {border_color}; background: #1e293b; color: #ffffff; padding: 12px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.35);">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                        <span style="color: #ffffff; font-size: 15px; font-weight: 700;">{status_icon} {p['web_name']}</span>
                        {price_badge}
                    </div>
                    <div style="color: #94a3b8; font-size: 12px; margin-bottom: 4px;">({p['club_name']})</div>
                    <div style="color: #cbd5e1; font-size: 12px; line-height: 1.4;">
                        Price: <b style="color: #ffffff;">£{p['now_cost']:.1f}m</b> | Pts: <b style="color: #ffffff;">{int(p['total_points'])}</b> | Form: <b style="color: #ffffff;">{float(p.get('form', 0)):.1f}</b>
                    </div>
                    <div style="color: #cbd5e1; font-size: 12px; margin-top: 2px;">
                        Next: <b style="color: #ffffff;">{next_match}</b> | 5GW FDR: <span class="{fdr_badge_class}">{fdr_5:.2f}</span>
                    </div>
                    <div style="color: #34d399; font-weight: 600; font-size: 12px; margin-top: 4px;">
                        FDR Score: {float(p.get('fdr_moneyball_score', p.get('moneyball_score', 0))):.2f}
                    </div>{sp_badge}
                </div>
                """)
    
    st.markdown("---")
    st.subheader(f"💡 Recommended {num_transfers} Transfer(s) ({objective.upper()})")
    
    if st.button("🚀 Calculate Optimal Transfers", type="primary"):
        with st.spinner("Solving integer program..."):
            res = opt.optimize_transfers(
                current_player_names=DEFAULT_SQUAD,
                bank_balance=bank_balance,
                max_transfers=num_transfers,
                objective=objective
            )
    
        if res["success"]:
            tc1, tc2 = st.columns(2)
            with tc1:
                st.markdown("#### 🔻 Players OUT (Sell)")
                for _, r in res["transfers_out"].iterrows():
                    reason = r.get("news") if r.get("status") != "a" else "Low fixture efficiency"
                    render_html(f"""
                    <div class="squad-player-card" style="background: #3b1d1d; border-left: 4px solid #ef4444; color: #ffffff; padding: 12px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.35);">
                        <b style="color: #ffffff; font-size: 15px; font-weight: 700;">{r['web_name']}</b> <span style="color: #cbd5e1; font-size: 12px;">({r['position_name']} - {r['club_name']})</span><br/>
                        <span style="color: #cbd5e1; font-size: 12px;">Price: <b style="color: #ffffff;">£{r['now_cost']:.1f}m</b> | Points: <b style="color: #ffffff;">{int(r['total_points'])}</b> | Form: <b style="color: #ffffff;">{float(r.get('form', 0)):.1f}</b></span><br/>
                        <span style="color: #cbd5e1; font-size: 12px;">Next Match: <b style="color: #ffffff;">{r.get('next_fixture', 'N/A')}</b></span><br/>
                        <span style="color: #fca5a5; font-size: 12px; font-weight: 600;">Reason: {reason}</span>
                    </div>
                    """)
    
            with tc2:
                st.markdown("#### 🔺 Players IN (Buy)")
                for _, r in res["transfers_in"].iterrows():
                    fdr_val = float(r.get("fdr_next_5", 3.0))
                    fdr_cls = "badge-fdr-easy" if fdr_val <= 2.8 else ("badge-fdr-med" if fdr_val <= 3.2 else "badge-fdr-hard")
                    p_stat = r.get("price_status", "Stable")
                    render_html(f"""
                    <div class="squad-player-card" style="background: #064e3b; border-left: 4px solid #10b981; color: #ffffff; padding: 12px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.35);">
                        <b style="color: #ffffff; font-size: 15px; font-weight: 700;">{r['web_name']}</b> <span style="color: #cbd5e1; font-size: 12px;">({r['position_name']} - {r['club_name']})</span><br/>
                        <span style="color: #cbd5e1; font-size: 12px;">Price: <b style="color: #ffffff;">£{r['now_cost']:.1f}m</b> | Points: <b style="color: #ffffff;">{int(r['total_points'])}</b> | Form: <b style="color: #ffffff;">{float(r.get('form', 0)):.1f}</b></span><br/>
                        <span style="color: #cbd5e1; font-size: 12px;">Next Match: <b style="color: #ffffff;">{r.get('next_fixture', 'N/A')}</b> | 5GW FDR: <span class="{fdr_cls}">{fdr_val:.2f}</span></span><br/>
                        <span style="color: #6ee7b7; font-size: 12px; font-weight: 600;">FDR Score: {float(r.get('fdr_moneyball_score', r.get('moneyball_score', 0))):.2f}</span> | Price Alert: <b style="color: #ffffff;">{p_stat}</b>
                    </div>
                    """)
    
            st.success(f"""
            **Transfer Impact:**
            - Total Points Delta: **+{res['points_gain']} pts**
            - Score Delta: **+{res['score_gain']:.2f}**
            - New Bank Balance: **£{res['new_bank']:.1f}m**
            - New Squad Cost: **£{res['total_team_cost']:.1f}m**
            """)
        else:
            st.error(res.get("message"))
    

