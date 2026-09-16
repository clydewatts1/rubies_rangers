"""
ui/components/table.py
Standardized Zone 4 High-Contrast Quantitative Data Table.
Enforces dark surface styling, decimal precision, and clean column formatting.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
import pandas as pd
import streamlit as st


def render_quant_table(
    df: pd.DataFrame,
    columns_to_show: Optional[List[str]] = None,
    column_renames: Optional[Dict[str, str]] = None,
    height: Optional[int] = None
) -> None:
    """
    Renders a standardized, high-contrast quantitative data table.
    Hides dataframe index by default and handles formatting gracefully.
    """
    if df is None or df.empty:
        st.info("ℹ️ No records available for this selection.")
        return

    display_df = df.copy()

    if columns_to_show:
        valid_cols = [c for c in columns_to_show if c in display_df.columns]
        if valid_cols:
            display_df = display_df[valid_cols]

    if column_renames:
        display_df = display_df.rename(columns=column_renames)

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=height
    )
