"""
Open-Meteo Weather Client for Rubies Rangers
Fetches, caches, and persists high-resolution meteorological forecasts and historical weather data
for all Premier League stadiums using open-source, free Open-Meteo APIs.
"""

import os
import json
import logging
import urllib.request
import urllib.parse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List

from config_manager import get_system_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stadium GPS Registry & Architectural Micro-Climate Exposure Factors
# Exposure Factor:
#   > 1.10: Exposed coastal or elevated grounds (Bournemouth, Brighton, Newcastle, Sunderland)
#   ~ 1.00: Standard urban / open municipal venues
#   < 0.85: Sheltered covered modern bowls (Arsenal Emirates, Tottenham Hotspur Stadium)
# ---------------------------------------------------------------------------
PL_STADIUM_CATALOG: Dict[str, Dict[str, Any]] = {
    "ARS": {"name": "Emirates Stadium", "city": "London", "lat": 51.5549, "lon": -0.1084, "exposure": 0.70, "type": "COVERED_BOWL"},
    "AVL": {"name": "Villa Park", "city": "Birmingham", "lat": 52.5091, "lon": -1.8848, "exposure": 1.00, "type": "URBAN_OPEN"},
    "BOU": {"name": "Vitality Stadium", "city": "Bournemouth", "lat": 50.7352, "lon": -1.8384, "exposure": 1.25, "type": "COASTAL_EXPOSED"},
    "BRE": {"name": "Gtech Community Stadium", "city": "London", "lat": 51.4907, "lon": -0.2891, "exposure": 0.95, "type": "URBAN_OPEN"},
    "BHA": {"name": "Amex Stadium", "city": "Brighton", "lat": 50.8616, "lon": -0.0837, "exposure": 1.20, "type": "COASTAL_EXPOSED"},
    "CHE": {"name": "Stamford Bridge", "city": "London", "lat": 51.4816, "lon": -0.1910, "exposure": 0.85, "type": "URBAN_OPEN"},
    "COV": {"name": "Coventry Arena", "city": "Coventry", "lat": 52.4481, "lon": -1.4956, "exposure": 1.00, "type": "URBAN_OPEN"},
    "CRY": {"name": "Selhurst Park", "city": "London", "lat": 51.3983, "lon": -0.0855, "exposure": 0.95, "type": "URBAN_OPEN"},
    "EVE": {"name": "Goodison Park", "city": "Liverpool", "lat": 53.4388, "lon": -2.9664, "exposure": 1.20, "type": "COASTAL_EXPOSED"},
    "FUL": {"name": "Craven Cottage", "city": "London", "lat": 51.4749, "lon": -0.2217, "exposure": 1.05, "type": "RIVERSIDE_EXPOSED"},
    "HUL": {"name": "MKM Stadium", "city": "Hull", "lat": 53.7461, "lon": -0.3678, "exposure": 1.15, "type": "ESTUARY_EXPOSED"},
    "IPS": {"name": "Portman Road", "city": "Ipswich", "lat": 52.0556, "lon": 1.1444, "exposure": 1.05, "type": "URBAN_OPEN"},
    "LEE": {"name": "Elland Road", "city": "Leeds", "lat": 53.7778, "lon": -1.5722, "exposure": 1.05, "type": "URBAN_OPEN"},
    "LIV": {"name": "Anfield", "city": "Liverpool", "lat": 53.4308, "lon": -2.9608, "exposure": 1.05, "type": "URBAN_OPEN"},
    "MCI": {"name": "Etihad Stadium", "city": "Manchester", "lat": 53.4831, "lon": -2.2004, "exposure": 0.80, "type": "COVERED_BOWL"},
    "MUN": {"name": "Old Trafford", "city": "Manchester", "lat": 53.4631, "lon": -2.2913, "exposure": 0.85, "type": "COVERED_BOWL"},
    "NEW": {"name": "St James' Park", "city": "Newcastle", "lat": 54.9756, "lon": -1.6217, "exposure": 1.20, "type": "HILL_COASTAL_EXPOSED"},
    "NFO": {"name": "City Ground", "city": "Nottingham", "lat": 52.9400, "lon": -1.1328, "exposure": 1.00, "type": "RIVERSIDE_OPEN"},
    "TOT": {"name": "Tottenham Hotspur Stadium", "city": "London", "lat": 51.6043, "lon": -0.0664, "exposure": 0.70, "type": "COVERED_BOWL"},
    "SUN": {"name": "Stadium of Light", "city": "Sunderland", "lat": 54.9144, "lon": -1.3883, "exposure": 1.25, "type": "COASTAL_EXPOSED"},
    "SOU": {"name": "St Mary's Stadium", "city": "Southampton", "lat": 50.9058, "lon": -1.3911, "exposure": 1.20, "type": "COASTAL_EXPOSED"},
    "WHU": {"name": "London Stadium", "city": "London", "lat": 51.5387, "lon": -0.0166, "exposure": 1.10, "type": "OPEN_BOWL"},
    "WOL": {"name": "Molineux Stadium", "city": "Wolverhampton", "lat": 52.5902, "lon": -2.1304, "exposure": 1.00, "type": "URBAN_OPEN"},
    "LEI": {"name": "King Power Stadium", "city": "Leicester", "lat": 52.6203, "lon": -1.1422, "exposure": 1.00, "type": "URBAN_OPEN"},
}


