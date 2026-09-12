"""
Backward-compatibility shim for clients.tactical_client.
Canonical implementation now lives in `clients.tactical_client`.
"""

from clients.tactical_client import (
    CACHE_FILE,
    SHOTS_CACHE_DIR,
    CACHE_TTL,
    DEFAULT_SQUAD,
    NAME_ALIASES,
    normalize_name,
    TacticalClient,
)

__all__ = [
    "CACHE_FILE",
    "SHOTS_CACHE_DIR",
    "CACHE_TTL",
    "DEFAULT_SQUAD",
    "NAME_ALIASES",
    "normalize_name",
    "TacticalClient",
]

if __name__ == "__main__":
    tc = TacticalClient()
    print("Testing TacticalClient understat connection...")
    df = tc.get_squad_tactical_df(DEFAULT_SQUAD)
    print(df[["player_name", "npxG_per90", "shots_per90", "shot_quality_xg", "box_ratio", "threat_rating"]].to_string(index=False))
