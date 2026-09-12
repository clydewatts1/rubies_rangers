import pytest
import numpy as np
from analytics.venue_model import compute_effective_venue_multiplier, get_club_tier
from analytics.montecarlo import MonteCarloEngine

def test_fallback_logic_disabled():
    """Test mathematical identity fallback when venue.enabled = False"""
    venue_cfg = {"enabled": False, "def_home_mult": 1.18}
    player = {"position_name": "DEF", "club_short": "ARS"}
    
    mult = compute_effective_venue_multiplier(player, venue_cfg, "LIV (H)")
    assert mult == 1.00

def test_fallback_logic_blank_gameweek():
    """Test fallback when Gameweek is blank"""
    venue_cfg = {"enabled": True, "def_home_mult": 1.18}
    player = {"position_name": "DEF", "club_short": "ARS"}
    
    mult = compute_effective_venue_multiplier(player, venue_cfg, "BLANK")
    assert mult == 0.00
    
    mult = compute_effective_venue_multiplier(player, venue_cfg, "")
    assert mult == 0.00

def test_elite_tier_dampening():
    """Test that an elite team's home advantage is dampened (beta=0.7)"""
    venue_cfg = {
        "enabled": True,
        "def_home_mult": 1.18,
        "tier_damping": {"elite": 0.70}
    }
    # Elite club = ARS
    player = {"position_name": "DEF", "club_short": "ARS"}
    
    # Base V = 1.18. Effective V = 1.0 + (0.18 * 0.70) = 1.0 + 0.126 = 1.126 => 1.126
    mult = compute_effective_venue_multiplier(player, venue_cfg, "EVE (H)")
    assert mult == 1.126

def test_mid_table_dampening():
    """Test that a mid-table team's home advantage is amplified (beta=1.30)"""
    venue_cfg = {
        "enabled": True,
        "def_home_mult": 1.18,
        "tier_damping": {"mid_table": 1.30}
    }
    # Mid-table club = FUL
    player = {"position_name": "DEF", "club_short": "FUL"}
    
    # Base V = 1.18. Effective V = 1.0 + (0.18 * 1.30) = 1.0 + 0.234 = 1.234 => 1.234
    mult = compute_effective_venue_multiplier(player, venue_cfg, "EVE (H)")
    assert mult == 1.234

def test_gkp_away_save_boost():
    """Test that GKP away has a save counter-cyclical boost"""
    venue_cfg = {
        "enabled": True,
        "away_mult": 0.92,
        "gkp_away_save_boost": 1.20,
        "tier_damping": {"mid_table": 1.0}
    }
    player = {"position_name": "GKP", "club_short": "FUL"}
    
    # Base V = 0.92 * 1.20 = 1.104.
    # Effective V = 1.0 + (0.104 * 1.0) = 1.104
    mult = compute_effective_venue_multiplier(player, venue_cfg, "EVE (A)")
    assert mult == 1.104

def test_double_gameweek():
    """Test that DGW sums the effective multipliers"""
    venue_cfg = {
        "enabled": True,
        "def_home_mult": 1.18,
        "away_mult": 0.92,
        "tier_damping": {"mid_table": 1.0}
    }
    player = {"position_name": "DEF", "club_short": "FUL"}
    
    # Match 1: Home (1.18), Match 2: Away (0.92)
    # Total = 1.18 + 0.92 = 2.10
    mult = compute_effective_venue_multiplier(player, venue_cfg, "EVE (H), LIV (A)")
    assert mult == 2.10

def test_monte_carlo_blank_gameweek_zeros():
    """Test that Monte Carlo simulation cleanly zeroes out points for a blank gameweek"""
    mc = MonteCarloEngine()
    player = {
        "id": 999,
        "web_name": "GhostPlayer",
        "position_name": "DEF",
        "club_short": "TOT",
        "status": "a",
        "chance_of_playing": 100
    }
    # Override team odds to simulate blank
    mc.team_odds["TOT"] = {
        "exp_goals_scored": 0.0,
        "exp_goals_conceded": 0.0,
        "clean_sheet_prob": 0.0,
        "fixture_str": "BLANK"
    }
    sim_pts, sim_mins = mc.simulate_player(player, n_sims=500)
    assert np.all(sim_pts == 0.0)
    assert np.all(sim_mins == 0.0)
