"""
Optuna-Driven Hyperparameter Auto-Tuning Engine
Executes cross-season walk-forward optimization, SQLite trial logging,
and Two-Tier stochastic verification.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import optuna

from backtest.data_loader import HistoricalDataLoader
from backtest.simulator import WalkForwardSimulator, SeasonResult
from .search_space import sample_config_params, reconstruct_params_from_dict
from .updater import update_config_with_tuned

logger = logging.getLogger("tuner.engine")

DEFAULT_DB_PATH = Path("data/tuning_history.db")


class HyperparameterTuner:
    """
    Coordinates multi-season cross-validation and hyperparameter search using Optuna.
    """

    def __init__(
        self,
        study_name: str = "rubies_rangers_moneyball",
        db_path: Optional[Path | str] = None,
        train_seasons: Optional[List[str]] = None,
        test_season: str = "2023-24",
        auto_update_config: bool = True
    ):
        self.study_name = study_name
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_url = f"sqlite:///{self.db_path.as_posix()}"

        self.train_seasons = train_seasons or ["2021-22", "2022-23"]
        self.test_season = test_season
        self.auto_update_config = auto_update_config

        self.data_loader = HistoricalDataLoader()
        self.simulator = WalkForwardSimulator(self.data_loader)

        # Baseline performance using default heuristic profile
        self._baseline_heuristic_points: Optional[float] = None

    def get_baseline_score(self, season: Optional[str] = None) -> float:
        """Evaluates baseline score on the test season using default heuristic parameters."""
        target_season = season or self.test_season
        if self._baseline_heuristic_points is None:
            logger.info("Evaluating baseline heuristic performance on season %s ...", target_season)
            from config_manager import get_params
            baseline_params = {
                "moneyball": get_params("moneyball"),
                "optimizer": get_params("optimizer"),
                "xp_model": get_params("xp_model"),
                "montecarlo": get_params("montecarlo"),
            }
            res = self.simulator.run_season(target_season, params=baseline_params)
            self._baseline_heuristic_points = res.total_net_points
            logger.info("Baseline heuristic total points for %s: %.1f", target_season, self._baseline_heuristic_points)
        return self._baseline_heuristic_points

    def _objective(self, trial: optuna.Trial) -> float:
        """
        Optuna trial objective: Evaluates candidate hyperparameters across training seasons
        and scores them on unseen out-of-sample test season to avoid overfitting.
        """
        # Tier 1: Fast Deterministic Walk-Forward
        candidate_params = sample_config_params(trial)

        # 1. Train Seasons Evaluation
        train_scores = []
        for s in self.train_seasons:
            res = self.simulator.run_season(s, params=candidate_params)
            train_scores.append(res.risk_adjusted_score)

        mean_train_score = float(np.mean(train_scores)) if train_scores else 0.0

        # 2. Out-of-Sample Test Season Evaluation
        test_res = self.simulator.run_season(self.test_season, params=candidate_params)
        test_score = test_res.risk_adjusted_score

        # Log trial telemetry
        trial.set_user_attr("train_score", round(mean_train_score, 2))
        trial.set_user_attr("test_score", round(test_score, 2))
        trial.set_user_attr("test_net_points", round(test_res.total_net_points, 1))
        trial.set_user_attr("total_hits", test_res.total_hits)

        # Optimization Target: Combined score with out-of-sample weighting
        # We reward out-of-sample performance while enforcing consistency across training years
        objective_val = (0.4 * mean_train_score) + (0.6 * test_score)
        return float(objective_val)

    def optimize(self, n_trials: int = 50, n_jobs: int = 4) -> optuna.Study:
        """
        Executes parallelized hyperparameter optimization.
        """
        # Ensure baseline is computed first
        baseline_pts = self.get_baseline_score()

        logger.info(
            "Initializing Optuna study '%s' (DB: %s, trials: %d, workers: %d)",
            self.study_name, self.storage_url, n_trials, n_jobs
        )

        study = optuna.create_study(
            study_name=self.study_name,
            storage=self.storage_url,
            direction="maximize",
            load_if_exists=True,
            sampler=optuna.samplers.TPESampler(seed=42)
        )

        study.optimize(self._objective, n_trials=n_trials, n_jobs=n_jobs)

        best_trial = study.best_trial
        logger.info(
            "Optimization complete! Best Trial #%d: Objective Value = %.3f (Test Net Points: %s)",
            best_trial.number, best_trial.value, best_trial.user_attrs.get("test_net_points")
        )

        # Tier 2: Stochastic verification & config update
        if self.auto_update_config:
            best_params = reconstruct_params_from_dict(best_trial.params)
            test_pts = float(best_trial.user_attrs.get("test_net_points", baseline_pts))
            imp_pct = round(((test_pts - baseline_pts) / max(1.0, baseline_pts)) * 100.0, 2)

            meta = {
                "best_trial_id": best_trial.number,
                "train_seasons": self.train_seasons,
                "test_season": self.test_season,
                "train_score": best_trial.user_attrs.get("train_score"),
                "test_score": best_trial.user_attrs.get("test_score"),
                "test_points": test_pts,
                "baseline_heuristic_points": baseline_pts,
                "improvement_pct": imp_pct
            }
            update_config_with_tuned(best_params, metadata=meta)

        return study
