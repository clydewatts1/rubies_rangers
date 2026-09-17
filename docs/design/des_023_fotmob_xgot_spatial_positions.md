---
type: Design
title: "[#023] FotMob REST Client for xGOT Finishing Skill & Spatial Pitch Positions - Detailed Design"
description: "Architecture and mathematical specification for consuming FotMob public endpoints, calculating Finishing Skill Delta (xGOT - xG), detecting out-of-position deployments, and verifying pre-kickoff lineups."
tags: [design, architecture, python, fotmob, xgot, finishing, lineups, spatial, analytics, xp]
status: Active
sources: ["docs/issues/iss_023_fotmob_xgot_spatial_positions.md"]
generated:
  at: "2026-09-17T21:31:00Z"
  by: "agent:design-facilitator"
---

# Design [#023]: FotMob REST Client for xGOT Finishing Skill & Spatial Pitch Positions

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_ISSUE_READY`
> - **Current Transition**: `T_DESIGN`
> - **Next Place**: `P_DESIGN_READY`
> - **CPN Lineage**: Issue [#023] -> Design [des_023] -> Tasks [tsk_023] -> Playbook [plb_023]
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Origin Issue**: [`docs/issues/iss_023_fotmob_xgot_spatial_positions.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/issues/iss_023_fotmob_xgot_spatial_positions.md)
> - **Downstream Consumers**: `tsk_023`, `plb_023`, `clients/fotmob_client.py`, `analytics/xp_model.py`
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:des_023_fotmob_xgot_spatial_positions`

---

## 1. Purpose & Scope

### 1.1 Purpose
Standard expected goals ($xG$) models chance quality strictly prior to ball impact (distance, angle, defender pressure). However, an elite striker placed in an average chance can dramatically elevate conversion through shot placement, velocity, and disguise. **Expected Goals on Target ($xGOT$)** measures post-shot probability based on trajectory and corner placement.

The differential $\Delta_{\text{finish}} = xGOT - xG$ serves as the definitive forward metric separating clinical ball-strikers (e.g. Son, Haaland, Saka) from wasteful volume shooters. Additionally, FotMob provides verified matchday lineups 60 to 75 minutes before kickoff, giving Rubies Rangers real-time starting confirmation before FPL deadlines lock.

### 1.2 In Scope
- **`clients/fotmob_client.py`**: A client consuming FotMob's public data endpoints (`data.fotmob.com`) and Next.js page state.
- **Finishing Skill Delta ($\Delta_{\text{finish}}$)**: Calculation of $xGOT - xG$ across all Premier League attacking assets.
- **Goalkeeper Goals Prevented**: Ingestion of FotMob's post-shot goalkeeper prevention stats (`_goals_prevented.json`).
- **Pre-Kickoff Lineup Verification**: Querying confirmed starters for gameweek matches.
- **Integration with `analytics/xp_model.py`**: Wiring $\Delta_{\text{finish}}$ directly into `XPModel`'s forward metrics finishing multiplier.
- **Local Disk Caching**: 24-hour TTL cache at `.fotmob_cache.json`.

### 1.3 Out of Scope
- Real-time live websocket match tracking during match play (Rubies Rangers operates pre-deadline).
- Commercial paid FotMob pro API accounts (strictly free public endpoints).

---

## 2. Mathematical & Quantitative Formalisms

### 2.1 Finishing Skill Delta ($\Delta_{\text{finish}}$)
For each attacking player $i$:
$$\Delta_{\text{finish}, i} = xGOT_i - xG_i$$

Where:
- $\Delta_{\text{finish}, i} > 0$: The player consistently places shots into difficult-to-save zones (upper corners, side netting), upgrading raw chance quality into goals.
- $\Delta_{\text{finish}, i} < 0$: The player sprays shots wide or fires directly at the goalkeeper's torso, degrading raw chance quality.

### 2.2 Forward Finishing Multiplier Calibration
In `XPModel`, the forward metrics system adjusts base expected goals using finishing skill:
$$\gamma_{\text{finish}, i} = 1.0 + \text{clip}\left( 0.10 \cdot \Delta_{\text{finish}, i}, -0.15, +0.20 \right)$$

This multiplier directly scales the player's match expected goals $xG_{\text{match}, i}$ in `XPModel`:
$$xG_{\text{effective}, i} = xG_{\text{match}, i} \cdot \gamma_{\text{finish}, i}$$

### 2.3 Out-of-Position (OOP) Tactical Flag
When a player's listed FPL position differs from their actual tactical deployment in FotMob confirmed lineups:
- Nominal Defender starting as Midfielder / Winger: Attacking threat multiplier $\gamma_{\text{OOP}} = 1.25$.
- Nominal Midfielder starting as Central Striker: Attacking threat multiplier $\gamma_{\text{OOP}} = 1.15$.

---

## 3. Component Architecture & Data Contracts

### 3.1 Data Contracts (`clients/fotmob_client.py`)

```python
@dataclass(frozen=True)
class FotMobPlayerStats:
    """Player finishing and performance metrics from FotMob."""
    web_name: str
    team_name: str
    team_code: str
    xg: float
    xgot: float
    finishing_delta: float      # xGOT - xG
    goals_prevented: float      # For GKs
    save_pct: float             # For GKs
    as_of_timestamp: float

@dataclass(frozen=True)
class FotMobLineup:
    """Confirmed matchday lineup record."""
    match_id: str
    home_team: str
    away_team: str
    home_starters: List[str]    # Player names
    away_starters: List[str]    # Player names
    home_formation: str
    away_formation: str
    is_confirmed: bool
```

### 3.2 Ingestion Architecture
- **Primary Endpoint**: High-speed static JSON endpoints on `https://data.fotmob.com/stats/47/season/36781/`:
  - `expected_goalsontarget.json`
  - `expected_goals.json`
  - `_goals_prevented.json`
  - `_save_percentage.json`
- **Lineup Verification**: `https://www.fotmob.com/matches/<slug>/<id>` Next.js page state.
- **Disk Cache**: `.fotmob_cache.json` with a 24-hour TTL and fallback starter dictionary (`BASELINE_FOTMOB_STATS`).

---

## 4. Verification & Pytest Plan

- **`test_finishing_delta_calculation`**: Verifies accurate derivation of $\Delta_{\text{finish}} = xGOT - xG$ and finishing multiplier boundaries $[-15\%, +20\%]$.
- **`test_fotmob_dataclass_immutability`**: Ensures frozen contract integrity.
- **`test_fotmob_caching_and_ttl`**: Tests 24-hour disk cache loading without external queries.
- **`test_xp_model_fotmob_finishing_integration`**: Verifies that clinical finishers (Haaland, Saka) receive elevated goal expectations in `XPModel`.
