"""
Analytics Package for Rubies Rangers
Core quantitative engines: MILP optimizer, Monte Carlo stochastic simulator,
expected points model, and team state manager.
"""

from analytics.optimizer import FPLOptimizer
from analytics.montecarlo import MonteCarloEngine, clean_nans
from analytics.xp_model import XPModel, DEFAULT_SQUAD, GW4_MATCH_ODDS
from analytics.team_manager import load_dataset
from analytics.two_stage_optimizer import (
    TwoStageOptimizer,
    MILPCandidateGenerator,
    ParetoCandidateSquad,
    StochasticSquadEvaluation,
    TwoStageOptimizationReport,
)
from analytics.domain_intel import (
    ShaneIntelManager,
    PlayerOverride,
    AvailabilityOption,
    EligibilityOption,
    TacticalOption,
    TTLWindow,
)

__all__ = [
    "FPLOptimizer",
    "MonteCarloEngine",
    "clean_nans",
    "XPModel",
    "DEFAULT_SQUAD",
    "GW4_MATCH_ODDS",
    "load_dataset",
    "TwoStageOptimizer",
    "MILPCandidateGenerator",
    "ParetoCandidateSquad",
    "StochasticSquadEvaluation",
    "TwoStageOptimizationReport",
    "ShaneIntelManager",
    "PlayerOverride",
    "AvailabilityOption",
    "EligibilityOption",
    "TacticalOption",
    "TTLWindow",
]
