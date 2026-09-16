"""
ui/components/__init__.py
Atomic UI Component Library for the Rubies Rangers Quant Trading Desk.
"""

from ui.components.ticker import render_portfolio_ticker
from ui.components.header import render_terminal_header
from ui.components.kpi_strip import render_kpi_strip
from ui.components.table import render_quant_table
from ui.components.cards import render_candidate_card, get_fdr_badge

__all__ = [
    "render_portfolio_ticker",
    "render_terminal_header",
    "render_kpi_strip",
    "render_quant_table",
    "render_candidate_card",
    "get_fdr_badge",
]
