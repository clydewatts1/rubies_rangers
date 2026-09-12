"""
Streamlit Tab: Mini-League Scout & Rival Spy
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import math

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


def render_tab_leagues(df: pd.DataFrame):
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
                st.markdown("Interactive time-series progression analyzing cumulative championship points, relative lead/deficits vs **Rubies Rangers**, weekly scoring momentum, and catch-up runway trajectories.")

                try:
                    with st.spinner("Compiling gameweek-by-gameweek rival histories..."):
                        perf_data = load_league_history(active_league_id, max_teams=len(teams))
                    
                    hist_df = perf_data.get("df", pd.DataFrame())
                    chips_map = perf_data.get("chips", {})

                    if not hist_df.empty:
                        # Filter out unplayed/zero-point future gameweeks
                        valid_gw_mask = hist_df.groupby("gw_num")["gw_points"].transform("sum") > 0
                        active_df = hist_df[valid_gw_mask].copy() if valid_gw_mask.any() else hist_df.copy()

                        all_teams = sorted(active_df["team_name"].unique().tolist())
                        default_ref = "Rubies Rangers" if "Rubies Rangers" in all_teams else all_teams[0]

                        col_ref1, col_ref2 = st.columns([3, 2])
                        with col_ref1:
                            ref_team = st.selectbox(
                                "🎯 Relative Benchmark Reference Team:",
                                all_teams,
                                index=all_teams.index(default_ref),
                                help="All relative charts will compute margins and lead/deficits relative to this selected team."
                            )
                        with col_ref2:
                            st.caption(f"Showing performance relative to **{ref_team}** across all completed gameweeks.")

                        # Calculate relative metrics against selected reference team
                        ref_sub = active_df[active_df["team_name"] == ref_team].set_index("gw_num")
                        active_df["ref_cum"] = active_df["gw_num"].map(ref_sub["cumulative_points"])
                        active_df["ref_gw"] = active_df["gw_num"].map(ref_sub["gw_points"])
                        # Positive = Rival leads reference team; Negative = Rival trails reference team
                        active_df["lead_vs_ref"] = active_df["cumulative_points"] - active_df["ref_cum"]
                        # Positive = Reference team leads rival; Negative = Reference team trails rival
                        active_df["ref_advantage"] = active_df["ref_cum"] - active_df["cumulative_points"]
                        # Weekly swing: Reference team GW points minus Rival GW points
                        active_df["ref_gw_swing"] = active_df["ref_gw"] - active_df["gw_points"]

                        # KPI Summary Metrics Banner
                        latest_gw = int(active_df["gw_num"].max())
                        latest_df = active_df[active_df["gw_num"] == latest_gw]
                        leader_row = latest_df.sort_values(by="cumulative_points", ascending=False).iloc[0]
                        leader_team = leader_row["team_name"]
                        leader_pts = int(leader_row["cumulative_points"])
                        ref_row = latest_df[latest_df["team_name"] == ref_team]
                        ref_pts = int(ref_row.iloc[0]["cumulative_points"]) if not ref_row.empty else 0
                        ref_rank = int(ref_row.iloc[0]["league_rank"]) if not ref_row.empty else 0
                        gap_to_leader = leader_pts - ref_pts
                        leader_gw_pts = int(leader_row["gw_points"])
                        ref_gw_pts = int(ref_row.iloc[0]["gw_points"]) if not ref_row.empty else 0
                        gw_swing_vs_leader = ref_gw_pts - leader_gw_pts

                        col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
                        with col_kpi1:
                            st.metric("Mini-League Position", f"Rank #{ref_rank}", f"{len(teams)} Total Teams")
                        with col_kpi2:
                            if gap_to_leader > 0:
                                st.metric("Deficit to #1 Leader", f"-{gap_to_leader} pts", f"vs {leader_team}", delta_color="inverse")
                            elif gap_to_leader == 0:
                                st.metric("Mini-League Leader", "🥇 1st Place", "Leader Baseline", delta_color="normal")
                            else:
                                st.metric("Championship Cushion", f"+{abs(gap_to_leader)} pts", f"ahead of {leader_team}", delta_color="normal")
                        with col_kpi3:
                            swing_label = f"+{gw_swing_vs_leader} pts gained" if gw_swing_vs_leader >= 0 else f"{gw_swing_vs_leader} pts lost"
                            st.metric(f"GW{latest_gw} Swing vs #1", swing_label, f"{ref_team} ({ref_gw_pts}p) vs {leader_team} ({leader_gw_pts}p)")
                        with col_kpi4:
                            rem_gws = 38 - latest_gw
                            req_pace = gap_to_leader / rem_gws if rem_gws > 0 else 0.0
                            st.metric("Required Title Pace", f"{req_pace:.1f} pts / GW", f"{rem_gws} GWs Remaining")

                        c_tabs = st.tabs([
                            "⚔️ Relative to Rubies Rangers",
                            "🚀 Cumulative Points Progression",
                            "⚡ Gameweek Net Margin Swings",
                            "🗺️ Rival Matchup Net Heatmap",
                            "🎯 Deficit Bridge & Catch-Up Runway",
                            "🏅 Mini-League Rank Swings"
                        ])

                        # Tab 1: Relative Trajectory vs Reference Team (Rubies Rangers)
                        with c_tabs[0]:
                            st.markdown(f"#### ⚔️ Relative Lead / Deficit Trajectory (Anchored to {ref_team})")
                            st.markdown(f"Tracks rival performance relative to **{ref_team}** (fixed at **0 pts**). When rival curves slope **downward**, {ref_team} is outscoring them and closing the deficit. Curves below **0 pts** represent rivals trailing behind {ref_team}.")

                            col_opt1, col_opt2 = st.columns([2, 3])
                            with col_opt1:
                                view_mode = st.radio(
                                    "Perspective Mode:",
                                    ["Rival Lead / Deficit (+Ahead / -Behind)", f"{ref_team} Net Advantage (+You Lead / -You Trail)"],
                                    index=0,
                                    horizontal=True
                                )

                            y_col = "lead_vs_ref" if "Rival Lead" in view_mode else "ref_advantage"
                            y_label = f"Points Ahead / Behind {ref_team}" if "Rival Lead" in view_mode else f"{ref_team} Net Advantage (Pts)"

                            fig_rel = px.line(
                                active_df,
                                x="gameweek",
                                y=y_col,
                                color="team_name",
                                markers=True,
                                labels={"gameweek": "Gameweek", y_col: y_label, "team_name": "Team"},
                                hover_data={"gw_points": True, "cumulative_points": True, "lead_vs_ref": True}
                            )

                            # Highlight reference team and rivals
                            for tr in fig_rel.data:
                                if tr.name == ref_team:
                                    tr.line.width = 4.5
                                    tr.marker.size = 12
                                    tr.line.color = "#facc15"  # Glowing Gold
                                else:
                                    tr.line.width = 2.2
                                    tr.marker.size = 7

                            # Zero baseline anchor
                            fig_rel.add_hline(
                                y=0,
                                line_dash="dash",
                                line_color="#facc15",
                                line_width=2.5,
                                annotation_text=f"🎯 {ref_team} Baseline (0 pts)",
                                annotation_position="top right",
                                annotation_font_color="#facc15"
                            )

                            # Chip callouts on rival lines
                            for t_name, c_list in chips_map.items():
                                for ch in c_list:
                                    ev = ch.get("event")
                                    ch_code = ch.get("name", "").upper()
                                    if ch_code == "3XC":
                                        b_text = f"🔥 3XC ({t_name})"
                                    elif ch_code == "BBOOST":
                                        b_text = f"⚡ BB ({t_name})"
                                    elif ch_code == "WILDCARD":
                                        b_text = f"🃏 WC ({t_name})"
                                    elif ch_code == "FREEHIT":
                                        b_text = f"🆓 FH ({t_name})"
                                    else:
                                        b_text = f"🎯 {ch_code} ({t_name})"

                                    sub_m = active_df[(active_df["team_name"] == t_name) & (active_df["gw_num"] == ev)]
                                    if not sub_m.empty:
                                        y_pt = sub_m.iloc[0][y_col]
                                        fig_rel.add_annotation(
                                            x=f"GW{ev}",
                                            y=y_pt,
                                            text=b_text,
                                            showarrow=True,
                                            arrowhead=2,
                                            arrowcolor="#38bdf8",
                                            font=dict(size=10, color="#ffffff"),
                                            bgcolor="rgba(14, 165, 233, 0.85)",
                                            bordercolor="#ffffff",
                                            borderwidth=1,
                                            borderpad=3,
                                            ay=-28
                                        )

                            fig_rel.update_layout(
                                template="plotly_dark",
                                paper_bgcolor="rgba(15, 23, 42, 0.6)",
                                plot_bgcolor="rgba(15, 23, 42, 0.6)",
                                hovermode="x unified",
                                margin=dict(l=20, r=20, t=30, b=20),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            st.plotly_chart(fig_rel, use_container_width=True)

                            # Momentum Callout
                            if ref_team == "Rubies Rangers":
                                rr_gw3 = active_df[(active_df["team_name"] == "Rubies Rangers") & (active_df["gw_num"] == 3)]
                                if not rr_gw3.empty:
                                    st.info("💡 **RELATIVE MOMENTUM:** In Gameweek 3, **Rubies Rangers outscored the #1 leader Brennans Bread Today by +8 points** (shrinking the deficit from 64 to 56 pts) and gained **+13 points on Databricks & Chill**, marking a sharp positive slope towards the summit!")

                        # Tab 2: Absolute Cumulative Points Progression
                        with c_tabs[1]:
                            st.markdown("#### The Championship Race — Cumulative Points (GW1 ➔ Present)")
                            fig_cum = px.line(
                                active_df,
                                x="gameweek",
                                y="cumulative_points",
                                color="team_name",
                                markers=True,
                                labels={"gameweek": "Gameweek", "cumulative_points": "Total Points", "team_name": "Team"},
                                hover_data={"gw_points": True, "cumulative_points": True}
                            )

                            for tr in fig_cum.data:
                                if tr.name == ref_team:
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

                                    sub_m = active_df[(active_df["team_name"] == t_name) & (active_df["gw_num"] == ev)]
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

                        # Tab 3: Gameweek Scores & Swings
                        with c_tabs[2]:
                            st.markdown("#### Weekly Scoring Momentum & Head-to-Head Point Swings")
                            
                            view_choice = st.radio(
                                "Scoring Analysis View:",
                                ["All Rivals Gameweek Scores", f"Head-to-Head Net Margin Swing vs Rival ({ref_team})"],
                                horizontal=True
                            )

                            if view_choice == "All Rivals Gameweek Scores":
                                fig_gw = px.bar(
                                    active_df,
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
                            else:
                                rival_candidates = [t for t in all_teams if t != ref_team]
                                sel_rival = st.selectbox(f"Select Rival for Head-to-Head Swing Analysis with {ref_team}:", rival_candidates)
                                
                                h2h_df = active_df[active_df["team_name"] == sel_rival].copy()
                                h2h_df["swing"] = h2h_df["ref_gw_swing"]
                                h2h_df["bar_color"] = np.where(h2h_df["swing"] >= 0, "#10b981", "#ef4444")
                                
                                fig_h2h = go.Figure()
                                fig_h2h.add_trace(go.Bar(
                                    x=h2h_df["gameweek"],
                                    y=h2h_df["swing"],
                                    marker_color=h2h_df["bar_color"],
                                    text=[f"{s:+d} pts" for s in h2h_df["swing"]],
                                    textposition="outside",
                                    name="Net GW Swing"
                                ))
                                fig_h2h.add_hline(y=0, line_dash="solid", line_color="#94a3b8", line_width=1.5)
                                fig_h2h.update_layout(
                                    template="plotly_dark",
                                    paper_bgcolor="rgba(15, 23, 42, 0.6)",
                                    plot_bgcolor="rgba(15, 23, 42, 0.6)",
                                    title=f"Net Gameweek Swing: {ref_team} vs {sel_rival} (Green = {ref_team} Outscored Rival)",
                                    yaxis_title=f"Net Gameweek Points Margin",
                                    xaxis_title="Gameweek",
                                    margin=dict(l=20, r=20, t=40, b=20)
                                )
                                st.plotly_chart(fig_h2h, use_container_width=True)

                                wins = int((h2h_df["swing"] > 0).sum())
                                draws = int((h2h_df["swing"] == 0).sum())
                                losses = int((h2h_df["swing"] < 0).sum())
                                total_swing = int(h2h_df["swing"].sum())
                                sign = "+" if total_swing >= 0 else ""
                                st.caption(f"📊 **Head-to-Head Summary:** {ref_team} record vs **{sel_rival}**: **{wins}W - {draws}D - {losses}L** | Net Cumulative Differential: **{sign}{total_swing} pts**.")

                        # Tab 4: Net Margin Heatmap Matrix
                        with c_tabs[3]:
                            st.markdown(f"#### 🗺️ Gameweek Net Margin Heatmap vs {ref_team}")
                            st.markdown(f"Every cell shows how many points **{ref_team} gained (+) or lost (-)** against that rival in that gameweek. **Emerald green** indicates gameweeks where {ref_team} outscored the rival.")

                            rival_df = active_df[active_df["team_name"] != ref_team]
                            if not rival_df.empty:
                                heat_pivot = rival_df.pivot(index="team_name", columns="gameweek", values="ref_gw_swing").fillna(0)
                                
                                # Order rivals by latest cumulative deficit
                                latest_deficits = rival_df[rival_df["gw_num"] == latest_gw].set_index("team_name")["lead_vs_ref"]
                                ordered_index = [idx for idx in latest_deficits.sort_values(ascending=False).index if idx in heat_pivot.index]
                                heat_pivot = heat_pivot.reindex(ordered_index)

                                fig_heat = go.Figure(data=go.Heatmap(
                                    z=heat_pivot.values,
                                    x=list(heat_pivot.columns),
                                    y=list(heat_pivot.index),
                                    zmid=0,
                                    colorscale=[[0.0, "#ef4444"], [0.5, "#1e293b"], [1.0, "#10b981"]],
                                    text=[[f"{v:+.0f} pts" for v in row] for row in heat_pivot.values],
                                    texttemplate="%{text}",
                                    textfont={"size": 12, "color": "#ffffff"},
                                    hoverongaps=False
                                ))
                                fig_heat.update_layout(
                                    template="plotly_dark",
                                    paper_bgcolor="rgba(15, 23, 42, 0.6)",
                                    plot_bgcolor="rgba(15, 23, 42, 0.6)",
                                    xaxis_title="Gameweek",
                                    yaxis_title="Rival Team (Ranked by Gap)",
                                    margin=dict(l=20, r=20, t=30, b=20)
                                )
                                st.plotly_chart(fig_heat, use_container_width=True)
                            else:
                                st.info("No rivals found to generate heatmap.")

                        # Tab 5: Deficit Bridge & Catch-Up Runway Simulator
                        with c_tabs[4]:
                            st.markdown("#### 🎯 Deficit Bridge & Mini-League Title Runway Simulator")
                            st.markdown(f"Quantitative projection forecasting when **{ref_team}** will catch up to and overtake the #1 league leader (**{leader_team}**) based on weekly point outperformance velocity.")

                            if gap_to_leader > 0 and latest_gw < 38:
                                rem_gw_count = 38 - latest_gw
                                min_req_pace = gap_to_leader / rem_gw_count

                                col_sim1, col_sim2 = st.columns([3, 2])
                                with col_sim1:
                                    sim_velocity = st.slider(
                                        "Projected Outperformance Velocity vs Leader (+pts / GW):",
                                        min_value=0.5,
                                        max_value=8.0,
                                        value=float(min(max(round(min_req_pace + 0.5, 1), 1.5), 6.0)),
                                        step=0.1,
                                        help=f"Net average points {ref_team} expects to gain on the league leader per gameweek."
                                    )
                                with col_sim2:
                                    gw_to_catch = math.ceil(gap_to_leader / sim_velocity)
                                    proj_overtake_gw = latest_gw + gw_to_catch
                                    if proj_overtake_gw <= 38:
                                        st.success(f"🏆 **PROJECTED TITLE OVERTAKE: GW{proj_overtake_gw}**\n\nAt **+{sim_velocity:.1f} pts/GW**, {ref_team} erases the {gap_to_leader} pt deficit in {gw_to_catch} gameweeks!")
                                    else:
                                        st.warning(f"⚠️ **PACE DEFICIT:** At +{sim_velocity:.1f} pts/GW, deficit narrows by {sim_velocity * rem_gw_count:.0f} pts by GW38, but trails leader by {gap_to_leader - sim_velocity * rem_gw_count:.0f} pts. Increase pace to ≥ **{min_req_pace:.1f} pts/GW** to win the title.")

                                # Build Historical & Projected Runway Lines
                                hist_gws = sorted(active_df["gw_num"].unique().tolist())
                                hist_deficits = []
                                for g in hist_gws:
                                    g_leader_pts = active_df[(active_df["gw_num"] == g)]["cumulative_points"].max()
                                    g_ref_sub = active_df[(active_df["team_name"] == ref_team) & (active_df["gw_num"] == g)]
                                    g_ref_pts = g_ref_sub.iloc[0]["cumulative_points"] if not g_ref_sub.empty else 0
                                    hist_deficits.append(int(g_leader_pts - g_ref_pts))

                                proj_gws = list(range(latest_gw, 39))
                                proj_deficits = [gap_to_leader - sim_velocity * (g - latest_gw) for g in proj_gws]

                                fig_runway = go.Figure()
                                # Historical Deficit Line
                                fig_runway.add_trace(go.Scatter(
                                    x=[f"GW{g}" for g in hist_gws],
                                    y=hist_deficits,
                                    mode="lines+markers",
                                    name="Historical Deficit to Leader",
                                    line=dict(color="#f43f5e", width=3.5),
                                    marker=dict(size=8, color="#f43f5e")
                                ))
                                # Projected Runway Line
                                fig_runway.add_trace(go.Scatter(
                                    x=[f"GW{g}" for g in proj_gws],
                                    y=proj_deficits,
                                    mode="lines+markers",
                                    name=f"Projected Runway (+{sim_velocity:.1f} pts/GW)",
                                    line=dict(color="#38bdf8", width=3, dash="dash"),
                                    marker=dict(size=6, color="#38bdf8")
                                ))
                                # Baseline Zero
                                fig_runway.add_hline(
                                    y=0,
                                    line_dash="solid",
                                    line_color="#facc15",
                                    line_width=2.5,
                                    annotation_text="🏆 Mini-League Title Parity (0 pts)",
                                    annotation_position="top right",
                                    annotation_font_color="#facc15"
                                )
                                if proj_overtake_gw <= 38:
                                    fig_runway.add_annotation(
                                        x=f"GW{proj_overtake_gw}",
                                        y=0,
                                        text=f"👑 Projected Overtake (GW{proj_overtake_gw})",
                                        showarrow=True,
                                        arrowhead=2,
                                        arrowcolor="#facc15",
                                        font=dict(size=11, color="#0b0f19", family="Arial Black"),
                                        bgcolor="#facc15",
                                        bordercolor="#ffffff",
                                        borderwidth=1,
                                        ay=-35
                                    )

                                fig_runway.update_layout(
                                    template="plotly_dark",
                                    paper_bgcolor="rgba(15, 23, 42, 0.6)",
                                    plot_bgcolor="rgba(15, 23, 42, 0.6)",
                                    title=f"Championship Trajectory Runway (Deficit: {gap_to_leader} pts ➔ 0 pts)",
                                    yaxis_title="Points Behind Leader (+Deficit / -Surplus)",
                                    xaxis_title="Gameweek Progression",
                                    hovermode="x unified",
                                    margin=dict(l=20, r=20, t=40, b=20),
                                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                                )
                                st.plotly_chart(fig_runway, use_container_width=True)
                            elif gap_to_leader == 0:
                                st.success(f"🥇 **{ref_team} is currently leading the Mini-League!** Deficit is 0.")
                            else:
                                st.info("Season completed or no active deficit.")

                        # Tab 6: Mini-League Rank Volatility
                        with c_tabs[5]:
                            st.markdown("#### Table Position Volatility — Mini-League Rank by Gameweek")
                            fig_rank = px.line(
                                active_df,
                                x="gameweek",
                                y="league_rank",
                                color="team_name",
                                markers=True,
                                labels={"gameweek": "Gameweek", "league_rank": "Mini-League Rank", "team_name": "Team"}
                            )

                            for tr in fig_rank.data:
                                if tr.name == ref_team:
                                    tr.line.width = 4.5
                                    tr.marker.size = 11
                                    tr.line.color = "#facc15"
                                else:
                                    tr.line.width = 2.0
                                    tr.marker.size = 6

                            max_rank = int(active_df["league_rank"].max())
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
    

