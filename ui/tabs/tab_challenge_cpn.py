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
import streamlit.components.v1 as components

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
from automation.challenge_cpn.engine import (
    CHALLENGE_TRANSITION_SPECS,
    CHALLENGE_PLACE_SPECS,
)
from clients.auth_manager import AuthManager
from clients.fpl_challenge_client import FPLChallengeClient
from config_manager import get_system_config


def _get_default_challenge_snapshot() -> dict[str, Any]:
    """Generates default initial snapshot with complete specs for interactive inspection."""
    place_keys = list(CHALLENGE_PLACE_SPECS.keys())
    return {
        "place_counts": {p: 0 for p in place_keys},
        "marking_vector": [0] * len(place_keys),
        "transition_stats": {
            t: {"status": "STANDBY", "fire_count": 0, "mean_latency_ms": 0.0, "last_latency_ms": 0.0}
            for t in CHALLENGE_TRANSITION_SPECS
        },
        "transition_specs": CHALLENGE_TRANSITION_SPECS,
        "place_specs": CHALLENGE_PLACE_SPECS,
        "last_plan_id": None,
        "receipt_id": None,
    }


def _build_challenge_workbench_html(snapshot: dict[str, Any]) -> str:
    """
    Renders the complete cybernetic Challenge CPN Workbench with an interactive SVG bipartite net
    and a reactive Node Inspector panel matching the institutional trading desk standard.
    """
    if "transition_specs" not in snapshot:
        snapshot["transition_specs"] = CHALLENGE_TRANSITION_SPECS
    if "place_specs" not in snapshot:
        snapshot["place_specs"] = CHALLENGE_PLACE_SPECS
    if "transition_stats" not in snapshot:
        snapshot["transition_stats"] = {
            t_name: {"status": "STANDBY", "fire_count": 0, "mean_latency_ms": 0.0, "last_latency_ms": 0.0}
            for t_name in CHALLENGE_TRANSITION_SPECS
        }

    t_stats = snapshot.get("transition_stats", {})
    p_counts = snapshot.get("place_counts", {})
    is_confirmed = bool(p_counts.get("P_CHALLENGE_CONFIRMED", 0) > 0 or snapshot.get("receipt_id"))

    snapshot_json = json.dumps(snapshot)

    def _t_cls(t_name: str) -> str:
        st_val = t_stats.get(t_name, {}).get("status", "STANDBY")
        if st_val == "ALIVE_FIRED":
            return "trans-node trans-fired"
        elif st_val == "BLOCKED":
            return "trans-node trans-blocked"
        elif st_val == "RETRYING":
            return "trans-node trans-retrying"
        return "trans-node"

    def _t_badge(t_name: str) -> tuple[str, str]:
        st_val = t_stats.get(t_name, {}).get("status", "STANDBY")
        if st_val == "ALIVE_FIRED":
            return ("[ ALIVE / FIRED ]", "#4ade80")
        elif st_val == "BLOCKED":
            return ("[ BLOCKED ]", "#ef4444")
        elif st_val == "RETRYING":
            return ("[ SAGA RETRY ]", "#f59e0b")
        return ("[ STANDBY ]", "#94a3b8")

    def _p_cls(p_name: str) -> str:
        if p_name == "P_CHALLENGE_CONFIRMED" and is_confirmed:
            return "place-node place-committed"
        cnt = p_counts.get(p_name, 0)
        spec = CHALLENGE_PLACE_SPECS.get(p_name, {})
        if cnt > 0 or (spec.get("is_read_arc") and cnt is not False and cnt != 0):
            return "place-node place-has-token"
        return "place-node"

    # Badges for transitions
    b_rules, c_rules = _t_badge("T_FETCH_CHALLENGE_RULES")
    b_market, c_market = _t_badge("T_INGEST_CHALLENGE_MARKET")
    b_team, c_team = _t_badge("T_FETCH_CURRENT_TEAM")
    b_solve, c_solve = _t_badge("T_RUN_CHALLENGE_PICKER")
    b_val, c_val = _t_badge("T_VALIDATE_MODEL_SETTINGS")
    b_sub, c_sub = _t_badge("T_SAGA_SUBMIT")
    b_ver, c_ver = _t_badge("T_SAGA_VERIFY")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
    * {{
        box-sizing: border-box;
        margin: 0;
        padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}
    body {{
        background-color: #080c14;
        color: #e2e8f0;
        overflow: hidden;
        user-select: none;
    }}
    .workbench-container {{
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 720px;
        background: #080c14;
        border: 1px solid #1e293b;
        border-radius: 8px;
        overflow: hidden;
    }}
    /* Top HUD Bar */
    .hud-bar {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 16px;
        background: #0b1120;
        border-bottom: 1px solid #1e293b;
        font-size: 11px;
        letter-spacing: 0.5px;
    }}
    .hud-spec {{
        color: #38bdf8;
        font-weight: 700;
        font-family: monospace;
    }}
    .hud-counts {{
        color: #94a3b8;
        font-family: monospace;
    }}
    .hud-marking {{
        color: #4ade80;
        font-family: monospace;
        font-weight: 600;
    }}

    /* Main Workspace Layout */
    .workspace {{
        display: flex;
        flex: 1;
        height: calc(100% - 37px);
        position: relative;
    }}

    /* Left Net Canvas */
    .canvas-panel {{
        flex: 1;
        position: relative;
        background-color: #060911;
        background-image: radial-gradient(rgba(255, 255, 255, 0.07) 1px, transparent 1px);
        background-size: 20px 20px;
        overflow: auto;
    }}
    svg.net-svg {{
        width: 100%;
        height: 100%;
        min-width: 960px;
        min-height: 640px;
    }}

    /* Right Inspector Panel */
    .inspector-panel {{
        width: 350px;
        background: #0b1120;
        border-left: 1px solid #1e293b;
        display: flex;
        flex-direction: column;
        padding: 18px;
        overflow-y: auto;
        box-shadow: -4px 0 20px rgba(0, 0, 0, 0.5);
    }}
    .inspector-header {{
        border-bottom: 1px solid #1e293b;
        padding-bottom: 14px;
        margin-bottom: 16px;
    }}
    .node-type-badge {{
        display: inline-block;
        padding: 3px 8px;
        font-size: 10px;
        font-weight: 700;
        border-radius: 4px;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }}
    .badge-transition {{
        background: rgba(14, 165, 233, 0.15);
        color: #38bdf8;
        border: 1px solid #0284c7;
    }}
    .badge-place {{
        background: rgba(168, 85, 247, 0.15);
        color: #c084fc;
        border: 1px solid #9333ea;
    }}
    .node-title {{
        font-size: 15px;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 4px;
    }}
    .node-id {{
        font-size: 11px;
        color: #64748b;
        font-family: monospace;
        margin-bottom: 8px;
    }}
    .liveness-row {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
        margin-top: 6px;
    }}
    .pulse-dot {{
        width: 9px;
        height: 9px;
        border-radius: 50%;
        background: #22c55e;
        box-shadow: 0 0 10px #22c55e;
        animation: pulse 1.8s infinite;
    }}
    .pulse-dot.dot-error {{
        background: #ef4444;
        box-shadow: 0 0 10px #ef4444;
    }}
    .pulse-dot.dot-retry {{
        background: #f59e0b;
        box-shadow: 0 0 10px #f59e0b;
    }}
    .pulse-dot.dot-idle {{
        background: #64748b;
        box-shadow: 0 0 6px #64748b;
    }}
    @keyframes pulse {{
        0% {{ transform: scale(0.95); opacity: 0.8; }}
        50% {{ transform: scale(1.2); opacity: 1; }}
        100% {{ transform: scale(0.95); opacity: 0.8; }}
    }}

    /* Section Cards */
    .section-card {{
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 6px;
        padding: 12px;
        margin-bottom: 14px;
    }}
    .section-title {{
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.5px;
        color: #38bdf8;
        text-transform: uppercase;
        margin-bottom: 10px;
    }}
    .metric-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 12px;
        padding: 4px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }}
    .metric-row:last-child {{
        border-bottom: none;
    }}
    .metric-label {{
        color: #94a3b8;
    }}
    .metric-value {{
        font-weight: 600;
        color: #f1f5f9;
        font-family: monospace;
    }}
    .val-active {{
        color: #4ade80;
    }}
    .val-token {{
        background: #f97316;
        color: #fff;
        padding: 1px 7px;
        border-radius: 10px;
        font-weight: 700;
    }}

    /* SVG Node Styles */
    .subnet-box {{
        fill: rgba(15, 23, 42, 0.45);
        stroke: #1e293b;
        stroke-dasharray: 4 4;
        rx: 8px;
    }}
    .subnet-label {{
        fill: #64748b;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.5px;
        font-family: monospace;
    }}
    .edge-line {{
        stroke: #334155;
        stroke-width: 1.5;
        fill: none;
    }}
    .edge-active {{
        stroke: #0284c7;
        stroke-width: 2;
    }}
    .edge-reconciled {{
        stroke: #10b981;
        stroke-width: 2;
    }}

    /* Places */
    .place-node {{
        cursor: pointer;
        transition: all 0.2s ease;
    }}
    .place-outer {{
        fill: #0b1120;
        stroke: #334155;
        stroke-width: 2;
        transition: all 0.2s ease;
    }}
    .place-node:hover .place-outer {{
        stroke: #38bdf8;
        filter: drop-shadow(0 0 6px rgba(56, 189, 248, 0.6));
    }}
    .place-node.selected .place-outer {{
        stroke: #f59e0b;
        stroke-width: 3;
        filter: drop-shadow(0 0 8px rgba(245, 158, 11, 0.8));
    }}
    .place-has-token .place-outer {{
        stroke: #0284c7;
        fill: #0c4a6e;
    }}
    .place-committed .place-outer {{
        stroke: #10b981;
        fill: #064e3b;
        filter: drop-shadow(0 0 8px rgba(16, 185, 129, 0.5));
    }}
    .place-label {{
        fill: #cbd5e1;
        font-size: 10px;
        text-anchor: middle;
        font-weight: 500;
        pointer-events: none;
    }}

    /* Transitions */
    .trans-node {{
        cursor: pointer;
        transition: all 0.2s ease;
    }}
    .trans-rect {{
        fill: #0f172a;
        stroke: #334155;
        stroke-width: 1.5;
        rx: 6px;
        transition: all 0.2s ease;
    }}
    .trans-node:hover .trans-rect {{
        stroke: #38bdf8;
        filter: drop-shadow(0 0 8px rgba(56, 189, 248, 0.5));
    }}
    .trans-node.selected .trans-rect {{
        stroke: #f59e0b;
        stroke-width: 2.5;
        filter: drop-shadow(0 0 10px rgba(245, 158, 11, 0.9));
    }}
    .trans-fired .trans-rect {{
        stroke: #10b981;
        border: 1px solid #10b981;
    }}
    .trans-blocked .trans-rect {{
        stroke: #ef4444;
    }}
    .trans-retrying .trans-rect {{
        stroke: #f59e0b;
    }}
    .trans-badge-text {{
        font-size: 8px;
        font-weight: 700;
        text-anchor: middle;
        letter-spacing: 0.5px;
        pointer-events: none;
    }}
    .trans-title-text {{
        font-size: 10px;
        font-weight: 600;
        fill: #f8fafc;
        text-anchor: middle;
        pointer-events: none;
    }}
    .trans-sub-text {{
        font-size: 8.5px;
        fill: #64748b;
        text-anchor: middle;
        font-family: monospace;
        pointer-events: none;
    }}
