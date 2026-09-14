"""
clients/fpl_challenge_client.py
Dedicated HTTP Client for the Official FPL Challenge API (https://fplchallenge.premierleague.com/api).
Features robust local disk caching, configurable TTL, and resilient offline fallbacks with rich challenge presets.
"""

from __future__ import annotations

import os
import json
import time
import urllib.request
import logging
from typing import Dict, List, Any, Optional

from config_manager import get_system_config

logger = logging.getLogger(__name__)

CHALLENGE_BASE_URL = "https://fplchallenge.premierleague.com/api"
CHALLENGE_BOOTSTRAP_URL = f"{CHALLENGE_BASE_URL}/bootstrap-static/"
CHALLENGE_FIXTURES_URL = f"{CHALLENGE_BASE_URL}/fixtures/?future=1"

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CACHE_FILE = os.path.join(_PROJECT_ROOT, ".fpl_challenge_cache.json")
FIXTURES_CACHE_FILE = os.path.join(_PROJECT_ROOT, ".fpl_challenge_fixtures_cache.json")
DEFAULT_CACHE_TTL = 3600  # 1 hour


class FPLChallengeClient:
    """Client for retrieving and caching official FPL Challenge gameweek rules and data."""

    def __init__(self, cache_ttl: Optional[int] = None) -> None:
        self.cache_ttl = cache_ttl if cache_ttl is not None else (
            get_system_config("cache_ttl_seconds") or DEFAULT_CACHE_TTL
        )

    def _fetch_url(self, url: str, max_retries: Optional[int] = None) -> Any:
        if max_retries is None:
            max_retries = get_system_config("max_retries") or 3
        timeout = get_system_config("http_timeout_seconds") or 10
        backoff_base = get_system_config("retry_backoff_base") or 0.5
        last_err: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RubiesRangersChallenge/1.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(backoff_base * (2 ** attempt))
        if last_err is not None:
            raise last_err
        raise RuntimeError(f"Failed to fetch {url}")

    def get_challenge_bootstrap(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch Challenge bootstrap data with local caching and offline fallback."""
        if not force_refresh and os.path.exists(CACHE_FILE):
            file_age = time.time() - os.path.getmtime(CACHE_FILE)
            if file_age < self.cache_ttl:
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading challenge cache: {e}")

        try:
            data = self._fetch_url(CHALLENGE_BOOTSTRAP_URL)
            try:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception as e:
                logger.warning(f"Failed to write challenge cache: {e}")
            return data
        except Exception as e:
            logger.warning(f"Official FPL Challenge API unavailable ({e}). Using offline cached fallback or defaults.")
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
            return self._build_synthetic_challenge_bootstrap()

    def get_fixtures(self, gameweek: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch fixtures from challenge API or classic cache."""
        try:
            url = f"{CHALLENGE_BASE_URL}/fixtures/?event={gameweek}" if gameweek else CHALLENGE_FIXTURES_URL
            return self._fetch_url(url)
        except Exception as e:
            logger.info(f"Challenge fixtures endpoint fallback: {e}")
            # Fallback to standard fixtures cache if available
            std_fixtures_path = os.path.join(_PROJECT_ROOT, ".fpl_fixtures_cache.json")
            if os.path.exists(std_fixtures_path):
                try:
                    with open(std_fixtures_path, "r", encoding="utf-8") as f:
                        fixtures = json.load(f)
                        if gameweek:
                            return [f for f in fixtures if f.get("event") == gameweek]
                        return fixtures
                except Exception:
                    pass
            return []

    def _build_synthetic_challenge_bootstrap(self) -> Dict[str, Any]:
        """Generate high-fidelity synthetic challenge structure when live endpoints are offline."""
        return {
            "events": [
                {
                    "id": 5,
                    "name": "Gameweek 5 Challenge",
                    "deadline_time": "2026-09-19T10:00:00Z",
                    "is_current": True,
                    "overrides": {
                        "rules": {
                            "squad_squadplay": 6,
                            "squad_squadsize": 6,
                            "squad_total_spend": 9999,
                            "squad_team_limit": 1
                        },
                        "scoring": {
                            "outside_box_goals": 2.0,
                            "clean_sheets": {"MID": 2.0}
                        },
                        "element_types": [
                            {"id": 1, "singular_name_short": "GKP", "squad_min_select": 0, "squad_max_select": 0},
                            {"id": 2, "singular_name_short": "DEF", "squad_min_select": 1, "squad_max_select": 3},
                            {"id": 3, "singular_name_short": "MID", "squad_min_select": 1, "squad_max_select": 3},
                            {"id": 4, "singular_name_short": "FWD", "squad_min_select": 1, "squad_max_select": 3}
                        ]
                    }
                }
            ],
            "game_settings": {
                "squad_squadsize": 6,
                "squad_team_limit": 1,
                "total_transfers": 999
            }
        }
