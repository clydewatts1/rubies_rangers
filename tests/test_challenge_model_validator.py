"""
tests/test_challenge_model_validator.py
Unit tests for the ChallengeModelValidator and ModelValidationReport:
- Checks validation against config.yaml settings and quantitative constraints.
- Verifies budget cap violation detection.
- Verifies max per club limit violation detection.
- Verifies positional quota violation detection.
- Verifies archetype parameter anomaly checks (P99 right-tail sanity, negative bank balance).
"""

import pytest
import pandas as pd

from analytics.challenge.contracts import (
    ChallengeRuleSet,
    ChallengeOptimalSquad,
    EvaluatedChallengeCandidate,
)
from analytics.challenge.rule_extractor import CHALLENGE_PRESETS
from analytics.challenge.picker import ChallengePickerResult
from analytics.challenge.model_validator import (
    ChallengeModelValidator,
    ModelValidationReport,
)


@pytest.fixture
def rule_preset() -> ChallengeRuleSet:
    """GW5 One Player Per Club rule preset (squad_size=6, max_per_team=1, budget_cap=80.0, DEF: 1-3, MID: 1-3, FWD: 1-3)."""
    return CHALLENGE_PRESETS["gw5_one_player_per_club"]


@pytest.fixture
def valid_candidate_eval() -> EvaluatedChallengeCandidate:
    """A valid evaluated challenge candidate (2 DEF, 2 MID, 2 FWD)."""
    squad = ChallengeOptimalSquad(
        gameweek=5,
        squad_names=["Saliba", "Alexander-Arnold", "Saka", "Palmer", "Haaland", "Watkins"],
        captain="Haaland",
        vice_captain="Saka",
        total_cost=60.0,
        bank_remaining=20.0,
        projected_score=42.0,
        clubs_represented=6,
        formation="2-2-2",
        objective_name="max_ev",
    )
    return EvaluatedChallengeCandidate(
        candidate=squad,
        mean_points=42.0,
        floor_p10=30.0,
        median_p50=41.5,
        ceiling_p90=54.0,
        tournament_p99=64.0,
        std_dev=8.5,
        sharpe_ratio=4.9,
        flexibility_score=85.0,
        win_probability_pct=22.5,
    )


@pytest.fixture
def valid_picker_result(rule_preset, valid_candidate_eval) -> ChallengePickerResult:
    """A valid ChallengePickerResult object with 6 distinct clubs and 2 DEF, 2 MID, 2 FWD."""
    elements = [
        {"id": 103, "name": "Saliba", "club": "Arsenal", "position": "DEF", "cost": 6.0, "is_captain": False, "is_vice_captain": False},
        {"id": 303, "name": "Alexander-Arnold", "club": "Liverpool", "position": "DEF", "cost": 7.0, "is_captain": False, "is_vice_captain": False},
        {"id": 101, "name": "Saka", "club": "Arsenal_Midfield_Placeholder", "position": "MID", "cost": 10.0, "is_captain": False, "is_vice_captain": True},
        {"id": 401, "name": "Palmer", "club": "Chelsea", "position": "MID", "cost": 10.5, "is_captain": False, "is_vice_captain": False},
        {"id": 201, "name": "Haaland", "club": "Man City", "position": "FWD", "cost": 15.0, "is_captain": True, "is_vice_captain": False},
        {"id": 501, "name": "Watkins", "club": "Aston Villa", "position": "FWD", "cost": 9.0, "is_captain": False, "is_vice_captain": False},
    ]
    # Update Saka to distinct club for strict max_per_team=1 preset
    elements[2]["club"] = "Spurs"
    elements[2]["name"] = "Son"

    squad = ChallengeOptimalSquad(
        gameweek=5,
        squad_names=["Saliba", "Alexander-Arnold", "Son", "Palmer", "Haaland", "Watkins"],
        captain="Haaland",
        vice_captain="Son",
        total_cost=60.0,
        bank_remaining=20.0,
        projected_score=42.0,
        clubs_represented=6,
        formation="2-2-2",
        objective_name="max_ev",
    )

    eval_cand = EvaluatedChallengeCandidate(
        candidate=squad,
        mean_points=42.0,
        floor_p10=30.0,
        median_p50=41.5,
        ceiling_p90=54.0,
        tournament_p99=64.0,
        std_dev=8.5,
        sharpe_ratio=4.9,
        flexibility_score=85.0,
        win_probability_pct=22.5,
    )

    return ChallengePickerResult(
        selected_squad=squad,
        evaluated_candidate=eval_cand,
        archetype_chosen="max_ev",
        squad_elements=elements,
        element_ids=[e["id"] for e in elements],
        captain_id=201,
        vice_captain_id=101,
        picks_payload={"picks": elements},
        tournament_report=None,
    )


