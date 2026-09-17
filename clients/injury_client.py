"""
---
type: Module
title: "Premier League Injury Intelligence Scraper & Intel Engine"
description: "Scrapes live Premier League injury and suspension data, resolves player identities to FPL elements, and maps statuses into Shane's Domain Intel availability metrics."
tags: [client, injuries, scraper, availability, domain, intel]
sources: ["docs/design/des_021_premier_injuries_automated_intel.md"]
generated:
  at: "2026-09-17T20:25:00Z"
  by: "agent:task-runner"
---
"""

from __future__ import annotations
import os
import re
import json
import time
import logging
import unicodedata
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional, Tuple, Set

import requests

from analytics.domain_intel import (
    AvailabilityOption,
    EligibilityOption,
    PlayerOverride,
    TTLWindow,
    ShaneIntelManager,
)
from clients.fpl_client import FPLClient
from config_manager import get_system_config

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_INJURY_CACHE_FILE = os.path.join(_PROJECT_ROOT, ".injury_cache.json")
DEFAULT_INJURY_CACHE_TTL_HOURS = 2.0

EPL_INJURY_ENDPOINT = "https://www.rotowire.com/soccer/tables/injury-report.php?league=EPL"
EPL_INJURY_REFERER = "https://www.rotowire.com/soccer/injury-report.php?league=EPL"


@dataclass(frozen=True)
class RawInjuryRecord:
    """Raw scraped injury record from live feed."""
    source_id: str
    player_name: str
    team_code: str          # 3-letter FPL code (ARS, CHE, etc.)
    position: str           # F/M, D, G, etc.
    injury_type: str        # Hamstring, Calf, Knee, etc.
    raw_status: str         # OUT, GTD, SUS
    return_date_desc: str   # Expected return or note


@dataclass(frozen=True)
class ProcessedInjuryIntel:
    """Normalized, FPL-resolved injury intelligence record."""
    fpl_element_id: Optional[int]
    web_name: str
    full_name: str
    team_code: str
    injury_type: str
    raw_status: str
    availability: AvailabilityOption
    p_fit: float
    expected_minutes: float
    news_snippet: str
    as_of_timestamp: float


def normalize_text(text: str) -> str:
    """Strip accents, lowercase, and remove special characters for fuzzy matching."""
    for char, repl in (("ø", "o"), ("Ø", "O"), ("æ", "ae"), ("Æ", "Ae"), ("ß", "ss"), ("ł", "l"), ("Ł", "L"), ("đ", "d"), ("Đ", "D")):
        text = text.replace(char, repl)
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r"[^a-zA-Z0-9\s]", "", ascii_text).lower().strip()


def map_injury_status_to_availability(raw_status: str, injury_type: str = "") -> Tuple[AvailabilityOption, float]:
    """
    Formal mapping function Φ(Status, InjuryType) -> (AvailabilityOption, p_fit).
    Translates qualitative medical/press reports into calibrated probabilities.
    """
    s = raw_status.upper().strip()
    inj = injury_type.lower().strip()

    if s in ("OUT", "SUSPENDED", "SUS", "U"):
        return AvailabilityOption.CONFIRMED_OUT_0, 0.00

    if s in ("GTD", "DOUBT", "D", "QUESTIONABLE"):
        # Severe soft-tissue / ligament doubts tend to be held out
        if any(w in inj for w in ("hamstring", "knee", "cruciate", "achilles", "groin", "thigh")):
            return AvailabilityOption.HEAVY_DOUBT_25, 0.25
        # Minor knocks, illness, or match fitness are 50/50 coin flips
        if any(w in inj for w in ("illness", "knock", "undisclosed", "foot", "ankle", "calf")):
            return AvailabilityOption.COIN_FLIP_50, 0.50
        # Mild doubt / lack of match fitness
        if "fitness" in inj or "fatigue" in inj:
            return AvailabilityOption.MILD_DOUBT_75, 0.75
        return AvailabilityOption.COIN_FLIP_50, 0.50

    if s in ("FIT", "AVAILABLE", "CLEARED", "A"):
        return AvailabilityOption.CLEARED_FIT_100, 1.00

    return AvailabilityOption.DEFAULT_OFFICIAL, 1.00


