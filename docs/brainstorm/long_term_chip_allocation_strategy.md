# Brainstorm: Long-Term Chip Allocation Strategy & Optimal Stopping Engine
## Multi-Period Dynamic Programming & Real Options Theory for FPL Chips

**Status**: PROPOSED / BRAINSTORM  
**Target Subsystems**: `fpl_optimizer.py`, `montecarlo_engine.py`, `config.yaml`, `app.py`  
**Related Rule**: [`.agents/rules/moneyball_strategy.md`](../.agents/rules/moneyball_strategy.md) (Section 3: Dynamic Programming & Multi-Period Utility)

---

## Executive Summary

Fantasy Premier League provides each manager with a finite inventory of **strategic power-ups (chips)**:
1. **Wildcard 1 (WC1)**: Unlimited permanent free transfers (Valid GW1 ➔ GW19).
2. **Wildcard 2 (WC2)**: Unlimited permanent free transfers (Valid GW20 ➔ GW38).
3. **Free Hit (FH)**: Unlimited transfers for exactly one gameweek; squad reverts next week (1 per season).
4. **Triple Captain (TC)**: Designated captain receives $3\times$ points instead of $2\times$ (1 per season).
5. **Bench Boost (BB)**: Points from all 4 bench players are added to the gameweek total (1 per season).

Currently, Rubies Rangers tracks competitor chip usage via `league_tracker.py` and supports full 15-player squad re-optimization in `fpl_optimizer.py`. However, the platform lacks an **automated multi-period chip planning engine**.

Because chips are **irreversible, scarce options**, playing a chip in a standard single gameweek (like GW4) carries a catastrophic **opportunity cost**. Later in the season, FA Cup and League Cup scheduling creates **Double Gameweeks (DGW)**—where teams play twice in one round—and **Blank Gameweeks (BGW)**—where teams do not play.

This document formulates the long-term chip problem as a **Finite-Horizon Markov Decision Process (MDP) with Optimal Stopping**, designing a system to calculate the exact **Option Continuation Value** of each chip across the 38-gameweek horizon.

---

## 1. Mathematical Formulation: Real Options & Optimal Stopping

In financial mathematics and decision theory, holding a chip is equivalent to owning an **American-style call option**:
* At any gameweek $t$, you have two choices: **EXERCISE** (Play the chip now) or **HOLD** (Preserve the option for future turns).

### The Bellman Optimality Equation for Chips

For any chip $C \in \{\text{TC}, \text{BB}, \text{FH}, \text{WC1}, \text{WC2}\}$ at Gameweek $t \in [1, 38]$:

$$V_t(S_t, C) = \max \Big\{ \underbrace{V_{\text{exercise}}(t, C)}_{\text{Immediate Value Today}}, \quad \underbrace{\mathbb{E}\left[V_{t+1}(S_{t+1}, C) \mid S_t\right]}_{\text{Continuation Option Value}} \Big\}$$

### The Decision Rule:
* **PLAY CHIP TODAY** if and only if:
  $$\Delta \text{EV}(t, C) > \max_{s \in (t, T_{\text{expiry}}]} \mathbb{E}\left[\Delta \text{EV}(s, C)\right] + \text{Uncertainty Buffer}$$
* **HOLD CHIP** if the expected future lift in a Double or Blank Gameweek exceeds the gain today.

---

