"""
Clients Package for Rubies Rangers
Handles external data clients: Official FPL REST API and Understat tactical data.
"""

from clients.fpl_client import FPLClient
from clients.tactical_client import TacticalClient, normalize_name

__all__ = [
    "FPLClient",
    "TacticalClient",
    "normalize_name",
]
