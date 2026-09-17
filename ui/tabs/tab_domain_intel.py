"""
Streamlit Tab: Shane's Domain Intel & Availability Desk
Interactive qualitative-to-quantitative bridge restricted strictly to
Sliders and Option Selectors (Zero free-text input fields) with non-impacting defaults.
"""

from typing import List
import streamlit as st
import pandas as pd

from analytics.domain_intel import (
    ShaneIntelManager,
    PlayerOverride,
    AvailabilityOption,
    EligibilityOption,
    TacticalOption,
    TTLWindow,
)


def render_tab_domain_intel(df: pd.DataFrame, current_squad: List[str], current_gw: int = 4):
    """Render Shane's Human Domain Intel Desk."""
    st.title("🧠 Shane's Domain Intel & Availability Desk")
    st.markdown("""
    **The Qualitative-to-Quantitative Bridge**: Inject tactical intelligence, eye-test sharpness, 
    and late press-conference news into Rubies Rangers.  
    *Strict Control Governance: Sliders and Option Selectors ONLY. Every metric defaults to the mathematical identity element (zero passive bias).*
    """)

    intel_mgr = ShaneIntelManager()

    col_btn1, col_btn2, col_btn3 = st.columns([1.2, 1.5, 3])
    with col_btn1:
        if st.button("🔄 Reset to Defaults"):
            intel_mgr.clear_overrides()
            st.success("All domain overrides reset to non-impacting identity defaults!")
            st.rerun()
    with col_btn2:
        if st.button("🏥 Sync Premier Injuries"):
            from clients.injury_client import InjuryClient
            client = InjuryClient()
            squad_names = {p.lower() for p in current_squad}
            count = client.sync_to_shane_intel(intel_mgr, current_gw=current_gw, target_web_names=squad_names)
            if count > 0:
                st.success(f"Synced {count} injury override(s) for active squad!")
            else:
                st.info("No active squad members currently flagged in injury feed.")
            st.rerun()

    st.markdown("---")
    st.markdown(f"### 📋 Active 15-Man Squad Intel (Target Gameweek: **GW{current_gw}**)")

    # Match squad rows in df
    squad_df = df[df["web_name"].isin(current_squad)].copy()

    for idx, player_name in enumerate(current_squad):
        p_row = squad_df[squad_df["web_name"] == player_name]
        club = p_row["club_name"].iloc[0] if not p_row.empty else "UNK"
        pos = p_row["position_name"].iloc[0] if not p_row.empty else "UNK"
        cost = float(p_row["now_cost"].iloc[0]) if not p_row.empty else 5.0
        news = p_row["news"].iloc[0] if not p_row.empty and "news" in p_row.columns else ""
        official_cop = p_row["chance_of_playing"].iloc[0] if not p_row.empty and "chance_of_playing" in p_row.columns else 100

        # Load existing override or default
        existing_ov = intel_mgr.overrides.get(player_name.lower())
        has_override = existing_ov is not None and existing_ov.has_active_deviation()

        expander_title = f"{'⚡ [MODIFIED] ' if has_override else ''}{player_name} (£{cost:.1f}m | {club} | {pos})"
        with st.expander(expander_title, expanded=has_override):
            if news:
                st.warning(f"Official FPL Flag: {news} (Chance of Playing: {official_cop}%)")

            c1, c2 = st.columns(2)
            with c1:
                # 1. Availability Selector
                avail_opts = [
                    AvailabilityOption.DEFAULT_OFFICIAL.value,
                    AvailabilityOption.CONFIRMED_OUT_0.value,
                    AvailabilityOption.HEAVY_DOUBT_25.value,
                    AvailabilityOption.COIN_FLIP_50.value,
                    AvailabilityOption.MILD_DOUBT_75.value,
                    AvailabilityOption.CLEARED_FIT_100.value,
                ]
                current_avail = existing_ov.availability.value if existing_ov else AvailabilityOption.DEFAULT_OFFICIAL.value
                avail_sel = st.selectbox(
                    "Availability Status",
                    avail_opts,
                    index=avail_opts.index(current_avail),
                    format_func=lambda x: {
                        "DEFAULT_OFFICIAL": "Default (Official FPL API Status)",
                        "CONFIRMED_OUT_0": "0% Confirmed Out (Exclude from MILP)",
                        "HEAVY_DOUBT_25": "25% Heavy Doubt (Auto-Sub High Risk)",
                        "COIN_FLIP_50": "50% Coin-Flip / Late Fitness Test",
                        "MILD_DOUBT_75": "75% Minor Doubt (Porro Yellow Flag)",
                        "CLEARED_FIT_100": "100% Cleared Fit (Ignore Yellow Flag)"
                    }[x],
                    key=f"avail_{player_name}"
                )

                # 2. Reason Category Selector
                reasons = [
                    "Tactical Assessment",
                    "Personal Shock / Accident / Emergency",
                    "Midweek European Congestion (Pep Roulette)",
                    "Nagging Muscular Injury / Late Fitness Test",
                    "Tactical Role Shift / Out-of-Position",
                    "Eye-Test Sharpness / Sluggishness"
                ]
                current_reason = existing_ov.reason_category if existing_ov and existing_ov.reason_category in reasons else reasons[0]
                reason_sel = st.selectbox(
                    "Reason Category",
                    reasons,
                    index=reasons.index(current_reason),
                    key=f"reason_{player_name}"
                )

            with c2:
                # 3. Tactical Role / Minutes Selector
                tactical_opts = [
                    TacticalOption.DEFAULT_MINUTES.value,
                    TacticalOption.ROTATION_HOOK_60.value,
                    TacticalOption.FULL_90_LOCK.value,
                    TacticalOption.OUT_OF_POSITION_ADV.value,
                ]
                current_tactical = existing_ov.tactical_risk.value if existing_ov else TacticalOption.DEFAULT_MINUTES.value
                tactical_sel = st.selectbox(
                    "Tactical Role & Minutes Risk",
                    tactical_opts,
                    index=tactical_opts.index(current_tactical),
                    format_func=lambda x: {
                        "DEFAULT_MINUTES": "Default (Standard 85 min expectation)",
                        "ROTATION_HOOK_60": "Rotation Hook @ 60m (Congestion Risk)",
                        "FULL_90_LOCK": "Full 90m Lock (High Security Starter)",
                        "OUT_OF_POSITION": "Out-of-Position Advantage (+25% Attack)"
                    }[x],
                    key=f"tactical_{player_name}"
                )

                # 4. Validity Window (TTL)
                ttl_opts = [
                    TTLWindow.CURRENT_GW_ONLY.value,
                    TTLWindow.NEXT_TWO_GWS.value,
                    TTLWindow.UNTIL_CLEARED.value,
                ]
                current_ttl = existing_ov.ttl_window.value if existing_ov else TTLWindow.CURRENT_GW_ONLY.value
                ttl_sel = st.radio(
                    "Validity Window (Gameweek TTL)",
                    ttl_opts,
                    index=ttl_opts.index(current_ttl),
                    format_func=lambda x: {
                        "CURRENT_GW_ONLY": f"GW{current_gw} Only (Ephemeral Default)",
                        "NEXT_TWO_GWS": f"GW{current_gw} & GW{current_gw+1}",
                        "UNTIL_CLEARED": "Until Explicitly Cleared"
                    }[x],
                    horizontal=True,
                    key=f"ttl_{player_name}"
                )

            # 5. Sliders (With Identity Defaults)
            sl_col1, sl_col2 = st.columns(2)
            with sl_col1:
                cur_mins = float(existing_ov.expected_minutes) if existing_ov else 85.0
                mins_sel = st.slider(
                    "Expected Starting Minutes",
                    min_value=45.0,
                    max_value=90.0,
                    value=cur_mins,
                    step=5.0,
                    help="Default: 85 mins. Reduce for sub risk at 60 mins.",
                    key=f"mins_{player_name}"
                )
            with sl_col2:
                cur_mult = float(existing_ov.eye_test_multiplier) if existing_ov else 1.00
                mult_sel = st.slider(
                    "Eye-Test Form Multiplier",
                    min_value=0.80,
                    max_value=1.20,
                    value=cur_mult,
                    step=0.05,
                    help="Default: 1.00x (0% passive distortion). Boost for razor sharp players.",
                    key=f"mult_{player_name}"
                )

            # Save single player override
            if st.button(f"Save Overrides for {player_name}", key=f"save_{player_name}"):
                new_ov = PlayerOverride(
                    web_name=player_name,
                    scope="squad",
                    valid_gameweek=current_gw,
                    ttl_window=TTLWindow(ttl_sel),
                    availability=AvailabilityOption(avail_sel),
                    eligibility=EligibilityOption.DEFAULT_ELIGIBLE,
                    tactical_risk=TacticalOption(tactical_sel),
                    expected_minutes=mins_sel,
                    eye_test_multiplier=mult_sel,
                    reason_category=reason_sel,
                    active=True
                )
                intel_mgr.set_override(new_ov)
                intel_mgr.save_overrides(gameweek=current_gw)
                st.success(f"Saved intel for {player_name}!")
                st.rerun()
