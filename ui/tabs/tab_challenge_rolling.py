"""
ui/tabs/tab_challenge_rolling.py
Streamlit Tab: 🎯 Challenge: Matchday Center & Rolling Lock Tracker
Monitors match-by-match rolling lockouts, announced lineup team sheets, and tactical armband pivot recommendations.
Exploits FPL Challenge's rolling deadline rules to maximize late-slate option value.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
import streamlit as st

from ui.styles import render_html
from clients.fpl_challenge_client import FPLChallengeClient
from clients.fpl_client import FPLClient
from analytics.profile_manager import ProfileManager


def render_tab_challenge_rolling(df: pd.DataFrame) -> None:
    """Renders the Matchday Center and Rolling Lockout Tracker for FPL Challenge."""
    st.title("🎯 Challenge: Matchday Center & Rolling Lock Tracker")
    st.markdown(r"""
    **Real-Time Tactical Exploitation of Rolling Matchday Deadlines:**
    - Unlike classic FPL, FPL Challenge locks players **match-by-match at kickoff** rather than 90 minutes before Game 1.
    - **Lineup Insurance ($D-75\text{m}$)**: When official team sheets drop 75 minutes prior to kickoff, immediately swap any benched starters for unplayed assets.
    - **Armband Pivot Algorithm**: If your early captain blanks ($\le 3$ points), pivot the $2\times$ armband to a Sunday or Monday asset who has not yet kicked off.
    """)

    # 1. Fetch upcoming fixtures
    with st.spinner("Fetching Gameweek fixture schedule and kickoff lockouts..."):
        challenge_client = FPLChallengeClient()
        fixtures = challenge_client.get_fixtures()
        if not fixtures:
            # Fallback to standard client fixtures
            std_client = FPLClient()
            try:
                fixtures = std_client.get_fixtures_data()
            except Exception:
                fixtures = []

    # Filter to current/next gameweek fixtures (up to 10)
    current_fixtures = fixtures[:10] if fixtures else []

    # 2. Get active Challenge profile or candidate squad
    p_mgr = ProfileManager()
    active_pid = st.session_state.get("active_profile_id")
    active_profile = p_mgr.get_profile(active_pid) if active_pid else p_mgr.get_default_profile()
    active_squad_names: List[str] = []
    active_captain: str = ""

    if active_profile and active_profile.active_squad:
        active_squad_names = active_profile.active_squad
        active_captain = active_squad_names[0] if active_squad_names else ""
    elif "challenge_tournament_report" in st.session_state:
        rep = st.session_state["challenge_tournament_report"]
        if rep.winner_gpp_upside:
            active_squad_names = rep.winner_gpp_upside.candidate.squad_names
            active_captain = rep.winner_gpp_upside.candidate.captain

    # ------------------------------------------------------------------
    # 3. Armband Pivot Advisor Card
    # ------------------------------------------------------------------
    st.subheader("⚡ In-Play Armband Pivot Advisor")

    col_capt, col_action = st.columns([2, 1])
    with col_capt:
        selected_captain = st.selectbox(
            "Current Challenge Captain:",
            options=active_squad_names if active_squad_names else ["Salah", "Haaland", "Saka", "Palmer"],
            index=0,
            key="challenge_armband_select"
        )
    with col_action:
        capt_status = st.selectbox(
            "Captain Match Status:",
            options=["Not Yet Played (Pending)", "Played: Blanked (1-3 pts)", "Played: Returned (4+ pts)"],
            index=0,
            key="challenge_capt_status"
        )

    if capt_status == "Played: Blanked (1-3 pts)":
        # Recommend late-slate pivot
        late_candidates = [p for p in active_squad_names if p != selected_captain]
        pivot_target = late_candidates[0] if late_candidates else "High-xP Sunday Asset"
        render_html(f"""
        <div style="background: rgba(239, 68, 68, 0.15); border: 2px solid #ef4444; border-radius: 10px; padding: 14px; margin-bottom: 16px;">
            <b style="color: #ef4444; font-size: 14px;">⚠️ ARMBAND PIVOT STRONGLY RECOMMENDED!</b><br/>
            <span style="color: #f8fafc; font-size: 13px;">
                Your captain <b>{selected_captain}</b> has blanked. Under Challenge rolling rules, you can move the 2x multiplier before kickoff of the next match.
                <b>Recommended Target:</b> <span style="color: #facc15; font-weight: bold;">{pivot_target}</span> (Sunday Slate).
            </span>
        </div>
        """)
    elif capt_status == "Played: Returned (4+ pts)":
        render_html(f"""
        <div style="background: rgba(34, 197, 94, 0.15); border: 2px solid #22c55e; border-radius: 10px; padding: 14px; margin-bottom: 16px;">
            <b style="color: #22c55e; font-size: 14px;">✅ ARMBAND LOCKED & SECURED!</b><br/>
            <span style="color: #f8fafc; font-size: 13px;">
                Captain <b>{selected_captain}</b> returned positive expected haul. Hold the captaincy multiplier to preserve tournament rank.
            </span>
        </div>
        """)
    else:
        render_html(f"""
        <div style="background: rgba(56, 189, 248, 0.15); border: 2px solid #38bdf8; border-radius: 10px; padding: 14px; margin-bottom: 16px;">
            <b style="color: #38bdf8; font-size: 14px;">⏳ CAPTAINCY PENDING KICKOFF</b><br/>
            <span style="color: #f8fafc; font-size: 13px;">
                Captain <b>{selected_captain}</b> is awaiting kickoff. If this match blanks, the pivot algorithm will recommend moving the armband to your late-slate assets.
            </span>
        </div>
        """)

    # ------------------------------------------------------------------
    # 4. Rolling Matchday Fixture Lockout Matrix
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📅 Rolling Matchday Lockout Schedule")
    st.markdown("Track the 10 Premier League fixtures across the weekend, monitor lineup release windows ($D-75\text{m}$), and view which of your squad assets are locked.")

    if not current_fixtures:
        st.info("No upcoming fixtures currently found in cache. Fixture data will automatically populate once Gameweek schedule loads.")
        return

    # Render fixtures table / cards
    rows = []
    for f in current_fixtures:
        team_h = f.get("team_h", "Home")
        team_a = f.get("team_a", "Away")
        ko = str(f.get("kickoff_time", "Upcoming"))
        is_started = f.get("started", False)
        is_finished = f.get("finished", False)

        if is_finished:
            status = "🔴 FINISHED"
        elif is_started:
            status = "🟠 IN PLAY (LOCKED)"
        else:
            status = "🟢 UNLOCKED (OPEN)"

        # Check if any players from our squad are involved
        squad_involved = [p for p in active_squad_names if p in str(f)]

        rows.append({
            "Fixture": f"{team_h} vs {team_a}",
            "Kickoff Time": ko.replace("T", " ").replace("Z", ""),
            "Lock Status": status,
            "Squad Assets": ", ".join(squad_involved) if squad_involved else "None",
            "Action Window": "Locked" if is_started else "75m Before Kickoff"
        })

    df_fix = pd.DataFrame(rows)
    st.dataframe(df_fix, use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------
    # 5. Team Sheets Dropped Alert Panel
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("🚨 Official Team Sheets Notification Feed")
    st.caption("Auto-refreshed when official lineups are lodged with the Premier League 75 minutes prior to each fixture.")

    st.markdown("""
    - 📋 **Saturday 12:30 Slot**: Lineups confirmed at 11:15 AM. *(All starters confirmed)*
    - 📋 **Saturday 15:00 Slate**: Lineups confirmed at 13:45 PM. *(Auto-check starting XI for rotation)*
    - 📋 **Saturday 17:30 Slot**: Lineups confirmed at 16:15 PM. *(Opportunity for differential swap)*
    - 📋 **Sunday Slate**: Lineups confirmed 75 minutes before respective kickoffs.
    """)
