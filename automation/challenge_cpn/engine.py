"""
automation/challenge_cpn/engine.py
Kurt Jensen Coloured Petri Net Execution Engine for FPL Challenge mode.
Provides step-by-step and full-pipeline async execution with Saga transaction verification.
Runs completely standalone in-process with 0 dependency on the FastAPI microservice.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List

from analytics.challenge.picker import ChallengePickerConfig
from clients.fpl_challenge_client import FPLChallengeClient
from clients.fpl_client import FPLClient
from automation.challenge_cpn.places import ChallengeMarkingRegistry
from automation.challenge_cpn.diagnostics import ChallengeCPNDiagnosticJournal
from automation.challenge_cpn.transitions import ChallengeTransitions
from automation.challenge_cpn.tokens import (
    Color_ChallengePlan,
    Color_ChallengeValidation,
    Color_ChallengeReceipt,
    Color_ChallengeAlert,
    Color_ChallengeSagaToken,
    SagaStatus,
)

logger = logging.getLogger("rubies_rangers.challenge.engine")


CHALLENGE_TRANSITION_SPECS: dict[str, dict[str, Any]] = {
    "T_FETCH_CHALLENGE_RULES": {
        "display_title": "1A. Weekly Challenge Rule Ingester",
        "subnet": "SUBNET 1: INGESTION & MARKET",
        "mnemonic_role": "Extracts weekly tournament rule constraints (budget cap, max per club, squad size, scoring boosts) from official API or preset.",
        "consumed_places": ["P_CHALLENGE_IDLE"],
        "emitted_places": ["P_CHALLENGE_RULES_READY"],
        "guard_formula": "gameweek ∈ [1, 38] ∧ preset_valid",
        "retry_policy": "Fallback to Default Preset",
    },
    "T_INGEST_CHALLENGE_MARKET": {
        "display_title": "1B. Player Market & Odds Ingester",
        "subnet": "SUBNET 1: INGESTION & MARKET",
        "mnemonic_role": "Ingests live player pool, element types, FDR schedule, and bookmaker implied goal probabilities.",
        "consumed_places": ["P_CHALLENGE_IDLE"],
        "emitted_places": ["P_CHALLENGE_MARKET_READY"],
        "guard_formula": "|players| > 500 ∧ |fixtures| ≥ 1",
        "retry_policy": "Cached Disk Fallback",
    },
    "T_FETCH_CURRENT_TEAM": {
        "display_title": "1C. Current Published Team Ingester",
        "subnet": "SUBNET 1: INGESTION & MARKET",
        "mnemonic_role": "Fetches existing published squad and captaincy from FPL Challenge endpoint to calculate amendment deltas.",
        "consumed_places": ["P_CHALLENGE_IDLE"],
        "emitted_places": ["P_CHALLENGE_CURRENT_TEAM"],
        "guard_formula": "entry_id > 0",
        "retry_policy": "Empty Squad Cold-Start",
    },
    "T_RUN_CHALLENGE_PICKER": {
        "display_title": "2. Two-Stage Stochastic Challenge Solver",
        "subnet": "SUBNET 2: STOCHASTIC OPTIMIZATION",
        "mnemonic_role": "Executes Stage 1 screening and Stage 2 Monte Carlo simulations (500-2500 draws) to crown optimal candidate portfolio.",
        "consumed_places": ["P_CHALLENGE_RULES_READY", "P_CHALLENGE_MARKET_READY", "P_CHALLENGE_CURRENT_TEAM"],
        "emitted_places": ["P_CHALLENGE_OPTIMIZED"],
        "guard_formula": "guard_can_solve(rules, market, team) == TRUE",
        "retry_policy": "Dynamic Archetype Fallback",
    },
    "T_VALIDATE_MODEL_SETTINGS": {
        "display_title": "3. Quantitative Model & Invariant Validator",
        "subnet": "SUBNET 3: MODEL VALIDATION",
        "mnemonic_role": "Asserts physical Challenge rules, formation quotas, budget limits, and detects hyperparameter drift against config.yaml.",
        "consumed_places": ["P_CHALLENGE_OPTIMIZED"],
        "emitted_places": ["P_CHALLENGE_VALIDATED", "P_CHALLENGE_ALERTS"],
        "guard_formula": "is_valid(candidate, rules) ∧ zero_drift",
        "retry_policy": "Pipeline Abort on Error -> P_ALERTS",
    },
    "T_SAGA_SUBMIT": {
        "display_title": "4A. Saga Challenge Lineup Dispatcher",
        "subnet": "SUBNET 4: SAGA & VERIFICATION",
        "mnemonic_role": "Encapsulates picks into JSON payload and transmits to official FPL Challenge entry point (or dry-run simulation).",
        "consumed_places": ["P_CHALLENGE_VALIDATED", "P_CHALLENGE_SUBMITTING"],
        "emitted_places": ["P_CHALLENGE_VERIFYING"],
        "guard_formula": "guard_validation_passed ∧ attempt ≤ max_retries",
        "retry_policy": "Exponential Backoff (2^attempt * 0.5s)",
    },
    "T_SAGA_VERIFY": {
        "display_title": "4B. Closed-Loop Saga Verification Gate",
        "subnet": "SUBNET 4: SAGA & VERIFICATION",
        "mnemonic_role": "Queries live server state post-submission to verify element IDs and captaincy match planned picks exactly.",
        "consumed_places": ["P_CHALLENGE_VERIFYING"],
        "emitted_places": ["P_CHALLENGE_CONFIRMED", "P_CHALLENGE_SUBMITTING", "P_CHALLENGE_COMPENSATION"],
        "guard_formula": "server_picks ≡ expected_picks ∧ cap_match",
        "retry_policy": "Backoff Retry or P_COMPENSATION Rollback",
    },
}

CHALLENGE_PLACE_SPECS: dict[str, dict[str, Any]] = {
    "P_CHALLENGE_IDLE": {"display_title": "1. CPN Dispatch Idle Vault", "color": "Color_Trigger", "role": "Initial Petri Net entry token enabling concurrent pipeline triggers.", "is_read_arc": False, "capacity": "1-Safe"},
    "P_CHALLENGE_RULES_READY": {"display_title": "2. Challenge Rules & Cap Vault", "color": "Color_ChallengeRule", "role": "Continuous state place holding active weekly Challenge ruleset, budget cap, club limits, and bonus multipliers.", "is_read_arc": True, "capacity": "1 (Continuous)"},
    "P_CHALLENGE_MARKET_READY": {"display_title": "3. Market Intelligence & Odds Vault", "color": "Color_ChallengeMarket", "role": "Continuous state place holding element pricing, expected points (xP), fixture ticker, and bookmaker odds.", "is_read_arc": True, "capacity": "1 (Continuous)"},
    "P_CHALLENGE_CURRENT_TEAM": {"display_title": "4. Manager Squad Snapshot Vault", "color": "Color_ChallengeSquadState", "role": "Continuous state place holding current published lineup, captaincy armband, and entry metadata.", "is_read_arc": True, "capacity": "1 (Continuous)"},
    "P_CHALLENGE_OPTIMIZED": {"display_title": "5. Solved Candidate Portfolio Buffer", "color": "Color_ChallengePlan", "role": "FIFO buffer holding the optimal crowned squad generated by the two-stage stochastic picker.", "is_read_arc": False, "capacity": "1"},
    "P_CHALLENGE_VALIDATED": {"display_title": "6. Validated Model Invariant Ledger", "color": "Color_ChallengeValidation", "role": "FIFO buffer holding verified model invariants and config parameter alignment checks.", "is_read_arc": False, "capacity": "1"},
    "P_CHALLENGE_SUBMITTING": {"display_title": "7. Saga Submission & Retry Queue", "color": "Color_ChallengeSagaToken", "role": "Holds in-flight or exponential backoff retry tokens for API payload transmission.", "is_read_arc": False, "capacity": "3 (Bounded)"},
    "P_CHALLENGE_VERIFYING": {"display_title": "8. Verification Read-After-Write Gateway", "color": "Color_ChallengeSagaToken", "role": "Holds dispatched payload awaiting live server read-after-write audit.", "is_read_arc": False, "capacity": "1"},
    "P_CHALLENGE_CONFIRMED": {"display_title": "9. Terminal Confirmed Receipt Vault", "color": "Color_ChallengeReceipt", "role": "Terminal commitment place holding confirmed audit receipts and transaction IDs.", "is_read_arc": False, "capacity": "1-Safe"},
    "P_CHALLENGE_COMPENSATION": {"display_title": "10. Saga Compensation & Rollback Queue", "color": "Color_ChallengeSagaToken", "role": "Traps unrecoverable submission mismatches when maximum retries are exhausted.", "is_read_arc": False, "capacity": "Unbounded"},
    "P_CHALLENGE_ALERTS": {"display_title": "11. Dead-Letter Anomaly & Alert Queue", "color": "Color_ChallengeAlert", "role": "Traps critical invariant violations and diagnostic alerts.", "is_read_arc": False, "capacity": "Unbounded"},
}


class ChallengeCPNEngine:
    """
    Asynchronous Petri Net execution engine governing the FPL Challenge pipeline.
    Orchestrates transition firings, model validation invariant checks,
    and the self-healing Saga verification & retry loop.
    """

    def __init__(
        self,
        challenge_client: Optional[FPLChallengeClient] = None,
        fpl_client: Optional[FPLClient] = None,
        journal: Optional[ChallengeCPNDiagnosticJournal] = None,
        dry_run: bool = True
    ) -> None:
        self.dry_run = dry_run
        self.reg = ChallengeMarkingRegistry()
        self.journal = journal or ChallengeCPNDiagnosticJournal()
        self.transitions = ChallengeTransitions(
            registry=self.reg,
            journal=self.journal,
            challenge_client=challenge_client,
            fpl_client=fpl_client,
            dry_run=self.dry_run
        )
        self._last_plan: Optional[Color_ChallengePlan] = None
        self._last_validation: Optional[Color_ChallengeValidation] = None
        self._last_receipt: Optional[Color_ChallengeReceipt] = None
        self.transition_stats: Dict[str, Dict[str, Any]] = {
            t_name: {
                "status": "IDLE",
                "fire_count": 0,
                "mean_latency_ms": 0.0,
                "last_latency_ms": 0.0,
                "total_latency_ms": 0.0,
            }
            for t_name in CHALLENGE_TRANSITION_SPECS
        }

    def _record_transition_stat(self, t_name: str, status: str, latency_ms: float) -> None:
        """Records execution telemetry for a transition actor."""
        if t_name not in self.transition_stats:
            self.transition_stats[t_name] = {
                "status": status,
                "fire_count": 0,
                "mean_latency_ms": 0.0,
                "last_latency_ms": 0.0,
                "total_latency_ms": 0.0,
            }
        stat = self.transition_stats[t_name]
        stat["status"] = status
        stat["fire_count"] += 1
        stat["last_latency_ms"] = round(latency_ms, 2)
        stat["total_latency_ms"] += latency_ms
        stat["mean_latency_ms"] = round(stat["total_latency_ms"] / stat["fire_count"], 2)

    def get_telemetry_snapshot(self) -> Dict[str, Any]:
        """Provides thread-safe state inspection dictionary for Streamlit Challenge CPN UI."""
        summary = self.reg.get_marking_summary()
        place_order = list(CHALLENGE_PLACE_SPECS.keys())
        marking_vector = [1 if summary.get(p) else 0 for p in place_order]
        return {
            "place_counts": summary,
            "marking_vector": marking_vector,
            "transition_stats": self.transition_stats,
            "transition_specs": CHALLENGE_TRANSITION_SPECS,
            "place_specs": CHALLENGE_PLACE_SPECS,
            "last_plan_id": self._last_plan.plan_id if self._last_plan else None,
            "receipt_id": self._last_receipt.transaction_id if self._last_receipt else None,
        }

    @property
    def last_plan(self) -> Optional[Color_ChallengePlan]:
        """Returns the most recent solved challenge plan token."""
        return self._last_plan

    @property
    def last_validation(self) -> Optional[Color_ChallengeValidation]:
        """Returns the most recent model validation token."""
        return self._last_validation

    @property
    def last_validation_report(self) -> Optional[Any]:
        """Returns the underlying ModelValidationReport if validation occurred."""
        return self._last_validation.report if self._last_validation else None

    @property
    def last_receipt(self) -> Optional[Color_ChallengeReceipt]:
        """Returns the terminal Saga execution receipt token."""
        return self._last_receipt

    async def run_pipeline(
        self,
        gameweek: int = 5,
        entry_id: int = 6173410,
        archetype: str = "max_ev",
        preset_key: Optional[str] = None,
        n_simulations: int = 2500,
        lock_players: Optional[List[str]] = None,
        exclude_players: Optional[List[str]] = None,
        available_only: bool = True,
        auth_headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        verification_delay_seconds: float = 0.5,
        players_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Executes the full Challenge CPN pipeline end-to-end:
        1. Ingests weekly rules (API or preset).
        2. Ingests player pool and fixture data.
        3. Ingests current manager challenge lineup.
        4. Runs modular ChallengePicker to select designated crowned archetype.
        5. Compares candidate against config.yaml settings and asserts model invariants.
        6. Submits lineup via Saga transaction.
        7. Verifies that live team state matches planned picks, retrying up to max_retries on drop.
        """
        start_t = time.perf_counter()
        logger.info(
            "[ChallengeCPNEngine] Starting pipeline for GW%d | Entry: %d | Archetype: %s | DryRun: %s",
            gameweek, entry_id, archetype, self.dry_run
        )

        try:
            # 1. Fetch Challenge Rules
            t0 = time.perf_counter()
            await self.transitions.fire_fetch_rules(gameweek=gameweek, preset_key=preset_key)
            self._record_transition_stat("T_FETCH_CHALLENGE_RULES", "ALIVE_FIRED", (time.perf_counter() - t0) * 1000.0)

            # 2. Ingest Market
            t0 = time.perf_counter()
            await self.transitions.fire_ingest_market(gameweek=gameweek, players_df=players_df)
            self._record_transition_stat("T_INGEST_CHALLENGE_MARKET", "ALIVE_FIRED", (time.perf_counter() - t0) * 1000.0)

            # 3. Fetch Current Team
            t0 = time.perf_counter()
            await self.transitions.fire_fetch_current_team(entry_id=entry_id, auth_headers=auth_headers)
            self._record_transition_stat("T_FETCH_CURRENT_TEAM", "ALIVE_FIRED", (time.perf_counter() - t0) * 1000.0)

            # 4. Solve Optimal Candidate via ChallengePicker
            picker_cfg = ChallengePickerConfig(
                archetype=archetype,
                n_simulations=n_simulations,
                lock_players=lock_players,
                exclude_players=exclude_players,
                available_only=available_only
            )
            t0 = time.perf_counter()
            plan = await self.transitions.fire_solve_picker(config=picker_cfg)
            self._last_plan = plan
            self._record_transition_stat("T_RUN_CHALLENGE_PICKER", "ALIVE_FIRED", (time.perf_counter() - t0) * 1000.0)

            # 5. Validate Model Settings & Drift Invariants
            t0 = time.perf_counter()
            validation = await self.transitions.fire_validate_model()
            self._last_validation = validation
            val_lat = (time.perf_counter() - t0) * 1000.0

            if not validation.is_valid:
                self._record_transition_stat("T_VALIDATE_MODEL_SETTINGS", "BLOCKED", val_lat)
                logger.error("[ChallengeCPNEngine] Pipeline halted: Model validation errors: %s", validation.report.errors)
                return self._build_result_summary(False, start_t, error=f"Model validation failed: {validation.report.errors}")
            self._record_transition_stat("T_VALIDATE_MODEL_SETTINGS", "ALIVE_FIRED", val_lat)

            # 6. Saga Submission
            t0 = time.perf_counter()
            await self.transitions.fire_saga_submit(auth_headers=auth_headers, max_retries=max_retries)
            self._record_transition_stat("T_SAGA_SUBMIT", "ALIVE_FIRED", (time.perf_counter() - t0) * 1000.0)

            # 7. Saga Verification Loop (Handles Automatic Retries with Exponential Backoff)
            receipt: Optional[Color_ChallengeReceipt] = None
            while True:
                t0 = time.perf_counter()
                outcome = await self.transitions.fire_saga_verify(
                    auth_headers=auth_headers,
                    verification_delay_seconds=verification_delay_seconds
                )
                v_lat = (time.perf_counter() - t0) * 1000.0

                if isinstance(outcome, Color_ChallengeReceipt):
                    self._record_transition_stat("T_SAGA_VERIFY", "ALIVE_FIRED", v_lat)
                    receipt = outcome
                    self._last_receipt = receipt
                    logger.info("[ChallengeCPNEngine] Pipeline COMPLETED successfully! Receipt: %s", receipt.transaction_id)
                    break

                if isinstance(outcome, Color_ChallengeSagaToken):
                    if outcome.status == SagaStatus.RETRY_PENDING:
                        self._record_transition_stat("T_SAGA_VERIFY", "RETRYING", v_lat)
                        # Re-fire submit for next retry attempt
                        t_sub0 = time.perf_counter()
                        await self.transitions.fire_saga_submit(saga_token=outcome, auth_headers=auth_headers, max_retries=max_retries)
                        self._record_transition_stat("T_SAGA_SUBMIT", "ALIVE_FIRED", (time.perf_counter() - t_sub0) * 1000.0)
                        continue
                    elif outcome.status == SagaStatus.COMPENSATED:
                        self._record_transition_stat("T_SAGA_VERIFY", "COMPENSATED", v_lat)
                        logger.error("[ChallengeCPNEngine] Pipeline routed to compensation state. Submission dropped.")
                        return self._build_result_summary(False, start_t, error="Saga verification failed after retries.")

            return self._build_result_summary(True, start_t, receipt=receipt)

        except Exception as e:
            logger.exception("[ChallengeCPNEngine] Unhandled exception in CPN execution: %s", e)
            return self._build_result_summary(False, start_t, error=str(e))

    def _build_result_summary(
        self,
        success: bool,
        start_time: float,
        receipt: Optional[Color_ChallengeReceipt] = None,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """Constructs a comprehensive, serializable execution summary."""
        dur_ms = (time.perf_counter() - start_time) * 1000.0
        alerts = self.reg.P_ALERTS.snapshot()

        summary: Dict[str, Any] = {
            "success": success,
            "duration_ms": round(dur_ms, 2),
            "dry_run": self.dry_run,
            "markings": self.reg.get_marking_summary(),
            "snapshot": self.get_telemetry_snapshot(),
            "error": error,
            "alert_count": len(alerts),
            "alerts": [{"level": a.level, "source": a.source_transition, "message": a.message} for a in alerts],
        }

        if self._last_plan:
            p = self._last_plan
            res = p.picker_result
            summary["plan"] = {
                "plan_id": p.plan_id,
                "archetype": p.archetype,
                "squad": res.selected_squad.squad_names,
                "captain": res.selected_squad.captain,
                "vice_captain": res.selected_squad.vice_captain,
                "expected_utility": round(p.expected_utility, 1),
                "tournament_p99": round(p.tournament_p99, 1),
                "picks_count": len(res.element_ids)
            }

        if self._last_validation:
            v = self._last_validation
            summary["validation"] = v.report.to_dict()

        if receipt:
            summary["receipt"] = {
                "transaction_id": receipt.transaction_id,
                "entry_id": receipt.entry_id,
                "gameweek": receipt.gameweek,
                "verified": receipt.verified,
                "attempts_required": receipt.attempts_required,
                "element_ids": receipt.element_ids,
                "captain_id": receipt.captain_id,
                "vice_captain_id": receipt.vice_captain_id,
            }

        current_team = self.reg.P_CURRENT_TEAM.peek()
        if current_team and self._last_plan:
            initial_ids = set(current_team.element_ids)
            new_ids = set(self._last_plan.picker_result.element_ids)
            summary["amendment_delta"] = {
                "initial_element_ids": current_team.element_ids,
                "initial_captain_id": current_team.captain_id,
                "initial_vice_captain_id": current_team.vice_captain_id,
                "transfers_in": list(new_ids - initial_ids),
                "transfers_out": list(initial_ids - new_ids),
                "is_identical": (initial_ids == new_ids and current_team.captain_id == self._last_plan.picker_result.captain_id and current_team.vice_captain_id == self._last_plan.picker_result.vice_captain_id),
            }

        return summary
