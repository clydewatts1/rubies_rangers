---
type: Brainstorm
title: "[#011] Macro-Strategic Portfolio & Asset Management Framework"
description: "Managing FPL squads as dynamic investment portfolios with cash buffers and capital preservation."
tags: [brainstorm, portfolio, balance-sheet, strategy, transfers]
status: Legacy
sources: ["docs/issues/iss_011_strategic_portfolio_asset_management.md"]
generated:
  at: "2026-09-16T22:30:00Z"
  by: "agent:backfill_okf"
---
# Brainstorm: Macro-Strategic Portfolio & Asset Management Framework
## Multi-Period Stochastic Control, Balance Sheet Optionality & Game-Theoretic Pool Mechanics

**Status**: PROPOSED / BRAINSTORM  
**Target Subsystems**: `analytics/strategic/`, `analytics/two_stage_optimizer.py`, `analytics/chip_strategy.py`, `analytics/optimizer.py`, `ui/tabs/tab_strategic_macro.py`, `app.py`  
**Execution Governance**: **Strict Phased Staging (Only One Phase Implemented & Verified at a Time)**  
**Related Rules**:
- [`.agents/rules/moneyball_strategy.md`](../../.agents/rules/moneyball_strategy.md) (Unconstrained Solvers, Stochastic Distributions, Multi-Period Utility & Adversarial Game Theory)
- [`.agents/rules/python_standards.md`](../../.agents/rules/python_standards.md) (Layered Architecture, Frozen Dataclasses, Vectorization, Strict Types)

---

## Executive Summary

Conventional Fantasy Premier League (FPL) management is overwhelmingly **tactical and myopic**—focusing almost exclusively on the immediate next fixture, chasing the preceding week's points (recency bias), and making greedy 1-gameweek transfer swaps.

Mathematically, however, Fantasy Football is a **discrete-time, multi-period stochastic control problem with transaction friction, rolling capital constraints, and asymmetric tournament payoffs**. It operates as a dynamic quantitative equity portfolio and a competitive football prediction pool over a fixed 38-period time horizon.

```text
                               ┌─────────────────────────────────────────────────────────┐
                               │       MACRO-STRATEGIC FPL ENGINE (PORTFOLIO VIEW)       │
                               └────────────────────────────┬────────────────────────────┘
                                                            │
                 ┌───────────────────────────┬──────────────┴─────────────┬───────────────────────────┐
                 ▼                           ▼                            ▼                           ▼
        ┌──────────────────┐       ┌──────────────────┐         ┌──────────────────┐        ┌──────────────────┐
        │ 1. MULTI-PERIOD  │       │ 2. BALANCE SHEET │         │ 3. ASSET WAVES   │        │ 4. GAME THEORY   │
        │ DYNAMIC HORIZON  │       │ & OPTION VALUE   │         │ & SWING CYCLES   │        │ & POOL METAS     │
        ├──────────────────┤       ├──────────────────┤         ├──────────────────┤        ├──────────────────┤
        │ • Rolling 5-8 GW │       │ • FTs as Options │         │ • Core vs Swings │        │ • EO Beta Hedging│
        │ • Bellman Value  │       │ • Bank Liquidity │         │ • Fixture Tides  │        │ • Deficit Upside │
        │ • Reversible Ops │       │ • TV J-Curve     │         │ • Mean-Reversion │        │ • Mini-League Win│
        └──────────────────┘       └──────────────────┘         └──────────────────┘        └──────────────────┘
```

This document establishes the theoretical architecture, phased implementation blueprint, and strategic roadmap for transforming **Rubies Rangers** from a 1-GW tactical solver into a comprehensive **Macroeconomic & Portfolio Asset Management Engine**.

---

## 1. Core Operating Philosophy: Pure Quantitative Optimization

In accordance with [`.agents/rules/moneyball_strategy.md`](../../.agents/rules/moneyball_strategy.md), the system operates on **Zero Human Tactical Bias & Pure First-Principles Mathematics**:

1. **Zero Emotional Attachment**: Player selection is completely agnostic to player celebrity, historic reputation, club loyalty, or media narrative. Every asset is evaluated strictly on its underlying statistical generation parameters (Poisson $\lambda_{\text{goals}}$, $\lambda_{\text{assists}}$, starting probability distributions, minutes variance, and opponent defensive concession rates).
2. **Staged Migration Policy**: Rather than triggering an early Wildcard under panic, the platform employs a **Staged Multi-Period Migration** ($S_0 \xrightarrow{\mathbf{u}_0} S_1 \xrightarrow{\mathbf{u}_1} S_2 \dots \xrightarrow{\mathbf{u}_H} S_H$). Sub-optimal picks from initial drafts are systematically repaired across 3 to 6 gameweeks using optimal Free Transfer banking and amortized hit evaluation, preserving the Wildcard option for high-leverage Double Gameweek macro-states.
3. **Execution Rule — One Phase at a Time**: The platform development is strictly partitioned into independent, decoupled phases delivered across sequential milestones. Each phase must be fully engineered, covered with automated unit/integration tests, and validated in the UI before commencing subsequent phases.

