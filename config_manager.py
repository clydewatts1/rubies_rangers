"""
Configuration Manager for Rubies Rangers FPL
Loads, validates, and provides access to centralized configuration settings
from config.yaml with support for 'heuristic' and 'tuned' parameter profiles.
"""

import os
import copy
from typing import Dict, Any, Optional
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

# Fallback default configuration in case config.yaml is unavailable
_DEFAULT_CONFIG: Dict[str, Any] = {
    "active_profile": "heuristic",
    "system": {
        "target_gameweek": 4,
        "default_squad": [
            "Roefs", "Verbruggen",
            "Pedro Porro", "Senesi", "Guéhi", "Robinson", "Thiaw",
            "Foden", "Ødegaard", "Mbeumo", "Cherki", "Rogers",
            "João Pedro", "Isak", "Solanke"
        ],
        "default_bank": 3.7,
        "default_league_id": 325320,
        "default_entry_id": 6173410,
        "cache_ttl_seconds": 3600,
        "http_timeout_seconds": 15,
        "max_retries": 3,
        "retry_backoff_base": 0.5,
        "legal_formations": [
            [3, 5, 2], [3, 4, 3], [4, 4, 2], [4, 3, 3],
            [4, 5, 1], [5, 3, 2], [5, 4, 1], [5, 2, 3]
        ]
    },
    "heuristic": {
        "moneyball": {
            "fwd_mid": {"xgi_weight": 4.0, "ict_divisor": 50.0, "form_weight": 1.5, "ppg_weight": 1.2},
            "def": {"def_contrib_weight": 0.4, "xgi_weight": 3.0, "form_weight": 1.5, "ict_divisor": 60.0},
            "gkp": {"ppg_weight": 1.2, "form_weight": 1.5},
            "set_piece_bonuses": {
                "pen_order_1": 0.65, "pen_order_2": 0.25,
                "fk_order_1": 0.25, "fk_order_2": 0.10,
                "crn_order_1": 0.35, "crn_order_2": 0.15
            },
            "fdr_multiplier": {"neutral_baseline": 3.0, "scaling_factor": 5.0}
        },
        "xp_model": {
            "minutes": {
                "benched_or_dropped": {"exp_mins": 5.0, "p_60": 0.02},
                "rotation_risk": {"exp_mins": 40.0, "p_60": 0.40},
                "regular_starter": {"min_mins": 60.0, "max_mins": 80.0, "p_60": 0.85},
                "secure_starter": {"min_mins": 75.0, "max_mins": 90.0, "p_60": 0.98}
            },
            "penalty": {"conversion_rate": 0.79, "match_award_chance": 0.18},
            "deadball_bonus": 0.08,
            "team_baseline_goals_divisor": 1.35,
            "gkp_saves_rate": 2.8,
            "gkp_saves_pts_ratio": 0.33,
            "def_actions_bonus_weight": 0.08
        },
        "monte_carlo": {
            "default_sims": 5000,
            "api_default_sims": 2500,
            "default_form_weight": 0.25,
            "form_multiplier": {"baseline": 4.5, "step": 0.04, "min_clip": 0.75, "max_clip": 1.30}
        },
        "optimizer": {
            "budget": 100.0,
            "max_players_per_club": 3,
            "position_quotas": {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3},
            "default_objective": "moneyball"
        }
    }
}
_DEFAULT_CONFIG["tuned"] = copy.deepcopy(_DEFAULT_CONFIG["heuristic"])

# Cached parsed configuration
_CACHED_CONFIG: Optional[Dict[str, Any]] = None
_OVERRIDE_PROFILE: Optional[str] = None


def load_config(force_reload: bool = False) -> Dict[str, Any]:
    """Load configuration from config.yaml with caching and safe fallback."""
    global _CACHED_CONFIG
    if _CACHED_CONFIG is not None and not force_reload:
        return _CACHED_CONFIG

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    _CACHED_CONFIG = loaded
                    return _CACHED_CONFIG
        except Exception as e:
            print(f"Warning: Failed to load config.yaml ({e}). Using embedded defaults.")

    _CACHED_CONFIG = copy.deepcopy(_DEFAULT_CONFIG)
    return _CACHED_CONFIG


def get_config() -> Dict[str, Any]:
    """Return the loaded global configuration dictionary."""
    return load_config()


def get_active_profile() -> str:
    """Return the current active profile name ('heuristic' or 'tuned')."""
    global _OVERRIDE_PROFILE
    if _OVERRIDE_PROFILE:
        return _OVERRIDE_PROFILE
    config = get_config()
    return config.get("active_profile", "heuristic")


def set_active_profile(profile_name: str) -> None:
    """
    Dynamically set the active profile for the current runtime session.
    Allowed values: 'heuristic', 'tuned'.
    """
    global _OVERRIDE_PROFILE
    normalized = profile_name.lower().strip()
    if normalized not in ["heuristic", "tuned"]:
        raise ValueError(f"Unknown profile: '{profile_name}'. Must be 'heuristic' or 'tuned'.")
    _OVERRIDE_PROFILE = normalized


def get_system_config(key: Optional[str] = None) -> Any:
    """
    Retrieve system & environment configuration settings.
    If key is None, returns the entire system dictionary.
    """
    config = get_config()
    system_cfg = config.get("system", _DEFAULT_CONFIG["system"])
    if key is None:
        return system_cfg
    return system_cfg.get(key, _DEFAULT_CONFIG["system"].get(key))


def get_params(section: Optional[str] = None, profile: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve parameters from the active profile (or specified profile).
    Optionally narrow down to a specific section (e.g. 'moneyball', 'xp_model', 'monte_carlo', 'optimizer').
    """
    config = get_config()
    prof_name = (profile or get_active_profile()).lower().strip()

    profile_data = config.get(prof_name)
    if not profile_data:
        # Fallback to heuristic or embedded default
        profile_data = config.get("heuristic", _DEFAULT_CONFIG.get("heuristic", {}))

    if section is None:
        return profile_data

    sec_data = profile_data.get(section)
    if sec_data is None and section == "montecarlo":
        sec_data = profile_data.get("monte_carlo")
    elif sec_data is None and section == "monte_carlo":
        sec_data = profile_data.get("montecarlo")

    if sec_data is not None:
        return sec_data

    # Check fallback
    fallback_sec = _DEFAULT_CONFIG.get("heuristic", {}).get(section, {})
    if not fallback_sec and section in ["montecarlo", "monte_carlo"]:
        fallback_sec = _DEFAULT_CONFIG.get("heuristic", {}).get("monte_carlo", {})
    return fallback_sec
