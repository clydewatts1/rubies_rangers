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
from clients.auth_manager import AuthManager
from clients.fpl_transfer_service import execute_two_stage_transfer


def render_tab_two_stage(df: pd.DataFrame, current_squad: List[str], bank: float = 3.7):
    """Render Two-Stage Screen & Simulate Tournament view with complete graphical suite."""
    auth_mgr = AuthManager()
    session_info = auth_mgr.get_active_session()
    is_authenticated = session_info.is_authenticated

    st.title("⚔️ Two-Stage Optimization Tournament (Screen & Simulate)")
    st.markdown(r"""
    **Moneyball Chained Architecture:**
    - **Stage 1: Multi-Objective MILP Screening (~40ms)** solves the global combinatorial knapsack across all 650+ Premier League players across 5 distinct objective weight vectors (`fdr_moneyball`, `forward_moneyball`, `xgi`, `setpiece_moneyball`, `form`) with canonical `frozenset` deduplication.
    - **Stage 2: Monte Carlo Stochastic Tournament** stress-tests each unique candidate squad across 1,000–10,000 parallel gameweek draws, modeling Gaussian minutes jitter, bench auto-substitutions, and full risk distributions ($P_{10}, P_{50}, P_{90}$).
    """)

    from config_manager import get_pareto_objectives, update_pareto_objectives
    current_objs = get_pareto_objectives()
    active_objs = [o for o in current_objs if o.get("enabled", True)]

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
            st.markdown(f"**Active Stage 1 Pareto Objectives ({len(active_objs)} Enabled):**")
            for o in active_objs[:6]:
                st.markdown(f"• **{o['label'].replace('_', ' ').title()}** (`{o['metric']}`)")
            if len(active_objs) > 6:
                st.caption(f"+ {len(active_objs) - 6} more enabled in config panel below")

    # -------------------------------------------------------------
    # Configurable Pareto Objectives Panel (Saved to config.yaml)
    # -------------------------------------------------------------
    with st.expander("🛠️ Configure Pareto-Efficient Objectives (Saved to config.yaml)", expanded=False):
        st.markdown("""
        Configure which objective dimensions Stage 1 MILP sweeps across. Enabling more objectives broadens the Pareto frontier; disabling narrows candidate focus.  
        Changes saved here are **persisted to `config.yaml`** and take effect immediately.
        """)
        st.markdown("##### ⚡ Quick Strategy Combination Presets")
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
                if st.button(p_name, key=f"preset_btn_{p_idx}", use_container_width=True):
                    for o in current_objs:
                        o["enabled"] = (o["label"] in p_keys)
                    update_pareto_objectives(current_objs)
                    st.rerun()

        st.markdown("---")
        st.markdown("##### ⚙️ Custom Pareto Objective Toggles")
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
                    key=f"pareto_chk_{obj['label']}"
                )
                updated_objs.append({
                    "label": obj["label"],
                    "metric": obj["metric"],
                    "enabled": chk,
                    "tier": obj.get("tier", "core"),
                    "description": obj.get("description", "")
                })

        if st.button("💾 Save Objectives to config.yaml", key="save_pareto_cfg_btn", type="secondary"):
            update_pareto_objectives(updated_objs)
            st.success("✅ Pareto objectives successfully updated and saved to `config.yaml`!")
            st.rerun()

    # -------------------------------------------------------------
    # Live Transfer Sensitivity & Differences Inspector
    # -------------------------------------------------------------
    with st.expander("🔍 Live Transfer Sensitivity: Compare Selections Across Objective Sets", expanded=False):
        st.markdown(f"""
        **Direct Side-by-Side Comparison:** Evaluates the optimal **{num_transfers} transfer{' (Single Swap)' if num_transfers == 1 else 's'}** across all 11 objective dimensions for your squad and available bank (£{bank_balance:.1f}m).  
        Notice how the recommended transfers shift based on tactical philosophy:
        - **Attacking / Low-Block**: Targets high-xGI shot volume and outside-the-box long-range threats.
        - **Defensive / Weather**: Targets sheltered stadiums, high wind resilience, and defensive baseline contributors.
        - **Mean Reversion / Value**: Targets under-rewarded breakout candidates (Big Chances Missed - BCM) and high points-per-million (PPM) enablers.
        """)
        sens_opt = FPLOptimizer(df)
        sens_rows = []
        for o in current_objs:
            label = o["label"]
            metric = o["metric"]
            tier = "🌟 Core" if o.get("tier") == "core" else "🎯 Contextual"
            res = sens_opt.optimize_transfers(
                current_squad,
                bank_balance=bank_balance,
                max_transfers=num_transfers,
                objective=metric,
                available_only=False
            )
            if res.get("success"):
                tin_df = res.get("transfers_in")
                tout_df = res.get("transfers_out")
                tin = ", ".join(tin_df["web_name"].tolist()) if isinstance(tin_df, pd.DataFrame) else "None"
                tout = ", ".join(tout_df["web_name"].tolist()) if isinstance(tout_df, pd.DataFrame) else "None"
                cost_in = tin_df["now_cost"].sum() if isinstance(tin_df, pd.DataFrame) else 0.0
                cost_out = tout_df["now_cost"].sum() if isinstance(tout_df, pd.DataFrame) else 0.0
                cost_diff = cost_in - cost_out
                sens_rows.append({
                    "Tier": tier,
                    "Objective": label.replace("_", " ").title(),
                    "Metric Key": metric,
                    "Transfer OUT": tout,
                    "Transfer IN": tin,
                    "Cost Δ": f"{cost_diff:+.1f}m",
                    "Bank Left": f"£{res.get('bank_remaining', 0):.1f}m",
                    "Status in Sweep": "✅ Active" if o.get("enabled", True) else "⬜ Disabled"
                })
        if sens_rows:
            st.dataframe(pd.DataFrame(sens_rows), use_container_width=True, hide_index=True)

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

            # Direct Online Transfer Execution Popover
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            plan_label = badge_title.split(":")[1].strip() if ":" in badge_title else badge_title
            with st.popover(f"⚡ Apply to FPL Team", use_container_width=True):
                st.markdown(f"#### ⚡ Apply {plan_label}")
                st.markdown(
                    f"**Proposed Operations:**\n"
                    f"- 🔻 **SELL OUT:** `{opt_eval.out_player}` (£{opt_eval.out_cost:.1f}m)\n"
                    f"- 🔺 **BUY IN:** `{opt_eval.in_player}` (£{opt_eval.in_cost:.1f}m)\n"
                    f"- 💰 **Bank Left:** `£{opt_eval.bank_remaining:.1f}m`"
                )

                if hit_pen > 0:
                    st.warning(f"⚠️ **Point Hit:** This move exceeds free transfers and incurs a **-{hit_pen} pts** deduction.")
                else:
                    st.success("✅ **Free Move:** Zero point deduction will be incurred.")

                opt_exec_mode = st.radio(
                    "Execution Mode:",
                    options=["Dry-Run (Safe Simulation)", "Live Submit (Official FPL API)"],
                    index=0,
                    key=f"two_stage_exec_mode_{badge_title}"
                )
                is_dry = (opt_exec_mode == "Dry-Run (Safe Simulation)")

                if not is_dry:
                    if is_authenticated:
                        st.info(f"🟢 Live target: **{session_info.first_name} {session_info.last_name}** (Entry {session_info.entry_id})")
                    else:
                        st.error("🚨 **No active authenticated session found!** Switch to Dry-Run or authenticate in Settings.")

                btn_confirm = st.button(
                    f"🚀 Confirm & Transmit {'(Dry-Run)' if is_dry else '(LIVE)'}",
                    type="primary" if not is_dry else "secondary",
                    disabled=(not is_dry and not is_authenticated),
                    key=f"two_stage_confirm_btn_{badge_title}",
                    use_container_width=True
                )

                if btn_confirm:
                    with st.spinner(f"Processing transfer {'(Simulation)' if is_dry else 'to official FPL'}..."):
                        t_out = opt_eval.candidate.transfers_out or [opt_eval.out_player]
                        t_in = opt_eval.candidate.transfers_in or [opt_eval.in_player]
                        res = execute_two_stage_transfer(
                            candidate_out=t_out,
                            candidate_in=t_in,
                            df=df,
                            dry_run=is_dry
                        )
                        if res.get("success"):
                            st.success(res.get("message"))
                            st.toast("Transfer request successfully processed!", icon="✅")
                            if not is_dry:
                                st.balloons()
                        else:
                            st.error(res.get("message"))

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
