"""
---
type: Module
title: "ClubElo Client & Bivariate Poisson Goal Expectancy Engine"
description: "Fetches and parses daily ClubElo ratings to compute dynamic Poisson expected goals and clean sheet probabilities."
tags: [client, clubelo, ratings, poisson, analytics]
sources: ["docs/design/des_019_clubelo_dynamic_team_ratings.md"]
generated:
  at: "2026-09-17T20:05:00Z"
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
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_CACHE_FILE = os.path.join(_PROJECT_ROOT, ".clubelo_cache.json")
DEFAULT_CACHE_TTL_HOURS = 24

# ---------------------------------------------------------------------------
# ClubElo Name / Code to Official FPL 3-Letter Code Resolver
# ---------------------------------------------------------------------------
CLUBELO_TO_FPL: Dict[str, str] = {
    # Direct Elo 3-letter codes to FPL
    "ARS": "ARS",
    "MCI": "MCI",
    "LIV": "LIV",
    "CHE": "CHE",
    "AVL": "AVL",
    "MNU": "MUN",
    "MUN": "MUN",
    "NEW": "NEW",
    "BRI": "BHA",
    "BHA": "BHA",
    "BOU": "BOU",
    "BRE": "BRE",
    "EVE": "EVE",
    "CRY": "CRY",
    "LEE": "LEE",
    "FOR": "NFO",
    "NFO": "NFO",
    "FUL": "FUL",
    "TOT": "TOT",
    "SUN": "SUN",
    "IPS": "IPS",
    "COV": "COV",
    "HUL": "HUL",
    "WHU": "WHU",
    "WOL": "WOL",
    "SOU": "SOU",
    "LEI": "LEI",
    "BUR": "BUR",
    "SHU": "SHU",
    "LUT": "LUT",
    "WBA": "WBA",
    "NOR": "NOR",
    "WAT": "WAT",
    # Full names normalized
    "arsenal": "ARS",
    "mancity": "MCI",
    "manchestercity": "MCI",
    "man city": "MCI",
    "liverpool": "LIV",
    "chelsea": "CHE",
    "astonvilla": "AVL",
    "aston villa": "AVL",
    "manunited": "MUN",
    "manchesterunited": "MUN",
    "man united": "MUN",
    "newcastle": "NEW",
    "newcastleunited": "NEW",
    "brighton": "BHA",
    "bournemouth": "BOU",
    "brentford": "BRE",
    "everton": "EVE",
    "crystalpalace": "CRY",
    "crystal palace": "CRY",
    "leeds": "LEE",
    "forest": "NFO",
    "nottingham": "NFO",
    "nottinghamforest": "NFO",
    "nott'm forest": "NFO",
    "nottm forest": "NFO",
    "fulham": "FUL",
    "tottenham": "TOT",
    "spurs": "TOT",
    "sunderland": "SUN",
    "ipswich": "IPS",
    "ipswichtown": "IPS",
    "coventry": "COV",
    "coventrycity": "COV",
    "hull": "HUL",
    "hullcity": "HUL",
    "westham": "WHU",
    "west ham": "WHU",
    "wolves": "WOL",
    "wolverhampton": "WOL",
    "southampton": "SOU",
    "leicester": "LEI",
    "leicestercity": "LEI",
    "burnley": "BUR",
    "sheffieldunited": "SHU",
    "luton": "LUT",
}

# Offline baseline Elo ratings for Premier League clubs (fallback if offline & no cache)
BASELINE_EPL_ELO: Dict[str, float] = {
    "ARS": 2045.0,
    "MCI": 2032.0,
    "LIV": 1932.0,
    "CHE": 1889.0,
    "AVL": 1888.0,
    "MUN": 1879.0,
    "NEW": 1877.0,
    "BHA": 1876.0,
    "BOU": 1859.0,
    "BRE": 1850.0,
    "EVE": 1823.0,
    "CRY": 1819.0,
    "LEE": 1817.0,
    "NFO": 1813.0,
    "FUL": 1805.0,
    "TOT": 1803.0,
    "WHU": 1778.0,
    "SUN": 1739.0,
    "WOL": 1722.0,
    "SOU": 1704.0,
    "IPS": 1697.0,
    "COV": 1681.0,
    "HUL": 1635.0,
    "LEI": 1581.0,
}


@dataclass(frozen=True)
class ClubEloRecord:
    """Raw snapshot of a club's rating from ClubElo."""
    club_name: str
    fpl_code: str
    elo: float
    rank: Optional[int]
    as_of_timestamp: float


@dataclass(frozen=True)
class FixtureExpectancy:
    """Calibrated Poisson goal and clean sheet expectancy for a specific fixture."""
    home_team: str
    away_team: str
    home_elo: float
    away_elo: float
    delta_elo_home: float
    exp_goals_home: float
    exp_goals_away: float
    clean_sheet_prob_home: float
    clean_sheet_prob_away: float
    clean_sheet_odds_home: float
    clean_sheet_odds_away: float
    fixture_str_home: str
    fixture_str_away: str