---

## 2. Mathematical Foundation: Multi-Period Stochastic Control

### The Bellman Optimality Formulation
Instead of optimizing myopic 1-gameweek score $\mathbb{E}[S_t]$, the macro engine solves a **rolling lookahead horizon** ($H = 5 \text{ to } 8 \text{ gameweeks}$) using dynamic programming and backward induction:

$$V_t(S_t, \text{FT}_t, \text{Bank}_t) = \max_{\mathbf{u}_t \in \mathcal{U}(S_t)} \Big\{ \mathbb{E}[R_t(S_t, \mathbf{u}_t)] - \text{Cost}(\mathbf{u}_t) + \gamma \cdot \mathbb{E}\left[ V_{t+1}(S_{t+1}, \text{FT}_{t+1}, \text{Bank}_{t+1}) \mid S_t, \mathbf{u}_t \right] \Big\}$$

Where:
* $S_t \in \mathcal{S}$: 15-player squad state vector at gameweek $t$.
* $\mathbf{u}_t \in \mathcal{U}$: Transfer action vector (transfers in, transfers out, captaincy, bench order).
* $\text{FT}_t \in \{1, 2, 3, 4, 5\}$: Accumulated Free Transfer inventory.
* $\text{Bank}_t \ge 0$: Available Cash-in-Bank (£m).
* $R_t(S_t, \mathbf{u}_t)$: Realized gameweek point yield of active XI + autosubstitutions + captain multiplier.
* $\text{Cost}(\mathbf{u}_t) = 4 \times \max(0, \|\mathbf{u}_t\|_0 - \text{FT}_t)$: Point deduction for excess transfers.
* $\gamma \in [0.88, 0.95]$: Inter-temporal discount factor accounting for future uncertainty and injury risk.

### Irreversible Commitments & Path Tree Evaluation
Every transfer commits budget, consumes an FT, and alters future team state. A transfer is evaluated not as a static player swap, but across its **branching multi-week execution tree**:

```text
GW t:           [Current Squad S_t] (2 FTs)
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
    Action A: Roll FT        Action B: 1 Transfer (-1 FT)
    (Bank 3 FTs in GW t+1)   (Bank 2 FTs in GW t+1)
         │                       │
         ├───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
    Action A1 (Double Pivot) Action B1 (Single Move) Action B2 (Hold)
    (5-GW Net xP: 342.1)     (5-GW Net xP: 331.4)    (5-GW Net xP: 326.8)
```

---

## 3. Balance Sheet & Real Options Management

