---
type: Playbook
title: "[#024] Premier League Referee Historical Analytics & Penalty Tendency Modeling - Operational Playbook"
description: "Operational playbook and architectural store for referee historical analytics, penalty award rate multipliers, card accumulation tendencies, and XP/Monte Carlo engine integration."
tags: [playbook, python, referee, penalties, cards, montecarlo, analytics, xp]
status: Active
sources: ["docs/design/des_024_referee_penalty_variance_modeling.md"]
generated:
  at: "2026-09-17T21:40:00Z"
  by: "agent:playbook-facilitator"
---

# Playbook [#024]: Premier League Referee Historical Analytics & Penalty Tendency Modeling

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Operations & Maintenance**
> - **Origin Place**: `P_VERIFICATION`
> - **Current Transition**: `T_PLAYBOOK`
> - **Next Place**: `P_COMMITTED_PLAYBOOK`
> - **CPN Lineage**: Issue [#024] -> Design [des_024] -> Tasks [tsk_024] -> Code [P_VERIFICATION] -> Playbook [plb_024]
> - **Origin Design**: [`docs/design/des_024_referee_penalty_variance_modeling.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_024_referee_penalty_variance_modeling.md)
> - **Origin Issue**: [`docs/issues/iss_024_referee_penalty_variance_modeling.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/issues/iss_024_referee_penalty_variance_modeling.md)
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:plb_024_referee_penalty_variance_modeling`

---

## 1. Architectural Store & Design Decisions (The Why)

### 1.1 Beyond Homogenous Penalty Assumptions
In standard FPL predictive engines, penalty events are assumed to occur at a flat, homogenous rate ($18\%$). However, empirical Premier League officiating data demonstrates substantial variance across Select Group 1 referees:
1. **Spot-Kick Tendency Variance**: Officials like Robert Jones ($0.38$) and Anthony Taylor ($0.36$) award penalties at nearly double the rate of conservative officials like Paul Tierney ($0.15$) and Andrew Madley ($0.16$). For designated penalty takers (e.g., Erling Haaland, Bukayo Saka, Mohamed Salah), referee appointments represent high-conviction alpha signals.
2. **Disciplinary Strictness & Tail Risk**: Referees like Peter Bankes ($4.70$ yellows/match) and Robert Jones ($4.60$ yellows/match) systematically depress baseline BPS scoring ($-3$ BPS per yellow card) and elevate red card hazards ($-3$ FPL points and clean sheet invalidation).

### 1.2 Mathematical Formulation

1. **Referee Penalty Multiplier**:
   $$\mu_{\text{pen}, R} = \text{clip}\left( \frac{\rho_R}{\bar{\rho}_{\text{league}}}, 0.65, 1.85 \right)$$
   $$\text{pen\_award}_{\text{eff}} = P_{\text{award, base}} \cdot \mu_{\text{pen}, R}$$
   $$\text{pen\_bonus\_xg}_i = \text{pen\_conv} \cdot \text{pen\_award}_{\text{eff}}$$

2. **Excess Disciplinary Card Variance Deduction**:
   $$\Delta_{\text{cards}} = \left( \frac{Y_R - \bar{Y}}{22.0} \cdot 1.0 + \frac{K_R - \bar{K}}{22.0} \cdot 3.0 \right) \cdot \left(\frac{\text{mins}}{90}\right)$$
   Centering deductions on deviation from league baseline avoids penalizing players doubly for standard league play while accurately pricing excess referee strictness.

3. **Monte Carlo Disciplinary Scaling**:
   $$P(\text{YC}_i) = \min\left(P_{\text{max}}, P_{\text{base}} \cdot \mu_{\text{venue}} \cdot \mu_{\text{YC}, R}\right)$$
   $$P(\text{RC}_i) = \min\left(0.50, P_{\text{RC, base}} \cdot \mu_{\text{venue}} \cdot \mu_{\text{RC}, R}\right)$$

---

## 2. Implemented Reality & Primary Modules

```text
rubies_rangers/
├── data/
│   └── referee_tendencies.json           # Curated historical statistical profiles & appointments
├── clients/
│   └── referee_client.py                 # Referee profile parser, multipliers, and baseline fallback
├── analytics/
│   ├── xp_model.py                       # XPModel penalty taker & disciplinary modulation
│   └── montecarlo.py                     # MonteCarloEngine stochastic penalty & card scaling
└── tests/
    └── test_referee_client.py            # 16 unit and integration tests
```

### 2.1 Key Classes & Functions (`clients/referee_client.py`)
- `RefereeProfile`: Frozen dataclass containing `name`, `matches_refereed`, `penalties_per_match`, `yellows_per_match`, `reds_per_match`, `fouls_per_tackle`, `penalty_multiplier`, `yellow_multiplier`, `red_multiplier`, and `card_risk_tier`.
- `compute_referee_penalty_multiplier()`: Vector-ready formula computing $\rho_R / \bar{\rho}_{\text{league}}$, clamped between $[0.65, 1.85]$.
- `compute_referee_yellow_multiplier()`, `compute_referee_red_multiplier()`: Clamped disciplinary scalers.
- `RefereeClient`: High-speed client matching teams/fixtures to appointed officials with zero external network overhead and automatic fallback to `LEAGUE_BASELINE_PROFILE`.

---

## 3. Operational Verification & Telemetry

### 3.1 Verification Commands
```bash
# Run referee test suite
python -m pytest tests/test_referee_client.py -v

# Run full cross-client regression test suite (all 6 data sources)
python -m pytest tests/test_clubelo_client.py tests/test_odds_client.py tests/test_injury_client.py tests/test_fbref_client.py tests/test_fotmob_client.py tests/test_referee_client.py -v
```

### 3.2 Telemetry Outputs in `XPModel.calculate_player_xp()`
- `referee_name`: Display name of appointed match official.
- `referee_penalty_multiplier`: Penalty award rate scalar applied to designated taker.
- `referee_card_risk_tier`: Qualitative strictness label (`"LOW"`, `"MODERATE"`, `"ELEVATED"`, `"EXTREME"`).
