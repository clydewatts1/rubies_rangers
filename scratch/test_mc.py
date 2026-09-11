import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from montecarlo_engine import MonteCarloEngine

mc = MonteCarloEngine()
print("Clean pool count:", len(mc.get_clean_player_pool()))
res = mc.evaluate_transfers(bank=3.7, num_transfers=1, free_transfers=1, n_sims=1000)
print("Evaluation success:", res["success"])
print("Baseline Mean:", res["baseline"]["mean"])
print("\n================== 2 TRANSFERS (WITH -4 HIT PENALTY) ==================")
res2 = mc.evaluate_transfers(bank=3.7, num_transfers=2, free_transfers=1, n_sims=1000)
print("Hit penalty applied:", res2["hit_penalty"], "pts")
for i, opt in enumerate(res2["top_3"]):
    arch = opt["archetype"]
    out_p = opt["out_player"]
    in_p = opt["in_player"]
    gain = opt["net_mean_gain"]
    win = opt["win_prob"]
    p10 = opt["floor_p10"]
    p90 = opt["ceiling_p90"]
    print(f"Top {i+1}: {arch} -> OUT {out_p} IN {in_p} (Net Gain: +{gain} pts, Win: {win}%, Floor P10: {p10}, Ceiling P90: {p90})")