</style>
</head>
<body>

<div class="workbench-container">
    <!-- Top HUD Bar -->
    <div class="hud-bar">
        <div class="hud-spec">CHALLENGE CPN SPEC: N<sub>ch</sub> = (P, T, A, &Sigma;, G, E, M<sub>0</sub>)</div>
        <div class="hud-counts">|P| = 11 &bull; |T| = 7 &bull; |A| = 18 &bull; 1-Safe Challenge Net with Saga Verification</div>
        <div class="hud-marking" id="hudMarking">Marking Vector: M = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]</div>
    </div>

    <!-- Main Workspace -->
    <div class="workspace">
        <!-- SVG Canvas -->
        <div class="canvas-panel">
            <svg class="net-svg" viewBox="0 0 1060 620">
                <defs>
                    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#475569"/>
                    </marker>
                    <marker id="arrow-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#0284c7"/>
                    </marker>
                    <marker id="arrow-green" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#10b981"/>
                    </marker>
                    <marker id="arrow-amber" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#f59e0b"/>
                    </marker>
                    <marker id="arrow-red" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#ef4444"/>
                    </marker>
                </defs>

                <!-- Subnet 1: INGESTION & MARKET -->
                <rect class="subnet-box" x="20" y="20" width="230" height="570" />
                <text class="subnet-label" x="35" y="42">SUBNET: INGESTION & MARKET</text>

                <!-- Subnet 2: STOCHASTIC OPTIMIZATION -->
                <rect class="subnet-box" x="265" y="20" width="245" height="570" />
                <text class="subnet-label" x="280" y="42">SUBNET: STOCHASTIC OPTIMIZATION</text>

                <!-- Subnet 3: MODEL VALIDATION -->
                <rect class="subnet-box" x="525" y="20" width="225" height="570" />
                <text class="subnet-label" x="540" y="42">SUBNET: MODEL VALIDATION</text>

                <!-- Subnet 4: SAGA & VERIFICATION -->
                <rect class="subnet-box" x="765" y="20" width="275" height="570" />
                <text class="subnet-label" x="780" y="42">SUBNET: SAGA & VERIFICATION</text>

                <!-- Connecting Arcs -->
                <!-- Idle -> Ingestion Transitions -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 70 95 L 105 94" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 70 95 C 85 95, 85 254, 105 254" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 70 95 C 85 95, 85 414, 105 414" />

                <!-- Ingestion Transitions -> Ingestion Places -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 170 118 L 170 154" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 170 278 L 170 314" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 170 438 L 170 474" />

                <!-- Ingestion Places (Read-Arcs) -> T_RUN_CHALLENGE_PICKER -->
                <path class="edge-line" marker-end="url(#arrow-blue)" d="M 186 170 C 235 170, 245 290, 290 290" />
                <path class="edge-line" marker-end="url(#arrow-blue)" d="M 186 330 C 235 330, 245 302, 290 302" />
                <path class="edge-line" marker-end="url(#arrow-blue)" d="M 186 490 C 235 490, 245 315, 290 315" />

                <!-- T_RUN_CHALLENGE_PICKER -> P_CHALLENGE_OPTIMIZED -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 435 302 L 459 302" />

                <!-- P_CHALLENGE_OPTIMIZED -> T_VALIDATE_MODEL_SETTINGS -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 491 302 L 555 302" />

                <!-- T_VALIDATE_MODEL_SETTINGS -> P_CHALLENGE_VALIDATED / P_CHALLENGE_ALERTS -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 627 275 L 627 186" />
                <path class="edge-line" stroke-dasharray="3 3" marker-end="url(#arrow-red)" d="M 627 330 L 627 444" />

                <!-- P_CHALLENGE_VALIDATED -> T_SAGA_SUBMIT -->
                <path class="edge-line edge-active" marker-end="url(#arrow-blue)" d="M 643 170 L 795 170" />

                <!-- T_SAGA_SUBMIT -> P_CHALLENGE_VERIFYING -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 920 170 L 959 170" />

                <!-- P_CHALLENGE_VERIFYING -> T_SAGA_VERIFY -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 975 186 L 975 275" />

                <!-- T_SAGA_VERIFY -> P_CHALLENGE_CONFIRMED (Closed-Loop Verified Receipt) -->
                <path class="edge-line edge-reconciled" marker-end="url(#arrow-green)" d="M 975 330 L 975 401" />

                <!-- T_SAGA_VERIFY -> P_CHALLENGE_SUBMITTING (Saga Retry Backoff Loop) -->
                <path class="edge-line" stroke-dasharray="3 3" marker-end="url(#arrow-amber)" d="M 910 302 L 871 302" />
                <path class="edge-line" marker-end="url(#arrow-amber)" d="M 855 286 L 855 195" />

                <!-- T_SAGA_VERIFY -> P_CHALLENGE_COMPENSATION (Retries Exhausted / Dead Letter) -->
                <path class="edge-line" stroke-dasharray="3 3" marker-end="url(#arrow-red)" d="M 1025 330 C 1045 370, 1045 470, 991 525" />

                <!-- ================= PLACES ================= -->
                <!-- P_CHALLENGE_IDLE -->
                <g class="{_p_cls("P_CHALLENGE_IDLE")}" id="node_P_CHALLENGE_IDLE" onclick="selectNode('P_CHALLENGE_IDLE')">
                    <circle class="place-outer" cx="55" cy="95" r="15" />
                    <text class="place-label" x="55" y="125">P_IDLE</text>
                </g>

                <!-- P_CHALLENGE_RULES_READY -->
                <g class="{_p_cls("P_CHALLENGE_RULES_READY")}" id="node_P_CHALLENGE_RULES_READY" onclick="selectNode('P_CHALLENGE_RULES_READY')">
                    <circle class="place-outer" cx="170" cy="170" r="16" />
                    <circle cx="170" cy="170" r="6" fill="#38bdf8" />
                    <text class="place-label" x="170" y="202">P_RULES_READY</text>
                </g>

                <!-- P_CHALLENGE_MARKET_READY -->
                <g class="{_p_cls("P_CHALLENGE_MARKET_READY")}" id="node_P_CHALLENGE_MARKET_READY" onclick="selectNode('P_CHALLENGE_MARKET_READY')">
                    <circle class="place-outer" cx="170" cy="330" r="16" />
                    <circle cx="170" cy="330" r="6" fill="#38bdf8" />
                    <text class="place-label" x="170" y="362">P_MARKET_READY</text>
                </g>

                <!-- P_CHALLENGE_CURRENT_TEAM -->
                <g class="{_p_cls("P_CHALLENGE_CURRENT_TEAM")}" id="node_P_CHALLENGE_CURRENT_TEAM" onclick="selectNode('P_CHALLENGE_CURRENT_TEAM')">
                    <circle class="place-outer" cx="170" cy="490" r="16" />
                    <circle cx="170" cy="490" r="6" fill="#38bdf8" />
                    <text class="place-label" x="170" y="522">P_CURRENT_TEAM</text>
                </g>

                <!-- P_CHALLENGE_OPTIMIZED -->
                <g class="{_p_cls("P_CHALLENGE_OPTIMIZED")}" id="node_P_CHALLENGE_OPTIMIZED" onclick="selectNode('P_CHALLENGE_OPTIMIZED')">
                    <circle class="place-outer" cx="475" cy="302" r="16" />
                    <text class="place-label" x="475" y="334">P_OPTIMIZED</text>
                </g>

                <!-- P_CHALLENGE_VALIDATED -->
                <g class="{_p_cls("P_CHALLENGE_VALIDATED")}" id="node_P_CHALLENGE_VALIDATED" onclick="selectNode('P_CHALLENGE_VALIDATED')">
                    <circle class="place-outer" cx="627" cy="170" r="16" />
                    <text class="place-label" x="627" y="202">P_VALIDATED</text>
                </g>

                <!-- P_CHALLENGE_ALERTS -->
                <g class="{_p_cls("P_CHALLENGE_ALERTS")}" id="node_P_CHALLENGE_ALERTS" onclick="selectNode('P_CHALLENGE_ALERTS')">
                    <circle class="place-outer" cx="627" cy="460" r="16" />
                    <text class="place-label" x="627" y="492">P_ALERTS</text>
                </g>

                <!-- P_CHALLENGE_SUBMITTING -->
                <g class="{_p_cls("P_CHALLENGE_SUBMITTING")}" id="node_P_CHALLENGE_SUBMITTING" onclick="selectNode('P_CHALLENGE_SUBMITTING')">
                    <circle class="place-outer" cx="855" cy="302" r="16" />
                    <text class="place-label" x="855" y="334">P_SUBMITTING</text>
                </g>

                <!-- P_CHALLENGE_VERIFYING -->
                <g class="{_p_cls("P_CHALLENGE_VERIFYING")}" id="node_P_CHALLENGE_VERIFYING" onclick="selectNode('P_CHALLENGE_VERIFYING')">
                    <circle class="place-outer" cx="975" cy="170" r="16" />
                    <text class="place-label" x="975" y="202">P_VERIFYING</text>
                </g>

                <!-- P_CHALLENGE_CONFIRMED -->
                <g class="{_p_cls("P_CHALLENGE_CONFIRMED")}" id="node_P_CHALLENGE_CONFIRMED" onclick="selectNode('P_CHALLENGE_CONFIRMED')">
                    <circle class="place-outer" cx="975" cy="420" r="19" />
                    <circle cx="975" cy="420" r="13" fill="none" stroke="#4ade80" stroke-width="1.5" />
                    <circle cx="975" cy="420" r="6" fill="#4ade80" />
                    <text class="place-label" x="975" y="456" fill="#4ade80" font-weight="700">P_CONFIRMED</text>
                </g>

                <!-- P_CHALLENGE_COMPENSATION -->
                <g class="{_p_cls("P_CHALLENGE_COMPENSATION")}" id="node_P_CHALLENGE_COMPENSATION" onclick="selectNode('P_CHALLENGE_COMPENSATION')">
                    <circle class="place-outer" cx="975" cy="525" r="16" />
                    <text class="place-label" x="975" y="557">P_COMPENSATION</text>
                </g>

                <!-- ================= TRANSITIONS ================= -->
                <!-- T_FETCH_CHALLENGE_RULES -->
                <g class="{_t_cls("T_FETCH_CHALLENGE_RULES")}" id="node_T_FETCH_CHALLENGE_RULES" onclick="selectNode('T_FETCH_CHALLENGE_RULES')">
                    <rect class="trans-rect" x="105" y="70" width="130" height="48" />
                    <text class="trans-badge-text" x="170" y="84" fill="{c_rules}">{b_rules}</text>
                    <text class="trans-title-text" x="170" y="99">Extract Rules</text>
                    <text class="trans-sub-text" x="170" y="111">T_FETCH_CHALLENGE_RULES</text>
                </g>

                <!-- T_INGEST_CHALLENGE_MARKET -->
                <g class="{_t_cls("T_INGEST_CHALLENGE_MARKET")}" id="node_T_INGEST_CHALLENGE_MARKET" onclick="selectNode('T_INGEST_CHALLENGE_MARKET')">
                    <rect class="trans-rect" x="105" y="230" width="130" height="48" />
                    <text class="trans-badge-text" x="170" y="244" fill="{c_market}">{b_market}</text>
                    <text class="trans-title-text" x="170" y="259">Ingest Market</text>
                    <text class="trans-sub-text" x="170" y="271">T_INGEST_CHALLENGE_MARKET</text>
                </g>

                <!-- T_FETCH_CURRENT_TEAM -->
                <g class="{_t_cls("T_FETCH_CURRENT_TEAM")}" id="node_T_FETCH_CURRENT_TEAM" onclick="selectNode('T_FETCH_CURRENT_TEAM')">
                    <rect class="trans-rect" x="105" y="390" width="130" height="48" />
                    <text class="trans-badge-text" x="170" y="404" fill="{c_team}">{b_team}</text>
                    <text class="trans-title-text" x="170" y="419">Ingest Lineup</text>
                    <text class="trans-sub-text" x="170" y="431">T_FETCH_CURRENT_TEAM</text>
                </g>

                <!-- T_RUN_CHALLENGE_PICKER -->
                <g class="{_t_cls("T_RUN_CHALLENGE_PICKER")}" id="node_T_RUN_CHALLENGE_PICKER" onclick="selectNode('T_RUN_CHALLENGE_PICKER')">
                    <rect class="trans-rect" x="290" y="275" width="145" height="55" />
                    <text class="trans-badge-text" x="362" y="291" fill="{c_solve}">{b_solve}</text>
                    <text class="trans-title-text" x="362" y="307">Two-Stage Picker</text>
                    <text class="trans-sub-text" x="362" y="321">T_RUN_CHALLENGE_PICKER</text>
                </g>

                <!-- T_VALIDATE_MODEL_SETTINGS -->
                <g class="{_t_cls("T_VALIDATE_MODEL_SETTINGS")}" id="node_T_VALIDATE_MODEL_SETTINGS" onclick="selectNode('T_VALIDATE_MODEL_SETTINGS')">
                    <rect class="trans-rect" x="555" y="275" width="145" height="55" />
                    <text class="trans-badge-text" x="627" y="291" fill="{c_val}">{b_val}</text>
                    <text class="trans-title-text" x="627" y="307">Model Validator</text>
                    <text class="trans-sub-text" x="627" y="321">T_VALIDATE_MODEL_SETTINGS</text>
                </g>

                <!-- T_SAGA_SUBMIT -->
                <g class="{_t_cls("T_SAGA_SUBMIT")}" id="node_T_SAGA_SUBMIT" onclick="selectNode('T_SAGA_SUBMIT')">
                    <rect class="trans-rect" x="795" y="145" width="125" height="50" />
                    <text class="trans-badge-text" x="857" y="160" fill="{c_sub}">{b_sub}</text>
                    <text class="trans-title-text" x="857" y="174">Saga Submit</text>
                    <text class="trans-sub-text" x="857" y="186">T_SAGA_SUBMIT</text>
                </g>

                <!-- T_SAGA_VERIFY -->
                <g class="{_t_cls("T_SAGA_VERIFY")}" id="node_T_SAGA_VERIFY" onclick="selectNode('T_SAGA_VERIFY')">
                    <rect class="trans-rect" x="910" y="275" width="130" height="55" stroke="#10b981" stroke-width="2" />
                    <text class="trans-badge-text" x="975" y="291" fill="{c_ver}">{b_ver}</text>
                    <text class="trans-title-text" x="975" y="307">Saga Verify</text>
                    <text class="trans-sub-text" x="975" y="321">T_SAGA_VERIFY</text>
                </g>
            </svg>
        </div>

        <!-- Right Node Inspector Panel -->
        <div class="inspector-panel" id="inspectorPanel">
            <div class="inspector-header">
                <span class="node-type-badge badge-place" id="inspBadge">PLACE / VAULT</span>
                <div class="node-title" id="inspTitle">9. Terminal Confirmed Receipt Vault</div>
                <div class="node-id" id="inspId">P_CHALLENGE_CONFIRMED</div>
                <div class="liveness-row">
                    <div class="pulse-dot" id="inspPulse"></div>
                    <span id="inspLiveness" style="color:#4ade80; font-weight:600;">ACTIVE &bull; CLOSED-LOOP VERIFIED</span>
                </div>
            </div>

            <!-- Card 1: Role Description -->
            <div class="section-card">
                <div class="section-title">Mnemonic Role & Semantic Function</div>
                <p id="inspRole" style="font-size:12px; color:#cbd5e1; line-height:1.5;">
                    Terminal commitment place holding confirmed audit receipts and transaction IDs.
                </p>
            </div>

            <!-- Card 2: Metrics / Ledger -->
            <div class="section-card">
                <div class="section-title" id="inspMetricsTitle">Token Ledger State</div>
                <div id="inspMetricsBody">
                    <div class="metric-row">
                        <span class="metric-label">Current Marking:</span>
                        <span class="val-token">1</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Token Color (&Sigma;):</span>
                        <span class="metric-value">Color_ChallengeReceipt</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Capacity Limit:</span>
                        <span class="metric-value">1-Safe Bounded WF-Net</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Audit Verification:</span>
                        <span class="metric-value val-active">SAGA READ-AFTER-WRITE CONFIRMED</span>
                    </div>
                </div>
            </div>

            <!-- Card 3: Boundary Connections -->
            <div class="section-card">
                <div class="section-title">CPN Bipartite Invariant Relations</div>
                <div class="metric-row">
                    <span class="metric-label" id="inspRel1Label">Inbound Arcs:</span>
                    <span class="metric-value" id="inspRel1Val">T_SAGA_VERIFY</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label" id="inspRel2Label">Outbound Arcs:</span>
                    <span class="metric-value" id="inspRel2Val">None (Terminal Sink)</span>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
    const snapshotData = {snapshot_json};
    let activeNodeId = "P_CHALLENGE_CONFIRMED";

    // Update HUD Marking Vector
    if (snapshotData && snapshotData.marking_vector) {{
        document.getElementById("hudMarking").innerText = 
            "Marking Vector: M = [" + snapshotData.marking_vector.join(", ") + "]";
    }}

    function selectNode(nodeId) {{
        activeNodeId = nodeId;
        // Update SVG Selection Rings
        document.querySelectorAll(".place-node, .trans-node").forEach(el => el.classList.remove("selected"));
        const target = document.getElementById("node_" + nodeId);
        if (target) {{
            target.classList.add("selected");
        }}

        // Check if transition or place
        const tSpecs = snapshotData.transition_specs || {{}};
        const pSpecs = snapshotData.place_specs || {{}};
        const tStats = snapshotData.transition_stats || {{}};
        const pCounts = snapshotData.place_counts || {{}};

        if (tSpecs[nodeId]) {{
            renderTransitionInspector(nodeId, tSpecs[nodeId], tStats[nodeId] || {{}});
        }} else if (pSpecs[nodeId]) {{
            renderPlaceInspector(nodeId, pSpecs[nodeId], pCounts[nodeId] || 0);
        }}
    }}

    function renderTransitionInspector(id, spec, stats) {{
        document.getElementById("inspBadge").className = "node-type-badge badge-transition";
        document.getElementById("inspBadge").innerText = "TRANSITION / ACTOR";
        document.getElementById("inspTitle").innerText = spec.display_title || id;
        document.getElementById("inspId").innerText = id;

        const isAlive = stats.status === "ALIVE_FIRED";
        const isBlocked = stats.status === "BLOCKED";
        const isRetrying = stats.status === "RETRYING";
        const pulse = document.getElementById("inspPulse");
        const liveness = document.getElementById("inspLiveness");

        if (isAlive) {{
            pulse.className = "pulse-dot";
            liveness.innerHTML = "ALIVE &bull; VERIFIED HEALTHY";
            liveness.style.color = "#4ade80";
        }} else if (isBlocked) {{
            pulse.className = "pulse-dot dot-error";
            liveness.innerHTML = "BLOCKED &bull; CONSTRAINT ERROR";
            liveness.style.color = "#f87171";
        }} else if (isRetrying) {{
            pulse.className = "pulse-dot dot-retry";
            liveness.innerHTML = "RETRYING &bull; SAGA BACKOFF LOOP";
            liveness.style.color = "#fbbf24";
        }} else {{
            pulse.className = "pulse-dot dot-idle";
            liveness.innerHTML = "STANDBY &bull; READY TO FIRE";
            liveness.style.color = "#94a3b8";
        }}

        document.getElementById("inspRole").innerText = spec.mnemonic_role || "Executes discrete Challenge CPN transition coroutine.";
        document.getElementById("inspMetricsTitle").innerText = "Transition Execution Metrics";

        const latency = stats.mean_latency_ms ? stats.mean_latency_ms + " ms" : "0.0 ms";
        const fireCount = stats.fire_count || (isAlive ? 1 : 0);

        document.getElementById("inspMetricsBody").innerHTML = 
            '<div class="metric-row">' +
                '<span class="metric-label">Status:</span>' +
                '<span class="metric-value ' + (isAlive ? 'val-active' : (isBlocked ? 'val-token' : '')) + '">' + (stats.status || 'STANDBY') + '</span>' +
            '</div>' +
            '<div class="metric-row">' +
                '<span class="metric-label">Execution Count:</span>' +
                '<span class="metric-value">' + fireCount + '</span>' +
            '</div>' +
            '<div class="metric-row">' +
                '<span class="metric-label">Mean Latency:</span>' +
                '<span class="metric-value">' + latency + '</span>' +
            '</div>' +
            '<div class="metric-row">' +
                '<span class="metric-label">Guard Formula:</span>' +
                '<span class="metric-value" style="font-size:10px; color:#38bdf8;">' + (spec.guard_formula || 'TRUE') + '</span>' +
            '</div>' +
            '<div class="metric-row">' +
                '<span class="metric-label">Retry Policy:</span>' +
                '<span class="metric-value" style="font-size:11px;">' + (spec.retry_policy || 'None') + '</span>' +
            '</div>';

        document.getElementById("inspRel1Label").innerText = "Consumed Places:";
        document.getElementById("inspRel1Val").innerText = (spec.consumed_places || []).join(", ") || "None";
        document.getElementById("inspRel2Label").innerText = "Emitted Places:";
        document.getElementById("inspRel2Val").innerText = (spec.emitted_places || []).join(", ") || "None";
    }}

    function renderPlaceInspector(id, spec, count) {{
        document.getElementById("inspBadge").className = "node-type-badge badge-place";
        document.getElementById("inspBadge").innerText = "PLACE / VAULT";
        document.getElementById("inspTitle").innerText = spec.display_title || id;
        document.getElementById("inspId").innerText = id;

        const pulse = document.getElementById("inspPulse");
        const liveness = document.getElementById("inspLiveness");

        const hasTokens = (typeof count === "boolean" && count) || (typeof count === "number" && count > 0) || spec.is_read_arc;

        if (hasTokens) {{
            pulse.className = "pulse-dot";
            liveness.innerHTML = "ACTIVE &bull; TOKEN AVAILABLE";
            liveness.style.color = "#4ade80";
        }} else {{
            pulse.className = "pulse-dot dot-idle";
            liveness.innerHTML = "EMPTY &bull; 0 TOKENS";
            liveness.style.color = "#94a3b8";
        }}

        document.getElementById("inspRole").innerText = spec.role || "Petri Net state vault.";
        document.getElementById("inspMetricsTitle").innerText = "Token Ledger State";

        const countDisplay = typeof count === "boolean" ? (count ? "1 (Read-Arc)" : "0") : count;

        document.getElementById("inspMetricsBody").innerHTML = 
            '<div class="metric-row">' +
                '<span class="metric-label">Current Marking M(p):</span>' +
                '<span class="' + (hasTokens ? 'val-token' : 'metric-value') + '">' + countDisplay + '</span>' +
            '</div>' +
            '<div class="metric-row">' +
                '<span class="metric-label">Token Color Set (&Sigma;):</span>' +
                '<span class="metric-value" style="color:#c084fc;">' + (spec.color || 'Color_Token') + '</span>' +
            '</div>' +
            '<div class="metric-row">' +
                '<span class="metric-label">Capacity Limit:</span>' +
                '<span class="metric-value">' + (spec.capacity || '1 (Bounded)') + '</span>' +
            '</div>' +
            '<div class="metric-row">' +
                '<span class="metric-label">Storage Topology:</span>' +
                '<span class="metric-value">' + (spec.is_read_arc ? 'Continuous Read-Arc (Non-Destructive)' : 'Async FIFO Place Queue') + '</span>' +
            '</div>';

        document.getElementById("inspRel1Label").innerText = "Subnet:";
        const sub = id.includes("RULES") || id.includes("MARKET") || id.includes("TEAM") || id.includes("IDLE") ? "Ingestion & Market" : (id.includes("OPTIMIZED") ? "Optimization" : (id.includes("VALIDATED") || id.includes("ALERTS") ? "Model Validation" : "Saga Verification"));
        document.getElementById("inspRel1Val").innerText = sub;
        document.getElementById("inspRel2Label").innerText = "Read Access:";
        document.getElementById("inspRel2Val").innerText = spec.is_read_arc ? "Non-Destructive Peek / Read" : "Destructive Queue Get";
    }}

    // Default selection
    if (snapshotData && snapshotData.receipt_id) {{
        selectNode("P_CHALLENGE_CONFIRMED");
    }} else if (snapshotData && snapshotData.last_plan_id) {{
        selectNode("P_CHALLENGE_OPTIMIZED");
    }} else {{
        selectNode("T_RUN_CHALLENGE_PICKER");
    }}
</script>

</body>
</html>
"""
    return html


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
    # 2. Cybernetic Mission-Control Workbench (Interactive HTML/SVG + Inspector)
    # ------------------------------------------------------------------
    st.markdown("#### 🔬 CPN Topology & Interactive Transition/Place Inspector")
    st.caption("Click any transition box or place vault to inspect real-time metrics, liveness, and token ledgers.")

    last_receipt = st.session_state.get("ch_cpn_last_receipt")
    last_engine: Optional[ChallengeCPNEngine] = st.session_state.get("ch_cpn_last_engine")

    snapshot = {}
    if last_receipt and isinstance(last_receipt, dict) and "snapshot" in last_receipt:
        snapshot = last_receipt["snapshot"]
    elif last_engine:
        snapshot = last_engine.get_telemetry_snapshot()
    else:
        snapshot = _get_default_challenge_snapshot()

    workbench_html = _build_challenge_workbench_html(snapshot)
    components.html(workbench_html, height=730, scrolling=False)

    with st.expander("🗺️ Formal Petri Net Bipartite Architecture Graph (van der Aalst)", expanded=False):
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
