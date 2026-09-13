import pytest
from analytics.chip_strategy import BackwardInductionSolver, ChipLiftCalculator, StochasticFixtureMatrix

def test_stochastic_fixture_matrix_historical_baselines():
    matrix = StochasticFixtureMatrix(cup_elo_model_enabled=True)
    
    p_blank, p_double = matrix.get_probabilities("GENERIC", 29)
    assert p_blank == 0.60
    assert p_double == 0.00
    
    p_blank, p_double = matrix.get_probabilities("GENERIC", 37)
    assert p_blank == 0.00
    assert p_double == 0.80

def test_backward_induction_solver_massive_dgw_value():
    solver = BackwardInductionSolver(discount_factor_gamma=1.0) # Disable discount for easy testing
    
    # TC future value checking from GW30 to GW38
    # It should identify GW37 as a Massive DGW and return its expected lift (22.0)
    future_tc_val = solver.get_best_future_option_value("TC", current_gw=30, expiry_gw=38)
    assert future_tc_val == 22.0
    
    # BB future value should be 26.0 for GW37
    future_bb_val = solver.get_best_future_option_value("BB", current_gw=30, expiry_gw=38)
    assert future_bb_val == 26.0

def test_evaluate_chip_decision_hold():
    solver = BackwardInductionSolver(discount_factor_gamma=1.0)
    
    # If our current TC lift is 15.0, but we have a Massive DGW coming up worth 22.0
    # It should recommend HOLD
    decision = solver.evaluate_chip_decision("TC", current_ev_lift=15.0, current_gw=30, expiry_gw=38)
    
    assert decision["action"] == "HOLD"
    assert decision["opportunity_cost"] == 7.0

def test_evaluate_chip_decision_play():
    solver = BackwardInductionSolver(discount_factor_gamma=1.0)
    
    # If our current TC lift is 25.0, and the best future is 22.0
    # It should recommend PLAY
    decision = solver.evaluate_chip_decision("TC", current_ev_lift=25.0, current_gw=30, expiry_gw=38)
    
    assert decision["action"] == "PLAY"
    assert decision["opportunity_cost"] == 0.0

def test_chip_lift_calculator():
    expected_points = {1: 8.5, 2: 3.0, 3: 4.0, 4: 2.0}
    
    # TC lift is exactly the captain's points added once more
    tc_lift = ChipLiftCalculator.calculate_tc_lift(expected_points, captain_id=1)
    assert tc_lift == 8.5
    
    # BB lift is the sum of bench players
    bb_lift = ChipLiftCalculator.calculate_bb_lift(expected_points, bench_ids=[2, 3, 4])
    assert bb_lift == 9.0
