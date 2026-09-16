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
            await self.transitions.fire_fetch_rules(gameweek=gameweek, preset_key=preset_key)

            # 2. Ingest Market
            await self.transitions.fire_ingest_market(gameweek=gameweek, players_df=players_df)

            # 3. Fetch Current Team
            await self.transitions.fire_fetch_current_team(entry_id=entry_id, auth_headers=auth_headers)

            # 4. Solve Optimal Candidate via ChallengePicker
            picker_cfg = ChallengePickerConfig(
                archetype=archetype,
                n_simulations=n_simulations,
                lock_players=lock_players,
                exclude_players=exclude_players,
                available_only=available_only
            )
            plan = await self.transitions.fire_solve_picker(config=picker_cfg)
            self._last_plan = plan

            # 5. Validate Model Settings & Drift Invariants
            validation = await self.transitions.fire_validate_model()
            self._last_validation = validation

            if not validation.is_valid:
                logger.error("[ChallengeCPNEngine] Pipeline halted: Model validation errors: %s", validation.report.errors)
                return self._build_result_summary(False, start_t, error=f"Model validation failed: {validation.report.errors}")

            # 6. Saga Submission
            await self.transitions.fire_saga_submit(auth_headers=auth_headers, max_retries=max_retries)

            # 7. Saga Verification Loop (Handles Automatic Retries with Exponential Backoff)
            receipt: Optional[Color_ChallengeReceipt] = None
            while True:
                outcome = await self.transitions.fire_saga_verify(
                    auth_headers=auth_headers,
                    verification_delay_seconds=verification_delay_seconds
                )

                if isinstance(outcome, Color_ChallengeReceipt):
                    receipt = outcome
                    self._last_receipt = receipt
                    logger.info("[ChallengeCPNEngine] Pipeline COMPLETED successfully! Receipt: %s", receipt.transaction_id)
                    break

                if isinstance(outcome, Color_ChallengeSagaToken):
                    if outcome.status == SagaStatus.RETRY_PENDING:
                        # Re-fire submit for next retry attempt
                        await self.transitions.fire_saga_submit(saga_token=outcome, auth_headers=auth_headers, max_retries=max_retries)
                        continue
                    elif outcome.status == SagaStatus.COMPENSATED:
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
