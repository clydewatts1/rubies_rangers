"""
Rubies Rangers FPL Web Dashboard
Interactive Moneyball team picker, FDR fixture ticker, and Market Velocity Price Predictor built with Streamlit.
Run locally with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fpl_client import FPLClient
from fpl_optimizer import FPLOptimizer
from price_tracker import PriceTracker
from tactical_client import TacticalClient
from xp_model import XPModel
from league_tracker import LeagueTracker
from montecarlo_engine import MonteCarloEngine
from config_manager import get_system_config, get_params, get_active_profile, set_active_profile

DEFAULT_SQUAD = get_system_config("default_squad") or [
    "Roefs", "Verbruggen",
    "Pedro Porro", "Senesi", "Guéhi", "Robinson", "Thiaw",
    "Foden", "Ødegaard", "Mbeumo", "Cherki", "Rogers",
    "João Pedro", "Isak", "Solanke"
]
DEFAULT_BANK = float(get_system_config("default_bank") or 3.7)
DEFAULT_LEAGUE_ID = int(get_system_config("default_league_id") or 325320)

st.set_page_config(

    page_title="Rubies Rangers — FPL Moneyball Optimizer",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp {
        background-color: #0b0f19;
        color: #f8fafc;
    }
    header[data-testid="stHeader"] {
        background-color: #0b0f19;
    }
    section[data-testid="stSidebar"] {
        background-color: #0f172a;
    }
    .stMetric { background-color: #1a1f2c; padding: 12px; border-radius: 8px; border: 1px solid #2d3748; }
    .badge-fdr-easy { background-color: #064e3b; color: #6ee7b7; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-fdr-med { background-color: #78350f; color: #fde68a; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-fdr-hard { background-color: #7f1d1d; color: #fca5a5; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-rise { background-color: #064e3b; color: #34d399; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-fall { background-color: #7f1d1d; color: #f87171; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    
    /* High contrast player cards */
    .squad-player-card {
        background: #1e293b !important;
        color: #f8fafc !important;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 10px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
    }
    .squad-player-card * {
        color: #f8fafc !important;
    }
    .squad-player-card b, .squad-player-card strong {
        color: #ffffff !important;
    }
    .squad-player-card .player-title {
        color: #ffffff !important;
        font-size: 15px !important;
        font-weight: 700 !important;
    }
    .squad-player-card .club-subtitle {
        color: #94a3b8 !important;
        font-size: 12px !important;
    }
    .squad-player-card .metric-line {
        color: #cbd5e1 !important;
        font-size: 12px !important;
    }
    .squad-player-card .score-line {
        color: #34d399 !important;
        font-weight: 600 !important;
        font-size: 12px !important;
    }
    .pitch-container {
        background: radial-gradient(circle at center, #065f46 0%, #064e3b 70%, #022c22 100%);
        border: 2px solid rgba(255, 255, 255, 0.2);
        border-radius: 16px;
        padding: 24px 16px;
        margin-bottom: 24px;
        position: relative;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    }
    .pitch-row {
        display: flex;
        justify-content: space-around;
        align-items: center;
        margin-bottom: 24px;
        flex-wrap: wrap;
        gap: 12px;
    }
    .player-card {
        background: rgba(15, 23, 42, 0.90);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 12px;
        padding: 12px 14px;
        text-align: center;
        min-width: 140px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .player-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 25px rgba(56, 189, 248, 0.4);
        border-color: #38bdf8;
    }
    .captain-badge {
        background: linear-gradient(135deg, #ef4444, #b91c1c);
        color: white;
        font-weight: 800;
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 12px;
        display: inline-block;
        margin-bottom: 4px;
        box-shadow: 0 0 10px rgba(239, 68, 68, 0.6);
    }
    .vc-badge {
        background: linear-gradient(135deg, #3b82f6, #1d4ed8);
        color: white;
        font-weight: 800;
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 12px;
        display: inline-block;
        margin-bottom: 4px;
        box-shadow: 0 0 10px rgba(59, 130, 246, 0.6);
    }
    .xp-pill {
        background: rgba(34, 197, 94, 0.2);
        color: #4ade80;
        border: 1px solid #22c55e;
        padding: 2px 8px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 13px;
        margin-top: 4px;
        display: inline-block;
    }
    .bench-card {
        background: rgba(30, 41, 59, 0.85);
        border: 1px dashed rgba(255, 255, 255, 0.2);
        border-radius: 8px;
        padding: 10px 14px;
        text-align: center;
        min-width: 130px;
    }
    /* Never let markdown code formatting create white boxes over custom cards */
    div[data-testid="stMarkdownContainer"] pre {
        background-color: transparent !important;
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
        box-shadow: none !important;
    }
    div[data-testid="stMarkdownContainer"] code {
        background-color: transparent !important;
        color: inherit !important;
    }
    /* Ensure KPI metric values are crystal clear in all modes */
    [data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricDelta"] {
        color: #38bdf8 !important;
    }
    .step-card {
        background: #1e293b;
        border-radius: 10px;
        padding: 14px 16px;
        margin-bottom: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }
    .badge-step-red {
        background: #991b1b;
        color: #fecaca;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-step-green {
        background: #065f46;
        color: #a7f3d0;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-step-yellow {
        background: #854d0e;
        color: #fef08a;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-step-blue {
        background: #1e40af;
        color: #bfdbfe;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-step-purple {
        background: #581c87;
        color: #e9d5ff;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
</style>
""", unsafe_allow_html=True)

def render_html(html_code: str):
    """Cleanly render raw HTML without markdown converting indented lines into code blocks."""
    clean = "\n".join(line.strip() for line in html_code.splitlines() if line.strip())
    st.markdown(clean, unsafe_allow_html=True)


@st.cache_data(ttl=1800)
def load_data(source: str, force_refresh: bool = False):
    if source == "Historical CSV":
        df = pd.read_csv("fpl_player_statistics.csv")
        if "now_cost" in df.columns:
            df["now_cost"] = pd.to_numeric(df["now_cost"], errors="coerce")
        if "web_name" not in df.columns and "player_name" in df.columns:
            df["web_name"] = df["player_name"]
            df["full_name"] = df["player_name"]
        if "moneyball_score" not in df.columns:
            mb_params = get_params("moneyball")
            fwd_mid = mb_params.get("fwd_mid_weights", {})
            xgi_w = float(fwd_mid.get("xgi_per_90", 4.0))
            ict_div = float(fwd_mid.get("ict_index_divisor", 50.0))
            ppg_w = float(fwd_mid.get("ppg_weight", 1.2))
            xgi = df.get("expected_goal_involvements_per_90", 0).fillna(0)
            ict = df.get("ict_index", 0).fillna(0)
            ppg = df.get("points_per_game", 0).fillna(0)
            df["moneyball_score"] = (xgi * xgi_w) + (ict / ict_div) + (ppg * ppg_w)
        if "fdr_moneyball_score" not in df.columns:
            df["fdr_moneyball_score"] = df["moneyball_score"]
        if "fdr_next_5" not in df.columns:
            df["fdr_next_5"] = 3.0
            df["next_fixture"] = "N/A"
        if "price_status" not in df.columns:
            df["price_status"] = "Stable"
            df["net_transfers"] = 0
            df["price_progress_pct"] = 0.0
        if "status" not in df.columns:
            df["status"] = "a"
        return df
    else:
        client = FPLClient()
        return client.get_players_df(force_refresh=force_refresh)


@st.cache_data(ttl=1800)
def load_fdr_map(n_gameweeks: int = 5, force_refresh: bool = False):
    client = FPLClient()
    return client.get_team_fdr_map(n_gameweeks=n_gameweeks)


@st.cache_data(ttl=1800)
def load_squad_trends(force_refresh: bool = False):
    client = FPLClient()
    return client.get_squad_trends(DEFAULT_SQUAD)


@st.cache_data(ttl=1800)
def load_player_trends(player_id: int, n_recent: int = 3, force_refresh: bool = False):
    client = FPLClient()
    return client.get_player_trends(player_id, n_recent=n_recent)


@st.cache_data(ttl=3600)
def load_squad_tactical(force_refresh: bool = False):
    tc = TacticalClient()
    return tc.get_squad_tactical_df(force_refresh=force_refresh)


@st.cache_data(ttl=3600)
def load_league_tactical(force_refresh: bool = False):
    tc = TacticalClient()
    return tc.get_league_tactical_df(force_refresh=force_refresh)


@st.cache_data(ttl=3600)
def load_player_shot_breakdown(understat_id: str):
    tc = TacticalClient()
    return tc.get_player_shot_breakdown(understat_id)


@st.cache_data(ttl=1800)
def load_xp_lineup(force_refresh: bool = False):
    xm = XPModel()
    return xm.optimize_lineup()


@st.cache_data(ttl=1800)
def load_xp_squad(force_refresh: bool = False):
    xm = XPModel()
    return xm.evaluate_squad_xp()


@st.cache_data(ttl=1800)
def load_gw4_odds(force_refresh: bool = False):
    xm = XPModel()
    return xm.get_gw4_odds_table()


@st.cache_data(ttl=1800)
def load_top_captains(top_n: int = 15, force_refresh: bool = False):
    xm = XPModel()
    return xm.get_top_captains(top_n=top_n)


@st.cache_data(ttl=600)
def load_league_standings(league_id: int):
    tracker = LeagueTracker()
    return tracker.get_league_standings(league_id)


@st.cache_data(ttl=600)
def load_team_leagues(entry_id: int):
    tracker = LeagueTracker()
    return tracker.get_team_leagues(entry_id)


@st.cache_data(ttl=600)
def load_team_picks(entry_id: int, gameweek: int = None):
    tracker = LeagueTracker()
    return tracker.get_team_picks(entry_id, gameweek=gameweek)


@st.cache_data(ttl=600)
def load_league_ownership(league_id: int, gameweek: int = None, max_teams: int = 20):
    tracker = LeagueTracker()
    return tracker.get_league_ownership(league_id, gameweek=gameweek, max_teams=max_teams)


@st.cache_data(ttl=600)
def load_league_history(league_id: int, max_teams: int = 20):
    tracker = LeagueTracker()
    return tracker.get_league_performance_history(league_id, max_teams=max_teams)


@st.cache_data(ttl=600, show_spinner=False)
def load_montecarlo_simulation(bank: float = 3.7,
                               num_transfers: int = 1,
                               free_transfers: int = 1,
                               n_sims: int = 2500,
                               pos_filter: str = "ALL",
                               sell_filter: str = None,
                               strict_filter: bool = True):
    mc = MonteCarloEngine()
    return mc.evaluate_transfers(
        bank=bank,
        num_transfers=num_transfers,
        free_transfers=free_transfers,
        n_sims=n_sims,
        position_filter=None if pos_filter == "ALL" else pos_filter,
        sell_player_filter=sell_filter,
        strict_injury_filter=strict_filter
    )


