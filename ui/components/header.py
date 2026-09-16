"""
ui/components/header.py
Standardized Zone 1 Terminal Header & Mission Briefing Component.
Enforces consistent typography, thesis equations, and status pill badges.
"""

from __future__ import annotations

from typing import List, Dict, Optional
import streamlit as st
from ui.styles import render_html


def render_terminal_header(
    title: str,
    subtitle: str,
    badges: Optional[List[Dict[str, str]]] = None,
    icon: Optional[str] = None
) -> None:
    """
    Renders the canonical Zone 1 Terminal Header.
    
    Args:
        title: Main view title (e.g. "Portfolio Holdings & Tactical Formation")
        subtitle: Quantitative thesis or equation governing this view
        badges: Optional list of badge dicts: [{"text": "...", "color": "green"|"blue"|"amber"|"purple"}]
        icon: Optional leading icon
    """
    badge_html_parts = []
    if badges:
        color_styles = {
            "green": "background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid #10b981;",
            "blue": "background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid #0284c7;",
            "amber": "background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid #d97706;",
            "purple": "background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid #7e22ce;",
            "red": "background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid #b91c1c;",
        }
        for b in badges:
            c = b.get("color", "blue")
            style = color_styles.get(c, color_styles["blue"])
            text = b.get("text", "")
            badge_html_parts.append(
                f'<span style="{style} border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 700; margin-left: 6px;">{text}</span>'
            )

    badges_html = "".join(badge_html_parts)
    icon_str = f"{icon} " if icon else ""

    header_html = f"""
    <div style="margin-bottom: 18px;">
        <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 8px;">
            <h1 style="color: #f8fafc; font-size: 24px; font-weight: 800; margin: 0; padding: 0; letter-spacing: -0.5px;">
                {icon_str}{title}
            </h1>
            <div>{badges_html}</div>
        </div>
        <p style="color: #94a3b8; font-size: 13px; margin: 6px 0 0 0; line-height: 1.5;">
            {subtitle}
        </p>
    </div>
    """
    render_html(header_html)
