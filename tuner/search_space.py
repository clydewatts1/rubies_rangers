"""
Search Space Definition for Optuna Hyperparameter Optimization
Maps Optuna Trial suggestions directly into the nested config structure.

Populates both canonical and alias keys for full interoperability across
all sub-models (Moneyball, Venue, Strategic, Macro Jitter, Weather, Seasonality, Forward Alpha).
"""

from __future__ import annotations
from typing import Dict, Optional
import copy
import optuna

from config_manager import get_config


def get_param_ranges() -> Dict:
    """Returns documentation of the active parameter search boundaries."""
    return {
        # Moneyball FWD/MID weights
        "moneyball.fwd_mid_weights.xgi_per_90": (2.0, 6.0, 0.1),
        "moneyball.fwd_mid_weights.ict_index_divisor": (30.0, 80.0, 2.0),
        "moneyball.fwd_mid_weights.ppg_weight": (0.5, 2.5, 0.1),
        "moneyball.fwd_mid_weights.form_weight": (0.5, 3.0, 0.1),
        # Moneyball DEF weights
        "moneyball.def_weights.def_contribution_per_90": (0.2, 1.6, 0.1),
        "moneyball.def_weights.clean_sheets_per_90": (0.0, 5.0, 0.25),
        "moneyball.def_weights.xgi_per_90": (1.0, 5.0, 0.25),
        "moneyball.def_weights.ict_index_divisor": (30.0, 90.0, 5.0),
        "moneyball.def_weights.form_weight": (0.5, 3.0, 0.1),
        # Moneyball GKP weights
        "moneyball.gkp_weights.saves_per_90": (0.0, 1.5, 0.1),
        "moneyball.gkp_weights.clean_sheets_per_90": (0.0, 6.0, 0.5),
        "moneyball.gkp_weights.ppg_weight": (0.5, 2.5, 0.1),
        "moneyball.gkp_weights.form_weight": (0.5, 3.0, 0.1),
        # FDR scaling
        "moneyball.fdr.scaling_factor": (0.05, 0.35, 0.05),
        # Venue Impact Multipliers
        "venue.def_home_mult": (1.05, 1.35, 0.05),
        "venue.gkp_home_mult": (1.00, 1.20, 0.02),
        "venue.att_home_mult": (1.00, 1.20, 0.02),
        "venue.away_mult": (0.84, 1.00, 0.02),
        "venue.gkp_away_save_boost": (1.05, 1.35, 0.05),
        "venue.tier_damping.mid_table": (1.10, 1.50, 0.05),
        # Macro Match Jitter
        "monte_carlo.macro_jitter.pace_volatility": (0.05, 0.30, 0.05),
        # Strategic Horizon & Discount
        "strategic.horizon.discount_gamma": (0.82, 0.98, 0.01),
        # Strategic Venue Multipliers
        "strategic.venue.nu_att_home": (1.02, 1.30, 0.01),
        "strategic.venue.nu_att_away": (0.75, 0.98, 0.01),
        "strategic.venue.nu_def_home": (0.70, 0.95, 0.01),
        "strategic.venue.nu_def_away": (1.05, 1.35, 0.01),
        # Strategic Defense Clean Sheet Scale
        "strategic.defense.kappa_cs_scale": (0.80, 1.25, 0.01),
        # Strategic Fixture Wave Thresholds
        "strategic.waves.threshold_green": (2.20, 2.80, 0.05),
        "strategic.waves.threshold_red": (3.10, 3.80, 0.05),
        # Strategic Market Momentum Weight
        "strategic.market.momentum_weight": (0.00, 0.50, 0.02),
        # Strategic Balance Sheet Option Value
        "strategic.balance_sheet.ft_option_mult": (0.50, 3.00, 0.10),
        # Weather Environmental Multipliers
        "weather.beta_wind": (0.002, 0.020, 0.002),
        "weather.beta_rain": (0.005, 0.050, 0.005),
        "weather.max_dampener": (0.10, 0.40, 0.05),
        # Seasonality & Fixture Congestion
        "seasonality.alpha_congestion": (0.02, 0.15, 0.01),
        "seasonality.veteran_multiplier": (1.10, 2.00, 0.10),
        # Forward Alpha Tactical Process Weights
        "forward_metrics.weights.talisman_share": (0.01, 0.10, 0.01),
        "forward_metrics.weights.box_touch_ratio": (0.01, 0.08, 0.01),
        "forward_metrics.weights.finishing_delta": (0.01, 0.08, 0.01),
        "forward_metrics.weights.defensive_disruption": (0.01, 0.05, 0.01),
    }


