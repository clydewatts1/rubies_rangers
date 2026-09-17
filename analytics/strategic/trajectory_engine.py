"""
Multi-Horizon Trajectory Engine for Strategic Quantitative FPL Analytics.
Generates dense (N_players x H_gameweeks) expectation tensors, venue-calibrated
club schedules, and immutable domain contracts in compliance with .agents/rules/moneyball_strategy.md.
"""

from __future__ import annotations
import math
import time
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from config_manager import get_params, get_system_config
from clients.fpl_client import FPLClient
from analytics.strategic.contracts import (
    PlayerTrajectoryProfile,
    ClubScheduleProfile,
    StrategicSquadState,
)


class TrajectoryEngine:
    """
    High-performance engine that computes multi-horizon expectation trajectories
    across all Premier League players and clubs for H future gameweeks.
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
        self._club_profiles_cache: Optional[Dict[str, ClubScheduleProfile]] = None
        self._player_profiles_cache: Optional[Dict[int, PlayerTrajectoryProfile]] = None
        self._last_computed: float = 0.0

    def get_club_profiles(
        self,
        horizon: Optional[int] = None,
        force_refresh: bool = False
    ) -> Dict[str, ClubScheduleProfile]:
        """Retrieve multi-horizon club schedule profiles."""
        h = horizon or self.default_horizon
        if not force_refresh and self._club_profiles_cache is not None:
            # Verify horizon length matches
            first_prof = next(iter(self._club_profiles_cache.values()), None)
            if first_prof and len(first_prof.fdr_vector) == h:
                return self._club_profiles_cache

        profiles = build_club_schedule_profiles(
            fpl_client=self.client,
            horizon=h,
            profile=self.profile
        )
        self._club_profiles_cache = profiles
        return profiles

    def get_player_profiles(
        self,
        horizon: Optional[int] = None,
        force_refresh: bool = False
    ) -> Dict[int, PlayerTrajectoryProfile]:
        """Retrieve multi-horizon player trajectory profiles."""
        h = horizon or self.default_horizon
        if not force_refresh and self._player_profiles_cache is not None:
            first_prof = next(iter(self._player_profiles_cache.values()), None)
            if first_prof and len(first_prof.xp_trajectory) == h:
                return self._player_profiles_cache

        club_profs = self.get_club_profiles(horizon=h, force_refresh=force_refresh)
        player_profs = build_player_trajectory_profiles(
            fpl_client=self.client,
            club_profiles=club_profs,
            horizon=h,
            profile=self.profile
        )
        self._player_profiles_cache = player_profs
        return player_profs

    def get_xp_matrix(
        self,
        player_ids: List[int],
        horizon: Optional[int] = None
    ) -> np.ndarray:
        """
        Extract a dense NumPy matrix of shape (len(player_ids), horizon)
        representing expected points across the planning horizon.
        """
        h = horizon or self.default_horizon
        profiles = self.get_player_profiles(horizon=h)
        matrix = np.zeros((len(player_ids), h), dtype=np.float64)
        for idx, pid in enumerate(player_ids):
            prof = profiles.get(pid)
            if prof:
                matrix[idx, :] = np.array(prof.xp_trajectory[:h], dtype=np.float64)
        return matrix

    def get_squad_state(
        self,
        entry_id: Optional[int] = None
    ) -> StrategicSquadState:
        """Retrieve current manager squad state and balance sheet liquidity."""
        return build_strategic_squad_state(fpl_client=self.client, entry_id=entry_id)


def build_club_schedule_profiles(
    fpl_client: Optional[FPLClient] = None,
    horizon: int = 8,
    profile: Optional[str] = None
) -> Dict[str, ClubScheduleProfile]:
    """
    Constructs multi-horizon fixture schedules and dynamic Poisson strength ratings
    for all 20 Premier League clubs across H gameweeks.
    """
    client = fpl_client or FPLClient()
    boot = client.get_bootstrap_data()
    fixtures = client.get_fixtures_data()
    current_gw = client.get_current_gameweek() or 1
    next_gw = current_gw + 1
    target_gws = [next_gw + i for i in range(horizon)]

    # Load strategic parameters with graceful fallbacks
    strat_cfg = get_params("strategic", profile=profile) or {}
    venue_cfg = strat_cfg.get("venue", {})
    nu_att_home = float(venue_cfg.get("nu_att_home", 1.15))
    nu_att_away = float(venue_cfg.get("nu_att_away", 0.87))
    nu_def_home = float(venue_cfg.get("nu_def_home", 0.85))
    nu_def_away = float(venue_cfg.get("nu_def_away", 1.18))
    kappa_cs_scale = float(strat_cfg.get("defense", {}).get("kappa_cs_scale", 1.00))

    teams_data = boot.get("teams", [])
    team_id_to_short = {t["id"]: t["short_name"] for t in teams_data}
    team_id_to_name = {t["id"]: t["name"] for t in teams_data}
    team_short_to_id = {t["short_name"]: t["id"] for t in teams_data}

    # 1. Compute Base Club Dynamic Strength Ratings (alpha_c, delta_c)
    # Preferentially calibrated from ClubElo ratings, falling back to FPL API strength
    attack_ratings: Dict[int, float] = {}
    defense_concessions: Dict[int, float] = {}

    elo_ratings = {}
    try:
        from clients.clubelo_client import ClubEloClient
        elo_client = ClubEloClient()
        elo_ratings = elo_client.get_epl_ratings()
    except Exception:
        elo_ratings = {}

    for t in teams_data:
        t_id = t["id"]
        club_short = team_id_to_short.get(t_id, "")
        elo_rec = elo_ratings.get(club_short)

        if elo_rec and elo_rec.elo > 1000.0:
            # Elo normalized around 1800.0 (Premier League median ~ 1800)
            norm_elo = elo_rec.elo / 1800.0
            attack_ratings[t_id] = round(norm_elo * 1.35, 3)
            defense_concessions[t_id] = round((1.0 / max(0.6, norm_elo)) * 1.00, 3)
        else:
            # Strength ratings from FPL API (scale 1000-1400) normalized around 1.35 goals/match
            att_h = float(t.get("strength_attack_home", 1150))
            att_a = float(t.get("strength_attack_away", 1150))
            def_h = float(t.get("strength_defence_home", 1150))
            def_a = float(t.get("strength_defence_away", 1150))

            avg_att = (att_h + att_a) / 2300.0  # Normalized ~ 1.0
            avg_def = (def_h + def_a) / 2300.0  # Higher defence rating means FEWER goals conceded
            def_concession = 1.0 / max(0.6, avg_def)  # Inverse: higher concession = leakier defense

            attack_ratings[t_id] = round(avg_att * 1.35, 3)
            defense_concessions[t_id] = round(def_concession * 1.00, 3)

    # 2. Extract Fixture Sequences for each GW in Target Horizon
    # Map (team_id, gw) -> fixture info
    gw_fixture_map: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for f in fixtures:
        gw = f.get("event")
        if gw in target_gws:
            h_id = f["team_h"]
            a_id = f["team_a"]
            h_diff = float(f.get("team_h_difficulty", 3))
            a_diff = float(f.get("team_a_difficulty", 3))

            gw_fixture_map[(h_id, gw)] = {
                "opp_id": a_id,
                "opp_short": team_id_to_short.get(a_id, "UNK"),
                "is_home": True,
                "difficulty": h_diff,
            }
            gw_fixture_map[(a_id, gw)] = {
                "opp_id": h_id,
                "opp_short": team_id_to_short.get(h_id, "UNK"),
                "is_home": False,
                "difficulty": a_diff,
            }

    # 3. Construct ClubScheduleProfile for each club
    profiles: Dict[str, ClubScheduleProfile] = {}

    for t in teams_data:
        t_id = t["id"]
        club_short = t["short_name"]
        club_name = t["name"]

        fdr_list: List[float] = []
        opp_list: List[str] = []
        is_home_list: List[bool] = []
        cs_prob_list: List[float] = []
        exp_goals_scored_list: List[float] = []
        exp_goals_conceded_list: List[float] = []

        alpha_self = attack_ratings.get(t_id, 1.35)
        delta_self = defense_concessions.get(t_id, 1.00)

        for gw in target_gws:
            fix = gw_fixture_map.get((t_id, gw))
            if fix:
                opp_id = fix["opp_id"]
                opp_short = fix["opp_short"]
                is_h = fix["is_home"]
                diff = fix["difficulty"]

                alpha_opp = attack_ratings.get(opp_id, 1.35)
                delta_opp = defense_concessions.get(opp_id, 1.00)

                # Venue modulation
                nu_att = nu_att_home if is_h else nu_att_away
                nu_def = nu_def_home if is_h else nu_def_away

                # Expected Goals Scored & Conceded
                exp_scored = round(alpha_self * delta_opp * nu_att, 2)
                exp_conceded = round(alpha_opp * delta_self * nu_def, 2)

                # Clean Sheet Probability: exp(-exp_conceded * kappa)
                cs_prob = round(float(np.clip(math.exp(-exp_conceded * kappa_cs_scale), 0.01, 0.95)), 3)

                fdr_list.append(diff)
                opp_list.append(opp_short)
                is_home_list.append(is_h)
                cs_prob_list.append(cs_prob)
                exp_goals_scored_list.append(exp_scored)
                exp_goals_conceded_list.append(exp_conceded)
            else:
                # Blank Gameweek (0 matches)
                fdr_list.append(3.0)
                opp_list.append("BLANK")
                is_home_list.append(False)
                cs_prob_list.append(0.0)
                exp_goals_scored_list.append(0.0)
                exp_goals_conceded_list.append(0.0)

        profiles[club_short] = ClubScheduleProfile(
            club_short=club_short,
            club_name=club_name,
            fdr_vector=tuple(fdr_list),
            opponents=tuple(opp_list),
            is_home=tuple(is_home_list),
            clean_sheet_probs=tuple(cs_prob_list),
            expected_goals_scored=tuple(exp_goals_scored_list),
            expected_goals_conceded=tuple(exp_goals_conceded_list),
        )

    return profiles


def build_player_trajectory_profiles(
    fpl_client: Optional[FPLClient] = None,
    club_profiles: Optional[Dict[str, ClubScheduleProfile]] = None,
    horizon: int = 8,
    profile: Optional[str] = None
) -> Dict[int, PlayerTrajectoryProfile]:
    """
    Computes the dense (N_players x H_gameweeks) expectation tensor via vectorized
    NumPy operations and produces immutable PlayerTrajectoryProfile objects.
    """
    client = fpl_client or FPLClient()
    boot = client.get_bootstrap_data()
    elements = boot.get("elements", [])
    teams_data = boot.get("teams", [])
    pos_map = {p["id"]: p["singular_name_short"] for p in boot.get("element_types", [])}
    team_short_map = {t["id"]: t["short_name"] for t in teams_data}

    if club_profiles is None:
        club_profiles = build_club_schedule_profiles(
            fpl_client=client,
            horizon=horizon,
            profile=profile
        )

    strat_cfg = get_params("strategic", profile=profile) or {}
    venue_cfg = strat_cfg.get("venue", {})
    nu_att_home = float(venue_cfg.get("nu_att_home", 1.15))
    nu_att_away = float(venue_cfg.get("nu_att_away", 0.87))
    momentum_weight = float(strat_cfg.get("market", {}).get("momentum_weight", 0.20))

    # Point rules
    pts_goal_map = {"GKP": 10.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}
    pts_cs_map = {"GKP": 4.0, "DEF": 4.0, "MID": 1.0, "FWD": 0.0}
    pts_ast = 3.0
    pts_app_60 = 2.0

    # Extract arrays for vectorized computation
    n_players = len(elements)
    element_ids = np.zeros(n_players, dtype=np.int32)
    costs = np.zeros(n_players, dtype=np.float64)
    xg90_arr = np.zeros(n_players, dtype=np.float64)
    xa90_arr = np.zeros(n_players, dtype=np.float64)
    mins_exp_arr = np.zeros(n_players, dtype=np.float64)
    bonus_exp_arr = np.zeros(n_players, dtype=np.float64)
    cards_exp_arr = np.zeros(n_players, dtype=np.float64)
    pts_goal_arr = np.zeros(n_players, dtype=np.float64)
    pts_cs_arr = np.zeros(n_players, dtype=np.float64)
    momentum_arr = np.zeros(n_players, dtype=np.float64)
    chances_arr = np.zeros(n_players, dtype=np.float64)

    # String & club lookups per player
    web_names: List[str] = []
    full_names: List[str] = []
    club_shorts: List[str] = []
    pos_names: List[str] = []
    statuses: List[str] = []

    price_cfg = get_params("moneyball", profile=profile).get("price_prediction", {})
    rise_base = price_cfg.get("rise_thresh_base", 75000)
    rise_frac = price_cfg.get("rise_selected_frac", 0.075)

    for i, p in enumerate(elements):
        p_id = p["id"]
        element_ids[i] = p_id
        cost = p["now_cost"] / 10.0
        costs[i] = cost

        pos_str = pos_map.get(p["element_type"], "MID")
        pos_names.append(pos_str)
        pts_goal_arr[i] = pts_goal_map.get(pos_str, 5.0)
        pts_cs_arr[i] = pts_cs_map.get(pos_str, 0.0)

        club_id = p["team"]
        c_short = team_short_map.get(club_id, "UNK")
        club_shorts.append(c_short)
        web_names.append(p.get("web_name", "Unknown"))
        full_names.append(f"{p.get('first_name', '')} {p.get('second_name', '')}".strip())
        statuses.append(p.get("status", "a"))

        # Underlying rates
        xg90 = float(p.get("expected_goals_per_90") or 0.0)
        xa90 = float(p.get("expected_assists_per_90") or 0.0)
        if xg90 == 0.0 and float(p.get("expected_goals") or 0.0) > 0:
            mins = float(p.get("minutes") or 0)
            if mins > 0:
                xg90 = (float(p.get("expected_goals")) / mins) * 90.0
        if xa90 == 0.0 and float(p.get("expected_assists") or 0.0) > 0:
            mins = float(p.get("minutes") or 0)
            if mins > 0:
                xa90 = (float(p.get("expected_assists")) / mins) * 90.0

        xg90_arr[i] = min(2.0, xg90)
        xa90_arr[i] = min(1.5, xa90)

        # Minutes Expectation
        mins_played = float(p.get("minutes") or 0)
        starts = float(p.get("starts") or 0)
        chance = p.get("chance_of_playing_next_round")
        chance_val = float(chance) if chance is not None else 100.0
        chances_arr[i] = chance_val

        if p.get("status") in ["i", "u"]:
            exp_mins = 0.0
        elif chance_val == 0.0:
            exp_mins = 0.0
        elif starts >= 3 or mins_played >= 270:
            exp_mins = 80.0 * (chance_val / 100.0)
        elif starts >= 1 or mins_played >= 90:
            exp_mins = 55.0 * (chance_val / 100.0)
        elif mins_played > 0:
            exp_mins = 25.0 * (chance_val / 100.0)
        else:
            exp_mins = 5.0 * (chance_val / 100.0)

        mins_exp_arr[i] = exp_mins

        # Bonus & Card rates
        bps_per_90 = float(p.get("bps") or 0) / (mins_played / 90.0) if mins_played > 90 else 10.0
        bonus_exp_arr[i] = min(1.2, max(0.0, (bps_per_90 - 15.0) * 0.05))
        yc = float(p.get("yellow_cards") or 0)
        cards_exp_arr[i] = min(0.3, (yc / (mins_played / 90.0) * 0.15) if mins_played > 90 else 0.05)

        # Price momentum progress
        tin = float(p.get("transfers_in_event") or 0)
        tout = float(p.get("transfers_out_event") or 0)
        net_t = tin - tout
        sel = float(p.get("selected") or 1000)
        r_thresh = max(rise_base, sel * rise_frac)
        momentum_arr[i] = round(max(-100.0, min(100.0, (net_t / r_thresh) * 100.0)), 1)

    # 4. Vectorized Multi-Horizon Tensor Computation
    # xp_tensor shape: (n_players, horizon)
    xp_tensor = np.zeros((n_players, horizon), dtype=np.float64)

    # Pre-build lookup matrices from club profiles
    cs_matrix = np.zeros((n_players, horizon), dtype=np.float64)
    venue_att_matrix = np.ones((n_players, horizon), dtype=np.float64)
    opp_concession_matrix = np.ones((n_players, horizon), dtype=np.float64)

    club_profile_dict = club_profiles

    for i in range(n_players):
        c_short = club_shorts[i]
        c_prof = club_profile_dict.get(c_short)
        if c_prof:
            for t_step in range(horizon):
                if t_step < len(c_prof.clean_sheet_probs):
                    cs_matrix[i, t_step] = c_prof.clean_sheet_probs[t_step]
                    is_h = c_prof.is_home[t_step]
                    venue_att_matrix[i, t_step] = nu_att_home if is_h else nu_att_away
                    opp_short = c_prof.opponents[t_step]
                    opp_prof = club_profile_dict.get(opp_short)
                    if opp_prof and t_step < len(opp_prof.expected_goals_conceded):
                        # Concession factor relative to 1.35 baseline
                        opp_concession_matrix[i, t_step] = max(0.5, opp_prof.expected_goals_conceded[t_step] / 1.35)

    # Vectorized expectation formula across entire universe
    min_fraction = np.clip(mins_exp_arr[:, None] / 90.0, 0.0, 1.0)
    lambda_goal = xg90_arr[:, None] * opp_concession_matrix * venue_att_matrix
    lambda_ast = xa90_arr[:, None] * opp_concession_matrix * venue_att_matrix

    raw_xp = min_fraction * (
        pts_app_60
        + (pts_goal_arr[:, None] * lambda_goal)
        + (pts_ast * lambda_ast)
        + (pts_cs_arr[:, None] * cs_matrix)
        + bonus_exp_arr[:, None]
        - cards_exp_arr[:, None]
    )

    # Apply slight market momentum alpha modulation (+/- 5%) if enabled
    momentum_mod = 1.0 + (momentum_weight * (momentum_arr[:, None] / 1000.0))
    xp_tensor = np.clip(np.round(raw_xp * momentum_mod, 2), 0.0, 25.0)

    # 5. Build Final Immutable PlayerTrajectoryProfile objects
    player_profiles: Dict[int, PlayerTrajectoryProfile] = {}

    for i in range(n_players):
        p_id = int(element_ids[i])
        c_short = club_shorts[i]
        c_prof = club_profile_dict.get(c_short)

        fdr_traj = c_prof.fdr_vector[:horizon] if c_prof else tuple([3.0] * horizon)
        opp_traj = c_prof.opponents[:horizon] if c_prof else tuple(["UNK"] * horizon)
        home_traj = c_prof.is_home[:horizon] if c_prof else tuple([True] * horizon)

        player_profiles[p_id] = PlayerTrajectoryProfile(
            element_id=p_id,
            web_name=web_names[i],
            full_name=full_names[i],
            club_short=c_short,
            position_name=pos_names[i],
            now_cost=float(costs[i]),
            xp_trajectory=tuple(float(x) for x in xp_tensor[i, :]),
            fdr_trajectory=fdr_traj,
            opponents=opp_traj,
            is_home=home_traj,
            minutes_expectation=round(float(mins_exp_arr[i]), 1),
            price_change_momentum=float(momentum_arr[i]),
            chance_of_playing=float(chances_arr[i]),
            status=statuses[i],
        )

    return player_profiles


def build_strategic_squad_state(
    fpl_client: Optional[FPLClient] = None,
    entry_id: Optional[int] = None
) -> StrategicSquadState:
    """
    Constructs an immutable StrategicSquadState representing active squad picks,
    bank liquidity, and Free Transfers in hand.
    """
    client = fpl_client or FPLClient()
    current_gw = client.get_current_gameweek() or 1
    sys_entry_id = entry_id or get_system_config("default_entry_id") or 6173410
    default_squad = get_system_config("default_squad") or []
    default_bank = float(get_system_config("default_bank") or 3.7)

    # Check if AuthManager has live team data
    live_picks: List[int] = []
    live_bank = default_bank
    live_ft = 1
    chips: List[str] = ["wildcard", "freehit", "bboost", "3xc"]

    try:
        from clients.auth_manager import get_auth_manager
        auth_mgr = get_auth_manager()
        session = auth_mgr.get_active_session()
        if session and session.team_state:
            t_state = session.team_state
            live_picks = list(t_state.picks) if t_state.picks else []
            live_bank = t_state.bank
            live_ft = t_state.transfers_available
            if t_state.chips:
                chips = [c for c, status in t_state.chips.items() if status.get("status_for_entry") == "available"]
    except Exception:
        pass

    # Fallback to resolving squad names if live picks are empty
    boot = client.get_bootstrap_data()
    elements = boot.get("elements", [])
    el_map = {p["id"]: p for p in elements}
    name_to_id = {p["web_name"].lower(): p["id"] for p in elements}
    full_to_id = {f"{p.get('first_name', '')} {p.get('second_name', '')}".strip().lower(): p["id"] for p in elements}

    resolved_ids: List[int] = []
    resolved_names: List[str] = []

    if live_picks:
        for pid in live_picks:
            p_obj = el_map.get(pid)
            if p_obj:
                resolved_ids.append(pid)
                resolved_names.append(p_obj.get("web_name", f"Player_{pid}"))
    else:
        for s_name in default_squad:
            s_clean = s_name.lower().strip()
            pid = name_to_id.get(s_clean) or full_to_id.get(s_clean)
            if pid:
                p_obj = el_map.get(pid)
                resolved_ids.append(pid)
                resolved_names.append(p_obj.get("web_name", s_name) if p_obj else s_name)

    # Compute team value
    team_val = sum((el_map.get(pid, {}).get("now_cost", 50) / 10.0) for pid in resolved_ids) + live_bank

    return StrategicSquadState(
        squad_player_ids=tuple(resolved_ids),
        squad_player_names=tuple(resolved_names),
        bank_balance=round(float(live_bank), 2),
        free_transfers_available=int(max(1, min(5, live_ft))),
        chips_available=tuple(chips),
        team_value=round(float(team_val), 2),
        gameweek=int(current_gw),
    )
