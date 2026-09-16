"""
tests/test_challenge_cpn.py
Unit and integration tests for the autonomous Challenge Coloured Petri Net (CPN):
- Colored tokens and Place markings.
- Invariant transition guards (guard_can_solve, guard_validation_passed, guard_saga_verify, retry guards).
- End-to-end dry-run CPN pipeline execution.
- Chaos drill: Simulating dropped submission and verifying that the Saga retry loop recovers on attempt 2.
"""

import pytest
import asyncio
import pandas as pd
from unittest.mock import patch, MagicMock

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
from automation.challenge_cpn.engine import ChallengeCPNEngine
from analytics.challenge.rule_extractor import CHALLENGE_PRESETS
from clients.fpl_challenge_client import FPLChallengeClient


@pytest.fixture
def sample_players_df() -> pd.DataFrame:
    """Fixture providing a diverse player pool with element IDs and club metadata."""
    return pd.DataFrame([
        {"id": 103, "web_name": "Saliba", "position": "DEF", "club_name": "Arsenal", "club": "Arsenal", "now_cost": 6.0, "xP": 4.5, "threat": 10, "status": "a"},
        {"id": 303, "web_name": "Alexander-Arnold", "position": "DEF", "club_name": "Liverpool", "club": "Liverpool", "now_cost": 7.0, "xP": 5.2, "threat": 30, "status": "a"},
        {"id": 101, "web_name": "Saka", "position": "MID", "club_name": "Arsenal", "club": "Arsenal", "now_cost": 10.0, "xP": 6.5, "threat": 60, "status": "a"},
        {"id": 401, "web_name": "Palmer", "position": "MID", "club_name": "Chelsea", "club": "Chelsea", "now_cost": 10.5, "xP": 7.2, "threat": 70, "status": "a"},
        {"id": 201, "web_name": "Haaland", "position": "FWD", "club_name": "Man City", "club": "Man City", "now_cost": 15.0, "xP": 8.5, "threat": 90, "status": "a"},
        {"id": 501, "web_name": "Watkins", "position": "FWD", "club_name": "Aston Villa", "club": "Aston Villa", "now_cost": 9.0, "xP": 6.0, "threat": 60, "status": "a"},
        {"id": 601, "web_name": "Son", "position": "MID", "club_name": "Spurs", "club": "Spurs", "now_cost": 10.0, "xP": 6.8, "threat": 65, "status": "a"},
        {"id": 603, "web_name": "Porro", "position": "DEF", "club_name": "Spurs", "club": "Spurs", "now_cost": 5.5, "xP": 4.4, "threat": 20, "status": "a"},
    ])


def test_cpn_token_immutability_and_marking(sample_players_df):
    """Verify CPN tokens and marking data structures."""
    rule_preset = CHALLENGE_PRESETS["gw5_one_player_per_club"]
    rule_token = Color_ChallengeRule(
        gameweek=5,
        name="GW5 Preset",
        rule_set=rule_preset
    )
    assert rule_token.name == "GW5 Preset"
    assert rule_token.rule_set.squad_size == 6

    market_token = Color_ChallengeMarket(
        elements_df=sample_players_df,
        fixtures=[],
        gameweek=5
    )
    assert len(market_token.elements_df) == len(sample_players_df)

    registry = ChallengeMarkingRegistry()
    summary = registry.get_marking_summary()
    assert summary["P_CHALLENGE_RULES_READY"] is False

    registry.P_RULES_READY._value = rule_token
    summary_updated = registry.get_marking_summary()
    assert summary_updated["P_CHALLENGE_RULES_READY"] is True


