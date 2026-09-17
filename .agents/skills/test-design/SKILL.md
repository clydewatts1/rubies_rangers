---
name: test-design
description: Architects comprehensive test plans, invariant matrices, boundary cases, and synthetic fixtures for quantitative models, solvers, and CPN automation.
---

# test-design

## Purpose
This skill designs rigorous test strategies before code generation begins. It ensures that every mathematical model, optimization solver, and CPN workflow has an exhaustive verification matrix covering:
1. **Happy Paths**: Standard execution scenarios with clean data.
2. **Boundary & Extremal Invariants**: Empty dataframes, 0 bank balance, ties in scores, extreme weather conditions.
3. **Adversarial Scenarios**: Corrupted API responses, dropped lineups, HTTP 403/429 errors, duplicate player names.
4. **Property Invariants**: Monotonicity of quantiles ($P_{10} \le P_{50} \le P_{99}$), exact squad quotas ($\sum x_i = 15$ or $6$), budget compliance.
5. **Performance Benchmarks**: Timing guarantees under `@pytest.mark.benchmark` (e.g. MILP $< 50$ms).

## Test Matrix Template

| Test ID | Test Category | Target Component | Scenario Description | Expected Invariant |
| :--- | :--- | :--- | :--- | :--- |
| `TC-01` | Unit / Happy | `FPLOptimizer` | Optimal 15-man draft with £100m budget | 15 picks, cost $\le 100$, 0 club violations |
| `TC-02` | Boundary | `TwoStageOptimizer` | Zero bank remaining (£0.0m) | Infeasible or exact 0-bank solution |
| `TC-03` | Property | `MonteCarloEngine` | 2,500 simulation draws | $P_{10} \le P_{50} \le P_{99}$ |
| `TC-04` | Chaos / Saga | `ChallengeCPNEngine` | Drop 1st submission attempt | Attempt 2 retries and recovers with receipt |
