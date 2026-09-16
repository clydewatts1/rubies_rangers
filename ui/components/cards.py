"""
ui/components/cards.py
Reusable Streamlit UI Presentation Cards & Badges.
Includes candidate cards, FDR badges, and Pareto comparison cards.
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional
import streamlit as st
from ui.styles import render_html


def get_fdr_badge(fdr_val: float) -> str:
    """Generate HTML badge for Fixture Difficulty Rating."""
    if fdr_val <= 2.5:
        return f'<span class="badge-fdr-easy">FDR {fdr_val:.2f}</span>'
    elif fdr_val <= 3.5:
        return f'<span class="badge-fdr-med">FDR {fdr_val:.2f}</span>'
    else:
        return f'<span class="badge-fdr-hard">FDR {fdr_val:.2f}</span>'


def render_candidate_card(
    candidate_title: str,
    objective_label: str,
    transfers_in: List[str],
    transfers_out: List[str],
    mean_pts: float,
    p10_floor: float,
    p90_ceiling: float,
    win_prob_pct: float,
    net_gain: float,
    badge_label: str = "RECOMMENDED",
    badge_color: str = "green"
) -> None:
    """Renders a high-contrast comparison card for a Pareto candidate squad."""
    badge_cls = f"badge-step-{badge_color}"
    tin_str = ", ".join(transfers_in) if transfers_in else "None"
    tout_str = ", ".join(transfers_out) if transfers_out else "None"
    gain_sign = "+" if net_gain >= 0 else ""

    card_html = f"""
    <div class="step-card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <b style="color: #ffffff; font-size: 16px;">{candidate_title}</b>
            <span class="{badge_cls}">{badge_label}</span>
        </div>
        <div style="color: #94a3b8; font-size: 13px; margin-bottom: 8px;">
            Generated via Objective: <b style="color: #38bdf8;">{objective_label}</b>
        </div>
        <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;">
            <span style="color: #ef4444; font-weight: bold;">OUT:</span> {tout_str} &nbsp;|&nbsp;
            <span style="color: #22c55e; font-weight: bold;">IN:</span> {tin_str}
        </div>
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; text-align: center;">
            <div style="background: rgba(30, 41, 59, 0.7); padding: 6px; border-radius: 6px;">
                <div style="font-size: 11px; color: #94a3b8;">Mean EV</div>
                <div style="font-size: 16px; font-weight: bold; color: #ffffff;">{mean_pts:.1f}</div>
            </div>
            <div style="background: rgba(30, 41, 59, 0.7); padding: 6px; border-radius: 6px;">
                <div style="font-size: 11px; color: #94a3b8;">P10 Floor</div>
                <div style="font-size: 16px; font-weight: bold; color: #f87171;">{p10_floor:.1f}</div>
            </div>
            <div style="background: rgba(30, 41, 59, 0.7); padding: 6px; border-radius: 6px;">
                <div style="font-size: 11px; color: #94a3b8;">P90 Ceiling</div>
                <div style="font-size: 16px; font-weight: bold; color: #4ade80;">{p90_ceiling:.1f}</div>
            </div>
            <div style="background: rgba(30, 41, 59, 0.7); padding: 6px; border-radius: 6px;">
                <div style="font-size: 11px; color: #94a3b8;">Win Prob</div>
                <div style="font-size: 16px; font-weight: bold; color: #38bdf8;">{win_prob_pct:.1f}%</div>
            </div>
        </div>
        <div style="margin-top: 8px; font-size: 12px; color: #cbd5e1; text-align: right;">
            Net Gain vs Baseline: <b style="color: {'#34d399' if net_gain >= 0 else '#f87171'};">{gain_sign}{net_gain:.2f} pts</b>
        </div>
    </div>
    """
    render_html(card_html)
