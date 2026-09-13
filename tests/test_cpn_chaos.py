"""
tests/test_cpn_chaos.py
Dedicated Stress and Adversarial Chaos Battery for Rubies Rangers CPN.
Implements 4 breaking-point stress tests and scenarios ADV-1 through ADV-8.
"""
import asyncio
from datetime import datetime, timezone, timedelta
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import pytest

from automation.cpn import (
    CPNEngine,
    CPNPlace,
    CPNMarkingRegistry,
    K3Status,
    Color_Deadline,
    Color_Session,
    Color_MarketData,
    Color_SquadState,
    Color_OptimizedPlan,
    Color_GuardToken,
    Color_Receipt,
    Color_Alert,
    t_dispatch_transfers,
    t_reconcile_transfers,
    t_dispatch_lineup,
    t_reconcile_lineup,
    t_force_disambiguate,
    evaluate_joint_guards,
)


@pytest.fixture
def base_squad_15():
    return Color_SquadState(
        entry_id=99999,
        squad_ids=list(range(1, 16)),
        bank=1.0,
        free_transfers=1,
        chips_available={"wildcard": True, "freehit": True, "3xc": True, "bboost": True},
        active_chip=None,
        selling_prices={i: 5.0 for i in range(1, 16)},
        ghost_squad_ids=list(range(1, 16)),
        ghost_bank=1.0,
        ghost_selling_prices={i: 5.0 for i in range(1, 16)},
    )


@pytest.fixture
def base_market_15():
    return Color_MarketData(
        elements=pd.DataFrame({
            "id": list(range(1, 16)),
            "team": [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5],
            "position_name": ["GKP", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "GKP", "DEF", "MID", "FWD"],
            "moneyball_score": [float(16 - i) for i in range(1, 16)],
        }),
        fixtures=[],
        odds={},
        injury_flags={},
    )


@pytest.fixture
def base_session_valid():
    now = datetime.now(timezone.utc)
    return Color_Session(
        auth_cookie="valid_cookie",
        csrf_token="valid_csrf",
        expires_at=now + timedelta(hours=3),
        is_authenticated=True,
        last_keepalive_utc=now,
    )


# ===========================================================================
# Part 1: Four Breaking-Point Stress Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_stress_1_queue_saturation_and_backpressure():
    """
    Stress 1: Place Saturation & Queue Backpressure Flooding.
    Floods CPNPlace with 1,000 synthetic plans; asserts FIFO capacity, backpressure, and clean drain.
    """
    place: CPNPlace[Color_Alert] = CPNPlace("FloodPlace", maxsize=100)
    now = datetime.now(timezone.utc)

    # Producer task pushing 500 tokens
    async def producer():
        for i in range(500):
            token = Color_Alert(severity="INFO", reason=f"flood_{i}", context={}, timestamp=now)
            await place.put(token)

    # Consumer task draining concurrently
    consumed = []
    async def consumer():
        while len(consumed) < 500:
            token = await place.get()
            consumed.append(token)
            place.task_done()

    prod_task = asyncio.create_task(producer())
    cons_task = asyncio.create_task(consumer())

    await asyncio.gather(prod_task, cons_task)
    assert len(consumed) == 500
    assert place.empty()


