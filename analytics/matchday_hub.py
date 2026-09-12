"""
Matchday Center & Live Gameweek Squad Engine
Aggregates live Premier League fixture scores, player event statistics, and manager active squad picks.
Maps active starters, captaincy multiplier (2x), and bench to real-time match events.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

from clients.fpl_client import FPLClient
from trackers.league import LeagueTracker, DEFAULT_ENTRY_ID
from analytics.xp_model import DEFAULT_SQUAD


@dataclass(frozen=True)
class MatchdayPlayer:
    """Represents a player in the active squad with live matchday stats."""
    id: int
    web_name: str
    club_short: str
    position: str
    role: str  # 'CAP', 'VC', 'START', 'BENCH'
    multiplier: int
    is_starter: bool
    live_points: int
    effective_points: int  # live_points * multiplier
    minutes: int
    goals: int
    assists: int
    clean_sheets: int
    goals_conceded: int
    saves: int
    bonus: int
    bps: int
    match_status: str  # 'COMPLETED', 'ON_PITCH', 'DID_NOT_PLAY', 'UPCOMING'
    fixture_id: Optional[int]
    opponent_short: str
    is_home: bool


@dataclass(frozen=True)
class MatchdayFixture:
    """Represents a gameweek fixture with live scoreline and squad players involved."""
    fixture_id: int
    home_short: str
    away_short: str
    home_score: Optional[int]
    away_score: Optional[int]
    started: bool
    finished: bool
    minutes: int
    kickoff_time: str
    status_label: str  # e.g., 'FT', 'LIVE 72\'', 'Sat 15:00'
    has_squad_player: bool
    home_squad_players: List[MatchdayPlayer]
    away_squad_players: List[MatchdayPlayer]


@dataclass(frozen=True)
class MatchdaySummary:
    """Comprehensive matchday report for the manager's active squad."""
    gameweek: int
    entry_id: int
    entry_name: str
    total_live_points: int
    starters_played_count: int
    starters_playing_count: int
    starters_to_play_count: int
    captain_name: str
    captain_points: int
    vice_captain_name: str
    vice_captain_points: int
    bench_reserve_points: int
    active_chip: Optional[str]
    auto_subs: List[Dict[str, Any]]
    fixtures: List[MatchdayFixture]
    starters: List[MatchdayPlayer]
    bench: List[MatchdayPlayer]


