# Brainstorm: Autonomous Execution Pipeline & Robotic Manager
## Lightweight Coloured Petri Net (CPN) Model, Programmatic FPL API Actions, and K3 Transition Guards

**Status**: PROPOSED / BRAINSTORM (Deferred for Future Implementation)  
**Target Subsystems**: `fpl_client.py`, `montecarlo_engine.py`, `fpl_optimizer.py`, `config.yaml`  
**Philosophy**: Hands-on learning and manual interactive experimentation come first; autonomous automation is approached as a formal, lightweight CPN model when ready.

---

## Executive Summary

While full end-to-end automation is technically feasible, premature automation bypasses the most valuable phase of system development: **interactive learning, intuition building, and hands-on discovery**. 

By manually operating the Streamlit dashboard (`app.py`), observing how Monte Carlo distributions behave in real matches, and watching how injury doubts (like Pedro Porro's 75% flag) play out, the engineer develops deep domain insight and discovers high-alpha modeling ideas.

When the time comes to automate, the pipeline will be implemented as a **Lightweight Coloured Petri Net (CPN) Model** with **Kleene 3-Valued ($K_3$) Transition Guards**. This formal discrete-event approach ensures that all state transitions (data ingestion, stochastic simulation, transfer validation, and lineup dispatch) are mathematically deterministic, maintain token invariants, and handle incomplete/uncertain information without crashing or executing hazardous moves.

---

## 1. The Learning-First vs. Automation Lifecycle

```text
Phase 1: Interactive Learning & Exploration (CURRENT PHASE)
  • Hands-on usage of Streamlit UI (app.py)
  • Manual transfer experimentation and scenario testing
  • Observing live matches vs. Monte Carlo probability distributions
  • Generating new modeling hypotheses (e.g. Venue impact, Macro match jitter)
           │
           ▼
Phase 2: Assisted Copilot (INTERMEDIATE PHASE)
  • System solves optimal XI and transfers at T-2 hours before deadline
  • Sends a Telegram / Discord summary with full reasoning
  • User reviews and clicks "Approve" (Human-in-the-Loop)
           │
           ▼
Phase 3: Autonomous Robotic Manager via Lightweight CPN (PRODUCTION HORIZON)
  • Lightweight pure-Python CPN model orchestrates tokens and transitions
  • Formal K3 transition guards prevent unintended actions
  • Zero manual overhead required
```

---

## 2. The Lightweight Coloured Petri Net (CPN) Architecture

Rather than relying on brittle procedural shell scripts, the autonomous pipeline is formulated as a formal **Coloured Petri Net $\mathcal{N} = (P, T, A, \Sigma, C, G, E, I)$**:

### A. Color Sets (Typed Structured Tokens)
* **`Color_Deadline`**: `tuple(gameweek: int, deadline_utc: datetime)`
* **`Color_SquadState`**: `tuple(squad_ids: list[int], bank: float, free_transfers: int)`
* **`Color_MarketData`**: `tuple(elements: DataFrame, fixtures: dict, odds: dict)`
* **`Color_OptimizedPlan`**: `tuple(starters: list[int], bench: list[int], captain: int, vice_captain: int, transfers: list[dict], chip: str | None)`
* **`Color_Receipt`**: `tuple(http_status: int, timestamp: datetime, confirmation_id: str)`

### B. Places (Typed State Buffers)
* **$P_{\text{Timer}}$**: Holds the deadline trigger token (fires at $T-120\text{m}$).
* **$P_{\text{Squad}}$**: Holds the current squad marking.
* **$P_{\text{Market}}$**: Holds live FPL API and Understat telemetry.
* **$P_{\text{Plan}}$**: Holds the solved lineup and transfer decision from MILP/Monte Carlo.
* **$P_{\text{Contingency}}$**: Buffer holding indeterminate tokens ($\mathbf{U}$) awaiting $T-60\text{m}$ official team sheets.
* **$P_{\text{Committed}}$**: Terminal sink place holding verified API transaction receipts.

### C. Transitions & CPN Flow Topology

```text
  (P_Timer)             (P_Squad)
      │                     │
      ▼                     │
[ T_IngestMarketData ]      │
      │                     │
      ▼                     │
  (P_Market)                │
      │                     │
      └──────────┬──────────┘
                 │
                 ▼
     [ T_SimulateAndSolve ]  (Monte Carlo + MILP Solver)
                 │
                 ▼
             (P_Plan)
                 │
                 ▼
         [ T_EvaluateGuards ] ──(If any Guard == F)──> [ T_AbortAndAlert ]
                 │
      ┌──────────┴──────────┐
      ▼ (If all Guards == T)▼ (If Guard == U)
[ T_DispatchFplApi ]     (P_Contingency)
      │                     │
      ▼                     ▼ (At T-60m Official Lineup Release)
 (P_Committed)         [ T_ResolveContingency ]
                            │
                            ▼
                       [ T_DispatchFplApi ]
```

### D. CPN Transition Firing Sequence
1. **$T_{\text{IngestMarketData}}$**: Fires at $T-120\text{m}$. Pulls live FPL bootstrap-static, confirmed injury flags, Understat shot quality, and sharp bookmaker odds. Deposits a typed `Color_MarketData` token into $P_{\text{Market}}$.
2. **$T_{\text{SimulateAndSolve}}$**: Consumes tokens from $P_{\text{Squad}}$ and $P_{\text{Market}}$. Executes 5,000 Monte Carlo simulations with calibrated 'tuned' parameters and solves the MILP optimal starting XI, bench hierarchy, captain, and transfers. Deposits a `Color_OptimizedPlan` token into $P_{\text{Plan}}$.
3. **$T_{\text{EvaluateGuards}}$**: Evaluates all formal predicates under Kleene 3-valued logic ($K_3$):
   * If $\mathbf{T}$: Passes token directly to $T_{\text{DispatchFplApi}}$.
   * If $\mathbf{F}$: Fires $T_{\text{AbortAndAlert}}$, immediately halting execution and notifying the user.
   * If $\mathbf{U}$: Deposits token into $P_{\text{Contingency}}$ to await resolution.
4. **$T_{\text{ResolveContingency}}$**: At $T-60\text{m}$ (when official Premier League team sheets are published), consumes the contingency token, resolves the indeterminate proposition, updates the lineup/bench order accordingly, and enables $T_{\text{DispatchFplApi}}$.
5. **$T_{\text{DispatchFplApi}}$**: Executes authenticated HTTP POST transactions to the official FPL API, depositing the terminal confirmation token into $P_{\text{Committed}}$.

---

## 3. Technical Mechanics: Programmatic FPL API Actions

The official Fantasy Premier League web application is powered by standard REST endpoints that accept authenticated JSON payloads.

### A. Authentication & Session Handling
* **Endpoint**: `POST https://users.premierleague.com/accounts/login/`
* **Payload**:
  ```json
  {
    "login": "user@example.com",
    "password": "SecurePassword123",
    "app": "plfpl-web",
    "redirect_uri": "https://fantasy.premierleague.com/"
  }
  ```
* **Cookie Management**: The server issues a session token (`pl_profile`). All subsequent requests include this cookie along with standard browser headers (`User-Agent`, `Referer`).

### B. Setting Lineup, Captaincy & Bench Order
* **Endpoint**: `POST https://fantasy.premierleague.com/api/my-team/{entry_id}/`
* **Payload Structure**:
  ```json
  {
    "picks": [
      {"element": 499, "position": 1, "is_captain": false, "is_vice_captain": false},
      {"element": 350, "position": 2, "is_captain": true,  "is_vice_captain": false},
      ...
      {"element": 120, "position": 12, "is_captain": false, "is_vice_captain": false}
    ]
  }
  ```
  * `position`: 1 to 11 are Starting XI players; 12 to 15 are Bench (12 = GKP2, 13 = Sub 1, 14 = Sub 2, 15 = Sub 3).
  * `is_captain`: True for exactly one player.
  * `is_vice_captain`: True for exactly one player.

### C. Executing Confirmed Transfers & Activating Chips
* **Endpoint**: `POST https://fantasy.premierleague.com/api/transfers/`
* **Payload Structure**:
  ```json
  {
    "chips": null,
    "entry": 6173410,
    "event": 4,
    "transfers": [
      {"element_in": 280, "element_out": 499, "purchase_price": 55, "selling_price": 55}
    ]
  }
  ```
  *(To activate a chip, `"chips"` is set to `"wildcard"`, `"freehit"`, `"3xc"`, or `"bboost"`).*

---

## 4. Formal Transition Guards under Kleene 3-Valued Logic ($K_3$ Semantics)

In **Coloured Petri Nets (CPN)** and formal transition systems, real-world actions (such as executing a transfer or submitting a team sheet) cannot be modeled strictly with naive 2-valued Boolean logic because information is frequently **incomplete, delayed, or uncertain** prior to kickoff.

Guards are therefore evaluated under **Kleene's Strong 3-Valued Logic ($K_3$)**:
$$\mathbb{V}_{K_3} = \{\mathbf{T} \text{ (True / Verified)}, \quad \mathbf{F} \text{ (False / Violated)}, \quad \mathbf{U} \text{ (Unknown / Indeterminate)}\}$$

### $K_3$ Conjunction ($\land$) for Joint Enabling:
$$\mathbf{T} \land \mathbf{T} = \mathbf{T}, \qquad \mathbf{F} \land \text{anything} = \mathbf{F}, \qquad \mathbf{T} \land \mathbf{U} = \mathbf{U}, \qquad \mathbf{U} \land \mathbf{U} = \mathbf{U}$$

* If **any Guard evaluates to $\mathbf{F}$**: The overall transition evaluates to $\mathbf{F}$ (hard block; action aborted).
* If **all Guards evaluate to $\mathbf{T}$**: The transition is **Enabled** (safe to execute).
* If **any Guard evaluates to $\mathbf{U}$ (with no $\mathbf{F}$)**: The transition evaluates to $\mathbf{U}$ (**Suspended / Contingent**). It does not fire blindly; it triggers a contingency branch or holds execution until the $T-60\text{m}$ official team sheets resolve $\mathbf{U} \rightarrow \mathbf{T}$ or $\mathbf{U} \rightarrow \mathbf{F}$.

### Guard Specification Matrix ($K_3$ Types):

| Guard (Predicate) | Formal Condition | When $\mathbf{T}$ (True) | When $\mathbf{F}$ (False) | When $\mathbf{U}$ (Unknown / Indeterminate) |
| :--- | :--- | :--- | :--- | :--- |
| **`Guard_Budget`** | $\sum \text{Cost}_i \le \text{Bank} + \text{TeamValue}$ | Cost strictly verified under bank. | Cost exceeds available capital. | Unresolved price-change event in progress. |
| **`Guard_ClubCap`** | $\max_c (\sum \mathbf{1}(\text{Club}_i = c)) \le 3$ | Club counts $\le 3$. | $\ge 4$ players from same club. | Transfer news abroad / loan status ambiguous. |
| **`Guard_Formation`** | $\text{DEF}\ge 3 \land \text{MID}\ge 2 \land \text{FWD}\ge 1$ | Formation is strictly legal. | Formation violates FPL rules. | Player position reclassification pending. |
| **`Guard_HitCeiling`** | $\text{Hits} \le \text{MaxAllowedHits}$ | Transfer hits within budget cap. | Transfer hits exceed threshold. | Free transfer rollover count unverified. |
| **`Guard_Fitness`** | $\text{COP}(\text{Starter}) \ge \text{Threshold}$ | Player confirmed 100% fit / starting. | Player confirmed 0% / ruled out. | **Yellow flag / 50%–75% doubt** (e.g. Porro 75%). |
| **`Guard_ApiLiveness`** | $\text{HTTP\_Status} == 200 \land \text{Latency} \le 10\text{s}$ | FPL API responsive and verified. | Hard 500 error / offline. | Network timeout / pending response socket. |

### Handling $\mathbf{U}$ (Indeterminate) States in Practice:
1. **Contingency Branching**: If `Guard_Fitness` is $\mathbf{U}$ (e.g. Porro 75%), the system arms the Vice-Captain fallback and places the #1 bench defender on hot-standby.
2. **Deadline Deferral**: The transition holds its token in place until $T-60\text{ minutes}$, when Premier League lineups are officially released, resolving $\mathbf{U}$ to $\mathbf{T}$ (starts) or $\mathbf{F}$ (benched).

---

## 5. Milestone Checklist (Before Transitioning to Automation)

Before enabling programmatic execution, the following milestones should be completed manually:

- [ ] **Observe 5+ Gameweek Deadlines**: Track live matches and verify that Monte Carlo expected outcomes match empirical reality.
- [ ] **Validate Bench Substitutions**: Observe how auto-substitutions perform when doubtful starters miss out.
- [ ] **Ablation Backtesting Complete**: Validate that the Optuna-tuned parameters consistently outperform heuristic baselines on out-of-sample data.
- [ ] **Venue & Jitter Modules Integrated**: Incorporate home/away dampening and macro match jitter into the core engine.
- [ ] **Dry-Run Testing**: Run the automated script for 3 gameweeks in "Log Only / Dry Run" mode without transmitting live HTTP POST requests.

---

## 6. Summary

* **Current Focus**: **Hands-on exploration and learning.** Use the interactive Streamlit app to test hypotheses, understand parameter sensitivities, and develop modeling intuition.
* **Future Role**: This specification will serve as the architectural guide when the time comes to build the automated deadline runner.
