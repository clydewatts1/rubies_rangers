"""
Shane's Domain Intel Desk & Ephemeral Human Overrides Engine
Provides a qualitative-to-quantitative bridge with strict non-impacting defaults
and Gameweek Time-to-Live (TTL) temporal decay governance.
"""

from __future__ import annotations
import os
import copy
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import pandas as pd
import yaml

from config_manager import get_system_config


class AvailabilityOption(str, Enum):
    DEFAULT_OFFICIAL = "DEFAULT_OFFICIAL"   # Identity: passthrough official FPL status
    CONFIRMED_OUT_0 = "CONFIRMED_OUT_0"     # 0% cop, status='u' (MILP hard exclusion)
    HEAVY_DOUBT_25 = "HEAVY_DOUBT_25"       # 25% cop, p_fit=0.25
    COIN_FLIP_50 = "COIN_FLIP_50"           # 50% cop, p_fit=0.50
    MILD_DOUBT_75 = "MILD_DOUBT_75"         # 75% cop, p_fit=0.75
    CLEARED_FIT_100 = "CLEARED_FIT_100"     # 100% cop, status='a'


class EligibilityOption(str, Enum):
    DEFAULT_ELIGIBLE = "DEFAULT_ELIGIBLE"   # Identity: passthrough
    TRANSFERRED_OUT = "TRANSFERRED_OUT"     # Excluded from squad selection
    INELIGIBLE_LOAN = "INELIGIBLE_LOAN"     # Ineligible vs parent club
    INTERNAL_SANCTION = "INTERNAL_SANCTION" # Locker room ban


class TacticalOption(str, Enum):
    DEFAULT_MINUTES = "DEFAULT_MINUTES"     # Identity: standard baseline
    ROTATION_HOOK_60 = "ROTATION_HOOK_60"   # Midweek congestion risk: 60 mins, std=15.0
    FULL_90_LOCK = "FULL_90_LOCK"           # Nailed starter: 90 mins, std=2.0
    OUT_OF_POSITION_ADV = "OUT_OF_POSITION" # Out-of-position attacking boost (1.25x xGI)


class TTLWindow(str, Enum):
    CURRENT_GW_ONLY = "CURRENT_GW_ONLY"     # Strictly expires after current Gameweek
    NEXT_TWO_GWS = "NEXT_TWO_GWS"           # Valid for current GW + next GW
    UNTIL_CLEARED = "UNTIL_CLEARED"         # Persists until explicitly reset


@dataclass
class PlayerOverride:
    """Individual player domain intel record."""
    web_name: str
    scope: str = "squad"                    # "squad" or "shortlist"
    valid_gameweek: int = 1
    ttl_window: TTLWindow = TTLWindow.CURRENT_GW_ONLY
    availability: AvailabilityOption = AvailabilityOption.DEFAULT_OFFICIAL
    eligibility: EligibilityOption = EligibilityOption.DEFAULT_ELIGIBLE
    tactical_risk: TacticalOption = TacticalOption.DEFAULT_MINUTES
    expected_minutes: float = 85.0          # Identity default
    eye_test_multiplier: float = 1.00       # Identity default (1.00x = 0% distortion)
    reason_category: str = "Tactical Assessment"
    active: bool = True

    def is_valid_for_gw(self, current_gw: int) -> bool:
        """Enforces temporal decay and TTL expiration."""
        if not self.active:
            return False
        if self.ttl_window == TTLWindow.UNTIL_CLEARED:
            return True
        elif self.ttl_window == TTLWindow.NEXT_TWO_GWS:
            return self.valid_gameweek <= current_gw <= (self.valid_gameweek + 1)
        else:  # CURRENT_GW_ONLY
            return self.valid_gameweek == current_gw

    def has_active_deviation(self) -> bool:
        """Returns True if the override deviates from mathematical identity defaults."""
        return (
            self.availability != AvailabilityOption.DEFAULT_OFFICIAL
            or self.eligibility != EligibilityOption.DEFAULT_ELIGIBLE
            or self.tactical_risk != TacticalOption.DEFAULT_MINUTES
            or abs(self.expected_minutes - 85.0) > 1e-4
            or abs(self.eye_test_multiplier - 1.00) > 1e-4
        )


