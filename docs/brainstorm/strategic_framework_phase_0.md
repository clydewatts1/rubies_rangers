---
type: Brainstorm
title: "[#010] Strategic Framework Phase 0 - Foundational Data & Portfolio Ingestion"
description: "Multi-gameweek transfer planning, bank optimization, and rolling horizon setup."
tags: [brainstorm, portfolio, transfers, strategy]
status: Legacy
sources: []
generated:
  at: "2026-09-16T22:30:00Z"
  by: "agent:backfill_okf"
---
# Brainstorm: Strategic Framework Phase 0 — Foundational Data Pipelines, Multi-Horizon Metrics & Domain Contracts
## The Data Engineering, Generative Metrics & Immutable Contract Layer for Multi-Period Optimization

**Status**: PROPOSED / BRAINSTORM  
**Target Subsystems**: `analytics/strategic/contracts.py`, `clients/fpl_client.py`, `analytics/strategic/trajectory_engine.py`, `tuner/`, `config.yaml`, `config_manager.py`, `tests/test_strategic_phase0.py`  
**Execution Order**: **PHASE 0 (Prerequisite Foundation for Phase 1 & Phase 2)**  
**Related Rules**:
- [`.agents/rules/moneyball_strategy.md`](../../.agents/rules/moneyball_strategy.md) (Unconstrained Solvers, Stochastic Distributions, Vectorization, Anti-Leakage, Rule 6: Baseline Priors vs. Post-Optimization Execution)
- [`.agents/rules/python_standards.md`](../../.agents/rules/python_standards.md) (Layered Architecture, Frozen Dataclasses, PEP 8, No Row Iteration)

---

## Executive Summary

Before the platform can execute **Phase 1 (Macro Fixture Regime / Wave Scanner)** or **Phase 2 (Multi-Period Rolling Horizon Solver)**, it requires a robust, zero-leakage **Data and Mathematical Foundation (Phase 0)**.

Currently, Rubies Rangers computes single-gameweek expected points ($xP$) and basic rolling FDR tables. However, multi-period strategic optimization requires **dense, multi-horizon expectation tensors** spanning 8 future gameweeks ($H \in [1, 8]$), venue-calibrated club strength ratings, and frozen domain contracts that maintain squad state across time.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              PHASE 0: FOUNDATIONAL ARCHITECTURE TOPOLOGY                               │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                        │
│   ┌───────────────────────────┐      ┌───────────────────────────┐      ┌───────────────────────────┐  │
│   │ 1. MULTI-HORIZON FIXTURES │      │ 2. DENSE XP TRAJECTORIES  │      │ 3. SQUAD BALANCE SHEET    │  │
│   │    & CLUB RATINGS         │      │    (N_PLAYERS × 8 GWs)    │      │    & FT STATE CONTRACTS   │  │
│   ├───────────────────────────┤      ├───────────────────────────┤      ├───────────────────────────┤  │
│   │ • 8-GW Opponent Vectors   │ ───► │ • Poisson λ_goals / λ_ast │ ───► │ • Banked FTs (1 to 5)     │  │
│   │ • Venue Multipliers (H/A) │      │ • Clean Sheet Binaries    │      │ • Cash-in-Bank Liquidity  │  │
│   │ • Dynamic Attack/Def xG   │      │ • Vectorized Numpy Matrix │      │ • Frozen Dataclass Schema │  │
│   └───────────────────────────┘      └───────────────────────────┘      └───────────────────────────┘  │
│                                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Furthermore, in strict adherence to **Rule 6 of [`.agents/rules/moneyball_strategy.md`](../../.agents/rules/moneyball_strategy.md)**, **all heuristic parameters introduced in Phase 0 must default to intuitive baseline priors under the `heuristic` profile in `config.yaml`, while being fully exposed as continuous/discrete search spaces for automated Bayesian optimization in `tuner/` (producing the `tuned` empirical profile)**.

---

## 1. Multi-Horizon Fixture & Club Dynamic Strength Engine

### Problem Statement:
Standard FPL FDR is a static integer (1 to 5) that does not reflect actual attacking and defensive prowess. For example, playing against a high-scoring but defensively leaky team (e.g. Spurs) offers high attacking xP but low clean-sheet probability.

