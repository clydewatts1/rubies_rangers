"""
analytics/challenge/picker.py
Modular, shared squad selection service for FPL Challenge.
Chains Two-Stage MILP screening and Monte Carlo tournament simulation.
Produces ready-to-transmit picks payloads with captaincy and element IDs.
Shared identically by Streamlit UI tabs and Autonomous Challenge CPN.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np

from analytics.challenge.contracts import (
    ChallengeRuleSet,
    ChallengeOptimalSquad,
    EvaluatedChallengeCandidate,
    ChallengeTournamentReport,
)
from analytics.challenge.two_stage_optimizer import ChallengeTwoStageOptimizer

logger = logging.getLogger("rubies_rangers.challenge.picker")


@dataclass(frozen=True)
class ChallengePickerConfig:
    """Configuration options driving the Challenge squad picker."""
    archetype: str = "max_ev"                    # "max_ev" (Balanced), "safe_floor", "gpp_upside"
    n_simulations: int = 2500                   # Monte Carlo draws (1,000 to 10,000)
    lock_players: Optional[List[str]] = None    # Players forced into squad
    exclude_players: Optional[List[str]] = None # Players barred from selection
    available_only: bool = True                 # Filter to available starters
    random_seed: int = 42


@dataclass(frozen=True)
class ChallengePickerResult:
    """Comprehensive output of the Challenge picker process."""
    selected_squad: ChallengeOptimalSquad
    evaluated_candidate: EvaluatedChallengeCandidate
    archetype_chosen: str
    squad_elements: List[Dict[str, Any]]
    element_ids: List[int]
    captain_id: int
    vice_captain_id: int
    picks_payload: Dict[str, Any]
    tournament_report: ChallengeTournamentReport

    @property
    def summary_str(self) -> str:
        names = ", ".join(self.selected_squad.squad_names)
        return (
            f"Archetype: {self.archetype_chosen.upper()} | "
            f"Squad ({len(self.selected_squad.squad_names)}): {names} | "
            f"C: {self.selected_squad.captain} | VC: {self.selected_squad.vice_captain} | "
            f"EV: {self.evaluated_candidate.mean_points:.1f} pts | "
            f"P99: {self.evaluated_candidate.tournament_p99:.1f} pts"
        )


class ChallengePicker:
    """
    Stateless functional service that executes Stage 1 MILP Screening + Stage 2 Monte Carlo Simulation
    and crowns the designated strategic archetype with full element-level payload resolution.
    """

    @classmethod
    def pick_challenge_squad(
        cls,
        players_df: pd.DataFrame,
        rule_set: ChallengeRuleSet,
        fixtures: Optional[List[Dict[str, Any]]] = None,
        config: Optional[ChallengePickerConfig] = None
    ) -> ChallengePickerResult:
        """
        Executes the two-stage tournament optimization and extracts the target archetype.
        Maps player names to database element IDs and generates the official FPL Challenge picks payload.
        """
        cfg = config or ChallengePickerConfig()
        logger.info(
            "[ChallengePicker] Running two-stage solver for GW%d '%s' (Archetype: %s, Sims: %d)",
            rule_set.gameweek, rule_set.name, cfg.archetype, cfg.n_simulations
        )

        engine = ChallengeTwoStageOptimizer(
            players_df=players_df,
            rule_set=rule_set,
            fixtures=fixtures,
            random_seed=cfg.random_seed
        )

        report = engine.run_tournament(
            n_simulations=cfg.n_simulations,
            lock_players=cfg.lock_players,
            exclude_players=cfg.exclude_players,
            available_only=cfg.available_only
        )

        if not report.evaluated_candidates:
            raise ValueError(
                f"No mathematically feasible Challenge squads found for GW{rule_set.gameweek} with active constraints."
            )

        # Select crowned candidate based on requested archetype
        archetype_key = cfg.archetype.lower().strip()
        candidate_eval: EvaluatedChallengeCandidate

        if archetype_key in ("safe_floor", "floor", "safety"):
            candidate_eval = report.winner_safe_floor or report.evaluated_candidates[0]
            archetype_name = "safe_floor"
        elif archetype_key in ("gpp_upside", "gpp", "upside", "p99", "ceiling"):
            candidate_eval = report.winner_gpp_upside or report.evaluated_candidates[0]
            archetype_name = "gpp_upside"
        else:  # default to max_ev
            candidate_eval = report.winner_balanced or report.evaluated_candidates[0]
            archetype_name = "max_ev"

        squad = candidate_eval.candidate

        # Build Element Mapping & Payload
        element_details, element_ids, cap_id, vc_id, payload = cls._resolve_element_payload(
            players_df=players_df,
            squad_names=squad.squad_names,
            captain_name=squad.captain,
            vice_captain_name=squad.vice_captain
        )

        result = ChallengePickerResult(
            selected_squad=squad,
            evaluated_candidate=candidate_eval,
            archetype_chosen=archetype_name,
            squad_elements=element_details,
            element_ids=element_ids,
            captain_id=cap_id,
            vice_captain_id=vc_id,
            picks_payload=payload,
            tournament_report=report
        )

        logger.info("[ChallengePicker] Selected squad: %s", result.summary_str)
        return result

    @classmethod
    def _resolve_element_payload(
        cls,
        players_df: pd.DataFrame,
        squad_names: List[str],
        captain_name: str,
        vice_captain_name: str
    ) -> Tuple[List[Dict[str, Any]], List[int], int, int, Dict[str, Any]]:
        """
        Maps squad player names to unique element IDs in players_df,
        resolves captain/vice-captain IDs, and generates the FPL Challenge picks payload.
        """
        df = players_df.copy()
        if "web_name" not in df.columns:
            df["web_name"] = df.get("name", "Unknown")

        # Create quick lookup by web_name (prioritizing highest xP or moneyball score)
        sort_col = "xP" if "xP" in df.columns else ("moneyball_score" if "moneyball_score" in df.columns else None)
        if sort_col:
            df_sorted = df.sort_values(by=sort_col, ascending=False)
        else:
            df_sorted = df

        lookup = df_sorted.drop_duplicates(subset=["web_name"]).set_index("web_name").to_dict(orient="index")

        element_details: List[Dict[str, Any]] = []
        element_ids: List[int] = []

        for name in squad_names:
            p_data = lookup.get(name, {})
            eid = int(p_data.get("id", len(element_ids) + 1))
            element_ids.append(eid)
            element_details.append({
                "id": eid,
                "web_name": name,
                "position": p_data.get("position_name") or p_data.get("position", "MID"),
                "club": p_data.get("club_name") or p_data.get("club_short") or p_data.get("club") or str(p_data.get("club_id") or p_data.get("team", "")),
                "price": float(p_data.get("price") or p_data.get("now_cost", 50) / 10.0),
                "xP": float(p_data.get("challenge_xP") or p_data.get("xP", 0.0))
            })

        # Resolve Captain ID
        cap_info = lookup.get(captain_name, {})
        cap_id = int(cap_info.get("id")) if cap_info.get("id") else (element_ids[0] if element_ids else 1)

        # Resolve Vice-Captain ID
        vc_info = lookup.get(vice_captain_name, {}) if vice_captain_name else {}
        if vc_info.get("id") and int(vc_info.get("id")) != cap_id:
            vc_id = int(vc_info.get("id"))
        else:
            # Fallback to second player in squad
            other_ids = [eid for eid in element_ids if eid != cap_id]
            vc_id = other_ids[0] if other_ids else cap_id

        # Generate official FPL Challenge lineup payload
        # Format: {"picks": [{"element": 123, "position": 1, "is_captain": True, "is_vice_captain": False}, ...]}
        picks = []
        for idx, eid in enumerate(element_ids):
            picks.append({
                "element": eid,
                "position": idx + 1,
                "is_captain": (eid == cap_id),
                "is_vice_captain": (eid == vc_id)
            })

        payload = {
            "picks": picks,
            "chip": None
        }

        return element_details, element_ids, cap_id, vc_id, payload
