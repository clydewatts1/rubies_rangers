"""
Macro Fixture Regime & Wave Scanner Engine for Strategic FPL Management.
Implements Green Wave swing detection, Red Cliff liquidation warnings,
combinatorial 190-pair budget defensive rotation, and squad macro audits.
Governed by .agents/rules/moneyball_strategy.md and .agents/rules/python_standards.md.
"""

from __future__ import annotations
import itertools
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from config_manager import get_params
from clients.fpl_client import FPLClient
from analytics.strategic.contracts import (
    ClubScheduleProfile,
    FixtureWaveAlert,
    DefensiveRotationPair,
    SquadWaveAudit,
)
from analytics.strategic.trajectory_engine import (
    build_club_schedule_profiles,
    build_strategic_squad_state,
)


class WaveScanner:
    """
    Macro information radar that scans Premier League club schedules across 4 to 8 gameweeks
    to identify high-probability asset accumulation regimes and defensive rotation synergies.
    """

    def __init__(
        self,
        fpl_client: Optional[FPLClient] = None,
        default_horizon: int = 8,
        profile: Optional[str] = None
    ) -> None:
        self.client = fpl_client or FPLClient()
        self.default_horizon = default_horizon
        self.profile = profile
        self._club_profiles: Optional[Dict[str, ClubScheduleProfile]] = None
        self._cached_waves: Optional[List[FixtureWaveAlert]] = None
        self._cached_pairs: Optional[List[DefensiveRotationPair]] = None

    def get_club_profiles(self, force_refresh: bool = False) -> Dict[str, ClubScheduleProfile]:
        """Fetch or retrieve cached club schedule profiles."""
        if self._club_profiles is None or force_refresh:
            self._club_profiles = build_club_schedule_profiles(
                fpl_client=self.client,
                horizon=self.default_horizon,
                profile=self.profile
            )
        return self._club_profiles

    def scan_waves(self, force_refresh: bool = False) -> List[FixtureWaveAlert]:
        """Scan all clubs for active Green Waves and Red Cliffs."""
        if self._cached_waves is None or force_refresh:
            c_profs = self.get_club_profiles(force_refresh=force_refresh)
            self._cached_waves = scan_fixture_waves(
                club_profiles=c_profs,
                horizon=self.default_horizon,
                profile=self.profile,
                fpl_client=self.client
            )
        return self._cached_waves

    def get_rotation_pairs(
        self,
        max_cost: float = 4.5,
        top_k: int = 5,
        force_refresh: bool = False
    ) -> List[DefensiveRotationPair]:
        """Find optimal 2-club budget defensive rotation pairings."""
        if self._cached_pairs is None or force_refresh:
            c_profs = self.get_club_profiles(force_refresh=force_refresh)
            self._cached_pairs = find_optimal_defensive_rotation_pairs(
                club_profiles=c_profs,
                horizon=self.default_horizon,
                max_cost=max_cost,
                top_k=top_k,
                fpl_client=self.client
            )
        return self._cached_pairs

    def audit_squad(
        self,
        squad_player_ids: Optional[Tuple[int, ...]] = None
    ) -> List[SquadWaveAudit]:
        """Audit active squad players against upcoming macro fixture regimes."""
        c_profs = self.get_club_profiles()
        return audit_squad_waves(
            squad_player_ids=squad_player_ids,
            club_profiles=c_profs,
            horizon=self.default_horizon,
            fpl_client=self.client
        )


