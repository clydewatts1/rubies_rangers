"""
tests/test_challenge_api.py
Unit and integration tests for FPL Challenge REST API endpoints.
Tests /api/challenge/rules, /api/challenge/solve, /api/challenge/cpn/run, and /api/challenge/cpn/journal.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_api_challenge_rules():
    """Verify /api/challenge/rules returns standard presets."""
    response = client.get("/api/challenge/rules?gameweek=5")
    assert response.status_code == 200
    data = response.json()
    assert data["gameweek"] == 5
    assert "available_presets" in data
    assert "gw5_one_player_per_club" in data["available_presets"]
    assert "standard_6_a_side" in data["available_presets"]


def test_api_challenge_solve_max_ev():
    """Verify /api/challenge/solve produces optimal squad via ChallengePicker."""
    payload = {
        "gameweek": 5,
        "archetype": "max_ev",
        "preset_key": "gw5_one_player_per_club",
        "n_simulations": 500,
        "available_only": True
    }
    response = client.post("/api/challenge/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["archetype"] == "max_ev"
    assert len(data["squad"]) == 6
    assert data["captain"] is not None
    assert data["vice_captain"] is not None
    assert data["expected_ev"] > 0.0


def test_api_challenge_cpn_run_dry_run():
    """Verify /api/challenge/cpn/run executes CPN pipeline with Saga verification."""
    payload = {
        "gameweek": 5,
        "archetype": "max_ev",
        "preset_key": "gw5_one_player_per_club",
        "dry_run": True,
        "max_retries": 2,
        "n_simulations": 500
    }
    response = client.post("/api/challenge/cpn/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "receipt" in data
    assert "plan" in data
    assert "validation" in data
    assert data["receipt"]["attempts_required"] >= 1


def test_api_challenge_cpn_journal():
    """Verify /api/challenge/cpn/journal returns recent telemetry."""
    response = client.get("/api/challenge/cpn/journal?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "entries" in data
    assert isinstance(data["entries"], list)
