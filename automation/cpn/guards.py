"""
automation/cpn/guards.py
Pure functional Kleene K3 transition guard evaluators.
Distinguishes fatal invariant breaches from degradable chip failures.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from automation.cpn.tokens import (
    K3Status, Color_OptimizedPlan, Color_SquadState, Color_MarketData,
    Color_Session, Color_GuardToken
)


@dataclass(frozen=True)
class GuardEvaluationResult:
    """Aggregated outcome of joint guard evaluations."""
    joint_status: K3Status
    tokens: list[Color_GuardToken]
    has_fatal_failure: bool
    has_degradable_chip_failure: bool


def evaluate_budget_guard(plan: Color_OptimizedPlan, squad: Color_SquadState) -> K3Status:
    """Verifies transfer spend does not exceed bank plus effective selling prices."""
    if not plan.transfers:
        return K3Status.TRUE
    total_cost = sum(t["purchase_price"] for t in plan.transfers)
    total_sales = sum(
        squad.selling_prices.get(t["element_out"], t.get("selling_price", 0.0))
        for t in plan.transfers
    )
    available_capital = round(squad.bank + total_sales, 2)
    return K3Status.TRUE if total_cost <= available_capital else K3Status.FALSE


def evaluate_club_cap_guard(plan: Color_OptimizedPlan, market: Color_MarketData) -> K3Status:
    """Verifies no single Premier League club has more than 3 players across all 15."""
    team_counts: dict[int, int] = {}
    element_team_map = market.elements.set_index("id")["team"].to_dict()
    all_15 = plan.starters + plan.bench
    for el_id in all_15:
        team_id = element_team_map.get(el_id)
        if team_id is None:
            return K3Status.UNKNOWN
        team_counts[team_id] = team_counts.get(team_id, 0) + 1
        if team_counts[team_id] > 3:
            return K3Status.FALSE
    return K3Status.TRUE


def evaluate_formation_guard(
    plan: Color_OptimizedPlan,
    legal_formations: set[tuple[int, int, int]]
) -> K3Status:
    """Verifies Starting XI formation matches configured legal tuples (DEF, MID, FWD)."""
    return K3Status.TRUE if plan.formation_tuple in legal_formations else K3Status.FALSE


def evaluate_hit_utility_guard(
    plan: Color_OptimizedPlan,
    squad: Color_SquadState,
    baseline_utility: float,
    discount_gamma: float = 0.90,
    horizon: int = 4
) -> K3Status:
    """
    Evaluates multi-period expected utility net of hit points vs NoTransfer baseline.
    Enforces Moneyball Strategy Rule 3: No arbitrary hit limits; justified by positive EV.
    """
    transfer_count = len(plan.transfers)
    excess_transfers = max(0, transfer_count - squad.free_transfers)
    hit_cost = excess_transfers * 4.0

    # Discounted net utility margin
    net_plan_utility = plan.expected_utility - hit_cost
    if net_plan_utility > baseline_utility:
        return K3Status.TRUE
    elif net_plan_utility < baseline_utility - 2.0:
        return K3Status.FALSE
    else:
        return K3Status.UNKNOWN


def evaluate_fitness_guard(
    plan: Color_OptimizedPlan,
    market: Color_MarketData,
    tau_fitness: float = 0.70
) -> list[Color_GuardToken]:
    """Inspects Starting XI players for injury flags and fitness doubt."""
    tokens: list[Color_GuardToken] = []
    flags = market.injury_flags
    for pid in plan.starters:
        flag = flags.get(pid, {})
        chance = flag.get("chance_of_playing")
        if chance is None or chance == 100:
            continue
        elif chance == 0:
            tokens.append(Color_GuardToken(
                plan_id=plan.plan_id, guard_name="Guard_Fitness", status=K3Status.FALSE,
                subject_id=pid, doubt_type="red_flag", is_fatal=False, context=flag
            ))
        elif chance in (25, 50, 75):
            tokens.append(Color_GuardToken(
                plan_id=plan.plan_id, guard_name="Guard_Fitness", status=K3Status.UNKNOWN,
                subject_id=pid, doubt_type="yellow_flag", is_fatal=False, context=flag
            ))
    return tokens


def evaluate_chip_safety_guard(
    plan: Color_OptimizedPlan,
    squad: Color_SquadState,
    market: Color_MarketData,
    max_banked_ft: int = 5
) -> tuple[K3Status, list[Color_GuardToken], bool]:
    """
    Evaluates chip rules and invariants under modern FPL regulations (2024/25+).
    Preserves banked free transfers up to max_banked_ft through Wildcard and Free Hit.
    Returns (status, tokens, is_fatal).
    """
    if plan.chip is None:
        return K3Status.TRUE, [], False

    # Core Invariant 1: Single-Chip Rule
    if squad.active_chip is not None and squad.active_chip != plan.chip:
        return K3Status.FALSE, [Color_GuardToken(
            plan_id=plan.plan_id, guard_name="Guard_ChipSafety", status=K3Status.FALSE,
            subject_id=None, doubt_type="single_chip_violation", is_fatal=True, context={}
        )], True

    # Core Invariant 2: Availability
    if not squad.chips_available.get(plan.chip, False):
        return K3Status.FALSE, [Color_GuardToken(
            plan_id=plan.plan_id, guard_name="Guard_ChipSafety", status=K3Status.FALSE,
            subject_id=None, doubt_type="chip_not_available", is_fatal=True, context={}
        )], True

    # Sub-predicate: Wildcard Banked Transfer Invariant (Modern Rule: Max 5 Banked FTs)
    if plan.chip == "wildcard":
        if squad.free_transfers > max_banked_ft or squad.free_transfers < 0:
            return K3Status.FALSE, [Color_GuardToken(
                plan_id=plan.plan_id, guard_name="Guard_ChipSafety", status=K3Status.FALSE,
                subject_id=None, doubt_type="banked_ft_overflow", is_fatal=True, context={}
            )], True

    # Sub-predicate: Triple Captain
    if plan.chip == "3xc":
        cap_flag = market.injury_flags.get(plan.captain, {})
        cap_chance = cap_flag.get("chance_of_playing", 100)
        if cap_chance is not None and cap_chance < 50:
            # Captain doubtful/ruled out -> Degradable chip failure!
            return K3Status.FALSE, [Color_GuardToken(
                plan_id=plan.plan_id, guard_name="Guard_ChipSafety", status=K3Status.FALSE,
                subject_id=plan.captain, doubt_type="triple_captain_fitness_fail", is_fatal=False, context=cap_flag
            )], False
        elif cap_chance in (50, 75):
            return K3Status.UNKNOWN, [Color_GuardToken(
                plan_id=plan.plan_id, guard_name="Guard_ChipSafety", status=K3Status.UNKNOWN,
                subject_id=plan.captain, doubt_type="triple_captain_doubt", is_fatal=False, context=cap_flag
            )], False

    # Sub-predicate: Bench Boost
    if plan.chip == "bboost":
        for b_id in plan.bench:
            b_flag = market.injury_flags.get(b_id, {})
            b_chance = b_flag.get("chance_of_playing", 100)
            if b_chance is not None and b_chance < 50:
                # Bench player ruled out -> Degradable chip failure!
                return K3Status.FALSE, [Color_GuardToken(
                    plan_id=plan.plan_id, guard_name="Guard_ChipSafety", status=K3Status.FALSE,
                    subject_id=b_id, doubt_type="bench_boost_fitness_fail", is_fatal=False, context=b_flag
                )], False
            elif b_chance in (50, 75):
                return K3Status.UNKNOWN, [Color_GuardToken(
                    plan_id=plan.plan_id, guard_name="Guard_ChipSafety", status=K3Status.UNKNOWN,
                    subject_id=b_id, doubt_type="bench_boost_doubt", is_fatal=False, context=b_flag
                )], False

    # Sub-predicate: Free Hit Ghost Squad Validation
    if plan.chip == "freehit":
        if not squad.ghost_squad_ids or len(squad.ghost_squad_ids) != 15:
            return K3Status.FALSE, [Color_GuardToken(
                plan_id=plan.plan_id, guard_name="Guard_ChipSafety", status=K3Status.FALSE,
                subject_id=None, doubt_type="missing_ghost_squad", is_fatal=True, context={}
            )], True

    return K3Status.TRUE, [], False


def evaluate_preflight_session_guard(session: Color_Session, deadline_utc: datetime) -> K3Status:
    """Verifies that the session is authenticated and cookie expires strictly after deadline."""
    if not session.is_authenticated:
        return K3Status.FALSE
    if session.expires_at <= deadline_utc:
        return K3Status.FALSE
    return K3Status.TRUE


def evaluate_time_window_guard(deadline_utc: datetime, current_time: datetime) -> K3Status:
    """Verifies that current time falls strictly within dispatch window (D-7m to D-1m / 60s to 420s)."""
    seconds_to_deadline = (deadline_utc - current_time).total_seconds()
    if 60 <= seconds_to_deadline <= 420:
        return K3Status.TRUE
    elif seconds_to_deadline > 420:
        return K3Status.UNKNOWN
    else:
        return K3Status.FALSE


def evaluate_joint_guards(
    plan: Color_OptimizedPlan,
    squad: Color_SquadState,
    market: Color_MarketData,
    session: Color_Session,
    legal_formations: set[tuple[int, int, int]],
    deadline_utc: datetime | None = None
) -> GuardEvaluationResult:
    """Evaluates all guards and aggregates status under Kleene K3 strong conjunction."""
    tokens: list[Color_GuardToken] = []
    fatal_failure = False
    degradable_chip_failure = False

    # 1. Fatal Structural Guards
    if not session.is_authenticated or (deadline_utc and evaluate_preflight_session_guard(session, deadline_utc) == K3Status.FALSE):
        fatal_failure = True
        tokens.append(Color_GuardToken(
            plan_id=plan.plan_id, guard_name="Guard_PreflightSession", status=K3Status.FALSE,
            subject_id=None, doubt_type="session_auth_failure", is_fatal=True,
            context={"is_authenticated": session.is_authenticated}
        ))

    if evaluate_budget_guard(plan, squad) == K3Status.FALSE:
        fatal_failure = True
        tokens.append(Color_GuardToken(
            plan_id=plan.plan_id, guard_name="Guard_Budget", status=K3Status.FALSE,
            subject_id=None, doubt_type="budget_exceeded", is_fatal=True, context={}
        ))

    if evaluate_club_cap_guard(plan, market) == K3Status.FALSE:
        fatal_failure = True
        tokens.append(Color_GuardToken(
            plan_id=plan.plan_id, guard_name="Guard_ClubCap", status=K3Status.FALSE,
            subject_id=None, doubt_type="club_cap_exceeded", is_fatal=True, context={}
        ))

    if evaluate_formation_guard(plan, legal_formations) == K3Status.FALSE:
        fatal_failure = True
        tokens.append(Color_GuardToken(
            plan_id=plan.plan_id, guard_name="Guard_Formation", status=K3Status.FALSE,
            subject_id=None, doubt_type="illegal_formation", is_fatal=True, context={}
        ))

    # 2. Fitness Guards (Scatterable)
    fitness_tokens = evaluate_fitness_guard(plan, market)
    tokens.extend(fitness_tokens)
    if any(t.status == K3Status.FALSE for t in fitness_tokens):
        # A red-flagged starter is an indeterminate/substitutable situation handled in scatter-gather or marked UNKNOWN
        pass

    # 3. Chip Safety Guard (Degradable or Fatal)
    chip_status, chip_tokens, is_chip_fatal = evaluate_chip_safety_guard(plan, squad, market)
    tokens.extend(chip_tokens)
    if chip_status == K3Status.FALSE:
        if is_chip_fatal:
            fatal_failure = True
        else:
            degradable_chip_failure = True

    # Aggregate Joint Status under Kleene Strong Conjunction
    if fatal_failure:
        joint_status = K3Status.FALSE
    elif degradable_chip_failure:
        joint_status = K3Status.FALSE
    elif any(t.status == K3Status.UNKNOWN for t in tokens) or any(t.status == K3Status.FALSE and not t.is_fatal for t in tokens):
        # Red flagged starters or yellow flagged players require scatter-gather resolution
        joint_status = K3Status.UNKNOWN
    else:
        joint_status = K3Status.TRUE

    return GuardEvaluationResult(
        joint_status=joint_status,
        tokens=tokens,
        has_fatal_failure=fatal_failure,
        has_degradable_chip_failure=degradable_chip_failure
    )