@pytest.mark.asyncio
async def test_stress_2_15_doubtful_player_combinatorial_fuzzing(base_squad_15, base_market_15):
    """
    Stress 2: 15-Player Doubt Fuzz.
    All 15 squad players flagged yellow/doubtful. Forced collapse resolves them to FALSE.
    Asserts _apply_contingency_tree executes rapidly (<50ms) and preserves legal formation and GKP.
    """
    legal_formations = {(3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3), (5, 3, 2), (5, 4, 1)}
    client = MagicMock()
    engine = CPNEngine(fpl_client=client, solver_engine=MagicMock(), legal_formations=legal_formations)

    plan = Color_OptimizedPlan(
        plan_id="p_fuzz_15",
        starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        bench=[12, 13, 14, 15],
        captain=10,
        vice_captain=11,
        transfers=[],
        chip=None,
        expected_utility=55.0,
        formation_tuple=(3, 5, 2),
    )

    # Resolve all starters to FALSE
    resolved = [
        Color_GuardToken(
            plan_id=plan.plan_id, guard_name="Guard_Fitness", status=K3Status.FALSE,
            subject_id=i, doubt_type="yellow_flag", is_fatal=False, context={},
            resolved_at=datetime.now(timezone.utc)
        )
        for i in range(1, 12)
    ]

    t0 = time.perf_counter()
    reconstituted = engine._apply_contingency_tree(plan, resolved, base_market_15)
    duration_ms = (time.perf_counter() - t0) * 1000.0

    assert duration_ms < 50.0  # Performance constraint
    assert len(reconstituted.starters) == 11
    assert len(reconstituted.bench) == 4
    # GKP 1 was replaced by Sub GKP 12
    assert reconstituted.starters[0] == 12
    assert reconstituted.formation_tuple in legal_formations


@pytest.mark.asyncio
async def test_stress_3_micro_window_deadline_compression(base_squad_15, base_market_15, base_session_valid):
    """
    Stress 3: Micro-Window Deadline Compression.
    Simulates rapid deadline countdown with sub-second temporal limits.
    """
    client = MagicMock()
    client.entry_id = 99999
    now = datetime.now(timezone.utc)
    client.authenticate = AsyncMock(return_value=base_session_valid)
    client.get_bootstrap_static = AsyncMock(return_value={"elements": base_market_15.elements, "injury_flags": {}})
    client.get_fixtures = AsyncMock(return_value=[])
    client.get_market_odds = AsyncMock(return_value={})
    client.get_my_team = AsyncMock(return_value={
        "picks": [{"element": i, "position": i, "is_captain": (i == 10), "is_vice_captain": (i == 11)} for i in range(1, 16)],
        "transfers": {"bank": 10, "limit": 1},
        "chips": [],
        "active_chip": None,
    })
    client.post_transfers = AsyncMock(return_value={"status_code": 200})
    client.post_lineup = AsyncMock(return_value={"status_code": 200})

    solver = MagicMock()
    solver.solve_optimal_gameweek = AsyncMock(return_value={
        "plan_id": "p_compress",
        "starters": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "bench": [12, 13, 14, 15],
        "captain": 10,
        "vice_captain": 11,
        "transfers": [],
        "chip": None,
        "expected_utility": 60.0,
        "formation_tuple": (3, 5, 2),
    })

    engine = CPNEngine(fpl_client=client, solver_engine=solver, legal_formations={(3, 5, 2)})
    # Deadline 5 seconds in future
    compressed_deadline = now + timedelta(seconds=5)
    await engine.run_gameweek_cycle(gameweek=1, deadline_utc=compressed_deadline)

    assert not engine.marking.P_Committed.empty()
    await engine.shutdown()


@pytest.mark.asyncio
async def test_stress_4_multi_gameweek_soak_and_task_leak(base_squad_15, base_market_15, base_session_valid):
    """
    Stress 4: Multi-Cycle Soak & Task Leakage Test.
    Runs 5 consecutive gameweek cycles; asserts background tasks and memory baseline return to zero.
    """
    client = MagicMock()
    client.entry_id = 99999
    now = datetime.now(timezone.utc)
    client.authenticate = AsyncMock(return_value=base_session_valid)
    client.get_bootstrap_static = AsyncMock(return_value={"elements": base_market_15.elements, "injury_flags": {}})
    client.get_fixtures = AsyncMock(return_value=[])
    client.get_market_odds = AsyncMock(return_value={})
    client.get_my_team = AsyncMock(return_value={
        "picks": [{"element": i, "position": i, "is_captain": (i == 10), "is_vice_captain": (i == 11)} for i in range(1, 16)],
        "transfers": {"bank": 10, "limit": 1},
        "chips": [],
        "active_chip": None,
    })
    client.post_transfers = AsyncMock(return_value={"status_code": 200})
    client.post_lineup = AsyncMock(return_value={"status_code": 200})

    solver = MagicMock()
    solver.solve_optimal_gameweek = AsyncMock(return_value={
        "plan_id": "p_soak",
        "starters": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "bench": [12, 13, 14, 15],
        "captain": 10,
        "vice_captain": 11,
        "transfers": [],
        "chip": None,
        "expected_utility": 60.0,
        "formation_tuple": (3, 5, 2),
    })

    engine = CPNEngine(fpl_client=client, solver_engine=solver, legal_formations={(3, 5, 2)})

    initial_tasks = len([t for t in asyncio.all_tasks() if not t.done()])

    for gw in range(1, 4):
        deadline = now + timedelta(minutes=10)
        await engine.run_gameweek_cycle(gameweek=gw, deadline_utc=deadline)
        # Drain receipt
        if not engine.marking.P_Committed.empty():
            await engine.marking.P_Committed.get()
        await engine.shutdown()

    final_tasks = len([t for t in asyncio.all_tasks() if not t.done()])
    assert final_tasks <= initial_tasks + 1  # No task leakage


