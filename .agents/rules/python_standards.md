# Python Engineering & Coding Standards

This rule enforces high-performance, clean, and maintainable Python engineering standards across the **Rubies Rangers** repository.

---

## 1. Type Annotations & Data Structures
- **Type Hints**: All functions, methods, and class attributes must include explicit type annotations (`typing.Dict`, `typing.List`, `typing.Optional`, `typing.Tuple`, `typing.Any`, `typing.Callable`).
- **Structured Records**: Use `@dataclass` (with `frozen=True` or slots where appropriate) or typed dictionaries for passing complex structures between modules (e.g. `GameweekRecord`, `SeasonResult`).
- **Modern Syntax**: Prefer modern union syntax (`Optional[T]` or `T | None`) consistently.

---

## 2. Vectorization & High Performance (No Slow Row Iteration)
- **Vectorized Operations**: All calculations over player and fixture datasets must use vectorized `pandas` and `numpy` operations (`np.where`, `.isin()`, `.map()`, `.clip()`).
- **Avoid Row Iteration**: Never use `.iterrows()` or `.itertuples()` in performance-sensitive code (e.g. data loader pipelines, walk-forward simulations, or Monte Carlo loops).
- **In-Memory Efficiency**: Filter dataframes early using boolean masks to minimize memory footprints during multi-season processing.

---

## 3. Separation of Concerns, Modularity & Anti-Pattern Avoidance
All agents must strictly adhere to the principles of **Separation of Concerns (SoC)**, **Single Responsibility (SRP)**, and **High Cohesion, Loose Coupling**:

- **Strict Layered Architecture**:
  - **Presentation Layer (`ui/`, Streamlit views)**: Exclusively handles rendering HTML/CSS, user input widgets, and Plotly visualization charts. Strictly prohibited from executing combinatorial solvers, Monte Carlo loops, or raw HTTP fetches.
  - **Orchestration Layer (`analytics/two_stage_optimizer.py`)**: Coordinates execution pipelines between multiple analytical subsystems via clean `@dataclass` contracts.
  - **Analytical & Mathematical Engines (`analytics/`)**: Pure computational routines (MILP solvers, Poisson distributions, Monte Carlo ensemble trees). Must remain 100% headless, CLI-executable, and completely decoupled from Streamlit or UI dependencies.
  - **Data Ingestion & Clients (`clients/`, `trackers/`)**: Interfaces with external APIs (FPL REST API, Understat, FBref) and local disk caches.

- **Explicit Anti-Patterns Prohibited in this Repository**:
  1. **The God Object / Monolith Anti-Pattern**: Dumping presentation, session state, math algorithms, and data parsing into a single monolithic script (e.g. legacy `app.py`). New features must be broken into cohesive modules.
  2. **Leaky Abstractions**: Never allow presentation layers to manipulate raw solver matrix rows or unvalidated API payloads. All data crossing layer boundaries must use typed `@dataclass` structures.
  3. **Circular Dependencies**: Subsystems must not circularly import each other. Coupling between two engines (e.g. MILP and Monte Carlo) must be resolved via an intermediary orchestrator or shared interface contract.
  4. **Flat-Namespace Clutter ("The Junk Drawer")**: Specialized trackers, analyzers, or helper scripts must be organized into logical domain packages (`trackers/`, `analytics/`, `clients/`) rather than dumped into the repository root.
  5. **Hidden / Mutating Global State**: Avoid unencapsulated module-level globals. Use dependency injection, parameter passing, or explicit configuration wrappers (`config_manager.py`).
  6. **Premature Big-Bang Refactoring**: Never move or rename files on disk while long-running background tasks (e.g. overnight hyperparameter tuners) are in flight. Use phased, contract-first strangler patterns to preserve system stability.

---

## 4. Defensive Configuration Access & Error Handling
- **Graceful Config Fallbacks**: When reading nested parameters from `config.yaml` or `get_params()`, always use `.get(key, default)` with safe defaults so missing or unmigrated keys do not cause runtime crashes.
- **No Bare Excepts**: Never catch bare exceptions (`except:`). Catch specific exceptions or log unexpected failures with full diagnostic context using `logger.exception()` or `logger.warning()`.
- **Structured Logging**: Use `logger = logging.getLogger(__name__)` across all engine files instead of arbitrary `print()` statements in production code.

---

## 5. Code Style & PEP 8 Standards
- **Naming Conventions**:
  - Functions & Variables: `snake_case` (e.g., `calculate_venue_multiplier`, `expected_goals_per_90`).
  - Classes: `PascalCase` (e.g., `WalkForwardSimulator`, `HyperparameterTuner`).
  - Global Constants & Enums: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_SQUAD`, `DEFAULT_DB_PATH`).
- **Formatting**: Adhere to PEP 8 standards with 4-space indentation and clean import grouping (standard library $\rightarrow$ third-party $\rightarrow$ local project imports).

---

## 6. Documentation & Comment Integrity
- **Mathematical Formulations**: Functions implementing analytical equations (e.g., Poisson implied goals, Sharpe ratio, venue multipliers) must include docstrings documenting the mathematical formulas and parameter definitions.
- **Preserve Comments**: Preserve existing explanatory comments, docstrings, and historical issue annotations (`ISSUE-X fix`, `BUG-Y fix`) unless explicitly refactoring that specific block.

---

## 7. Determinism & Stochastic Reproducibility
- **Reproducible Seeds**: Any stochastic simulation or randomized sampling (e.g. Optuna TPE sampler, Monte Carlo binomial/normal draws) must accept a configurable `seed` parameter (defaulting to a stable integer, e.g. `42`) to enable deterministic testing and debugging.
