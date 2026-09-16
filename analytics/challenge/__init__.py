"""
analytics/challenge package.
High-dimensional quantitative optimization engine for FPL Challenge mode.
"""

from analytics.challenge.contracts import (
    ChallengeRuleSet,
    ChallengeOptimalSquad,
    EvaluatedChallengeCandidate,
    ChallengeTournamentReport,
)
from analytics.challenge.rule_extractor import (
    CHALLENGE_PRESETS,
    get_available_challenge_presets,
    extract_rules_from_event,
)
from analytics.challenge.scoring_adapter import ChallengeScoringAdapter
from analytics.challenge.optimizer import ChallengeOptimizer
from analytics.challenge.two_stage_optimizer import ChallengeTwoStageOptimizer
from analytics.challenge.picker import (
    ChallengePicker,
    ChallengePickerConfig,
    ChallengePickerResult,
)
from analytics.challenge.model_validator import (
    ChallengeModelValidator,
    ModelValidationReport,
)

__all__ = [
    "ChallengeRuleSet",
    "ChallengeOptimalSquad",
    "EvaluatedChallengeCandidate",
    "ChallengeTournamentReport",
    "CHALLENGE_PRESETS",
    "get_available_challenge_presets",
    "extract_rules_from_event",
    "ChallengeScoringAdapter",
    "ChallengeOptimizer",
    "ChallengeTwoStageOptimizer",
    "ChallengePicker",
    "ChallengePickerConfig",
    "ChallengePickerResult",
    "ChallengeModelValidator",
    "ModelValidationReport",
]
