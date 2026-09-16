"""
Closed-Loop Suggestion & Outcome Audit Ledger & Calibration Engine
Tracks solver suggestions (transfers, captaincy, starting XI) prior to deadlines,
reconciles them against official match ground truth, computes prediction residuals,
and evaluates model calibration metrics (MAE, RMSE, MBE, CUSUM) to detect alpha drift.
"""

from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import pandas as pd

from config_manager import get_system_config
from clients.fpl_client import FPLClient

logger = logging.getLogger("trackers.decision_audit")

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_LEDGER_PATH = os.path.join(_PROJECT_ROOT, "data", "decision_audit_ledger.json")


@dataclass(frozen=True)
class PlayerAuditItem:
    """Audit record for an individual player in a gameweek lineup."""
    player_id: int
    web_name: str
    position_name: str
    club_short: str
    projected_xp: float
    actual_points: float = 0.0
    actual_minutes: int = 0
    is_starter: bool = True
    is_captain: bool = False
    is_vice_captain: bool = False
    auto_subbed_in: bool = False
    auto_subbed_out: bool = False

    @property
    def residual(self) -> float:
        """Prediction residual: Actual - Projected xP."""
        return round(self.actual_points - self.projected_xp, 2)


@dataclass(frozen=True)
class TransferAuditItem:
    """Audit record for a recommended or executed transfer."""
    player_in_id: int
    player_in_name: str
    player_in_xp: float
    player_out_id: int
    player_out_name: str
    player_out_xp: float
    hit_cost: int = 0
    player_in_actual_pts: float = 0.0
    player_out_actual_pts: float = 0.0

    @property
    def projected_gain(self) -> float:
        return round(self.player_in_xp - self.player_out_xp - self.hit_cost, 2)

    @property
    def realized_roi(self) -> float:
        """Realized net gain: (In Actual - Out Actual) - Hit."""
        return round((self.player_in_actual_pts - self.player_out_actual_pts) - self.hit_cost, 2)


@dataclass
class SuggestionSnapshot:
    """Pre-deadline snapshot of solver recommendations for a target gameweek."""
    gw: int
    season: str
    timestamp: str
    profile_name: str
    formation: str
    projected_starting_xp: float
    projected_effective_xp: float  # includes captain 2x
    captain_name: str
    vice_captain_name: str
    starters: List[Dict[str, Any]]
    bench: List[Dict[str, Any]]
    transfers: List[Dict[str, Any]] = field(default_factory=list)
    applied_by_user: bool = True
    is_reconciled: bool = False
    actual_starting_points: float = 0.0
    actual_effective_points: float = 0.0
    actual_captain_points: float = 0.0
    auto_subs: List[Tuple[str, str]] = field(default_factory=list)
    prediction_residual: float = 0.0
    transfer_net_alpha: float = 0.0
    captaincy_efficiency: float = 0.0  # (Actual C / Optimal Squad C)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SuggestionSnapshot:
        # Convert auto_subs list if loaded as lists of lists from JSON
        if "auto_subs" in data and data["auto_subs"]:
            data["auto_subs"] = [tuple(sub) for sub in data["auto_subs"]]
        return cls(**data)


@dataclass(frozen=True)
class CalibrationMetrics:
    """Summary of model calibration and drift diagnostics across audited gameweeks."""
    total_gws_audited: int
    mean_bias_error: float  # Sum(Residual) / N. Positive = under-projecting, Negative = over-projecting
    mean_absolute_error: float  # MAE of team points
    root_mean_squared_error: float  # RMSE of team points
    cumulative_residual: float  # CUSUM of (Actual - Projected)
    transfer_total_roi: float  # Sum of all realized transfer net gains
    captaincy_accuracy_pct: float  # % of times chosen captain was highest/near-highest scorer
    positional_bias: Dict[str, float]  # Mean error by position (GKP, DEF, MID, FWD)
    calibration_status: str  # 'WELL_CALIBRATED', 'OVER_PROJECTING', 'UNDER_PROJECTING', 'INSUFFICIENT_DATA'
    calibration_diagnosis: str


