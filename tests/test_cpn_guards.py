"""
tests/test_cpn_guards.py
Comprehensive unit tests for Kleene K3 transition guards and chip safety matrix.
Tests 32 truth-table cells and full 16-case chip degradation matrix.
"""
from datetime import datetime, timezone, timedelta
import pandas as pd
import pytest
from automation.cpn.tokens import (
    K3Status,
    Color_OptimizedPlan,
    Color_SquadState,
    Color_MarketData,
    Color_Session,
)
from automation.cpn.guards import (
    evaluate_budget_guard,
    evaluate_club_cap_guard,
    evaluate_formation_guard,
    evaluate_hit_utility_guard,
    evaluate_fitness_guard,
    evaluate_chip_safety_guard,
    evaluate_preflight_session_guard,
    evaluate_time_window_guard,
    evaluate_joint_guards,
)


@pytest.fixture
def base_squad():
    return Color_SquadState(
        entry_id=12345,
        squad_ids=list(range(1, 16)),
        bank=1.0,
        free_transfers=1,
        chips_available={"3xc": True, "bboost": True, "wildcard": True, "freehit": True},
        active_chip=None,
        selling_prices={i: 5.0 for i in range(1, 16)},
        ghost_squad_ids=list(range(1, 16)),
        ghost_bank=1.0,
        ghost_selling_prices={i: 5.0 for i in range(1, 16)},
    )


@pytest.fixture
def base_market():
    # 15 players distributed across clubs 1, 2, 3, 4, 5
    teams = [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5]
    elements = pd.DataFrame({
        "id": list(range(1, 16)),
        "team": teams,
        "position_name": ["GKP", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "GKP", "DEF", "MID", "FWD"],
        "moneyball_score": [5.0] * 15,
    })
    return Color_MarketData(
        elements=elements,
        fixtures=[],
        odds={},
        injury_flags={},
    )


@pytest.fixture
def base_session():
    now = datetime.now(timezone.utc)
    return Color_Session(
        auth_cookie="cookie",
        csrf_token="csrf",
        expires_at=now + timedelta(hours=2),
        is_authenticated=True,
        last_keepalive_utc=now,
    )


@pytest.fixture
def base_plan():
    return Color_OptimizedPlan(
        plan_id="plan_001",
        starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        bench=[12, 13, 14, 15],
        captain=10,
        vice_captain=11,
        transfers=[],
        chip=None,
        expected_utility=60.0,
        formation_tuple=(3, 5, 2),
    )


# ---------------------------------------------------------------------------
# 1. Budget Guard Tests
# ---------------------------------------------------------------------------
def test_budget_guard_no_transfers(base_plan, base_squad):
    assert evaluate_budget_guard(base_plan, base_squad) == K3Status.TRUE


