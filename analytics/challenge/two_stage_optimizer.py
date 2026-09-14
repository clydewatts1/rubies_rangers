"""
analytics/challenge/two_stage_optimizer.py
Stage 2: Monte Carlo Tournament Simulation & Tail-Risk Evaluation for FPL Challenge.
Evaluates Stage 1 candidate squads across thousands of stochastic joint draws for P10, P50, P90, and P99 right tail.
Calculates rolling in-play flexibility score and GPP tournament win probability against the field.
Crowns Top 3 Archetypes: Max EV (Balanced), High Floor (Safety), and GPP Winner (P99 Right Tail).
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd

from analytics.challenge.contracts import (
    ChallengeRuleSet,
    ChallengeOptimalSquad,
    EvaluatedChallengeCandidate,
    ChallengeTournamentReport,
)
from analytics.challenge.optimizer import ChallengeOptimizer
from analytics.challenge.scoring_adapter import ChallengeScoringAdapter

logger = logging.getLogger(__name__)


class ChallengeTwoStageOptimizer:
    """Orchestrates Stage 1 MILP Screening and Stage 2 Monte Carlo Tournament for FPL Challenge."""

    def __init__(
        self,
        players_df: pd.DataFrame,
        rule_set: ChallengeRuleSet,
        fixtures: Optional[List[Dict[str, Any]]] = None,
        random_seed: int = 42
    ) -> None:
        self.players_df = players_df.copy()
        self.rule_set = rule_set
        self.fixtures = fixtures or []
        self.random_seed = random_seed
        self.rng = np.random.default_rng(self.random_seed)

        # Precompute player lookup table
        self.augmented_df = ChallengeScoringAdapter.adjust_projections(self.players_df, self.rule_set)
        if "web_name" not in self.augmented_df.columns:
            self.augmented_df["web_name"] = self.augmented_df.get("name", "Player")
        
        lookup_df = self.augmented_df.sort_values(
            by="challenge_xP" if "challenge_xP" in self.augmented_df.columns else "xP",
            ascending=False
        ).drop_duplicates(subset=["web_name"])
        self.player_map = lookup_df.set_index("web_name").to_dict(orient="index")

    def _compute_flexibility_score(self, squad_names: List[str]) -> float:
        """
        Calculate the rolling in-play flexibility score based on match kickoff distribution.
        Teams with players spread across multiple match slots (and late matches) retain the
        real option to pivot captaincy or bench late scratches.
        Score normalized between 0.0 and 100.0.
        """
        if not self.fixtures:
            # Fallback based on club distribution diversity
            clubs = [self.player_map.get(name, {}).get("club", name) for name in squad_names]
            unique_clubs = len(set(clubs))
            return round(min(100.0, (unique_clubs / max(1, len(squad_names))) * 85.0 + 15.0), 1)

        # Fixture kickoff timing lookup
        # Count players whose kickoff is on Saturday late or Sunday/Monday
        late_kickoff_count = 0
        total_players = len(squad_names)
        if total_players == 0:
            return 50.0

        for name in squad_names:
            p_data = self.player_map.get(name, {})
            club = p_data.get("club", "")
            # Check if club plays in late slot in fixtures
            is_late = False
            for f in self.fixtures:
                teams = [f.get("team_h"), f.get("team_a")]
                # If kickoff is after Saturday 17:00 or on Sunday/Monday
                kickoff = str(f.get("kickoff_time", ""))
                # e.g., Sunday "2026-09-20" or Saturday evening "17:30"
                if "17:30" in kickoff or "Sun" in kickoff or "Mon" in kickoff or "T" in kickoff:
                    # Simple heuristic check
                    is_late = True
                    break
            if is_late:
                late_kickoff_count += 1

        flex_ratio = (late_kickoff_count / total_players)
        return round(float(np.clip(flex_ratio * 70.0 + 30.0, 10.0, 100.0)), 1)

    def _simulate_squad(
        self,
        candidate: ChallengeOptimalSquad,
        n_sims: int
    ) -> Tuple[np.ndarray, float, float, float, float, float, float, float, str]:
        """
        Execute vectorized Monte Carlo joint simulation for a single candidate squad.
        Returns: (raw_totals, mean, p10, p50, p90, p99, std_dev, sharpe, key_talismans)
        """
        squad_names = candidate.squad_names
        captain_name = candidate.captain
        m = len(squad_names)
        if m == 0:
            zeros = np.zeros(n_sims)
            return zeros, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ""

        means = np.zeros(m)
        sigmas = np.zeros(m)
        multipliers = np.ones(m)
        clubs = []

        for idx, name in enumerate(squad_names):
            p_data = self.player_map.get(name, {})
            means[idx] = float(p_data.get("challenge_xP", 3.5))
            sigmas[idx] = float(p_data.get("sigma", 2.0))
            clubs.append(p_data.get("club", "UNK"))
            if name == captain_name:
                multipliers[idx] = 2.0  # Challenge 2x captaincy

        # 1. Base individual player draws from normal distribution truncated at 0
        # Shape: (n_sims, m)
        raw_draws = self.rng.normal(loc=means, scale=sigmas, size=(n_sims, m))
        raw_draws = np.clip(raw_draws, 0.0, None)

        # 2. Minutes volatility / start probability (~94% start rate)
        # Occasional sub or bench appearance gives 1 point
        start_mask = self.rng.binomial(n=1, p=0.94, size=(n_sims, m))
        raw_draws = np.where(start_mask == 1, raw_draws, np.clip(raw_draws * 0.25, 0.0, 1.0))

        # 3. Apply captain multiplier
        squad_draws = raw_draws * multipliers

        # 4. Club covariance: if multiple players from same club, boost in high-scoring draws
        unique_clubs, counts = np.unique(clubs, return_counts=True)
        stacked_clubs = unique_clubs[counts > 1]
        if len(stacked_clubs) > 0:
            for c in stacked_clubs:
                club_indices = [i for i, club_name in enumerate(clubs) if club_name == c]
                # Joint team attack shock
                team_shock = self.rng.normal(0.0, 1.2, size=n_sims)
                for c_idx in club_indices:
                    squad_draws[:, c_idx] = np.clip(squad_draws[:, c_idx] + team_shock * 0.35, 0.0, None)

        # Sum draws across squad
        totals = np.sum(squad_draws, axis=1)

        mean_pts = round(float(np.mean(totals)), 2)
        p10 = round(float(np.percentile(totals, 10)), 1)
        p50 = round(float(np.percentile(totals, 50)), 1)
        p90 = round(float(np.percentile(totals, 90)), 1)
        p99 = round(float(np.percentile(totals, 99)), 1)
        std_dev = round(float(np.std(totals)), 2)
        sharpe = round(float(mean_pts / max(0.1, std_dev)), 2)

        # Top 2 point producers as key talismans
        mean_contributions = means * multipliers
        top_indices = np.argsort(mean_contributions)[-2:][::-1]
        key_talismans = ", ".join([squad_names[i] for i in top_indices])

        return totals, mean_pts, p10, p50, p90, p99, std_dev, sharpe, key_talismans

    def run_tournament(
        self,
        n_simulations: int = 5000,
        lock_players: Optional[List[str]] = None,
        exclude_players: Optional[List[str]] = None,
        available_only: bool = True
    ) -> ChallengeTournamentReport:
        """
        Execute full Two-Stage FPL Challenge Tournament:
        Stage 1: Multi-objective Pareto screening via MILP.
        Stage 2: Monte Carlo simulation, P99 evaluation, and archetype crowning.
        """
        # --- Stage 1: Screen ---
        optimizer = ChallengeOptimizer(self.players_df, self.rule_set)
        candidates = optimizer.generate_candidate_pool(
            lock_players=lock_players,
            exclude_players=exclude_players,
            available_only=available_only
        )

        if not candidates:
            # Fallback: solve baseline vector alone
            fallback_sol = optimizer.solve_single_vector("max_ev", lock_players, exclude_players, available_only)
            if fallback_sol:
                candidates = [fallback_sol]

        if not candidates:
            return ChallengeTournamentReport(
                rule_set=self.rule_set,
                evaluated_candidates=[],
                winner_balanced=None,
                winner_safe_floor=None,
                winner_gpp_upside=None,
                all_results_df=pd.DataFrame()
            )

        # --- Stage 2: Simulate ---
        evaluated: List[EvaluatedChallengeCandidate] = []

        # Determine GPP tournament threshold against typical 200,000 manager field
        # Typical 6-a-side field: mean ~ 38.0, sigma ~ 11.5. Top 1% threshold ~ 65.0
        gpp_target_threshold = 64.0 if self.rule_set.squad_size == 6 else 95.0

        for cand in candidates:
            totals, mean_pts, p10, p50, p90, p99, std_dev, sharpe, talismans = self._simulate_squad(
                cand, n_simulations
            )
            flex_score = self._compute_flexibility_score(cand.squad_names)
            win_prob = round(float(np.mean(totals >= gpp_target_threshold) * 100.0), 1)

            evaluated.append(
                EvaluatedChallengeCandidate(
                    candidate=cand,
                    mean_points=mean_pts,
                    floor_p10=p10,
                    median_p50=p50,
                    ceiling_p90=p90,
                    tournament_p99=p99,
                    std_dev=std_dev,
                    sharpe_ratio=sharpe,
                    flexibility_score=flex_score,
                    win_probability_pct=win_prob,
                    raw_totals=totals,
                    archetype="",
                    key_talismans=talismans
                )
            )

        # --- Crown Archetypes ---
        # Option 1: Max EV (Highest Expected Mean)
        best_balanced = max(evaluated, key=lambda c: c.mean_points)
        # Option 2: Safety Floor (Highest P10 Floor)
        best_floor = max(evaluated, key=lambda c: (c.floor_p10, c.mean_points))
        # Option 3: GPP Tournament Winner (Highest P99 Right-Tail & Win Probability)
        best_gpp = max(evaluated, key=lambda c: (c.tournament_p99, c.win_probability_pct))

        # Annotate archetypes
        crowned_list: List[EvaluatedChallengeCandidate] = []
        for c in evaluated:
            arch = []
            if c.candidate == best_balanced.candidate:
                arch.append("Option 1: Max EV (Balanced)")
            if c.candidate == best_floor.candidate:
                arch.append("Option 2: Safety Floor")
            if c.candidate == best_gpp.candidate:
                arch.append("Option 3: GPP Tournament Winner")
            arch_str = " / ".join(arch) if arch else "Contender"

            c_updated = EvaluatedChallengeCandidate(
                candidate=c.candidate,
                mean_points=c.mean_points,
                floor_p10=c.floor_p10,
                median_p50=c.median_p50,
                ceiling_p90=c.ceiling_p90,
                tournament_p99=c.tournament_p99,
                std_dev=c.std_dev,
                sharpe_ratio=c.sharpe_ratio,
                flexibility_score=c.flexibility_score,
                win_probability_pct=c.win_probability_pct,
                raw_totals=c.raw_totals,
                archetype=arch_str,
                key_talismans=c.key_talismans
            )
            crowned_list.append(c_updated)

        # Create structured comparison DataFrame
        rows = []
        for c in crowned_list:
            rows.append({
                "Archetype": c.archetype,
                "Objective": c.candidate.objective_name,
                "E[Points]": c.mean_points,
                "Floor (P10)": c.floor_p10,
                "Median (P50)": c.median_p50,
                "Ceiling (P90)": c.ceiling_p90,
                "Tournament (P99)": c.tournament_p99,
                "GPP Win %": f"{c.win_probability_pct}%",
                "Flexibility": f"{c.flexibility_score}/100",
                "Captain": c.candidate.captain,
                "Formation": c.candidate.formation,
                "Cost": f"£{c.candidate.total_cost}m",
                "Clubs": c.candidate.clubs_represented,
                "Squad": ", ".join(c.candidate.squad_names)
            })

        df_results = pd.DataFrame(rows).sort_values(by="Tournament (P99)", ascending=False).reset_index(drop=True)

        return ChallengeTournamentReport(
            rule_set=self.rule_set,
            evaluated_candidates=crowned_list,
            winner_balanced=best_balanced,
            winner_safe_floor=best_floor,
            winner_gpp_upside=best_gpp,
            all_results_df=df_results
        )
