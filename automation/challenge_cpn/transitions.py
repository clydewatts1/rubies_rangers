"""
automation/challenge_cpn/transitions.py
Transition firing logic for the FPL Challenge Coloured Petri Net.
Executes rule resolution, market ingestion, modular picking, model validation,
and the Saga submission & verification loop with exponential backoff retries.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import pandas as pd

from analytics.challenge.contracts import ChallengeRuleSet
from analytics.challenge.rule_extractor import (
    get_available_challenge_presets,
    extract_rules_from_event,
)
from analytics.challenge.picker import ChallengePicker, ChallengePickerConfig, ChallengePickerResult
from analytics.challenge.model_validator import ChallengeModelValidator, ModelValidationReport
from clients.fpl_challenge_client import FPLChallengeClient
from clients.fpl_client import FPLClient
from automation.challenge_cpn.tokens import (
    Color_ChallengeRule,
    Color_ChallengeMarket,
    Color_ChallengeSquadState,
    Color_ChallengePlan,
    Color_ChallengeValidation,
    Color_ChallengeSagaToken,
    Color_ChallengeReceipt,
    Color_ChallengeAlert,
    SagaStatus,
)
from automation.challenge_cpn.places import ChallengeMarkingRegistry
from automation.challenge_cpn.guards import (
    guard_can_solve,
    guard_validation_passed,
    guard_saga_verify,
    guard_can_retry,
    guard_retries_exhausted,
)
from automation.challenge_cpn.diagnostics import ChallengeCPNDiagnosticJournal

logger = logging.getLogger("rubies_rangers.challenge.transitions")


class ChallengeTransitions:
    """Encapsulates all transition executors for the Challenge CPN."""

    def __init__(
        self,
        registry: ChallengeMarkingRegistry,
        journal: ChallengeCPNDiagnosticJournal,
        challenge_client: Optional[FPLChallengeClient] = None,
        fpl_client: Optional[FPLClient] = None,
        dry_run: bool = True
    ) -> None:
        self.reg = registry
        self.journal = journal
        self.challenge_client = challenge_client or FPLChallengeClient()
        self.fpl_client = fpl_client or FPLClient()
        self.dry_run = dry_run

    # ------------------------------------------------------------------
    # 1. T_FETCH_CHALLENGE_RULES
    # ------------------------------------------------------------------
    async def fire_fetch_rules(self, gameweek: int, preset_key: Optional[str] = None) -> Color_ChallengeRule:
        """Fetches active Challenge rules from official API or specified preset."""
        start_t = time.perf_counter()
        presets = get_available_challenge_presets()
        rule_set: ChallengeRuleSet

        if preset_key and preset_key in presets:
            rule_set = presets[preset_key]
            source = f"Preset: {preset_key}"
        else:
            try:
                bootstrap = self.challenge_client.get_challenge_bootstrap()
                events = bootstrap.get("events", [])
                curr_ev = next((e for e in events if e.get("id") == gameweek or e.get("is_current")), events[0] if events else {})
                rule_set = extract_rules_from_event(curr_ev)
                source = "Live Challenge API"
            except Exception as e:
                logger.warning("[Transitions:T_FETCH_RULES] API fetch failed (%s); using preset fallback.", e)
                rule_set = presets.get("gw5_one_player_per_club") or presets[list(presets.keys())[0]]
                source = "Fallback Preset"

        token = Color_ChallengeRule(gameweek=gameweek, name=rule_set.name, rule_set=rule_set)
        await self.reg.P_RULES_READY.update(token)
        dur = (time.perf_counter() - start_t) * 1000.0

        self.journal.record_transition("T_FETCH_CHALLENGE_RULES", "SUCCESS", dur, {
            "gameweek": gameweek,
            "rule_name": rule_set.name,
            "squad_size": rule_set.squad_size,
            "max_per_team": rule_set.max_per_team,
            "budget_cap": rule_set.budget_cap,
            "source": source
        })
        logger.info("[T_FETCH_CHALLENGE_RULES] Loaded '%s' (N=%d, C=%d) in %.1fms", rule_set.name, rule_set.squad_size, rule_set.max_per_team, dur)
        return token

    # ------------------------------------------------------------------
    # 2. T_INGEST_CHALLENGE_MARKET
    # ------------------------------------------------------------------
    async def fire_ingest_market(self, gameweek: int, players_df: Optional[pd.DataFrame] = None) -> Color_ChallengeMarket:
        """Ingests player pool, fixtures, and odds."""
        start_t = time.perf_counter()
        df = players_df if players_df is not None else self.fpl_client.get_players_df()
        fixtures = self.challenge_client.get_fixtures(gameweek=gameweek)

        token = Color_ChallengeMarket(elements_df=df, fixtures=fixtures, gameweek=gameweek)
        await self.reg.P_MARKET_READY.update(token)
        dur = (time.perf_counter() - start_t) * 1000.0

        self.journal.record_transition("T_INGEST_CHALLENGE_MARKET", "SUCCESS", dur, {
            "gameweek": gameweek,
            "players_count": len(df),
            "fixtures_count": len(fixtures)
        })
        logger.info("[T_INGEST_CHALLENGE_MARKET] Ingested %d players, %d fixtures in %.1fms", len(df), len(fixtures), dur)
        return token

    # ------------------------------------------------------------------
    # 3. T_FETCH_CURRENT_TEAM
    # ------------------------------------------------------------------
    async def fire_fetch_current_team(self, entry_id: int, auth_headers: Optional[Dict[str, str]] = None) -> Color_ChallengeSquadState:
        """Fetches manager's current challenge squad."""
        start_t = time.perf_counter()
        team_data = self.challenge_client.get_my_team(entry_id=entry_id, auth_headers=auth_headers)
        picks = team_data.get("picks", [])

        element_ids = [int(p.get("element", 0)) for p in picks]
        cap = next((int(p.get("element", 0)) for p in picks if p.get("is_captain")), element_ids[0] if element_ids else 0)
        vc = next((int(p.get("element", 0)) for p in picks if p.get("is_vice_captain")), element_ids[1] if len(element_ids) > 1 else cap)

        token = Color_ChallengeSquadState(
            entry_id=entry_id,
            picks=picks,
            captain_id=cap,
            vice_captain_id=vc,
            element_ids=element_ids,
            is_live=bool(auth_headers and not self.dry_run)
        )
        await self.reg.P_CURRENT_TEAM.update(token)
        dur = (time.perf_counter() - start_t) * 1000.0

        self.journal.record_transition("T_FETCH_CURRENT_TEAM", "SUCCESS", dur, {
            "entry_id": entry_id,
            "picks_count": len(picks),
            "captain_id": cap,
            "vice_captain_id": vc
        })
        logger.info("[T_FETCH_CURRENT_TEAM] Ingested team for Entry %d (picks: %d) in %.1fms", entry_id, len(picks), dur)
        return token

    # ------------------------------------------------------------------
    # 4. T_RUN_CHALLENGE_PICKER
    # ------------------------------------------------------------------
    async def fire_solve_picker(self, config: Optional[ChallengePickerConfig] = None) -> Color_ChallengePlan:
        """Invokes the modular ChallengePicker to generate optimal crowned candidate."""
        start_t = time.perf_counter()
        rules_token = await self.reg.P_RULES_READY.read()
        market_token = await self.reg.P_MARKET_READY.read()
        team_token = await self.reg.P_CURRENT_TEAM.read()

        if not guard_can_solve(rules_token, market_token, team_token):
            raise RuntimeError("Guard condition failed for T_RUN_CHALLENGE_PICKER: Incomplete net markings.")

        cfg = config or ChallengePickerConfig()
        picker_result = ChallengePicker.pick_challenge_squad(
            players_df=market_token.elements_df,
            rule_set=rules_token.rule_set,
            fixtures=market_token.fixtures,
            config=cfg
        )

        plan_id = f"challenge_plan_{uuid.uuid4().hex[:8]}"
        plan_token = Color_ChallengePlan(
            picker_result=picker_result,
            archetype=picker_result.archetype_chosen,
            gameweek=rules_token.gameweek,
            expected_utility=picker_result.evaluated_candidate.mean_points,
            tournament_p99=picker_result.evaluated_candidate.tournament_p99,
            plan_id=plan_id
        )

        await self.reg.P_OPTIMIZED.put(plan_token)
        dur = (time.perf_counter() - start_t) * 1000.0

        self.journal.record_transition("T_RUN_CHALLENGE_PICKER", "SUCCESS", dur, {
            "plan_id": plan_id,
            "archetype": picker_result.archetype_chosen,
            "mean_points": picker_result.evaluated_candidate.mean_points,
            "tournament_p99": picker_result.evaluated_candidate.tournament_p99,
            "squad": picker_result.selected_squad.squad_names,
            "captain": picker_result.selected_squad.captain
        })
        logger.info("[T_RUN_CHALLENGE_PICKER] Generated %s in %.1fms", plan_token.plan_id, dur)
        return plan_token

    # ------------------------------------------------------------------
    # 5. T_VALIDATE_MODEL_SETTINGS
    # ------------------------------------------------------------------
    async def fire_validate_model(self) -> Color_ChallengeValidation:
        """Validates picker output against config.yaml settings and invariants."""
        start_t = time.perf_counter()
        plan = await self.reg.P_OPTIMIZED.get()
        self.reg.P_OPTIMIZED.task_done()

        rules_token = await self.reg.P_RULES_READY.read()
        report = ChallengeModelValidator.validate(plan.picker_result, rules_token.rule_set)

        validation_token = Color_ChallengeValidation(
            plan_id=plan.plan_id,
            report=report,
            is_valid=report.is_valid,
            error_count=len(report.errors),
            warning_count=len(report.warnings)
        )

        self.journal.record_model_validation(
            plan_id=plan.plan_id,
            is_valid=report.is_valid,
            error_count=len(report.errors),
            warning_count=len(report.warnings),
            errors=report.errors,
            warnings=report.warnings,
            setting_comparison=report.setting_comparison
        )

        await self.reg.P_VALIDATED.put(validation_token)
        dur = (time.perf_counter() - start_t) * 1000.0

        if not report.is_valid:
            alert = Color_ChallengeAlert(
                level="CRITICAL",
                source_transition="T_VALIDATE_MODEL_SETTINGS",
                message=f"Model validation failed with {len(report.errors)} constraint error(s)",
                context={"errors": report.errors}
            )
            await self.reg.P_ALERTS.put(alert)
            self.journal.record_alert("CRITICAL", "T_VALIDATE_MODEL_SETTINGS", alert.message, alert.context)
            logger.error("[T_VALIDATE_MODEL_SETTINGS] Validation failed: %s", report.errors)
        else:
            self.journal.record_transition("T_VALIDATE_MODEL_SETTINGS", "SUCCESS", dur, {
                "plan_id": plan.plan_id,
                "checks_passed": len(report.checks_passed),
                "warnings": len(report.warnings)
            })
            logger.info("[T_VALIDATE_MODEL_SETTINGS] Validation PASSED for %s in %.1fms", plan.plan_id, dur)

        # Store plan in temporary state place for saga submission
        self._current_plan = plan
        return validation_token

    # ------------------------------------------------------------------
    # 6. T_SAGA_SUBMIT
    # ------------------------------------------------------------------
    async def fire_saga_submit(
        self,
        saga_token: Optional[Color_ChallengeSagaToken] = None,
        auth_headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3
    ) -> Color_ChallengeSagaToken:
        """Transmits the Challenge lineup payload to the client."""
        start_t = time.perf_counter()
        team_token = await self.reg.P_CURRENT_TEAM.read()
        entry_id = team_token.entry_id if team_token else 6173410

        if saga_token is None:
            # First attempt
            validation = await self.reg.P_VALIDATED.get()
            self.reg.P_VALIDATED.task_done()
            if not guard_validation_passed(validation):
                raise ValueError("Cannot submit: Model validation failed.")

            plan = getattr(self, "_current_plan", None)
            if not plan:
                raise RuntimeError("No active plan found for submission.")

            res = plan.picker_result
            # Inspect initial team state from P_CURRENT_TEAM before submitting amendment
            current_team = await self.reg.P_CURRENT_TEAM.read()
            if current_team and current_team.element_ids:
                initial_ids = set(current_team.element_ids)
                new_ids = set(res.element_ids)
                transfers_in = list(new_ids - initial_ids)
                transfers_out = list(initial_ids - new_ids)
                cap_changed = (current_team.captain_id != res.captain_id)
                vc_changed = (current_team.vice_captain_id != res.vice_captain_id)
                is_noop = (not transfers_in and not transfers_out and not cap_changed and not vc_changed)
                logger.info(
                    "[T_SAGA_SUBMIT] Initial lineup vs amendment delta: +%d in, -%d out | C: %s->%s | VC: %s->%s (Identical: %s)",
                    len(transfers_in), len(transfers_out),
                    current_team.captain_id, res.captain_id,
                    current_team.vice_captain_id, res.vice_captain_id,
                    is_noop
                )

            tx_id = f"tx_challenge_{uuid.uuid4().hex[:8]}"
            token = Color_ChallengeSagaToken(
                transaction_id=tx_id,
                plan_id=plan.plan_id,
                entry_id=entry_id,
                attempt=1,
                max_retries=max_retries,
                status=SagaStatus.INITIATED,
                payload=res.picks_payload,
                expected_element_ids=res.element_ids,
                expected_captain_id=res.captain_id,
                expected_vice_captain_id=res.vice_captain_id
            )
        else:
            token = saga_token

        # Execute submission
        resp = self.challenge_client.post_challenge_team(
            entry_id=token.entry_id,
            payload=token.payload,
            auth_headers=auth_headers,
            dry_run=self.dry_run
        )

        submitted_token = Color_ChallengeSagaToken(
            transaction_id=token.transaction_id,
            plan_id=token.plan_id,
            entry_id=token.entry_id,
            attempt=token.attempt,
            max_retries=token.max_retries,
            status=SagaStatus.SUBMITTED,
            payload=token.payload,
            expected_element_ids=token.expected_element_ids,
            expected_captain_id=token.expected_captain_id,
            expected_vice_captain_id=token.expected_vice_captain_id,
            last_response=resp
        )

        await self.reg.P_VERIFYING.put(submitted_token)
        dur = (time.perf_counter() - start_t) * 1000.0

        self.journal.record_saga_step(
            transaction_id=token.transaction_id,
            attempt=token.attempt,
            max_retries=token.max_retries,
            action="SUBMIT_LINEUP",
            status="SUBMITTED",
            error_message=resp.get("error") if resp.get("status_code", 200) >= 400 else None
        )
        logger.info("[T_SAGA_SUBMIT] Attempt %d/%d submitted (HTTP %s) in %.1fms",
                    token.attempt, token.max_retries, resp.get("status_code"), dur)
        return submitted_token

    # ------------------------------------------------------------------
    # 7. T_SAGA_VERIFY (Verification & Automatic Retry Loop)
    # ------------------------------------------------------------------
    async def fire_saga_verify(
        self,
        auth_headers: Optional[Dict[str, str]] = None,
        verification_delay_seconds: float = 0.5
    ) -> Color_ChallengeReceipt | Color_ChallengeSagaToken:
        """
        Verifies that submitted lineup changes took effect on FPL Challenge servers.
        If verified: generates confirmed receipt and moves to P_CONFIRMED.
        If mismatch: re-queues to P_SUBMITTING with exponential backoff or fails to P_COMPENSATION.
        """
        start_t = time.perf_counter()
        saga_token = await self.reg.P_VERIFYING.get()
        self.reg.P_VERIFYING.task_done()

        if verification_delay_seconds > 0:
            await asyncio.sleep(verification_delay_seconds)

        # Query live state from client
        live_team = self.challenge_client.get_my_team(entry_id=saga_token.entry_id, auth_headers=auth_headers)
        is_match, diff = guard_saga_verify(saga_token, live_team)

        dur = (time.perf_counter() - start_t) * 1000.0

        if is_match:
            receipt = Color_ChallengeReceipt(
                transaction_id=saga_token.transaction_id,
                entry_id=saga_token.entry_id,
                gameweek=getattr(self, "_current_plan", None).gameweek if getattr(self, "_current_plan", None) else 5,
                element_ids=saga_token.expected_element_ids,
                captain_id=saga_token.expected_captain_id,
                vice_captain_id=saga_token.expected_vice_captain_id,
                http_status=200,
                attempts_required=saga_token.attempt,
                verified=True
            )
            await self.reg.P_CONFIRMED.put(receipt)

            self.journal.record_saga_step(
                transaction_id=saga_token.transaction_id,
                attempt=saga_token.attempt,
                max_retries=saga_token.max_retries,
                action="VERIFY_PICKS",
                status="VERIFIED",
                diff=diff
            )
            self.journal.record_receipt({
                "transaction_id": receipt.transaction_id,
                "entry_id": receipt.entry_id,
                "attempts_required": receipt.attempts_required,
                "captain_id": receipt.captain_id,
                "element_ids": receipt.element_ids
            })
            logger.info("[T_SAGA_VERIFY] Lineup VERIFIED on Attempt %d! Receipt created.", saga_token.attempt)
            return receipt

        # Verification failed / mismatch detected
        self.journal.record_saga_step(
            transaction_id=saga_token.transaction_id,
            attempt=saga_token.attempt,
            max_retries=saga_token.max_retries,
            action="VERIFY_PICKS",
            status="MISMATCH",
            diff=diff
        )

        if guard_can_retry(saga_token):
            backoff_secs = 0.5 * (2 ** saga_token.attempt)
            logger.warning("[T_SAGA_VERIFY] Mismatch on attempt %d/%d; scheduling retry after %.1fs backoff...",
                           saga_token.attempt, saga_token.max_retries, backoff_secs)
            await asyncio.sleep(backoff_secs)

            retry_token = Color_ChallengeSagaToken(
                transaction_id=saga_token.transaction_id,
                plan_id=saga_token.plan_id,
                entry_id=saga_token.entry_id,
                attempt=saga_token.attempt + 1,
                max_retries=saga_token.max_retries,
                status=SagaStatus.RETRY_PENDING,
                payload=saga_token.payload,
                expected_element_ids=saga_token.expected_element_ids,
                expected_captain_id=saga_token.expected_captain_id,
                expected_vice_captain_id=saga_token.expected_vice_captain_id,
                verification_diff=diff
            )
            await self.reg.P_SUBMITTING.put(retry_token)
            return retry_token
        else:
            # Retries exhausted -> Compensation
            logger.error("[T_SAGA_VERIFY] Retries exhausted (%d/%d)! Routing to P_CHALLENGE_COMPENSATION.",
                         saga_token.attempt, saga_token.max_retries)
            failed_token = Color_ChallengeSagaToken(
                transaction_id=saga_token.transaction_id,
                plan_id=saga_token.plan_id,
                entry_id=saga_token.entry_id,
                attempt=saga_token.attempt,
                max_retries=saga_token.max_retries,
                status=SagaStatus.COMPENSATED,
                payload=saga_token.payload,
                expected_element_ids=saga_token.expected_element_ids,
                expected_captain_id=saga_token.expected_captain_id,
                expected_vice_captain_id=saga_token.expected_vice_captain_id,
                verification_diff=diff,
                error_message="Verification failed after maximum retries."
            )
            await self.reg.P_COMPENSATION.put(failed_token)
            alert = Color_ChallengeAlert(
                level="CRITICAL",
                source_transition="T_SAGA_VERIFY",
                message=f"Challenge submission unverified after {saga_token.attempt} attempts! Live squad did not update.",
                context={"diff": diff}
            )
            await self.reg.P_ALERTS.put(alert)
            self.journal.record_alert("CRITICAL", "T_SAGA_VERIFY", alert.message, alert.context)
            return failed_token
