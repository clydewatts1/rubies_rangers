"""
automation/challenge_cpn package.
Autonomous Coloured Petri Net execution engine and Saga transaction pipeline for FPL Challenge.
"""

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
from automation.challenge_cpn.places import (
    ChallengePlace,
    ChallengeStatePlace,
    ChallengeMarkingRegistry,
)
from automation.challenge_cpn.diagnostics import ChallengeCPNDiagnosticJournal
from automation.challenge_cpn.transitions import ChallengeTransitions
from automation.challenge_cpn.engine import ChallengeCPNEngine

__all__ = [
    "ChallengeCPNEngine",
    "ChallengeMarkingRegistry",
    "ChallengeCPNDiagnosticJournal",
    "ChallengeTransitions",
    "ChallengePlace",
    "ChallengeStatePlace",
    "Color_ChallengeRule",
    "Color_ChallengeMarket",
    "Color_ChallengeSquadState",
    "Color_ChallengePlan",
    "Color_ChallengeValidation",
    "Color_ChallengeSagaToken",
    "Color_ChallengeReceipt",
    "Color_ChallengeAlert",
    "SagaStatus",
]
