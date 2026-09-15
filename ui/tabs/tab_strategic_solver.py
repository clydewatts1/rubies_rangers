"""
Streamlit Tab: 5-Gameweek Strategic Transfer Chessboard (Phase 2 Two-Stage Framework).
Chains Stage 1 Multi-Period Strategic Pathway Generation (MILP / Markowitz Sweeps)
into Stage 2 Stochastic Multi-Gameweek Monte Carlo Simulation.
Governed by .agents/rules/moneyball_strategy.md and .agents/rules/python_standards.md.
"""

from typing import List, Dict, Any, Optional
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from clients.fpl_client import FPLClient
from analytics.strategic.contracts import (
    MultiPeriodGameweekPlan,
    MultiPeriodStrategicSolution,
    EvaluatedStrategicPathway,
    StrategicTwoStageReport,
)
from analytics.strategic.multi_period_solver import MultiPeriodSolver
from analytics.strategic.two_stage_solver import StrategicTwoStageOptimizer
from analytics.strategic.trajectory_engine import build_strategic_squad_state
from ui.styles import render_html


def render_tab_strategic_solver(df: pd.DataFrame, current_squad: List[str]) -> None:
    """Renders the Two-Stage 5-Gameweek Strategic Transfer Chessboard tournament dashboard."""
    st.title("♟️ 5-GW Strategic Transfer Chessboard (Two-Stage Tournament)")
    st.markdown(
        "**Two-Stage Multi-Period Rolling Horizon Framework**:\n"
        "- **Stage 1 (Strategic Pathway Generator)**: Solves multi-period integer linear programs across diverse tactical "
        "paradigms (`max_ev`, `conservative_banking`, `markowitz_multi_period`, `wave_rider`, `differential_climb`, `cost_efficiency`) "
        "modeling dynamic Free Transfer accumulation ($1 \\le \\text{FT} \\le 5$) and hit amortization.\n"
        "- **Stage 2 (Multi-Gameweek Monte Carlo Simulation)**: Stress-tests each 5-week roadmap across 1,000–5,000 parallel season draws, "
        "modeling joint macro fixture states, starter minutes/hazard, auto-substitutions, and vice-captaincy transfers."
    )

    client = FPLClient()
    squad_state = build_strategic_squad_state(client)

    # 1. Control Panel
    st.markdown("---")
    with st.expander("⚙️ Strategic Multi-Period Horizon & Simulation Settings", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            horizon = st.slider(
                "Planning Horizon (GWs)",
                min_value=3,
                max_value=6,
                value=5,
                key="strategic_solver_horizon_slider",
                help="Number of future gameweeks to optimize sequentially."
            )
            sim_count = st.select_slider(
                "Monte Carlo Season Draws",
                options=[1000, 2000, 5000],
                value=2000,
                key="strategic_solver_sim_count",
                help="Number of stochastic season trials simulated over the multi-week horizon."
            )
        with c2:
            starting_bank = st.number_input(
                "Initial Bank Balance (£m)",
                min_value=0.0,
                max_value=15.0,
                value=float(squad_state.bank_balance),
                step=0.1,
                key="strategic_solver_bank_input",
                help="Current cash in bank."
            )
            max_hits = st.selectbox(
                "Max Hits per Gameweek",
                options=[0, 1, 2, 3],
                index=1,
                key="strategic_solver_max_hits_select",
                help="Maximum allowed points deduction transfers per GW (-4 pts each)."
            )
        with c3:
            starting_ft = st.slider(
                "Starting Free Transfers (FT)",
                min_value=1,
                max_value=5,
                value=int(squad_state.free_transfers_available),
                key="strategic_solver_ft_slider",
                help="Current Free Transfers available for next gameweek."
            )
        with c4:
            st.markdown("**Stage 1 Candidate Archetypes:**")
            st.markdown("• **Max EV** (`max_ev`)\n• **FT Banking** (`conservative_banking`)\n• **Markowitz MIQP** (`markowitz_multi_period`)\n• **Wave Rider** (`wave_rider`)\n• **Differential** (`differential_climb`)\n• **Cost Value** (`cost_efficiency`)")

        with st.expander("🔧 Advanced Quantitative Hyperparameters (Discount & Option Multipliers)", expanded=False):
            adv_c1, adv_c2 = st.columns(2)
            with adv_c1:
                gamma = st.slider(
                    "Discount Factor (γ)",
                    min_value=0.80,
                    max_value=1.00,
                    value=0.92,
                    step=0.01,
                    key="strategic_solver_gamma_slider",
                    help="Temporal decay applied to future GW expected points (γ^t)."
                )
            with adv_c2:
                ft_mult = st.slider(
                    "FT Banking Option Multiplier",
                    min_value=0.50,
                    max_value=4.00,
                    value=1.50,
                    step=0.10,
                    key="strategic_solver_ft_mult_slider",
                    help="Utility bonus awarded for carrying unspent FTs forward into future GWs."
                )

    run_btn = st.button("🚀 Run Two-Stage Strategic Tournament", type="primary", key="strategic_run_btn")

    if run_btn or "strategic_two_stage_report" not in st.session_state:
        with st.spinner(f"🤖 Executing Stage 1 Pathway Screening & Stage 2 Monte Carlo Tournament ({sim_count:,} seasons)..."):
            two_stage_opt = StrategicTwoStageOptimizer(fpl_client=client, default_horizon=horizon)
            report: StrategicTwoStageReport = two_stage_opt.run_strategic_tournament(
                initial_squad_names_or_ids=current_squad if current_squad else None,
                horizon=horizon,
                bank=starting_bank,
                initial_ft=starting_ft,
                max_hits_per_gw=max_hits,
                n_sims=sim_count,
            )
            st.session_state["strategic_two_stage_report"] = report

    report = st.session_state.get("strategic_two_stage_report")
    if not report or not report.evaluated_pathways:
        st.error("❌ No strategic candidate pathways generated.")
        return

    top_ev = report.winner_balanced or report.evaluated_pathways[0]
    top_floor = report.winner_safe_floor or report.evaluated_pathways[0]
    top_ceiling = report.winner_explosive_ceiling or report.evaluated_pathways[0]

    # Ensure 3 distinct cards if possible
    top_3 = [top_ev]
    rem1 = [p for p in report.evaluated_pathways if p != top_ev]
    if rem1:
        best_f = max(rem1, key=lambda x: x.floor_p10)
        top_3.append(best_f)
        rem2 = [p for p in rem1 if p != best_f]
        if rem2:
            top_3.append(max(rem2, key=lambda x: x.ceiling_p90))
        else:
            top_3.append(top_ceiling)
    else:
        top_3 = [top_ev, top_floor, top_ceiling]

    # -------------------------------------------------------------
    # 2. Hero KPI Banners
    # -------------------------------------------------------------
    st.markdown("---")
    hk1, hk2, hk3, hk4, hk5 = st.columns(5)
    with hk1:
        st.metric(
            f"Baseline Status Quo ({report.horizon} GWs)",
            f"{report.baseline_mean:.1f} pts",
            f"P10: {report.baseline_p10:.1f} | P90: {report.baseline_p90:.1f}",
            help="Status quo baseline team simulated over the horizon with 0 transfers."
        )
    with hk2:
        net_gain = top_3[0].mean_points - report.baseline_mean
        st.metric(
            "Max EV Net Gain",
            f"{net_gain:+.1f} pts",
            f"via {top_3[0].objective_name.upper()}",
            help="Simulated point lift over status quo baseline across the entire planning window."
        )
    with hk3:
        st.metric(
            "Top Win Probability",
            f"{top_3[0].win_probability_pct:.1f}%",
            "Beats Status Quo",
            help="Fraction of Monte Carlo season trials where the chosen roadmap beats the baseline."
        )
    with hk4:
        tot_transfers = sum(len(p.transfers_in) for p in top_3[0].solution.plans)
        hits = top_3[0].solution.cumulative_hits_taken
        st.metric(
            "Strategic Transfers",
            f"{tot_transfers} Total",
            f"{hits} Hits (-{hits * 4} pts)",
            help="Transfers executed across the horizon."
        )
    with hk5:
        terminal_ft = top_3[0].solution.plans[-1].free_transfers_banked_next if top_3[0].solution.plans else 1
        st.metric(
            "Terminal Banked FTs",
            f"{terminal_ft} Banked",
            f"Bank: £{top_3[0].solution.terminal_bank:.1f}m",
            help="Free Transfers in hand at the conclusion of the planning horizon."
        )

    st.markdown("---")

    # -------------------------------------------------------------
    # 3. The 3 Best Strategic Roadmap Archetype Cards
    # -------------------------------------------------------------
    st.subheader(f"✨ The 3 Best Strategic Multi-Period Roadmaps ({report.horizon}-Gameweek Horizon)")
    st.markdown("Chained Stage 1 Multi-Period MILP + Stage 2 Monte Carlo identifies 3 mathematically distinct strategic pathways:")

    card_c1, card_c2, card_c3 = st.columns(3)
    card_configs = [
        (card_c1, top_3[0], "OPTION 1: 🏆 MAX EXPECTED VALUE", "#facc15"),
        (card_c2, top_3[1] if len(top_3) > 1 else top_3[0], "OPTION 2: 🛡️ MAX FLOOR & CAPITAL SAFETY", "#10b981"),
        (card_c3, top_3[2] if len(top_3) > 2 else top_3[0], "OPTION 3: 🚀 MAX CEILING & FIXTURE WAVE", "#a855f7")
    ]

    for col, path_eval, badge_title, border_color in card_configs:
        with col:
            sol = path_eval.solution
            tot_t = sum(len(p.transfers_in) for p in sol.plans)
            hits = sol.cumulative_hits_taken
            net_lift = path_eval.mean_points - report.baseline_mean
            tin_text = "<br/>".join(
                f"<b style='color:#38bdf8;'>GW{p.gameweek}:</b> +{', '.join(x[1] for x in p.transfers_in)} ➔ -{', '.join(x[1] for x in p.transfers_out)}"
                for p in sol.plans if p.transfers_in
            ) or "<i style='color:#94a3b8;'>Roll all transfers (Build FTs)</i>"

            render_html(f"""
            <div style="background: #1e293b; border: 2px solid {border_color}; border-radius: 12px; padding: 16px; min-height: 440px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <b style="color: {border_color}; font-size: 13px; text-transform: uppercase;">{badge_title}</b>
                        <span style="background: #0f172a; color: #94a3b8; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{path_eval.objective_name}</span>
                    </div>
                    <div style="background: #0f172a; padding: 10px; border-radius: 8px; margin-bottom: 12px; font-size: 12px;">
                        <span style="color: #94a3b8; font-size: 11px; font-weight: bold; text-transform: uppercase;">TRANSFER ROADMAP</span><br/>
                        {tin_text}
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; background: rgba(15, 23, 42, 0.6); padding: 8px; border-radius: 8px;">
                        <div><span style="color: #94a3b8; font-size: 11px;">5-GW Simulated Mean:</span><br/><b style="color: {border_color}; font-size: 16px;">{path_eval.mean_points:.1f} pts</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">Win Probability:</span><br/><b style="color: #38bdf8; font-size: 16px;">{path_eval.win_probability_pct:.1f}%</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">Floor (P10):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{path_eval.floor_p10:.1f} pts</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">Ceiling (P90):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{path_eval.ceiling_p90:.1f} pts</b></div>
                    </div>
                </div>
                <div>
                    <div style="color: #cbd5e1; font-size: 12px; line-height: 1.4; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">
                        <i>{path_eval.rationale}</i>
                    </div>
                    <div style="margin-top: 8px; display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8;">
                        <span>Transfers: <b style="color:white;">{tot_t} ({hits} hits)</b></span>
                        <span>Banked FTs: <b style="color:white;">{sol.plans[-1].free_transfers_banked_next if sol.plans else 1} FT</b></span>
                        <span>Terminal Bank: <b style="color:white;">£{sol.terminal_bank:.1f}m</b></span>
                    </div>
                </div>
            </div>
            """)

    st.markdown("---")

    # -------------------------------------------------------------
    # 4. Multi-Week Stochastic Visualization & Charts
    # -------------------------------------------------------------
    st.subheader("📊 Multi-Week Stochastic Visual Analytics")
    v_tab1, v_tab2 = st.tabs([
        "📈 5-GW Cumulative Trajectory & Confidence Fan Chart",
        "🎯 Risk vs. Reward Efficiency Frontier"
    ])

    with v_tab1:
        st.markdown("#### Weekly Progression: Floor (P10) ➔ Mean ➔ Ceiling (P90)")
        gw_labels = [f"GW{p.gameweek}" for p in top_3[0].solution.plans]
        
        fig_fan = go.Figure()
        
        colors = ["#facc15", "#10b981", "#a855f7"]
        for idx, (p_eval, color) in enumerate(zip(top_3[:3], colors), 1):
            if p_eval.weekly_mean_totals:
                fig_fan.add_trace(go.Scatter(
                    x=gw_labels,
                    y=list(p_eval.weekly_mean_totals),
                    mode="lines+markers",
                    name=f"Opt {idx}: {p_eval.objective_name.upper()} (Mean)",
                    line=dict(color=color, width=3),
                ))
                fig_fan.add_trace(go.Scatter(
                    x=gw_labels,
                    y=list(p_eval.weekly_p90_totals),
                    mode="lines",
                    name=f"Opt {idx} P90 Ceiling",
                    line=dict(color=color, width=1, dash="dot"),
                    showlegend=False
                ))
                fig_fan.add_trace(go.Scatter(
                    x=gw_labels,
                    y=list(p_eval.weekly_p10_totals),
                    mode="lines",
                    name=f"Opt {idx} P10 Floor",
                    line=dict(color=color, width=1, dash="dot"),
                    fill="tonexty",
                    fillcolor=f"rgba(255,255,255,0.04)",
                    showlegend=False
                ))

        fig_fan.update_layout(
            paper_bgcolor="#0b0f19",
            plot_bgcolor="#1e293b",
            font={"color": "#f8fafc"},
            xaxis={"title": "Gameweek", "gridcolor": "rgba(255,255,255,0.08)"},
            yaxis={"title": "Weekly Expected Points", "gridcolor": "rgba(255,255,255,0.08)"},
            legend={"orientation": "h", "y": 1.15, "x": 0.0},
            height=400,
            margin={"l": 20, "r": 20, "t": 40, "b": 20}
        )
        st.plotly_chart(fig_fan, use_container_width=True)

    with v_tab2:
        st.markdown("#### Strategic Efficiency Frontier (All Candidate Roadmaps)")
        if report.all_results_df_data:
            df_results = pd.DataFrame(list(report.all_results_df_data))
            fig_scatter = px.scatter(
                df_results,
                x="floor_p10",
                y="mean_points",
                size="ceiling_p90",
                color="win_prob",
                hover_name="objective",
                hover_data={
                    "transfers_total": True,
                    "hits_total": True,
                    "terminal_ft": True,
                    "terminal_bank": True,
                    "floor_p10": ":.1f",
                    "mean_points": ":.1f",
                    "ceiling_p90": ":.1f",
                    "win_prob": ":.1f%"
                },
                labels={
                    "floor_p10": f"{report.horizon}-GW Downside Floor (P10)",
                    "mean_points": f"{report.horizon}-GW Mean Points",
                    "win_prob": "Win Prob vs Baseline %"
                },
                color_continuous_scale="Viridis"
            )
            fig_scatter.update_layout(
                paper_bgcolor="#0b0f19",
                plot_bgcolor="#1e293b",
                font={"color": "#f8fafc"},
                xaxis={"gridcolor": "rgba(255,255,255,0.08)"},
                yaxis={"gridcolor": "rgba(255,255,255,0.08)"},
                height=400,
                margin={"l": 20, "r": 20, "t": 20, "b": 20}
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown("---")

    # -------------------------------------------------------------
    # 5. Interactive Roadmap Inspector
    # -------------------------------------------------------------
    st.subheader("🔍 Interactive Strategic Roadmap Inspector")
    pathway_options = {
        f"{p.objective_name.upper()} (Mean: {p.mean_points:.1f} pts | Win: {p.win_probability_pct:.1f}%)": p
        for p in report.evaluated_pathways
    }
    selected_label = st.selectbox(
        "Select Roadmap to Inspect Step-by-Step Tactical Breakdown:",
        options=list(pathway_options.keys()),
        key="strategic_selected_pathway_select"
    )
    selected_path = pathway_options[selected_label]
    selected_solution = selected_path.solution

    st.info(f"💡 **Selected Roadmap**: {selected_solution.staged_turnaround_summary}")

    plan_tabs = st.tabs([f"Gameweek {p.gameweek}" for p in selected_solution.plans])

    for tab, plan in zip(plan_tabs, selected_solution.plans):
        with tab:
            gw_m1, gw_m2, gw_m3, gw_m4 = st.columns(4)
            with gw_m1:
                st.metric("Weekly Projected Net xP", f"{plan.net_xp:.1f} pts", f"Gross: {plan.gross_xp:.1f} pts")
            with gw_m2:
                hit_badge = f"{plan.hits_taken} (-{plan.hit_cost_points} pts)" if plan.hits_taken > 0 else "0 (No deduction)"
                st.metric("Hits Deducted", hit_badge)
            with gw_m3:
                st.metric("FT Balance", f"{plan.free_transfers_available} avail ➔ {plan.free_transfers_banked_next} banked next")
            with gw_m4:
                st.metric("Bank Balance", f"£{plan.bank_remaining:.1f}m")

            # Transfers Section
            st.markdown("#### 🔄 Executed Transfers")
            if plan.transfers_in or plan.transfers_out:
                t_col1, t_col2 = st.columns(2)
                with t_col1:
                    st.markdown("**🟢 Transfers IN:**")
                    for pid, pname, cost in plan.transfers_in:
                        st.markdown(f"• **{pname}** — £{cost:.1f}m")
                with t_col2:
                    st.markdown("**🔴 Transfers OUT:**")
                    for pid, pname, cost in plan.transfers_out:
                        st.markdown(f"• **{pname}** — £{cost:.1f}m")
            else:
                st.success("✨ **Roll Transfer (No transfers executed)** — Banking Free Transfer for future multi-transfer leverage.")

            # Starting XI & Bench Section
            st.markdown("#### 🛡️ Optimized Starting XI & Bench")
            c_lineup, c_bench = st.columns([2, 1])

            with c_lineup:
                st.markdown(f"**Starting XI (Captain: 👑 {plan.captain_name} | Vice: 🥈 {plan.vice_captain_name})**")
                starting_rows = []
                for pid, pname, pos, pxp in plan.starting_xi:
                    role_badge = "👑 Captain (2x)" if pid == plan.captain_id else ("🥈 Vice" if pid == plan.vice_captain_id else "Starter")
                    eff_xp = pxp * 2 if pid == plan.captain_id else pxp
                    starting_rows.append({
                        "Pos": pos,
                        "Player": pname,
                        "Role": role_badge,
                        "Base xP": f"{pxp:.2f}",
                        "Effective xP": f"{eff_xp:.2f}",
                    })
                st.dataframe(pd.DataFrame(starting_rows), use_container_width=True)

            with c_bench:
                st.markdown("**Bench (Ordered by xP):**")
                bench_rows = []
                for sub_idx, (pid, pname, pos, pxp) in enumerate(plan.bench, start=1):
                    sub_label = "Sub GK" if pos == "GKP" else f"Sub #{sub_idx - (1 if any(p[2] == 'GKP' for p in plan.bench) and pos != 'GKP' else 0)}"
                    bench_rows.append({
                        "Order": sub_label,
                        "Pos": pos,
                        "Player": pname,
                        "xP": f"{pxp:.2f}",
                    })
                st.dataframe(pd.DataFrame(bench_rows), use_container_width=True)

    # -------------------------------------------------------------
    # 6. Comprehensive Evaluated Roadmaps Leaderboard Table & CSV
    # -------------------------------------------------------------
    st.markdown("---")
    st.subheader("📋 Comprehensive Evaluated Roadmaps Leaderboard")
    if report.all_results_df_data:
        df_lb = pd.DataFrame(list(report.all_results_df_data))
        renames = {
            "objective": "Strategy Objective",
            "transfers_total": "Total Transfers",
            "hits_total": "Hits Taken",
            "terminal_ft": "Banked FTs",
            "terminal_bank": "Terminal Bank (£m)",
            "net_xp_projected": "Projected Net xP",
            "mean_points": "Simulated Mean Pts",
            "floor_p10": "P10 Floor",
            "median_p50": "P50 Median",
            "ceiling_p90": "P90 Ceiling",
            "win_prob": "Win Prob vs Baseline %",
            "sharpe": "Sharpe Ratio",
            "roadmap_summary": "Roadmap Action Summary"
        }
        df_display = df_lb.rename(columns=renames)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        csv_data = df_display.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Strategic Roadmaps Evaluation (CSV)",
            data=csv_data,
            file_name=f"strategic_two_stage_{report.horizon}gw_sim{sim_count}.csv",
            mime="text/csv",
            key="strategic_csv_download_btn"
        )
