"""
Streamlit Tab: Two-Stage Tournament (Screen & Simulate)
Integrates Stage 1 (Multi-Objective MILP) with Stage 2 (Monte Carlo Tournament)
Includes complete stochastic visual analytics suite: Hero KPIs, 3 Archetype Cards,
KDE distribution curves, P10/P50/P90 range comparison, scatter frontier, and CSV export.
"""

import streamlit as st
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from typing import List
import pandas as pd

from analytics.optimizer import FPLOptimizer
from analytics.montecarlo import MonteCarloEngine
from analytics.two_stage_optimizer import TwoStageOptimizer
from ui.styles import render_html


def render_tab_two_stage(df: pd.DataFrame, current_squad: List[str], bank: float = 3.7):
    """Render Two-Stage Screen & Simulate Tournament view with complete graphical suite."""
    st.title("⚔️ Two-Stage Optimization Tournament (Screen & Simulate)")
    st.markdown(r"""
    **Moneyball Chained Architecture:**
    - **Stage 1: Multi-Objective MILP Screening (~40ms)** solves the global combinatorial knapsack across all 650+ Premier League players across 4 distinct objective weight vectors (`fdr_moneyball`, `xgi`, `setpiece_moneyball`, `form`) with canonical `frozenset` deduplication.
    - **Stage 2: Monte Carlo Stochastic Tournament** stress-tests each unique candidate squad across 1,000–10,000 parallel gameweek draws, modeling Gaussian minutes jitter, bench auto-substitutions, and full risk distributions ($P_{10}, P_{50}, P_{90}$).
    """)

    # -------------------------------------------------------------
    # Simulation Settings & Control Panel
    # -------------------------------------------------------------
    with st.expander("⚙️ Two-Stage Tournament Settings & Constraints", expanded=True):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            num_transfers = st.radio(
                "Number of Transfers",
                [1, 2, 3],
                format_func=lambda x: f"{x} Transfer{' (Single Swap)' if x == 1 else 's'}",
                horizontal=True,
                key="two_stage_transfers"
            )
            free_transfers = st.slider(
                "Free Transfers Available",
                1, 5, 1,
                help="If transfers exceed free quota, a -4 point hit penalty is deducted from the simulation.",
                key="two_stage_free"
            )
        with sc2:
            bank_balance = st.slider(
                "Available Bank (£m)",
                0.0, 15.0, float(bank), 0.1,
                key="two_stage_bank"
            )
            sim_count = st.select_slider(
                "Monte Carlo Simulations",
                options=[1000, 2500, 5000, 10000],
                value=2500,
                help="Higher simulation counts yield tighter probability confidence intervals.",
                key="two_stage_sims"
            )
        with sc3:
            st.markdown("**Strategic Objectives Evaluated in Stage 1:**")
            st.markdown("""
            • 🏆 **Balanced**: Fixture-Adjusted Moneyball (`fdr_moneyball`)  
            • ⚡ **Attack**: Understat Shot Quality (`xgi`)  
            • 🎯 **Dead-Ball**: Set-Piece & Penalty Duties (`setpiece`)  
            • 🔥 **Momentum**: 30-Day Form Streak (`form`)
            """)

    hit_penalty = max(0, num_transfers - free_transfers) * 4
    if hit_penalty > 0:
        st.warning(f"⚠️ **Transfer Hit Penalty Active:** Making {num_transfers} transfer(s) with {free_transfers} free transfer incurs a **-{hit_penalty} point deduction**, factored into all simulation outcomes.")

    run_clicked = st.button("🚀 Run Two-Stage Tournament", type="primary", key="two_stage_run_btn")

    if run_clicked:
        with st.spinner(f"Executing Stage 1 MILP Screening & Stage 2 Monte Carlo Tournament ({sim_count:,} draws)..."):
            opt = FPLOptimizer(df)
            mc = MonteCarloEngine()
            orchestrator = TwoStageOptimizer(opt, mc)

            report = orchestrator.run_screen_and_simulate(
                current_squad=current_squad,
                bank=bank_balance,
                num_transfers=num_transfers,
                n_sims=sim_count
            )
            st.session_state["two_stage_report"] = report
            st.session_state["two_stage_hit_penalty"] = hit_penalty

    report = st.session_state.get("two_stage_report")
    hit_pen = st.session_state.get("two_stage_hit_penalty", 0)

    if report is None:
        st.info("💡 Click **'Run Two-Stage Tournament'** above to generate Pareto candidates via MILP and stress-test them through Monte Carlo simulations.")
        return

    evaluated = report.evaluated_candidates
    if not evaluated:
        st.error("❌ No valid Pareto candidate squads found within current budget and club limits.")
        return

    # Extract top 3 archetypes
    top_ev = report.winner_balanced or evaluated[0]
    top_floor = report.winner_safe_floor or evaluated[0]
    top_ceiling = report.winner_explosive_ceiling or evaluated[0]

    # Ensure 3 distinct cards if possible
    top_3 = [top_ev]
    remaining = [c for c in evaluated if c != top_ev]
    if remaining:
        best_f = max(remaining, key=lambda x: x.floor_p10)
        top_3.append(best_f)
        remaining2 = [c for c in remaining if c != best_f]
        if remaining2:
            top_3.append(max(remaining2, key=lambda x: x.ceiling_p90))
        else:
            top_3.append(top_ceiling)
    else:
        top_3 = [top_ev, top_floor, top_ceiling]

    # -------------------------------------------------------------
    # Hero KPIs Container
    # -------------------------------------------------------------
    st.markdown("---")
    hk1, hk2, hk3, hk4, hk5 = st.columns(5)
    hk1.metric(
        "Baseline Squad xP",
        f"{report.baseline_mean:.1f} pts",
        f"P10: {report.baseline_p10:.1f} | P90: {report.baseline_p90:.1f}"
    )
    hk2.metric(
        "Transfer Hit Penalty",
        f"-{hit_pen} pts",
        "Free Move" if hit_pen == 0 else f"{num_transfers - free_transfers} hit(s)"
    )
    hk3.metric(
        "Max EV Net Gain",
        f"{top_3[0].net_gain_vs_current:+.2f} pts",
        f"via {top_3[0].candidate.objective_name.upper()}"
    )
    hk4.metric(
        "Top Win Probability",
        f"{top_3[0].win_probability_pct:.1f}%",
        "Beats Current Squad"
    )
    hk5.metric(
        "Candidates Screened",
        f"{len(evaluated)} Unique Plans",
        f"Bank: £{top_3[0].bank_remaining:.1f}m"
    )

    st.markdown("---")

    # -------------------------------------------------------------
    # Section 1: The 3 Best Strategic Transfer Archetype Cards
    # -------------------------------------------------------------
    st.subheader("✨ The 3 Best Strategic Transfer Plans (Monte Carlo Tournament Modeled)")
    st.markdown("Unlike simple linear models, the Two-Stage optimizer surfaces 3 mathematically distinct strategic archetypes:")

    card_col1, card_col2, card_col3 = st.columns(3)

    archetype_configs = [
        (card_col1, top_3[0], "OPTION 1: 🏆 MAX EXPECTED VALUE", "#facc15"),
        (card_col2, top_3[1] if len(top_3) > 1 else top_3[0], "OPTION 2: 🛡️ MAX FLOOR & SAFETY", "#10b981"),
        (card_col3, top_3[2] if len(top_3) > 2 else top_3[0], "OPTION 3: 🚀 MAX CEILING & DIFFERENTIAL", "#a855f7")
    ]

    for col, opt_eval, badge_title, border_color in archetype_configs:
        with col:
            hit_badge = (
                f'<span style="background: #dc2626; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 6px;">-{hit_pen} pts hit</span>'
                if hit_pen > 0
                else '<span style="background: #15803d; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 6px;">Free Move</span>'
            )
            render_html(f"""
            <div style="background: #1e293b; border: 2px solid {border_color}; border-radius: 12px; padding: 16px; min-height: 400px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <b style="color: {border_color}; font-size: 13px; text-transform: uppercase;">{badge_title}</b>
                        {hit_badge}
                    </div>
                    <div style="background: #0f172a; padding: 10px; border-radius: 8px; margin-bottom: 12px; border-left: 3px solid #ef4444;">
                        <span style="color: #ef4444; font-size: 11px; font-weight: bold; text-transform: uppercase;">SELL OUT</span><br/>
                        <b style="color: #ffffff; font-size: 15px;">{opt_eval.out_player}</b> <span style="color: #94a3b8; font-size: 12px;">({opt_eval.out_club} • £{opt_eval.out_cost}m)</span><br/>
                        <span style="color: #94a3b8; font-size: 12px;">Baseline Simulated: <b style="color: #cbd5e1;">{opt_eval.out_mean:.2f} pts</b></span>
                    </div>
                    <div style="background: #0f172a; padding: 10px; border-radius: 8px; margin-bottom: 12px; border-left: 3px solid #22c55e;">
                        <span style="color: #22c55e; font-size: 11px; font-weight: bold; text-transform: uppercase;">BUY IN</span><br/>
                        <b style="color: #ffffff; font-size: 15px;">{opt_eval.in_player}</b> <span style="color: #94a3b8; font-size: 12px;">({opt_eval.in_club} • £{opt_eval.in_cost}m)</span><br/>
                        <span style="color: #94a3b8; font-size: 12px;">Projected Score: <b style="color: #22c55e;">{opt_eval.in_mean:.2f} pts</b></span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; background: rgba(15, 23, 42, 0.6); padding: 8px; border-radius: 8px;">
                        <div><span style="color: #94a3b8; font-size: 11px;">Net Gain:</span><br/><b style="color: {border_color}; font-size: 16px;">{opt_eval.net_gain_vs_current:+.2f} pts</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">Win Probability:</span><br/><b style="color: #38bdf8; font-size: 16px;">{opt_eval.win_probability_pct:.1f}%</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">Floor (P10):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{opt_eval.floor_p10:.1f} pts</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">Ceiling (P90):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{opt_eval.ceiling_p90:.1f} pts</b></div>
                    </div>
                </div>
                <div>
                    <div style="color: #cbd5e1; font-size: 12px; line-height: 1.4; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">
                        <i>{opt_eval.rationale}</i>
                    </div>
                    <div style="margin-top: 8px; text-align: right;">
                        <span style="color: #94a3b8; font-size: 11px;">Bank Left: <b style="color: white;">£{opt_eval.bank_remaining:.1f}m</b></span>
                    </div>
                </div>
            </div>
            """)

    st.markdown("---")

    # -------------------------------------------------------------
    # Section 2: Interactive Stochastic Analysis & Visualizations
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
        if len(report.baseline_raw_totals) > 0:
            fig_dist.add_trace(go.Histogram(
                x=report.baseline_raw_totals,
                histnorm="probability density",
                name="Current Squad (Baseline)",
                marker_color="#94a3b8",
                opacity=0.35,
                nbinsx=40
            ))

        # Archetype traces
        trace_colors = ["#facc15", "#10b981", "#a855f7"]
        for idx, (opt_eval, color) in enumerate(zip(top_3[:3], trace_colors), 1):
            if len(opt_eval.raw_totals) > 0:
                fig_dist.add_trace(go.Histogram(
                    x=opt_eval.raw_totals,
                    histnorm="probability density",
                    name=f"Option {idx}: {opt_eval.in_player} ({opt_eval.candidate.objective_name})",
                    marker_color=color,
                    opacity=0.45,
                    nbinsx=40
                ))

        # Vertical dashed lines for means
        fig_dist.add_vline(
            x=report.baseline_mean,
            line_dash="dash",
            line_color="#94a3b8",
            annotation_text=f"Base: {report.baseline_mean:.1f}",
            annotation_position="top left"
        )
        if top_3 and len(top_3[0].raw_totals) > 0:
            fig_dist.add_vline(
                x=top_3[0].mean_points,
                line_dash="dash",
                line_color="#facc15",
                annotation_text=f"Opt 1: {top_3[0].mean_points:.1f}",
                annotation_position="top right"
            )

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

        comp_names = ["Current Baseline"] + [
            f"Opt {i}: {cand.in_player} ({cand.candidate.objective_name})"
            for i, cand in enumerate(top_3[:3], 1)
        ]
        p10_vals = [report.baseline_p10] + [c.floor_p10 for c in top_3[:3]]
        p50_vals = [round(float(report.baseline_mean), 1)] + [c.median_p50 for c in top_3[:3]]
        p90_vals = [report.baseline_p90] + [c.ceiling_p90 for c in top_3[:3]]

        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            name="P10 Floor (Safety Net)",
            y=comp_names,
            x=p10_vals,
            orientation="h",
            marker_color="#38bdf8",
            text=[f"{v:.1f}" for v in p10_vals],
            textposition="inside"
        ))
        fig_bar.add_trace(go.Bar(
            name="P50 Median (Expected)",
            y=comp_names,
            x=[max(0.0, p50 - p10) for p50, p10 in zip(p50_vals, p10_vals)],
            base=p10_vals,
            orientation="h",
            marker_color="#facc15",
            text=[f"{v:.1f}" for v in p50_vals],
            textposition="inside"
        ))
        fig_bar.add_trace(go.Bar(
            name="P90 Ceiling (Haul Potential)",
            y=comp_names,
            x=[max(0.0, p90 - p50) for p90, p50 in zip(p90_vals, p50_vals)],
            base=p50_vals,
            orientation="h",
            marker_color="#ec4899",
            text=[f"{v:.1f}" for v in p90_vals],
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
        st.markdown("#### Risk vs. Reward Efficiency Frontier (All Evaluated Pareto Candidates)")
        st.markdown("Each bubble represents an optimal Pareto candidate plan. Top-right = High Net Gain & High Safety Floor; Larger bubble = Higher 90th-percentile haul upside.")

        df_all = report.all_results_df
        if not df_all.empty:
            fig_scatter = px.scatter(
                df_all,
                x="floor_p10",
                y="net_mean_gain",
                size="ceiling_p90",
                color="win_prob",
                hover_name="in_player",
                hover_data={
                    "out_player": True,
                    "objective": True,
                    "net_mean_gain": ":+.2f",
                    "win_prob": ":.1f%",
                    "cost_diff": ":+.1f",
                    "bank_remaining": ":.1f",
                    "floor_p10": ":.1f",
                    "ceiling_p90": ":.1f"
                },
                labels={
                    "floor_p10": "10th-Percentile Floor (Downside Safety)",
                    "net_mean_gain": "Net Expected Gain (pts/GW)",
                    "win_prob": "Win Probability %",
                    "ceiling_p90": "90th-Percentile Ceiling"
                },
                color_continuous_scale="Viridis"
            )

            fig_scatter.add_hline(
                y=0,
                line_dash="dash",
                line_color="#ef4444",
                annotation_text="Break-Even (0 Net Gain)"
            )

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
        else:
            st.info("No candidates available for scatter plot.")

    st.markdown("---")

    # -------------------------------------------------------------
    # Section 3: Comprehensive Evaluated Candidates Table & CSV
    # -------------------------------------------------------------
    st.subheader(f"📋 Comprehensive Evaluated Pareto Candidates ({len(evaluated)} Unique Plans)")
    st.markdown("Search, sort, and inspect every Pareto-optimal candidate plan screened by Stage 1 MILP and evaluated by Stage 2 Monte Carlo.")

    df_all = report.all_results_df
    if not df_all.empty:
        display_cols = [
            "out_player", "in_player", "objective", "in_pos", "in_club",
            "cost_diff", "bank_remaining", "net_mean_gain", "win_prob",
            "floor_p10", "median_p50", "ceiling_p90", "sharpe", "fdr_next_5"
        ]
        available_cols = [c for c in display_cols if c in df_all.columns]
        renames = {
            "out_player": "Sell Out",
            "in_player": "Buy In",
            "objective": "Objective Sweep",
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

        df_display = df_all[available_cols].rename(columns=renames)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        csv_data = df_display.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Full Two-Stage Tournament Evaluation (CSV)",
            data=csv_data,
            file_name=f"two_stage_tournament_{num_transfers}x_sim{sim_count}.csv",
            mime="text/csv",
            key="two_stage_csv_download"
        )
