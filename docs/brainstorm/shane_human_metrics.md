---
type: Brainstorm
title: "[#009] Shane's Human Domain Metrics & Tacit Knowledge Formalization"
description: "Translating subjective domain scouting heuristics into formal quantitative signals."
tags: [brainstorm, scout, tactics, moneyball]
status: Legacy
sources: []
generated:
  at: "2026-09-16T22:30:00Z"
  by: "agent:backfill_okf"
---
# Brainstorm: Shane's Human Domain Metrics & Tacit Knowledge Feed
## The Qualitative-to-Quantitative Bridge for Rubies Rangers

**Status**: PROPOSED / BRAINSTORM  
**Target Subsystems**: `config.yaml`, `fpl_optimizer.py`, `montecarlo_engine.py`, `docs/brainstorm/two_stage_screen_and_simulate.md`  
**Collaborators**:
* **Quantitative & Operations Research Lead**: Systems Architecture & Mathematical Solvers (No football knowledge required)
* **Football Domain Specialist (Shane)**: Real-World Tactical Intelligence, Eye-Test Nuance & Exogenous Shocks

---

## Executive Summary

Pure statistical models and Mixed-Integer Linear Programs (MILP) are mathematically rigorous, but they suffer from **information blindness**: they only know what is recorded in historical data tables and API endpoints.

In real-world football, crucial events happen outside the tabular metrics:
* A player was involved in an off-pitch incident or personal emergency.
* A manager subtly hinted in a press conference that a starter will be rested for a midweek Champions League clash.
* A player's tactical position was changed on the pitch (e.g. a defender shifted into defensive midfield, or a winger played as a central striker).
* The "Eye Test": a player looks visibly exhausted, sluggish, or conversely, exceptionally sharp in live match play before the stats catch up.

This document establishes the **"Shane Metric Feed"**: a structured, reproducible interface that translates Shane's qualitative football domain knowledge into formal mathematical inputs for Rubies Rangers.

---

## 1. The Three Injection Tiers: Where Shane's Knowledge Enters the Pipeline

Shane's insights enter the modeling pipeline at three distinct stages depending on the *nature* of the information:

```text
SHANE'S TACIT KNOWLEDGE INJECTION PIPELINE:
================================================================================
                       [ SHANE'S WEEKLY INPUT FEED ]
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           ▼                         ▼                         ▼
       [ TIER 1 ]                [ TIER 2 ]                [ TIER 3 ]
    Hard Facts & Multipliers   Minutes Risk & Volatility   Strategy & Risk Appetite
   (Pre-Stage 1 / Feature)   (Pre-Stage 2 / Monte Carlo)  (Post-Stage 2 / Decision)
           │                         │                         │
           ▼                         ▼                         ▼
   • Exclude Porro (Accident)  • Pep Roulette (Sub @ 60) • Chase 1st Place (P90)
   • 1.25x Boost (New Role)    • Late Fitness Test (60%) • Protect Lead (P10)
           │                         │                         │
           ▼                         ▼                         ▼
    [ STAGE 1: MILP ]        [ STAGE 2: MONTE CARLO ]   [ FINAL SQUAD PICK ]
   Solves Knapsack around     Simulates auto-subs and     Selects between
   rebalanced budget          bench coverage              efficient trade-offs
================================================================================
```

---

### Tier 1: Pre-Stage 1 Exogenous Shocks & Player Multipliers
**Where it enters**: Input DataFrame / Feature Store (Before MILP runs).  
**Why here**: The MILP solver needs to rebalance the £100m budget *around* these facts. If a player is ruled out, MILP must not waste budget on them.

* **Hard Exclusion (State Shock)**:
  * *Shane's Insight*: "Player X was in an accident / broke a bone in training / had a training ground bust-up and won't play."
  * *Model Translation*: `status: 'unavailable'`, `availability: 0.0`. MILP constraint $x_i = 0$.
* **Tactical Role Shift (Out-Of-Position Advantage)**:
  * *Shane's Insight*: "Player Y is listed as a defender, but the new coach is playing him as an attacking central midfielder."
  * *Model Translation*: `xgi_multiplier: 1.30` (30% boost to attacking involvement).
