---
type: Design
title: "[#021] Automated Premier Injuries Scraper for Pre-Deadline Availability Intel - Detailed Design"
description: "Architecture and availability modeling for automated ingestion of Premier League injury intelligence, press conference status, and seamless integration with Shane's Domain Intel desk."
tags: [design, architecture, python, injuries, availability, intel, domain, xp]
status: Active
sources: ["docs/issues/iss_021_premier_injuries_automated_intel.md"]
generated:
  at: "2026-09-17T20:25:00Z"
  by: "agent:design-facilitator"
---

# Design [#021]: Automated Premier Injuries Scraper for Pre-Deadline Availability Intel

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_ISSUE_READY`
> - **Current Transition**: `T_DESIGN`
> - **Next Place**: `P_DESIGN_READY`
> - **CPN Lineage**: Issue [#021] -> Design [des_021] -> Tasks [tsk_021] -> Playbook [plb_021]
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Origin Issue**: [`docs/issues/iss_021_premier_injuries_automated_intel.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/issues/iss_021_premier_injuries_automated_intel.md)
> - **Downstream Consumers**: `tsk_021`, `plb_021`, `clients/injury_client.py`, `analytics/domain_intel.py`, `ui/`
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:des_021_premier_injuries_automated_intel`

---

## 1. Purpose & Scope

### 1.1 Purpose
A major vulnerability in weekly FPL optimization is **availability latency**. Official FPL flags (`status='d'`, `chance_of_playing_next_round=50`) often lag behind Friday afternoon manager press conferences by 12 to 24 hours. If an optimization solver runs before official flags update, it risks selecting a player who has already been confirmed out with a hamstring tear or illness.

This design implements an automated, zero-cost injury intelligence pipeline (`clients/injury_client.py`). It scrapes public Premier League injury tables and press conference reports in real time, normalizes player identities, maps raw clinical/press statuses into quantitative availability probabilities ($p_{\text{fit}}$), and feeds directly into Shane's Domain Intel desk (`analytics/domain_intel.py`).

### 1.2 In Scope
- **`clients/injury_client.py`**: A resilient HTTP scraper and parser fetching live Premier League injury tables across all 20 clubs.
- **Player Identity Resolution**: A fuzzy resolver mapping external player names ("Amine Adli", "Omar Alderete", "William Saliba") to official FPL element IDs and `web_name` attributes.
- **Availability Mapping Function ($\Phi$)**: Formal translation of injury statuses (`OUT`, `GTD`, `SUS`, `ILL`) into Shane's `AvailabilityOption` enums and numerical fitness probabilities $p_{\text{fit}} \in \{0.0, 0.25, 0.50, 0.75, 1.0\}$.
- **Integration with `ShaneIntelManager`**: Automated translation into `PlayerOverride` records with 1-Gameweek TTL governance.
- **Local Disk Cache**: `.injury_cache.json` with a 2-hour TTL to respect host bandwidth and provide instant offline operation.

### 1.3 Out of Scope
- Direct medical diagnosis validation (we consume reported public data as-is).
- Paid subscription scraping (strictly 100% free open-web endpoints).

---

## 2. Mathematical & Quantitative Formalisms

### 2.1 The Availability Transfer Function $\Phi$
Let $S \in \{\text{OUT}, \text{SUS}, \text{GTD}, \text{FIT}\}$ represent the raw reported status, and $T_{\text{inj}}$ represent the diagnosis category (e.g. `Hamstring`, `Calf`, `Knee`, `Illness`).
We define the mapping:
$$\Phi(S, T_{\text{inj}}) \longrightarrow (\text{AvailabilityOption}, p_{\text{fit}})$$

$$\Phi(S, T_{\text{inj}}) = \begin{cases}
(\text{CONFIRMED\_OUT\_0}, 0.00) & \text{if } S \in \{\text{OUT}, \text{SUS}\} \\
(\text{HEAVY\_DOUBT\_25}, 0.25) & \text{if } S = \text{GTD} \land T_{\text{inj}} \in \{\text{Hamstring}, \text{Groin}, \text{Knee}\} \\
(\text{COIN\_FLIP\_50}, 0.50) & \text{if } S = \text{GTD} \land T_{\text{inj}} \in \{\text{Knock}, \text{Illness}, \text{Undisclosed}\} \\
(\text{MILD\_DOUBT\_75}, 0.75) & \text{if } S = \text{GTD} \land T_{\text{inj}} \in \{\text{Lack of Match Fitness}\} \\
(\text{CLEARED\_FIT\_100}, 1.00) & \text{if } S = \text{FIT}
\end{cases}$$

### 2.2 Expected Points Adjustment Under Injury Risk
Under Shane's domain metrics framework, the expected points $\mathbb{E}[\text{xP}_i]$ for player $i$ is conditioned on fitness:
$$\mathbb{E}[\text{xP}_i] = p_{\text{fit}, i} \cdot \left( \frac{\min(\hat{m}_i, 90)}{90} \right) \cdot \text{xP}_{\text{base}, i} \cdot \gamma_{\text{eye}, i}$$

Where:
- For $p_{\text{fit}, i} = 0.00$ (`CONFIRMED_OUT_0`), the player is assigned status `'u'`, forcing the mixed-integer linear programming (MILP) selection binary $x_i = 0$.
- For $0.0 < p_{\text{fit}, i} < 1.0$, the down-weighted expected points naturally penalize borderline picks during transfers and starting XI selection without requiring arbitrary manual hit bans.

---

## 3. Data Contracts & Architecture

### 3.1 Data Contracts (`clients/injury_client.py`)

```python
@dataclass(frozen=True)
class RawInjuryRecord:
    """Raw scraped record from injury table."""
    source_id: str
    player_name: str
    team_code: str          # 3-letter FPL code: ARS, MCI, LIV, etc.
    position: str           # F/M, D, G, etc.
    injury_type: str        # Hamstring, Calf, Knee, etc.
    raw_status: str         # OUT, GTD, SUS
    return_date_desc: str   # Text or estimate

