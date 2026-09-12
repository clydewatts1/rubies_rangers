"""
Streamlit Tab: Two-Stage Tournament (Screen & Simulate)
Integrates Stage 1 (Multi-Objective MILP) with Stage 2 (Monte Carlo Tournament)
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
from ui.components import render_candidate_card


def render_tab_two_stage(df: pd.DataFrame, current_squad: List[str], bank: float = 3.7):
    """Render Two-Stage Screen & Simulate Tournament view."""
    st.title("⚔️ Two-Stage Optimization Tournament")
    st.markdown("""
    **Architecture**: **Stage 1 (MILP Pareto Generator)** solves the knapsack across 4 distinct objective functions (~40ms).  
    **Stage 2 (Monte Carlo Tournament)** stress-tests each candidate squad under 1,000+ stochastic draws with minutes jitter and bench auto-substitutions.
    """)

    col1, col2, col3 = st.columns(3)
    with col1:
        num_transfers = st.slider("Max Transfers", 1, 3, 1, key="two_stage_transfers")
    with col2:
        bank_balance = st.slider("Available Bank (£m)", 0.0, 15.0, float(bank), 0.1, key="two_stage_bank")
    with col3:
        sim_count = st.select_slider("Monte Carlo Simulations", options=[500, 1000, 2500, 5000], value=1000, key="two_stage_sims")

    risk_posture = st.radio(
        "Tournament Evaluation Posture",
        ["Balanced (Highest Expected Gain EV)", "Capital Preservation (Highest P10 Floor)", "Explosive Haul (Highest P90 Ceiling)"],
        horizontal=True
    )

    if st.button("🚀 Run Two-Stage Tournament", type="primary"):
        with st.spinner("Executing Stage 1 MILP Screening & Stage 2 Monte Carlo Tournament..."):
            opt = FPLOptimizer(df)
            mc = MonteCarloEngine()
            orchestrator = TwoStageOptimizer(opt, mc)

            report = orchestrator.run_screen_and_simulate(
                current_squad=current_squad,
                bank=bank_balance,
                num_transfers=num_transfers,
                n_sims=sim_count
            )

            st.success("Tournament Complete! All Pareto candidates evaluated.")

            # Baseline metrics
            st.markdown("### 📊 Baseline Squad Metrics (Current Team)")
            b_col1, b_col2, b_col3, b_col4 = st.columns(4)
            b_col1.metric("Baseline Mean EV", f"{report.baseline_mean:.1f} pts")
            b_col2.metric("P10 Floor", f"{report.baseline_p10:.1f} pts")
            b_col3.metric("P90 Ceiling", f"{report.baseline_p90:.1f} pts")
            b_col4.metric("Candidates Screened", f"{len(report.evaluated_candidates)}")

            st.markdown("---")
            st.markdown("### 🏆 Tournament Winner & Candidates")

            # Determine highlighted winner
            if "Highest P10" in risk_posture:
                winner = report.winner_safe_floor
                highlight_badge = "TOP SAFE FLOOR"
                badge_color = "blue"
            elif "Highest P90" in risk_posture:
                winner = report.winner_explosive_ceiling
                highlight_badge = "TOP EXPLOSIVE CEILING"
                badge_color = "purple"
            else:
                winner = report.winner_balanced
                highlight_badge = "OVERALL WINNER (BALANCED EV)"
                badge_color = "green"

            if winner:
                render_candidate_card(
                    candidate_title=f"🥇 Tournament Champion ({winner.candidate.objective_name.upper()})",
                    objective_label=winner.candidate.objective_name,
                    transfers_in=winner.candidate.transfers_in,
                    transfers_out=winner.candidate.transfers_out,
                    mean_pts=winner.mean_points,
                    p10_floor=winner.floor_p10,
                    p90_ceiling=winner.ceiling_p90,
                    win_prob_pct=winner.win_probability_pct,
                    net_gain=winner.net_gain_vs_current,
                    badge_label=highlight_badge,
                    badge_color=badge_color
                )

            st.markdown("#### All Evaluated Pareto Candidates")
            for i, cand_eval in enumerate(report.evaluated_candidates, 1):
                render_candidate_card(
                    candidate_title=f"Plan {i}: {cand_eval.candidate.objective_name.title()} Strategy",
                    objective_label=cand_eval.candidate.objective_name,
                    transfers_in=cand_eval.candidate.transfers_in,
                    transfers_out=cand_eval.candidate.transfers_out,
                    mean_pts=cand_eval.mean_points,
                    p10_floor=cand_eval.floor_p10,
                    p90_ceiling=cand_eval.ceiling_p90,
                    win_prob_pct=cand_eval.win_probability_pct,
                    net_gain=cand_eval.net_gain_vs_current,
                    badge_label=f"SCORE: {cand_eval.candidate.projected_score:.1f}",
                    badge_color="yellow"
                )
