"""
Streamlit Tab: Two-Stage 15-Man Squad Draft Tournament (Screen & Simulate) & Player Explorer

Architecture:
- Stage 1: Fast Multi-Objective MILP global knapsack screening across configured Pareto objective vectors
  (balanced, forward_alpha, high_attack, defensive_solidity, weather_resilience, setpiece_focus, etc.)
  with canonical frozenset deduplication.
- Stage 2: Monte Carlo Stochastic Tournament simulating all drafted 15-man squad candidates across
  500–10,000 parallel gameweek draws, modeling Gaussian minutes jitter, bench auto-substitutions,
  optimal starting XI lineup selection, and distribution metrics (E[V], P10, P50, P90, Sharpe, Win Prob).
- Surfaces the Top 3 Strategic Archetypes:
  1. 🏆 Max Expected Value (Balanced Core)
  2. 🛡️ Max Safety Floor (P10 Resilience)
  3. 🚀 Max Haul Ceiling (P90 Differential Upside)
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Dict, Any
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from ui.styles import render_html
from analytics.optimizer import FPLOptimizer
from analytics.montecarlo import MonteCarloEngine
from analytics.two_stage_optimizer import (
    TwoStageOptimizer,
    TwoStageOptimizationReport,
    StochasticSquadEvaluation,
    ParetoCandidateSquad
)
from analytics.profile_manager import ProfileManager, slugify_name
from analytics.profile_contracts import ManagerProfile, ProfileType
import config_manager


def render_tab_draft(
    df: pd.DataFrame,
    opt: FPLOptimizer,
    current_squad: Optional[List[str]] = None,
    objective: str = "fdr_moneyball",
    mc_engine: Optional[MonteCarloEngine] = None
) -> None:
    """
    Renders the flagship Two-Stage 15-Man Squad Draft Tournament.
    """
    st.title("🏆 Two-Stage 15-Man Squad Draft Tournament (Screen & Simulate)")
    st.markdown(r"""
    **Moneyball Chained Architecture for Squad Drafting:**
    - **Stage 1: Multi-Objective MILP Knapsack (~50ms)** solves the global combinatorial knapsack across all 650+ Premier League players,
      enforcing FPL squad constraints (15 players: 2 GKP, 5 DEF, 5 MID, 3 FWD; max 3 per club; within budget) across diverse tactical Pareto objective vectors.
    - **Stage 2: Monte Carlo Stochastic Tournament** stress-tests every drafted squad across 500–5,000 parallel gameweek scenarios,
      accounting for minutes stochasticity, optimal lineup selection (Starting XI vs Bench 4), bench auto-substitutions, and joint covariance.
    - **Surfaces the Top 3 Archetypes:** **Max Expected Value** (Balanced Core), **Max Floor** (High-floor Safety Net), and **Max Ceiling** (Explosive Upside).
    """)

    # Retrieve configured Pareto objectives
    current_objs = config_manager.get_pareto_objectives()
    active_objs = [o for o in current_objs if o.get("enabled", True)]

    # Available player names for locks & excludes
    all_player_names = sorted(df["web_name"].dropna().unique().tolist()) if "web_name" in df.columns else []

    # -------------------------------------------------------------
    # 1. Executive Criteria & Constraints Control Panel
    # -------------------------------------------------------------
    with st.expander("⚙️ Squad Draft Criteria & Tournament Parameters", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            budget = st.slider(
                "Total Squad Budget (£m)",
                min_value=90.0,
                max_value=110.0,
                value=100.0,
                step=0.5,
                help="Official FPL starting budget is £100.0m. Adjust for team value variations.",
                key="draft_budget_slider"
            )
            lock_players = st.multiselect(
                "🔒 Must-Have Player Locks (Optional)",
                options=all_player_names,
                default=[],
                help="Selected players are strictly forced into the 15-man squad for all candidate sweeps.",
                key="draft_lock_multiselect"
            )
        with c2:
            exclude_players = st.multiselect(
                "🚫 Exclude Players (Optional)",
                options=all_player_names,
                default=[],
                help="Selected players will be barred from being drafted (e.g., long-term injuries or rotation risks).",
                key="draft_exclude_multiselect"
            )
            sim_count = st.select_slider(
                "Monte Carlo Simulations",
                options=[500, 1000, 1500, 2500, 5000],
                value=1500,
                help="Higher simulation draws yield tighter confidence intervals for P10/P90 tail risk.",
                key="draft_sim_slider"
            )
        with c3:
            st.markdown(f"**Active Stage 1 Pareto Dimensions ({len(active_objs)} Enabled):**")
            for o in active_objs[:5]:
                tier_badge = "🌟" if o.get("tier") == "core" else "🎯"
                st.markdown(f"• {tier_badge} **{o['label'].replace('_', ' ').title()}** (`{o['metric']}`)")
            if len(active_objs) > 5:
                st.caption(f"+ {len(active_objs) - 5} more enabled in settings")

    # -------------------------------------------------------------
    # 2. Configurable Pareto Objectives Panel
    # -------------------------------------------------------------
    with st.expander("🛠️ Configure Pareto-Efficient Objectives for Draft Sweeps", expanded=False):
        st.markdown("""
        Configure which tactical weight vectors Stage 1 MILP sweeps across when assembling 15-man draft candidates.
        Enabling more dimensions expands strategic diversity across candidate squads.
        """)
        st.markdown("##### ⚡ Quick Strategy Presets")
        presets = {
            "🌟 Core Moneyball (5)": ["balanced", "forward_alpha", "weather_resilience", "high_attack", "setpiece_focus"],
            "⚡ Attacking Edge (4)": ["high_attack", "forward_alpha", "low_block_threat", "mean_reversion"],
            "🛡️ Defensive & Weather (4)": ["defensive_solidity", "weather_resilience", "setpiece_focus", "balanced"],
            "📈 Value & Momentum (4)": ["cost_efficiency", "momentum", "mean_reversion", "odds_implied_xp"],
            "🌌 All 11 Dimensions": [o["label"] for o in current_objs],
        }
        p_cols = st.columns(len(presets))
        for p_idx, (p_name, p_keys) in enumerate(presets.items()):
            with p_cols[p_idx]:
                if st.button(p_name, key=f"draft_preset_btn_{p_idx}", use_container_width=True):
                    for o in current_objs:
                        o["enabled"] = (o["label"] in p_keys)
                    config_manager.update_pareto_objectives(current_objs)
                    st.rerun()

        st.markdown("---")
        st.markdown("##### ⚙️ Custom Objective Toggles")
        updated_objs = []
        c_left, c_right = st.columns(2)
        half = (len(current_objs) + 1) // 2
        for idx, obj in enumerate(current_objs):
            col = c_left if idx < half else c_right
            with col:
                tier_badge = "🌟 CORE" if obj.get("tier") == "core" else "🎯 CONTEXTUAL"
                chk = st.checkbox(
                    f"{tier_badge}: **{obj['label'].replace('_', ' ').title()}** (`{obj['metric']}`)",
                    value=bool(obj.get("enabled", True)),
                    help=obj.get("description", ""),
                    key=f"draft_pareto_chk_{obj['label']}"
                )
                updated_objs.append({
                    "label": obj["label"],
                    "metric": obj["metric"],
                    "enabled": chk,
                    "tier": obj.get("tier", "core"),
                    "description": obj.get("description", "")
                })

        if st.button("💾 Save Objectives to config.yaml", key="draft_save_pareto_btn", type="secondary"):
            config_manager.update_pareto_objectives(updated_objs)
            st.success("✅ Pareto objectives successfully updated and saved to `config.yaml`!")
            st.rerun()

    # -------------------------------------------------------------
    # 3. Action Buttons & Execution
    # -------------------------------------------------------------
    btn_col1, btn_col2 = st.columns([2, 1])
    with btn_col1:
        run_tournament = st.button(
            "🚀 Run 15-Man Two-Stage Draft Tournament",
            type="primary",
            use_container_width=True,
            key="btn_run_draft_tournament"
        )
    with btn_col2:
        quick_milp = st.button(
            "⚡ Quick Single-MILP Draft (Instant)",
            type="secondary",
            use_container_width=True,
            key="btn_quick_draft_milp"
        )

    # Execution logic
    if run_tournament:
        with st.spinner(f"Running Stage 1 Multi-Objective MILP Screening & Stage 2 Monte Carlo Tournament ({sim_count:,} draws)..."):
            mc = mc_engine or MonteCarloEngine()
            orchestrator = TwoStageOptimizer(opt, mc)
            report = orchestrator.run_draft_tournament(
                budget=budget,
                lock_players=lock_players if lock_players else None,
                exclude_players=exclude_players if exclude_players else None,
                n_sims=sim_count,
                reference_squad=current_squad
            )
            st.session_state["two_stage_draft_report"] = report
            st.session_state["quick_draft_result"] = None

    elif quick_milp:
        with st.spinner(f"Solving single-objective MILP squad ({objective})..."):
            quick_res = opt.optimize_squad(
                budget=budget,
                objective=objective,
                lock_players=lock_players if lock_players else None,
                exclude_players=exclude_players if exclude_players else None
            )
            st.session_state["quick_draft_result"] = quick_res
            st.session_state["two_stage_draft_report"] = None

    # Handle quick MILP fallback display if triggered
    quick_res = st.session_state.get("quick_draft_result")
    if quick_res is not None:
        _render_quick_milp_result(quick_res, df)
        st.markdown("---")

    report: Optional[TwoStageOptimizationReport] = st.session_state.get("two_stage_draft_report")

    if report is None and quick_res is None:
        st.info("💡 Click **'Run 15-Man Two-Stage Draft Tournament'** above to screen Pareto candidates and stress-test them under stochastic simulation.")
        _render_player_explorer_section(df)
        return

    if report is not None:
        evaluated = report.evaluated_candidates
        if not evaluated:
            st.error("❌ No valid 15-man squad candidates could be formed within current budget and constraints. Try relaxing player locks or increasing budget.")
            return

        # Top 3 Archetypes
        top_ev = report.winner_balanced or evaluated[0]
        top_floor = report.winner_safe_floor or evaluated[0]
        top_ceiling = report.winner_explosive_ceiling or evaluated[0]

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
        # 4. Hero KPIs Container
        # -------------------------------------------------------------
        st.markdown("---")
        hk1, hk2, hk3, hk4, hk5 = st.columns(5)
        hk1.metric(
            "Current Squad xP (Baseline)",
            f"{report.baseline_mean:.1f} pts",
            f"P10: {report.baseline_p10:.1f} | P90: {report.baseline_p90:.1f}"
        )
        hk2.metric(
            "Top Draft Pick EV",
            f"{top_3[0].mean_points:.1f} pts",
            f"via {top_3[0].candidate.objective_name.upper()}"
        )
        hk3.metric(
            "Net Gain vs Current Squad",
            f"{top_3[0].net_gain_vs_current:+.2f} pts",
            "Expected Advantage" if top_3[0].net_gain_vs_current >= 0 else "Below Baseline"
        )
        hk4.metric(
            "Top Win Probability",
            f"{top_3[0].win_probability_pct:.1f}%",
            "Beats Current Squad"
        )
        hk5.metric(
            "Candidates Screened",
            f"{len(evaluated)} Unique Squads",
            f"Bank Left: £{top_3[0].bank_remaining:.1f}m"
        )

        st.markdown("---")

        # -------------------------------------------------------------
        # 5. The 3 Best Strategic Draft Archetype Cards
        # -------------------------------------------------------------
        st.subheader("✨ The 3 Best Strategic 15-Man Draft Archetypes (Monte Carlo Modeled)")
        st.markdown("The Two-Stage solver surfaces three mathematically distinct draft philosophies:")

        card_col1, card_col2, card_col3 = st.columns(3)
        archetype_configs = [
            (card_col1, top_3[0], "OPTION 1: 🏆 MAX EXPECTED VALUE", "#facc15", "Balanced Core"),
            (card_col2, top_3[1] if len(top_3) > 1 else top_3[0], "OPTION 2: 🛡️ MAX FLOOR & SAFETY", "#10b981", "Safe Floor"),
            (card_col3, top_3[2] if len(top_3) > 2 else top_3[0], "OPTION 3: 🚀 MAX CEILING & DIFFERENTIAL", "#a855f7", "Explosive Ceiling")
        ]

        for col, opt_eval, badge_title, border_color, arch_tag in archetype_configs:
            with col:
                # Top talismans in squad
                talisman_str = opt_eval.in_player or ", ".join(opt_eval.candidate.squad_names[:3])
                render_html(f"""
                <div style="background: #1e293b; border: 2px solid {border_color}; border-radius: 12px; padding: 16px; min-height: 420px; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <b style="color: {border_color}; font-size: 13px; text-transform: uppercase;">{badge_title}</b>
                            <span style="background: #334155; color: #e2e8f0; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{opt_eval.candidate.objective_name.upper()}</span>
                        </div>
                        <div style="background: #0f172a; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 3px solid {border_color};">
                            <span style="color: #94a3b8; font-size: 11px; font-weight: bold; text-transform: uppercase;">KEY TALISMANS</span><br/>
                            <b style="color: #ffffff; font-size: 14px;">{talisman_str}</b><br/>
                            <span style="color: #cbd5e1; font-size: 12px;">Total Cost: <b style="color: #ffffff;">£{opt_eval.candidate.total_cost:.1f}m</b> | Bank: <b style="color: #38bdf8;">£{opt_eval.bank_remaining:.1f}m</b></span>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; background: rgba(15, 23, 42, 0.6); padding: 10px; border-radius: 8px;">
                            <div><span style="color: #94a3b8; font-size: 11px;">Expected Score (Mean):</span><br/><b style="color: {border_color}; font-size: 17px;">{opt_eval.mean_points:.1f} pts</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Win Probability:</span><br/><b style="color: #38bdf8; font-size: 17px;">{opt_eval.win_probability_pct:.1f}%</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Floor (P10):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{opt_eval.floor_p10:.1f} pts</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Ceiling (P90):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{opt_eval.ceiling_p90:.1f} pts</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Net Gain vs Baseline:</span><br/><b style="color: {'#22c55e' if opt_eval.net_gain_vs_current >= 0 else '#ef4444'}; font-size: 14px;">{opt_eval.net_gain_vs_current:+.2f} pts</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Sharpe Ratio:</span><br/><b style="color: #cbd5e1; font-size: 14px;">{opt_eval.sharpe_ratio:.2f}</b></div>
                        </div>
                    </div>
                </div>
                """)

        # -------------------------------------------------------------
        # 6. Graphical Visual Analytics Suite
        # -------------------------------------------------------------
        st.markdown("---")
        st.subheader("📊 Stochastic Distribution & Tail Risk Analysis")
        gv_tab1, gv_tab2, gv_tab3 = st.tabs([
            "📈 Probability Density Overlay",
            "📊 Points Range (P10 ➔ P50 ➔ P90)",
            "🎯 Risk vs. Reward Frontier"
        ])

        with gv_tab1:
            st.markdown("#### Monte Carlo Density Comparison: Draft Archetypes vs. Current Squad Baseline")
            fig_dist = go.Figure()

            # Baseline density
            if report.baseline_raw_totals is not None and len(report.baseline_raw_totals) > 0:
                fig_dist.add_trace(go.Histogram(
                    x=report.baseline_raw_totals,
                    histnorm="probability density",
                    name="Current Squad Baseline",
                    marker_color="#64748b",
                    opacity=0.35,
                    nbinsx=40
                ))

            # Add traces for top 3 archetypes
            colors = ["#facc15", "#10b981", "#a855f7"]
            for idx, cand in enumerate(top_3[:3]):
                if cand.raw_totals is not None and len(cand.raw_totals) > 0:
                    fig_dist.add_trace(go.Histogram(
                        x=cand.raw_totals,
                        histnorm="probability density",
                        name=f"Opt {idx + 1}: {cand.candidate.objective_name.upper()} ({cand.mean_points:.1f} pts)",
                        marker_color=colors[idx],
                        opacity=0.45,
                        nbinsx=40
                    ))

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
                height=420,
                margin={"l": 20, "r": 20, "t": 40, "b": 20}
            )
            st.plotly_chart(fig_dist, use_container_width=True)

        with gv_tab2:
            st.markdown("#### Squad Points Range: Floor (P10) ➔ Median (P50) ➔ Ceiling (P90)")
            comp_names = ["Current Baseline"] + [
                f"Opt {i}: {cand.candidate.objective_name.upper()}"
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
                name="P90 Ceiling (Haul Upside)",
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
                height=350,
                margin={"l": 20, "r": 20, "t": 40, "b": 20}
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with gv_tab3:
            st.markdown("#### Risk vs. Reward Frontier (All Evaluated Draft Candidates)")
            df_all = report.all_results_df
            if not df_all.empty and "floor_p10" in df_all.columns and "mean_points" in df_all.columns:
                color_col = "win_probability_pct" if "win_probability_pct" in df_all.columns else ("win_prob_vs_ref" if "win_prob_vs_ref" in df_all.columns else "mean_points")
                try:
                    fig_scatter = px.scatter(
                        df_all,
                        x="floor_p10",
                        y="mean_points",
                        size="ceiling_p90" if "ceiling_p90" in df_all.columns else None,
                        color=color_col,
                        hover_name="objective" if "objective" in df_all.columns else None,
                        color_continuous_scale="Viridis",
                        labels={
                            "floor_p10": "Downside Safety Floor (P10 Points)",
                            "mean_points": "Simulated Expected Score E[V] (Points)",
                            "ceiling_p90": "Ceiling Upside (P90)",
                            color_col: "Win Prob vs Baseline (%)"
                        },
                        title="Draft Pareto Frontier: Top-Right = Optimal Expected Points & Resilience"
                    )
                    fig_scatter.update_layout(
                        paper_bgcolor="#0b0f19",
                        plot_bgcolor="#1e293b",
                        font={"color": "#f8fafc"},
                        xaxis={"gridcolor": "rgba(255,255,255,0.08)"},
                        yaxis={"gridcolor": "rgba(255,255,255,0.08)"},
                        height=450
                    )
                    st.plotly_chart(fig_scatter, use_container_width=True)
                except Exception as e:
                    st.caption(f"Scatter chart not available: {e}")

        # -------------------------------------------------------------
        # 7. Comparative Distribution Leaderboard
        # -------------------------------------------------------------
        st.markdown("---")
        st.subheader("📋 Comparative Draft Tournament Leaderboard (All Screened Squads)")
        st.markdown("Complete rank-ordered distribution metrics across all unique 15-man squad candidate configurations.")

        df_leaderboard = report.all_results_df.copy()
        if not df_leaderboard.empty:
            display_cols = [
                c for c in [
                    "rank", "objective", "cost", "bank_left", "mean_points",
                    "floor_p10", "median_p50", "ceiling_p90", "std_dev",
                    "sharpe", "win_probability_pct", "net_mean_gain"
                ] if c in df_leaderboard.columns
            ]
            st.dataframe(
                df_leaderboard[display_cols].rename(columns={
                    "rank": "Rank",
                    "objective": "Objective Vector",
                    "cost": "Cost (£m)",
                    "bank_left": "Bank Left (£m)",
                    "mean_points": "E[V] (pts)",
                    "floor_p10": "Floor P10",
                    "median_p50": "Median P50",
                    "ceiling_p90": "Ceiling P90",
                    "std_dev": "Std Dev (σ)",
                    "sharpe": "Sharpe",
                    "win_probability_pct": "Win Prob (%)",
                    "net_mean_gain": "Net Δ vs Baseline"
                }),
                use_container_width=True,
                hide_index=True
            )

        # -------------------------------------------------------------
        # 8. Interactive 15-Player Squad Pitch & Roster Inspector
        # -------------------------------------------------------------
        st.markdown("---")
        st.subheader("🔍 Interactive 15-Man Squad Pitch & Roster Inspector")
        st.markdown("Inspect full position compositions, FDR difficulty, set-piece roles, and starting lineup assignments for any drafted squad.")

        squad_options = [
            f"Option {idx + 1}: {c.candidate.objective_name.upper()} (E[V]: {c.mean_points:.1f} pts, £{c.candidate.total_cost:.1f}m)"
            for idx, c in enumerate(evaluated)
        ]
        selected_squad_label = st.selectbox(
            "Select Draft Candidate to Inspect:",
            options=squad_options,
            index=0,
            key="draft_inspect_squad_select"
        )
        selected_idx = squad_options.index(selected_squad_label)
        selected_eval = evaluated[selected_idx]
        selected_squad_names = selected_eval.candidate.squad_names

        # Compute optimal starting lineup vs bench
        mc_eng = mc_engine or MonteCarloEngine()
        lineup_eval = mc_eng.optimize_lineup_and_substitutions(
            squad_names=selected_squad_names,
            n_sims=500,
            df=df
        )
        starters = set(lineup_eval.get("starters", selected_squad_names[:11]))
        bench = [p for p in selected_squad_names if p not in starters]

        # Summary badge bar for selected squad
        st.markdown(f"""
        <div style="background: #1e293b; border-left: 4px solid #38bdf8; padding: 10px 16px; border-radius: 8px; margin-bottom: 16px;">
            <b style="color: #38bdf8; font-size: 15px;">Squad Composition Overview:</b>
            <span style="color: #cbd5e1; font-size: 13px; margin-left: 12px;">
                Formation: <b style="color: #ffffff;">{lineup_eval.get('formation', '3-4-3')}</b> |
                Starting XI xP: <b style="color: #facc15;">{lineup_eval.get('starting_11_mean', selected_eval.mean_points):.1f} pts</b> |
                Total Cost: <b style="color: #ffffff;">£{selected_eval.candidate.total_cost:.1f}m</b> |
                Remaining Bank: <b style="color: #34d399;">£{selected_eval.bank_remaining:.1f}m</b>
            </span>
        </div>
        """, unsafe_allow_html=True)

        # 4-Column Squad Display
        _render_squad_cards_4col(df, selected_squad_names, starters)

        # 1-Click Save as Sandbox Profile Draft
        st.markdown("---")
        st.markdown("##### 💾 Save this 15-Man Squad to a Sandbox Draft Profile")
        st.caption("Creates an independent Sandbox Draft profile in your manager switcher so you can track, tweak, and simulate this team anytime.")

        save_c1, save_c2 = st.columns([3, 1])
        with save_c1:
            draft_save_name = st.text_input(
                "Draft Profile Name",
                value=f"Draft: {selected_eval.candidate.objective_name.title()} ({selected_eval.mean_points:.1f} pts)",
                key="input_save_draft_profile_name"
            )
        with save_c2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("📥 Save as Profile Draft", key="btn_save_draft_as_profile", use_container_width=True):
                if draft_save_name.strip():
                    try:
                        p_mgr = ProfileManager()
                        new_pid = f"draft_{slugify_name(draft_save_name.strip())}"
                        new_profile = ManagerProfile(
                            profile_id=new_pid,
                            display_name=draft_save_name.strip(),
                            profile_type=ProfileType.SANDBOX,
                            fpl_entry_id=None,
                            bank_balance=round(float(selected_eval.bank_remaining), 1),
                            active_squad=list(selected_squad_names),
                            mini_league_ids=[],
                            calibration_profile="tuned",
                            notes=f"Drafted via Two-Stage Optimizer. E[V]={selected_eval.mean_points:.1f} pts, P10={selected_eval.floor_p10:.1f}, P90={selected_eval.ceiling_p90:.1f}.",
                            is_read_only=False,
                            is_default=False
                        )
                        p_mgr.save_profile(new_profile)
                        st.session_state["active_profile_id"] = new_pid
                        st.cache_data.clear()
                        st.success(f"✅ Created and switched to sandbox draft '{new_profile.display_name}'!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save draft profile: {e}")

    # Player Explorer Section at bottom
    _render_player_explorer_section(df)


def _render_squad_cards_4col(df: pd.DataFrame, squad_names: List[str], starters: set) -> None:
    """Render 4-column cards for GKP, DEF, MID, FWD with starting lineup indicators."""
    squad_df = df[df["web_name"].isin(squad_names)].copy() if "web_name" in df.columns else pd.DataFrame()
    if squad_df.empty:
        st.warning("Player details not found in current dataset.")
        return

    p_cols = st.columns(4)
    positions = [("GKP", "Goalkeepers"), ("DEF", "Defenders"), ("MID", "Midfielders"), ("FWD", "Forwards")]

    for idx, (pos, pos_label) in enumerate(positions):
        with p_cols[idx]:
            st.markdown(f"### {pos} ({pos_label})")
            sub = squad_df[squad_df["position_name"] == pos]
            if sub.empty:
                st.caption("No players")
                continue

            for _, r in sub.iterrows():
                p_name = r["web_name"]
                is_start = p_name in starters
                status_badge = (
                    '<span style="background: #15803d; color: #ffffff; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;">STARTING XI</span>'
                    if is_start
                    else '<span style="background: #475569; color: #cbd5e1; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;">BENCH</span>'
                )

                fdr_val = float(r.get("fdr_next_5", 3.0))
                fdr_cls = "badge-fdr-easy" if fdr_val <= 2.8 else ("badge-fdr-med" if fdr_val <= 3.2 else "badge-fdr-hard")
                sp_b = r.get("set_piece_badges", "None")
                sp_html = f'<br/><small style="color: #38bdf8;">🎯 {sp_b}</small>' if sp_b != "None" else ""

                border_color = "#38bdf8" if is_start else "#475569"

                render_html(f"""
                <div class="squad-player-card" style="background: #1e293b; border-left: 4px solid {border_color}; color: #ffffff; padding: 12px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.35);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <b style="color: #ffffff; font-size: 14px; font-weight: 700;">{p_name}</b>
                        {status_badge}
                    </div>
                    <span style="color: #94a3b8; font-size: 12px;">{r.get('club_name', '')}</span><br/>
                    <span style="color: #cbd5e1; font-size: 12px;">Price: <b style="color: #ffffff;">£{r.get('now_cost', 0.0):.1f}m</b> | Pts: <b style="color: #ffffff;">{int(r.get('total_points', 0))}</b> | Form: <b style="color: #ffffff;">{float(r.get('form', 0)):.1f}</b></span><br/>
                    <span style="color: #cbd5e1; font-size: 12px;">Next: <b style="color: #ffffff;">{r.get('next_fixture', 'N/A')}</b> | FDR: <span class="{fdr_cls}">{fdr_val:.2f}</span></span><br/>
                    <span style="color: #a78bfa; font-size: 12px; font-weight: 600;">Score: {float(r.get('setpiece_moneyball_score', r.get('fdr_moneyball_score', r.get('moneyball_score', 0)))):.2f}</span>{sp_html}
                </div>
                """)


def _render_quick_milp_result(res: Dict[str, Any], df: pd.DataFrame) -> None:
    """Render single-MILP draft solve result."""
    if not res.get("success"):
        st.error(res.get("message", "Optimization failed."))
        return

    st.success(f"Optimal Squad Found! Total Cost: £{res['total_cost']:.1f}m | Remaining Bank: £{res['bank_remaining']:.1f}m | Total Points: {res['total_points']}")
    squad = res["squad"]
    if isinstance(squad, pd.DataFrame) and "web_name" in squad.columns:
        starters = set(squad["web_name"].tolist()[:11])
        _render_squad_cards_4col(df, squad["web_name"].tolist(), starters)


def _render_player_explorer_section(df: pd.DataFrame) -> None:
    """Render preserved Player Explorer & Moneyball Table at bottom of page."""
    st.markdown("---")
    with st.expander("🔍 Player Explorer & Moneyball Ranking Database", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            pos_filter = st.multiselect("Position", ["GKP", "DEF", "MID", "FWD"], default=["FWD", "MID"], key="explorer_pos_filter")
        with c2:
            max_price = st.slider("Max Price (£m)", 4.0, 16.0, 15.5, 0.5, key="explorer_price_slider")
        with c3:
            filter_set_pieces = st.checkbox("Only Set-Piece & Penalty Specialists", value=False, key="explorer_sp_filter")

        sub_df = df[(df["position_name"].isin(pos_filter)) & (df["now_cost"] <= max_price) & (df["status"] == "a")].copy()
        if filter_set_pieces and "is_any_set_piece" in sub_df.columns:
            sub_df = sub_df[sub_df["is_any_set_piece"]]

        sort_col = "fdr_moneyball_efficiency" if "fdr_moneyball_efficiency" in sub_df.columns else "total_points"
        sub_df = sub_df.sort_values(by=sort_col, ascending=False)

        cols_to_display = [
            "web_name", "club_name", "position_name", "now_cost", "total_points",
            "form", "next_fixture", "fdr_next_5", "price_status", "set_piece_badges",
            "moneyball_score", "setpiece_moneyball_score"
        ]
        st.dataframe(sub_df[[c for c in cols_to_display if c in sub_df.columns]], use_container_width=True, hide_index=True)


def render_tab_explorer(df: pd.DataFrame) -> None:
    """Standalone wrapper for Player Explorer tab if invoked directly from app.py."""
    st.title("🔍 Player Explorer & Moneyball Table")
    _render_player_explorer_section(df)
