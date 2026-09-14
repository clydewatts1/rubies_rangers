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
from analytics.profile_manager import ProfileManager
from analytics.profile_contracts import ProfileType, ManagerProfile
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
    render_tab_chip_strategy,
    render_tab_autonomous_cpn,
    render_tab_weather,
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

# 4. Profile & Active Squad Management
profile_mgr = ProfileManager()
profile_mgr.ensure_seeded()
all_profiles = profile_mgr.list_profiles()

default_profile = profile_mgr.get_default_profile()
default_pid = default_profile.profile_id if default_profile else "rubies_rangers"

if "active_profile_id" not in st.session_state or not profile_mgr.get_profile(st.session_state["active_profile_id"]):
    st.session_state["active_profile_id"] = default_pid

active_profile = profile_mgr.get_profile(st.session_state["active_profile_id"])
if not active_profile:
    active_profile = default_profile

st.session_state["active_squad"] = list(active_profile.active_squad)
st.session_state["active_entry_id"] = active_profile.fpl_entry_id
st.session_state["active_profile_name"] = active_profile.display_name
st.session_state["active_profile_league_ids"] = list(active_profile.mini_league_ids)
st.session_state["active_profile_is_sandbox"] = (active_profile.profile_type == ProfileType.SANDBOX)
st.session_state["active_bank"] = active_profile.bank_balance
current_squad = st.session_state["active_squad"]