def test_budget_guard_within_budget(base_plan, base_squad):
    plan = Color_OptimizedPlan(
        plan_id="p1", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11,
        transfers=[{"element_in": 20, "element_out": 1, "purchase_price": 5.5, "selling_price": 5.0}],
        chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    # Bank = 1.0, sale = 5.0, total available = 6.0 >= 5.5
    assert evaluate_budget_guard(plan, base_squad) == K3Status.TRUE


def test_budget_guard_exceeded(base_plan, base_squad):
    plan = Color_OptimizedPlan(
        plan_id="p2", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11,
        transfers=[{"element_in": 20, "element_out": 1, "purchase_price": 6.5, "selling_price": 5.0}],
        chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    # Bank = 1.0, sale = 5.0, total available = 6.0 < 6.5
    assert evaluate_budget_guard(plan, base_squad) == K3Status.FALSE


# ---------------------------------------------------------------------------
# 2. Club Cap Guard Tests
# ---------------------------------------------------------------------------
def test_club_cap_guard_legal(base_plan, base_market):
    assert evaluate_club_cap_guard(base_plan, base_market) == K3Status.TRUE


def test_club_cap_guard_exceeded(base_plan, base_market):
    # Set 4 players to team 1
    market_df = base_market.elements.copy()
    market_df.loc[market_df["id"] == 4, "team"] = 1
    m = Color_MarketData(elements=market_df, fixtures=[], odds={}, injury_flags={})
    assert evaluate_club_cap_guard(base_plan, m) == K3Status.FALSE


def test_club_cap_guard_missing_player_unknown(base_plan, base_market):
    # Exclude player 15 from market data
    market_df = base_market.elements[base_market.elements["id"] != 15].copy()
    m = Color_MarketData(elements=market_df, fixtures=[], odds={}, injury_flags={})
    assert evaluate_club_cap_guard(base_plan, m) == K3Status.UNKNOWN


# ---------------------------------------------------------------------------
# 3. Formation Guard Tests
# ---------------------------------------------------------------------------
def test_formation_guard(base_plan):
    legal = {(3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3), (5, 3, 2), (5, 4, 1)}
    assert evaluate_formation_guard(base_plan, legal) == K3Status.TRUE

    illegal_plan = Color_OptimizedPlan(
        plan_id="p_ill", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip=None,
        expected_utility=60.0, formation_tuple=(2, 5, 3)
    )
    assert evaluate_formation_guard(illegal_plan, legal) == K3Status.FALSE


# ---------------------------------------------------------------------------
# 4. Hit Utility Guard Tests
# ---------------------------------------------------------------------------
def test_hit_utility_guard(base_plan, base_squad):
    # 0 excess transfers, utility 60 vs baseline 55 -> TRUE
    assert evaluate_hit_utility_guard(base_plan, base_squad, baseline_utility=55.0) == K3Status.TRUE

    # 1 excess transfer (4 pt hit). Plan utility = 58 - 4 = 54. Baseline = 55.
    # 54 >= 55 - 2.0 (53) -> UNKNOWN marginal boundary
    plan_marginal = Color_OptimizedPlan(
        plan_id="p_m", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11,
        transfers=[{"element_in": 20, "element_out": 1}, {"element_in": 21, "element_out": 2}],
        chip=None, expected_utility=58.0, formation_tuple=(3, 5, 2)
    )
    assert evaluate_hit_utility_guard(plan_marginal, base_squad, baseline_utility=55.0) == K3Status.UNKNOWN

    # Plan utility = 50 - 4 = 46. Baseline = 55. 46 < 53 -> FALSE
    plan_poor = Color_OptimizedPlan(
        plan_id="p_poor", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11,
        transfers=[{"element_in": 20, "element_out": 1}, {"element_in": 21, "element_out": 2}],
        chip=None, expected_utility=50.0, formation_tuple=(3, 5, 2)
    )
    assert evaluate_hit_utility_guard(plan_poor, base_squad, baseline_utility=55.0) == K3Status.FALSE


# ---------------------------------------------------------------------------
# 5. Fitness Guard Tests
# ---------------------------------------------------------------------------
def test_fitness_guard_healthy(base_plan, base_market):
    assert len(evaluate_fitness_guard(base_plan, base_market)) == 0


def test_fitness_guard_yellow_and_red_flags(base_plan, base_market):
    market = Color_MarketData(
        elements=base_market.elements,
        fixtures=[],
        odds={},
        injury_flags={
            10: {"chance_of_playing": 50, "news": "Hamstring"},
            11: {"chance_of_playing": 0, "news": "Suspended"},
            1: {"chance_of_playing": 100, "news": ""},
        }
    )
    tokens = evaluate_fitness_guard(base_plan, market)
    assert len(tokens) == 2
    token_map = {t.subject_id: t for t in tokens}
    assert token_map[10].status == K3Status.UNKNOWN
    assert token_map[10].doubt_type == "yellow_flag"
    assert token_map[11].status == K3Status.FALSE
    assert token_map[11].doubt_type == "red_flag"


# ---------------------------------------------------------------------------
# 6. Session Guard Tests
# ---------------------------------------------------------------------------
def test_preflight_session_guard(base_session):
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=1)
    assert evaluate_preflight_session_guard(base_session, deadline) == K3Status.TRUE

    unauth_session = Color_Session(
        auth_cookie="c", csrf_token="t", expires_at=now + timedelta(hours=2),
        is_authenticated=False, last_keepalive_utc=now
    )
    assert evaluate_preflight_session_guard(unauth_session, deadline) == K3Status.FALSE

    expired_session = Color_Session(
        auth_cookie="c", csrf_token="t", expires_at=now - timedelta(minutes=5),
        is_authenticated=True, last_keepalive_utc=now
    )
    assert evaluate_preflight_session_guard(expired_session, deadline) == K3Status.FALSE


# ---------------------------------------------------------------------------
# 7. Time Window Guard Tests
# ---------------------------------------------------------------------------
def test_time_window_guard():
    now = datetime.now(timezone.utc)
    # Window is 60s to 420s (D-7m to D-1m)
    deadline_in_window = now + timedelta(seconds=180)
    assert evaluate_time_window_guard(deadline_in_window, now) == K3Status.TRUE

    deadline_early = now + timedelta(seconds=600)  # > 420s
    assert evaluate_time_window_guard(deadline_early, now) == K3Status.UNKNOWN

    deadline_late = now + timedelta(seconds=30)  # < 60s
    assert evaluate_time_window_guard(deadline_late, now) == K3Status.FALSE


# ---------------------------------------------------------------------------
# 8. Chip Safety Guard Matrix (16 Tests: 4 Chips x 4 States)
# ---------------------------------------------------------------------------
# --- Triple Captain (3xc) ---
def test_chip_safety_3xc_clean_pass(base_plan, base_squad, base_market):
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="3xc",
        expected_utility=70.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, base_squad, base_market)
    assert status == K3Status.TRUE
    assert len(tokens) == 0
    assert not is_fatal