A competitive FPL team maintains a **multi-asset balance sheet** consisting of capital, fixture equity, and structural options:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       FPL SQUAD BALANCE SHEET                               │
├──────────────────────────────────────┬──────────────────────────────────────┤
│ ASSETS & CAPITAL                     │ LIQUIDITY & STRUCTURAL OPTIONS       │
├──────────────────────────────────────┼──────────────────────────────────────┤
│ • Core Squad Value (£m)              │ • Cash in Bank (CIB) Liquidity       │
│ • Fixture Equity ($\sum$ xGI next 5) │ • Free Transfer Inventory (1–5 FTs)  │
│ • Unrealized Market Gains (£m)       │ • Unplayed American Option Chips     │
└──────────────────────────────────────┴──────────────────────────────────────┘
```

### 1. The Team Value (TV) J-Curve
Capital appreciation is non-linear and front-loaded:
* **Phase 1 (GW 1–12 - Capital Accumulation):** Catching early price rises (+£0.1m / +£0.2m) is prioritized. Reaching £103.0m–£105.0m early expands the Pareto frontier, allowing the squad to field an extra premium player in the second half of the season without structural compromise.
* **Phase 2 (GW 13–24 - Asset Stabilization):** Transitioning value into fixture-optimal mid-tier assets.
* **Phase 3 (GW 25–38 - Capital Monetization):** Selling value-locked bench assets to fund a fully stacked starting XI and Double Gameweek Bench Boost; team value preservation drops to zero priority.

### 2. Free Transfers as American Call Options
Under the expanded rules (banking up to 5 FTs), an unspent FT is an **option contract on future market information**:
* **1 FT:** Low optionality; forced into 1-for-1 like-for-like swaps.
* **2–3 FTs:** Medium optionality; enables price-bracket jumps (£6.5m MID + £4.5m FWD ➔ £4.5m MID + £6.5m FWD).
* **4–5 FTs:** High optionality ("Mini-Wildcard"); enables total structural pivot across multiple positions with **zero transfer deductions**.
* **Valuation Rule:** Spending an FT on a marginal $+0.5\text{ xP}$ upgrade is rejected if the **option continuation value** of saving the FT is $+2.2\text{ xP}$ in structural agility for the upcoming fixture swing.

### 3. Cash-in-Bank (CIB) Liquidity Buffer
Leaving £0.5m to £1.5m in the bank serves as **liquidity insurance**:
* Absorbs mid-week price rises of target assets without forcing early, risky pre-deadline moves before press conferences.
* Allows single-transfer upgrades across price tiers without requiring a paired downgrade.

---

## 4. Asset Class Allocation & Macro Fixture Regime Waves

The platform segments the player universe into four distinct **financial asset classes**:

| Asset Class | Target Allocation | Holding Horizon | Selection Objective | Risk / Return Profile |
| :--- | :---: | :---: | :--- | :--- |
| **Core Blue Chips** | 2–3 Players (£25m–£35m) | Long (10–25+ GWs) | Baseline captaincy, elite underlying xGI, fixture-resilient | Low beta, high baseline expectation, high EO |
| **Cyclical Swing Trades** | 4–6 Players (£25m–£35m) | Medium (4–7 GWs) | 4–6 game green fixture run (FDR $\le 2.4$), high attacking involvement | High alpha, high momentum, mean-reverting |
| **Paired Rotations** | 2–4 Players (£9m–£18m) | Season-Long Pairs | Home/Away fixture alternation between low-cost defenders/GKPs | Synthetic premium defense at budget cost |
| **Cash Equivalents / Fodder** | 3–4 Players (£16m–£18m) | Permanent / Bench | Minimum cost (£4.0m DEF, £4.5m MID) with guaranteed 90-min appearance | Liquidity enablers, zero capital drag |

```text
Macro Swing Trading Cycle:
GW1 ──[Accumulation]──> GW3 ──[Green Wave Peak (Hold & Captain)]──> GW7 ──[Liquidation]──> GW8
  ▲                       ▲                                           ▲
  │                       │                                           │
  Buy 1 GW Before Rush    Crowd Buys (Price Rises)                   Sell to Late Crowd Before Red Fixtures
```

---

## 5. Phased Staged Implementation Architecture

> [!IMPORTANT]
> **Staged Execution Policy**: Development proceeds strictly **one phase at a time**. Each phase is fully self-contained, tested, and validated in Streamlit before moving to the next.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 STRATEGIC ROADMAP PHASING ARCHITECTURE                                 │
├────────────────────────────────────────────────────┬───────────────────────────────────────────────────┤
│ PHASE 1 (DAY 1): MACRO RADAR (INFORMATION LAYER)   │ PHASE 2 (DAY 2): ROLLING SOLVER (EXECUTION LAYER) │
├────────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
│ • Module: `analytics/strategic/wave_scanner.py`    │ • Module: `analytics/strategic/multi_period.py`   │
│ • 4–8 GW Fixture Regime Classification             │ • 5-GW Lookahead Integer Linear Program (MILP)    │
│ • Green Wave Accumulation & Red Cliff Alerts       │ • Dynamic FT Banking Trajectory (1 to 5 FTs)      │
│ • Defensive Rotation Pairing Combinatorics         │ • Staged Migration Engine (Current ➔ Optimal)     │
│ • UI: Fixture Difficulty Heatmap & Radar Cards     │ • UI: 5-GW Strategic Transfer Chessboard Table    │
├────────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
│ PHASE 3 (DAY 3): BALANCE SHEET & LIQUIDITY ENGINE  │ PHASE 4 (DAY 4): ADVERSARIAL POOL & MINI-LEAGUE   │
├────────────────────────────────────────────────────┼───────────────────────────────────────────────────┤
│ • Module: `analytics/strategic/balance_sheet.py`   │ • Module: `analytics/strategic/adversarial.py`    │
│ • FT American Option Continuation Valuation Curves │ • Competitor Joint Probability Simulation         │
│ • Team Value (TV) J-Curve & Liquidity Optimization │ • Lead Defense (Beta Hedging / EO Alignment)      │
│ • Pre-Deadline Price Volatility Hedge Matrix       │ • Deficit Chasing (Orthogonal Alpha & P90 Ceil)   │
└────────────────────────────────────────────────────┴───────────────────────────────────────────────────┘
```

---

### Phase 1: Macro Fixture Regime / Wave Scanner (The Information Radar)
**Status**: ACTIVE / NEXT TO EXECUTE  
**Objective**: Provide macro clarity on upcoming multi-week fixture trends across all 20 clubs, identifying high-probability accumulation zones, exit cliffs, and budget defensive rotations.

