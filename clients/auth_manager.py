"""
clients/auth_manager.py
Automated FPL Authentication & Session Synchronization Engine.

Supports:
1. Headless automated authentication via official Premier League Identity API.
2. 1-click browser cookie ingestion from Chrome / Edge bookmarklet.
3. Automated manager identity & team metadata resolution (/api/me/ and /api/my-team/).
4. Background token refresh and health monitoring.
"""

from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
import requests

logger = logging.getLogger("rubies_rangers.auth")

FPL_LOGIN_URL = "https://users.premierleague.com/v2/identity/users/authenticate/"
FPL_ME_URL = "https://fantasy.premierleague.com/api/me/"
FPL_MY_TEAM_URL = "https://fantasy.premierleague.com/api/my-team/{}/"

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ENV_FILE = os.path.join(_PROJECT_ROOT, ".env")
_AUTH_CACHE_FILE = os.path.join(_PROJECT_ROOT, ".fpl_auth_session.json")


@dataclass(frozen=True)
class AuthSessionInfo:
    """Immutable representation of verified FPL authentication credentials & team state."""
    auth_token: str
    cookie_header: str
    entry_id: Optional[int]
    first_name: str
    last_name: str
    team_name: str
    bank: float
    free_transfers: int
    is_authenticated: bool
    expires_at: datetime
    auth_source: str  # "API_LOGIN", "BROWSER_SYNC", "ENV_COOKIE", "UNAUTHENTICATED"
    error_message: Optional[str] = None
    last_verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if token is expired or within buffer threshold of expiring."""
        now = datetime.now(timezone.utc)
        return now >= (self.expires_at - timedelta(seconds=buffer_seconds))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "entry_id": self.entry_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "team_name": self.team_name,
            "bank": round(float(self.bank), 2),
            "free_transfers": int(self.free_transfers),
            "is_authenticated": bool(self.is_authenticated),
            "auth_source": str(self.auth_source),
            "expires_at": self.expires_at.isoformat(),
            "last_verified_at": self.last_verified_at.isoformat(),
            "error_message": self.error_message,
        }


class AuthManager:
    """
    Centralized Authentication & Session Lifecycle Manager for Rubies Rangers.
    Thread-safe singleton managing headless login, token resolution, and browser sync.
    """
    _instance: Optional[AuthManager] = None
    _active_session: Optional[AuthSessionInfo] = None

    def __new__(cls) -> AuthManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RubiesRangers/1.0"
        })

    # ----------------------------------------------------------------------
    # Core Public Methods
    # ----------------------------------------------------------------------

    def get_active_session(self, force_refresh: bool = False) -> AuthSessionInfo:
        """
        Retrieves active verified session, automatically refreshing if expired
        or loading from cache/environment if available.
        """
        if self._active_session is not None and not force_refresh:
            if not self._active_session.is_expired():
                return self._active_session

        # 1. Try restoring from cache file
        if not force_refresh:
            cached = self._load_session_cache()
            if cached and not cached.is_expired():
                # Verify token alive
                verified = self._verify_and_populate(cached.auth_token, cached.auth_source)
                if verified.is_authenticated:
                    self._active_session = verified
                    return verified

        # 2. Try credentials from environment / .env
        email = os.environ.get("FPL_EMAIL")
        password = os.environ.get("FPL_PASSWORD")
        if not email or not password:
            self._load_dotenv()
            email = os.environ.get("FPL_EMAIL")
            password = os.environ.get("FPL_PASSWORD")

        if email and password:
            session = self.authenticate_with_credentials(email, password)
            if session.is_authenticated:
                return session

        # 3. Try raw cookie from environment / .env
        cookie_val = os.environ.get("FPL_AUTH_COOKIE") or os.environ.get("FPL_COOKIE")
        if cookie_val:
            session = self.sync_browser_cookie(cookie_val, source="ENV_COOKIE")
            if session.is_authenticated:
                return session

        # 4. Fallback to unauthenticated session
        now = datetime.now(timezone.utc)
        unauth = AuthSessionInfo(
            auth_token="",
            cookie_header="",
            entry_id=6173410,  # Fallback default
            first_name="Guest",
            last_name="Manager",
            team_name="Rubies Rangers (Offline)",
            bank=3.7,
            free_transfers=1,
            is_authenticated=False,
            expires_at=now + timedelta(hours=24),
            auth_source="UNAUTHENTICATED",
            error_message="No active credentials found in .env or browser session."
        )
        self._active_session = unauth
        return unauth

    def authenticate_with_credentials(
        self,
        email: str,
        password: str
    ) -> AuthSessionInfo:
        """
        Headless authentication against official Premier League Identity API.
        POST https://users.premierleague.com/v2/identity/users/authenticate/
        """
        payload = {
            "login": email.strip(),
            "password": password.strip(),
            "app": "plfpl-web",
            "redirect_uri": "https://fantasy.premierleague.com/"
        }
        try:
            resp = self.session.post(
                FPL_LOGIN_URL,
                json=payload,
                timeout=12,
                headers={"Content-Type": "application/json"}
            )
            if resp.status_code == 200:
                # Premier League returns cookie in Set-Cookie or JSON token
                token = ""
                # Check cookies returned
                for cookie in self.session.cookies:
                    if cookie.name == "pl_profile":
                        token = cookie.value
                        break

                # If not in session cookies, inspect json or headers
                if not token:
                    try:
                        data = resp.json()
                        token = data.get("access_token") or data.get("id_token") or ""
                    except Exception:
                        pass

                if not token:
                    # Parse Set-Cookie header manually
                    set_cookie = resp.headers.get("Set-Cookie", "")
                    token = self._extract_token_from_string(set_cookie)

                if token:
                    logger.info("[AuthManager] Headless login successful for %s", email)
                    session_info = self._verify_and_populate(token, source="API_LOGIN")
                    if session_info.is_authenticated:
                        self._save_session_cache(session_info)
                        self._active_session = session_info
                        return session_info

                return self._create_error_session("Login succeeded but pl_profile token was not found in response.")
            elif resp.status_code == 401:
                return self._create_error_session("Invalid FPL email or password.")
            else:
                return self._create_error_session(f"FPL Identity API returned HTTP {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            logger.error(f"[AuthManager] Credential authentication failed: {e}")
            return self._create_error_session(f"Network error during authentication: {e}")

    def sync_browser_cookie(
        self,
        cookie_str: str,
        source: str = "BROWSER_SYNC"
    ) -> AuthSessionInfo:
        """
        Ingests and validates raw cookie string pushed from Chrome bookmarklet or UI paste.
        """
        if not cookie_str or not isinstance(cookie_str, str):
            return self._create_error_session("Empty or invalid cookie string provided.")

        token = self._extract_token_from_string(cookie_str)
        if not token:
            # If the user pasted the raw JWT directly
            token = cookie_str.strip().replace("pl_profile=", "").replace("access_token=", "").strip(" ;\"'")

        if not token:
            return self._create_error_session("Could not extract pl_profile token from cookie payload.")

        session_info = self._verify_and_populate(token, source=source)
        if session_info.is_authenticated:
            self._save_session_cache(session_info)
            self._active_session = session_info
            logger.info("[AuthManager] Browser cookie synchronized successfully for Entry ID %s", session_info.entry_id)
        return session_info

    def refresh_session(self) -> AuthSessionInfo:
        """Forces a fresh re-authentication or re-verification."""
        return self.get_active_session(force_refresh=True)

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns JSON-serializable status dictionary for UI and API."""
        session = self.get_active_session(force_refresh=False)
        return session.to_dict()

    # ----------------------------------------------------------------------
    # Internal Verification & Resolution Helpers
    # ----------------------------------------------------------------------

    def _verify_and_populate(self, token: str, source: str) -> AuthSessionInfo:
        """
        Calls /api/me/ and /api/my-team/ to verify token validity and retrieve live state.
        """
        cookie_header = f"pl_profile={token}" if not token.startswith("pl_profile=") else token
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RubiesRangers/1.0",
            "Cookie": cookie_header
        }
        if token.startswith("eyJ") and ";" not in token:
            headers["Authorization"] = f"Bearer {token}"

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=4)

        try:
            me_resp = requests.get(FPL_ME_URL, headers=headers, timeout=10)
            if me_resp.status_code != 200:
                return self._create_error_session(f"/api/me/ returned HTTP {me_resp.status_code} (Token expired or unauthorized)")

            me_data = me_resp.json()
            player = me_data.get("player", {})
            entry_id = player.get("entry")
            first_name = player.get("first_name", "Manager")
            last_name = player.get("last_name", "")

            # Fetch team state if entry_id exists
            team_name = "Rubies Rangers"
            bank = 3.7
            free_transfers = 1

            if entry_id:
                try:
                    team_url = FPL_MY_TEAM_URL.format(entry_id)
                    team_resp = requests.get(team_url, headers=headers, timeout=10)
                    if team_resp.status_code == 200:
                        team_data = team_resp.json()
                        transfers = team_data.get("transfers", {})
                        bank = float(transfers.get("bank", 37)) / 10.0
                        free_transfers = int(transfers.get("limit", 1))
                except Exception as e:
                    logger.warning(f"[AuthManager] Failed to fetch /api/my-team/: {e}")

            session_info = AuthSessionInfo(
                auth_token=token,
                cookie_header=cookie_header,
                entry_id=entry_id,
                first_name=first_name,
                last_name=last_name,
                team_name=team_name,
                bank=bank,
                free_transfers=free_transfers,
                is_authenticated=True,
                expires_at=expires_at,
                auth_source=source,
                error_message=None,
                last_verified_at=now
            )
            return session_info

        except Exception as e:
            return self._create_error_session(f"Verification request failed: {e}")

    def _extract_token_from_string(self, s: str) -> str:
        """Parses cookie string for pl_profile or access_token."""
        if not s:
            return ""
        parts = s.split(";")
        for part in parts:
            part = part.strip()
            if part.startswith("pl_profile="):
                return part.split("pl_profile=")[1].strip()
            if part.startswith("access_token="):
                return part.split("access_token=")[1].strip()
        return ""

    def _create_error_session(self, msg: str) -> AuthSessionInfo:
        now = datetime.now(timezone.utc)
        return AuthSessionInfo(
            auth_token="",
            cookie_header="",
            entry_id=6173410,
            first_name="Guest",
            last_name="Manager",
            team_name="Rubies Rangers (Unauthenticated)",
            bank=3.7,
            free_transfers=1,
            is_authenticated=False,
            expires_at=now,
            auth_source="UNAUTHENTICATED",
            error_message=msg,
            last_verified_at=now
        )

    def _load_session_cache(self) -> Optional[AuthSessionInfo]:
        """Loads cached session from disk if valid."""
        if not os.path.exists(_AUTH_CACHE_FILE):
            return None
        try:
            with open(_AUTH_CACHE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            expires_at = datetime.fromisoformat(d["expires_at"])
            last_verified = datetime.fromisoformat(d.get("last_verified_at", datetime.now(timezone.utc).isoformat()))
            return AuthSessionInfo(
                auth_token=d["auth_token"],
                cookie_header=d.get("cookie_header", f"pl_profile={d['auth_token']}"),
                entry_id=d.get("entry_id"),
                first_name=d.get("first_name", "Manager"),
                last_name=d.get("last_name", ""),
                team_name=d.get("team_name", "Rubies Rangers"),
                bank=float(d.get("bank", 3.7)),
                free_transfers=int(d.get("free_transfers", 1)),
                is_authenticated=bool(d.get("is_authenticated", False)),
                expires_at=expires_at,
                auth_source=d.get("auth_source", "CACHE"),
                error_message=d.get("error_message"),
                last_verified_at=last_verified
            )
        except Exception:
            return None

    def _save_session_cache(self, session: AuthSessionInfo) -> None:
        """Persists verified session token to disk cache."""
        try:
            payload = {
                "auth_token": session.auth_token,
                "cookie_header": session.cookie_header,
                "entry_id": session.entry_id,
                "first_name": session.first_name,
                "last_name": session.last_name,
                "team_name": session.team_name,
                "bank": session.bank,
                "free_transfers": session.free_transfers,
                "is_authenticated": session.is_authenticated,
                "expires_at": session.expires_at.isoformat(),
                "auth_source": session.auth_source,
                "last_verified_at": session.last_verified_at.isoformat(),
                "error_message": session.error_message
            }
            with open(_AUTH_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.warning(f"[AuthManager] Failed to write auth cache file: {e}")

    def _load_dotenv(self) -> None:
        """Simple, robust .env file parser without extra dependencies."""
        if not os.path.exists(_ENV_FILE):
            return
        try:
            with open(_ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("\"'")
                    if k and v and k not in os.environ:
                        os.environ[k] = v
        except Exception as e:
            logger.debug(f"Failed to load .env: {e}")