def scan_fixture_waves(
    club_profiles: Optional[Dict[str, ClubScheduleProfile]] = None,
    horizon: int = 8,
    profile: Optional[str] = None,
    fpl_client: Optional[FPLClient] = None
) -> List[FixtureWaveAlert]:
    """
    Identifies contiguous Green Waves and Red Cliffs across all Premier League clubs.
    
    Mathematical Formulation:
        Green Wave: Contiguous run >= 3 fixtures with avg FDR <= threshold_green (default 2.50)
        Red Cliff:  Contiguous run >= 3 fixtures with avg FDR >= threshold_red (default 3.40)
        Inflection Point: Act 1 GW prior to wave/cliff commencement to front-run market liquidity.
    """
    client = fpl_client or FPLClient()
    if club_profiles is None:
        club_profiles = build_club_schedule_profiles(fpl_client=client, horizon=horizon, profile=profile)

    current_gw = client.get_current_gameweek() or 1
    next_gw = current_gw + 1
    target_gws = [next_gw + i for i in range(horizon)]

    # Load thresholds from config
    strat_cfg = get_params("strategic", profile=profile) or {}
    wave_cfg = strat_cfg.get("waves", {})
    thresh_green = float(wave_cfg.get("threshold_green", 2.50))
    thresh_red = float(wave_cfg.get("threshold_red", 3.40))

    # Pre-fetch key talent per club
    players_df = client.get_players_df()
    top_assets_by_club: Dict[str, List[str]] = {}
    if not players_df.empty:
        for c_short, group in players_df.groupby("club_short"):
            # Sort by fdr_moneyball_score or xp descending
            top_p = group.sort_values(by="fdr_moneyball_score", ascending=False).head(3)
            top_assets_by_club[str(c_short)] = [f"{row['web_name']} (£{row['now_cost']:.1f}m)" for _, row in top_p.iterrows()]

    alerts: List[FixtureWaveAlert] = []

    for c_short, prof in club_profiles.items():
        fdr_vec = prof.fdr_vector[:horizon]
        n_gws = len(fdr_vec)
        if n_gws < 3:
            continue

        best_green_run: Optional[Tuple[int, int, float]] = None
        best_red_run: Optional[Tuple[int, int, float]] = None

        # Scan all window lengths from 3 to n_gws
        for length in range(3, n_gws + 1):
            for start_idx in range(n_gws - length + 1):
                end_idx = start_idx + length
                sub_fdr = fdr_vec[start_idx:end_idx]
                avg_val = sum(sub_fdr) / length

                # Check Green Wave
                if avg_val <= thresh_green:
                    if best_green_run is None or (length >= best_green_run[1] - best_green_run[0] and avg_val < best_green_run[2]):
                        best_green_run = (start_idx, end_idx, avg_val)

                # Check Red Cliff
                if avg_val >= thresh_red:
                    if best_red_run is None or (length >= best_red_run[1] - best_red_run[0] and avg_val > best_red_run[2]):
                        best_red_run = (start_idx, end_idx, avg_val)

        # Build Alert if Green Wave detected
        if best_green_run is not None:
            s_idx, e_idx, avg_fdr = best_green_run
            s_gw = target_gws[s_idx]
            e_gw = target_gws[e_idx - 1]
            dur = e_idx - s_idx
            inflection = max(current_gw, s_gw - 1)
            rec_action = "ACCUMULATE" if s_gw > next_gw else "HOLD"
            assets = tuple(top_assets_by_club.get(c_short, []))
            rationale = (
                f"Favorable {dur}-match schedule run (GW{s_gw}-GW{e_gw}) with average FDR {avg_fdr:.2f}. "
                f"High potential for clean sheets and attacking returns."
            )
            alerts.append(FixtureWaveAlert(
                club_short=c_short,
                club_name=prof.club_name,
                regime_type="GREEN_WAVE",
                start_gw=s_gw,
                end_gw=e_gw,
                duration_gws=dur,
                avg_fdr=round(avg_fdr, 2),
                recommended_action=rec_action,
                inflection_gw=inflection,
                key_assets=assets,
                rationale=rationale,
            ))

        # Build Alert if Red Cliff detected
        if best_red_run is not None:
            s_idx, e_idx, avg_fdr = best_red_run
            s_gw = target_gws[s_idx]
            e_gw = target_gws[e_idx - 1]
            dur = e_idx - s_idx
            inflection = max(current_gw, s_gw - 1)
            rec_action = "LIQUIDATE" if s_gw <= next_gw + 1 else "AVOID"
            assets = tuple(top_assets_by_club.get(c_short, []))
            rationale = (
                f"Severe {dur}-match difficulty spike (GW{s_gw}-GW{e_gw}) with average FDR {avg_fdr:.2f}. "
                f"Elevated risk of blanking and price erosion."
            )
            alerts.append(FixtureWaveAlert(
                club_short=c_short,
                club_name=prof.club_name,
                regime_type="RED_CLIFF",
                start_gw=s_gw,
                end_gw=e_gw,
                duration_gws=dur,
                avg_fdr=round(avg_fdr, 2),
                recommended_action=rec_action,
                inflection_gw=inflection,
                key_assets=assets,
                rationale=rationale,
            ))

    # Sort alerts: Green Waves first (lowest FDR), then Red Cliffs (highest FDR)
    green_alerts = [a for a in alerts if a.regime_type == "GREEN_WAVE"]
    green_alerts.sort(key=lambda x: x.avg_fdr)
    red_alerts = [a for a in alerts if a.regime_type == "RED_CLIFF"]
    red_alerts.sort(key=lambda x: x.avg_fdr, reverse=True)

    return green_alerts + red_alerts