@dataclass(frozen=True)
class WeatherObservation:
    """Immutable meteorological state captured for a specific stadium and kickoff hour."""
    temperature_c: float
    wind_speed_kmh: float
    wind_gusts_kmh: float
    precipitation_mm: float
    relative_humidity: float
    condition_code: int
    condition_label: str
    condition_icon: str
    is_adverse: bool
    hazard_alert: Optional[str]
    exposure_factor: float
    effective_wind_kmh: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeatherObservation":
        return cls(**data)


def _wmo_code_to_meta(code: int, wind_speed: float) -> Tuple[str, str]:
    """Translates WMO weather code and wind speed to icon and human-readable label."""
    if wind_speed >= 35.0:
        return "💨", f"Gale Force Wind ({wind_speed:.0f} km/h)"
    if code == 0:
        return "☀️", "Clear Sky"
    elif code in (1, 2):
        return "⛅", "Partly Cloudy"
    elif code == 3:
        return "☁️", "Overcast"
    elif code in (45, 48):
        return "🌫️", "Foggy Conditions"
    elif code in (51, 53, 55):
        return "🌦️", "Light Drizzle"
    elif code in (61, 63):
        return "🌧️", "Rain"
    elif code == 65:
        return "🌧️", "Heavy Rain"
    elif code in (71, 73, 75, 77):
        return "❄️", "Snow / Sleet"
    elif code in (80, 81, 82):
        return "🌧️", "Rain Showers"
    elif code in (95, 96, 99):
        return "⛈️", "Thunderstorm"
    elif wind_speed >= 25.0:
        return "💨", f"Breezy & Wind ({wind_speed:.0f} km/h)"
    return "⛅", "Cloudy & Moderate"


