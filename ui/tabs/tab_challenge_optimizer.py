"""
ui/tabs/tab_challenge_optimizer.py
Streamlit Tab: 🎯 Challenge: Two-Stage Tournament (Screen & Simulate)
Flagship quantitative studio for FPL Challenge mode.
Chains Stage 1 MILP Multi-Objective Screening into Stage 2 Monte Carlo Tournament Simulation.
Surfaces Top 3 Crowned Archetypes: Max EV (Balanced), Safe Floor, and GPP Winner (P99 Right-Tail).
Includes dynamic rule presets, 6-a-side pitch visualizer, and 1-click Challenge profile saving.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional, Dict, Any
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from ui.styles import render_html
from analytics.challenge.contracts import (
    ChallengeRuleSet,
    ChallengeOptimalSquad,
    EvaluatedChallengeCandidate,
    ChallengeTournamentReport,
)
from analytics.challenge.rule_extractor import (
    CHALLENGE_PRESETS,
    get_available_challenge_presets,
    extract_rules_from_event,
    build_custom_challenge_rule_set,
)
from analytics.challenge.two_stage_optimizer import ChallengeTwoStageOptimizer
from analytics.challenge.picker import ChallengePicker, ChallengePickerConfig, ChallengePickerResult
from automation.challenge_cpn.engine import ChallengeCPNEngine
from automation.challenge_cpn.diagnostics import ChallengeCPNDiagnosticJournal
from clients.fpl_challenge_client import FPLChallengeClient
from clients.auth_manager import AuthManager
from analytics.profile_manager import ProfileManager, slugify_name
from analytics.profile_contracts import ManagerProfile, ProfileType


def render_tab_challenge_optimizer(df: pd.DataFrame) -> None:
    """Renders the Two-Stage Challenge Optimization Studio."""
    st.title("🎯 Challenge: Two-Stage Tournament (Screen & Simulate)")
    st.markdown(r"""
    **High-Dimensional Quantitative Optimization Engine for FPL Challenge Mode:**
    - **Stage 1 (MILP Screening, <25ms)**: Enforces weekly dynamic constraints (variable squad size $N \in \{5, 6, 7, 11\}$, strict club limits $C \in \{1, 3, 5\}$, budget caps $\mathcal{B}$, positional constraints $\min \le x_{\text{pos}} \le \max$, and captaincy $c_i \le x_i$) across 5 tactical Pareto vectors.
    - **Stage 2 (Monte Carlo Tournament)**: Simulates each candidate across 1,000–10,000 joint draws to quantify Expected Return ($E[V]$), Downside Floor ($P_{10}$), Upside Ceiling ($P_{90}$), Tournament-Winning Right-Tail ($P_{99}$), and GPP Win Probability.
    """)

    presets = get_available_challenge_presets()
    preset_names = list(presets.keys())
    preset_labels = [presets[k].name for k in preset_names]
    preset_labels.append("🌐 Live Challenge API (Auto-Fetch)")
    preset_labels.append("🛠️ Custom Positional & Squad Configuration")

    # ------------------------------------------------------------------
    # 1. Dynamic Rules & Challenge Preset Selector
    # ------------------------------------------------------------------
    with st.expander("⚙️ Dynamic Challenge Rule Set & Positional Structure", expanded=True):
        col_preset, col_sim = st.columns([2, 1])
        with col_preset:
            selected_label = st.selectbox(
                "Select Gameweek Challenge Rule Preset / Mode:",
                options=preset_labels,
                index=0,
                key="challenge_preset_select",
                help="Switch between official weekly challenge formats (e.g. Balanced 2-2-2, One Player Per Club, All-Out Attack, Live API, or Custom Positional Configuration)."
            )

        with col_sim:
            sim_count = st.select_slider(
                "Monte Carlo Tournament Draws",
                options=[1000, 2500, 5000, 10000],
                value=2500,
                key="challenge_sim_slider",
                help="Higher draws provide tighter tail estimation for tournament-winning P99 metrics."
            )

        # Resolve initial base ChallengeRuleSet from preset or API
        base_rule_set: ChallengeRuleSet
        active_preset_key: Optional[str] = None
        if selected_label == "🌐 Live Challenge API (Auto-Fetch)":
            with st.spinner("Connecting to official FPL Challenge API..."):
                try:
                    client = FPLChallengeClient()
                    bootstrap = client.get_challenge_bootstrap()
                    events = bootstrap.get("events", [])
                    curr_ev = next((e for e in events if e.get("is_current")), events[0] if events else {})
                    base_rule_set = extract_rules_from_event(curr_ev)
                    st.success(f"Connected to Live API: Loaded '{base_rule_set.name}'")
                except Exception as e:
                    st.warning(f"Could not connect to live challenge endpoint ({e}). Falling back to One Player Per Club preset.")
                    base_rule_set = presets["gw5_one_player_per_club"]
        elif selected_label == "🛠️ Custom Positional & Squad Configuration":
            base_rule_set = presets["standard_6_a_side"]
        else:
            p_idx = preset_labels.index(selected_label)
            p_key = preset_names[p_idx]
            active_preset_key = p_key
            base_rule_set = presets[p_key]

        # --------------------------------------------------------------
        # Positional Requirements & Squad Structure Controls
        # --------------------------------------------------------------
        is_custom_selected = (selected_label == "🛠️ Custom Positional & Squad Configuration")
        override_positions = st.checkbox(
            "🛠️ Override / Fine-Tune Weekly Positional Limits & Squad Rules",
            value=is_custom_selected,
            key="challenge_override_positions_toggle",
            help="Enable direct manual control over Min/Max requirements for Goalkeepers, Defenders, Midfielders, Forwards, Squad Size, and Budget."
        )

        active_rule_set: ChallengeRuleSet
        if override_positions:
            st.markdown("##### 📐 Positional Requirements (Min – Max Players per Position)")
            p_c1, p_c2, p_c3, p_c4 = st.columns(4)

            init_gkp = base_rule_set.get_position_bounds("GKP")
            init_def = base_rule_set.get_position_bounds("DEF")
            init_mid = base_rule_set.get_position_bounds("MID")
            init_fwd = base_rule_set.get_position_bounds("FWD")

            with p_c1:
                gkp_range = st.slider(
                    "🧤 Goalkeepers (GKP)",
                    min_value=0,
                    max_value=2,
                    value=(int(init_gkp[0]), int(init_gkp[1])),
                    key="slider_challenge_gkp"
                )
            with p_c2:
                def_range = st.slider(
                    "🛡️ Defenders (DEF)",
                    min_value=0,
                    max_value=5,
                    value=(int(init_def[0]), int(init_def[1])),
                    key="slider_challenge_def"
                )
            with p_c3:
                mid_range = st.slider(
                    "⚙️ Midfielders (MID)",
                    min_value=0,
                    max_value=5,
                    value=(int(init_mid[0]), int(init_mid[1])),
                    key="slider_challenge_mid"
                )
            with p_c4:
                fwd_range = st.slider(
                    "🎯 Forwards (FWD)",
                    min_value=0,
                    max_value=5,
                    value=(int(init_fwd[0]), int(init_fwd[1])),
                    key="slider_challenge_fwd"
                )

            st.markdown("##### 🏟️ Squad & Financial Constraints")
            s_c1, s_c2, s_c3 = st.columns(3)
            with s_c1:
                custom_size = st.number_input(
                    "Squad Size (N Players)",
                    min_value=5,
                    max_value=15,
                    value=int(base_rule_set.squad_size),
                    step=1,
                    key="input_challenge_squad_size"
                )
            with s_c2:
                custom_max_club = st.number_input(
                    "Max Players Per Club (C)",
                    min_value=1,
                    max_value=5,
                    value=int(base_rule_set.max_per_team),
                    step=1,
                    key="input_challenge_max_per_team"
                )
            with s_c3:
                custom_budget = st.number_input(
                    "Budget Cap £m (999.9 for Unlimited)",
                    min_value=30.0,
                    max_value=999.9,
                    value=float(base_rule_set.budget_cap),
                    step=5.0,
                    key="input_challenge_budget_cap"
                )

            # Feasibility validation
            min_sum = gkp_range[0] + def_range[0] + mid_range[0] + fwd_range[0]
            max_sum = gkp_range[1] + def_range[1] + mid_range[1] + fwd_range[1]

            if min_sum > custom_size:
                st.error(f"⚠️ **Infeasible Positional Limits:** Sum of minimum positions required ({min_sum}) exceeds total squad size ({custom_size})! Please adjust your bounds.")
            elif max_sum < custom_size:
                st.error(f"⚠️ **Infeasible Positional Limits:** Sum of maximum positions allowed ({max_sum}) is less than total squad size ({custom_size})! Please adjust your bounds.")
            else:
                st.success(f"✅ **Valid Structure:** Required min sum ({min_sum}) ≤ Squad size ({custom_size}) ≤ Max capacity ({max_sum}).")

            active_rule_set = build_custom_challenge_rule_set(
                gameweek=base_rule_set.gameweek,
                name=f"Custom: {custom_size}-a-side ({def_range[0]}-{def_range[1]} DEF, {mid_range[0]}-{mid_range[1]} MID, {fwd_range[0]}-{fwd_range[1]} FWD)",
                squad_size=int(custom_size),
                max_per_team=int(custom_max_club),
                budget_cap=float(custom_budget),
                gkp_bounds=(int(gkp_range[0]), int(gkp_range[1])),
                def_bounds=(int(def_range[0]), int(def_range[1])),
                mid_bounds=(int(mid_range[0]), int(mid_range[1])),
                fwd_bounds=(int(fwd_range[0]), int(fwd_range[1])),
                scoring_modifiers=base_rule_set.scoring_modifiers,
                description=f"User configured: {custom_size} players, max {custom_max_club} per club, budget £{custom_budget:.1f}m."
            )
        else:
            active_rule_set = base_rule_set

        # Render Active Constraint KPI Badges
        st.markdown("---")
        kb1, kb2, kb3, kb4, kb5 = st.columns(5)
        kb1.metric(
            "🏟️ Squad Size",
            f"{active_rule_set.squad_size} Players",
            "Outfield Only (No GK)" if active_rule_set.is_outfield_only else "Goalkeeper Active"
        )
        kb2.metric(
            "🚫 Club Quota",
            f"Max {active_rule_set.max_per_team} Per Club",
            "Unique Club Limit" if active_rule_set.max_per_team == 1 else "Standard Cap"
        )
        kb3.metric(
            "💰 Budget Cap",
            "Unlimited (£999.9m)" if active_rule_set.budget_cap >= 900.0 else f"£{active_rule_set.budget_cap:.1f}m",
            "Financial Austerity" if active_rule_set.budget_cap < 90.0 else "Unconstrained"
        )
        kb4.metric(
            "📐 Positional Limits",
            active_rule_set.position_summary_str,
            "Exact Formation" if "Exact" in active_rule_set.name else "Dynamic Range"
        )
        mod_desc = ", ".join([f"{k} (+{v})" for k, v in active_rule_set.scoring_modifiers.items()]) if active_rule_set.scoring_modifiers else "Standard Rules"
        kb5.metric(
            "⚡ Scoring Modifiers",
            f"{len(active_rule_set.scoring_modifiers)} Active" if active_rule_set.scoring_modifiers else "None",
            mod_desc
        )

        st.caption(f"ℹ️ **Active Challenge Specification:** {active_rule_set.description}")

    # ------------------------------------------------------------------
    # 2. Squad Draft Constraints (Locks & Excludes)
    # ------------------------------------------------------------------
    all_player_names = sorted(df["web_name"].dropna().unique().tolist()) if "web_name" in df.columns else []

    with st.expander("🔒 Roster Locks, Excludes & Availability Filters", expanded=False):
        c_lock, c_exc, c_avail = st.columns([2, 2, 1])
        with c_lock:
            lock_players = st.multiselect(
                "Must-Have Locks (Forced in Squad):",
                options=all_player_names,
                default=[],
                key="challenge_lock_multiselect"
            )
        with c_exc:
            exclude_players = st.multiselect(
                "Excluded Players (Barred from Selection):",
                options=all_player_names,
                default=[],
                key="challenge_exclude_multiselect"
            )
        with c_avail:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            available_only = st.checkbox("Available Starters Only", value=True, key="challenge_avail_only")

    # ------------------------------------------------------------------
    # 2.5 Autonomous Challenge CPN Pipeline & Saga Diagnostics HUD
    # ------------------------------------------------------------------
    with st.expander("⚡ Autonomous Challenge CPN Pipeline & Saga Diagnostics HUD", expanded=False):
        st.markdown(r"""
        **Autonomous Coloured Petri Net (CPN) Engine with Verification & Saga Retry Protocol:**
        - **Formal Net**: $\mathcal{N} = (P, T, A, \Sigma, G, E, M_0)$ orchestrates rules extraction, market ingestion, squad optimization, config validation, and submission.
        - **Model Validation Engine**: Validates decisions against `config.yaml` (`tuned` profile) to flag parameter drift or constraint anomalies.
        - **Saga Processing**: Automated submission with live API state verification and exponential backoff retry loop.
        """)

        cpn_c1, cpn_c2, cpn_c3, cpn_c4 = st.columns([1.5, 1.5, 1.2, 1.2])
        with cpn_c1:
            cpn_mode = st.radio(
                "CPN Execution Mode:",
                options=["Dry-Run (Safe Drill)", "Live Submit (Official API)"],
                index=0,
                key="challenge_cpn_mode_radio",
                help="Dry-run tests the entire CPN flow and simulated Saga state without modifying your live FPL account."
            )
            is_dry_run = (cpn_mode == "Dry-Run (Safe Drill)")
        with cpn_c2:
            cpn_archetype = st.selectbox(
                "Target Archetype:",
                options=["max_ev", "safe_floor", "gpp_upside"],
                format_func=lambda x: {"max_ev": "👑 Max EV (Balanced)", "safe_floor": "🛡️ Safe Floor (High P10)", "gpp_upside": "🚀 GPP Upside (P99)"}[x],
                key="challenge_cpn_archetype_select"
            )
        with cpn_c3:
            cpn_retries = st.number_input("Max Saga Retries", min_value=1, max_value=5, value=3, step=1, key="challenge_cpn_retries")
        with cpn_c4:
            cpn_sims = st.selectbox("Monte Carlo Draws", options=[500, 1000, 2500], index=1, key="challenge_cpn_sims")

        auth_mgr = AuthManager()
        session_info = auth_mgr.get_active_session()
        is_authenticated = session_info.is_authenticated
        user_display = (
            f"{session_info.first_name} {session_info.last_name} (Entry ID: {session_info.entry_id})"
            if is_authenticated and session_info.first_name
            else "Clyde Watts (Entry ID: 6173410)"
        )

        if not is_dry_run:
            if is_authenticated:
                st.info(f"🔑 Live Submission Target: **{user_display}** (Active Session Token Verified)")
            else:
                st.warning("⚠️ No active FPL session found. Please authenticate in Profile Settings or use Dry-Run mode.")

        btn_run_cpn = st.button(
            "⚡ Launch Challenge CPN Pipeline",
            type="secondary",
            use_container_width=True,
            key="btn_run_challenge_cpn_pipeline"
        )

        if btn_run_cpn:
            with st.spinner("Executing Autonomous Challenge CPN Pipeline with Saga Verification..."):
                try:
                    journal = ChallengeCPNDiagnosticJournal()
                    engine = ChallengeCPNEngine(
                        journal=journal,
                        dry_run=is_dry_run
                    )
                    auth_headers = None
                    resolved_entry = session_info.entry_id or 6173410
                    if not is_dry_run and is_authenticated:
                        auth_headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RubiesRangersChallenge/1.0",
                            "Cookie": session_info.cookie_header
                        }
                        if session_info.auth_token.startswith("eyJ") and ";" not in session_info.auth_token:
                            auth_headers["Authorization"] = f"Bearer {session_info.auth_token}"

                    cpn_receipt = asyncio.run(engine.run_pipeline(
                        gameweek=active_rule_set.gameweek,
                        entry_id=resolved_entry,
                        players_df=df,
                        preset_key=active_preset_key,
                        archetype=cpn_archetype,
                        n_simulations=int(cpn_sims),
                        max_retries=int(cpn_retries),
                        lock_players=lock_players,
                        exclude_players=exclude_players,
                        available_only=available_only,
                        auth_headers=auth_headers
                    ))
                    st.session_state["last_challenge_cpn_receipt"] = cpn_receipt
                    st.session_state["last_challenge_cpn_engine"] = engine
                    st.toast("Challenge CPN execution complete!", icon="✅")
                except Exception as e:
                    st.error(f"Challenge CPN Pipeline execution error: {e}")

        # Show CPN execution results if available
        last_cpn_receipt = st.session_state.get("last_challenge_cpn_receipt")
        last_cpn_engine: Optional[ChallengeCPNEngine] = st.session_state.get("last_challenge_cpn_engine")

        if last_cpn_receipt:
            st.markdown("---")
            st.markdown("##### 📋 CPN Pipeline Execution Results & Saga Verification")
            res_c1, res_c2, res_c3, res_c4 = st.columns(4)
            rec = last_cpn_receipt.get("receipt", {}) if isinstance(last_cpn_receipt, dict) else {}
            plan = last_cpn_receipt.get("plan", {}) if isinstance(last_cpn_receipt, dict) else {}
            is_success = last_cpn_receipt.get("success", False) if isinstance(last_cpn_receipt, dict) else False

            res_c1.metric("Saga Status", "VERIFIED (CONFIRMED)" if is_success else "FAILED", f"GW{rec.get('gameweek', active_rule_set.gameweek)}")
            res_c2.metric("Captain / VC", f"{plan.get('captain', 'N/A')} (C)", f"{plan.get('vice_captain', 'N/A')} (VC)")
            res_c3.metric("Squad", f"{len(plan.get('squad', []))} Players", f"Archetype: {plan.get('archetype', '').upper()}")
            res_c4.metric("Verification Attempts", f"{rec.get('attempts_required', 1)} / {cpn_retries}", f"{last_cpn_receipt.get('duration_ms', 0):.1f} ms")

            # Model Validation Report Display
            if last_cpn_engine and last_cpn_engine.last_validation_report:
                val_rep = last_cpn_engine.last_validation_report
                st.markdown("##### 🔍 Model Validation Report (Config Settings vs Model State)")
                v_col1, v_col2 = st.columns([1, 2])
                with v_col1:
                    if val_rep.is_valid:
                        st.success("✅ **ALL MODEL CHECKS PASSED**\nNo constraint violations or parameter drift detected.")
                    else:
                        st.error(f"❌ **MODEL VALIDATION FAILED ({len(val_rep.errors)} Errors)**")
                with v_col2:
                    st.json(val_rep.summary_dict)

            # CPN Diagnostics Journal View
            st.markdown("##### 📜 Recent CPN Journal Telemetry")
            journal = ChallengeCPNDiagnosticJournal()
            recent_logs = journal.tail(15)
            if recent_logs:
                log_df = pd.DataFrame(recent_logs)[["timestamp", "event_type", "transition", "status", "message", "latency_ms"]]
                st.dataframe(log_df, use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------
    # 3. Execution Action Button (Interactive Studio Solver)
    # ------------------------------------------------------------------
    run_btn = st.button(
        "🚀 Run Challenge Two-Stage Tournament (Screen & Simulate)",
        type="primary",
        use_container_width=True,
        key="btn_run_challenge_tournament"
    )

    if run_btn:
        with st.spinner(f"Solving Stage 1 MILP & simulating {sim_count:,} Monte Carlo tournament draws..."):
            client = FPLChallengeClient()
            fixtures = client.get_fixtures(active_rule_set.gameweek)
            picker_cfg = ChallengePickerConfig(
                archetype="max_ev",
                n_simulations=sim_count,
                lock_players=lock_players if lock_players else None,
                exclude_players=exclude_players if exclude_players else None,
                available_only=available_only,
            )
            picker_result = ChallengePicker.pick_challenge_squad(
                players_df=df,
                rule_set=active_rule_set,
                fixtures=fixtures,
                config=picker_cfg,
            )
            st.session_state["challenge_tournament_report"] = picker_result.tournament_report
            st.session_state["challenge_picker_result"] = picker_result

    report: Optional[ChallengeTournamentReport] = st.session_state.get("challenge_tournament_report")

    if report is None:
        st.info("💡 Click **'Run Challenge Two-Stage Tournament'** above to generate optimal candidate squads across all tactical vectors and stress-test them under Monte Carlo simulation.")
        return

    evaluated = report.evaluated_candidates
    if not evaluated:
        st.error("❌ No mathematically feasible squads could be formed with the current constraints and player locks. Please relax locks or budget.")
        return

    # Top 3 Crowned Archetypes
    winner_ev = report.winner_balanced or evaluated[0]
    winner_floor = report.winner_safe_floor or evaluated[0]
    winner_gpp = report.winner_gpp_upside or evaluated[0]

    # ------------------------------------------------------------------
    # 4. Hero KPIs Container
    # ------------------------------------------------------------------
    st.markdown("---")
    hk1, hk2, hk3, hk4, hk5 = st.columns(5)
    hk1.metric(
        "Top Expected Return E[V]",
        f"{winner_ev.mean_points:.1f} pts",
        f"via {winner_ev.candidate.objective_name.upper()}"
    )
    hk2.metric(
        "Top Safety Floor (P10)",
        f"{winner_floor.floor_p10:.1f} pts",
        f"Median: {winner_floor.median_p50:.1f} pts"
    )
    hk3.metric(
        "GPP Haul Ceiling (P99)",
        f"{winner_gpp.tournament_p99:.1f} pts",
        f"P90: {winner_gpp.ceiling_p90:.1f} pts"
    )
    hk4.metric(
        "GPP Win Probability",
        f"{winner_gpp.win_probability_pct:.1f}%",
        "Field Top 1% Odds"
    )
    hk5.metric(
        "Screened Candidates",
        f"{len(evaluated)} Unique Roster(s)",
        f"Format: {active_rule_set.squad_size}-a-side"
    )

    # ------------------------------------------------------------------
    # 5. The 3 Crowned Strategic Archetype Cards
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("✨ The 3 Crowned Challenge Archetypes (Monte Carlo Modeled)")
    st.markdown("The Two-Stage solver surfaces three mathematically distinct tournament philosophies for this week's rule set:")

    card_c1, card_c2, card_c3 = st.columns(3)
    card_configs = [
        (card_c1, winner_ev, "OPTION 1: 🏆 MAX EXPECTED VALUE", "#facc15", "Balanced EV Engine"),
        (card_c2, winner_floor, "OPTION 2: 🛡️ HIGH-FLOOR SAFETY ANCHOR", "#38bdf8", "Downside Resilient"),
        (card_c3, winner_gpp, "OPTION 3: 🚀 GPP TOURNAMENT WINNER", "#ec4899", "Explosive P99 Right Tail"),
    ]

    for col, c_cand, badge_title, border_color, tag in card_configs:
        with col:
            talisman_str = c_cand.key_talismans or ", ".join(c_cand.candidate.squad_names[:2])
            render_html(f"""
            <div style="background: #1e293b; border: 2px solid {border_color}; border-radius: 12px; padding: 16px; min-height: 420px; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <b style="color: {border_color}; font-size: 13px; text-transform: uppercase;">{badge_title}</b>
                        <span style="background: #334155; color: #e2e8f0; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{c_cand.candidate.objective_name.upper()}</span>
                    </div>
                    <div style="background: #0f172a; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 3px solid {border_color};">
                        <span style="color: #94a3b8; font-size: 11px; font-weight: bold; text-transform: uppercase;">KEY TALISMANS & CAPTAIN</span><br/>
                        <b style="color: #ffffff; font-size: 14px;">{c_cand.candidate.captain} (C 2x)</b><br/>
                        <span style="color: #cbd5e1; font-size: 12px;">Supporting: <b style="color: #ffffff;">{talisman_str}</b></span><br/>
                        <span style="color: #94a3b8; font-size: 11px;">Cost: <b style="color: #ffffff;">£{c_cand.candidate.total_cost:.1f}m</b> | Clubs: <b style="color: #38bdf8;">{c_cand.candidate.clubs_represented}</b></span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; background: rgba(15, 23, 42, 0.6); padding: 10px; border-radius: 8px;">
                        <div><span style="color: #94a3b8; font-size: 11px;">Expected Score E[V]:</span><br/><b style="color: {border_color}; font-size: 17px;">{c_cand.mean_points:.1f} pts</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">Tournament P99 Tail:</span><br/><b style="color: #ec4899; font-size: 17px;">{c_cand.tournament_p99:.1f} pts</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">Floor (P10):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{c_cand.floor_p10:.1f} pts</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">Ceiling (P90):</span><br/><b style="color: #cbd5e1; font-size: 14px;">{c_cand.ceiling_p90:.1f} pts</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">GPP Win Probability:</span><br/><b style="color: #38bdf8; font-size: 14px;">{c_cand.win_probability_pct:.1f}%</b></div>
                        <div><span style="color: #94a3b8; font-size: 11px;">In-Play Flexibility:</span><br/><b style="color: #34d399; font-size: 14px;">{c_cand.flexibility_score}/100</b></div>
                    </div>
                </div>
            </div>
            """)

    # ------------------------------------------------------------------
    # 6. Interactive 6-a-Side Pitch Visualizer
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("🏟️ 6-a-Side Dynamic Challenge Pitch Visualizer")
    st.markdown("Inspect tactical formations (e.g. 1-3-2, 2-2-2, 1-2-3), club allocations, captaincy multiplier ($2\\times$), and individual expected point yields.")

    squad_options = [
        f"{c.archetype}: {c.candidate.objective_name.upper()} (E[V]: {c.mean_points:.1f} pts, P99: {c.tournament_p99:.1f} pts)"
        for c in evaluated
    ]
    selected_label = st.selectbox(
        "Select Challenge Candidate Roster to Inspect:",
        options=squad_options,
        index=0,
        key="challenge_pitch_select"
    )
    selected_idx = squad_options.index(selected_label)
    active_eval = evaluated[selected_idx]
    active_squad = active_eval.candidate

    # Pitch overview banner
    st.markdown(f"""
    <div style="background: #1e293b; border-left: 4px solid #38bdf8; padding: 10px 16px; border-radius: 8px; margin-bottom: 16px;">
        <b style="color: #38bdf8; font-size: 15px;">Active Roster:</b>
        <span style="color: #cbd5e1; font-size: 13px; margin-left: 12px;">
            Formation: <b style="color: #ffffff;">{active_squad.formation}</b> |
            Captain: <b style="color: #facc15;">{active_squad.captain} (2x)</b> |
            Total Spend: <b style="color: #ffffff;">£{active_squad.total_cost:.1f}m</b> |
            Clubs: <b style="color: #34d399;">{active_squad.clubs_represented} Distinct Clubs</b>
        </span>
    </div>
    """, unsafe_allow_html=True)

    _render_challenge_pitch(df, active_squad)

    # ------------------------------------------------------------------
    # 7. Graphical Visual Suite (Tail Risk & Monte Carlo Density)
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Stochastic Distribution & Tournament Tail Risk Analysis")
    g_tab1, g_tab2, g_tab3 = st.tabs([
        "📈 Probability Density Overlay",
        "📊 Percentile Spread (P10 ➔ P50 ➔ P90 ➔ P99)",
        "🎯 GPP Risk vs. Right-Tail Frontier"
    ])

    with g_tab1:
        st.markdown("#### Monte Carlo Density Comparison: Top Challenge Archetypes")
        fig_dist = go.Figure()
        colors = ["#facc15", "#38bdf8", "#ec4899", "#a855f7", "#22c55e"]
        for idx, cand in enumerate(evaluated[:5]):
            if cand.raw_totals is not None and len(cand.raw_totals) > 0:
                fig_dist.add_trace(go.Histogram(
                    x=cand.raw_totals,
                    histnorm="probability density",
                    name=f"{cand.candidate.objective_name.upper()} ({cand.mean_points:.1f} pts)",
                    marker_color=colors[idx % len(colors)],
                    opacity=0.45,
                    nbinsx=40
                ))
        fig_dist.update_layout(
            barmode="overlay",
            paper_bgcolor="#0b0f19",
            plot_bgcolor="#1e293b",
            font={"color": "#f8fafc"},
            xaxis={"title": "Simulated Gameweek Score (Points)", "gridcolor": "rgba(255,255,255,0.08)"},
            yaxis={"title": "Probability Density", "gridcolor": "rgba(255,255,255,0.08)"},
            legend={"orientation": "h", "y": 1.15, "x": 0.0},
            height=380,
            margin={"l": 20, "r": 20, "t": 40, "b": 20}
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    with g_tab2:
        st.markdown("#### Horizontal Distribution Breakdown (Floor ➔ Median ➔ Ceiling ➔ P99 Tail)")
        comp_names = [f"{c.candidate.objective_name.upper()} ({c.mean_points:.1f})" for c in evaluated]
        p10_vals = [c.floor_p10 for c in evaluated]
        p50_vals = [c.median_p50 for c in evaluated]
        p90_vals = [c.ceiling_p90 for c in evaluated]
        p99_vals = [c.tournament_p99 for c in evaluated]

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
            name="P50 Median",
            y=comp_names,
            x=[max(0.0, p50 - p10) for p50, p10 in zip(p50_vals, p10_vals)],
            base=p10_vals,
            orientation="h",
            marker_color="#facc15",
            text=[f"{v:.1f}" for v in p50_vals],
            textposition="inside"
        ))
        fig_bar.add_trace(go.Bar(
            name="P90 Ceiling",
            y=comp_names,
            x=[max(0.0, p90 - p50) for p90, p50 in zip(p90_vals, p50_vals)],
            base=p50_vals,
            orientation="h",
            marker_color="#ec4899",
            text=[f"{v:.1f}" for v in p90_vals],
            textposition="inside"
        ))
        fig_bar.add_trace(go.Bar(
            name="P99 Tournament Winning Tail",
            y=comp_names,
            x=[max(0.0, p99 - p90) for p99, p90 in zip(p99_vals, p90_vals)],
            base=p90_vals,
            orientation="h",
            marker_color="#a855f7",
            text=[f"{v:.1f}" for v in p99_vals],
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

    with g_tab3:
        st.markdown("#### Risk vs. Right-Tail Frontier (Floor P10 vs. P99 Tail)")
        df_all = report.all_results_df
        if not df_all.empty:
            try:
                fig_scatter = px.scatter(
                    df_all,
                    x="Floor (P10)",
                    y="Tournament (P99)",
                    size="E[Points]",
                    color="Objective",
                    hover_name="Captain",
                    text="Objective",
                    title="Challenge GPP Frontier: Top-Right = High Floor & Explosive Tournament Upside"
                )
                fig_scatter.update_traces(textposition="top center")
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
                st.caption(f"Scatter chart unavailable: {e}")

    # ------------------------------------------------------------------
    # 8. Comparative Candidate Leaderboard Table
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📋 Comparative Candidate Leaderboard (All Screened Squads)")
    if not report.all_results_df.empty:
        st.dataframe(
            report.all_results_df,
            use_container_width=True,
            hide_index=True
        )

    # ------------------------------------------------------------------
    # 9. 1-Click Save as Challenge Profile Draft
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown("##### 💾 Save this Challenge Squad to a Profile Draft")
    st.caption("Creates an independent Challenge profile in your manager switcher so you can monitor rolling lockouts and captaincy pivots.")

    s_col1, s_col2 = st.columns([3, 1])
    with s_col1:
        draft_name = st.text_input(
            "Challenge Profile Name",
            value=f"Challenge: {active_squad.objective_name.title()} ({active_eval.mean_points:.1f} pts)",
            key="input_save_challenge_profile"
        )
    with s_col2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("📥 Save Challenge Profile", key="btn_save_challenge_profile", use_container_width=True):
            if draft_name.strip():
                try:
                    p_mgr = ProfileManager()
                    new_pid = f"challenge_{slugify_name(draft_name.strip())}"
                    new_profile = ManagerProfile(
                        profile_id=new_pid,
                        display_name=draft_name.strip(),
                        profile_type=ProfileType.CHALLENGE,
                        fpl_entry_id=None,
                        bank_balance=round(float(active_squad.bank_remaining), 1),
                        active_squad=list(active_squad.squad_names),
                        mini_league_ids=[],
                        calibration_profile="challenge",
                        notes=f"FPL Challenge Roster ({active_rule_set.name}). Captain={active_squad.captain}. E[V]={active_eval.mean_points:.1f}, P99={active_eval.tournament_p99:.1f}.",
                        is_read_only=False,
                        is_default=False
                    )
                    p_mgr.save_profile(new_profile)
                    st.session_state["active_profile_id"] = new_pid
                    st.cache_data.clear()
                    st.success(f"✅ Created and switched to Challenge profile '{new_profile.display_name}'!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save profile: {e}")


def _render_challenge_pitch(df: pd.DataFrame, squad: ChallengeOptimalSquad) -> None:
    """Renders synthetic pitch graphic grouping players by GKP, DEF, MID, FWD."""
    # Lookup player details
    p_df = df[df["web_name"].isin(squad.squad_names)].copy()
    if "position" not in p_df.columns and "position_name" in p_df.columns:
        p_df["position"] = p_df["position_name"]

    gkps = p_df[p_df["position"] == "GKP"].to_dict(orient="records")
    defs = p_df[p_df["position"] == "DEF"].to_dict(orient="records")
    mids = p_df[p_df["position"] == "MID"].to_dict(orient="records")
    fwds = p_df[p_df["position"] == "FWD"].to_dict(orient="records")

    def _render_player_card(p: Dict[str, Any]) -> str:
        name = p.get("web_name", "Player")
        club = p.get("club", p.get("team_name", ""))
        cost = p.get("now_cost", 0.0)
        xp = p.get("challenge_xP", p.get("xP", 0.0))
        is_capt = (name == squad.captain)

        border_style = "border: 2px solid #ffd700;" if is_capt else "border: 1px solid rgba(255,255,255,0.15);"
        capt_badge = "<span style='background: #ffd700; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;'>CAPT (2x)</span>" if is_capt else ""

        return f"""
        <div style="background: rgba(15, 23, 42, 0.85); {border_style} border-radius: 8px; padding: 8px 10px; text-align: center; min-width: 120px; box-shadow: 0 4px 8px rgba(0,0,0,0.5);">
            <div style="margin-bottom: 4px;">{capt_badge}</div>
            <b style="color: #ffffff; font-size: 13px;">{name}</b><br/>
            <span style="color: #94a3b8; font-size: 11px;">{club} • £{cost:.1f}m</span><br/>
            <span style="color: #38bdf8; font-size: 12px; font-weight: bold;">{xp:.1f} xP</span>
        </div>
        """

    # Build pitch container
    gkp_cards = "".join([_render_player_card(p) for p in gkps])
    def_cards = "".join([_render_player_card(p) for p in defs])
    mid_cards = "".join([_render_player_card(p) for p in mids])
    fwd_cards = "".join([_render_player_card(p) for p in fwds])

    gkp_section = f"""
        <div style="border-top: 1px dashed rgba(255,255,255,0.2); margin: 16px 0;"></div>
        <div style="text-align: center; color: rgba(255,255,255,0.4); font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 12px;">GOALKEEPING BASE</div>
        <div style="display: flex; justify-content: space-around; align-items: center;">
            {gkp_cards}
        </div>
    """ if gkps else ""

    render_html(f"""
    <div style="background: radial-gradient(ellipse at center, #14532d 0%, #052e16 100%); border: 2px solid #22c55e; border-radius: 14px; padding: 24px; margin-bottom: 20px; box-shadow: inset 0 0 40px rgba(0,0,0,0.6);">
        <!-- Pitch Markings -->
        <div style="text-align: center; color: rgba(255,255,255,0.4); font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 12px;">ATTACKING THIRD</div>
        <div style="display: flex; justify-content: space-around; align-items: center; margin-bottom: 20px;">
            {fwd_cards if fwd_cards else "<span style='color: #64748b;'>No Forwards</span>"}
        </div>
        
        <div style="border-top: 1px dashed rgba(255,255,255,0.2); margin: 16px 0;"></div>
        <div style="text-align: center; color: rgba(255,255,255,0.4); font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 12px;">MIDFIELD ENGINE</div>
        <div style="display: flex; justify-content: space-around; align-items: center; margin-bottom: 20px;">
            {mid_cards if mid_cards else "<span style='color: #64748b;'>No Midfielders</span>"}
        </div>
        
        <div style="border-top: 1px dashed rgba(255,255,255,0.2); margin: 16px 0;"></div>
        <div style="text-align: center; color: rgba(255,255,255,0.4); font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 12px;">DEFENSIVE BASE</div>
        <div style="display: flex; justify-content: space-around; align-items: center;">
            {def_cards if def_cards else "<span style='color: #64748b;'>No Defenders</span>"}
        </div>
        {gkp_section}
    </div>
    """)
