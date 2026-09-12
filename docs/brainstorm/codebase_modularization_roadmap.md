# Brainstorm: Codebase Modularization & Two-Stage Architectural Roadmap
## Decoupling the Monolith, Protecting Active Runs, and Transitioning to a Clean Package Architecture

**Status**: COMPLETED / VERIFIED (Branch: `modulerization`)  
**Tuner Status**: 3,151 Trials Complete (+268 pts Out-of-Sample Gain, `active_profile: tuned`)  
**Target Subsystems**: `app.py`, `fpl_optimizer.py`, `montecarlo_engine.py`, `trackers/`, `analytics/`, `clients/`, `ui/` (100% Modularized)  
**Related Rules**: 
* [`.agents/rules/python_standards.md`](../.agents/rules/python_standards.md) (Clean separation between presentation and analytical engines, vectorization, typed dataclasses)
* [`.agents/rules/moneyball_strategy.md`](../.agents/rules/moneyball_strategy.md) (Unconstrained solvers, stochastic distributions)
* [`docs/brainstorm/two_stage_screen_and_simulate.md`](./two_stage_screen_and_simulate.md) (Chaining MILP and Monte Carlo)

---

## Executive Summary

As Rubies Rangers evolves from a single-script analytics utility into an advanced quantitative operations research engine, the codebase is undergoing a structured modularization on the dedicated **`modulerization`** branch:

1. **Current Architectural State**: 
   * **Clean Packages**: `tuner/` and `backtest/` are already cleanly isolated into modular packages with independent CLIs, dashboards, and simulators.
   * **The Flat Root Cluster**: 15+ Python files reside flat in the repository root, including 8 separate tracker modules (`fixture_tracker.py`, `price_tracker.py`, `league_tracker.py`, etc.) and core mathematical engines.
   * **The Presentation Monolith**: `app.py` has grown into a 2,641-line (137 KB) monolith mixing Streamlit UI layouts, CSS injection, session state logic, and analytical execution.

2. **In-Flight Constraint Cleared**:
   * The 3,151-trial overnight hyperparameter tuner (`run_overnight_tuner.ps1`) has **successfully completed** and updated `config.yaml` with the winning `tuned:` profile.
   * With the file lock constraint lifted and the work isolated on the new **`modulerization` branch**, we can safely execute the physical package reorganization without risking production stability.

---

## 1. Architectural Audit of the Current Codebase

```text
CURRENT CODEBASE TOPOLOGY:
================================================================================
rubies_rangers/
├── tuner/                   [MODULAR] Optuna search space, workers, CLI, dashboard
├── backtest/                [MODULAR] Historical data loader, walk-forward simulator
├── tests/                   [MODULAR] Unit and integration test suites
├── docs/brainstorm/         [MODULAR] Mathematical specifications & research docs
│
├── app.py                   [MONOLITH: 2,641 lines / 137 KB]
│                            Combines UI tabs, CSS, HTML cards, and inline prep
│
├── Core Analytical Engines: [FLAT IN ROOT]
│   ├── fpl_optimizer.py     (302 lines - Scipy MILP knapsack solver)
│   ├── montecarlo_engine.py (1,240 lines - Stochastic match & lineup simulation)
│   ├── xp_model.py          (560 lines - Expected points & bookmaker Poisson odds)
│   └── team_manager.py      (950 lines - FPL team squad state manager)
│
├── Data Clients:            [FLAT IN ROOT]
│   ├── fpl_client.py        (FPL official REST API wrapper with caching)
│   └── tactical_client.py   (Understat / FBref tactical metrics scraper)
│
└── Trackers:                [FLAT IN ROOT - 8 distinct files]
    ├── fixture_tracker.py
    ├── price_tracker.py
    ├── league_tracker.py
    ├── tactical_tracker.py
    ├── trend_tracker.py
    ├── setpiece_tracker.py
    ├── montecarlo_tracker.py
    └── xp_tracker.py
================================================================================
```

---

## 2. In-Flight Dependency Protection (Why Wait on File Moves)

The repository currently has three long-running terminal processes:

