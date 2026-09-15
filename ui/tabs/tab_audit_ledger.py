"""
Streamlit Tab: Suggestion & Outcome Audit Ledger & Model Calibration
Tracks pre-deadline solver recommendations, reconciles them against realized FPL matchday
ground truth, evaluates prediction residuals, and monitors closed-loop model calibration.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from trackers.decision_audit import DecisionAuditLedger, SuggestionSnapshot
from clients.fpl_client import FPLClient
from analytics.xp_model import XPModel


def render_tab_audit_ledger(df: pd.DataFrame, current_squad: list[str], active_profile_name: str = "Rubies Rangers"):
    st.title("📋 Suggestion & Outcome Audit Ledger")
    st.markdown(r"""
    **Quantitative Accountability & Closed-Loop Calibration:**
    In mathematical optimization, single-gameweek variance ($\sigma \approx 3.5$ pts/player) is normal match noise. 
    However, across $N \ge 4$ gameweeks, cumulative residuals $\sum (\text{Actual} - \mathbb{E}[xP])$ must converge toward zero.
    Persistent negative drift diagnoses **systematic modeling bias** (e.g. minutes inflation or over-optimistic clean sheets).
    """)

    client = FPLClient()
    ledger = DecisionAuditLedger(client=client)

    # Auto-seed initial historical GWs if completely empty so the user sees immediate value
    all_snaps = ledger.get_all_snapshots()
    if not all_snaps:
        with st.spinner("Initializing audit ledger with historical gameweek snapshots..."):
            ledger.seed_historical_gameweeks(up_to_gw=4)
            ledger.load()
            all_snaps = ledger.get_all_snapshots()

    metrics = ledger.compute_calibration_metrics()
    reconciled_snaps = ledger.get_reconciled_snapshots()

    # -------------------------------------------------------------
    # 1. Action Controls & Pre-Deadline Snapshot Bar
    # -------------------------------------------------------------
    with st.expander("⚡ Audit Ledger Actions & Snapshot Controls", expanded=False):
        c_act1, c_act2, c_act3 = st.columns([1.2, 1.2, 1.2])

        with c_act1:
            st.markdown("**📸 Pre-Deadline Snapshot**")
            current_gw = client.get_current_gameweek() or 5
            target_snap_gw = st.number_input("Target GW to Snapshot", min_value=1, max_value=38, value=current_gw, step=1, key="snap_gw_input")
            if st.button(f"Snapshot Recommendations for GW{target_snap_gw}", key="btn_snapshot_gw", use_container_width=True):
                try:
                    with st.spinner(f"Computing optimal recommendations for GW{target_snap_gw}..."):
                        xp_mod = XPModel()
                        lineup_res = xp_mod.optimize_lineup()
                        starters_list = lineup_res["starting_xi"].to_dict(orient="records")
                        bench_list = lineup_res["bench"].to_dict(orient="records")
                        cap_name = lineup_res["captain"]["web_name"]
                        vc_name = lineup_res["vice_captain"]["web_name"]
                        form_str = lineup_res["formation"]
                        base_xp = float(lineup_res["base_starting_xp"])
                        eff_xp = float(lineup_res["effective_total_xp"])

                        snap = ledger.snapshot_suggestion(
                            gw=int(target_snap_gw),
                            season="2024-25",
                            starters=starters_list,
                            bench=bench_list,
                            captain_name=cap_name,
                            vice_captain_name=vc_name,
                            formation=form_str,
                            projected_starting_xp=base_xp,
                            projected_effective_xp=eff_xp,
                            profile_name=active_profile_name,
                            applied_by_user=True
                        )
                        st.success(f"✅ Snapshotted GW{target_snap_gw} recommendations! (Projected Effective: {eff_xp:.1f} xP)")
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to snapshot recommendations: {e}")

        with c_act2:
            st.markdown("**🔄 Live Ground Truth Reconciliation**")
            st.caption("Pulls official match scores and auto-substitutions for completed GWs.")
            if st.button("Reconcile All Pending Gameweeks", key="btn_reconcile_all", use_container_width=True):
                with st.spinner("Reconciling gameweeks against official matchday ground truth..."):
                    count = 0
                    for s in ledger.get_all_snapshots():
                        if not s.is_reconciled:
                            rec = ledger.reconcile_gameweek(s.season, s.gw)
                            if rec and rec.is_reconciled:
                                count += 1
                    st.success(f"✅ Reconciled {count} gameweek(s) against live match ground truth!")
                    st.rerun()

        with c_act3:
            st.markdown("**🌱 Reset / Re-Seed Baseline Data**")
            st.caption("Re-evaluates Gameweeks 1-4 standard historical baselines.")
            if st.button("Re-Seed Historical Baselines", key="btn_reseed_baselines", use_container_width=True):
                with st.spinner("Re-seeding GW1-4 historical baselines..."):
                    ledger.seed_historical_gameweeks(up_to_gw=4)
                    st.success("✅ Baseline history re-seeded!")
                    st.rerun()

    # -------------------------------------------------------------
    # 2. Executive KPI Summary Cards
    # -------------------------------------------------------------
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

    status_color = "#10b981" if metrics.calibration_status == "WELL_CALIBRATED" else (
        "#f59e0b" if metrics.calibration_status == "OVER_PROJECTING" else "#06b6d4"
    )
    status_label = {
        "WELL_CALIBRATED": "🟢 Well-Calibrated",
        "OVER_PROJECTING": "🟠 Over-Projecting",
        "UNDER_PROJECTING": "🔵 Under-Projecting",
        "INSUFFICIENT_DATA": "⚪ Insufficient Data",
    }.get(metrics.calibration_status, "Unknown")

    kpi1.metric(
        label="Audited Gameweeks",
        value=f"{metrics.total_gws_audited} GWs",
        delta=f"{len(all_snaps)} Total Snapshots"
    )

    kpi2.markdown(
        f"""
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid {status_color}; border-radius: 8px; padding: 10px 14px; text-align: center;">
            <div style="color: #94a3b8; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Calibration Status</div>
            <div style="color: {status_color}; font-size: 16px; font-weight: 700; margin-top: 4px;">{status_label}</div>
            <div style="color: #cbd5e1; font-size: 11px; margin-top: 2px;">MBE: {metrics.mean_bias_error:+.1f} pts/GW</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    kpi3.metric(
        label="Cumulative Residual (CUSUM)",
        value=f"{metrics.cumulative_residual:+.1f} pts",
        delta=f"MAE: {metrics.mean_absolute_error:.1f} pts",
        delta_color="normal" if abs(metrics.cumulative_residual) <= 15 else "inverse"
    )

    kpi4.metric(
        label="Realized Transfer Alpha",
        value=f"{metrics.transfer_total_roi:+.1f} pts",
        delta="Net Gain vs Kept Players"
    )

    kpi5.metric(
        label="Captaincy Accuracy",
        value=f"{metrics.captaincy_accuracy_pct:.0f}%",
        delta="High-Scorer Efficiency"
    )

    # Diagnosis Banner
    if metrics.calibration_status == "WELL_CALIBRATED":
        st.success(f"🎯 **Model Calibration Health:** {metrics.calibration_diagnosis}")
    elif metrics.calibration_status == "OVER_PROJECTING":
        st.warning(f"⚠️ **Alpha Decay Alert:** {metrics.calibration_diagnosis}")
    elif metrics.calibration_status == "UNDER_PROJECTING":
        st.info(f"ℹ️ **Conservative Model Bias:** {metrics.calibration_diagnosis}")

    st.markdown("---")

    # -------------------------------------------------------------
    # 3. Interactive Analytics & Calibration Visualizations
    # -------------------------------------------------------------
    tab_cusum, tab_parity, tab_pos, tab_table = st.tabs([
        "📈 Cumulative Residual (CUSUM) Trend",
        "🎯 Prediction vs Actual Parity Plot",
        "🧱 Positional Bias Diagnostics",
        "📋 Reconciled Gameweek Ledger"
    ])

    # TAB 1: CUSUM Drift Curve
    with tab_cusum:
        st.subheader("Cumulative Residual Drift (CUSUM Control Chart)")
        st.markdown("""
        The **CUSUM chart** plots the running cumulative sum of prediction residuals:
        $$\\text{CUSUM}_T = \\sum_{t=1}^{T} (\\text{Actual}_t - \\mathbb{E}[xP_t])$$
        * **Flat horizontal trajectory around 0:** Model is perfectly calibrated.
        * **Consistent downward slope:** Systematic over-projection (alpha decay).
        * **Consistent upward slope:** Systematic under-projection.
        """)

        if reconciled_snaps:
            gw_labels = [f"GW{s.gw}" for s in reconciled_snaps]
            residuals = [s.prediction_residual for s in reconciled_snaps]
            cusum_vals = np.cumsum(residuals).tolist()
            actuals = [s.actual_effective_points for s in reconciled_snaps]
            projecteds = [s.projected_effective_xp for s in reconciled_snaps]

            fig_cusum = go.Figure()

            # Zero Baseline
            fig_cusum.add_hline(y=0, line_dash="dash", line_color="#94a3b8", annotation_text="Zero Bias Parity (E[e] = 0)")

            # CUSUM line
            fig_cusum.add_trace(go.Scatter(
                x=gw_labels,
                y=cusum_vals,
                mode="lines+markers",
                name="Cumulative Residual (CUSUM)",
                line=dict(color="#38bdf8", width=3),
                marker=dict(size=10, color="#0284c7")
            ))

            # Per-GW Residual Bars
            fig_cusum.add_trace(go.Bar(
                x=gw_labels,
                y=residuals,
                name="Per-GW Residual (Actual - xP)",
                marker_color=["#10b981" if r >= 0 else "#ef4444" for r in residuals],
                opacity=0.45
            ))

            fig_cusum.update_layout(
                title="CUSUM Model Residual Trajectory Across Completed Gameweeks",
                xaxis_title="Gameweek",
                yaxis_title="Points Delta",
                plot_bgcolor="rgba(15, 23, 42, 0.6)",
                paper_bgcolor="rgba(0, 0, 0, 0)",
                font=dict(color="#cbd5e1"),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_cusum, use_container_width=True)
        else:
            st.info("No reconciled gameweeks available yet to plot CUSUM chart.")

    # TAB 2: Parity & Calibration Scatter Plot
    with tab_parity:
        st.subheader("Expected Points vs. Ground Truth Actuals")
        st.markdown("""
        Compares **Projected Effective $xP$** against **Actual Points Scored** for each gameweek.
        Points lying along the **45° gold line** represent perfect predictions. Points above represent positive upside variance; points below represent underperformance.
        """)

        if reconciled_snaps:
            scatter_data = []
            for s in reconciled_snaps:
                scatter_data.append({
                    "Gameweek": f"GW{s.gw}",
                    "Projected_xP": s.projected_effective_xp,
                    "Actual_Points": s.actual_effective_points,
                    "Residual": s.prediction_residual,
                    "Captain": s.captain_name,
                    "Formation": s.formation
                })
            sdf = pd.DataFrame(scatter_data)

            min_val = min(sdf["Projected_xP"].min(), sdf["Actual_Points"].min()) - 5
            max_val = max(sdf["Projected_xP"].max(), sdf["Actual_Points"].max()) + 5

            fig_parity = go.Figure()

            # 45-degree parity reference line
            fig_parity.add_trace(go.Scatter(
                x=[min_val, max_val],
                y=[min_val, max_val],
                mode="lines",
                name="45° Perfect Parity Line",
                line=dict(color="#f59e0b", dash="dash", width=2)
            ))

            # Scatter points
            fig_parity.add_trace(go.Scatter(
                x=sdf["Projected_xP"],
                y=sdf["Actual_Points"],
                mode="markers+text",
                text=sdf["Gameweek"],
                textposition="top center",
                name="Audited Gameweek",
                marker=dict(
                    size=14,
                    color=sdf["Residual"],
                    colorscale="RdYlGn",
                    showscale=True,
                    colorbar=dict(title="Residual (Pts)")
                ),
                hovertemplate="<b>%{text}</b><br>Projected: %{x:.1f} xP<br>Actual: %{y:.1f} Pts<br>Residual: %{marker.color:+.1f}<extra></extra>"
            ))

            fig_parity.update_layout(
                title="Gameweek-by-Gameweek Projection Calibration",
                xaxis_title="Projected Effective xP",
                yaxis_title="Actual Effective Points Scored",
                xaxis=dict(range=[min_val, max_val]),
                yaxis=dict(range=[min_val, max_val]),
                plot_bgcolor="rgba(15, 23, 42, 0.6)",
                paper_bgcolor="rgba(0, 0, 0, 0)",
                font=dict(color="#cbd5e1")
            )
            st.plotly_chart(fig_parity, use_container_width=True)
        else:
            st.info("No reconciled gameweeks available for parity plot.")

    # TAB 3: Positional Bias Diagnostics
    with tab_pos:
        st.subheader("Positional Bias Decomposition")
        st.markdown("""
        Evaluates whether specific positional models suffer from systematic projection drift.
        * **Negative DEF Bias:** Clean sheet Poisson exponent is overestimating defensive stability.
        * **Negative FWD/MID Bias:** Minutes model or non-penalty $xG$ conversion is inflated.
        """)

        pos_bias = metrics.positional_bias
        pos_df = pd.DataFrame([
            {"Position": pos, "Mean Error (Pts/Player)": err}
            for pos, err in pos_bias.items()
        ])

        fig_pos = px.bar(
            pos_df,
            x="Position",
            y="Mean Error (Pts/Player)",
            color="Mean Error (Pts/Player)",
            color_continuous_scale="RdYlGn",
            title="Mean Prediction Error by Position across Audited Starting Lineups"
        )
        fig_pos.add_hline(y=0, line_dash="dash", line_color="#94a3b8")
        fig_pos.update_layout(
            plot_bgcolor="rgba(15, 23, 42, 0.6)",
            paper_bgcolor="rgba(0, 0, 0, 0)",
            font=dict(color="#cbd5e1")
        )
        st.plotly_chart(fig_pos, use_container_width=True)

        c_d1, c_d2 = st.columns(2)
        with c_d1:
            st.markdown("#### Positional Calibration Table")
            st.dataframe(pos_df, use_container_width=True, hide_index=True)
        with c_d2:
            st.markdown("#### Calibration Rules of Thumb")
            st.markdown("""
            * **$|\\text{Error}| \\le 0.5$ pts/player:** Excellent positional calibration.
            * **Error $< -0.8$ pts/player:** Investigate venue multipliers or expected minutes discount.
            * **Error $> +0.8$ pts/player:** Underestimating attacking talisman disruption.
            """)

    # TAB 4: Reconciled Gameweek Ledger Table & Deep-Dive
    with tab_table:
        st.subheader("Audited Gameweek History Ledger")

        if all_snaps:
            table_rows = []
            for s in all_snaps:
                sub_str = "None"
                if s.auto_subs:
                    sub_str = ", ".join([f"{out_p} ➔ {in_p}" for out_p, in_p in s.auto_subs])

                table_rows.append({
                    "GW": f"GW{s.gw}",
                    "Season": s.season,
                    "Status": "✅ Reconciled" if s.is_reconciled else "⏳ Pending Matchday",
                    "Formation": s.formation,
                    "Captain": f"{s.captain_name} ({s.actual_captain_points:.0f} pts)" if s.is_reconciled else s.captain_name,
                    "Projected xP": f"{s.projected_effective_xp:.1f}",
                    "Actual Points": f"{s.actual_effective_points:.1f}" if s.is_reconciled else "—",
                    "Residual Delta": f"{s.prediction_residual:+.1f}" if s.is_reconciled else "—",
                    "Auto-Subs": sub_str,
                    "Transfer Alpha": f"{s.transfer_net_alpha:+.1f}" if s.is_reconciled else "—",
                    "Cap Efficiency": f"{s.captaincy_efficiency:.0f}%" if s.is_reconciled else "—"
                })

            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

            # Deep-dive into specific gameweek
            st.markdown("---")
            st.subheader("🔍 Gameweek Deep-Dive Audit")
            gw_choices = [f"GW{s.gw}" for s in all_snaps]
            selected_gw_label = st.selectbox("Select Gameweek to Inspect:", gw_choices, index=len(gw_choices) - 1)
            selected_gw_num = int(selected_gw_label.replace("GW", ""))
            chosen_snap = next(s for s in all_snaps if s.gw == selected_gw_num)

            d_col1, d_col2 = st.columns(2)
            with d_col1:
                st.markdown(f"**Starting XI Ground Truth ({chosen_snap.formation})**")
                starters_df = pd.DataFrame(chosen_snap.starters)
                view_cols = ["web_name", "position_name", "club_short", "projected_xp", "actual_points", "actual_minutes"]
                renames = {
                    "web_name": "Player",
                    "position_name": "Pos",
                    "club_short": "Club",
                    "projected_xp": "Proj xP",
                    "actual_points": "Actual Pts",
                    "actual_minutes": "Mins"
                }
                disp_starters = [c for c in view_cols if c in starters_df.columns]
                st.dataframe(starters_df[disp_starters].rename(columns=renames), use_container_width=True, hide_index=True)

            with d_col2:
                st.markdown("**Substitutes & Auto-Sub Priority**")
                bench_df = pd.DataFrame(chosen_snap.bench)
                disp_bench = [c for c in view_cols if c in bench_df.columns]
                st.dataframe(bench_df[disp_bench].rename(columns=renames), use_container_width=True, hide_index=True)

                if chosen_snap.auto_subs:
                    st.warning(f"🔁 **Auto-Subs Triggered:** {', '.join([f'{out_p} (0 mins) ➔ {in_p}' for out_p, in_p in chosen_snap.auto_subs])}")
                else:
                    st.info("ℹ️ All starters featured; no bench auto-substitutions required.")
        else:
            st.info("No audit snapshots recorded yet.")
