"""
---
type: Module
title: "The Odds API Client & Vig-Removed Market Consensus Engine"
description: "Ingests live bookmaker match odds, removes market vig, and derives fair Poisson goal arrival rates and clean sheet odds."
tags: [client, odds, market, vig, poisson, analytics]
sources: ["docs/design/des_020_the_odds_api_market_consensus.md"]
generated:
  at: "2026-09-17T20:18:00Z"
  by: "agent:task-runner"
---
"""

from __future__ import annotations
import os
import re
import json
import time
import math
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List, Tuple

import requests
from config_manager import get_system_config

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_ODDS_CACHE_FILE = os.path.join(_PROJECT_ROOT, ".odds_cache.json")
DEFAULT_ODDS_CACHE_TTL_HOURS = 12

# ---------------------------------------------------------------------------
# The Odds API Team Name to Official FPL 3-Letter Code Resolver
# ---------------------------------------------------------------------------
ODDS_API_TO_FPL: Dict[str, str] = {
    "arsenal": "ARS",
    "aston villa": "AVL",
    "bournemouth": "BOU",
    "afc bournemouth": "BOU",
    "brentford": "BRE",
    "brighton and hove albion": "BHA",
    "brighton": "BHA",
    "chelsea": "CHE",
    "crystal palace": "CRY",
    "everton": "EVE",
    "fulham": "FUL",
    "ipswich town": "IPS",
    "ipswich": "IPS",
    "leicester city": "LEI",
    "leicester": "LEI",
    "liverpool": "LIV",
    "manchester city": "MCI",
    "man city": "MCI",
    "manchester united": "MUN",
    "man united": "MUN",
    "newcastle united": "NEW",
    "newcastle": "NEW",
    "nottingham forest": "NFO",
    "southampton": "SOU",
    "tottenham hotspur": "TOT",
    "tottenham": "TOT",
    "west ham united": "WHU",
    "west ham": "WHU",
    "wolverhampton wanderers": "WOL",
    "wolves": "WOL",
    "coventry city": "COV",
    "coventry": "COV",
    "hull city": "HUL",
    "hull": "HUL",
    "sunderland": "SUN",
    "leeds united": "LEE",
    "leeds": "LEE",
    "burnley": "BUR",
    "sheffield united": "SHU",
    "luton town": "LUT",
}


@dataclass(frozen=True)
class MarketOddsRecord:
    """Raw parsed market odds from a single fixture."""
    fixture_id: str
    home_team: str
    away_team: str
    commence_time: str
    bookmaker: str
    h2h_home: float
    h2h_draw: float
    h2h_away: float
    total_over_25: float
    total_under_25: float


@dataclass(frozen=True)
class FairMarketExpectancy:
    """Vig-removed fair probability and derived Poisson goal expectancy."""
    home_team: str
    away_team: str
    prob_home_win: float
    prob_draw: float
    prob_away_win: float
    prob_over_25: float
    prob_under_25: float
    total_exp_goals: float
    exp_goals_home: float
    exp_goals_away: float
    clean_sheet_prob_home: float
    clean_sheet_prob_away: float
    clean_sheet_odds_home: float
    clean_sheet_odds_away: float
    is_market_derived: bool


def normalize_team_name(raw_name: str) -> str:
    """Resolve bookmaker team name to official 3-letter FPL code."""
    cleaned = raw_name.lower().strip()
    cleaned = re.sub(r"\bfc\b", "", cleaned).strip()
    return ODDS_API_TO_FPL.get(cleaned, ODDS_API_TO_FPL.get(raw_name.lower(), "UNK"))


def remove_proportional_vig(odds_list: List[float]) -> List[float]:
    """
    Normalizes a list of decimal odds into fair probabilities by removing bookmaker vig.
    Returns probabilities summing strictly to 1.0.
    """
    implied = [1.0 / o if o > 0 else 0.0 for o in odds_list]
    overround = sum(implied)
    if overround <= 0:
        return [1.0 / len(odds_list)] * len(odds_list)
    return [round(p / overround, 4) for p in implied]


def solve_total_goals(prob_under_25: float) -> float:
    """
    Numerically inverts Poisson cumulative probability P(G <= 2) = exp(-T)(1 + T + T^2/2)
    to solve for total match expected goals T using bounded bisection.
    """
    if prob_under_25 <= 0.02:
        return 4.80
    if prob_under_25 >= 0.95:
        return 1.10

    low, high = 0.5, 6.0
    for _ in range(35):
        mid = (low + high) / 2.0
        val = math.exp(-mid) * (1.0 + mid + 0.5 * mid * mid)
        if val > prob_under_25:
            low = mid
        else:
            high = mid
    return round((low + high) / 2.0, 3)


