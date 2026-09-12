"""
Rubies Rangers FPL Operations Research & Analytics Platform
Slim entry router dispatching to modular presentation tabs in `ui/tabs/`.
Run locally with: streamlit run app.py
"""

import streamlit as st
import pandas as pd

from ui.styles import inject_custom_css
from ui.cache import load_data
from analytics.optimizer import FPLOptimizer
from analytics.xp_model import DEFAULT_SQUAD
from trackers.league import LeagueTracker
from config_manager import get_system_config, get_active_profile, set_active_profile, get_config
from ui.tabs import (
    render_tab_two_stage,
    render_tab_domain_intel,
    render_tab_transfers,
    render_tab_montecarlo_lineup,
    render_tab_montecarlo_transfers,
    render_tab_leagues,
    render_tab_odds_xp,
    render_tab_tactical,
    render_tab_trends,
    render_tab_market,
    render_tab_fixtures,
    render_tab_setpieces,
    render_tab_draft,
    render_tab_explorer,
    render_tab_venue,
    render_tab_matchday,
)

# 1. Page Configuration
st.set_page_config(
    page_title="Rubies Rangers — FPL Moneyball Optimizer",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Inject Theme CSS & Design Tokens
inject_custom_css()

# 3. Sidebar Brand & Profile Selection
st.sidebar.title("⚽ Rubies Rangers")
st.sidebar.markdown("**Strategy:** Quantitative Moneyball")

active_prof = get_active_profile()
prof_choice = st.sidebar.selectbox("Active Calibration Profile", ["tuned", "heuristic"], index=0 if active_prof == "tuned" else 1)
if prof_choice != active_prof:
    set_active_profile(prof_choice)
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
cfg = get_config()
is_venue_active = cfg.get(active_prof, {}).get("venue", {}).get("enabled", True)
venue_enabled = st.sidebar.toggle("🏟️ Enable Venue Impact", value=is_venue_active, key="venue_enabled_toggle")
if is_venue_active != venue_enabled:
    cfg[active_prof]["venue"]["enabled"] = venue_enabled
    st.cache_data.clear()
    st.rerun()

data_source = st.sidebar.radio("Data Source", ["Live FPL API", "Historical CSV"])
if st.sidebar.button("🔄 Force Refresh Live Data"):
    st.cache_data.clear()
    load_data("Live FPL API", force_refresh=True)
    st.sidebar.success("Live data refreshed!")
    st.rerun()

df = load_data(data_source)
opt = FPLOptimizer(df)

# 4. Active Squad Management
if "active_squad" not in st.session_state:
    st.session_state["active_squad"] = list(DEFAULT_SQUAD)

current_squad = st.session_state["active_squad"]

with st.sidebar.expander("👥 Active Squad & Live FPL Sync", expanded=False):
    st.markdown(f"**Current Squad ({len(current_squad)}/15 Players):**")
    st.caption(", ".join(current_squad))
    
    if st.button("📥 Sync from Published FPL Picks (Entry 6173410)"):
        try:
            lt = LeagueTracker()
            picks_data = lt.get_team_picks(6173410)
            s_names = [p["web_name"] for p in picks_data.get("starters", [])]
            b_names = [p["web_name"] for p in picks_data.get("bench", [])]
            if len(s_names) + len(b_names) == 15:
                st.session_state["active_squad"] = s_names + b_names
                st.cache_data.clear()
                st.success("Synced 15 players from FPL Entry 6173410!")
                st.rerun()
            else:
                st.warning("Could not retrieve all 15 picks from FPL API.")
        except Exception as e:
            st.error(f"Sync failed: {e}")

    st.markdown("---")
    st.markdown("**🔄 Swap a Player:**")
    swap_out = st.selectbox("Sell Player", current_squad, key="sidebar_swap_out")
    all_player_names = sorted(df["web_name"].dropna().unique().tolist())
    swap_in = st.selectbox("Buy Player", all_player_names, index=all_player_names.index("João Pedro") if "João Pedro" in all_player_names else 0, key="sidebar_swap_in")
    if st.button("Apply Swap to Active Squad"):
        if swap_out in st.session_state["active_squad"]:
            s_idx = st.session_state["active_squad"].index(swap_out)
            st.session_state["active_squad"][s_idx] = swap_in
            st.cache_data.clear()
            st.success(f"Swapped {swap_out} ➔ {swap_in}!")
            st.rerun()

    if st.button("Reset to Default Rubies Rangers"):
        st.session_state["active_squad"] = list(DEFAULT_SQUAD)
        st.cache_data.clear()
        st.rerun()

# 5. Workflow Dispatcher
mode = st.sidebar.selectbox("Workflow", [
    "🏟️ Matchday Center & Live Gameweek Scores",
    "⚔️ Two-Stage Tournament (Screen & Simulate)",
    "🧠 Shane's Domain Intel Desk",
    "Modify Current Team (Transfers)",
    "🏆 Mini-League Scout & Rival Spy",
    "🛡️ Monte Carlo Lineup & Substitution Strategist",
    "🎰 Bookmaker Odds & Expected Points (xP)",
    "🎲 Monte Carlo Transfer Simulator",
    "Tactical Process & Shot Quality",
    "Match-by-Match Trend Engine",
    "Market Velocity & Price Predictor",
    "Fixture Difficulty (FDR) Ticker",
    "Set-Piece & Penalty Hierarchy",
    "🏟️ Venue Impact & Home/Away Analysis",
    "Draft New Optimal Squad",
    "Player Explorer"
])

# Shared knobs
bank_balance = float(get_system_config("default_bank") or 3.7)

# Dispatch to modular tab renderers
if mode == "🏟️ Matchday Center & Live Gameweek Scores":
    render_tab_matchday(df, current_squad)
elif mode == "⚔️ Two-Stage Tournament (Screen & Simulate)":
    render_tab_two_stage(df, current_squad, bank=bank_balance)
elif mode == "🧠 Shane's Domain Intel Desk":
    render_tab_domain_intel(df, current_squad)
elif mode == "Modify Current Team (Transfers)":
    num_transfers = st.sidebar.slider("Number of Transfers", 1, 4, 1, key="mod_transfers_count")
    objective = st.sidebar.selectbox("Optimization Metric", ["fdr_moneyball", "setpiece_moneyball", "moneyball", "points", "form"], format_func=lambda x: {
        "fdr_moneyball": "Fixture-Adjusted Moneyball (xGI & FDR)",
        "setpiece_moneyball": "Set-Piece & Dead-Ball Moneyball (xG/xA Boost)",
        "moneyball": "Base Moneyball Score (xGI / Expected Return)",
        "points": "Total Points",
        "form": "Current Form"
    }[x], key="mod_transfers_obj")
    bank_slider = st.sidebar.slider("Bank Balance (£m)", 0.0, 15.0, bank_balance, 0.1, key="mod_transfers_bank")
    render_tab_transfers(df, opt, current_squad, bank_balance=bank_slider, num_transfers=num_transfers, objective=objective)
elif mode == "🏆 Mini-League Scout & Rival Spy":
    render_tab_leagues(df)
elif mode == "🛡️ Monte Carlo Lineup & Substitution Strategist":
    render_tab_montecarlo_lineup(df, current_squad)
elif mode == "🎰 Bookmaker Odds & Expected Points (xP)":
    render_tab_odds_xp()
elif mode == "🎲 Monte Carlo Transfer Simulator":
    render_tab_montecarlo_transfers(df, current_squad, bank_balance=bank_balance)
elif mode == "Tactical Process & Shot Quality":
    render_tab_tactical()
elif mode == "Match-by-Match Trend Engine":
    render_tab_trends(df, current_squad)
elif mode == "Market Velocity & Price Predictor":
    render_tab_market(df, current_squad)
elif mode == "Fixture Difficulty (FDR) Ticker":
    render_tab_fixtures(df, current_squad)
elif mode == "Set-Piece & Penalty Hierarchy":
    render_tab_setpieces(df)
elif mode == "🏟️ Venue Impact & Home/Away Analysis":
    render_tab_venue(df, current_squad=current_squad)
elif mode == "Draft New Optimal Squad":
    objective = st.sidebar.selectbox("Optimization Metric", ["fdr_moneyball", "setpiece_moneyball", "moneyball", "points", "form"], format_func=lambda x: {
        "fdr_moneyball": "Fixture-Adjusted Moneyball (xGI & FDR)",
        "setpiece_moneyball": "Set-Piece & Dead-Ball Moneyball (xG/xA Boost)",
        "moneyball": "Base Moneyball Score (xGI / Expected Return)",
        "points": "Total Points",
        "form": "Current Form"
    }[x])
    render_tab_draft(df, opt, objective=objective)
else:
    render_tab_explorer(df)