def test_cpn_guards_logic(sample_players_df):
    """Verify functional invariant guard expressions."""
    rule_preset = CHALLENGE_PRESETS["gw5_one_player_per_club"]
    rule_token = Color_ChallengeRule(
        gameweek=5,
        name="GW5 Preset",
        rule_set=rule_preset
    )
    market_token = Color_ChallengeMarket(
        elements_df=sample_players_df,
        fixtures=[],
        gameweek=5
    )
    current_team = Color_ChallengeSquadState(
        entry_id=6173410,
        picks=[],
        captain_id=0,
        vice_captain_id=0,
        element_ids=[]
    )

    # guard_can_solve
    assert guard_can_solve(rule_token, market_token, current_team) is True
    assert guard_can_solve(None, market_token, current_team) is False
    assert guard_can_solve(rule_token, None, current_team) is False
    assert guard_can_solve(rule_token, market_token, None) is False

    # guard_validation_passed
    report_pass = MagicMock()
    report_pass.is_valid = True
    val_pass = Color_ChallengeValidation(
        plan_id="plan_123",
        report=report_pass,
        is_valid=True,
        error_count=0,
        warning_count=0
    )
    report_fail = MagicMock()
    report_fail.is_valid = False
    val_fail = Color_ChallengeValidation(
        plan_id="plan_123",
        report=report_fail,
        is_valid=False,
        error_count=1,
        warning_count=0
    )
    assert guard_validation_passed(val_pass) is True
    assert guard_validation_passed(val_fail) is False

    # guard_saga_verify
    saga_token = MagicMock()
    saga_token.expected_element_ids = [101, 201, 301]
    saga_token.expected_captain_id = 201
    saga_token.expected_vice_captain_id = 101

    matching_team = {
        "picks": [
            {"element": 101, "is_captain": False, "is_vice_captain": True},
            {"element": 201, "is_captain": True, "is_vice_captain": False},
            {"element": 301, "is_captain": False, "is_vice_captain": False},
        ]
    }
    mismatch_team = {
        "picks": [
            {"element": 101, "is_captain": False, "is_vice_captain": True},
            {"element": 999, "is_captain": True, "is_vice_captain": False},  # Mismatched element!
            {"element": 301, "is_captain": False, "is_vice_captain": False},
        ]
    }
    is_verified_match, diff_match = guard_saga_verify(saga_token, matching_team)
    assert is_verified_match is True
    assert diff_match.get("missing_elements") == []
    assert diff_match.get("captain_mismatch") is False

    is_verified_mismatch, diff_mismatch = guard_saga_verify(saga_token, mismatch_team)
    assert is_verified_mismatch is False
    assert len(diff_mismatch.get("missing_elements", [])) > 0 or diff_mismatch.get("captain_mismatch") is True

    # Retry guards
    token_retry = MagicMock()
    token_retry.attempt = 1
    token_retry.max_retries = 3
    assert guard_can_retry(token_retry) is True

    token_exhausted = MagicMock()
    token_exhausted.attempt = 3
    token_exhausted.max_retries = 3
    assert guard_can_retry(token_exhausted) is False
    assert guard_retries_exhausted(token_exhausted) is True


def test_cpn_engine_dry_run_pipeline(sample_players_df, tmp_path):
    """Verify autonomous end-to-end Challenge CPN pipeline execution in dry-run mode."""
    journal = ChallengeCPNDiagnosticJournal(log_dir=str(tmp_path))

    engine = ChallengeCPNEngine(
        journal=journal,
        dry_run=True,
    )

    result = asyncio.run(engine.run_pipeline(
        players_df=sample_players_df,
        preset_key="gw5_one_player_per_club",
        archetype="max_ev",
        n_simulations=300,
        max_retries=3,
        verification_delay_seconds=0.01,
    ))

    assert result["success"] is True
    assert result["dry_run"] is True
    assert "plan" in result
    assert "receipt" in result

    receipt_info = result["receipt"]
    assert receipt_info["verified"] is True
    assert receipt_info["attempts_required"] == 1
    assert receipt_info["gameweek"] == 5
    assert len(receipt_info["element_ids"]) == 6

    # Verify Journal logged execution entries
    logs = journal.tail(20)
    assert len(logs) >= 5
    record_types = [entry.get("record_type") for entry in logs]
    assert "transition_firing" in record_types
    assert "saga_step" in record_types


def test_cpn_saga_retry_loop_recovery(sample_players_df, tmp_path):
    """
    Chaos Test:
    Simulate a dropped submission on attempt 1 (e.g. FPL API race condition or dropped packet).
    Verify that the Saga verification guard detects the mismatch, initiates a retry with backoff,
    and successfully confirms on attempt 2.
    """
    journal = ChallengeCPNDiagnosticJournal(log_dir=str(tmp_path))

    engine = ChallengeCPNEngine(
        journal=journal,
        dry_run=True,
    )

    call_count = {"calls": 0}
    original_get_my_team = FPLChallengeClient.get_my_team

    def mock_get_my_team(client_self, *args, **kwargs):
        call_count["calls"] += 1
        # Call 1: fire_fetch_current_team -> initial baseline squad
        # Call 2: fire_saga_verify (attempt 1) -> simulate dropped state
        # Call 3: fire_saga_verify (attempt 2) -> actual updated squad (recovery)
        if call_count["calls"] == 2:
            return {"picks": []}
        return original_get_my_team(client_self, *args, **kwargs)

    with patch.object(FPLChallengeClient, "get_my_team", mock_get_my_team):
        result = asyncio.run(engine.run_pipeline(
            players_df=sample_players_df,
            preset_key="gw5_one_player_per_club",
            archetype="max_ev",
            n_simulations=300,
            max_retries=3,
            verification_delay_seconds=0.01  # Fast test backoff
        ))

    # Assert recovery on attempt 2
    assert result["success"] is True
    receipt_info = result["receipt"]
    assert receipt_info["verified"] is True
    assert receipt_info["attempts_required"] == 2, "Should recover and confirm on attempt 2"
    assert call_count["calls"] >= 3

    # Verify Journal contains SUBMITTED, MISMATCH, and VERIFIED
    logs = journal.tail(30)
    saga_events = [e["data"] for e in logs if e.get("record_type") == "saga_step"]
    statuses = [s.get("status") for s in saga_events]
    assert "MISMATCH" in statuses
    assert "VERIFIED" in statuses
    assert statuses.count("SUBMITTED") == 2, "Both initial submit and retry submit must be recorded"
