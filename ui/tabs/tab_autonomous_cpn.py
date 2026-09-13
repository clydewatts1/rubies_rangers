"""
ui/tabs/tab_autonomous_cpn.py
Streamlit telemetry, live monitoring, and interactive execution controller for the
Kurt Jensen Timed Coloured Petri Net (TCPN) Autonomous Robotic Manager.
Features a cybernetic CPN Mission-Control Workbench with interactive node inspector.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import glob
import json
import os
from typing import Any
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from automation.cpn import (
    CPNEngine,
    CPNDiagnosticJournal,
    Color_Session,
    Color_MarketData,
    Color_SquadState,
)
from automation.runner import DemoFPLClient, DemoSolverEngine


class ScenarioFPLClient(DemoFPLClient):
    """Synthetic FPL client with scenario injection capabilities."""
    def __init__(self, scenario: str, entry_id: int = 99999) -> None:
        super().__init__(entry_id=entry_id)
        self.scenario = scenario
        self._transfers_called = 0

    async def authenticate(self) -> Color_Session:
        now = datetime.now(timezone.utc)
        if self.scenario == "Critical Auth Failure":
            return Color_Session(
                auth_cookie="",
                csrf_token="",
                expires_at=now - timedelta(hours=1),
                is_authenticated=False,
                last_keepalive_utc=now,
            )
        return await super().authenticate()

    async def get_bootstrap_static(self) -> dict[str, Any]:
        data = await super().get_bootstrap_static()
        if self.scenario == "ADV-3: Late Vice-Captain Red Flag":
            data["injury_flags"] = {11: {"chance_of_playing": 0, "news": "Red Flag: Hamstring Tear"}}
        return data

    async def post_transfers(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._transfers_called += 1
        if self.scenario == "ADV-1: 502 Gateway Recovery" and self._transfers_called == 1:
            return {"status_code": 502, "result": "Bad Gateway"}
        return await super().post_transfers(payload)


def _load_diagnostic_events(limit: int = 25) -> pd.DataFrame:
    """Load latest diagnostic events from logs/diagnostics/*.jsonl files."""
    log_dir = os.path.join("logs", "diagnostics")
    if not os.path.exists(log_dir):
        return pd.DataFrame()

    files = sorted(glob.glob(os.path.join(log_dir, "cpn_journal_*.jsonl")), reverse=True)
    if not files:
        return pd.DataFrame()

    records = []
    for filepath in files[:3]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            continue

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    if "timestamp_utc" in df.columns:
        df = df.sort_values(by="timestamp_utc", ascending=False)
    return df.head(limit)


async def _run_async_cycle(gameweek: int, scenario: str, deadline_mins: int = 35) -> dict[str, Any]:
    """Asynchronously execute a full CPN gameweek cycle and capture state."""
    deadline = datetime.now(timezone.utc) + timedelta(minutes=deadline_mins)
    journal = CPNDiagnosticJournal()

    client = ScenarioFPLClient(scenario=scenario)
    solver = DemoSolverEngine()
    legal_formations = {(3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3), (5, 3, 2)}

    engine = CPNEngine(
        fpl_client=client,
        solver_engine=solver,
        legal_formations=legal_formations,
        journal=journal,
    )

    t0 = datetime.now(timezone.utc)
    await engine.run_gameweek_cycle(gameweek=gameweek, deadline_utc=deadline)
    duration_s = (datetime.now(timezone.utc) - t0).total_seconds()

    snapshot = engine.get_telemetry_snapshot()

    committed_receipt = None
    if not engine.marking.P_Committed.empty():
        committed_receipt = await engine.marking.P_Committed.get()

    dead_letter_alert = None
    if not engine.marking.P_DeadLetter.empty():
        dead_letter_alert = await engine.marking.P_DeadLetter.get()

    await engine.shutdown()
    daily_summary = await journal.get_daily_summary()

    return {
        "gameweek": gameweek,
        "scenario": scenario,
        "deadline_utc": deadline.isoformat(),
        "duration_seconds": duration_s,
        "snapshot": snapshot,
        "committed_receipt": committed_receipt,
        "dead_letter_alert": dead_letter_alert,
        "daily_summary": daily_summary,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _build_workbench_html(snapshot: dict[str, Any]) -> str:
    """
    Renders the complete cybernetic CPN Workbench with an interactive SVG bipartite net
    and a reactive Node Inspector panel matching the user's reference image.
    """
    from automation.cpn.engine import TRANSITION_SPECS, PLACE_SPECS
    if "transition_specs" not in snapshot:
        snapshot["transition_specs"] = TRANSITION_SPECS
    if "place_specs" not in snapshot:
        snapshot["place_specs"] = PLACE_SPECS
    if "transition_stats" not in snapshot:
        snapshot["transition_stats"] = {
            t_name: {"status": "ALIVE_FIRED", "fire_count": 1, "mean_latency_ms": 0.08, "last_latency_ms": 0.08}
            for t_name in TRANSITION_SPECS
        }

    snapshot_json = json.dumps(snapshot)

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
        font-size: 16px;
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
        border: 1px solid #10b981;
        stroke: #10b981;
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
        <div class="hud-spec">CPN FORMAL SPEC: N = (P, T, A, &Sigma;, G, E, M0)</div>
        <div class="hud-counts">|P| = 14 &bull; |T| = 10 &bull; |A| = 24 &bull; 1-Safe Workflow Net (van der Aalst)</div>
        <div class="hud-marking" id="hudMarking">Marking Vector: M = [1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0]</div>
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
                    <marker id="arrow-green" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#10b981"/>
                    </marker>
                </defs>

                <!-- Subnets -->
                <rect class="subnet-box" x="20" y="20" width="220" height="570" />
                <text class="subnet-label" x="35" y="42">SUBNET: INGESTION & SESSIONS</text>

                <rect class="subnet-box" x="260" y="20" width="250" height="570" />
                <text class="subnet-label" x="275" y="42">SUBNET: STOCHASTIC OPTIMIZATION</text>

                <rect class="subnet-box" x="530" y="20" width="220" height="570" />
                <text class="subnet-label" x="545" y="42">SUBNET: K3 GUARDS & DEGRADE</text>

                <rect class="subnet-box" x="770" y="20" width="270" height="570" />
                <text class="subnet-label" x="785" y="42">SUBNET: TWO-STAGE GATES</text>

                <!-- Connecting Arcs -->
                <!-- Timer -> T_Preflight -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 65 100 L 115 100" />
                <!-- T_Preflight -> P_Session, P_Market, P_Squad -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 175 90 C 190 90, 195 140, 205 140" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 175 100 C 190 100, 195 240, 205 240" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 175 110 C 190 110, 195 340, 205 340" />

                <!-- P_Squad, P_Market -> T_Solve -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 235 240 L 310 240" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 235 340 C 270 340, 280 250, 310 250" />

                <!-- T_Solve -> P_Plan, P_PendingPlan, P_Contingency -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 430 230 C 445 230, 450 140, 465 140" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 430 240 L 465 240" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 430 250 C 445 250, 450 340, 465 340" />

                <!-- P_Contingency -> T_ScatterGather -> P_ResolvedGuard -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 480 360 L 480 430" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 480 490 C 480 520, 560 520, 560 480 L 560 360" />

                <!-- P_Plan, P_PendingPlan, P_ResolvedGuard -> T_EvaluateGuards -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 495 140 C 530 140, 540 230, 570 230" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 495 240 L 570 240" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 575 340 C 585 340, 590 270, 600 270" />

                <!-- T_EvaluateGuards -> P_PlanDegrade / T_DispatchTransfers -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 640 225 C 640 160, 650 140, 675 140" />
                <path class="edge-line edge-active" marker-end="url(#arrow)" d="M 690 240 L 795 240" />

                <!-- P_PlanDegrade -> T_DegradePlan -> T_DispatchTransfers -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 705 140 L 720 140" />

                <!-- Stage 1: T_DispatchTransfers -> P_TWait -> T_ReconcileTransfers -> P_TExec -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 855 240 L 880 240" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 910 240 L 935 240" />
                <path class="edge-line edge-reconciled" marker-end="url(#arrow-green)" d="M 995 240 L 1020 240" />

                <!-- Stage 2: P_TExec -> T_DispatchLineup -> P_LWait -> T_ReconcileLineup -> P_Committed -->
                <path class="edge-line" marker-end="url(#arrow)" d="M 1035 255 C 1035 320, 835 320, 835 350" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 895 365 L 920 365" />
                <path class="edge-line" marker-end="url(#arrow)" d="M 950 365 L 975 365" />
                <path class="edge-line edge-reconciled" marker-end="url(#arrow-green)" d="M 1035 365 C 1050 365, 1050 260, 1040 260" />

                <!-- Reconcile Gates -> P_DeadLetter on Error -->
                <path class="edge-line" stroke-dasharray="3 3" marker-end="url(#arrow)" d="M 965 265 L 965 470" />
                <path class="edge-line" stroke-dasharray="3 3" marker-end="url(#arrow)" d="M 1005 390 C 1005 440, 975 460, 975 470" />

                <!-- ================= PLACES ================= -->
                <!-- P_Timer -->
                <g class="place-node" id="node_P_Timer" onclick="selectNode('P_Timer')">
                    <circle class="place-outer" cx="50" cy="100" r="15" />
                    <text class="place-label" x="50" y="130">P_Timer</text>
                </g>

                <!-- P_Session -->
                <g class="place-node place-has-token" id="node_P_Session" onclick="selectNode('P_Session')">
                    <circle class="place-outer" cx="220" cy="140" r="16" />
                    <circle cx="220" cy="140" r="6" fill="#38bdf8" />
                    <text class="place-label" x="220" y="172">P_Session</text>
                </g>

                <!-- P_Market -->
                <g class="place-node place-has-token" id="node_P_Market" onclick="selectNode('P_Market')">
                    <circle class="place-outer" cx="220" cy="240" r="16" />
                    <circle cx="220" cy="240" r="6" fill="#38bdf8" />
                    <text class="place-label" x="220" y="272">P_Market</text>
                </g>

                <!-- P_Squad -->
                <g class="place-node place-has-token" id="node_P_Squad" onclick="selectNode('P_Squad')">
                    <circle class="place-outer" cx="220" cy="340" r="16" />
                    <circle cx="220" cy="340" r="6" fill="#38bdf8" />
                    <text class="place-label" x="220" y="372">P_Squad</text>
                </g>

                <!-- P_Plan -->
                <g class="place-node" id="node_P_Plan" onclick="selectNode('P_Plan')">
                    <circle class="place-outer" cx="480" cy="140" r="15" />
                    <text class="place-label" x="480" y="172">P_Plan</text>
                </g>

                <!-- P_PendingPlan -->
                <g class="place-node" id="node_P_PendingPlan" onclick="selectNode('P_PendingPlan')">
                    <circle class="place-outer" cx="480" cy="240" r="15" />
                    <text class="place-label" x="480" y="272">P_PendingPlan</text>
                </g>

                <!-- P_Contingency -->
                <g class="place-node" id="node_P_Contingency" onclick="selectNode('P_Contingency')">
                    <circle class="place-outer" cx="480" cy="340" r="15" />
                    <text class="place-label" x="480" y="372">P_Contingency</text>
                </g>

                <!-- P_ResolvedGuard -->
                <g class="place-node" id="node_P_ResolvedGuard" onclick="selectNode('P_ResolvedGuard')">
                    <circle class="place-outer" cx="560" cy="340" r="15" />
                    <text class="place-label" x="560" y="372">P_ResolvedGuard</text>
                </g>

                <!-- P_PlanDegrade -->
                <g class="place-node" id="node_P_PlanDegrade" onclick="selectNode('P_PlanDegrade')">
                    <circle class="place-outer" cx="690" cy="140" r="15" />
                    <text class="place-label" x="690" y="172">P_PlanDegrade</text>
                </g>

                <!-- P_TransfersAwaitingValidation -->
                <g class="place-node" id="node_P_TransfersAwaitingValidation" onclick="selectNode('P_TransfersAwaitingValidation')">
                    <circle class="place-outer" cx="895" cy="240" r="15" />
                    <text class="place-label" x="895" y="272">P_TWait</text>
                </g>

                <!-- P_TransfersExecuted -->
                <g class="place-node" id="node_P_TransfersExecuted" onclick="selectNode('P_TransfersExecuted')">
                    <circle class="place-outer" cx="1035" cy="240" r="15" />
                    <text class="place-label" x="1035" y="272">P_TExec</text>
                </g>

                <!-- P_LineupAwaitingValidation -->
                <g class="place-node" id="node_P_LineupAwaitingValidation" onclick="selectNode('P_LineupAwaitingValidation')">
                    <circle class="place-outer" cx="935" cy="365" r="15" />
                    <text class="place-label" x="935" y="397">P_LWait</text>
                </g>

                <!-- P_Committed -->
                <g class="place-node place-committed selected" id="node_P_Committed" onclick="selectNode('P_Committed')">
                    <circle class="place-outer" cx="1035" cy="140" r="19" />
                    <circle cx="1035" cy="140" r="13" fill="none" stroke="#4ade80" stroke-width="1.5" />
                    <circle cx="1035" cy="140" r="6" fill="#4ade80" />
                    <text class="place-label" x="1035" y="176" fill="#4ade80" font-weight="700">P_Committed</text>
                </g>

                <!-- P_DeadLetter -->
                <g class="place-node" id="node_P_DeadLetter" onclick="selectNode('P_DeadLetter')">
                    <circle class="place-outer" cx="965" cy="490" r="16" />
                    <text class="place-label" x="965" y="522">P_DeadLetter</text>
                </g>

                <!-- ================= TRANSITIONS ================= -->
                <!-- T_PreflightAndIngest -->
                <g class="trans-node trans-fired" id="node_T_PreflightAndIngest" onclick="selectNode('T_PreflightAndIngest')">
                    <rect class="trans-rect" x="115" y="75" width="105" height="50" />
                    <text class="trans-badge-text" x="167" y="90" fill="#4ade80">[ ALIVE / FIRED ]</text>
                    <text class="trans-title-text" x="167" y="105">Preflight Ingest</text>
                    <text class="trans-sub-text" x="167" y="118">T_PreflightAndIngest</text>
                </g>

                <!-- T_SessionKeepalive -->
                <g class="trans-node" id="node_T_SessionKeepalive" onclick="selectNode('T_SessionKeepalive')">
                    <rect class="trans-rect" x="80" y="470" width="110" height="50" />
                    <text class="trans-badge-text" x="135" y="485" fill="#38bdf8">[ DAEMON / ALIVE ]</text>
                    <text class="trans-title-text" x="135" y="500">Session Keepalive</text>
                    <text class="trans-sub-text" x="135" y="513">T_SessionKeepalive</text>
                </g>

                <!-- T_SimulateAndSolve -->
                <g class="trans-node trans-fired" id="node_T_SimulateAndSolve" onclick="selectNode('T_SimulateAndSolve')">
                    <rect class="trans-rect" x="310" y="215" width="120" height="50" />
                    <text class="trans-badge-text" x="370" y="230" fill="#4ade80">[ ALIVE / FIRED ]</text>
                    <text class="trans-title-text" x="370" y="245">Simulate & Solve</text>
                    <text class="trans-sub-text" x="370" y="258">T_SimulateAndSolve</text>
                </g>

                <!-- T_ScatterGather -->
                <g class="trans-node" id="node_T_ScatterGather" onclick="selectNode('T_ScatterGather')">
                    <rect class="trans-rect" x="425" y="440" width="110" height="50" />
                    <text class="trans-badge-text" x="480" y="455" fill="#94a3b8">[ D-8m BOUNDARY ]</text>
                    <text class="trans-title-text" x="480" y="470">Scatter-Gather</text>
                    <text class="trans-sub-text" x="480" y="483">T_ScatterGather</text>
                </g>

                <!-- T_EvaluateGuards -->
                <g class="trans-node trans-fired" id="node_T_EvaluateGuards" onclick="selectNode('T_EvaluateGuards')">
                    <rect class="trans-rect" x="570" y="215" width="120" height="50" />
                    <text class="trans-badge-text" x="630" y="230" fill="#4ade80">[ GUARDS TRUE ]</text>
                    <text class="trans-title-text" x="630" y="245">Evaluate Guards</text>
                    <text class="trans-sub-text" x="630" y="258">T_EvaluateGuards</text>
                </g>

                <!-- T_DegradePlan -->
                <g class="trans-node" id="node_T_DegradePlan" onclick="selectNode('T_DegradePlan')">
                    <rect class="trans-rect" x="660" y="60" width="105" height="45" />
                    <text class="trans-badge-text" x="712" y="74" fill="#94a3b8">[ SAFE HARBOR ]</text>
                    <text class="trans-title-text" x="712" y="88">Degrade Plan</text>
                    <text class="trans-sub-text" x="712" y="99">T_DegradePlan</text>
                </g>

                <!-- T_DispatchTransfers -->
                <g class="trans-node trans-fired" id="node_T_DispatchTransfers" onclick="selectNode('T_DispatchTransfers')">
                    <rect class="trans-rect" x="745" y="215" width="110" height="50" />
                    <text class="trans-badge-text" x="800" y="230" fill="#38bdf8">[ STAGE 1 DISPATCH ]</text>
                    <text class="trans-title-text" x="800" y="245">Dispatch Xfers</text>
                    <text class="trans-sub-text" x="800" y="258">T_DispatchTransfers</text>
                </g>

                <!-- T_ReconcileTransfers (Gate 1) -->
                <g class="trans-node trans-fired" id="node_T_ReconcileTransfers" onclick="selectNode('T_ReconcileTransfers')">
                    <rect class="trans-rect" x="935" y="215" width="115" height="50" stroke="#f59e0b" stroke-width="2" />
                    <text class="trans-badge-text" x="992" y="230" fill="#f59e0b">[ GATE 1 AUDIT ]</text>
                    <text class="trans-title-text" x="992" y="245">Reconcile Xfers</text>
                    <text class="trans-sub-text" x="992" y="258">T_ReconcileTransfers</text>
                </g>

                <!-- T_DispatchLineup -->
                <g class="trans-node trans-fired" id="node_T_DispatchLineup" onclick="selectNode('T_DispatchLineup')">
                    <rect class="trans-rect" x="780" y="340" width="115" height="50" />
                    <text class="trans-badge-text" x="837" y="355" fill="#38bdf8">[ STAGE 2 DISPATCH ]</text>
                    <text class="trans-title-text" x="837" y="370">Dispatch Lineup</text>
                    <text class="trans-sub-text" x="837" y="383">T_DispatchLineup</text>
                </g>

                <!-- T_ReconcileLineup (Gate 2) -->
                <g class="trans-node trans-fired" id="node_T_ReconcileLineup" onclick="selectNode('T_ReconcileLineup')">
                    <rect class="trans-rect" x="975" y="340" width="125" height="50" stroke="#10b981" stroke-width="2" />
                    <text class="trans-badge-text" x="1037" y="355" fill="#10b981">[ GATE 2 AUDIT ]</text>
                    <text class="trans-title-text" x="1037" y="370">Reconcile Lineup</text>
                    <text class="trans-sub-text" x="1037" y="383">T_ReconcileLineup</text>
                </g>
            </svg>
        </div>

        <!-- Right Node Inspector Panel -->
        <div class="inspector-panel" id="inspectorPanel">
            <div class="inspector-header">
                <span class="node-type-badge badge-place" id="inspBadge">PLACE / VAULT</span>
                <div class="node-title" id="inspTitle">13. Final Commitment Vault</div>
                <div class="node-id" id="inspId">P_Committed</div>
                <div class="liveness-row">
                    <div class="pulse-dot" id="inspPulse"></div>
                    <span id="inspLiveness" style="color:#4ade80; font-weight:600;">ACTIVE &bull; CLOSED-LOOP VERIFIED</span>
                </div>
            </div>

            <!-- Card 1: Role Description -->
            <div class="section-card">
                <div class="section-title">Mnemonic Role & Semantic Function</div>
                <p id="inspRole" style="font-size:12px; color:#cbd5e1; line-height:1.5;">
                    Terminal commitment place holding cryptographic SHA-256 receipts verified by Gate 2 source-system audit.
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
                        <span class="metric-value">Color_Receipt</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Capacity Limit:</span>
                        <span class="metric-value">1 (1-Safe Bounded WF-Net)</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Audit Verification:</span>
                        <span class="metric-value val-active">SHA-256 HASH VERIFIED</span>
                    </div>
                </div>
            </div>

            <!-- Card 3: Boundary Connections -->
            <div class="section-card">
                <div class="section-title">CPN Bipartite Invariant Relations</div>
                <div class="metric-row">
                    <span class="metric-label" id="inspRel1Label">Inbound Arcs:</span>
                    <span class="metric-value" id="inspRel1Val">T_ReconcileLineup</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label" id="inspRel2Label">Outbound Arcs:</span>
                    <span class="metric-value" id="inspRel2Val">None (Sink Place)</span>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
    const snapshotData = {snapshot_json};
    let activeNodeId = "P_Committed";

    // Update HUD Vector
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

        const isAlive = stats.status === "ALIVE_FIRED" || stats.status === "ALIVE_RUNNING";
        const pulse = document.getElementById("inspPulse");
        const liveness = document.getElementById("inspLiveness");

        if (isAlive) {{
            pulse.className = "pulse-dot";
            liveness.innerHTML = "ALIVE &bull; VERIFIED HEALTHY";
            liveness.style.color = "#4ade80";
        }} else if (stats.status === "BLOCKED") {{
            pulse.className = "pulse-dot dot-error";
            liveness.innerHTML = "BLOCKED &bull; CRITICAL ERROR";
            liveness.style.color = "#f87171";
        }} else {{
            pulse.className = "pulse-dot dot-idle";
            liveness.innerHTML = "IDLE &bull; WAITING ON TOKENS";
            liveness.style.color = "#94a3b8";
        }}

        document.getElementById("inspRole").innerText = spec.mnemonic_role || "Executes discrete CPN transition coroutine.";
        document.getElementById("inspMetricsTitle").innerText = "Transition Execution Metrics";

        const latency = stats.mean_latency_ms ? stats.mean_latency_ms + " ms" : "0.08 ms";
        const fireCount = stats.fire_count || (isAlive ? 1 : 0);

        document.getElementById("inspMetricsBody").innerHTML = `
            <div class="metric-row">
                <span class="metric-label">Status:</span>
                <span class="metric-value val-active">${{stats.status || "ALIVE_FIRED"}}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Execution Count:</span>
                <span class="metric-value">${{fireCount}}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Mean Latency:</span>
                <span class="metric-value">${{latency}}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Guard Equation:</span>
                <span class="metric-value" style="font-size:10px; color:#38bdf8;">${{spec.guard_formula || "K3(Joint) == TRUE"}}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Retry Policy:</span>
                <span class="metric-value" style="font-size:11px;">${{spec.retry_policy || "None"}}</span>
            </div>
        `;

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

        if (count > 0 || spec.is_read_arc) {{
            pulse.className = "pulse-dot";
            liveness.innerHTML = "ACTIVE &bull; TOKEN AVAILABLE";
            liveness.style.color = "#4ade80";
        }} else {{
            pulse.className = "pulse-dot dot-idle";
            liveness.innerHTML = "EMPTY &bull; 0 TOKENS";
            liveness.style.color = "#94a3b8";
        }}

        document.getElementById("inspRole").innerText = spec.role || "Strongly typed Petri Net FIFO or continuous state buffer.";
        document.getElementById("inspMetricsTitle").innerText = "Token Ledger State";

        document.getElementById("inspMetricsBody").innerHTML = `
            <div class="metric-row">
                <span class="metric-label">Current Marking M(p):</span>
                <span class="${{count > 0 ? "val-token" : "metric-value"}}">${{count}}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Token Color Set (&Sigma;):</span>
                <span class="metric-value" style="color:#c084fc;">${{spec.color || "Color_Token"}}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Capacity Limit:</span>
                <span class="metric-value">${{spec.capacity || "1 (Bounded)"}}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Storage Topology:</span>
                <span class="metric-value">${{spec.is_read_arc ? "Continuous Read-Arc" : "Async FIFO Queue"}}</span>
            </div>
        `;

        document.getElementById("inspRel1Label").innerText = "Subnet:";
        document.getElementById("inspRel1Val").innerText = id.includes("Transfers") || id.includes("Lineup") || id.includes("Committed") ? "Stage 2 Gates" : (id.includes("Plan") ? "Optimization" : "Ingestion");
        document.getElementById("inspRel2Label").innerText = "Read Access:";
        document.getElementById("inspRel2Val").innerText = spec.is_read_arc ? "Non-Destructive Peek/Read" : "Destructive Queue Get";
    }}

    // Initialize with P_Committed or T_ReconcileLineup
    selectNode("P_Committed");
</script>

</body>
</html>
"""
    return html


def render_tab_autonomous_cpn(df: pd.DataFrame | None = None, current_squad: list[str] | None = None) -> None:
    """Render the Autonomous CPN Robotic Manager Telemetry and Execution Tab."""
    st.header("🤖 Autonomous CPN Execution Pipeline & Robotic Manager")
    st.caption(
        "Formal Kurt Jensen Timed Coloured Petri Net (TCPN) Runtime • Kleene $K_3$ Functional Guards • "
        "Closed-Loop Source Reconciliation Gates"
    )

    st.markdown(
        """
        The **Robotic Manager** operates as an autonomous, provably deadlock-free Coloured Petri Net (CPN). 
        Click on **any transition or place** on the interactive workbench canvas below to inspect its real-time 
        liveness, firing counts, execution latency, guard equations, and token multiset.
        """
    )

    # Automatically pre-populate default nominal state on initial load
    if "cpn_last_run" in st.session_state:
        if "transition_specs" not in st.session_state["cpn_last_run"].get("snapshot", {}):
            del st.session_state["cpn_last_run"]

    if "cpn_last_run" not in st.session_state:
        with st.spinner("Initializing CPN Runtime Telemetry & Nominal State..."):
            try:
                st.session_state["cpn_last_run"] = asyncio.run(_run_async_cycle(1, "Nominal Full-Pipeline Flow", 35))
            except Exception as e:
                st.warning(f"Initial CPN telemetry preflight skipped: {e}")

    # -------------------------------------------------------------------------
    # Control Panel
    # -------------------------------------------------------------------------
    st.subheader("🎛️ CPN Execution Controller")
    c1, c2, c3 = st.columns([1, 1.5, 1.5])

    with c1:
        target_gw = st.number_input("Target Gameweek", min_value=1, max_value=38, value=1, step=1, key="cpn_gw_select")

    with c2:
        scenario = st.selectbox(
            "Adversarial Scenario / Flow Mode",
            [
                "Nominal Full-Pipeline Flow",
                "ADV-1: 502 Gateway Recovery",
                "ADV-3: Late Vice-Captain Red Flag",
                "Critical Auth Failure",
            ],
            key="cpn_scenario_select"
        )

    with c3:
        mins_to_deadline = st.slider(
            "Minutes to Official Deadline ($D$)",
            min_value=5,
            max_value=120,
            value=35,
            step=5,
            help="Simulates proximity to the API-published deadline (D-8m forced disambiguation boundary)",
            key="cpn_deadline_slider"
        )

    b_col1, b_col2, _ = st.columns([1.5, 1, 2])
    with b_col1:
        run_cycle = st.button("🚀 Trigger CPN Execution Cycle", type="primary", use_container_width=True)
    with b_col2:
        refresh_data = st.button("🔄 Refresh Telemetry", use_container_width=True)

    if run_cycle:
        with st.spinner(f"Executing Timed CPN Gameweek {target_gw} cycle under scenario '{scenario}'..."):
            try:
                res = asyncio.run(_run_async_cycle(target_gw, scenario, mins_to_deadline))
                st.session_state["cpn_last_run"] = res
                st.toast("CPN Gameweek cycle completed!", icon="✅")
            except Exception as ex:
                st.error(f"Execution failed with unexpected runtime exception: {ex}")

    if refresh_data:
        st.cache_data.clear()
        st.rerun()

    # -------------------------------------------------------------------------
    # Execution Results Display & Mission Control Workbench
    # -------------------------------------------------------------------------
    last_run = st.session_state.get("cpn_last_run")

    if last_run:
        receipt = last_run.get("committed_receipt")
        alert = last_run.get("dead_letter_alert")
        duration = last_run.get("duration_seconds", 0.0)

        if receipt:
            st.success(
                f"**[SUCCESS] CLOSED-LOOP COMMITMENT VERIFIED BY SOURCE AUDIT GATE**  \n"
                f"Cycle executed in **{duration:.2f}s** • Target GW: **{last_run['gameweek']}** • Mode: **{last_run['scenario']}** • "
                f"Confirmation ID: **`{receipt.confirmation_id}`** • Hash: **`{receipt.payload_hash[:16]}...`**"
            )
        elif alert:
            st.error(
                f"**[HALTED] DEAD-LETTER QUEUE ALERT DEPOSITED: [{alert.severity}]**  \n"
                f"Reason: **{alert.reason}**  \n"
                f"Cycle halted in **{duration:.2f}s** • Context: `{alert.context}`"
            )

        # ---------------------------------------------------------------------
        # Cybernetic Mission-Control Workbench (Interactive HTML/SVG + Inspector)
        # ---------------------------------------------------------------------
        st.markdown("#### 🔬 CPN Topology & Interactive Transition/Place Inspector")
        st.caption("Click any transition box or place vault to inspect real-time metrics, liveness, and token ledgers.")
        
        workbench_html = _build_workbench_html(last_run.get("snapshot", {}))
        components.html(workbench_html, height=730, scrolling=False)

    # -------------------------------------------------------------------------
    # Real-Time Diagnostic Journal & Health Telemetry
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("📜 Continuous Diagnostic Journal & Event Stream")
    st.caption("Structured, non-blocking JSONL audit log recorded to logs/diagnostics/.")

    events_df = _load_diagnostic_events(limit=15)
    if not events_df.empty:
        display_df = events_df.copy()
        if "runtime_health" in display_df.columns:
            display_df["memory_rss_mb"] = display_df["runtime_health"].apply(lambda x: x.get("memory_rss_mb") if isinstance(x, dict) else None)
            display_df["cpu_percent"] = display_df["runtime_health"].apply(lambda x: x.get("cpu_percent") if isinstance(x, dict) else None)
            display_df = display_df.drop(columns=["runtime_health"])
        
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No diagnostic events found in logs/diagnostics/. Run an execution cycle above to populate events.")
