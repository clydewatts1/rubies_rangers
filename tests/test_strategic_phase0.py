"""
Unit & Integration Test Suite for Strategic Framework Phase 0.
Verifies contracts, trajectory tensors, config dual-profiles, tuner search spaces, and execution speed.
"""

import time
import pytest
import numpy as np

from config_manager import get_params, set_active_profile, get_active_profile, load_config
from tuner.search_space import get_param_ranges, sample_config_params, reconstruct_params_from_dict
from analytics.strategic.contracts import (
    PlayerTrajectoryProfile,
    ClubScheduleProfile,
    StrategicSquadState,
)
from analytics.strategic.trajectory_engine import (
    TrajectoryEngine,
    build_club_schedule_profiles,
    build_player_trajectory_profiles,
    build_strategic_squad_state,
)
from clients.fpl_client import FPLClient


class TestStrategicContracts:
    """Test frozen domain contracts and immutable serialization."""

    def test_player_trajectory_profile_immutability(self):
        prof = PlayerTrajectoryProfile(
            element_id=300,
            web_name="Haaland",
            full_name="Erling Haaland",
            club_short="MCI",
            position_name="FWD",
            now_cost=15.2,
            xp_trajectory=(8.4, 7.8, 9.1, 5.2, 8.6, 7.9, 6.4, 8.1),
            fdr_trajectory=(2.0, 3.0, 2.0, 4.0, 2.0, 3.0, 4.0, 2.0),
            opponents=("FUL", "BRE", "IPS", "ARS", "NEW", "SOU", "BOU", "BHA"),
            is_home=(True, True, True, False, False, True, False, False),
            minutes_expectation=85.0,
            price_change_momentum=45.0,
            chance_of_playing=100.0,
            status="a",
        )
        assert prof.element_id == 300
        assert prof.web_name == "Haaland"
        assert len(prof.xp_trajectory) == 8
        assert prof.xp_trajectory[0] == 8.4

        # Verify frozen immutability
        with pytest.raises(Exception):
            prof.now_cost = 15.3  # type: ignore

        # Verify serialization roundtrip
        d = prof.to_dict()
        assert isinstance(d, dict)
        reconstructed = PlayerTrajectoryProfile.from_dict(d)
        assert reconstructed == prof

    def test_club_schedule_profile_immutability(self):
        c_prof = ClubScheduleProfile(
            club_short="ARS",
            club_name="Arsenal",
            fdr_vector=(2.0, 4.0, 3.0, 2.0, 2.0, 3.0, 4.0, 2.0),
            opponents=("SOU", "LIV", "NEW", "IPS", "NFO", "WHU", "CHE", "FUL"),
            is_home=(True, True, False, True, True, False, False, True),
            clean_sheet_probs=(0.55, 0.28, 0.42, 0.60, 0.58, 0.40, 0.30, 0.52),
            expected_goals_scored=(2.10, 1.45, 1.60, 2.30, 2.05, 1.70, 1.35, 1.90),
            expected_goals_conceded=(0.60, 1.25, 0.85, 0.50, 0.55, 0.90, 1.20, 0.65),
        )
        assert c_prof.club_short == "ARS"
        assert len(c_prof.fdr_vector) == 8
        assert 0.0 <= c_prof.clean_sheet_probs[0] <= 1.0

        with pytest.raises(Exception):
            c_prof.club_name = "The Arsenal"  # type: ignore

        d = c_prof.to_dict()
        reconstructed = ClubScheduleProfile.from_dict(d)
        assert reconstructed == c_prof

    def test_strategic_squad_state_immutability_and_bounds(self):
        state = StrategicSquadState(
            squad_player_ids=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
            squad_player_names=("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11", "P12", "P13", "P14", "P15"),
            bank_balance=3.5,
            free_transfers_available=3,
            chips_available=("wildcard", "freehit"),
            team_value=101.5,
            gameweek=4,
        )
        assert len(state.squad_player_ids) == 15
        assert 1 <= state.free_transfers_available <= 5
        assert state.bank_balance == 3.5

        # Test FT bounds clipping in from_dict
        d = state.to_dict()
        d["free_transfers_available"] = 8  # Exceeds max 5
        clipped_state = StrategicSquadState.from_dict(d)
        assert clipped_state.free_transfers_available == 5


