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
   - **Operational Trading Desks**: Partitions workflows into 4 unified trading desks (Portfolio, Solvers, Autonomous Operations CPN, Alpha Signals).
   - **Canonical 4-Zone Page Anatomy**: Strict structure across all views (Terminal Header -> KPI Telemetry Strip -> In-Page Strategy Deck -> Dual-Aspect Data Inspector).
   - **Componentized Presentation**: Eliminates inline HTML sprawl via atomic primitives in `ui/components/`; prohibits sidebar widget bleed.

4. **Engineering Lifecycle & Agentic Skills (`.agents/skills/`)**:
   - **6-Stage Provenance DAG**: Rigorous document lifecycle connecting `docs/issues/` $\rightarrow$ `docs/brainstorm/` $\rightarrow$ `docs/design/` $\rightarrow$ `docs/plans/` $\rightarrow$ `docs/tasks/` $\rightarrow$ `docs/playbooks/`.
   - **3 Execution Tracks**:
     - *Track A (Deep Architecture - 6 Stages)*: Issue $\rightarrow$ Brainstorm $\rightarrow$ Design $\rightarrow$ Plan $\rightarrow$ Tasks $\rightarrow$ Implementation $\rightarrow$ Playbook.
     - *Track B (Fast-Track Feature - 4 Stages)*: Issue $\rightarrow$ Design $\rightarrow$ Tasks $\rightarrow$ Implementation $\rightarrow$ Playbook.
     - *Track C (Express Hotfix - 2 Stages)*: Issue $\rightarrow$ Implementation $\rightarrow$ Pytest Verification.
   - **Agentic Resource Discovery (ARD)**: Sub-millisecond zero-crawl indexing across federated manifests (`ard.yaml`, `ard.json`, `scripts/ard_search.py`, `scripts/ard_builder.py`).
   - **Code-as-Knowledge (OKF)**: YAML frontmatter embedded in module docstrings (`"""\n---\n...\n---\n"""`) and audited via `python .agents/skills/code-frontmatter-generator/scripts/validate_code_okf.py`.

---

## Architectural Hierarchy

```text
rubies_rangers/
├── AGENTS.md                                # Root Project Guidelines (This File)
├── ard.yaml                                 # Agentic Resource Discovery (ARD) Registry Config
├── config.yaml                              # Central Parameter & Hyperparameter Store
├── README.md                                # Comprehensive Platform & Subsystem Guide
├── docs/                                    # 6-Stage Engineering Knowledge Base
│   ├── issues/                              # Stage 1: iss_<ID>_<slug>.md
│   ├── brainstorm/                          # Stage 2: brn_<ID>_<slug>.md
│   ├── design/                              # Stage 3: des_<ID>_<slug>.md
│   ├── plans/                               # Stage 4: pln_<ID>_<slug>.md
│   ├── tasks/                               # Stage 5: tsk_<ID>_<slug>.md
│   ├── playbooks/                           # Stage 6: plb_<ID>_<slug>.md
│   └── tools/                               # Tooling & ARD Reference
├── scripts/                                 # ARD Builder & Search CLI
│   ├── ard_builder.py                       # Manifest generator & indexer
│   └── ard_search.py                        # Zero-crawl keyword/tag search
└── .agents/
    ├── rules/                               # Behavioral Standards & Principles
    │   ├── moneyball_strategy.md            # FPL Team Selection & Analytical Rules
    │   ├── python_standards.md              # Python & Vectorization Coding Standards
    │   └── ui_ux_standards.md               # UI/UX Quant Trading Desk Dashboard Standards
    └── skills/                              # Modular Agentic Skills
        ├── issue-ingestion-parser/          # Stage 1: Issue generator
        ├── brainstorm-facilitator/          # Stage 2: Single-shot brainstorm
        ├── brainstorm-ideate-loop/          # Stage 2: Socratic sparring
        ├── design-facilitator/              # Stage 3: Detailed technical design
        ├── spec-to-plan/                    # Stage 4: Implementation plan compiler
        ├── plan-to-task/                    # Stage 5: Micro-task harness compiler
        ├── design-to-task/                  # Composite: spec-to-plan + plan-to-task
        ├── playbook-facilitator/            # Stage 6: Operational reality playbook
        ├── doc-frontmatter-generator/       # Markdown OKF frontmatter validator
        ├── code-frontmatter-generator/      # Python docstring OKF validator
        ├── review-audit-architecture/       # Domain layering auditor
        ├── review-audit-vectorization/      # NumPy/pandas vectorization auditor
        ├── test-design/                     # Test strategy & boundary matrices
        └── test-generation-python/          # Pytest & hypothesis generator
```
