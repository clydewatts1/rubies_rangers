"""
Unit & Integration Test Suite for Strategic Framework Phase 1: Macro Fixture Radar & Wave Scanner.
Verifies wave detection algorithms, 190-pair rotation combinatorial sweeps, squad audits, and contracts.
"""

import pytest
import pandas as pd
from typing import Dict, List

from analytics.strategic.contracts import (
    ClubScheduleProfile,
    FixtureWaveAlert,
    DefensiveRotationPair,
    SquadWaveAudit,
)
from analytics.strategic.wave_scanner import (
    WaveScanner,
    scan_fixture_waves,
    find_optimal_defensive_rotation_pairs,
    audit_squad_waves,
)
from analytics.strategic.trajectory_engine import (
    build_club_schedule_profiles,
    build_strategic_squad_state,
)
from clients.fpl_client import FPLClient
from ui.tabs.tab_strategic_macro import render_tab_strategic_macro


class TestPhase1Contracts:
    """Test immutability, validation, and serialization of Phase 1 contracts."""

    def test_fixture_wave_alert_contract(self):
        alert = FixtureWaveAlert(
            club_short="FUL",
            club_name="Fulham",
            regime_type="GREEN_WAVE",
            start_gw=5,
            end_gw=9,
            duration_gws=5,
            avg_fdr=2.20,
            recommended_action="ACCUMULATE",
            inflection_gw=4,
            key_assets=("Robinson (£4.7m)", "Smith Rowe (£5.6m)"),
            rationale="Favorable 5-match run with FDR 2.20",
        )
        assert alert.club_short == "FUL"
        assert alert.regime_type == "GREEN_WAVE"
        assert alert.duration_gws == 5
        assert alert.inflection_gw == 4

        with pytest.raises(Exception):
            alert.avg_fdr = 2.10  # type: ignore

        d = alert.to_dict()
        assert isinstance(d, dict)
        reconstructed = FixtureWaveAlert.from_dict(d)
        assert reconstructed == alert

    def test_defensive_rotation_pair_contract(self):
        pair = DefensiveRotationPair(
            club_a_short="FUL",
            club_b_short="BRE",
            combined_home_ratio=0.875,
            combined_easy_ratio=0.75,
            combined_avg_fdr=2.25,
            combined_schedule=(
                (5, "FUL", "LEI", True, 2.0),
                (6, "BRE", "WHU", True, 2.0),
                (7, "FUL", "SOU", True, 2.0),
                (8, "BRE", "WOL", True, 2.0),
                (9, "FUL", "BOU", True, 2.0),
                (10, "BRE", "IPS", True, 2.0),
                (11, "FUL", "CRY", True, 2.0),
                (12, "BRE", "EVE", True, 2.0),
            ),
            budget_sample_defenders=(("Robinson", 4.7), ("Collins", 4.5)),
        )
        assert pair.club_a_short == "FUL"
        assert pair.combined_home_ratio == 0.875
        assert len(pair.combined_schedule) == 8

        with pytest.raises(Exception):
            pair.combined_avg_fdr = 2.00  # type: ignore

        d = pair.to_dict()
        reconstructed = DefensiveRotationPair.from_dict(d)
        assert reconstructed == pair

    def test_squad_wave_audit_contract(self):
        aud = SquadWaveAudit(
            element_id=101,
            web_name="Robinson",
            club_short="FUL",
            position_name="DEF",
            now_cost=4.7,
            current_regime="GREEN_WAVE",
            alert_label="🌊 Green Wave (GW5-9)",
            action_priority="HOLD_HARVEST",
            next_5_fdr=2.20,
        )
        assert aud.web_name == "Robinson"
        assert aud.action_priority == "HOLD_HARVEST"

        d = aud.to_dict()
        reconstructed = SquadWaveAudit.from_dict(d)
        assert reconstructed == aud