def find_optimal_defensive_rotation_pairs(
    club_profiles: Optional[Dict[str, ClubScheduleProfile]] = None,
    horizon: int = 8,
    max_cost: float = 4.5,
    top_k: int = 5,
    fpl_client: Optional[FPLClient] = None
) -> List[DefensiveRotationPair]:
    """
    Combinatorially evaluates all 190 Premier League 2-club combinations to find
    pairs that optimize home fixtures and easy schedule difficulty for budget defenders.
    """
    client = fpl_client or FPLClient()
    if club_profiles is None:
        club_profiles = build_club_schedule_profiles(fpl_client=client, horizon=horizon)

    current_gw = client.get_current_gameweek() or 1
    next_gw = current_gw + 1
    target_gws = [next_gw + i for i in range(horizon)]

    # Fetch budget defenders (<= max_cost) grouped by club
    players_df = client.get_players_df()
    budget_defs_by_club: Dict[str, List[Tuple[str, float]]] = {}
    if not players_df.empty:
        defs_df = players_df[(players_df["position_name"] == "DEF") & (players_df["now_cost"] <= max_cost + 0.1)]
        for c_short, group in defs_df.groupby("club_short"):
            # Sort by form / minutes descending
            sorted_p = group.sort_values(by="minutes", ascending=False).head(2)
            budget_defs_by_club[str(c_short)] = [(str(row["web_name"]), float(row["now_cost"])) for _, row in sorted_p.iterrows()]

    clubs = list(club_profiles.keys())
    pairs_evaluated: List[Tuple[float, DefensiveRotationPair]] = []

    for c_a, c_b in itertools.combinations(clubs, 2):
        prof_a = club_profiles[c_a]
        prof_b = club_profiles[c_b]

        combined_schedule: List[Tuple[int, str, str, bool, float]] = []
        home_count = 0
        easy_count = 0
        fdr_sum = 0.0

        for t_step in range(horizon):
            gw = target_gws[t_step]
            fdr_a = prof_a.fdr_vector[t_step]
            fdr_b = prof_b.fdr_vector[t_step]
            home_a = prof_a.is_home[t_step]
            home_b = prof_b.is_home[t_step]
            opp_a = prof_a.opponents[t_step]
            opp_b = prof_b.opponents[t_step]

            # Selection Logic:
            # 1. Lower FDR wins
            # 2. If FDR tied, Home match wins
            # 3. Else default to Club A
            if fdr_a < fdr_b:
                chosen_club, chosen_opp, chosen_home, chosen_fdr = c_a, opp_a, home_a, fdr_a
            elif fdr_b < fdr_a:
                chosen_club, chosen_opp, chosen_home, chosen_fdr = c_b, opp_b, home_b, fdr_b
            else:
                if home_a and not home_b:
                    chosen_club, chosen_opp, chosen_home, chosen_fdr = c_a, opp_a, home_a, fdr_a
                elif home_b and not home_a:
                    chosen_club, chosen_opp, chosen_home, chosen_fdr = c_b, opp_b, home_b, fdr_b
                else:
                    chosen_club, chosen_opp, chosen_home, chosen_fdr = c_a, opp_a, home_a, fdr_a

            combined_schedule.append((gw, chosen_club, chosen_opp, chosen_home, chosen_fdr))
            if chosen_home:
                home_count += 1
            if chosen_fdr <= 2.5:
                easy_count += 1
            fdr_sum += chosen_fdr

        home_ratio = home_count / horizon
        easy_ratio = easy_count / horizon
        avg_fdr = fdr_sum / horizon

        # Pair Score: higher easy %, higher home %, lower avg FDR
        score = (easy_ratio * 0.45) + (home_ratio * 0.35) + (((5.0 - avg_fdr) / 5.0) * 0.20)

        # Budget defender recommendations
        defs_a = budget_defs_by_club.get(c_a, [(f"{c_a} Defender", 4.5)])
        defs_b = budget_defs_by_club.get(c_b, [(f"{c_b} Defender", 4.5)])
        sample_defs = tuple(defs_a[:1] + defs_b[:1])

        pair_obj = DefensiveRotationPair(
            club_a_short=c_a,
            club_b_short=c_b,
            combined_home_ratio=round(home_ratio, 3),
            combined_easy_ratio=round(easy_ratio, 3),
            combined_avg_fdr=round(avg_fdr, 2),
            combined_schedule=tuple(combined_schedule),
            budget_sample_defenders=sample_defs,
        )
        pairs_evaluated.append((score, pair_obj))

    # Sort descending by synergy score
    pairs_evaluated.sort(key=lambda x: x[0], reverse=True)
    return [p[1] for p in pairs_evaluated[:top_k]]


