"""
tests/test_cpn_engine.py
Integration tests for CPNEngine and CPNDiagnosticJournal.
Verifies complete gameweek cycle lifecycle, scatter-gather concurrency,
token conservation, and diagnostic journal persistence.
"""
import asyncio
from datetime import datetime, timezone, timedelta
import os
import shutil
from unittest.mock import AsyncMock, MagicMock
import pandas as pd
import pytest

from automation.cpn import (
    CPNEngine,
    CPNDiagnosticJournal,
    K3Status,
    Color_Deadline,
    Color_Session,
    Color_MarketData,
    Color_OptimizedPlan,
    Color_GuardToken,
    t_preflight_and_ingest,
)


@pytest.fixture
def mock_fpl():
    client = MagicMock()
    client.entry_id = 99999
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

    server_picks = []
    for i in range(1, 12):
        server_picks.append({"element": i, "position": i, "selling_price": 50, "is_captain": (i == 10), "is_vice_captain": (i == 11)})
    for i in range(12, 16):
        server_picks.append({"element": i, "position": i, "selling_price": 50, "is_captain": False, "is_vice_captain": False})

    client.get_my_team = AsyncMock(return_value={
        "picks": server_picks,
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


@pytest.fixture
def mock_solver():
    solver = MagicMock()
    solver.solve_optimal_gameweek = AsyncMock(return_value={
        "plan_id": "plan_engine_gw1",
        "starters": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "bench": [12, 13, 14, 15],
        "captain": 10,
        "vice_captain": 11,
        "transfers": [],
        "chip": None,
        "expected_utility": 68.0,
        "formation_tuple": (3, 5, 2),
    })
    return solver


@pytest.mark.asyncio
async def test_cpn_engine_happy_path_cycle(mock_fpl, mock_solver):
    """Verifies complete end-to-end gameweek cycle reaches P_Committed with token conservation."""
    legal = {(3, 5, 2), (4, 4, 2)}
    engine = CPNEngine(fpl_client=mock_fpl, solver_engine=mock_solver, legal_formations=legal)

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(minutes=5)

    await engine.run_gameweek_cycle(gameweek=1, deadline_utc=deadline)

    # Assert receipt deposited in P_Committed
    assert not engine.marking.P_Committed.empty()
    receipt = await engine.marking.P_Committed.get()
    assert receipt.http_status == 200
    assert receipt.confirmation_id.startswith("VERIFIED_")

    # Assert token conservation: intermediate transaction places are completely drained
    summary = engine.marking.get_summary()
    assert summary["P_Plan"] == 0
    assert summary["P_PendingPlan"] == 0
    assert summary["P_Contingency"] == 0
    assert summary["P_TransfersAwaitingValidation"] == 0
    assert summary["P_TransfersExecuted"] == 0
    assert summary["P_LineupAwaitingValidation"] == 0
    assert summary["P_DeadLetter"] == 0

    # Telemetry snapshot check
    telemetry = engine.get_telemetry_snapshot()
    assert telemetry["is_running"] is True
    assert "place_counts" in telemetry

    await engine.shutdown()
    assert engine._running is False


@pytest.mark.asyncio
async def test_cpn_engine_scatter_gather_and_safe_harbor(mock_fpl, mock_solver):
    """Verifies streaming scatter-gather resolves doubt and applies armband safe harbor."""
    legal = {(3, 5, 2), (4, 4, 2)}
    engine = CPNEngine(fpl_client=mock_fpl, solver_engine=mock_solver, legal_formations=legal)

    # Ingest baseline
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(minutes=10)
    await engine.marking.P_Timer.put(Color_Deadline(gameweek=1, deadline_utc=deadline, cutoff_disambiguation_utc=deadline - timedelta(minutes=8)))
    await t_preflight_and_ingest(engine.marking, mock_fpl)

    # Park plan with captain 10 doubtful
    plan = Color_OptimizedPlan(
        plan_id="p_sg_test",
        starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        bench=[12, 13, 14, 15],
        captain=10,
        vice_captain=11,
        transfers=[],
        chip=None,
        expected_utility=60.0,
        formation_tuple=(3, 5, 2),
    )
    await engine.marking.P_PendingPlan.put(plan)
    doubt_token = Color_GuardToken(
        plan_id=plan.plan_id, guard_name="Guard_Fitness", status=K3Status.UNKNOWN,
        subject_id=10, doubt_type="yellow_flag", is_fatal=False, context={"chance": 50}
    )
    await engine.marking.P_Contingency.put(doubt_token)

    # Mock leak indicating captain is ruled out
    mock_fpl.listen_for_leak = AsyncMock(return_value={"starts": False})

    await engine.execute_scatter_gather(deadline)

    assert not engine.marking.P_Plan.empty()
    reconstituted = await engine.marking.P_Plan.get()
    # Captain 10 replaced, captaincy shifted to vice-captain 11
    assert 10 not in reconstituted.starters
    assert reconstituted.captain == 11
    await engine.shutdown()


@pytest.mark.asyncio
async def test_cpn_diagnostic_journal(tmp_path):
    """Verifies CPNDiagnosticJournal asynchronous flush and daily summary generation."""
    log_dir = str(tmp_path / "diagnostics")
    journal = CPNDiagnosticJournal(log_dir=log_dir)

    # Record 12 events to trigger auto-flush (threshold 10)
    for i in range(12):
        await journal.record_event(
            record_type="guard_evaluation",
            metrics={"duration_ms": 1.5, "guard": "Guard_Budget"},
            context={"attempt": i},
            invariants={"budget_ok": True}
        )

    # Explicit flush
    await journal.flush()

    summary = await journal.get_daily_summary()
    assert summary["total_events"] == 12
    assert summary["event_counts"].get("guard_evaluation") == 12
    assert summary["max_memory_rss_mb"] > 0.0


@pytest.mark.asyncio
async def test_cpn_engine_scatter_gather_empty_contingency(mock_fpl, mock_solver):
    engine = CPNEngine(fpl_client=mock_fpl, solver_engine=mock_solver, legal_formations={(3, 5, 2)})
    plan = Color_OptimizedPlan("p_empty_c", list(range(1, 12)), list(range(12, 16)), 10, 11, [], None, 60.0, (3, 5, 2))
    await engine.marking.P_PendingPlan.put(plan)

    # Contingency place is empty -> directly moves plan to P_Plan
    await engine.execute_scatter_gather(datetime.now(timezone.utc) + timedelta(minutes=10))
    assert not engine.marking.P_Plan.empty()
    assert (await engine.marking.P_Plan.get()).plan_id == "p_empty_c"


@pytest.mark.asyncio
async def test_cpn_engine_scatter_gather_timeout_psi_averse(mock_fpl, mock_solver):
    engine = CPNEngine(fpl_client=mock_fpl, solver_engine=mock_solver, legal_formations={(3, 5, 2)})
    plan = Color_OptimizedPlan("p_psi", list(range(1, 12)), list(range(12, 16)), 10, 11, [], None, 60.0, (3, 5, 2))
    await engine.marking.P_PendingPlan.put(plan)
    doubt = Color_GuardToken(plan.plan_id, "Guard_Fitness", K3Status.UNKNOWN, 10, "yellow", False, {})
    await engine.marking.P_Contingency.put(doubt)

    # Ingest market data so _apply_contingency_tree can inspect positions
    market = Color_MarketData(
        elements=pd.DataFrame({
            "id": list(range(1, 16)),
            "team": [1, 2, 3, 4, 5] * 3,
            "position_name": ["GKP", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "GKP", "DEF", "MID", "FWD"]
        }),
        fixtures=[], odds={}, injury_flags={}
    )
    await engine.marking.P_Market.publish(market)

    # listen_for_leak times out
    mock_fpl.listen_for_leak = AsyncMock(side_effect=TimeoutError("Timeout"))

    await engine.execute_scatter_gather(datetime.now(timezone.utc) + timedelta(minutes=10))
    assert not engine.marking.P_Plan.empty()
    resolved = await engine.marking.P_Plan.get()
    assert 10 not in resolved.starters


@pytest.mark.asyncio
async def test_cpn_engine_cycle_with_transfers(mock_fpl):
    # Solver outputs plan with 1 transfer
    solver = MagicMock()
    solver.solve_optimal_gameweek = AsyncMock(return_value={
        "plan_id": "p_with_xfer",
        "starters": [20, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "bench": [12, 13, 14, 15],
        "captain": 10,
        "vice_captain": 11,
        "transfers": [{"element_in": 20, "element_out": 1, "purchase_price": 5.0, "selling_price": 5.0}],
        "chip": None,
        "expected_utility": 72.0,
        "formation_tuple": (3, 5, 2),
    })

    # Server state reflects transfer after dispatch
    server_picks = [
        {"element": 20, "position": 1, "selling_price": 50, "is_captain": False, "is_vice_captain": False}
    ]
    for i in range(2, 12):
        server_picks.append({"element": i, "position": i, "selling_price": 50, "is_captain": (i == 10), "is_vice_captain": (i == 11)})
    for i in range(12, 16):
        server_picks.append({"element": i, "position": i, "selling_price": 50, "is_captain": False, "is_vice_captain": False})

    mock_fpl.get_my_team = AsyncMock(return_value={
        "picks": server_picks,
        "transfers": {"bank": 10, "limit": 0},
        "chips": [],
        "active_chip": None,
        "current_event": 1,
    })

    engine = CPNEngine(fpl_client=mock_fpl, solver_engine=solver, legal_formations={(3, 5, 2)})
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(minutes=5)
    await engine.run_gameweek_cycle(gameweek=1, deadline_utc=deadline)

    assert not engine.marking.P_Committed.empty()
    await engine.shutdown()


@pytest.mark.asyncio
async def test_cpn_engine_cycle_with_degraded_chip(mock_fpl):
    # Solver outputs plan with bboost, but bench player 12 has chance 25 -> degradable
    solver = MagicMock()
    solver.solve_optimal_gameweek = AsyncMock(return_value={
        "plan_id": "p_deg_cycle",
        "starters": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "bench": [12, 13, 14, 15],
        "captain": 10,
        "vice_captain": 11,
        "transfers": [],
        "chip": "bboost",
        "expected_utility": 75.0,
        "formation_tuple": (3, 5, 2),
    })

    # Bench player 12 has injury flag chance 25 (<50 on bboost -> degradable)
    mock_fpl.get_bootstrap_static = AsyncMock(return_value={
        "elements": pd.DataFrame({
            "id": list(range(1, 16)),
            "team": [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5],
            "position_name": ["GKP", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "GKP", "DEF", "MID", "FWD"],
            "moneyball_score": [5.0] * 15,
        }),
        "injury_flags": {12: {"chance_of_playing": 25}}
    })

    server_picks = []
    for i in range(1, 12):
        server_picks.append({"element": i, "position": i, "selling_price": 50, "is_captain": (i == 10), "is_vice_captain": (i == 11)})
    for i in range(12, 16):
        server_picks.append({"element": i, "position": i, "selling_price": 50, "is_captain": False, "is_vice_captain": False})

    mock_fpl.get_my_team = AsyncMock(return_value={
        "picks": server_picks,
        "transfers": {"bank": 10, "limit": 1},
        "chips": [{"name": "bboost", "status_for_entry": "available"}],
        "active_chip": None,
        "current_event": 1,
    })

    engine = CPNEngine(fpl_client=mock_fpl, solver_engine=solver, legal_formations={(3, 5, 2)})
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(minutes=5)
    await engine.run_gameweek_cycle(gameweek=1, deadline_utc=deadline)

    # Cycle degrades plan (strips chip) and successfully commits baseline
    assert not engine.marking.P_Committed.empty()
    await engine.shutdown()
