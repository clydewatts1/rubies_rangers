# Quantitative Strategy & Optimization Principles

This rule defines the core **mathematical, macroeconomic, and portfolio optimization principles** governing all analytical models, solvers, and simulation engines in **Rubies Rangers**.

The platform explicitly rejects human tactical heuristics and conventional "FPL folk wisdom" (e.g. fixed £4.5m defender rotations, rigid transfer hit hurdles, VORP/£m minimums, or dogmatic bench structures). Instead, it establishes formal objective functions, models generative stochastic distributions, treats Fantasy Football as a **long-running quantitative asset portfolio and competitive football prediction pool**, and grants computational solvers complete autonomy to discover emergent, mathematically optimal solutions.

---

## 1. Unconstrained Optimization & Emergent Strategy

- **Physical Invariants Only**: Hard constraints in optimization models (MILP via `scipy.optimize.milp` or custom solvers) are strictly limited to the official rules of Fantasy Premier League:
  1. Total squad cost $\le \text{Budget}$ (£100.0m + accumulated team value).
  2. Roster quotas: exactly 2 GKP, 5 DEF, 5 MID, 3 FWD.
  3. Club limit: $\le 3$ players per Premier League club.
  4. Formation legality: $\ge 3$ DEF, $\ge 2$ MID, $\ge 1$ FWD, exactly 1 GKP.
  5. Transaction mechanics: Free transfer accumulation rules (1 to 5 FTs) and exact point deductions ($-4$ per excess transfer).
- **Zero Tactical Dogma**: Solvers must never be constrained by human rules of thumb. If an un-intuitive squad structure (e.g. three ultra-premiums with zero-playing fodder, or doubling up on away defenders) yields higher risk-adjusted return or win probability across the simulated horizon, the solver must be unhindered to select it. Tactical strategy must be an *emergent output* of computation, not an input constraint.

---

## 2. Stochastic Modeling & Joint Probability Distributions

- **Full Distributional Simulation**: Player returns must never be treated as scalar deterministic values. The platform evaluates decisions across full probability distributions generated through stochastic Monte Carlo simulation (`montecarlo_engine.py`).
- **Generative Process Modeling**: Model outcomes through underlying stochastic components (Poisson $\lambda_{\text{goals}}$ and $\lambda_{\text{assists}}$, starting probability distributions, minutes variance, opponent defensive concession rates, venue multipliers, and disciplinary risk) rather than regressing directly onto noisy historical points.
- **Joint Correlation & Portfolio Variance**: Player returns are not independent. Monte Carlo simulations must account for intra-match covariance (e.g. clean sheet correlation across defenders of the same club, negative covariance between attacking assets and opposing goalkeepers, and team goal-scoring covariance via macro match-state jitter).
- **Multi-Dimensional Risk Profiles**: Decisions are evaluated not merely on the mean expectation $\mathbb{E}[S]$, but on the entire profile:
  - Downside preservation ($P_{10}$, Conditional Value at Risk / Expected Shortfall).
  - Median expectation ($P_{50}$) and expected value ($\mathbb{E}[S]$).
  - Explosive upside ceiling ($P_{90}$, $P_{95}$).

---

## 3. Dynamic Programming & Multi-Period Utility

- **Rolling Lookahead Horizon ($H \in [5, 8]$ Gameweeks)**: Transfer choices and point-hit decisions are formulated as discrete-time multi-period stochastic decision problems:
  $$V_t(S_t, \text{FT}_t, \text{Bank}_t) = \max_{\mathbf{u}_t \in \mathcal{U}(S_t)} \Big\{ \mathbb{E}[R_t(S_t, \mathbf{u}_t)] - \text{Cost}(\mathbf{u}_t) + \gamma \cdot \mathbb{E}\left[ V_{t+1}(S_{t+1}, \text{FT}_{t+1}, \text{Bank}_{t+1}) \mid S_t, \mathbf{u}_t \right] \Big\}$$
- **Hit Amortization NPV**: Rejects arbitrary hit hurdles (e.g. "hits must recover 4 points in 1 week"). A transfer hit is justified if and only if the multi-period net present value (NPV) across the full fixture run of the incoming asset exceeds the decay of the outgoing asset plus the $-4$ deduction and lost option flexibility.
- **Irreversible Commitments & Branching Trees**: Models must evaluate the full branching decision tree of subsequent moves rather than greedy 1-gameweek swaps.