* **The "Eye Test" Sharpness Multiplier**:
  * *Shane's Insight*: "Player Z looks electric on the ball, hitting the woodwork twice; underlying stats are lagging reality."
  * *Model Translation*: `subjective_multiplier: 1.15`.

---

### Tier 2: Pre-Stage 2 Volatility & Minutes Jitter
**Where it enters**: Parameters passed into `MonteCarloEngine` (Between Stage 1 and Stage 2).  
**Why here**: The player is still worth drafting, but their variance profile has changed. Monte Carlo needs to stress-test your bench depth.

* **Early Substitution / Congestion Risk ("Pep Roulette")**:
  * *Shane's Insight*: "Team has Real Madrid away 3 days after this match. If they lead by 2 goals, the manager will pull him off at 60 minutes."
  * *Model Translation*: 
    * `expected_minutes: 60.0` (down from standard 85.0).
    * `minutes_jitter_std: 14.0` (higher volatility).
* **Nagging Injury / Late Fitness Test**:
  * *Shane's Insight*: "He missed training on Thursday with a tight hamstring. He might start, but he is a coin-flip to last the game."
  * *Model Translation*: `p_fit: 0.60` (40% chance of 0 minutes, forcing Monte Carlo to trigger automatic bench substitutions).

---

### Tier 3: Post-Stage 2 Strategy & Risk Profile
**Where it enters**: Post-Simulation Selection (After Monte Carlo produces distributions).  
**Why here**: The simulation has produced distinct candidate profiles; Shane's input here reflects strategic risk appetite.

* **Chasing Mini-League Rivals**:
  * *Shane's Insight*: "Our rival owns Salah and Haaland. We cannot win by copying them; we need explosive variance."
  * *Model Translation*: Sort candidates by `ceiling_p90` (90th percentile upside) rather than mean EV.
* **Defending a Lead**:
  * *Shane's Insight*: "We are 35 points ahead; we just need to avoid a disastrous blowout week."
  * *Model Translation*: Sort candidates by `floor_p10` (capital preservation floor).

---

## 2. Shane's Weekly Intake Template (The Domain Sheet)

Each Gameweek, Shane can fill out a simple, 4-row structured checklist without needing to write any Python code:

```text
================================================================================
RUBIES RANGERS — SHANE'S DOMAIN INTEL SHEET (GW ___)
================================================================================

1. HARD EXCLUSIONS & BREAKING SHOCKS (Exclude from MILP):
   • Player: [ Player Name ]
     Reason: [ Injury rumor / Training bust-up / Personal emergency ]
     Confidence: [ Definite / Probable ]

2. TACTICAL ROLE SHIFTS & EYE TEST BOOSTS (Multipliers):
   • Player: [ Player Name ]
     Observation: [ Playing higher up pitch / Looks razor sharp / New role ]
     Suggested Shift: [ Slight Boost (+10%) / Major Boost (+25%) ]

3. ROTATION & MINUTES CONGESTION RISKS (Monte Carlo Jitter):
   • Player: [ Player Name ]
     Observation: [ Champions League midweek / Manager rotation warning ]
     Risk Level: [ Early Sub at 60 mins / 50-50 Start Risk ]

4. CAPTAINCY & DIFFERENTIAL CALL (Post-Simulation Selection):
   • Rival Status: [ Chasing (High Risk P90) / Defending (Safe Floor P10) ]
================================================================================
```

---

## 3. Data Schema: How Rubies Rangers Consumes Shane's Feed

In `config.yaml` or a dedicated override file (`data/shane_intel.yaml`), the system can store Shane's inputs as a clean dictionary:

