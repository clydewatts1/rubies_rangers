---
name: test-generation-python
description: Generates high-performance pytest test suites, hypothesis property-based tests, synthetic DataFrame fixtures, and async CPN pipeline tests for Rubies Rangers.
---

# test-generation-python

## Purpose
This skill generates complete, executable Python test suites adhering to the repository's testing conventions. It translates a Stage 3 Design or `test-design` matrix into robust `tests/test_*.py` files.

## Supported Test Patterns

### 1. Standard Pytest Unit Tests
```python
import pytest
import pandas as pd
from analytics.optimizer import FPLOptimizer

def test_optimizer_budget_constraint(sample_players_df: pd.DataFrame):
    opt = FPLOptimizer(sample_players_df, budget=100.0)
    squad = opt.solve()
    assert len(squad) == 15
    assert sum(p.now_cost for p in squad) <= 100.0
```

### 2. Async CPN Pipeline & Saga Tests
```python
import pytest
import asyncio
from automation.challenge_cpn.engine import ChallengeCPNEngine

@pytest.mark.asyncio
async def test_challenge_cpn_pipeline_dry_run():
    engine = ChallengeCPNEngine(dry_run=True)
    receipt = await engine.run_pipeline(...)
    assert receipt["success"] is True
    assert receipt["verified"] is True
```

### 3. Hypothesis Property-Based Invariant Tests
```python
from hypothesis import given, strategies as st
import numpy as np

@given(st.lists(st.floats(min_value=0.0, max_value=20.0), min_size=10, max_size=100))
def test_tail_risk_monotonicity(points_draws):
    arr = np.array(points_draws)
    p10 = np.percentile(arr, 10)
    p50 = np.percentile(arr, 50)
    p90 = np.percentile(arr, 90)
    assert p10 <= p50 <= p90
```

## Rules for Test Generation
- Always use descriptive test function names: `test_<component>_<scenario>_<expected_outcome>`.
- Use synthetic in-memory fixtures (do NOT make real network calls to official FPL servers during tests).
- Isolate random state using deterministic seeds: `np.random.seed(42)`.
- Assert strict binary conditions with clear error messages.
