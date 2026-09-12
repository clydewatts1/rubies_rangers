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
