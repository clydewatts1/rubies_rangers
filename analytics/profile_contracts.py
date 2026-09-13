"""
analytics/profile_contracts.py
Domain models and data contracts for Multi-User, Multi-Team, and Pre-Season Sandboxes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ProfileType(str, Enum):
    """Classification of manager profile."""
    LIVE_FPL = "LIVE_FPL"            # Linked to an official public/authenticated FPL entry
    SANDBOX = "SANDBOX"              # Hypothetical draft or pre-season experimentation sandbox


@dataclass(frozen=True)
class ManagerProfile:
    """
    Immutable representation of a manager profile or experimental squad draft.
    Persisted in data/profiles/{profile_id}.json
    """
    profile_id: str
    display_name: str
    profile_type: ProfileType
    fpl_entry_id: Optional[int] = None
    bank_balance: float = 0.0
    active_squad: list[str] = field(default_factory=list)
    mini_league_ids: list[int] = field(default_factory=list)
    calibration_profile: str = "tuned"
    notes: str = ""
    is_read_only: bool = True
    is_default: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        is_clyde = (
            self.profile_id == "rubies_rangers"
            or "clyde" in self.display_name.lower()
            or self.fpl_entry_id == 6173410
        )
        if not is_clyde:
            object.__setattr__(self, "is_read_only", True)
            object.__setattr__(self, "is_default", False)
        elif self.profile_id == "rubies_rangers" or self.fpl_entry_id == 6173410:
            object.__setattr__(self, "is_read_only", False)
            object.__setattr__(self, "is_default", True)

    def to_dict(self) -> dict[str, Any]:
        """Convert profile contract to a JSON-serializable dictionary."""
        return {
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "profile_type": self.profile_type.value if isinstance(self.profile_type, ProfileType) else str(self.profile_type),
            "fpl_entry_id": self.fpl_entry_id,
            "bank_balance": round(float(self.bank_balance), 2),
            "active_squad": list(self.active_squad),
            "mini_league_ids": list(self.mini_league_ids),
            "calibration_profile": self.calibration_profile,
            "notes": self.notes,
            "is_read_only": self.is_read_only,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManagerProfile:
        """Hydrate a ManagerProfile contract from a dictionary with defensive defaults."""
        pt_raw = data.get("profile_type", ProfileType.SANDBOX.value)
        try:
            p_type = ProfileType(pt_raw)
        except ValueError:
            p_type = ProfileType.SANDBOX

        p_id = str(data["profile_id"])
        display = str(data.get("display_name", p_id)).lower()
        is_clyde = (p_id == "rubies_rangers" or "clyde" in display or data.get("fpl_entry_id") == 6173410)
        
        if not is_clyde:
            is_ro = True
            is_def = False
        else:
            raw_ro = data.get("is_read_only")
            is_ro = bool(raw_ro) if raw_ro is not None else False
            is_def = True

        return cls(
            profile_id=p_id,
            display_name=str(data.get("display_name", data["profile_id"])),
            profile_type=p_type,
            fpl_entry_id=int(data["fpl_entry_id"]) if data.get("fpl_entry_id") is not None else None,
            bank_balance=float(data.get("bank_balance", 0.0)),
            active_squad=list(data.get("active_squad", [])),
            mini_league_ids=[int(lid) for lid in data.get("mini_league_ids", [])],
            calibration_profile=str(data.get("calibration_profile", "tuned")),
            notes=str(data.get("notes", "")),
            is_read_only=is_ro,
            is_default=is_def,
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            updated_at=str(data.get("updated_at", datetime.now(timezone.utc).isoformat())),
        )
