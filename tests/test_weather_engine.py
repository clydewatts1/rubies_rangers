"""
Unit and Integration Tests for Weather & Seasonality Subsystem
Validates Open-Meteo client caching, meteorological dampener formulas,
turnaround congestion decay, XPModel modulation, and Matchday Center telemetry.
"""

import os
import pytest
from dataclasses import FrozenInstanceError

from clients.weather_client import WeatherClient, WeatherObservation, PL_STADIUM_CATALOG
from analytics.weather_engine import WeatherEngine, PlayerWeatherReport
from analytics.matchday_hub import MatchdayHub, MatchdaySummary
from analytics.xp_model import XPModel


@pytest.fixture
def weather_client(tmp_path):
    cache_file = str(tmp_path / "test_weather_store.json")
    return WeatherClient(cache_file=cache_file)


@pytest.fixture
def weather_engine(weather_client):
    return WeatherEngine(weather_client=weather_client)


def test_weather_observation_immutability():
    """Verify WeatherObservation is an immutable frozen dataclass."""
    obs = WeatherObservation(
        temperature_c=18.5,
        wind_speed_kmh=24.0,
        wind_gusts_kmh=36.0,
        precipitation_mm=1.2,
        relative_humidity=72.0,
        condition_code=61,
        condition_label="Rain",
        condition_icon="🌧️",
        is_adverse=True,
        hazard_alert="Slick Pitch",
        exposure_factor=1.20,
        effective_wind_kmh=28.8
    )
    assert obs.temperature_c == 18.5
    assert obs.condition_icon == "🌧️"
    with pytest.raises(FrozenInstanceError):
        obs.temperature_c = 25.0


def test_weather_observation_serialization():
    """Verify WeatherObservation serializes to and from dict seamlessly."""
    obs = WeatherObservation(
        temperature_c=12.0,
        wind_speed_kmh=15.0,
        wind_gusts_kmh=22.0,
        precipitation_mm=0.0,
        relative_humidity=65.0,
        condition_code=2,
        condition_label="Partly Cloudy",
        condition_icon="⛅",
        is_adverse=False,
        hazard_alert=None,
        exposure_factor=1.00,
        effective_wind_kmh=15.0
    )
    d = obs.to_dict()
    restored = WeatherObservation.from_dict(d)
    assert restored == obs


def test_stadium_catalog_resolution(weather_client):
    """Verify PL stadium catalog resolves coordinates and exposure factors."""
    meta_bou = weather_client.get_stadium_meta("BOU")
    assert meta_bou["exposure"] == 1.25
    assert meta_bou["type"] == "COASTAL_EXPOSED"

    meta_tot = weather_client.get_stadium_meta("TOT")
    assert meta_tot["exposure"] == 0.70
    assert meta_tot["type"] == "COVERED_BOWL"


def test_weather_fallback_logic(weather_client):
    """Verify fallback observation operates defensively when offline."""
    fallback = weather_client._build_fallback_observation(exposure=1.25)
    assert isinstance(fallback, WeatherObservation)
    assert fallback.temperature_c == 14.5
    assert fallback.effective_wind_kmh == 15.0
    assert fallback.is_adverse is False


def test_weather_dampener_benign_conditions(weather_engine):
    """Verify benign conditions yield identity multiplier (1.00)."""
    calm_obs = WeatherObservation(
        temperature_c=18.0,
        wind_speed_kmh=12.0,
        wind_gusts_kmh=18.0,
        precipitation_mm=0.0,
        relative_humidity=60.0,
        condition_code=1,
        condition_label="Mainly Clear",
        condition_icon="☀️",
        is_adverse=False,
        hazard_alert=None,
        exposure_factor=1.00,
        effective_wind_kmh=12.0
    )
    mult = weather_engine.compute_weather_dampener(calm_obs, position="MID")
    assert mult == 1.00


