"""
Backward-compatibility shim for analytics.optimizer.
Canonical implementation now lives in `analytics.optimizer`.
"""

from analytics.optimizer import FPLOptimizer

__all__ = ["FPLOptimizer"]

if __name__ == "__main__":
    from clients.fpl_client import FPLClient
    client = FPLClient()
    df = client.get_players_df()
    opt = FPLOptimizer(df)
    res = opt.optimize_squad(budget=100.0, objective="moneyball")
    print(f"Optimal Squad Cost: £{res['total_cost']:.1f}m | Score: {res['objective_score']:.2f}")