---

## 4. Balance Sheet & Option Value Engineering

A competitive squad maintains a dynamic **multi-asset balance sheet**:

1. **The Team Value (TV) J-Curve**:
   - *Early Season (GW 1–12 - Capital Accumulation)*: Prioritizes building squad value (+£2.0m to +£4.0m) through early price rise anticipation. Reaching £104.0m+ early expands the future Pareto frontier, allowing the squad to field an additional premium asset during the second half of the season without structural compromise.
   - *Late Season (GW 25–38 - Capital Monetization)*: Full monetization into raw point expectancy; team value preservation drops to zero priority.
2. **Free Transfers (FTs) as American Call Options**:
   - Under the 5-FT accumulation rules, an unspent Free Transfer is an **option contract on future market information**.
   - Holding 3 to 5 FTs provides a rolling "Mini-Wildcard" with zero hit penalty, enabling multi-player structural pivots that single-transfer managers cannot execute.
   - Spending an FT on a marginal $+0.5\text{ xP}$ upgrade is rejected if the **option continuation value** of banking the FT provides greater structural agility for an upcoming fixture swing.
3. **Cash-in-Bank (CIB) Liquidity Buffers**:
   - Unspent capital (£0.5m to £1.5m) is treated as **liquidity insurance** that prevents two-step transaction bottlenecks and absorbs price rise slippage.

---

## 5. Asset Class Allocation & Macro Fixture Regime Waves

The player universe is segmented into four distinct **financial asset classes**:

| Asset Class | Target Allocation | Holding Horizon | Selection Objective | Risk / Return Profile |
| :--- | :---: | :---: | :--- | :--- |
| **Core Blue Chips** | 2–3 Players (£25m–£35m) | Long (10–25+ GWs) | Baseline captaincy, elite underlying xGI, fixture-resilient | Low beta, high baseline expectation, high EO |
| **Cyclical Swing Trades** | 4–6 Players (£25m–£35m) | Medium (4–7 GWs) | 4–6 game green fixture run (FDR $\le 2.4$), high attacking involvement | High alpha, high momentum, mean-reverting |
| **Paired Rotations** | 2–4 Players (£9m–£18m) | Season-Long Pairs | Home/Away fixture alternation between low-cost defenders/GKPs | Synthetic premium defense at budget cost |
| **Cash Equivalents / Fodder** | 3–4 Players (£16m–£18m) | Permanent / Bench | Minimum cost (£4.0m DEF, £4.5m MID) with guaranteed 90-min appearance | Liquidity enablers, zero capital drag |

- **Macro Swing Trading Cycle**: Positions are entered **1 gameweek before a favorable 5-fixture green wave begins** (buying low before crowd hype) and liquidated **1 gameweek before the wave ends** (selling high to late adopters before red fixture cliffs).
- **Counter-Cyclical Mean-Reversion Alpha**: The broader FPL market is pro-cyclical (buying high after a 15-point haul). The engine systematically targets **underlying xGI underperformers** before positive mean reversion occurs during easy fixture runs.

---

## 6. Real Options Pricing & Optimal Stopping for Strategic Chips

Strategic chips (Wildcard 1, Wildcard 2, Free Hit, Bench Boost, Triple Captain) are **American Options** with discrete execution opportunities $t \in [1, 38]$:

$$\text{Exercise Chip } C \text{ at GW } t \iff \text{Immediate Lift}(t, C) \ge \max_{s \in (t, T_{\text{expiry}}]} \mathbb{E}\left[ \gamma^{s-t} \cdot \text{Future Lift}(s, C) \right] + \text{Uncertainty Buffer}$$

- **Macro Calendar Synchronization**: Chips are preserved for high-leverage macro calendar events (Massive Double Gameweek 37, Massive Blank Gameweek 29, or major multi-club fixture swings).
- **Bench Boost Stacking**: Bench Boost is deployed exclusively post-Wildcard 2, ensuring all 15 players have active Double Gameweek fixtures.

---

## 7. Adversarial Game Theory & Tournament Pool Postures