### Mathematical Formulation:
For each club $c \in [1, 20]$ and future gameweek $t \in [1, 8]$:
1. **Club Attack Rating ($\alpha_c$):** Rolling 10-match expected goals scored per 90 ($\text{xG}_{\text{for}}$).
2. **Club Defense Concession Rating ($\delta_c$):** Rolling 10-match expected goals conceded per 90 ($\text{xG}_{\text{against}}$).
3. **Venue Multiplier ($\nu$):**
   $$\nu_{\text{attack}} = \begin{cases} \nu_{\text{att\_home}} & \text{if Home} \\ \nu_{\text{att\_away}} & \text{if Away} \end{cases}, \quad \nu_{\text{defense}} = \begin{cases} \nu_{\text{def\_home}} & \text{if Home (Concedes fewer)} \\ \nu_{\text{def\_away}} & \text{if Away (Concedes more)} \end{cases}$$
4. **Expected Match Goals (Poisson Intensity):**
   $$\lambda_{\text{match}, c, t} = \alpha_c \times \delta_{\text{opp}(c, t)} \times \nu_{\text{attack}}$$
5. **Expected Opponent Goals Conceded:**
   $$\mu_{\text{conceded}, c, t} = \alpha_{\text{opp}(c, t)} \times \delta_c \times \nu_{\text{defense}}$$
6. **Clean Sheet Probability ($P(\text{CS})$):**
   $$P(\text{CS}_{c, t}) = \exp(-\mu_{\text{conceded}, c, t} \times \kappa_{\text{cs\_scale}})$$

---

## 2. Multi-Horizon Expected Points ($xP$) Trajectory Tensor

Phase 0 computes a dense $(N_{\text{players}} \times 8)$ matrix representing the expected points of every player for every week in the 8-gameweek horizon.

```text
Player Universe (N ≈ 650)
┌──────────────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┐
│ Player       │ GW t  │ GW t+1│ GW t+2│ GW t+3│ GW t+4│ GW t+5│ GW t+6│ GW t+7│
├──────────────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┤
│ Haaland      │ 8.42  │ 7.85  │ 9.10  │ 5.20  │ 8.65  │ 7.90  │ 6.40  │ 8.10  │
│ Salah        │ 7.90  │ 8.30  │ 6.10  │ 7.40  │ 8.80  │ 5.50  │ 7.20  │ 7.60  │
│ Mbeumo       │ 5.10  │ 6.80  │ 7.20  │ 6.90  │ 6.40  │ 4.10  │ 4.50  │ 5.80  │
│ Robinson     │ 3.20  │ 4.80  │ 5.10  │ 4.90  │ 4.60  │ 2.10  │ 2.40  │ 3.80  │
└──────────────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┘
```

### Generative Points Formula for Player $i$ in Gameweek $t$:
$$xP_{i, t} = \mathbb{E}[\text{Min}_i] \times \Big[ \text{Pts}_{\text{app}} + (\text{Pts}_{\text{goal}} \times \lambda_{\text{goal}, i, t}) + (\text{Pts}_{\text{assist}} \times \lambda_{\text{ast}, i, t}) + (\text{Pts}_{\text{CS}} \times P(\text{CS}_{\text{club}(i), t})) + \mathbb{E}[\text{Bonus}_{i, t}] - \mathbb{E}[\text{Cards}_{i, t}] \Big]$$

Where:
* $\lambda_{\text{goal}, i, t} = \text{xG90}_i \times \delta_{\text{opp}(i, t)} \times \nu_{\text{attack}}$.
* $\lambda_{\text{ast}, i, t} = \text{xA90}_i \times \delta_{\text{opp}(i, t)} \times \nu_{\text{attack}}$.
* $\mathbb{E}[\text{Min}_i]$: Player's expected minutes (0.0 to 1.0 scalar fraction of 90 mins).

---

## 3. Domain Contracts Schema (`analytics/strategic/contracts.py`)

In accordance with [`.agents/rules/python_standards.md`](../../.agents/rules/python_standards.md), all data structures in Phase 0 are defined as **immutable `@dataclass(frozen=True)`** contracts:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import numpy as np


