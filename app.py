"""
Rubies Rangers FPL Operations Research & Analytics Platform
Slim entry router dispatching to modular presentation tabs in `ui/tabs/`.
Run locally with: streamlit run app.py
"""

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("rubies_rangers.app")

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
from ui.components import render_portfolio_ticker
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
    render_tab_challenge_optimizer,
    render_tab_challenge_rolling,
    render_tab_challenge_cpn,
    render_tab_strategic_macro,
    render_tab_strategic_solver,
    render_tab_strategic_balance_sheet,
    render_tab_audit_ledger,
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

# -------------------------------------------------------------
# Live FPL Session Authentication in Sidebar
# -------------------------------------------------------------
from clients.auth_manager import AuthManager
auth_mgr = AuthManager()
session_info = auth_mgr.get_active_session()

logger.info(
    "[App] FPL Session loaded: Authenticated=%s | Manager=%s %s | Entry ID=%s | Bank=£%.1fm | FT=%d | Source=%s",
    session_info.is_authenticated, session_info.first_name, session_info.last_name,
    session_info.entry_id, session_info.bank, session_info.free_transfers, session_info.auth_source
)

if session_info.is_authenticated:
    st.sidebar.markdown(
        f"""
        <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="color: #4ade80; font-weight: 700; font-size: 13px;">
                    🟢 {session_info.first_name} {session_info.last_name}
                </div>
                <div style="color: #6ee7b7; font-size: 10px; background: rgba(16, 185, 129, 0.25); padding: 1px 5px; border-radius: 3px;">
                    {session_info.auth_source}
                </div>
            </div>
            <div style="color: #cbd5e1; font-size: 11px; margin-top: 3px;">
                Entry #{session_info.entry_id} • Bank: £{session_info.bank:.1f}m • FT: {session_info.free_transfers}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.sidebar.markdown(
        """
        <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px;">
            <div style="color: #f87171; font-weight: 700; font-size: 13px;">
                🔴 Offline Session
            </div>
            <div style="color: #94a3b8; font-size: 11px; margin-top: 2px;">
                Sync Chrome session or set .env
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

col_auth1, col_auth2 = st.sidebar.columns([1, 1])
with col_auth1:
    if st.button("🔄 Refresh", key="sidebar_refresh_auth_btn", help="Re-verify FPL Session & Live Team State"):
        logger.info("[App] Sidebar '🔄 Refresh' clicked by user; refreshing FPL session...")
        with st.spinner("Re-verifying..."):
            auth_mgr.refresh_session()
            st.cache_data.clear()
            st.rerun()

with col_auth2:
    with st.popover("⚡ Sync"):
        st.markdown(
            """
            **Method 1: 1-Click Chrome Bookmarklet (Recommended)**
            1. Press **`Ctrl + Shift + B`** in Chrome to show the Bookmarks Bar.
            2. Right-click the Bookmarks Bar $\rightarrow$ **Add page...**
            3. **Name**: `⚡ Sync Rubies Rangers`
            4. **URL**: Copy and paste the snippet below:
            """
        )
        st.code(
            """javascript:(async()=>{try{const m=await(await fetch('/api/me/')).json();if(!m||!m.player){alert('❌ Please log into fantasy.premierleague.com first.');return;}let b=0.0,ft=1;try{const t=await(await fetch(`/api/my-team/${m.player.entry}/`)).json();if(t.transfers){b=t.transfers.bank/10.0;ft=t.transfers.limit;}}catch(e){}const r=await fetch('http://localhost:8000/api/auth/sync_browser',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({entry_id:m.player.entry,first_name:m.player.first_name,last_name:m.player.last_name,bank:b,free_transfers:ft,cookie:document.cookie})});const d=await r.json();if(d.is_authenticated){alert(`✅ Synced with Rubies Rangers!\nManager: ${d.first_name} ${d.last_name}\nTeam ID: ${d.entry_id}\nBank: £${d.bank}m\nFree Transfers: ${d.free_transfers}`);}else{alert('❌ Sync failed: '+d.error_message);}}catch(e){alert('❌ Could not connect to API on localhost:8000. Make sure launch_api.bat is running.');}})()""",
            language="javascript"
        )
        st.markdown(
            """
            5. Go to [fantasy.premierleague.com](https://fantasy.premierleague.com/) (logged in) and click the bookmark on your top bar!

            ---
            **Method 2: Run via Chrome DevTools Console**
            1. On [fantasy.premierleague.com](https://fantasy.premierleague.com/) (logged in), press **`F12`** $\rightarrow$ click the **Console** tab.
            2. ⚠️ **Chrome Security Notice:** Chrome blocks pasting code into the Console by default. To unlock it:
               - Type **`allow pasting`** into the console and press **Enter**.
            3. Now copy and paste the command below, then press **Enter**:
            """
        )
        st.code(
            """(async()=>{try{const m=await(await fetch('/api/me/')).json();if(!m||!m.player){alert('❌ Please log into fantasy.premierleague.com first.');return;}let b=0.0,ft=1;try{const t=await(await fetch(`/api/my-team/${m.player.entry}/`)).json();if(t.transfers){b=t.transfers.bank/10.0;ft=t.transfers.limit;}}catch(e){}const r=await fetch('http://localhost:8000/api/auth/sync_browser',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({entry_id:m.player.entry,first_name:m.player.first_name,last_name:m.player.last_name,bank:b,free_transfers:ft,cookie:document.cookie})});const d=await r.json();if(d.is_authenticated){alert(`✅ Synced with Rubies Rangers!\nManager: ${d.first_name} ${d.last_name}\nTeam ID: ${d.entry_id}\nBank: £${d.bank}m\nFree Transfers: ${d.free_transfers}`);}else{alert('❌ Sync failed: '+d.error_message);}}catch(e){alert('❌ Could not connect to API on localhost:8000. Make sure launch_api.bat is running.');}})()""",
            language="javascript"
        )
        st.markdown("---")
        raw_c = st.text_input("Or paste cookie / pl_profile:", key="sidebar_paste_cookie")
        if st.button("Apply Token", key="sidebar_apply_cookie"):
            if raw_c:
                res = auth_mgr.sync_browser_cookie(raw_c, source="SIDEBAR_PASTE")
                if res.is_authenticated:
                    st.success(f"Connected as {res.first_name} {res.last_name}!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(res.error_message or "Invalid token.")

st.sidebar.markdown("---")

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

# -------------------------------------------------------------
# 5. Quant Trading Desk Navigation (2-Tier Hierarchical Router)
# -------------------------------------------------------------
DESKS: dict[str, list[str]] = {
    "📈 Portfolio & Balance Sheet": [
        "🏟️ Portfolio Holdings & Matchday Live",
        "♟️ 5-GW Strategic Chessboard",
        "💰 Dynamic Balance Sheet & Options",
        "🔄 Squad Rebalancing (Transfers & Hits)",
        "🎴 Chip Execution Roadmap",
        "🏆 Mini-League Scout & Rival Spy",
    ],
    "⚔️ Quantitative Solvers": [
        "⚔️ Two-Stage Tournament (Screen & Sim)",
        "🛡️ Lineup & Substitution Strategist",
        "🎲 Monte Carlo Transfer Simulator",
        "✨ Draft Optimal 15-Man Squad",
        "🌊 Macro Fixture Radar & Wave Scanner",
    ],
    "🎯 FPL Challenge Tournaments": [
        "🎯 Two-Stage Tournament Solver",
        "⏱️ Rolling Lock & Matchday Tracker",
        "🤖 Autonomous Challenge CPN",
    ],
    "🤖 Autonomous Operations (CPN)": [
        "🤖 Fantasy CPN Robotic Manager",
        "🎯 Challenge CPN Autonomous Runner",
        "📋 Suggestion & Outcome Audit Ledger",
    ],
    "📡 Alpha Signals & Intelligence": [
        "🎰 Bookmaker Odds & Implied xP",
        "⚽ Tactical Process & Shot Quality",
        "🌤️ Weather Radar & Environmental Intel",
        "📈 Market Velocity & Price Predictor",
        "📅 Fixture Difficulty (FDR) Ticker",
        "🎯 Set-Piece & Penalty Hierarchy",
        "🏟️ Venue Impact & Home/Away Analysis",
        "🧠 Shane's Domain Intel Desk",
        "🔍 Player Explorer & Factor Radar",
    ],
}

st.sidebar.markdown("### 🏛️ Operational Trading Desks")
selected_desk = st.sidebar.radio(
    "Select Desk:",
    options=list(DESKS.keys()),
    index=0,
    key="quant_nav_desk_selector"
)

st.sidebar.markdown("---")
available_views = DESKS[selected_desk]
selected_view = st.sidebar.radio(
    "Active Desk View:",
    options=available_views,
    index=0,
    key="quant_nav_view_selector"
)

# Shared bank balance
bank_balance = float(get_system_config("default_bank") or 3.7)

# Persistent Top Portfolio Ticker Tape
render_portfolio_ticker(
    session_info=session_info,
    active_profile_name=active_profile.display_name,
    gameweek=5,
    bank_balance=bank_balance
)

# -------------------------------------------------------------
# 6. Dispatch to Modular Tab Renderers
# -------------------------------------------------------------
# 📈 Portfolio & Balance Sheet Desk
if selected_view == "🏟️ Portfolio Holdings & Matchday Live":
    render_tab_matchday(df, current_squad, active_profile.display_name)
elif selected_view == "♟️ 5-GW Strategic Chessboard":
    render_tab_strategic_solver(df, current_squad)
elif selected_view == "💰 Dynamic Balance Sheet & Options":
    render_tab_strategic_balance_sheet(df, current_squad)
elif selected_view == "🔄 Squad Rebalancing (Transfers & Hits)":
    render_tab_transfers(df, opt, current_squad, bank_balance=bank_balance)
elif selected_view == "🎴 Chip Execution Roadmap":
    render_tab_chip_strategy()
elif selected_view == "🏆 Mini-League Scout & Rival Spy":
    render_tab_leagues(df)

# ⚔️ Quantitative Solvers Desk
elif selected_view == "⚔️ Two-Stage Tournament (Screen & Sim)":
    render_tab_two_stage(df, current_squad, bank=bank_balance)
elif selected_view == "🛡️ Lineup & Substitution Strategist":
    render_tab_montecarlo_lineup(df, current_squad)
elif selected_view == "🎲 Monte Carlo Transfer Simulator":
    render_tab_montecarlo_transfers(df, current_squad, bank_balance=bank_balance)
elif selected_view == "✨ Draft Optimal 15-Man Squad":
    render_tab_draft(df, opt, current_squad=current_squad)
elif selected_view == "🌊 Macro Fixture Radar & Wave Scanner":
    render_tab_strategic_macro(df, current_squad)

# 🎯 FPL Challenge Tournament Desk
elif selected_view == "🎯 Two-Stage Tournament Solver":
    render_tab_challenge_optimizer(df)
elif selected_view == "⏱️ Rolling Lock & Matchday Tracker":
    render_tab_challenge_rolling(df)
elif selected_view == "🤖 Autonomous Challenge CPN":
    render_tab_challenge_cpn(df)

# 🤖 Autonomous Operations (CPN) Desk
elif selected_view == "🤖 Fantasy CPN Robotic Manager":
    render_tab_autonomous_cpn(df, current_squad)
elif selected_view == "🎯 Challenge CPN Autonomous Runner":
    render_tab_challenge_cpn(df)
elif selected_view == "📋 Suggestion & Outcome Audit Ledger":
    render_tab_audit_ledger(df, current_squad, active_profile.display_name)

# 📡 Alpha Signals & Intelligence Desk
elif selected_view == "🎰 Bookmaker Odds & Implied xP":
    render_tab_odds_xp()
elif selected_view == "⚽ Tactical Process & Shot Quality":
    render_tab_tactical(df)
elif selected_view == "🌤️ Weather Radar & Environmental Intel":
    render_tab_weather(df, current_squad)
elif selected_view == "📈 Market Velocity & Price Predictor":
    render_tab_market(df, current_squad)
elif selected_view == "📅 Fixture Difficulty (FDR) Ticker":
    render_tab_fixtures(df, current_squad)
elif selected_view == "🎯 Set-Piece & Penalty Hierarchy":
    render_tab_setpieces(df)
elif selected_view == "🏟️ Venue Impact & Home/Away Analysis":
    render_tab_venue(df, current_squad=current_squad)
elif selected_view == "🧠 Shane's Domain Intel Desk":
    render_tab_domain_intel(df, current_squad)
else:
    render_tab_explorer(df)