class ShaneIntelManager:
    """
    Manages loading, persisting, validating, and applying Shane's domain metrics.
    Guarantees the Mathematical Identity Invariant: unedited or expired overrides have 0 delta.
    """
    DEFAULT_STORAGE_PATH = os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        "data", "shane_intel.yaml"
    )

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or self.DEFAULT_STORAGE_PATH
        self.overrides: Dict[str, PlayerOverride] = {}
        self.load_overrides()

    def load_overrides(self) -> Dict[str, PlayerOverride]:
        """Load overrides from disk safely with fallback to empty dict."""
        self.overrides = {}
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                raw_list = data.get("shane_metrics", {}).get("overrides", [])
                for item in raw_list:
                    ov = PlayerOverride(
                        web_name=item["web_name"],
                        scope=item.get("scope", "squad"),
                        valid_gameweek=int(item.get("valid_gameweek", 1)),
                        ttl_window=TTLWindow(item.get("ttl_window", TTLWindow.CURRENT_GW_ONLY.value)),
                        availability=AvailabilityOption(item.get("availability", AvailabilityOption.DEFAULT_OFFICIAL.value)),
                        eligibility=EligibilityOption(item.get("eligibility", EligibilityOption.DEFAULT_ELIGIBLE.value)),
                        tactical_risk=TacticalOption(item.get("tactical_risk", TacticalOption.DEFAULT_MINUTES.value)),
                        expected_minutes=float(item.get("expected_minutes", 85.0)),
                        eye_test_multiplier=float(item.get("eye_test_multiplier", 1.00)),
                        reason_category=item.get("reason_category", ""),
                        active=bool(item.get("active", True))
                    )
                    self.overrides[ov.web_name.lower()] = ov
            except Exception as e:
                # Defensive fallback: never crash on corrupt YAML
                self.overrides = {}
        return self.overrides

    def save_overrides(self, gameweek: int = 1):
        """Persist active overrides to YAML storage."""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        raw_list = []
        for ov in self.overrides.values():
            raw_list.append({
                "web_name": ov.web_name,
                "scope": ov.scope,
                "valid_gameweek": ov.valid_gameweek,
                "ttl_window": ov.ttl_window.value,
                "availability": ov.availability.value,
                "eligibility": ov.eligibility.value,
                "tactical_risk": ov.tactical_risk.value,
                "expected_minutes": ov.expected_minutes,
                "eye_test_multiplier": ov.eye_test_multiplier,
                "reason_category": ov.reason_category,
                "active": ov.active
            })
        data = {
            "gameweek": gameweek,
            "shane_metrics": {
                "overrides": raw_list
            }
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False)

    def set_override(self, override: PlayerOverride):
        """Set or update a player override."""
        self.overrides[override.web_name.lower()] = override

    def clear_overrides(self):
        """Clear all active overrides."""
        self.overrides = {}
        if os.path.exists(self.storage_path):
            try:
                os.remove(self.storage_path)
            except Exception:
                pass

    def sync_injury_intel(
        self,
        current_gw: int,
        injury_client: Optional[Any] = None,
        target_web_names: Optional[Set[str]] = None,
        auto_apply_out: bool = True,
    ) -> int:
        """
        Synchronizes live Premier League injury intelligence into Shane's Domain Intel overrides.
        Filters to target_web_names (e.g. squad/shortlist) if provided.
        Returns number of overrides set.
        """
        from clients.injury_client import InjuryClient
        client = injury_client if injury_client is not None else InjuryClient()
        return client.sync_to_shane_intel(
            intel_manager=self,
            current_gw=current_gw,
            auto_apply_out=auto_apply_out,
            target_web_names=target_web_names,
        )

    def apply_pre_stage1_overrides(self, df: pd.DataFrame, current_gw: int) -> pd.DataFrame:
        """
        Applies Tier 1 availability exclusions and tactical multipliers before MILP runs.
        If no deviations exist or overrides are expired, returns bit-for-bit unchanged copy.
        """
        mod_df = df.copy()
        if not self.overrides:
            return mod_df

        for idx, row in mod_df.iterrows():
            name = str(row.get("web_name", "")).lower()
            ov = self.overrides.get(name)
            if not ov or not ov.is_valid_for_gw(current_gw) or not ov.has_active_deviation():
                continue

            # 1. Availability / Eligibility exclusions
            if (ov.availability == AvailabilityOption.CONFIRMED_OUT_0 or 
                ov.eligibility in [EligibilityOption.TRANSFERRED_OUT, EligibilityOption.INTERNAL_SANCTION, EligibilityOption.INELIGIBLE_LOAN]):
                mod_df.at[idx, "status"] = "u"
                mod_df.at[idx, "chance_of_playing"] = 0
                if "fdr_moneyball_score" in mod_df.columns:
                    mod_df.at[idx, "fdr_moneyball_score"] = 0.0
                if "moneyball_score" in mod_df.columns:
                    mod_df.at[idx, "moneyball_score"] = 0.0
            elif ov.availability == AvailabilityOption.CLEARED_FIT_100:
                mod_df.at[idx, "status"] = "a"
                mod_df.at[idx, "chance_of_playing"] = 100
            elif ov.availability == AvailabilityOption.HEAVY_DOUBT_25:
                mod_df.at[idx, "chance_of_playing"] = 25
            elif ov.availability == AvailabilityOption.COIN_FLIP_50:
                mod_df.at[idx, "chance_of_playing"] = 50
            elif ov.availability == AvailabilityOption.MILD_DOUBT_75:
                mod_df.at[idx, "chance_of_playing"] = 75

            # 2. Eye-Test & Tactical Multipliers
            mult = ov.eye_test_multiplier
            if ov.tactical_risk == TacticalOption.OUT_OF_POSITION_ADV:
                mult *= 1.25

            if abs(mult - 1.0) > 1e-4:
                if "fdr_moneyball_score" in mod_df.columns:
                    mod_df.at[idx, "fdr_moneyball_score"] = float(mod_df.at[idx, "fdr_moneyball_score"]) * mult
                if "moneyball_score" in mod_df.columns:
                    mod_df.at[idx, "moneyball_score"] = float(mod_df.at[idx, "moneyball_score"]) * mult
                if "expected_goal_involvements_per_90" in mod_df.columns:
                    mod_df.at[idx, "expected_goal_involvements_per_90"] = float(mod_df.at[idx, "expected_goal_involvements_per_90"]) * mult

        return mod_df

    def apply_pre_stage2_overrides(self, player_dict: Dict[str, Any], current_gw: int) -> Dict[str, Any]:
        """
        Applies Tier 2 minutes expectation and volatility adjustments before Monte Carlo runs.
        """
        mod_player = copy.deepcopy(player_dict)
        name = str(mod_player.get("web_name", "")).lower()
        ov = self.overrides.get(name)
        if not ov or not ov.is_valid_for_gw(current_gw) or not ov.has_active_deviation():
            return mod_player

        # Adjust availability
        if ov.availability == AvailabilityOption.CONFIRMED_OUT_0:
            mod_player["chance_of_playing"] = 0
            mod_player["status"] = "u"
        elif ov.availability == AvailabilityOption.HEAVY_DOUBT_25:
            mod_player["chance_of_playing"] = 25
        elif ov.availability == AvailabilityOption.COIN_FLIP_50:
            mod_player["chance_of_playing"] = 50
        elif ov.availability == AvailabilityOption.MILD_DOUBT_75:
            mod_player["chance_of_playing"] = 75
        elif ov.availability == AvailabilityOption.CLEARED_FIT_100:
            mod_player["chance_of_playing"] = 100
            mod_player["status"] = "a"

        # Adjust tactical minutes & jitter
        if ov.tactical_risk == TacticalOption.ROTATION_HOOK_60:
            mod_player["expected_minutes"] = 60.0
            mod_player["minutes_std"] = 15.0
        elif ov.tactical_risk == TacticalOption.FULL_90_LOCK:
            mod_player["expected_minutes"] = 90.0
            mod_player["minutes_std"] = 2.0
        elif abs(ov.expected_minutes - 85.0) > 1e-4:
            mod_player["expected_minutes"] = ov.expected_minutes

        return mod_player