@dataclass(frozen=True)
class PlayerTrajectoryProfile:
    """Immutable 8-gameweek projected profile for an individual player."""
    element_id: int
    web_name: str
    full_name: str
    club_short: str
    position_name: str         # "GKP", "DEF", "MID", "FWD"
    now_cost: float            # e.g. 7.5 (£m)
    xp_trajectory: tuple[float, ...]  # Length H (e.g. 8 floats)
    fdr_trajectory: tuple[float, ...] # Length H
    opponents: tuple[str, ...]        # Length H opponent short codes (e.g. ("FUL", "BRE", "MCI"))
    is_home: tuple[bool, ...]         # Length H venue indicators
    minutes_expectation: float        # Expected minutes per match (0 to 90)
    price_change_momentum: float      # Velocity score (-100 to +100)


@dataclass(frozen=True)
class ClubScheduleProfile:
    """Immutable 8-gameweek schedule and difficulty vector for a Premier League club."""
    club_short: str
    club_name: str
    fdr_vector: tuple[float, ...]
    opponents: tuple[str, ...]
    is_home: tuple[bool, ...]
    clean_sheet_probs: tuple[float, ...]
    expected_goals_scored: tuple[float, ...]
    expected_goals_conceded: tuple[float, ...]


@dataclass(frozen=True)
class StrategicSquadState:
    """Snapshot of a manager's current team state and balance sheet."""
    squad_player_ids: tuple[int, ...]
    squad_player_names: tuple[str, ...]
    bank_balance: float
    free_transfers_available: int  # 1 to 5
    chips_available: tuple[str, ...]
    team_value: float
    gameweek: int
```

---

## 4. Market Dynamics & Price Velocity Ingestion

Phase 0 integrates real-time market price momentum to protect the squad from value erosion and capitalize on early-season price jumps:

1. **Net Transfer Velocity ($\Delta \text{Transfers}_{24\text{h}}$):** Tracks rate of crowd accumulation/dumping.
2. **Price Change Threshold:** Models the FPL price algorithm threshold ($\approx \pm 100\%$ target threshold) to assign:
   * `RISE_PROBABILITY`: Estimated probability of price increase (+£0.1m) within 48 hours.
   * `FALL_PROBABILITY`: Estimated probability of price decrease (-£0.1m) within 48 hours.
3. **Liquidity Flagging:** Tags players in danger of immediate capital depreciation so Phase 1 and Phase 2 can prioritize liquidation.

---

## 5. Point-in-Time Anti-Leakage & High-Performance Caching

To guarantee scientific integrity and fast execution:

1. **Strict Anti-Leakage Isolation**:
   * Historical backtesting engines strictly consume bootstrap and fixture snapshots from *before* the deadline of each gameweek.
   * Forward-looking match results or future price changes are strictly inaccessible to the trajectory engine.
2. **Vectorized NumPy / Pandas Operations**:
   * Zero row iteration (`.iterrows()` prohibited).
   * All multi-horizon calculations execute via vectorized matrix multiplications:
     $$\mathbf{XP} = \mathbf{M} \odot \left( \mathbf{Pts}_{\text{goal}} \boldsymbol{\Lambda}_{\text{goal}} + \mathbf{Pts}_{\text{ast}} \boldsymbol{\Lambda}_{\text{ast}} + \mathbf{Pts}_{\text{CS}} \mathbf{P}_{\text{CS}} + \mathbf{C} \right)$$
   * Computes the entire 650-player $\times$ 8-gameweek expectation matrix in $< 15\text{ milliseconds}$.

---

## 6. Heuristic Baseline Defaults & Bayesian Hyperparameter Trainability Lifecycle

In accordance with **Rule 6 of [`.agents/rules/moneyball_strategy.md`](../../.agents/rules/moneyball_strategy.md)**, no heuristic rule of thumb is hardcoded as an immutable truth. Every parameter exists in a dual lifecycle:

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              PARAMETER LIFECYCLE & DUAL-PROFILE ARCHITECTURE                           │
├────────────────────────────────────────────────────┬───────────────────────────────────────────────────┤
│ 1. COLD-START BOOTSTRAP: `heuristic` PROFILE       │ 2. EMPIRICAL EXECUTION: `tuned` PROFILE           │
├────────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
│ • Pre-training / cold-start baseline prior         │ • Discovered via Bayesian Optuna Optimization     │
│ • Defined under `heuristic:` in `config.yaml`      │ • Backtested across 3 historical seasons          │
│ • Sensible domain defaults for immediate operation │ • Written to `tuned:` in `config.yaml` by tuner   │
│ • Serves as warm-start prior for tuner             │ • Zero heuristic overrides permitted once tuned   │
└────────────────────────────────────────────────────┴───────────────────────────────────────────────────┘
```

