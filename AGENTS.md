# Project Rules & Guidelines: Rubies Rangers FPL

Welcome to **Rubies Rangers**, an advanced quantitative optimization engine and analytics platform for Fantasy Premier League (FPL).

All development and automated decision-making in this repository are governed by modular rules located in [`.agents/rules/`](.agents/rules/):

---

## Active Repository Rules

1. **[Quantitative Strategy & Optimization Principles](.agents/rules/moneyball_strategy.md)**:
   - **Unconstrained Solvers**: Imposes only physical FPL rules (budget, squad quotas, club caps, formations); rejects human tactical dogma so optimal strategies emerge naturally.
   - **Stochastic & Monte Carlo Modeling**: Propagates full joint probability distributions with covariance, minutes volatility, and downside/upside tail metrics (P10, P50, P90).
   - **Multi-Period Stochastic Utility**: Formulates transfers and hits as rolling-horizon dynamic decisions maximizing cumulative expected utility without arbitrary hit hurdle rates.
   - **Game-Theoretic Adversarial Optimization**: Maximizes mini-league win probability P(Squad > Rival) by simulating competitor portfolio distributions.
   - **First-Principles Alpha vs. Folk Wisdom**: Rejects conventional community "best practices"; mandates empirical ablation backtesting and strict point-in-time isolation.
   - **Lifecycle (Baseline Priors to Empirical Settings)**: Uses heuristic configurations strictly as initial cold-start defaults before Monte Carlo simulation or tuning; once training finishes, empirical settings take over completely and heuristic rules are avoided.

2. **[Python Engineering & Coding Standards](.agents/rules/python_standards.md)**:
   - **Separation of Concerns & Modularity**: Enforces strict domain layering (UI -> Orchestration -> Analytical Engines -> Data Clients) and single-responsibility modules.
   - **Anti-Pattern Avoidance**: Explicitly prohibits God Object monoliths, leaky abstractions, circular dependencies, flat-namespace clutter, mutating global state, and premature in-flight refactoring.
   - **Performance & Types**: Enforces strict type annotations, frozen `@dataclass` contracts, PEP 8 compliance, vectorization (`pandas`/`numpy`), and prohibits slow row iteration (`.iterrows()`).
   - **Defensive Engineering**: Requires graceful config fallbacks, structured logging, mathematical docstrings, and deterministic random seed configuration.

3. **[UI/UX & Dashboard Engineering Standards](.agents/rules/ui_ux_standards.md)**:
   - **The Quant Trading Desk**: High-contrast financial terminal dark mode (`#0b0f19`/`#111827`/`#1f2937`) with persistent Portfolio Ticker (AUM, Cash-in-Bank, FT call options).
   - **Two-Tier Hierarchical Navigation**: Partitions workflows into 5 Operational Trading Desks (Portfolio, Solvers, Challenge, Autonomous CPN, Alpha Signals) to eliminate 27-item flat selectbox clutter.
   - **Canonical 4-Zone Page Anatomy**: Strict structure across all views (Terminal Header -> KPI Telemetry Strip -> In-Page Strategy Deck -> Dual-Aspect Data Inspector).
   - **Componentized Presentation**: Eliminates inline HTML sprawl via atomic primitives in `ui/components/`; prohibits sidebar widget bleed.

---

## Architectural Hierarchy

```text
rubies_rangers/
├── AGENTS.md                                # Root Project Guidelines (This File)
├── config.yaml                              # Central Parameter & Hyperparameter Store
├── README.md                                # Comprehensive Platform & Subsystem Guide
└── .agents/
    └── rules/
        ├── moneyball_strategy.md            # FPL Team Selection & Analytical Rules
        ├── python_standards.md              # Python & Vectorization Coding Standards
        └── ui_ux_standards.md               # UI/UX Quant Trading Desk Dashboard Standards
```
