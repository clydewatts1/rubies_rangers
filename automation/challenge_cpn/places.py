"""
automation/challenge_cpn/places.py
Typed FIFO and State places for the Challenge Coloured Petri Net.
Provides non-destructive state inspection for the Streamlit UI and audit diagnostics.
"""

from __future__ import annotations

import asyncio
from typing import Generic, TypeVar, List, Optional, Any

from automation.challenge_cpn.tokens import (
    Color_ChallengeRule,
    Color_ChallengeMarket,
    Color_ChallengeSquadState,
    Color_ChallengePlan,
    Color_ChallengeValidation,
    Color_ChallengeSagaToken,
    Color_ChallengeReceipt,
    Color_ChallengeAlert,
)

T = TypeVar("T")


class ChallengePlace(Generic[T]):
    """Strongly typed FIFO place buffer encapsulating asyncio.Queue."""

    def __init__(self, name: str, maxsize: int = 100) -> None:
        self.name = name
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=maxsize)
        self._history: List[T] = []

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

    def snapshot(self) -> List[T]:
        """Read-only view of tokens currently in the queue without dequeuing."""
        return list(self._queue._queue)  # type: ignore[attr-defined]

    def peek(self) -> Optional[T]:
        tokens = self.snapshot()
        return tokens[0] if tokens else None


class ChallengeStatePlace(Generic[T]):
    """
    Non-destructive state buffer modeling formal Jensen CPN read-arcs (test arcs).
    Allows concurrent reads without dequeuing tokens.
    """

    def __init__(self, name: str, initial_value: Optional[T] = None) -> None:
        self.name = name
        self._value: Optional[T] = initial_value
        self._lock = asyncio.Lock()
        self._updated_event = asyncio.Event()

    async def read(self) -> Optional[T]:
        async with self._lock:
            return self._value

    async def update(self, new_value: T) -> None:
        async with self._lock:
            self._value = new_value
            self._updated_event.set()

    def peek(self) -> Optional[T]:
        return self._value


class ChallengeMarkingRegistry:
    """Central registry of all places in the Challenge Coloured Petri Net."""

    def __init__(self) -> None:
        self.P_IDLE = ChallengePlace[int]("P_CHALLENGE_IDLE")
        self.P_RULES_READY = ChallengeStatePlace[Color_ChallengeRule]("P_CHALLENGE_RULES_READY")
        self.P_MARKET_READY = ChallengeStatePlace[Color_ChallengeMarket]("P_CHALLENGE_MARKET_READY")
        self.P_CURRENT_TEAM = ChallengeStatePlace[Color_ChallengeSquadState]("P_CHALLENGE_CURRENT_TEAM")
        self.P_OPTIMIZED = ChallengePlace[Color_ChallengePlan]("P_CHALLENGE_OPTIMIZED")
        self.P_VALIDATED = ChallengePlace[Color_ChallengeValidation]("P_CHALLENGE_VALIDATED")
        self.P_SUBMITTING = ChallengePlace[Color_ChallengeSagaToken]("P_CHALLENGE_SUBMITTING")
        self.P_VERIFYING = ChallengePlace[Color_ChallengeSagaToken]("P_CHALLENGE_VERIFYING")
        self.P_CONFIRMED = ChallengePlace[Color_ChallengeReceipt]("P_CHALLENGE_CONFIRMED")
        self.P_COMPENSATION = ChallengePlace[Color_ChallengeSagaToken]("P_CHALLENGE_COMPENSATION")
        self.P_ALERTS = ChallengePlace[Color_ChallengeAlert]("P_CHALLENGE_ALERTS")

    def get_marking_summary(self) -> dict[str, Any]:
        """Returns JSON-serializable representation of current net markings for UI & logs."""
        return {
            "P_CHALLENGE_IDLE": self.P_IDLE.qsize(),
            "P_CHALLENGE_RULES_READY": bool(self.P_RULES_READY.peek()),
            "P_CHALLENGE_MARKET_READY": bool(self.P_MARKET_READY.peek()),
            "P_CHALLENGE_CURRENT_TEAM": bool(self.P_CURRENT_TEAM.peek()),
            "P_CHALLENGE_OPTIMIZED": self.P_OPTIMIZED.qsize(),
            "P_CHALLENGE_VALIDATED": self.P_VALIDATED.qsize(),
            "P_CHALLENGE_SUBMITTING": self.P_SUBMITTING.qsize(),
            "P_CHALLENGE_VERIFYING": self.P_VERIFYING.qsize(),
            "P_CHALLENGE_CONFIRMED": self.P_CONFIRMED.qsize(),
            "P_CHALLENGE_COMPENSATION": self.P_COMPENSATION.qsize(),
            "P_CHALLENGE_ALERTS": self.P_ALERTS.qsize(),
        }