def test_chip_safety_3xc_scatter_doubt(base_plan, base_squad, base_market):
    market = Color_MarketData(
        elements=base_market.elements, fixtures=[], odds={},
        injury_flags={10: {"chance_of_playing": 75}}
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="3xc",
        expected_utility=70.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, base_squad, market)
    assert status == K3Status.UNKNOWN
    assert len(tokens) == 1
    assert not is_fatal


def test_chip_safety_3xc_degradable_failure(base_plan, base_squad, base_market):
    market = Color_MarketData(
        elements=base_market.elements, fixtures=[], odds={},
        injury_flags={10: {"chance_of_playing": 25}}  # < 50 -> degradable
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="3xc",
        expected_utility=70.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, base_squad, market)
    assert status == K3Status.FALSE
    assert not is_fatal  # Degradable!


def test_chip_safety_3xc_fatal_already_active(base_plan, base_squad, base_market):
    squad = Color_SquadState(
        entry_id=123, squad_ids=base_squad.squad_ids, bank=1.0, free_transfers=1,
        chips_available={"3xc": True}, active_chip="wildcard", selling_prices=base_squad.selling_prices,
        ghost_squad_ids=base_squad.ghost_squad_ids, ghost_bank=1.0, ghost_selling_prices=base_squad.ghost_selling_prices
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="3xc",
        expected_utility=70.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, squad, base_market)
    assert status == K3Status.FALSE
    assert is_fatal


# --- Bench Boost (bboost) ---
def test_chip_safety_bboost_clean_pass(base_plan, base_squad, base_market):
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="bboost",
        expected_utility=75.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, base_squad, base_market)
    assert status == K3Status.TRUE
    assert not is_fatal


def test_chip_safety_bboost_scatter_doubt(base_plan, base_squad, base_market):
    market = Color_MarketData(
        elements=base_market.elements, fixtures=[], odds={},
        injury_flags={12: {"chance_of_playing": 50}}  # Bench player 12 doubtful
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="bboost",
        expected_utility=75.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, base_squad, market)
    assert status == K3Status.UNKNOWN
    assert len(tokens) == 1
    assert not is_fatal


def test_chip_safety_bboost_degradable_failure(base_plan, base_squad, base_market):
    market = Color_MarketData(
        elements=base_market.elements, fixtures=[], odds={},
        injury_flags={13: {"chance_of_playing": 0}}  # Bench player ruled out
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="bboost",
        expected_utility=75.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, base_squad, market)
    assert status == K3Status.FALSE
    assert not is_fatal  # Degradable!


def test_chip_safety_bboost_fatal_unavailable(base_plan, base_squad, base_market):
    squad = Color_SquadState(
        entry_id=123, squad_ids=base_squad.squad_ids, bank=1.0, free_transfers=1,
        chips_available={"bboost": False}, active_chip=None, selling_prices=base_squad.selling_prices,
        ghost_squad_ids=base_squad.ghost_squad_ids, ghost_bank=1.0, ghost_selling_prices=base_squad.ghost_selling_prices
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="bboost",
        expected_utility=75.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, squad, base_market)
    assert status == K3Status.FALSE
    assert is_fatal


# --- Wildcard (wildcard) ---
def test_chip_safety_wildcard_clean_pass(base_plan, base_squad, base_market):
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="wildcard",
        expected_utility=80.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, base_squad, base_market)
    assert status == K3Status.TRUE
    assert not is_fatal


def test_chip_safety_wildcard_banked_ft_preservation(base_plan, base_squad, base_market):
    # Squad has 4 FTs, expected rollover = min(5, 5) = 5 <= 5 -> True
    squad = Color_SquadState(
        entry_id=123, squad_ids=base_squad.squad_ids, bank=1.0, free_transfers=4,
        chips_available={"wildcard": True}, active_chip=None, selling_prices=base_squad.selling_prices,
        ghost_squad_ids=base_squad.ghost_squad_ids, ghost_bank=1.0, ghost_selling_prices=base_squad.ghost_selling_prices
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="wildcard",
        expected_utility=80.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, squad, base_market, max_banked_ft=5)
    assert status == K3Status.TRUE


