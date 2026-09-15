"""
Unit Tests for Optuna Auto-Tuning and Search Space
"""

import tempfile
from pathlib import Path
import pytest
import yaml
import optuna

from tuner.search_space import sample_config_params, get_param_ranges, reconstruct_params_from_dict
from tuner.updater import update_config_with_tuned


def test_get_param_ranges():
    ranges = get_param_ranges()
    assert "moneyball.fwd_mid_weights.xgi_per_90" in ranges
    assert "moneyball.def_weights.def_contribution_per_90" in ranges
    assert "moneyball.gkp_weights.saves_per_90" in ranges
    assert "moneyball.fdr.scaling_factor" in ranges
    assert "venue.def_home_mult" in ranges
    assert "venue.away_mult" in ranges
    assert "monte_carlo.macro_jitter.pace_volatility" in ranges
    assert "strategic.horizon.discount_gamma" in ranges
    assert "strategic.venue.nu_att_home" in ranges
    assert "weather.beta_wind" in ranges
    assert "seasonality.alpha_congestion" in ranges
    assert "forward_metrics.weights.talisman_share" in ranges
    # Active search space has 14 Moneyball + 6 Venue + 1 Macro Jitter + 10 Strategic + 3 Weather + 2 Seasonality + 4 Forward Alpha = 40 parameters
    assert len(ranges) == 40


def test_sample_config_params():
    def mock_objective(trial: optuna.Trial) -> float:
        params = sample_config_params(trial)
        assert "moneyball" in params
        assert "fwd_mid" in params["moneyball"]
        assert "fwd_mid_weights" in params["moneyball"]
        assert "xgi_per_90" in params["moneyball"]["fwd_mid_weights"]
        assert 2.0 <= params["moneyball"]["fwd_mid_weights"]["xgi_per_90"] <= 6.0
        assert "venue" in params
        assert "monte_carlo" in params
        assert "macro_jitter" in params["monte_carlo"]
        assert 0.05 <= params["monte_carlo"]["macro_jitter"]["pace_volatility"] <= 0.30
        assert "weather" in params
        assert "beta_wind" in params["weather"]
        assert "seasonality" in params
        assert "alpha_congestion" in params["seasonality"]
        assert "forward_metrics" in params
        assert "talisman_share" in params["forward_metrics"]["weights"]
        return 1.0

    study = optuna.create_study(direction="maximize")
    study.optimize(mock_objective, n_trials=2)
    assert len(study.trials) == 2


def test_update_config_with_tuned(tmp_path: Path):
    sample_cfg = {
        "active_profile": "heuristic",
        "heuristic": {"moneyball": {"test": 1}},
        "tuned": {"moneyball": {"test": 1}}
    }
    tmp_file = tmp_path / "test_config.yaml"
    with open(tmp_file, "w", encoding="utf-8") as f:
        yaml.dump(sample_cfg, f)

    new_tuned = {"moneyball": {"test": 42, "weight": 9.9}}
    meta = {"best_trial_id": 99, "improvement_pct": 5.2}

    success = update_config_with_tuned(new_tuned, metadata=meta, config_path=tmp_file)
    assert success is True

    with open(tmp_file, "r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)

    # Heuristic preserved
    assert loaded["heuristic"]["moneyball"]["test"] == 1
    # Tuned updated
    assert loaded["tuned"]["moneyball"]["test"] == 42
    assert loaded["tuned"]["moneyball"]["weight"] == 9.9
    # Metadata recorded
    assert loaded["tuning_metadata"]["best_trial_id"] == 99
    assert loaded["tuning_metadata"]["improvement_pct"] == 5.2
    assert "last_tuned_at" in loaded["tuning_metadata"]


def test_reconstruct_params_from_dict():
    sample_params = {
        "mb_fwd_xgi_90": 4.5,
        "mb_fwd_ict_div": 45.0,
        "mb_fwd_ppg_weight": 1.4,
        "mb_fwd_form_weight": 1.8,
        "mb_def_contrib_90": 0.8,
        "mb_def_cs_90": 3.0,
        "mb_def_xgi_90": 2.5,
        "mb_def_ict_div": 55.0,
        "mb_def_form_weight": 1.2,
        "mb_gkp_saves_90": 1.1,
        "mb_gkp_cs_90": 4.0,
        "mb_gkp_ppg_weight": 1.5,
        "mb_gkp_form_weight": 1.6,
        "mb_fdr_scaling": 0.20,
    }
    reconstructed = reconstruct_params_from_dict(sample_params)
    assert reconstructed["moneyball"]["fwd_mid"]["xgi_weight"] == 4.5
    assert reconstructed["moneyball"]["fwd_mid_weights"]["xgi_per_90"] == 4.5
    assert reconstructed["moneyball"]["def"]["def_contrib_weight"] == 0.8
    assert reconstructed["moneyball"]["def_weights"]["def_contribution_per_90"] == 0.8
    assert reconstructed["moneyball"]["gkp"]["saves_weight"] == 1.1
    assert reconstructed["moneyball"]["gkp_weights"]["saves_per_90"] == 1.1
    assert reconstructed["moneyball"]["fdr_multiplier"]["scaling_factor"] == 0.20
    assert "xp_model" in reconstructed