| Process ID / Command | Uptime | Active File Dependencies | Risk of Moving Files |
| :--- | :--- | :--- | :--- |
| `run_overnight_tuner.ps1` (Optuna Tuner) | 13.5+ hours | `fpl_optimizer.py`, `config_manager.py`, `backtest/` | **CRITICAL**: Moving `fpl_optimizer.py` immediately throws `ModuleNotFoundError` in running worker processes, aborting 13+ hours of compute. |
| `streamlit run app.py` (Port 8501) | 15.5+ hours | `app.py`, all root trackers and engines | **HIGH**: Triggers Streamlit file watcher re-run errors. |
| `python -m tuner.cli dashboard` (Port 8502) | 1.0+ hours | `data/tuning_history.db` | **LOW**: Read-only access to SQLite DB. |

**Engineering Rule**: Never perform physical filesystem refactoring while long-running distributed stochastic training or hyperparameter optimization processes are executing against the repository root.

---

## 3. The Two Types of Modularization

### Type A: Interface Modularization (Contract-First Design)
* **What It Does**: Defines clean boundaries, data structures, and typed contracts between subsystems without changing their physical file paths.
* **Timing**: **Do this immediately.**
* **Mechanism**: Create a new, isolated file (`two_stage_optimizer.py`). It imports from `fpl_optimizer.py` and `montecarlo_engine.py`, wraps both in a clean typed orchestrator, and returns structured `@dataclass` outputs.
* **Risk to Running Systems**: **Zero.** Does not alter any existing file or import path.

### Type B: Physical Package Modularization (Directory Reorganization)
* **What It Does**: Moves flat files into dedicated Python packages (`analytics/`, `trackers/`, `clients/`, `ui/`).
* **Timing**: **Execute immediately after the overnight tuner completes.**
* **Risk to Running Systems**: High if executed during tuning; zero once completed.

---

## 4. Phase 1: Contract-First Interface Design (`two_stage_optimizer.py`)

Before touching any existing engine or UI code, define the typed contracts that bridge Stage 1 (MILP) and Stage 2 (Monte Carlo):

```python
"""
two_stage_optimizer.py
Clean typed contract bridging MILP combinatorial screening with Monte Carlo stochastic evaluation.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import numpy as np

@dataclass(frozen=True)
class ParetoCandidateSquad:
    """Stage 1 Output: Candidate generated by MILP under a specific objective."""
    objective_name: str           # e.g., "fdr_moneyball", "xgi", "setpiece_moneyball"
    generator_type: str = "MILP"  # e.g., "MILP", "CP-SAT", "NSGA-II", "GRASP"
    squad_names: List[str]        # 15 player names
    transfers_in: List[str]       # Incoming player names
    transfers_out: List[str]      # Outgoing player names
    total_cost: float             # Total squad cost in £m
    bank_remaining: float         # Remaining bank in £m
    projected_score: float        # Deterministic / heuristic score from generator

@dataclass
class StochasticSquadEvaluation:
    """Stage 2 Output: Monte Carlo stress-test distribution metrics."""
    candidate: ParetoCandidateSquad
    mean_points: float            # Expected points (EV)
    floor_p10: float              # 10th percentile downside floor
    median_p50: float             # 50th percentile median outcome
    ceiling_p90: float            # 90th percentile explosive haul ceiling
    standard_deviation: float     # Volatility / risk metric
    net_gain_vs_current: float    # EV delta compared to current squad
    win_probability_pct: float    # P(Candidate > Current Squad)
    zero_minute_rate_pct: float   # Bench auto-sub trigger frequency (e.g. Porro 75%)
    sharpe_ratio: float           # Risk-adjusted return: (EV - baseline) / std_dev

@dataclass
class TwoStageOptimizationReport:
    """Final decision package passed cleanly to app.py or CLI."""
    baseline_squad: List[str]
    baseline_mean: float
    baseline_p10: float
    baseline_p90: float
    evaluated_candidates: List[StochasticSquadEvaluation]
    winner_balanced: StochasticSquadEvaluation
    winner_safe_floor: StochasticSquadEvaluation
    winner_explosive_ceiling: StochasticSquadEvaluation
```

### Why This Decouples the Subsystems
* `FPLOptimizer` does not know `MonteCarloEngine` exists.
* `MonteCarloEngine` does not know `FPLOptimizer` exists.
* `app.py` does not run math logic; it simply receives `TwoStageOptimizationReport` and renders the visual comparison cards.

---

## 5. Phase 2: Target Package Architecture (Post-Tuner Refactor)

Once the 3,000-trial tuner completes its run, the repository will be reorganized into the following clean package structure:

