import pytest
from starlette.testclient import TestClient
from api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "endpoints" in data


def test_api_odds(client):
    response = client.get("/api/odds")
    assert response.status_code == 200
    data = response.json()
    assert "gameweek" in data
    assert "fixtures" in data
    assert len(data["fixtures"]) == 20



def test_api_clean_players(client):
    response = client.get("/api/players/clean?min_minutes=90")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 100
    assert "players" in data


def test_api_simulate_lineup(client):
    payload = {
        "sims": 500,
        "form_weight": 0.25,
        "include_disciplinary": True
    }
    response = client.post("/api/simulate/lineup", json=payload)
    assert response.status_code == 200
    data = response.json()
    LEGAL_FORMATIONS = {"3-5-2", "3-4-3", "4-4-2", "4-3-3", "4-5-1", "5-3-2", "5-4-1", "5-2-3"}
    assert data["optimal_formation"] in LEGAL_FORMATIONS
    assert len(data["starters"]) == 11
    assert len(data["bench"]) == 4
    assert "captaincy_duel" in data
    assert "move_around_checklist" in data


def test_api_config(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "active_profile" in data
    assert "system" in data
    assert "parameters" in data
    assert data["active_profile"] in ["heuristic", "tuned"]

    # Test profile switch
    post_res = client.post("/api/config/profile?profile=tuned")
    assert post_res.status_code == 200
    assert post_res.json()["active_profile"] == "tuned"

    # Reset to heuristic
    post_res2 = client.post("/api/config/profile?profile=heuristic")
    assert post_res2.status_code == 200
    assert post_res2.json()["active_profile"] == "heuristic"