@st.cache_data(ttl=600, show_spinner=False)
def load_montecarlo_lineup(squad_names: tuple = None,
                           n_sims: int = 2500,
                           form_weight: float = 0.25,
                           include_disciplinary: bool = True,
                           force_refresh: bool = False):
    if squad_names is None:
        squad_names = tuple(DEFAULT_SQUAD)
    mc = MonteCarloEngine()
    return mc.optimize_lineup_and_substitutions(
        squad_names=list(squad_names),
        n_sims=n_sims,
        form_weight=form_weight,
        include_disciplinary=include_disciplinary
    )


# Sidebar
st.sidebar.title("⚽ Rubies Rangers")
st.sidebar.markdown("**Strategy:** Moneyball Optimization")
st.sidebar.markdown(f"**Config Profile:** `{get_active_profile().capitalize()}`")

data_source = st.sidebar.radio("Data Source", ["Live FPL API", "Historical CSV"])
if st.sidebar.button("🔄 Force Refresh Live Data"):
    st.cache_data.clear()
    load_data("Live FPL API", force_refresh=True)
    load_fdr_map(force_refresh=True)
    load_squad_trends(force_refresh=True)
    load_squad_tactical(force_refresh=True)
    load_league_tactical(force_refresh=True)
    load_xp_lineup(force_refresh=True)
    load_xp_squad(force_refresh=True)
    load_gw4_odds(force_refresh=True)
    load_top_captains(force_refresh=True)
    load_montecarlo_lineup(force_refresh=True)
    st.sidebar.success("Live data refreshed!")

df = load_data(data_source)
opt = FPLOptimizer(df)

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
    st.markdown("**🔄 Swap a Player (Test Live Changes):**")
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

mode = st.sidebar.selectbox("Workflow", [
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
    "Draft New Optimal Squad",
    "Player Explorer"
])

objective = st.sidebar.selectbox("Optimization Metric", ["fdr_moneyball", "setpiece_moneyball", "moneyball", "points", "form"], format_func=lambda x: {
    "fdr_moneyball": "Fixture-Adjusted Moneyball (xGI & FDR)",
    "setpiece_moneyball": "Set-Piece & Dead-Ball Moneyball (xG/xA Boost)",
    "moneyball": "Base Moneyball Score (xGI / Expected Return)",
    "points": "Total Points",
    "form": "Current Form"
}[x])


if mode == "Modify Current Team (Transfers)":
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

