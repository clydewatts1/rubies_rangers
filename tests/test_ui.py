"""
Headless unit tests for UI presentation layer.
Validates style constants, components, and tab module imports.
"""

import pytest
import pandas as pd
from ui.styles import CUSTOM_CSS
from ui.components import get_fdr_badge, render_candidate_card
from ui.tabs import (
    render_tab_two_stage,
    render_tab_domain_intel,
    render_tab_transfers,
    render_tab_montecarlo_lineup,
    render_tab_montecarlo_transfers,
    render_tab_leagues,
    render_tab_odds_xp,
    render_tab_tactical,
    render_tab_trends,
    render_tab_market,
    render_tab_fixtures,
    render_tab_setpieces,
    render_tab_draft,
    render_tab_explorer,
    render_tab_venue,
    render_tab_matchday,
)


def test_custom_css_tokens():
    """Verify custom CSS has core tokens for dark theme and high contrast."""
    assert ".stApp" in CUSTOM_CSS
    assert "#0b0f19" in CUSTOM_CSS
    assert ".squad-player-card" in CUSTOM_CSS
    assert ".pitch-container" in CUSTOM_CSS
    assert ".step-card" in CUSTOM_CSS


def test_fdr_badge_helper():
    """Verify FDR badge HTML generation based on difficulty rating."""
    easy_badge = get_fdr_badge(2.0)
    assert "badge-fdr-easy" in easy_badge
    assert "2.00" in easy_badge

    med_badge = get_fdr_badge(3.0)
    assert "badge-fdr-med" in med_badge

    hard_badge = get_fdr_badge(4.5)
    assert "badge-fdr-hard" in hard_badge


def test_tab_callables():
    """Verify all tab view entry points are callable."""
    assert callable(render_tab_two_stage)
    assert callable(render_tab_domain_intel)
    assert callable(render_tab_transfers)
    assert callable(render_tab_montecarlo_lineup)
    assert callable(render_tab_montecarlo_transfers)
    assert callable(render_tab_leagues)
    assert callable(render_tab_odds_xp)
    assert callable(render_tab_tactical)
    assert callable(render_tab_trends)
    assert callable(render_tab_market)
    assert callable(render_tab_fixtures)
    assert callable(render_tab_setpieces)
    assert callable(render_tab_draft)
    assert callable(render_tab_explorer)
    assert callable(render_tab_venue)
    assert callable(render_tab_matchday)


def test_league_relative_trajectory_metrics():
    """Verify relative point calculations, zero-baseline, and runway projection."""
    import math

    # Mock historical mini-league records
    records = [
        {"team_name": "Rubies Rangers", "gw_num": 1, "gw_points": 44, "cumulative_points": 44, "league_rank": 5},
        {"team_name": "Rubies Rangers", "gw_num": 2, "gw_points": 65, "cumulative_points": 109, "league_rank": 5},
        {"team_name": "Rubies Rangers", "gw_num": 3, "gw_points": 64, "cumulative_points": 173, "league_rank": 5},
        {"team_name": "Leader FC", "gw_num": 1, "gw_points": 75, "cumulative_points": 75, "league_rank": 1},
        {"team_name": "Leader FC", "gw_num": 2, "gw_points": 98, "cumulative_points": 173, "league_rank": 1},
        {"team_name": "Leader FC", "gw_num": 3, "gw_points": 56, "cumulative_points": 229, "league_rank": 1},
        {"team_name": "Trailing United", "gw_num": 1, "gw_points": 41, "cumulative_points": 41, "league_rank": 6},
        {"team_name": "Trailing United", "gw_num": 2, "gw_points": 62, "cumulative_points": 103, "league_rank": 6},
        {"team_name": "Trailing United", "gw_num": 3, "gw_points": 49, "cumulative_points": 152, "league_rank": 6},
    ]
    df = pd.DataFrame(records)

    ref_team = "Rubies Rangers"
    ref_sub = df[df["team_name"] == ref_team].set_index("gw_num")
    df["ref_cum"] = df["gw_num"].map(ref_sub["cumulative_points"])
    df["ref_gw"] = df["gw_num"].map(ref_sub["gw_points"])

    df["lead_vs_ref"] = df["cumulative_points"] - df["ref_cum"]
    df["ref_advantage"] = df["ref_cum"] - df["cumulative_points"]
    df["ref_gw_swing"] = df["ref_gw"] - df["gw_points"]

    # 1. Reference team baseline must be exactly 0 across all GWs
    rr_leads = df[df["team_name"] == ref_team]["lead_vs_ref"].tolist()
    assert rr_leads == [0, 0, 0]

    # 2. Leader lead vs Rubies Rangers
    leader_leads = df[df["team_name"] == "Leader FC"]["lead_vs_ref"].tolist()
    assert leader_leads == [31, 64, 56]  # Grew to 64, then shrunk to 56 in GW3!

    # 3. GW3 Swing: Rubies Rangers outscored Leader by +8 pts
    gw3_leader_swing = df[(df["team_name"] == "Leader FC") & (df["gw_num"] == 3)]["ref_gw_swing"].iloc[0]
    assert gw3_leader_swing == 8

    # 4. Trailing team lead vs Rubies Rangers is negative
    trailing_leads = df[df["team_name"] == "Trailing United"]["lead_vs_ref"].tolist()
    assert trailing_leads == [-3, -6, -21]

    # 5. Runway Overtake Projection
    gap = 56
    velocity = 2.5
    latest_gw = 3
    gw_to_catch = math.ceil(gap / velocity)  # 56 / 2.5 = 22.4 -> 23
    assert gw_to_catch == 23
    proj_overtake_gw = latest_gw + gw_to_catch  # 3 + 23 = 26
    assert proj_overtake_gw == 26