class ClubEloClient:
    """
    Robust HTTP client and Poisson calculation engine for ClubElo ratings.
    Supports primary scraping from clubelo.com/ENG, fallback to api.clubelo.com CSV,
    local 24h disk caching, and graceful offline baseline fallback.
    """
    DEFAULT_HOME_ADVANTAGE: float = 75.0
    DEFAULT_BASE_GOALS: float = 1.36
    DEFAULT_BETA: float = 0.00231
    MIN_LAMBDA: float = 0.40
    MAX_LAMBDA: float = 3.85

    def __init__(
        self,
        cache_file: Optional[str] = None,
        cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
        home_advantage: float = DEFAULT_HOME_ADVANTAGE,
        base_goals: float = DEFAULT_BASE_GOALS,
        beta: float = DEFAULT_BETA,
        http_timeout: int = 10,
    ) -> None:
        self.cache_file = cache_file or DEFAULT_CACHE_FILE
        self.cache_ttl_seconds = cache_ttl_hours * 3600
        self.home_advantage = home_advantage
        self.base_goals = base_goals
        self.beta = beta
        self.http_timeout = http_timeout
        self._memory_cache: Optional[Dict[str, ClubEloRecord]] = None

    def get_epl_ratings(self, force_refresh: bool = False) -> Dict[str, ClubEloRecord]:
        """
        Retrieves current Premier League Elo ratings mapped by 3-letter FPL club code.
        Reads from memory or disk cache if fresh; otherwise queries ClubElo.
        """
        if not force_refresh and self._memory_cache is not None:
            return self._memory_cache

        # Check local disk cache
        if not force_refresh and os.path.exists(self.cache_file):
            try:
                file_age = time.time() - os.path.getmtime(self.cache_file)
                if file_age < self.cache_ttl_seconds:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    records = {
                        k: ClubEloRecord(**v) for k, v in data.items()
                    }
                    self._memory_cache = records
                    return records
            except Exception as e:
                logger.warning(f"Failed to read ClubElo disk cache: {e}")

        # Attempt network fetch
        records = self._fetch_ratings_network()

        # If network failed, try stale cache or fall back to baseline
        if not records:
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    records = {k: ClubEloRecord(**v) for k, v in data.items()}
                    logger.info("Serving stale ClubElo cache after network failure.")
                except Exception:
                    pass

        if not records:
            logger.warning("Using built-in baseline EPL Elo ratings as fallback.")
            now = time.time()
            records = {
                code: ClubEloRecord(
                    club_name=code,
                    fpl_code=code,
                    elo=elo,
                    rank=None,
                    as_of_timestamp=now
                )
                for code, elo in BASELINE_EPL_ELO.items()
            }

        # Persist to disk cache
        if records:
            try:
                serializable = {k: asdict(v) for k, v in records.items()}
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(serializable, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to write ClubElo cache: {e}")

        self._memory_cache = records
        return records

    def _fetch_ratings_network(self) -> Dict[str, ClubEloRecord]:
        """Fetch ratings from web endpoints."""
        records: Dict[str, ClubEloRecord] = {}

        # 1. Primary approach: scrape clubelo.com/ENG
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RubiesRangers/2.0"}
        try:
            url = "https://clubelo.com/ENG"
            resp = requests.get(url, headers=headers, timeout=self.http_timeout)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                tables = soup.find_all("table")
                now = time.time()
                for t in tables:
                    for row in t.find_all("tr"):
                        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                        if len(cells) == 2 and cells[1].isdigit():
                            raw_name, raw_elo = cells[0], cells[1]
                            m = re.match(r"^(\d+)?([A-Z]{3})(.+)$", raw_name)
                            if m:
                                rank = int(m.group(1)) if m.group(1) else None
                                elo_code = m.group(2)
                                club_name = m.group(3).strip()
                                elo_val = float(raw_elo)

                                fpl_code = (
                                    CLUBELO_TO_FPL.get(elo_code)
                                    or CLUBELO_TO_FPL.get(club_name.lower())
                                    or CLUBELO_TO_FPL.get(re.sub(r"[^a-z]", "", club_name.lower()))
                                )
                                if fpl_code and fpl_code not in records:
                                    records[fpl_code] = ClubEloRecord(
                                        club_name=club_name,
                                        fpl_code=fpl_code,
                                        elo=elo_val,
                                        rank=rank,
                                        as_of_timestamp=now
                                    )
                if records:
                    return records
        except Exception as e:
            logger.warning(f"ClubElo web scrape failed: {e}")

        # 2. Secondary approach: api.clubelo.com CSV
        try:
            csv_url = "http://api.clubelo.com/"
            resp = requests.get(csv_url, headers=headers, timeout=self.http_timeout)
            if resp.status_code == 200 and "Rank,Club,Country,Level,Elo" in resp.text:
                now = time.time()
                lines = resp.text.splitlines()
                header = lines[0].split(",")
                for line in lines[1:]:
                    parts = line.split(",")
                    if len(parts) >= 5:
                        country = parts[2].strip()
                        level = parts[3].strip()
                        if country == "ENG" and level == "1":
                            rank_str = parts[0].strip()
                            club = parts[1].strip()
                            elo_str = parts[4].strip()
                            fpl_code = (
                                CLUBELO_TO_FPL.get(club.lower())
                                or CLUBELO_TO_FPL.get(re.sub(r"[^a-z]", "", club.lower()))
                            )
                            if fpl_code:
                                records[fpl_code] = ClubEloRecord(
                                    club_name=club,
                                    fpl_code=fpl_code,
                                    elo=float(elo_str),
                                    rank=int(rank_str) if rank_str.isdigit() else None,
                                    as_of_timestamp=now
                                )
                if records:
                    return records
        except Exception as e:
            logger.warning(f"ClubElo API CSV fetch failed: {e}")

        return records

    def compute_fixture_expectancy(
        self,
        home_team: str,
        away_team: str,
        ratings: Optional[Dict[str, ClubEloRecord]] = None
    ) -> FixtureExpectancy:
        """
        Computes calibrated Poisson lambda goals and clean sheet probabilities
        given two FPL 3-letter team codes.
        """
        ratings_map = ratings or self.get_epl_ratings()
        h_rec = ratings_map.get(home_team)
        a_rec = ratings_map.get(away_team)

        h_elo = h_rec.elo if h_rec else BASELINE_EPL_ELO.get(home_team, 1800.0)
        a_elo = a_rec.elo if a_rec else BASELINE_EPL_ELO.get(away_team, 1800.0)

        # Rating differential with home ground advantage
        delta_elo_h = (h_elo + self.home_advantage) - a_elo

        # Poisson goal arrival rates: lambda = mu_0 * exp(beta * delta)
        exp_goals_h = self.base_goals * math.exp(self.beta * delta_elo_h)
        exp_goals_a = self.base_goals * math.exp(-self.beta * delta_elo_h)

        # Apply physical safety clamping
        exp_goals_h = max(self.MIN_LAMBDA, min(self.MAX_LAMBDA, exp_goals_h))
        exp_goals_a = max(self.MIN_LAMBDA, min(self.MAX_LAMBDA, exp_goals_a))

        # Poisson clean sheet probabilities: P(CS) = exp(-opp_goals)
        cs_prob_h = round(math.exp(-exp_goals_a), 3)
        cs_prob_a = round(math.exp(-exp_goals_h), 3)

        # Fair decimal clean sheet odds
        cs_odds_h = round(1.0 / cs_prob_h, 2) if cs_prob_h > 0 else 99.0
        cs_odds_a = round(1.0 / cs_prob_a, 2) if cs_prob_a > 0 else 99.0

        return FixtureExpectancy(
            home_team=home_team,
            away_team=away_team,
            home_elo=h_elo,
            away_elo=a_elo,
            delta_elo_home=round(delta_elo_h, 1),
            exp_goals_home=round(exp_goals_h, 2),
            exp_goals_away=round(exp_goals_a, 2),
            clean_sheet_prob_home=cs_prob_h,
            clean_sheet_prob_away=cs_prob_a,
            clean_sheet_odds_home=cs_odds_h,
            clean_sheet_odds_away=cs_odds_a,
            fixture_str_home=f"{away_team} (H)",
            fixture_str_away=f"{home_team} (A)",
        )

    def build_team_odds_map(
        self,
        fixtures: List[Dict[str, Any]],
        ratings: Optional[Dict[str, ClubEloRecord]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Constructs the standard team_odds dictionary consumed by XPModel and MatchdayHub:
        team_odds[club_code] = {
            'team': club_code,
            'opponent': opp_code,
            'is_home': bool,
            'exp_goals_scored': float,
            'exp_goals_conceded': float,
            'clean_sheet_prob': float,
            'clean_sheet_odds': float,
            'fixture_str': str
        }
        """
        ratings_map = ratings or self.get_epl_ratings()
        odds_map: Dict[str, Dict[str, Any]] = {}

        for fix in fixtures:
            h_code = fix.get("home") or fix.get("team_h_short") or fix.get("h_short")
            a_code = fix.get("away") or fix.get("team_a_short") or fix.get("a_short")

            if not h_code or not a_code:
                continue

            exp = self.compute_fixture_expectancy(h_code, a_code, ratings=ratings_map)

            odds_map[h_code] = {
                "team": h_code,
                "opponent": a_code,
                "is_home": True,
                "exp_goals_scored": exp.exp_goals_home,
                "exp_goals_conceded": exp.exp_goals_away,
                "clean_sheet_prob": exp.clean_sheet_prob_home,
                "clean_sheet_odds": exp.clean_sheet_odds_home,
                "fixture_str": exp.fixture_str_home,
                "elo": exp.home_elo,
                "opp_elo": exp.away_elo,
            }
            odds_map[a_code] = {
                "team": a_code,
                "opponent": h_code,
                "is_home": False,
                "exp_goals_scored": exp.exp_goals_away,
                "exp_goals_conceded": exp.exp_goals_home,
                "clean_sheet_prob": exp.clean_sheet_prob_away,
                "clean_sheet_odds": exp.clean_sheet_odds_away,
                "fixture_str": exp.fixture_str_away,
                "elo": exp.away_elo,
                "opp_elo": exp.home_elo,
            }

        return odds_map
