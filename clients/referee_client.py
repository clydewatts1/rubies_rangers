"""
---
type: Module
title: "Premier League Referee Historical Analytics & Tendency Client"
description: "Ingests referee profiles, historical penalty award frequencies, and card accumulation tendencies to dynamically modulate penalty taker expectations and disciplinary tail risks."
tags: [client, referee, penalties, cards, analytics, xp, montecarlo]
sources: ["docs/design/des_024_referee_penalty_variance_modeling.md"]
generated:
  at: "2026-09-17T21:37:00Z"
  by: "agent:task-runner"
---
"""

from __future__ import annotations
import os
import re
import json
import logging
import unicodedata
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_REFEREE_DATA_FILE = os.path.join(_PROJECT_ROOT, "data", "referee_tendencies.json")

LEAGUE_BASELINE_PENALTIES_PER_MATCH = 0.20
LEAGUE_BASELINE_YELLOWS_PER_MATCH = 3.95
LEAGUE_BASELINE_REDS_PER_MATCH = 0.11
LEAGUE_BASELINE_FOULS_PER_TACKLE = 0.58


@dataclass(frozen=True)
class RefereeProfile:
    """Historical disciplinary and penalty profile for a match referee."""
    name: str
    matches_refereed: int
    penalties_per_match: float
    yellows_per_match: float
    reds_per_match: float
    fouls_per_tackle: float
    penalty_multiplier: float
    yellow_multiplier: float
    red_multiplier: float
    card_risk_tier: str         # "LOW", "MODERATE", "ELEVATED", "EXTREME"


LEAGUE_BASELINE_PROFILE = RefereeProfile(
    name="League Average Official",
    matches_refereed=1000,
    penalties_per_match=LEAGUE_BASELINE_PENALTIES_PER_MATCH,
    yellows_per_match=LEAGUE_BASELINE_YELLOWS_PER_MATCH,
    reds_per_match=LEAGUE_BASELINE_REDS_PER_MATCH,
    fouls_per_tackle=LEAGUE_BASELINE_FOULS_PER_TACKLE,
    penalty_multiplier=1.0,
    yellow_multiplier=1.0,
    red_multiplier=1.0,
    card_risk_tier="MODERATE",
)


def normalize_name(text: str) -> str:
    """Normalize text for cross-dataset mapping and lookup."""
    for char, repl in (("ø", "o"), ("Ø", "O"), ("æ", "ae"), ("Æ", "Ae"), ("ß", "ss"), ("ł", "l"), ("Ł", "L")):
        text = text.replace(char, repl)
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r"[^a-zA-Z0-9\s]", "", ascii_text).lower().strip()


def compute_referee_penalty_multiplier(
    penalties_per_match: float,
    league_avg: float = LEAGUE_BASELINE_PENALTIES_PER_MATCH,
    min_mult: float = 0.65,
    max_mult: float = 1.85,
) -> float:
    """
    Computes penalty award multiplier based on historical penalty award frequency.
    Clamps between [0.65, 1.85].
    """
    if league_avg <= 0:
        return 1.0
    raw_mult = penalties_per_match / league_avg
    return round(max(min_mult, min(max_mult, raw_mult)), 3)


def compute_referee_yellow_multiplier(
    yellows_per_match: float,
    league_avg: float = LEAGUE_BASELINE_YELLOWS_PER_MATCH,
    min_mult: float = 0.75,
    max_mult: float = 1.35,
) -> float:
    """
    Computes yellow card frequency multiplier relative to league baseline.
    Clamps between [0.75, 1.35].
    """
    if league_avg <= 0:
        return 1.0
    raw_mult = yellows_per_match / league_avg
    return round(max(min_mult, min(max_mult, raw_mult)), 3)


def compute_referee_red_multiplier(
    reds_per_match: float,
    league_avg: float = LEAGUE_BASELINE_REDS_PER_MATCH,
    min_mult: float = 0.60,
    max_mult: float = 1.60,
) -> float:
    """
    Computes red card frequency multiplier relative to league baseline.
    Clamps between [0.60, 1.60].
    """
    if league_avg <= 0:
        return 1.0
    raw_mult = reds_per_match / league_avg
    return round(max(min_mult, min(max_mult, raw_mult)), 3)


def determine_card_risk_tier(yellows_per_match: float) -> str:
    """Categorizes referee strictness into qualitative risk tier."""
    if yellows_per_match >= 4.50:
        return "EXTREME"
    elif yellows_per_match >= 4.15:
        return "ELEVATED"
    elif yellows_per_match >= 3.75:
        return "MODERATE"
    else:
        return "LOW"


