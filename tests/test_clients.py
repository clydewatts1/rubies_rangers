"""
Unit tests for clients package: FPLClient and TacticalClient.
Validates both direct package imports and root backward-compatibility shims.
"""

import pytest
import pandas as pd
from clients import FPLClient, TacticalClient, normalize_name
import fpl_client as fpl_shim
import tactical_client as tac_shim


def test_package_exports():
    """Verify package public API exports."""
    assert FPLClient is fpl_shim.FPLClient
    assert TacticalClient is tac_shim.TacticalClient
    assert normalize_name is tac_shim.normalize_name


def test_normalize_name():
    """Verify player name normalization handles accents and aliases."""
    assert normalize_name("Martin Odegaard") == "ødegaard"
    assert normalize_name("Marc Guéhi") == "guéhi"
    assert normalize_name("João Pedro") == "joão pedro"
    assert normalize_name("Rayan Cherki") == "mathis cherki"
    assert normalize_name("") == ""


def test_fpl_client_bootstrap():
    """Verify FPLClient loads players DataFrame with expected columns."""
    client = FPLClient()
    df = client.get_players_df()
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "web_name" in df.columns
    assert "now_cost" in df.columns
    assert "fdr_moneyball_score" in df.columns
    assert "form" in df.columns


def test_tactical_client_init():
    """Verify TacticalClient initializes with proper cache directories."""
    client = TacticalClient()
    assert client.cache_ttl > 0
    assert hasattr(client, "get_squad_tactical_df")
