"""
automation/cpn/engine.py
Kurt Jensen Timed Coloured Petri Net Orchestration Engine.
Coordinates asyncio Actor tasks, scatter-gather concurrency, and deadline timeouts.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
import logging
from typing import Any
from automation.cpn.tokens import (
    Color_Deadline, Color_MarketData, Color_OptimizedPlan, Color_GuardToken, K3Status
)
from automation.cpn.places import CPNMarkingRegistry
from automation.cpn.transitions import (
    t_preflight_and_ingest, t_session_keepalive, t_simulate_and_solve,
    t_evaluate_guards, t_degrade_plan, t_dispatch_transfers, t_reconcile_transfers,
    t_dispatch_lineup, t_reconcile_lineup
)

logger = logging.getLogger("rubies_rangers.cpn.engine")


TRANSITION_SPECS: dict[str, dict[str, Any]] = {
    "T_PreflightAndIngest": {
        "display_title": "1A. Preflight Ingest & Session Audit",
        "subnet": "SUBNET 1: TELEMETRY INGESTION & SESSIONS",
        "mnemonic_role": "Authenticates manager credentials and ingests raw FPL telemetry into read-arc continuous state buffers.",
        "consumed_places": ["P_Timer"],
        "emitted_places": ["P_Session", "P_Market", "P_Squad"],
        "guard_formula": "t ≤ (deadline - 35m) ∧ is_authenticated",
        "retry_policy": "3 Retries with Exponential Backoff + Jitter",
    },
    "T_SessionKeepalive": {
        "display_title": "1B. Session Liveness Heartbeat Daemon",
        "subnet": "SUBNET 1: TELEMETRY INGESTION & SESSIONS",
        "mnemonic_role": "Periodic non-blocking background actor refreshing session authorization tokens before expiry.",
        "consumed_places": ["P_Session"],
        "emitted_places": ["P_Session"],
        "guard_formula": "session.expires_at > now + 10m",
        "retry_policy": "Autonomous Daemon (10m interval)",
    },
    "T_SimulateAndSolve": {
        "display_title": "2A. Stochastic MILP & Two-Stage Optimizer",
        "subnet": "SUBNET 2: STOCHASTIC TWO-STAGE OPTIMIZATION",
        "mnemonic_role": "Solves optimal starting XI, transfers, and captaincy under joint expected points covariance distributions.",
        "consumed_places": ["P_Squad", "P_Market"],
        "emitted_places": ["P_Plan", "P_PendingPlan", "P_Contingency"],
        "guard_formula": "bank + selling_prices ≥ squad_cost ∧ legal_formation",
        "retry_policy": "Fallback Baseline Plan Generation",
    },
    "T_ScatterGather": {
        "display_title": "2B. Streaming Scatter-Gather Disambiguator",
        "subnet": "SUBNET 2: STOCHASTIC TWO-STAGE OPTIMIZATION",
        "mnemonic_role": "Streams early leaks via asyncio.as_completed without Head-of-Line blocking; collapses at D-8m boundary.",
        "consumed_places": ["P_Contingency", "P_PendingPlan"],
        "emitted_places": ["P_ResolvedGuard", "P_Plan"],
        "guard_formula": "t ≤ (deadline - 8m) ∨ Ψ_Averse_Collapse",
        "retry_policy": "Hard D-8m Timeout Boundary",
    },
    "T_EvaluateGuards": {
        "display_title": "3A. Pure Kleene K3 Joint Guard Evaluator",
        "subnet": "SUBNET 3: K3 GUARDS & CONTINGENCY",
        "mnemonic_role": "Evaluates 8 pure functional invariants over candidate plan: budget, club caps, formations, hits, fitness, chips.",
        "consumed_places": ["P_Plan", "P_ResolvedGuard"],
        "emitted_places": ["P_TransfersAwaitingValidation", "P_PlanDegrade"],
        "guard_formula": "K3(g_budget ∧ g_club ∧ g_formation ∧ g_hit ∧ g_flags ∧ g_chips ∧ g_session ∧ g_time)",
        "retry_policy": "Algebraic Degradation Loop",
    },
    "T_DegradePlan": {
        "display_title": "3B. Safe Harbor Plan Degradation Actor",
        "subnet": "SUBNET 3: K3 GUARDS & CONTINGENCY",
        "mnemonic_role": "Strips compromised chip tokens and substitutes healthy baseline XI, avoiding emergency abort.",
        "consumed_places": ["P_PlanDegrade"],
        "emitted_places": ["P_Plan"],
        "guard_formula": "is_chip_degradable(plan) == TRUE",
        "retry_policy": "Re-evaluates via T_EvaluateGuards",
    },
    "T_DispatchTransfers": {
        "display_title": "4A. Stage 1 Transfer & Chip Dispatcher",
        "subnet": "SUBNET 4: TWO-STAGE DISPATCH & GATES",
        "mnemonic_role": "Submits transfers and pre-activates Wildcard / Free Hit chips to the FPL gateway at D-6.5m.",
        "consumed_places": ["P_Plan"],
        "emitted_places": ["P_TransfersAwaitingValidation"],
        "guard_formula": "t ≤ (deadline - 6.5m) ∧ authenticated",
        "retry_policy": "Max 3 Retries (Backoff + Jitter)",
    },
    "T_ReconcileTransfers": {
        "display_title": "4B. Gate 1 Read-After-Write Transfer Auditor",
        "subnet": "SUBNET 4: TWO-STAGE DISPATCH & GATES",
        "mnemonic_role": "Audits server state to verify elements bought/sold exist on FPL database, preventing Phantom 200 drops.",
        "consumed_places": ["P_TransfersAwaitingValidation"],
        "emitted_places": ["P_TransfersExecuted", "P_DeadLetter"],
        "guard_formula": "actual_elements_in_squad ≡ plan_transfers",
        "retry_policy": "Immediate Dead-Letter Alarm on Mismatch",
    },
    "T_DispatchLineup": {
        "display_title": "4C. Stage 2 Lineup & Armband Dispatcher",
        "subnet": "SUBNET 4: TWO-STAGE DISPATCH & GATES",
        "mnemonic_role": "Submits 11 starters, captain, vice-captain, and bench priority order to FPL gateway at D-4.0m.",
        "consumed_places": ["P_TransfersExecuted"],
        "emitted_places": ["P_LineupAwaitingValidation"],
        "guard_formula": "t ≤ (deadline - 4.0m) ∧ Stage1_Verified",
        "retry_policy": "Max 3 Retries (Backoff + Jitter)",
    },
    "T_ReconcileLineup": {
        "display_title": "4D. Gate 2 Ultimate Lineup Reconciliation Gate",
        "subnet": "SUBNET 4: TWO-STAGE DISPATCH & GATES",
        "mnemonic_role": "Audits 15-player server roster against solver picks; deposits cryptographic SHA-256 receipt into P_Committed.",
        "consumed_places": ["P_LineupAwaitingValidation"],
        "emitted_places": ["P_Committed", "P_DeadLetter"],
        "guard_formula": "server_picks ≡ plan_picks ∧ hash_match",
        "retry_policy": "Gate 2 Audit or Emergency Rollback",
    },
}

PLACE_SPECS: dict[str, dict[str, Any]] = {
    "P_Session": {"display_title": "1. Session Vault", "color": "Color_Session", "role": "Read-arc holding active session auth & CSRF cookies.", "is_read_arc": True, "capacity": "1 (Continuous)"},
    "P_Market": {"display_title": "2. Market State Vault", "color": "Color_MarketData", "role": "Read-arc holding bootstrap-static, fixtures, and odds.", "is_read_arc": True, "capacity": "1 (Continuous)"},
    "P_Squad": {"display_title": "3. Squad State Vault", "color": "Color_SquadState", "role": "Read-arc holding verified player IDs, selling prices, and ghost squad.", "is_read_arc": True, "capacity": "1 (Continuous)"},
    "P_Timer": {"display_title": "4. Gameweek Deadline Timer", "color": "Color_Deadline", "role": "Timed token specifying API-published deadline and D-8m cutoff.", "is_read_arc": False, "capacity": "1"},
    "P_Plan": {"display_title": "5. Selected Optimal Plan", "color": "Color_OptimizedPlan", "role": "Candidate lineup plan ready for guard evaluation and dispatch.", "is_read_arc": False, "capacity": "1"},
    "P_PendingPlan": {"display_title": "6. Disambiguation In-Flight Buffer", "color": "Color_OptimizedPlan", "role": "Holds candidate plan while scatter-gather resolves doubt tokens.", "is_read_arc": False, "capacity": "1"},
    "P_Contingency": {"display_title": "7. Contingency Doubt Tokens", "color": "Color_GuardToken", "role": "Holds unresolved Kleene UNKNOWN tokens awaiting verified leaks.", "is_read_arc": False, "capacity": "15 (k-bounded)"},
    "P_ResolvedGuard": {"display_title": "8. Resolved Guard Ledger", "color": "Color_GuardToken", "role": "Holds resolved guard tokens (TRUE or FALSE) streamed by scatter-gather.", "is_read_arc": False, "capacity": "15 (k-bounded)"},
    "P_PlanDegrade": {"display_title": "9. Plan Degradation Queue", "color": "Color_OptimizedPlan", "role": "Holds candidate plans requiring chip stripping or baseline fallback.", "is_read_arc": False, "capacity": "1"},
    "P_TransfersAwaitingValidation": {"display_title": "10. Stage 1 In-Flight Buffer", "color": "Color_OptimizedPlan", "role": "Holds transfers submitted to gateway awaiting Gate 1 audit.", "is_read_arc": False, "capacity": "1"},
    "P_TransfersExecuted": {"display_title": "11. Stage 1 Verified Queue", "color": "Color_OptimizedPlan", "role": "Verified transfers committed on FPL server; unblocks Stage 2.", "is_read_arc": False, "capacity": "1"},
    "P_LineupAwaitingValidation": {"display_title": "12. Stage 2 In-Flight Buffer", "color": "Color_OptimizedPlan", "role": "Holds lineup submitted to gateway awaiting Gate 2 audit.", "is_read_arc": False, "capacity": "1"},
    "P_Committed": {"display_title": "13. Final Commitment Vault", "color": "Color_Receipt", "role": "Terminal commitment place holding cryptographic SHA-256 receipts.", "is_read_arc": False, "capacity": "1-Safe"},
    "P_DeadLetter": {"display_title": "14. Dead-Letter Alert Queue", "color": "Color_Alert", "role": "Traps unrecoverable critical failures and mismatch anomalies.", "is_read_arc": False, "capacity": "Unbounded"},
}


class CPNEngine:
    """Production TCPN Runtime Orchestrator."""

    def __init__(
        self,
        fpl_client: Any,
        solver_engine: Any,
        legal_formations: set[tuple[int, int, int]],
        journal: Any = None,
    ) -> None:
        self.fpl_client = fpl_client
        self.solver_engine = solver_engine
        self.legal_formations = legal_formations
        self.journal = journal
        self.marking = CPNMarkingRegistry()
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # Telemetry metrics per transition
        self.transition_stats: dict[str, dict[str, Any]] = {
            t_name: {
                "status": "IDLE",
                "fire_count": 0,
                "last_latency_ms": 0.0,
                "mean_latency_ms": 0.0,
                "total_latency_ms": 0.0,
                "last_fired_utc": None,
                "last_error": None,
            }
            for t_name in TRANSITION_SPECS
        }

    def _record_transition(self, name: str, duration_ms: float, success: bool, error: str | None = None) -> None:
        """Update live telemetry for an individual transition."""
        if name not in self.transition_stats:
            return
        st_entry = self.transition_stats[name]
        st_entry["fire_count"] += 1
        st_entry["last_latency_ms"] = round(duration_ms, 2)
        st_entry["total_latency_ms"] += duration_ms
        st_entry["mean_latency_ms"] = round(st_entry["total_latency_ms"] / st_entry["fire_count"], 2)
        st_entry["last_fired_utc"] = datetime.now(timezone.utc).isoformat()
        st_entry["status"] = "ALIVE_FIRED" if success else "BLOCKED"
        st_entry["last_error"] = error

    async def execute_scatter_gather(self, deadline_utc: datetime) -> None:
        """
        Executes Event-Driven Streaming Scatter-Gather concurrency.
        Streams early leaks into P_ResolvedGuard via asyncio.as_completed without HoL blocking.
        D-8m acts as hard fallback boundary collapsing residual U tokens via Psi_Averse.
        Consumes parent plan safely from P_PendingPlan, eliminating queue dequeue deadlocks.
        """
        if self.marking.P_PendingPlan.empty():
            return
        plan = await self.marking.P_PendingPlan.get()

        contingency_tokens: list[Color_GuardToken] = []
        while not self.marking.P_Contingency.empty():
            token = await self.marking.P_Contingency.get()
            if token.plan_id == plan.plan_id:
                contingency_tokens.append(token)
            else:
                await self.marking.P_Contingency.put(token)

        if not contingency_tokens:
            await self.marking.P_Plan.put(plan)
            return

        cutoff_utc = deadline_utc - timedelta(minutes=8)
        timeout_seconds = max(0.01, (cutoff_utc - datetime.now(timezone.utc)).total_seconds())

        async def resolve_single_guard(guard_token: Color_GuardToken) -> Color_GuardToken:
            """Waits for verified leak or times out at D-8m cutoff."""
            try:
                leak_result = await asyncio.wait_for(
                    self.fpl_client.listen_for_leak(guard_token.subject_id),
                    timeout=timeout_seconds
                )
                if leak_result:
                    status = K3Status.TRUE if leak_result.get("starts") else K3Status.FALSE
                    return Color_GuardToken(
                        plan_id=guard_token.plan_id, guard_name=guard_token.guard_name,
                        status=status, subject_id=guard_token.subject_id,
                        doubt_type=guard_token.doubt_type, is_fatal=guard_token.is_fatal,
                        context=leak_result, resolved_at=datetime.now(timezone.utc)
                    )
                else:
                    # No leak reported, collapse to Psi_Averse
                    return Color_GuardToken(
                        plan_id=guard_token.plan_id, guard_name=guard_token.guard_name,
                        status=K3Status.FALSE, subject_id=guard_token.subject_id,
                        doubt_type="psi_averse_collapsed", is_fatal=False,
                        context={"reason": "No leak confirmed"}, resolved_at=datetime.now(timezone.utc)
                    )
            except (asyncio.TimeoutError, TimeoutError):
                # D-8m Forced Disambiguation Collapse (Psi_Averse)
                logger.info(f"[Psi_Averse] Collapsing doubtful token {guard_token.subject_id} at D-8m cutoff")
                return Color_GuardToken(
                    plan_id=guard_token.plan_id, guard_name=guard_token.guard_name,
                    status=K3Status.FALSE, subject_id=guard_token.subject_id,
                    doubt_type="psi_averse_collapsed", is_fatal=False,
                    context={"reason": "D-8m timeout reached"}, resolved_at=datetime.now(timezone.utc)
                )

        # Stream completed resolutions without Head-of-Line blocking
        tasks = [asyncio.create_task(resolve_single_guard(t)) for t in contingency_tokens]
        resolved_tokens: list[Color_GuardToken] = []
        for fut in asyncio.as_completed(tasks):
            resolved = await fut
            await self.marking.P_ResolvedGuard.put(resolved)
            resolved_tokens.append(resolved)
            logger.info(f"[ScatterGather] Streamed resolution for element {resolved.subject_id} -> {resolved.status.name}")

        # Reconstitute Plan via Position- and Formation-Aware Contingency Tree
        market = await self.marking.P_Market.read()
        reconstituted = self._apply_contingency_tree(plan, resolved_tokens, market)
        await self.marking.P_Plan.put(reconstituted)

    def _apply_contingency_tree(
        self,
        plan: Color_OptimizedPlan,
        resolved: list[Color_GuardToken],
        market: Color_MarketData
    ) -> Color_OptimizedPlan:
        """
        Applies formation- and position-aware bench substitution and dual-armband safe harbor.
        Guarantees GKP is only swapped with Sub GKP and outfield formations remain legal.
        """
        starters = list(plan.starters)
        bench = list(plan.bench)
        captain = plan.captain
        vice_captain = plan.vice_captain

        elements_df = market.elements.set_index("id") if "id" in market.elements.columns else market.elements
        pos_map = elements_df["position_name"].to_dict() if "position_name" in elements_df.columns else {}
        ev_map = elements_df["moneyball_score"].to_dict() if "moneyball_score" in elements_df.columns else {}

        fitness_map = {g.subject_id: g.status for g in resolved}

        for g in resolved:
            if g.status == K3Status.FALSE and g.subject_id in starters:
                ruled_out_id = g.subject_id
                player_pos = pos_map.get(ruled_out_id, "MID")

                if player_pos == "GKP":
                    sub_gkp = bench[0]
                    starters.remove(ruled_out_id)
                    starters.insert(0, sub_gkp)
                    bench[0] = ruled_out_id
                else:
                    # Outfield bench candidates: bench[1], bench[2], bench[3]
                    promoted_idx = None
                    for b_idx in range(1, len(bench)):
                        cand = bench[b_idx]
                        if fitness_map.get(cand) == K3Status.FALSE:
                            continue
                        # Test provisional formation legality
                        cand_pos = pos_map.get(cand, "MID")
                        prov_starters = [p for p in starters if p != ruled_out_id] + [cand]
                        d_cnt = sum(1 for p in prov_starters if pos_map.get(p) == "DEF")
                        m_cnt = sum(1 for p in prov_starters if pos_map.get(p) == "MID")
                        f_cnt = sum(1 for p in prov_starters if pos_map.get(p) == "FWD")
                        if (d_cnt, m_cnt, f_cnt) in self.legal_formations:
                            promoted_idx = b_idx
                            break

                    if promoted_idx is not None:
                        promoted_id = bench[promoted_idx]
                        starters.remove(ruled_out_id)
                        starters.append(promoted_id)
                        bench.remove(promoted_id)
                        bench.append(ruled_out_id)

                # Armband Safe-Harbor: verify captaincy and vice-captaincy
                if captain == ruled_out_id or fitness_map.get(captain) == K3Status.FALSE:
                    if vice_captain in starters and fitness_map.get(vice_captain, K3Status.TRUE) == K3Status.TRUE:
                        captain = vice_captain
                        eligible = [p for p in starters if p != captain and fitness_map.get(p, K3Status.TRUE) == K3Status.TRUE]
                        vice_captain = max(eligible, key=lambda p: ev_map.get(p, 0.0)) if eligible else captain
                    else:
                        fit_starters = [p for p in starters if fitness_map.get(p, K3Status.TRUE) == K3Status.TRUE]
                        sorted_ev = sorted(fit_starters or starters, key=lambda p: ev_map.get(p, 0.0), reverse=True)
                        captain = sorted_ev[0]
                        vice_captain = sorted_ev[1] if len(sorted_ev) > 1 else sorted_ev[0]

        # Recompute formation tuple dynamically to prevent invariant desync
        d_cnt = sum(1 for p in starters if pos_map.get(p) == "DEF")
        m_cnt = sum(1 for p in starters if pos_map.get(p) == "MID")
        f_cnt = sum(1 for p in starters if pos_map.get(p) == "FWD")
        new_formation = (d_cnt, m_cnt, f_cnt) if (d_cnt + m_cnt + f_cnt == 10) else plan.formation_tuple

        return Color_OptimizedPlan(
            plan_id=plan.plan_id, starters=starters, bench=bench,
            captain=captain, vice_captain=vice_captain, transfers=plan.transfers,
            chip=plan.chip, expected_utility=plan.expected_utility,
            formation_tuple=new_formation, fallback_plan=plan.fallback_plan,
            is_degraded=plan.is_degraded, chip_degraded_reason=plan.chip_degraded_reason,
            contingency_tree=plan.contingency_tree
        )

    async def _execute_timed_transition(self, name: str, coroutine_func: Any, *args: Any, **kwargs: Any) -> Any:
        """Executes a transition coroutine while recording execution latency and status."""
        t0 = datetime.now(timezone.utc)
        try:
            res = await coroutine_func(*args, **kwargs)
            dur_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000.0
            has_crit = self._has_critical_failure()
            self._record_transition(name, dur_ms, success=not has_crit)
            return res
        except Exception as ex:
            dur_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000.0
            self._record_transition(name, dur_ms, success=False, error=str(ex))
            raise

    async def run_gameweek_cycle(self, gameweek: int, deadline_utc: datetime) -> None:
        """Main lifecycle entrypoint for an automated gameweek execution."""
        self._running = True
        logger.info(f"[CPNEngine] Initializing CPN cycle for GW {gameweek}, Deadline: {deadline_utc.isoformat()}")

        # Initial Markings M0
        deadline_token = Color_Deadline(
            gameweek=gameweek,
            deadline_utc=deadline_utc,
            cutoff_disambiguation_utc=deadline_utc - timedelta(minutes=8)
        )
        await self.marking.P_Timer.put(deadline_token)

        # 1. Preflight Ingestion at D-35m
        await self._execute_timed_transition("T_PreflightAndIngest", t_preflight_and_ingest, self.marking, self.fpl_client)
        if self._has_critical_failure():
            logger.critical("[CPNEngine] Preflight failed; aborting gameweek cycle.")
            return

        # 2. Start Background Heartbeat Actor (Every 10m)
        self.transition_stats["T_SessionKeepalive"]["status"] = "ALIVE_RUNNING"
        self._tasks.append(asyncio.create_task(t_session_keepalive(self.marking, self.fpl_client)))

        # 3. Solve Optimal Plan at D-30m
        await self._execute_timed_transition("T_SimulateAndSolve", t_simulate_and_solve, self.marking, self.solver_engine)
        if self._has_critical_failure():
            logger.critical("[CPNEngine] Solver failed; aborting gameweek cycle.")
            return

        # 4. Guard Evaluation at D-29m
        await self._execute_timed_transition("T_EvaluateGuards", t_evaluate_guards, self.marking, self.legal_formations)
        if self._has_critical_failure():
            logger.critical("[CPNEngine] Fatal guard violation; aborting gameweek cycle.")
            return

        # 5. Handle Plan Degradation if chip safety failed
        if not self.marking.P_PlanDegrade.empty():
            await self._execute_timed_transition("T_DegradePlan", t_degrade_plan, self.marking)
            await self._execute_timed_transition("T_EvaluateGuards", t_evaluate_guards, self.marking, self.legal_formations)
            if self._has_critical_failure():
                return

        # 6. Handle Scatter-Gather if suspended plans exist
        if not self.marking.P_PendingPlan.empty():
            await self._execute_timed_transition("T_ScatterGather", self.execute_scatter_gather, deadline_utc)
            await self._execute_timed_transition("T_EvaluateGuards", t_evaluate_guards, self.marking, self.legal_formations)
            if self._has_critical_failure():
                return

        # 7. Stage 1 Dispatch: Transfers & Chips at D-6.5m
        if not self.marking.P_Plan.empty():
            wait_xfer = (deadline_utc - timedelta(minutes=6.5) - datetime.now(timezone.utc)).total_seconds()
            if wait_xfer > 0 and wait_xfer < 1800:
                await asyncio.sleep(min(wait_xfer, 0.05))
            await self._execute_timed_transition("T_DispatchTransfers", t_dispatch_transfers, self.marking, self.fpl_client, deadline_utc)
            if self._has_critical_failure():
                return

        # 8. Source-System Reconciliation Gate 1: Transfers & Chips at D-5.5m
        if not self.marking.P_TransfersAwaitingValidation.empty():
            await self._execute_timed_transition("T_ReconcileTransfers", t_reconcile_transfers, self.marking, self.fpl_client)
            if self._has_critical_failure():
                return

        # 9. Stage 2 Dispatch: Lineup & Armband at D-4.0m
        if not self.marking.P_TransfersExecuted.empty():
            wait_lineup = (deadline_utc - timedelta(minutes=4.0) - datetime.now(timezone.utc)).total_seconds()
            if wait_lineup > 0 and wait_lineup < 1800:
                await asyncio.sleep(min(wait_lineup, 0.05))
            await self._execute_timed_transition("T_DispatchLineup", t_dispatch_lineup, self.marking, self.fpl_client)
            if self._has_critical_failure():
                return

        # 10. Source-System Reconciliation Gate 2: Lineup, Armband & Bench at D-2.0m
        if not self.marking.P_LineupAwaitingValidation.empty():
            await self._execute_timed_transition("T_ReconcileLineup", t_reconcile_lineup, self.marking, self.fpl_client)

        logger.info("[CPNEngine] Gameweek execution cycle concluded.")

    def _has_critical_failure(self) -> bool:
        """Checks if any unrecoverable critical alert was deposited into DeadLetter."""
        return any(a.severity == "CRITICAL" for a in self.marking.P_DeadLetter.snapshot())

    def get_telemetry_snapshot(self) -> dict[str, Any]:
        """Provides thread-safe state inspection dictionary for Streamlit app.py."""
        summary = self.marking.get_summary()
        place_order = list(PLACE_SPECS.keys())
        marking_vector = [summary.get(p, 0) for p in place_order]
        return {
            "is_running": self._running,
            "place_counts": summary,
            "marking_vector": marking_vector,
            "active_plans": [p.plan_id for p in self.marking.P_Plan.snapshot()],
            "alerts": [a.reason for a in self.marking.P_DeadLetter.snapshot()],
            "transition_stats": self.transition_stats,
            "transition_specs": TRANSITION_SPECS,
            "place_specs": PLACE_SPECS,
        }


    async def shutdown(self) -> None:
        """Graceful shutdown handler for daemon termination."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("[CPNEngine] Gracefully stopped all CPN tasks.")