### Strategic Hyperparameter Search Space Specification (for `tuner/`):

| Parameter Name | Configuration Key | Heuristic Baseline (Default) | Tuner Search Space (Optuna Bounds) | Tuning Objective Metric |
| :--- | :--- | :---: | :---: | :--- |
| **Home Attack Boost** | `strategic.venue.nu_att_home` | `1.15` | `[1.02, 1.30]` (Float) | Maximizes multi-gameweek xP predictive $R^2$ |
| **Away Attack Penalty**| `strategic.venue.nu_att_away` | `0.87` | `[0.75, 0.98]` (Float) | Maximizes multi-gameweek xP predictive $R^2$ |
| **Home Defense Multiplier**| `strategic.venue.nu_def_home` | `0.85` | `[0.70, 0.95]` (Float) | Minimizes Clean Sheet cross-entropy loss |
| **Away Defense Penalty**| `strategic.venue.nu_def_away` | `1.18` | `[1.05, 1.35]` (Float) | Minimizes Clean Sheet cross-entropy loss |
| **Clean Sheet Scale** | `strategic.defense.kappa_cs_scale` | `1.00` | `[0.80, 1.25]` (Float) | Brier score minimization on CS outcomes |
| **Lookahead Discount ($\gamma$)** | `strategic.horizon.discount_gamma` | `0.92` | `[0.82, 0.98]` (Float) | Rolling 5-GW squad cumulative score |
| **Green Wave FDR Threshold** | `strategic.waves.threshold_green` | `2.50` | `[2.20, 2.80]` (Float) | Sharpe ratio of swing trade transitions |
| **Red Cliff FDR Threshold** | `strategic.waves.threshold_red` | `3.40` | `[3.10, 3.80]` (Float) | Hit-reduction rate on difficult runs |
| **Price Momentum Weight** | `strategic.market.momentum_weight` | `0.20` | `[0.00, 0.50]` (Float) | Team Value J-Curve appreciation vs xP delta |
| **FT Option Value Multiplier** | `strategic.balance_sheet.ft_option_mult` | `1.50` | `[0.50, 3.00]` (Float) | Net utility across 5-week transfer sequences |

### Training Integration:
* Automated training runs (`run_overnight_tuner.bat` or `python -m tuner.tune_params`) evaluate the full parameter space against historical seasons (2022/23, 2023/24, 2024/25).
* Once the training job finishes, the best trial parameters are serialized automatically into `config.yaml` under `tuned:`, and production decision engines switch to `active_profile: tuned`.

---

## 7. Phase 0 Acceptance Criteria & Verification Plan

### Automated Test Suite (`tests/test_strategic_phase0.py`):
1. **Contract Integrity**: Verify all dataclasses (`PlayerTrajectoryProfile`, `ClubScheduleProfile`, `StrategicSquadState`) instantiate cleanly, are immutable, and serialize to dict.
2. **Dual-Profile Parameter Loading**: Ensure `config_manager.get_params("strategic")` resolves correctly under both `heuristic` and `tuned` profiles with zero hardcoded magic numbers.
3. **Tuner Search Space Registration**: Ensure all 10 strategic hyperparameters are registered in `tuner/` with valid Optuna distributions.
4. **Dimension Invariants**: Ensure all trajectory vectors have exact length $H$ (e.g. 8 gameweeks).
5. **Mathematical Bounds**:
   * $0.0 \le P(\text{CS}_{c, t}) \le 1.0$ for all clubs and gameweeks.
   * $0.0 \le xP_{i, t} \le 25.0$ (sanity bounds).
   * Free transfers constrained to $1 \le \text{FT} \le 5$.
6. **Performance Benchmark**: Multi-horizon tensor generation across all 650 players executes in $< 50\text{ms}$.

---

## 8. Next Step: Progression to Phase 1

Upon implementation and verification of Phase 0:
* **Phase 1 (The Wave Scanner)** directly consumes `ClubScheduleProfile` and `PlayerTrajectoryProfile` to detect Green Waves, Red Cliffs, and Defensive Rotation Pairs using either heuristic defaults or tuned thresholds.
* **Phase 2 (The Multi-Period Solver)** consumes the dense $(N \times H)$ $xP$ tensor, dynamic discount $\gamma$, and `StrategicSquadState` to solve the 5-gameweek integer linear program.