elif mode == "🏆 Mini-League Scout & Rival Spy":
    st.title("🏆 Mini-League Scout & Rival Spy")
    st.markdown("""
    **Moneyball Rival Intelligence:** Win your mini-league by spying on rival managers, auditing their exact Starting XIs, bench order, and active chips (Wildcard / Triple Captain), and computing **Effective Ownership (EO%)** to exploit differential leverage against your league.
    """)

    with st.expander("📌 How to find your League ID or FPL Team ID (in 5 seconds)", expanded=False):
        st.markdown("""
        - **Mini-League ID:**
          1. Go to [fantasy.premierleague.com](https://fantasy.premierleague.com)
          2. Click **Leagues & Cups** ➔ Click on your private mini-league
          3. Look at your browser address bar: `https://fantasy.premierleague.com/leagues/XXXXXX/standings/c`
          4. The number **`XXXXXX`** is your **League ID**!
        - **Team / Entry ID:**
          1. On the FPL website, click **Points** or **Pick Team**
          2. Look at URL: `https://fantasy.premierleague.com/entry/YYYYYYY/event/...`
          3. The number **`YYYYYYY`** is your **Team ID** (all your mini-leagues will be automatically discovered).
        """)

    # Selection Tabs
    tab_mode = st.radio("Search Method", ["Enter Mini-League ID", "Auto-Discover Leagues from FPL Team ID"], horizontal=True)

    active_league_id = None
    default_league_id = 325320  # Bronze, Silver & Gold League

    if tab_mode == "Enter Mini-League ID":
        c_in, _ = st.columns([1, 1])
        with c_in:
            l_input = st.text_input("Enter FPL Mini-League ID:", value=str(default_league_id))
            if l_input.strip().isdigit():
                active_league_id = int(l_input.strip())
    else:
        c_tin, _ = st.columns([1, 1])
        with c_tin:
            t_input = st.text_input("Enter your FPL Team / Entry ID:", value="6173410")
        
        if t_input.strip().isdigit():
            team_id = int(t_input.strip())
            try:
                with st.spinner("Fetching manager profile and leagues..."):
                    manager_info = load_team_leagues(team_id)

                st.markdown(f"""
                <div style="background: #1e293b; border-left: 4px solid #38bdf8; padding: 12px 16px; border-radius: 8px; margin-bottom: 15px;">
                    <b style="color: #ffffff; font-size: 16px;">{manager_info['team_name']}</b> <span style="color: #94a3b8;">({manager_info['manager_name']})</span><br/>
                    <span style="color: #cbd5e1; font-size: 13px;">Overall Points: <b style="color: #facc15;">{manager_info['overall_points']}</b> | Overall Rank: <b style="color: #38bdf8;">#{manager_info['overall_rank']:,}</b></span>
                </div>
                """, unsafe_allow_html=True)

                leagues = manager_info.get("leagues", [])
                if leagues:
                    league_choices = {f"{l['name']} (Rank #{l['rank']:,})": l['id'] for l in leagues}
                    # Default index to Bronze, Silver & Gold League if found
                    keys_list = list(league_choices.keys())
                    default_idx = 0
                    for i, k in enumerate(keys_list):
                        if "Bronze" in k or league_choices[k] == 325320:
                            default_idx = i
                            break
                    selected_league_label = st.selectbox("Select Mini-League to Scout:", keys_list, index=default_idx)
                    active_league_id = league_choices[selected_league_label]
                else:
                    st.warning("No classic mini-leagues found for this Team ID.")
            except Exception as e:
                st.error(f"Error loading manager profile: {e}")

    # If an active league is loaded
    if active_league_id:
        try:
            with st.spinner("Extracting mini-league standings & rival teams..."):
                league_data = load_league_standings(active_league_id)

            league_name = league_data.get("league_name", "Mini-League")
            teams = league_data.get("teams", [])

            if not teams:
                st.warning(f"No teams found in League {active_league_id}. Please check the ID.")
            else:
                leader = teams[0]
                gw_pts_list = [t["gw_points"] for t in teams if t.get("gw_points") is not None]
                tot_pts_list = [t["total_points"] for t in teams if t.get("total_points") is not None]
                avg_gw = round(sum(gw_pts_list) / len(gw_pts_list), 1) if gw_pts_list else 0
                avg_tot = round(sum(tot_pts_list) / len(tot_pts_list), 1) if tot_pts_list else 0

                # Summary KPIs
                st.markdown(f"### 📋 Standings — {league_name}")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total Teams", f"{len(teams)}")
                k2.metric("Leader", f"{leader['team_name']}", f"{leader['total_points']} pts")
                k3.metric("League Avg GW", f"{avg_gw} pts")
                k4.metric("League Avg Total", f"{avg_tot} pts")

                # Standings Table
                standings_rows = []
                for t in teams:
                    rank = t["rank"]
                    last = t["last_rank"]
                    if last is not None and rank < last:
                        move_str = f"▲ {last - rank}"
                    elif last is not None and rank > last:
                        move_str = f"▼ {rank - last}"
                    else:
                        move_str = "="
                    
                    standings_rows.append({
                        "Rank": rank,
                        "Trend": move_str,
                        "Team Name": t["team_name"],
                        "Manager": t["manager_name"],
                        "GW Points": t["gw_points"],
                        "Total Points": t["total_points"],
                        "Entry ID": t["entry_id"]
                    })

                standings_df = pd.DataFrame(standings_rows)
                st.dataframe(standings_df, use_container_width=True, hide_index=True)

                # -------------------------------------------------------------
                # Standings Comparison Bar Chart
                # -------------------------------------------------------------
                st.markdown("#### 📊 Standings Comparison Bar Chart")
                bar_metric = st.radio(
                    "Compare by:",
                    ["🏆 Cumulative Total Points", "⚡ Latest Gameweek Points"],
                    horizontal=True,
                    key="standings_bar_metric"
                )

                if bar_metric == "🏆 Cumulative Total Points":
                    # Sort by Rank (#1 at top)
                    df_bar = standings_df.sort_values(by="Rank", ascending=True).copy()
                    bar_colors = ["#facc15" if "Rubies Rangers" in str(t) else "#38bdf8" for t in df_bar["Team Name"]]
                    y_labels = [f"#{r['Rank']} {r['Team Name']}" + (" ★ (You)" if "Rubies Rangers" in str(r["Team Name"]) else "") for _, r in df_bar.iterrows()]
                    
                    fig_standings = go.Figure()
                    fig_standings.add_trace(go.Bar(
                        x=df_bar["Total Points"],
                        y=y_labels,
                        orientation="h",
                        marker=dict(color=bar_colors, line=dict(color="rgba(255,255,255,0.4)", width=1)),
                        text=[f"<b>{p} pts</b>" for p in df_bar["Total Points"]],
                        textposition="outside",
                        hoverinfo="text",
                        hovertext=[f"<b>{r['Team Name']}</b> ({r['Manager']})<br>Total Points: <b>{r['Total Points']}</b><br>Rank: <b>#{r['Rank']}</b>" for _, r in df_bar.iterrows()]
                    ))
                    if avg_tot > 0:
                        fig_standings.add_vline(
                            x=avg_tot,
                            line_dash="dash",
                            line_color="#ef4444",
                            annotation_text=f"League Avg: {avg_tot:.1f} pts",
                            annotation_position="top right",
                            annotation_font=dict(color="#f87171", size=11)
                        )
                    fig_standings.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="rgba(15, 23, 42, 0.6)",
                        plot_bgcolor="rgba(15, 23, 42, 0.6)",
                        yaxis=dict(autorange="reversed"),
                        xaxis=dict(title="Total Points", showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
                        margin=dict(l=20, r=40, t=30, b=20),
                        height=380
                    )
                    st.plotly_chart(fig_standings, use_container_width=True)

                else:
                    # Sort by GW Points descending
                    df_gw_bar = standings_df.sort_values(by="GW Points", ascending=False).copy()
                    bar_colors_gw = ["#facc15" if "Rubies Rangers" in str(t) else "#10b981" for t in df_gw_bar["Team Name"]]
                    y_labels_gw = [f"{r['Team Name']}" + (" ★ (You)" if "Rubies Rangers" in str(r["Team Name"]) else "") for _, r in df_gw_bar.iterrows()]
                    
                    fig_standings_gw = go.Figure()
                    fig_standings_gw.add_trace(go.Bar(
                        x=df_gw_bar["GW Points"],
                        y=y_labels_gw,
                        orientation="h",
                        marker=dict(color=bar_colors_gw, line=dict(color="rgba(255,255,255,0.4)", width=1)),
                        text=[f"<b>{p} pts</b>" for p in df_gw_bar["GW Points"]],
                        textposition="outside",
                        hoverinfo="text",
                        hovertext=[f"<b>{r['Team Name']}</b> ({r['Manager']})<br>GW Points: <b>{r['GW Points']}</b>" for _, r in df_gw_bar.iterrows()]
                    ))
                    if avg_gw > 0:
                        fig_standings_gw.add_vline(
                            x=avg_gw,
                            line_dash="dash",
                            line_color="#f59e0b",
                            annotation_text=f"GW Avg: {avg_gw:.1f} pts",
                            annotation_position="top right",
                            annotation_font=dict(color="#fbbf24", size=11)
                        )
                    fig_standings_gw.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="rgba(15, 23, 42, 0.6)",
                        plot_bgcolor="rgba(15, 23, 42, 0.6)",
                        yaxis=dict(autorange="reversed"),
                        xaxis=dict(title="Gameweek Points", showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
                        margin=dict(l=20, r=40, t=30, b=20),
                        height=380
                    )
                    st.plotly_chart(fig_standings_gw, use_container_width=True)

                st.markdown("---")

                # -------------------------------------------------------------
                # Mini-League Performance Trajectory Over Time Charts
                # -------------------------------------------------------------
                st.subheader("📈 Mini-League Performance Trajectory Over Time")
                st.markdown("Interactive time-series progression analyzing cumulative championship points, weekly scoring momentum, and mini-league rank volatility.")

                try:
                    with st.spinner("Compiling gameweek-by-gameweek rival histories..."):
                        perf_data = load_league_history(active_league_id, max_teams=len(teams))
                    
                    hist_df = perf_data.get("df", pd.DataFrame())
                    chips_map = perf_data.get("chips", {})

                    if not hist_df.empty:
                        c_tabs = st.tabs([
                            "🚀 Cumulative Points Progression",
                            "⚡ Weekly Gameweek Scores",
                            "🏅 Mini-League Rank Swings"
                        ])

                        # Tab 1: Cumulative Points
                        with c_tabs[0]:
                            st.markdown("#### The Championship Race — Cumulative Points (GW1 ➔ Present)")
                            fig_cum = px.line(
                                hist_df,
                                x="gameweek",
                                y="cumulative_points",
                                color="team_name",
                                markers=True,
                                labels={"gameweek": "Gameweek", "cumulative_points": "Total Points", "team_name": "Team"},
                                hover_data={"gw_points": True, "cumulative_points": True}
                            )

                            for tr in fig_cum.data:
                                if tr.name == "Rubies Rangers":
                                    tr.line.width = 4.5
                                    tr.marker.size = 11
                                    tr.line.color = "#facc15"  # Glowing Gold
                                else:
                                    tr.line.width = 2.0
                                    tr.marker.size = 6

                            # Chip callouts
                            for t_name, c_list in chips_map.items():
                                for ch in c_list:
                                    ev = ch.get("event")
                                    ch_code = ch.get("name", "").upper()
                                    if ch_code == "3XC":
                                        b_text = f"🔥 3XC ({t_name})"
                                    elif ch_code == "BBOOST":
                                        b_text = f"⚡ Bench Boost ({t_name})"
                                    elif ch_code == "WILDCARD":
                                        b_text = f"🃏 Wildcard ({t_name})"
                                    elif ch_code == "FREEHIT":
                                        b_text = f"🆓 Free Hit ({t_name})"
                                    else:
                                        b_text = f"🎯 {ch_code} ({t_name})"

                                    sub_m = hist_df[(hist_df["team_name"] == t_name) & (hist_df["gw_num"] == ev)]
                                    if not sub_m.empty:
                                        y_pt = sub_m.iloc[0]["cumulative_points"]
                                        fig_cum.add_annotation(
                                            x=f"GW{ev}",
                                            y=y_pt,
                                            text=b_text,
                                            showarrow=True,
                                            arrowhead=2,
                                            arrowcolor="#f43f5e",
                                            font=dict(size=10, color="#ffffff"),
                                            bgcolor="rgba(244, 63, 94, 0.85)",
                                            bordercolor="#ffffff",
                                            borderwidth=1,
                                            borderpad=3,
                                            ay=-32
                                        )

                            fig_cum.update_layout(
                                template="plotly_dark",
                                paper_bgcolor="rgba(15, 23, 42, 0.6)",
                                plot_bgcolor="rgba(15, 23, 42, 0.6)",
                                hovermode="x unified",
                                margin=dict(l=20, r=20, t=30, b=20),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            st.plotly_chart(fig_cum, use_container_width=True)

                        # Tab 2: Weekly Scores
                        with c_tabs[1]:
                            st.markdown("#### Weekly Scoring Momentum — Gameweek Points")
                            fig_gw = px.bar(
                                hist_df,
                                x="gameweek",
                                y="gw_points",
                                color="team_name",
                                barmode="group",
                                labels={"gameweek": "Gameweek", "gw_points": "Gameweek Points", "team_name": "Team"},
                                hover_data={"gw_points": True, "cumulative_points": True}
                            )
                            fig_gw.update_layout(
                                template="plotly_dark",
                                paper_bgcolor="rgba(15, 23, 42, 0.6)",
                                plot_bgcolor="rgba(15, 23, 42, 0.6)",
                                margin=dict(l=20, r=20, t=30, b=20),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            st.plotly_chart(fig_gw, use_container_width=True)

                            # Highlight Rubies Rangers GW3 performance
                            rr_gw3 = hist_df[(hist_df["team_name"] == "Rubies Rangers") & (hist_df["gw_num"] == 3)]
                            if not rr_gw3.empty:
                                pts3 = int(rr_gw3.iloc[0]["gw_points"])
                                st.info(f"💡 **MONEYBALL MOMENTUM:** In Gameweek 3, **Rubies Rangers scored {pts3} points** — outscoring league leader *Brennans Bread Today* (56 pts, **+8 advantage**) and rival *IraolaCoaster* (62 pts) despite their active Triple Captain chip!")

                        # Tab 3: Rank Swings
                        with c_tabs[2]:
                            st.markdown("#### Table Position Volatility — Mini-League Rank by Gameweek")
                            fig_rank = px.line(
                                hist_df,
                                x="gameweek",
                                y="league_rank",
                                color="team_name",
                                markers=True,
                                labels={"gameweek": "Gameweek", "league_rank": "Mini-League Rank", "team_name": "Team"}
                            )

                            for tr in fig_rank.data:
                                if tr.name == "Rubies Rangers":
                                    tr.line.width = 4.5
                                    tr.marker.size = 11
                                    tr.line.color = "#facc15"
                                else:
                                    tr.line.width = 2.0
                                    tr.marker.size = 6

                            max_rank = int(hist_df["league_rank"].max())
                            fig_rank.update_yaxes(
                                autorange="reversed",
                                tickmode="linear",
                                tick0=1,
                                dtick=1,
                                range=[max_rank + 0.5, 0.5]
                            )
                            fig_rank.update_layout(
                                template="plotly_dark",
                                paper_bgcolor="rgba(15, 23, 42, 0.6)",
                                plot_bgcolor="rgba(15, 23, 42, 0.6)",
                                hovermode="x unified",
                                margin=dict(l=20, r=20, t=30, b=20),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            st.plotly_chart(fig_rank, use_container_width=True)

                    else:
                        st.info("No historical gameweek data found for these teams.")
                except Exception as e:
                    st.warning(f"Could not render historical charts: {e}")

                st.markdown("---")

                # Rival Squad Spy
                st.subheader("🕵️ Rival Squad Spy — Inspect Formation, Captain & Bench")
                st.markdown("Select any competitor from your league to inspect their exact 15-player lineup, active chips, and captaincy choice.")

                team_options = {f"#{t['rank']} — {t['team_name']} ({t['manager_name']})": t['entry_id'] for t in teams}
                selected_team_label = st.selectbox("Select Rival Team to Spy On:", list(team_options.keys()))
                rival_entry_id = team_options[selected_team_label]

                try:
                    with st.spinner("Scouting rival squad & tactical picks..."):
                        rival_picks = load_team_picks(rival_entry_id)

                    gw_num = rival_picks["gameweek"]
                    r_cap = rival_picks["captain"]
                    r_vc = rival_picks["vice_captain"]
                    chip = rival_picks.get("active_chip")
                    chip_badge = f'<span style="background: #e11d48; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px;">🔥 {chip.upper()}</span>' if chip else '<span style="color: #94a3b8;">None</span>'

                    # Rival Meta Banner
                    render_html(f"""
                    <div style="background: #1e293b; border-left: 4px solid #f59e0b; padding: 14px 18px; border-radius: 8px; margin-bottom: 20px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                            <div>
                                <b style="color: #ffffff; font-size: 16px;">Gameweek {gw_num} Lineup & Tactics</b><br/>
                                <span style="color: #cbd5e1; font-size: 13px;">Active Chip: {chip_badge} | Transfers: <b style="color: white;">{rival_picks['transfers']} (-{rival_picks['transfer_cost']} pts)</b></span>
                            </div>
                            <div style="text-align: right;">
                                <span style="color: #cbd5e1; font-size: 13px;">★ Captain: <b style="color: #f87171; font-size: 14px;">{r_cap['web_name'] if r_cap else 'N/A'} ({r_cap['club'] if r_cap else ''})</b></span><br/>
                                <span style="color: #cbd5e1; font-size: 13px;">☆ Vice: <b style="color: #60a5fa; font-size: 14px;">{r_vc['web_name'] if r_vc else 'N/A'} ({r_vc['club'] if r_vc else ''})</b></span>
                            </div>
                        </div>
                    </div>
                    """)

                    # Starters & Bench in columns
                    starters = rival_picks.get("starters", [])
                    bench = rival_picks.get("bench", [])

                    st.markdown("#### ⚡ Starting XI")
                    s_cols = st.columns(4)
                    for idx, pos in enumerate(["GKP", "DEF", "MID", "FWD"]):
                        with s_cols[idx]:
                            st.markdown(f"**{pos}**")
                            p_list = [p for p in starters if p["pos"] == pos]
                            for p in p_list:
                                role_badge = ""
                                border = "#3b82f6"
                                if p["is_captain"]:
                                    role_badge = '<span style="background: #ef4444; color: white; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; margin-left: 6px;">(C)</span>'
                                    border = "#ef4444"
                                elif p["is_vice_captain"]:
                                    role_badge = '<span style="background: #3b82f6; color: white; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; margin-left: 6px;">(VC)</span>'
                                    border = "#60a5fa"

                                render_html(f"""
                                <div class="squad-player-card" style="background: #1e293b; border-left: 4px solid {border}; color: #ffffff; padding: 10px 12px; border-radius: 8px; margin-bottom: 8px;">
                                    <b style="color: #ffffff; font-size: 14px;">{p['web_name']}</b>{role_badge} <span style="color: #94a3b8; font-size: 11px;">({p['club']})</span><br/>
                                    <span style="color: #cbd5e1; font-size: 12px;">Price: <b style="color: #ffffff;">£{p['cost']:.1f}m</b></span>
                                </div>
                                """)

                    st.markdown("#### 🪑 Substitutes Bench")
                    b_cols = st.columns(4)
                    for idx, p in enumerate(bench):
                        with b_cols[idx]:
                            render_html(f"""
                            <div class="bench-card" style="background: #1e293b; border: 1px solid #334155; padding: 10px; border-radius: 8px; text-align: center; margin-bottom: 8px;">
                                <small style="color: #94a3b8; font-weight: bold;">Sub {idx + 1} • {p['pos']}</small><br/>
                                <b style="color: #ffffff; font-size: 14px;">{p['web_name']}</b><br/>
                                <small style="color: #cbd5e1;">{p['club']} | £{p['cost']:.1f}m</small>
                            </div>
                            """)

                    # Tactical Head-to-Head Comparison with Rubies Rangers
                    st.markdown("---")
                    st.subheader("⚔️ Head-to-Head Tactical Delta vs Rubies Rangers")
                    st.markdown("Comparing this rival's 15 players directly against your **Rubies Rangers** squad:")

                    rival_player_names = {p["web_name"].lower() for p in (starters + bench)}
                    rubies_names = {p.lower(): p for p in DEFAULT_SQUAD}

                    shared = []
                    for r_name_low, r_name_orig in rubies_names.items():
                        if any(r_name_low in rival_name for rival_name in rival_player_names):
                            shared.append(r_name_orig)

                    rival_unique = []
                    for p in (starters + bench):
                        p_low = p["web_name"].lower()
                        if not any(r_low in p_low for r_low in rubies_names.keys()):
                            role_tag = " (C)" if p["is_captain"] else ""
                            rival_unique.append(f"{p['web_name']} ({p['club']}){role_tag}")

                    rubies_unique = []
                    for r_name_low, r_name_orig in rubies_names.items():
                        if not any(r_name_low in rival_name for rival_name in rival_player_names):
                            rubies_unique.append(r_name_orig)

                    h1, h2, h3 = st.columns(3)
                    with h1:
                        render_html(f"""
                        <div style="background: #1e293b; border-top: 4px solid #10b981; padding: 14px; border-radius: 8px;">
                            <b style="color: #34d399; font-size: 15px;">🤝 Mutual Cover ({len(shared)} Players)</b><br/>
                            <span style="color: #94a3b8; font-size: 12px;">Both you and this rival own these players (neutral impact):</span>
                            <div style="margin-top: 10px; color: #ffffff; font-size: 13px; line-height: 1.6;">
                                {"<br/>".join(f"• <b>{name}</b>" for name in shared) if shared else "<i>No overlap</i>"}
                            </div>
                        </div>
                        """)

                    with h2:
                        render_html(f"""
                        <div style="background: #1e293b; border-top: 4px solid #ef4444; padding: 14px; border-radius: 8px;">
                            <b style="color: #f87171; font-size: 15px;">⚠️ Rival Threats ({len(rival_unique)} Players)</b><br/>
                            <span style="color: #94a3b8; font-size: 12px;">Rival owns, Rubies Rangers does NOT (rank hazards):</span>
                            <div style="margin-top: 10px; color: #ffffff; font-size: 13px; line-height: 1.6;">
                                {"<br/>".join(f"• <b>{name}</b>" for name in rival_unique) if rival_unique else "<i>None</i>"}
                            </div>
                        </div>
                        """)

                    with h3:
                        render_html(f"""
                        <div style="background: #1e293b; border-top: 4px solid #38bdf8; padding: 14px; border-radius: 8px;">
                            <b style="color: #38bdf8; font-size: 15px;">🚀 Rubies Rangers Weapons ({len(rubies_unique)} Players)</b><br/>
                            <span style="color: #94a3b8; font-size: 12px;">YOU own, rival does NOT (your differential leverage):</span>
                            <div style="margin-top: 10px; color: #ffffff; font-size: 13px; line-height: 1.6;">
                                {"<br/>".join(f"• <b>{name}</b>" for name in rubies_unique) if rubies_unique else "<i>None</i>"}
                            </div>
                        </div>
                        """)

                except Exception as e:
                    st.error(f"Error fetching rival picks: {e}")

                # Effective Ownership Matrix
                st.markdown("---")
                st.subheader("📊 Mini-League Effective Ownership (EO%) Matrix")
                st.markdown("""
                **Effective Ownership (EO% = Starting % + Captaincy %):**
                - If a player has **>100% EO**, you lose net rank if they score and you haven't captained them.
                - If a player has **<25% EO**, any return provides massive mathematical upside over your mini-league rivals!
                """)

                max_scout_teams = st.slider("Number of Rival Teams to Sample for Ownership:", 5, min(50, len(teams)), min(20, len(teams)))
                if st.button("⚡ Calculate Mini-League Effective Ownership", type="primary"):
                    with st.spinner(f"Computing Effective Ownership across top {max_scout_teams} rival teams..."):
                        eo_df = load_league_ownership(active_league_id, max_teams=max_scout_teams)

                    if not eo_df.empty:
                        st.dataframe(eo_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("Could not calculate ownership matrix.")
        except Exception as e:
            st.error(f"Error loading mini-league: {e}")

elif mode == "🎰 Bookmaker Odds & Expected Points (xP)":
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

elif mode == "🎲 Monte Carlo Transfer Simulator":
    st.title("🎲 Monte Carlo Transfer Engine & Stochastic Simulation")
    st.markdown(r"""
    **Moneyball Philosophy:** Traditional fantasy optimizers rely on static expected points ($xP$). But football outcomes are **skewed, discrete Poisson & Bernoulli distributions**. 
    
    This engine runs **up to 10,000 parallel gameweek simulations** testing candidate transfers across bookmaker odds ($\lambda_{\text{team}}$), Understat tactical metrics (NPxG/xA), penalty duties, minutes security (starts vs cameos), and automatic bench substitutions.
    """)

    # Filter & Simulation Control Panel
    with st.expander("⚙️ Simulation Settings & Constraints", expanded=True):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            mc_transfers = st.radio("Number of Transfers", [1, 2], format_func=lambda x: f"{x} Transfer{' (Single Swap)' if x==1 else 's (Double Move)'}", horizontal=True)
            mc_free = st.slider("Free Transfers Available", 1, 5, 1, help="If transfers made exceed free quota, a -4 point hit penalty is deducted from the simulation.")
        with sc2:
            mc_bank = st.slider("Bank Balance (£m)", 0.0, 15.0, 3.7, 0.1)
            mc_sims = st.select_slider("Simulation Count", options=[1000, 2500, 5000, 10000], value=2500, help="Higher simulation counts yield tighter probability confidence intervals.")
        with sc3:
            mc_pos = st.selectbox("Position Filter", ["ALL", "GKP", "DEF", "MID", "FWD"], help="Filter candidate transfers by position.")
            sell_options = ["All Squad Players"] + DEFAULT_SQUAD
            mc_sell_choice = st.selectbox("Sell Target Filter", sell_options, help="Filter transfers to sell a specific player (e.g. benched Senesi or Solanke).")
            mc_sell = None if mc_sell_choice == "All Squad Players" else mc_sell_choice

        mc_strict = st.checkbox(
            "Strict Hygiene: Purge Injured, Suspended & Transferred-Out Players",
            value=True,
            help="Strictly removes all players with status 'u' (unavailable/left the PL), 'i' (injured), 's' (suspended), or chance_of_playing == 0%."
        )

    hit_penalty = max(0, mc_transfers - mc_free) * 4
    if hit_penalty > 0:
        st.warning(f"⚠️ **Transfer Hit Penalty Active:** Making {mc_transfers} transfer(s) with {mc_free} free transfer incurs a **-{hit_penalty} point deduction**, which has been factored directly into all simulation outcomes.")

    with st.spinner(f"Running {mc_sims:,} Monte Carlo simulations across candidate transfer permutations..."):
        mc_res = load_montecarlo_simulation(
            bank=mc_bank,
            num_transfers=mc_transfers,
            free_transfers=mc_free,
            n_sims=mc_sims,
            pos_filter=mc_pos,
            sell_filter=mc_sell,
            strict_filter=mc_strict
        )

    if not mc_res.get("success"):
        st.error(f"❌ {mc_res.get('message', 'No valid transfers found within budget and constraints.')}")
    else:
        base = mc_res["baseline"]
        top_3 = mc_res["top_3"]
        df_all = mc_res["all_results_df"]
        best_opt = top_3[0]

        # Hero KPIs Container
        hk1, hk2, hk3, hk4, hk5 = st.columns(5)
        hk1.metric("Baseline Squad xP", f"{base['mean']:.1f} pts", f"P10: {base['p10']} | P90: {base['p90']}")
        hk2.metric("Transfer Hit Penalty", f"-{hit_penalty} pts", "Free" if hit_penalty == 0 else f"{mc_transfers - mc_free} hit(s)")
        hk3.metric("Max EV Net Gain", f"{best_opt['net_mean_gain']:+.2f} pts", f"{best_opt['transfer_type']}")
        hk4.metric("Top Win Probability", f"{best_opt['win_prob']:.1f}%", "Beats Current Squad")
        hk5.metric("Bank Remaining", f"£{best_opt['bank_remaining']:.1f}m", f"Δ {best_opt['cost_diff']:+.1f}m")

        st.markdown("---")

        # -------------------------------------------------------------
        # Section 1: The 3 Best Transfer Archetypes Cards
        # -------------------------------------------------------------
        st.subheader("✨ The 3 Best Strategic Transfer Options (Monte Carlo Modeled)")
        st.markdown("Unlike simple linear models, the Monte Carlo optimizer surfaces 3 mathematically distinct transfer archetypes:")

        card_col1, card_col2, card_col3 = st.columns(3)

        for col, opt, badge_title, border_color in [
            (card_col1, top_3[0], "OPTION 1: 🏆 MAX EXPECTED VALUE", "#facc15"),
            (card_col2, top_3[1], "OPTION 2: 🛡️ MAX FLOOR & SAFETY", "#10b981"),
            (card_col3, top_3[2], "OPTION 3: 🚀 MAX CEILING & DIFFERENTIAL", "#a855f7")
        ]:
            with col:
                hit_badge = f'<span style="background: #dc2626; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 6px;">-{opt["hit_penalty"]} pts hit</span>' if opt["hit_penalty"] > 0 else '<span style="background: #15803d; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 6px;">Free Move</span>'
                render_html(f"""
                <div style="background: #1e293b; border: 2px solid {border_color}; border-radius: 12px; padding: 16px; min-height: 380px; display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <b style="color: {border_color}; font-size: 13px; text-transform: uppercase;">{badge_title}</b>
                            {hit_badge}
                        </div>
                        <div style="background: #0f172a; padding: 10px; border-radius: 8px; margin-bottom: 12px; border-left: 3px solid #ef4444;">
                            <span style="color: #ef4444; font-size: 11px; font-weight: bold; text-transform: uppercase;">SELL OUT</span><br/>
                            <b style="color: #ffffff; font-size: 16px;">{opt['out_player']}</b> <span style="color: #94a3b8; font-size: 12px;">({opt['out_club']} • £{opt['out_cost']}m)</span><br/>
                            <span style="color: #94a3b8; font-size: 12px;">Baseline Simulated: <b style="color: #cbd5e1;">{opt['out_mean']:.2f} pts</b></span>
                        </div>
                        <div style="background: #0f172a; padding: 10px; border-radius: 8px; margin-bottom: 12px; border-left: 3px solid #22c55e;">
                            <span style="color: #22c55e; font-size: 11px; font-weight: bold; text-transform: uppercase;">BUY IN</span><br/>
                            <b style="color: #ffffff; font-size: 16px;">{opt['in_player']}</b> <span style="color: #94a3b8; font-size: 12px;">({opt['in_club']} • £{opt['in_cost']}m)</span><br/>
                            <span style="color: #94a3b8; font-size: 12px;">Simulated Projection: <b style="color: #22c55e;">{opt['in_mean']:.2f} pts</b></span>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; background: rgba(15, 23, 42, 0.6); padding: 8px; border-radius: 8px;">
                            <div><span style="color: #94a3b8; font-size: 11px;">Net Gain:</span><br/><b style="color: {border_color}; font-size: 16px;">{opt['net_mean_gain']:+.2f} pts</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Win Probability:</span><br/><b style="color: #38bdf8; font-size: 16px;">{opt['win_prob']:.1f}%</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Floor (P10):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{opt['floor_p10']} pts</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Ceiling (P90):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{opt['ceiling_p90']} pts</b></div>
                        </div>
                    </div>
                    <div>
                        <div style="color: #cbd5e1; font-size: 12px; line-height: 1.4; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">
                            <i>{opt['rationale']}</i>
                        </div>
                        <div style="margin-top: 8px; text-align: right;">
                            <span style="color: #94a3b8; font-size: 11px;">Bank Left: <b style="color: white;">£{opt['bank_remaining']:.1f}m</b></span>
                        </div>
                    </div>
                </div>
                """)

        st.markdown("---")

        # -------------------------------------------------------------
        # Section 2: Interactive Graphical Visualizations
        # -------------------------------------------------------------
        st.subheader("📊 Interactive Stochastic Analysis & Visualizations")
        
        gv_tab1, gv_tab2, gv_tab3 = st.tabs([
            "📈 Score Distribution Density (KDE Curves)",
            "📊 Percentile Range Comparison (P10 vs P50 vs P90)",
            "🎯 Risk vs. Reward Scatter Matrix"
        ])

        with gv_tab1:
            st.markdown("#### Probability Density of Total Squad Gameweek Points")
            st.markdown("Compares the full probability distributions across all simulated matches. Shift to the right = higher expected score; taller curve = lower variance.")

            fig_dist = go.Figure()

            # Baseline distribution
            fig_dist.add_trace(go.Histogram(
                x=base["raw_totals"],
                histnorm="probability density",
                name="Current Squad (Baseline)",
                marker_color="#94a3b8",
                opacity=0.35,
                nbinsx=40
            ))

            # Option 1 Max EV
            fig_dist.add_trace(go.Histogram(
                x=top_3[0]["raw_totals"],
                histnorm="probability density",
                name=f"Option 1: Max EV ({top_3[0]['in_player']})",
                marker_color="#facc15",
                opacity=0.45,
                nbinsx=40
            ))

            # Option 2 Max Floor
            fig_dist.add_trace(go.Histogram(
                x=top_3[1]["raw_totals"],
                histnorm="probability density",
                name=f"Option 2: Max Floor ({top_3[1]['in_player']})",
                marker_color="#10b981",
                opacity=0.45,
                nbinsx=40
            ))

            # Option 3 Max Ceiling
            fig_dist.add_trace(go.Histogram(
                x=top_3[2]["raw_totals"],
                histnorm="probability density",
                name=f"Option 3: Max Ceiling ({top_3[2]['in_player']})",
                marker_color="#a855f7",
                opacity=0.45,
                nbinsx=40
            ))

            # Add vertical lines for means
            fig_dist.add_vline(x=base["mean"], line_dash="dash", line_color="#94a3b8", annotation_text=f"Base: {base['mean']:.1f}", annotation_position="top left")
            fig_dist.add_vline(x=top_3[0]["new_mean"], line_dash="dash", line_color="#facc15", annotation_text=f"Opt 1: {top_3[0]['new_mean']:.1f}", annotation_position="top right")

            fig_dist.update_layout(
                barmode="overlay",
                paper_bgcolor="#0b0f19",
                plot_bgcolor="#1e293b",
                font={"color": "#f8fafc"},
                xaxis={"title": "Total Gameweek Squad Points", "gridcolor": "rgba(255,255,255,0.08)"},
                yaxis={"title": "Probability Density", "gridcolor": "rgba(255,255,255,0.08)"},
                legend={"orientation": "h", "y": 1.15, "x": 0.0},
                height=450,
                margin={"l": 20, "r": 20, "t": 40, "b": 20}
            )
            st.plotly_chart(fig_dist, use_container_width=True)

        with gv_tab2:
            st.markdown("#### Squad Points Range: Floor (P10) ➔ Median (P50) ➔ Ceiling (P90)")
            st.markdown("Visualizes downside risk protection vs explosive haul ceiling across each strategic option.")

            comp_names = [
                "Current Baseline",
                f"Opt 1: {top_3[0]['in_player']} (EV)",
                f"Opt 2: {top_3[1]['in_player']} (Floor)",
                f"Opt 3: {top_3[2]['in_player']} (Ceiling)"
            ]
            p10_vals = [base["p10"], top_3[0]["floor_p10"], top_3[1]["floor_p10"], top_3[2]["floor_p10"]]
            p50_vals = [base["p50"], top_3[0]["median_p50"], top_3[1]["median_p50"], top_3[2]["median_p50"]]
            p90_vals = [base["p90"], top_3[0]["ceiling_p90"], top_3[1]["ceiling_p90"], top_3[2]["ceiling_p90"]]

            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                name="P10 Floor (Safety Net)",
                y=comp_names,
                x=p10_vals,
                orientation="h",
                marker_color="#38bdf8",
                text=[f"{v:.0f}" for v in p10_vals],
                textposition="inside"
            ))
            fig_bar.add_trace(go.Bar(
                name="P50 Median (Expected)",
                y=comp_names,
                x=[p50 - p10 for p50, p10 in zip(p50_vals, p10_vals)],
                base=p10_vals,
                orientation="h",
                marker_color="#facc15",
                text=[f"{v:.0f}" for v in p50_vals],
                textposition="inside"
            ))
            fig_bar.add_trace(go.Bar(
                name="P90 Ceiling (Haul Potential)",
                y=comp_names,
                x=[p90 - p50 for p90, p50 in zip(p90_vals, p50_vals)],
                base=p50_vals,
                orientation="h",
                marker_color="#ec4899",
                text=[f"{v:.0f}" for v in p90_vals],
                textposition="inside"
            ))

            fig_bar.update_layout(
                barmode="stack",
                paper_bgcolor="#0b0f19",
                plot_bgcolor="#1e293b",
                font={"color": "#f8fafc"},
                xaxis={"title": "Simulated Squad Points", "gridcolor": "rgba(255,255,255,0.08)"},
                yaxis={"title": "", "gridcolor": "rgba(255,255,255,0.08)", "autorange": "reversed"},
                legend={"orientation": "h", "y": 1.15, "x": 0.0},
                height=380,
                margin={"l": 20, "r": 20, "t": 40, "b": 20}
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with gv_tab3:
            st.markdown("#### Risk vs. Reward Efficiency Frontier (All Evaluated Transfers)")
            st.markdown("Each bubble represents a legal transfer move. Top-right = High Gain & High Safety Floor; Larger bubble = Greater 90th-percentile haul upside.")

            fig_scatter = px.scatter(
                df_all,
                x="floor_p10",
                y="net_mean_gain",
                size="ceiling_p90",
                color="win_prob",
                hover_name="in_player",
                hover_data={
                    "out_player": True,
                    "in_club": True,
                    "net_mean_gain": ":+.2f",
                    "win_prob": ":.1f%",
                    "cost_diff": ":+.1f",
                    "bank_remaining": ":.1f",
                    "floor_p10": True,
                    "ceiling_p90": True
                },
                labels={
                    "floor_p10": "10th-Percentile Floor (Downside Safety)",
                    "net_mean_gain": "Net Expected Gain (pts/GW)",
                    "win_prob": "Win Probability %",
                    "ceiling_p90": "90th-Percentile Ceiling"
                },
                color_continuous_scale="Viridis"
            )

            fig_scatter.add_hline(y=0, line_dash="dash", line_color="#ef4444", annotation_text="Break-Even (0 Net Gain)")

            fig_scatter.update_layout(
                paper_bgcolor="#0b0f19",
                plot_bgcolor="#1e293b",
                font={"color": "#f8fafc"},
                xaxis={"gridcolor": "rgba(255,255,255,0.08)"},
                yaxis={"gridcolor": "rgba(255,255,255,0.08)"},
                height=450,
                margin={"l": 20, "r": 20, "t": 20, "b": 20}
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        st.markdown("---")

        # -------------------------------------------------------------
        # Section 3: Comprehensive Transfer Candidates Table
        # -------------------------------------------------------------
        st.subheader(f"📋 Comprehensive Evaluated Transfers Matrix ({len(df_all)} Legal Moves)")
        st.markdown("Search, sort, and inspect every legal transfer option tested by the Monte Carlo engine.")

        display_cols = [
            "out_player", "in_player", "in_pos", "in_club", "cost_diff", "bank_remaining",
            "net_mean_gain", "win_prob", "floor_p10", "median_p50", "ceiling_p90", "sharpe", "fdr_next_5"
        ]
        renames = {
            "out_player": "Sell Out",
            "in_player": "Buy In",
            "in_pos": "Pos",
            "in_club": "Club",
            "cost_diff": "Cost Δ (£m)",
            "bank_remaining": "Bank Left (£m)",
            "net_mean_gain": "Net Gain (pts)",
            "win_prob": "Win Prob %",
            "floor_p10": "P10 Floor",
            "median_p50": "P50 Median",
            "ceiling_p90": "P90 Ceiling",
            "sharpe": "Sharpe Ratio",
            "fdr_next_5": "FDR Next 5"
        }

        df_display = df_all[display_cols].rename(columns=renames)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # CSV Download Button
        csv_data = df_display.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Full Monte Carlo Transfer Evaluation (CSV)",
            data=csv_data,
            file_name=f"monte_carlo_transfers_{mc_transfers}x_sim{mc_sims}.csv",
            mime="text/csv"
        )

elif mode == "🛡️ Monte Carlo Lineup & Substitution Strategist":
    st.title("🛡️ Monte Carlo Lineup, Bench & Captaincy Strategist")
    st.markdown(r"""
    **Moneyball Tactical Optimization:** Standard fantasy managers pick their starting XI based on past points or gut feel. 
    This engine executes **2,500+ parallel Monte Carlo stochastic simulations** across every match in the upcoming gameweek to solve four interdependent problems simultaneously:
    - **Formation Optimization:** Tests all 8 legal FPL formations (3-5-2, 3-4-3, 4-4-2, 4-5-1, 4-3-3, 5-3-2, 5-4-1, 5-2-3) to find the mathematical maximum expected output.
    - **Bench Substitution Activation ($P(\text{Subbed In})$):** Calculates the exact empirical probability that each substitute enters the match, strictly enforcing Premier League formation legality (minimum 3 defenders, 2 midfielders, 1 forward).
    - **Captaincy Head-to-Head Duel & Fallback Protection:** Simulates captain score distributions head-to-head ($P(\text{Cap} > \text{VC})$) and automatically triggers the vice-captain 2x fallback if the captain plays zero minutes.
    - **Disciplinary & Injury Risk Modeling:** Incorporates red card odds (-3 points and clean sheet forfeiture), yellow card suspensions, injury flags, and recent minutes security.
    """)

    # Simulation Controls
    with st.expander("⚙️ Lineup Simulation Settings & Risk Parameters", expanded=True):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            mc_lineup_sims = st.select_slider(
                "Simulation Iterations",
                options=[1000, 2500, 5000, 10000],
                value=2500,
                help="Number of stochastic trials simulated across the entire squad."
            )
        with sc2:
            mc_form_weight = st.slider(
                "Recent Form Weight",
                min_value=0.0,
                max_value=0.50,
                value=0.25,
                step=0.05,
                help="Weight assigned to player recent form (3-match rolling performance) blended with fixture expectancy."
            )
        with sc3:
            mc_disciplinary = st.checkbox(
                "Model In-Match Red Cards & Yellows",
                value=True,
                help="Simulates match red cards (-3 pts, clean sheet forfeit, sub prevention) and yellow card accumulation."
            )

    with st.spinner(f"Running {mc_lineup_sims:,} Monte Carlo simulations to optimize Starting XI, bench hierarchy, and captaincy..."):
        lineup_res = load_montecarlo_lineup(
            squad_names=tuple(current_squad),
            n_sims=mc_lineup_sims,
            form_weight=mc_form_weight,
            include_disciplinary=mc_disciplinary
        )

    sq_sum = lineup_res["squad_summary"]
    opt_form = lineup_res["optimal_formation"]
    cap_duel = lineup_res["captaincy_duel"]
    cap_info = cap_duel["captain"]
    vc_info = cap_duel["vice_captain"]
    bench_data = lineup_res["bench"]
    starters_data = lineup_res["starters"]
    checklist = lineup_res["move_around_checklist"]

    # Hero KPI Summary Cards
    hk1, hk2, hk3, hk4 = st.columns(4)
    hk1.metric(
        "Optimal Formation",
        f"{opt_form}",
        delta="Beats 7 Other Formations"
    )
    hk2.metric(
        "Expected Lineup Total",
        f"{sq_sum['mean_total']:.1f} pts",
        delta=f"P10 Floor: {sq_sum['floor_p10']} | P90 Ceiling: {sq_sum['ceiling_p90']}"
    )
    hk3.metric(
        "Designated Captain (C)",
        f"{cap_info['web_name']}",
        delta=f"{cap_info['mean_captain_pts']:.1f} pts (2x) • {cap_info['haul_prob_pct']}% Haul"
    )
    hk4.metric(
        "Primary Bench Cover (Sub 1)",
        f"{bench_data[0]['web_name']}",
        delta=f"{bench_data[0]['activation_prob_pct']}% Auto-Sub • +{bench_data[0]['points_saved_mean']:.1f} EV"
    )

    st.markdown("---")

    # -------------------------------------------------------------
    # Section 1: What to Move Around (Actionable Checklist)
    # -------------------------------------------------------------
    st.subheader("📋 What to Move Around (Actionable Pre-Deadline Checklist)")
    st.markdown("Step-by-step instructions to configure Rubies Rangers for optimal expected return and risk mitigation:")

    for item in checklist:
        cat = item.get("category", "")
        if "BENCH" in cat and "ORDER" not in cat:
            badge_class = "badge-step-red"
            border_color = "#ef4444"
        elif "START" in cat:
            badge_class = "badge-step-green"
            border_color = "#10b981"
        elif "ORDER" in cat or "SUB" in cat:
            badge_class = "badge-step-yellow"
            border_color = "#f59e0b"
        elif "VICE" in cat:
            badge_class = "badge-step-purple"
            border_color = "#a855f7"
        else:
            badge_class = "badge-step-blue"
            border_color = "#3b82f6"

        render_html(f"""
        <div class="step-card" style="border-left: 5px solid {border_color};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-weight: 700; font-size: 16px; color: #ffffff;">Step {item['step']}: {item['action']}</span>
                <span class="{badge_class}">{item['badge']}</span>
            </div>
            <div style="color: #cbd5e1; font-size: 13px; line-height: 1.5;">
                {item['reason']}
            </div>
        </div>
        """)

    st.markdown("---")

    # -------------------------------------------------------------
    # Section 2: Suggested Starting XI Tactical Pitch
    # -------------------------------------------------------------
    st.subheader(f"🏟️ Suggested Starting XI ({opt_form} Formation)")
    st.markdown("Simulated starting lineup optimized for expected points, fixture difficulty, and minutes security:")

    # Group starters by position
    starters_df = pd.DataFrame(starters_data)
    fwds = starters_df[starters_df["pos"] == "FWD"]
    mids = starters_df[starters_df["pos"] == "MID"]
    defs = starters_df[starters_df["pos"] == "DEF"]
    gkps = starters_df[starters_df["pos"] == "GKP"]

    def _render_mc_pitch_card(p):
        is_cap = (p["web_name"] == cap_info["web_name"])
        is_vc = (p["web_name"] == vc_info["web_name"])
        
        badge_html = ""
        if is_cap:
            badge_html = '<div class="captain-badge">★ CAPTAIN (C)</div><br/>'
        elif is_vc:
            badge_html = '<div class="vc-badge">☆ VICE-CAPTAIN (VC)</div><br/>'

        card_warning = ""
        yc_raw = p.get("yellow_cards", 0)
        yc = int(yc_raw) if (yc_raw is not None and pd.notna(yc_raw)) else 0
        if yc >= 2:
            card_warning = f'<small style="color: #fef08a;">⚠️ {yc} Yellows</small><br/>'

        cop_raw = p.get("cop", 100)
        cop = int(cop_raw) if (cop_raw is not None and pd.notna(cop_raw)) else 100
        cop_warning = ""
        if cop < 100:
            cop_warning = f'<small style="color: #f87171;">⚠️ {cop}% Fit</small><br/>'

        fdr_raw = p.get("fdr", 3)
        fdr_val = float(fdr_raw) if (fdr_raw is not None and pd.notna(fdr_raw)) else 3.0
        fdr_class = "badge-fdr-easy" if fdr_val <= 2.5 else ("badge-fdr-med" if fdr_val <= 3.2 else "badge-fdr-hard")

        form_raw = p.get("form", 0.0)
        form_val = float(form_raw) if (form_raw is not None and pd.notna(form_raw)) else 0.0

        p10_raw = p.get("p10", 0.0)
        p10_val = float(p10_raw) if (p10_raw is not None and pd.notna(p10_raw)) else 0.0

        p90_raw = p.get("p90", 0.0)
        p90_val = float(p90_raw) if (p90_raw is not None and pd.notna(p90_raw)) else 0.0

        mean_raw = p.get("mean_pts", 0.0)
        mean_pts = float(mean_raw) if (mean_raw is not None and pd.notna(mean_raw)) else 0.0
        pts_display = mean_pts * 2 if is_cap else mean_pts

        return f"""
        <div class="player-card" style="min-width: 145px; margin: 4px;">
            {badge_html}
            <b style="font-size: 15px; color: #f8fafc;">{p['web_name']}</b><br/>
            <small style="color: #94a3b8;">{p['club']} vs {p['fixture']}</small><br/>
            <span class="{fdr_class}">FDR {fdr_val:.0f}</span> 
            <small style="color: #38bdf8;">⚡ Form {form_val:.1f}</small><br/>
            {cop_warning}{card_warning}
            <div class="xp-pill">{pts_display:.2f} pts{' (2x)' if is_cap else ''}</div><br/>
            <small style="color: #94a3b8; font-size: 11px;">P10: {p10_val:.1f} | P90: {p90_val:.1f}</small>
        </div>
        """

    pitch_markup = '<div class="pitch-container">'
    # FWD Row
    pitch_markup += '<div class="pitch-row">'
    for _, p in fwds.iterrows():
        pitch_markup += _render_mc_pitch_card(p)
    pitch_markup += '</div>'
    # MID Row
    pitch_markup += '<div class="pitch-row">'
    for _, p in mids.iterrows():
        pitch_markup += _render_mc_pitch_card(p)
    pitch_markup += '</div>'
    # DEF Row
    pitch_markup += '<div class="pitch-row">'
    for _, p in defs.iterrows():
        pitch_markup += _render_mc_pitch_card(p)
    pitch_markup += '</div>'
    # GKP Row
    pitch_markup += '<div class="pitch-row">'
    for _, p in gkps.iterrows():
        pitch_markup += _render_mc_pitch_card(p)
    pitch_markup += '</div>'
    pitch_markup += '</div>'
    render_html(pitch_markup)

    # -------------------------------------------------------------
    # Section 3: Priority Substitutes & Auto-Sub Activation Strategy
    # -------------------------------------------------------------
    st.markdown("#### 🪑 Priority Substitutes & Bench Activation Matrix")
    st.markdown(
        "Bench order matters critically in FPL. If a starter misses out, the game substitutes from left to right, "
        "provided the resulting team has at least **3 defenders, 2 midfielders, and 1 forward**."
    )

    b_cols = st.columns(4)
    for idx, b_item in enumerate(bench_data):
        with b_cols[idx]:
            act_pct = b_item["activation_prob_pct"]
            act_color = "#10b981" if act_pct >= 20 else ("#f59e0b" if act_pct >= 5 else "#94a3b8")
            
            border_color = "#3b82f6" if idx == 0 else "rgba(255, 255, 255, 0.15)"
            sub_badge = f'<span style="background: {act_color}; color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">{act_pct}% Auto-Sub</span>'

            render_html(f"""
            <div class="bench-card" style="border: 2px solid {border_color}; min-height: 250px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <b style="color: #38bdf8; font-size: 13px;">{b_item['slot']}</b>
                        {sub_badge}
                    </div>
                    <b style="color: white; font-size: 16px;">{b_item['web_name']}</b> <small style="color: #94a3b8;">({b_item['position']})</small><br/>
                    <small style="color: #cbd5e1;">{b_item['club']} vs {b_item['fixture']}</small><br/>
                    <div style="margin: 8px 0; background: rgba(15, 23, 42, 0.6); padding: 6px; border-radius: 6px; font-size: 12px;">
                        <span style="color: #94a3b8;">EV if Subbed:</span> <b style="color: #34d399;">{b_item['pts_when_subbed']:.2f} pts</b><br/>
                        <span style="color: #94a3b8;">Points Saved EV:</span> <b style="color: #38bdf8;">+{b_item['points_saved_mean']:.2f} pts</b><br/>
                        <span style="color: #94a3b8;">Form:</span> <b style="color: white;">{b_item['form']:.1f}</b>
                    </div>
                </div>
                <div style="font-size: 11px; color: #cbd5e1; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px; text-align: left;">
                    <i>{b_item['tactical_rationale']}</i>
                </div>
            </div>
            """)

    # Bench Activation Bar Chart
    sub_names = [f"{b['slot']}: {b['web_name']} ({b['position']})" for b in bench_data]
    sub_probs = [b["activation_prob_pct"] for b in bench_data]

    fig_bench = go.Figure()
    fig_bench.add_trace(go.Bar(
        x=sub_names,
        y=sub_probs,
        name="Activation Probability (%)",
        marker_color=["#10b981", "#f59e0b", "#94a3b8", "#64748b"],
        text=[f"{p}%" for p in sub_probs],
        textposition="auto"
    ))
    fig_bench.update_layout(
        title="Substitute Activation Probability across Simulated Gameweeks",
        paper_bgcolor="#0b0f19",
        plot_bgcolor="#1e293b",
        font={"color": "#f8fafc"},
        xaxis={"gridcolor": "rgba(255,255,255,0.08)"},
        yaxis={"title": "Probability (%)", "gridcolor": "rgba(255,255,255,0.08)", "range": [0, max(sub_probs) * 1.3 + 5]},
        height=320,
        margin={"l": 20, "r": 20, "t": 40, "b": 20}
    )
    st.plotly_chart(fig_bench, use_container_width=True)

    st.markdown("---")

    # -------------------------------------------------------------
    # Section 4: Captaincy & Vice-Captaincy Monte Carlo Duel
    # -------------------------------------------------------------
    st.subheader("👑 Captaincy & Vice-Captaincy Monte Carlo Duel")
    st.markdown(
        r"Armband optimization requires evaluating head-to-head win probability, explosive haul ceiling ($\ge 10$ points), "
        r"and catastrophic blank risk ($\le 2$ points). Furthermore, Vice-Captain selection provides **insurance protection** if the captain suffers a late training knock or scratch."
    )

    cap_col1, cap_col2 = st.columns(2)

    with cap_col1:
        render_html(f"""
        <div style="background: #1e293b; border: 2px solid #ef4444; border-radius: 12px; padding: 18px; box-shadow: 0 4px 15px rgba(239, 68, 68, 0.2);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span class="captain-badge" style="font-size: 13px;">★ DESIGNATED CAPTAIN</span>
                <span style="background: #065f46; color: #a7f3d0; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px;">Win Rate: {cap_info['win_rate_pct']}%</span>
            </div>
            <h2 style="color: white; margin: 4px 0 2px 0;">{cap_info['web_name']}</h2>
            <div style="color: #94a3b8; font-size: 13px; margin-bottom: 12px;">{cap_info['club']} vs {cap_info['fixture']} • Form: {cap_info['form']:.1f}</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; background: #0f172a; padding: 12px; border-radius: 8px;">
                <div><span style="color: #94a3b8; font-size: 12px;">Captain Expected Points (2x):</span><br/><b style="color: #ef4444; font-size: 20px;">{cap_info['mean_captain_pts']:.2f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Single Match EV:</span><br/><b style="color: white; font-size: 18px;">{cap_info['mean_single_pts']:.2f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Haul Probability (≥10 pts):</span><br/><b style="color: #10b981; font-size: 16px;">{cap_info['haul_prob_pct']}%</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Blank Risk (≤2 pts):</span><br/><b style="color: #f87171; font-size: 16px;">{cap_info['blank_prob_pct']}%</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Floor (P10 2x):</span><br/><b style="color: #cbd5e1; font-size: 15px;">{cap_info['p10']:.1f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Ceiling (P90 2x):</span><br/><b style="color: #cbd5e1; font-size: 15px;">{cap_info['p90']:.1f} pts</b></div>
            </div>
        </div>
        """)

    with cap_col2:
        render_html(f"""
        <div style="background: #1e293b; border: 2px solid #3b82f6; border-radius: 12px; padding: 18px; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.2);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span class="vc-badge" style="font-size: 13px;">☆ DESIGNATED VICE-CAPTAIN</span>
                <span style="background: #1e3a8a; color: #bfdbfe; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px;">Win Rate: {vc_info['win_rate_pct']}%</span>
            </div>
            <h2 style="color: white; margin: 4px 0 2px 0;">{vc_info['web_name']}</h2>
            <div style="color: #94a3b8; font-size: 13px; margin-bottom: 12px;">{vc_info['club']} vs {vc_info['fixture']} • Form: {vc_info['form']:.1f}</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; background: #0f172a; padding: 12px; border-radius: 8px;">
                <div><span style="color: #94a3b8; font-size: 12px;">Captain Expected Points (2x):</span><br/><b style="color: #3b82f6; font-size: 20px;">{vc_info['mean_captain_pts']:.2f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Single Match EV:</span><br/><b style="color: white; font-size: 18px;">{vc_info['mean_single_pts']:.2f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Haul Probability (≥10 pts):</span><br/><b style="color: #10b981; font-size: 16px;">{vc_info['haul_prob_pct']}%</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Blank Risk (≤2 pts):</span><br/><b style="color: #f87171; font-size: 16px;">{vc_info['blank_prob_pct']}%</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Floor (P10 2x):</span><br/><b style="color: #cbd5e1; font-size: 15px;">{vc_info['p10']:.1f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Ceiling (P90 2x):</span><br/><b style="color: #cbd5e1; font-size: 15px;">{vc_info['p90']:.1f} pts</b></div>
            </div>
        </div>
        """)

    st.info(f"""
    **🛡️ Vice-Captain Insurance Policy:** In {cap_info['win_rate_pct']}% of simulations, **{cap_info['web_name']}** outscores **{vc_info['web_name']}**.
    However, if {cap_info['web_name']} plays 0 minutes due to unexpected pre-match illness or rotation, FPL rules automatically transfer the 2x multiplier to **{vc_info['web_name']}**, securing an expected return of **{vc_info['mean_captain_pts']:.2f} points**.
    """)

    # Contenders Table
    st.markdown("#### Top 5 Captaincy Contenders Evaluation")
    cont_df = pd.DataFrame(cap_duel["contenders"])
    cont_display = cont_df[[
        "web_name", "club", "pos", "fixture", "form",
        "mean_captain_pts", "haul_prob_pct", "blank_prob_pct", "p10", "p90"
    ]].rename(columns={
        "web_name": "Player",
        "club": "Club",
        "pos": "Pos",
        "fixture": "GW4 Fixture",
        "form": "Form",
        "mean_captain_pts": "Expected 2x Points",
        "haul_prob_pct": "Haul % (≥10)",
        "blank_prob_pct": "Blank % (≤2)",
        "p10": "P10 Floor",
        "p90": "P90 Ceiling"
    })
    st.dataframe(cont_display, use_container_width=True, hide_index=True)

    st.markdown("---")

    # -------------------------------------------------------------
    # Section 5: Formations Optimization Comparison
    # -------------------------------------------------------------
    st.subheader("📐 All 8 Legal Formations Evaluated")
    st.markdown(
        "FPL permits exactly 8 outfield combinations (always requiring 1 GKP, at least 3 DEF, and at least 1 FWD). "
        "Here is the Monte Carlo performance comparison for Rubies Rangers across all 8 configurations:"
    )

    form_evals = lineup_res["formation_evaluations"]
    form_df = pd.DataFrame(form_evals)

    f_col1, f_col2 = st.columns([1, 1])
    with f_col1:
        fig_form = go.Figure()
        fig_form.add_trace(go.Bar(
            y=form_df["formation"][::-1],
            x=form_df["mean_score"][::-1],
            orientation="h",
            marker_color=["#10b981" if f == opt_form else "#3b82f6" for f in form_df["formation"][::-1]],
            text=[f"{score:.1f} pts" for score in form_df["mean_score"][::-1]],
            textposition="auto"
        ))
        fig_form.update_layout(
            title="Expected Lineup Score by Legal Formation",
            paper_bgcolor="#0b0f19",
            plot_bgcolor="#1e293b",
            font={"color": "#f8fafc"},
            xaxis={"title": "Mean Simulated Total (pts)", "gridcolor": "rgba(255,255,255,0.08)"},
            yaxis={"gridcolor": "rgba(255,255,255,0.08)"},
            height=380,
            margin={"l": 20, "r": 20, "t": 40, "b": 20}
        )
        st.plotly_chart(fig_form, use_container_width=True)

    with f_col2:
        st.markdown("#### Formations Leaderboard")
        form_disp = form_df[["formation", "defenders", "midfielders", "forwards", "mean_score", "p10", "p50", "p90", "std"]].rename(columns={
            "formation": "Formation",
            "defenders": "DEF",
            "midfielders": "MID",
            "forwards": "FWD",
            "mean_score": "Mean (pts)",
            "p10": "Floor (P10)",
            "p50": "Median (P50)",
            "p90": "Ceiling (P90)",
            "std": "Volatility (Std)"
        })
        st.dataframe(form_disp, use_container_width=True, hide_index=True)
        st.caption("💡 **Why 3-5-2 dominates:** Rubies Rangers possesses 5 elite starting midfielders (Foden, Cherki, Rogers, Ødegaard, Mbeumo) and 2 explosive forwards (Isak, Pedro). Dropping any midfielder to play an extra defender costs an average of 6.2 to 17.6 points.")

    st.markdown("---")

    # -------------------------------------------------------------
    # Section 6: Disciplinary, Form & Injury Risk Monitor
    # -------------------------------------------------------------
    st.subheader("🩺 Squad Health, Form & Disciplinary Risk Monitor")
    st.markdown("Monitors cards accumulation, in-match red card risk, recent minutes, injury statuses, and player form:")

    risk_alerts = lineup_res["disciplinary_and_injury_alerts"]
    if risk_alerts:
        alert_df = pd.DataFrame(risk_alerts)
        alert_disp = alert_df[["web_name", "club", "pos", "status", "cop", "yellow_cards", "red_cards", "form", "notes"]].rename(columns={
            "web_name": "Player",
            "club": "Club",
            "pos": "Pos",
            "status": "FPL Status",
            "cop": "Chance of Playing (%)",
            "yellow_cards": "Yellow Cards",
            "red_cards": "Red Cards",
            "form": "Current Form",
            "notes": "Risk Flag / Description"
        })
        st.dataframe(alert_disp, use_container_width=True, hide_index=True)
    else:
        st.success("✅ All squad players are currently available with zero active injury flags or disciplinary suspensions.")

elif mode == "Tactical Process & Shot Quality":
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

elif mode == "Match-by-Match Trend Engine":
    st.title("📈 Granular Match-by-Match Trend Analysis & Minutes Security")
    st.markdown("""
    **Moneyball Philosophy:** Aggregated seasonal stats disguise recent role shifts, minutes collapse, and rotation risks.
    Querying `/api/element-summary/{player_id}/` provides rolling 3-GW $xGI$, rotation risk categorization, and granular defensive work rate.
    """)

    with st.spinner("Fetching granular match data for squad..."):
        squad_trends = load_squad_trends()

    # Metric KPI Cards
    benched_count = len(squad_trends[squad_trends["minutes_status"] == "BENCHED_OR_DROPPED"])
    rotation_count = len(squad_trends[squad_trends["minutes_status"] == "ROTATION_RISK"])
    secure_count = len(squad_trends[squad_trends["minutes_status"] == "SECURE_STARTER"])
    regular_count = len(squad_trends[squad_trends["minutes_status"] == "REGULAR_STARTER"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Benched / Dropped", f"{benched_count} players", delta=f"-{benched_count} Alert", delta_color="inverse")
    c2.metric("Rotation Risk / Cameos", f"{rotation_count} players", delta="Caution" if rotation_count > 0 else "None", delta_color="off")
    c3.metric("Secure 90m Starters", f"{secure_count} players", delta="Solid Floor")
    c4.metric("Regular Starters", f"{regular_count} players")

    # High-Priority Tactical Alerts
    benched_names = squad_trends[squad_trends["minutes_status"] == "BENCHED_OR_DROPPED"]
    if not benched_names.empty:
        alert_text = " • ".join([f"**{r['web_name']}** ({r['recent_minutes_str']} mins)" for _, r in benched_names.iterrows()])
        st.error(f"🚨 **CRITICAL MINUTES ALERT (Benched / Out of Favor):** {alert_text} — Immediate transfer out recommended!")

    tab1, tab2, tab3, tab4 = st.tabs([
        "🛡️ Squad Minutes Security Matrix",
        "🔍 Granular Player Match Log",
        "⚡ Attacking Momentum ($xGI$)",
        "🧱 Defensive Workhorse Floor"
    ])

    with tab1:
        st.subheader("Squad Minutes Security & Rotation Risk Audit")
        show_risks_only = st.checkbox("Show Only Rotation / Bench Risks", value=False)
        
        display_df = squad_trends.copy()
        if show_risks_only:
            display_df = display_df[display_df["minutes_status"].isin(["BENCHED_OR_DROPPED", "ROTATION_RISK"])]

        cols_view = [
            "position_name", "web_name", "club_short", "now_cost",
            "recent_minutes_str", "recent_starts", "status_badge",
            "avg_recent_xgi", "season_xgi_per_match", "xgi_trend_label",
            "avg_recent_def_contrib", "avg_recent_pts"
        ]
        rename_dict = {
            "position_name": "Pos",
            "web_name": "Player",
            "club_short": "Club",
            "now_cost": "Cost (£m)",
            "recent_minutes_str": "Last 3 GW Mins",
            "recent_starts": "Starts",
            "status_badge": "Minutes Security",
            "avg_recent_xgi": "Roll xGI (3GW)",
            "season_xgi_per_match": "Season xGI/m",
            "xgi_trend_label": "Attacking Trend",
            "avg_recent_def_contrib": "Def Actions/m",
            "avg_recent_pts": "Pts/m"
        }
        st.dataframe(display_df[cols_view].rename(columns=rename_dict), use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("Granular Player Deep-Dive & Match Timeline")
        
        player_choices = list(squad_trends["web_name"].unique())
        default_idx = player_choices.index("Solanke") if "Solanke" in player_choices else 0
        selected_player_name = st.selectbox("Select Player from Rubies Rangers:", player_choices, index=default_idx)
        
        chosen_row = squad_trends[squad_trends["web_name"] == selected_player_name].iloc[0]
        p_id = int(chosen_row["id"])
        
        p_tr = load_player_trends(p_id)
        
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Minutes Security", p_tr["status_badge"])
        p2.metric("Rolling 3GW xGI", f"{p_tr['avg_recent_xgi']:.2f}", delta=f"{p_tr['xgi_trend_delta']:+.2f} vs Season")
        p3.metric("Defensive Actions/m", f"{p_tr['avg_recent_def_contrib']:.1f}")
        p4.metric("Recent Points/m", f"{p_tr['avg_recent_pts']:.1f}")

        st.markdown(f"#### Match Log for {chosen_row['web_name']} ({chosen_row['club_name']})")
        log_df = pd.DataFrame(p_tr["match_log"])
        if not log_df.empty:
            log_cols = [
                "round", "fixture", "score", "minutes", "starts",
                "expected_goals", "expected_assists", "expected_goal_involvements",
                "tackles", "cbi", "recoveries", "defensive_contribution",
                "bps", "total_points"
            ]
            log_renames = {
                "round": "GW",
                "fixture": "Match",
                "score": "Score",
                "minutes": "Mins",
                "starts": "Start",
                "expected_goals": "xG",
                "expected_assists": "xA",
                "expected_goal_involvements": "xGI",
                "tackles": "Tackles",
                "cbi": "CBI",
                "recoveries": "Recov",
                "defensive_contribution": "Def Contrib",
                "bps": "BPS",
                "total_points": "Pts"
            }
            st.dataframe(log_df[log_cols].rename(columns=log_renames), use_container_width=True, hide_index=True)

            ch_col1, ch_col2 = st.columns(2)
            with ch_col1:
                st.markdown("**Minutes & Points Timeline**")
                chart_data = log_df.set_index("round")[["minutes", "total_points"]]
                st.bar_chart(chart_data)

            with ch_col2:
                st.markdown("**Expected Goal Involvements (xGI) vs Defensive Actions**")
                metric_chart = log_df.set_index("round")[["expected_goal_involvements", "defensive_contribution"]]
                st.line_chart(metric_chart)

    with tab3:
        st.subheader("Attacking Form Momentum: Rolling 3-GW xGI vs Season Baseline")
        st.markdown("Identifies players undergoing tactical role elevation or surging attacking involvement.")
        
        attackers_mids = squad_trends[squad_trends["position_name"].isin(["MID", "FWD"])].copy()
        if not attackers_mids.empty:
            xgi_comp = attackers_mids.set_index("web_name")[["avg_recent_xgi", "season_xgi_per_match"]].rename(columns={
                "avg_recent_xgi": "Rolling 3-GW xGI/m",
                "season_xgi_per_match": "Season xGI/m Baseline"
            })
            st.bar_chart(xgi_comp)

    with tab4:
        st.subheader("Defensive Floor & Workhorse Ranks (CBI, Tackles, Recoveries)")
        st.markdown("Defenders with high underlying defensive actions accumulate regular baseline BPS and provide an elite floor even when clean sheets are conceded.")
        
        defenders = squad_trends[squad_trends["position_name"] == "DEF"].copy()
        if not defenders.empty:
            def_comp = defenders.set_index("web_name")[["avg_recent_cbi", "avg_recent_tackles", "avg_recent_recoveries"]].rename(columns={
                "avg_recent_cbi": "Clearances/Blocks/Interceptions",
                "avg_recent_tackles": "Tackles Won",
                "avg_recent_recoveries": "Ball Recoveries"
            })
            st.bar_chart(def_comp)

elif mode == "Market Velocity & Price Predictor":
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

elif mode == "Fixture Difficulty (FDR) Ticker":
    st.title("📅 Premier League Fixture Difficulty & Swing Ticker")
    st.markdown("Analyze rolling schedule difficulty and detect **critical fixture swings** (teams transitioning from tough games into easy runs, or heading into red walls).")

    client = FPLClient()
    current_gw = client.get_current_gameweek() or 1

    horizon = st.sidebar.slider("Rolling Schedule Horizon (Gameweeks)", 3, 6, 5)
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

elif mode == "Set-Piece & Penalty Hierarchy":
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

elif mode == "Draft New Optimal Squad":
    st.title("🏆 Mathematical 15-Man Squad Draft")
    budget = st.sidebar.slider("Total Squad Budget (£m)", 90.0, 110.0, 100.0, 0.5)
    lock_player = st.sidebar.text_input("Lock Player (Optional, e.g. Haaland)")

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

else:
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