def test_weather_dampener_high_wind(weather_engine):
    """Verify gale-force wind dampens attacking return."""
    windy_obs = WeatherObservation(
        temperature_c=14.0,
        wind_speed_kmh=32.0,
        wind_gusts_kmh=45.0,
        precipitation_mm=0.0,
        relative_humidity=70.0,
        condition_code=3,
        condition_label="Overcast",
        condition_icon="💨",
        is_adverse=True,
        hazard_alert="High Wind",
        exposure_factor=1.25,
        effective_wind_kmh=40.0
    )
    mult_fwd = weather_engine.compute_weather_dampener(windy_obs, position="FWD")
    mult_def = weather_engine.compute_weather_dampener(windy_obs, position="DEF")

    # Attacker should be dampened
    assert mult_fwd < 1.00
    # Defender penalty is dampened/attenuated due to Clean Sheet probability expansion
    assert mult_def > mult_fwd


def test_congestion_multiplier_turnaround(weather_engine):
    """Verify turnaround rest logic applies proper decay."""
    # Full week rest: identity
    assert weather_engine.compute_congestion_multiplier(rest_days=7.0, age=26) == 1.00

    # 3-day turnaround (72h): moderate penalty
    mult_72h = weather_engine.compute_congestion_multiplier(rest_days=3.0, age=26)
    assert mult_72h < 1.00

    # 2-day turnaround (48h festive): severe penalty
    mult_48h = weather_engine.compute_congestion_multiplier(rest_days=2.0, age=26)
    assert mult_48h < mult_72h

    # Veteran age amplification
    mult_vet = weather_engine.compute_congestion_multiplier(rest_days=2.0, age=33)
    assert mult_vet < mult_48h


def test_xp_model_weather_integration():
    """Verify XPModel returns weather metadata and applies dampeners."""
    xp_model = XPModel(gameweek=4)
    df_xp = xp_model.evaluate_squad_xp()

    assert "weather_dampener" in df_xp.columns
    assert "congestion_multiplier" in df_xp.columns
    assert "unadjusted_xP" in df_xp.columns
    assert "weather_condition" in df_xp.columns

    # Verify all multipliers are bounded valid numbers
    assert (df_xp["weather_dampener"] > 0.5).all()
    assert (df_xp["weather_dampener"] <= 1.05).all()
    assert (df_xp["congestion_multiplier"] > 0.5).all()


def test_matchday_summary_weather_telemetry():
    """Verify MatchdayHub generates weather badges and summary alerts."""
    hub = MatchdayHub()
    summary = hub.get_matchday_summary(gameweek=4)

    assert isinstance(summary, MatchdaySummary)
    assert hasattr(summary, "adverse_weather_count")
    assert hasattr(summary, "squad_weather_alerts")
    assert len(summary.fixtures) > 0

    first_fix = summary.fixtures[0]
    assert first_fix.weather is not None
    assert isinstance(first_fix.weather, WeatherObservation)
    assert "°C" in first_fix.weather_badge_html


def test_weather_engine_squad_forecast(weather_engine):
    """Verify get_squad_weather_forecast compiles full 15-player report."""
    squad = [
        "Roefs", "Verbruggen",
        "Pedro Porro", "Senesi", "Guéhi", "Robinson", "Thiaw",
        "Foden", "Ødegaard", "Mbeumo", "Cherki", "Rogers",
        "João Pedro", "Isak", "Solanke"
    ]
    reports = weather_engine.get_squad_weather_forecast(squad, gameweek=4)
    assert len(reports) == 15
    for r in reports:
        assert isinstance(r, PlayerWeatherReport)
        assert r.risk_level in ("LOW", "MODERATE", "HIGH", "SEVERE")
        assert r.combined_multiplier > 0.0


def test_weather_engine_gameweek_radar(weather_engine):
    """Verify get_gameweek_radar returns fixture radar items."""
    radar = weather_engine.get_gameweek_radar(gameweek=4)
    assert len(radar) > 0
    first = radar[0]
    assert "stadium_name" in first
    assert "weather" in first
    assert isinstance(first["weather"], WeatherObservation)
