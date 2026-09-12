"""
Backward-compatibility shim for clients.fpl_client.
Canonical implementation now lives in `clients.fpl_client`.
"""

from clients.fpl_client import (
    BOOTSTRAP_URL,
    FIXTURES_URL,
    ELEMENT_SUMMARY_URL,
    CACHE_FILE,
    FIXTURES_CACHE_FILE,
    ELEMENTS_CACHE_DIR,
    CACHE_TTL_SECONDS,
    FPLClient,
)

__all__ = [
    "BOOTSTRAP_URL",
    "FIXTURES_URL",
    "ELEMENT_SUMMARY_URL",
    "CACHE_FILE",
    "FIXTURES_CACHE_FILE",
    "ELEMENTS_CACHE_DIR",
    "CACHE_TTL_SECONDS",
    "FPLClient",
]

if __name__ == "__main__":
    client = FPLClient()
    df = client.get_players_df()
    print(f"Loaded {len(df)} players with rolling FDR.")
    print(f"Current GW: {client.get_current_gameweek()}")
    print("\nTop 5 Players by Fixture-Adjusted Moneyball Score:")
    top = df[df["status"] == "a"].sort_values(by="fdr_moneyball_score", ascending=False).head(5)
    print(top[["web_name", "club_name", "position_name", "now_cost", "form", "fdr_next_5", "next_fixture", "fdr_moneyball_score"]].to_string(index=False))
