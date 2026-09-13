"""
Tactical Client: Understat Shot Quality and Non-Penalty Process Engine
Interfaces Understat API with local disk caching to compute:
- NPxG (Non-Penalty Expected Goals) & NPxG/90
- Shot Quality (xG per Shot)
- Box Shot Ratio & 6-Yard Box Presence
- Open-Play Threat (NPxGI/90)
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
import json
import time
import unicodedata
from typing import Dict, List, Any, Optional
import pandas as pd
from understatapi import UnderstatClient

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CACHE_FILE = os.path.join(_PROJECT_ROOT, ".understat_cache.json")
SHOTS_CACHE_DIR = os.path.join(_PROJECT_ROOT, ".understat_shots_cache")
CACHE_TTL = 6 * 3600  # 6 hours cache

DEFAULT_SQUAD = [
    "Roefs", "Verbruggen",
    "Pedro Porro", "Senesi", "Guéhi", "Robinson", "Thiaw",
    "Foden", "Ødegaard", "Mbeumo", "Cherki", "Rogers",
    "João Pedro", "Isak", "Solanke"
]

NAME_ALIASES = {
    "mathis cherki": "rayan cherki",
    "rayan cherki": "mathis cherki",
    "martin odegaard": "ødegaard",
    "joao pedro": "joão pedro",
    "marc guehi": "guéhi",
    "guehi": "guéhi"
}


def normalize_name(name: str) -> str:
    """Strip accents and lower case for robust player name matching."""
    if not name:
        return ""
    n = unicodedata.normalize("NFD", name)
    stripped = "".join(c for c in n if unicodedata.category(c) != "Mn").lower().strip()
    return NAME_ALIASES.get(stripped, stripped)


class TacticalClient:
    def __init__(self, cache_ttl: int = CACHE_TTL):
        self.cache_ttl = cache_ttl
        os.makedirs(SHOTS_CACHE_DIR, exist_ok=True)

    def get_league_players_raw(self, season: str = "2026", force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch raw Premier League player dataset from Understat with local caching."""
        if not force_refresh and os.path.exists(CACHE_FILE):
            file_age = time.time() - os.path.getmtime(CACHE_FILE)
            if file_age < self.cache_ttl:
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        with UnderstatClient() as client:
            data = client.league(league="EPL").get_player_data(season=season)

        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

        return data

    def get_player_shots_raw(self, understat_id: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch granular shot-by-shot data for an individual player with caching."""
        cache_path = os.path.join(SHOTS_CACHE_DIR, f"{understat_id}.json")
        if not force_refresh and os.path.exists(cache_path):
            file_age = time.time() - os.path.getmtime(cache_path)
            if file_age < self.cache_ttl:
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        with UnderstatClient() as client:
            shots = client.player(player=understat_id).get_shot_data()

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(shots, f)
        except Exception:
            pass

        return shots

    def get_league_tactical_df(self, season: str = "2026", force_refresh: bool = False) -> pd.DataFrame:
        """
        Return comprehensive DataFrame of all Premier League players with advanced tactical metrics:
        NPxG, NPxG/90, Shot Quality (xG/Shot), Open-Play Threat (NPxGI/90),
        Post-Shot Finishing True Skill (Goals - xG), and Talisman Share (% xGI_Team).
        """
        raw_players = self.get_league_players_raw(season=season, force_refresh=force_refresh)

        # Pre-compute team aggregate xG and xA for Talisman Share calculation
        team_totals: Dict[str, float] = {}
        for p in raw_players:
            t = p.get("team_title", "Unknown")
            xg_val = float(p.get("xG") or 0.0)
            xa_val = float(p.get("xA") or 0.0)
            team_totals[t] = team_totals.get(t, 0.0) + xg_val + xa_val

        records = []
        for p in raw_players:
            p_id = str(p["id"])
            p_name = p["player_name"]
            team = p["team_title"]
            pos = p.get("position", "")
            games = int(p.get("games") or 0)
            mins = float(p.get("time") or 0.0)
            shots = float(p.get("shots") or 0.0)
            goals = int(p.get("goals") or 0)
            npg = int(p.get("npg") or 0)
            xg = float(p.get("xG") or 0.0)
            npxg = float(p.get("npxG") or 0.0)
            xa = float(p.get("xA") or 0.0)
            key_passes = int(p.get("key_passes") or 0)

            ninetys = mins / 90.0 if mins > 0 else 0.0
            npxg_90 = (npxg / ninetys) if ninetys > 0 else 0.0
            xa_90 = (xa / ninetys) if ninetys > 0 else 0.0
            npxgi_90 = npxg_90 + xa_90
            xg_per_shot = (xg / shots) if shots > 0 else 0.0

            # Finishing True Skill Delta (Actual Goals - xG)
            finishing_delta = round(goals - xg, 2)
            finishing_npxg_delta = round(npg - npxg, 2)

            # Team xGI Share (Talisman Share)
            team_xgi = team_totals.get(team, 0.0)
            player_xgi = xg + xa
            talisman_share = round((player_xgi / team_xgi * 100.0), 1) if team_xgi > 0 else 0.0

            if talisman_share >= 32.0 and mins >= 90:
                talisman_tier = "👑 ALPHA TALISMAN"
            elif talisman_share >= 22.0:
                talisman_tier = "⚔️ MAJOR CONTRIBUTOR"
            elif talisman_share >= 12.0:
                talisman_tier = "⚖️ SYSTEM COG"
            else:
                talisman_tier = "🌱 SQUAD ROTATION"

            # Determine tactical archetype
            if npxgi_90 >= 0.80 and mins >= 90:
                archetype = "👑 ELITE DUAL THREAT"
            elif xg_per_shot >= 0.20 and shots >= 3:
                archetype = "🎯 CLINICAL BOX FINISHER"
            elif xa_90 >= 0.35 and key_passes >= 3:
                archetype = "🎨 CREATIVE PLAYMAKER"
            elif npxg_90 >= 0.40 and mins >= 90:
                archetype = "⚡ ACTIVE ATTACKER"
            elif shots >= 5 and xg_per_shot < 0.08:
                archetype = "🚀 PERIMETER SHOOTER"
            else:
                archetype = "⚖️ BALANCED SQUAD ASSET"

            records.append({
                "understat_id": p_id,
                "player_name": p_name,
                "norm_name": normalize_name(p_name),
                "team_title": team,
                "position": pos,
                "games": games,
                "minutes": mins,
                "ninetys": round(ninetys, 2),
                "goals": goals,
                "npg": npg,
                "shots": shots,
                "xG": round(xg, 2),
                "NPxG": round(npxg, 2),
                "NPxG_90": round(npxg_90, 2),
                "xA": round(xa, 2),
                "xA_90": round(xa_90, 2),
                "NPxGI_90": round(npxgi_90, 2),
                "xG_per_shot": round(xg_per_shot, 3),
                "finishing_skill_delta": finishing_delta,
                "finishing_skill_npxg": finishing_npxg_delta,
                "talisman_share": talisman_share,
                "talisman_tier": talisman_tier,
                "key_passes": key_passes,
                "tactical_archetype": archetype
            })

        return pd.DataFrame(records)

    def get_player_shot_breakdown(self, understat_id: str, season_year: str = "2026") -> Dict[str, Any]:
        """
        Analyze pitch coordinates (X, Y) from Understat shot maps:
        - 6-Yard Box shots (poacher zone: X >= 0.94, 0.37 <= Y <= 0.63)
        - 18-Yard Penalty Box shots (X >= 0.82, 0.21 <= Y <= 0.79)
        - Outside Box shots & xG_obox
        - Big Chance extraction (xG >= 0.35) and BCM (Big Chances Missed)
        - Shot on target accuracy (SoT %)
        - Mean-reversion pressure breakout score
        """
        all_shots = self.get_player_shots_raw(understat_id)
        # Filter for current season dates
        shots_season = [s for s in all_shots if str(s.get("date", "")).startswith(season_year)]
        if not shots_season and all_shots:
            # Fallback to last 15 shots if date tag format differs
            shots_season = all_shots[-15:]

        total_shots = len(shots_season)
        six_yard = 0
        pen_box = 0
        outside_box = 0
        open_play_shots = 0
        set_piece_shots = 0
        penalty_shots = 0
        total_xg = 0.0
        outside_box_xg = 0.0
        big_chances = 0
        big_chances_missed = 0
        big_chances_scored = 0
        shots_on_target = 0
        goals_in_shots = 0

        shot_log = []
        for s in shots_season:
            x = float(s.get("X") or 0.0)
            y = float(s.get("Y") or 0.0)
            shot_xg = float(s.get("xG") or 0.0)
            total_xg += shot_xg
            sit = s.get("situation", "OpenPlay")
            res = s.get("result", "")
            shot_type = s.get("shotType", "")
            minute = s.get("minute", "")

            # Geometry check
            is_six_yard = (x >= 0.94 and 0.37 <= y <= 0.63)
            is_pen_box = (x >= 0.82 and 0.21 <= y <= 0.79)

            if is_six_yard:
                zone = "6-Yard Box"
                six_yard += 1
                pen_box += 1
            elif is_pen_box:
                zone = "Penalty Box"
                pen_box += 1
            else:
                zone = "Outside Box"
                outside_box += 1
                outside_box_xg += shot_xg

            if sit == "Penalty":
                penalty_shots += 1
            elif sit in ["FromCorner", "SetPiece"]:
                set_piece_shots += 1
            else:
                open_play_shots += 1

            is_goal = (res == "Goal")
            if is_goal:
                goals_in_shots += 1

            # Big Chance definition (xG >= 0.35 Opta standard)
            is_big_chance = (shot_xg >= 0.35)
            if is_big_chance:
                big_chances += 1
                if is_goal:
                    big_chances_scored += 1
                else:
                    big_chances_missed += 1

            # On-target shot (Goal or SavedShot)
            is_on_target = (res in ["Goal", "SavedShot"])
            if is_on_target:
                shots_on_target += 1

            shot_log.append({
                "minute": minute,
                "result": res,
                "situation": sit,
                "shot_type": shot_type,
                "location": zone,
                "xG": round(shot_xg, 3),
                "is_big_chance": is_big_chance,
                "is_on_target": is_on_target,
                "is_outside_box": not is_pen_box,
                "X": round(x, 3),
                "Y": round(y, 3)
            })

        box_shot_pct = (pen_box / total_shots * 100.0) if total_shots > 0 else 0.0
        avg_shot_xg = (total_xg / total_shots) if total_shots > 0 else 0.0
        big_chance_conv = round(big_chances_scored / big_chances * 100.0, 1) if big_chances > 0 else 0.0
        sot_pct = round(shots_on_target / total_shots * 100.0, 1) if total_shots > 0 else 0.0

        # Mean-reversion breakout score: High BCM combined with underperformed xG predicts multi-goal haul
        mean_rev_score = round(big_chances_missed * 1.25 + max(0.0, total_xg - goals_in_shots) * 2.0, 2)

        return {
            "understat_id": understat_id,
            "total_shots": total_shots,
            "total_xG": round(total_xg, 2),
            "avg_shot_quality": round(avg_shot_xg, 3),
            "six_yard_shots": six_yard,
            "penalty_box_shots": pen_box,
            "outside_box_shots": outside_box,
            "outside_box_xg": round(outside_box_xg, 2),
            "box_shot_pct": round(box_shot_pct, 1),
            "big_chances": big_chances,
            "big_chances_missed": big_chances_missed,
            "big_chance_conversion": big_chance_conv,
            "shots_on_target": shots_on_target,
            "sot_pct": sot_pct,
            "mean_reversion_score": mean_rev_score,
            "open_play_shots": open_play_shots,
            "set_piece_shots": set_piece_shots,
            "penalty_shots": penalty_shots,
            "shot_log": shot_log
        }

    def get_squad_tactical_df(self, squad_names: Optional[List[str]] = None, force_refresh: bool = False) -> pd.DataFrame:
        """Match and compile advanced tactical process metrics for Rubies Rangers squad."""
        if squad_names is None:
            squad_names = DEFAULT_SQUAD

        df_league = self.get_league_tactical_df(force_refresh=force_refresh)

        records = []
        for name in squad_names:
            norm = normalize_name(name)
            # Match against normalized understat player_name
            m = df_league[df_league["norm_name"].str.contains(norm, case=False, na=False)]
            if m.empty:
                # Try parts
                parts = norm.split()
                if len(parts) > 1:
                    m = df_league[df_league["norm_name"].str.contains(parts[-1], case=False, na=False)]

            if not m.empty:
                row = m.iloc[0].to_dict()
                u_id = row["understat_id"]
                # Fetch shot breakdown
                sb = self.get_player_shot_breakdown(u_id)
                row["box_shot_pct"] = sb["box_shot_pct"]
                row["six_yard_shots"] = sb["six_yard_shots"]
                row["outside_box_shots"] = sb["outside_box_shots"]
                row["outside_box_xg"] = sb["outside_box_xg"]
                row["big_chances"] = sb["big_chances"]
                row["big_chances_missed"] = sb["big_chances_missed"]
                row["big_chance_conversion"] = sb["big_chance_conversion"]
                row["shots_on_target"] = sb["shots_on_target"]
                row["sot_pct"] = sb["sot_pct"]
                row["mean_reversion_score"] = sb["mean_reversion_score"]
                row["shot_log"] = sb["shot_log"]
                row["fpl_target_name"] = name
                records.append(row)
            else:
                records.append({
                    "understat_id": None,
                    "player_name": name,
                    "norm_name": norm,
                    "team_title": "Unknown",
                    "position": "UNK",
                    "games": 0,
                    "minutes": 0,
                    "ninetys": 0.0,
                    "goals": 0,
                    "npg": 0,
                    "shots": 0,
                    "xG": 0.0,
                    "NPxG": 0.0,
                    "NPxG_90": 0.0,
                    "xA": 0.0,
                    "xA_90": 0.0,
                    "NPxGI_90": 0.0,
                    "xG_per_shot": 0.0,
                    "key_passes": 0,
                    "tactical_archetype": "⚪ UNMATCHED",
                    "finishing_skill_delta": 0.0,
                    "finishing_skill_npxg": 0.0,
                    "talisman_share": 0.0,
                    "talisman_tier": "🌱 SQUAD ROTATION",
                    "box_shot_pct": 0.0,
                    "six_yard_shots": 0,
                    "outside_box_shots": 0,
                    "outside_box_xg": 0.0,
                    "big_chances": 0,
                    "big_chances_missed": 0,
                    "big_chance_conversion": 0.0,
                    "shots_on_target": 0,
                    "sot_pct": 0.0,
                    "mean_reversion_score": 0.0,
                    "shot_log": [],
                    "fpl_target_name": name
                })

        return pd.DataFrame(records)


if __name__ == "__main__":
    tc = TacticalClient()
    squad_df = tc.get_squad_tactical_df()
    print("Tactical Client Squad Process Metrics:")
    print(squad_df[["fpl_target_name", "player_name", "team_title", "shots", "NPxG_90", "xG_per_shot", "box_shot_pct", "NPxGI_90", "tactical_archetype"]].to_string(index=False))