def sample_config_params(trial: optuna.Trial, base_config: Optional[Dict] = None) -> Dict:
    """
    Samples trial values and structures them into a complete parameter dictionary
    ready to be tested by WalkForwardSimulator or written to config.yaml.
    """
    if base_config is None:
        cfg = get_config()
        base_params = copy.deepcopy(cfg.get("heuristic", {}))
    else:
        base_params = copy.deepcopy(base_config)

    mb = base_params.setdefault("moneyball", {})

    # 1. Forward / Midfielder Weights
    fwd_xgi = round(trial.suggest_float("mb_fwd_xgi_90", 2.0, 6.0, step=0.1), 2)
    fwd_ict = round(trial.suggest_float("mb_fwd_ict_div", 30.0, 80.0, step=2.0), 1)
    fwd_ppg = round(trial.suggest_float("mb_fwd_ppg_weight", 0.5, 2.5, step=0.1), 2)
    fwd_form = round(trial.suggest_float("mb_fwd_form_weight", 0.5, 3.0, step=0.1), 2)

    # Canonical
    fwd_mid = mb.setdefault("fwd_mid", {})
    fwd_mid["xgi_weight"] = fwd_xgi
    fwd_mid["ict_divisor"] = fwd_ict
    fwd_mid["ppg_weight"] = fwd_ppg
    fwd_mid["form_weight"] = fwd_form

    # Alias
    fwd_mid_w = mb.setdefault("fwd_mid_weights", {})
    fwd_mid_w["xgi_per_90"] = fwd_xgi
    fwd_mid_w["ict_index_divisor"] = fwd_ict
    fwd_mid_w["ppg_weight"] = fwd_ppg
    fwd_mid_w["form_weight"] = fwd_form

    # 2. Defender Weights
    def_contrib = round(trial.suggest_float("mb_def_contrib_90", 0.2, 1.6, step=0.1), 2)
    def_cs = round(trial.suggest_float("mb_def_cs_90", 0.0, 5.0, step=0.25), 2)
    def_xgi = round(trial.suggest_float("mb_def_xgi_90", 1.0, 5.0, step=0.25), 2)
    def_ict = round(trial.suggest_float("mb_def_ict_div", 30.0, 90.0, step=5.0), 1)
    def_form = round(trial.suggest_float("mb_def_form_weight", 0.5, 3.0, step=0.1), 2)

    # Canonical
    def_w = mb.setdefault("def", {})
    def_w["def_contrib_weight"] = def_contrib
    def_w["clean_sheets_weight"] = def_cs
    def_w["xgi_weight"] = def_xgi
    def_w["ict_divisor"] = def_ict
    def_w["form_weight"] = def_form

    # Alias
    def_weights = mb.setdefault("def_weights", {})
    def_weights["def_contribution_per_90"] = def_contrib
    def_weights["clean_sheets_per_90"] = def_cs
    def_weights["xgi_per_90"] = def_xgi
    def_weights["ict_index_divisor"] = def_ict
    def_weights["form_weight"] = def_form

    # 3. Goalkeeper Weights
    gkp_saves = round(trial.suggest_float("mb_gkp_saves_90", 0.0, 1.5, step=0.1), 2)
    gkp_cs = round(trial.suggest_float("mb_gkp_cs_90", 0.0, 6.0, step=0.5), 2)
    gkp_ppg = round(trial.suggest_float("mb_gkp_ppg_weight", 0.5, 2.5, step=0.1), 2)
    gkp_form = round(trial.suggest_float("mb_gkp_form_weight", 0.5, 3.0, step=0.1), 2)

    # Canonical
    gkp_w = mb.setdefault("gkp", {})
    gkp_w["saves_weight"] = gkp_saves
    gkp_w["clean_sheets_weight"] = gkp_cs
    gkp_w["ppg_weight"] = gkp_ppg
    gkp_w["form_weight"] = gkp_form

    # Alias
    gkp_weights = mb.setdefault("gkp_weights", {})
    gkp_weights["saves_per_90"] = gkp_saves
    gkp_weights["clean_sheets_per_90"] = gkp_cs
    gkp_weights["ppg_weight"] = gkp_ppg
    gkp_weights["form_weight"] = gkp_form

    # 4. FDR Multiplier
    fdr_scale = round(trial.suggest_float("mb_fdr_scaling", 0.05, 0.35, step=0.05), 3)
    fdr_m = mb.setdefault("fdr_multiplier", {})
    fdr_m["scaling_factor"] = fdr_scale
    mb.setdefault("fdr", {})["scaling_factor"] = fdr_scale

    # 5. Venue Impact
    venue = base_params.setdefault("venue", {})
    venue["def_home_mult"] = round(trial.suggest_float("mb_def_home_mult", 1.05, 1.35, step=0.05), 2)
    venue["gkp_home_mult"] = round(trial.suggest_float("mb_gkp_home_mult", 1.00, 1.20, step=0.02), 2)
    venue["att_home_mult"] = round(trial.suggest_float("mb_att_home_mult", 1.00, 1.20, step=0.02), 2)
    venue["away_mult"] = round(trial.suggest_float("mb_away_mult", 0.84, 1.00, step=0.02), 2)
    venue["gkp_away_save_boost"] = round(trial.suggest_float("mb_gkp_away_save_boost", 1.05, 1.35, step=0.05), 2)
    
    tier = venue.setdefault("tier_damping", {})
    tier["mid_table"] = round(trial.suggest_float("mb_mid_tier_mult", 1.10, 1.50, step=0.05), 2)

    # 6. Macro Match Jitter
    mc = base_params.setdefault("monte_carlo", {})
    mj = mc.setdefault("macro_jitter", {})
    mj["pace_volatility"] = round(trial.suggest_float("mc_pace_volatility", 0.05, 0.30, step=0.05), 2)

    # 7. Strategic Multi-Period Hyperparameters
    strat = base_params.setdefault("strategic", {})
    strat_hor = strat.setdefault("horizon", {})
    strat_hor["discount_gamma"] = round(trial.suggest_float("strat_discount_gamma", 0.82, 0.98, step=0.01), 2)

    strat_ven = strat.setdefault("venue", {})
    strat_ven["nu_att_home"] = round(trial.suggest_float("strat_nu_att_home", 1.02, 1.30, step=0.01), 2)
    strat_ven["nu_att_away"] = round(trial.suggest_float("strat_nu_att_away", 0.75, 0.98, step=0.01), 2)
    strat_ven["nu_def_home"] = round(trial.suggest_float("strat_nu_def_home", 0.70, 0.95, step=0.01), 2)
    strat_ven["nu_def_away"] = round(trial.suggest_float("strat_nu_def_away", 1.05, 1.35, step=0.01), 2)

    strat_def = strat.setdefault("defense", {})
    strat_def["kappa_cs_scale"] = round(trial.suggest_float("strat_kappa_cs_scale", 0.80, 1.25, step=0.01), 2)

    strat_wav = strat.setdefault("waves", {})
    strat_wav["threshold_green"] = round(trial.suggest_float("strat_threshold_green", 2.20, 2.80, step=0.05), 2)
    strat_wav["threshold_red"] = round(trial.suggest_float("strat_threshold_red", 3.10, 3.80, step=0.05), 2)

    strat_mkt = strat.setdefault("market", {})
    strat_mkt["momentum_weight"] = round(trial.suggest_float("strat_momentum_weight", 0.00, 0.50, step=0.02), 2)

    strat_bs = strat.setdefault("balance_sheet", {})
    strat_bs["ft_option_mult"] = round(trial.suggest_float("strat_ft_option_mult", 0.50, 3.00, step=0.10), 2)

    # 8. Weather Environmental Multipliers
    wthr = base_params.setdefault("weather", {})
    wthr["beta_wind"] = round(trial.suggest_float("wthr_beta_wind", 0.002, 0.020, step=0.002), 4)
    wthr["beta_rain"] = round(trial.suggest_float("wthr_beta_rain", 0.005, 0.050, step=0.005), 4)
    wthr["max_dampener"] = round(trial.suggest_float("wthr_max_dampener", 0.10, 0.40, step=0.05), 2)

    # 9. Seasonality & Congestion
    seas = base_params.setdefault("seasonality", {})
    seas["alpha_congestion"] = round(trial.suggest_float("seas_alpha_congestion", 0.02, 0.15, step=0.01), 3)
    seas["veteran_multiplier"] = round(trial.suggest_float("seas_veteran_multiplier", 1.10, 2.00, step=0.10), 2)

    # 10. Forward Alpha Tactical Process Weights
    fwd_m = base_params.setdefault("forward_metrics", {})
    fwd_m_w = fwd_m.setdefault("weights", {})
    fwd_m_w["talisman_share"] = round(trial.suggest_float("fwd_talisman_share", 0.01, 0.10, step=0.01), 3)
    fwd_m_w["box_touch_ratio"] = round(trial.suggest_float("fwd_box_touch_ratio", 0.01, 0.08, step=0.01), 3)
    fwd_m_w["finishing_delta"] = round(trial.suggest_float("fwd_finishing_delta", 0.01, 0.08, step=0.01), 3)
    fwd_m_w["defensive_disruption"] = round(trial.suggest_float("fwd_defensive_disruption", 0.01, 0.05, step=0.01), 3)

    return base_params


