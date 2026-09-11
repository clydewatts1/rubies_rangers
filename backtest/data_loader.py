"""
Historical Data Pipeline for Multi-Season Walk-Forward Backtesting
Fetches, normalizes, and extracts point-in-time (anti-leakage) player features
from the Vaastav Fantasy Premier League historical datasets.
"""

from __future__ import annotations
import os
import urllib.request
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("backtest.data_loader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

VAASTAV_BASE_URL = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
DEFAULT_HISTORICAL_DIR = Path("data/historical")


class HistoricalDataLoader:
    """
    Handles downloading, disk-caching, and point-in-time feature extraction
    for multi-season FPL datasets.
    """

    AVAILABLE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25"]

    POSITION_MAP = {
        "GK": "GKP",
        "GKP": "GKP",
        "1": "GKP",
        1: "GKP",
        "DEF": "DEF",
        "2": "DEF",
        2: "DEF",
        "MID": "MID",
        "3": "MID",
        3: "MID",
        "FWD": "FWD",
        "4": "FWD",
        4: "FWD",
    }

    def __init__(self, data_dir: Optional[Path | str] = None):
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_HISTORICAL_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._season_cache: Dict[str, pd.DataFrame] = {}

    def fetch_season_raw(self, season: str, force_refresh: bool = False) -> pd.DataFrame:
        """
        Loads the raw merged gameweek CSV for the requested season.
        Caches on disk to avoid redundant downloads.
        """
        if not force_refresh and season in self._season_cache:
            return self._season_cache[season]

        cache_path = self.data_dir / f"{season}_merged_gw.csv"
        if not force_refresh and cache_path.exists():
            logger.info("Loading cached season %s from %s", season, cache_path)
            df = pd.read_csv(cache_path, low_memory=False)
            self._season_cache[season] = df
            return df

        url = f"{VAASTAV_BASE_URL}/{season}/gws/merged_gw.csv"
        logger.info("Downloading season %s data from %s ...", season, url)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RubiesRangers-Backtester/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read()
            with open(cache_path, "wb") as f:
                f.write(content)
            df = pd.read_csv(cache_path, low_memory=False)
            logger.info("Downloaded %d rows for season %s", len(df), season)
            self._season_cache[season] = df
            return df
        except Exception as e:
            logger.error("Failed to fetch season %s from %s: %s", season, url, e)
            if cache_path.exists():
                logger.warning("Falling back to existing disk cache for %s", season)
                df = pd.read_csv(cache_path, low_memory=False)
                self._season_cache[season] = df
                return df
            raise RuntimeError(f"Unable to load historical data for season {season}: {e}") from e

    def normalize_season_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalizes schemas across seasons into standard Moneyball backtesting columns.
        """
        df = raw_df.copy()

        # Gameweek / Round normalization
        if "round" in df.columns:
            df["gw"] = pd.to_numeric(df["round"], errors="coerce").fillna(0).astype(int)
        elif "GW" in df.columns:
            df["gw"] = pd.to_numeric(df["GW"], errors="coerce").fillna(0).astype(int)
        else:
            df["gw"] = 1

        # Player Name normalization
        if "name" in df.columns:
            df["web_name"] = df["name"].astype(str)
        elif "player_name" in df.columns:
            df["web_name"] = df["player_name"].astype(str)
        else:
            df["web_name"] = "Unknown"

        # Position normalization
        pos_col = None
        for col in ["position", "element_type"]:
            if col in df.columns:
                pos_col = col
                break
        if pos_col:
            df["position_name"] = df[pos_col].map(lambda x: self.POSITION_MAP.get(str(x).upper(), "MID"))
        else:
            df["position_name"] = "MID"

        # Cost normalization (FPL stores value in tenths of millions, e.g. 55 = £5.5m)
        if "value" in df.columns:
            df["now_cost"] = pd.to_numeric(df["value"], errors="coerce").fillna(50.0) / 10.0
        elif "now_cost" in df.columns:
            df["now_cost"] = pd.to_numeric(df["now_cost"], errors="coerce").fillna(5.0)
        else:
            df["now_cost"] = 5.0

        # Team / Club normalization
        if "team" in df.columns:
            df["club_name"] = df["team"].astype(str)
        else:
            df["club_name"] = "Unknown"

        # Points & Minutes
        df["total_points"] = pd.to_numeric(df["total_points"], errors="coerce").fillna(0.0) if "total_points" in df.columns else pd.Series(0.0, index=df.index)
        df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0) if "minutes" in df.columns else pd.Series(0.0, index=df.index)

        # Underlying Moneyball metrics
        if "expected_goal_involvements" in df.columns:
            df["xgi"] = pd.to_numeric(df["expected_goal_involvements"], errors="coerce").fillna(0.0)
        else:
            xg = pd.to_numeric(df["expected_goals"], errors="coerce").fillna(0.0) if "expected_goals" in df.columns else pd.Series(0.0, index=df.index)
            xa = pd.to_numeric(df["expected_assists"], errors="coerce").fillna(0.0) if "expected_assists" in df.columns else pd.Series(0.0, index=df.index)
            df["xgi"] = xg + xa

        df["ict_index"] = pd.to_numeric(df["ict_index"], errors="coerce").fillna(0.0) if "ict_index" in df.columns else pd.Series(0.0, index=df.index)
        df["clean_sheets"] = pd.to_numeric(df["clean_sheets"], errors="coerce").fillna(0.0) if "clean_sheets" in df.columns else pd.Series(0.0, index=df.index)
        df["saves"] = pd.to_numeric(df["saves"], errors="coerce").fillna(0.0) if "saves" in df.columns else pd.Series(0.0, index=df.index)
        df["goals_conceded"] = pd.to_numeric(df["goals_conceded"], errors="coerce").fillna(0.0) if "goals_conceded" in df.columns else pd.Series(0.0, index=df.index)
        df["yellow_cards"] = pd.to_numeric(df["yellow_cards"], errors="coerce").fillna(0.0) if "yellow_cards" in df.columns else pd.Series(0.0, index=df.index)
        df["red_cards"] = pd.to_numeric(df["red_cards"], errors="coerce").fillna(0.0) if "red_cards" in df.columns else pd.Series(0.0, index=df.index)
        df["bps"] = pd.to_numeric(df["bps"], errors="coerce").fillna(0.0) if "bps" in df.columns else pd.Series(0.0, index=df.index)

        return df

    @staticmethod
    def _resolve_moneyball_params(moneyball_params: Optional[Dict]) -> Dict:
        """
        Normalizes Moneyball config keys to canonical form, accepting both
        heuristic-style keys (fwd_mid.xgi_weight) and tuned-style keys
        (fwd_mid_weights.xgi_per_90).
        """
        mp = moneyball_params or {}

        # FWD/MID weights — try tuned keys first, fall back to heuristic keys
        fwd_src = mp.get("fwd_mid_weights", mp.get("fwd_mid", {}))
        fwd_mid = {
            "xgi_weight": float(fwd_src.get("xgi_per_90", fwd_src.get("xgi_weight", 4.0))),
            "ict_divisor": float(fwd_src.get("ict_index_divisor", fwd_src.get("ict_divisor", 50.0))),
            "form_weight": float(fwd_src.get("form_weight", 1.5)),
            "ppg_weight": float(fwd_src.get("ppg_weight", 1.2)),
        }

        # DEF weights
        def_src = mp.get("def_weights", mp.get("def", {}))
        def_w = {
            "def_contrib_weight": float(def_src.get("def_contribution_per_90", def_src.get("def_contrib_weight", 0.4))),
            "xgi_weight": float(def_src.get("xgi_per_90", def_src.get("xgi_weight", 3.0))),
            "form_weight": float(def_src.get("form_weight", 1.5)),
            "ict_divisor": float(def_src.get("ict_index_divisor", def_src.get("ict_divisor", 60.0))),
            "clean_sheets_weight": float(def_src.get("clean_sheets_per_90", 0.0)),
        }

        # GKP weights
        gkp_src = mp.get("gkp_weights", mp.get("gkp", {}))
        gkp_w = {
            "ppg_weight": float(gkp_src.get("ppg_weight", 1.2)),
            "form_weight": float(gkp_src.get("form_weight", 1.5)),
            "saves_weight": float(gkp_src.get("saves_per_90", 0.0)),
            "clean_sheets_weight": float(gkp_src.get("clean_sheets_per_90", 0.0)),
        }

        # FDR scaling
        fdr_src = mp.get("fdr", mp.get("fdr_multiplier", {}))
        fdr = {
            "scaling_factor": float(fdr_src.get("scaling_factor", 5.0)),
        }

        return {"fwd_mid": fwd_mid, "def": def_w, "gkp": gkp_w, "fdr": fdr}

    def _get_prior_season(self, season: str) -> Optional[str]:
        """Returns the season immediately preceding the given one, if available."""
        try:
            idx = self.AVAILABLE_SEASONS.index(season)
            if idx > 0:
                return self.AVAILABLE_SEASONS[idx - 1]
        except ValueError:
            pass
        return None

    def _build_cross_season_priors(
        self,
        current_player_pool: pd.DataFrame,
        prior_season: str,
    ) -> pd.DataFrame:
        """
        Uses the prior season's full-season stats as informative priors
        for GW1 of the current season, matched by web_name.
        Falls back to flat priors for players without prior history.
        """
        try:
            prior_raw = self.fetch_season_raw(prior_season)
            prior_df = self.normalize_season_df(prior_raw)
        except Exception:
            logger.warning("Could not load prior season %s for priors; using flat defaults", prior_season)
            return self._build_flat_priors(current_player_pool)

        # Aggregate entire prior season per player
        prior_agg = prior_df.groupby("web_name").agg(
            prior_games=("minutes", lambda m: (m > 0).sum()),
            prior_minutes=("minutes", "sum"),
            prior_points=("total_points", "sum"),
            prior_xgi=("xgi", "sum"),
            prior_ict=("ict_index", "sum"),
            prior_cs=("clean_sheets", "sum"),
            prior_saves=("saves", "sum"),
        ).reset_index()

        features_df = current_player_pool[["web_name", "position_name", "club_name", "now_cost"]].drop_duplicates(subset=["web_name"]).copy()
        features_df = pd.merge(features_df, prior_agg, on="web_name", how="left")

        # Fill missing (new players) with flat defaults
        features_df["prior_games"] = features_df["prior_games"].fillna(0)
        has_prior = features_df["prior_games"] > 0

        n_90s = np.maximum(0.5, features_df["prior_minutes"].fillna(0) / 90.0)
        gp = np.maximum(1, features_df["prior_games"])

        # Per-90 rates from prior season
        features_df["points_per_game"] = np.where(has_prior, features_df["prior_points"] / gp, 3.5)
        features_df["minutes_per_game"] = np.where(has_prior, features_df["prior_minutes"] / gp, 60.0)
        features_df["expected_goal_involvements_per_90"] = np.where(has_prior, features_df["prior_xgi"] / n_90s, 0.25)
        features_df["ict_index"] = np.where(has_prior, features_df["prior_ict"] / gp, 25.0)
        features_df["clean_sheets_per_90"] = np.where(has_prior, features_df["prior_cs"] / n_90s, 0.25)
        features_df["saves_per_90"] = np.where(has_prior, features_df["prior_saves"] / n_90s, 1.5)
        features_df["defensive_contribution_per_90"] = np.where(has_prior, features_df["clean_sheets_per_90"] * 1.5, 0.5)
        features_df["form"] = features_df["points_per_game"]  # Prior season PPG as initial form
        features_df["recent_ppg"] = features_df["form"]

        features_df["games_played"] = 0
        features_df["total_points_sum"] = 0.0
        features_df["total_points"] = 0.0
        features_df["status"] = "a"

        # Drop temporary prior columns
        features_df.drop(columns=[c for c in features_df.columns if c.startswith("prior_")], inplace=True)

        return features_df

    @staticmethod
    def _build_flat_priors(player_pool: pd.DataFrame) -> pd.DataFrame:
        """Builds flat (uninformative) priors when no prior season data is available."""
        features_df = player_pool[["web_name", "position_name", "club_name", "now_cost"]].drop_duplicates(subset=["web_name"]).copy()
        features_df["games_played"] = 0
        features_df["total_points_sum"] = 0.0
        features_df["total_points"] = 0.0
        features_df["points_per_game"] = 3.5
        features_df["minutes_per_game"] = 60.0
        features_df["expected_goal_involvements_per_90"] = 0.25
        features_df["ict_index"] = 25.0
        features_df["clean_sheets_per_90"] = 0.25
        features_df["saves_per_90"] = 1.5
        features_df["defensive_contribution_per_90"] = 0.5
        features_df["form"] = 3.5
        features_df["recent_ppg"] = 3.5
        features_df["status"] = "a"
        return features_df

    def get_point_in_time_snapshot(
        self,
        season: str,
        gw: int,
        moneyball_params: Optional[Dict] = None,
        form_window: int = 5
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Anti-leakage point-in-time snapshot generator.
        
        Returns:
            features_df: Available information strictly from gameweeks < gw (or pre-season if gw == 1).
            actuals_df: Match actuals strictly from gameweek gw (used only for scoring the chosen lineup).
        """
        raw_df = self.fetch_season_raw(season)
        df = self.normalize_season_df(raw_df)

        actuals_df = df[df["gw"] == gw].copy()
        history_df = df[df["gw"] < gw].copy()

        # ISSUE-9 fix: If gw == 1, use cross-season priors instead of flat constants
        if gw == 1 or history_df.empty:
            prior_season = self._get_prior_season(season)
            if prior_season:
                features_df = self._build_cross_season_priors(actuals_df, prior_season)
            else:
                features_df = self._build_flat_priors(actuals_df)
        else:
            # BUG-3 fix: Use recent_history for form calculation
            recent_gw_min = max(1, gw - form_window)
            recent_history = history_df[history_df["gw"] >= recent_gw_min]

            # Latest player metadata and cost
            latest_records = (
                history_df.sort_values(by=["gw"])
                .groupby("web_name")
                .last()
                .reset_index()[["web_name", "position_name", "club_name", "now_cost"]]
            )

            # Cumulative stats across all previous gameweeks of the season
            agg_stats = history_df.groupby("web_name").agg(
                games_played=("minutes", lambda m: (m > 0).sum()),
                total_minutes=("minutes", "sum"),
                total_points_sum=("total_points", "sum"),
                total_xgi=("xgi", "sum"),
                total_ict=("ict_index", "sum"),
                total_cs=("clean_sheets", "sum"),
                total_saves=("saves", "sum"),
            ).reset_index()

            # BUG-3 fix: Recent form from form_window (not last row of all history)
            recent_agg = recent_history.groupby("web_name").agg(
                recent_games=("minutes", lambda m: (m > 0).sum()),
                recent_points=("total_points", "sum"),
                recent_minutes=("minutes", "sum"),
            ).reset_index()

            features_df = pd.merge(latest_records, agg_stats, on="web_name", how="left").fillna(0)
            features_df = pd.merge(features_df, recent_agg, on="web_name", how="left").fillna(0)
            features_df["total_points"] = features_df["total_points_sum"]

            # Calculate per-90 rates (cumulative season)
            n_90s = np.maximum(0.5, features_df["total_minutes"] / 90.0)
            gp = np.maximum(1, features_df["games_played"])

            features_df["points_per_game"] = features_df["total_points_sum"] / gp
            features_df["minutes_per_game"] = features_df["total_minutes"] / gp
            features_df["expected_goal_involvements_per_90"] = features_df["total_xgi"] / n_90s
            features_df["ict_index"] = features_df["total_ict"] / gp
            features_df["clean_sheets_per_90"] = features_df["total_cs"] / n_90s
            features_df["saves_per_90"] = features_df["total_saves"] / n_90s
            features_df["defensive_contribution_per_90"] = features_df["clean_sheets_per_90"] * 1.5

            # BUG-3 fix: Synthetic form = recent PPG over form_window
            recent_gp = np.maximum(1, features_df["recent_games"])
            features_df["form"] = features_df["recent_points"] / recent_gp
            features_df["recent_ppg"] = features_df["form"]

            # BUG-3 fix: Availability based on recent window, not single last row
            last_2_gw_min = max(1, gw - 2)
            last_2_gws = history_df[history_df["gw"] >= last_2_gw_min]
            last_2_mins = last_2_gws.groupby("web_name")["minutes"].sum().reset_index()
            last_2_mins.columns = ["web_name", "last_2gw_minutes"]
            features_df = pd.merge(features_df, last_2_mins, on="web_name", how="left").fillna(0)
            features_df["status"] = np.where(features_df["last_2gw_minutes"] > 0, "a", "d")

        # ISSUE-7 fix: Normalize config keys to canonical form
        resolved = self._resolve_moneyball_params(moneyball_params)
        fwd_mid_cfg = resolved["fwd_mid"]
        def_cfg = resolved["def"]
        gkp_cfg = resolved["gkp"]

        # Ensure form column exists (flat priors set it, history path sets it)
        if "form" not in features_df.columns:
            features_df["form"] = features_df.get("points_per_game", 3.5)

        # BUG-1 fix: Position-differentiated Moneyball scoring
        # Mirrors the live system in fpl_client.py (lines 271-276)
        is_fwd_mid = features_df["position_name"].isin(["FWD", "MID"])
        is_def = features_df["position_name"] == "DEF"
        is_gkp = features_df["position_name"] == "GKP"

        # FWD/MID: xGI/90 * xgi_weight + ICT / ict_divisor + form * form_weight
        fwd_mid_score = (
            (features_df["expected_goal_involvements_per_90"] * fwd_mid_cfg["xgi_weight"])
            + (features_df["ict_index"] / fwd_mid_cfg["ict_divisor"])
            + (features_df["form"] * fwd_mid_cfg["form_weight"])
        )

        # DEF: def_contrib/90 * weight + xGI/90 * weight + form * weight + ICT / divisor
        def_score = (
            (features_df["defensive_contribution_per_90"] * def_cfg["def_contrib_weight"])
            + (features_df["expected_goal_involvements_per_90"] * def_cfg["xgi_weight"])
            + (features_df["form"] * def_cfg["form_weight"])
            + (features_df["ict_index"] / def_cfg["ict_divisor"])
        )

        # GKP: ppg * weight + form * weight + saves/90 * weight + cs/90 * weight
        gkp_score = (
            (features_df["points_per_game"] * gkp_cfg["ppg_weight"])
            + (features_df["form"] * gkp_cfg["form_weight"])
            + (features_df["saves_per_90"] * gkp_cfg["saves_weight"])
            + (features_df["clean_sheets_per_90"] * gkp_cfg["clean_sheets_weight"])
        )

        features_df["moneyball_score"] = np.where(
            is_fwd_mid, fwd_mid_score,
            np.where(is_def, def_score, gkp_score)
        )
        features_df["fdr_moneyball_score"] = features_df["moneyball_score"]

        return features_df, actuals_df