class WeatherClient:
    """
    Coordinates weather forecast fetching, persistent storage of historic matchday weather,
    and rolling forward forecast caching for Rubies Rangers.
    """

    def __init__(self, cache_file: Optional[str] = None):
        cfg = get_system_config("weather") or {}
        default_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "weather_store.json")
        self.cache_path = cache_file or cfg.get("cache_file", default_file)
        self.cache_ttl_hours = cfg.get("cache_ttl_hours", 6)
        self.store = self._load_store()

    def _load_store(self) -> Dict[str, Any]:
        """Loads persistent JSON weather store from disk."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load weather store from {self.cache_path}: {e}")
        return {"historical": {}, "forecasts": {}}

    def _save_store(self) -> None:
        """Persists the updated weather cache to disk."""
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.store, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist weather store to {self.cache_path}: {e}")

    def get_stadium_meta(self, club_short: str) -> Dict[str, Any]:
        """Returns catalog coordinates and exposure factors for a club."""
        club = club_short.upper()
        return PL_STADIUM_CATALOG.get(club, {
            "name": f"{club} Stadium",
            "city": "UK",
            "lat": 51.5074,
            "lon": -0.1278,
            "exposure": 1.00,
            "type": "URBAN_OPEN"
        })

    def fetch_open_meteo(self, lat: float, lon: float, past_days: int = 7, forecast_days: int = 14) -> Optional[Dict[str, Any]]:
        """
        Executes an HTTP GET query against Open-Meteo forecast endpoint.
        Returns parsed JSON dict or None on failure.
        """
        base_url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,weather_code",
            "past_days": str(past_days),
            "forecast_days": str(forecast_days),
            "timezone": "auto"
        }
        query_str = urllib.parse.urlencode(params)
        req_url = f"{base_url}?{query_str}"

        try:
            req = urllib.request.Request(
                req_url,
                headers={"User-Agent": "RubiesRangers-FPL/1.0 (Quantitative Moneyball Engine)"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Open-Meteo query failed for ({lat}, {lon}): {e}")
        return None

    def get_fixture_weather(
        self,
        home_club: str,
        kickoff_iso: str,
        fixture_id: Optional[int] = None,
        is_finished: bool = False,
        force_refresh: bool = False
    ) -> WeatherObservation:
        """
        Retrieves the exact WeatherObservation for a fixture:
        1. If match is finished and in historical cache -> returns immediately.
        2. If in forecast cache and fresh (< 6h) -> returns matched kickoff hour.
        3. Otherwise queries Open-Meteo, updates cache, and returns observation.
        4. Gracefully falls back to climatic baseline if offline.
        """
        home_club = home_club.upper()
        fix_key = str(fixture_id) if fixture_id is not None else f"{home_club}_{kickoff_iso}"

        # 1. Historical Permanent Cache Hit
        if not force_refresh and fix_key in self.store.get("historical", {}):
            try:
                return WeatherObservation.from_dict(self.store["historical"][fix_key])
            except Exception:
                pass

        # 2. Check Forecast Cache
        meta = self.get_stadium_meta(home_club)
        cached_fc = self.store.get("forecasts", {}).get(home_club)
        now_utc = datetime.now(timezone.utc)
        cache_valid = False

        if not force_refresh and cached_fc:
            try:
                fetched_dt = datetime.fromisoformat(cached_fc["fetched_at"])
                if (now_utc - fetched_dt) < timedelta(hours=self.cache_ttl_hours):
                    cache_valid = True
            except Exception:
                cache_valid = False

        # 3. Fetch from API if cache invalid or missing
        if not cache_valid:
            api_data = self.fetch_open_meteo(meta["lat"], meta["lon"], past_days=7, forecast_days=14)
            if api_data and "hourly" in api_data:
                self.store.setdefault("forecasts", {})[home_club] = {
                    "fetched_at": now_utc.isoformat(),
                    "hourly": api_data["hourly"]
                }
                self._save_store()
                cached_fc = self.store["forecasts"][home_club]

        # 4. Match Kickoff Hour from cached data
        obs = self._extract_observation_at_kickoff(home_club, meta, cached_fc, kickoff_iso)

        # 5. If fixture is finished, permanently record in historical
        if is_finished:
            self.store.setdefault("historical", {})[fix_key] = obs.to_dict()
            self._save_store()

        return obs

    def _extract_observation_at_kickoff(
        self,
        home_club: str,
        meta: Dict[str, Any],
        cached_fc: Optional[Dict[str, Any]],
        kickoff_iso: str
    ) -> WeatherObservation:
        """Finds closest hourly slot in cached forecast array and formats WeatherObservation."""
        exposure = float(meta.get("exposure", 1.00))

        if not cached_fc or "hourly" not in cached_fc:
            return self._build_fallback_observation(exposure)

        hourly = cached_fc["hourly"]
        times = hourly.get("time", [])
        if not times:
            return self._build_fallback_observation(exposure)

        # Parse target kickoff time (e.g. 2026-09-13T15:00)
        target_str = kickoff_iso[:13] if len(kickoff_iso) >= 13 else ""
        idx = 0
        best_diff = 999999

        try:
            # Clean kickoff string
            clean_ko = kickoff_iso.replace("Z", "+00:00")
            ko_dt = datetime.fromisoformat(clean_ko)
            if ko_dt.tzinfo is not None:
                ko_dt = ko_dt.astimezone(timezone.utc).replace(tzinfo=None)

            for i, t_str in enumerate(times):
                t_dt = datetime.fromisoformat(t_str)
                diff = abs((ko_dt - t_dt).total_seconds())
                if diff < best_diff:
                    best_diff = diff
                    idx = i
        except Exception:
            # Fallback to prefix match
            for i, t_str in enumerate(times):
                if target_str and t_str.startswith(target_str):
                    idx = i
                    break

        temp_c = float(hourly.get("temperature_2m", [15.0])[idx])
        wind_kmh = float(hourly.get("wind_speed_10m", [12.0])[idx])
        gusts_kmh = float(hourly.get("wind_gusts_10m", [wind_kmh * 1.3])[idx])
        precip_mm = float(hourly.get("precipitation", [0.0])[idx])
        humidity = float(hourly.get("relative_humidity_2m", [70.0])[idx])
        w_code = int(hourly.get("weather_code", [0])[idx])

        effective_wind = round(wind_kmh * exposure, 1)
        icon, label = _wmo_code_to_meta(w_code, effective_wind)

        # Evaluate hazard alert
        is_adverse = False
        hazard: Optional[str] = None

        if effective_wind >= 32.0:
            is_adverse = True
            hazard = f"💨 High Wind Alert ({effective_wind:.0f} km/h): Outside-box shots depressed, aerial disruption"
        elif precip_mm >= 3.0:
            is_adverse = True
            hazard = f"🌧️ Slick Pitch Alert ({precip_mm:.1f} mm/h): Goalkeeper spillage risk, sliding tackle cards elevated"
        elif temp_c <= 0.0:
            is_adverse = True
            hazard = f"❄️ Freezing Turf Alert ({temp_c:.1f}°C): Soft-tissue injury surge, early substitution risk"
        elif effective_wind >= 22.0:
            is_adverse = True
            hazard = f"💨 Moderate Wind ({effective_wind:.0f} km/h): Minor cross drift"

        return WeatherObservation(
            temperature_c=round(temp_c, 1),
            wind_speed_kmh=round(wind_kmh, 1),
            wind_gusts_kmh=round(gusts_kmh, 1),
            precipitation_mm=round(precip_mm, 1),
            relative_humidity=round(humidity, 1),
            condition_code=w_code,
            condition_label=label,
            condition_icon=icon,
            is_adverse=is_adverse,
            hazard_alert=hazard,
            exposure_factor=round(exposure, 2),
            effective_wind_kmh=effective_wind
        )

    def _build_fallback_observation(self, exposure: float) -> WeatherObservation:
        """Graceful climatic fallback when network or forecast data is temporarily unavailable."""
        return WeatherObservation(
            temperature_c=14.5,
            wind_speed_kmh=12.0,
            wind_gusts_kmh=18.0,
            precipitation_mm=0.0,
            relative_humidity=68.0,
            condition_code=2,
            condition_label="Moderate & Overcast",
            condition_icon="⛅",
            is_adverse=False,
            hazard_alert=None,
            exposure_factor=round(exposure, 2),
            effective_wind_kmh=round(12.0 * exposure, 1)
        )

    def refresh_all_forecasts(self) -> int:
        """Forces a refresh of all 20 Premier League stadium forecasts."""
        refreshed = 0
        now_utc = datetime.now(timezone.utc)
        for club, meta in PL_STADIUM_CATALOG.items():
            api_data = self.fetch_open_meteo(meta["lat"], meta["lon"], past_days=3, forecast_days=14)
            if api_data and "hourly" in api_data:
                self.store.setdefault("forecasts", {})[club] = {
                    "fetched_at": now_utc.isoformat(),
                    "hourly": api_data["hourly"]
                }
                refreshed += 1
        self._save_store()
        return refreshed