def test_validator_clean_pass(rule_preset, valid_picker_result):
    """Ensure a compliant squad with valid config passes all checks without errors."""
    validator = ChallengeModelValidator()
    report = validator.validate(valid_picker_result, rule_preset)

    assert isinstance(report, ModelValidationReport)
    assert report.is_valid is True
    assert len(report.errors) == 0
    assert report.budget_valid is True
    assert report.club_limits_valid is True
    assert report.position_quotas_valid is True
    assert report.archetype_consistency_valid is True
    assert "VALID" in report.summary_dict["status"]


def test_validator_budget_cap_violation(rule_preset, valid_candidate_eval):
    """Ensure budget overflow is strictly caught and flagged as an error."""
    expensive_elements = [
        {"id": 103, "name": "Saliba", "club": "Arsenal", "position": "DEF", "cost": 15.0, "is_captain": False, "is_vice_captain": False},
        {"id": 303, "name": "Alexander-Arnold", "club": "Liverpool", "position": "DEF", "cost": 15.0, "is_captain": False, "is_vice_captain": False},
        {"id": 601, "name": "Son", "club": "Spurs", "position": "MID", "cost": 15.0, "is_captain": False, "is_vice_captain": True},
        {"id": 401, "name": "Palmer", "club": "Chelsea", "position": "MID", "cost": 15.0, "is_captain": False, "is_vice_captain": False},
        {"id": 201, "name": "Haaland", "club": "Man City", "position": "FWD", "cost": 18.0, "is_captain": True, "is_vice_captain": False},
        {"id": 501, "name": "Watkins", "club": "Aston Villa", "position": "FWD", "cost": 15.0, "is_captain": False, "is_vice_captain": False},
    ]  # Sum = 93.0m > 80.0m limit

    bad_squad = ChallengeOptimalSquad(
        gameweek=5,
        squad_names=[e["name"] for e in expensive_elements],
        captain="Haaland",
        vice_captain="Son",
        total_cost=93.0,
        bank_remaining=-13.0,
        projected_score=45.0,
        clubs_represented=6,
        formation="2-2-2",
        objective_name="max_ev",
    )
    picker_res = ChallengePickerResult(
        selected_squad=bad_squad,
        evaluated_candidate=valid_candidate_eval,
        archetype_chosen="max_ev",
        squad_elements=expensive_elements,
        element_ids=[e["id"] for e in expensive_elements],
        captain_id=201,
        vice_captain_id=601,
        picks_payload={"picks": expensive_elements},
        tournament_report=None,
    )

    budget_rule = CHALLENGE_PRESETS["gw7_penny_pincher"]  # 80.0m limit
    validator = ChallengeModelValidator()
    report = validator.validate(picker_res, budget_rule)

    assert report.is_valid is False
    assert report.budget_valid is False
    assert any("budget" in err.lower() for err in report.errors)


def test_validator_club_limit_violation(rule_preset, valid_candidate_eval):
    """Ensure exceeding max players per club (max_per_team=1 in GW5 preset) is flagged."""
    # 2 Arsenal players selected (Saliba + Saka)
    club_violation_elements = [
        {"id": 103, "name": "Saliba", "club": "Arsenal", "position": "DEF", "cost": 6.0, "is_captain": False, "is_vice_captain": False},
        {"id": 303, "name": "Alexander-Arnold", "club": "Liverpool", "position": "DEF", "cost": 7.0, "is_captain": False, "is_vice_captain": False},
        {"id": 101, "name": "Saka", "club": "Arsenal", "position": "MID", "cost": 10.0, "is_captain": False, "is_vice_captain": True},
        {"id": 401, "name": "Palmer", "club": "Chelsea", "position": "MID", "cost": 10.5, "is_captain": False, "is_vice_captain": False},
        {"id": 201, "name": "Haaland", "club": "Man City", "position": "FWD", "cost": 15.0, "is_captain": True, "is_vice_captain": False},
        {"id": 501, "name": "Watkins", "club": "Aston Villa", "position": "FWD", "cost": 9.0, "is_captain": False, "is_vice_captain": False},
    ]

    bad_squad = ChallengeOptimalSquad(
        gameweek=5,
        squad_names=[e["name"] for e in club_violation_elements],
        captain="Haaland",
        vice_captain="Saka",
        total_cost=57.5,
        bank_remaining=22.5,
        projected_score=40.0,
        clubs_represented=5,
        formation="2-2-2",
        objective_name="max_ev",
    )
    picker_res = ChallengePickerResult(
        selected_squad=bad_squad,
        evaluated_candidate=valid_candidate_eval,
        archetype_chosen="max_ev",
        squad_elements=club_violation_elements,
        element_ids=[e["id"] for e in club_violation_elements],
        captain_id=201,
        vice_captain_id=101,
        picks_payload={"picks": club_violation_elements},
        tournament_report=None,
    )

    validator = ChallengeModelValidator()
    report = validator.validate(picker_res, rule_preset)

    assert report.is_valid is False
    assert report.club_limits_valid is False
    assert any("Club quota violation" in err for err in report.errors)
    assert any("Arsenal" in err for err in report.errors)


