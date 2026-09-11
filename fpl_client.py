"""
Live Fantasy Premier League (FPL) API Client
Fetches, caches, and prepares player statistics, pricing, availability, and fixtures with FDR.
"""

import os
import json
import time
import urllib.request
import pandas as pd
from typing import Dict, List, Any, Optional

from config_manager import get_system_config, get_params

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/?future=1"
ELEMENT_SUMMARY_URL = "https://fantasy.premierleague.com/api/element-summary/{}/"
CACHE_FILE = os.path.join(os.path.dirname(__file__), ".fpl_cache.json")
FIXTURES_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".fpl_fixtures_cache.json")
ELEMENTS_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".fpl_elements_cache")
CACHE_TTL_SECONDS = get_system_config("cache_ttl_seconds") or 3600  # Default 1 hour cache



class FPLClient:
    def __init__(self, cache_ttl: Optional[int] = None):
        self.cache_ttl = cache_ttl if cache_ttl is not None else (get_system_config("cache_ttl_seconds") or CACHE_TTL_SECONDS)

    def _fetch_url(self, url: str, max_retries: Optional[int] = None) -> Any:
        if max_retries is None:
            max_retries = get_system_config("max_retries") or 3
        timeout = get_system_config("http_timeout_seconds") or 15
        backoff_base = get_system_config("retry_backoff_base") or 0.5
        last_err = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RubiesRangersFPL/1.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(backoff_base * (2 ** attempt))
        raise last_err


    def get_bootstrap_data(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch bootstrap data with local caching and offline fallback."""
        if not force_refresh and os.path.exists(CACHE_FILE):
            file_age = time.time() - os.path.getmtime(CACHE_FILE)
            if file_age < self.cache_ttl:
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        try:
            data = self._fetch_url(BOOTSTRAP_URL)
            try:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception as e:
                print(f"Warning: Failed to write bootstrap cache: {e}")
            return data
        except Exception as e:
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
            raise e

    def get_fixtures_data(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch upcoming fixtures with local caching and offline fallback."""
        if not force_refresh and os.path.exists(FIXTURES_CACHE_FILE):
            file_age = time.time() - os.path.getmtime(FIXTURES_CACHE_FILE)
            if file_age < self.cache_ttl:
                try:
                    with open(FIXTURES_CACHE_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        try:
            data = self._fetch_url(FIXTURES_URL)
            try:
                with open(FIXTURES_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception as e:
                print(f"Warning: Failed to write fixtures cache: {e}")
            return data
        except Exception as e:
            if os.path.exists(FIXTURES_CACHE_FILE):
                try:
                    with open(FIXTURES_CACHE_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
            raise e

    def get_current_gameweek(self) -> Optional[int]:
        """Return the current active gameweek."""
        data = self.get_bootstrap_data()
        for event in data.get("events", []):
            if event.get("is_current"):
                return event.get("id")
        return None

    def get_team_fdr_map(self, n_gameweeks: int = 5, swing_split: int = 2) -> Dict[int, Dict[str, Any]]:
        """
        Compute rolling Fixture Difficulty Rating (FDR) schedule and Fixture Swing metrics for all clubs.
        swing_split: number of upcoming fixtures to compare against remaining horizon (default 2).
        """
        boot = self.get_bootstrap_data()
        fixtures = self.get_fixtures_data()

        teams = {t["id"]: t["name"] for t in boot["teams"]}
        team_shorts = {t["id"]: t["short_name"] for t in boot["teams"]}
        
        current_gw = self.get_current_gameweek() or 1
        next_gw = current_gw + 1
        target_gws = list(range(next_gw, next_gw + n_gameweeks))

        team_fixtures = {t_id: [] for t_id in teams}
        for f in fixtures:
            gw = f.get("event")
            if gw in target_gws:
                h_id = f["team_h"]
                a_id = f["team_a"]
                h_diff = f["team_h_difficulty"]
                a_diff = f["team_a_difficulty"]
                team_fixtures[h_id].append({
                    "gw": gw,
                    "opp_id": a_id,
                    "opp_name": teams.get(a_id, "UNK"),
                    "opp_short": team_shorts.get(a_id, "UNK"),
                    "is_home": True,
                    "difficulty": h_diff
                })
                team_fixtures[a_id].append({
                    "gw": gw,
                    "opp_id": h_id,
                    "opp_name": teams.get(h_id, "UNK"),
                    "opp_short": team_shorts.get(h_id, "UNK"),
                    "is_home": False,
                    "difficulty": a_diff
                })

        result = {}
        for t_id, fix_list in team_fixtures.items():
            # Sort by gameweek
            fix_list.sort(key=lambda x: x["gw"])
            if fix_list:
                avg_diff = sum(x["difficulty"] for x in fix_list) / len(fix_list)
                next_match = fix_list[0]
                next_str = f"{next_match['opp_short']} ({'H' if next_match['is_home'] else 'A'}, {next_match['difficulty']})"
                next_diff = next_match["difficulty"]

                # Fixture Swing Calculations (near-term vs later fixtures)
                near_fixes = fix_list[:swing_split]
                later_fixes = fix_list[swing_split:]

                near_fdr = sum(x["difficulty"] for x in near_fixes) / len(near_fixes) if near_fixes else avg_diff
                later_fdr = sum(x["difficulty"] for x in later_fixes) / len(later_fixes) if later_fixes else avg_diff
                # Positive swing delta = near-term is harder than later (schedule gets much easier!)
                swing_delta = round(near_fdr - later_fdr, 2)

                if swing_delta >= 1.0:
                    swing_label = "▲ MAJOR GREEN SWING (Buy Target)"
                    swing_status = "POSITIVE_MAJOR"
                elif swing_delta >= 0.5:
                    swing_label = "▲ GREEN SWING (Accumulate)"
                    swing_status = "POSITIVE"
                elif swing_delta <= -1.0:
                    swing_label = "▼ MAJOR RED WALL (Sell Alert)"
                    swing_status = "NEGATIVE_MAJOR"
                elif swing_delta <= -0.5:
                    swing_label = "▼ RED WALL (Prepare to Sell)"
                    swing_status = "NEGATIVE"
                else:
                    swing_label = "STABLE"
                    swing_status = "NEUTRAL"
            else:
                avg_diff = 3.0
                next_str = "TBD"
                next_diff = 3
                near_fdr = 3.0
                later_fdr = 3.0
                swing_delta = 0.0
                swing_label = "STABLE"
                swing_status = "NEUTRAL"

            # FDR multiplier: neutral baseline (default 3.0); green schedule (<neutral) gives boost, red (>neutral) discounts
            mb_params = get_params("moneyball")
            fdr_cfg = mb_params.get("fdr_multiplier", {})
            neutral_base = fdr_cfg.get("neutral_baseline", 3.0)
            scaling = fdr_cfg.get("scaling_factor", 5.0)
            fdr_multiplier = 1.0 + ((neutral_base - avg_diff) / scaling)


            result[t_id] = {
                "team_name": teams.get(t_id, "Unknown"),
                "team_short": team_shorts.get(t_id, "UNK"),
                "avg_fdr": round(avg_diff, 2),
                "next_fixture": next_str,
                "next_fdr": next_diff,
                "near_fdr": round(near_fdr, 2),
                "later_fdr": round(later_fdr, 2),
                "swing_delta": swing_delta,
                "swing_label": swing_label,
                "swing_status": swing_status,
                "fdr_multiplier": round(fdr_multiplier, 3),
                "fixtures": fix_list
            }

        return result

    def get_players_df(self, force_refresh: bool = False, n_fdr_weeks: int = 5) -> pd.DataFrame:
        """
        Extract clean, structured DataFrame of all players with Moneyball and rolling FDR metrics.
        """
        data = self.get_bootstrap_data(force_refresh=force_refresh)
        fdr_map = self.get_team_fdr_map(n_gameweeks=n_fdr_weeks)

        teams = {t["id"]: t["name"] for t in data["teams"]}
        team_short = {t["id"]: t["short_name"] for t in data["teams"]}
        positions = {p["id"]: p["singular_name_short"] for p in data["element_types"]}

        # Load configurable Moneyball parameters
        mb_params = get_params("moneyball")
        fwd_mid_cfg = mb_params.get("fwd_mid", {})
        def_cfg = mb_params.get("def", {})
        gkp_cfg = mb_params.get("gkp", {})
        sp_cfg = mb_params.get("set_piece_bonuses", {})
        price_cfg = mb_params.get("price_prediction", {})

        rows = []
        for p in data["elements"]:
            cost = p["now_cost"] / 10.0
            total_points = p.get("total_points", 0)
            minutes = p.get("minutes", 0)
            ninetys = minutes / 90.0 if minutes > 0 else 0.0

            xG = float(p.get("expected_goals") or 0.0)
            xA = float(p.get("expected_assists") or 0.0)
            xGI = float(p.get("expected_goal_involvements") or 0.0)
            
            xG_90 = float(p.get("expected_goals_per_90") or 0.0)
            xA_90 = float(p.get("expected_assists_per_90") or 0.0)
            xGI_90 = float(p.get("expected_goal_involvements_per_90") or 0.0)

            # Defensive contribution calculation
            def_contrib = float(p.get("defensive_contribution") or 0.0)
            def_contrib_90 = float(p.get("defensive_contribution_per_90") or 0.0)
            if def_contrib_90 == 0.0 and ninetys > 0 and def_contrib > 0:
                def_contrib_90 = def_contrib / ninetys

            ict = float(p.get("ict_index") or 0.0)
            form = float(p.get("form") or 0.0)
            ppg = float(p.get("points_per_game") or 0.0)

            # Moneyball base score from config parameters
            pos_code = positions.get(p["element_type"], "UNK")
            if pos_code in ["FWD", "MID"]:
                base_exp = (xGI_90 * fwd_mid_cfg.get("xgi_weight", 4.0)) + (ict / fwd_mid_cfg.get("ict_divisor", 50.0)) + (form * fwd_mid_cfg.get("form_weight", 1.5))
            elif pos_code == "DEF":
                base_exp = (def_contrib_90 * def_cfg.get("def_contrib_weight", 0.4)) + (xGI_90 * def_cfg.get("xgi_weight", 3.0)) + (form * def_cfg.get("form_weight", 1.5)) + (ict / def_cfg.get("ict_divisor", 60.0))
            else:  # GKP
                base_exp = (ppg * gkp_cfg.get("ppg_weight", 1.2)) + (form * gkp_cfg.get("form_weight", 1.5))

            moneyball_efficiency = (base_exp / cost) if cost > 0 else 0.0
            ppm = (total_points / cost) if cost > 0 else 0.0

            # FDR metrics integration
            team_id = p["team"]
            team_fdr_info = fdr_map.get(team_id, {
                "avg_fdr": 3.0,
                "next_fixture": "TBD",
                "next_fdr": 3,
                "fdr_multiplier": 1.0,
                "fixtures": []
            })
            fdr_next_5 = team_fdr_info["avg_fdr"]
            next_fix = team_fdr_info["next_fixture"]
            next_fdr_val = team_fdr_info["next_fdr"]
            fdr_multiplier = team_fdr_info["fdr_multiplier"]
            swing_delta = team_fdr_info.get("swing_delta", 0.0)
            swing_label = team_fdr_info.get("swing_label", "STABLE")
            swing_status = team_fdr_info.get("swing_status", "NEUTRAL")
            near_fdr = team_fdr_info.get("near_fdr", 3.0)
            later_fdr = team_fdr_info.get("later_fdr", 3.0)
            
            fdr_adjusted_mb = base_exp * fdr_multiplier
            fdr_adjusted_eff = (fdr_adjusted_mb / cost) if cost > 0 else 0.0

            # Market Velocity & Price Change Prediction from config
            tin = p.get("transfers_in_event", 0)
            tout = p.get("transfers_out_event", 0)
            net_transfers = tin - tout
            selected = p.get("selected", 1)
            cost_change_event = p.get("cost_change_event", 0) / 10.0

            rise_base = price_cfg.get("rise_thresh_base", 75000)
            rise_frac = price_cfg.get("rise_selected_frac", 0.075)
            rise_mult = price_cfg.get("rise_cost_change_mult", 1.5)
            fall_base = price_cfg.get("fall_thresh_base", 60000)
            fall_frac = price_cfg.get("fall_selected_frac", 0.065)

            rise_thresh = max(rise_base, selected * rise_frac)
            fall_thresh = max(fall_base, selected * fall_frac)
            if cost_change_event > 0:
                rise_thresh *= rise_mult

            if net_transfers >= 0:
                price_progress_pct = round((net_transfers / rise_thresh) * 100, 1)
                price_direction = "RISE"
            else:
                price_progress_pct = round((abs(net_transfers) / fall_thresh) * 100, 1)
                price_direction = "FALL"

            soon_thresh = price_cfg.get("soon_threshold_pct", 70.0)
            tonight_thresh = price_cfg.get("tonight_threshold_pct", 100.0)
            if price_progress_pct >= tonight_thresh:
                price_status = f"{price_direction} TONIGHT"
            elif price_progress_pct >= soon_thresh:
                price_status = f"{price_direction} Soon"
            else:
                price_status = "Stable"

            # Set-piece hierarchies & duties
            pen_order = p.get("penalties_order")
            pen_text = p.get("penalties_text") or ""
            fk_order = p.get("direct_freekicks_order")
            fk_text = p.get("direct_freekicks_text") or ""
            crn_order = p.get("corners_and_indirect_freekicks_order")
            crn_text = p.get("corners_and_indirect_freekicks_text") or ""

            is_penalty_taker = (pen_order == 1)
            is_direct_fk_taker = (fk_order in [1, 2])
            is_corner_taker = (crn_order in [1, 2])
            is_any_set_piece = bool(
                is_penalty_taker or is_direct_fk_taker or is_corner_taker or
                (pen_order is not None and pen_order <= 2) or
                (fk_order is not None and fk_order <= 2) or
                (crn_order is not None and crn_order <= 2)
            )

            # Build badge labels
            def _ord(n):
                if n == 1: return "1st"
                elif n == 2: return "2nd"
                elif n == 3: return "3rd"
                return f"{n}th"

            badges = []
            if pen_order:
                badges.append(f"⚽ PEN ({_ord(pen_order)})")
            if fk_order:
                badges.append(f"🎯 FK ({_ord(fk_order)})")
            if crn_order:
                badges.append(f"🚩 CRN ({_ord(crn_order)})")

            set_piece_badges = " | ".join(badges) if badges else "None"

            # Moneyball set-piece bonus from config
            sp_bonus = 0.0
            if pen_order == 1:
                sp_bonus += sp_cfg.get("pen_order_1", 0.65)
            elif pen_order == 2:
                sp_bonus += sp_cfg.get("pen_order_2", 0.25)

            if fk_order == 1:
                sp_bonus += sp_cfg.get("fk_order_1", 0.25)
            elif fk_order == 2:
                sp_bonus += sp_cfg.get("fk_order_2", 0.10)

            if crn_order == 1:
                sp_bonus += sp_cfg.get("crn_order_1", 0.35)
            elif crn_order == 2:
                sp_bonus += sp_cfg.get("crn_order_2", 0.15)

            base_with_sp = base_exp + sp_bonus
            setpiece_fdr_mb = base_with_sp * fdr_multiplier


            rows.append({
                "id": p["id"],
                "web_name": p["web_name"],
                "first_name": p["first_name"],
                "second_name": p["second_name"],
                "full_name": f"{p['first_name']} {p['second_name']}",
                "club_id": team_id,
                "club_name": teams.get(team_id, "Unknown"),
                "club_short": team_short.get(team_id, "UNK"),
                "position_id": p["element_type"],
                "position_name": pos_code,
                "now_cost": cost,
                "cost_change_event": cost_change_event,
                "total_points": total_points,
                "points_per_game": ppg,
                "form": form,
                "selected_by_percent": float(p.get("selected_by_percent") or 0.0),
                "minutes": minutes,
                "status": p.get("status", "a"),
                "news": p.get("news", ""),
                "chance_of_playing": p.get("chance_of_playing_next_round"),
                "yellow_cards": p.get("yellow_cards", 0),
                "red_cards": p.get("red_cards", 0),
                "is_penalty_taker": is_penalty_taker,
                "is_direct_fk_taker": is_direct_fk_taker,
                "is_corner_taker": is_corner_taker,
                "is_any_set_piece": is_any_set_piece,
                "penalties_order": pen_order,
                "penalties_text": pen_text,
                "direct_freekicks_order": fk_order,
                "direct_freekicks_text": fk_text,
                "corners_and_indirect_freekicks_order": crn_order,
                "corners_and_indirect_freekicks_text": crn_text,
                "set_piece_badges": set_piece_badges,
                "set_piece_bonus": round(sp_bonus, 2),
                "setpiece_moneyball_score": round(setpiece_fdr_mb, 2),
                "transfers_in_event": tin,
                "transfers_out_event": tout,
                "net_transfers": net_transfers,
                "price_direction": price_direction,
                "price_progress_pct": price_progress_pct,
                "price_status": price_status,
                "goals_scored": p.get("goals_scored", 0),
                "assists": p.get("assists", 0),
                "clean_sheets": p.get("clean_sheets", 0),
                "ict_index": ict,
                "expected_goals": xG,
                "expected_assists": xA,
                "expected_goal_involvements": xGI,
                "expected_goals_per_90": xG_90,
                "expected_assists_per_90": xA_90,
                "expected_goal_involvements_per_90": xGI_90,
                "defensive_contribution": def_contrib,
                "defensive_contribution_per_90": def_contrib_90,
                "fdr_next_5": fdr_next_5,
                "next_fixture": next_fix,
                "next_fdr": next_fdr_val,
                "near_fdr": near_fdr,
                "later_fdr": later_fdr,
                "swing_delta": swing_delta,
                "swing_label": swing_label,
                "swing_status": swing_status,
                "fdr_multiplier": fdr_multiplier,
                "ppm": round(ppm, 2),
                "moneyball_score": round(base_exp, 2),
                "moneyball_efficiency": round(moneyball_efficiency, 2),
                "fdr_moneyball_score": round(fdr_adjusted_mb, 2),
                "fdr_moneyball_efficiency": round(fdr_adjusted_eff, 2)
            })

        return pd.DataFrame(rows)

    def get_fixture_swings(self, n_gameweeks: int = 6) -> Dict[str, Any]:
        """
        Detect fixture difficulty swings across Premier League clubs over a rolling horizon.
        Returns positive swing teams (buy targets) and negative swing teams (sell alerts).
        """
        fdr_map = self.get_team_fdr_map(n_gameweeks=n_gameweeks)
        teams = list(fdr_map.values())

        pos_swings = [t for t in teams if t["swing_delta"] >= 0.5]
        pos_swings.sort(key=lambda x: x["swing_delta"], reverse=True)

        neg_swings = [t for t in teams if t["swing_delta"] <= -0.5]
        neg_swings.sort(key=lambda x: x["swing_delta"])

        return {
            "positive_swings": pos_swings,
            "negative_swings": neg_swings,
            "all_teams": sorted(teams, key=lambda x: x["swing_delta"], reverse=True)
        }

    def get_set_piece_hierarchy(self, club_name: Optional[str] = None) -> pd.DataFrame:
        """
        Return structured table of all designated set-piece takers across Premier League clubs.
        """
        df = self.get_players_df()
        sp_df = df[df["is_any_set_piece"]].copy()
        if club_name:
            sp_df = sp_df[sp_df["club_name"].str.contains(club_name, case=False, na=False) |
                          sp_df["club_short"].str.contains(club_name, case=False, na=False)]
        return sp_df.sort_values(by=["club_name", "penalties_order", "direct_freekicks_order", "corners_and_indirect_freekicks_order"], na_position="last")

    def get_price_predictions(self, min_progress: float = 70.0) -> pd.DataFrame:
        """Return all players predicted to change price soon or tonight."""
        df = self.get_players_df()
        active = df[df["status"] == "a"].copy()
        pred = active[active["price_progress_pct"] >= min_progress].copy()
        return pred.sort_values(by="price_progress_pct", ascending=False)

    def get_element_summary(self, player_id: int, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch match-by-match element summary for a player with local disk caching."""
        os.makedirs(ELEMENTS_CACHE_DIR, exist_ok=True)
        cache_path = os.path.join(ELEMENTS_CACHE_DIR, f"{player_id}.json")
        if not force_refresh and os.path.exists(cache_path):
            file_age = time.time() - os.path.getmtime(cache_path)
            if file_age < self.cache_ttl:
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        url = ELEMENT_SUMMARY_URL.format(player_id)
        try:
            data = self._fetch_url(url)
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception:
                pass
            return data
        except Exception as e:
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
            raise e

    def get_player_trends(self, player_id: int, n_recent: int = 3) -> Dict[str, Any]:
        """
        Analyze match-by-match trends for a player:
        - Rolling xGI trends (last n_recent matches vs seasonal average)
        - Minutes stability & rotation risk (starts vs subs)
        - Granular defensive actions (CBI, tackles, recoveries, defensive contribution)
        """
        boot = self.get_bootstrap_data()
        teams = {t["id"]: t["name"] for t in boot["teams"]}
        team_shorts = {t["id"]: t["short_name"] for t in boot["teams"]}

        p_info = None
        for el in boot["elements"]:
            if el["id"] == player_id:
                p_info = el
                break

        summary = self.get_element_summary(player_id)
        history = summary.get("history", [])
        history.sort(key=lambda x: x.get("round", 0))

        total_matches = len(history)
        recent_matches = history[-n_recent:] if total_matches > 0 else []
        k = len(recent_matches)

        match_log = []
        for m in history:
            opp_id = m.get("opponent_team", 0)
            was_home = m.get("was_home", True)
            ha_str = "H" if was_home else "A"
            opp_short = team_shorts.get(opp_id, f"T{opp_id}")
            fixture_label = f"{opp_short} ({ha_str})"
            
            h_score = m.get("team_h_score")
            a_score = m.get("team_a_score")
            score_str = f"{h_score}-{a_score}" if h_score is not None and a_score is not None else "N/A"

            match_log.append({
                "round": m.get("round", 0),
                "fixture": fixture_label,
                "score": score_str,
                "minutes": m.get("minutes", 0),
                "starts": m.get("starts", 0),
                "total_points": m.get("total_points", 0),
                "goals_scored": m.get("goals_scored", 0),
                "assists": m.get("assists", 0),
                "clean_sheets": m.get("clean_sheets", 0),
                "expected_goals": float(m.get("expected_goals") or 0.0),
                "expected_assists": float(m.get("expected_assists") or 0.0),
                "expected_goal_involvements": float(m.get("expected_goal_involvements") or 0.0),
                "expected_goals_conceded": float(m.get("expected_goals_conceded") or 0.0),
                "tackles": m.get("tackles", 0),
                "cbi": m.get("clearances_blocks_interceptions", 0),
                "recoveries": m.get("recoveries", 0),
                "defensive_contribution": m.get("defensive_contribution", 0),
                "bps": m.get("bps", 0),
                "bonus": m.get("bonus", 0),
                "ict_index": float(m.get("ict_index") or 0.0)
            })

        if k == 0:
            return {
                "player_id": player_id,
                "web_name": p_info.get("web_name", "Unknown") if p_info else "Unknown",
                "total_matches": 0,
                "recent_minutes": [],
                "recent_minutes_str": "N/A",
                "avg_recent_mins": 0.0,
                "recent_starts": "0/0",
                "starts_ratio": 0.0,
                "minutes_status": "NO_DATA",
                "status_badge": "⚪ No Data",
                "avg_recent_xgi": 0.0,
                "season_xgi_per_match": 0.0,
                "xgi_trend_delta": 0.0,
                "xgi_trend_label": "STABLE",
                "xgi_trend_status": "STABLE",
                "avg_recent_cbi": 0.0,
                "avg_recent_tackles": 0.0,
                "avg_recent_recoveries": 0.0,
                "avg_recent_def_contrib": 0.0,
                "season_def_contrib_per_match": 0.0,
                "avg_recent_pts": 0.0,
                "match_log": match_log
            }

        # Minutes & Starts
        recent_mins = [m.get("minutes", 0) for m in recent_matches]
        avg_recent_mins = sum(recent_mins) / k
        recent_starts = [m.get("starts", 0) for m in recent_matches]
        num_starts = sum(recent_starts)
        starts_ratio = num_starts / k
        latest_mins = recent_mins[-1] if recent_mins else 0

        # Minutes Stability Classification
        if total_matches >= 2 and (latest_mins == 0 or (avg_recent_mins < 30 and num_starts == 0)):
            minutes_status = "BENCHED_OR_DROPPED"
            status_badge = "🔴 BENCHED / DROPPED"
        elif num_starts == k and avg_recent_mins >= 75:
            minutes_status = "SECURE_STARTER"
            status_badge = "🟢 SECURE (90m Core)"
        elif num_starts >= (k - 1) and avg_recent_mins >= 55:
            minutes_status = "REGULAR_STARTER"
            status_badge = "🟢 REGULAR STARTER"
        else:
            minutes_status = "ROTATION_RISK"
            status_badge = "🟡 ROTATION RISK / SUB"

        # Attacking Metrics (Rolling 3 vs Seasonal)
        recent_xgi = [float(m.get("expected_goal_involvements") or 0.0) for m in recent_matches]
        avg_recent_xgi = sum(recent_xgi) / k
        all_xgi = [float(m.get("expected_goal_involvements") or 0.0) for m in history]
        season_xgi_per_match = sum(all_xgi) / total_matches if total_matches > 0 else 0.0
        xgi_trend_delta = round(avg_recent_xgi - season_xgi_per_match, 2)

        if xgi_trend_delta >= 0.25 or (season_xgi_per_match > 0.1 and (avg_recent_xgi / season_xgi_per_match) >= 1.4):
            xgi_trend_label = "🔥 SURGING THREAT (Role Elevation)"
            xgi_trend_status = "SURGING"
        elif xgi_trend_delta <= -0.25 or (season_xgi_per_match > 0.2 and (avg_recent_xgi / season_xgi_per_match) <= 0.6):
            xgi_trend_label = "❄️ COOLING OFF"
            xgi_trend_status = "COOLING"
        else:
            xgi_trend_label = "➡️ STABLE"
            xgi_trend_status = "STABLE"

        # Defensive Actions
        recent_cbi = [m.get("clearances_blocks_interceptions", 0) for m in recent_matches]
        recent_tackles = [m.get("tackles", 0) for m in recent_matches]
        recent_rec = [m.get("recoveries", 0) for m in recent_matches]
        recent_dc = [m.get("defensive_contribution", 0) for m in recent_matches]
        all_dc = [m.get("defensive_contribution", 0) for m in history]

        avg_recent_cbi = sum(recent_cbi) / k
        avg_recent_tackles = sum(recent_tackles) / k
        avg_recent_rec = sum(recent_rec) / k
        avg_recent_dc = sum(recent_dc) / k
        season_dc_per_match = sum(all_dc) / total_matches if total_matches > 0 else 0.0

        # Points
        recent_pts = [m.get("total_points", 0) for m in recent_matches]
        avg_recent_pts = sum(recent_pts) / k

        web_name = p_info.get("web_name", "Unknown") if p_info else "Unknown"

        return {
            "player_id": player_id,
            "web_name": web_name,
            "total_matches": total_matches,
            "recent_minutes": recent_mins,
            "recent_minutes_str": ", ".join(str(m) for m in recent_mins),
            "avg_recent_mins": round(avg_recent_mins, 1),
            "recent_starts": f"{num_starts}/{k}",
            "starts_ratio": round(starts_ratio, 2),
            "minutes_status": minutes_status,
            "status_badge": status_badge,
            "avg_recent_xgi": round(avg_recent_xgi, 2),
            "season_xgi_per_match": round(season_xgi_per_match, 2),
            "xgi_trend_delta": xgi_trend_delta,
            "xgi_trend_label": xgi_trend_label,
            "xgi_trend_status": xgi_trend_status,
            "avg_recent_cbi": round(avg_recent_cbi, 1),
            "avg_recent_tackles": round(avg_recent_tackles, 1),
            "avg_recent_recoveries": round(avg_recent_rec, 1),
            "avg_recent_def_contrib": round(avg_recent_dc, 1),
            "season_def_contrib_per_match": round(season_dc_per_match, 1),
            "avg_recent_pts": round(avg_recent_pts, 1),
            "match_log": match_log
        }

    def get_squad_trends(self, squad_names_or_ids: Optional[List[Any]] = None, n_recent: int = 3) -> pd.DataFrame:
        """
        Batch analyze match-by-match trends for squad players or specified target list.
        """
        df = self.get_players_df()
        if squad_names_or_ids is None:
            squad_names_or_ids = [
                "Roefs", "Verbruggen",
                "Pedro Porro", "Senesi", "Guéhi", "Robinson", "Thiaw",
                "Foden", "Ødegaard", "Mbeumo", "Cherki", "Rogers",
                "João Pedro", "Isak", "Solanke"
            ]

        records = []
        for item in squad_names_or_ids:
            if isinstance(item, int):
                p_match = df[df["id"] == item]
            else:
                name_str = str(item)
                p_match = df[df["web_name"].str.lower() == name_str.lower()]
                if p_match.empty:
                    p_match = df[df["full_name"].str.lower() == name_str.lower()]
                if p_match.empty:
                    p_match = df[df["web_name"].str.contains(name_str, case=False, na=False)]
                if p_match.empty:
                    p_match = df[df["full_name"].str.contains(name_str, case=False, na=False)]

            if not p_match.empty:
                row = p_match.iloc[0]
                p_id = int(row["id"])
                tr = self.get_player_trends(p_id, n_recent=n_recent)
                records.append({
                    "id": p_id,
                    "web_name": row["web_name"],
                    "club_name": row["club_name"],
                    "club_short": row["club_short"],
                    "position_name": row["position_name"],
                    "now_cost": row["now_cost"],
                    "status": row.get("status", "a"),
                    "news": row.get("news", ""),
                    "recent_minutes_str": tr["recent_minutes_str"],
                    "avg_recent_mins": tr["avg_recent_mins"],
                    "recent_starts": tr["recent_starts"],
                    "minutes_status": tr["minutes_status"],
                    "status_badge": tr["status_badge"],
                    "avg_recent_xgi": tr["avg_recent_xgi"],
                    "season_xgi_per_match": tr["season_xgi_per_match"],
                    "xgi_trend_delta": tr["xgi_trend_delta"],
                    "xgi_trend_label": tr["xgi_trend_label"],
                    "xgi_trend_status": tr["xgi_trend_status"],
                    "avg_recent_def_contrib": tr["avg_recent_def_contrib"],
                    "avg_recent_cbi": tr["avg_recent_cbi"],
                    "avg_recent_tackles": tr["avg_recent_tackles"],
                    "avg_recent_recoveries": tr["avg_recent_recoveries"],
                    "avg_recent_pts": tr["avg_recent_pts"],
                    "total_points": row["total_points"],
                    "fdr_moneyball_score": row["fdr_moneyball_score"],
                    "match_log": tr["match_log"]
                })

        return pd.DataFrame(records)


if __name__ == "__main__":
    client = FPLClient()
    df = client.get_players_df()
    print(f"Loaded {len(df)} players with rolling FDR.")
    print(f"Current GW: {client.get_current_gameweek()}")
    print("\nTop 5 Players by Fixture-Adjusted Moneyball Score:")
    top = df[df["status"] == "a"].sort_values(by="fdr_moneyball_score", ascending=False).head(5)
    print(top[["web_name", "club_name", "position_name", "now_cost", "form", "fdr_next_5", "next_fixture", "fdr_moneyball_score"]].to_string(index=False))
