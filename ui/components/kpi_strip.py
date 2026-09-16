"""
ui/components/kpi_strip.py
Standardized Zone 2 Unified KPI Telemetry Strip.
Renders uniform high-contrast metric cards with delta indicators and proper formatting.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
import streamlit as st


def render_kpi_strip(metrics: List[Dict[str, Any]]) -> None:
    """
    Renders the canonical Zone 2 KPI Telemetry Strip across 3 to 6 columns.
    
    Args:
        metrics: List of metric dicts:
            [
                {
                    "label": "Expected Return",
                    "value": "64.2 pts",
                    "delta": "+5.8 vs Baseline",
                    "delta_color": "normal" | "inverse" | "off",
                    "help": "Optional tooltip description"
                },
                ...
            ]
    """
    if not metrics:
        return

    n_cols = min(max(len(metrics), 1), 6)
    cols = st.columns(n_cols)

    for i, m in enumerate(metrics):
        with cols[i % n_cols]:
            st.metric(
                label=m.get("label", ""),
                value=m.get("value", "N/A"),
                delta=m.get("delta", None),
                delta_color=m.get("delta_color", "normal"),
                help=m.get("help", None)
            )