class DecisionAuditLedger:
    """
    Persistent ledger managing gameweek recommendation snapshots,
    ground-truth reconciliation, and closed-loop calibration metrics.
    """

    LEGAL_FORMATIONS = [
        (3, 4, 3), (3, 5, 2), (4, 4, 2), (4, 3, 3),
        (4, 5, 1), (5, 3, 2), (5, 4, 1), (5, 2, 3)
    ]

    def __init__(self, ledger_file: Optional[str] = None, client: Optional[FPLClient] = None):
        self.ledger_file = ledger_file or DEFAULT_LEDGER_PATH
        self.client = client or FPLClient()
        self._ensure_dir()
        self._snapshots: Dict[str, SuggestionSnapshot] = {}
        self.load()

    def _ensure_dir(self) -> None:
        os.makedirs(os.path.dirname(self.ledger_file), exist_ok=True)

    def _make_key(self, season: str, gw: int) -> str:
        return f"{season}_GW{gw}"

    def load(self) -> None:
        """Load audit ledger from disk."""
        if not os.path.exists(self.ledger_file):
            self._snapshots = {}
            return

        try:
            with open(self.ledger_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            self._snapshots = {
                k: SuggestionSnapshot.from_dict(v) for k, v in raw_data.items()
            }
        except Exception as e:
            logger.warning("Failed to parse audit ledger %s: %s", self.ledger_file, e)
            self._snapshots = {}

    def save(self) -> None:
        """Persist audit ledger to disk."""
        try:
            data = {k: v.to_dict() for k, v in self._snapshots.items()}
            with open(self.ledger_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save audit ledger %s: %s", self.ledger_file, e)

    def snapshot_suggestion(
        self,
        gw: int,
        season: str,
        starters: List[Dict[str, Any]],
        bench: List[Dict[str, Any]],
        captain_name: str,
        vice_captain_name: str,
        formation: str,
        projected_starting_xp: float,
        projected_effective_xp: float,
        transfers: Optional[List[Dict[str, Any]]] = None,
        profile_name: str = "Rubies Rangers",
        applied_by_user: bool = True
    ) -> SuggestionSnapshot:
        """Record or update a suggestion snapshot prior to gameweek deadline."""
        key = self._make_key(season, gw)
        now_str = datetime.now(timezone.utc).isoformat()

        snapshot = SuggestionSnapshot(
            gw=gw,
            season=season,
            timestamp=now_str,
            profile_name=profile_name,
            formation=formation,
            projected_starting_xp=round(projected_starting_xp, 2),
            projected_effective_xp=round(projected_effective_xp, 2),
            captain_name=captain_name,
            vice_captain_name=vice_captain_name,
            starters=starters,
            bench=bench,
            transfers=transfers or [],
            applied_by_user=applied_by_user,
            is_reconciled=False
        )

        self._snapshots[key] = snapshot
        self.save()
        logger.info("Snapshotted suggestion for %s (Projected Eff xP: %.2f)", key, projected_effective_xp)
        return snapshot

    def reconcile_gameweek(
        self,
        season: str,
        gw: int,
        live_data: Optional[Dict[str, Any]] = None,
        bootstrap_data: Optional[Dict[str, Any]] = None
    ) -> Optional[SuggestionSnapshot]:
        """
        Reconcile a snapshotted gameweek against official match ground truth.
        Computes actual starting points, captain doubling, auto-subs, and residuals.
        """
        key = self._make_key(season, gw)
        if key not in self._snapshots:
            logger.warning("No snapshot found for %s to reconcile", key)
            return None

        snap = self._snapshots[key]

        # Fetch live elements for this gameweek
        if live_data is None:
            live_data = self.client.get_gameweek_live(gameweek=gw)

        if bootstrap_data is None:
            bootstrap_data = self.client.get_bootstrap_data()

        elements = live_data.get("elements", [])
        if not elements:
            logger.warning("Live data for GW%d contains no elements", gw)
            return snap

        # Build player lookup maps by ID and Web Name
        id_to_stats: Dict[int, Dict[str, Any]] = {}
        for elem in elements:
            p_id = elem.get("id")
            stats = elem.get("stats", {})
            id_to_stats[p_id] = {
                "total_points": stats.get("total_points", 0),
                "minutes": stats.get("minutes", 0),
                "goals_scored": stats.get("goals_scored", 0),
                "assists": stats.get("assists", 0),
                "clean_sheets": stats.get("clean_sheets", 0),
                "bonus": stats.get("bonus", 0),
            }

        name_to_id: Dict[str, int] = {}
        pos_map: Dict[str, str] = {}
        for p in bootstrap_data.get("elements", []):
            name_to_id[p.get("web_name", "")] = p.get("id", 0)
            element_type = p.get("element_type", 0)
            pos_str = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}.get(element_type, "MID")
            pos_map[p.get("web_name", "")] = pos_str

        # Update starters with ground truth
        updated_starters = []
        for s in snap.starters:
            w_name = s.get("web_name", "")
            p_id = s.get("id") or name_to_id.get(w_name, 0)
            stats = id_to_stats.get(p_id, {"total_points": 0, "minutes": 0})
            s_dict = dict(s)
            s_dict["actual_points"] = float(stats.get("total_points", 0))
            s_dict["actual_minutes"] = int(stats.get("minutes", 0))
            updated_starters.append(s_dict)

        # Update bench with ground truth
        updated_bench = []
        for b in snap.bench:
            w_name = b.get("web_name", "")
            p_id = b.get("id") or name_to_id.get(w_name, 0)
            stats = id_to_stats.get(p_id, {"total_points": 0, "minutes": 0})
            b_dict = dict(b)
            b_dict["actual_points"] = float(stats.get("total_points", 0))
            b_dict["actual_minutes"] = int(stats.get("minutes", 0))
            updated_bench.append(b_dict)

        # Execute Auto-Substitutions
        active_xi_names = [s.get("web_name", "") for s in updated_starters]
        starter_map = {s["web_name"]: s for s in updated_starters}
        bench_map = {b["web_name"]: b for b in updated_bench}
        auto_subs: List[Tuple[str, str]] = []

        # 1. GKP Auto-Sub
        gkp_starter = next((p for p in active_xi_names if pos_map.get(p) == "GKP"), None)
        gkp_bench = next((b.get("web_name", "") for b in updated_bench if pos_map.get(b.get("web_name", "")) == "GKP"), None)

        if gkp_starter and gkp_bench:
            s_mins = starter_map.get(gkp_starter, {}).get("actual_minutes", 0)
            b_mins = bench_map.get(gkp_bench, {}).get("actual_minutes", 0)
            if s_mins == 0 and b_mins > 0:
                active_xi_names[active_xi_names.index(gkp_starter)] = gkp_bench
                auto_subs.append((gkp_starter, gkp_bench))

        # 2. Outfield Auto-Subs
        outfield_bench_names = [b.get("web_name", "") for b in updated_bench if pos_map.get(b.get("web_name", "")) != "GKP"]
        used_bench: set = set()

        for starter_name in list(active_xi_names):
            if pos_map.get(starter_name) == "GKP":
                continue
            s_mins = starter_map.get(starter_name, {}).get("actual_minutes", 0)
            if s_mins == 0:
                for b_name in outfield_bench_names:
                    if b_name in used_bench:
                        continue
                    b_mins = bench_map.get(b_name, {}).get("actual_minutes", 0)
                    if b_mins > 0:
                        temp_xi = [b_name if p == starter_name else p for p in active_xi_names]
                        n_d = sum(1 for p in temp_xi if pos_map.get(p) == "DEF")
                        n_m = sum(1 for p in temp_xi if pos_map.get(p) == "MID")
                        n_f = sum(1 for p in temp_xi if pos_map.get(p) == "FWD")
                        if (n_d, n_m, n_f) in self.LEGAL_FORMATIONS:
                            active_xi_names[active_xi_names.index(starter_name)] = b_name
                            used_bench.add(b_name)
                            auto_subs.append((starter_name, b_name))
                            break

        # Calculate actual points with captain doubling
        c_name = snap.captain_name
        vc_name = snap.vice_captain_name

        c_mins = starter_map.get(c_name, {}).get("actual_minutes", 0)
        vc_mins = starter_map.get(vc_name, {}).get("actual_minutes", 0)

        effective_c = c_name if c_mins > 0 else (vc_name if vc_mins > 0 else c_name)
        c_actual_pts = starter_map.get(effective_c, {}).get("actual_points", 0.0)

        actual_starting_pts = 0.0
        actual_effective_pts = 0.0
        all_pool = {**starter_map, **bench_map}

        for player_name in active_xi_names:
            pts = float(all_pool.get(player_name, {}).get("actual_points", 0.0))
            actual_starting_pts += pts
            if player_name == effective_c:
                actual_effective_pts += (pts * 2.0)
            else:
                actual_effective_pts += pts

        # Score transfers net ROI if present
        updated_transfers = []
        transfer_net_alpha = 0.0
        for tr in snap.transfers:
            tr_dict = dict(tr)
            p_in_id = tr.get("player_in_id") or name_to_id.get(tr.get("player_in_name", ""), 0)
            p_out_id = tr.get("player_out_id") or name_to_id.get(tr.get("player_out_name", ""), 0)
            in_pts = float(id_to_stats.get(p_in_id, {}).get("total_points", 0.0))
            out_pts = float(id_to_stats.get(p_out_id, {}).get("total_points", 0.0))
            hit = int(tr.get("hit_cost", 0))

            tr_dict["player_in_actual_pts"] = in_pts
            tr_dict["player_out_actual_pts"] = out_pts
            roi = (in_pts - out_pts) - hit
            tr_dict["realized_roi"] = roi
            transfer_net_alpha += roi
            updated_transfers.append(tr_dict)

        # Captaincy Efficiency: compare chosen captain pts with best starter pts
        max_starter_pts = max([s.get("actual_points", 0.0) for s in updated_starters], default=1.0)
        cap_efficiency = round((c_actual_pts / max(1.0, max_starter_pts)) * 100.0, 1)

        residual = round(actual_effective_pts - snap.projected_effective_xp, 2)

        reconciled_snap = SuggestionSnapshot(
            gw=snap.gw,
            season=snap.season,
            timestamp=snap.timestamp,
            profile_name=snap.profile_name,
            formation=snap.formation,
            projected_starting_xp=snap.projected_starting_xp,
            projected_effective_xp=snap.projected_effective_xp,
            captain_name=snap.captain_name,
            vice_captain_name=snap.vice_captain_name,
            starters=updated_starters,
            bench=updated_bench,
            transfers=updated_transfers,
            applied_by_user=snap.applied_by_user,
            is_reconciled=True,
            actual_starting_points=round(actual_starting_pts, 1),
            actual_effective_points=round(actual_effective_pts, 1),
            actual_captain_points=round(c_actual_pts, 1),
            auto_subs=auto_subs,
            prediction_residual=residual,
            transfer_net_alpha=round(transfer_net_alpha, 1),
            captaincy_efficiency=cap_efficiency
        )

        self._snapshots[key] = reconciled_snap
        self.save()
        logger.info("Reconciled %s: Actual %.1f pts vs Projected %.1f (Residual: %+.1f)",
                    key, actual_effective_pts, snap.projected_effective_xp, residual)
        return reconciled_snap

    def get_all_snapshots(self) -> List[SuggestionSnapshot]:
        """Return all snapshots sorted chronologically by GW."""
        return sorted(self._snapshots.values(), key=lambda s: s.gw)

    def get_reconciled_snapshots(self) -> List[SuggestionSnapshot]:
        """Return only reconciled snapshots sorted by GW."""
        return [s for s in self.get_all_snapshots() if s.is_reconciled]

    def compute_calibration_metrics(self) -> CalibrationMetrics:
        """
        Calculates full statistical calibration metrics across reconciled gameweeks:
        Mean Bias Error (MBE), MAE, RMSE, CUSUM, Positional Bias, and Drift status.
        """
        reconciled = self.get_reconciled_snapshots()
        if not reconciled:
            return CalibrationMetrics(
                total_gws_audited=0,
                mean_bias_error=0.0,
                mean_absolute_error=0.0,
                root_mean_squared_error=0.0,
                cumulative_residual=0.0,
                transfer_total_roi=0.0,
                captaincy_accuracy_pct=0.0,
                positional_bias={"GKP": 0.0, "DEF": 0.0, "MID": 0.0, "FWD": 0.0},
                calibration_status="INSUFFICIENT_DATA",
                calibration_diagnosis="No completed gameweeks reconciled yet in the audit ledger."
            )

        residuals = [s.prediction_residual for s in reconciled]
        mbe = float(np.mean(residuals))
        mae = float(np.mean(np.abs(residuals)))
        rmse = float(np.sqrt(np.mean(np.square(residuals))))
        cusum = float(np.sum(residuals))
        total_transfer_roi = float(np.sum([s.transfer_net_alpha for s in reconciled]))

        cap_hits = sum(1 for s in reconciled if s.captaincy_efficiency >= 80.0)
        cap_acc_pct = round((cap_hits / len(reconciled)) * 100.0, 1)

        # Positional Error Breakdown
        pos_errors: Dict[str, List[float]] = {"GKP": [], "DEF": [], "MID": [], "FWD": []}
        for s in reconciled:
            for p in s.starters:
                pos = p.get("position_name", "MID")
                proj = float(p.get("projected_xp", p.get("xP", 0.0)))
                act = float(p.get("actual_points", 0.0))
                if pos in pos_errors:
                    pos_errors[pos].append(act - proj)

        pos_bias = {
            pos: round(float(np.mean(errs)), 2) if errs else 0.0
            for pos, errs in pos_errors.items()
        }

        # Calibration Diagnosis
        n = len(reconciled)
        if n < 3:
            status = "INSUFFICIENT_DATA"
            diagnosis = f"Audited {n} gameweeks. Minimum 3 required for robust statistical calibration."
        elif abs(mbe) <= 4.0:
            status = "WELL_CALIBRATED"
            diagnosis = f"Model is well-calibrated (Mean Error: {mbe:+.1f} pts/GW). Predictions match actual ground truth within standard statistical variance."
        elif mbe < -4.0:
            status = "OVER_PROJECTING"
            diagnosis = f"Model is systematically over-projecting points (Mean Error: {mbe:+.1f} pts/GW). Check minutes inflation or defensive clean sheet multipliers."
        else:
            status = "UNDER_PROJECTING"
            diagnosis = f"Model is under-projecting points (Mean Error: {mbe:+.1f} pts/GW). Expected returns may be too conservative."

        return CalibrationMetrics(
            total_gws_audited=n,
            mean_bias_error=round(mbe, 2),
            mean_absolute_error=round(mae, 2),
            root_mean_squared_error=round(rmse, 2),
            cumulative_residual=round(cusum, 2),
            transfer_total_roi=round(total_transfer_roi, 2),
            captaincy_accuracy_pct=cap_acc_pct,
            positional_bias=pos_bias,
            calibration_status=status,
            calibration_diagnosis=diagnosis
        )

    def seed_historical_gameweeks(self, up_to_gw: int = 4, force: bool = False) -> int:
        """
        Auto-seeds historical completed gameweeks using dynamic fixture-adjusted
        XPModel projections, and reconciles against live match ground truth.
        If force=True, re-evaluates and overwrites existing historical records.
        """
        seeded_count = 0
        current_season = "2024-25"

        # Baseline squad definitions used as robust fallback if dynamic solver is offline
        default_squad_names = [
            ("Roefs", "GKP", "SUN", 4.5, 4.0),
            ("Pedro Porro", "DEF", "TOT", 5.5, 5.0),
            ("Senesi", "DEF", "BOU", 4.8, 4.2),
            ("Guéhi", "DEF", "CRY", 4.5, 3.8),
            ("Robinson", "DEF", "FUL", 4.6, 4.1),
            ("Foden", "MID", "MCI", 9.5, 7.2),
            ("Ødegaard", "MID", "ARS", 8.5, 6.8),
            ("Mbeumo", "MID", "BRE", 7.1, 6.5),
            ("Cherki", "MID", "MCI", 6.0, 4.5),
            ("João Pedro", "FWD", "BHA", 5.7, 5.8),
            ("Isak", "FWD", "NEW", 8.5, 7.5),
        ]
        bench_names = [
            ("Verbruggen", "GKP", "BHA", 4.5, 3.5),
            ("Rogers", "MID", "AVL", 5.1, 4.2),
            ("Solanke", "FWD", "TOT", 7.5, 5.5),
            ("Thiaw", "DEF", "NEW", 4.5, 3.0),
        ]

        for gw in range(1, up_to_gw + 1):
            key = self._make_key(current_season, gw)
            if not force and key in self._snapshots and self._snapshots[key].is_reconciled:
                continue

            dynamic_success = False
            starters = []
            bench = []
            cap_name = ""
            vc_name = ""
            formation = "4-4-2"
            starting_xp = 0.0
            effective_xp = 0.0

            try:
                from analytics.xp_model import XPModel
                xp_mod = XPModel(gameweek=gw, fpl_client=self.client)
                lineup_res = xp_mod.optimize_lineup()

                starters_df = lineup_res["starting_xi"]
                bench_df = lineup_res["bench"]

                starters = []
                for s in starters_df.to_dict(orient="records"):
                    s_rec = dict(s)
                    xp_val = float(s_rec.get("xP", s_rec.get("projected_xp", 0.0)))
                    s_rec["projected_xp"] = xp_val
                    s_rec["xP"] = xp_val
                    starters.append(s_rec)

                bench = []
                for b in bench_df.to_dict(orient="records"):
                    b_rec = dict(b)
                    xp_val = float(b_rec.get("xP", b_rec.get("projected_xp", 0.0)))
                    b_rec["projected_xp"] = xp_val
                    b_rec["xP"] = xp_val
                    bench.append(b_rec)

                cap_name = lineup_res["captain"]["web_name"]
                vc_name = lineup_res["vice_captain"]["web_name"]
                formation = lineup_res["formation"]
                starting_xp = float(lineup_res["base_starting_xp"])
                effective_xp = float(lineup_res["effective_total_xp"])
                dynamic_success = True
                logger.info("Dynamic XPModel optimization succeeded for GW%d: formation=%s, cap=%s, eff_xp=%.1f",
                            gw, formation, cap_name, effective_xp)
            except Exception as e:
                logger.warning("Dynamic XPModel unavailable for GW%d (%s); falling back to baseline squad", gw, e)
                dynamic_success = False

            if not dynamic_success:
                starters = [
                    {
                        "web_name": name,
                        "position_name": pos,
                        "club_short": club,
                        "now_cost": cost,
                        "projected_xp": xp,
                        "xP": xp
                    }
                    for name, pos, club, cost, xp in default_squad_names
                ]
                bench = [
                    {
                        "web_name": name,
                        "position_name": pos,
                        "club_short": club,
                        "now_cost": cost,
                        "projected_xp": xp,
                        "xP": xp
                    }
                    for name, pos, club, cost, xp in bench_names
                ]
                cap_name = "Isak" if gw in [1, 2] else "Foden"
                vc_name = "Ødegaard"
                formation = "4-4-2"
                starting_xp = sum(s["projected_xp"] for s in starters)
                cap_xp = next(s["projected_xp"] for s in starters if s["web_name"] == cap_name)
                effective_xp = starting_xp + cap_xp

            self.snapshot_suggestion(
                gw=gw,
                season=current_season,
                starters=starters,
                bench=bench,
                captain_name=cap_name,
                vice_captain_name=vc_name,
                formation=formation,
                projected_starting_xp=starting_xp,
                projected_effective_xp=effective_xp,
                profile_name="Rubies Rangers",
                applied_by_user=True
            )

            # Reconcile if live data exists
            self.reconcile_gameweek(current_season, gw)
            seeded_count += 1

        return seeded_count
