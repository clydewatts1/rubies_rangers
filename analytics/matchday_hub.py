"""
Matchday Center & Live Gameweek Squad Engine
Aggregates live Premier League fixture scores, player event statistics, and manager active squad picks.
Maps active starters, captaincy multiplier (2x), and bench to real-time match events.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore
from typing import Dict, List, Any, Optional

from clients.fpl_client import FPLClient
from clients.weather_client import WeatherClient, WeatherObservation
from trackers.league import DEFAULT_ENTRY_ID, DEFAULT_LEAGUE_ID, LeagueTracker
from analytics.xp_model import DEFAULT_SQUAD


@dataclass(frozen=True)
class MemberDayScore:
    """Live matchday breakdown for a single mini-league member."""
    entry_id: int
    team_name: str
    manager_name: str
    rank: int
    last_rank: int
    captain_name: str
    captain_multiplier: int
    captain_points: int
    captain_day: str  # e.g., 'Saturday', 'Sunday', 'Upcoming'
    active_chip: Optional[str]
    transfer_cost: int
    starters_played: int
    starters_playing: int
    starters_to_play: int
    day_points: Dict[str, int]  # points scored on each day of week (e.g. {"Saturday": 58, "Sunday": 45})
    cumulative_day_points: Dict[str, int]  # running sum across days (e.g. {"Saturday": 58, "Sunday": 103})
    live_gw_points: int  # sum of starters effective points
    net_gw_points: int  # live_gw_points - transfer_cost
    projected_final_points: float  # live_gw_points + remaining_xp - transfer_cost
    total_league_points: int
    remaining_players: List[Dict[str, Any]] = field(default_factory=list)
    auto_subs_pending: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class MiniLeagueScoreboard:
    """Comprehensive Gameweek live scoreboard and day-of-week progression for a mini-league."""
    league_id: int
    league_name: str
    gameweek: int
    active_days: List[str]  # e.g., ['Friday', 'Saturday', 'Sunday', 'Monday']
    members: List[MemberDayScore]
    highest_day_scorers: Dict[str, Dict[str, Any]]  # day -> {"team": str, "points": int, "manager": str}
    top_captains: Dict[str, int]  # captain_name -> count
    league_avg_live_points: float
    league_avg_net_points: float


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
    talisman_share: float = 0.0


@dataclass(frozen=True)
class FixturePrediction:
    """Quantitative Poisson match outcome prediction."""
    home_xg: float
    away_xg: float
    predicted_home_score: int
    predicted_away_score: int
    home_win_prob: float      # percentage e.g. 58.2
    draw_prob: float          # percentage e.g. 24.1
    away_win_prob: float      # percentage e.g. 17.7
    home_cs_prob: float       # percentage e.g. 42.5
    away_cs_prob: float       # percentage e.g. 18.0
    home_cs_odds: float       # decimal odds e.g. 2.35
    away_cs_odds: float       # decimal odds e.g. 5.56
    btts_prob: float          # both teams to score %
    over_25_prob: float       # over 2.5 goals %
    expected_total_goals: float
    outcome_label: str        # e.g., 'ARS Win 2-0 (64% Win Prob | 58% CS)'


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
    weather: Optional[WeatherObservation] = None
    weather_badge_html: str = ""
    match_day: str = "Saturday"
    match_date_str: str = ""
    match_time_str: str = ""
    prediction: Optional[FixturePrediction] = None


def calculate_fixture_prediction(
    h_short: str,
    a_short: str,
    gameweek: int = 4,
    team_odds_map: Optional[Dict[str, Any]] = None
) -> FixturePrediction:
    """
    Computes bivariate Poisson match probabilities and most likely scoreline
    from team expected goals (xG).
    """
    import math

    if team_odds_map and h_short in team_odds_map and a_short in team_odds_map:
        h_xg = float(team_odds_map[h_short].get("exp_goals_scored", 1.45))
        a_xg = float(team_odds_map[a_short].get("exp_goals_scored", 1.15))
    else:
        try:
            from analytics.xp_model import XPModel
            xm = XPModel(gameweek=gameweek)
            h_info = xm.team_odds.get(h_short, {})
            a_info = xm.team_odds.get(a_short, {})
            h_xg = float(h_info.get("exp_goals_scored", 1.45))
            a_xg = float(a_info.get("exp_goals_scored", 1.15))
        except Exception:
            h_xg = 1.45
            a_xg = 1.15

    # Poisson distribution over score grid 0..6
    probs: Dict[Tuple[int, int], float] = {}
    for h in range(7):
        p_h = (h_xg ** h) * math.exp(-h_xg) / math.factorial(h)
        for a in range(7):
            p_a = (a_xg ** a) * math.exp(-a_xg) / math.factorial(a)
            probs[(h, a)] = p_h * p_a

    # Mode of distribution (most likely integer scoreline)
    best_score = max(probs.keys(), key=lambda k: probs[k])
    pred_h, pred_a = best_score

    p_h_win_raw = sum(p for (h, a), p in probs.items() if h > a)
    p_draw_raw = sum(p for (h, a), p in probs.items() if h == a)
    p_a_win_raw = sum(p for (h, a), p in probs.items() if h < a)
    total_w_d_l = p_h_win_raw + p_draw_raw + p_a_win_raw

    if total_w_d_l > 0:
        p_h_win = (p_h_win_raw / total_w_d_l) * 100.0
        p_draw = (p_draw_raw / total_w_d_l) * 100.0
        p_a_win = (p_a_win_raw / total_w_d_l) * 100.0
    else:
        p_h_win = 33.3
        p_draw = 33.4
        p_a_win = 33.3

    h_cs_prob = math.exp(-a_xg) * 100.0
    a_cs_prob = math.exp(-h_xg) * 100.0
    h_cs_odds = round(100.0 / h_cs_prob, 2) if h_cs_prob > 0 else 99.0
    a_cs_odds = round(100.0 / a_cs_prob, 2) if a_cs_prob > 0 else 99.0

    over_25 = sum(p for (h, a), p in probs.items() if (h + a) >= 3) * 100.0
    btts = (1.0 - math.exp(-h_xg)) * (1.0 - math.exp(-a_xg)) * 100.0
    exp_total = round(h_xg + a_xg, 2)

    if p_h_win >= p_a_win and p_h_win >= p_draw:
        outcome_lbl = f"{h_short} Win ({p_h_win:.0f}%)"
    elif p_a_win >= p_h_win and p_a_win >= p_draw:
        outcome_lbl = f"{a_short} Win ({p_a_win:.0f}%)"
    else:
        outcome_lbl = f"Draw ({p_draw:.0f}%)"

    return FixturePrediction(
        home_xg=round(h_xg, 2),
        away_xg=round(a_xg, 2),
        predicted_home_score=pred_h,
        predicted_away_score=pred_a,
        home_win_prob=round(p_h_win, 1),
        draw_prob=round(p_draw, 1),
        away_win_prob=round(p_a_win, 1),
        home_cs_prob=round(h_cs_prob, 1),
        away_cs_prob=round(a_cs_prob, 1),
        home_cs_odds=h_cs_odds,
        away_cs_odds=a_cs_odds,
        btts_prob=round(btts, 1),
        over_25_prob=round(over_25, 1),
        expected_total_goals=exp_total,
        outcome_label=outcome_lbl
    )


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
    adverse_weather_count: int = 0
    squad_weather_alerts: List[str] = field(default_factory=list)


class MatchdayHub:
    """Coordinates data extraction and live aggregation for the Matchday Center."""

    def __init__(
        self,
        fpl_client: Optional[FPLClient] = None,
        league_tracker: Optional[LeagueTracker] = None,
        weather_client: Optional[WeatherClient] = None
    ):
        self.fpl_client = fpl_client or FPLClient()
        self.league_tracker = league_tracker or LeagueTracker()
        self.weather_client = weather_client or WeatherClient()

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

        team_xgi_totals: Dict[int, float] = {}
        for el in boot.get("elements", []):
            t_id = el.get("team")
            xgi_val = float(el.get("expected_goal_involvements") or 0.0)
            team_xgi_totals[t_id] = team_xgi_totals.get(t_id, 0.0) + xgi_val

        elements_map = {
            el["id"]: {
                "id": el["id"],
                "web_name": el["web_name"],
                "full_name": f"{el.get('first_name', '')} {el.get('second_name', '')}".strip(),
                "team_id": el["team"],
                "club_short": teams_map.get(el["team"], "UNK"),
                "position": pos_map.get(el["element_type"], "UNK"),
                "now_cost": el.get("now_cost", 50) / 10.0,
                "talisman_share": round((float(el.get("expected_goal_involvements") or 0.0) / team_xgi_totals[el["team"]] * 100.0), 1) if team_xgi_totals.get(el["team"], 0) > 0 else 0.0
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
                is_home=is_home,
                talisman_share=el_info.get("talisman_share", 0.0)
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

        # 7. Construct MatchdayFixture objects with Meteorological Intelligence & Predicted Outcomes
        matchday_fixtures: List[MatchdayFixture] = []
        adverse_count = 0
        squad_weather_alerts = []

        # Precompute team odds for Poisson outcome predictions
        try:
            from analytics.xp_model import XPModel
            xm = XPModel(gameweek=gameweek)
            team_odds_map = xm.team_odds
        except Exception:
            team_odds_map = {}

        for f in fixtures_raw:
            f_id = f["id"]
            h_short = teams_map.get(f["team_h"], f"T{f['team_h']}")
            a_short = teams_map.get(f["team_a"], f"T{f['team_a']}")
            h_score = f.get("team_h_score")
            a_score = f.get("team_a_score")
            started = f.get("started", False)
            finished = f.get("finished", False)
            m_mins = f.get("minutes", 0)
            ko = f.get("kickoff_time", "")

            m_day = "Saturday"
            m_date_str = ""
            m_time_str = ""

            if finished:
                status_lbl = "FT"
            elif started:
                status_lbl = f"LIVE {m_mins}'"
            else:
                status_lbl = "UPCOMING"

            if ko:
                try:
                    clean_ko = ko.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(clean_ko)
                    if ZoneInfo is not None:
                        try:
                            dt = dt.astimezone(ZoneInfo("Europe/London"))
                        except Exception:
                            pass
                    m_day = dt.strftime("%A")
                    m_date_str = dt.strftime("%d %b %Y")
                    m_time_str = dt.strftime("%H:%M")
                    if not finished and not started:
                        status_lbl = dt.strftime("%a %H:%M")
                except Exception:
                    m_time_str = ko[11:16] if len(ko) >= 16 else "UPCOMING"
                    if not finished and not started:
                        status_lbl = m_time_str

            h_squad = players_by_fixture_home.get(f_id, [])
            a_squad = players_by_fixture_away.get(f_id, [])
            has_squad = (len(h_squad) + len(a_squad)) > 0

            # Compute Poisson match outcome prediction
            pred = calculate_fixture_prediction(
                h_short=h_short,
                a_short=a_short,
                gameweek=gameweek,
                team_odds_map=team_odds_map
            )

            # Query weather observation from WeatherClient
            obs = self.weather_client.get_fixture_weather(
                home_club=h_short,
                kickoff_iso=ko,
                fixture_id=f_id,
                is_finished=finished,
                force_refresh=force_refresh
            )

            w_badge = f'<span title="{obs.condition_label} • Wind: {obs.wind_speed_kmh}km/h (Eff: {obs.effective_wind_kmh}km/h) • Rain: {obs.precipitation_mm}mm" style="background: rgba(255,255,255,0.08); padding: 2px 7px; border-radius: 6px; font-size: 11px; margin-left: 6px; font-weight: 500;">{obs.condition_icon} {obs.temperature_c:.0f}°C • {obs.effective_wind_kmh:.0f} km/h</span>'
            if obs.is_adverse and obs.hazard_alert:
                w_badge += f' <span title="{obs.hazard_alert}" style="background: #7f1d1d; color: #fca5a5; padding: 2px 6px; border-radius: 6px; font-size: 10px; font-weight: 700;">⚠️ HAZARD</span>'

            if has_squad and obs.is_adverse:
                adverse_count += 1
                if obs.hazard_alert:
                    squad_weather_alerts.append(f"{h_short} vs {a_short}: {obs.hazard_alert}")

            matchday_fixtures.append(MatchdayFixture(
                fixture_id=f_id,
                home_short=h_short,
                away_short=a_short,
                home_score=h_score,
                away_score=a_score,
                started=started,
                finished=finished,
                minutes=m_mins,
                kickoff_time=ko,
                status_label=status_lbl,
                has_squad_player=has_squad,
                home_squad_players=h_squad,
                away_squad_players=a_squad,
                weather=obs,
                weather_badge_html=w_badge,
                match_day=m_day,
                match_date_str=m_date_str,
                match_time_str=m_time_str,
                prediction=pred
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
            bench=bench,
            adverse_weather_count=adverse_count,
            squad_weather_alerts=squad_weather_alerts
        )

    def get_mini_league_scoreboard(
        self,
        league_id: Optional[int] = None,
        gameweek: Optional[int] = None,
        max_teams: int = 25,
        force_refresh: bool = False
    ) -> MiniLeagueScoreboard:
        """
        Builds the Live Gameweek Mini-League Scoreboard with Day-of-Week points progression,
        played/in-play counts, captain returns, hits, and projected final finishes.
        """
        target_league_id = int(league_id or DEFAULT_LEAGUE_ID)

        # 1. Determine active gameweek
        if gameweek is None:
            gameweek = self.fpl_client.get_current_gameweek() or 4

        # 2. Fetch fixtures and map fixture ID to kickoff day of week
        fixtures = self.fpl_client.get_gameweek_fixtures(gameweek=gameweek)
        fixture_day_map: Dict[int, str] = {}
        day_first_ko: Dict[str, datetime] = {}
        fixture_status_map: Dict[int, Dict[str, Any]] = {}
        team_fixtures_map: Dict[int, List[int]] = {}

        for f in fixtures:
            f_id = f.get("id")
            ko = f.get("kickoff_time")
            team_h = f.get("team_h")
            team_a = f.get("team_a")
            if team_h and f_id:
                team_fixtures_map.setdefault(team_h, []).append(f_id)
            if team_a and f_id:
                team_fixtures_map.setdefault(team_a, []).append(f_id)

            day_name = "Saturday"
            if ko:
                try:
                    dt = datetime.fromisoformat(ko.replace("Z", "+00:00"))
                    day_name = dt.strftime("%A")
                    if day_name not in day_first_ko or dt < day_first_ko[day_name]:
                        day_first_ko[day_name] = dt
                except Exception:
                    pass

            if f_id:
                fixture_day_map[f_id] = day_name
                fixture_status_map[f_id] = {
                    "started": f.get("started", False),
                    "finished": f.get("finished", False),
                    "minutes": f.get("minutes", 0),
                    "day": day_name,
                    "team_h": team_h,
                    "team_a": team_a
                }

        # Chronologically ordered active days
        days_order = ["Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
        if day_first_ko:
            active_days = sorted(day_first_ko.keys(), key=lambda d: day_first_ko[d])
        else:
            unique_days = set(fixture_day_map.values())
            active_days = [d for d in days_order if d in unique_days] or ["Saturday", "Sunday"]

        # 3. Fetch live scoring events
        live_raw = self.fpl_client.get_gameweek_live(gameweek=gameweek)
        live_elements: Dict[int, Dict[str, Any]] = {}
        for el in live_raw.get("elements", []):
            el_id = el.get("id")
            stats = el.get("stats", {})
            explain = el.get("explain", [])
            f_pts: Dict[int, int] = {}
            for exp in explain:
                fid = exp.get("fixture")
                pts = sum(s.get("points", 0) for s in exp.get("stats", []))
                f_pts[fid] = pts

            live_elements[el_id] = {
                "total_points": stats.get("total_points", 0),
                "minutes": stats.get("minutes", 0),
                "goals": stats.get("goals_scored", 0),
                "assists": stats.get("assists", 0),
                "clean_sheets": stats.get("clean_sheets", 0),
                "bps": stats.get("bps", 0),
                "bonus": stats.get("bonus", 0),
                "fixture_pts": f_pts
            }

        # 4. Bootstrap data for club names and baseline xP
        boot = self.fpl_client.get_bootstrap_data()
        teams_short = {t["id"]: t["short_name"] for t in boot.get("teams", [])}
        element_team_map = {el["id"]: el.get("team") for el in boot.get("elements", [])}
        element_xp_map = {el["id"]: float(el.get("ep_this") or el.get("points_per_game") or 4.0) for el in boot.get("elements", [])}

        # 5. Fetch league standings
        standings = self.league_tracker.get_league_standings(target_league_id, max_teams=max_teams)
        league_name = standings.get("league_name", "FPL Mini-League")
        teams_list = standings.get("teams", [])

        # 6. Process each member's squad
        members: List[MemberDayScore] = []
        top_captains_counter: Dict[str, int] = {}

        for t in teams_list:
            e_id = t["entry_id"]
            try:
                picks_data = self.league_tracker.get_team_picks(e_id, gameweek=gameweek)
            except Exception:
                continue

            starters = picks_data.get("starters", [])
            bench = picks_data.get("bench", [])
            transfer_cost = int(picks_data.get("transfer_cost") or 0)
            active_chip = picks_data.get("active_chip")

            # Captaincy info
            cap_obj = picks_data.get("captain")
            cap_name = cap_obj.get("web_name", "Unknown") if cap_obj else "Unknown"
            cap_id = cap_obj.get("id") if cap_obj else None
            cap_mult = cap_obj.get("multiplier", 2) if cap_obj else 2
            cap_day = "Upcoming"
            cap_effective_pts = 0

            top_captains_counter[cap_name] = top_captains_counter.get(cap_name, 0) + 1

            day_points = {d: 0 for d in active_days}
            played_count = 0
            playing_count = 0
            to_play_count = 0
            remaining_players: List[Dict[str, Any]] = []

            for p in starters:
                p_id = p["id"]
                p_mult = p.get("multiplier", 1)
                p_live = live_elements.get(p_id, {"fixture_pts": {}, "minutes": 0, "total_points": 0})
                p_team_id = element_team_map.get(p_id)
                p_xp = element_xp_map.get(p_id, 4.0)

                p_fixtures = list(p_live["fixture_pts"].keys())
                if not p_fixtures and p_team_id:
                    p_fixtures = team_fixtures_map.get(p_team_id, [])

                has_started = False
                has_finished = False
                p_day = active_days[0] if active_days else "Saturday"

                if p_fixtures:
                    f_info = fixture_status_map.get(p_fixtures[0], {})
                    has_started = f_info.get("started", False)
                    has_finished = f_info.get("finished", False)
                    p_day = f_info.get("day", p_day)

                if p_live["minutes"] > 0:
                    if has_finished:
                        played_count += 1
                    else:
                        playing_count += 1
                elif has_finished:
                    played_count += 1
                elif has_started:
                    playing_count += 1
                else:
                    to_play_count += 1
                    opp_short = "UNK"
                    if p_fixtures:
                        f_info = fixture_status_map.get(p_fixtures[0], {})
                        h_team = f_info.get("team_h")
                        a_team = f_info.get("team_a")
                        is_home = (p_team_id == h_team)
                        opp_id = a_team if is_home else h_team
                        opp_short = teams_short.get(opp_id, "UNK")

                    remaining_players.append({
                        "name": p.get("web_name", f"Player {p_id}"),
                        "club": p.get("club", "UNK"),
                        "pos": p.get("pos", "MID"),
                        "opp": opp_short,
                        "day": p_day,
                        "xp": round(p_xp, 1)
                    })

                # Day points calculation
                if p_live["fixture_pts"]:
                    for fid, pts in p_live["fixture_pts"].items():
                        d_name = fixture_day_map.get(fid, p_day)
                        if d_name in day_points:
                            day_points[d_name] += (pts * p_mult)
                else:
                    if p_day in day_points:
                        day_points[p_day] += (p_live["total_points"] * p_mult)

                # Captain tracking
                if p_id == cap_id:
                    cap_day = p_day
                    cap_effective_pts = p_live["total_points"] * cap_mult

            # Cumulative day-of-week points
            cum = 0
            cumulative_day_points = {}
            for d in active_days:
                cum += day_points[d]
                cumulative_day_points[d] = cum

            live_gw = sum(day_points.values())
            net_gw = live_gw - transfer_cost
            remaining_xp_sum = sum(rem["xp"] for rem in remaining_players)
            projected_final = round(live_gw + remaining_xp_sum - transfer_cost, 1)

            # Check potential auto-subs
            auto_subs_pending = []
            for s in starters:
                s_id = s["id"]
                s_live = live_elements.get(s_id, {"minutes": 0, "total_points": 0})
                s_team = element_team_map.get(s_id)
                s_fix = team_fixtures_map.get(s_team, [])
                s_finished = any(fixture_status_map.get(fid, {}).get("finished", False) for fid in s_fix)
                if s_live["minutes"] == 0 and s_finished:
                    for b in bench:
                        b_id = b["id"]
                        b_live = live_elements.get(b_id, {"minutes": 0, "total_points": 0})
                        if b_live["minutes"] > 0:
                            auto_subs_pending.append({
                                "sub_out": s.get("web_name"),
                                "sub_in": b.get("web_name"),
                                "points": b_live["total_points"]
                            })
                            break

            members.append(MemberDayScore(
                entry_id=e_id,
                team_name=t["team_name"],
                manager_name=t["manager_name"],
                rank=t["rank"],
                last_rank=t.get("last_rank", t["rank"]),
                captain_name=cap_name,
                captain_multiplier=cap_mult,
                captain_points=cap_effective_pts,
                captain_day=cap_day,
                active_chip=active_chip,
                transfer_cost=transfer_cost,
                starters_played=played_count,
                starters_playing=playing_count,
                starters_to_play=to_play_count,
                day_points=day_points,
                cumulative_day_points=cumulative_day_points,
                live_gw_points=live_gw,
                net_gw_points=net_gw,
                projected_final_points=projected_final,
                total_league_points=t.get("total_points", 0),
                remaining_players=remaining_players,
                auto_subs_pending=auto_subs_pending
            ))

        # Sort members by Net GW Points descending, then by mini-league rank
        members.sort(key=lambda m: (-m.net_gw_points, m.rank))

        # Compute Highest Day Scorers
        highest_day_scorers: Dict[str, Dict[str, Any]] = {}
        for d in active_days:
            best_m = max(members, key=lambda m: m.day_points.get(d, 0), default=None)
            if best_m and best_m.day_points.get(d, 0) > 0:
                highest_day_scorers[d] = {
                    "team": best_m.team_name,
                    "manager": best_m.manager_name,
                    "points": best_m.day_points[d]
                }

        avg_live = round(sum(m.live_gw_points for m in members) / max(1, len(members)), 1)
        avg_net = round(sum(m.net_gw_points for m in members) / max(1, len(members)), 1)

        return MiniLeagueScoreboard(
            league_id=target_league_id,
            league_name=league_name,
            gameweek=gameweek,
            active_days=active_days,
            members=members,
            highest_day_scorers=highest_day_scorers,
            top_captains=top_captains_counter,
            league_avg_live_points=avg_live,
            league_avg_net_points=avg_net
        )
