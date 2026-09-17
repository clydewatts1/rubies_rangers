---
type: Brainstorm
title: "[#006] Macro Match-State Jitter & Teammate Covariance Modeling"
description: "Full covariance matrix simulation modeling match-state blowouts, game script correlation, and variance."
tags: [brainstorm, monte-carlo, optimization, tactics]
status: Legacy
sources: ["docs/issues/iss_006_macro_match_jitter_covariance.md"]
generated:
  at: "2026-09-16T22:30:00Z"
  by: "agent:backfill_okf"
---
# Brainstorm: Macro Match-State Jitter & Teammate Covariance Modeling
## Inspired by Numerical Weather Ensemble Forecasting for Monte Carlo Simulation

**Status**: PROPOSED / BRAINSTORM  
**Target Subsystems**: `montecarlo_engine.py`, `xp_model.py`, `config.yaml`, `backtest/simulator.py`  
**Related Rule**: [`.agents/rules/moneyball_strategy.md`](../.agents/rules/moneyball_strategy.md) (Section 2: Stochastic Modeling & Joint Probability Distributions)

---

## Executive Summary

Rubies Rangers currently injects stochastic "jitter" at the **micro player level** (Gaussian minutes volatility, Bernoulli fitness tests, and Poisson event draws). While this accurately models individual player risk, each player is simulated independently. 

This creates the **Independent Teammate Fallacy**:
* Two defenders from the same club (e.g. Gabriel and Saliba) can have conflicting clean sheet results in the exact same simulation run.
* A forward can score a hat-trick against a goalkeeper who simultaneously keeps a clean sheet in the user's squad.
* Total team goal volume varies wildly between teammates in the same match.

Drawing inspiration from **Numerical Weather Prediction (NWP) Ensemble Forecasting**—where meteorologists perturb macro atmospheric fields to evaluate joint trajectory uncertainty—this enhancement introduces **Hierarchical Two-Tier Monte Carlo Simulation**. 

By first simulating the macro match state (pace, team goals scored, and team goals conceded) and then conditioning individual player outcomes on that shared state, the model captures **true joint portfolio covariance**, realistic double-up variance, and accurate tail risk ($P_{10}$ downside floor and $P_{90}$ upside ceiling).

---

## 1. Scientific Background: Numerical Weather Forecasting & Stochastic Jitter

