"""
Backward-compatibility shim for analytics.xp_model.
Canonical implementation now lives in `analytics.xp_model`.
"""

from analytics.xp_model import XPModel, DEFAULT_SQUAD, GW4_MATCH_ODDS

__all__ = ["XPModel", "DEFAULT_SQUAD", "GW4_MATCH_ODDS"]

if __name__ == "__main__":
    xm = XPModel()
    print("Testing XPModel odds...")
    df = xm.get_expected_points_df()
    print(df.head())