```text
rubies_rangers/
├── analytics/                      # Core quantitative engines
│   ├── __init__.py
│   ├── optimizer.py               # (formerly fpl_optimizer.py)
│   ├── montecarlo.py              # (formerly montecarlo_engine.py)
│   ├── xp_model.py                # Expected points & bookmaker odds
│   ├── two_stage_optimizer.py     # Stage 1 + Stage 2 orchestrator
│   └── team_manager.py            # Squad state & budget management
│
├── trackers/                       # Data feature extractors & monitors
│   ├── __init__.py
│   ├── fixture.py                 # (formerly fixture_tracker.py)
│   ├── price.py                   # (formerly price_tracker.py)
│   ├── league.py                  # (formerly league_tracker.py)
│   ├── tactical.py                # (formerly tactical_tracker.py)
│   ├── trend.py                   # (formerly trend_tracker.py)
│   ├── setpiece.py                # (formerly setpiece_tracker.py)
│   └── xp.py                      # (formerly xp_tracker.py)
│
├── clients/                        # External API & web scraping clients
│   ├── __init__.py
│   ├── fpl_client.py
│   └── tactical_client.py
│
├── ui/                             # Modular Streamlit presentation layer
│   ├── __init__.py
│   ├── styles.py                  # CSS tokens, glassmorphism, badge themes
│   ├── components.py              # Reusable player cards, pitch grids, metric boxes
│   ├── tab_two_stage.py           # Two-Stage Tournament dashboard view
│   ├── tab_optimizer.py           # MILP squad builder view
│   ├── tab_montecarlo.py          # Stochastic simulation view
│   ├── tab_fixtures.py            # FDR ticker view
│   └── tab_market.py              # Price predictor & transfer trends view
│
├── tuner/                          # Hyperparameter tuning package (unchanged)
├── backtest/                       # Historical walk-forward simulation (unchanged)
├── app.py                          # Slim entry point (~80 lines): routing & sidebar only
├── config.yaml                     # Central parameter repository
└── config_manager.py               # Safe config getter & schema validation
```

---

## 6. Comparison: Before vs. After Modularization

| Dimension | Current Monolithic State | Target Modular State |
| :--- | :--- | :--- |
| **`app.py` File Size** | 2,641 lines (137 KB) | ~80 lines (slim router importing `ui/tab_*.py`) |
| **Tracker Organization** | 8 loose scripts scattered in root | 1 unified package (`trackers/`) |
| **Engine Coupling** | Direct calls inside UI callback functions | Clean `@dataclass` contracts (`TwoStageOptimizationReport`) |
| **Testability** | Hard to unit-test UI-bound logic | Every engine and tracker tested in isolation without Streamlit |
| **Execution Safety** | Modifying UI risks breaking optimization | Total separation: UI changes cannot break analytical engines |

---

## 7. Action Plan & Sequencing

```text
EXECUTION SEQUENCE:
================================================================================
STEP 1 [COMPLETED]:
├── Tuner finished 3,151 trials across 4 worker cores (+268 pts gain).
├── Updated `config.yaml` with winning `tuned:` profile (#1685).
└── Created dedicated `modulerization` branch.

STEP 2 [COMPLETED]:
├── Codified strict Separation of Concerns & Anti-Patterns in `.agents/rules/`.
├── Documented Two-Stage "Screen & Simulate" architecture.
└── Documented Shane's Human Domain Intel Feed & Non-Impacting Defaults.

STEP 3 [COMPLETED ON BRANCH `modulerization`]:
├── Created `analytics/`, `trackers/`, `clients/`, `ui/` packages.
├── Relocated 8 flat tracker scripts into `trackers/` with backward-compatible aliases.
├── Relocated core engines (`fpl_optimizer.py`, `montecarlo_engine.py`, `xp_model.py`) into `analytics/`.
├── Implemented clean `TwoStageOptimizer` in `analytics/two_stage_optimizer.py`.
├── Implemented Shane's `ShaneIntelManager` with identity defaults in `analytics/domain_intel.py`.
├── Decomposed the 2,641-line `app.py` monolith into modular Streamlit tabs in `ui/tabs/`.
└── Ran automated pytest suite: 53 tests passing (100% test pass rate).
================================================================================
```

---

## 8. Summary

* **Verdict**: Modularization is vital for long-term maintainability, but **timing is everything**.
* **Prudent Strategy**: First modularize the **interfaces** (creating `two_stage_optimizer.py` with zero disruption to the active overnight tuner). Then, once the tuner completes, perform the **physical directory reorganization** to turn the flat root and `app.py` monolith into an enterprise-grade package architecture.