class RefereeClient:
    """
    Client for accessing Premier League referee tendencies and fixture appointments.
    Provides penalty award multipliers and disciplinary variance metrics.
    """

    def __init__(self, data_file: Optional[str] = None) -> None:
        self.data_file = data_file or DEFAULT_REFEREE_DATA_FILE
        self._profiles_cache: Optional[Dict[str, RefereeProfile]] = None
        self._appointments_cache: Optional[Dict[str, str]] = None
        self._load_data()

    def _load_data(self) -> None:
        """Load curated referee tendencies and appointments from disk."""
        if not os.path.exists(self.data_file):
            logger.warning(f"Referee data file not found at {self.data_file}. Using defaults.")
            self._profiles_cache = {}
            self._appointments_cache = {}
            return

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            base_pen = data.get("league_baseline", {}).get("penalties_per_match", LEAGUE_BASELINE_PENALTIES_PER_MATCH)
            base_yc = data.get("league_baseline", {}).get("yellows_per_match", LEAGUE_BASELINE_YELLOWS_PER_MATCH)
            base_rc = data.get("league_baseline", {}).get("reds_per_match", LEAGUE_BASELINE_REDS_PER_MATCH)

            profiles: Dict[str, RefereeProfile] = {}
            for key, rec in data.get("referees", {}).items():
                norm_key = normalize_name(key)
                pen_rate = float(rec.get("penalties_per_match", base_pen))
                yc_rate = float(rec.get("yellows_per_match", base_yc))
                rc_rate = float(rec.get("reds_per_match", base_rc))
                foul_rate = float(rec.get("fouls_per_tackle", LEAGUE_BASELINE_FOULS_PER_TACKLE))

                profiles[norm_key] = RefereeProfile(
                    name=rec.get("name", key.title()),
                    matches_refereed=int(rec.get("matches_refereed", 50)),
                    penalties_per_match=pen_rate,
                    yellows_per_match=yc_rate,
                    reds_per_match=rc_rate,
                    fouls_per_tackle=foul_rate,
                    penalty_multiplier=compute_referee_penalty_multiplier(pen_rate, base_pen),
                    yellow_multiplier=compute_referee_yellow_multiplier(yc_rate, base_yc),
                    red_multiplier=compute_referee_red_multiplier(rc_rate, base_rc),
                    card_risk_tier=determine_card_risk_tier(yc_rate),
                )

            self._profiles_cache = profiles
            self._appointments_cache = {
                k.upper(): normalize_name(v) for k, v in data.get("default_appointments", {}).items()
            }
        except Exception as e:
            logger.error(f"Failed to load referee data: {e}")
            self._profiles_cache = {}
            self._appointments_cache = {}

    def get_all_referees(self) -> Dict[str, RefereeProfile]:
        """Returns map of normalized referee name -> RefereeProfile."""
        if self._profiles_cache is None:
            self._load_data()
        return self._profiles_cache or {}

    def get_referee_profile(self, referee_name: str) -> RefereeProfile:
        """
        Retrieves profile for named referee.
        Gracefully falls back to LEAGUE_BASELINE_PROFILE if not found.
        """
        if self._profiles_cache is None:
            self._load_data()

        key = normalize_name(referee_name)
        if self._profiles_cache and key in self._profiles_cache:
            return self._profiles_cache[key]

        # Check last name match
        tokens = key.split()
        if tokens and self._profiles_cache:
            for k, prof in self._profiles_cache.items():
                if tokens[-1] in k.split():
                    return prof

        return LEAGUE_BASELINE_PROFILE

    def get_referee_for_team(self, team_short: str) -> RefereeProfile:
        """
        Looks up appointed referee for team's upcoming match.
        Falls back to LEAGUE_BASELINE_PROFILE if unassigned.
        """
        if self._appointments_cache is None:
            self._load_data()

        t_code = team_short.upper()
        if self._appointments_cache and t_code in self._appointments_cache:
            ref_name = self._appointments_cache[t_code]
            return self.get_referee_profile(ref_name)

        return LEAGUE_BASELINE_PROFILE

    def get_referee_for_fixture(self, home_team: str, away_team: str) -> RefereeProfile:
        """Looks up appointed referee for a home/away team pair."""
        return self.get_referee_for_team(home_team) or self.get_referee_for_team(away_team)
