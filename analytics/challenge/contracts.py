"""
analytics/challenge/contracts.py
Data contracts and domain models for FPL Challenge quantitative engine.
Strictly frozen immutable dataclasses complying with repository standards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ChallengeRuleSet:
    """Dynamic constraint rules for a specific Challenge Gameweek."""
    gameweek: int
    name: str = "FPL Challenge Weekly Sprint"
    squad_size: int = 6                         # e.g., 6 (outfield) or 11 (full)
    max_per_team: int = 3                       # e.g., 1 (one player per club), 3, or 5
    budget_cap: float = 999.9                   # e.g., 999.9 (unlimited) or 80.0
    allowed_positions: Dict[str, Tuple[int, int]] = field(
        default_factory=lambda: {
            "GKP": (0, 0),
            "DEF": (1, 3),
            "MID": (1, 3),
            "FWD": (1, 3)
        }
    )
    scoring_modifiers: Dict[str, float] = field(default_factory=dict)
    rolling_deadlines: bool = True
    description: str = "Dynamic constraint weekly challenge."

    def get_position_bounds(self, pos: str) -> Tuple[int, int]:
        """Return (min_select, max_select) for position, defaulting safely."""
        pos_upper = pos.strip().upper()
        if pos_upper in self.allowed_positions:
            return self.allowed_positions[pos_upper]
        if pos_upper == "GKP":
            return (0, 0) if self.squad_size <= 6 else (1, 1)
        return (0, self.squad_size)

    @property
    def is_outfield_only(self) -> bool:
        """True if goalkeepers are not permitted."""
        return self.get_position_bounds("GKP")[1] == 0

    @property
    def position_summary_str(self) -> str:
        """Formatted string of active positional limits (e.g. DEF: 1-3 | MID: 1-3 | FWD: 1-3)."""
        parts = []
        for pos in ["GKP", "DEF", "MID", "FWD"]:
            if pos in self.allowed_positions:
                low, high = self.allowed_positions[pos]
                if pos == "GKP" and high == 0:
                    continue
                parts.append(f"{pos}: {low}-{high}" if low != high else f"{pos}: {low}")
        return " | ".join(parts) if parts else "Standard Outfield"


@dataclass(frozen=True)
class ChallengeOptimalSquad:
    """Optimal Stage 1 MILP candidate solution for an FPL Challenge gameweek."""
    gameweek: int
    squad_names: List[str]
    captain: str
    total_cost: float
    bank_remaining: float
    projected_score: float
    clubs_represented: int
    objective_name: str
    formation: str = "1-3-2"
    generator_type: str = "MILP Challenge"
    vice_captain: str = ""


@dataclass(frozen=True)
class EvaluatedChallengeCandidate:
    """Stochastically modeled evaluation of a candidate Challenge squad."""
    candidate: ChallengeOptimalSquad
    mean_points: float                          # Expected Return E[V]
    floor_p10: float                            # Downside Floor (10th percentile)
    median_p50: float                           # Median (50th percentile)
    ceiling_p90: float                          # Upside Ceiling (90th percentile)
    tournament_p99: float                       # Tournament Winning Right Tail (99th percentile)
    std_dev: float                              # Volatility / Standard Deviation
    sharpe_ratio: float                         # Mean-to-volatility ratio
    flexibility_score: float                    # Rolling matchday in-play adjustment score
    win_probability_pct: float                  # GPP field win probability vs top 5% threshold
    raw_totals: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=float))
    archetype: str = ""
    key_talismans: str = ""


@dataclass(frozen=True)
class ChallengeTournamentReport:
    """Comprehensive two-stage tournament report for an FPL Challenge Gameweek."""
    rule_set: ChallengeRuleSet
    evaluated_candidates: List[EvaluatedChallengeCandidate]
    winner_balanced: Optional[EvaluatedChallengeCandidate]
    winner_safe_floor: Optional[EvaluatedChallengeCandidate]
    winner_gpp_upside: Optional[EvaluatedChallengeCandidate]
    all_results_df: pd.DataFrame = field(default_factory=pd.DataFrame)
