import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from montecarlo_engine import MonteCarloEngine
from xp_model import DEFAULT_SQUAD

mc = MonteCarloEngine()
fpl_df = mc.fpl_client.get_players_df()
squad_players = []
for name in DEFAULT_SQUAD:
    p = fpl_df[fpl_df["web_name"].str.lower() == name.lower()]
    if p.empty:
        p = fpl_df[fpl_df["full_name"].str.lower() == name.lower()]
    if not p.empty:
        squad_players.append(p.iloc[0].to_dict())

n_sims = 5000
sim_cache = mc.precompute_player_sims(squad_players, is_current_squad=True, n_sims=n_sims)

# Starters for 3-5-2:
gkps = [p for p in squad_players if p["position_name"] == "GKP"]
defs = [p for p in squad_players if p["position_name"] == "DEF"]
mids = [p for p in squad_players if p["position_name"] == "MID"]
fwds = [p for p in squad_players if p["position_name"] == "FWD"]

gkps.sort(key=lambda p: sim_cache[p["web_name"]]["mean_pts"], reverse=True)
defs.sort(key=lambda p: sim_cache[p["web_name"]]["mean_pts"], reverse=True)
mids.sort(key=lambda p: sim_cache[p["web_name"]]["mean_pts"], reverse=True)
fwds.sort(key=lambda p: sim_cache[p["web_name"]]["mean_pts"], reverse=True)

starters = [gkps[0]] + defs[:3] + mids[:5] + fwds[:2]
starter_names = [s["web_name"] for s in starters]
bench_outfield = [p for p in squad_players if p["web_name"] not in starter_names and p["position_name"] != "GKP"]
# Sort bench outfield by mean points:
bench_outfield.sort(key=lambda p: sim_cache[p["web_name"]]["mean_pts"], reverse=True)
bench_gkp = [p for p in gkps if p["web_name"] not in starter_names][0]

print("Starters (3-5-2):", starter_names)
print("Bench Outfield:", [b["web_name"] for b in bench_outfield])
print("Bench GKP:", bench_gkp["web_name"])

# Simulation arrays
starter_mins = np.array([sim_cache[s["web_name"]]["mins"] for s in starters]) # (11, n_sims)
starter_pts = np.array([sim_cache[s["web_name"]]["pts"] for s in starters])

b_mins = np.array([sim_cache[b["web_name"]]["mins"] for b in bench_outfield]) # (3, n_sims)
b_pts = np.array([sim_cache[b["web_name"]]["pts"] for b in bench_outfield])

gkp_sub_mins = sim_cache[bench_gkp["web_name"]]["mins"]
gkp_sub_pts = sim_cache[bench_gkp["web_name"]]["pts"]

# Bench activation tracking
sub_1_act = np.zeros(n_sims, dtype=bool)
sub_2_act = np.zeros(n_sims, dtype=bool)
sub_3_act = np.zeros(n_sims, dtype=bool)
gkp_sub_act = np.zeros(n_sims, dtype=bool)

# GKP check
gkp_sub_act = (starter_mins[0] == 0) & (gkp_sub_mins > 0)

# Outfield check
# In 3-5-2: starter_mins[1:4] are DEFs, [4:9] are MIDs, [9:11] are FWDs.
# Min formation requirements: 3 DEF, 2 MID, 1 FWD
for t in range(n_sims):
    n_def_playing = np.sum(starter_mins[1:4, t] > 0)
    n_mid_playing = np.sum(starter_mins[4:9, t] > 0)
    n_fwd_playing = np.sum(starter_mins[9:11, t] > 0)
    
    # Check each zero starter
    zero_outfield = [idx for idx in range(1, 11) if starter_mins[idx, t] == 0]
    if not zero_outfield:
        continue
    
    # Try bench in order
    used_bench = set()
    for z_idx in zero_outfield:
        pos_lost = starters[z_idx]["position_name"]
        
        for b_i, b_p in enumerate(bench_outfield):
            if b_i in used_bench or b_mins[b_i, t] == 0:
                continue
            b_pos = b_p["position_name"]
            
            # Check formation legality if b_p replaces z_idx
            cand_def = n_def_playing + (1 if b_pos == "DEF" else 0)
            cand_mid = n_mid_playing + (1 if b_pos == "MID" else 0)
            cand_fwd = n_fwd_playing + (1 if b_pos == "FWD" else 0)
            
            if cand_def >= 3 and cand_mid >= 2 and cand_fwd >= 1:
                used_bench.add(b_i)
                if b_i == 0: sub_1_act[t] = True
                elif b_i == 1: sub_2_act[t] = True
                elif b_i == 2: sub_3_act[t] = True
                
                n_def_playing = cand_def
                n_mid_playing = cand_mid
                n_fwd_playing = cand_fwd
                break

print(f"\nSub 1 ({bench_outfield[0]['web_name']}) Activation: {np.mean(sub_1_act)*100:.1f}%, Mean pts when subbed: {np.mean(b_pts[0, sub_1_act]):.2f}")
print(f"Sub 2 ({bench_outfield[1]['web_name']}) Activation: {np.mean(sub_2_act)*100:.1f}%, Mean pts when subbed: {np.mean(b_pts[1, sub_2_act]):.2f}")
print(f"Sub 3 ({bench_outfield[2]['web_name']}) Activation: {np.mean(sub_3_act)*100:.1f}%, Mean pts when subbed: {np.mean(b_pts[2, sub_3_act]):.2f}")
print(f"GKP Sub ({bench_gkp['web_name']}) Activation: {np.mean(gkp_sub_act)*100:.1f}%")

# Captaincy Duel: Isak vs João Pedro vs Foden vs Rogers
print("\n--- Captaincy Duel ---")
cands = ["Isak", "João Pedro", "Rogers", "Foden", "Cherki", "Ødegaard", "Mbeumo"]
for c in cands:
    c_pts = sim_cache[c]["pts"]
    mean_cap = np.mean(c_pts * 2)
    haul_pct = np.mean(c_pts >= 10) * 100
    blank_pct = np.mean(c_pts <= 2) * 100
    print(f"{c:12s}: Cap Mean={mean_cap:.2f} pts | Haul (>=10 pts)={haul_pct:.1f}% | Blank (<=2 pts)={blank_pct:.1f}%")

# Win rate Isak vs João Pedro
isak_pts = sim_cache["Isak"]["pts"]
jp_pts = sim_cache["João Pedro"]["pts"]
isak_win = np.mean(isak_pts > jp_pts) * 100
jp_win = np.mean(jp_pts > isak_pts) * 100
tie = np.mean(isak_pts == jp_pts) * 100
print(f"\nHead-to-Head: Isak wins {isak_win:.1f}% vs João Pedro {jp_win:.1f}% (Ties {tie:.1f}%)")
