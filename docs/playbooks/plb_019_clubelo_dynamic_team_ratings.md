---
type: Playbook
title: "[#019] ClubElo API Dynamic Team Ratings & Bivariate Poisson Goals Engine - Operational Playbook"
description: "Offline context memory and operational store for ClubElo dynamic ratings, Poisson goal expectations, and automated fixture strength."
tags: [playbook, python, clubelo, ratings, poisson, analytics, client]
status: Active
sources: ["docs/design/des_019_clubelo_dynamic_team_ratings.md"]
generated:
  at: "2026-09-17T20:15:00Z"
  by: "agent:playbook-facilitator"
---

# Playbook [#019]: ClubElo API Dynamic Team Ratings & Bivariate Poisson Goals Engine

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Operations & Maintenance**
> - **Origin Place**: `P_VERIFICATION`
> - **Current Transition**: `T_PLAYBOOK`
> - **Next Place**: `P_COMMITTED_PLAYBOOK`
> - **CPN Lineage**: Issue [#019] -> Design [des_019] -> Tasks [tsk_019] -> Code [P_VERIFICATION] -> Playbook [plb_019]
> - **Origin Design**: [`docs/design/des_019_clubelo_dynamic_team_ratings.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_019_clubelo_dynamic_team_ratings.md)
> - **Origin Issue**: [`docs/issues/iss_019_clubelo_dynamic_team_ratings.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/issues/iss_019_clubelo_dynamic_team_ratings.md)
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:plb_019_clubelo_dynamic_team_ratings`

---

## 1. Architectural Store & Design Decisions (The Why)

### 1.1 Rationale for ClubElo over FPL Official FDR
Official FPL Fixture Difficulty Ratings (FDR 1–5) suffer from severe analytical deficiencies:
1. **Coarse Resolution**: Only 5 integer steps; treats Man City at home the same as Chelsea at home.
2. **Lagging Human Bias**: Static editorial assignments set in August that do not update after tactical collapse or managerial changes.
3. **Absence of Expected Goals**: FDR cannot yield a mathematically rigorous clean sheet probability or goal arrival rate.

**Design Decision**: ClubElo provides daily-updated objective Elo ratings based strictly on match margins of victory and opponent quality. Mapping $\Delta \text{Elo}$ directly into bivariate Poisson arrival rates eliminates manual odds maintenance and provides continuous fixture difficulty for all 38 gameweeks.

### 1.2 Mathematical Formulation
- **Home Advantage**: $H_a = +75.0$ Elo points.
- **Differential**: $\Delta \text{Elo}_H = \text{Elo}_H + 75.0 - \text{Elo}_A$.
- **Poisson Arrival Rate**:
  $$\lambda_H = 1.36 \cdot \exp(0.00231 \cdot \Delta \text{Elo}_H), \quad \lambda_A = 1.36 \cdot \exp(-0.00231 \cdot \Delta \text{Elo}_H)$$
- **Clean Sheet Probability**: $P(\text{CS}_H) = \exp(-\lambda_A), \quad P(\text{CS}_A) = \exp(-\lambda_H)$.
- **Physical Safety Bounds**: Enforced clipping $\lambda \in [0.40, 3.85]$ to prevent runaway captaincy solver scores during blowout mismatches.

---

## 2. Implemented Reality & Primary Modules

```text
rubies_rangers/
├── clients/
│   └── clubelo_client.py                 # Core ClubElo HTTP client, scraper, cache, & Poisson engine
├── analytics/
│   ├── xp_model.py                       # XPModel._build_team_odds_map() with ClubElo integration
│   └── strategic/
│       └── trajectory_engine.py          # Multi-horizon schedule profiles with dynamic Elo strength
└── tests/
    └── test_clubelo_client.py            # Unit tests covering contracts, formulas, and offline fallback
```

### Key Contracts (`clients/clubelo_client.py`)
- `ClubEloRecord`: Immutable frozen dataclass capturing raw rating data (`club_name`, `fpl_code`, `elo`, `rank`, `as_of_timestamp`).
- `FixtureExpectancy`: Immutable frozen contract holding Poisson parameters $(\lambda_H, \lambda_A)$, clean sheet probabilities, and decimal odds.
- `ClubEloClient`: Thread-safe client providing `get_epl_ratings()`, `compute_fixture_expectancy()`, and `build_team_odds_map()`.

---

## 3. Implementation Drift & Edge-Case Adaptations (Real-World vs. Design Spec)

During live deployment, a critical discrepancy between the initial specification and network reality was discovered and resolved:

> [!NOTE]
> **Implementation Drift: API Subdomain 502 vs. Direct Table Scraping**
> - **Initial Design**: Intended to query `http://api.clubelo.com/` for raw CSV.
> - **Runtime Reality**: The `api.clubelo.com` subdomain consistently returns `HTTP 502 Bad Gateway` from Microsoft-IIS under corporate network environments.
> - **Adopted Architecture**: `ClubEloClient` was augmented with a multi-tier ingestion fallback:
>   1. **Primary**: Scrapes `https://clubelo.com/ENG` (Table 6), parsing all 20 Premier League and Championship clubs via robust regex extraction: `r'^(\d+)?([A-Z]{3})(.+)$'`. This endpoint is fast ($\sim 1.5\text{s}$), returns clean HTML, and bypasses the 502 error completely.
>   2. **Secondary**: Attempts `http://api.clubelo.com/` CSV.
>   3. **Tertiary**: Reads stale disk cache from `.clubelo_cache.json` (24-hour TTL).
>   4. **Quaternary**: Built-in hardcoded `BASELINE_EPL_ELO` dictionary ensuring 100% crash immunity even in total offline/airplane mode.

---

## 4. Operational Guide & Usage

### 4.1 CLI Validation & Interactive Testing
To test the ClubElo client and compute fixture expectancies from the command line:

```bash
# Test ratings ingestion
python -c "from clients.clubelo_client import ClubEloClient; c = ClubEloClient(); print(len(c.get_epl_ratings()))"

# Test specific fixture Poisson calculation
python -c "from clients.clubelo_client import ClubEloClient; c = ClubEloClient(); print(c.compute_fixture_expectancy('MCI', 'NFO'))"

# Verify dynamic XPModel generation for any target Gameweek
python -c "from analytics.xp_model import XPModel; xm = XPModel(gameweek=5); print(xm.team_odds['ARS'])"
```

### 4.2 Force Cache Refresh
Elo ratings update once daily following completed matches. To force an immediate refresh bypassing the 24-hour TTL:

```python
from clients.clubelo_client import ClubEloClient
client = ClubEloClient()
fresh_ratings = client.get_epl_ratings(force_refresh=True)
```

---

## 5. Troubleshooting & Diagnostics

| Symptom / Failure Mode | Root Cause | System Behavior | Resolution |
| :--- | :--- | :--- | :--- |
| **ClubElo Website Down (503/Timeout)** | Remote server outage | Client automatically serves `.clubelo_cache.json` if available, or falls back to `BASELINE_EPL_ELO`. No crash occurs. | None needed. System logs a warning and continues with calibrated baseline. |
| **New Promoted Club (Alias Miss)** | Promoted club uses variant spelling | Unrecognized club falls back to league median Elo ($1800.0$). | Add alias mapping to `CLUBELO_TO_FPL` in [`clients/clubelo_client.py`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/clients/clubelo_client.py). |
| **Cache Corruption** | Corrupt JSON in `.clubelo_cache.json` | Client catches `json.JSONDecodeError`, logs warning, and refetches from network. | Delete `.clubelo_cache.json` to allow clean regeneration. |

---

## 6. Verification Status
- **Test Suite**: [`tests/test_clubelo_client.py`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/tests/test_clubelo_client.py) (7/7 tests passed in 2.97s).
- **Regression Suite**: 26 integration tests across `test_analytics.py`, `test_strategic_wave_scanner.py`, `test_strategic_two_stage.py`, and `test_two_stage_optimizer.py` passed with 0 regressions.