with st.sidebar:
    st.markdown("---")
    st.markdown("### 👤 Manager Profile & Squad")

    profile_map = {p.profile_id: p for p in all_profiles}
    def _format_profile_item(pid: str) -> str:
        p = profile_map.get(pid)
        if not p:
            return pid
        default_tag = "⭐ [DEFAULT] " if p.is_default else ""
        tag = "✏️ [WRITABLE]" if not p.is_read_only else "🔒 [READ-ONLY]"
        return f"{default_tag}{tag} {p.display_name}"

    profile_ids = [p.profile_id for p in all_profiles]
    sel_idx = profile_ids.index(active_profile.profile_id) if active_profile.profile_id in profile_ids else 0
    selected_pid = st.selectbox(
        "Active Profile / Draft:",
        profile_ids,
        index=sel_idx,
        format_func=_format_profile_item,
        key="sidebar_profile_selector"
    )
    if selected_pid != active_profile.profile_id:
        st.session_state["active_profile_id"] = selected_pid
        st.rerun()

    # Profile Status Summary
    is_live = (active_profile.profile_type == ProfileType.LIVE_FPL)
    entry_str = f"FPL Entry #{active_profile.fpl_entry_id}" if active_profile.fpl_entry_id else "Hypothetical Draft"
    bank_str = f"Bank: £{active_profile.bank_balance:.1f}M"
    ro_badge = "🔒 READ-ONLY" if active_profile.is_read_only else "✏️ WRITABLE (Clyde Watts)"
    def_badge = "⭐ DEFAULT • " if active_profile.is_default else ""
    st.caption(f"**{entry_str}** • {bank_str} • **{def_badge}{ro_badge}** • {len(current_squad)}/15 Players")

    # 15-Player Roster & Swaps Expander
    with st.expander("📋 Roster & Player Swaps", expanded=False):
        st.caption(", ".join(current_squad))
        st.markdown("---")
        if active_profile.is_read_only:
            st.info("🔒 **Profile is Read-Only**: Roster mutations and player swaps are locked for competitor profiles. To experiment with this team, clone it using 'Clone to Sandbox Draft' below.")
        else:
            st.markdown("**🔄 Swap a Player:**")
            swap_out = st.selectbox("Sell Player", current_squad, key="sidebar_swap_out")
            all_player_names = sorted(df["web_name"].dropna().unique().tolist())
            swap_in = st.selectbox(
                "Buy Player",
                all_player_names,
                index=all_player_names.index("João Pedro") if "João Pedro" in all_player_names else 0,
                key="sidebar_swap_in"
            )
            if st.button("Apply Swap & Save to Profile", key="btn_apply_swap"):
                if swap_out in current_squad:
                    idx = current_squad.index(swap_out)
                    new_squad = list(current_squad)
                    new_squad[idx] = swap_in
                    updated_profile = ManagerProfile(
                        profile_id=active_profile.profile_id,
                        display_name=active_profile.display_name,
                        profile_type=active_profile.profile_type,
                        fpl_entry_id=active_profile.fpl_entry_id,
                        bank_balance=active_profile.bank_balance,
                        active_squad=new_squad,
                        mini_league_ids=active_profile.mini_league_ids,
                        calibration_profile=active_profile.calibration_profile,
                        notes=active_profile.notes,
                        is_read_only=active_profile.is_read_only
                    )
                    profile_mgr.save_profile(updated_profile)
                    st.session_state["active_squad"] = new_squad
                    st.cache_data.clear()
                    st.success(f"Swapped {swap_out} ➔ {swap_in}!")
                    st.rerun()

    # Sync Live Picks Button (if LIVE_FPL)
    if is_live and active_profile.fpl_entry_id:
        if st.button(f"📥 Sync Live Picks (Entry {active_profile.fpl_entry_id})", key="btn_sync_live"):
            try:
                with st.spinner(f"Syncing picks from FPL Entry {active_profile.fpl_entry_id}..."):
                    lt = LeagueTracker()
                    picks_data = lt.get_team_picks(active_profile.fpl_entry_id)
                    s_names = [p["web_name"] for p in picks_data.get("starters", [])]
                    b_names = [p["web_name"] for p in picks_data.get("bench", [])]
                    if len(s_names) + len(b_names) == 15:
                        synced_squad = s_names + b_names
                        bank_val = round(picks_data.get("entry_history", {}).get("bank", 0) / 10.0, 2)
                        updated_p = ManagerProfile(
                            profile_id=active_profile.profile_id,
                            display_name=active_profile.display_name,
                            profile_type=active_profile.profile_type,
                            fpl_entry_id=active_profile.fpl_entry_id,
                            bank_balance=bank_val,
                            active_squad=synced_squad,
                            mini_league_ids=active_profile.mini_league_ids,
                            calibration_profile=active_profile.calibration_profile,
                            notes=active_profile.notes,
                            is_read_only=active_profile.is_read_only
                        )
                        profile_mgr.save_profile(updated_p)
                        st.session_state["active_squad"] = synced_squad
                        st.session_state["active_bank"] = bank_val
                        st.cache_data.clear()
                        st.success(f"Synced 15 players & £{bank_val:.1f}M bank from FPL Entry {active_profile.fpl_entry_id}!")
                        st.rerun()
                    else:
                        st.warning("Could not retrieve all 15 picks from FPL API.")
            except Exception as e:
                st.error(f"Sync failed: {e}")

    # Profile Management Expander (Import Any Team ID, Clone, Delete)
    with st.expander("⚙️ Manage Profiles & Import Teams", expanded=False):
        st.markdown("**➕ Import Any FPL Team ID:**")
        import_id_input = st.number_input("FPL Team / Entry ID", min_value=1, value=6173410, step=1, key="import_entry_id")
        custom_import_name = st.text_input("Custom Display Name (optional)", key="import_custom_name")
        if st.button("📥 Import & Switch to Team", key="btn_import_team"):
            try:
                with st.spinner(f"Fetching published roster for Entry {import_id_input}..."):
                    new_p = profile_mgr.import_fpl_team(int(import_id_input), custom_display_name=custom_import_name)
                    st.session_state["active_profile_id"] = new_p.profile_id
                    st.cache_data.clear()
                    st.success(f"Imported '{new_p.display_name}'!")
                    st.rerun()
            except Exception as e:
                st.error(f"Failed to import team {import_id_input}: {e}")

        st.markdown("---")
        st.markdown("**🏆 Batch Import Mini-League Teams:**")
        league_import_id = st.number_input("Mini-League ID", min_value=1, value=325320, step=1, key="import_league_id")
        if st.button("📥 Import All Teams from League", key="btn_import_league"):
            try:
                with st.spinner(f"Fetching all competitor teams from League {league_import_id}..."):
                    imported = profile_mgr.import_league_teams(int(league_import_id))
                    st.cache_data.clear()
                    st.success(f"Imported {len(imported)} teams from League {league_import_id}!")
                    st.rerun()
            except Exception as e:
                st.error(f"Failed to import league: {e}")

        st.markdown("---")
        st.markdown("**🧪 Clone to New Sandbox Draft:**")
        clone_name = st.text_input("Draft Name", value=f"{active_profile.display_name} (Draft)", key="clone_draft_name")
        if st.button("📋 Clone to Sandbox Draft", key="btn_clone_draft"):
            if clone_name.strip():
                cloned = profile_mgr.clone_profile(active_profile.profile_id, clone_name.strip())
                st.session_state["active_profile_id"] = cloned.profile_id
                st.cache_data.clear()
                st.success(f"Created sandbox draft '{cloned.display_name}'!")
                st.rerun()

        if len(all_profiles) > 1 and active_profile.profile_type == ProfileType.SANDBOX:
            st.markdown("---")
            if st.button(f"🗑️ Delete Draft '{active_profile.display_name}'", key="btn_delete_draft"):
                profile_mgr.delete_profile(active_profile.profile_id)
                st.session_state["active_profile_id"] = "rubies_rangers"
                st.cache_data.clear()
                st.success("Draft deleted.")
                st.rerun()

    st.markdown("---")

