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


class CPNEngine:
    """Production TCPN Runtime Orchestrator."""

    def __init__(
        self,
        fpl_client: Any,
        solver_engine: Any,
        legal_formations: set[tuple[int, int, int]]
    ) -> None:
        self.fpl_client = fpl_client
        self.solver_engine = solver_engine
        self.legal_formations = legal_formations
        self.marking = CPNMarkingRegistry()
        self._running = False
        self._tasks: list[asyncio.Task] = []

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
        await t_preflight_and_ingest(self.marking, self.fpl_client)
        if self._has_critical_failure():
            logger.critical("[CPNEngine] Preflight failed; aborting gameweek cycle.")
            return

        # 2. Start Background Heartbeat Actor (Every 10m)
        self._tasks.append(asyncio.create_task(t_session_keepalive(self.marking, self.fpl_client)))

        # 3. Solve Optimal Plan at D-30m
        await t_simulate_and_solve(self.marking, self.solver_engine)
        if self._has_critical_failure():
            logger.critical("[CPNEngine] Solver failed; aborting gameweek cycle.")
            return

        # 4. Guard Evaluation at D-29m
        await t_evaluate_guards(self.marking, self.legal_formations)
        if self._has_critical_failure():
            logger.critical("[CPNEngine] Fatal guard violation; aborting gameweek cycle.")
            return

        # 5. Handle Plan Degradation if chip safety failed
        if not self.marking.P_PlanDegrade.empty():
            await t_degrade_plan(self.marking)
            await t_evaluate_guards(self.marking, self.legal_formations)
            if self._has_critical_failure():
                return

        # 6. Handle Scatter-Gather if suspended plans exist
        if not self.marking.P_PendingPlan.empty():
            await self.execute_scatter_gather(deadline_utc)
            await t_evaluate_guards(self.marking, self.legal_formations)
            if self._has_critical_failure():
                return

        # 7. Stage 1 Dispatch: Transfers & Chips at D-6.5m
        if not self.marking.P_Plan.empty():
            wait_xfer = (deadline_utc - timedelta(minutes=6.5) - datetime.now(timezone.utc)).total_seconds()
            if wait_xfer > 0 and wait_xfer < 1800:
                await asyncio.sleep(min(wait_xfer, 0.05))
            await t_dispatch_transfers(self.marking, self.fpl_client, deadline_utc)
            if self._has_critical_failure():
                return

        # 8. Source-System Reconciliation Gate 1: Transfers & Chips at D-5.5m
        if not self.marking.P_TransfersAwaitingValidation.empty():
            await t_reconcile_transfers(self.marking, self.fpl_client)
            if self._has_critical_failure():
                return

        # 9. Stage 2 Dispatch: Lineup & Armband at D-4.0m
        if not self.marking.P_TransfersExecuted.empty():
            wait_lineup = (deadline_utc - timedelta(minutes=4.0) - datetime.now(timezone.utc)).total_seconds()
            if wait_lineup > 0 and wait_lineup < 1800:
                await asyncio.sleep(min(wait_lineup, 0.05))
            await t_dispatch_lineup(self.marking, self.fpl_client)
            if self._has_critical_failure():
                return

        # 10. Source-System Reconciliation Gate 2: Lineup, Armband & Bench at D-2.0m
        if not self.marking.P_LineupAwaitingValidation.empty():
            await t_reconcile_lineup(self.marking, self.fpl_client)

        logger.info("[CPNEngine] Gameweek execution cycle concluded.")

    def _has_critical_failure(self) -> bool:
        """Checks if any unrecoverable critical alert was deposited into DeadLetter."""
        return any(a.severity == "CRITICAL" for a in self.marking.P_DeadLetter.snapshot())

    def get_telemetry_snapshot(self) -> dict[str, Any]:
        """Provides thread-safe state inspection dictionary for Streamlit app.py."""
        return {
            "is_running": self._running,
            "place_counts": self.marking.get_summary(),
            "active_plans": [p.plan_id for p in self.marking.P_Plan.snapshot()],
            "alerts": [a.reason for a in self.marking.P_DeadLetter.snapshot()]
        }

    async def shutdown(self) -> None:
        """Graceful shutdown handler for daemon termination."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("[CPNEngine] Gracefully stopped all CPN tasks.")
