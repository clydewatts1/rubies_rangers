"""
tests/test_fpl_transfer_service.py
Unit tests for FPL transfer resolution, payload building, and dispatch service.
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from clients.fpl_transfer_service import (
    resolve_player_element,
    build_transfer_payload,
    submit_transfers,
    execute_two_stage_transfer,
)
from clients.auth_manager import AuthSessionInfo
from datetime import datetime, timezone, timedelta


@pytest.fixture
def sample_players_df():
    return pd.DataFrame([
        {"id": 101, "web_name": "Saka", "full_name": "Bukayo Saka", "now_cost": 10.0, "team": 1},
        {"id": 102, "web_name": "Salah", "full_name": "Mohamed Salah", "now_cost": 12.5, "team": 11},
        {"id": 103, "web_name": "Watkins", "full_name": "Ollie Watkins", "now_cost": 9.0, "team": 2},
        {"id": 104, "web_name": "Haaland", "full_name": "Erling Haaland", "now_cost": 15.2, "team": 12},
    ])


def test_resolve_player_element(sample_players_df):
    # Exact web_name
    p1 = resolve_player_element("Salah", sample_players_df)
    assert p1 is not None
    assert p1["id"] == 102

    # Case-insensitive
    p2 = resolve_player_element("saka", sample_players_df)
    assert p2 is not None
    assert p2["id"] == 101

    # Full name
    p3 = resolve_player_element("Erling Haaland", sample_players_df)
    assert p3 is not None
    assert p3["id"] == 104

    # Non-existent
    assert resolve_player_element("NonExistentPlayer", sample_players_df) is None


def test_build_transfer_payload_single(sample_players_df):
    payload, errors = build_transfer_payload(
        transfers_out=["Saka"],
        transfers_in=["Salah"],
        df=sample_players_df,
        entry_id=6173410,
        gameweek=5
    )
    assert len(errors) == 0
    assert payload["entry"] == 6173410
    assert payload["event"] == 5
    assert len(payload["transfers"]) == 1

    t = payload["transfers"][0]
    assert t["element_out"] == 101
    assert t["element_in"] == 102
    assert t["selling_price"] == 100  # 10.0 * 10
    assert t["purchase_price"] == 125  # 12.5 * 10


def test_build_transfer_payload_multi(sample_players_df):
    payload, errors = build_transfer_payload(
        transfers_out=["Saka", "Watkins"],
        transfers_in=["Salah", "Haaland"],
        df=sample_players_df,
        entry_id=99999,
        gameweek=6
    )
    assert len(errors) == 0
    assert len(payload["transfers"]) == 2
    assert payload["transfers"][1]["element_out"] == 103
    assert payload["transfers"][1]["element_in"] == 104
    assert payload["transfers"][1]["purchase_price"] == 152  # 15.2 * 10


def test_build_transfer_payload_missing_player(sample_players_df):
    payload, errors = build_transfer_payload(
        transfers_out=["Saka"],
        transfers_in=["GhostPlayer"],
        df=sample_players_df,
        entry_id=6173410,
        gameweek=5
    )
    assert len(errors) == 1
    assert "GhostPlayer" in errors[0]
    assert len(payload["transfers"]) == 0


def test_submit_transfers_dry_run():
    payload = {
        "chips": None,
        "entry": 6173410,
        "event": 5,
        "transfers": [{"element_in": 102, "element_out": 101, "purchase_price": 125, "selling_price": 100}]
    }
    res = submit_transfers(payload, dry_run=True)
    assert res["success"] is True
    assert res["dry_run"] is True
    assert res["status_code"] == 200
    assert "DRY RUN" in res["message"]


@patch("requests.post")
def test_submit_transfers_live_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "ok"}'
    mock_resp.json.return_value = {"status": "ok"}
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_post.return_value = mock_resp

    payload = {
        "chips": None,
        "entry": 6173410,
        "event": 5,
        "transfers": [{"element_in": 102, "element_out": 101, "purchase_price": 125, "selling_price": 100}]
    }
    res = submit_transfers(payload, cookie_header="pl_profile=dummy", auth_token="eyJdummy", dry_run=False)
    assert res["success"] is True
    assert res["dry_run"] is False
    assert res["status_code"] == 200
    assert mock_post.called


@patch("requests.post")
def test_submit_transfers_live_failure(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Transfer window is closed"
    mock_resp.headers = {"Content-Type": "text/plain"}
    mock_post.return_value = mock_resp

    payload = {
        "chips": None,
        "entry": 6173410,
        "event": 5,
        "transfers": [{"element_in": 102, "element_out": 101, "purchase_price": 125, "selling_price": 100}]
    }
    res = submit_transfers(payload, cookie_header="pl_profile=dummy", auth_token="eyJdummy", dry_run=False)
    assert res["success"] is False
    assert res["status_code"] == 400
    assert "rejected transfer" in res["message"]


@patch("clients.fpl_transfer_service.AuthManager")
def test_execute_two_stage_transfer_dry_run(mock_auth_cls, sample_players_df):
    mock_auth = MagicMock()
    mock_auth.get_active_session.return_value = AuthSessionInfo(
        auth_token="",
        cookie_header="",
        entry_id=6173410,
        first_name="Clyde",
        last_name="Watts",
        team_name="Rubies Rangers",
        bank=3.5,
        free_transfers=1,
        is_authenticated=False,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        auth_source="UNAUTHENTICATED"
    )
    mock_auth_cls.return_value = mock_auth

    res = execute_two_stage_transfer(
        candidate_out=["Saka"],
        candidate_in=["Salah"],
        df=sample_players_df,
        dry_run=True,
        custom_gameweek=5
    )
    assert res["success"] is True
    assert res["dry_run"] is True
    assert res["status_code"] == 200


@patch("clients.fpl_transfer_service.AuthManager")
def test_execute_two_stage_transfer_unauthenticated_live_blocked(mock_auth_cls, sample_players_df):
    mock_auth = MagicMock()
    mock_auth.get_active_session.return_value = AuthSessionInfo(
        auth_token="",
        cookie_header="",
        entry_id=None,
        first_name="",
        last_name="",
        team_name="",
        bank=0.0,
        free_transfers=1,
        is_authenticated=False,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        auth_source="UNAUTHENTICATED"
    )
    mock_auth_cls.return_value = mock_auth

    res = execute_two_stage_transfer(
        candidate_out=["Saka"],
        candidate_in=["Salah"],
        df=sample_players_df,
        dry_run=False,
        custom_gameweek=5
    )
    assert res["success"] is False
    assert res["status_code"] == 401
    assert "No authenticated FPL session found" in res["message"]
