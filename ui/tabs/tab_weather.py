"""
Weather Radar & Environmental Intelligence Workflow Tab
Presents real-time stadium micro-climate telemetry, 1-2 week forward weather forecasting,
squad exposure risk profiling, and calendar turnaround congestion analytics.
"""

import streamlit as st
import pandas as pd
from typing import List, Dict, Any, Optional

from ui.styles import render_html
from clients.weather_client import WeatherClient, PL_STADIUM_CATALOG
from analytics.weather_engine import WeatherEngine, PlayerWeatherReport
from analytics.xp_model import DEFAULT_SQUAD


def render_tab_weather(df: pd.DataFrame, current_squad: Optional[List[str]] = None):
    """Renders the comprehensive Weather Radar & Environmental Intelligence tab."""
    st.markdown("## 🌤️ Weather Radar & Environmental Intelligence")
    st.caption("High-resolution micro-climate telemetry, 1–2 week forward stadium forecasts, and calendar congestion modeling for Rubies Rangers.")

    weather_engine = WeatherEngine()
    squad_list = current_squad or DEFAULT_SQUAD

    # 1. Controls Toolbar
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 2])
    with ctrl_col1:
        sel_gw = st.selectbox(
            "Forecast Horizon / Gameweek:",
            [4, 5, 6],
            index=0,
            format_func=lambda x: f"Gameweek {x} {'(Current Live GW)' if x == 4 else f'(+{x-4} Week Ahead)'}",
            key="weather_tab_gw_select"
        )
    with ctrl_col2:
        only_adverse = st.checkbox("⚠️ Filter Adverse Conditions Only", value=False, help="Show only fixtures and players facing wind >22km/h, heavy rain, freezing cold, or short rest.")
    with ctrl_col3:
        st.write("")
        if st.button("🔄 Refresh All 20 Stadium Forecasts", help="Forces a fresh API pull from Open-Meteo across all Premier League venues."):
            with st.spinner("Fetching latest high-resolution forecasts from Open-Meteo..."):
                count = weather_engine.weather_client.refresh_all_forecasts()
                st.success(f"Successfully refreshed forecasts across {count} stadiums!")
                st.rerun()

    # 2. Fetch Data
    with st.spinner(f"Compiling environmental reports for Gameweek {sel_gw}..."):
        squad_reports = weather_engine.get_squad_weather_forecast(squad_list, gameweek=sel_gw)
        gw_radar = weather_engine.get_gameweek_radar(gameweek=sel_gw)

    # 3. Hero Meteorological KPIs
    if squad_reports:
        valid_reports = [r for r in squad_reports if r.status_label != "NO FIXTURE"]
        avg_wind = sum(r.weather.effective_wind_kmh for r in valid_reports) / len(valid_reports) if valid_reports else 0.0
        adverse_squad = [r for r in valid_reports if r.risk_level in ("MODERATE", "HIGH", "SEVERE")]
        most_exposed = max(valid_reports, key=lambda r: r.weather.effective_wind_kmh) if valid_reports else None
        avg_rest = sum(r.rest_days for r in valid_reports) / len(valid_reports) if valid_reports else 7.0

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric(
                "Squad Avg Wind Exposure",
                f"{avg_wind:.1f} km/h",
                delta="🟢 Calm & Controlled" if avg_wind < 20.0 else "⚠️ High Wind Shear",
                delta_color="normal" if avg_wind < 20.0 else "inverse",
                help="Average effective pitch-level wind speed across active squad fixtures, accounting for stadium exposure factors."
            )
        with k2:
            st.metric(
                "Adverse Weather Matches",
                f"{len(adverse_squad)} / {len(valid_reports)} Players",
                delta=f"{len([r for r in adverse_squad if r.risk_level in ('HIGH', 'SEVERE')])} High/Severe Alerts",
                delta_color="normal" if len(adverse_squad) == 0 else "inverse",
                help="Count of squad players featuring in wind >22km/h, heavy rain, or sub-zero conditions."
            )
        with k3:
            if most_exposed:
                st.metric(
                    "Most Exposed Asset",
                    f"{most_exposed.web_name} ({most_exposed.club_short})",
                    delta=f"{most_exposed.weather.effective_wind_kmh:.0f} km/h • {most_exposed.weather.condition_icon} {most_exposed.weather.condition_label}",
                    help="Player facing the highest combined pitch-level wind shear or precipitation."
                )
            else:
                st.metric("Most Exposed Asset", "None", delta="Optimal")
        with k4:
            st.metric(
                "Squad Turnaround Rest",
                f"{avg_rest:.1f} Days Avg",
                delta="🟢 Fully Rested" if avg_rest >= 5.0 else "⚠️ Short Turnaround",
                help="Average days elapsed since last official competitive match."
            )

    st.markdown("---")

    # 4. View Tabs: Squad Forecast vs League Radar vs Physics Guide
    tab_squad, tab_radar, tab_guide = st.tabs([
        f"👥 Rubies Rangers Squad Telemetry (GW{sel_gw})",
        f"🌐 League-Wide Stadium Weather Radar (GW{sel_gw})",
        "📚 Moneyball Aerodynamics & Physics Guide"
    ])

    with tab_squad:
        st.subheader(f"🛡️ Environmental Impact on Active Squad (Gameweek {sel_gw})")
        st.caption("Shows forecasted temperature, wind shear, rain, turnaround fatigue, and calculated xP multipliers for each player.")

        filtered_reports = squad_reports
        if only_adverse:
            filtered_reports = [r for r in squad_reports if r.risk_level in ("MODERATE", "HIGH", "SEVERE")]

        if not filtered_reports:
            st.info("No squad players are currently facing adverse meteorological or congestion conditions in this horizon!")
        else:
            table_rows = []
            for r in filtered_reports:
                w = r.weather
                risk_badge = {
                    "LOW": "🟢 LOW",
                    "MODERATE": "🟡 MOD",
                    "HIGH": "🟠 HIGH",
                    "SEVERE": "🔴 SEVERE"
                }.get(r.risk_level, "🟢 LOW")

                venue_str = f"{r.opponent_short} ({'H' if r.is_home else 'A'})" if r.opponent_short != "BLANK" else "BLANK"
                weather_str = f"{w.condition_icon} {w.temperature_c:.0f}°C • {w.effective_wind_kmh:.0f} km/h (Gusts {w.wind_gusts_kmh:.0f})"
                if w.precipitation_mm > 0.0:
                    weather_str += f" • 🌧️ {w.precipitation_mm:.1f}mm"

                table_rows.append({
                    "Player": r.web_name,
                    "Club": r.club_short,
                    "Pos": r.position,
                    "Fixture": venue_str,
                    "Kickoff": r.status_label,
                    "Forecast Telemetry": weather_str,
                    "Rest": f"{r.rest_days:.1f}d",
                    "Risk": risk_badge,
                    "Φ (Weather)": f"{r.weather_dampener:.2f}",
                    "Ω (Rest)": f"{r.congestion_multiplier:.2f}",
                    "Net Mult": f"{r.combined_multiplier:.2f}x",
                    "Tactical Telemetry & Notes": r.tactical_note
                })

            df_squad_weather = pd.DataFrame(table_rows)
            st.dataframe(
                df_squad_weather,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Player": st.column_config.TextColumn("Player", width="small"),
                    "Club": st.column_config.TextColumn("Club", width="small"),
                    "Pos": st.column_config.TextColumn("Pos", width="small"),
                    "Fixture": st.column_config.TextColumn("Fixture", width="small"),
                    "Kickoff": st.column_config.TextColumn("Kickoff", width="small"),
                    "Forecast Telemetry": st.column_config.TextColumn("Forecast & Wind", width="medium"),
                    "Rest": st.column_config.TextColumn("Rest", width="small"),
                    "Risk": st.column_config.TextColumn("Risk Rating", width="small"),
                    "Φ (Weather)": st.column_config.TextColumn("Φ (Weather)", width="small"),
                    "Ω (Rest)": st.column_config.TextColumn("Ω (Rest)", width="small"),
                    "Net Mult": st.column_config.TextColumn("Multiplier", width="small"),
                    "Tactical Telemetry & Notes": st.column_config.TextColumn("Tactical Telemetry", width="large")
                }
            )

    with tab_radar:
        st.subheader(f"🌐 League-Wide Stadium Meteorological Radar (Gameweek {sel_gw})")
        st.caption("Full overview of weather conditions across all 10 fixtures for scouting upcoming transfer targets.")

        if not gw_radar:
            st.info("No fixtures found for this gameweek.")
        else:
            r_col1, r_col2 = st.columns(2)
            for i, item in enumerate(gw_radar):
                target_col = r_col1 if (i % 2 == 0) else r_col2
                w = item["weather"]
                with target_col:
                    is_adv = w.is_adverse
                    border_color = "#ef4444" if w.effective_wind_kmh >= 30.0 else ("#f59e0b" if is_adv else "rgba(255,255,255,0.10)")
                    bg_color = "rgba(30, 41, 59, 0.70)" if not is_adv else "rgba(69, 26, 3, 0.40)"
                    hazard_str = f'<div style="color: #fca5a5; font-size: 11px; font-weight: 700; margin-top: 6px;">⚠️ {w.hazard_alert}</div>' if w.hazard_alert else ""

                    render_html(f"""
                    <div style="background: {bg_color}; border: 1px solid {border_color}; border-radius: 10px; padding: 12px; margin-bottom: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="font-weight: 800; font-size: 15px; color: #ffffff;">{item['match_label']}</span>
                            <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 6px; font-size: 11px; color: #93c5fd;">⏳ {item['day_time']}</span>
                        </div>
                        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 6px;">
                            🏟️ {item['stadium_name']} <small>({item['stadium_type'].replace('_', ' ')})</small>
                        </div>
                        <div style="display: flex; gap: 12px; font-size: 13px; color: #e2e8f0; align-items: center;">
                            <span>{w.condition_icon} <b>{w.temperature_c:.0f}°C</b></span>
                            <span>💨 <b>{w.effective_wind_kmh:.0f} km/h</b> (Raw: {w.wind_speed_kmh:.0f}, Gusts: {w.wind_gusts_kmh:.0f})</span>
                            <span>🌧️ <b>{w.precipitation_mm:.1f} mm/h</b></span>
                        </div>
                        {hazard_str}
                    </div>
                    """)

    with tab_guide:
        st.subheader("📚 Quantitative Environmental Modeling Principles")
        st.markdown(r"""
        ### Why Weather Matters in Premier League Analytics
        Academic sports science and professional betting syndicate models demonstrate that environmental conditions and calendar congestion produce non-linear deviations from standard Poisson goal expectancies:

        1. **Wind Speed is the #1 Scoring Dampener**:
           * High sustained wind ($> 25\text{ km/h}$) causes chaotic Magnus forces on long deliveries and craters outside-the-box goal conversion by over $-40\%$.
           * Exposed coastal stadiums (e.g. Bournemouth's Vitality Stadium, Brighton's Amex) suffer significantly higher wind shear than sheltered modern covered bowls (Arsenal's Emirates Stadium, Tottenham Hotspur Stadium).
           * In gale matches, expected total goals drop by $-14\%$, which directly inflates clean sheet probability mass for defenders and goalkeepers.

        2. **Precipitation & Slick Pitch Dynamics**:
           * Heavy rain increases ball drag, disrupting high-tempo tiki-taka ground-passing sides.
           * Goalkeeper handling errors and ball spillages surge by $+18\%$, creating lucrative second-chance tap-ins for opportunistic poachers.
           * Sliding tackles increase, boosting yellow card penalties and depressing baseline BPS scores.

        3. **Sub-Zero Temperatures & Soft-Tissue Strain**:
           * Cold turf ($T \le 0^\circ\text{C}$) stiffens muscle fibers, causing a $+34\%$ spike in hamstring and groin injuries.
           * Managers are statistically far more likely to substitute star attacking assets at minute 65–70 rather than risking the full 90 minutes.

        4. **Turnaround Rest & Rotation Decay**:
           * When teams face matches with $\le 48\text{ hours}$ turnaround, starting probability for veteran players ($\ge 31$ years old) drops from $95\%$ to $65\%$.
           * Rubies Rangers applies the $\Omega_{\text{season}}$ discount factor to downweight rotation risks and prioritize bench order depth during festive congestion.
        """)