class TestWaveScannerEngine:
    """Test wave scanning algorithms and rotation pair sweeps."""

    def test_scan_fixture_waves_detects_regimes(self):
        client = FPLClient()
        club_profs = build_club_schedule_profiles(fpl_client=client, horizon=8)
        alerts = scan_fixture_waves(club_profiles=club_profs, horizon=8, fpl_client=client)

        assert isinstance(alerts, list)
        assert len(alerts) > 0

        # Check wave types
        for alert in alerts:
            assert alert.regime_type in ["GREEN_WAVE", "RED_CLIFF", "NEUTRAL"]
            assert alert.duration_gws >= 3
            assert alert.start_gw <= alert.end_gw
            assert alert.inflection_gw <= alert.start_gw
            assert 1.0 <= alert.avg_fdr <= 5.0

            if alert.regime_type == "GREEN_WAVE":
                assert alert.avg_fdr <= 2.80  # Under green threshold bounds
                assert alert.recommended_action in ["ACCUMULATE", "HOLD"]
            elif alert.regime_type == "RED_CLIFF":
                assert alert.avg_fdr >= 3.10  # Under red threshold bounds
                assert alert.recommended_action in ["LIQUIDATE", "AVOID"]

    def test_find_optimal_defensive_rotation_pairs_sweep(self):
        client = FPLClient()
        club_profs = build_club_schedule_profiles(fpl_client=client, horizon=8)
        pairs = find_optimal_defensive_rotation_pairs(
            club_profiles=club_profs,
            horizon=8,
            max_cost=4.5,
            top_k=5,
            fpl_client=client
        )

        assert len(pairs) == 5, f"Expected top 5 pairs, got {len(pairs)}"

        for p in pairs:
            assert isinstance(p, DefensiveRotationPair)
            assert p.club_a_short != p.club_b_short
            assert 0.0 <= p.combined_home_ratio <= 1.0
            assert 0.0 <= p.combined_easy_ratio <= 1.0
            assert 1.0 <= p.combined_avg_fdr <= 5.0
            assert len(p.combined_schedule) == 8

            # Ensure budget defenders attached
            assert len(p.budget_sample_defenders) >= 1
            for d_name, d_cost in p.budget_sample_defenders:
                assert d_cost <= 4.7, f"Defender {d_name} cost {d_cost} exceeded budget bound"

    def test_audit_squad_waves_coverage(self):
        client = FPLClient()
        sq_state = build_strategic_squad_state(fpl_client=client)
        squad_audits = audit_squad_waves(
            squad_player_ids=sq_state.squad_player_ids,
            horizon=8,
            fpl_client=client
        )

        assert len(squad_audits) == 15, f"Expected audit for all 15 players, got {len(squad_audits)}"

        for aud in squad_audits:
            assert isinstance(aud, SquadWaveAudit)
            assert aud.action_priority in ["URGENT_SELL", "WATCH_EXIT", "HOLD_HARVEST", "BUY_TARGET"]
            assert aud.current_regime in ["GREEN_WAVE", "RED_CLIFF", "NEUTRAL"]
            assert 1.0 <= aud.next_5_fdr <= 5.0

    def test_wave_scanner_facade_caching(self):
        scanner = WaveScanner(default_horizon=8)
        c_profs = scanner.get_club_profiles()
        assert len(c_profs) == 20

        waves1 = scanner.scan_waves()
        waves2 = scanner.scan_waves()
        assert waves1 is waves2  # Cached reference

        pairs1 = scanner.get_rotation_pairs()
        pairs2 = scanner.get_rotation_pairs()
        assert pairs1 is pairs2  # Cached reference

        squad_audits = scanner.audit_squad()
        assert len(squad_audits) == 15


class TestPhase1UIRendering:
    """Verify UI tab renderer is callable and cleanly integrates with Streamlit."""

    def test_ui_tab_callable(self):
        assert callable(render_tab_strategic_macro)