@dataclass(frozen=True)
class ProcessedInjuryIntel:
    """Normalized, FPL-resolved injury intelligence."""
    fpl_element_id: Optional[int]
    web_name: str
    full_name: str
    team_code: str
    injury_type: str
    availability: AvailabilityOption
    p_fit: float
    expected_minutes: float
    news_snippet: str
    as_of_timestamp: float
```

### 3.2 Ingestion & Tiered Topology

```text
       [ Live RotoWire / EPL Injury Table ] (Tier 1)
                       │
                       ▼ (HTTP GET / Cache check)
             [ InjuryClient Parser ]
                       │
                       ├─► Normalizes Team Code (20 EPL clubs)
                       ├─► Fuzzy Resolves Player Name -> FPL Element ID / web_name
                       └─► Computes AvailabilityOption & p_fit via Φ
                       │
                       ▼
             [ ProcessedInjuryIntel ]
                       │
                       ├─► Persists to .injury_cache.json (2-hr TTL)
                       │
                       ▼
             [ ShaneIntelManager ] (analytics/domain_intel.py)
                       │
                       ├─► auto_sync_injury_overrides(current_gw)
                       └─► apply_pre_stage1_overrides(df, current_gw)
                               │
                               ▼
                    [ MILP Squad Optimizer ]
```

---

## 4. Name Resolution Engine

To map arbitrary strings like `"Amine Adli"`, `"William Saliba"`, or `"Diogo Jota"` to FPL element records:
1. **Direct Exact Match**: Exact case-insensitive match on `first_name + " " + second_name`.
2. **Direct Web Name Match**: Match on `web_name` (e.g., `"Saliba"`, `"Haaland"`).
3. **Normalized Token Match**: Stripping accents, special characters, and matching `(team_code, last_name)`.
4. **Fallback Unresolved**: If confidence is below threshold, record is tagged with `fpl_element_id = None` and held for manual inspection.

---

## 5. Verification & Test Plan

- **`test_injury_mapping_phi`**: Validates status and injury type categorization into `AvailabilityOption` and $p_{\text{fit}}$ values.
- **`test_player_name_resolution`**: Tests exact, web_name, and token-based player identity resolution against FPL bootstrap data.
- **`test_cache_persistence_and_ttl`**: Verifies `.injury_cache.json` reads and 2-hour TTL expiration.
- **`test_shane_intel_sync_overrides`**: Verifies automated creation of `PlayerOverride` objects in `ShaneIntelManager` with `valid_gameweek` and `CURRENT_GW_ONLY` TTL window.
- **`test_offline_fallback`**: Tests graceful operation and empty return when network is unreachable.