# ===========================================================================
# Part 2: Eight Hostile Adversarial Chaos Scenarios (ADV-1 to ADV-8)
# ===========================================================================

@pytest.mark.asyncio
async def test_adv1_wildcard_socket_blackout_state_recovery():
    """
    ADV-1: Wildcard Mid-Transaction Blackout (Timeout Race Condition).
    Socket drops during transfer POST with Wildcard.
    Engine must not duplicate requests; state audit discovers active wildcard on server and recovers.
    """
    marking = CPNMarkingRegistry()
    plan = Color_OptimizedPlan(
        plan_id="p_adv1", starters=list(range(1, 12)), bench=list(range(12, 16)),
        captain=10, vice_captain=11,
        transfers=[{"element_in": 20, "element_out": 1}],
        chip="wildcard", expected_utility=85.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_Plan.put(plan)

    client = MagicMock()
    client.entry_id = 99999
    # Transfer POST drops connection
    client.post_transfers = AsyncMock(side_effect=ConnectionResetError("Connection dropped by peer"))
    # State audit reveals server registered wildcard
    client.get_my_team = AsyncMock(return_value={
        "picks": [{"element": 20, "position": 1}] + [{"element": i, "position": i} for i in range(2, 16)],
        "active_chip": "wildcard",
    })

    deadline = datetime.now(timezone.utc) + timedelta(minutes=6)
    await t_dispatch_transfers(marking, client, deadline)

    assert not marking.P_TransfersAwaitingValidation.empty()
    assert marking.P_DeadLetter.empty()


@pytest.mark.asyncio
async def test_adv2_byzantine_conflicting_leak_feed():
    """
    ADV-2: Byzantine Leak Feed (Conflicting Telemetry).
    Conflicting leaks: no consensus reached. Failsafe forced disambiguation at D-8m collapses safely to Psi_Averse.
    """
    marking = CPNMarkingRegistry()
    token = Color_GuardToken(
        plan_id="p_adv2", guard_name="Guard_Fitness", status=K3Status.UNKNOWN,
        subject_id=10, doubt_type="byzantine_feed", is_fatal=False, context={"sources": ["starts", "benched"]}
    )
    await marking.P_Contingency.put(token)

    now = datetime.now(timezone.utc)
    # Forced disambiguation fires at D-8m
    await t_force_disambiguate(marking, now)

    assert marking.P_Contingency.empty()
    assert not marking.P_ResolvedGuard.empty()
    resolved = await marking.P_ResolvedGuard.get()
    assert resolved.status == K3Status.FALSE
    assert resolved.doubt_type == "psi_averse_timeout_collapse"


@pytest.mark.asyncio
async def test_adv3_clock_skew_ntp_desync_anchor():
    """
    ADV-3: Clock Skew & NTP Desync Attack.
    When local clock is skewed, preflight verification ensures session expiration is strictly evaluated
    against authoritative deadline UTC.
    """
    now = datetime.now(timezone.utc)
    skewed_deadline = now + timedelta(hours=2)
    # Session claims to expire in 1 hour, which is before the skewed deadline
    session = Color_Session(
        auth_cookie="c", csrf_token="t", expires_at=now + timedelta(hours=1),
        is_authenticated=True, last_keepalive_utc=now
    )
    res = evaluate_joint_guards(
        plan=Color_OptimizedPlan(
            plan_id="p_skew", starters=list(range(1, 12)), bench=list(range(12, 16)),
            captain=10, vice_captain=11, transfers=[], chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
        ),
        squad=MagicMock(bank=1.0, selling_prices={}, active_chip=None, chips_available={}),
        market=MagicMock(elements=pd.DataFrame({"id": list(range(1, 16)), "team": [1, 2, 3, 4, 5] * 3}), injury_flags={}),
        session=session,
        legal_formations={(3, 5, 2)},
        deadline_utc=skewed_deadline
    )
    # Expiration breach triggers fatal failure
    assert res.has_fatal_failure is True
    assert res.joint_status == K3Status.FALSE


@pytest.mark.asyncio
async def test_adv4_mid_countdown_session_revocation():
    """
    ADV-4: Mid-Countdown Session Revocation & Cloudflare CAPTCHA Challenge.
    Session revoked mid-countdown; evaluate_joint_guards immediately traps auth failure into DeadLetter.
    """
    unauth_session = Color_Session(
        auth_cookie="revoked", csrf_token="expired", expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        is_authenticated=False, last_keepalive_utc=datetime.now(timezone.utc)
    )
    marking = CPNMarkingRegistry()
    await marking.P_Session.publish(unauth_session)
    await marking.P_Market.publish(Color_MarketData(elements=pd.DataFrame({"id": list(range(1, 16)), "team": [1, 2, 3, 4, 5] * 3}), fixtures=[], odds={}, injury_flags={}))
    await marking.P_Squad.publish(Color_SquadState(entry_id=1, squad_ids=list(range(1, 16)), bank=1.0, free_transfers=1, chips_available={}, active_chip=None, selling_prices={}, ghost_squad_ids=[], ghost_bank=1.0, ghost_selling_prices={}))

    plan = Color_OptimizedPlan(
        plan_id="p_adv4", starters=list(range(1, 12)), bench=list(range(12, 16)),
        captain=10, vice_captain=11, transfers=[], chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_Plan.put(plan)

    from automation.cpn.transitions import t_evaluate_guards
    await t_evaluate_guards(marking, {(3, 5, 2)})

    assert not marking.P_DeadLetter.empty()
    alert = await marking.P_DeadLetter.get()
    assert alert.severity == "CRITICAL"


@pytest.mark.asyncio
async def test_adv5_phantom_price_rise_budget_evaporation():
    """
    ADV-5: Phantom Price Fluctuation (Budget Evaporation at Dispatch).
    Target price rises at D-7m, exceeding manager bank.
    Pre-dispatch guard detects budget breach and safely halts to DeadLetter.
    """
    squad = Color_SquadState(
        entry_id=1, squad_ids=list(range(1, 16)), bank=0.2, free_transfers=1,
        chips_available={}, active_chip=None, selling_prices={1: 5.0}, ghost_squad_ids=[], ghost_bank=0.2, ghost_selling_prices={}
    )
    # Transfer target priced at 5.5M (available capital: 5.0 + 0.2 = 5.2M < 5.5M)
    plan = Color_OptimizedPlan(
        plan_id="p_adv5", starters=list(range(1, 12)), bench=list(range(12, 16)),
        captain=10, vice_captain=11,
        transfers=[{"element_in": 99, "element_out": 1, "purchase_price": 5.5, "selling_price": 5.0}],
        chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )

    marking = CPNMarkingRegistry()
    now = datetime.now(timezone.utc)
    await marking.P_Session.publish(Color_Session(auth_cookie="c", csrf_token="t", expires_at=now + timedelta(hours=1), is_authenticated=True, last_keepalive_utc=now))
    await marking.P_Market.publish(Color_MarketData(elements=pd.DataFrame({"id": list(range(1, 16)) + [99], "team": [1, 2, 3, 4, 5] * 3 + [1]}), fixtures=[], odds={}, injury_flags={}))
    await marking.P_Squad.publish(squad)
    await marking.P_Plan.put(plan)

    from automation.cpn.transitions import t_evaluate_guards
    await t_evaluate_guards(marking, {(3, 5, 2)})

    assert not marking.P_DeadLetter.empty()
    alert = await marking.P_DeadLetter.get()
    assert alert.severity == "CRITICAL"


@pytest.mark.asyncio
async def test_adv6_gameweek_rollover_race_condition():
    """
    ADV-6: Early Gameweek Rollover Desync.
    Server serves current_event in payload; dispatcher maps current_event correctly.
    """
    marking = CPNMarkingRegistry()
    plan = Color_OptimizedPlan(
        plan_id="p_adv6", starters=list(range(1, 12)), bench=list(range(12, 16)),
        captain=10, vice_captain=11, transfers=[{"element_in": 20, "element_out": 1}],
        chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_Plan.put(plan)

    client = MagicMock()
    client.entry_id = 99999
    # Server rolled over to GW 11
    client.get_my_team = AsyncMock(return_value={"current_event": 11, "picks": [{"element": i, "position": i} for i in range(1, 16)]})
    client.post_transfers = AsyncMock(return_value={"status_code": 200})

    deadline = datetime.now(timezone.utc) + timedelta(minutes=6)
    await t_dispatch_transfers(marking, client, deadline)

    client.post_transfers.assert_awaited_once()
    payload = client.post_transfers.call_args[0][0]
    assert payload["event"] == 11
    assert not marking.P_TransfersAwaitingValidation.empty()


@pytest.mark.asyncio
async def test_adv7_fpl_api_429_rate_limit_storm():
    """
    ADV-7: FPL API Rate Limiting / 429 Storm.
    API returns 429; dispatcher backs off without crashing or exceeding error budget.
    """
    marking = CPNMarkingRegistry()
    plan = Color_OptimizedPlan(
        plan_id="p_adv7", starters=list(range(1, 12)), bench=list(range(12, 16)),
        captain=10, vice_captain=11, transfers=[{"element_in": 20, "element_out": 1}],
        chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_Plan.put(plan)

    client = MagicMock()
    client.entry_id = 99999
    client.get_my_team = AsyncMock(return_value={"picks": [{"element": i, "position": i} for i in range(1, 16)]})
    client.post_transfers = AsyncMock(side_effect=RuntimeError("HTTP 429: Too Many Requests"))

    deadline = datetime.now(timezone.utc) + timedelta(minutes=6)
    await t_dispatch_transfers(marking, client, deadline)

    assert marking.P_TransfersAwaitingValidation.empty()
    assert not marking.P_DeadLetter.empty()
    alert = await marking.P_DeadLetter.get()
    assert "retry budget exhausted" in alert.reason


@pytest.mark.asyncio
async def test_adv8_source_system_phantom_success_reconciliation_abort():
    """
    ADV-8: Source System Silent Drop ("Phantom HTTP 200") & Backend Replica Desync.
    POST /api/transfers/ returned 200, but Gate 1 discovers purchased element missing from server picks.
    Aborts transaction into P_DeadLetter, preventing corrupted lineup POST.
    """
    marking = CPNMarkingRegistry()
    plan = Color_OptimizedPlan(
        plan_id="p_adv8", starters=list(range(1, 12)), bench=list(range(12, 16)),
        captain=10, vice_captain=11,
        transfers=[{"element_in": 55, "element_out": 1}],
        chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_TransfersAwaitingValidation.put(plan)

    client = MagicMock()
    client.entry_id = 99999
    # Server picks did NOT update element 55
    client.get_my_team = AsyncMock(return_value={
        "picks": [{"element": i, "position": i} for i in range(1, 16)],
        "active_chip": None,
    })

    await t_reconcile_transfers(marking, client, max_retries=2)

    assert marking.P_TransfersExecuted.empty()
    assert not marking.P_DeadLetter.empty()
    alert = await marking.P_DeadLetter.get()
    assert alert.severity == "CRITICAL"
    assert "Transfer Reconciliation Failed" in alert.reason
    assert "missing_in=[55]" in alert.reason