class TestStrategicConfigurationAndTuner:
    """Test configuration dual-profile and Optuna search space registration."""

    def test_config_dual_profile_loading(self):
        # Force reload config
        load_config(force_reload=True)

        # Test heuristic profile
        h_strat = get_params("strategic", profile="heuristic")
        assert "horizon" in h_strat
        assert "venue" in h_strat
        assert "defense" in h_strat
        assert "waves" in h_strat
        assert "market" in h_strat
        assert "balance_sheet" in h_strat

        assert h_strat["horizon"]["lookahead_gws"] == 8
        assert h_strat["horizon"]["discount_gamma"] == 0.92
        assert h_strat["venue"]["nu_att_home"] == 1.15
        assert h_strat["venue"]["nu_def_home"] == 0.85
        assert h_strat["defense"]["kappa_cs_scale"] == 1.00
        assert h_strat["waves"]["threshold_green"] == 2.50
        assert h_strat["waves"]["threshold_red"] == 3.40
        assert h_strat["market"]["momentum_weight"] == 0.20
        assert h_strat["balance_sheet"]["ft_option_mult"] == 1.50

        # Test tuned profile
        t_strat = get_params("strategic", profile="tuned")
        assert "horizon" in t_strat
        assert "venue" in t_strat

    def test_tuner_param_ranges_contains_all_10_strategic_params(self):
        ranges = get_param_ranges()
        expected_keys = [
            "strategic.horizon.discount_gamma",
            "strategic.venue.nu_att_home",
            "strategic.venue.nu_att_away",
            "strategic.venue.nu_def_home",
            "strategic.venue.nu_def_away",
            "strategic.defense.kappa_cs_scale",
            "strategic.waves.threshold_green",
            "strategic.waves.threshold_red",
            "strategic.market.momentum_weight",
            "strategic.balance_sheet.ft_option_mult",
        ]
        for k in expected_keys:
            assert k in ranges, f"Missing strategic tuner parameter: {k}"
            low, high, step = ranges[k]
            assert low < high
            assert step > 0

    def test_reconstruct_params_from_dict_populates_strategic(self):
        mock_params = {
            "strat_discount_gamma": 0.94,
            "strat_nu_att_home": 1.20,
            "strat_nu_att_away": 0.85,
            "strat_nu_def_home": 0.80,
            "strat_nu_def_away": 1.22,
            "strat_kappa_cs_scale": 1.05,
            "strat_threshold_green": 2.45,
            "strat_threshold_red": 3.50,
            "strat_momentum_weight": 0.25,
            "strat_ft_option_mult": 1.80,
        }
        reconstructed = reconstruct_params_from_dict(mock_params)
        assert "strategic" in reconstructed
        s = reconstructed["strategic"]
        assert s["horizon"]["discount_gamma"] == 0.94
        assert s["venue"]["nu_att_home"] == 1.20
        assert s["venue"]["nu_att_away"] == 0.85
        assert s["venue"]["nu_def_home"] == 0.80
        assert s["venue"]["nu_def_away"] == 1.22
        assert s["defense"]["kappa_cs_scale"] == 1.05
        assert s["waves"]["threshold_green"] == 2.45
        assert s["waves"]["threshold_red"] == 3.50
        assert s["market"]["momentum_weight"] == 0.25
        assert s["balance_sheet"]["ft_option_mult"] == 1.80


class TestTrajectoryEngineAndTensors:
    """Test multi-horizon trajectory generation, tensor dimensions, and bounds."""

    def test_club_schedule_profiles_generation(self):
        client = FPLClient()
        profiles = build_club_schedule_profiles(fpl_client=client, horizon=8)
        assert len(profiles) == 20, f"Expected 20 PL clubs, got {len(profiles)}"

        for club_short, prof in profiles.items():
            assert isinstance(prof, ClubScheduleProfile)
            assert len(prof.fdr_vector) == 8
            assert len(prof.opponents) == 8
            assert len(prof.is_home) == 8
            assert len(prof.clean_sheet_probs) == 8
            assert len(prof.expected_goals_scored) == 8
            assert len(prof.expected_goals_conceded) == 8

            for cs in prof.clean_sheet_probs:
                assert 0.0 <= cs <= 1.0, f"Invalid clean sheet prob {cs} for {club_short}"
            for fdr in prof.fdr_vector:
                assert 1.0 <= fdr <= 5.0, f"Invalid FDR {fdr} for {club_short}"

    def test_player_trajectory_profiles_and_xp_bounds(self):
        client = FPLClient()
        club_profs = build_club_schedule_profiles(fpl_client=client, horizon=8)
        player_profs = build_player_trajectory_profiles(
            fpl_client=client,
            club_profiles=club_profs,
            horizon=8
        )

        assert len(player_profs) >= 500, f"Expected at least 500 players, got {len(player_profs)}"

        for p_id, prof in player_profs.items():
            assert isinstance(prof, PlayerTrajectoryProfile)
            assert len(prof.xp_trajectory) == 8
            assert len(prof.fdr_trajectory) == 8
            assert len(prof.opponents) == 8
            assert len(prof.is_home) == 8

            # Physical mathematical bounds
            for xp in prof.xp_trajectory:
                assert 0.0 <= xp <= 25.0, f"xP out of bounds: {xp} for player {prof.web_name}"

            assert 0.0 <= prof.minutes_expectation <= 90.0
            assert -100.0 <= prof.price_change_momentum <= 100.0

    def test_trajectory_engine_facade_and_matrix_extraction(self):
        engine = TrajectoryEngine(default_horizon=8)
        c_profs = engine.get_club_profiles()
        p_profs = engine.get_player_profiles()
        assert len(c_profs) == 20
        assert len(p_profs) >= 500

        # Test matrix extraction
        sample_pids = list(p_profs.keys())[:15]
        mat = engine.get_xp_matrix(sample_pids, horizon=8)
        assert isinstance(mat, np.ndarray)
        assert mat.shape == (15, 8)
        assert np.all(mat >= 0.0)
        assert np.all(mat <= 25.0)

    def test_strategic_squad_state_resolution(self):
        state = build_strategic_squad_state()
        assert isinstance(state, StrategicSquadState)
        assert len(state.squad_player_ids) == 15
        assert len(state.squad_player_names) == 15
        assert state.bank_balance >= 0.0
        assert 1 <= state.free_transfers_available <= 5
        assert state.team_value >= 80.0
        assert state.gameweek >= 1

    def test_performance_benchmark_under_50ms(self):
        """Verify that multi-horizon tensor computation across all players takes < 50ms."""
        client = FPLClient()
        club_profs = build_club_schedule_profiles(fpl_client=client, horizon=8)

        # Warm up JIT / cache
        _ = build_player_trajectory_profiles(fpl_client=client, club_profiles=club_profs, horizon=8)

        # Timed execution
        start_time = time.perf_counter()
        _ = build_player_trajectory_profiles(fpl_client=client, club_profiles=club_profs, horizon=8)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        print(f"\n[BENCHMARK] Multi-horizon (650+ players x 8 GWs) tensor computed in {duration_ms:.2f} ms")
        assert duration_ms < 50.0, f"Trajectory computation took {duration_ms:.2f}ms, exceeding 50ms SLA"
