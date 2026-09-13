"""
tests/test_cpn_places.py
Unit tests verifying CPNPlace FIFO queues, CPNStatePlace concurrent read-arcs,
and CPNMarkingRegistry 14-place tracking.
"""
import asyncio
from datetime import datetime, timezone
import pytest
import pandas as pd
from automation.cpn.places import CPNPlace, CPNStatePlace, CPNMarkingRegistry
from automation.cpn.tokens import (
    Color_Deadline,
    Color_Session,
    Color_MarketData,
    Color_SquadState,
    Color_OptimizedPlan,
    Color_Alert,
)


@pytest.mark.asyncio
async def test_cpn_place_fifo_and_snapshot():
    """Verify CPNPlace maintains strict FIFO ordering and non-destructive snapshot."""
    place: CPNPlace[str] = CPNPlace("TestPlace", maxsize=5)
    assert place.empty()
    assert place.qsize() == 0
    assert place.peek() is None

    await place.put("token_1")
    await place.put("token_2")
    await place.put("token_3")

    assert place.qsize() == 3
    assert not place.empty()
    assert place.peek() == "token_1"
    assert place.snapshot() == ["token_1", "token_2", "token_3"]

    # Dequeue FIFO
    assert await place.get() == "token_1"
    place.task_done()
    assert await place.get() == "token_2"
    place.task_done()
    assert await place.get() == "token_3"
    place.task_done()

    assert place.empty()
    assert place.qsize() == 0
    assert place.peek() is None


@pytest.mark.asyncio
async def test_cpn_state_place_concurrent_read_arcs():
    """Verify CPNStatePlace supports multiple concurrent read tasks without token consumption."""
    state_place: CPNStatePlace[str] = CPNStatePlace("TestStatePlace")
    assert state_place.peek() is None
    assert state_place.version == 0

    results: list[str] = []

    async def reader_task(idx: int) -> None:
        val = await state_place.read()
        results.append(f"reader_{idx}:{val}")

    # Launch 5 concurrent readers waiting for publish
    tasks = [asyncio.create_task(reader_task(i)) for i in range(5)]
    await asyncio.sleep(0.01)
    assert len(results) == 0

    # Publish state
    await state_place.publish("session_authenticated_v1")
    await asyncio.gather(*tasks)

    assert len(results) == 5
    assert all("session_authenticated_v1" in r for r in results)
    assert state_place.peek() == "session_authenticated_v1"
    assert state_place.version == 1

    # Subsequent immediate non-destructive reads do not block
    val2 = await state_place.read()
    assert val2 == "session_authenticated_v1"

    # Publishing new version increments version counter and updates peek
    await state_place.publish("session_authenticated_v2")
    assert state_place.version == 2
    assert state_place.peek() == "session_authenticated_v2"
    assert await state_place.read() == "session_authenticated_v2"
    assert await state_place.read(timeout=None) == "session_authenticated_v2"


@pytest.mark.asyncio
async def test_cpn_marking_registry_initial_and_populated():
    """Verify CPNMarkingRegistry tracks all 14 Places with accurate telemetry summaries."""
    registry = CPNMarkingRegistry()

    # Initial marking M0
    summary = registry.get_summary()
    assert len(summary) == 14
    assert all(count == 0 for count in summary.values())

    snapshot = registry.get_marking_snapshot()
    assert len(snapshot) == 14
    assert all(len(tokens) == 0 for tokens in snapshot.values())

    # Populate 1 state place and 2 queue places
    now = datetime.now(timezone.utc)
    session_token = Color_Session(
        auth_cookie="cookie", csrf_token="csrf", expires_at=now,
        is_authenticated=True, last_keepalive_utc=now
    )
    await registry.P_Session.publish(session_token)

    deadline_token = Color_Deadline(gameweek=1, deadline_utc=now, cutoff_disambiguation_utc=now)
    await registry.P_Timer.put(deadline_token)

    alert_token = Color_Alert(severity="CRITICAL", reason="Fatal test halt", context={}, timestamp=now)
    await registry.P_DeadLetter.put(alert_token)

    updated_summary = registry.get_summary()
    assert updated_summary["P_Session"] == 1
    assert updated_summary["P_Timer"] == 1
    assert updated_summary["P_DeadLetter"] == 1
    assert updated_summary["P_Market"] == 0
    assert updated_summary["P_Plan"] == 0

    updated_snapshot = registry.get_marking_snapshot()
    assert len(updated_snapshot["P_Session"]) == 1
    assert updated_snapshot["P_Session"][0].auth_cookie == "cookie"
    assert len(updated_snapshot["P_Timer"]) == 1
    assert len(updated_snapshot["P_DeadLetter"]) == 1
