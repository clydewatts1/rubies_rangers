"""
Tabs Package for Rubies Rangers Streamlit UI
"""

from ui.tabs.tab_two_stage import render_tab_two_stage
from ui.tabs.tab_domain_intel import render_tab_domain_intel
from ui.tabs.tab_transfers import render_tab_transfers
from ui.tabs.tab_montecarlo import render_tab_montecarlo_lineup, render_tab_montecarlo_transfers
from ui.tabs.tab_leagues import render_tab_leagues
from ui.tabs.tab_odds_xp import render_tab_odds_xp
from ui.tabs.tab_tactical import render_tab_tactical
from ui.tabs.tab_trends import render_tab_trends
from ui.tabs.tab_market import render_tab_market
from ui.tabs.tab_fixtures import render_tab_fixtures
from ui.tabs.tab_setpieces import render_tab_setpieces
from ui.tabs.tab_draft import render_tab_draft, render_tab_explorer
from ui.tabs.tab_venue import render_tab_venue
from ui.tabs.tab_matchday import render_tab_matchday
from ui.tabs.tab_chip_strategy import render_tab_chip_strategy
from ui.tabs.tab_autonomous_cpn import render_tab_autonomous_cpn

__all__ = [
    "render_tab_two_stage",
    "render_tab_domain_intel",
    "render_tab_transfers",
    "render_tab_montecarlo_lineup",
    "render_tab_montecarlo_transfers",
    "render_tab_leagues",
    "render_tab_odds_xp",
    "render_tab_tactical",
    "render_tab_trends",
    "render_tab_market",
    "render_tab_fixtures",
    "render_tab_setpieces",
    "render_tab_draft",
    "render_tab_explorer",
    "render_tab_venue",
    "render_tab_matchday",
    "render_tab_chip_strategy",
    "render_tab_autonomous_cpn",
]