def test_validator_positional_quota_violation(valid_candidate_eval):
    """Ensure positional minimum constraints are enforced."""
    rule_with_def = CHALLENGE_PRESETS["standard_6_a_side"]  # Requires min 1 DEF

    # All MID and FWD, 0 DEF
    no_def_elements = [
        {"id": 101, "name": "Saka", "club": "Arsenal", "position": "MID", "cost": 10.0, "is_captain": False, "is_vice_captain": False},
        {"id": 202, "name": "Foden", "club": "Man City", "position": "MID", "cost": 9.5, "is_captain": False, "is_vice_captain": False},
        {"id": 301, "name": "Salah", "club": "Liverpool", "position": "MID", "cost": 12.5, "is_captain": False, "is_vice_captain": True},
        {"id": 401, "name": "Palmer", "club": "Chelsea", "position": "MID", "cost": 10.5, "is_captain": False, "is_vice_captain": False},
        {"id": 201, "name": "Haaland", "club": "Man City", "position": "FWD", "cost": 15.0, "is_captain": True, "is_vice_captain": False},
        {"id": 501, "name": "Watkins", "club": "Aston Villa", "position": "FWD", "cost": 9.0, "is_captain": False, "is_vice_captain": False},
    ]

    picker_res = ChallengePickerResult(
        selected_squad=valid_candidate_eval.candidate,
        evaluated_candidate=valid_candidate_eval,
        archetype_chosen="max_ev",
        squad_elements=no_def_elements,
        element_ids=[e["id"] for e in no_def_elements],
        captain_id=201,
        vice_captain_id=301,
        picks_payload={"picks": no_def_elements},
        tournament_report=None,
    )

    validator = ChallengeModelValidator()
    report = validator.validate(picker_res, rule_with_def)

    assert report.is_valid is False
    assert report.position_quotas_valid is False
    assert any("Positional deficit for DEF" in err for err in report.errors)


def test_validator_archetype_tail_sanity():
    """Ensure irrational tail distributions (P99 < E[V]) trigger an error."""
    irrational_candidate = EvaluatedChallengeCandidate(
        candidate=ChallengeOptimalSquad(
            gameweek=5,
            squad_names=["Saliba", "Alexander-Arnold", "Son", "Palmer", "Haaland", "Watkins"],
            captain="Haaland",
            vice_captain="Son",
            total_cost=60.0,
            bank_remaining=20.0,
            projected_score=50.0,
            clubs_represented=6,
            formation="2-2-2",
            objective_name="gpp_upside",
        ),
        mean_points=50.0,
        floor_p10=40.0,
        median_p50=49.0,
        ceiling_p90=45.0,
        tournament_p99=42.0,  # Paradoxical: P99 right-tail (42.0) is lower than mean (50.0)!
        std_dev=5.0,
        sharpe_ratio=10.0,
        flexibility_score=80.0,
        win_probability_pct=5.0,
    )

    elements = [
        {"id": 103, "name": "Saliba", "club": "Arsenal", "position": "DEF", "cost": 6.0, "is_captain": False, "is_vice_captain": False},
        {"id": 303, "name": "Alexander-Arnold", "club": "Liverpool", "position": "DEF", "cost": 7.0, "is_captain": False, "is_vice_captain": False},
        {"id": 601, "name": "Son", "club": "Spurs", "position": "MID", "cost": 10.0, "is_captain": False, "is_vice_captain": True},
        {"id": 401, "name": "Palmer", "club": "Chelsea", "position": "MID", "cost": 10.5, "is_captain": False, "is_vice_captain": False},
        {"id": 201, "name": "Haaland", "club": "Man City", "position": "FWD", "cost": 15.0, "is_captain": True, "is_vice_captain": False},
        {"id": 501, "name": "Watkins", "club": "Aston Villa", "position": "FWD", "cost": 9.0, "is_captain": False, "is_vice_captain": False},
    ]

    picker_res = ChallengePickerResult(
        selected_squad=irrational_candidate.candidate,
        evaluated_candidate=irrational_candidate,
        archetype_chosen="gpp_upside",
        squad_elements=elements,
        element_ids=[e["id"] for e in elements],
        captain_id=201,
        vice_captain_id=601,
        picks_payload={"picks": elements},
        tournament_report=None,
    )

    rule = CHALLENGE_PRESETS["gw5_one_player_per_club"]
    validator = ChallengeModelValidator()
    report = validator.validate(picker_res, rule)

    assert report.is_valid is False
    assert any("P99 tournament tail" in err for err in report.errors)
