"""
UI Package for Rubies Rangers
Modular Streamlit presentation layer.
"""

from ui.styles import inject_custom_css, render_html, CUSTOM_CSS
from ui.components import render_candidate_card, get_fdr_badge
from ui.cache import load_data

__all__ = [
    "inject_custom_css",
    "render_html",
    "CUSTOM_CSS",
    "render_candidate_card",
    "get_fdr_badge",
    "load_data",
]
