"""
Unit tests for config.yaml and config_manager.py
"""

import pytest
import config_manager


def test_config_loads_properly():
    cfg = config_manager.get_config()
    assert isinstance(cfg, dict)
    assert "active_profile" in cfg
    assert "system" in cfg
    assert "heuristic" in cfg
    assert "tuned" in cfg


def test_system_config_keys():
    sys_cfg = config_manager.get_system_config()
    assert sys_cfg["target_gameweek"] == 4
    assert len(sys_cfg["default_squad"]) == 15
    assert sys_cfg["default_bank"] == 3.7
    assert sys_cfg["default_league_id"] == 325320
    assert len(sys_cfg["legal_formations"]) == 8
    assert len(sys_cfg["gw4_match_odds"]) == 10


def test_heuristic_and_tuned_profiles_exist():
    h_params = config_manager.get_params(profile="heuristic")
    t_params = config_manager.get_params(profile="tuned")

    assert set(h_params.keys()) == set(t_params.keys())
    assert "moneyball" in h_params
    assert "xp_model" in h_params
    assert "monte_carlo" in h_params
    assert "optimizer" in h_params

    # Verify both profiles have valid positive weights
    assert h_params["moneyball"]["fwd_mid"]["xgi_weight"] > 0
    assert t_params["moneyball"]["fwd_mid"]["xgi_weight"] > 0
    assert h_params["monte_carlo"]["default_form_weight"] > 0
    assert t_params["monte_carlo"]["default_form_weight"] > 0


def test_set_active_profile():
    original = config_manager.get_active_profile()

    config_manager.set_active_profile("tuned")
    assert config_manager.get_active_profile() == "tuned"

    config_manager.set_active_profile("heuristic")
    assert config_manager.get_active_profile() == "heuristic"

    # Invalid profile raises ValueError
    with pytest.raises(ValueError):
        config_manager.set_active_profile("invalid_profile_xyz")


def test_section_retrieval():
    mb = config_manager.get_params("moneyball")
    assert "fwd_mid" in mb
    assert mb["fwd_mid"]["xgi_weight"] == 4.0

    mc = config_manager.get_params("monte_carlo")
    assert mc["default_sims"] == 5000
    assert mc["default_form_weight"] == 0.25

    opt = config_manager.get_params("optimizer")
    assert opt["budget"] == 100.0
    assert opt["max_players_per_club"] == 3


def test_pareto_objectives_config():
    objs = config_manager.get_pareto_objectives()
    assert isinstance(objs, list)
    assert len(objs) >= 5
    labels = [o["label"] for o in objs]
    assert "balanced" in labels
    assert "forward_alpha" in labels
    assert "weather_resilience" in labels
    assert "mean_reversion" in labels
    assert "high_attack" in labels

    # Verify enabled flags exist
    enabled_objs = [o for o in objs if o.get("enabled")]
    assert len(enabled_objs) >= 3

