"""
Immutable Domain Contracts for Strategic Multi-Period Optimization.
Governed by .agents/rules/moneyball_strategy.md and .agents/rules/python_standards.md.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple, Optional


@dataclass(frozen=True)
class PlayerTrajectoryProfile:
    """
    Immutable multi-horizon projected profile for an individual player.
    All trajectory sequences have exact length H (e.g. H = 8 future gameweeks).
    """
    element_id: int
    web_name: str
    full_name: str
    club_short: str
    position_name: str              # "GKP", "DEF", "MID", "FWD"
    now_cost: float                 # e.g. 7.5 (£m)
    xp_trajectory: Tuple[float, ...]   # Projected expected points for GW t ... GW t+H-1
    fdr_trajectory: Tuple[float, ...]  # FDR integer/float ratings
    opponents: Tuple[str, ...]         # Opponent short codes (e.g. ("FUL", "BRE", "MCI"))
    is_home: Tuple[bool, ...]          # Venue indicators (True if Home, False if Away)
    minutes_expectation: float         # Expected minutes per match (0.0 to 90.0)
    price_change_momentum: float       # Velocity score / price progress (-100 to +100)
    chance_of_playing: Optional[float] = 100.0  # FPL availability percentage (0 to 100)
    status: str = "a"                          # FPL player status ('a', 'd', 'i', 's', 'u')

    def to_dict(self) -> Dict[str, Any]:
        """Serialize contract to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PlayerTrajectoryProfile:
        """Construct contract from dictionary, casting collections to immutable tuples."""
        return cls(
            element_id=int(data["element_id"]),
            web_name=str(data["web_name"]),
            full_name=str(data["full_name"]),
            club_short=str(data["club_short"]),
            position_name=str(data["position_name"]),
            now_cost=float(data["now_cost"]),
            xp_trajectory=tuple(float(x) for x in data["xp_trajectory"]),
            fdr_trajectory=tuple(float(x) for x in data["fdr_trajectory"]),
            opponents=tuple(str(x) for x in data["opponents"]),
            is_home=tuple(bool(x) for x in data["is_home"]),
            minutes_expectation=float(data["minutes_expectation"]),
            price_change_momentum=float(data.get("price_change_momentum", 0.0)),
            chance_of_playing=float(data["chance_of_playing"]) if data.get("chance_of_playing") is not None else None,
            status=str(data.get("status", "a")),
        )


