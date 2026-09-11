"""
Walk-Forward Season Simulator for Multi-Season FPL Backtesting
Executes gameweek-by-gameweek simulation with strict anti-leakage,
MILP transfer optimization, official FPL auto-substitutions, and Sharpe scoring.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set

import numpy as np
import pandas as pd

from .data_loader import HistoricalDataLoader
from fpl_optimizer import FPLOptimizer

logger = logging.getLogger("backtest.simulator")


@dataclass
class GameweekRecord:
    gw: int
    starting_xi: List[str]
    bench: List[str]
    captain: str
    vice_captain: str
    auto_subs: List[Tuple[str, str]]  # (out_player, in_player)
    raw_points: float
    hits_taken: int
    net_points: float
    squad_value: float
    bank: float


@dataclass
class SeasonResult:
    season: str
    total_net_points: float
    mean_gw_points: float
    std_gw_points: float
    sharpe_ratio: float
    risk_adjusted_score: float
    total_transfers: int
    total_hits: int
    gameweeks: List[GameweekRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "season": self.season,
            "total_net_points": round(self.total_net_points, 1),
            "mean_gw_points": round(self.mean_gw_points, 2),
            "std_gw_points": round(self.std_gw_points, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "risk_adjusted_score": round(self.risk_adjusted_score, 2),
            "total_transfers": self.total_transfers,
            "total_hits": self.total_hits,
            "gameweeks_completed": len(self.gameweeks),
        }


class WalkForwardSimulator:
    """
    Simulates a full 38-gameweek FPL season in a walk-forward manner.
    """

    LEGAL_FORMATIONS = [
        (3, 4, 3), (3, 5, 2), (4, 4, 2), (4, 3, 3),
        (4, 5, 1), (5, 3, 2), (5, 4, 1), (5, 2, 3)
    ]

    def __init__(self, data_loader: Optional[HistoricalDataLoader] = None):
        self.data_loader = data_loader or HistoricalDataLoader()

    def _select_lineup_and_bench(
        self,
        squad_df: pd.DataFrame,
        score_col: str = "moneyball_score"
    ) -> Tuple[List[str], List[str], str, str]:
        """
        Picks optimal starting XI (11) and ordered bench (4) according to legal formation rules.
        """
        gkps = squad_df[squad_df["position_name"] == "GKP"].sort_values(by=score_col, ascending=False)
        defs = squad_df[squad_df["position_name"] == "DEF"].sort_values(by=score_col, ascending=False)
        mids = squad_df[squad_df["position_name"] == "MID"].sort_values(by=score_col, ascending=False)
        fwds = squad_df[squad_df["position_name"] == "FWD"].sort_values(by=score_col, ascending=False)

        best_score = -1e9
        best_xi: List[str] = []
        best_bench: List[str] = []

        starting_gkp = gkps.iloc[0]["web_name"] if len(gkps) > 0 else ""
        bench_gkp = gkps.iloc[1]["web_name"] if len(gkps) > 1 else ""

        # Test each legal formation
        for n_def, n_mid, n_fwd in self.LEGAL_FORMATIONS:
            if len(defs) < n_def or len(mids) < n_mid or len(fwds) < n_fwd:
                continue

            xi_defs = defs.iloc[:n_def]
            xi_mids = mids.iloc[:n_mid]
            xi_fwds = fwds.iloc[:n_fwd]

            formation_score = (
                (gkps.iloc[0][score_col] if len(gkps) > 0 else 0)
                + xi_defs[score_col].sum()
                + xi_mids[score_col].sum()
                + xi_fwds[score_col].sum()
            )

            if formation_score > best_score:
                best_score = formation_score
                best_xi = (
                    [starting_gkp]
                    + xi_defs["web_name"].tolist()
                    + xi_mids["web_name"].tolist()
                    + xi_fwds["web_name"].tolist()
                )
                # Outfield bench
                bench_defs = defs.iloc[n_def:]
                bench_mids = mids.iloc[n_mid:]
                bench_fwds = fwds.iloc[n_fwd:]
                outfield_bench = pd.concat([bench_defs, bench_mids, bench_fwds]).sort_values(by=score_col, ascending=False)
                best_bench = [bench_gkp] + outfield_bench["web_name"].tolist()

        # Captain & Vice-captain from XI
        xi_df = squad_df[squad_df["web_name"].isin(best_xi)].sort_values(by=score_col, ascending=False)
        captain = xi_df.iloc[0]["web_name"] if len(xi_df) > 0 else (best_xi[0] if best_xi else "")
        vice_captain = xi_df.iloc[1]["web_name"] if len(xi_df) > 1 else captain

        return best_xi, best_bench, captain, vice_captain

    def _evaluate_actuals(
        self,
        starting_xi: List[str],
        bench: List[str],
        captain: str,
        vice_captain: str,
        actuals_df: pd.DataFrame
    ) -> Tuple[float, List[Tuple[str, str]]]:
        """
        Scores the selected lineup against actual match ground truth, executing official FPL auto-subs.
        """
        # Aggregate in case of Double Gameweeks or multiple fixture records
        agg_actuals = actuals_df.groupby("web_name").agg({
            "total_points": "sum",
            "minutes": "sum",
            "position_name": "first"
        }).reset_index()

        actual_map = agg_actuals.set_index("web_name").to_dict(orient="index")
        pos_map = agg_actuals.set_index("web_name")["position_name"].to_dict()

        active_xi = list(starting_xi)
        auto_subs: List[Tuple[str, str]] = []

        # 1. Goalkeeper Auto-Sub
        gkp_starter = next((p for p in active_xi if pos_map.get(p) == "GKP"), None)
        bench_gkp = next((p for p in bench if pos_map.get(p) == "GKP"), None)

        if gkp_starter and bench_gkp:
            starter_mins = actual_map.get(gkp_starter, {}).get("minutes", 0)
            bench_mins = actual_map.get(bench_gkp, {}).get("minutes", 0)
            if starter_mins == 0 and bench_mins > 0:
                active_xi[active_xi.index(gkp_starter)] = bench_gkp
                auto_subs.append((gkp_starter, bench_gkp))

        # 2. Outfield Auto-Subs
        outfield_bench = [p for p in bench if pos_map.get(p) != "GKP"]
        used_bench: Set[str] = set()

        for starter in list(active_xi):
            if pos_map.get(starter) == "GKP":
                continue
            mins = actual_map.get(starter, {}).get("minutes", 0)
            if mins == 0:
                # Find first eligible bench player
                for b_player in outfield_bench:
                    if b_player in used_bench:
                        continue
                    b_mins = actual_map.get(b_player, {}).get("minutes", 0)
                    if b_mins > 0:
                        # Test if swapping creates a legal formation
                        temp_xi = [b_player if p == starter else p for p in active_xi]
                        n_d = sum(1 for p in temp_xi if pos_map.get(p) == "DEF")
                        n_m = sum(1 for p in temp_xi if pos_map.get(p) == "MID")
                        n_f = sum(1 for p in temp_xi if pos_map.get(p) == "FWD")
                        if (n_d, n_m, n_f) in self.LEGAL_FORMATIONS:
                            active_xi[active_xi.index(starter)] = b_player
                            used_bench.add(b_player)
                            auto_subs.append((starter, b_player))
                            break

        # 3. Calculate points with captain doubling
        c_mins = actual_map.get(captain, {}).get("minutes", 0)
        vc_mins = actual_map.get(vice_captain, {}).get("minutes", 0)

        effective_c = captain if c_mins > 0 else (vice_captain if vc_mins > 0 else captain)

        raw_points = 0.0
        for player in active_xi:
            pts = float(actual_map.get(player, {}).get("total_points", 0.0))
            if player == effective_c:
                raw_points += (pts * 2.0)
            else:
                raw_points += pts

        return raw_points, auto_subs

    # Season-dependent max banked free transfers
    FT_CAP_BY_SEASON = {
        "2021-22": 2,
        "2022-23": 2,
        "2023-24": 2,
        "2024-25": 5,
    }

    def run_season(
        self,
        season: str,
        params: Optional[Dict] = None,
        start_gw: int = 1,
        end_gw: int = 38
    ) -> SeasonResult:
        """
        Simulates an entire season walk-forward from start_gw to end_gw.
        """
        logger.info("Starting walk-forward backtest for season %s (GW%d to GW%d)", season, start_gw, end_gw)

        mb_params = (params or {}).get("moneyball", {})
        opt_params = (params or {}).get("optimizer", {})

        # BUG-4 fix: Season-dependent FT cap (from config rules if present, fallback to FT_CAP_BY_SEASON)
        try:
            from config_manager import get_system_config
            sys_rules = get_system_config("rules") or {}
            max_banked_map = sys_rules.get("max_banked_ft", {})
            ft_cap = int(max_banked_map.get(season, self.FT_CAP_BY_SEASON.get(season, 5)))
        except Exception:
            ft_cap = self.FT_CAP_BY_SEASON.get(season, 5)

        # Step 1: Initial GW1 squad selection
        f1, a1 = self.data_loader.get_point_in_time_snapshot(season, start_gw, moneyball_params=mb_params)
        opt1 = FPLOptimizer(f1)
        budget = float(opt_params.get("budget", 100.0))
        max_club = int(opt_params.get("max_per_club", 3))

        init_squad = opt1.optimize_squad(budget=budget)
        if not init_squad or not init_squad.get("success", False):
            # Fallback to top 2 GKP, 5 DEF, 5 MID, 3 FWD by score
            logger.warning("MILP squad solver failed for season %s GW1; using positional greedy fallback", season)
            squad_names = []
            for pos, count in [("GKP", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]:
                top_pos = f1[f1["position_name"] == pos].sort_values(by="moneyball_score", ascending=False).head(count)
                squad_names.extend(top_pos["web_name"].tolist())
            current_squad = squad_names
            squad_cost = float(f1[f1["web_name"].isin(current_squad)]["now_cost"].sum())
        else:
            squad_res = init_squad["squad"]
            if isinstance(squad_res, pd.DataFrame):
                current_squad = squad_res["web_name"].tolist()
            else:
                current_squad = list(squad_res)
            squad_cost = float(init_squad["total_cost"])

        bank = max(0.0, budget - squad_cost)
        free_transfers = 1
        total_transfers = 0
        total_hits = 0
        gw_records: List[GameweekRecord] = []

        # Step 2: Iterate gameweeks
        for gw in range(start_gw, end_gw + 1):
            features_df, actuals_df = self.data_loader.get_point_in_time_snapshot(
                season, gw, moneyball_params=mb_params
            )

            # ISSUE-6 fix: Multi-transfer support — allow up to free_transfers swaps per GW
            hits_this_gw = 0
            transfers_this_gw = 0
            if gw > start_gw:
                squad_features = features_df[features_df["web_name"].isin(current_squad)]
                doubtful = squad_features[squad_features["status"] != "a"]

                # Determine max transfers to attempt this GW
                max_transfers_this_gw = max(free_transfers, 1 if len(doubtful) > 0 else 0)

                for _t in range(max_transfers_this_gw):
                    # Refresh squad features after each transfer
                    squad_features = features_df[features_df["web_name"].isin(current_squad)]
                    if squad_features.empty:
                        break

                    # Prioritize doubtful players first, then lowest score
                    doubtful_now = squad_features[squad_features["status"] != "a"]
                    if len(doubtful_now) > 0:
                        sell_candidate = doubtful_now.sort_values(by="moneyball_score", ascending=True).iloc[0]
                    else:
                        sell_candidate = squad_features.sort_values(by="moneyball_score", ascending=True).iloc[0]

                    pos = sell_candidate["position_name"]
                    sell_price = sell_candidate["now_cost"]
                    max_buy = bank + sell_price

                    # Buy candidate in same position not already in squad
                    pool = features_df[
                        (features_df["position_name"] == pos)
                        & (~features_df["web_name"].isin(current_squad))
                        & (features_df["now_cost"] <= max_buy)
                        & (features_df["status"] == "a")
                    ].sort_values(by="moneyball_score", ascending=False)

                    # Only make the swap if the buy is meaningfully better
                    improvement_threshold = 0.5 if len(doubtful_now) == 0 else 0.0
                    if len(pool) > 0 and pool.iloc[0]["moneyball_score"] > (sell_candidate["moneyball_score"] + improvement_threshold):
                        buy_candidate = pool.iloc[0]
                        current_squad.remove(sell_candidate["web_name"])
                        current_squad.append(buy_candidate["web_name"])
                        bank = bank + sell_price - buy_candidate["now_cost"]
                        total_transfers += 1
                        transfers_this_gw += 1

                        if free_transfers > 0:
                            free_transfers -= 1
                        else:
                            hits_this_gw += 1
                            total_hits += 1
                    else:
                        break  # No worthwhile transfer found, stop trying

                # BUG-4 fix: Accrue free transfer for next week (season-dependent cap)
                free_transfers = min(ft_cap, free_transfers + 1)

            # Select Starting XI and Bench from current squad
            squad_df = features_df[features_df["web_name"].isin(current_squad)]
            xi, bench, captain, vc = self._select_lineup_and_bench(squad_df)

            # Evaluate match ground truth
            raw_pts, auto_subs = self._evaluate_actuals(xi, bench, captain, vc, actuals_df)
            net_pts = raw_pts - (hits_this_gw * 4.0)

            squad_val = float(squad_df["now_cost"].sum())
            gw_records.append(GameweekRecord(
                gw=gw,
                starting_xi=xi,
                bench=bench,
                captain=captain,
                vice_captain=vc,
                auto_subs=auto_subs,
                raw_points=raw_pts,
                hits_taken=hits_this_gw,
                net_points=net_pts,
                squad_value=squad_val,
                bank=bank
            ))

        # Step 3: Compute summary performance metrics
        net_pts_series = [r.net_points for r in gw_records]
        total_net = sum(net_pts_series)
        mean_gw = float(np.mean(net_pts_series)) if net_pts_series else 0.0
        # ISSUE-8 fix: Use sample std dev (ddof=1) instead of population std dev
        std_gw = float(np.std(net_pts_series, ddof=1)) if len(net_pts_series) > 1 else 1.0

        # BUG-2 fix: net_points already includes hit deductions, don't subtract again
        # Sharpe ratio: mean net points over standard deviation
        sharpe = mean_gw / max(1.0, std_gw)

        # Risk-adjusted score: rewards high average while penalizing variance
        risk_adjusted = mean_gw - (0.15 * std_gw)

        result = SeasonResult(
            season=season,
            total_net_points=total_net,
            mean_gw_points=mean_gw,
            std_gw_points=std_gw,
            sharpe_ratio=sharpe,
            risk_adjusted_score=risk_adjusted,
            total_transfers=total_transfers,
            total_hits=total_hits,
            gameweeks=gw_records
        )

        logger.info(
            "Season %s complete: Total %d pts | Mean %.1f +/- %.1f | Sharpe %.3f | Hits %d | Transfers %d",
            season, total_net, mean_gw, std_gw, sharpe, total_hits, total_transfers
        )
        return result
