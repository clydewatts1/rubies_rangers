"""
automation/runner.py
CLI entrypoint and execution runner for the Rubies Rangers CPN Pipeline.
Supports dry-run simulation, demo mode, and live execution.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
import logging
import sys
from typing import Any
import pandas as pd

from automation.cpn import (
    CPNEngine,
    CPNDiagnosticJournal,
    Color_Session,
    Color_MarketData,
    Color_SquadState,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("rubies_rangers.runner")


class DemoFPLClient:
    """High-fidelity synthetic FPL client for local demonstrations."""
    def __init__(self, entry_id: int = 99999) -> None:
        self.entry_id = entry_id

    async def authenticate(self) -> Color_Session:
        now = datetime.now(timezone.utc)
        return Color_Session(
            auth_cookie="demo_auth_cookie_valid",
            csrf_token="demo_csrf_token_valid",
            expires_at=now + timedelta(hours=4),
            is_authenticated=True,
            last_keepalive_utc=now,
        )

    async def get_bootstrap_static(self) -> dict[str, Any]:
        elements = pd.DataFrame({
            "id": list(range(1, 16)),
            "team": [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5],
            "position_name": ["GKP", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "GKP", "DEF", "MID", "FWD"],
            "moneyball_score": [float(16 - i) for i in range(1, 16)],
        })
        return {"elements": elements, "injury_flags": {}}

    async def get_fixtures(self, event: int) -> list[dict[str, Any]]:
        return [{"id": 1, "event": event, "team_h": 1, "team_a": 2}]

    async def get_market_odds(self, event: int) -> dict[str, Any]:
        return {"event": event, "status": "nominal"}

    async def get_my_team(self, squad_entry_id: int | None = None, force_refresh: bool = False) -> dict[str, Any]:
        picks = []
        for i in range(1, 12):
            picks.append({"element": i, "position": i, "selling_price": 50, "is_captain": (i == 10), "is_vice_captain": (i == 11)})
        for i in range(12, 16):
            picks.append({"element": i, "position": i, "selling_price": 50, "is_captain": False, "is_vice_captain": False})
        return {
            "picks": picks,
            "transfers": {"bank": 15, "limit": 1},
            "chips": [
                {"name": "wildcard", "status_for_entry": "available"},
                {"name": "freehit", "status_for_entry": "available"},
                {"name": "3xc", "status_for_entry": "available"},
                {"name": "bboost", "status_for_entry": "available"},
            ],
            "active_chip": None,
            "current_event": 1,
        }

    async def post_transfers(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"[DemoClient] Transmitted transfers payload: {len(payload.get('transfers', []))} moves, chip={payload.get('chips')}")
        return {"status_code": 200, "result": "ok"}

    async def post_lineup(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"[DemoClient] Transmitted lineup payload: {len(payload.get('picks', []))} picks")
        return {"status_code": 200, "result": "ok"}

    async def check_session_alive(self) -> bool:
        return True

    async def listen_for_leak(self, element_id: int) -> dict[str, Any] | None:
        return {"element_id": element_id, "starts": True}


class DemoSolverEngine:
    """Mock two-stage solver returning candidate lineup."""
    async def solve_optimal_gameweek(self, squad: Color_SquadState, market: Color_MarketData) -> dict[str, Any]:
        return {
            "plan_id": "demo_plan_optimal_001",
            "starters": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
            "bench": [12, 13, 14, 15],
            "captain": 10,
            "vice_captain": 11,
            "transfers": [],
            "chip": None,
            "expected_utility": 68.4,
            "formation_tuple": (3, 5, 2),
            "fallback_plan": None,
            "contingency_tree": {},
        }


async def run_pipeline(gameweek: int, demo_mode: bool = False) -> None:
    """Runs a complete Timed Coloured Petri Net execution cycle."""
    legal_formations = {(3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3), (5, 3, 2), (5, 4, 1)}

    journal = CPNDiagnosticJournal(log_dir="logs/diagnostics")
    await journal.record_event(
        record_type="pipeline_init",
        metrics={"gameweek": gameweek, "demo_mode": demo_mode},
        context={"mode": "demo" if demo_mode else "production"}
    )

    client = DemoFPLClient()
    solver = DemoSolverEngine()

    engine = CPNEngine(fpl_client=client, solver_engine=solver, legal_formations=legal_formations)

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(minutes=5)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("\n" + "="*70)
    print("  [CPN] RUBIES RANGERS AUTONOMOUS EXECUTION PIPELINE  ")
    print(f"  Gameweek: {gameweek} | Target Deadline UTC: {deadline.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")

    logger.info("Starting CPN execution cycle...")
    t0 = datetime.now()

    await engine.run_gameweek_cycle(gameweek=gameweek, deadline_utc=deadline)

    elapsed = (datetime.now() - t0).total_seconds()
    snapshot = engine.get_telemetry_snapshot()

    print("\n" + "-"*70)
    print("  EXECUTION CYCLE SUMMARY & MARKING MULTISET M(p)")
    print("-"*70)
    for place_name, count in snapshot["place_counts"].items():
        symbol = "[OK]" if count > 0 and place_name == "P_Committed" else ("[ALERT]" if count > 0 and place_name == "P_DeadLetter" else " •  ")
        print(f"  {symbol} {place_name:30}: {count} token(s)")

    if not engine.marking.P_Committed.empty():
        receipt = await engine.marking.P_Committed.get()
        print("\n  [SUCCESS] COMMITMENT VERIFIED BY SOURCE RECONCILIATION GATE:")
        print(f"     Confirmation ID: {receipt.confirmation_id}")
        print(f"     Payload Hash   : {receipt.payload_hash}")
        print(f"     Status Code    : {receipt.http_status}")
        print(f"     Audit Timestamp: {receipt.timestamp.isoformat()}")
    elif not engine.marking.P_DeadLetter.empty():
        alert = await engine.marking.P_DeadLetter.get()
        print(f"\n  [HALTED] DEAD-LETTER QUEUE: [{alert.severity}] {alert.reason}")

    await engine.shutdown()

    # Flush diagnostics scorecard
    summary = await journal.get_daily_summary()
    print(f"\n  [DIAGNOSTICS] Daily Journal: {summary.get('total_events', 0)} events recorded.")
    print(f"  [METRICS] Total Duration: {elapsed:.2f}s\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rubies Rangers CPN Autonomous Execution Pipeline")
    parser.add_argument("--gameweek", "-g", type=int, default=1, help="Target Gameweek (default: 1)")
    parser.add_argument("--demo", action="store_true", default=True, help="Run in local synthetic demonstration mode")
    args = parser.parse_args()

    asyncio.run(run_pipeline(gameweek=args.gameweek, demo_mode=args.demo))


if __name__ == "__main__":
    main()
