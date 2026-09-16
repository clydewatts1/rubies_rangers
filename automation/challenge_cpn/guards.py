"""
automation/challenge_cpn/guards.py
Transition guard conditions and invariant verification for FPL Challenge CPN.
Ensures formal Jensen CPN safety properties and mathematical consistency.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Tuple, Optional

from automation.challenge_cpn.tokens import (
    Color_ChallengeRule,
    Color_ChallengeMarket,
    Color_ChallengeSquadState,
    Color_ChallengePlan,
    Color_ChallengeValidation,
    Color_ChallengeSagaToken,
)

logger = logging.getLogger("rubies_rangers.challenge.guards")


def guard_can_solve(
    rules: Optional[Color_ChallengeRule],
    market: Optional[Color_ChallengeMarket],
    current_team: Optional[Color_ChallengeSquadState]
) -> bool:
    """Asserts that rules, player market, and current team markings are populated and feasible."""
    if rules is None or market is None or current_team is None:
        return False
    if market.elements_df.empty:
        return False
    if rules.rule_set.squad_size < 5 or rules.rule_set.squad_size > 15:
        return False
    return True


def guard_validation_passed(validation: Color_ChallengeValidation) -> bool:
    """Asserts that model validation passed with 0 fatal constraint errors."""
    return validation.is_valid and validation.error_count == 0


def guard_saga_verify(
    saga_token: Color_ChallengeSagaToken,
    live_team_state: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any]]:
    """
    Compares live team picks returned by FPL Challenge against expected picks from the plan.
    Checks:
    1. All expected element IDs are present in live picks.
    2. The designated captain element ID matches live is_captain == True.
    3. The designated vice-captain element ID matches live is_vice_captain == True.
    Returns (is_match: bool, diff: dict).
    """
    live_picks = live_team_state.get("picks", [])
    live_element_ids = [int(p.get("element", 0)) for p in live_picks]
    
    live_captain = next((int(p.get("element", 0)) for p in live_picks if p.get("is_captain")), None)
    live_vice = next((int(p.get("element", 0)) for p in live_picks if p.get("is_vice_captain")), None)

    expected_set = set(saga_token.expected_element_ids)
    live_set = set(live_element_ids)

    missing_elements = list(expected_set - live_set)
    extra_elements = list(live_set - expected_set)
    captain_mismatch = (live_captain != saga_token.expected_captain_id)
    vice_mismatch = (live_vice != saga_token.expected_vice_captain_id)

    is_match = (
        len(missing_elements) == 0
        and len(extra_elements) == 0
        and not captain_mismatch
        and not vice_mismatch
    )

    diff = {
        "is_match": is_match,
        "expected_count": len(saga_token.expected_element_ids),
        "live_count": len(live_element_ids),
        "missing_elements": missing_elements,
        "extra_elements": extra_elements,
        "expected_captain": saga_token.expected_captain_id,
        "live_captain": live_captain,
        "captain_mismatch": captain_mismatch,
        "expected_vice_captain": saga_token.expected_vice_captain_id,
        "live_vice_captain": live_vice,
        "vice_mismatch": vice_mismatch,
    }

    if not is_match:
        logger.warning(
            "[ChallengeGuards] Saga verification mismatch (Attempt %d/%d): missing=%s, extra=%s, cap_diff=%s, vc_diff=%s",
            saga_token.attempt, saga_token.max_retries, missing_elements, extra_elements, captain_mismatch, vice_mismatch
        )
    else:
        logger.info(
            "[ChallengeGuards] Saga verification exact match confirmed for Entry %d (Attempt %d)",
            saga_token.entry_id, saga_token.attempt
        )

    return is_match, diff


def guard_can_retry(saga_token: Color_ChallengeSagaToken) -> bool:
    """Returns True if the saga has remaining retry attempts."""
    return saga_token.attempt < saga_token.max_retries


def guard_retries_exhausted(saga_token: Color_ChallengeSagaToken) -> bool:
    """Returns True if the saga has exhausted all allowed retry attempts."""
    return saga_token.attempt >= saga_token.max_retries
