"""
Weather & Seasonality Analytical Engine for Rubies Rangers
Translates physical meteorological observations and fixture congestion into
statistically validated expected point (xP) multipliers and squad risk models.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from clients.weather_client import WeatherClient, WeatherObservation
from clients.fpl_client import FPLClient
from config_manager import get_system_config, get_params


@dataclass(frozen=True)
class PlayerWeatherReport:
    """Detailed environmental and rest profile for a player in a specific gameweek."""
    player_id: int
    web_name: str
    club_short: str
    position: str
    role: str
    opponent_short: str
    is_home: bool
    kickoff_time: str
    status_label: str
    weather: WeatherObservation
    rest_days: float
    is_short_rest: bool
    weather_dampener: float      # Phi_weather
    congestion_multiplier: float # Omega_season
    combined_multiplier: float   # Phi * Omega
    risk_level: str              # 'LOW', 'MODERATE', 'HIGH', 'SEVERE'
    tactical_note: str


class WeatherEngine:
    """
    Evaluates meteorological dampeners, turnaround fatigue, and squad exposure
    for Rubies Rangers operations.
    """

    def __init__(self, weather_client: Optional[WeatherClient] = None, fpl_client: Optional[FPLClient] = None):
        self.weather_client = weather_client or WeatherClient()
        self.fpl_client = fpl_client or FPLClient()

    def compute_weather_dampener(
        self,
        weather: WeatherObservation,
        position: str = "MID"
    ) -> float:
        """
        Computes the environmental expected points multiplier (Phi_weather).
        - High wind (> 20 km/h) dampens attacking returns (outside box shots & crossing).
        - Rain (> 3 mm/h) slick pitch introduces variance & foul friction.
        - Sub-zero cold (<= 0°C) introduces soft-tissue early-substitution risk.
        - GKP/DEF receive less wind penalty as low-scoring 0-0 clean sheet probability mass expands.
        """
        w_cfg = get_params("weather") or {}
        if not w_cfg.get("enabled", True):
            return 1.00

        beta_wind = float(w_cfg.get("beta_wind", 0.008))
        beta_rain = float(w_cfg.get("beta_rain", 0.025))
        max_damp = float(w_cfg.get("max_dampener", 0.25))

        eff_wind = weather.effective_wind_kmh
        wind_excess = max(0.0, eff_wind - 20.0)
        rain_excess = max(0.0, weather.precipitation_mm - 0.5)

        # Baseline raw penalty
        penalty = (beta_wind * wind_excess) + (beta_rain * rain_excess)

        # Cold penalty for soft-tissue early substitution risk
        if weather.temperature_c <= 0.0:
            penalty += 0.05
        elif weather.temperature_c <= 3.0:
            penalty += 0.02

        # Position-specific elasticity:
        # GKP and DEF benefit from depressed attacking output (higher Clean Sheet mass)
        if position in ("DEF", "GKP"):
            penalty = penalty * 0.40  # 60% attenuation for defenders/goalkeepers

        penalty = min(max_damp, max(0.0, penalty))
        return round(1.0 - penalty, 3)

    def compute_congestion_multiplier(
        self,
        rest_days: float,
        age: int = 26
    ) -> float:
        """
        Computes the calendar congestion multiplier (Omega_season).
        - Rest <= 2 days (48h turnaround): severe rotation and fatigue risk.
        - Rest <= 3 days (72h turnaround): moderate rotation risk.
        - Veteran age (>= 31) amplifies rotation probability by 1.5x.
        """
        s_cfg = get_params("seasonality") or {}
        if not s_cfg.get("enabled", True):
            return 1.00

        alpha = float(s_cfg.get("alpha_congestion", 0.08))
        vet_mult = float(s_cfg.get("veteran_multiplier", 1.5))
        is_vet = (age >= int(s_cfg.get("veteran_age_threshold", 31)))

        age_factor = vet_mult if is_vet else 1.0

        if rest_days <= 2.1:
            penalty = alpha * 1.6 * age_factor
        elif rest_days <= 3.1:
            penalty = alpha * 1.0 * age_factor
        else:
            penalty = 0.0

        penalty = min(0.30, max(0.0, penalty))
        return round(1.0 - penalty, 3)

    def calculate_fixture_rest_days(
        self,
        club_short: str,
        current_kickoff_iso: str,
        all_fixtures: List[Dict[str, Any]],
        team_id_map: Dict[int, str]
    ) -> float:
        """Calculates days elapsed since the club's previous official fixture."""
        if not current_kickoff_iso:
            return 7.0

        try:
            curr_clean = current_kickoff_iso.replace("Z", "+00:00")
            curr_dt = datetime.fromisoformat(curr_clean)
        except Exception:
            return 7.0

        # Find previous fixture for this club
        prev_kickoffs = []
        for f in all_fixtures:
            h_short = team_id_map.get(f.get("team_h", -1), "")
            a_short = team_id_map.get(f.get("team_a", -1), "")
            if club_short in (h_short, a_short):
                ko = f.get("kickoff_time")
                if ko:
                    try:
                        f_dt = datetime.fromisoformat(ko.replace("Z", "+00:00"))
                        if f_dt < curr_dt:
                            prev_kickoffs.append(f_dt)
                    except Exception:
                        pass

        if not prev_kickoffs:
            return 7.0

        last_ko = max(prev_kickoffs)
        diff_days = (curr_dt - last_ko).total_seconds() / 86400.0
        return round(max(1.0, diff_days), 1)

    def get_squad_weather_forecast(
        self,
        squad_names: List[str],
        gameweek: int
    ) -> List[PlayerWeatherReport]:
        """
        Builds a comprehensive environmental forecast for all players in the active squad
        for the given gameweek.
        """
        boot = self.fpl_client.get_bootstrap_data()
        elements = boot.get("elements", [])
        teams = boot.get("teams", [])
        team_id_map = {t["id"]: t["short_name"] for t in teams}

        # Fetch target gameweek fixtures (using get_gameweek_fixtures with fallback)
        gw_fixtures = self.fpl_client.get_gameweek_fixtures(gameweek)
        if not gw_fixtures:
            all_fix = self.fpl_client.get_fixtures_data()
            gw_fixtures = [f for f in all_fix if f.get("event") == gameweek]
        else:
            all_fix = self.fpl_client.get_fixtures_data()
        fixtures = all_fix

        fixture_map_by_team: Dict[str, Dict[str, Any]] = {}
        for f in gw_fixtures:
            h_short = team_id_map.get(f["team_h"], "")
            a_short = team_id_map.get(f["team_a"], "")
            if h_short:
                fixture_map_by_team[h_short] = {"fixture": f, "is_home": True, "opponent": a_short}
            if a_short:
                fixture_map_by_team[a_short] = {"fixture": f, "is_home": False, "opponent": h_short}

        # Build name lookup
        name_lower_map = {}
        for el in elements:
            name_lower_map[el["web_name"].lower()] = el
            full = f"{el.get('first_name', '')} {el.get('second_name', '')}".strip().lower()
            name_lower_map[full] = el

        reports: List[PlayerWeatherReport] = []

        for name in squad_names:
            el = name_lower_map.get(name.lower())
            if not el:
                continue

            club_short = team_id_map.get(el["team"], "UNK")
            pos_id = el.get("element_type", 3)
            pos = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}.get(pos_id, "MID")
            age = 27  # Default age if unavailable

            fix_info = fixture_map_by_team.get(club_short)
            if not fix_info:
                # Blank Gameweek
                obs = self.weather_client._build_fallback_observation(1.00)
                reports.append(PlayerWeatherReport(
                    player_id=el["id"],
                    web_name=el["web_name"],
                    club_short=club_short,
                    position=pos,
                    role="START",
                    opponent_short="BLANK",
                    is_home=True,
                    kickoff_time="",
                    status_label="NO FIXTURE",
                    weather=obs,
                    rest_days=7.0,
                    is_short_rest=False,
                    weather_dampener=1.00,
                    congestion_multiplier=1.00,
                    combined_multiplier=1.00,
                    risk_level="LOW",
                    tactical_note="Blank Gameweek — No physical match scheduled."
                ))
                continue

            raw_f = fix_info["fixture"]
            is_home = fix_info["is_home"]
            opp_short = fix_info["opponent"]
            home_club = club_short if is_home else opp_short
            ko_time = raw_f.get("kickoff_time", "")
            f_id = raw_f.get("id")
            finished = raw_f.get("finished", False)

            # Weather observation at host stadium
            obs = self.weather_client.get_fixture_weather(
                home_club=home_club,
                kickoff_iso=ko_time,
                fixture_id=f_id,
                is_finished=finished
            )

            # Rest days
            rest_days = self.calculate_fixture_rest_days(club_short, ko_time, fixtures, team_id_map)
            is_short_rest = (rest_days <= 3.1)

            # Multipliers
            phi = self.compute_weather_dampener(obs, position=pos)
            omega = self.compute_congestion_multiplier(rest_days, age=age)
            combined = round(phi * omega, 3)

            # Risk Rating & Tactical Note
            risk_level = "LOW"
            notes = []

            if obs.effective_wind_kmh >= 30.0:
                risk_level = "SEVERE" if combined < 0.85 else "HIGH"
                notes.append(f"Gale wind ({obs.effective_wind_kmh:.0f} km/h) disrupts long-range xG")
            elif obs.effective_wind_kmh >= 22.0:
                if risk_level != "SEVERE":
                    risk_level = "MODERATE"
                notes.append(f"Breezy pitch ({obs.effective_wind_kmh:.0f} km/h)")

            if obs.precipitation_mm >= 3.0:
                if risk_level not in ("SEVERE", "HIGH"):
                    risk_level = "MODERATE"
                notes.append(f"Heavy rain ({obs.precipitation_mm:.1f} mm/h) creates greasy turf")

            if obs.temperature_c <= 0.0:
                if risk_level != "SEVERE":
                    risk_level = "HIGH"
                notes.append(f"Freezing cold ({obs.temperature_c:.1f}°C) elevates muscle tear risk")

            if is_short_rest:
                if risk_level != "SEVERE":
                    risk_level = "HIGH" if rest_days <= 2.1 else "MODERATE"
                notes.append(f"Short turnaround ({rest_days:.1f} days rest)")

            if not notes:
                tactical_note = "Optimal benign playing conditions."
            else:
                tactical_note = " • ".join(notes)

            # Format status label
            try:
                dt = datetime.fromisoformat(ko_time.replace("Z", "+00:00"))
                status_lbl = dt.strftime("%a %H:%M")
            except Exception:
                status_lbl = "UPCOMING"

            reports.append(PlayerWeatherReport(
                player_id=el["id"],
                web_name=el["web_name"],
                club_short=club_short,
                position=pos,
                role="START",
                opponent_short=opp_short,
                is_home=is_home,
                kickoff_time=ko_time,
                status_label=status_lbl,
                weather=obs,
                rest_days=rest_days,
                is_short_rest=is_short_rest,
                weather_dampener=phi,
                congestion_multiplier=omega,
                combined_multiplier=combined,
                risk_level=risk_level,
                tactical_note=tactical_note
            ))

        return reports

    def get_gameweek_radar(self, gameweek: int) -> List[Dict[str, Any]]:
        """Compiles meteorological radar summaries for all fixtures in a gameweek."""
        boot = self.fpl_client.get_bootstrap_data()
        teams = boot.get("teams", [])
        team_id_map = {t["id"]: t["short_name"] for t in teams}

        gw_fixtures = self.fpl_client.get_gameweek_fixtures(gameweek)
        if not gw_fixtures:
            all_fix = self.fpl_client.get_fixtures_data()
            gw_fixtures = [f for f in all_fix if f.get("event") == gameweek]
        else:
            all_fix = self.fpl_client.get_fixtures_data()
        fixtures = all_fix

        radar_items: List[Dict[str, Any]] = []

        for f in gw_fixtures:
            h_short = team_id_map.get(f["team_h"], "UNK")
            a_short = team_id_map.get(f["team_a"], "UNK")
            ko = f.get("kickoff_time", "")
            f_id = f.get("id")
            finished = f.get("finished", False)

            obs = self.weather_client.get_fixture_weather(
                home_club=h_short,
                kickoff_iso=ko,
                fixture_id=f_id,
                is_finished=finished
            )

            h_rest = self.calculate_fixture_rest_days(h_short, ko, fixtures, team_id_map)
            a_rest = self.calculate_fixture_rest_days(a_short, ko, fixtures, team_id_map)

            try:
                dt = datetime.fromisoformat(ko.replace("Z", "+00:00"))
                day_time = dt.strftime("%a %H:%M")
            except Exception:
                day_time = "TBD"

            radar_items.append({
                "fixture_id": f_id,
                "home_short": h_short,
                "away_short": a_short,
                "match_label": f"{h_short} vs {a_short}",
                "day_time": day_time,
                "kickoff_time": ko,
                "weather": obs,
                "home_rest_days": h_rest,
                "away_rest_days": a_rest,
                "stadium_name": self.weather_client.get_stadium_meta(h_short).get("name", "Stadium"),
                "stadium_type": self.weather_client.get_stadium_meta(h_short).get("type", "URBAN_OPEN")
            })

        return radar_items
