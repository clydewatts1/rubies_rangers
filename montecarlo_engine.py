"""
Backward-compatibility shim for analytics.montecarlo.
Canonical implementation now lives in `analytics.montecarlo`.
"""

from analytics.montecarlo import MonteCarloEngine, clean_nans

__all__ = ["MonteCarloEngine", "clean_nans"]

if __name__ == "__main__":
    mc = MonteCarloEngine()
    print("Testing Monte Carlo Engine...")
    res = mc.optimize_lineup_and_substitutions(n_sims=500)
    print(f"Optimal Formation: {res['optimal_formation']}")
