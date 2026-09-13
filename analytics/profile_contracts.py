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
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

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

        return cls(
            profile_id=str(data["profile_id"]),
            display_name=str(data.get("display_name", data["profile_id"])),
            profile_type=p_type,
            fpl_entry_id=int(data["fpl_entry_id"]) if data.get("fpl_entry_id") is not None else None,
            bank_balance=float(data.get("bank_balance", 0.0)),
            active_squad=list(data.get("active_squad", [])),
            mini_league_ids=[int(lid) for lid in data.get("mini_league_ids", [])],
            calibration_profile=str(data.get("calibration_profile", "tuned")),
            notes=str(data.get("notes", "")),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            updated_at=str(data.get("updated_at", datetime.now(timezone.utc).isoformat())),
        )
