# Quantitative Strategy & Optimization Principles

This rule defines the core **mathematical and optimization principles** governing all analytical models, solvers, and simulation engines in **Rubies Rangers**.

The platform explicitly rejects human tactical heuristics and conventional "FPL folk wisdom" (e.g. fixed £4.5m defender rotations, rigid transfer hit hurdles, VORP/£m minimums, or dogmatic bench structures). Instead, it establishes formal objective functions, models generative stochastic distributions, and grants computational solvers complete autonomy to discover emergent, mathematically optimal solutions.

---

## 1. Unconstrained Optimization & Emergent Strategy

- **Physical Invariants Only**: Hard constraints in optimization models (MILP via `scipy.optimize.milp` or custom solvers) are strictly limited to the official rules of Fantasy Premier League:
  1. Total squad cost $\le \text{Budget}$ (£100.0m + accumulated team value).
  2. Roster quotas: exactly 2 GKP, 5 DEF, 5 MID, 3 FWD.
  3. Club limit: $\le 3$ players per Premier League club.
  4. Formation legality: $\ge 3$ DEF, $\ge 2$ MID, $\ge 1$ FWD, exactly 1 GKP.
  5. Transaction mechanics: Free transfer accumulation rules and exact point deductions for excess transfers.
- **Zero Tactical Dogma**: Solvers must never be constrained by human rules of thumb. If an un-intuitive squad structure (e.g. three ultra-premiums with zero-playing fodder, or doubling up on away defenders) yields higher risk-adjusted return or win probability across the simulated horizon, the solver must be unhindered to select it. Tactical strategy must be an *emergent output* of computation, not an input constraint.

---

## 2. Stochastic Modeling & Joint Probability Distributions

- **Full Distributional Simulation**: Player returns must never be treated as scalar deterministic values. The platform evaluates decisions across full probability distributions generated through stochastic Monte Carlo simulation (`montecarlo_engine.py`).
- **Generative Process Modeling**: Model outcomes through underlying stochastic components (starting probabilities, minutes distributions, expected involvement per 90, opponent fragility, venue multipliers, and disciplinary risk) rather than regressing directly onto noisy historical points.
- **Joint Correlation & Portfolio Variance**: Player returns are not independent. Monte Carlo simulations must account for intra-match covariance (e.g. clean sheet correlation across defenders of the same club, negative covariance between attacking assets and opposing goalkeepers, and team goal-scoring covariance).
- **Multi-Dimensional Risk Profiles**: Decisions are evaluated not merely on the mean expectation $\mathbb{E}[S]$, but on the entire profile:
  - Downside preservation ($P_{10}$, Conditional Value at Risk / Expected Shortfall).
  - Median expectation ($P_{50}$) and expected value ($\mathbb{E}[S]$).
  - Explosive upside ceiling ($P_{90}$, $P_{95}$).

---

## 3. Dynamic Programming & Multi-Period Utility

- **Continuous Utility Formulation**: Transfer choices and point-hit decisions are evaluated as multi-period stochastic decision problems across a rolling lookahead horizon (H in [3, 6] gameweeks):
  - No fixed hit hurdles (e.g. no arbitrary "hits must recover 4 points in 3 weeks" rules).
  - A transfer or hit is justified if and only if it maximizes cumulative expected utility across the horizon net of transfer deductions, capital depreciation, and the opportunity cost of future transfer flexibility.
- **Option Value of Resources**: Models must account for the endogenous option value of having unspent bank capital and rollover Free Transfers in subsequent gameweeks.

---

## 4. Adversarial Game Theory & Target Optimization

- **Outcome-Driven Objectives**: In competitive mini-leagues (e.g. Bronze, Silver & Gold League) or overall rank targets, maximizing raw expected points is often sub-optimal. The objective is maximizing the probability of achieving the target outcome:
  `max P(Squad_points > Rival_points)` or `max P(Squad_points > Target_points)`
- **Simulating Competitor Distributions**: Mini-league strategy is determined by simulating competitor portfolios simultaneously with our own. Whether to select assets correlated with rivals (variance dampening) or uncorrelated assets (variance expansion) is computed dynamically from the current points deficit and remaining gameweeks, never determined by static heuristics.

---

## 5. First-Principles Alpha vs. Folk Wisdom

- **Exploiting Community Inefficiencies**: Conventional "best practices" reflect the collective behavior of human managers. In quantitative finance and competitive games, excess return (alpha) is discovered precisely where conventional common practices are mathematically sub-optimal.
- **Ablation & Empirical Validation**: Every model feature (e.g. venue impact, fixture dampening, form weights) must be validated via out-of-sample backtesting (`backtest/`) and Bayesian hyperparameter optimization (`tuner/`). Features that do not empirically improve simulated risk-adjusted performance are rejected, regardless of their popularity in the FPL community.
- **Strict Point-in-Time Anti-Leakage**: All feature training and historical evaluations must strictly consume data available prior to Gameweek deadline, preventing forward-looking leakage.

---

## 6. Baseline Priors vs. Post-Optimization Execution

- **Cold-Start Baseline (Pre-Optimization)**: Prior to running Monte Carlo simulations or Bayesian parameter tuning (or upon initial system boot before training data is processed), the engine utilizes a sensible baseline heuristic configuration (e.g., `active_profile: heuristic` in `config.yaml`). This serves strictly as a stable initial prior and warm start.
- **Empirical Execution (Post-Optimization)**: Once Monte Carlo simulation, out-of-sample backtesting, or automated tuning (`tuner/`) has completed, the system **must strictly transition to the trained, empirical settings** (e.g., `active_profile: tuned`).
- **Prohibition of Post-Optimization Heuristic Overrides**: Heuristic rules of thumb must be avoided. Once optimization has completed, human heuristics or community rules must never override, post-filter, or constrain the actual data-driven settings and decisions discovered by the models. Heuristics are purely bootstrap scaffolds; empirical optimization governs production decisions.