## 2. In-Depth Analysis of Each Chip Archetype

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                    CHIP OPPORTUNITY COST & VALUE MATRIX                      │
├───────────────────┬───────────────┬─────────────────┬────────────────────────┤
│ Chip Archetype    │ Normal GW EV  │ Peak DGW/BGW EV │ Optimal Strategic Role │
├───────────────────┼───────────────┼─────────────────┼────────────────────────┤
│ Triple Captain    │ +5 to +8 pts  │ +15 to +28 pts  │ DGW Elite Home Pair    │
│ Bench Boost       │ +6 to +10 pts │ +22 to +36 pts  │ Massive DGW (Post-WC2) │
│ Free Hit          │ +8 to +14 pts │ +25 to +40 pts  │ Massive BGW Survival   │
│ Wildcard 1        │ +12 to +18 pts│ +20 to +30 pts  │ GW6-10 Fixture Swing   │
│ Wildcard 2        │ +15 to +22 pts│ +35 to +50 pts  │ Setting up DGW & BB    │
└───────────────────┴───────────────┴─────────────────┴────────────────────────┘
```

---

### A. Triple Captain (TC)
* **Official Mechanic**: Multiplies designated captain points by $3\times$ instead of $2\times$ (Net Lift: $+1\times$ captain score).
* **The Math in a Standard Gameweek (GW4)**:
  - An elite captain (e.g. Haaland vs Brentford, Salah vs Forest) plays 90 minutes with an expected points baseline of $\approx 7.5\text{ to }9.0\text{ xP}$.
  - Net chip lift: $+1 \times 8.0 = \mathbf{+8.0\text{ points}}$.
* **The Math in a Double Gameweek (e.g. GW34 / GW37)**:
  - An elite captain plays **two matches (180 minutes)** in the same gameweek (e.g. Southampton at home + Ipswich at home).
  - Expected points across two matches: $\approx 16.0\text{ to }20.0\text{ xP}$.
  - Net chip lift: $+1 \times 18.0 = \mathbf{+18.0\text{ to }+22.0\text{ points}}$ (with a 90th percentile haul ceiling exceeding 40+ points).
* **Opportunity Cost of Playing in GW4**:
  $$\text{Loss} = 18.0 - 8.0 = \mathbf{-10.0\text{ Net Expected Points wasted}}.$$

---

### B. Bench Boost (BB)
* **Official Mechanic**: Scores all 15 squad players (11 starters + 4 bench).
* **The Math in a Standard Gameweek**:
  - Bench players are typically budget enablers (£4.0m DEF, £4.5m MID, £4.0m backup GKP).
  - In a standard gameweek, 2 of your bench players may not play or face top-six opponents (Expected bench output: $\approx 6\text{ to }8\text{ points}$).
* **The Math in a Double Gameweek**:
  - In a major DGW, a properly structured squad features **15 starting players who all have two matches** (30 player appearances!).
  - 4 bench players playing 2 matches each yields 8 player appearances:
    $$\text{Bench Output} \approx 4 \text{ players} \times 2 \text{ matches} \times 3.5 \text{ pts} = \mathbf{24\text{ to }32\text{ points}}.$$
* **The Benchmark Synergy**: Bench Boost should almost **never be played in isolation**. It is paired with **Wildcard 2** one gameweek prior to build an optimal 15-man active squad with zero dead weight.

---

### C. Free Hit (FH)
* **Official Mechanic**: Make unlimited transfers for one gameweek; the following gameweek, your original squad returns automatically.
* **The Math in a Standard Gameweek**:
  - Rebuilding for one week saves at most 1 or 2 transfer hits ($+4$ to $+8$ points).
* **The Math in a Major Blank Gameweek (BGW)**:
  - Due to FA Cup quarter-finals/semi-finals, only 4 to 6 Premier League matches take place in GW29 or GW32.
  - A standard squad may only have 4 or 5 active players. Fielding a competitive XI without Free Hit would require taking $-16$ to $-24$ in transfer penalties and butchering the long-term squad.
  - Free Hit fields a pristine XI of 11 in-form starters for that week alone, outscoring passive managers by **25 to 40 net points**.

---

### D. Wildcard 1 & Wildcard 2 (WC1 / WC2)
* **Official Rules**:
  * **Wildcard 1**: Must be played before the **Gameweek 19 deadline** (December/January). If unused, it expires permanently.
  * **Wildcard 2**: Available from **Gameweek 20** to Gameweek 38.
* **Optimal Timing for WC1 (GW6 to GW10)**:
  - By Gameweek 6, Premier League teams have established tactical identities, new signings have settled, and early sample noise has resolved into statistically significant underlying xG/xA trends.
  - Major fixture swings occur (e.g. Arsenal's brutal early fixtures turn into an ultra-green 8-game run).
  - Wildcard 1 enables a permanent structural pivot without hits.
* **Optimal Timing for WC2 (GW30 to GW34)**:
  - Deployed immediately ahead of the season's largest Double Gameweek to set up the Bench Boost chip.

---

## 3. Algorithmic Architecture: The Season Roadmap Solver

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LONG-TERM CHIP ROADMAP ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
           ┌──────────────────────────┴──────────────────────────┐
           ▼                                                     ▼
┌───────────────────────┐                             ┌───────────────────────┐
│ Fixture Calendar Sync │                             │ Chip Inventory State  │
│ (Detects DGWs & BGWs) │                             │ {WC1, WC2, FH, TC, BB}│
└──────────┬────────────┘                             └──────────┬────────────┘
           │                                                     │
           └──────────────────────────┬──────────────────────────┘
                                      │
                                      ▼
                      ┌───────────────────────────────┐
                      │ Dynamic Programming Solver    │
                      │ (Rollout Horizon: GW_t ➔ GW38)│
                      └───────────────┬───────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         ▼                            ▼                            ▼
┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
│ Expected Lift    │        │ Opportunity Cost │        │ Recommended      │
│ Vector: ΔEV(t, C)│        │ vs. Best Future  │        │ Action:          │
│ for all GWs      │        │ Window           │        │ HOLD vs. PLAY    │
└──────────────────┘        └──────────────────┘        └──────────────────┘
```