@dataclass(frozen=True)
class ClubScheduleProfile:
    """
    Immutable multi-horizon schedule and dynamic strength profile for a Premier League club.
    All sequence vectors have exact length H (e.g. H = 8 future gameweeks).
    """
    club_short: str
    club_name: str
    fdr_vector: Tuple[float, ...]
    opponents: Tuple[str, ...]
    is_home: Tuple[bool, ...]
    clean_sheet_probs: Tuple[float, ...]
    expected_goals_scored: Tuple[float, ...]
    expected_goals_conceded: Tuple[float, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize contract to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ClubScheduleProfile:
        """Construct contract from dictionary, casting collections to immutable tuples."""
        return cls(
            club_short=str(data["club_short"]),
            club_name=str(data["club_name"]),
            fdr_vector=tuple(float(x) for x in data["fdr_vector"]),
            opponents=tuple(str(x) for x in data["opponents"]),
            is_home=tuple(bool(x) for x in data["is_home"]),
            clean_sheet_probs=tuple(float(x) for x in data["clean_sheet_probs"]),
            expected_goals_scored=tuple(float(x) for x in data["expected_goals_scored"]),
            expected_goals_conceded=tuple(float(x) for x in data["expected_goals_conceded"]),
        )


@dataclass(frozen=True)
class StrategicSquadState:
    """
    Snapshot of manager squad composition, balance sheet liquidity, and decision constraints.
    """
    squad_player_ids: Tuple[int, ...]
    squad_player_names: Tuple[str, ...]
    bank_balance: float
    free_transfers_available: int      # Physical constraint: 1 to 5
    chips_available: Tuple[str, ...]   # ("wildcard", "freehit", "bboost", "3xc")
    team_value: float                  # Total squad valuation (£m)
    gameweek: int                      # Snapshot current gameweek

    def to_dict(self) -> Dict[str, Any]:
        """Serialize contract to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StrategicSquadState:
        """Construct contract from dictionary, casting collections to immutable tuples."""
        return cls(
            squad_player_ids=tuple(int(x) for x in data["squad_player_ids"]),
            squad_player_names=tuple(str(x) for x in data["squad_player_names"]),
            bank_balance=float(data["bank_balance"]),
            free_transfers_available=int(max(1, min(5, data["free_transfers_available"]))),
            chips_available=tuple(str(x) for x in data["chips_available"]),
            team_value=float(data["team_value"]),
            gameweek=int(data["gameweek"]),
        )


@dataclass(frozen=True)
class FixtureWaveAlert:
    """
    Immutable representation of a detected macro fixture regime wave (Green Wave or Red Cliff).
    """
    club_short: str
    club_name: str
    regime_type: str               # "GREEN_WAVE", "RED_CLIFF", "NEUTRAL"
    start_gw: int
    end_gw: int
    duration_gws: int
    avg_fdr: float
    recommended_action: str        # "ACCUMULATE", "HOLD", "LIQUIDATE", "AVOID"
    inflection_gw: int             # Optimal action gameweek (1 GW prior to wave/cliff)
    key_assets: Tuple[str, ...]    # Top talent names for this club
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FixtureWaveAlert:
        return cls(
            club_short=str(data["club_short"]),
            club_name=str(data["club_name"]),
            regime_type=str(data["regime_type"]),
            start_gw=int(data["start_gw"]),
            end_gw=int(data["end_gw"]),
            duration_gws=int(data["duration_gws"]),
            avg_fdr=float(data["avg_fdr"]),
            recommended_action=str(data["recommended_action"]),
            inflection_gw=int(data["inflection_gw"]),
            key_assets=tuple(str(x) for x in data["key_assets"]),
            rationale=str(data["rationale"]),
        )


@dataclass(frozen=True)
class DefensiveRotationPair:
    """
    Immutable representation of an optimal 2-club budget defensive rotation pairing.
    Alternates home/away or easy fixtures to generate synthetic elite defense at budget cost.
    """
    club_a_short: str
    club_b_short: str
    combined_home_ratio: float       # Ratio of fixtures played at Home (0.0 to 1.0)
    combined_easy_ratio: float       # Ratio of fixtures with FDR <= 2.5 (0.0 to 1.0)
    combined_avg_fdr: float          # Average FDR of the chosen best fixture each week
    combined_schedule: Tuple[Tuple[int, str, str, bool, float], ...]  # (gw, chosen_club, opp, is_home, fdr)
    budget_sample_defenders: Tuple[Tuple[str, float], ...]            # ((player_name, cost), ...)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DefensiveRotationPair:
        return cls(
            club_a_short=str(data["club_a_short"]),
            club_b_short=str(data["club_b_short"]),
            combined_home_ratio=float(data["combined_home_ratio"]),
            combined_easy_ratio=float(data["combined_easy_ratio"]),
            combined_avg_fdr=float(data["combined_avg_fdr"]),
            combined_schedule=tuple(tuple(x) for x in data["combined_schedule"]),
            budget_sample_defenders=tuple(tuple(x) for x in data["budget_sample_defenders"]),
        )


@dataclass(frozen=True)
class SquadWaveAudit:
    """
    Audit item mapping a current squad player against upcoming macro fixture regimes.
    """
    element_id: int
    web_name: str
    club_short: str
    position_name: str
    now_cost: float
    current_regime: str             # "GREEN_WAVE", "RED_CLIFF", "NEUTRAL"
    alert_label: str                # e.g. "🌊 Peak Wave (GW5-9)", "⚠️ Cliff Ahead (GW6)"
    action_priority: str            # "URGENT_SELL", "WATCH_EXIT", "HOLD_HARVEST", "BUY_TARGET"
    next_5_fdr: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SquadWaveAudit:
        return cls(
            element_id=int(data["element_id"]),
            web_name=str(data["web_name"]),
            club_short=str(data["club_short"]),
            position_name=str(data["position_name"]),
            now_cost=float(data["now_cost"]),
            current_regime=str(data["current_regime"]),
            alert_label=str(data["alert_label"]),
            action_priority=str(data["action_priority"]),
            next_5_fdr=float(data["next_5_fdr"]),
        )


@dataclass(frozen=True)
class MultiPeriodGameweekPlan:
    """
    Detailed tactical and balance-sheet plan for a single gameweek in the rolling horizon.
    """
    gameweek: int
    transfers_in: Tuple[Tuple[int, str, float], ...]          # ((element_id, web_name, cost), ...)
    transfers_out: Tuple[Tuple[int, str, float], ...]         # ((element_id, web_name, cost), ...)
    starting_xi: Tuple[Tuple[int, str, str, float], ...]      # ((element_id, web_name, pos, xp), ...)
    bench: Tuple[Tuple[int, str, str, float], ...]            # ((element_id, web_name, pos, xp), ...)
    captain_id: int
    captain_name: str
    vice_captain_id: int
    vice_captain_name: str
    free_transfers_available: int                             # FTs at start of gameweek (1 to 5)
    free_transfers_used: int                                  # Number of FTs consumed
    free_transfers_banked_next: int                           # FTs rolled to next gameweek (1 to 5)
    hits_taken: int                                           # Number of paid transfer hits
    hit_cost_points: int                                      # Total point deduction (hits * 4)
    gross_xp: float                                           # Total starting XI + captain xP
    net_xp: float                                             # gross_xp - hit_cost_points
    bank_remaining: float                                     # Cash in bank (£m)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MultiPeriodGameweekPlan:
        return cls(
            gameweek=int(data["gameweek"]),
            transfers_in=tuple(tuple(x) for x in data["transfers_in"]),
            transfers_out=tuple(tuple(x) for x in data["transfers_out"]),
            starting_xi=tuple(tuple(x) for x in data["starting_xi"]),
            bench=tuple(tuple(x) for x in data["bench"]),
            captain_id=int(data["captain_id"]),
            captain_name=str(data["captain_name"]),
            vice_captain_id=int(data["vice_captain_id"]),
            vice_captain_name=str(data["vice_captain_name"]),
            free_transfers_available=int(data["free_transfers_available"]),
            free_transfers_used=int(data["free_transfers_used"]),
            free_transfers_banked_next=int(data["free_transfers_banked_next"]),
            hits_taken=int(data["hits_taken"]),
            hit_cost_points=int(data["hit_cost_points"]),
            gross_xp=float(data["gross_xp"]),
            net_xp=float(data["net_xp"]),
            bank_remaining=float(data["bank_remaining"]),
        )


@dataclass(frozen=True)
class MultiPeriodStrategicSolution:
    """
    Immutable multi-horizon sequential transfer and lineup optimization roadmap.
    """
    horizon: int
    plans: Tuple[MultiPeriodGameweekPlan, ...]
    cumulative_gross_xp: float
    cumulative_net_xp: float
    cumulative_hits_taken: int
    terminal_squad_value: float
    terminal_bank: float
    staged_turnaround_summary: str
    objective_name: str = "max_ev"
    generator_type: str = "Multi-Period MILP"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MultiPeriodStrategicSolution:
        return cls(
            horizon=int(data["horizon"]),
            plans=tuple(MultiPeriodGameweekPlan.from_dict(p) if isinstance(p, dict) else p for p in data["plans"]),
            cumulative_gross_xp=float(data["cumulative_gross_xp"]),
            cumulative_net_xp=float(data["cumulative_net_xp"]),
            cumulative_hits_taken=int(data["cumulative_hits_taken"]),
            terminal_squad_value=float(data["terminal_squad_value"]),
            terminal_bank=float(data["terminal_bank"]),
            staged_turnaround_summary=str(data["staged_turnaround_summary"]),
            objective_name=str(data.get("objective_name", "max_ev")),
            generator_type=str(data.get("generator_type", "Multi-Period MILP")),
        )


@dataclass(frozen=True)
class FreeTransferOptionProfile:
    """
    Quantitative valuation of holding and banking Free Transfers (1 to 5 FTs).
    Quantifies continuation value vs. greedy immediate single transfer execution.
    """
    current_ft: int                                            # 1 to 5
    continuation_value_pts: float                              # Total points utility of holding current FT count
    marginal_option_values: Tuple[float, ...]                  # Marginal pts lift for holding [1, 2, 3, 4, 5] FTs
    pivot_readiness_score: float                               # 0.0 to 1.0 readiness for multi-player structural pivot
    recommended_action: str                                    # "BANK_FOR_PIVOT", "EXECUTE_SINGLE", "EXECUTE_DOUBLE", "HOLD_RESERVE"
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FreeTransferOptionProfile:
        return cls(
            current_ft=int(data["current_ft"]),
            continuation_value_pts=float(data["continuation_value_pts"]),
            marginal_option_values=tuple(float(x) for x in data["marginal_option_values"]),
            pivot_readiness_score=float(data["pivot_readiness_score"]),
            recommended_action=str(data["recommended_action"]),
            rationale=str(data["rationale"]),
        )


@dataclass(frozen=True)
class PriceRiskProfile:
    """
    Evaluates player market price change risk vs pre-match information uncertainty.
    """
    player_id: int
    web_name: str
    club_short: str
    now_cost: float
    projected_change_prob: float                               # Probability of imminent price change (0.0 to 1.0)
    early_transfer_hurdle_rate_xp: float                       # Net xP lift required to justify early move
    information_risk_penalty_xp: float                         # Expected point loss from early move injury risk
    risk_recommendation: str                                   # "LOCK_PRICE_EARLY", "WAIT_FOR_PRESS_CONFERENCES", "AVOID_PRICE_FALL"
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PriceRiskProfile:
        return cls(
            player_id=int(data["player_id"]),
            web_name=str(data["web_name"]),
            club_short=str(data["club_short"]),
            now_cost=float(data["now_cost"]),
            projected_change_prob=float(data["projected_change_prob"]),
            early_transfer_hurdle_rate_xp=float(data["early_transfer_hurdle_rate_xp"]),
            information_risk_penalty_xp=float(data["information_risk_penalty_xp"]),
            risk_recommendation=str(data["risk_recommendation"]),
            rationale=str(data["rationale"]),
        )


@dataclass(frozen=True)
class ChipRealOptionValuation:
    """
    American Real Options valuation and optimal stopping pricing for strategic FPL chips.
    """
    chip_name: str                                             # "wildcard", "freehit", "bench_boost", "triple_captain"
    chip_display_name: str
    is_available: bool
    immediate_exercise_lift_xp: float                          # Expected points lift if triggered in current GW t
    continuation_option_value_xp: float                        # Expected discounted peak future deployment value
    exercise_boundary_gap: float                               # Immediate Lift - Continuation Value (>= 0 -> EXERCISE)
    optimal_decision: str                                      # "EXERCISE_NOW", "HOLD_OPTION", "EXPIRED"
    target_gameweek_window: str                                # e.g. "GW34–GW37 (Major Double Gameweeks)"
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChipRealOptionValuation:
        return cls(
            chip_name=str(data["chip_name"]),
            chip_display_name=str(data["chip_display_name"]),
            is_available=bool(data["is_available"]),
            immediate_exercise_lift_xp=float(data["immediate_exercise_lift_xp"]),
            continuation_option_value_xp=float(data["continuation_option_value_xp"]),
            exercise_boundary_gap=float(data["exercise_boundary_gap"]),
            optimal_decision=str(data["optimal_decision"]),
            target_gameweek_window=str(data["target_gameweek_window"]),
            rationale=str(data["rationale"]),
        )


@dataclass(frozen=True)
class SquadBalanceSheet:
    """
    Comprehensive quantitative balance sheet and real options state of the FPL squad.
    """
    team_value: float                                          # Total squad purchase cost (£m)
    selling_value: float                                       # Realizable cash after 50% profit deduction (£m)
    bank_liquidity: float                                      # Liquid cash in bank (£m)
    dead_cash_drag_penalty_xp: float                           # Pitch yield penalty for excess unspent cash (> £1.5m)
    free_transfers_available: int                              # 1 to 5 FTs
    ft_option_value_xp: float                                  # Valuation of current FT inventory (points)
    total_balance_sheet_utility: float                         # Combined monetary and optionality utility
    lifecycle_phase: str                                       # "CAPITAL_ACCUMULATION", "MID_SEASON_HARVEST", "DGW_MONETIZATION"
    top_price_risks: Tuple[PriceRiskProfile, ...]
    chip_options: Tuple[ChipRealOptionValuation, ...]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SquadBalanceSheet:
        return cls(
            team_value=float(data["team_value"]),
            selling_value=float(data["selling_value"]),
            bank_liquidity=float(data["bank_liquidity"]),
            dead_cash_drag_penalty_xp=float(data["dead_cash_drag_penalty_xp"]),
            free_transfers_available=int(data["free_transfers_available"]),
            ft_option_value_xp=float(data["ft_option_value_xp"]),
            total_balance_sheet_utility=float(data["total_balance_sheet_utility"]),
            lifecycle_phase=str(data["lifecycle_phase"]),
            top_price_risks=tuple(PriceRiskProfile.from_dict(r) if isinstance(r, dict) else r for r in data["top_price_risks"]),
            chip_options=tuple(ChipRealOptionValuation.from_dict(c) if isinstance(c, dict) else c for c in data["chip_options"]),
        )


@dataclass(frozen=True)
class EvaluatedStrategicPathway:
    """
    Two-Stage Strategic Evaluation:
    Chains a Stage 1 multi-period optimization solution with Stage 2 Monte Carlo distribution metrics.
    """
    pathway_id: str
    objective_name: str
    generator_type: str
    solution: MultiPeriodStrategicSolution
    mean_points: float
    floor_p10: float
    median_p50: float
    ceiling_p90: float
    standard_deviation: float
    win_probability_pct: float
    sharpe_ratio: float
    weekly_mean_totals: Tuple[float, ...]
    weekly_p10_totals: Tuple[float, ...]
    weekly_p90_totals: Tuple[float, ...]
    raw_totals: Tuple[float, ...]
    archetype: str = ""
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvaluatedStrategicPathway:
        return cls(
            pathway_id=str(data["pathway_id"]),
            objective_name=str(data["objective_name"]),
            generator_type=str(data.get("generator_type", "Multi-Period MILP")),
            solution=MultiPeriodStrategicSolution.from_dict(data["solution"]) if isinstance(data["solution"], dict) else data["solution"],
            mean_points=float(data["mean_points"]),
            floor_p10=float(data["floor_p10"]),
            median_p50=float(data["median_p50"]),
            ceiling_p90=float(data["ceiling_p90"]),
            standard_deviation=float(data["standard_deviation"]),
            win_probability_pct=float(data["win_probability_pct"]),
            sharpe_ratio=float(data["sharpe_ratio"]),
            weekly_mean_totals=tuple(float(x) for x in data.get("weekly_mean_totals", ())),
            weekly_p10_totals=tuple(float(x) for x in data.get("weekly_p10_totals", ())),
            weekly_p90_totals=tuple(float(x) for x in data.get("weekly_p90_totals", ())),
            raw_totals=tuple(float(x) for x in data.get("raw_totals", ())),
            archetype=str(data.get("archetype", "")),
            rationale=str(data.get("rationale", "")),
        )


@dataclass(frozen=True)
class StrategicTwoStageReport:
    """
    Final decision report comparing all multi-period strategic candidate pathways.
    """
    horizon: int
    baseline_solution: MultiPeriodStrategicSolution
    baseline_mean: float
    baseline_p10: float
    baseline_p90: float
    baseline_raw_totals: Tuple[float, ...]
    evaluated_pathways: Tuple[EvaluatedStrategicPathway, ...]
    winner_balanced: Optional[EvaluatedStrategicPathway]
    winner_safe_floor: Optional[EvaluatedStrategicPathway]
    winner_explosive_ceiling: Optional[EvaluatedStrategicPathway]
    all_results_df_data: Tuple[Dict[str, Any], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StrategicTwoStageReport:
        return cls(
            horizon=int(data["horizon"]),
            baseline_solution=MultiPeriodStrategicSolution.from_dict(data["baseline_solution"]) if isinstance(data["baseline_solution"], dict) else data["baseline_solution"],
            baseline_mean=float(data["baseline_mean"]),
            baseline_p10=float(data["baseline_p10"]),
            baseline_p90=float(data["baseline_p90"]),
            baseline_raw_totals=tuple(float(x) for x in data.get("baseline_raw_totals", ())),
            evaluated_pathways=tuple(EvaluatedStrategicPathway.from_dict(p) if isinstance(p, dict) else p for p in data.get("evaluated_pathways", ())),
            winner_balanced=EvaluatedStrategicPathway.from_dict(data["winner_balanced"]) if data.get("winner_balanced") else None,
            winner_safe_floor=EvaluatedStrategicPathway.from_dict(data["winner_safe_floor"]) if data.get("winner_safe_floor") else None,
            winner_explosive_ceiling=EvaluatedStrategicPathway.from_dict(data["winner_explosive_ceiling"]) if data.get("winner_explosive_ceiling") else None,
            all_results_df_data=tuple(dict(x) for x in data.get("all_results_df_data", ())),
        )