```yaml
# data/shane_intel.yaml
gameweek: 5
updated_at: "2026-09-12"

shane_metrics:
  # Tier 1: Hard Exclusions (Scoped to Squad / Shortlist with TTL)
  exclusions:
    - name: "Pedro Porro"
      scope: "squad"                # Target is currently in user's 15-man squad
      valid_gameweek: 5             # STRICT TTL: Automatically expires after GW5
      reason: "Unspecified injury doubt / Limping in training"
      active: true

  # Tier 1: Subjective / Tactical Multipliers (With TTL)
  player_multipliers:
    - name: "Antoine Semenyo"
      scope: "shortlist"            # Prospective transfer-in target
      valid_gameweek: 5             # STRICT TTL: Automatically expires after GW5
      multiplier: 1.20
      reason: "Taking high volume of shots, looks explosive on tape"
    - name: "Rico Lewis"
      scope: "squad"                # Target is in user's 15-man squad
      valid_gameweek: 5             # STRICT TTL: Automatically expires after GW5
      multiplier: 1.15
      reason: "Inverting into central attacking midfield"

  # Tier 2: Minutes & Volatility Adjustments (With TTL)
  stochastic_adjustments:
    - name: "Phil Foden"
      scope: "squad"                # Target is in user's 15-man squad
      valid_gameweek: 5             # STRICT TTL: Automatically expires after GW5
      p_fit: 0.70
      expected_minutes: 65
      minutes_std: 15.0
      reason: "Returning from illness, Champions League on Wednesday"

  # Tier 3: Strategic Posture
  strategic_posture: "balanced"     # "high_floor", "balanced", or "high_ceiling"
```

---

## 4. Temporal Decay & Time-To-Live (TTL) Governance

### The "Ghost Metric" Hazard
The biggest risk of human input in algorithmic systems is **stale state accumulation**:
* Shane enters: *"Phil Foden has flu and might be benched for GW5."*
* Everyone forgets to delete the file.
* Five months later in Gameweek 28, the solver is still penalizing Foden because the human override became permanent!

### Strict Temporal Governance Rules:
1. **Mandatory Gameweek Validity (`valid_gameweek`)**:
   * Every single Shane metric is **ephemeral by default**.
   * A metric applies **only to the specified Gameweek** (e.g. `valid_gameweek: 5`).
   * Once the live deadline for GW5 passes, the engine's data ingestion layer automatically flags the record as `EXPIRED` and discards it.
   * To persist a metric into GW6, Shane must explicitly renew it.
2. **Squad Scope Enclosure (`scope: "squad"`)**:
   * Shane does not need to analyze all 650 players in the Premier League.
   * Shane's analytical focus is strictly constrained to:
     * **Primary Scope (`scope: "squad"`)**: The 15 players currently in your Rubies Rangers team.
     * **Secondary Scope (`scope: "shortlist"`)**: The top 2 to 3 prospective transfer-in targets flagged by the model.
   * This bounds the human cognitive load and prevents unmonitored players from carrying rogue human biases.

---

## 6. The In-App UI Workflow: "Domain Intel & Availability Desk"

Rather than requiring Shane to manually edit YAML files, the dashboard must provide an interactive, intuitive UI workflow in Streamlit. This translates Shane's real-world observations into model parameters via **standardized, generic metric categories**.

### Strict UI Control Constraint: Sliders & Option Selectors Only
To eliminate typing errors, illegal values, negative costs, or formatting crashes, **all UI controls must strictly be either Option Selectors or Sliders (Zero free-text input fields)**:
* **Option Selectors (`st.selectbox` / `st.radio` / `st.segmented_control`)**: Used for all discrete states (availability flags, eligibility, transfer status, reason tags, and TTL windows).
* **Bounded Sliders (`st.slider`)**: Used for continuous numerical parameters (minutes expectation and eye-test multipliers), with their default values fixed squarely at the **non-impacting identity element** (e.g. `1.00x` multiplier or `85` mins).