### Step 1: Calendar Matrix & Fixture Density Detection
The engine scans the Premier League schedule from the FPL API and detects non-standard gameweeks:
* `is_double_gw(team, gw)`: True if team has $\ge 2$ fixtures in gameweek.
* `is_blank_gw(team, gw)`: True if team has 0 fixtures in gameweek.

### Step 2: Expected Chip Lift Functions

1. **Triple Captain Expected Lift**:
   $$\Delta \text{EV}_{\text{TC}}(t) = \max_{p \in \text{Squad}} \Big(\mathbb{E}[\text{Points}(p, t)]\Big)$$
   *(Calculated using `montecarlo_engine.py` simulating 10,000 runs including DGW minutes)*.

2. **Bench Boost Expected Lift**:
   $$\Delta \text{EV}_{\text{BB}}(t) = \sum_{b \in \text{Bench}} \mathbb{E}[\text{Points}(b, t)]$$

3. **Free Hit Expected Lift**:
   $$\Delta \text{EV}_{\text{FH}}(t) = \mathbb{E}[\text{Points}(\text{OptimalXI}_{\text{FH}}, t)] - \mathbb{E}[\text{Points}(\text{CurrentSquad}, t)] + \text{HitsSaved}(t)$$

4. **Wildcard Structural Lift**:
   $$\Delta \text{EV}_{\text{WC}}(t) = \sum_{w=t}^{t+H} \gamma^{w-t} \Big(\mathbb{E}[\text{Points}(\text{RebuiltSquad}, w)] - \mathbb{E}[\text{Points}(\text{CurrentSquad}, w)]\Big) + 4.0 \cdot \text{HitsSaved}$$

---

## 4. UI Design Blueprint (Streamlit Dashboard View)

A new interactive dashboard screen: **`"🎴 Long-Term Chip Strategy & Season Roadmap"`**:

```text
================================================================================
🎴 RUBIES RANGERS — LONG-TERM CHIP ALLOCATION ENGINE
================================================================================

[ACTIVE CHIP INVENTORY]
  🃏 Wildcard 1: [ AVAILABLE ] (Expires GW19)  ───> Projected Optimal: GW6
  🔥 Triple Captain: [ AVAILABLE ]              ───> Projected Optimal: GW34 (DGW)
  ⚡ Bench Boost: [ AVAILABLE ]                 ───> Projected Optimal: GW37 (DGW)
  🆓 Free Hit: [ AVAILABLE ]                    ───> Projected Optimal: GW29 (BGW)
  🃏 Wildcard 2: [ LOCKED ] (Unlocks GW20)     ───> Projected Optimal: GW33 (Setup)

--------------------------------------------------------------------------------
💡 STRATEGIC RECOMMENDATION FOR GAMEWEEK 4:
🔒 HOLD ALL CHIPS (Confidence: 99.4%)
Opportunity Cost Warning: Playing Triple Captain in GW4 burns an estimated 
12.4 expected points compared to holding for the Double Gameweek in GW34.
--------------------------------------------------------------------------------

📊 SEASON ROADMAP (GW1 ➔ GW38 SIMULATED TRAJECTORY)
[ Interactive Plotly Chart showing Expected Value Lift across all 38 weeks ]
Peak Spikes highlighted:
  • GW6:  Wildcard 1 Window (Arsenal & Villa fixture turn)
  • GW29: Free Hit Window (FA Cup Blank Gameweek)
  • GW34: Triple Captain Window (Haaland DGW vs SOU + IPS)
  • GW37: Bench Boost Window (Double Gameweek 15-player surge)
================================================================================
```

---

## 5. Proposed Configuration Schema (`config.yaml`)

```yaml
chips:
  enabled: true
  min_dgw_expected_lift: 15.0       # Minimum EV gain to trigger Triple Captain
  min_bb_fixture_count: 7           # Minimum bench fixtures (out of 8) for Bench Boost
  wc1_expiry_gameweek: 19
  wc2_start_gameweek: 20
  target_windows:
    wc1_window_start: 6
    wc1_window_end: 10
    free_hit_min_blank_players: 5   # Trigger FH if >= 5 current starters blank
```

---

## 6. Verification & Validation Plan

1. **Synthetic Historical Backtesting**:
   * Simulate seasons 2021-22, 2022-23, and 2023-24 in `backtest/simulator.py`.
   * Compare:
     * Strategy A: Naive / Early Chip Usage (e.g. playing TC/BB in GW1–GW5).
     * Strategy B: Dynamic Programming Optimal Stopping Allocation.
   * Quantify the historical point lift (typical delta: **+45 to +80 net points** across the season).

---

## 7. Summary

* **Verdict on GW4**: **All chips must remain locked.** 
* **Core Takeaway**: Chips are scarce capital assets. Maximizing their value requires saving them for calendar anomalies (Double and Blank Gameweeks).
* **Next Steps**: Kept safely in `docs/brainstorm/` for future implementation when multi-week lookahead features are scheduled.
