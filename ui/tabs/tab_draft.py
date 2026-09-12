"""
Streamlit Tab: Draft New Optimal Squad & Player Explorer
"""

import streamlit as st
import pandas as pd
import numpy as np

from ui.styles import render_html
from analytics.optimizer import FPLOptimizer

def render_tab_draft(df: pd.DataFrame, opt: FPLOptimizer, objective: str = "fdr_moneyball"):
    st.title("🏆 Mathematical 15-Man Squad Draft")
    budget = st.sidebar.slider("Total Squad Budget (£m)", 90.0, 110.0, 100.0, 0.5, key="draft_budget")
    lock_player = st.sidebar.text_input("Lock Player (Optional, e.g. Haaland)", key="draft_lock_player")
    
    if st.button("⚡ Solve Optimal Squad", type="primary"):
        locks = [lock_player] if lock_player else None
        with st.spinner("Finding optimal team..."):
            res = opt.optimize_squad(budget=budget, objective=objective, lock_players=locks)
    
        if res["success"]:
            st.success(f"Optimal Squad Found! Total Cost: £{res['total_cost']:.1f}m | Remaining Bank: £{res['bank_remaining']:.1f}m | Total Points: {res['total_points']}")
            squad = res["squad"]
            
            p_cols = st.columns(4)
            for idx, pos in enumerate(["GKP", "DEF", "MID", "FWD"]):
                with p_cols[idx]:
                    st.markdown(f"### {pos}")
                    sub = squad[squad["position_name"] == pos]
                    for _, r in sub.iterrows():
                        fdr_val = float(r.get("fdr_next_5", 3.0))
                        fdr_cls = "badge-fdr-easy" if fdr_val <= 2.8 else ("badge-fdr-med" if fdr_val <= 3.2 else "badge-fdr-hard")
                        sp_b = r.get("set_piece_badges", "None")
                        sp_html = f'<br/><small style="color: #38bdf8;">🎯 {sp_b}</small>' if sp_b != "None" else ""
                        render_html(f"""
                        <div class="squad-player-card" style="background: #1e293b; border-left: 4px solid #8b5cf6; color: #ffffff; padding: 12px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.35);">
                            <b style="color: #ffffff; font-size: 15px; font-weight: 700;">{r['web_name']}</b> <span style="color: #cbd5e1; font-size: 12px;">({r['club_name']})</span><br/>
                            <span style="color: #cbd5e1; font-size: 12px;">Price: <b style="color: #ffffff;">£{r['now_cost']:.1f}m</b> | Pts: <b style="color: #ffffff;">{int(r['total_points'])}</b> | Form: <b style="color: #ffffff;">{float(r.get('form', 0)):.1f}</b></span><br/>
                            <span style="color: #cbd5e1; font-size: 12px;">Next: <b style="color: #ffffff;">{r.get('next_fixture', 'N/A')}</b> | FDR: <span class="{fdr_cls}">{fdr_val:.2f}</span></span><br/>
                            <span style="color: #a78bfa; font-size: 12px; font-weight: 600;">Score: {float(r.get('setpiece_moneyball_score', r.get('fdr_moneyball_score', r.get('moneyball_score', 0)))):.2f}</span>{sp_html}
                        </div>
                        """)
        else:
            st.error(res.get("message"))
    


def render_tab_explorer(df: pd.DataFrame):
    st.title("🔍 Player Explorer & Moneyball Table")
    pos_filter = st.multiselect("Position", ["GKP", "DEF", "MID", "FWD"], default=["FWD", "MID"])
    max_price = st.slider("Max Price (£m)", 4.0, 16.0, 15.5, 0.5)
    filter_set_pieces = st.checkbox("Only Set-Piece & Penalty Specialists", value=False)
    
    sub_df = df[(df["position_name"].isin(pos_filter)) & (df["now_cost"] <= max_price) & (df["status"] == "a")].copy()
    if filter_set_pieces and "is_any_set_piece" in sub_df.columns:
        sub_df = sub_df[sub_df["is_any_set_piece"]]
    sub_df = sub_df.sort_values(by="fdr_moneyball_efficiency", ascending=False)
    
    cols_to_display = ["web_name", "club_name", "position_name", "now_cost", "total_points", "form", "next_fixture", "fdr_next_5", "price_status", "set_piece_badges", "moneyball_score", "setpiece_moneyball_score"]
    st.dataframe(sub_df[[c for c in cols_to_display if c in sub_df.columns]], use_container_width=True)

