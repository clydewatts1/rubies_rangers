"""
---
type: TestSuite
title: "Premier League Injury Intelligence Scraper & Intel Engine Tests"
description: "Unit and integration tests for injury parsing, availability mapping, player resolution, disk caching, and Shane's Domain Intel sync."
tags: [test, pytest, injuries, availability, domain, intel]
sources: ["docs/design/des_021_premier_injuries_automated_intel.md", "clients/injury_client.py"]
generated:
  at: "2026-09-17T20:25:00Z"
  by: "agent:test-generation-python"
---
"""

import os
import json
import time
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

from analytics.domain_intel import (
    AvailabilityOption,
    PlayerOverride,
    ShaneIntelManager,
    TTLWindow,
)
from clients.injury_client import (
    InjuryClient,
    RawInjuryRecord,
    ProcessedInjuryIntel,
    map_injury_status_to_availability,
    normalize_text,
)


# ---------------------------------------------------------------------------
# 1. Availability Mapping Function Φ(Status, InjuryType)
# ---------------------------------------------------------------------------

def test_map_injury_status_confirmed_out():
    """OUT and SUS must strictly map to CONFIRMED_OUT_0 and p_fit=0.0."""
    opt, p_fit = map_injury_status_to_availability("OUT", "Hamstring")
    assert opt == AvailabilityOption.CONFIRMED_OUT_0
    assert p_fit == 0.0

    opt_sus, p_fit_sus = map_injury_status_to_availability("SUS", "Red Card")
    assert opt_sus == AvailabilityOption.CONFIRMED_OUT_0
    assert p_fit_sus == 0.0


def test_map_injury_status_gtd_severe():
    """GTD with severe soft-tissue / ligament issues maps to HEAVY_DOUBT_25."""
    opt, p_fit = map_injury_status_to_availability("GTD", "Hamstring Strain")
    assert opt == AvailabilityOption.HEAVY_DOUBT_25
    assert p_fit == 0.25

    opt_k, p_fit_k = map_injury_status_to_availability("GTD", "Knee Swelling")
    assert opt_k == AvailabilityOption.HEAVY_DOUBT_25
    assert p_fit_k == 0.25


def test_map_injury_status_gtd_minor_or_illness():
    """GTD with illness or minor knock maps to COIN_FLIP_50."""
    opt_ill, p_fit_ill = map_injury_status_to_availability("GTD", "Illness")
    assert opt_ill == AvailabilityOption.COIN_FLIP_50
    assert p_fit_ill == 0.50

    opt_undisc, p_fit_undisc = map_injury_status_to_availability("GTD", "Undisclosed")
    assert opt_undisc == AvailabilityOption.COIN_FLIP_50
    assert p_fit_undisc == 0.50


def test_map_injury_status_gtd_mild():
    """GTD with match fitness / fatigue maps to MILD_DOUBT_75."""
    opt, p_fit = map_injury_status_to_availability("GTD", "Lack of Match Fitness")
    assert opt == AvailabilityOption.MILD_DOUBT_75
    assert p_fit == 0.75


def test_map_injury_status_cleared():
    """Cleared or available maps to CLEARED_FIT_100."""
    opt, p_fit = map_injury_status_to_availability("FIT", "")
    assert opt == AvailabilityOption.CLEARED_FIT_100
    assert p_fit == 1.0


# ---------------------------------------------------------------------------
# 2. Text Normalization & Fuzzy Resolution
# ---------------------------------------------------------------------------

def test_normalize_text():
    """Accents, punctuation, and casing must be stripped cleanly."""
    assert normalize_text("Martin Ødegaard") == "martin odegaard"
    assert normalize_text("Marc Guéhi") == "marc guehi"
    assert normalize_text("João Pedro") == "joao pedro"


def test_player_resolution_mock_fpl():
    """Test resolution of player names to official FPL element records."""
    mock_fpl = MagicMock()
    mock_fpl.get_bootstrap_data.return_value = {
        "teams": [
            {"id": 1, "short_name": "ARS"},
            {"id": 11, "short_name": "MCI"},
        ],
        "elements": [
            {
                "id": 101,
                "first_name": "William",
                "second_name": "Saliba",
                "web_name": "Saliba",
                "team": 1,
                "status": "a",
                "chance_of_playing_next_round": 100,
                "news": "",
            },
            {
                "id": 202,
                "first_name": "Erling",
                "second_name": "Haaland",
                "web_name": "Haaland",
                "team": 11,
                "status": "a",
                "chance_of_playing_next_round": 100,
                "news": "",
            },
        ],
    }

    client = InjuryClient(fpl_client=mock_fpl)

    # 1. Exact full name
    p1 = client.resolve_player("William Saliba", "ARS")
    assert p1 is not None
    assert p1["id"] == 101
    assert p1["web_name"] == "Saliba"

    # 2. Team + Last Name match
    p2 = client.resolve_player("W. Saliba", "ARS")
    assert p2 is not None
    assert p2["id"] == 101

    # 3. Web name match
    p3 = client.resolve_player("Haaland", "MCI")
    assert p3 is not None
    assert p3["id"] == 202

    # 4. Unknown player
    p_none = client.resolve_player("Unknown Guy", "ARS")
    assert p_none is None


# ---------------------------------------------------------------------------
# 3. Dataclass Contracts
# ---------------------------------------------------------------------------

