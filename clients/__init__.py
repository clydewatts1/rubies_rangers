"""
Clients Package for Rubies Rangers
Handles external data clients: Official FPL REST API and Understat tactical data.
"""

from clients.fpl_client import FPLClient
from clients.fpl_challenge_client import FPLChallengeClient
from clients.tactical_client import TacticalClient, normalize_name
from clients.weather_client import WeatherClient, WeatherObservation

__all__ = [
    "FPLClient",
    "FPLChallengeClient",
    "TacticalClient",
    "WeatherClient",
    "WeatherObservation",
    "normalize_name",
]

