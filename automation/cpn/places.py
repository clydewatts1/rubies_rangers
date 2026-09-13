"""
automation/cpn/places.py
Typed asyncio.Queue places and Marking Registry for the CPN.
Provides non-destructive state inspection for the Streamlit UI.
"""
from __future__ import annotations
import asyncio
from typing import Generic, TypeVar, Any
from automation.cpn.tokens import (
    Color_Deadline, Color_Session, Color_MarketData, Color_SquadState,
    Color_OptimizedPlan, Color_GuardToken, Color_Receipt, Color_Alert
)

T = TypeVar("T")


class CPNPlace(Generic[T]):
    """Strongly typed FIFO place buffer encapsulating asyncio.Queue."""
    def __init__(self, name: str, maxsize: int = 100) -> None:
        self.name = name
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=maxsize)
        self._history: list[T] = []

    async def put(self, token: T) -> None:
        await self._queue.put(token)
        self._history.append(token)

    async def get(self) -> T:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()

    def empty(self) -> bool:
        return self._queue.empty()

    def snapshot(self) -> list[T]:
        """Read-only view of tokens currently in the queue without dequeuing (for UI)."""
        return list(self._queue._queue)  # type: ignore[attr-defined]

    def peek(self) -> T | None:
        """Returns head token without removing it, or None if empty."""
        tokens = self.snapshot()
        return tokens[0] if tokens else None


class CPNStatePlace(Generic[T]):
    """
    Non-destructive state buffer modeling formal Jensen CPN read-arcs (test arcs).
    Allows concurrent, non-destructive reads without altering token presence.
    Updates are serialized via an asyncio.Lock and notify waiting observers.
    """
    def __init__(self, name: str, initial_value: T | None = None) -> None:
        self.name = name
        self._value: T | None = initial_value
        self._lock = asyncio.Lock()
        self._updated_event = asyncio.Event()
        self._version: int = 0 if initial_value is None else 1

    async def read(self, timeout: float | None = 5.0) -> T:
        """Non-destructive read. If uninitialized, waits until first publication."""
        while self._value is None:
            event = self._updated_event
            if timeout is not None:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            else:
                await event.wait()
        return self._value

    def peek(self) -> T | None:
        """Synchronous non-blocking inspection for UI telemetry."""
        return self._value

    async def publish(self, new_value: T) -> None:
        """Thread-safe update of shared state token notifying all waiting readers."""
        async with self._lock:
            self._value = new_value
            self._version += 1
            # Signal existing waiters and create fresh event for subsequent waits
            event = self._updated_event
            event.set()
            self._updated_event = asyncio.Event()

    @property
    def version(self) -> int:
        return self._version


class CPNMarkingRegistry:
    """Central container storing all 14 Petri Net places with proper read-arc separation."""
    def __init__(self) -> None:
        # Continuous Shared State Places (Non-destructive Read-Arcs)
        self.P_Session: CPNStatePlace[Color_Session] = CPNStatePlace("P_Session")
        self.P_Market: CPNStatePlace[Color_MarketData] = CPNStatePlace("P_Market")
        self.P_Squad: CPNStatePlace[Color_SquadState] = CPNStatePlace("P_Squad")

        # Discrete Transactional Queues (Consumptive Arcs)
        self.P_Timer: CPNPlace[Color_Deadline] = CPNPlace("P_Timer")
        self.P_Plan: CPNPlace[Color_OptimizedPlan] = CPNPlace("P_Plan")
        self.P_PendingPlan: CPNPlace[Color_OptimizedPlan] = CPNPlace("P_PendingPlan")
        self.P_Contingency: CPNPlace[Color_GuardToken] = CPNPlace("P_Contingency")
        self.P_ResolvedGuard: CPNPlace[Color_GuardToken] = CPNPlace("P_ResolvedGuard")
        self.P_PlanDegrade: CPNPlace[Color_OptimizedPlan] = CPNPlace("P_PlanDegrade")
        self.P_TransfersAwaitingValidation: CPNPlace[Color_OptimizedPlan] = CPNPlace("P_TransfersAwaitingValidation")
        self.P_TransfersExecuted: CPNPlace[Color_OptimizedPlan] = CPNPlace("P_TransfersExecuted")
        self.P_LineupAwaitingValidation: CPNPlace[Color_OptimizedPlan] = CPNPlace("P_LineupAwaitingValidation")
        self.P_Committed: CPNPlace[Color_Receipt] = CPNPlace("P_Committed")
        self.P_DeadLetter: CPNPlace[Color_Alert] = CPNPlace("P_DeadLetter")

    def get_summary(self) -> dict[str, int]:
        """Returns marking multiset counts M(p) for telemetry."""
        summary = {
            "P_Session": 1 if self.P_Session.peek() is not None else 0,
            "P_Market": 1 if self.P_Market.peek() is not None else 0,
            "P_Squad": 1 if self.P_Squad.peek() is not None else 0,
        }
        for q_name in [
            "P_Timer", "P_Plan", "P_PendingPlan", "P_Contingency",
            "P_ResolvedGuard", "P_PlanDegrade", "P_TransfersAwaitingValidation",
            "P_TransfersExecuted", "P_LineupAwaitingValidation",
            "P_Committed", "P_DeadLetter"
        ]:
            summary[q_name] = getattr(self, q_name).qsize()
        return summary

    def get_marking_snapshot(self) -> dict[str, Any]:
        """Returns snapshot of all active tokens across all places for UI state inspector."""
        snapshot: dict[str, Any] = {
            "P_Session": [self.P_Session.peek()] if self.P_Session.peek() is not None else [],
            "P_Market": [self.P_Market.peek()] if self.P_Market.peek() is not None else [],
            "P_Squad": [self.P_Squad.peek()] if self.P_Squad.peek() is not None else [],
        }
        for q_name in [
            "P_Timer", "P_Plan", "P_PendingPlan", "P_Contingency",
            "P_ResolvedGuard", "P_PlanDegrade", "P_TransfersAwaitingValidation",
            "P_TransfersExecuted", "P_LineupAwaitingValidation",
            "P_Committed", "P_DeadLetter"
        ]:
            snapshot[q_name] = getattr(self, q_name).snapshot()
        return snapshot
