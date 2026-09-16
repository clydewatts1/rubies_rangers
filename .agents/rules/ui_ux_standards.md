# UI/UX & Dashboard Engineering Standards: The Quant Trading Desk

This rule governs the visual design, user experience, architectural hierarchy, and component standards for the **Rubies Rangers** Streamlit application.

---

## 1. Core Philosophy: The Institutional Quant Trading Desk

Rubies Rangers is **not** a casual fantasy football game; it is an **institutional quantitative sports hedge fund** operating across discrete trading periods under capital constraints and asymmetric payoffs.

The dashboard must reflect this identity through an **Institutional Quant Trading Desk** aesthetic:
- **Surface & Hierarchy**: High-contrast, sleek financial dark mode (`#0b0f19` canvas, `#111827` cards, `#1f2937` borders).
- **Color Semantics**:
  - 🟢 **Alpha / Positive Yield**: Emerald green (`#10b981`, `#34d399`).
  - 🔵 **Execution / Telemetry / Signal**: Cybernetic blue (`#38bdf8`, `#60a5fa`).
  - 🟡 **Option / Capacity / Delay**: Amber gold (`#f59e0b`, `#fbbf24`).
  - 🔴 **Concession / Risk / Penalty**: Crimson red (`#ef4444`, `#f87171`).
- **Dual-Aspect Visualization**: Every primary squad view provides both:
  1. **Tactical Pitch View**: Visual spatial formation (3-5-2, 4-3-3, etc.) on dark turf for human football checks (starters, bench order, armbands).
  2. **Quantitative Distribution & Risk Deck**: Asset allocation tables, covariance correlations, and Monte Carlo probability density curves ($P_{10}, P_{50}, P_{99}$).

---

## 2. Two-Tier Hierarchical Navigation (5 Operational Trading Desks)

To eliminate decision fatigue and avoid navigation bloat, workflows are strictly partitioned into **5 Operational Trading Desks**:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        PERSISTENT PORTFOLIO TICKER TAPE                                │
│ [AUM: £104.2m]  •  [Bank (CIB): £1.5m]  •  [Options: 2 Banked FTs]  •  [Beta: 0.94]   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **📈 Desk 1: Portfolio & Balance Sheet Desk**
   - *Portfolio Holdings & Tactical Pitch Deck*
   - *5-GW Strategic Transfer Chessboard*
   - *Dynamic Balance Sheet (Team Value J-Curve & Real Options)*
   - *Squad Rebalancing & Transfer Execution*
   - *Chip Execution Roadmap & Dynamic Pricing*
   - *Mini-League Scout & Rival Portfolio Spy*

2. **⚔️ Desk 2: Quantitative Solvers & Optimization Desk**
   - *Two-Stage MILP Knapsack Solver (Screen & Simulate)*
   - *10,000-Path Monte Carlo Simulation Deck*
   - *Tail-Risk & Sharpe Ratio Optimizer ($P_{10}/P_{50}/P_{99}$)*
   - *15-Man Optimal Squad Draft Architecture*

3. **🎯 Desk 3: FPL Challenge Tournament Desk**
   - *Weekly Challenge Two-Stage Solver (Archetype Selection)*
   - *Rolling Deadline & Matchday Lock Tracker*
   - *Autonomous Challenge CPN Pipeline*

4. **🤖 Desk 4: Autonomous Operations & CPN Desk**
   - *Fantasy Coloured Petri Net (CPN) Robotic Manager*
   - *Challenge Coloured Petri Net (CPN) Autonomous Runner*
   - *Self-Healing Saga Verification & Retry Inspector*
   - *Suggestion & Outcome Audit Ledger*

5. **📡 Desk 5: Alpha Signals & Market Intelligence**
   - *Bookmaker Poisson Odds & Implied xP*
   - *Understat Shot Quality & Tactical Process*
   - *Match-by-Match Trend Engine*
   - *Weather Radar & Aerodynamic Intelligence*
   - *Venue Impact & Home/Away Analysis*
   - *Set-Piece & Penalty Hierarchy*
   - *Player Explorer & Factor Radar*

---

## 3. The Canonical 4-Zone Page Anatomy

Every single view in `ui/tabs/` must conform strictly to the following 4-zone structure:

```text
+-------------------------------------------------------------------------------+
| ZONE 1: TERMINAL HEADER & MISSION BRIEFING                                    |
| [Icon + View Title]  |  [Mathematical Formula / Thesis]  |  [Status Badges]   |
+-------------------------------------------------------------------------------+
| ZONE 2: UNIFIED KPI TELEMETRY STRIP                                           |
| [Metric 1: Expected Yield] [Metric 2: Downside P10] [Metric 3: Capacity] ...   |
+-------------------------------------------------------------------------------+
| ZONE 3: STRATEGY & ORDER EXECUTION DECK                                       |
| [Param 1: Scenario] | [Param 2: Objective] | [Param 3: Bounds] | [EXECUTE]    |
+-------------------------------------------------------------------------------+
| ZONE 4: DUAL-ASPECT DEEP DATA & VISUAL INSPECTOR                              |
| [Tab A: Pitch / Plotly Chart] | [Tab B: Asset Matrix] | [Tab C: Saga Audit]   |
+-------------------------------------------------------------------------------+
```

### Prohibited UX Patterns:
1. **Sidebar Bleed Anti-Pattern**: Never inject tab-specific sliders, number inputs, or action buttons into the sidebar. The sidebar is reserved exclusively for global brand, manager authentication, strategy profile, and desk navigation.
2. **Raw HTML Sprawl Anti-Pattern**: Do not embed inline HTML `<div style="...">` blocks with ad-hoc colors across individual tabs. Use atomic primitives in `ui/components/`.
3. **Un-Namespaced State Keys**: All `st.session_state` keys must follow the pattern `f"{desk_slug}_{view_slug}_{param_name}"` to avoid cross-tab state contamination.

---

## 4. Reusable UI Component Library (`ui/components/`)

All dashboard presentation logic must utilize standardized components:
- `render_portfolio_ticker(session_info)`: Top ticker displaying AUM, Cash-in-Bank, FT options, active profile, and target gameweek.
- `render_terminal_header(title, subtitle, badges)`: Uniform Zone 1 header with title, quantitative subtitle, and status pill badges.
- `render_kpi_strip(metrics)`: 4–5 column metric strip with formatted values, units, and deltas.
- `render_quant_table(df, hide_index=True)`: High-contrast data table with currency, percentage, and point formatting.
- `render_saga_receipt(receipt)`: Standardized transaction receipt card for verified CPN submissions.

---

## 5. Modern Streamlit & Forward-Compatibility Standards

- **Container Widths**: Never use deprecated `use_container_width=True` on buttons, metrics, or tables where modern Streamlit warns. Wrap containers cleanly or use forward-compatible parameters.
- **Defensive Data Handling**: Always handle empty datasets, unauthenticated manager sessions, and API fallbacks gracefully with clear UI info/warning banners instead of unhandled Python exceptions.
