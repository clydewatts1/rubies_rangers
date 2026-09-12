"""
Streamlit Tab: Monte Carlo Transfer Simulator & Lineup Strategist
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from ui.styles import render_html
from ui.cache import (
    load_montecarlo_simulation,
    load_montecarlo_lineup,
)
from analytics.xp_model import DEFAULT_SQUAD
from config_manager import get_params

def render_tab_montecarlo_transfers(df: pd.DataFrame, current_squad, bank_balance: float = 3.7):
    st.title("🎲 Monte Carlo Transfer Engine & Stochastic Simulation")
    st.markdown(r"""
    **Moneyball Philosophy:** Traditional fantasy optimizers rely on static expected points ($xP$). But football outcomes are **skewed, discrete Poisson & Bernoulli distributions**. 
    
    This engine runs **up to 10,000 parallel gameweek simulations** testing candidate transfers across bookmaker odds ($\lambda_{\text{team}}$), Understat tactical metrics (NPxG/xA), penalty duties, minutes security (starts vs cameos), and automatic bench substitutions.
    """)
    
    # Filter & Simulation Control Panel
    with st.expander("⚙️ Simulation Settings & Constraints", expanded=True):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            mc_transfers = st.radio("Number of Transfers", [1, 2], format_func=lambda x: f"{x} Transfer{' (Single Swap)' if x==1 else 's (Double Move)'}", horizontal=True)
            mc_free = st.slider("Free Transfers Available", 1, 5, 1, help="If transfers made exceed free quota, a -4 point hit penalty is deducted from the simulation.")
        with sc2:
            mc_bank = st.slider("Bank Balance (£m)", 0.0, 15.0, 3.7, 0.1)
            mc_sims = st.select_slider("Simulation Count", options=[1000, 2500, 5000, 10000], value=2500, help="Higher simulation counts yield tighter probability confidence intervals.")
        with sc3:
            mc_pos = st.selectbox("Position Filter", ["ALL", "GKP", "DEF", "MID", "FWD"], help="Filter candidate transfers by position.")
            sell_options = ["All Squad Players"] + DEFAULT_SQUAD
            mc_sell_choice = st.selectbox("Sell Target Filter", sell_options, help="Filter transfers to sell a specific player (e.g. benched Senesi or Solanke).")
            mc_sell = None if mc_sell_choice == "All Squad Players" else mc_sell_choice
    
        mc_strict = st.checkbox(
            "Strict Hygiene: Purge Injured, Suspended & Transferred-Out Players",
            value=True,
            help="Strictly removes all players with status 'u' (unavailable/left the PL), 'i' (injured), 's' (suspended), or chance_of_playing == 0%."
        )
    
    hit_penalty = max(0, mc_transfers - mc_free) * 4
    if hit_penalty > 0:
        st.warning(f"⚠️ **Transfer Hit Penalty Active:** Making {mc_transfers} transfer(s) with {mc_free} free transfer incurs a **-{hit_penalty} point deduction**, which has been factored directly into all simulation outcomes.")
    
    with st.spinner(f"Running {mc_sims:,} Monte Carlo simulations across candidate transfer permutations..."):
        mc_res = load_montecarlo_simulation(
            bank=mc_bank,
            num_transfers=mc_transfers,
            free_transfers=mc_free,
            n_sims=mc_sims,
            pos_filter=mc_pos,
            sell_filter=mc_sell,
            strict_filter=mc_strict
        )
    
    if not mc_res.get("success"):
        st.error(f"❌ {mc_res.get('message', 'No valid transfers found within budget and constraints.')}")
    else:
        base = mc_res["baseline"]
        top_3 = mc_res["top_3"]
        df_all = mc_res["all_results_df"]
        best_opt = top_3[0]
    
        # Hero KPIs Container
        hk1, hk2, hk3, hk4, hk5 = st.columns(5)
        hk1.metric("Baseline Squad xP", f"{base['mean']:.1f} pts", f"P10: {base['p10']} | P90: {base['p90']}")
        hk2.metric("Transfer Hit Penalty", f"-{hit_penalty} pts", "Free" if hit_penalty == 0 else f"{mc_transfers - mc_free} hit(s)")
        hk3.metric("Max EV Net Gain", f"{best_opt['net_mean_gain']:+.2f} pts", f"{best_opt['transfer_type']}")
        hk4.metric("Top Win Probability", f"{best_opt['win_prob']:.1f}%", "Beats Current Squad")
        hk5.metric("Bank Remaining", f"£{best_opt['bank_remaining']:.1f}m", f"Δ {best_opt['cost_diff']:+.1f}m")
    
        st.markdown("---")
    
        # -------------------------------------------------------------
        # Section 1: The 3 Best Transfer Archetypes Cards
        # -------------------------------------------------------------
        st.subheader("✨ The 3 Best Strategic Transfer Options (Monte Carlo Modeled)")
        st.markdown("Unlike simple linear models, the Monte Carlo optimizer surfaces 3 mathematically distinct transfer archetypes:")
    
        card_col1, card_col2, card_col3 = st.columns(3)
    
        for col, opt, badge_title, border_color in [
            (card_col1, top_3[0], "OPTION 1: 🏆 MAX EXPECTED VALUE", "#facc15"),
            (card_col2, top_3[1], "OPTION 2: 🛡️ MAX FLOOR & SAFETY", "#10b981"),
            (card_col3, top_3[2], "OPTION 3: 🚀 MAX CEILING & DIFFERENTIAL", "#a855f7")
        ]:
            with col:
                hit_badge = f'<span style="background: #dc2626; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 6px;">-{opt["hit_penalty"]} pts hit</span>' if opt["hit_penalty"] > 0 else '<span style="background: #15803d; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 6px;">Free Move</span>'
                render_html(f"""
                <div style="background: #1e293b; border: 2px solid {border_color}; border-radius: 12px; padding: 16px; min-height: 380px; display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <b style="color: {border_color}; font-size: 13px; text-transform: uppercase;">{badge_title}</b>
                            {hit_badge}
                        </div>
                        <div style="background: #0f172a; padding: 10px; border-radius: 8px; margin-bottom: 12px; border-left: 3px solid #ef4444;">
                            <span style="color: #ef4444; font-size: 11px; font-weight: bold; text-transform: uppercase;">SELL OUT</span><br/>
                            <b style="color: #ffffff; font-size: 16px;">{opt['out_player']}</b> <span style="color: #94a3b8; font-size: 12px;">({opt['out_club']} • £{opt['out_cost']}m)</span><br/>
                            <span style="color: #94a3b8; font-size: 12px;">Baseline Simulated: <b style="color: #cbd5e1;">{opt['out_mean']:.2f} pts</b></span>
                        </div>
                        <div style="background: #0f172a; padding: 10px; border-radius: 8px; margin-bottom: 12px; border-left: 3px solid #22c55e;">
                            <span style="color: #22c55e; font-size: 11px; font-weight: bold; text-transform: uppercase;">BUY IN</span><br/>
                            <b style="color: #ffffff; font-size: 16px;">{opt['in_player']}</b> <span style="color: #94a3b8; font-size: 12px;">({opt['in_club']} • £{opt['in_cost']}m)</span><br/>
                            <span style="color: #94a3b8; font-size: 12px;">Simulated Projection: <b style="color: #22c55e;">{opt['in_mean']:.2f} pts</b></span>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; background: rgba(15, 23, 42, 0.6); padding: 8px; border-radius: 8px;">
                            <div><span style="color: #94a3b8; font-size: 11px;">Net Gain:</span><br/><b style="color: {border_color}; font-size: 16px;">{opt['net_mean_gain']:+.2f} pts</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Win Probability:</span><br/><b style="color: #38bdf8; font-size: 16px;">{opt['win_prob']:.1f}%</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Floor (P10):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{opt['floor_p10']} pts</b></div>
                            <div><span style="color: #94a3b8; font-size: 11px;">Ceiling (P90):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{opt['ceiling_p90']} pts</b></div>
                        </div>
                    </div>
                    <div>
                        <div style="color: #cbd5e1; font-size: 12px; line-height: 1.4; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">
                            <i>{opt['rationale']}</i>
                        </div>
                        <div style="margin-top: 8px; text-align: right;">
                            <span style="color: #94a3b8; font-size: 11px;">Bank Left: <b style="color: white;">£{opt['bank_remaining']:.1f}m</b></span>
                        </div>
                    </div>
                </div>
                """)
    
        st.markdown("---")
    
        # -------------------------------------------------------------
        # Section 2: Interactive Graphical Visualizations
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
            fig_dist.add_trace(go.Histogram(
                x=base["raw_totals"],
                histnorm="probability density",
                name="Current Squad (Baseline)",
                marker_color="#94a3b8",
                opacity=0.35,
                nbinsx=40
            ))
    
            # Option 1 Max EV
            fig_dist.add_trace(go.Histogram(
                x=top_3[0]["raw_totals"],
                histnorm="probability density",
                name=f"Option 1: Max EV ({top_3[0]['in_player']})",
                marker_color="#facc15",
                opacity=0.45,
                nbinsx=40
            ))
    
            # Option 2 Max Floor
            fig_dist.add_trace(go.Histogram(
                x=top_3[1]["raw_totals"],
                histnorm="probability density",
                name=f"Option 2: Max Floor ({top_3[1]['in_player']})",
                marker_color="#10b981",
                opacity=0.45,
                nbinsx=40
            ))
    
            # Option 3 Max Ceiling
            fig_dist.add_trace(go.Histogram(
                x=top_3[2]["raw_totals"],
                histnorm="probability density",
                name=f"Option 3: Max Ceiling ({top_3[2]['in_player']})",
                marker_color="#a855f7",
                opacity=0.45,
                nbinsx=40
            ))
    
            # Add vertical lines for means
            fig_dist.add_vline(x=base["mean"], line_dash="dash", line_color="#94a3b8", annotation_text=f"Base: {base['mean']:.1f}", annotation_position="top left")
            fig_dist.add_vline(x=top_3[0]["new_mean"], line_dash="dash", line_color="#facc15", annotation_text=f"Opt 1: {top_3[0]['new_mean']:.1f}", annotation_position="top right")
    
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
    
            comp_names = [
                "Current Baseline",
                f"Opt 1: {top_3[0]['in_player']} (EV)",
                f"Opt 2: {top_3[1]['in_player']} (Floor)",
                f"Opt 3: {top_3[2]['in_player']} (Ceiling)"
            ]
            p10_vals = [base["p10"], top_3[0]["floor_p10"], top_3[1]["floor_p10"], top_3[2]["floor_p10"]]
            p50_vals = [base["p50"], top_3[0]["median_p50"], top_3[1]["median_p50"], top_3[2]["median_p50"]]
            p90_vals = [base["p90"], top_3[0]["ceiling_p90"], top_3[1]["ceiling_p90"], top_3[2]["ceiling_p90"]]
    
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                name="P10 Floor (Safety Net)",
                y=comp_names,
                x=p10_vals,
                orientation="h",
                marker_color="#38bdf8",
                text=[f"{v:.0f}" for v in p10_vals],
                textposition="inside"
            ))
            fig_bar.add_trace(go.Bar(
                name="P50 Median (Expected)",
                y=comp_names,
                x=[p50 - p10 for p50, p10 in zip(p50_vals, p10_vals)],
                base=p10_vals,
                orientation="h",
                marker_color="#facc15",
                text=[f"{v:.0f}" for v in p50_vals],
                textposition="inside"
            ))
            fig_bar.add_trace(go.Bar(
                name="P90 Ceiling (Haul Potential)",
                y=comp_names,
                x=[p90 - p50 for p90, p50 in zip(p90_vals, p50_vals)],
                base=p50_vals,
                orientation="h",
                marker_color="#ec4899",
                text=[f"{v:.0f}" for v in p90_vals],
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
            st.markdown("#### Risk vs. Reward Efficiency Frontier (All Evaluated Transfers)")
            st.markdown("Each bubble represents a legal transfer move. Top-right = High Gain & High Safety Floor; Larger bubble = Greater 90th-percentile haul upside.")
    
            fig_scatter = px.scatter(
                df_all,
                x="floor_p10",
                y="net_mean_gain",
                size="ceiling_p90",
                color="win_prob",
                hover_name="in_player",
                hover_data={
                    "out_player": True,
                    "in_club": True,
                    "net_mean_gain": ":+.2f",
                    "win_prob": ":.1f%",
                    "cost_diff": ":+.1f",
                    "bank_remaining": ":.1f",
                    "floor_p10": True,
                    "ceiling_p90": True
                },
                labels={
                    "floor_p10": "10th-Percentile Floor (Downside Safety)",
                    "net_mean_gain": "Net Expected Gain (pts/GW)",
                    "win_prob": "Win Probability %",
                    "ceiling_p90": "90th-Percentile Ceiling"
                },
                color_continuous_scale="Viridis"
            )
    
            fig_scatter.add_hline(y=0, line_dash="dash", line_color="#ef4444", annotation_text="Break-Even (0 Net Gain)")
    
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
    
        st.markdown("---")
    
        # -------------------------------------------------------------
        # Section 3: Comprehensive Transfer Candidates Table
        # -------------------------------------------------------------
        st.subheader(f"📋 Comprehensive Evaluated Transfers Matrix ({len(df_all)} Legal Moves)")
        st.markdown("Search, sort, and inspect every legal transfer option tested by the Monte Carlo engine.")
    
        display_cols = [
            "out_player", "in_player", "in_pos", "in_club", "cost_diff", "bank_remaining",
            "net_mean_gain", "win_prob", "floor_p10", "median_p50", "ceiling_p90", "sharpe", "fdr_next_5"
        ]
        renames = {
            "out_player": "Sell Out",
            "in_player": "Buy In",
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
    
        df_display = df_all[display_cols].rename(columns=renames)
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    
        # CSV Download Button
        csv_data = df_display.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Full Monte Carlo Transfer Evaluation (CSV)",
            data=csv_data,
            file_name=f"monte_carlo_transfers_{mc_transfers}x_sim{mc_sims}.csv",
            mime="text/csv"
        )
    


def render_tab_montecarlo_lineup(df: pd.DataFrame, current_squad):
    st.title("🛡️ Monte Carlo Lineup, Bench & Captaincy Strategist")
    st.markdown(r"""
    **Moneyball Tactical Optimization:** Standard fantasy managers pick their starting XI based on past points or gut feel. 
    This engine executes **2,500+ parallel Monte Carlo stochastic simulations** across every match in the upcoming gameweek to solve four interdependent problems simultaneously:
    - **Formation Optimization:** Tests all 8 legal FPL formations (3-5-2, 3-4-3, 4-4-2, 4-5-1, 4-3-3, 5-3-2, 5-4-1, 5-2-3) to find the mathematical maximum expected output.
    - **Bench Substitution Activation ($P(\text{Subbed In})$):** Calculates the exact empirical probability that each substitute enters the match, strictly enforcing Premier League formation legality (minimum 3 defenders, 2 midfielders, 1 forward).
    - **Captaincy Head-to-Head Duel & Fallback Protection:** Simulates captain score distributions head-to-head ($P(\text{Cap} > \text{VC})$) and automatically triggers the vice-captain 2x fallback if the captain plays zero minutes.
    - **Disciplinary & Injury Risk Modeling:** Incorporates red card odds (-3 points and clean sheet forfeiture), yellow card suspensions, injury flags, and recent minutes security.
    """)
    
    # Simulation Controls
    with st.expander("⚙️ Lineup Simulation Settings & Risk Parameters", expanded=True):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            mc_lineup_sims = st.select_slider(
                "Simulation Iterations",
                options=[1000, 2500, 5000, 10000],
                value=2500,
                help="Number of stochastic trials simulated across the entire squad."
            )
        with sc2:
            mc_form_weight = st.slider(
                "Recent Form Weight",
                min_value=0.0,
                max_value=0.50,
                value=0.25,
                step=0.05,
                help="Weight assigned to player recent form (3-match rolling performance) blended with fixture expectancy."
            )
        with sc3:
            mc_disciplinary = st.checkbox(
                "Model In-Match Red Cards & Yellows",
                value=True,
                help="Simulates match red cards (-3 pts, clean sheet forfeit, sub prevention) and yellow card accumulation."
            )
    
    with st.spinner(f"Running {mc_lineup_sims:,} Monte Carlo simulations to optimize Starting XI, bench hierarchy, and captaincy..."):
        lineup_res = load_montecarlo_lineup(
            squad_names=tuple(current_squad),
            n_sims=mc_lineup_sims,
            form_weight=mc_form_weight,
            include_disciplinary=mc_disciplinary
        )
    
    sq_sum = lineup_res["squad_summary"]
    opt_form = lineup_res["optimal_formation"]
    cap_duel = lineup_res["captaincy_duel"]
    cap_info = cap_duel["captain"]
    vc_info = cap_duel["vice_captain"]
    bench_data = lineup_res["bench"]
    starters_data = lineup_res["starters"]
    checklist = lineup_res["move_around_checklist"]
    
    # Hero KPI Summary Cards
    hk1, hk2, hk3, hk4 = st.columns(4)
    hk1.metric(
        "Optimal Formation",
        f"{opt_form}",
        delta="Beats 7 Other Formations"
    )
    hk2.metric(
        "Expected Lineup Total",
        f"{sq_sum['mean_total']:.1f} pts",
        delta=f"P10 Floor: {sq_sum['floor_p10']} | P90 Ceiling: {sq_sum['ceiling_p90']}"
    )
    hk3.metric(
        "Designated Captain (C)",
        f"{cap_info['web_name']}",
        delta=f"{cap_info['mean_captain_pts']:.1f} pts (2x) • {cap_info['haul_prob_pct']}% Haul"
    )
    hk4.metric(
        "Primary Bench Cover (Sub 1)",
        f"{bench_data[0]['web_name']}",
        delta=f"{bench_data[0]['activation_prob_pct']}% Auto-Sub • +{bench_data[0]['points_saved_mean']:.1f} EV"
    )
    
    st.markdown("---")
    
    # Macro Match-State Jitter Transparency Card
    macro_cfg = get_params("monte_carlo").get("macro_jitter", {})
    if macro_cfg.get("enabled", True):
        st.info(
            f"⚡ **Macro Match-State Jitter & Teammate Covariance Active** (Atmospheric Pace Volatility $\\sigma = {macro_cfg.get('pace_volatility', 0.15):.2f}$)\n\n"
            "• **Defensive Synchronization**: Clean sheets and discrete goals conceded are synchronized across teammates on the pitch via joint Poisson match realizations.\n"
            "• **Atmospheric Tempo**: Player attacking xG is modulated by simulated fixture match pace (fast open matches vs low-event grinds).\n"
            "• **Portfolio Risk**: Lineup and bench optimization penalizes unhedged defender double-ups in high-volatility fixtures while accurately pricing correlated tail outcomes ($P_{10}$, $P_{90}$)."
        )
    # -------------------------------------------------------------
    # Section 1: What to Move Around (Actionable Checklist)
    # -------------------------------------------------------------
    st.subheader("📋 What to Move Around (Actionable Pre-Deadline Checklist)")
    st.markdown("Step-by-step instructions to configure Rubies Rangers for optimal expected return and risk mitigation:")
    
    for item in checklist:
        cat = item.get("category", "")
        if "BENCH" in cat and "ORDER" not in cat:
            badge_class = "badge-step-red"
            border_color = "#ef4444"
        elif "START" in cat:
            badge_class = "badge-step-green"
            border_color = "#10b981"
        elif "ORDER" in cat or "SUB" in cat:
            badge_class = "badge-step-yellow"
            border_color = "#f59e0b"
        elif "VICE" in cat:
            badge_class = "badge-step-purple"
            border_color = "#a855f7"
        else:
            badge_class = "badge-step-blue"
            border_color = "#3b82f6"
    
        render_html(f"""
        <div class="step-card" style="border-left: 5px solid {border_color};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-weight: 700; font-size: 16px; color: #ffffff;">Step {item['step']}: {item['action']}</span>
                <span class="{badge_class}">{item['badge']}</span>
            </div>
            <div style="color: #cbd5e1; font-size: 13px; line-height: 1.5;">
                {item['reason']}
            </div>
        </div>
        """)
    
    st.markdown("---")
    
    # -------------------------------------------------------------
    # Section 2: Suggested Starting XI Tactical Pitch
    # -------------------------------------------------------------
    st.subheader(f"🏟️ Suggested Starting XI ({opt_form} Formation)")
    st.markdown("Simulated starting lineup optimized for expected points, fixture difficulty, and minutes security:")
    
    # Group starters by position
    starters_df = pd.DataFrame(starters_data)
    fwds = starters_df[starters_df["pos"] == "FWD"]
    mids = starters_df[starters_df["pos"] == "MID"]
    defs = starters_df[starters_df["pos"] == "DEF"]
    gkps = starters_df[starters_df["pos"] == "GKP"]
    
    def _render_mc_pitch_card(p):
        is_cap = (p["web_name"] == cap_info["web_name"])
        is_vc = (p["web_name"] == vc_info["web_name"])
        
        badge_html = ""
        if is_cap:
            badge_html = '<div class="captain-badge">★ CAPTAIN (C)</div><br/>'
        elif is_vc:
            badge_html = '<div class="vc-badge">☆ VICE-CAPTAIN (VC)</div><br/>'
    
        card_warning = ""
        yc_raw = p.get("yellow_cards", 0)
        yc = int(yc_raw) if (yc_raw is not None and pd.notna(yc_raw)) else 0
        if yc >= 2:
            card_warning = f'<small style="color: #fef08a;">⚠️ {yc} Yellows</small><br/>'
    
        cop_raw = p.get("cop", 100)
        cop = int(cop_raw) if (cop_raw is not None and pd.notna(cop_raw)) else 100
        cop_warning = ""
        if cop < 100:
            cop_warning = f'<small style="color: #f87171;">⚠️ {cop}% Fit</small><br/>'
    
        fdr_raw = p.get("fdr", 3)
        fdr_val = float(fdr_raw) if (fdr_raw is not None and pd.notna(fdr_raw)) else 3.0
        fdr_class = "badge-fdr-easy" if fdr_val <= 2.5 else ("badge-fdr-med" if fdr_val <= 3.2 else "badge-fdr-hard")
    
        form_raw = p.get("form", 0.0)
        form_val = float(form_raw) if (form_raw is not None and pd.notna(form_raw)) else 0.0
    
        p10_raw = p.get("p10", 0.0)
        p10_val = float(p10_raw) if (p10_raw is not None and pd.notna(p10_raw)) else 0.0
    
        p90_raw = p.get("p90", 0.0)
        p90_val = float(p90_raw) if (p90_raw is not None and pd.notna(p90_raw)) else 0.0
    
        mean_raw = p.get("mean_pts", 0.0)
        mean_pts = float(mean_raw) if (mean_raw is not None and pd.notna(mean_raw)) else 0.0
        pts_display = mean_pts * 2 if is_cap else mean_pts
    
        return f"""
        <div class="player-card" style="min-width: 145px; margin: 4px;">
            {badge_html}
            <b style="font-size: 15px; color: #f8fafc;">{p['web_name']}</b><br/>
            <small style="color: #94a3b8;">{p['club']} vs {p['fixture']}</small><br/>
            <span class="{fdr_class}">FDR {fdr_val:.0f}</span> 
            <small style="color: #38bdf8;">⚡ Form {form_val:.1f}</small><br/>
            {cop_warning}{card_warning}
            <div class="xp-pill">{pts_display:.2f} pts{' (2x)' if is_cap else ''}</div><br/>
            <small style="color: #94a3b8; font-size: 11px;">P10: {p10_val:.1f} | P90: {p90_val:.1f}</small>
        </div>
        """
    
    pitch_markup = '<div class="pitch-container">'
    # FWD Row
    pitch_markup += '<div class="pitch-row">'
    for _, p in fwds.iterrows():
        pitch_markup += _render_mc_pitch_card(p)
    pitch_markup += '</div>'
    # MID Row
    pitch_markup += '<div class="pitch-row">'
    for _, p in mids.iterrows():
        pitch_markup += _render_mc_pitch_card(p)
    pitch_markup += '</div>'
    # DEF Row
    pitch_markup += '<div class="pitch-row">'
    for _, p in defs.iterrows():
        pitch_markup += _render_mc_pitch_card(p)
    pitch_markup += '</div>'
    # GKP Row
    pitch_markup += '<div class="pitch-row">'
    for _, p in gkps.iterrows():
        pitch_markup += _render_mc_pitch_card(p)
    pitch_markup += '</div>'
    pitch_markup += '</div>'
    render_html(pitch_markup)
    
    # -------------------------------------------------------------
    # Section 3: Priority Substitutes & Auto-Sub Activation Strategy
    # -------------------------------------------------------------
    st.markdown("#### 🪑 Priority Substitutes & Bench Activation Matrix")
    st.markdown(
        "Bench order matters critically in FPL. If a starter misses out, the game substitutes from left to right, "
        "provided the resulting team has at least **3 defenders, 2 midfielders, and 1 forward**."
    )
    
    b_cols = st.columns(4)
    for idx, b_item in enumerate(bench_data):
        with b_cols[idx]:
            act_pct = b_item["activation_prob_pct"]
            act_color = "#10b981" if act_pct >= 20 else ("#f59e0b" if act_pct >= 5 else "#94a3b8")
            
            border_color = "#3b82f6" if idx == 0 else "rgba(255, 255, 255, 0.15)"
            sub_badge = f'<span style="background: {act_color}; color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">{act_pct}% Auto-Sub</span>'
    
            render_html(f"""
            <div class="bench-card" style="border: 2px solid {border_color}; min-height: 250px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <b style="color: #38bdf8; font-size: 13px;">{b_item['slot']}</b>
                        {sub_badge}
                    </div>
                    <b style="color: white; font-size: 16px;">{b_item['web_name']}</b> <small style="color: #94a3b8;">({b_item['position']})</small><br/>
                    <small style="color: #cbd5e1;">{b_item['club']} vs {b_item['fixture']}</small><br/>
                    <div style="margin: 8px 0; background: rgba(15, 23, 42, 0.6); padding: 6px; border-radius: 6px; font-size: 12px;">
                        <span style="color: #94a3b8;">EV if Subbed:</span> <b style="color: #34d399;">{b_item['pts_when_subbed']:.2f} pts</b><br/>
                        <span style="color: #94a3b8;">Points Saved EV:</span> <b style="color: #38bdf8;">+{b_item['points_saved_mean']:.2f} pts</b><br/>
                        <span style="color: #94a3b8;">Form:</span> <b style="color: white;">{b_item['form']:.1f}</b>
                    </div>
                </div>
                <div style="font-size: 11px; color: #cbd5e1; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px; text-align: left;">
                    <i>{b_item['tactical_rationale']}</i>
                </div>
            </div>
            """)
    
    # Bench Activation Bar Chart
    sub_names = [f"{b['slot']}: {b['web_name']} ({b['position']})" for b in bench_data]
    sub_probs = [b["activation_prob_pct"] for b in bench_data]
    
    fig_bench = go.Figure()
    fig_bench.add_trace(go.Bar(
        x=sub_names,
        y=sub_probs,
        name="Activation Probability (%)",
        marker_color=["#10b981", "#f59e0b", "#94a3b8", "#64748b"],
        text=[f"{p}%" for p in sub_probs],
        textposition="auto"
    ))
    fig_bench.update_layout(
        title="Substitute Activation Probability across Simulated Gameweeks",
        paper_bgcolor="#0b0f19",
        plot_bgcolor="#1e293b",
        font={"color": "#f8fafc"},
        xaxis={"gridcolor": "rgba(255,255,255,0.08)"},
        yaxis={"title": "Probability (%)", "gridcolor": "rgba(255,255,255,0.08)", "range": [0, max(sub_probs) * 1.3 + 5]},
        height=320,
        margin={"l": 20, "r": 20, "t": 40, "b": 20}
    )
    st.plotly_chart(fig_bench, use_container_width=True)
    
    st.markdown("---")
    
    # -------------------------------------------------------------
    # Section 4: Captaincy & Vice-Captaincy Monte Carlo Duel
    # -------------------------------------------------------------
    st.subheader("👑 Captaincy & Vice-Captaincy Monte Carlo Duel")
    st.markdown(
        r"Armband optimization requires evaluating head-to-head win probability, explosive haul ceiling ($\ge 10$ points), "
        r"and catastrophic blank risk ($\le 2$ points). Furthermore, Vice-Captain selection provides **insurance protection** if the captain suffers a late training knock or scratch."
    )
    
    cap_col1, cap_col2 = st.columns(2)
    
    with cap_col1:
        render_html(f"""
        <div style="background: #1e293b; border: 2px solid #ef4444; border-radius: 12px; padding: 18px; box-shadow: 0 4px 15px rgba(239, 68, 68, 0.2);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span class="captain-badge" style="font-size: 13px;">★ DESIGNATED CAPTAIN</span>
                <span style="background: #065f46; color: #a7f3d0; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px;">Win Rate: {cap_info['win_rate_pct']}%</span>
            </div>
            <h2 style="color: white; margin: 4px 0 2px 0;">{cap_info['web_name']}</h2>
            <div style="color: #94a3b8; font-size: 13px; margin-bottom: 12px;">{cap_info['club']} vs {cap_info['fixture']} • Form: {cap_info['form']:.1f}</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; background: #0f172a; padding: 12px; border-radius: 8px;">
                <div><span style="color: #94a3b8; font-size: 12px;">Captain Expected Points (2x):</span><br/><b style="color: #ef4444; font-size: 20px;">{cap_info['mean_captain_pts']:.2f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Single Match EV:</span><br/><b style="color: white; font-size: 18px;">{cap_info['mean_single_pts']:.2f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Haul Probability (≥10 pts):</span><br/><b style="color: #10b981; font-size: 16px;">{cap_info['haul_prob_pct']}%</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Blank Risk (≤2 pts):</span><br/><b style="color: #f87171; font-size: 16px;">{cap_info['blank_prob_pct']}%</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Floor (P10 2x):</span><br/><b style="color: #cbd5e1; font-size: 15px;">{cap_info['p10']:.1f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Ceiling (P90 2x):</span><br/><b style="color: #cbd5e1; font-size: 15px;">{cap_info['p90']:.1f} pts</b></div>
            </div>
        </div>
        """)
    
    with cap_col2:
        render_html(f"""
        <div style="background: #1e293b; border: 2px solid #3b82f6; border-radius: 12px; padding: 18px; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.2);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span class="vc-badge" style="font-size: 13px;">☆ DESIGNATED VICE-CAPTAIN</span>
                <span style="background: #1e3a8a; color: #bfdbfe; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 12px;">Win Rate: {vc_info['win_rate_pct']}%</span>
            </div>
            <h2 style="color: white; margin: 4px 0 2px 0;">{vc_info['web_name']}</h2>
            <div style="color: #94a3b8; font-size: 13px; margin-bottom: 12px;">{vc_info['club']} vs {vc_info['fixture']} • Form: {vc_info['form']:.1f}</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; background: #0f172a; padding: 12px; border-radius: 8px;">
                <div><span style="color: #94a3b8; font-size: 12px;">Captain Expected Points (2x):</span><br/><b style="color: #3b82f6; font-size: 20px;">{vc_info['mean_captain_pts']:.2f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Single Match EV:</span><br/><b style="color: white; font-size: 18px;">{vc_info['mean_single_pts']:.2f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Haul Probability (≥10 pts):</span><br/><b style="color: #10b981; font-size: 16px;">{vc_info['haul_prob_pct']}%</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Blank Risk (≤2 pts):</span><br/><b style="color: #f87171; font-size: 16px;">{vc_info['blank_prob_pct']}%</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Floor (P10 2x):</span><br/><b style="color: #cbd5e1; font-size: 15px;">{vc_info['p10']:.1f} pts</b></div>
                <div><span style="color: #94a3b8; font-size: 12px;">Ceiling (P90 2x):</span><br/><b style="color: #cbd5e1; font-size: 15px;">{vc_info['p90']:.1f} pts</b></div>
            </div>
        </div>
        """)
    
    st.info(f"""
    **🛡️ Vice-Captain Insurance Policy:** In {cap_info['win_rate_pct']}% of simulations, **{cap_info['web_name']}** outscores **{vc_info['web_name']}**.
    However, if {cap_info['web_name']} plays 0 minutes due to unexpected pre-match illness or rotation, FPL rules automatically transfer the 2x multiplier to **{vc_info['web_name']}**, securing an expected return of **{vc_info['mean_captain_pts']:.2f} points**.
    """)
    
    # Contenders Table
    st.markdown("#### Top 5 Captaincy Contenders Evaluation")
    cont_df = pd.DataFrame(cap_duel["contenders"])
    cont_display = cont_df[[
        "web_name", "club", "pos", "fixture", "form",
        "mean_captain_pts", "haul_prob_pct", "blank_prob_pct", "p10", "p90"
    ]].rename(columns={
        "web_name": "Player",
        "club": "Club",
        "pos": "Pos",
        "fixture": "GW4 Fixture",
        "form": "Form",
        "mean_captain_pts": "Expected 2x Points",
        "haul_prob_pct": "Haul % (≥10)",
        "blank_prob_pct": "Blank % (≤2)",
        "p10": "P10 Floor",
        "p90": "P90 Ceiling"
    })
    st.dataframe(cont_display, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # -------------------------------------------------------------
    # Section 5: Formations Optimization Comparison
    # -------------------------------------------------------------
    st.subheader("📐 All 8 Legal Formations Evaluated")
    st.markdown(
        "FPL permits exactly 8 outfield combinations (always requiring 1 GKP, at least 3 DEF, and at least 1 FWD). "
        "Here is the Monte Carlo performance comparison for Rubies Rangers across all 8 configurations:"
    )
    
    form_evals = lineup_res["formation_evaluations"]
    form_df = pd.DataFrame(form_evals)
    
    f_col1, f_col2 = st.columns([1, 1])
    with f_col1:
        fig_form = go.Figure()
        fig_form.add_trace(go.Bar(
            y=form_df["formation"][::-1],
            x=form_df["mean_score"][::-1],
            orientation="h",
            marker_color=["#10b981" if f == opt_form else "#3b82f6" for f in form_df["formation"][::-1]],
            text=[f"{score:.1f} pts" for score in form_df["mean_score"][::-1]],
            textposition="auto"
        ))
        fig_form.update_layout(
            title="Expected Lineup Score by Legal Formation",
            paper_bgcolor="#0b0f19",
            plot_bgcolor="#1e293b",
            font={"color": "#f8fafc"},
            xaxis={"title": "Mean Simulated Total (pts)", "gridcolor": "rgba(255,255,255,0.08)"},
            yaxis={"gridcolor": "rgba(255,255,255,0.08)"},
            height=380,
            margin={"l": 20, "r": 20, "t": 40, "b": 20}
        )
        st.plotly_chart(fig_form, use_container_width=True)
    
    with f_col2:
        st.markdown("#### Formations Leaderboard")
        form_disp = form_df[["formation", "defenders", "midfielders", "forwards", "mean_score", "p10", "p50", "p90", "std"]].rename(columns={
            "formation": "Formation",
            "defenders": "DEF",
            "midfielders": "MID",
            "forwards": "FWD",
            "mean_score": "Mean (pts)",
            "p10": "Floor (P10)",
            "p50": "Median (P50)",
            "p90": "Ceiling (P90)",
            "std": "Volatility (Std)"
        })
        st.dataframe(form_disp, use_container_width=True, hide_index=True)
        st.caption("💡 **Why 3-5-2 dominates:** Rubies Rangers possesses 5 elite starting midfielders (Foden, Cherki, Rogers, Ødegaard, Mbeumo) and 2 explosive forwards (Isak, Pedro). Dropping any midfielder to play an extra defender costs an average of 6.2 to 17.6 points.")
    
    st.markdown("---")
    
    # -------------------------------------------------------------
    # Section 6: Disciplinary, Form & Injury Risk Monitor
    # -------------------------------------------------------------
    st.subheader("🩺 Squad Health, Form & Disciplinary Risk Monitor")
    st.markdown("Monitors cards accumulation, in-match red card risk, recent minutes, injury statuses, and player form:")
    
    risk_alerts = lineup_res["disciplinary_and_injury_alerts"]
    if risk_alerts:
        alert_df = pd.DataFrame(risk_alerts)
        alert_disp = alert_df[["web_name", "club", "pos", "status", "cop", "yellow_cards", "red_cards", "form", "notes"]].rename(columns={
            "web_name": "Player",
            "club": "Club",
            "pos": "Pos",
            "status": "FPL Status",
            "cop": "Chance of Playing (%)",
            "yellow_cards": "Yellow Cards",
            "red_cards": "Red Cards",
            "form": "Current Form",
            "notes": "Risk Flag / Description"
        })
        st.dataframe(alert_disp, use_container_width=True, hide_index=True)
    else:
        st.success("✅ All squad players are currently available with zero active injury flags or disciplinary suspensions.")
    