def audit_squad_waves(
    squad_player_ids: Optional[Tuple[int, ...]] = None,
    club_profiles: Optional[Dict[str, ClubScheduleProfile]] = None,
    horizon: int = 8,
    fpl_client: Optional[FPLClient] = None
) -> List[SquadWaveAudit]:
    """
    Audits active squad players against upcoming fixture regimes, flagging liquidation
    cliffs, hold windows, and accumulation priorities.
    """
    client = fpl_client or FPLClient()
    if club_profiles is None:
        club_profiles = build_club_schedule_profiles(fpl_client=client, horizon=horizon)

    if squad_player_ids is None:
        sq_state = build_strategic_squad_state(fpl_client=client)
        squad_player_ids = sq_state.squad_player_ids

    players_df = client.get_players_df()
    wave_alerts = scan_fixture_waves(club_profiles=club_profiles, horizon=horizon, fpl_client=client)
    wave_map_green = {a.club_short: a for a in wave_alerts if a.regime_type == "GREEN_WAVE"}
    wave_map_red = {a.club_short: a for a in wave_alerts if a.regime_type == "RED_CLIFF"}

    audit_records: List[SquadWaveAudit] = []

    for pid in squad_player_ids:
        match_p = players_df[players_df["id"] == pid]
        if match_p.empty:
            continue
        row = match_p.iloc[0]
        c_short = str(row["club_short"])
        cost = float(row["now_cost"])
        pos = str(row["position_name"])
        name = str(row["web_name"])

        c_prof = club_profiles.get(c_short)
        fdr_next_5 = sum(c_prof.fdr_vector[:5]) / 5.0 if c_prof else 3.0

        green_alert = wave_map_green.get(c_short)
        red_alert = wave_map_red.get(c_short)

        if green_alert:
            regime = "GREEN_WAVE"
            label = f"🌊 Wave (GW{green_alert.start_gw}-{green_alert.end_gw}, avg {green_alert.avg_fdr:.1f})"
            priority = "HOLD_HARVEST"
        elif red_alert:
            regime = "RED_CLIFF"
            label = f"⚠️ Cliff (GW{red_alert.start_gw}-{red_alert.end_gw}, avg {red_alert.avg_fdr:.1f})"
            # If expensive asset approaching cliff, prioritize sell
            priority = "URGENT_SELL" if cost >= 6.0 else "WATCH_EXIT"
        else:
            regime = "NEUTRAL"
            label = f"➡️ Stable (avg FDR {fdr_next_5:.1f})"
            priority = "HOLD_HARVEST"

        audit_records.append(SquadWaveAudit(
            element_id=pid,
            web_name=name,
            club_short=c_short,
            position_name=pos,
            now_cost=cost,
            current_regime=regime,
            alert_label=label,
            action_priority=priority,
            next_5_fdr=round(fdr_next_5, 2),
        ))

    # Sort: URGENT_SELL first, then by now_cost descending
    priority_order = {"URGENT_SELL": 0, "WATCH_EXIT": 1, "HOLD_HARVEST": 2, "BUY_TARGET": 3}
    audit_records.sort(key=lambda x: (priority_order.get(x.action_priority, 9), -x.now_cost))
    return audit_records
