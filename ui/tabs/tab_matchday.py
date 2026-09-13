"""
Streamlit Tab: Matchday Center & Live Gameweek Mini-League Scoreboard
Displays real-time live fixture scores, day-of-week weekly points progression across mini-league members,
captaincy outcomes, remaining unplayed firepower, and active squad performance tracking.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from typing import Optional, List, Dict, Any

from ui.styles import render_html
from ui.cache import load_matchday_summary, load_mini_league_scoreboard
from trackers.league import DEFAULT_ENTRY_ID, DEFAULT_LEAGUE_ID
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

    st.title("🏟️ Matchday Center & Live Gameweek Mini-League Scoreboard")
    st.markdown(
        f"Track live Premier League fixture scores, audit daily point progression by **Day of Week** across "
        f"your mini-league, compare captaincy outcomes, monitor unplayed assets, and track **{team_name}** live match performances."
    )

    fpl = FPLClient()
    current_gw = fpl.get_current_gameweek() or 4

    # Top Control Bar
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1.5, 2, 2, 1.5])
    with ctrl_col1:
        sel_gw = st.selectbox(
            "Gameweek",
            options=list(range(1, 39)),
            index=max(0, current_gw - 1),
            help="Select gameweek to view live matchday scores and player outcomes."
        )
    with ctrl_col2:
        league_id_input = st.number_input(
            "Mini-League ID",
            value=int(DEFAULT_LEAGUE_ID),
            step=1,
            help="FPL Classic Mini-League ID (defaults to Bronze, Silver & Gold League)."
        )
    with ctrl_col3:
        default_entry = st.session_state.get("active_entry_id") or int(DEFAULT_ENTRY_ID)
        entry_input = st.number_input(
            f"Manager Entry ID ({team_name})",
            value=int(default_entry),
            step=1,
            help="FPL team ID for active manager (defaults to currently selected profile)."
        )
    with ctrl_col4:
        st.write("")  # vertical spacer
        st.write("")
        force_refresh = st.button("🔄 Refresh Live Data", help="Bypasses cache and fetches latest live scores, standings, and stats.")

    # Two Main Tabs
    tab_scoreboard, tab_squad_center = st.tabs([
        "📊 Mini-League Day-of-Week Scoreboard & Progression Race",
        f"🏟️ {team_name} Live Matchday Radar & Fixtures"
    ])

    # =========================================================================
    # TAB 1: MINI-LEAGUE DAY-OF-WEEK SCOREBOARD & WEEKLY PROGRESSION
    # =========================================================================
    with tab_scoreboard:
        with st.spinner(f"Aggregating Gameweek {sel_gw} live mini-league standings and Day-of-Week progression..."):
            ml_sb = load_mini_league_scoreboard(
                league_id=int(league_id_input),
                gameweek=int(sel_gw),
                max_teams=25,
                force_refresh=force_refresh
            )

        if not ml_sb.members:
            st.warning(f"No active teams or standings found for Mini-League ID {league_id_input} in Gameweek {sel_gw}.")
        else:
            # 1. Top KPI Hero Cards
            leader = ml_sb.members[0]
            my_member = next((m for m in ml_sb.members if m.entry_id == int(entry_input) or m.team_name.lower() == team_name.lower()), None)

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            with kpi1:
                st.metric(
                    "👑 Live GW Leader",
                    f"{leader.net_gw_points} pts",
                    delta=f"{leader.team_name} ({leader.manager_name})",
                    help="Highest Net GW Score in the mini-league currently."
                )
            with kpi2:
                if my_member:
                    st.metric(
                        f"⚔️ {team_name} Live Score",
                        f"{my_member.net_gw_points} pts",
                        delta=f"Rank #{my_member.rank} • Total {my_member.total_league_points} pts",
                        help=f"Net GW points for {team_name} after transfer hits."
                    )
                else:
                    st.metric(
                        f"⚔️ {team_name} Status",
                        "Tracking",
                        delta="Competitor View Active"
                    )
            with kpi3:
                st.metric(
                    "📈 League Average",
                    f"{ml_sb.league_avg_net_points:.1f} pts",
                    delta=f"Live Gross: {ml_sb.league_avg_live_points:.1f} pts",
                    help="Average net points across all mini-league members this gameweek."
                )
            with kpi4:
                if ml_sb.highest_day_scorers:
                    best_day, best_info = max(ml_sb.highest_day_scorers.items(), key=lambda item: item[1]["points"])
                    st.metric(
                        f"🚀 Top Day Surge ({best_day[:3]})",
                        f"+{best_info['points']} pts",
                        delta=f"{best_info['team']}",
                        help=f"Best single-day scoring performance achieved on {best_day}."
                    )
                else:
                    st.metric("🚀 Top Day Surge", "0 pts", delta="Pre-Matchday")

            st.markdown("---")

            # 2. Interactive Weekly Progression Race Chart (Plotly)
            st.subheader(f"📈 {ml_sb.league_name} — Weekly Score Progression by Day")
            st.caption("Track how each manager's score accelerates through the weekend (Friday ➔ Saturday ➔ Sunday ➔ Monday).")

            fig = go.Figure()
            chart_days = ["Start"] + ml_sb.active_days

            color_palette = [
                "#38bdf8", "#ec4899", "#a855f7", "#34d399", "#f97316",
                "#818cf8", "#fb7185", "#2dd4bf", "#c084fc", "#fb923c",
                "#4ade80", "#60a5fa", "#f43f5e", "#a3e635", "#06b6d4"
            ]

            for idx, m in enumerate(ml_sb.members):
                is_user = (my_member is not None and m.entry_id == my_member.entry_id)
                y_pts = [0] + [m.cumulative_day_points.get(d, 0) for d in ml_sb.active_days]
                gains = [0] + [m.day_points.get(d, 0) for d in ml_sb.active_days]

                if is_user:
                    line_color = "#facc15"  # Radiant Gold/Amber
                    line_width = 4.5
                    marker_size = 9
                    marker_symbol = "diamond"
                    display_name = f"⭐ {m.team_name} ({m.manager_name})"
                else:
                    line_color = color_palette[idx % len(color_palette)]
                    line_width = 2
                    marker_size = 6
                    marker_symbol = "circle"
                    display_name = f"{m.team_name} ({m.manager_name})"

                fig.add_trace(go.Scatter(
                    x=chart_days,
                    y=y_pts,
                    mode="lines+markers",
                    name=display_name,
                    line=dict(color=line_color, width=line_width),
                    marker=dict(size=marker_size, symbol=marker_symbol),
                    customdata=gains,
                    hovertemplate=(
                        f"<b>{m.team_name}</b> ({m.manager_name})<br>" +
                        "Stage: %{x}<br>" +
                        "Cumulative Score: <b>%{y} pts</b><br>" +
                        "Day Surge: <b>+%{customdata} pts</b>" +
                        "<extra></extra>"
                    )
                ))

            fig.update_layout(
                height=440,
                margin=dict(l=15, r=15, t=30, b=25),
                paper_bgcolor="rgba(15, 23, 42, 0.6)",
                plot_bgcolor="rgba(15, 23, 42, 0.9)",
                font=dict(color="#e2e8f0", size=12),
                xaxis=dict(
                    title="Matchday Timeline",
                    showgrid=True,
                    gridcolor="rgba(255, 255, 255, 0.08)",
                    linecolor="rgba(255, 255, 255, 0.2)"
                ),
                yaxis=dict(
                    title="Cumulative Points",
                    showgrid=True,
                    gridcolor="rgba(255, 255, 255, 0.08)",
                    linecolor="rgba(255, 255, 255, 0.2)"
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    font=dict(size=10)
                ),
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # 3. Day-of-Week Points Progression Table
            st.subheader(f"📋 Live Gameweek {sel_gw} Scoreboard & Day-of-Week Matrix")
            st.caption("Points earned per match day (including Captain 2x/3x on their fixture day), transfer hits, and forward projected finish.")

            table_rows = []
            for m in ml_sb.members:
                is_user = (my_member is not None and m.entry_id == my_member.entry_id)
                prefix = "⭐ " if is_user else ""
                chip_str = f" [{m.active_chip.upper()}]" if m.active_chip else ""

                row_dict = {
                    "Rank": m.rank,
                    "Team": f"{prefix}{m.team_name}{chip_str}",
                    "Manager": m.manager_name,
                    "Captain (C)": f"{m.captain_name} ({m.captain_multiplier}x, {m.captain_points}p)",
                    "Played": f"{m.starters_played}/11" + (f" (+{m.starters_playing} live)" if m.starters_playing > 0 else ""),
                }

                # Dynamic columns for each active matchday
                for d in ml_sb.active_days:
                    row_dict[d] = m.day_points.get(d, 0)

                row_dict["Hits"] = f"-{m.transfer_cost}" if m.transfer_cost > 0 else "0"
                row_dict["GW Total"] = m.live_gw_points
                row_dict["Net GW"] = m.net_gw_points
                row_dict["Proj Finish"] = m.projected_final_points
                row_dict["Overall Total"] = m.total_league_points

                table_rows.append(row_dict)

            df_scoreboard = pd.DataFrame(table_rows)
            st.dataframe(df_scoreboard, use_container_width=True, hide_index=True)

            st.markdown("---")

            # 4. Tactical Matchday Differentials (Remaining Firepower & Captain Radar)
            st.subheader("🎯 Tactical Matchday Intelligence & Differentials")
            diff_col1, diff_col2 = st.columns(2)

            with diff_col1:
                st.markdown("#### ⚡ The Sunday/Monday Swing (Remaining Firepower)")
                st.caption("Players yet to feature for each competitor, their fixture, and algorithmic expected return ($xP$):")

                unplayed_members = [m for m in ml_sb.members if m.starters_to_play > 0]
                if not unplayed_members:
                    st.success("✅ All 11 starters have completed their matches for all tracked managers!")
                else:
                    for m in unplayed_members:
                        xp_sum = sum(p['xp'] for p in m.remaining_players)
                        with st.expander(f"**{m.team_name}** ({m.starters_to_play} to play • ~{xp_sum:.1f} xP left)", expanded=False):
                            for p in m.remaining_players:
                                st.markdown(f"• **{p['name']}** ({p['club']}, {p['pos']}) vs **{p['opp']}** ({p['day'][:3]}) — Expected: **{p['xp']} xP**")

            with diff_col2:
                st.markdown("#### 👑 Captaincy Distribution & Returns")
                st.caption("How armband choices split across the league and their live point contribution:")

                cap_summary = []
                for cap_name, count in ml_sb.top_captains.items():
                    sample_m = next((m for m in ml_sb.members if m.captain_name == cap_name), None)
                    cap_pts = sample_m.captain_points if sample_m else 0
                    cap_day = sample_m.captain_day if sample_m else "Upcoming"
                    cap_summary.append({
                        "Captain": cap_name,
                        "Managers": count,
                        "Day": cap_day,
                        "Points (2x)": cap_pts
                    })

                df_cap = pd.DataFrame(cap_summary).sort_values(by="Managers", ascending=False)
                st.dataframe(df_cap, use_container_width=True, hide_index=True)

            # Auto-Sub Watch Banner across mini-league
            pending_subs = [m for m in ml_sb.members if m.auto_subs_pending]
            if pending_subs:
                with st.expander(f"🔄 **Mini-League Auto-Substitution Watch ({len(pending_subs)} Teams Pending Cascade)**", expanded=False):
                    for m in pending_subs:
                        for sub in m.auto_subs_pending:
                            st.info(f"**{m.team_name}**: Starter **{sub['sub_out']}** did not play (0 mins) ➔ Sub **{sub['sub_in']}** (+{sub['points']} pts) ready to activate.")

    # =========================================================================
    # TAB 2: ACTIVE SQUAD MATCHDAY RADAR & FIXTURES
    # =========================================================================
    with tab_squad_center:
        with st.spinner(f"Fetching Gameweek {sel_gw} live matchday fixtures and squad statistics..."):
            squad_tuple = tuple(current_squad) if current_squad else None
            summary = load_matchday_summary(
                entry_id=int(entry_input),
                gameweek=int(sel_gw),
                squad_names=squad_tuple,
                force_refresh=force_refresh
            )

        # Squad KPI Cards
        sq_kpi1, sq_kpi2, sq_kpi3, sq_kpi4 = st.columns(4)
        with sq_kpi1:
            st.metric(
                f"{team_name} Live Total",
                f"{summary.total_live_points} pts",
                delta=f"GW{summary.gameweek} Active Score",
                help="Sum of effective points across all 11 starters (including Captain 2x)."
            )
        with sq_kpi2:
            st.metric(
                "Starters In Play",
                f"{summary.starters_played_count + summary.starters_playing_count} / 11 Active",
                delta=f"{summary.starters_to_play_count} Players Yet to Play",
                help="Count of starting players who have finished or are currently on the pitch."
            )
        with sq_kpi3:
            st.metric(
                "Designated Captain (C)",
                f"{summary.captain_name}",
                delta=f"{summary.captain_points} pts (2x Multiplier)",
                help="Points earned by the designated team captain with 2x multiplier applied."
            )
        with sq_kpi4:
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

        # Adverse Weather Warning Banner
        if summary.squad_weather_alerts:
            with st.expander(f"⚠️ **Meteorological Intelligence & Adverse Weather ({len(summary.squad_weather_alerts)} Squad Alerts)**", expanded=False):
                st.caption(f"Active {team_name} players featuring in high wind, slick rain, or extreme cold conditions:")
                for alert in summary.squad_weather_alerts:
                    st.markdown(f"• **{alert}**")

        st.markdown("---")

        # Matchday Fixtures Scoreboard Grid
        st.subheader(f"⚡ Gameweek {summary.gameweek} Fixtures & Squad Match Center")
        st.caption(f"Matches featuring active {team_name} players are highlighted with ⭐ badges, live weather readings, and player contribution pills.")

        col_left, col_right = st.columns(2)
        for idx, fix in enumerate(summary.fixtures):
            target_col = col_left if (idx % 2 == 0) else col_right
            with target_col:
                if fix.has_squad_player:
                    card_border = "1.5px solid #facc15"
                    card_bg = "linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.95))"
                    star_badge = f'<span style="background: #eab308; color: #000; padding: 2px 8px; border-radius: 12px; font-weight: 800; font-size: 11px;">⭐ {badge_name} MATCH</span>'
                else:
                    card_border = "1px solid rgba(255, 255, 255, 0.10)"
                    card_bg = "rgba(15, 23, 42, 0.75)"
                    star_badge = ""

                if fix.finished:
                    status_html = '<span style="background: #065f46; color: #34d399; padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 11px;">FULL TIME</span>'
                elif fix.started:
                    status_html = f'<span style="background: #7f1d1d; color: #f87171; padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; animation: blinker 1.5s linear infinite;">🔴 LIVE {fix.minutes}\'</span>'
                else:
                    status_html = f'<span style="background: #1e3a8a; color: #93c5fd; padding: 2px 8px; border-radius: 6px; font-weight: 600; font-size: 11px;">⏳ {fix.status_label}</span>'

                if fix.started or fix.finished:
                    h_sc = fix.home_score if fix.home_score is not None else 0
                    a_sc = fix.away_score if fix.away_score is not None else 0
                    score_display = f"{h_sc} - {a_sc}"
                else:
                    score_display = "vs"

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
                        <div style="display: flex; align-items: center; gap: 6px;">
                            {star_badge}
                            {fix.weather_badge_html}
                        </div>
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

        # Active Squad Live Performance Tables
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