class OddsClient:
    """
    Lightweight client for The Odds API (free tier: 500 requests/month).
    Features vig-removal, Poisson goal conversion, strict quota guards, and local caching.
    """
    BASE_URL: str = "https://api.the-odds-api.com/v4/sports/soccer_epl/odds"
    PREFERRED_BOOKMAKERS: List[str] = ["pinnacle", "betfair_ex_uk", "bet365", "williamhill", "bovada"]
    MIN_LAMBDA: float = 0.40
    MAX_LAMBDA: float = 3.85
    QUOTA_SAFETY_THRESHOLD: int = 5

    solve_total_goals = staticmethod(solve_total_goals)
    remove_proportional_vig = staticmethod(remove_proportional_vig)
    normalize_team_name = staticmethod(normalize_team_name)

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_file: Optional[str] = None,
        cache_ttl_hours: int = DEFAULT_ODDS_CACHE_TTL_HOURS,
        http_timeout: int = 10,
    ) -> None:
        self.api_key = api_key or os.getenv("ODDS_API_KEY") or get_system_config("odds_api_key")
        self.cache_file = cache_file or DEFAULT_ODDS_CACHE_FILE
        self.cache_ttl_seconds = cache_ttl_hours * 3600
        self.http_timeout = http_timeout
        self.requests_remaining: Optional[int] = None
        self.requests_used: Optional[int] = None
        self._memory_cache: Optional[Dict[str, FairMarketExpectancy]] = None

    def get_quota_info(self) -> Dict[str, Any]:
        """Return quota telemetry."""
        return {
            "has_api_key": bool(self.api_key),
            "requests_remaining": self.requests_remaining,
            "requests_used": self.requests_used,
        }

    def get_market_expectancies(self, force_refresh: bool = False) -> Dict[str, FairMarketExpectancy]:
        """
        Retrieves vig-removed fair market expectations for active Premier League matches.
        Reads from memory or disk cache if fresh; queries The Odds API if quota permits.
        Returns dictionary keyed by home_team 3-letter code.
        """
        if not force_refresh and self._memory_cache is not None:
            return self._memory_cache

        # Check local disk cache
        if not force_refresh and os.path.exists(self.cache_file):
            try:
                file_age = time.time() - os.path.getmtime(self.cache_file)
                if file_age < self.cache_ttl_seconds:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        cached_data = json.load(f)
                    self.requests_remaining = cached_data.get("requests_remaining")
                    self.requests_used = cached_data.get("requests_used")
                    items = {
                        k: FairMarketExpectancy(**v)
                        for k, v in cached_data.get("expectancies", {}).items()
                    }
                    if items:
                        self._memory_cache = items
                        return items
            except Exception as e:
                logger.warning(f"Failed to read odds disk cache: {e}")

        # If no API key configured, return empty
        if not self.api_key:
            return {}

        # If quota is exhausted, halt outbound calls
        if self.requests_remaining is not None and self.requests_remaining < self.QUOTA_SAFETY_THRESHOLD:
            logger.warning(f"The Odds API quota critical ({self.requests_remaining} left). Halting outbound calls.")
            return {}

        # Fetch from network
        expectancies = self._fetch_odds_network()

        # Persist to disk cache
        if expectancies:
            try:
                payload = {
                    "requests_remaining": self.requests_remaining,
                    "requests_used": self.requests_used,
                    "as_of_timestamp": time.time(),
                    "expectancies": {k: asdict(v) for k, v in expectancies.items()},
                }
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to write odds cache: {e}")

        self._memory_cache = expectancies
        return expectancies

    def _fetch_odds_network(self) -> Dict[str, FairMarketExpectancy]:
        """Execute network query to The Odds API."""
        if not self.api_key:
            return {}

        params = {
            "apiKey": self.api_key,
            "regions": "uk,eu",
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
        }
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=self.http_timeout)
            if "x-requests-remaining" in resp.headers:
                self.requests_remaining = int(resp.headers.get("x-requests-remaining", 0))
            if "x-requests-used" in resp.headers:
                self.requests_used = int(resp.headers.get("x-requests-used", 0))

            if resp.status_code != 200:
                logger.warning(f"The Odds API returned status {resp.status_code}: {resp.text}")
                return {}

            raw_fixtures = resp.json()
            return self._parse_fixtures(raw_fixtures)
        except Exception as e:
            logger.warning(f"The Odds API network request failed: {e}")
            return {}

    def _parse_fixtures(self, fixtures_data: List[Dict[str, Any]]) -> Dict[str, FairMarketExpectancy]:
        """Parse raw API JSON into FairMarketExpectancy objects."""
        results: Dict[str, FairMarketExpectancy] = {}

        for fix in fixtures_data:
            home_raw = fix.get("home_team", "")
            away_raw = fix.get("away_team", "")
            h_code = normalize_team_name(home_raw)
            a_code = normalize_team_name(away_raw)

            if h_code == "UNK" or a_code == "UNK":
                continue

            bookmakers = fix.get("bookmakers", [])
            if not bookmakers:
                continue

            # Prioritize sharpest bookmaker available
            selected_bm = None
            for pref in self.PREFERRED_BOOKMAKERS:
                match = next((b for b in bookmakers if b.get("key") == pref), None)
                if match:
                    selected_bm = match
                    break
            if not selected_bm:
                selected_bm = bookmakers[0]

            h2h_market = next((m for m in selected_bm.get("markets", []) if m.get("key") == "h2h"), None)
            totals_market = next((m for m in selected_bm.get("markets", []) if m.get("key") == "totals"), None)

            if not h2h_market:
                continue

            # Parse 1X2 odds
            h2h_outcomes = {o["name"]: o["price"] for o in h2h_market.get("outcomes", [])}
            odds_h = float(h2h_outcomes.get(home_raw, 2.5))
            odds_d = float(h2h_outcomes.get("Draw", 3.2))
            odds_a = float(h2h_outcomes.get(away_raw, 2.8))

            p_h, p_d, p_a = remove_proportional_vig([odds_h, odds_d, odds_a])

            # Parse Totals (Over/Under 2.5)
            p_over, p_under = 0.52, 0.48
            if totals_market:
                for o in totals_market.get("outcomes", []):
                    if o.get("point") == 2.5:
                        if o.get("name") == "Over":
                            odds_over = float(o.get("price", 1.9))
                        elif o.get("name") == "Under":
                            odds_under = float(o.get("price", 1.9))
                if "odds_over" in locals() and "odds_under" in locals():
                    p_over, p_under = remove_proportional_vig([odds_over, odds_under])

            # Solve for total goals T and partition
            total_goals = solve_total_goals(p_under)
            s_h = p_h + 0.5 * p_d
            s_a = p_a + 0.5 * p_d

            exp_h = round(max(self.MIN_LAMBDA, min(self.MAX_LAMBDA, total_goals * s_h)), 2)
            exp_a = round(max(self.MIN_LAMBDA, min(self.MAX_LAMBDA, total_goals * s_a)), 2)

            cs_prob_h = round(math.exp(-exp_a), 3)
            cs_prob_a = round(math.exp(-exp_h), 3)
            cs_odds_h = round(1.0 / cs_prob_h, 2) if cs_prob_h > 0 else 99.0
            cs_odds_a = round(1.0 / cs_prob_a, 2) if cs_prob_a > 0 else 99.0

            results[h_code] = FairMarketExpectancy(
                home_team=h_code,
                away_team=a_code,
                prob_home_win=p_h,
                prob_draw=p_d,
                prob_away_win=p_a,
                prob_over_25=p_over,
                prob_under_25=p_under,
                total_exp_goals=total_goals,
                exp_goals_home=round(exp_h, 2),
                exp_goals_away=round(exp_a, 2),
                clean_sheet_prob_home=cs_prob_h,
                clean_sheet_prob_away=cs_prob_a,
                clean_sheet_odds_home=cs_odds_h,
                clean_sheet_odds_away=cs_odds_a,
                is_market_derived=True,
            )

        return results

    def build_team_odds_map(
        self,
        expectancies: Optional[Dict[str, FairMarketExpectancy]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Convert expectancies into standard team_odds dictionary consumed by XPModel."""
        exp_map = expectancies if expectancies is not None else self.get_market_expectancies()
        odds_map: Dict[str, Dict[str, Any]] = {}

        for h_code, exp in exp_map.items():
            a_code = exp.away_team
            odds_map[h_code] = {
                "team": h_code,
                "opponent": a_code,
                "is_home": True,
                "exp_goals_scored": exp.exp_goals_home,
                "exp_goals_conceded": exp.exp_goals_away,
                "clean_sheet_prob": exp.clean_sheet_prob_home,
                "clean_sheet_odds": exp.clean_sheet_odds_home,
                "fixture_str": f"{a_code} (H)",
                "market_derived": True,
            }
            odds_map[a_code] = {
                "team": a_code,
                "opponent": h_code,
                "is_home": False,
                "exp_goals_scored": exp.exp_goals_away,
                "exp_goals_conceded": exp.exp_goals_home,
                "clean_sheet_prob": exp.clean_sheet_prob_away,
                "clean_sheet_odds": exp.clean_sheet_odds_away,
                "fixture_str": f"{h_code} (A)",
                "market_derived": True,
            }

        return odds_map