In competitive mini-leagues (e.g. Bronze, Silver & Gold League) or overall rank targets, maximizing raw expected points is sub-optimal. The objective is **maximizing the probability of achieving the target outcome**:

$$\max_{\mathbf{u}} P(S_{\text{you}}(\mathbf{u}) > S_{\text{rival}})$$

1. **Lead Protection Mode ($\Delta > +30$ pts)**:
   - *Objective*: Minimize portfolio tracking error variance $\min \text{Var}(S_{\text{you}} - S_{\text{rival}})$.
   - *Action*: Align portfolio Beta with closest rivals by matching high Effective Ownership (EO) assets and mirroring captaincy on consensus premiums.
2. **Deficit Chasing Mode ($\Delta < -40$ pts)**:
   - *Objective*: Maximize probability of overtaking $P(S_{\text{you}} > S_{\text{rival}})$.
   - *Action*: Deploy **orthogonal alpha** (assets with low rival ownership, high $P_{90}$ explosive upside, and differential captaincy). Copying the leader's squad is mathematically prohibited when chasing.

---

## 8. Staged Portfolio Turnaround & Anti-Panic Policy

- **Zero Emotional / Tactical Bias**: Player selection is completely agnostic to player celebrity, club sentiment, or media narrative ("it's all about the maths").
- **Staged Multi-Period Migration**: When a team is in a sub-optimal starting state or deficit, the platform strictly prohibits emotional $-8 / -12$ hit cascades. Instead, it executes a **Staged Migration Path**:
  $$S_0 \xrightarrow{\mathbf{u}_0} S_1 \xrightarrow{\mathbf{u}_1} S_2 \dots \xrightarrow{\mathbf{u}_H} S_H$$
  Systematically repairing weak links across 3 to 6 gameweeks using optimal Free Transfer banking, preserving the Wildcard for high-leverage Double Gameweek macro-states.

---

## 9. Bench Quality as Portfolio Insurance

- **Anti-Fragile Bench Allocation**: With 5 substitutions allowed in modern Premier League matches and congested European schedules (Champions League rotation risk), the bench is evaluated as an **Insurance Option Policy**:
  - The capital cost of an active £4.5m regular starter over a £4.0m ghost is weighed directly against the expected points recovered via automatic substitutions when an elite starter is unexpectedly rested.

---

## 10. First-Principles Alpha vs. Folk Wisdom

- **Exploiting Community Inefficiencies**: Conventional "best practices" reflect the collective behavior of human managers. Excess return (alpha) is discovered precisely where conventional common practices are mathematically sub-optimal.
- **Ablation & Empirical Validation**: Every model feature (e.g. venue impact, fixture dampening, form weights, price momentum) must be validated via out-of-sample backtesting (`backtest/`) and Bayesian hyperparameter optimization (`tuner/`). Features that do not empirically improve simulated risk-adjusted performance are rejected.
- **Strict Point-in-Time Anti-Leakage**: All feature training and historical evaluations must strictly consume data available prior to Gameweek deadline, preventing forward-looking leakage.

---

## 11. Baseline Priors vs. Post-Optimization Execution

- **Cold-Start Baseline (Pre-Optimization)**: Prior to running Monte Carlo simulations or Bayesian parameter tuning (or upon initial system boot), the engine utilizes a sensible baseline heuristic configuration (e.g., `active_profile: heuristic` in `config.yaml`). This serves strictly as a stable initial prior and warm start.
- **All Heuristic Parameters Must Be Trainable**: Every newly introduced parameter (venue multipliers, green wave thresholds, discount factors, price momentum weights, FT continuation multipliers) **must default to a heuristic prior under `heuristic:` in `config.yaml`, while being fully exposed as an Optuna search space for automated Bayesian tuning (`tuner/`)**.
- **Empirical Execution (Post-Optimization)**: Once Monte Carlo simulation, out-of-sample backtesting, or automated tuning (`tuner/`) has completed, the system **must strictly transition to the trained, empirical settings** (e.g., `active_profile: tuned`).
- **Prohibition of Post-Optimization Heuristic Overrides**: Heuristic rules of thumb must be avoided. Once optimization has completed, human heuristics or community rules must never override, post-filter, or constrain the actual data-driven settings and decisions discovered by the models. Heuristics are purely bootstrap scaffolds; empirical optimization governs production decisions.
