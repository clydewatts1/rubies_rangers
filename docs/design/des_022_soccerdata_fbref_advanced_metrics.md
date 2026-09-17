---
type: Design
title: "[#022] FBref / StatsBomb Integration via soccerdata for Goalkeeper PSxG and Attacking SCA/GCA - Detailed Design"
description: "Architecture and mathematical specification for extracting Post-Shot xG (PSxG) and Shot/Goal Creating Actions (SCA/GCA) via soccerdata to refine goalkeeper save points and outfield BPS bonus propensity."
tags: [design, architecture, python, soccerdata, fbref, goalkeeper, psxg, sca, gca, analytics, xp]
status: Active
sources: ["docs/issues/iss_022_soccerdata_fbref_advanced_metrics.md"]
generated:
  at: "2026-09-17T21:24:00Z"
  by: "agent:design-facilitator"
---

# Design [#022]: FBref / StatsBomb Integration via soccerdata for Goalkeeper PSxG and Attacking SCA/GCA

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_ISSUE_READY`
> - **Current Transition**: `T_DESIGN`
> - **Next Place**: `P_DESIGN_READY`
> - **CPN Lineage**: Issue [#022] -> Design [des_022] -> Tasks [tsk_022] -> Playbook [plb_022]
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Origin Issue**: [`docs/issues/iss_022_soccerdata_fbref_advanced_metrics.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/issues/iss_022_soccerdata_fbref_advanced_metrics.md)
> - **Downstream Consumers**: `tsk_022`, `plb_022`, `clients/fbref_client.py`, `analytics/xp_model.py`
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:des_022_soccerdata_fbref_advanced_metrics`

---

## 1. Purpose & Scope

### 1.1 Purpose
While Understat provides granular shot and key pass coordinates, it omits two indispensable dimensions of football performance:
1. **Goalkeeper Shot-Stopping Alpha (PSxG +/- per 90)**: Understat cannot discern whether a goalkeeper is conceding goals due to systemic defensive collapses or substandard shot-stopping technique. FBref/StatsBomb provides **Post-Shot Expected Goals (PSxG)** and $\text{PSxG} - \text{Goals Conceded}$ ($\text{PSxG} +/-$), which directly isolates pure shot-stopping ability and expected save generation.
2. **Shot-Creating Actions (SCA) & Goal-Creating Actions (GCA)**: Standard metrics count only final passes leading to a shot. SCA captures the two offensive actions directly leading to a shot (dribbles, tackles won, fouls drawn, secondary passes, rebounds). In FPL, these creative actions form the bedrock of the Bonus Point System (BPS) baseline for elite midfielders and fullbacks.

This design implements a robust, cached client (`clients/fbref_client.py`) utilizing `soccerdata` (with direct fallback), ingesting seasonal goalkeeper and outfield advanced metrics, and integrating them into `analytics/xp_model.py`.

### 1.2 In Scope
- **`clients/fbref_client.py`**: A client querying FBref Premier League advanced statistics tables with persistent multi-day disk caching (`.fbref_cache.json`).
- **Goalkeeper Advanced Metrics**: Extraction of $\text{PSxG}/90$, $\text{PSxG} +/- \text{ per } 90$, $\text{Save Pct}$, and $\text{SoTA}/90$.
- **Outfield Advanced Metrics**: Extraction of $\text{SCA}/90$, $\text{GCA}/90$, $\text{npxG}/90$, and $\text{xAG}/90$.
- **Refined Goalkeeper Expected Points ($\text{xP}_{\text{GK}}$)**: Modeling expected save volumes $\mathbb{E}[\text{Saves}]$ and save point yields as a function of opponent goal arrival rates $\lambda_{\text{opp}}$ and goalkeeper save percentage.
- **Enhanced Bonus Point System (BPS) Propensity**: Calibrating baseline BPS expectations via $\text{SCA}/90$ and $\text{GCA}/90$.

### 1.3 Out of Scope
- Scraping historical seasons prior to the current 2024/25 and 2025/26 campaign.
- Heavy un-cached real-time scraping during optimization loops.

---

## 2. Mathematical & Quantitative Formalisms

### 2.1 Goalkeeper Save Point Expectancy Model
In FPL scoring rules, goalkeepers earn $+1$ point for every 3 saves made in a match:
$$\text{Pts}_{\text{saves}} = \left\lfloor \frac{\text{Saves}}{3} \right\rfloor$$

Under a Poisson framework with opponent goal expectancy $\lambda_{\text{opp}}$ and goalkeeper historical save percentage $\eta \in [0.55, 0.85]$:
Let $S_{\text{on}}$ denote expected shots on target faced by the goalkeeper:
$$\mathbb{E}[S_{\text{on}}] = \frac{\lambda_{\text{opp}}}{1.0 - \eta + \epsilon}$$
Where $\epsilon = 10^{-4}$ prevents division by zero.
The expected number of saves generated is:
$$\mathbb{E}[\text{Saves}] = \eta \cdot \mathbb{E}[S_{\text{on}}] = \frac{\eta}{1.0 - \eta} \cdot \lambda_{\text{opp}}$$

Using continuous Poisson expectation for save points:
$$\mathbb{E}[\text{xP}_{\text{saves}}] = \frac{\mathbb{E}[\text{Saves}]}{3.0} = \frac{\eta}{3.0 \cdot (1.0 - \eta)} \cdot \lambda_{\text{opp}}$$

Furthermore, true shot-stopping skill $\Delta_{\text{PSxG}} = \text{PSxG} +/- \text{ per } 90$ modulates clean sheet survival probability:
$$P(\text{CS}_{\text{effective}}) = \exp\left( -\max(0.30, \lambda_{\text{opp}} - \Delta_{\text{PSxG}}) \right)$$
Elite shot-stoppers ($\Delta_{\text{PSxG}} > 0$) absorb defensive leakage and boost clean sheet odds, while deficient shot-stoppers ($\Delta_{\text{PSxG}} < 0$) experience downward clean sheet decay.

### 2.2 Outfield BPS Baseline Modulation via SCA & GCA
The FPL Bonus Point System awards BPS points for:
- Creating a big chance: $+3$ BPS
- Key passes: $+1$ to $+2$ BPS
- Successful open play crosses: $+1$ BPS
- Successful dribbles / take-ons: $+1$ BPS
- Recoveries / tackles won leading to attacking transitions: $+1$ BPS

Players with high Shot-Creating Actions ($\text{SCA}_{90} \ge 4.0$) reliably generate $+12$ to $+20$ raw BPS points per 90 minutes even in matches without a direct goal or assist, making them bonus point magnets when their team secures a $1-0$ win or clean sheet.

We define the BPS multiplier $\beta_{\text{SCA}}$:
$$\beta_{\text{SCA}} = 1.0 + \text{clip}\left( 0.035 \cdot (\text{SCA}_{90} - 2.8) + 0.070 \cdot (\text{GCA}_{90} - 0.35), -0.15, +0.25 \right)$$

This multiplier scales the baseline expected bonus points $\mathbb{E}[\text{Bonus}_{\text{base}}]$ in `XPModel`:
$$\mathbb{E}[\text{Bonus}] = \mathbb{E}[\text{Bonus}_{\text{base}}] \cdot \beta_{\text{SCA}}$$

---

## 3. Component Architecture & Data Contracts

### 3.1 Data Contracts (`clients/fbref_client.py`)

```python
@dataclass(frozen=True)
class GoalkeeperAdvancedMetrics:
    """Advanced FBref/StatsBomb goalkeeper metrics."""
    web_name: str
    team_code: str
    psxg: float                 # Post-Shot xG faced
    goals_conceded: float       # Actual goals conceded
    psxg_net_per90: float       # PSxG +/- per 90 (shot stopping alpha)
    save_pct: float             # Save percentage (0.0 to 1.0)
    sota_per90: float           # Shots on Target Against per 90
    clean_sheet_pct: float      # Clean sheet percentage
    as_of_timestamp: float