class InjuryClient:
    """
    Client for scraping and compiling Premier League injury intelligence.
    Extracts real-time statuses from public injury feeds, cross-references with FPL
    official player databases, and provisions Shane's Domain Intel desk.
    """

    def __init__(
        self,
        fpl_client: Optional[FPLClient] = None,
        cache_file: Optional[str] = None,
        cache_ttl_hours: float = DEFAULT_INJURY_CACHE_TTL_HOURS,
        http_timeout: int = 10,
    ) -> None:
        self.fpl_client = fpl_client or FPLClient()
        self.cache_file = cache_file or DEFAULT_INJURY_CACHE_FILE
        self.cache_ttl_seconds = cache_ttl_hours * 3600.0
        self.http_timeout = http_timeout
        self._fpl_players_index: Optional[Dict[str, Any]] = None

    def _build_fpl_player_index(self) -> Dict[str, Any]:
        """Index all active FPL players for rapid O(1) fuzzy resolution."""
        if self._fpl_players_index is not None:
            return self._fpl_players_index

        index = {
            "by_exact_name": {},        # "william saliba": player_dict
            "by_web_name": {},          # "saliba": [player_dict, ...]
            "by_team_last_name": {},    # ("ARS", "saliba"): player_dict
            "by_id": {},                # 123: player_dict
            "team_id_to_short": {},     # 1: "ARS"
            "short_to_team_id": {},     # "ARS": 1
        }

        try:
            boot = self.fpl_client.get_bootstrap_data()
            for t in boot.get("teams", []):
                t_id = t.get("id")
                s_name = t.get("short_name", "").upper()
                if t_id and s_name:
                    index["team_id_to_short"][t_id] = s_name
                    index["short_to_team_id"][s_name] = t_id

            for p in boot.get("elements", []):
                p_id = p.get("id")
                web_name = p.get("web_name", "")
                first_name = p.get("first_name", "")
                second_name = p.get("second_name", "")
                team_id = p.get("team")
                t_code = index["team_id_to_short"].get(team_id, "UNK")

                full_name = f"{first_name} {second_name}".strip()
                norm_full = normalize_text(full_name)
                norm_web = normalize_text(web_name)
                norm_last = normalize_text(second_name)

                record = {
                    "id": p_id,
                    "web_name": web_name,
                    "full_name": full_name,
                    "team_code": t_code,
                    "team_id": team_id,
                    "status": p.get("status"),
                    "chance_of_playing_next_round": p.get("chance_of_playing_next_round"),
                    "news": p.get("news", ""),
                }

                index["by_id"][p_id] = record
                index["by_exact_name"][norm_full] = record

                if norm_web not in index["by_web_name"]:
                    index["by_web_name"][norm_web] = []
                index["by_web_name"][norm_web].append(record)

                if norm_last:
                    index["by_team_last_name"][(t_code, norm_last)] = record

            self._fpl_players_index = index
        except Exception as e:
            logger.warning(f"Failed to build FPL player index: {e}")
            self._fpl_players_index = index

        return index

    def resolve_player(self, raw_player_name: str, team_code: str) -> Optional[Dict[str, Any]]:
        """
        Resolves an external player string to an official FPL element dict.
        Combines exact full name, (team, last name), and web name matching.
        """
        idx = self._build_fpl_player_index()
        norm_name = normalize_text(raw_player_name)
        t_code = team_code.upper().strip()

        # 1. Exact full name match
        if norm_name in idx["by_exact_name"]:
            return idx["by_exact_name"][norm_name]

        # 2. Team + Last Name match
        tokens = norm_name.split()
        if tokens:
            last_token = tokens[-1]
            if (t_code, last_token) in idx["by_team_last_name"]:
                return idx["by_team_last_name"][(t_code, last_token)]

        # 3. Web name match within the same team
        if norm_name in idx["by_web_name"]:
            candidates = idx["by_web_name"][norm_name]
            for c in candidates:
                if c["team_code"] == t_code:
                    return c
            if len(candidates) == 1:
                return candidates[0]

        # 4. Token search within the team's players
        for key, p in idx["by_exact_name"].items():
            if p["team_code"] == t_code:
                if any(tok in key for tok in tokens if len(tok) > 3):
                    return p

        return None

    def fetch_live_injuries_network(self) -> List[RawInjuryRecord]:
        """Fetch real-time Premier League injury records from public feed."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": EPL_INJURY_REFERER,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

        try:
            resp = requests.get(EPL_INJURY_ENDPOINT, headers=headers, timeout=self.http_timeout)
            if resp.status_code != 200:
                logger.warning(f"Injury feed returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            records: List[RawInjuryRecord] = []
            for item in data:
                raw_rec = RawInjuryRecord(
                    source_id=str(item.get("ID", "")),
                    player_name=str(item.get("player", "")).strip(),
                    team_code=str(item.get("team", "")).upper().strip(),
                    position=str(item.get("position", "")).strip(),
                    injury_type=str(item.get("injury", "Undisclosed")).strip(),
                    raw_status=str(item.get("status", "GTD")).upper().strip(),
                    return_date_desc=str(item.get("rDate", "")).strip(),
                )
                records.append(raw_rec)

            return records
        except Exception as e:
            logger.warning(f"Failed to fetch live injury feed: {e}")
            return []

    def get_injury_intel(self, force_refresh: bool = False) -> List[ProcessedInjuryIntel]:
        """
        Retrieves complete, normalized Premier League injury intelligence.
        Uses local cache if valid (< 2 hours), otherwise queries network with FPL fallback.
        """
        # 1. Read from disk cache if fresh
        if not force_refresh and os.path.exists(self.cache_file):
            try:
                age = time.time() - os.path.getmtime(self.cache_file)
                if age < self.cache_ttl_seconds:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        cached_json = json.load(f)
                    items = [
                        ProcessedInjuryIntel(
                            fpl_element_id=v["fpl_element_id"],
                            web_name=v["web_name"],
                            full_name=v["full_name"],
                            team_code=v["team_code"],
                            injury_type=v["injury_type"],
                            raw_status=v["raw_status"],
                            availability=AvailabilityOption(v["availability"]),
                            p_fit=v["p_fit"],
                            expected_minutes=v["expected_minutes"],
                            news_snippet=v["news_snippet"],
                            as_of_timestamp=v["as_of_timestamp"],
                        )
                        for v in cached_json.get("injuries", [])
                    ]
                    if items:
                        return items
            except Exception as e:
                logger.warning(f"Error reading injury cache: {e}")

        # 2. Fetch from live network feed
        raw_records = self.fetch_live_injuries_network()
        processed_list: List[ProcessedInjuryIntel] = []
        now = time.time()

        if raw_records:
            for raw in raw_records:
                resolved = self.resolve_player(raw.player_name, raw.team_code)
                avail_opt, p_fit = map_injury_status_to_availability(raw.raw_status, raw.injury_type)

                if avail_opt == AvailabilityOption.CONFIRMED_OUT_0:
                    exp_mins = 0.0
                elif avail_opt == AvailabilityOption.HEAVY_DOUBT_25:
                    exp_mins = 25.0
                elif avail_opt == AvailabilityOption.COIN_FLIP_50:
                    exp_mins = 45.0
                elif avail_opt == AvailabilityOption.MILD_DOUBT_75:
                    exp_mins = 65.0
                else:
                    exp_mins = 85.0

                fpl_id = resolved["id"] if resolved else None
                web_name = resolved["web_name"] if resolved else raw.player_name
                full_name = resolved["full_name"] if resolved else raw.player_name

                snippet = f"{raw.injury_type} ({raw.raw_status})"
                if resolved and resolved.get("news"):
                    snippet = f"{snippet} | FPL: {resolved['news']}"

                p_intel = ProcessedInjuryIntel(
                    fpl_element_id=fpl_id,
                    web_name=web_name,
                    full_name=full_name,
                    team_code=raw.team_code,
                    injury_type=raw.injury_type,
                    raw_status=raw.raw_status,
                    availability=avail_opt,
                    p_fit=p_fit,
                    expected_minutes=exp_mins,
                    news_snippet=snippet,
                    as_of_timestamp=now,
                )
                processed_list.append(p_intel)

        # 3. Fallback: If network scrape empty, compile from FPL official bootstrap
        if not processed_list:
            try:
                boot = self.fpl_client.get_bootstrap_data()
                id_to_short = {t["id"]: t["short_name"] for t in boot.get("teams", [])}
                for p in boot.get("elements", []):
                    status = p.get("status", "a")
                    if status != "a":
                        t_code = id_to_short.get(p.get("team"), "UNK")
                        news = p.get("news", "")
                        raw_status = "OUT" if status in ("u", "i") else "GTD"
                        avail_opt, p_fit = map_injury_status_to_availability(raw_status, news)

                        p_intel = ProcessedInjuryIntel(
                            fpl_element_id=p.get("id"),
                            web_name=p.get("web_name", "UNK"),
                            full_name=f"{p.get('first_name', '')} {p.get('second_name', '')}".strip(),
                            team_code=t_code,
                            injury_type="Official FPL Flag",
                            raw_status=raw_status,
                            availability=avail_opt,
                            p_fit=p_fit,
                            expected_minutes=0.0 if p_fit == 0.0 else 45.0,
                            news_snippet=news,
                            as_of_timestamp=now,
                        )
                        processed_list.append(p_intel)
            except Exception as e:
                logger.warning(f"Failed to generate FPL fallback injury list: {e}")

        # 4. Save to cache
        if processed_list:
            try:
                payload = {
                    "as_of_timestamp": now,
                    "count": len(processed_list),
                    "injuries": [
                        {
                            "fpl_element_id": p.fpl_element_id,
                            "web_name": p.web_name,
                            "full_name": p.full_name,
                            "team_code": p.team_code,
                            "injury_type": p.injury_type,
                            "raw_status": p.raw_status,
                            "availability": p.availability.value,
                            "p_fit": p.p_fit,
                            "expected_minutes": p.expected_minutes,
                            "news_snippet": p.news_snippet,
                            "as_of_timestamp": p.as_of_timestamp,
                        }
                        for p in processed_list
                    ],
                }
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to write injury cache: {e}")

        return processed_list

    def get_injury_intel_by_web_name(self, force_refresh: bool = False) -> Dict[str, ProcessedInjuryIntel]:
        """Returns map of lowercase web_name -> ProcessedInjuryIntel for rapid lookup."""
        intel_list = self.get_injury_intel(force_refresh=force_refresh)
        return {item.web_name.lower(): item for item in intel_list}

    def sync_to_shane_intel(
        self,
        intel_manager: ShaneIntelManager,
        current_gw: int,
        auto_apply_out: bool = True,
        target_web_names: Optional[Set[str]] = None,
    ) -> int:
        """
        Synchronizes scraped injury intelligence into ShaneIntelManager overrides.
        Filters to target_web_names (e.g., current squad or shortlist) if specified.
        Returns number of overrides set.
        """
        injury_map = self.get_injury_intel_by_web_name()
        synced_count = 0

        for web_name_lower, intel in injury_map.items():
            if target_web_names and web_name_lower not in target_web_names:
                continue

            # Only sync deviations from full fitness
            if intel.availability == AvailabilityOption.DEFAULT_OFFICIAL or intel.availability == AvailabilityOption.CLEARED_FIT_100:
                continue

            if not auto_apply_out and intel.availability == AvailabilityOption.CONFIRMED_OUT_0:
                continue

            override = PlayerOverride(
                web_name=intel.web_name,
                scope="squad",
                valid_gameweek=current_gw,
                ttl_window=TTLWindow.CURRENT_GW_ONLY,
                availability=intel.availability,
                eligibility=EligibilityOption.DEFAULT_ELIGIBLE,
                expected_minutes=intel.expected_minutes,
                reason_category=f"Premier Injuries Scraper: {intel.injury_type}",
                active=True,
            )
            intel_manager.set_override(override)
            synced_count += 1

        if synced_count > 0:
            intel_manager.save_overrides(gameweek=current_gw)

        return synced_count