def reconstruct_params_from_dict(params_dict: Dict, base_config: Optional[Dict] = None) -> Dict:
    """
    Reconstructs the full config structure from an Optuna trial's params dict.
    Used by engine.py to safely reconstruct best trial params without calling
    suggest_* on a frozen trial (ISSUE-12 fix).
    """
    if base_config is None:
        cfg = get_config()
        base_params = copy.deepcopy(cfg.get("heuristic", {}))
    else:
        base_params = copy.deepcopy(base_config)

    mb = base_params.setdefault("moneyball", {})

    # FWD/MID
    fwd_xgi = round(params_dict.get("mb_fwd_xgi_90", 4.0), 2)
    fwd_ict = round(params_dict.get("mb_fwd_ict_div", 50.0), 1)
    fwd_ppg = round(params_dict.get("mb_fwd_ppg_weight", 1.2), 2)
    fwd_form = round(params_dict.get("mb_fwd_form_weight", 1.5), 2)

    fwd_mid = mb.setdefault("fwd_mid", {})
    fwd_mid["xgi_weight"] = fwd_xgi
    fwd_mid["ict_divisor"] = fwd_ict
    fwd_mid["ppg_weight"] = fwd_ppg
    fwd_mid["form_weight"] = fwd_form

    fwd_mid_w = mb.setdefault("fwd_mid_weights", {})
    fwd_mid_w["xgi_per_90"] = fwd_xgi
    fwd_mid_w["ict_index_divisor"] = fwd_ict
    fwd_mid_w["ppg_weight"] = fwd_ppg
    fwd_mid_w["form_weight"] = fwd_form

    # DEF
    def_contrib = round(params_dict.get("mb_def_contrib_90", 0.4), 2)
    def_cs = round(params_dict.get("mb_def_cs_90", 3.5), 2)
    def_xgi = round(params_dict.get("mb_def_xgi_90", 3.0), 2)
    def_ict = round(params_dict.get("mb_def_ict_div", 60.0), 1)
    def_form = round(params_dict.get("mb_def_form_weight", 1.5), 2)

    def_w = mb.setdefault("def", {})
    def_w["def_contrib_weight"] = def_contrib
    def_w["clean_sheets_weight"] = def_cs
    def_w["xgi_weight"] = def_xgi
    def_w["ict_divisor"] = def_ict
    def_w["form_weight"] = def_form

    def_weights = mb.setdefault("def_weights", {})
    def_weights["def_contribution_per_90"] = def_contrib
    def_weights["clean_sheets_per_90"] = def_cs
    def_weights["xgi_per_90"] = def_xgi
    def_weights["ict_index_divisor"] = def_ict
    def_weights["form_weight"] = def_form

    # GKP
    gkp_saves = round(params_dict.get("mb_gkp_saves_90", 0.9), 2)
    gkp_cs = round(params_dict.get("mb_gkp_cs_90", 3.0), 2)
    gkp_ppg = round(params_dict.get("mb_gkp_ppg_weight", 1.2), 2)
    gkp_form = round(params_dict.get("mb_gkp_form_weight", 1.5), 2)

    gkp_w = mb.setdefault("gkp", {})
    gkp_w["saves_weight"] = gkp_saves
    gkp_w["clean_sheets_weight"] = gkp_cs
    gkp_w["ppg_weight"] = gkp_ppg
    gkp_w["form_weight"] = gkp_form

    gkp_weights = mb.setdefault("gkp_weights", {})
    gkp_weights["saves_per_90"] = gkp_saves
    gkp_weights["clean_sheets_per_90"] = gkp_cs
    gkp_weights["ppg_weight"] = gkp_ppg
    gkp_weights["form_weight"] = gkp_form

    # FDR
    fdr_scale = round(params_dict.get("mb_fdr_scaling", 0.15), 3)
    fdr_m = mb.setdefault("fdr_multiplier", {})
    fdr_m["scaling_factor"] = fdr_scale
    mb.setdefault("fdr", {})["scaling_factor"] = fdr_scale

    # Venue Impact
    venue = base_params.setdefault("venue", {})
    venue["def_home_mult"] = round(params_dict.get("mb_def_home_mult", 1.18), 2)
    venue["gkp_home_mult"] = round(params_dict.get("mb_gkp_home_mult", 1.08), 2)
    venue["att_home_mult"] = round(params_dict.get("mb_att_home_mult", 1.08), 2)
    venue["away_mult"] = round(params_dict.get("mb_away_mult", 0.92), 2)
    venue["gkp_away_save_boost"] = round(params_dict.get("mb_gkp_away_save_boost", 1.20), 2)
    
    tier = venue.setdefault("tier_damping", {})
    tier["mid_table"] = round(params_dict.get("mb_mid_tier_mult", 1.30), 2)

    # Macro Match Jitter
    mc = base_params.setdefault("monte_carlo", {})
    mj = mc.setdefault("macro_jitter", {})
    mj["pace_volatility"] = round(params_dict.get("mc_pace_volatility", 0.15), 2)

    # Strategic Multi-Period Hyperparameters
    strat = base_params.setdefault("strategic", {})
    strat_hor = strat.setdefault("horizon", {})
    strat_hor["discount_gamma"] = round(params_dict.get("strat_discount_gamma", 0.92), 2)

    strat_ven = strat.setdefault("venue", {})
    strat_ven["nu_att_home"] = round(params_dict.get("strat_nu_att_home", 1.15), 2)
    strat_ven["nu_att_away"] = round(params_dict.get("strat_nu_att_away", 0.87), 2)
    strat_ven["nu_def_home"] = round(params_dict.get("strat_nu_def_home", 0.85), 2)
    strat_ven["nu_def_away"] = round(params_dict.get("strat_nu_def_away", 1.18), 2)

    strat_def = strat.setdefault("defense", {})
    strat_def["kappa_cs_scale"] = round(params_dict.get("strat_kappa_cs_scale", 1.00), 2)

    strat_wav = strat.setdefault("waves", {})
    strat_wav["threshold_green"] = round(params_dict.get("strat_threshold_green", 2.50), 2)
    strat_wav["threshold_red"] = round(params_dict.get("strat_threshold_red", 3.40), 2)

    strat_mkt = strat.setdefault("market", {})
    strat_mkt["momentum_weight"] = round(params_dict.get("strat_momentum_weight", 0.20), 2)

    strat_bs = strat.setdefault("balance_sheet", {})
    strat_bs["ft_option_mult"] = round(params_dict.get("strat_ft_option_mult", 1.50), 2)

    # Weather
    wthr = base_params.setdefault("weather", {})
    wthr["beta_wind"] = round(params_dict.get("wthr_beta_wind", 0.008), 4)
    wthr["beta_rain"] = round(params_dict.get("wthr_beta_rain", 0.025), 4)
    wthr["max_dampener"] = round(params_dict.get("wthr_max_dampener", 0.25), 2)

    # Seasonality
    seas = base_params.setdefault("seasonality", {})
    seas["alpha_congestion"] = round(params_dict.get("seas_alpha_congestion", 0.08), 3)
    seas["veteran_multiplier"] = round(params_dict.get("seas_veteran_multiplier", 1.50), 2)

    # Forward Alpha
    fwd_m = base_params.setdefault("forward_metrics", {})
    fwd_m_w = fwd_m.setdefault("weights", {})
    fwd_m_w["talisman_share"] = round(params_dict.get("fwd_talisman_share", 0.05), 3)
    fwd_m_w["box_touch_ratio"] = round(params_dict.get("fwd_box_touch_ratio", 0.03), 3)
    fwd_m_w["finishing_delta"] = round(params_dict.get("fwd_finishing_delta", 0.04), 3)
    fwd_m_w["defensive_disruption"] = round(params_dict.get("fwd_defensive_disruption", 0.02), 3)

    return base_params
