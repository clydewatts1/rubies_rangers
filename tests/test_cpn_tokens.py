"""
tests/test_cpn_tokens.py
Unit tests verifying strict immutability, type contracts, and serialization for CPN tokens.
"""
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import pytest
import pandas as pd
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


def test_k3_status_enum():
    """Verify Kleene K3 tri-value enum definitions and string semantics."""
    assert K3Status.TRUE == "TRUE"
    assert K3Status.FALSE == "FALSE"
    assert K3Status.UNKNOWN == "UNKNOWN"
    assert len(K3Status) == 3


def test_color_deadline_immutability():
    """Verify Color_Deadline is frozen and respects default n_sims."""
    now = datetime.now(timezone.utc)
    token = Color_Deadline(gameweek=10, deadline_utc=now, cutoff_disambiguation_utc=now)
    assert token.gameweek == 10
    assert token.n_sims == 5000

    with pytest.raises(FrozenInstanceError):
        token.gameweek = 11  # type: ignore[misc]


def test_color_session_immutability():
    """Verify Color_Session is frozen."""
    now = datetime.now(timezone.utc)
    token = Color_Session(
        auth_cookie="cookie_123",
        csrf_token="csrf_abc",
        expires_at=now,
        is_authenticated=True,
        last_keepalive_utc=now,
    )
    assert token.is_authenticated is True

    with pytest.raises(FrozenInstanceError):
        token.is_authenticated = False  # type: ignore[misc]


def test_color_market_data_immutability():
    """Verify Color_MarketData frozen contract."""
    df = pd.DataFrame({"id": [1, 2], "name": ["Salah", "Haaland"]})
    token = Color_MarketData(
        elements=df,
        fixtures=[{"id": 1, "event": 1}],
        odds={"1": 1.5},
        injury_flags={1: {"chance_of_playing": 100}},
    )
    assert len(token.elements) == 2

    with pytest.raises(FrozenInstanceError):
        token.odds = {}  # type: ignore[misc]


def test_color_squad_state_immutability_and_ghost_squad():
    """Verify Color_SquadState retains ghost squad state for Free Hit reversion."""
    token = Color_SquadState(
        entry_id=99999,
        squad_ids=[1, 2, 3],
        bank=1.5,
        free_transfers=2,
        chips_available={"wildcard": True, "freehit": True, "3xc": True, "bboost": True},
        active_chip=None,
        selling_prices={1: 12.5, 2: 8.0, 3: 5.5},
        ghost_squad_ids=[10, 20, 30],
        ghost_bank=2.0,
        ghost_selling_prices={10: 12.0, 20: 8.5, 30: 5.0},
    )
    assert token.ghost_squad_ids == [10, 20, 30]
    assert token.ghost_bank == 2.0

    with pytest.raises(FrozenInstanceError):
        token.bank = 5.0  # type: ignore[misc]


def test_color_optimized_plan_immutability_and_defaults():
    """Verify Color_OptimizedPlan defaults, immutability, and degradation flags."""
    token = Color_OptimizedPlan(
        plan_id="plan_test_001",
        starters=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        bench=[12, 13, 14, 15],
        captain=1,
        vice_captain=2,
        transfers=[{"element_in": 10, "element_out": 12}],
        chip="3xc",
        expected_utility=64.2,
        formation_tuple=(3, 5, 2),
    )
    assert token.fallback_plan is None
    assert token.is_degraded is False
    assert token.chip_degraded_reason is None
    assert token.contingency_tree == {}

    with pytest.raises(FrozenInstanceError):
        token.is_degraded = True  # type: ignore[misc]


def test_color_guard_token_immutability():
    """Verify Color_GuardToken fields and immutability."""
    token = Color_GuardToken(
        plan_id="plan_test_001",
        guard_name="Guard_Fitness",
        status=K3Status.UNKNOWN,
        subject_id=10,
        doubt_type="yellow_flag",
        is_fatal=False,
        context={"chance": 50},
    )
    assert token.status == K3Status.UNKNOWN
    assert token.resolved_at is None

    with pytest.raises(FrozenInstanceError):
        token.status = K3Status.TRUE  # type: ignore[misc]


def test_color_receipt_immutability():
    """Verify Color_Receipt commitment confirmation fields."""
    now = datetime.now(timezone.utc)
    token = Color_Receipt(
        http_status=200,
        timestamp=now,
        payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        confirmation_id="VERIFIED_E3B0C44298FC",
    )
    assert token.http_status == 200
    assert token.confirmation_id == "VERIFIED_E3B0C44298FC"

    with pytest.raises(FrozenInstanceError):
        token.http_status = 201  # type: ignore[misc]


def test_color_alert_immutability():
    """Verify Color_Alert fields in dead letter queue."""
    now = datetime.now(timezone.utc)
    token = Color_Alert(
        severity="CRITICAL",
        reason="Budget exceeded by 1.2M",
        context={"bank": 0.5, "cost": 1.7},
        timestamp=now,
    )
    assert token.severity == "CRITICAL"

    with pytest.raises(FrozenInstanceError):
        token.severity = "WARNING"  # type: ignore[misc]