* **Core Subsystem**: `analytics/strategic/contracts.py`, `analytics/strategic/wave_scanner.py`, `ui/tabs/tab_strategic_macro.py`
* **Key Capabilities**:
  1. **Fixture Wave Classification**: Classifies each club's rolling schedule into `GREEN_WAVE` (run of 4–6 games with FDR $\le 2.4$), `RED_CLIFF` (run of 3+ games with FDR $\ge 3.4$), or `NEUTRAL`.
  2. **Entry & Exit Windows**: Flags optimal buy points (1 GW before the wave starts) and liquidation points (1 GW before the cliff).
  3. **Combinatorial Defensive Pair Finder**: Sweeps all $\binom{20}{2} = 190$ club pairings across budget defenders (£4.0m–£4.5m) to find pairs that maximize the percentage of easy home fixtures (e.g. Fulham + Brentford = 85% home games).
  4. **Squad Fixture Audit**: Automatically parses the manager's current 15 players against upcoming wave inflections.
  5. **UI Component**: Interactive Fixture Heatmap, Wave Alert Cards, and Rotation Matrix in Streamlit.

---

### Phase 2: Multi-Period Rolling Horizon Solver (The 5-GW Transfer Chessboard)
**Status**: QUEUED (Execute after Phase 1 Verification)  
**Objective**: Formulate and solve a rolling 5-gameweek multi-period integer program that outputs the mathematically optimal sequential transfer path for a staged portfolio turnaround.

* **Core Subsystem**: `analytics/strategic/multi_period_solver.py`
* **Key Capabilities**:
  1. **State Continuity & Staged Migration**: Evaluates the step-by-step transition:
     $$S_0 \xrightarrow{\mathbf{u}_0} S_1 \xrightarrow{\mathbf{u}_1} S_2 \dots \xrightarrow{\mathbf{u}_H} S_H$$
     Systematically pruning underperforming/fragile assets while acquiring green wave assets.
  2. **Free Transfer Accumulation**: Implements dynamic FT inventory tracking:
     $$\text{FT}_{t+1} = \min(5, \text{FT}_t - \text{TransfersUsed}_t + 1)$$
  3. **Multi-Step Pivot Planning**: Determines when banking an FT to execute a 2-player or 3-player pivot in GW $t+1$ yields higher terminal utility than a greedy single transfer in GW $t$.
  4. **Hit Amortization NPV**: Rejects $-4$ hits unless the multi-gameweek cumulative xP gain net of risk and flexibility decay exceeds $+4.0$ points.
  5. **Branch Trajectory Output**: Displays the step-by-step 5-week transfer route with captaincy, bench order, and banked FT levels in an interactive dashboard table.

---

### Phase 3: Dynamic Balance Sheet & Real Options Valuation
**Status**: QUEUED (Execute after Phase 2 Verification)  
**Objective**: Quantify the monetary and structural flexibility of the squad.
* **Subsystem**: `analytics/strategic/balance_sheet.py`
* **Features**:
  * Free Transfer Option Valuation: Computes the continuation value of holding 1, 2, 3, 4, or 5 FTs.
  * Price Change Risk Matrix: Evaluates whether taking an early transfer before a price rise is justified given press conference information uncertainty.
  * Team Value J-Curve Tracker: Recommends when to prioritize value-building vs. raw point harvest.

---

### Phase 4: Adversarial Mini-League & Football Pool Game Theory
**Status**: QUEUED (Execute after Phase 3 Verification)  
**Objective**: Optimize transfer and captaincy decisions against specific mini-league competitors and tournament prize pools.
* **Subsystem**: `analytics/strategic/adversarial_engine.py`
* **Features**:
  * **Lead Protection Mode (Defending $\Delta > +30$ pts)**: Minimizes portfolio tracking error $\min \text{Var}(S_{\text{you}} - S_{\text{rival}})$ by aligning with rival high Effective Ownership (EO) assets and mirroring captaincy.
  * **Deficit Chasing Mode (Chasing $\Delta < -40$ pts)**: Maximizes probability of winning $P(S_{\text{you}} > S_{\text{rival}})$ by selecting orthogonal alpha, high-$P_{90}$ explosive ceiling differentials.
  * **Kelly Criterion for Hit Allocation**: Treats $-4$ point hits as fractional Kelly bets proportional to your statistical edge over the mini-league field.

---

## 6. Verification & Backtesting Plan

1. **Ablation Backtesting (`backtest/`):**
   * Compare 1-GW greedy MILP vs. 5-GW Rolling Horizon Dynamic Programming across historical seasons (2022/23, 2023/24, 2024/25).
   * Benchmark net points gain, hit reduction, and average team value trajectory.
2. **Automated Unit & Scenario Tests (`tests/test_strategic_framework.py`):**
   * Test FT accumulation constraints (max 5 FTs, rollover logic).
   * Test chip option pricing under blank/double gameweek probability injections.
   * Test game-theoretic posture transitions (Lead $> 30$ pts ➔ Beta Hedging mode).
