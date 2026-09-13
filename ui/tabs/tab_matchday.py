"""
Streamlit Tab: Matchday Center & Current Week Scoreboard
Displays real-time live fixture scores, active squad points, captaincy contributions,
and fixture-to-player performance tracking.
"""

import streamlit as st
import pandas as pd
from typing import Optional, List

from ui.styles import render_html
from ui.cache import load_matchday_summary
from trackers.league import DEFAULT_ENTRY_ID
from clients.fpl_client import FPLClient


def render_tab_matchday(
    df: pd.DataFrame,
    current_squad: Optional[List[str]] = None,
    profile_name: Optional[str] = None
):
    if not profile_name:
        profile_name = st.session_state.get("active_profile_name", "Rubies Rangers")

    # Clean display name: "Rubies Rangers (Clyde Watts)" -> "Rubies Rangers", "IraolaCoaster (Shane McLaughlin)" -> "IraolaCoaster"
    if " (" in profile_name:
        team_name = profile_name.split(" (")[0].strip()
    elif ":" in profile_name:
        team_name = profile_name.split(":")[0].strip()
    else:
        team_name = profile_name.strip()

    badge_name = team_name.upper()

    st.title("🏟️ Matchday Center & Live Gameweek Scoreboard")
    st.markdown(
        f"Track live Premier League fixture scores in real-time, audit **{team_name}** active squad performances, "
        "and monitor in-play captaincy, bonus points, and bench auto-substitutions."
    )

    fpl = FPLClient()
    current_gw = fpl.get_current_gameweek() or 4

    # Top Control Bar
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 2])
    with ctrl_col1:
        sel_gw = st.selectbox(
            "Gameweek",
            options=list(range(1, 39)),
            index=max(0, current_gw - 1),
            help="Select gameweek to view live matchday scores and player outcomes."
        )
    with ctrl_col2:
        default_entry = st.session_state.get("active_entry_id") or int(DEFAULT_ENTRY_ID)
        entry_input = st.number_input(
            f"Manager Entry ID ({team_name})",
            value=int(default_entry),
            step=1,
            help="FPL team ID for active manager (defaults to currently selected profile)."
        )
    with ctrl_col3:
        st.write("")  # vertical spacer
        force_refresh = st.button("🔄 Refresh Live Scores & Stats", help="Bypasses cache and fetches latest live matchday data.")

    # Load Matchday Data
    with st.spinner(f"Fetching Gameweek {sel_gw} live matchday fixtures and squad statistics..."):
        squad_tuple = tuple(current_squad) if current_squad else None
        summary = load_matchday_summary(
            entry_id=int(entry_input),
            gameweek=int(sel_gw),
            squad_names=squad_tuple,
            force_refresh=force_refresh
        )

    # 1. Hero KPI Metric Cards
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric(
            f"{team_name} Live Total",
            f"{summary.total_live_points} pts",
            delta=f"GW{summary.gameweek} Active Score",
            help="Sum of effective points across all 11 starters (including Captain 2x)."
        )
    with kpi2:
        st.metric(
            "Starters In Play",
            f"{summary.starters_played_count + summary.starters_playing_count} / 11 Active",
            delta=f"{summary.starters_to_play_count} Players Yet to Play",
            help="Count of starting players who have finished or are currently on the pitch."
        )
    with kpi3:
        st.metric(
            "Designated Captain (C)",
            f"{summary.captain_name}",
            delta=f"{summary.captain_points} pts (2x Multiplier)",
            help="Points earned by the designated team captain with 2x multiplier applied."
        )
    with kpi4:
        st.metric(
            "Bench Reserve Points",
            f"{summary.bench_reserve_points} pts",
            delta=f"{len(summary.bench)} Substitutes",
            help="Total points held on the bench in reserve."
        )

    # Auto-Sub Banner if any active
    if summary.auto_subs:
        for sub in summary.auto_subs:
            st.warning(
                f"🔄 **Auto-Substitution Watch**: **{sub['sub_out']}** did not feature. "
                f"Projected replacement: **{sub['sub_in']}** (+{sub['points_added']} pts). "
                f"Reason: {sub['reason']}."
            )

    st.markdown("---")

    # 2. Matchday Fixtures Scoreboard Grid
    st.subheader(f"⚡ Gameweek {summary.gameweek} Fixtures & Squad Match Center")
    st.caption(f"Matches featuring active {team_name} players are highlighted with ⭐ badges and player contribution pills.")

    # Render fixtures in a 2-column grid
    col_left, col_right = st.columns(2)
    for idx, fix in enumerate(summary.fixtures):
        target_col = col_left if (idx % 2 == 0) else col_right
        with target_col:
            # Border styling for squad matches
            if fix.has_squad_player:
                card_border = "1.5px solid #facc15"
                card_bg = "linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.95))"
                star_badge = f'<span style="background: #eab308; color: #000; padding: 2px 8px; border-radius: 12px; font-weight: 800; font-size: 11px;">⭐ {badge_name} MATCH</span>'
            else:
                card_border = "1px solid rgba(255, 255, 255, 0.10)"
                card_bg = "rgba(15, 23, 42, 0.75)"
                star_badge = ""

            # Match status badge
            if fix.finished:
                status_html = '<span style="background: #065f46; color: #34d399; padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 11px;">FULL TIME</span>'
            elif fix.started:
                status_html = f'<span style="background: #7f1d1d; color: #f87171; padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; animation: blinker 1.5s linear infinite;">🔴 LIVE {fix.minutes}\'</span>'
            else:
                status_html = f'<span style="background: #1e3a8a; color: #93c5fd; padding: 2px 8px; border-radius: 6px; font-weight: 600; font-size: 11px;">⏳ {fix.status_label}</span>'

            # Score text
            if fix.started or fix.finished:
                h_sc = fix.home_score if fix.home_score is not None else 0
                a_sc = fix.away_score if fix.away_score is not None else 0
                score_display = f"{h_sc} - {a_sc}"
            else:
                score_display = "vs"

            # Squad player pill HTML
            player_pills_html = ""
            if fix.home_squad_players or fix.away_squad_players:
                player_pills_html += '<div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255, 255, 255, 0.08); font-size: 12px;">'
                for p in fix.home_squad_players:
                    role_bg = "#ef4444" if p.role == "CAP" else ("#a855f7" if p.role == "VC" else ("#3b82f6" if p.is_starter else "#64748b"))
                    events_str = ""
                    if p.goals > 0:
                        events_str += f" • {p.goals}G"
                    if p.assists > 0:
                        events_str += f" • {p.assists}A"
                    if p.clean_sheets > 0:
                        events_str += " • CS"
                    if p.saves > 0:
                        events_str += f" • {p.saves} Saves"
                    if p.bonus > 0:
                        events_str += f" • {p.bonus} Bonus"

                    player_pills_html += f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <span>
                            <span style="background: {role_bg}; color: white; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; margin-right: 6px;">{p.role}</span>
                            <b>{p.web_name}</b> <small style="color: #94a3b8;">({fix.home_short}, {p.position})</small>
                            <small style="color: #cbd5e1;">{events_str} {f'• {p.minutes}\'' if p.minutes > 0 else ''}</small>
                        </span>
                        <span style="font-weight: 700; color: #34d399; font-size: 13px;">+{p.effective_points} pts {f'(x{p.multiplier})' if p.multiplier > 1 else ''}</span>
                    </div>
                    """
                for p in fix.away_squad_players:
                    role_bg = "#ef4444" if p.role == "CAP" else ("#a855f7" if p.role == "VC" else ("#3b82f6" if p.is_starter else "#64748b"))
                    events_str = ""
                    if p.goals > 0:
                        events_str += f" • {p.goals}G"
                    if p.assists > 0:
                        events_str += f" • {p.assists}A"
                    if p.clean_sheets > 0:
                        events_str += " • CS"
                    if p.saves > 0:
                        events_str += f" • {p.saves} Saves"
                    if p.bonus > 0:
                        events_str += f" • {p.bonus} Bonus"

                    player_pills_html += f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <span>
                            <span style="background: {role_bg}; color: white; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; margin-right: 6px;">{p.role}</span>
                            <b>{p.web_name}</b> <small style="color: #94a3b8;">({fix.away_short}, {p.position})</small>
                            <small style="color: #cbd5e1;">{events_str} {f'• {p.minutes}\'' if p.minutes > 0 else ''}</small>
                        </span>
                        <span style="font-weight: 700; color: #34d399; font-size: 13px;">+{p.effective_points} pts {f'(x{p.multiplier})' if p.multiplier > 1 else ''}</span>
                    </div>
                    """
                player_pills_html += '</div>'

            render_html(f"""
            <div style="background: {card_bg}; border: {card_border}; border-radius: 10px; padding: 14px; margin-bottom: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    {star_badge}
                    {status_html}
                </div>
                <div style="display: flex; justify-content: space-around; align-items: center; font-size: 18px; font-weight: 800;">
                    <div style="text-align: center; width: 35%;">
                        <span style="font-size: 20px; color: #ffffff;">{fix.home_short}</span>
                    </div>
                    <div style="text-align: center; width: 30%; font-size: 22px; color: #38bdf8; letter-spacing: 2px;">
                        {score_display}
                    </div>
                    <div style="text-align: center; width: 35%;">
                        <span style="font-size: 20px; color: #ffffff;">{fix.away_short}</span>
                    </div>
                </div>
                {player_pills_html}
            </div>
            """)

    st.markdown("---")

    # 3. Active Squad Live Performance Tables
    st.subheader(f"👥 {team_name} Live Performance Roster")
    tab_starters, tab_bench = st.tabs(["⚔️ Starting XI (Active Lineup)", "🛡️ Substitutes Bench"])

    with tab_starters:
        starters_data = []
        for p in summary.starters:
            starters_data.append({
                "Player": p.web_name,
                "Position": p.position,
                "Club": p.club_short,
                "Role": p.role,
                "Fixture": f"{'vs ' if p.is_home else '@ '}{p.opponent_short}",
                "Status": p.match_status,
                "Mins": p.minutes,
                "G": p.goals,
                "A": p.assists,
                "CS": p.clean_sheets,
                "Saves": p.saves,
                "Bonus": p.bonus,
                "BPS": p.bps,
                "Live Pts": p.live_points,
                "Effective Pts": p.effective_points,
            })
        st_df = pd.DataFrame(starters_data)
        st.dataframe(
            st_df.sort_values(by="Effective Pts", ascending=False),
            use_container_width=True,
            hide_index=True
        )

    with tab_bench:
        bench_data = []
        for idx, p in enumerate(summary.bench, 1):
            bench_data.append({
                "Order": f"Sub {idx}",
                "Player": p.web_name,
                "Position": p.position,
                "Club": p.club_short,
                "Fixture": f"{'vs ' if p.is_home else '@ '}{p.opponent_short}",
                "Status": p.match_status,
                "Mins": p.minutes,
                "G": p.goals,
                "A": p.assists,
                "CS": p.clean_sheets,
                "Live Pts": p.live_points,
            })
        bench_df = pd.DataFrame(bench_data)
        st.dataframe(bench_df, use_container_width=True, hide_index=True)
