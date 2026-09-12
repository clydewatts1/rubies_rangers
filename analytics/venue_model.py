import math
from typing import Dict, Any, List

def get_club_tier(club_short: str) -> str:
    """
    Classifies a Premier League club into one of three strength tiers:
    'elite' (Top 1-4), 'mid_table' (5-14), 'relegation' (15-20).
    This determines the dampening factor (beta) applied to their home/away multiplier.
    """
    club = club_short.upper()
    elite_clubs = {"MCI", "ARS", "LIV", "CHE", "AVL"}
    relegation_clubs = {"IPS", "SOU", "LEI", "EVE", "WOL", "SHU", "BUR", "LUT", "NFO"}
    
    if club in elite_clubs:
        return "elite"
    elif club in relegation_clubs:
        return "relegation"
    return "mid_table"

def compute_effective_venue_multiplier(
    player_row: Dict[str, Any], 
    venue_cfg: Dict[str, Any],
    fixture_str: str
) -> float:
    """
    Computes the effective venue multiplier (V_effective) for a player based on their upcoming fixture(s).
    Follows the FPL Moneyball stochastic venue logic:
    - If venue.enabled is False, strictly returns 1.00 (Identity fallback)
    - Separates GKP (save volume hedge) from DEF (clean sheet collapse).
    - Applies tier damping based on club strength.
    - Handles Double/Blank Gameweeks with expectation-weighted summation.
    """
    # 1. Feature Flag: Identity Fallback
    if not venue_cfg.get("enabled", True):
        return 1.00
        
    if not fixture_str or fixture_str.strip() == "" or fixture_str.upper() == "BLANK":
        return 0.0 # Blank Gameweek (0 matches)
        
    fixtures = [f.strip() for f in fixture_str.split(",")]
    if len(fixtures) == 0:
        return 0.0
        
    pos = player_row.get("position_name", "MID")
    club = player_row.get("club_short", "UNK")
    club_tier = get_club_tier(club)
    
    tier_damping = venue_cfg.get("tier_damping", {})
    # Defaults from brainstorm Option 1
    beta = tier_damping.get(club_tier, 1.0)
    if club_tier == "elite":
        beta = tier_damping.get("elite", 0.70)
    elif club_tier == "mid_table":
        beta = tier_damping.get("mid_table", 1.30)
    elif club_tier == "relegation":
        beta = tier_damping.get("relegation", 1.15)
        
    def_home_mult = venue_cfg.get("def_home_mult", 1.18)
    gkp_home_mult = venue_cfg.get("gkp_home_mult", 1.08)
    att_home_mult = venue_cfg.get("att_home_mult", 1.08)
    away_mult = venue_cfg.get("away_mult", 0.92)
    gkp_away_save_boost = venue_cfg.get("gkp_away_save_boost", 1.20)
    
    total_effective_v = 0.0
    weight_per_match = 1.0 
    
    for fx in fixtures:
        is_home = "(H)" in fx.upper()
        
        # Determine Base Multiplier
        v_base = 1.0
        if is_home:
            if pos == "DEF":
                v_base = def_home_mult
            elif pos == "GKP":
                v_base = gkp_home_mult
            else:
                v_base = att_home_mult
        else:
            if pos == "GKP":
                # GKP away has base away penalty BUT a save volume counter-cyclical boost
                v_base = away_mult * gkp_away_save_boost
            else:
                v_base = away_mult
                
        # Modulate by tier dampening
        v_effective = 1.0 + ((v_base - 1.0) * beta)
        total_effective_v += (v_effective * weight_per_match)
        
    return round(total_effective_v, 3)
