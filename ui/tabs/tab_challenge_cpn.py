"""
ui/tabs/tab_challenge_cpn.py
Streamlit telemetry, live monitoring, and execution controller for the
Autonomous Challenge Coloured Petri Net (CPN) Robotic Manager.
Features a cybernetic Petri Net HUD, Saga verification inspector,
and quantitative model validation engine.
"""

from __future__ import annotations

import asyncio
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import pandas as pd
import streamlit as st

from analytics.challenge.contracts import (
    ChallengeRuleSet,
)
from analytics.challenge.rule_extractor import (
    CHALLENGE_PRESETS,
    get_available_challenge_presets,
    extract_rules_from_event,
)
from analytics.challenge.picker import ChallengePickerConfig
from automation.challenge_cpn import (
    ChallengeCPNEngine,
    ChallengeCPNDiagnosticJournal,
)
from clients.auth_manager import AuthManager
from clients.fpl_challenge_client import FPLChallengeClient
from config_manager import get_system_config


def render_tab_challenge_cpn(df: pd.DataFrame) -> None:
    """Renders the autonomous Challenge Coloured Petri Net (CPN) Mission-Control Dashboard."""

    st.header("🤖 Autonomous Challenge CPN Robotic Manager")
    st.markdown(
        "Formal **Kurt Jensen Coloured Petri Net** $\\mathcal{N} = (P, T, A, \\Sigma, G, E, M_0)$ "
        "governing FPL Challenge team selection, quantitative model validation, and self-healing **Saga submission & verification**."
    )

    # ------------------------------------------------------------------
    # 1. Manager Identity & Live Session Status
    # ------------------------------------------------------------------
    auth_mgr = AuthManager()
    session_info = auth_mgr.get_active_session()
    is_authenticated = session_info.is_authenticated
    user_display = (
        f"{session_info.first_name} {session_info.last_name} (Entry ID: {session_info.entry_id})"
        if is_authenticated and session_info.first_name
        else "Clyde Watts (Entry ID: 6173410)"
    )

    id_col1, id_col2 = st.columns([3, 1])
    with id_col1:
        if is_authenticated:
            st.markdown(
                f"""
                <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid #10b981; border-radius: 8px; padding: 10px 16px; margin-bottom: 12px;">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <span style="color: #4ade80; font-weight: 700; font-size: 14px;">
                            🟢 LIVE CHALLENGE SESSION: {user_display}
                        </span>
                        <span style="background: #064e3b; color: #a7f3d0; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">
                            Source: {session_info.auth_source} • Bank: £{session_info.bank:.1f}m
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                """
                <div style="background: rgba(245, 158, 11, 0.12); border: 1px solid #f59e0b; border-radius: 8px; padding: 10px 16px; margin-bottom: 12px;">
                    <span style="color: #fbbf24; font-weight: 700; font-size: 14px;">
                        ⚠️ OFFLINE / GUEST SESSION: Running in local sandbox mode. Authenticate in Settings for live submission.
                    </span>
                </div>
                """,
                unsafe_allow_html=True
            )

    with id_col2:
        journal_file_exists = os.path.exists(
            os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "logs", "diagnostics")
        )
        st.markdown(
            f"""
            <div style="background: rgba(59, 130, 246, 0.12); border: 1px solid #3b82f6; border-radius: 8px; padding: 10px 16px; text-align: center; margin-bottom: 12px;">
                <span style="color: #60a5fa; font-weight: 700; font-size: 13px;">
                    📜 Journal: {'ACTIVE' if journal_file_exists else 'STANDBY'}
                </span>
            </div>
            """,
            unsafe_allow_html=True
        )

    # ------------------------------------------------------------------
    # 2. Formal Petri Net Bipartite Architecture Graph
    # ------------------------------------------------------------------
    with st.expander("🗺️ Petri Net Bipartite Architecture & Token Life-Cycle", expanded=False):
        st.markdown(
            """
            ```mermaid
            graph LR
                P_IDLE([P_IDLE]) --> T_RULES[T_RULES]
                T_RULES --> P_RULES([P_RULES_READY])
                P_RULES --> T_MARKET[T_MARKET]
                T_MARKET --> P_MARKET([P_MARKET_READY])
                P_MARKET --> T_TEAM[T_TEAM]
                T_TEAM --> P_TEAM([P_TEAM_READY])
                P_TEAM --> T_SOLVE[T_SOLVE_PICKER]
                T_SOLVE --> P_OPT([P_OPTIMIZED])
                P_OPT --> T_VAL[T_VALIDATE_MODEL]
                T_VAL --> P_VAL([P_VALIDATED])
                P_VAL --> T_SUBMIT[T_SAGA_SUBMIT]
                T_SUBMIT --> P_SUBMIT([P_SAGA_SUBMITTED])
                P_SUBMIT --> T_VERIFY[T_SAGA_VERIFY]
                T_VERIFY -->|Verified| P_RECEIPT([P_SAGA_VERIFIED])
                T_VERIFY -->|Mismatch / Retry| T_SUBMIT

                classDef place fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
                classDef trans fill:#0f172a,stroke:#f59e0b,stroke-width:2px,color:#fde047;
                classDef receipt fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#a7f3d0;
                class P_IDLE,P_RULES,P_MARKET,P_TEAM,P_OPT,P_VAL,P_SUBMIT place;
                class T_RULES,T_MARKET,T_TEAM,T_SOLVE,T_VAL,T_SUBMIT,T_VERIFY trans;
                class P_RECEIPT receipt;
            ```
            """
        )
        st.caption("Flow diagram of mathematical places $P$ (circles), transitions $T$ (boxes), and self-healing Saga verification arc.")

    # ------------------------------------------------------------------
    # 3. Execution Configuration Deck
    # ------------------------------------------------------------------
    st.markdown("### 🎛️ CPN Execution Deck & Strategy Knobs")
    presets = get_available_challenge_presets()
    preset_names = list(presets.keys())
    preset_options = ["🌐 Live Challenge API (Auto-Fetch)"] + [f"📋 {presets[k].name}" for k in preset_names]

    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1.5, 1.5, 1.5, 1.0])

    with ctrl_col1:
        exec_mode = st.radio(
            "CPN Execution Mode:",
            options=["Dry-Run (Safe Drill)", "Live Submit (Official FPL API)"],
            index=0,
            key="ch_cpn_tab_mode_radio",
            help="Dry-run tests the entire CPN solver, model validation, and simulated Saga verification without touching live accounts."
        )
        is_dry_run = (exec_mode == "Dry-Run (Safe Drill)")

    with ctrl_col2:
        archetype = st.selectbox(
            "Target Optimization Archetype:",
            options=["max_ev", "safe_floor", "gpp_upside"],
            format_func=lambda x: {
                "max_ev": "👑 Max EV (Balanced Portfolio)",
                "safe_floor": "🛡️ Safe Floor (High P10 Capital Preservation)",
                "gpp_upside": "🚀 GPP Upside (P99 Right-Tail Tournament)"
            }[x],
            key="ch_cpn_tab_archetype"
        )

    with ctrl_col3:
        selected_preset = st.selectbox(
            "Challenge Rule Specification:",
            options=preset_options,
            index=1,
            key="ch_cpn_tab_preset"
        )
        preset_key: Optional[str] = None
        if selected_preset != "🌐 Live Challenge API (Auto-Fetch)":
            p_idx = preset_options.index(selected_preset) - 1
            preset_key = preset_names[p_idx]

    with ctrl_col4:
        gameweek = st.number_input("Gameweek", min_value=1, max_value=38, value=5, step=1, key="ch_cpn_tab_gw")

    # Advanced Knobs Expander
    with st.expander("⚙️ Advanced Roster Locks, Excludes & Solver Parameters", expanded=False):
        all_player_names = sorted(df["web_name"].dropna().unique().tolist()) if "web_name" in df.columns else []
        adv_c1, adv_c2, adv_c3, adv_c4 = st.columns([2, 2, 1, 1])

        with adv_c1:
            lock_players = st.multiselect(
                "Must-Have Player Locks:",
                options=all_player_names,
                default=[],
                key="ch_cpn_tab_locks"
            )
        with adv_c2:
            exclude_players = st.multiselect(
                "Excluded Players (Barred):",
                options=all_player_names,
                default=[],
                key="ch_cpn_tab_excludes"
            )
        with adv_c3:
            max_retries = st.number_input("Max Saga Retries", min_value=1, max_value=5, value=3, step=1, key="ch_cpn_tab_retries")
        with adv_c4:
            n_sims = st.selectbox("Monte Carlo Draws", options=[500, 1000, 2500], index=1, key="ch_cpn_tab_sims")

        available_only = st.checkbox("Available Starters Only (Exclude 0% / 25% injury flags)", value=True, key="ch_cpn_tab_avail")

    # ------------------------------------------------------------------
    # 4. Pipeline Execution Button & Controller
    # ------------------------------------------------------------------
    run_col1, run_col2 = st.columns([3, 1])
    with run_col1:
        if not is_dry_run:
            if is_authenticated:
                st.warning(f"⚠️ **LIVE SUBMISSION ENABLED:** Squad will be dispatched directly to FPL Challenge API for **{user_display}**.")
            else:
                st.error("🚨 **No active authenticated FPL session found!** Switch to Dry-Run mode or authenticate in Settings.")

    btn_fire_cpn = st.button(
        "⚡ Launch Autonomous Challenge CPN Cycle",
        type="primary",
        use_container_width=True,
        key="btn_fire_challenge_cpn_main"
    )

    if btn_fire_cpn:
        with st.spinner("🤖 Orchestrating Kurt Jensen Challenge CPN transitions & Saga loop..."):
            try:
                journal = ChallengeCPNDiagnosticJournal()
                engine = ChallengeCPNEngine(
                    journal=journal,
                    dry_run=is_dry_run
                )

                auth_headers: Optional[Dict[str, str]] = None
                resolved_entry = session_info.entry_id or 6173410
                if not is_dry_run and is_authenticated:
                    auth_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RubiesRangersChallenge/1.0",
                        "Cookie": session_info.cookie_header
                    }
                    if session_info.auth_token.startswith("eyJ") and ";" not in session_info.auth_token:
                        auth_headers["Authorization"] = f"Bearer {session_info.auth_token}"

                t0 = datetime.now(timezone.utc)
                receipt = asyncio.run(engine.run_pipeline(
                    gameweek=int(gameweek),
                    entry_id=resolved_entry,
                    players_df=df,
                    preset_key=preset_key,
                    archetype=archetype,
                    n_simulations=int(n_sims),
                    max_retries=int(max_retries),
                    lock_players=lock_players,
                    exclude_players=exclude_players,
                    available_only=available_only,
                    auth_headers=auth_headers
                ))
                st.session_state["ch_cpn_last_receipt"] = receipt
                st.session_state["ch_cpn_last_engine"] = engine
                st.toast("Autonomous Challenge CPN cycle complete!", icon="✅")
            except Exception as e:
                st.error(f"❌ Challenge CPN Pipeline Error: {e}")

    # ------------------------------------------------------------------
    # 5. Pipeline Telemetry & Results Display
    # ------------------------------------------------------------------
    last_receipt = st.session_state.get("ch_cpn_last_receipt")
    last_engine: Optional[ChallengeCPNEngine] = st.session_state.get("ch_cpn_last_engine")

    if last_receipt and isinstance(last_receipt, dict):
        st.markdown("---")
        st.subheader("📊 CPN Execution Telemetry & Verification Audit")

        is_success = last_receipt.get("success", False)
        rec = last_receipt.get("receipt", {})
        plan = last_receipt.get("plan", {})
        val = last_receipt.get("validation", {})
        duration_ms = last_receipt.get("duration_ms", 0.0)

        # Top KPIs
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("Saga Status", "VERIFIED (CONFIRMED)" if is_success else "FAILED", f"GW{rec.get('gameweek', gameweek)}")
        kpi2.metric("Archetype", plan.get("archetype", archetype).upper(), f"E[V] {plan.get('expected_ev', 0.0):.1f} pts")
        kpi3.metric("Captain / VC", f"{plan.get('captain', 'N/A')} (C)", f"{plan.get('vice_captain', 'N/A')} (VC)")
        kpi4.metric("Saga Attempts", f"{rec.get('attempts_required', 1)} / {max_retries}", f"Latency: {duration_ms:.1f}ms")
        kpi5.metric("Model Invariants", "PASSED (0 Errors)" if val.get("is_valid") else "FAILED", f"{len(val.get('warnings', []))} Warnings")

        # 5.1 Selected Lineup Table
        st.markdown("#### 🏆 Optimal Challenge Squad Selection")
        squad_names = plan.get("squad", [])
        if squad_names and "web_name" in df.columns:
            sub_df = df[df["web_name"].isin(squad_names)].copy()
            if not sub_df.empty:
                # Add status indicators
                sub_df["Role"] = sub_df["web_name"].apply(
                    lambda name: "👑 Captain (2x)" if name == plan.get("captain")
                    else ("🛡️ Vice-Captain" if name == plan.get("vice_captain") else "Starter")
                )
                cols_to_show = ["Role", "web_name", "element_type", "team", "now_cost", "ep_this"]
                display_cols = [c for c in cols_to_show if c in sub_df.columns]
                st.dataframe(
                    sub_df[display_cols].rename(columns={
                        "web_name": "Player",
                        "element_type": "Position",
                        "team": "Club",
                        "now_cost": "Cost (£m)",
                        "ep_this": "xP"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.write(", ".join(squad_names))
        else:
            st.write(", ".join(squad_names))

        # 5.2 Quantitative Model Validation Report Card
        if last_engine and last_engine.last_validation_report:
            val_rep = last_engine.last_validation_report
            st.markdown("#### 🔍 Quantitative Model Validation (Config vs Model State)")
            mv_c1, mv_c2 = st.columns([1, 2])
            with mv_c1:
                if val_rep.is_valid:
                    st.success(
                        f"✅ **ALL INVARIANTS SATISFIED**\n\n"
                        f"- Total Checks: **{len(val_rep.checks_passed)} passed**\n"
                        f"- Zero constraint violations or parameter drift detected."
                    )
                else:
                    st.error(f"❌ **MODEL VALIDATION FAILED ({len(val_rep.errors)} Errors)**")
                    for err in val_rep.errors:
                        st.markdown(f"- 🚨 {err}")

            with mv_c2:
                with st.expander("📋 Verified Constraint Checks & Parameter Comparison", expanded=True):
                    for chk in val_rep.checks_passed:
                        st.markdown(f"✓ `{chk}`")
                    if val_rep.setting_comparison:
                        st.markdown("##### Hyperparameter Alignment (`config.yaml` tuned profile):")
                        cmp_df = pd.DataFrame([
                            {"Parameter": k, "Config Setting": v.get("config_value"), "Model Realized": v.get("model_value"), "Match": "✅" if v.get("matches") else "⚠️"}
                            for k, v in val_rep.setting_comparison.items()
                        ])
                        st.dataframe(cmp_df, use_container_width=True, hide_index=True)

        # 5.3 Saga Transaction Receipt Card
        st.markdown("#### 🧾 Saga Transaction Receipt")
        st.json(rec)

    # ------------------------------------------------------------------
    # 6. Append-Only Diagnostic Journal Telemetry Feed
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📜 Diagnostic Journal & Real-Time Telemetry Feed")
    journal = ChallengeCPNDiagnosticJournal()
    recent_entries = journal.tail(limit=25)

    if recent_entries:
        records_for_display = []
        for e in reversed(recent_entries):
            r_type = e.get("record_type", "event")
            d = e.get("data", {})
            records_for_display.append({
                "Timestamp (UTC)": e.get("timestamp_utc", ""),
                "Type": r_type,
                "Detail": (
                    f"Transition: {d.get('transition')} ({d.get('status')}) [{d.get('duration_ms')}ms]" if r_type == "transition_firing"
                    else (
                        f"Saga: {d.get('action')} - Attempt {d.get('attempt')}/{d.get('max_retries')} ({d.get('status')})" if r_type == "saga_step"
                        else (
                            f"Model Val: Valid={d.get('is_valid')} (Errors={d.get('error_count')}, Warnings={d.get('warning_count')})" if r_type == "model_validation"
                            else str(d)[:80]
                        )
                    )
                )
            })
        st.dataframe(pd.DataFrame(records_for_display), use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ No diagnostic entries recorded yet for today. Launch a CPN cycle above to generate immutable telemetry.")
