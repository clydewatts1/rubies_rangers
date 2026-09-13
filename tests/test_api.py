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


def test_api_cpn_telemetry(client):
    res = client.get("/api/cpn/telemetry")
    assert res.status_code == 200
    data = res.json()
    assert "places" in data
    assert "transitions" in data
    assert "P_Committed" in data["places"]
    assert "T_DispatchLineup" in data["transitions"]


def test_api_cpn_run_demo(client):
    payload = {
        "gameweek": 1,
        "live": False,
        "dry_run": True,
        "entry_id": 99999,
        "deadline_mins": 5
    }
    res = client.post("/api/cpn/run", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["mode"] == "Synthetic Demo"
    assert "committed_receipt" in data
    assert data["committed_receipt"] is not None
    assert data["place_counts"]["P_Committed"] >= 1


def test_api_cpn_daemon_lifecycle(client):
    # 1. Initial status check
    res = client.get("/api/cpn/daemon/status")
    assert res.status_code == 200
    data = res.json()
    assert "is_running" in data
    assert "indicator" in data

    # 2. Start daemon
    start_payload = {
        "live": False,
        "dry_run": True,
        "check_interval_seconds": 15,
        "preflight_lead_minutes": 35
    }
    start_res = client.post("/api/cpn/daemon/start", json=start_payload)
    assert start_res.status_code == 200
    start_data = start_res.json()
    assert start_data["success"] is True
    assert start_data["status"]["is_running"] is True
    assert "🟢" in start_data["status"]["indicator"]

    # 3. Status during running
    status_res = client.get("/api/cpn/daemon/status")
    assert status_res.status_code == 200
    assert status_res.json()["is_running"] is True
    assert "next_gameweek" in status_res.json()

    # 4. Stop daemon
    stop_res = client.post("/api/cpn/daemon/stop")
    assert stop_res.status_code == 200
    stop_data = stop_res.json()
    assert stop_data["success"] is True
    assert stop_data["status"]["is_running"] is False
    assert "⚪" in stop_data["status"]["indicator"]


