"""
tests/test_cpn_transitions.py
Unit tests verifying all 14 CPN transitions, retries, jitter, and reconciliation gates.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import pandas as pd
import pytest

from automation.cpn.tokens import (
    K3Status,
    Color_Deadline,
    Color_Session,
    Color_MarketData,
    Color_SquadState,
    Color_OptimizedPlan,
    Color_GuardToken,
    Color_Receipt,
    Color_Alert,
)
from automation.cpn.places import CPNMarkingRegistry
from automation.cpn.transitions import (
    t_preflight_and_ingest,
    t_session_keepalive,
    t_simulate_and_solve,
    t_evaluate_guards,
    t_abort_and_alert,
    t_degrade_plan,
    t_scatter_indeterminate,
    t_early_leak_resolve,
    t_force_disambiguate,
    t_gather_and_reevaluate,
    t_dispatch_transfers,
    t_reconcile_transfers,
    t_dispatch_lineup,
    t_reconcile_lineup,
)


@pytest.fixture
def marking():
    return CPNMarkingRegistry()


@pytest.fixture
def mock_fpl_client():
    client = MagicMock()
    client.entry_id = 12345
    now = datetime.now(timezone.utc)
    client.authenticate = AsyncMock(return_value=Color_Session(
        auth_cookie="cookie", csrf_token="csrf", expires_at=now + timedelta(hours=2),
        is_authenticated=True, last_keepalive_utc=now
    ))
    client.get_bootstrap_static = AsyncMock(return_value={
        "elements": pd.DataFrame({
            "id": list(range(1, 16)),
            "team": [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5],
            "position_name": ["GKP", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "GKP", "DEF", "MID", "FWD"],
            "moneyball_score": [5.0] * 15,
        }),
        "injury_flags": {}
    })
    client.get_fixtures = AsyncMock(return_value=[{"event": 1}])
    client.get_market_odds = AsyncMock(return_value={})
    client.get_my_team = AsyncMock(return_value={
        "picks": [{"element": i, "position": i, "selling_price": 50, "is_captain": (i == 10), "is_vice_captain": (i == 11)} for i in range(1, 16)],
        "transfers": {"bank": 10, "limit": 1},
        "chips": [{"name": "wildcard", "status_for_entry": "available"}],
        "active_chip": None,
        "current_event": 1,
    })
    client.post_transfers = AsyncMock(return_value={"status_code": 200})
    client.post_lineup = AsyncMock(return_value={"status_code": 200})
    client.check_session_alive = AsyncMock(return_value=True)
    client.listen_for_leak = AsyncMock(return_value=None)
    return client


@pytest.mark.asyncio
async def test_t_preflight_and_ingest_success(marking, mock_fpl_client):
    now = datetime.now(timezone.utc)
    deadline = Color_Deadline(gameweek=1, deadline_utc=now, cutoff_disambiguation_utc=now)
    await marking.P_Timer.put(deadline)

    await t_preflight_and_ingest(marking, mock_fpl_client)

    assert marking.P_Session.peek() is not None
    assert marking.P_Market.peek() is not None
    assert marking.P_Squad.peek() is not None
    assert marking.P_DeadLetter.empty()


@pytest.mark.asyncio
async def test_t_preflight_and_ingest_failure(marking, mock_fpl_client):
    now = datetime.now(timezone.utc)
    deadline = Color_Deadline(gameweek=1, deadline_utc=now, cutoff_disambiguation_utc=now)
    await marking.P_Timer.put(deadline)

    mock_fpl_client.get_bootstrap_static = AsyncMock(side_effect=RuntimeError("Bootstrap HTTP 500"))
    await t_preflight_and_ingest(marking, mock_fpl_client)

    assert not marking.P_DeadLetter.empty()
    alert = await marking.P_DeadLetter.get()
    assert alert.severity == "CRITICAL"
    assert "Bootstrap HTTP 500" in alert.reason


@pytest.mark.asyncio
async def test_t_simulate_and_solve(marking):
    now = datetime.now(timezone.utc)
    session = Color_Session(auth_cookie="c", csrf_token="t", expires_at=now, is_authenticated=True, last_keepalive_utc=now)
    await marking.P_Session.publish(session)

    market = Color_MarketData(
        elements=pd.DataFrame({"id": list(range(1, 16)), "position_name": ["MID"] * 15, "team": [1] * 15}),
        fixtures=[], odds={}, injury_flags={}
    )
    await marking.P_Market.publish(market)

    squad = Color_SquadState(
        entry_id=123, squad_ids=list(range(1, 16)), bank=1.0, free_transfers=1,
        chips_available={}, active_chip=None, selling_prices={}, ghost_squad_ids=[], ghost_bank=1.0, ghost_selling_prices={}
    )
    await marking.P_Squad.publish(squad)

    mock_solver = MagicMock()
    mock_solver.solve_optimal_gameweek = AsyncMock(return_value={
        "plan_id": "plan_opt_1",
        "starters": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "bench": [12, 13, 14, 15],
        "captain": 10,
        "vice_captain": 11,
        "transfers": [],
        "chip": None,
        "expected_utility": 65.0,
        "formation_tuple": (3, 5, 2),
    })

    await t_simulate_and_solve(marking, mock_solver)
    assert not marking.P_Plan.empty()
    plan = await marking.P_Plan.get()
    assert plan.plan_id == "plan_opt_1"


@pytest.mark.asyncio
async def test_t_evaluate_guards_routes_to_plan_degrade(marking):
    now = datetime.now(timezone.utc)
    session = Color_Session(auth_cookie="c", csrf_token="t", expires_at=now + timedelta(hours=2), is_authenticated=True, last_keepalive_utc=now)
    await marking.P_Session.publish(session)

    market = Color_MarketData(
        elements=pd.DataFrame({
            "id": list(range(1, 16)),
            "position_name": ["MID"] * 15,
            "team": [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5]
        }),
        fixtures=[], odds={},
        injury_flags={10: {"chance_of_playing": 25}}  # Captain ruled out on 3xc -> degradable
    )
    await marking.P_Market.publish(market)

    squad = Color_SquadState(
        entry_id=123, squad_ids=list(range(1, 16)), bank=1.0, free_transfers=1,
        chips_available={"3xc": True}, active_chip=None, selling_prices={}, ghost_squad_ids=[], ghost_bank=1.0, ghost_selling_prices={}
    )
    await marking.P_Squad.publish(squad)

    plan = Color_OptimizedPlan(
        plan_id="p_chip_fail", starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], bench=[12, 13, 14, 15],
        captain=10, vice_captain=11, transfers=[], chip="3xc", expected_utility=70.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_Plan.put(plan)

    await t_evaluate_guards(marking, {(3, 5, 2)})
    assert not marking.P_PlanDegrade.empty()
    assert marking.P_Plan.empty()


@pytest.mark.asyncio
async def test_t_evaluate_guards_routes_to_scatter_and_happy_paths(marking):
    now = datetime.now(timezone.utc)
    session = Color_Session("c", "t", now + timedelta(hours=2), True, now)
    await marking.P_Session.publish(session)

    squad = Color_SquadState(
        entry_id=123, squad_ids=list(range(1, 16)), bank=1.0, free_transfers=1,
        chips_available={}, active_chip=None, selling_prices={1: 5.0}, ghost_squad_ids=[], ghost_bank=1.0, ghost_selling_prices={}
    )
    await marking.P_Squad.publish(squad)

    # 1. Unknown fitness -> routes to P_PendingPlan and P_Contingency
    market_doubt = Color_MarketData(
        elements=pd.DataFrame({"id": list(range(1, 16)), "position_name": ["MID"] * 15, "team": [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5]}),
        fixtures=[], odds={}, injury_flags={10: {"chance_of_playing": 75}}
    )
    await marking.P_Market.publish(market_doubt)
    plan_doubt = Color_OptimizedPlan("p_doubt", list(range(1, 12)), list(range(12, 16)), 10, 11, [], None, 60.0, (3, 5, 2))
    await marking.P_Plan.put(plan_doubt)
    await t_evaluate_guards(marking, {(3, 5, 2)})
    assert not marking.P_PendingPlan.empty()
    assert not marking.P_Contingency.empty()

    # Clear
    await marking.P_PendingPlan.get()
    await marking.P_Contingency.get()

    # 2. Happy path with transfers -> routes to P_Plan
    market_clean = Color_MarketData(
        elements=pd.DataFrame({"id": list(range(1, 21)), "position_name": ["MID"] * 20, "team": [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6, 6, 6]}),
        fixtures=[], odds={}, injury_flags={}
    )
    await marking.P_Market.publish(market_clean)
    plan_xfer = Color_OptimizedPlan(
        "p_clean_xfer", list(range(1, 12)), list(range(12, 16)), 10, 11,
        [{"element_in": 20, "element_out": 1, "purchase_price": 5.0, "selling_price": 5.0}],
        None, 65.0, (3, 5, 2)
    )
    await marking.P_Plan.put(plan_xfer)
    await t_evaluate_guards(marking, {(3, 5, 2)})
    assert not marking.P_Plan.empty()
    assert (await marking.P_Plan.get()).plan_id == "p_clean_xfer"

    # 3. Happy path without transfers -> routes to P_TransfersExecuted
    plan_no_xfer = Color_OptimizedPlan(
        "p_clean_no_xfer", list(range(1, 12)), list(range(12, 16)), 10, 11, [], None, 65.0, (3, 5, 2)
    )
    await marking.P_Plan.put(plan_no_xfer)
    await t_evaluate_guards(marking, {(3, 5, 2)})
    assert not marking.P_TransfersExecuted.empty()
    assert (await marking.P_TransfersExecuted.get()).plan_id == "p_clean_no_xfer"


@pytest.mark.asyncio
async def test_t_degrade_plan(marking):
    plan = Color_OptimizedPlan(
        plan_id="p_deg", starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], bench=[12, 13, 14, 15],
        captain=10, vice_captain=11, transfers=[], chip="3xc", expected_utility=70.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_PlanDegrade.put(plan)

    await t_degrade_plan(marking)
    assert not marking.P_Plan.empty()
    degraded = await marking.P_Plan.get()
    assert degraded.chip is None
    assert degraded.is_degraded is True
    assert degraded.captain == 11  # Captain switched to vice captain for stripped 3xc


@pytest.mark.asyncio
async def test_t_scatter_and_early_leak_resolve(marking, mock_fpl_client):
    plan = Color_OptimizedPlan(
        plan_id="p_scatter", starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], bench=[12, 13, 14, 15],
        captain=10, vice_captain=11, transfers=[], chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    unknown_token = Color_GuardToken(
        plan_id=plan.plan_id, guard_name="Guard_Fitness", status=K3Status.UNKNOWN,
        subject_id=10, doubt_type="yellow_flag", is_fatal=False, context={"chance": 50}
    )

    await t_scatter_indeterminate(marking, plan, [unknown_token])
    assert not marking.P_PendingPlan.empty()
    assert not marking.P_Contingency.empty()

    # Early leak resolves: player starts!
    mock_fpl_client.listen_for_leak = AsyncMock(return_value={"starts": True})
    await t_early_leak_resolve(marking, mock_fpl_client)

    assert not marking.P_ResolvedGuard.empty()
    resolved = await marking.P_ResolvedGuard.get()
    assert resolved.status == K3Status.TRUE
    assert resolved.subject_id == 10


@pytest.mark.asyncio
async def test_t_force_disambiguate(marking):
    now = datetime.now(timezone.utc)
    token = Color_GuardToken(
        plan_id="p", guard_name="Guard_Fitness", status=K3Status.UNKNOWN,
        subject_id=9, doubt_type="yellow_flag", is_fatal=False, context={}
    )
    await marking.P_Contingency.put(token)

    await t_force_disambiguate(marking, now)
    assert marking.P_Contingency.empty()
    assert not marking.P_ResolvedGuard.empty()
    resolved = await marking.P_ResolvedGuard.get()
    assert resolved.status == K3Status.FALSE


@pytest.mark.asyncio
async def test_t_gather_and_reevaluate(marking):
    market = Color_MarketData(
        elements=pd.DataFrame({
            "id": list(range(1, 16)),
            "position_name": ["GKP", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "GKP", "DEF", "MID", "FWD"],
            "team": [1] * 15
        }),
        fixtures=[], odds={}, injury_flags={}
    )
    await marking.P_Market.publish(market)

    plan = Color_OptimizedPlan(
        plan_id="p_gather", starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], bench=[12, 13, 14, 15],
        captain=10, vice_captain=11, transfers=[], chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_PendingPlan.put(plan)

    # Ruled out starter 10 (captain)
    resolved_guard = Color_GuardToken(
        plan_id=plan.plan_id, guard_name="Guard_Fitness", status=K3Status.FALSE,
        subject_id=10, doubt_type="yellow_flag", is_fatal=False, context={}
    )
    await marking.P_ResolvedGuard.put(resolved_guard)

    await t_gather_and_reevaluate(marking)
    assert not marking.P_Plan.empty()
    reconstituted = await marking.P_Plan.get()
    assert 10 not in reconstituted.starters
    assert reconstituted.captain == 11  # Switched to VC


@pytest.mark.asyncio
async def test_t_dispatch_transfers_and_reconcile_transfers_success(marking, mock_fpl_client):
    plan = Color_OptimizedPlan(
        plan_id="p_xfer", starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], bench=[12, 13, 14, 15],
        captain=10, vice_captain=11,
        transfers=[{"element_in": 20, "element_out": 1, "purchase_price": 5.0, "selling_price": 5.0}],
        chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_Plan.put(plan)

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(minutes=6)

    # 1. Dispatch
    await t_dispatch_transfers(marking, mock_fpl_client, deadline)
    assert not marking.P_TransfersAwaitingValidation.empty()

    # 2. Gate 1 Reconciliation - mock server reflects transfer (element 20 in picks, 1 removed)
    server_picks = [{"element": 20, "position": 1, "selling_price": 50, "is_captain": False, "is_vice_captain": False}]
    for i in range(2, 16):
        server_picks.append({"element": i, "position": i, "selling_price": 50, "is_captain": (i == 10), "is_vice_captain": (i == 11)})

    mock_fpl_client.get_my_team = AsyncMock(return_value={
        "picks": server_picks,
        "transfers": {"bank": 10, "limit": 0},
        "chips": [],
        "active_chip": None,
    })

    await t_reconcile_transfers(marking, mock_fpl_client, max_retries=2)
    assert not marking.P_TransfersExecuted.empty()
    assert marking.P_DeadLetter.empty()


@pytest.mark.asyncio
async def test_t_reconcile_transfers_phantom_drop_fails_to_deadletter(marking, mock_fpl_client):
    plan = Color_OptimizedPlan(
        plan_id="p_phantom", starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], bench=[12, 13, 14, 15],
        captain=10, vice_captain=11,
        transfers=[{"element_in": 99, "element_out": 1}],
        chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_TransfersAwaitingValidation.put(plan)

    # Server still has old squad (element 99 is missing)
    mock_fpl_client.get_my_team = AsyncMock(return_value={
        "picks": [{"element": i, "position": i} for i in range(1, 16)],
        "active_chip": None,
    })

    await t_reconcile_transfers(marking, mock_fpl_client, max_retries=1)
    assert marking.P_TransfersExecuted.empty()
    assert not marking.P_DeadLetter.empty()
    alert = await marking.P_DeadLetter.get()
    assert "Transfer Reconciliation Failed" in alert.reason


@pytest.mark.asyncio
async def test_t_dispatch_lineup_and_reconcile_lineup_success(marking, mock_fpl_client):
    plan = Color_OptimizedPlan(
        plan_id="p_lineup", starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], bench=[12, 13, 14, 15],
        captain=10, vice_captain=11, transfers=[], chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_TransfersExecuted.put(plan)

    # Dispatch lineup
    await t_dispatch_lineup(marking, mock_fpl_client)
    assert not marking.P_LineupAwaitingValidation.empty()

    # Reconcile lineup Gate 2
    server_picks = []
    for i in range(1, 12):
        server_picks.append({"element": i, "position": i, "is_captain": (i == 10), "is_vice_captain": (i == 11)})
    for i in range(12, 16):
        server_picks.append({"element": i, "position": i, "is_captain": False, "is_vice_captain": False})

    mock_fpl_client.get_my_team = AsyncMock(return_value={"picks": server_picks})

    await t_reconcile_lineup(marking, mock_fpl_client, max_retries=2)
    assert not marking.P_Committed.empty()
    receipt = await marking.P_Committed.get()
    assert receipt.http_status == 200
    assert receipt.confirmation_id.startswith("VERIFIED_")
    assert len(receipt.payload_hash) == 64


@pytest.mark.asyncio
async def test_t_reconcile_lineup_mismatch_fails_to_deadletter(marking, mock_fpl_client):
    plan = Color_OptimizedPlan(
        plan_id="p_lineup_bad", starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], bench=[12, 13, 14, 15],
        captain=10, vice_captain=11, transfers=[], chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_LineupAwaitingValidation.put(plan)

    # Server returned captain as 1 instead of 10
    server_picks = []
    for i in range(1, 12):
        server_picks.append({"element": i, "position": i, "is_captain": (i == 1), "is_vice_captain": (i == 11)})
    for i in range(12, 16):
        server_picks.append({"element": i, "position": i, "is_captain": False, "is_vice_captain": False})

    mock_fpl_client.get_my_team = AsyncMock(return_value={"picks": server_picks})

    await t_reconcile_lineup(marking, mock_fpl_client, max_retries=1)
    assert marking.P_Committed.empty()
    assert not marking.P_DeadLetter.empty()
    alert = await marking.P_DeadLetter.get()
    assert "Lineup Reconciliation Failed" in alert.reason


@pytest.mark.asyncio
async def test_t_abort_and_alert(marking):
    now = datetime.now(timezone.utc)
    alert = Color_Alert(severity="CRITICAL", reason="Emergency net stop", context={}, timestamp=now)
    await marking.P_DeadLetter.put(alert)

    mock_notifier = MagicMock()
    mock_notifier.send_alert = AsyncMock()

    await t_abort_and_alert(marking, notifier=mock_notifier)
    mock_notifier.send_alert.assert_awaited_once()
    # Alert token remains in DeadLetter queue for audit ledger
    assert not marking.P_DeadLetter.empty()


@pytest.mark.asyncio
async def test_t_session_keepalive(marking, mock_fpl_client):
    now = datetime.now(timezone.utc)
    session = Color_Session(
        auth_cookie="cookie", csrf_token="csrf", expires_at=now + timedelta(hours=2),
        is_authenticated=True, last_keepalive_utc=now
    )
    await marking.P_Session.publish(session)

    # Run keepalive with very short interval
    task = asyncio.create_task(t_session_keepalive(marking, mock_fpl_client, interval_sec=0.01))
    await asyncio.sleep(0.03)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert marking.P_Session.version > 1


@pytest.mark.asyncio
async def test_t_session_keepalive_error(marking, mock_fpl_client):
    now = datetime.now(timezone.utc)
    session = Color_Session(
        auth_cookie="cookie", csrf_token="csrf", expires_at=now + timedelta(hours=2),
        is_authenticated=True, last_keepalive_utc=now
    )
    await marking.P_Session.publish(session)

    mock_fpl_client.check_session_alive = AsyncMock(side_effect=RuntimeError("Keepalive timeout"))
    task = asyncio.create_task(t_session_keepalive(marking, mock_fpl_client, interval_sec=0.01))
    await asyncio.sleep(0.03)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_t_simulate_and_solve_failure(marking):
    now = datetime.now(timezone.utc)
    await marking.P_Session.publish(Color_Session("c", "t", now, True, now))
    await marking.P_Market.publish(Color_MarketData(pd.DataFrame({"id": [1]}), [], {}, {}))
    await marking.P_Squad.publish(Color_SquadState(1, [1], 1.0, 1, {}, None, {}, [], 1.0, {}))

    mock_solver = MagicMock()
    mock_solver.solve_optimal_gameweek = AsyncMock(side_effect=RuntimeError("MILP infeasible"))

    await t_simulate_and_solve(marking, mock_solver)
    assert marking.P_Plan.empty()
    assert not marking.P_DeadLetter.empty()
    alert = await marking.P_DeadLetter.get()
    assert "MILP infeasible" in alert.reason


@pytest.mark.asyncio
async def test_empty_places_noop(marking, mock_fpl_client):
    """Assert calling transitions when input queues are empty gracefully returns without exception."""
    assert marking.P_Timer.empty()
    await t_preflight_and_ingest(marking, mock_fpl_client)

    assert marking.P_Plan.empty()
    await t_evaluate_guards(marking, {(3, 5, 2)})

    assert marking.P_DeadLetter.empty()
    await t_abort_and_alert(marking)

    assert marking.P_PlanDegrade.empty()
    await t_degrade_plan(marking)

    assert marking.P_Contingency.empty()
    await t_early_leak_resolve(marking, mock_fpl_client)

    assert marking.P_PendingPlan.empty()
    await t_gather_and_reevaluate(marking)

    assert marking.P_Plan.empty()
    await t_dispatch_transfers(marking, mock_fpl_client, datetime.now(timezone.utc))

    assert marking.P_TransfersAwaitingValidation.empty()
    await t_reconcile_transfers(marking, mock_fpl_client)

    assert marking.P_TransfersExecuted.empty()
    await t_dispatch_lineup(marking, mock_fpl_client)

    assert marking.P_LineupAwaitingValidation.empty()
    await t_reconcile_lineup(marking, mock_fpl_client)


@pytest.mark.asyncio
async def test_t_dispatch_lineup_http_error(marking, mock_fpl_client):
    plan = Color_OptimizedPlan(
        plan_id="p_err", starters=list(range(1, 12)), bench=list(range(12, 16)),
        captain=10, vice_captain=11, transfers=[], chip=None, expected_utility=60.0, formation_tuple=(3, 5, 2)
    )
    await marking.P_TransfersExecuted.put(plan)

    mock_fpl_client.post_lineup = AsyncMock(return_value={"status_code": 400, "text": "Invalid team"})
    await t_dispatch_lineup(marking, mock_fpl_client)

    assert marking.P_LineupAwaitingValidation.empty()
    assert not marking.P_DeadLetter.empty()
    alert = await marking.P_DeadLetter.get()
    assert alert.severity == "CRITICAL"