# 5. Workflow Dispatcher
mode = st.sidebar.selectbox("Workflow", [
    "🏟️ Matchday Center & Live Gameweek Team Scoreboard",
    "🌤️ Weather Radar & Environmental Intelligence",
    "⚔️ Two-Stage Tournament (Screen & Simulate)",
    "🎴 Long-Term Chip Strategy & Season Roadmap",
    "🤖 Autonomous CPN Execution & Robotic Manager",
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
if mode in (
    "🏟️ Matchday Center & Live Gameweek Team Scoreboard",
    "🏟️ Matchday Center & Live Gameweek Mini-League Scoreboard",
    "🏟️ Matchday Center & Live Gameweek Scores"
):
    render_tab_matchday(df, current_squad, active_profile.display_name)
elif mode == "🌤️ Weather Radar & Environmental Intelligence":
    render_tab_weather(df, current_squad)
elif mode == "⚔️ Two-Stage Tournament (Screen & Simulate)":
    render_tab_two_stage(df, current_squad, bank=bank_balance)
elif mode == "🎴 Long-Term Chip Strategy & Season Roadmap":
    render_tab_chip_strategy()
elif mode == "🤖 Autonomous CPN Execution & Robotic Manager":
    render_tab_autonomous_cpn(df, current_squad)
elif mode == "🧠 Shane's Domain Intel Desk":
    render_tab_domain_intel(df, current_squad)
elif mode == "Modify Current Team (Transfers)":
    num_transfers = st.sidebar.slider("Number of Transfers", 1, 4, 1, key="mod_transfers_count")
    objective = st.sidebar.selectbox("Optimization Metric", ["fdr_moneyball", "forward_moneyball", "setpiece_moneyball", "moneyball", "points", "form"], format_func=lambda x: {
        "fdr_moneyball": "Fixture-Adjusted Moneyball (xGI & FDR)",
        "forward_moneyball": "Forward Alpha (Talisman Share & Disruption)",
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
    render_tab_tactical(df)
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
    objective = st.sidebar.selectbox("Optimization Metric (Quick Solve)", ["fdr_moneyball", "setpiece_moneyball", "moneyball", "points", "form"], format_func=lambda x: {
        "fdr_moneyball": "Fixture-Adjusted Moneyball (xGI & FDR)",
        "setpiece_moneyball": "Set-Piece & Dead-Ball Moneyball (xG/xA Boost)",
        "moneyball": "Base Moneyball Score (xGI / Expected Return)",
        "points": "Total Points",
        "form": "Current Form"
    }[x], key="sidebar_draft_obj")
    render_tab_draft(df, opt, current_squad=current_squad, objective=objective)
else:
    render_tab_explorer(df)
