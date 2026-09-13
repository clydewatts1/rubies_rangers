"""
analytics/profile_manager.py
Manager profile and draft persistence layer.
Handles seeding, CRUD operations, cloning, and 1-click FPL Team ID importing.
"""

from __future__ import annotations
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from analytics.profile_contracts import ManagerProfile, ProfileType
import config_manager

logger = logging.getLogger("rubies_rangers.profile_manager")

DEFAULT_PROFILES_DIR = Path("data/profiles")


def slugify_name(text: str) -> str:
    """Convert a human display name into a clean filesystem-safe slug."""
    s = text.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", "_", s)
    return s.strip("_") or "profile"


class ProfileManager:
    """Manages file-backed manager profiles and experimental pre-season drafts in data/profiles/."""

    def __init__(self, profiles_dir: Path = DEFAULT_PROFILES_DIR) -> None:
        self.profiles_dir = Path(profiles_dir)

    def ensure_seeded(self) -> None:
        """
        Ensures the profiles directory exists and contains default baseline profiles.
        Seeded from config.yaml without altering legacy config behavior.
        """
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        # 1. Primary Default Profile (Rubies Rangers / Clyde Watts)
        primary_file = self.profiles_dir / "rubies_rangers.json"
        if not primary_file.exists():
            sys_cfg = config_manager.get_system_config()
            default_entry = sys_cfg.get("default_entry_id", 6173410)
            default_squad = sys_cfg.get("default_squad", [])
            default_bank = sys_cfg.get("default_bank", 3.7)
            default_league = sys_cfg.get("default_league_id", 325320)

            primary_profile = ManagerProfile(
                profile_id="rubies_rangers",
                display_name="Rubies Rangers (Clyde Watts)",
                profile_type=ProfileType.LIVE_FPL,
                fpl_entry_id=default_entry,
                bank_balance=default_bank,
                active_squad=list(default_squad),
                mini_league_ids=[default_league] if default_league else [],
                calibration_profile="tuned",
                notes="Primary active competitive manager profile."
            )
            self.save_profile(primary_profile)
            logger.info("Seeded primary profile: %s", primary_file)

        # 2. Starter Pre-Season Sandbox Draft: Haaland + Salah Premiums
        haaland_file = self.profiles_dir / "preseason_gw1_haaland_salah.json"
        if not haaland_file.exists():
            haaland_draft = ManagerProfile(
                profile_id="preseason_gw1_haaland_salah",
                display_name="GW1 Draft: Haaland + Salah Premiums",
                profile_type=ProfileType.SANDBOX,
                fpl_entry_id=None,
                bank_balance=0.0,
                active_squad=[
                    "Pickford", "Turner", "Alexander-Arnold", "Gabriel", "Robinson",
                    "Faes", "Harwood-Bellis", "Salah", "Palmer", "Eze",
                    "Rogers", "Winks", "Haaland", "João Pedro", "Armstrong"
                ],
                mini_league_ids=[],
                calibration_profile="tuned",
                notes="Heavy-premium structure prioritizing the two highest-ceiling captain assets."
            )
            self.save_profile(haaland_draft)

        # 3. Starter Pre-Season Sandbox Draft: Balanced Depth
        balanced_file = self.profiles_dir / "preseason_gw1_balanced_depth.json"
        if not balanced_file.exists():
            balanced_draft = ManagerProfile(
                profile_id="preseason_gw1_balanced_depth",
                display_name="GW1 Draft: Balanced Midfield & Bench",
                profile_type=ProfileType.SANDBOX,
                fpl_entry_id=None,
                bank_balance=0.5,
                active_squad=[
                    "Raya", "Valdimarsson", "Gvardiol", "Saliba", "Pedro Porro",
                    "Konsa", "Barco", "Saka", "Foden", "Palmer",
                    "Gordon", "Nkunku", "Watkins", "Isak", "João Pedro"
                ],
                mini_league_ids=[],
                calibration_profile="tuned",
                notes="No-Haaland balanced portfolio maximizing 5-midfield aggregate expected points."
            )
            self.save_profile(balanced_draft)

    def list_profiles(self) -> list[ManagerProfile]:
        """Returns all manager profiles discovered on disk, sorted by type and display name."""
        self.ensure_seeded()
        profiles: list[ManagerProfile] = []

        for p_file in self.profiles_dir.glob("*.json"):
            try:
                with open(p_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    profiles.append(ManagerProfile.from_dict(data))
            except Exception as e:
                logger.error("Failed to load profile from %s: %s", p_file, e)

        # Sort: LIVE_FPL profiles first, then SANDBOX drafts alphabetically
        profiles.sort(key=lambda p: (0 if p.profile_type == ProfileType.LIVE_FPL else 1, p.display_name.lower()))
        return profiles

    def get_profile(self, profile_id: str) -> Optional[ManagerProfile]:
        """Retrieve a specific profile by identifier."""
        p_file = self.profiles_dir / f"{profile_id}.json"
        if not p_file.exists():
            return None
        try:
            with open(p_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return ManagerProfile.from_dict(data)
        except Exception as e:
            logger.error("Error reading profile %s: %s", profile_id, e)
            return None

    def save_profile(self, profile: ManagerProfile) -> Path:
        """Persist a manager profile contract as formatted JSON."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        p_file = self.profiles_dir / f"{profile.profile_id}.json"

        # Update modification timestamp
        p_dict = profile.to_dict()
        p_dict["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(p_file, "w", encoding="utf-8") as f:
            json.dump(p_dict, f, indent=2, ensure_ascii=False)

        return p_file

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile by ID. Prevents deleting the final remaining profile."""
        profiles = self.list_profiles()
        if len(profiles) <= 1:
            logger.warning("Cannot delete the final remaining profile.")
            return False

        p_file = self.profiles_dir / f"{profile_id}.json"
        if p_file.exists():
            p_file.unlink()
            logger.info("Deleted profile %s", profile_id)
            return True
        return False

    def clone_profile(self, source_id: str, new_display_name: str) -> ManagerProfile:
        """Clones an existing profile into a new isolated pre-season sandbox draft."""
        source = self.get_profile(source_id)
        if not source:
            raise ValueError(f"Source profile '{source_id}' not found.")

        base_slug = slugify_name(new_display_name)
        new_id = base_slug
        counter = 1
        while (self.profiles_dir / f"{new_id}.json").exists():
            new_id = f"{base_slug}_{counter}"
            counter += 1

        now_iso = datetime.now(timezone.utc).isoformat()
        cloned = ManagerProfile(
            profile_id=new_id,
            display_name=new_display_name.strip(),
            profile_type=ProfileType.SANDBOX,
            fpl_entry_id=None,
            bank_balance=source.bank_balance,
            active_squad=list(source.active_squad),
            mini_league_ids=list(source.mini_league_ids),
            calibration_profile=source.calibration_profile,
            notes=f"Cloned from '{source.display_name}'.",
            created_at=now_iso,
            updated_at=now_iso,
        )
        self.save_profile(cloned)
        return cloned

    def import_fpl_team(
        self,
        entry_id: int,
        gameweek: Optional[int] = None,
        custom_display_name: Optional[str] = None
    ) -> ManagerProfile:
        """
        Queries public FPL endpoints via LeagueTracker to import manager details,
        mini-leagues, bank balance, and the published 15-player squad.
        """
        from trackers.league import LeagueTracker

        lt = LeagueTracker()
        manager_info = lt.get_team_leagues(entry_id)
        picks_data = lt.get_team_picks(entry_id, gameweek=gameweek)

        team_name = manager_info.get("team_name", f"Team {entry_id}")
        manager_name = manager_info.get("manager_name", "")

        if custom_display_name and custom_display_name.strip():
            display_name = custom_display_name.strip()
        else:
            display_name = f"{team_name} ({manager_name})" if manager_name else team_name

        # Extract squad
        starters = [p["web_name"] for p in picks_data.get("starters", [])]
        bench = [p["web_name"] for p in picks_data.get("bench", [])]
        active_squad = starters + bench

        # Fallback if picks couldn't be loaded (e.g. before season starts)
        if len(active_squad) < 15:
            sys_cfg = config_manager.get_system_config()
            active_squad = list(sys_cfg.get("default_squad", []))

        # Extract bank balance
        bank_tenths = picks_data.get("entry_history", {}).get("bank", 0)
        bank_balance = round(bank_tenths / 10.0, 2) if bank_tenths else 0.0

        # Extract classic mini-leagues
        classic_leagues = [int(l["id"]) for l in manager_info.get("leagues", []) if "id" in l]

        # Generate unique profile ID
        base_slug = f"fpl_{entry_id}_{slugify_name(team_name)}"
        profile_id = base_slug
        counter = 1
        while (self.profiles_dir / f"{profile_id}.json").exists():
            profile_id = f"{base_slug}_{counter}"
            counter += 1

        imported_profile = ManagerProfile(
            profile_id=profile_id,
            display_name=display_name,
            profile_type=ProfileType.LIVE_FPL,
            fpl_entry_id=int(entry_id),
            bank_balance=bank_balance,
            active_squad=active_squad,
            mini_league_ids=classic_leagues,
            calibration_profile="tuned",
            notes=f"Imported from FPL Entry {entry_id} (Overall Rank: #{manager_info.get('overall_rank', 0):,})."
        )
        self.save_profile(imported_profile)
        logger.info("Successfully imported FPL team %d as profile '%s'", entry_id, profile_id)
        return imported_profile
