---
type: Playbook
title: "[#021] Automated Premier Injuries Scraper for Pre-Deadline Availability Intel - Operational Playbook"
description: "Operational playbook and architectural store for live Premier League injury intelligence, availability transfer mapping, player identity resolution, and domain intel sync."
tags: [playbook, python, injuries, availability, intel, domain, client]
status: Active
sources: ["docs/design/des_021_premier_injuries_automated_intel.md"]
generated:
  at: "2026-09-17T20:26:00Z"
  by: "agent:playbook-facilitator"
---

# Playbook [#021]: Automated Premier Injuries Scraper for Pre-Deadline Availability Intel

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Operations & Maintenance**
> - **Origin Place**: `P_VERIFICATION`
> - **Current Transition**: `T_PLAYBOOK`
> - **Next Place**: `P_COMMITTED_PLAYBOOK`
> - **CPN Lineage**: Issue [#021] -> Design [des_021] -> Tasks [tsk_021] -> Code [P_VERIFICATION] -> Playbook [plb_021]
> - **Origin Design**: [`docs/design/des_021_premier_injuries_automated_intel.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_021_premier_injuries_automated_intel.md)
> - **Origin Issue**: [`docs/issues/iss_021_premier_injuries_automated_intel.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/issues/iss_021_premier_injuries_automated_intel.md)
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:plb_021_premier_injuries_automated_intel`

---

## 1. Architectural Store & Design Decisions (The Why)

### 1.1 Solving the Availability Latency Problem
Official Fantasy Premier League availability flags (`status='d'`, `chance_of_playing_next_round=50`) consistently lag behind Friday afternoon manager press conferences by 12 to 24 hours. Optimization runs executed before late Friday night routinely risk fielding players who have already been ruled out with soft-tissue injuries or international duty knocks.

### 1.2 Quantitative Formulation & Availability Mapping ($\Phi$)
The engine formalizes the transfer function $\Phi(\text{Status}, \text{InjuryType}) \rightarrow (\text{AvailabilityOption}, p_{\text{fit}})$:
- **`OUT` / `SUSPENDED`**: Assigned `AvailabilityOption.CONFIRMED_OUT_0` ($p_{\text{fit}} = 0.00$), automatically marking the player with `status='u'` to force MILP squad exclusion ($x_i = 0$).
- **`GTD` with Severe Soft-Tissue Injury** (`Hamstring`, `Knee`, `Groin`): Assigned `AvailabilityOption.HEAVY_DOUBT_25` ($p_{\text{fit}} = 0.25$).
- **`GTD` with Minor Knock / Illness / Undisclosed**: Assigned `AvailabilityOption.COIN_FLIP_50` ($p_{\text{fit}} = 0.50$).
- **`GTD` with Match Fitness / Fatigue**: Assigned `AvailabilityOption.MILD_DOUBT_75` ($p_{\text{fit}} = 0.75$).
- **`CLEARED` / `FIT`**: Assigned `AvailabilityOption.CLEARED_FIT_100` ($p_{\text{fit}} = 1.00$).

Expected minutes and points scale monotonically:
$$\mathbb{E}[\text{xP}_i] = p_{\text{fit}, i} \cdot \left( \frac{\min(\hat{m}_i, 90)}{90} \right) \cdot \text{xP}_{\text{base}, i} \cdot \gamma_{\text{eye}, i}$$

---

## 2. Implemented Reality & Primary Modules

```text
rubies_rangers/
├── clients/
│   └── injury_client.py                  # Live scraper, name resolver, Φ mapping, and caching engine
├── analytics/
│   └── domain_intel.py                   # ShaneIntelManager.sync_injury_intel() bridging into 1-GW TTL overrides
├── ui/tabs/
│   └── tab_domain_intel.py               # Streamlit "Sync Premier Injuries" action button
└── tests/
    └── test_injury_client.py             # 11 unit & integration tests
```

### Key Contracts (`clients/injury_client.py`)
- `RawInjuryRecord`: Immutable frozen dataclass capturing raw player records (`source_id`, `player_name`, `team_code`, `position`, `injury_type`, `raw_status`, `return_date_desc`).
- `ProcessedInjuryIntel`: Immutable frozen contract holding resolved FPL element ID, web name, full name, availability option enum, fitness probability $p_{\text{fit}}$, expected minutes, and news snippet.
- `InjuryClient`: Thread-safe client providing `get_injury_intel()`, `get_injury_intel_by_web_name()`, `resolve_player()`, and `sync_to_shane_intel()`.

---

## 3. Implementation Drift & Edge-Case Adaptations (Real-World vs. Design Spec)

1. **Cloudflare Evasion: Direct HTML vs. RotoWire EPL Live Table Endpoint**:
   - `premierinjuries.com` deploys Cloudflare browser challenges on direct Python requests (`HTTP 403`).
   - Rather than introducing heavy headless browser dependencies (e.g. Playwright or Selenium), `InjuryClient` connects to the open, public EPL injury feed table at `https://www.rotowire.com/soccer/tables/injury-report.php?league=EPL`.
   - This endpoint returns structured JSON for all 100+ active Premier League injuries across all 20 clubs directly, with native FPL 3-letter team codes (`ARS`, `MCI`, `LIV`, etc.) in $< 0.8\text{s}$.

2. **Special Latin Character Transliteration**:
   - Standard Unicode decomposition (`NFKD`) does not decompose non-combining characters like Scandinavian `Ø`/`ø`, German `ß`, or Slavic `Ł`/`ł`.
   - `normalize_text()` implements an explicit pre-transliteration step (`Ø` $\rightarrow$ `O`, `ø` $\rightarrow$ `o`, `æ` $\rightarrow$ `ae`, `ß` $\rightarrow$ `ss`), preventing name resolution dropouts for players like Martin Ødegaard or Marc Guéhi.

---

## 4. Operational Guide & Usage

### 4.1 Diagnostic Commands
```bash
# Retrieve live injury count and view first 5 records
python -c "from clients.injury_client import InjuryClient; c = InjuryClient(); intel = c.get_injury_intel(); print(f'Active injuries: {len(intel)}'); [print(' ', i.web_name, '|', i.team_code, '|', i.injury_type, '|', i.availability.value) for i in intel[:5]]"

# Test name resolution for specific player
python -c "from clients.injury_client import InjuryClient; c = InjuryClient(); print(c.resolve_player('William Saliba', 'ARS'))"

# Sync active squad injuries into Shane's Domain Intel
python -c "from analytics.domain_intel import ShaneIntelManager; sm = ShaneIntelManager(); print('Synced overrides:', sm.sync_injury_intel(current_gw=4))"
```

### 4.2 Interactive UI
In the Streamlit dashboard under **Shane's Domain Intel Desk**, click **"🏥 Sync Premier Injuries"** to automatically populate overrides for all injured squad members with 1-Gameweek TTL governance.

---

## 5. Test Coverage & Verification Matrix

The test suite in [`tests/test_injury_client.py`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/tests/test_injury_client.py) verifies:
- `test_map_injury_status_confirmed_out`: Confirmed out/suspension mapping to 0.0% fitness.
- `test_map_injury_status_gtd_severe`: Severe soft-tissue doubts mapped to 25.0%.
- `test_map_injury_status_gtd_minor_or_illness`: Minor knocks and illnesses mapped to 50.0%.
- `test_map_injury_status_gtd_mild`: Fatigue / match fitness mapped to 75.0%.
- `test_map_injury_status_cleared`: Fit status mapped to 100.0%.
- `test_normalize_text`: Robust accent and special character transliteration.
- `test_player_resolution_mock_fpl`: Exact, web name, and token-based player resolution.
- `test_dataclass_contracts_immutable`: Verification of frozen dataclass contracts.
- `test_injury_client_caching`: Disk cache reads without network queries.
- `test_injury_client_fallback_to_fpl_elements`: Graceful fallback to FPL bootstrap elements when offline.
- `test_sync_to_shane_intel`: Automated creation of `PlayerOverride` records with 1-GW TTL and zero score setting in `apply_pre_stage1_overrides`.

All 11 tests execute in $< 1.9\text{s}$ with 100% pass rate.