In atmospheric physics (ECMWF, GFS), running a single deterministic model from initial sensor readings fails because small measurement errors explode over time (Lorenz's butterfly effect).

```text
Deterministic Forecasting (Traditional FPL Model):
  Initial Conditions (Scalar xG, xA)  ───> Single Deterministic Run ───> Flawed Point Estimate

Ensemble Forecasting with Jitter (Weather Physics / Advanced Monte Carlo):
  Initial Conditions ──┬──> Run 01 (+Jitter A) ───> Trajectory 01 ──┐
                       ├──> Run 02 (+Jitter B) ───> Trajectory 02 ──┼──> Full Joint Probability
                       └──> Run N  (+Jitter N) ───> Trajectory N  ──┘    Distribution & Tail Risk
```

In modern weather ensembles, two types of perturbations are injected:
1. **Initial Condition Perturbation**: Slight variations in starting measurements (e.g. player fitness, starting probability).
2. **Stochastic Physics Parameterization (Macro Jitter)**: Perturbing the equations of motion themselves (e.g. overall match pace, referee strictness, high-tempo chaos vs. defensive gridlock).

Rubies Rangers currently implements Level 1 (micro player noise). This enhancement implements Level 2 (macro match physics).

---

## 2. Current State vs. Proposed Architecture

### Current State: Independent Micro Jitter

```text
Match Context (Fixed Bookmaker xG)
  │
  ├──> Player A (Gabriel, DEF)  ──> Indep. Sim 42 ──> cs_draw = 1 (Clean Sheet)  [INCONSISTENT]
  │
  └──> Player B (Saliba, DEF)   ──> Indep. Sim 42 ──> cs_draw = 0 (Conceded)     [INCONSISTENT]
```

* **Current Implementation** in `montecarlo_engine.py`:
  - Starter minutes: `mins = np.random.normal(exp_starter_mins, 7.5)`
  - Clean sheet draw: `cs_draw = np.random.binomial(1, cs_prob, n_sims)` (drawn independently per player)
  - Player goals: `goals_draw = np.random.poisson(match_xg)` (drawn independently per player)

### Proposed State: Hierarchical Two-Tier Ensemble Simulation

```text
[TIER 1: MACRO MATCH STATE JITTER] (Simulated Once per Fixture per Run k)
  │
  ├── Draw Match Pace Jitter:  pace_mult ~ LogNormal(0, sigma_pace)
  ├── Draw Home Team Goals:    G_home ~ Poisson(h_xg * pace_mult)
  ├── Draw Away Team Goals:    G_away ~ Poisson(a_xg * pace_mult)
  ├── Determine Clean Sheets:  CS_home = (G_away == 0), CS_away = (G_home == 0)
  │
  ▼
[TIER 2: MICRO PLAYER REALIZATION] (Conditioned on Tier 1 Match State k)
  │
  ├── Gabriel (Arsenal DEF, Run k):
  │     If mins >= 60: inherits Arsenal CS_home_k! Concession penalty = -(G_away_k // 2)
  │
  ├── Saliba (Arsenal DEF, Run k):
  │     If mins >= 60: inherits Arsenal CS_home_k! Concession penalty = -(G_away_k // 2)
  │     (Both defenders mathematically guaranteed identical clean sheet status)
  │
  └── Saka (Arsenal Attacker, Run k):
        Goal share sampled conditionally from the drawn team goals G_home_k
```

---

## 3. Mathematical Formulation

For each simulation run $k \in \{1, 2, \dots, N\}$ and each fixture $m = (\text{Home}, \text{Away})$:

### Step 1: Match Pace Multiplier (Atmospheric Jitter)
Match intensity varies due to game state, weather, pitch conditions, and tactical pressing:
$$\theta_{m, k} \sim \text{LogNormal}\left(-\frac{\sigma_{\text{pace}}^2}{2}, \sigma_{\text{pace}}\right), \quad \mathbb{E}[\theta_{m, k}] = 1.0$$
* Default baseline: $\sigma_{\text{pace}} = 0.15$.
* In a high-pace simulation run ($\theta > 1.25$), match volume expands for both clubs.
* In a low-pace simulation run ($\theta < 0.75$), match volume contracts for both clubs.

### Step 2: Joint Team Goals & Clean Sheet Realization
Using bookmaker expected goals $(xG_{\text{home}}, xG_{\text{away}})$:
$$G_{\text{home}, k} \sim \text{Poisson}(xG_{\text{home}} \cdot \theta_{m, k})$$
$$G_{\text{away}, k} \sim \text{Poisson}(xG_{\text{away}} \cdot \theta_{m, k})$$

The clean sheet binary state for run $k$ is an exact physical identity:
$$\text{CS}_{\text{home}, k} = \begin{cases} 1 & \text{if } G_{\text{away}, k} = 0 \\ 0 & \text{if } G_{\text{away}, k} \ge 1 \end{cases}$$
$$\text{CS}_{\text{away}, k} = \begin{cases} 1 & \text{if } G_{\text{home}, k} = 0 \\ 0 & \text{if } G_{\text{home}, k} \ge 1 \end{cases}$$

### Step 3: Coupled Player Scoring Conditioned on Macro State

1. **Defenders & Goalkeepers (Coupled Floor & Penalties)**:
   For player $i$ on team $T$ in run $k$:
   $$\text{CS\_pts}_{i, k} = \mathbf{1}(\text{mins}_{i, k} \ge 60) \cdot \text{CS}_{T, k} \cdot 4$$
   $$\text{GC\_penalty}_{i, k} = -\left\lfloor \frac{G_{\text{conceded}, k} \cdot (\text{mins}_{i, k} / 90)}{2} \right\rfloor$$

2. **Attackers (Coupled Ceiling & Team Goal Allocation)**:
   Individual expected goals are scaled by the macro match pace:
   $$\lambda_{\text{goal}, i, k} = \text{NPxG\_90}_i \cdot \left(\frac{\text{mins}_{i, k}}{90}\right) \cdot \theta_{m, k} \cdot \text{FormMult}_i$$
   $$\text{goals}_{i, k} \sim \text{Poisson}(\lambda_{\text{goal}, i, k})$$
   *(Optional Constraint Mode: cap individual goals so $\sum_{i \in T} \text{goals}_{i, k} \le G_{T, k}$)*.

---

## 4. Key Portfolio & Decision Benefits

### A. Realistic Double-Up & Triple-Up Risk Modeling
* **The "All-or-Nothing" Defense**: In reality, doubling up on Arsenal defenders (Raya + Gabriel) is a high-variance strategy: either you gain $+12$ points or lose clean sheets entirely.
* Independent modeling artificially underestimates this portfolio variance (the central limit theorem falsely smooths independent draws).
* Coupled macro jitter correctly reveals the true bimodal distribution: wider 10th-to-90th percentile spreads ($P_{10}$ to $P_{90}$).

### B. Natural Negative Covariance (Attacker vs. Own Defender)
* If your squad owns an attacker (e.g. Erling Haaland) facing your goalkeeper (e.g. David Raya):
  * When Man City scores in run $k$, Haaland earns points, but Raya's clean sheet is simultaneously wiped out.
  * The optimizer can natively calculate the **hedging effect** (lowering portfolio variance) versus an unhedged lineup.

### C. True Game-Theoretic Mini-League Tail Optimization
* In head-to-head or mini-league matchups where you need an explosive ceiling ($P_{90}$) to overturn a 30-point deficit:
  * The solver will naturally identify that doubling up on an elite home defense yields higher ceiling variance than diversifying across different clubs.

---

## 5. Technical Blueprint & Vectorized Implementation

To maintain fast execution across 5,000 to 10,000 simulations without nested Python loops, the entire two-tier architecture is vectorized using NumPy:

```python
# ============================================================================
# Vectorized Macro Match Jitter (Pre-computed once for all 10 fixtures)
# ============================================================================
import numpy as np

def simulate_macro_fixtures(fixture_odds: dict, n_sims: int = 5000, pace_sigma: float = 0.15) -> dict:
    """
    Simulates macro match outcomes across N runs for all Premier League fixtures.
    Returns dictionary mapping team_code -> dict of arrays of shape (n_sims,).
    """
    team_macro_states = {}
    
    for fix_id, fix in fixture_odds.items():
        h_team = fix["home"]
        a_team = fix["away"]
        h_xg = fix["h_goals"]
        a_xg = fix["a_goals"]
        
        # 1. Atmospheric Match Pace Jitter
        pace_mult = np.random.lognormal(-0.5 * (pace_sigma ** 2), pace_sigma, n_sims)
        
        # 2. Joint Goals Scored & Conceded
        h_goals = np.random.poisson(h_xg * pace_mult)
        a_goals = np.random.poisson(a_xg * pace_mult)
        
        # 3. Clean Sheet Binary Vectors
        h_cs = (a_goals == 0).astype(int)
        a_cs = (h_goals == 0).astype(int)
        
        team_macro_states[h_team] = {
            "goals_scored": h_goals,
            "goals_conceded": a_goals,
            "clean_sheet": h_cs,
            "pace_mult": pace_mult
        }
        team_macro_states[a_team] = {
            "goals_scored": a_goals,
            "goals_conceded": h_goals,
            "clean_sheet": a_cs,
            "pace_mult": pace_mult
        }
        
    return team_macro_states
```

### Consumption in `simulate_player()`:

```python
# Instead of independent binomial draw:
# cs_draw = (mins >= 60.0) * np.random.binomial(1, cs_prob, n_sims)

# Coupled clean sheet draw using macro match state:
team_state = macro_states.get(team_short)
if team_state is not None:
    cs_draw = (mins >= 60.0) * team_state["clean_sheet"]
    gc_draw = team_state["goals_conceded"]
else:
    # Fallback to independent draw if fixture unmapped
    cs_draw = (mins >= 60.0) * np.random.binomial(1, cs_prob, n_sims)
    gc_draw = np.random.poisson(team_xgc * (mins / 90.0))
```

---

## 6. Proposed Configuration Schema (`config.yaml`)

```yaml
monte_carlo:
  macro_jitter:
    enabled: true                   # Feature toggle
    pace_volatility: 0.15           # LogNormal sigma for match pace jitter
    enforce_coupled_defense: true   # Synchronizes CS and GC across teammates
    enforce_pace_scaling: true      # Attacker xG scaled by match pace multiplier
    clip_pace_min: 0.50
    clip_pace_max: 2.00
```

---

## 7. Ablation & Empirical Validation Plan

To satisfy [`.agents/rules/moneyball_strategy.md`](../.agents/rules/moneyball_strategy.md) Section 5 & 6 (First-Principles Alpha vs. Folk Wisdom):

1. **Backtest Metric**: Run `tuner/` walk-forward backtest across seasons 2021-22 and 2022-23.
2. **Comparison**:
   * Mode A: Independent Micro Jitter (Current baseline).
   * Mode B: Hierarchical Two-Tier Jitter (`pace_volatility = 0.15`).
3. **Hypothesis to Validate**:
   * Mode B will more accurately estimate squad portfolio variance (Sharpe ratio accuracy).
   * Mode B will prevent catastrophic double-up over-allocation during treacherous away fixtures, improving out-of-sample test points and downside capital preservation ($P_{10}$).

---

## 8. Summary & Next Steps

* **Concept**: Borrowing proven ensemble forecasting physics from meteorology to eliminate the independent teammate fallacy in FPL Monte Carlo simulation.
* **Cost**: Zero latency overhead (NumPy vectorization computes 10 fixture arrays in $< 5$ milliseconds).
* **Action**: Saved to brainstorm archive. Awaiting user authorization before integrating into `montecarlo_engine.py` and `config.yaml`.