def test_dataclass_contracts_immutable():
    """Contracts must be frozen to prevent accidental state mutation."""
    raw = RawInjuryRecord(
        source_id="1",
        player_name="Saka",
        team_code="ARS",
        position="M",
        injury_type="Hamstring",
        raw_status="OUT",
        return_date_desc="Late Oct",
    )
    with pytest.raises(Exception):
        raw.raw_status = "GTD"

    intel = ProcessedInjuryIntel(
        fpl_element_id=1,
        web_name="Saka",
        full_name="Bukayo Saka",
        team_code="ARS",
        injury_type="Hamstring",
        raw_status="OUT",
        availability=AvailabilityOption.CONFIRMED_OUT_0,
        p_fit=0.0,
        expected_minutes=0.0,
        news_snippet="Hamstring (OUT)",
        as_of_timestamp=1000.0,
    )
    with pytest.raises(Exception):
        intel.p_fit = 0.5


# ---------------------------------------------------------------------------
# 4. Caching & Offline Fallback
# ---------------------------------------------------------------------------

def test_injury_client_caching(tmp_path):
    """Client reads from local disk cache if within TTL without calling network."""
    cache_file = str(tmp_path / "test_injury_cache.json")
    mock_payload = {
        "as_of_timestamp": time.time(),
        "count": 1,
        "injuries": [
            {
                "fpl_element_id": 55,
                "web_name": "Jota",
                "full_name": "Diogo Jota",
                "team_code": "LIV",
                "injury_type": "Rib",
                "raw_status": "OUT",
                "availability": "CONFIRMED_OUT_0",
                "p_fit": 0.0,
                "expected_minutes": 0.0,
                "news_snippet": "Rib (OUT)",
                "as_of_timestamp": time.time(),
            }
        ],
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(mock_payload, f)

    client = InjuryClient(cache_file=cache_file)
    with patch.object(client, "fetch_live_injuries_network") as mock_net:
        items = client.get_injury_intel(force_refresh=False)
        assert len(items) == 1
        assert items[0].web_name == "Jota"
        assert items[0].availability == AvailabilityOption.CONFIRMED_OUT_0
        mock_net.assert_not_called()


def test_injury_client_fallback_to_fpl_elements(tmp_path):
    """When network fails and cache is missing, fallback extracts FPL flagged elements."""
    cache_file = str(tmp_path / "empty_cache.json")
    mock_fpl = MagicMock()
    mock_fpl.get_bootstrap_data.return_value = {
        "teams": [{"id": 1, "short_name": "ARS"}],
        "elements": [
            {
                "id": 10,
                "first_name": "Gabriel",
                "second_name": "Jesus",
                "web_name": "Jesus",
                "team": 1,
                "status": "i",
                "chance_of_playing_next_round": 0,
                "news": "Groin injury",
            }
        ],
    }

    client = InjuryClient(fpl_client=mock_fpl, cache_file=cache_file)
    with patch.object(client, "fetch_live_injuries_network", return_value=[]):
        items = client.get_injury_intel(force_refresh=True)
        assert len(items) == 1
        assert items[0].web_name == "Jesus"
        assert items[0].availability == AvailabilityOption.CONFIRMED_OUT_0
        assert items[0].p_fit == 0.0


# ---------------------------------------------------------------------------
# 5. Integration with ShaneIntelManager
# ---------------------------------------------------------------------------

def test_sync_to_shane_intel(tmp_path):
    """Verify syncing injuries into ShaneIntelManager overrides with 1-GW TTL."""
    storage_yaml = str(tmp_path / "shane_intel.yaml")
    sm = ShaneIntelManager(storage_path=storage_yaml)

    mock_intel = [
        ProcessedInjuryIntel(
            fpl_element_id=1,
            web_name="Saka",
            full_name="Bukayo Saka",
            team_code="ARS",
            injury_type="Hamstring",
            raw_status="OUT",
            availability=AvailabilityOption.CONFIRMED_OUT_0,
            p_fit=0.0,
            expected_minutes=0.0,
            news_snippet="Hamstring (OUT)",
            as_of_timestamp=time.time(),
        ),
        ProcessedInjuryIntel(
            fpl_element_id=2,
            web_name="Haaland",
            full_name="Erling Haaland",
            team_code="MCI",
            injury_type="Knock",
            raw_status="GTD",
            availability=AvailabilityOption.COIN_FLIP_50,
            p_fit=0.5,
            expected_minutes=45.0,
            news_snippet="Knock (GTD)",
            as_of_timestamp=time.time(),
        ),
    ]

    mock_client = MagicMock(spec=InjuryClient)
    mock_client.get_injury_intel_by_web_name.return_value = {
        "saka": mock_intel[0],
        "haaland": mock_intel[1],
    }
    mock_client.sync_to_shane_intel.side_effect = lambda intel_manager, current_gw, auto_apply_out, target_web_names: (
        InjuryClient.sync_to_shane_intel(
            mock_client,
            intel_manager=intel_manager,
            current_gw=current_gw,
            auto_apply_out=auto_apply_out,
            target_web_names=target_web_names,
        )
    )

    count = sm.sync_injury_intel(current_gw=5, injury_client=mock_client)
    assert count == 2
    assert "saka" in sm.overrides
    assert "haaland" in sm.overrides

    saka_ov = sm.overrides["saka"]
    assert saka_ov.availability == AvailabilityOption.CONFIRMED_OUT_0
    assert saka_ov.valid_gameweek == 5
    assert saka_ov.ttl_window == TTLWindow.CURRENT_GW_ONLY
    assert saka_ov.expected_minutes == 0.0

    # Verify that apply_pre_stage1_overrides correctly sets status='u' and chance=0
    df = pd.DataFrame([{"web_name": "Saka", "status": "a", "chance_of_playing": 100, "moneyball_score": 12.5}])
    mod_df = sm.apply_pre_stage1_overrides(df, current_gw=5)
    assert mod_df.iloc[0]["status"] == "u"
    assert mod_df.iloc[0]["chance_of_playing"] == 0
    assert mod_df.iloc[0]["moneyball_score"] == 0.0