def test_chip_safety_wildcard_overflow_fatal(base_plan, base_squad, base_market):
    # If squad free_transfers exceeds max_banked_ft (e.g. 6 > 5)
    squad = Color_SquadState(
        entry_id=123, squad_ids=base_squad.squad_ids, bank=1.0, free_transfers=6,
        chips_available={"wildcard": True}, active_chip=None, selling_prices=base_squad.selling_prices,
        ghost_squad_ids=base_squad.ghost_squad_ids, ghost_bank=1.0, ghost_selling_prices=base_squad.ghost_selling_prices
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="wildcard",
        expected_utility=80.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, squad, base_market, max_banked_ft=5)
    assert status == K3Status.FALSE
    assert is_fatal


def test_chip_safety_wildcard_fatal_already_active(base_plan, base_squad, base_market):
    squad = Color_SquadState(
        entry_id=123, squad_ids=base_squad.squad_ids, bank=1.0, free_transfers=1,
        chips_available={"wildcard": True}, active_chip="freehit", selling_prices=base_squad.selling_prices,
        ghost_squad_ids=base_squad.ghost_squad_ids, ghost_bank=1.0, ghost_selling_prices=base_squad.ghost_selling_prices
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="wildcard",
        expected_utility=80.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, squad, base_market)
    assert status == K3Status.FALSE
    assert is_fatal


# --- Free Hit (freehit) ---
def test_chip_safety_freehit_clean_pass(base_plan, base_squad, base_market):
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="freehit",
        expected_utility=85.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, base_squad, base_market)
    assert status == K3Status.TRUE
    assert not is_fatal


def test_chip_safety_freehit_missing_ghost_squad_fatal(base_plan, base_squad, base_market):
    squad = Color_SquadState(
        entry_id=123, squad_ids=base_squad.squad_ids, bank=1.0, free_transfers=1,
        chips_available={"freehit": True}, active_chip=None, selling_prices=base_squad.selling_prices,
        ghost_squad_ids=[],  # Missing!
        ghost_bank=1.0, ghost_selling_prices=base_squad.ghost_selling_prices
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="freehit",
        expected_utility=85.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, squad, base_market)
    assert status == K3Status.FALSE
    assert is_fatal


def test_chip_safety_freehit_invalid_ghost_squad_len_fatal(base_plan, base_squad, base_market):
    squad = Color_SquadState(
        entry_id=123, squad_ids=base_squad.squad_ids, bank=1.0, free_transfers=1,
        chips_available={"freehit": True}, active_chip=None, selling_prices=base_squad.selling_prices,
        ghost_squad_ids=[1, 2, 3],  # Only 3 players!
        ghost_bank=1.0, ghost_selling_prices=base_squad.ghost_selling_prices
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="freehit",
        expected_utility=85.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, squad, base_market)
    assert status == K3Status.FALSE
    assert is_fatal


def test_chip_safety_freehit_unavailable_fatal(base_plan, base_squad, base_market):
    squad = Color_SquadState(
        entry_id=123, squad_ids=base_squad.squad_ids, bank=1.0, free_transfers=1,
        chips_available={"freehit": False}, active_chip=None, selling_prices=base_squad.selling_prices,
        ghost_squad_ids=base_squad.ghost_squad_ids, ghost_bank=1.0, ghost_selling_prices=base_squad.ghost_selling_prices
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="freehit",
        expected_utility=85.0, formation_tuple=(3, 5, 2)
    )
    status, tokens, is_fatal = evaluate_chip_safety_guard(plan, squad, base_market)
    assert status == K3Status.FALSE
    assert is_fatal


# ---------------------------------------------------------------------------
# 9. Joint Guard Evaluator Tests
# ---------------------------------------------------------------------------
def test_joint_guards_all_true(base_plan, base_squad, base_market, base_session):
    legal = {(3, 5, 2)}
    res = evaluate_joint_guards(base_plan, base_squad, base_market, base_session, legal)
    assert res.joint_status == K3Status.TRUE
    assert not res.has_fatal_failure
    assert not res.has_degradable_chip_failure


def test_joint_guards_fatal_formation_failure(base_plan, base_squad, base_market, base_session):
    legal = {(4, 4, 2)}  # plan is (3, 5, 2)
    res = evaluate_joint_guards(base_plan, base_squad, base_market, base_session, legal)
    assert res.joint_status == K3Status.FALSE
    assert res.has_fatal_failure
    assert not res.has_degradable_chip_failure


