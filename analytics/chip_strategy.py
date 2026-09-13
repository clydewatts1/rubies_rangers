"""
chip_strategy.py

Dynamic Programming and Real Options pricing engine for Long-Term FPL Chip Allocation.
Implements Macro-State Abstraction and Stochastic Fixture Matrices.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional
import math

@dataclass
class MacroStateValue:
    """Represents the Option Continuation Value of a macro-state."""
    name: str
    expected_tc_lift: float
    expected_bb_lift: float
    expected_fh_lift: float
    expected_wc_lift: float

class StochasticFixtureMatrix:
    """
    Probabilistic model assigning P(Blank) and P(Double) to future gameweeks.
    For this baseline implementation, we use static historical probabilities 
    for known cup clash gameweeks (e.g. GW29, GW32, GW34, GW37).
    """
    def __init__(self, cup_elo_model_enabled: bool = True, variance_buffer: float = 0.15):
        self.cup_elo_model_enabled = cup_elo_model_enabled
        self.variance_buffer = variance_buffer
        
        # Historical baseline probabilities for cup disruptions
        # Format: gameweek -> (p_blank, p_double)
        self._historical_baselines = {
            29: (0.60, 0.00), # FA Cup QF Blank
            34: (0.20, 0.40), # FA Cup SF Blank / Catch-up Double
            37: (0.00, 0.80), # Major Catch-up Double
        }

    def get_probabilities(self, team: str, gameweek: int) -> tuple[float, float]:
        """Returns (p_blank, p_double) for a team in a given gameweek."""
        if not self.cup_elo_model_enabled:
            return (0.0, 0.0) # Assume standard schedule if disabled
            
        base_p_blank, base_p_double = self._historical_baselines.get(gameweek, (0.0, 0.0))
        # Add basic variance buffer logic here later if specific team ELOs are tracked.
        return (base_p_blank, base_p_double)

class ChipLiftCalculator:
    """Pure functions to calculate immediate Expected Value (EV) lift of chips."""
    
    @staticmethod
    def calculate_tc_lift(expected_points: Dict[int, float], captain_id: int) -> float:
        """Returns the lift of a Triple Captain (which is 1x additional captain points)."""
        return expected_points.get(captain_id, 0.0)
        
    @staticmethod
    def calculate_bb_lift(expected_points: Dict[int, float], bench_ids: List[int]) -> float:
        """Returns the lift of a Bench Boost (sum of bench points)."""
        return sum(expected_points.get(pid, 0.0) for pid in bench_ids)
        
    @staticmethod
    def calculate_fh_lift(optimal_fh_ev: float, current_squad_ev: float, hits_saved: int) -> float:
        """Returns lift of Free Hit: New Squad EV - Current Squad EV + Hits Saved."""
        return (optimal_fh_ev - current_squad_ev) + (hits_saved * 4.0)

    @staticmethod
    def calculate_wc_structural_lift(
        projected_rebuilt_ev: float, 
        projected_current_ev: float, 
        hits_saved: int, 
        discount_gamma: float = 0.92
    ) -> float:
        """
        Returns the structural lift of a Wildcard over a horizon.
        Simplified here as a pre-discounted aggregate delta.
        """
        # We apply gamma to discount the distant future EV delta.
        return (projected_rebuilt_ev - projected_current_ev) * discount_gamma + (hits_saved * 4.0)

class BackwardInductionSolver:
    """
    Evaluates current micro-state against future macro-states to determine Opportunity Cost.
    """
    def __init__(self, discount_factor_gamma: float = 0.92):
        self.gamma = discount_factor_gamma
        
        # Define the Macro-States and their historical Option Values
        self.macro_states = {
            "Standard": MacroStateValue("Standard", 8.0, 8.0, 10.0, 15.0),
            "Mini DGW": MacroStateValue("Mini DGW", 15.0, 16.0, 18.0, 22.0),
            "Massive DGW": MacroStateValue("Massive DGW", 22.0, 26.0, 24.0, 35.0),
            "Massive BGW": MacroStateValue("Massive BGW", 5.0, 2.0, 32.0, 10.0),
        }

    def get_best_future_option_value(self, chip: str, current_gw: int, expiry_gw: int) -> float:
        """
        Calculates the maximum expected continuation value for a chip.
        Assumes a massive DGW typically happens around GW37, and a massive BGW around GW29.
        """
        if current_gw > expiry_gw:
            return 0.0

        max_val = 0.0
        # Iterate future gameweeks to expiry
        for gw in range(current_gw + 1, expiry_gw + 1):
            # Determine expected macro-state of future gameweek
            macro = "Standard"
            if gw in [34]:
                macro = "Mini DGW"
            elif gw in [37]:
                macro = "Massive DGW"
            elif gw in [29]:
                macro = "Massive BGW"
                
            state_val = self.macro_states[macro]
            
            # Get specific chip lift
            lift = 0.0
            if chip == "TC": lift = state_val.expected_tc_lift
            elif chip == "BB": lift = state_val.expected_bb_lift
            elif chip == "FH": lift = state_val.expected_fh_lift
            elif chip == "WC": lift = state_val.expected_wc_lift
            
            # Apply discount factor for temporal distance
            discounted_lift = lift * math.pow(self.gamma, (gw - current_gw))
            
            if discounted_lift > max_val:
                max_val = discounted_lift
                
        return max_val

    def evaluate_chip_decision(self, chip: str, current_ev_lift: float, current_gw: int, expiry_gw: int) -> dict:
        """
        Returns the strategic recommendation (HOLD or PLAY) by comparing immediate lift
        to the best discounted future option value.
        """
        future_val = self.get_best_future_option_value(chip, current_gw, expiry_gw)
        
        action = "PLAY" if current_ev_lift > future_val else "HOLD"
        opportunity_cost = future_val - current_ev_lift if action == "HOLD" else 0.0
        
        return {
            "chip": chip,
            "action": action,
            "current_lift": current_ev_lift,
            "future_value": future_val,
            "opportunity_cost": opportunity_cost
        }
