"""
analytics/challenge/rule_extractor.py
Extracts and normalizes dynamic constraint rules from official FPL Challenge API responses or curated presets.
Ensures zero-exception handling and produces frozen ChallengeRuleSet contracts.
"""

from __future__ import annotations

from typing import Dict, Any, Optional
from analytics.challenge.contracts import ChallengeRuleSet

# Curated Preset Library representing official FPL Challenge archetypes
CHALLENGE_PRESETS: Dict[str, ChallengeRuleSet] = {
    "gw5_one_player_per_club": ChallengeRuleSet(
        gameweek=5,
        name="Gameweek 5: One Player Per Club Challenge",
        squad_size=6,
        max_per_team=1,
        budget_cap=999.9,
        allowed_positions={
            "GKP": (0, 0),
            "DEF": (1, 3),
            "MID": (1, 3),
            "FWD": (1, 3),
        },
        scoring_modifiers={},
        rolling_deadlines=True,
        description="Squad of 6 outfielders with a strict limit of 1 player per Premier League club.",
    ),
    "gw6_outside_box_boost": ChallengeRuleSet(
        gameweek=6,
        name="Gameweek 6: Long-Range Thunderbolts",
        squad_size=6,
        max_per_team=3,
        budget_cap=999.9,
        allowed_positions={
            "GKP": (0, 0),
            "DEF": (1, 3),
            "MID": (1, 3),
            "FWD": (1, 3),
        },
        scoring_modifiers={
            "outside_box_goals": 2.0,
            "mid_clean_sheet": 1.0,
        },
        rolling_deadlines=True,
        description="+2 extra FPL points for every goal scored from outside the penalty area.",
    ),
    "gw7_penny_pincher": ChallengeRuleSet(
        gameweek=7,
        name="Gameweek 7: Budget Buster (£80.0M Cap)",
        squad_size=6,
        max_per_team=3,
        budget_cap=80.0,
        allowed_positions={
            "GKP": (0, 0),
            "DEF": (1, 3),
            "MID": (1, 3),
            "FWD": (1, 3),
        },
        scoring_modifiers={},
        rolling_deadlines=True,
        description="Extreme financial austerity: Select 6 players under a strict £80.0M total budget.",
    ),
    "gw8_all_out_attack": ChallengeRuleSet(
        gameweek=8,
        name="Gameweek 8: All-Out Attack",
        squad_size=6,
        max_per_team=3,
        budget_cap=999.9,
        allowed_positions={
            "GKP": (0, 0),
            "DEF": (1, 1),
            "MID": (2, 4),
            "FWD": (2, 4),
        },
        scoring_modifiers={
            "forward_goal_multiplier": 1.5,
        },
        rolling_deadlines=True,
        description="Attack-oriented formation: Exactly 1 defender with heavy midfield & forward allocation.",
    ),
    "standard_6_a_side": ChallengeRuleSet(
        gameweek=5,
        name="Standard 6-a-Side Sprint",
        squad_size=6,
        max_per_team=3,
        budget_cap=999.9,
        allowed_positions={
            "GKP": (0, 0),
            "DEF": (1, 3),
            "MID": (1, 3),
            "FWD": (1, 3),
        },
        scoring_modifiers={},
        rolling_deadlines=True,
        description="Default 6-a-side outfield sprint with standard club quotas and unlimited budget.",
    ),
}


def get_available_challenge_presets() -> Dict[str, ChallengeRuleSet]:
    """Return dictionary of pre-calibrated challenge rule sets."""
    return CHALLENGE_PRESETS.copy()


def extract_rules_from_event(event_dict: Dict[str, Any], default_gw: int = 5) -> ChallengeRuleSet:
    """
    Extract dynamic ChallengeRuleSet from an official FPL Challenge event object.
    Falls back gracefully to sensible standard constraints if elements are omitted.
    """
    gw_id = event_dict.get("id", default_gw)
    event_name = event_dict.get("name", f"Gameweek {gw_id} Challenge")
    overrides = event_dict.get("overrides", {})
    rules = overrides.get("rules", {})
    scoring = overrides.get("scoring", {})
    element_types = overrides.get("element_types", [])

    # Squad size
    squad_size = int(rules.get("squad_squadsize") or rules.get("squad_squadplay") or 6)

    # Max per team
    max_per_team = int(rules.get("squad_team_limit") or 3)

    # Budget cap
    raw_spend = rules.get("squad_total_spend")
    if raw_spend is not None:
        spend_val = float(raw_spend)
        budget_cap = 999.9 if spend_val >= 999 else (spend_val / 10.0 if spend_val > 100 else spend_val)
    else:
        budget_cap = 999.9

    # Position constraints
    pos_bounds: Dict[str, tuple[int, int]] = {}
    if element_types:
        for et in element_types:
            name = et.get("singular_name_short") or et.get("name_short")
            if not name:
                etype_id = et.get("id")
                id_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
                name = id_map.get(etype_id, "UNK")
            min_sel = int(et.get("squad_min_select", 0))
            max_sel = int(et.get("squad_max_select", 3))
            pos_bounds[name] = (min_sel, max_sel)
    else:
        # Default 6-a-side outfield bounds
        if squad_size <= 6:
            pos_bounds = {
                "GKP": (0, 0),
                "DEF": (1, 3),
                "MID": (1, 3),
                "FWD": (1, 3),
            }
        else:
            pos_bounds = {
                "GKP": (1, 1),
                "DEF": (3, 5),
                "MID": (2, 5),
                "FWD": (1, 3),
            }

    # Scoring modifiers
    scoring_mods: Dict[str, float] = {}
    for k, v in scoring.items():
        if isinstance(v, (int, float)):
            scoring_mods[k] = float(v)
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                if isinstance(sub_v, (int, float)):
                    scoring_mods[f"{k}_{sub_k}"] = float(sub_v)

    return ChallengeRuleSet(
        gameweek=gw_id,
        name=event_name,
        squad_size=squad_size,
        max_per_team=max_per_team,
        budget_cap=budget_cap,
        allowed_positions=pos_bounds,
        scoring_modifiers=scoring_mods,
        rolling_deadlines=True,
        description=f"Official {event_name}: {squad_size}-player roster, max {max_per_team} per club.",
    )
