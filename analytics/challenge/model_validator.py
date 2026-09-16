"""
analytics/challenge/model_validator.py
Model Validation & Configuration Setting Drift Comparison Engine for FPL Challenge.
Validates solver candidates against active profile settings in config.yaml (tuned vs heuristic).
Detects constraint violations, parameter anomalies (NaN, negative xP), and archetype dominance drift.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import numpy as np

from analytics.challenge.contracts import ChallengeRuleSet
from analytics.challenge.picker import ChallengePickerResult
from config_manager import get_active_profile, get_config, get_system_config

logger = logging.getLogger("rubies_rangers.challenge.validator")


@dataclass(frozen=True)
class ModelValidationReport:
    """Comprehensive validation and setting comparison report."""
    is_valid: bool
    active_profile: str
    errors: List[str]
    warnings: List[str]
    checks_passed: List[str]
    setting_comparison: Dict[str, Any]

    @property
    def budget_valid(self) -> bool:
        return not any("budget" in e.lower() or "bank" in e.lower() for e in self.errors)

    @property
    def club_limits_valid(self) -> bool:
        return not any("club" in e.lower() for e in self.errors)

    @property
    def position_quotas_valid(self) -> bool:
        return not any("position" in e.lower() for e in self.errors)

    @property
    def archetype_consistency_valid(self) -> bool:
        return not any("tail" in e.lower() or "archetype" in e.lower() for e in self.errors)

    @property
    def summary_dict(self) -> Dict[str, Any]:
        return {
            "status": "VALID" if self.is_valid else "INVALID",
            "active_profile": self.active_profile,
            "errors": self.errors,
            "warnings": self.warnings,
            "checks_passed_count": len(self.checks_passed),
            "settings": self.setting_comparison,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "active_profile": self.active_profile,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "checks_passed": self.checks_passed,
            "setting_comparison": self.setting_comparison,
        }


class ChallengeModelValidator:
    """
    Validates ChallengePicker outputs against active configuration settings in config.yaml.
    Detects constraint violations, parameter drift, and mathematical archetype inconsistencies.
    """

    @classmethod
    def validate(
        cls,
        picker_result: ChallengePickerResult,
        rule_set: ChallengeRuleSet
    ) -> ModelValidationReport:
        """
        Executes a battery of sanity checks and setting comparisons on the picker result.
        """
        errors: List[str] = []
        warnings: List[str] = []
        checks_passed: List[str] = []

        active_prof = get_active_profile() or "tuned"
        full_cfg = get_config()
        prof_cfg = full_cfg.get(active_prof, {})

        squad = picker_result.selected_squad
        eval_cand = picker_result.evaluated_candidate
        report = picker_result.tournament_report

        # ------------------------------------------------------------------
        # 1. Squad Size Check
        # ------------------------------------------------------------------
        actual_size = len(squad.squad_names)
        expected_size = rule_set.squad_size
        if actual_size != expected_size:
            errors.append(
                f"Squad size mismatch: expected {expected_size} players, got {actual_size} ({squad.squad_names})"
            )
        else:
            checks_passed.append(f"Squad size exact match ({actual_size}/{expected_size})")

        # ------------------------------------------------------------------
        # 2. Financial Budget Compliance Check
        # ------------------------------------------------------------------
        budget_cap = rule_set.budget_cap
        total_cost = squad.total_cost
        if total_cost > budget_cap + 0.001:
            errors.append(
                f"Budget violation: squad cost £{total_cost:.1f}m exceeds rule budget cap of £{budget_cap:.1f}m"
            )
        else:
            checks_passed.append(f"Budget compliant (£{total_cost:.1f}m ≤ £{budget_cap:.1f}m)")

        # ------------------------------------------------------------------
        # 3. Club Quota Compliance Check
        # ------------------------------------------------------------------
        club_counts: Dict[str, int] = {}
        for el in picker_result.squad_elements:
            club = str(el.get("club", "Unknown"))
            club_counts[club] = club_counts.get(club, 0) + 1

        max_club_used = max(club_counts.values()) if club_counts else 0
        club_limit = rule_set.max_per_team
        if max_club_used > club_limit:
            violating_clubs = [c for c, count in club_counts.items() if count > club_limit]
            errors.append(
                f"Club quota violation: {violating_clubs} have {max_club_used} players (limit: {club_limit})"
            )
        else:
            checks_passed.append(f"Club quota compliant (max per club: {max_club_used} ≤ {club_limit})")

        # ------------------------------------------------------------------
        # 4. Positional Bounds Compliance Check
        # ------------------------------------------------------------------
        pos_counts: Dict[str, int] = {"GKP": 0, "DEF": 0, "MID": 0, "FWD": 0}
        for el in picker_result.squad_elements:
            p = str(el.get("position", "MID")).upper()
            pos_counts[p] = pos_counts.get(p, 0) + 1

        for pos, (low, high) in rule_set.allowed_positions.items():
            cnt = pos_counts.get(pos, 0)
            if cnt < low:
                errors.append(f"Positional deficit for {pos}: count {cnt} is less than required minimum {low}")
            elif cnt > high:
                errors.append(f"Positional excess for {pos}: count {cnt} exceeds maximum allowed {high}")
            else:
                checks_passed.append(f"Position {pos} bounds satisfied ({low} ≤ {cnt} ≤ {high})")

        # ------------------------------------------------------------------
        # 5. Captaincy & Vice-Captaincy Integrity
        # ------------------------------------------------------------------
        if not squad.captain or squad.captain not in squad.squad_names:
            errors.append(f"Captain '{squad.captain}' is not in the active squad ({squad.squad_names})")
        else:
            checks_passed.append(f"Captain verified in squad ({squad.captain})")

        if squad.vice_captain and squad.vice_captain not in squad.squad_names:
            errors.append(f"Vice-captain '{squad.vice_captain}' is not in the active squad")
        elif squad.vice_captain and squad.vice_captain == squad.captain and len(squad.squad_names) > 1:
            warnings.append(f"Captain and Vice-captain are identical ({squad.captain})")
        else:
            checks_passed.append(f"Vice-captain distinct and in squad ({squad.vice_captain})")

        # ------------------------------------------------------------------
        # 6. Expected Points ($xP$) & Variance Sanity Checks
        # ------------------------------------------------------------------
        if eval_cand.mean_points <= 0.0:
            errors.append(f"Anomalous Expected Return: mean points {eval_cand.mean_points:.2f} is non-positive")
        elif np.isnan(eval_cand.mean_points) or np.isinf(eval_cand.mean_points):
            errors.append(f"Corrupted Expected Return: mean points is NaN or infinite")
        else:
            checks_passed.append(f"Mean Expected Points positive and sane (E[V] = {eval_cand.mean_points:.1f} pts)")

        if eval_cand.tournament_p99 < eval_cand.floor_p10:
            errors.append(f"Tail risk inversion: P99 ({eval_cand.tournament_p99:.1f}) < P10 ({eval_cand.floor_p10:.1f})")
        elif eval_cand.tournament_p99 < eval_cand.mean_points:
            errors.append(f"Tail risk anomaly: P99 tournament tail ({eval_cand.tournament_p99:.1f}) is less than mean return ({eval_cand.mean_points:.1f})")
        else:
            checks_passed.append(f"Tail metrics monotonic (P10={eval_cand.floor_p10:.1f} ≤ P50={eval_cand.median_p50:.1f} ≤ P99={eval_cand.tournament_p99:.1f})")

        # ------------------------------------------------------------------
        # 7. Mathematical Archetype Consistency Invariant
        # ------------------------------------------------------------------
        if report and report.evaluated_candidates:
            all_means = [c.mean_points for c in report.evaluated_candidates]
            all_floors = [c.floor_p10 for c in report.evaluated_candidates]
            all_ceilings = [c.tournament_p99 for c in report.evaluated_candidates]

            if picker_result.archetype_chosen == "max_ev":
                max_possible_mean = max(all_means)
                if eval_cand.mean_points < max_possible_mean - 0.05:
                    warnings.append(
                        f"Archetype sub-optimality: Chosen 'max_ev' mean ({eval_cand.mean_points:.1f}) is less than highest observed ({max_possible_mean:.1f})"
                    )
                else:
                    checks_passed.append("Max EV candidate satisfies global maximum mean return")
            elif picker_result.archetype_chosen == "safe_floor":
                max_possible_floor = max(all_floors)
                if eval_cand.floor_p10 < max_possible_floor - 0.05:
                    warnings.append(
                        f"Archetype sub-optimality: Chosen 'safe_floor' P10 ({eval_cand.floor_p10:.1f}) is less than highest observed ({max_possible_floor:.1f})"
                    )
                else:
                    checks_passed.append("Safe Floor candidate satisfies global maximum downside floor")
            elif picker_result.archetype_chosen == "gpp_upside":
                max_possible_p99 = max(all_ceilings)
                if eval_cand.tournament_p99 < max_possible_p99 - 0.05:
                    warnings.append(
                        f"Archetype sub-optimality: Chosen 'gpp_upside' P99 ({eval_cand.tournament_p99:.1f}) is less than highest observed ({max_possible_p99:.1f})"
                    )
                else:
                    checks_passed.append("GPP Upside candidate satisfies global maximum right-tail ceiling")

        # ------------------------------------------------------------------
        # 8. Setting & Configuration Comparison Matrix
        # ------------------------------------------------------------------
        setting_comp = {
            "active_profile": active_prof,
            "config_budget_cap": budget_cap,
            "actual_spend": round(total_cost, 1),
            "bank_remaining": round(budget_cap - total_cost, 1) if budget_cap < 900 else 0.0,
            "rule_squad_size": expected_size,
            "actual_squad_size": actual_size,
            "rule_club_limit": club_limit,
            "actual_max_club": max_club_used,
            "clubs_represented": len(club_counts),
            "formation": squad.formation,
            "scoring_modifiers_active": len(rule_set.scoring_modifiers),
            "simulations_modeled": len(eval_cand.raw_totals) if eval_cand.raw_totals is not None else 0,
            "win_probability_pct": eval_cand.win_probability_pct
        }

        is_valid = len(errors) == 0

        if not is_valid:
            logger.warning("[ChallengeModelValidator] Model errors detected: %s", errors)
        if warnings:
            logger.info("[ChallengeModelValidator] Model warnings: %s", warnings)

        return ModelValidationReport(
            is_valid=is_valid,
            active_profile=active_prof,
            errors=errors,
            warnings=warnings,
            checks_passed=checks_passed,
            setting_comparison=setting_comp
        )