@dataclass(frozen=True)
class OutfieldAdvancedMetrics:
    """Advanced FBref/StatsBomb outfield creative and progression metrics."""
    web_name: str
    team_code: str
    sca90: float                # Shot-Creating Actions per 90
    gca90: float                # Goal-Creating Actions per 90
    npxg90: float               # Non-penalty xG per 90
    xag90: float                # Expected assisted goals per 90
    prog_carries90: float       # Progressive carries per 90
    prog_passes90: float        # Progressive passes per 90
    as_of_timestamp: float
```

### 3.2 Ingestion & Caching Strategy
- **Library**: Uses `soccerdata.FBref` when installed, backed by direct HTML / API table parsing fallback.
- **Cache**: Local JSON store at `.fbref_cache.json` with a 72-hour TTL, ensuring fast sub-millisecond local reads and zero network rate-limiting.
- **Player Identity Resolution**: Leverages `normalize_text` and `TacticalClient` alias mapping to link FBref player names with FPL IDs.

---

## 4. Verification & Pytest Plan

- **`test_goalkeeper_save_model`**: Verifies mathematical properties of save point calculation $\mathbb{E}[\text{Saves}]$ and PSxG modulation.
- **`test_outfield_bps_multiplier`**: Verifies BPS scaling boundaries ($\in [0.85, 1.25]$) and monotonicity with respect to SCA and GCA.
- **`test_fbref_dataclass_contracts`**: Enforces immutability of frozen dataclass structures.
- **`test_fbref_cache_ttl`**: Validates disk caching and offline persistence without network access.
- **`test_xp_model_gk_and_bps_integration`**: Tests integration into `XPModel`, ensuring goalkeepers with high save rates generate elevated xP against attacking opponents.
