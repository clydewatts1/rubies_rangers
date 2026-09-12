"""
UI Styles & Design Tokens for Rubies Rangers
Centralizes CSS variables, glassmorphic themes, and HTML card styling.
"""

import streamlit as st

CUSTOM_CSS = """
    .stApp {
        background-color: #0b0f19;
        color: #f8fafc;
    }
    header[data-testid="stHeader"] {
        background-color: #0b0f19;
    }
    section[data-testid="stSidebar"] {
        background-color: #0f172a;
    }
    .stMetric { background-color: #1a1f2c; padding: 12px; border-radius: 8px; border: 1px solid #2d3748; }
    .badge-fdr-easy { background-color: #064e3b; color: #6ee7b7; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-fdr-med { background-color: #78350f; color: #fde68a; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-fdr-hard { background-color: #7f1d1d; color: #fca5a5; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-rise { background-color: #064e3b; color: #34d399; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-fall { background-color: #7f1d1d; color: #f87171; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    
    /* High contrast player cards */
    .squad-player-card {
        background: #1e293b !important;
        color: #f8fafc !important;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 10px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
    }
    .squad-player-card * {
        color: #f8fafc !important;
    }
    .squad-player-card b, .squad-player-card strong {
        color: #ffffff !important;
    }
    .squad-player-card .player-title {
        color: #ffffff !important;
        font-size: 15px !important;
        font-weight: 700 !important;
    }
    .squad-player-card .club-subtitle {
        color: #94a3b8 !important;
        font-size: 12px !important;
    }
    .squad-player-card .metric-line {
        color: #cbd5e1 !important;
        font-size: 12px !important;
    }
    .squad-player-card .score-line {
        color: #34d399 !important;
        font-weight: 600 !important;
        font-size: 12px !important;
    }
    .pitch-container {
        background: radial-gradient(circle at center, #065f46 0%, #064e3b 70%, #022c22 100%);
        border: 2px solid rgba(255, 255, 255, 0.2);
        border-radius: 16px;
        padding: 24px 16px;
        margin-bottom: 24px;
        position: relative;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    }
    .pitch-row {
        display: flex;
        justify-content: space-around;
        align-items: center;
        margin-bottom: 24px;
        flex-wrap: wrap;
        gap: 12px;
    }
    .player-card {
        background: rgba(15, 23, 42, 0.90);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 12px;
        padding: 12px 14px;
        text-align: center;
        min-width: 140px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .player-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 25px rgba(56, 189, 248, 0.4);
        border-color: #38bdf8;
    }
    .captain-badge {
        background: linear-gradient(135deg, #ef4444, #b91c1c);
        color: white;
        font-weight: 800;
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 12px;
        display: inline-block;
        margin-bottom: 4px;
        box-shadow: 0 0 10px rgba(239, 68, 68, 0.6);
    }
    .vc-badge {
        background: linear-gradient(135deg, #3b82f6, #1d4ed8);
        color: white;
        font-weight: 800;
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 12px;
        display: inline-block;
        margin-bottom: 4px;
        box-shadow: 0 0 10px rgba(59, 130, 246, 0.6);
    }
    .xp-pill {
        background: rgba(34, 197, 94, 0.2);
        color: #4ade80;
        border: 1px solid #22c55e;
        padding: 2px 8px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 13px;
        margin-top: 4px;
        display: inline-block;
    }
    .bench-card {
        background: rgba(30, 41, 59, 0.85);
        border: 1px dashed rgba(255, 255, 255, 0.2);
        border-radius: 8px;
        padding: 10px 14px;
        text-align: center;
        min-width: 130px;
    }
    /* Never let markdown code formatting create white boxes over custom cards */
    div[data-testid="stMarkdownContainer"] pre {
        background-color: transparent !important;
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
        box-shadow: none !important;
    }
    div[data-testid="stMarkdownContainer"] code {
        background-color: transparent !important;
        color: inherit !important;
    }
    /* Ensure KPI metric values are crystal clear in all modes */
    [data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricDelta"] {
        color: #38bdf8 !important;
    }
    .step-card {
        background: #1e293b;
        border-radius: 10px;
        padding: 14px 16px;
        margin-bottom: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }
    .badge-step-red {
        background: #991b1b;
        color: #fecaca;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-step-green {
        background: #065f46;
        color: #a7f3d0;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-step-yellow {
        background: #854d0e;
        color: #fef08a;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-step-blue {
        background: #1e40af;
        color: #bfdbfe;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-step-purple {
        background: #581c87;
        color: #e9d5ff;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
"""

def inject_custom_css():
    """Inject custom dark theme CSS and typography tokens."""
    st.markdown(f"<style>{CUSTOM_CSS}</style>", unsafe_allow_html=True)


def render_html(html_code: str):
    """Cleanly render raw HTML without markdown converting indented lines into code blocks."""
    clean = "\n".join(line.strip() for line in html_code.splitlines() if line.strip())
    st.markdown(clean, unsafe_allow_html=True)
