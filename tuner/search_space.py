"""
Search Space Definition for Optuna Hyperparameter Optimization
Maps Optuna Trial suggestions directly into the nested config structure.

ISSUE-10 fix: Only includes parameters that the WalkForwardSimulator actually
reads and uses. XP model and Monte Carlo parameters are commented out until
those models are wired into the backtest simulation loop.
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
    }


def sample_config_params(trial: optuna.Trial, base_config: Optional[Dict] = None) -> Dict:
    """
    Samples trial values and structures them into a complete parameter dictionary
    ready to be tested by WalkForwardSimulator or written to config.yaml.

    Only tunes parameters that the simulator actually reads:
    - Moneyball scoring weights (FWD/MID, DEF, GKP)
    - FDR scaling
    Populates both canonical keys (fwd_mid, def, gkp, fdr_multiplier) and
    alias keys (fwd_mid_weights, def_weights, gkp_weights, fdr) for full compatibility.
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

    return base_params
