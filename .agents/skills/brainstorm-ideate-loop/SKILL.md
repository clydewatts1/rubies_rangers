---
name: brainstorm-ideate-loop
description: An interactive, Socratic brainstorming skill that spars with the user on an early-stage Issue. Analyzes mathematical, quantitative, and architectural options across vectorization, Moneyball strategy, separation of concerns, and agentic code generation friendliness, cycling through wildcards, safe bets, and probing questions until consolidation.
---

# brainstorm-ideate-loop

## Purpose
This skill sits between Stage 1 (Issue) and Stage 2 (Brainstorm) of the development lifecycle. Instead of immediately writing a brainstorm document, it engages the user in a rigorous, adversarial feedback loop. It forces lateral thinking, identifies mathematical constraints, and thoroughly analyzes architectural options before consolidating into a formal Brainstorm document (`docs/brainstorm/brn_<ID>_<slug>.md`).

## When to Activate
- When the user explicitly calls `/brainstorm-ideate-loop` or `/ideate`.
- When an Issue involves complex mathematics, novel optimization heuristics, or multi-component CPN workflows needing significant exploration before an architectural spec is authored.

## Routing Guidance
- **`brainstorm-ideate-loop`** (this skill): Interactive multi-turn sparring.
- **`brainstorm-facilitator`**: Single-shot generation when 2-3 options and trade-offs are already clear.

## Operational Constraints (CRITICAL)
- **Do NOT write a file immediately**: This skill is interactive. Do not write `brn_*.md` until the user says "Consolidate", "Write it down", or gives a definitive command to finalize.
- **Strict Option Analysis**: Every option evaluated during sparring must undergo the mandatory 4-pillar analysis.
- **Single Pivot Question**: Never overwhelm the user with multiple open questions in one turn. Focus on exactly *one* decisive constraint or mathematical trade-off per round.

## Execution Steps

### Phase 1: Setup & Scope Gate
1. Read the source Issue document using `view_file`.
2. **Scope Gate**: Evaluate whether the issue genuinely requires multi-turn exploration. If obvious, redirect to single-shot `brainstorm-facilitator`.
3. Acknowledge the core problem statement briefly and enter Phase 2.

### Phase 2: The Sparring Loop
In every turn, propose contrasting mathematical/architectural paths and evaluate them across the mandatory 4-pillar framework:

#### Mandatory 4-Pillar Option Analysis
1. **Pros & Cons**: Quantitative return benefits, computational overhead, latency, and edge-case risks.
2. **Separation of Concerns (SoC)**: Domain cleanliness conforming to `UI -> Orchestration -> Analytical Engines -> Data Clients`.
3. **Quantitative Moneyball Strategy Alignment**: Conformance to `.agents/rules/moneyball_strategy.md` (unconstrained solvers, dynamic multi-period stochastic utility, joint probability distributions, and tail metrics $P_{10}/P_{50}/P_{90}$).
4. **Vectorization & Pythonic Engineering**: Conformance to `.agents/rules/python_standards.md` (NumPy vectorization, avoiding row iteration, frozen `@dataclass` contracts, testability with `pytest`).

#### Turn Format
Every sparring turn must output:
1. **Turn Header**: `> **Sparring Round N / ~5**`
2. **Running Decision Ledger**: Decisions locked in prior rounds.
3. **2-3 Contrasting Options**: E.g., a "Safe Bet" (direct, standard) vs. a "Wildcard" (high-alpha, vectorized, stochastic).
4. **The Pivot Question**: Exactly *one* probing Socratic question forcing a decision on a core trade-off (e.g. *"Are we prioritizing 40ms interactive UI response time via MILP pre-screening, or 10,000-draw Monte Carlo fidelity at the expense of 5-second background latency?"*).

#### Turn Management
- **Round 3 - The Nudge**: Offer an off-ramp to consolidate if the user is satisfied.
- **Round 5 - Soft Cap**: Strongly recommend consolidation into `brn_<ID>_<slug>.md`.

### Phase 3: Consolidation
When the user commands consolidation:
1. Write `docs/brainstorm/brn_<ID>_<slug>.md` using the standard Brainstorm template.
2. Run `python scripts/ard_builder.py` to index the new document.
3. Prompt the user to advance to Stage 3 (Design) via `/design-facilitator`.