class MatchdayHub:
    """Coordinates data extraction and live aggregation for the Matchday Center."""

    def __init__(self, fpl_client: Optional[FPLClient] = None, league_tracker: Optional[LeagueTracker] = None):
        self.fpl_client = fpl_client or FPLClient()
        self.league_tracker = league_tracker or LeagueTracker()

    def get_matchday_summary(
        self,
        entry_id: Optional[int] = None,
        gameweek: Optional[int] = None,
        active_squad_override: Optional[List[str]] = None,
        force_refresh: bool = False
    ) -> MatchdaySummary:
        """
        Builds a comprehensive matchday report binding live fixture scorelines
        with the manager's active starting XI and bench.
        """
        target_entry_id = entry_id or DEFAULT_ENTRY_ID
        boot = self.fpl_client.get_bootstrap_data(force_refresh=force_refresh)

        # 1. Determine active gameweek
        if gameweek is None:
            gameweek = self.fpl_client.get_current_gameweek() or 1

        # Lookup dictionaries
        teams_map = {t["id"]: t["short_name"] for t in boot.get("teams", [])}
        pos_map = {p["id"]: p["singular_name_short"] for p in boot.get("element_types", [])}
        elements_map = {
            el["id"]: {
                "id": el["id"],
                "web_name": el["web_name"],
                "full_name": f"{el.get('first_name', '')} {el.get('second_name', '')}".strip(),
                "team_id": el["team"],
                "club_short": teams_map.get(el["team"], "UNK"),
                "position": pos_map.get(el["element_type"], "UNK"),
                "now_cost": el.get("now_cost", 50) / 10.0,
            }
            for el in boot.get("elements", [])
        }

        # 2. Fetch Fixtures for Current Gameweek
        fixtures_raw = self.fpl_client.get_gameweek_fixtures(gameweek, force_refresh=force_refresh)

        # 3. Fetch Live Player Events
        live_raw = self.fpl_client.get_gameweek_live(gameweek, force_refresh=force_refresh)
        live_elements = {
            el["id"]: el.get("stats", {})
            for el in live_raw.get("elements", [])
        }

        # 4. Fetch Active Team Picks (Fallback to active_squad_override or DEFAULT_SQUAD)
        picks_list: List[Dict[str, Any]] = []
        entry_name = "Rubies Rangers"
        active_chip = None

        if target_entry_id:
            try:
                picks_payload = self.league_tracker.get_team_picks(target_entry_id, gameweek)
                # Raw picks payload from FPL API
                entry_url = f"https://fantasy.premierleague.com/api/entry/{target_entry_id}/event/{gameweek}/picks/"
                raw_picks_data = self.fpl_client._fetch_url(entry_url)
                if isinstance(raw_picks_data, dict) and "picks" in raw_picks_data:
                    picks_list = raw_picks_data["picks"]
                    active_chip = raw_picks_data.get("active_chip")
            except Exception:
                picks_list = []

        # Fallback if picks cannot be fetched (e.g. pre-deadline or offline)
        if not picks_list:
            squad_names = active_squad_override or DEFAULT_SQUAD
            # Build synthetic picks
            name_to_el = {el["web_name"].lower(): el for el in elements_map.values()}
            pos_counter = 1
            for name in squad_names:
                el = name_to_el.get(name.lower())
                if not el:
                    # Partial match
                    for k, v in name_to_el.items():
                        if name.lower() in k:
                            el = v
                            break
                if el:
                    is_cap = (pos_counter == 11)
                    is_vc = (pos_counter == 5)
                    mult = 2 if is_cap else (1 if pos_counter <= 11 else 0)
                    picks_list.append({
                        "element": el["id"],
                        "position": pos_counter,
                        "multiplier": mult,
                        "is_captain": is_cap,
                        "is_vice_captain": is_vc
                    })
                    pos_counter += 1

        # 5. Map Fixtures by Team ID and build fixture lookup
        team_to_fixture: Dict[int, Dict[str, Any]] = {}
        for f in fixtures_raw:
            team_to_fixture[f["team_h"]] = f
            team_to_fixture[f["team_a"]] = f

        # 6. Construct MatchdayPlayer objects
        starters: List[MatchdayPlayer] = []
        bench: List[MatchdayPlayer] = []
        players_by_fixture_home: Dict[int, List[MatchdayPlayer]] = {}
        players_by_fixture_away: Dict[int, List[MatchdayPlayer]] = {}

        captain_name = "None"
        captain_pts = 0
        vice_captain_name = "None"
        vice_captain_pts = 0
        live_total = 0
        bench_reserve = 0
        played_count = 0
        playing_count = 0
        to_play_count = 0

        for p in picks_list:
            el_id = p["element"]
            el_info = elements_map.get(el_id, {
                "id": el_id,
                "web_name": f"Player {el_id}",
                "club_short": "UNK",
                "team_id": 0,
                "position": "MID"
            })
            p_stats = live_elements.get(el_id, {})
            mult = p.get("multiplier", 1 if p.get("position", 1) <= 11 else 0)
            is_cap = p.get("is_captain", False)
            is_vc = p.get("is_vice_captain", False)
            is_start = mult > 0 or p.get("position", 1) <= 11

            role = "CAP" if is_cap else ("VC" if is_vc else ("START" if is_start else "BENCH"))

            pts = int(p_stats.get("total_points", 0))
            mins = int(p_stats.get("minutes", 0))
            goals = int(p_stats.get("goals_scored", 0))
            assists = int(p_stats.get("assists", 0))
            cs = int(p_stats.get("clean_sheets", 0))
            gc = int(p_stats.get("goals_conceded", 0))
            saves = int(p_stats.get("saves", 0))
            bonus = int(p_stats.get("bonus", 0))
            bps = int(p_stats.get("bps", 0))

            eff_pts = pts * mult

            # Locate fixture
            t_id = el_info["team_id"]
            fix = team_to_fixture.get(t_id)
            fix_id = fix.get("id") if fix else None
            is_home = (fix.get("team_h") == t_id) if fix else True
            opp_id = fix.get("team_a") if is_home else fix.get("team_h") if fix else None
            opp_short = teams_map.get(opp_id, "TBD") if opp_id else "TBD"

            # Match status for player
            fix_started = fix.get("started", False) if fix else False
            fix_finished = fix.get("finished", False) if fix else False

            if fix_finished:
                p_status = "COMPLETED" if mins > 0 else "DID_NOT_PLAY"
            elif fix_started:
                p_status = "ON_PITCH" if mins > 0 else "UPCOMING"
            else:
                p_status = "UPCOMING"

            player_obj = MatchdayPlayer(
                id=el_id,
                web_name=el_info["web_name"],
                club_short=el_info["club_short"],
                position=el_info["position"],
                role=role,
                multiplier=mult,
                is_starter=is_start,
                live_points=pts,
                effective_points=eff_pts,
                minutes=mins,
                goals=goals,
                assists=assists,
                clean_sheets=cs,
                goals_conceded=gc,
                saves=saves,
                bonus=bonus,
                bps=bps,
                match_status=p_status,
                fixture_id=fix_id,
                opponent_short=opp_short,
                is_home=is_home
            )

            if is_cap:
                captain_name = player_obj.web_name
                captain_pts = eff_pts
            if is_vc:
                vice_captain_name = player_obj.web_name
                vice_captain_pts = eff_pts

            if is_start:
                starters.append(player_obj)
                live_total += eff_pts
                if p_status == "COMPLETED":
                    played_count += 1
                elif p_status == "ON_PITCH":
                    playing_count += 1
                else:
                    to_play_count += 1
            else:
                bench.append(player_obj)
                bench_reserve += pts

            if fix_id is not None:
                if is_home:
                    players_by_fixture_home.setdefault(fix_id, []).append(player_obj)
                else:
                    players_by_fixture_away.setdefault(fix_id, []).append(player_obj)

        # 7. Construct MatchdayFixture objects
        matchday_fixtures: List[MatchdayFixture] = []
        for f in fixtures_raw:
            f_id = f["id"]
            h_short = teams_map.get(f["team_h"], f"T{f['team_h']}")
            a_short = teams_map.get(f["team_a"], f"T{f['team_a']}")
            h_score = f.get("team_h_score")
            a_score = f.get("team_a_score")
            started = f.get("started", False)
            finished = f.get("finished", False)
            m_mins = f.get("minutes", 0)

            if finished:
                status_lbl = "FT"
            elif started:
                status_lbl = f"LIVE {m_mins}'"
            else:
                ko = f.get("kickoff_time", "")
                status_lbl = ko[11:16] if len(ko) >= 16 else "UPCOMING"

            h_squad = players_by_fixture_home.get(f_id, [])
            a_squad = players_by_fixture_away.get(f_id, [])
            has_squad = (len(h_squad) + len(a_squad)) > 0

            matchday_fixtures.append(MatchdayFixture(
                fixture_id=f_id,
                home_short=h_short,
                away_short=a_short,
                home_score=h_score,
                away_score=a_score,
                started=started,
                finished=finished,
                minutes=m_mins,
                kickoff_time=f.get("kickoff_time", ""),
                status_label=status_lbl,
                has_squad_player=has_squad,
                home_squad_players=h_squad,
                away_squad_players=a_squad
            ))

        # Sort fixtures: active squad fixtures first, then by started / kickoff time
        matchday_fixtures.sort(key=lambda x: (not x.has_squad_player, not x.started, x.finished, x.kickoff_time))

        # 8. Projected Automatic Substitutions
        auto_subs = []
        for s in starters:
            if s.match_status == "DID_NOT_PLAY":
                # Find eligible bench player who played or has yet to play
                for b in bench:
                    if b.position == s.position or (b.position != "GKP" and s.position != "GKP"):
                        auto_subs.append({
                            "sub_out": s.web_name,
                            "sub_in": b.web_name,
                            "points_added": b.live_points,
                            "reason": f"{s.web_name} played 0 minutes (Match Finished)"
                        })
                        break

        return MatchdaySummary(
            gameweek=gameweek,
            entry_id=target_entry_id,
            entry_name=entry_name,
            total_live_points=live_total,
            starters_played_count=played_count,
            starters_playing_count=playing_count,
            starters_to_play_count=to_play_count,
            captain_name=captain_name,
            captain_points=captain_pts,
            vice_captain_name=vice_captain_name,
            vice_captain_points=vice_captain_pts,
            bench_reserve_points=bench_reserve,
            active_chip=active_chip,
            auto_subs=auto_subs,
            fixtures=matchday_fixtures,
            starters=starters,
            bench=bench
        )