```text
INTERACTIVE APP WORKFLOW (SLIDERS & OPTION SELECTORS ONLY):
================================================================================
  [ 📋 YOUR 15-MAN SQUAD ]
  ┌────────────────────────────────────────────────────────────────────────────┐
  │ Pedro Porro (£5.5m) | Tottenham | DEF                                      │
  │ Official FPL Flag: "Unspecified injury - 75% chance of playing"            │
  │                                                                            │
  │ [Option Selector] Availability:                                            │
  │   ( ) Official Default  (•) 0% Confirmed Out  ( ) 25%  ( ) 50%  ( ) 75%    │
  │                                                                            │
  │ [Option Selector] Reason Category:                                         │
  │   [ Personal Shock / Accident / Emergency               ▼ ]                │
  │                                                                            │
  │ [Slider] Expected Minutes:                                                 │
  │   45 ───────────── 60 ─────────────● 85 ──────── 90  (Default: 85 mins)    │
  │                                                                            │
  │ [Slider] Eye-Test Form Multiplier:                                         │
  │   0.80x ────────── 0.90x ─────────● 1.00x ────── 1.20x  (Default: 1.00x)   │
  │                                                                            │
  │ [Option Selector] Validity Window (TTL):                                   │
  │   (•) GW5 Only (Ephemeral Default)   ( ) GW5 + GW6   ( ) Until Cleared     │
  │                                                                            │
  │ Status Badge: 🛑 [EXCLUDED FOR GW5]                                       │
  └────────────────────────────────────────────────────────────────────────────┘
  
  [ ⚡ APPLY INTEL & RE-RUN TWO-STAGE OPTIMIZATION ]   [ 🔄 RESET TO DEFAULTS ]
================================================================================
```

---

### 1. The Non-Impacting Default Invariant (Identity Passthrough)

A core engineering invariant governs this entire subsystem: **The default state of every human metric MUST be the mathematical identity element.**


```text
MATHEMATICAL INVARIANT:
f(Official_Data, Human_Defaults) ≡ f(Official_Data) [Zero Delta]
```

If Shane opens the app, changes nothing, or hits `[Reset to Defaults]`:
* The system introduces **zero passive distortion**, zero bias, and zero synthetic noise.
* All values pass through bit-for-bit identical to the pure algorithmic baseline.
* Expired metrics automatically fall back to this non-impacting identity state.

---

### 2. Standardized Generic Metric Taxonomy & Default Passthroughs

| Category | Generic Metric Enum | Model Translation | Impact vs. Pure Algorithmic Baseline |
| :--- | :--- | :--- | :--- |
| **Availability / Health** | **`DEFAULT_OFFICIAL` (DEFAULT)** | **`chance_of_playing = None`** | **ZERO IMPACT**: Pure passthrough of official FPL API status |
| | `CONFIRMED_OUT_0` | `chance_of_playing = 0.0`, `status = 'u'` | Pre-Stage 1 (MILP Hard Exclusion: $x_i = 0$) |
| | `HEAVY_DOUBT_25` | `chance_of_playing = 0.25`, `p_fit = 0.25` | Stage 1 Weight & Stage 2 Monte Carlo 75% Auto-Sub |
| | `COIN_FLIP_50` | `chance_of_playing = 0.50`, `p_fit = 0.50` | Stage 2 Monte Carlo 50% Auto-Sub Trigger |
| | `MILD_DOUBT_75` | `chance_of_playing = 0.75`, `p_fit = 0.75` | Stage 2 Monte Carlo 25% Auto-Sub Trigger (Porro flag) |
| | `CLEARED_FIT_100` | `chance_of_playing = 1.0`, `status = 'a'` | Clears false-alarm official yellow flags |
| **Eligibility & Transfers**| **`DEFAULT_ELIGIBLE` (DEFAULT)** | **`None`** | **ZERO IMPACT**: Inherits official Premier League squad status |
| | `TRANSFERRED_OUT` | `status = 'u'`, removed from pool | Pre-Stage 1 (MILP Hard Exclusion) |
| | `INELIGIBLE_LOAN` | `status = 'u'` for this GW only | Pre-Stage 1 (MILP Hard Exclusion vs Parent Club) |
| | `INTERNAL_SANCTION` | `chance_of_playing = 0.0` | Pre-Stage 1 (MILP Hard Exclusion: Locker Room Ban) |
| **Tactical & Minutes Risk**| **`DEFAULT_MINUTES` (DEFAULT)** | **`None`** | **ZERO IMPACT**: Uses standard baseline minutes expectation ($\mu=85, \sigma=7.5$) |
| | `ROTATION_HOOK_60` | `expected_minutes = 60`, `std = 15.0` | Pre-Stage 2 (Monte Carlo Midweek Congestion Jitter) |
| | `FULL_90_LOCK` | `expected_minutes = 90`, `std = 2.0` | Pre-Stage 2 (High Minutes Security) |
| | `OUT_OF_POSITION_ADV`| `xgi_multiplier = 1.25` | Pre-Stage 1 (MILP Objective Attacking Boost) |
| **Eye-Test Momentum** | **`DEFAULT_BASELINE` (DEFAULT)** | **`multiplier = 1.00`** | **ZERO IMPACT**: Absolute identity multiplier (0.0% distortion) |
| | `COLD_SLUGGISH` | `multiplier = 0.85` | Pre-Stage 1 (-15% subjective discount on form) |
| | `HOT_ELECTRIC` | `multiplier = 1.15` | Pre-Stage 1 (+15% subjective boost on underlying stats) |


