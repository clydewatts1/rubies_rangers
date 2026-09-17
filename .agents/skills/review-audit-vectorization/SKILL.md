---
name: review-audit-vectorization
description: Audits quantitative Python code in analytics/ and backtest/ against slow pandas row iteration (.iterrows()), unvectorized for-loops, and memory churn. Enforces NumPy broadcast vectorization and array math.
---

# review-audit-vectorization

## Purpose
This skill audits quantitative modeling, simulation, and scoring code in `analytics/` and `backtest/` to guarantee maximum mathematical performance. It enforces the vectorization mandates of [`.agents/rules/python_standards.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/.agents/rules/python_standards.md).

## Critical Anti-Patterns to Flag

### 1. The Cardinal Sin: `.iterrows()`
- **Violation**: Iterating through DataFrame rows with `for index, row in df.iterrows():`.
- **Performance Impact**: 100x–1000x latency penalty due to creating a `pd.Series` object on every row.
- **Remediation**: Use vectorized NumPy operations (`df["col_a"] * df["col_b"]`), `np.where()`, or `.to_numpy()` matrix math.

### 2. Slow `.apply()` with Python Lambdas
- **Violation**: `df["new_col"] = df.apply(lambda row: complex_func(row), axis=1)`.
- **Remediation**: Rewrite `complex_func` to accept NumPy arrays or use vectorized pandas expressions.

### 3. Repeated DataFrame Appends in Loops
- **Violation**: `df = pd.concat([df, new_row])` inside a loop.
- **Remediation**: Accumulate records in a Python list of dicts, then construct the DataFrame once at the end: `pd.DataFrame(records)`.

## Audit Commands & Patterns
Search for vectorization violations across the repo:
```bash
# Grep for iterrows
python -c "import glob, re; [print(f'{f}:{i+1}:{line.strip()}') for f in glob.glob('analytics/**/*.py', recursive=True) for i, line in enumerate(open(f, encoding='utf-8')) if '.iterrows()' in line]"
```