def test_joint_guards_degradable_chip_failure(base_plan, base_squad, base_market, base_session):
    legal = {(3, 5, 2)}
    market = Color_MarketData(
        elements=base_market.elements, fixtures=[], odds={},
        injury_flags={10: {"chance_of_playing": 25}}
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="3xc",
        expected_utility=70.0, formation_tuple=(3, 5, 2)
    )
    res = evaluate_joint_guards(plan, base_squad, market, base_session, legal)
    assert res.joint_status == K3Status.FALSE
    assert not res.has_fatal_failure
    assert res.has_degradable_chip_failure


def test_joint_guards_scatter_unknown(base_plan, base_squad, base_market, base_session):
    legal = {(3, 5, 2)}
    market = Color_MarketData(
        elements=base_market.elements, fixtures=[], odds={},
        injury_flags={10: {"chance_of_playing": 75}}
    )
    res = evaluate_joint_guards(base_plan, base_squad, market, base_session, legal)
    assert res.joint_status == K3Status.UNKNOWN
    assert not res.has_fatal_failure
    assert not res.has_degradable_chip_failure


def test_joint_guards_session_auth_failure(base_plan, base_squad, base_market):
    now = datetime.now(timezone.utc)
    session = Color_Session(
        auth_cookie="c", csrf_token="t", expires_at=now + timedelta(hours=1),
        is_authenticated=False, last_keepalive_utc=now
    )
    res = evaluate_joint_guards(base_plan, base_squad, base_market, session, {(3, 5, 2)})
    assert res.joint_status == K3Status.FALSE
    assert res.has_fatal_failure


def test_joint_guards_expired_session(base_plan, base_squad, base_market):
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=1)
    session = Color_Session(
        auth_cookie="c", csrf_token="t", expires_at=now - timedelta(minutes=10),
        is_authenticated=True, last_keepalive_utc=now
    )
    res = evaluate_joint_guards(base_plan, base_squad, base_market, session, {(3, 5, 2)}, deadline_utc=deadline)
    assert res.joint_status == K3Status.FALSE
    assert res.has_fatal_failure


def test_joint_guards_budget_failure(base_plan, base_squad, base_market, base_session):
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11,
        transfers=[{"element_in": 20, "element_out": 1, "purchase_price": 10.0, "selling_price": 5.0}],
        chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    res = evaluate_joint_guards(plan, base_squad, base_market, base_session, {(3, 5, 2)})
    assert res.joint_status == K3Status.FALSE
    assert res.has_fatal_failure


def test_joint_guards_club_cap_failure(base_plan, base_squad, base_market, base_session):
    market_df = base_market.elements.copy()
    market_df.loc[market_df["id"] == 4, "team"] = 1  # 4 players in club 1
    market = Color_MarketData(elements=market_df, fixtures=[], odds={}, injury_flags={})
    res = evaluate_joint_guards(base_plan, base_squad, market, base_session, {(3, 5, 2)})
    assert res.joint_status == K3Status.FALSE
    assert res.has_fatal_failure


def test_joint_guards_red_flag_fitness(base_plan, base_squad, base_market, base_session):
    market = Color_MarketData(
        elements=base_market.elements, fixtures=[], odds={},
        injury_flags={10: {"chance_of_playing": 0}}
    )
    res = evaluate_joint_guards(base_plan, base_squad, market, base_session, {(3, 5, 2)})
    assert res.joint_status == K3Status.UNKNOWN
    assert not res.has_fatal_failure


def test_joint_guards_fatal_chip_failure(base_plan, base_squad, base_market, base_session):
    squad = Color_SquadState(
        entry_id=123, squad_ids=base_squad.squad_ids, bank=1.0, free_transfers=1,
        chips_available={"wildcard": False}, active_chip=None, selling_prices=base_squad.selling_prices,
        ghost_squad_ids=base_squad.ghost_squad_ids, ghost_bank=1.0, ghost_selling_prices=base_squad.ghost_selling_prices
    )
    plan = Color_OptimizedPlan(
        plan_id="p", starters=base_plan.starters, bench=base_plan.bench,
        captain=10, vice_captain=11, transfers=[], chip="wildcard",
        expected_utility=80.0, formation_tuple=(3, 5, 2)
    )
    res = evaluate_joint_guards(plan, squad, base_market, base_session, {(3, 5, 2)})
    assert res.joint_status == K3Status.FALSE
    assert res.has_fatal_failure
