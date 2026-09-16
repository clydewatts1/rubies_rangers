"""
automation/challenge_runner.py
Standalone CLI Runner for the FPL Challenge Coloured Petri Net (CPN).
Executes completely standalone in pure Python without requiring the FastAPI service.
Supports both dry-run simulation and live account execution (Clyde Watts, Entry 6173410).
Outputs structured transition logs and model validation setting comparisons.

Usage:
    python -m automation.challenge_runner --dry-run --archetype gpp_upside --sims 2500
    python -m automation.challenge_runner --live --entry 6173410
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from automation.challenge_cpn.engine import ChallengeCPNEngine
from clients.auth_manager import AuthManager
from config_manager import get_system_config, get_active_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("rubies_rangers.challenge_runner")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FPL Challenge Autonomous Coloured Petri Net (CPN) Standalone Runner"
    )
    parser.add_argument("--gameweek", type=int, default=5, help="Target Challenge Gameweek (default: 5)")
    parser.add_argument("--entry", type=int, default=None, help="FPL Team / Entry ID (default: active session or 6173410)")
    parser.add_argument("--archetype", choices=["max_ev", "safe_floor", "gpp_upside"], default="max_ev",
                        help="Tournament strategic archetype (default: max_ev)")
    parser.add_argument("--preset", type=str, default=None, help="Challenge rule preset key (e.g. gw5_one_player_per_club)")
    parser.add_argument("--sims", type=int, default=2500, help="Monte Carlo tournament draws (default: 2500)")
    parser.add_argument("--retries", type=int, default=3, help="Maximum Saga verification retries (default: 3)")
    parser.add_argument("--live", action="store_true", help="Execute live against official FPL Challenge API")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Simulate execution without modifying live team (default: True)")
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> int:
    is_live = args.live
    dry_run = not is_live

    # 1. Resolve Manager Authentication
    auth_mgr = AuthManager()
    session = auth_mgr.get_active_session()
    resolved_entry = args.entry or session.entry_id or get_system_config("default_entry_id") or 6173410

    auth_headers: Optional[Dict[str, str]] = None
    if session.is_authenticated:
        auth_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RubiesRangersChallenge/1.0",
            "Cookie": session.cookie_header
        }
        if session.auth_token.startswith("eyJ") and ";" not in session.auth_token:
            auth_headers["Authorization"] = f"Bearer {session.auth_token}"
        manager_label = f"{session.first_name} {session.last_name} (Entry #{resolved_entry})"
    else:
        manager_label = f"Guest / Offline Manager (Entry #{resolved_entry})"

    print("=" * 80)
    print(" 🎯 RUBIES RANGERS — FPL CHALLENGE AUTONOMOUS CPN RUNNER")
    print("=" * 80)
    print(f" Manager Session  : {manager_label}")
    print(f" Execution Mode   : {'🔴 LIVE REAL-WORLD EXECUTION' if is_live else '🟢 STANDALONE DRY-RUN SIMULATION'}")
    print(f" Target Gameweek  : GW{args.gameweek}")
    print(f" Target Archetype : {args.archetype.upper()}")
    print(f" Monte Carlo Draws: {args.sims:,} joint draws")
    print(f" Active Profile   : {get_active_profile().upper()}")
    print("=" * 80)

    # 2. Instantiate and Run Challenge CPN Engine
    engine = ChallengeCPNEngine(dry_run=dry_run)
    result = await engine.run_pipeline(
        gameweek=args.gameweek,
        entry_id=resolved_entry,
        archetype=args.archetype,
        preset_key=args.preset,
        n_simulations=args.sims,
        auth_headers=auth_headers,
        max_retries=args.retries,
        verification_delay_seconds=0.3 if dry_run else 1.0
    )

    # 3. Print Structured Results & Invariant Comparison Report
    print("\n" + "=" * 80)
    print(" 📊 EXECUTION OUTCOME & DIAGNOSTIC SUMMARY")
    print("=" * 80)
    print(f" Overall Status   : {'✅ SUCCESS' if result.get('success') else '❌ FAILED'}")
    print(f" Pipeline Duration: {result.get('duration_ms', 0):.1f} ms")

    if "plan" in result:
        p = result["plan"]
        print(f"\n[OPTIMIZED SQUAD SELECTION]")
        print(f" • Archetype    : {p.get('archetype', '').upper()}")
        print(f" • Squad ({p.get('picks_count')}): {', '.join(p.get('squad', []))}")
        print(f" • Captain      : {p.get('captain')} (2x Armband)")
        print(f" • Vice-Captain : {p.get('vice_captain')}")
        print(f" • Expected EV  : {p.get('expected_utility')} pts")
        print(f" • P99 Right-Tail: {p.get('tournament_p99')} pts")

    if "validation" in result:
        v = result["validation"]
        comp = v.get("setting_comparison", {})
        print(f"\n[MODEL VALIDATION & CONFIGURATION COMPARISON]")
        print(f" • Invariant Checks: {'✅ ALL PASSED' if v.get('is_valid') else '⚠️ ANOMALIES DETECTED'}")
        print(f" • Checks Passed   : {len(v.get('checks_passed', []))} checks")
        for cp in v.get("checks_passed", []):
            print(f"   ✓ {cp}")
        if v.get("errors"):
            print(f" • Constraint Errors: {v.get('errors')}")
        if v.get("warnings"):
            print(f" • Warnings: {v.get('warnings')}")

        print(f"\n[SETTING MATRIX VS CONFIG.YAML]")
        print(f" • Active Profile   : {comp.get('active_profile')}")
        print(f" • Budget Cap       : £{comp.get('config_budget_cap', 0):.1f}m (Actual Cost: £{comp.get('actual_spend', 0):.1f}m)")
        print(f" • Club Quota Limit : Max {comp.get('rule_club_limit')} per club (Actual Max: {comp.get('actual_max_club')})")
        print(f" • Clubs Represented: {comp.get('clubs_represented')} unique clubs")
        print(f" • Formation Output : {comp.get('formation')}")
        print(f" • Field Win Prob   : {comp.get('win_probability_pct')}%")

    if "amendment_delta" in result:
        d = result["amendment_delta"]
        print(f"\n[AMENDMENT DELTA (INITIAL VS OPTIMAL)]")
        print(f" • Initial Squad   : {d.get('initial_element_ids')} (C: {d.get('initial_captain_id')}, VC: {d.get('initial_vice_captain_id')})")
        print(f" • Transfers In    : {d.get('transfers_in')}")
        print(f" • Transfers Out   : {d.get('transfers_out')}")
        t_in = len(d.get("transfers_in", []))
        t_out = len(d.get("transfers_out", []))
        status_str = "IDENTICAL (No-Op)" if d.get("is_identical") else f"MODIFIED (+{t_in} in / -{t_out} out)"
        print(f" • Lineup Status   : {status_str}")

    if "receipt" in result:
        r = result["receipt"]
        print(f"\n[SAGA VERIFICATION RECEIPT]")
        print(f" • Transaction ID   : {r.get('transaction_id')}")
        print(f" • Verified on Server: {'✅ YES' if r.get('verified') else '❌ NO'}")
        print(f" • Attempts Required: {r.get('attempts_required')} attempt(s)")
        print(f" • Element IDs      : {r.get('element_ids')}")

    if result.get("error"):
        print(f"\n[ERROR DETAILS]: {result.get('error')}")

    print("=" * 80 + "\n")
    return 0 if result.get("success") else 1


def main() -> None:
    args = parse_args()
    ret = asyncio.run(async_main(args))
    sys.exit(ret)


if __name__ == "__main__":
    main()