---

### 2. Parallels in Other Quantitative Disciplines

This exact "human-in-the-loop generic metric" pattern is used across leading quantitative industries:

1. **Quantitative Finance (The Black-Litterman Asset Allocation Model)**:
   * Quantitative portfolio managers do not manually rewrite the covariance matrix.
   * Instead, they enter standardized "Investor Views" (e.g. *"Asset X will outperform Asset Y by 2% over a 30-day horizon with 70% confidence"*).
   * The mathematical engine formally blends the human views with market equilibrium priors.
2. **Professional DFS Platforms (SaberSim / FantasyLabs)**:
   * Provide a standardized "Player Status & Minutes Exposure" table where users can override projected minutes, lock/exclude players, and adjust volatility sliders before running 20,000 game simulations.
3. **Defense & Aviation Command Systems**:
   * Automated route and resource optimization algorithms allow tactical operators to place temporary "Threat Corridor / No-Fly Overrides" with strict expiration timestamps.

---

### 3. Step-by-Step UI User Flow for Shane and You

```text
STEP 1: Shane opens the "Domain Intel Desk" tab in Rubies Rangers.
STEP 2: The app lists your current 15 squad players with their live FPL flags.
STEP 3: Shane selects Pedro Porro:
         • Availability: "Confirmed Out / Accident"
         • Validity: "GW5 Only"
STEP 4: Shane selects Phil Foden:
         • Tactical Risk: "Rotation Hook @ 60 mins (Midweek Champions League)"
         • Validity: "GW5 Only"
STEP 5: Shane clicks "[⚡ Apply & Re-Run Optimization]".
STEP 6: The system runs in 300ms:
         • MILP immediately sells Porro and drafts Gabriel into all candidates.
         • Monte Carlo stress-tests Foden's 60-minute limit and validates bench depth.
STEP 7: The UI displays the updated tournament cards with clean provenance badges:
         `[💡 Shane Intel: Porro Excluded (GW5) | Foden 60m Jitter (GW5)]`
STEP 8: When GW5 finishes, the system rolls to GW6 and automatically purges all overrides.
```

---

## 7. Defensive Implementation Rules for Shane's Feed

Following the repository rules in [`.agents/rules/python_standards.md`](../.agents/rules/python_standards.md) and [`.agents/rules/moneyball_strategy.md`](../.agents/rules/moneyball_strategy.md):

1. **Automatic Pruning on Gameweek Roll**: The system checks current gameweek via `fpl_client.get_current_gameweek()`. Any override where `valid_gameweek < current_gw` is automatically ignored and purged from the solver matrix.
2. **Graceful Config Fallback**: If `shane_intel.yaml` is empty, missing, expired, or has a syntax error, the system gracefully falls back to 100% automated algorithmic data without crashing.
3. **Deterministic Seed Preservation**: Shane's subjective multipliers modify deterministic expectations before Monte Carlo; random draws in Monte Carlo remain deterministically seeded (`seed=42`).
4. **Audit Trail & Visual Transparency**: Every squad recommendation affected by Shane's metrics must clearly display a badge in the UI:
   `[💡 Shane Intel (GW5 Only): Semenyo boosted +20% (Eye Test)]` so human inputs are never permanent and never hidden.
