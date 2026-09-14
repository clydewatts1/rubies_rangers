"""
Streamlit Tab: Matchday Center & Live Gameweek Team Scoreboard
Displays real-time live fixture scores, quantitative bivariate Poisson predicted outcomes,
day-of-week match schedules, active squad player contributions, auto-substitutions,
and comprehensive mini-league weekly point progression.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from ui.styles import render_html
from ui.cache import load_matchday_summary, load_mini_league_scoreboard
from trackers.league import DEFAULT_ENTRY_ID, DEFAULT_LEAGUE_ID
from clients.fpl_client import FPLClient
from analytics.matchday_hub import MatchdayFixture, MatchdayPlayer, MatchdaySummary


def render_tab_matchday(
    df: pd.DataFrame,
    current_squad: Optional[List[str]] = None,
    profile_name: Optional[str] = None
) -> None:
    if not profile_name:
        profile_name = st.session_state.get("active_profile_name", "Rubies Rangers")

    # Clean display name: "Rubies Rangers (Clyde Watts)" -> "Rubies Rangers"
    if " (" in profile_name:
        team_name = profile_name.split(" (")[0].strip()
    elif ":" in profile_name:
        team_name = profile_name.split(":")[0].strip()
    else:
        team_name = profile_name.strip()

    badge_name = team_name.upper()

    st.title("🏟️ Matchday Center & Live Gameweek Team Scoreboard")
    st.markdown(
        f"Real-time matchday command desk for **{team_name}**. Track current and upcoming Premier League games "
        f"for the active gameweek, evaluate **bivariate Poisson predicted outcomes** per day of the week, "
        f"monitor squad live points and auto-subs, and benchmark mini-league point progression."
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
            help="Select gameweek to view live matchday scores, predictions, and player outcomes."
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

    # Load Matchday Data
    with st.spinner(f"Fetching Gameweek {sel_gw} live fixtures, Poisson predicted outcomes, and {team_name} statistics..."):
        squad_tuple = tuple(current_squad) if current_squad else None
        summary: MatchdaySummary = load_matchday_summary(
            entry_id=int(entry_input),
            gameweek=int(sel_gw),
            squad_names=squad_tuple,
            force_refresh=force_refresh
        )

    # Three Main Tabs
    tab_team_scoreboard, tab_squad_roster, tab_minileague = st.tabs([
        f"📅 {team_name} Live Matchday & Day-by-Day Scoreboard",
        f"👥 {team_name} Live Performance Roster & Auto-Subs",
        "📊 Mini-League Day-of-Week Scoreboard & Progression Race"
    ])

    # =========================================================================
    # TAB 1: INDIVIDUAL TEAM SCOREBOARD & DAY-BY-DAY PREDICTED OUTCOMES
    # =========================================================================
    with tab_team_scoreboard:
        # Top KPI Metric Cards
        sq_kpi1, sq_kpi2, sq_kpi3, sq_kpi4 = st.columns(4)
        with sq_kpi1:
            st.metric(
                f"{team_name} Live Total",
                f"{summary.total_live_points} pts",
                delta=f"GW{summary.gameweek} Active Score",
                help="Sum of effective points across all 11 starters (including Captain 2x multiplier)."
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

        # -------------------------------------------------------------
        # Day-by-Day Match Organization & Filters
        # -------------------------------------------------------------
        st.subheader(f"⚡ Gameweek {summary.gameweek} Matchday Fixtures & Team Scoreboard")
        st.markdown(
            "Track live and upcoming games organized **per day of the week**, complete with **Poisson predicted outcomes** "
            f"(most likely scoreline, win/draw/loss %, clean sheet odds, over/under 2.5), weather intelligence, and **{team_name}** player impact."
        )

        # Extract active days in chronological order
        days_order = ["Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
        fixtures_by_day: Dict[str, List[MatchdayFixture]] = {}
        for f in summary.fixtures:
            d_name = f.match_day or "Saturday"
            fixtures_by_day.setdefault(d_name, []).append(f)

        ordered_days = [d for d in days_order if d in fixtures_by_day]
        for d in fixtures_by_day:
            if d not in ordered_days:
                ordered_days.append(d)

        # Day selection bar
        day_options = [f"🌟 All Matchdays ({len(summary.fixtures)} Matches)"] + [
            f"📅 {d} ({len(fixtures_by_day[d])} Matches)" for d in ordered_days
        ]

        f_col1, f_col2 = st.columns([3, 2])
        with f_col1:
            selected_day_label = st.selectbox(
                "Filter by Day of Week",
                options=day_options,
                index=0,
                key="matchday_day_filter"
            )
        with f_col2:
            st.write("")
            filter_squad_only = st.checkbox(
                f"⭐ Only show matches featuring {team_name} players",
                value=False,
                key="chk_filter_squad_only"
            )

        # Determine target fixtures
        if selected_day_label.startswith("🌟 All Matchdays"):
            target_fixtures = list(summary.fixtures)
            is_all_days = True
            current_day_name = "All Matchdays"
        else:
            # Extract day name e.g. "Saturday" from "📅 Saturday (7 Matches)"
            current_day_name = selected_day_label.split("📅 ")[1].split(" (")[0].strip()
            target_fixtures = fixtures_by_day.get(current_day_name, [])
            is_all_days = False

        if filter_squad_only:
            target_fixtures = [f for f in target_fixtures if f.has_squad_player]

        # -------------------------------------------------------------
        # Per-Day KPI Summary Banner
        # -------------------------------------------------------------
        _render_day_summary_banner(
            day_name=current_day_name,
            fixtures=target_fixtures,
            df=df,
            team_name=team_name,
            captain_name=summary.captain_name
        )

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # -------------------------------------------------------------
        # Current & Upcoming Fixture Scoreboard Cards Grid
        # -------------------------------------------------------------
        if not target_fixtures:
            st.info("No fixtures match the selected day and filters.")
        else:
            grid_col1, grid_col2 = st.columns(2)
            for idx, fix in enumerate(target_fixtures):
                target_col = grid_col1 if (idx % 2 == 0) else grid_col2
                with target_col:
                    _render_match_scoreboard_card(fix, team_name, badge_name, df)

    # =========================================================================
    # TAB 2: ACTIVE SQUAD LIVE PERFORMANCE ROSTER & AUTO-SUB WATCH
    # =========================================================================
    with tab_squad_roster:
        st.subheader(f"👥 {team_name} Live Gameweek {summary.gameweek} Roster")
        st.markdown("Detailed match performance breakdown across active Starting XI and Substitutes bench.")

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

        if summary.auto_subs:
            st.markdown("---")
            st.markdown("##### 🔄 Projected Automatic Substitutions")
            for sub in summary.auto_subs:
                st.info(
                    f"**Auto-Sub Triggered**: Starter **{sub['sub_out']}** (0 mins) ➔ "
                    f"Bench Replacement **{sub['sub_in']}** (+{sub['points_added']} pts). "
                    f"Rule: {sub['reason']}."
                )

    # =========================================================================
    # TAB 3: MINI-LEAGUE DAY-OF-WEEK SCOREBOARD & WEEKLY PROGRESSION
    # =========================================================================
    with tab_minileague:
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
                    "📊 League Live Average",
                    f"{ml_sb.league_avg_live_points:.1f} pts",
                    delta=f"Net Avg: {ml_sb.league_avg_net_points:.1f} pts"
                )
            with kpi4:
                top_cap_name, top_cap_count = next(iter(ml_sb.top_captains.items())) if ml_sb.top_captains else ("None", 0)
                st.metric(
                    "🎯 Consensus Captain",
                    f"{top_cap_name}",
                    delta=f"{top_cap_count} managers ({top_cap_count / len(ml_sb.members) * 100:.0f}%)"
                )

            st.markdown("---")
            st.subheader(f"📈 Mini-League Daily Scoreboard: Gameweek {sel_gw} Day-by-Day Points")
            st.caption("Points accumulated on each day of the Premier League matchday schedule (with hit deductions and captaincy doubling).")

            rows = []
            for m in ml_sb.members:
                row_dict: Dict[str, Any] = {
                    "Rank": f"#{m.rank}",
                    "Team": m.team_name,
                    "Manager": m.manager_name,
                    "Captain": f"{m.captain_name} (x{m.captain_multiplier})",
                    "Cap Pts": m.captain_points,
                    "Chip": m.active_chip.upper() if m.active_chip else "-",
                    "Played": f"{m.starters_played + m.starters_playing}/11",
                    "To Play": m.starters_to_play,
                }
                for d in ml_sb.active_days:
                    row_dict[d] = m.day_points.get(d, 0)

                row_dict["Hits"] = f"-{m.transfer_cost}" if m.transfer_cost > 0 else "0"
                row_dict["Net Live"] = m.net_gw_points
                row_dict["Total Ovr"] = m.total_league_points
                rows.append(row_dict)

            df_sb = pd.DataFrame(rows)
            st.dataframe(df_sb, use_container_width=True, hide_index=True)

            # Cumulative Progression Chart
            if len(ml_sb.active_days) > 1:
                st.markdown("---")
                st.subheader("🏎️ Cumulative Day-of-Week Points Progression Race")
                fig_prog = go.Figure()
                top_teams = ml_sb.members[:10]
                colors = ["#facc15", "#38bdf8", "#34d399", "#f87171", "#a855f7", "#fb923c", "#ec4899", "#94a3b8", "#e2e8f0", "#a3e635"]

                for idx, m in enumerate(top_teams):
                    days_x = ["Pre-GW"] + ml_sb.active_days
                    cum_y = [0] + [m.cumulative_day_points.get(d, 0) for d in ml_sb.active_days]
                    is_my_team = (m.team_name.lower() == team_name.lower() or m.entry_id == int(entry_input))
                    line_w = 4 if is_my_team else 2
                    col = "#facc15" if is_my_team else colors[idx % len(colors)]

                    fig_prog.add_trace(go.Scatter(
                        x=days_x,
                        y=cum_y,
                        mode="lines+markers",
                        name=f"{m.team_name}{' ⭐' if is_my_team else ''}",
                        line=dict(color=col, width=line_w),
                        marker=dict(size=7)
                    ))

                fig_prog.update_layout(
                    paper_bgcolor="#0b0f19",
                    plot_bgcolor="#1e293b",
                    font=dict(color="#f8fafc"),
                    xaxis=dict(title="Matchday Progression", gridcolor="rgba(255,255,255,0.08)"),
                    yaxis=dict(title="Cumulative Points", gridcolor="rgba(255,255,255,0.08)"),
                    height=420,
                    margin=dict(l=20, r=20, t=30, b=20),
                    legend=dict(orientation="h", y=1.15, x=0.0)
                )
                st.plotly_chart(fig_prog, use_container_width=True)


def _render_day_summary_banner(
    day_name: str,
    fixtures: List[MatchdayFixture],
    df: pd.DataFrame,
    team_name: str,
    captain_name: str
) -> None:
    """Renders a high-level summary card of team involvement and projected points for the selected day."""
    total_matches = len(fixtures)
    squad_players_today: List[MatchdayPlayer] = []
    live_points_today = 0
    remaining_xp_today = 0.0
    cap_features_today = False

    for f in fixtures:
        all_p = f.home_squad_players + f.away_squad_players
        for p in all_p:
            squad_players_today.append(p)
            live_points_today += p.effective_points
            if p.role == "CAP":
                cap_features_today = True
            if p.match_status == "UPCOMING":
                p_row = df[df["web_name"] == p.web_name] if "web_name" in df.columns else pd.DataFrame()
                xp_est = float(p_row.iloc[0].get("ep_this") or p_row.iloc[0].get("fdr_moneyball_score") or 4.0) if not p_row.empty else 4.0
                mult = p.multiplier if p.multiplier > 0 else (2 if p.role == "CAP" else (1 if p.is_starter else 0))
                remaining_xp_today += xp_est * mult

    starters_today = [p for p in squad_players_today if p.is_starter]
    bench_today = [p for p in squad_players_today if not p.is_starter]

    cap_badge = (
        f'<span style="background: #eab308; color: #000; padding: 2px 8px; border-radius: 10px; font-weight: 800; font-size: 11px;">⭐ CAPTAIN {captain_name.upper()} IN ACTION TODAY</span>'
        if cap_features_today
        else '<span style="background: #334155; color: #cbd5e1; padding: 2px 8px; border-radius: 10px; font-size: 11px;">Captain Not Playing Today</span>'
    )

    names_summary = ", ".join([f"<b>{p.web_name}</b> ({p.club_short})" for p in starters_today[:6]])
    if len(starters_today) > 6:
        names_summary += f", +{len(starters_today) - 6} more"
    elif not starters_today:
        names_summary = "None"

    render_html(f"""
    <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 16px; box-shadow: 0 4px 14px rgba(0,0,0,0.35);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="background: #38bdf8; color: #0b0f19; font-weight: 800; font-size: 12px; padding: 3px 10px; border-radius: 6px;">MATCHDAY SCHEDULE</span>
                <b style="color: #ffffff; font-size: 16px;">{day_name} Focus</b>
            </div>
            {cap_badge}
        </div>
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; background: rgba(15, 23, 42, 0.6); padding: 10px 14px; border-radius: 8px; margin-bottom: 10px;">
            <div><span style="color: #94a3b8; font-size: 11px;">Matches Scheduled:</span><br/><b style="color: #ffffff; font-size: 16px;">{total_matches} Fixtures</b></div>
            <div><span style="color: #94a3b8; font-size: 11px;">Starters Featuring:</span><br/><b style="color: #38bdf8; font-size: 16px;">{len(starters_today)} Starters</b> <small style="color: #94a3b8;">({len(bench_today)} Bench)</small></div>
            <div><span style="color: #94a3b8; font-size: 11px;">Points Scored Today:</span><br/><b style="color: #34d399; font-size: 16px;">+{live_points_today} pts</b></div>
            <div><span style="color: #94a3b8; font-size: 11px;">Projected Firepower:</span><br/><b style="color: #facc15; font-size: 16px;">~{remaining_xp_today:.1f} xP Remaining</b></div>
        </div>
        <div style="font-size: 12px; color: #cbd5e1;">
            <span style="color: #94a3b8;">{team_name} Starters in Action:</span> {names_summary}
        </div>
    </div>
    """)


def _render_match_scoreboard_card(
    fix: MatchdayFixture,
    team_name: str,
    badge_name: str,
    df: pd.DataFrame
) -> None:
    """Renders a single matchday fixture card with score, Poisson prediction, and squad player impact."""
    pred = fix.prediction

    if fix.has_squad_player:
        card_border = "1.5px solid #facc15"
        card_bg = "linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.95))"
        star_badge = f'<span style="background: #eab308; color: #000; padding: 2px 8px; border-radius: 12px; font-weight: 800; font-size: 11px;">⭐ {badge_name} MATCH</span>'
    else:
        card_border = "1px solid rgba(255, 255, 255, 0.10)"
        card_bg = "rgba(15, 23, 42, 0.85)"
        star_badge = ""

    # Status pill
    if fix.finished:
        status_html = '<span style="background: #065f46; color: #34d399; padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 11px;">FULL TIME</span>'
    elif fix.started:
        status_html = f'<span style="background: #7f1d1d; color: #f87171; padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 11px;">🔴 LIVE {fix.minutes}\'</span>'
    else:
        time_str = fix.match_time_str or fix.status_label
        status_html = f'<span style="background: #1e3a8a; color: #93c5fd; padding: 2px 8px; border-radius: 6px; font-weight: 600; font-size: 11px;">⏳ {fix.match_day[:3]} {time_str}</span>'

    # Score display
    if fix.started or fix.finished:
        h_sc = fix.home_score if fix.home_score is not None else 0
        a_sc = fix.away_score if fix.away_score is not None else 0
        score_display = f"{h_sc} - {a_sc}"
    else:
        score_display = "vs"

    # Prediction HTML block
    pred_html = ""
    if pred is not None:
        actual_vs_pred_html = ""
        if fix.started or fix.finished:
            actual_vs_pred_html = f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px; font-size: 11px; padding: 3px 8px; background: rgba(30, 41, 59, 0.7); border-radius: 4px;">
                <span style="color: #94a3b8;">Actual Score: <b style="color: #ffffff;">{h_sc} - {a_sc}</b></span>
                <span style="color: #94a3b8;">Mode Predicted: <b style="color: #38bdf8;">{pred.predicted_home_score} - {pred.predicted_away_score}</b></span>
            </div>
            """

        pred_html = f"""
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 8px; padding: 10px; margin-top: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="color: #38bdf8; font-size: 11px; font-weight: 800; text-transform: uppercase;">🔮 PREDICTED OUTCOME (POISSON xG)</span>
                <span style="background: #1e293b; color: #facc15; border: 1px solid #facc15; padding: 1px 6px; border-radius: 4px; font-size: 11px; font-weight: 700;">
                    Score: {pred.predicted_home_score} - {pred.predicted_away_score}
                </span>
            </div>
            <div style="display: flex; height: 8px; border-radius: 4px; overflow: hidden; margin-bottom: 6px; background: #334155;">
                <div style="width: {pred.home_win_prob}%; background: #3b82f6;" title="{fix.home_short} Win: {pred.home_win_prob}%"></div>
                <div style="width: {pred.draw_prob}%; background: #94a3b8;" title="Draw: {pred.draw_prob}%"></div>
                <div style="width: {pred.away_win_prob}%; background: #ec4899;" title="{fix.away_short} Win: {pred.away_win_prob}%"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin-bottom: 6px;">
                <span><b>{fix.home_short} Win</b>: {pred.home_win_prob:.0f}%</span>
                <span><b>Draw</b>: {pred.draw_prob:.0f}%</span>
                <span><b>{fix.away_short} Win</b>: {pred.away_win_prob:.0f}%</span>
            </div>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; text-align: center; font-size: 10px; background: rgba(0,0,0,0.3); padding: 5px 6px; border-radius: 6px;">
                <div><span style="color: #94a3b8;">{fix.home_short} CS:</span><br/><b style="color: #34d399;">{pred.home_cs_prob:.0f}%</b></div>
                <div><span style="color: #94a3b8;">{fix.away_short} CS:</span><br/><b style="color: #34d399;">{pred.away_cs_prob:.0f}%</b></div>
                <div><span style="color: #94a3b8;">Total xG:</span><br/><b style="color: #facc15;">{pred.expected_total_goals:.1f}</b></div>
                <div><span style="color: #94a3b8;">Over 2.5:</span><br/><b style="color: #38bdf8;">{pred.over_25_prob:.0f}%</b></div>
            </div>
            {actual_vs_pred_html}
        </div>
        """

    # Active squad player impact pills
    player_pills_html = ""
    if fix.home_squad_players or fix.away_squad_players:
        player_pills_html += '<div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255, 255, 255, 0.08); font-size: 12px;">'
        all_squad_p = [(p, fix.home_short) for p in fix.home_squad_players] + [(p, fix.away_short) for p in fix.away_squad_players]
        for p, c_short in all_squad_p:
            role_bg = "#ef4444" if p.role == "CAP" else ("#a855f7" if p.role == "VC" else ("#3b82f6" if p.is_starter else "#64748b"))

            if fix.finished or fix.started:
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
                stats_display = f"<small style='color: #cbd5e1;'>{events_str} {f'• {p.minutes}\'' if p.minutes > 0 else ''}</small>"
                score_pill = f"<span style='font-weight: 700; color: #34d399; font-size: 13px;'>+{p.effective_points} pts {f'(x{p.multiplier})' if p.multiplier > 1 else ''}</span>"
            else:
                p_row = df[df["web_name"] == p.web_name] if "web_name" in df.columns else pd.DataFrame()
                xp_val = float(p_row.iloc[0].get("ep_this") or p_row.iloc[0].get("fdr_moneyball_score") or 4.0) if not p_row.empty else 4.0
                mult = p.multiplier if p.multiplier > 0 else (2 if p.role == "CAP" else (1 if p.is_starter else 0))
                eff_xp = xp_val * mult
                stats_display = "<small style='color: #94a3b8;'>Upcoming Match</small>"
                score_pill = f"<span style='font-weight: 700; color: #facc15; font-size: 12px;'>~{eff_xp:.1f} xP {f'(x{mult})' if mult > 1 else ''}</span>"

            player_pills_html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span>
                    <span style="background: {role_bg}; color: white; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; margin-right: 6px;">{p.role}</span>
                    <b>{p.web_name}</b> <small style="color: #94a3b8;">({c_short}, {p.position})</small>
                    {stats_display}
                </span>
                {score_pill}
            </div>
            """
        player_pills_html += '</div>'

    date_label = f"📅 {fix.match_day} {fix.match_date_str}" if fix.match_date_str else f"📅 {fix.match_day}"

    render_html(f"""
    <div style="background: {card_bg}; border: {card_border}; border-radius: 12px; padding: 14px; margin-bottom: 14px; box-shadow: 0 4px 14px rgba(0,0,0,0.35);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 6px;">
                {star_badge}
                <span style="color: #94a3b8; font-size: 11px; font-weight: 600;">{date_label}</span>
                {fix.weather_badge_html}
            </div>
            {status_html}
        </div>
        <div style="display: flex; justify-content: space-around; align-items: center; font-size: 18px; font-weight: 800; padding: 6px 0;">
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
        {pred_html}
        {player_pills_html}
    </div>
    """)
