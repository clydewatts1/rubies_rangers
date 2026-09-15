"""
Strategic Quantitative Analytics Subsystem for Rubies Rangers FPL.
Provides multi-horizon trajectory engines, fixture radar wave scanning,
multi-period integer programming, and balance sheet capital management.
"""

from analytics.strategic.contracts import (
    PlayerTrajectoryProfile,
    ClubScheduleProfile,
    StrategicSquadState,
    FixtureWaveAlert,
    DefensiveRotationPair,
    SquadWaveAudit,
    MultiPeriodGameweekPlan,
    MultiPeriodStrategicSolution,
    EvaluatedStrategicPathway,
    StrategicTwoStageReport,
    FreeTransferOptionProfile,
    PriceRiskProfile,
    ChipRealOptionValuation,
    SquadBalanceSheet,
)
from analytics.strategic.trajectory_engine import (
    TrajectoryEngine,
    build_club_schedule_profiles,
    build_player_trajectory_profiles,
    build_strategic_squad_state,
)
from analytics.strategic.wave_scanner import (
    WaveScanner,
    scan_fixture_waves,
    find_optimal_defensive_rotation_pairs,
    audit_squad_waves,
)
from analytics.strategic.multi_period_solver import MultiPeriodSolver
from analytics.strategic.two_stage_solver import StrategicTwoStageOptimizer
from analytics.strategic.balance_sheet import BalanceSheetEngine

__all__ = [
    "PlayerTrajectoryProfile",
    "ClubScheduleProfile",
    "StrategicSquadState",
    "FixtureWaveAlert",
    "DefensiveRotationPair",
    "SquadWaveAudit",
    "MultiPeriodGameweekPlan",
    "MultiPeriodStrategicSolution",
    "EvaluatedStrategicPathway",
    "StrategicTwoStageReport",
    "FreeTransferOptionProfile",
    "PriceRiskProfile",
    "ChipRealOptionValuation",
    "SquadBalanceSheet",
    "TrajectoryEngine",
    "WaveScanner",
    "MultiPeriodSolver",
    "StrategicTwoStageOptimizer",
    "BalanceSheetEngine",
    "build_club_schedule_profiles",
    "build_player_trajectory_profiles",
    "build_strategic_squad_state",
    "scan_fixture_waves",
    "find_optimal_defensive_rotation_pairs",
    "audit_squad_waves",
]


