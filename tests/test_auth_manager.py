"""
tests/test_auth_manager.py
Unit and integration test suite for Automated FPL Authentication & Session Sync Subsystem.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from clients.auth_manager import AuthManager, AuthSessionInfo
from api import app

client = TestClient(app)


def test_auth_session_info_immutability():
    """Verify AuthSessionInfo is an immutable frozen dataclass."""
    now = datetime.now(timezone.utc)
    info = AuthSessionInfo(
        auth_token="sample_token_123",
        cookie_header="pl_profile=sample_token_123",
        entry_id=6173410,
        first_name="Clyde",
        last_name="Watts",
        team_name="Rubies Rangers",
        bank=3.7,
        free_transfers=1,
        is_authenticated=True,
        expires_at=now + timedelta(hours=4),
        auth_source="API_LOGIN"
    )
    assert info.entry_id == 6173410
    assert info.first_name == "Clyde"
    assert info.is_authenticated is True
    assert not info.is_expired()

    # Immutability check
    with pytest.raises(Exception):
        info.entry_id = 9999999  # type: ignore


def test_auth_session_expiry():
    """Verify expiration logic with threshold buffer."""
    now = datetime.now(timezone.utc)
    # Expired 10 seconds ago
    expired_info = AuthSessionInfo(
        auth_token="token",
        cookie_header="pl_profile=token",
        entry_id=6173410,
        first_name="Clyde",
        last_name="Watts",
        team_name="Rubies Rangers",
        bank=3.7,
        free_transfers=1,
        is_authenticated=True,
        expires_at=now - timedelta(seconds=10),
        auth_source="API_LOGIN"
    )
    assert expired_info.is_expired() is True


def test_extract_token_from_string():
    """Test cookie parsing for various browser cookie formats."""
    auth_mgr = AuthManager()
    
    # Standard format
    raw1 = "csrftoken=abc; pl_profile=jwt_token_sample_xyz; sessionid=123"
    assert auth_mgr._extract_token_from_string(raw1) == "jwt_token_sample_xyz"

    # access_token format
    raw2 = "access_token=token_abc_456; other=val"
    assert auth_mgr._extract_token_from_string(raw2) == "token_abc_456"

    # Empty format
    assert auth_mgr._extract_token_from_string("") == ""


@patch("requests.get")
def test_sync_browser_cookie_success(mock_get):
    """Test syncing browser cookies with successful /api/me/ resolution."""
    # Mock /api/me/ response
    mock_me = MagicMock()
    mock_me.status_code = 200
    mock_me.json.return_value = {
        "player": {
            "entry": 6173410,
            "first_name": "Clyde",
            "last_name": "Watts"
        }
    }

    # Mock /api/my-team/ response
    mock_team = MagicMock()
    mock_team.status_code = 200
    mock_team.json.return_value = {
        "transfers": {
            "bank": 37,
            "limit": 2
        }
    }

    mock_get.side_effect = [mock_me, mock_team]

    auth_mgr = AuthManager()
    cookie_str = "pl_profile=mock_live_jwt_cookie_string; Path=/"
    session = auth_mgr.sync_browser_cookie(cookie_str, source="TEST_SYNC")

    assert session.is_authenticated is True
    assert session.entry_id == 6173410
    assert session.first_name == "Clyde"
    assert session.bank == 3.7
    assert session.free_transfers == 2
    assert session.auth_source == "TEST_SYNC"


@patch("requests.Session.post")
@patch("requests.get")
def test_authenticate_with_credentials_success(mock_get, mock_post):
    """Test headless credential login against FPL identity endpoint."""
    # Mock Premier League Identity API
    mock_login_resp = MagicMock()
    mock_login_resp.status_code = 200
    mock_login_resp.json.return_value = {"access_token": "mock_jwt_access_token_123"}
    mock_login_resp.headers = {"Set-Cookie": "pl_profile=mock_jwt_access_token_123; Path=/"}
    mock_post.return_value = mock_login_resp

    # Mock /api/me/ and /api/my-team/
    mock_me = MagicMock()
    mock_me.status_code = 200
    mock_me.json.return_value = {
        "player": {"entry": 6173410, "first_name": "Clyde", "last_name": "Watts"}
    }
    mock_team = MagicMock()
    mock_team.status_code = 200
    mock_team.json.return_value = {"transfers": {"bank": 15, "limit": 1}}
    mock_get.side_effect = [mock_me, mock_team]

    auth_mgr = AuthManager()
    session = auth_mgr.authenticate_with_credentials("test@example.com", "password123")

    assert session.is_authenticated is True
    assert session.entry_id == 6173410
    assert session.first_name == "Clyde"
    assert session.bank == 1.5
    assert session.free_transfers == 1
    assert session.auth_source == "API_LOGIN"


@patch("requests.Session.post")
def test_authenticate_with_credentials_invalid_401(mock_post):
    """Test 401 invalid credentials error handling."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_post.return_value = mock_resp

    auth_mgr = AuthManager()
    session = auth_mgr.authenticate_with_credentials("test@example.com", "wrong_password")

    assert session.is_authenticated is False
    assert "Invalid FPL email or password" in str(session.error_message)


# -----------------------------------------------------------------------------
# FastAPI Authentication Endpoint Tests
# -----------------------------------------------------------------------------

def test_api_auth_status_endpoint():
    """Verify /api/auth/status returns 200 and schema fields."""
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert "entry_id" in data
    assert "is_authenticated" in data
    assert "bank" in data
    assert "free_transfers" in data


@patch.object(AuthManager, "sync_browser_cookie")
def test_api_auth_sync_browser_endpoint(mock_sync):
    """Verify /api/auth/sync_browser ingests payload correctly."""
    now = datetime.now(timezone.utc)
    mock_sync.return_value = AuthSessionInfo(
        auth_token="token_from_browser",
        cookie_header="pl_profile=token_from_browser",
        entry_id=6173410,
        first_name="Clyde",
        last_name="Watts",
        team_name="Rubies Rangers",
        bank=3.7,
        free_transfers=1,
        is_authenticated=True,
        expires_at=now + timedelta(hours=4),
        auth_source="BROWSER_SYNC"
    )

    response = client.post("/api/auth/sync_browser", json={"cookie": "pl_profile=token_from_browser"})
    assert response.status_code == 200
    data = response.json()
    assert data["is_authenticated"] is True
    assert data["entry_id"] == 6173410
    assert data["auth_source"] == "BROWSER_SYNC"


@patch.object(AuthManager, "refresh_session")
def test_api_auth_refresh_endpoint(mock_refresh):
    """Verify /api/auth/refresh triggers session re-verification."""
    now = datetime.now(timezone.utc)
    mock_refresh.return_value = AuthSessionInfo(
        auth_token="refreshed_token",
        cookie_header="pl_profile=refreshed_token",
        entry_id=6173410,
        first_name="Clyde",
        last_name="Watts",
        team_name="Rubies Rangers",
        bank=3.7,
        free_transfers=1,
        is_authenticated=True,
        expires_at=now + timedelta(hours=4),
        auth_source="CACHE"
    )

    response = client.post("/api/auth/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["is_authenticated"] is True
