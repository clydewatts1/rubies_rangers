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
import os
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



class LiveFPLClient:
    """Production live FPL API client for real-world automated execution."""
    def __init__(self, entry_id: int = 6173410, auth_cookie: str | None = None, dry_run: bool = True) -> None:
        from config_manager import get_system_config
        self.entry_id = entry_id
        self.auth_cookie = auth_cookie or os.environ.get("FPL_AUTH_COOKIE") or get_system_config("access_token")
        self.dry_run = dry_run
        from clients.fpl_client import FPLClient
        self._fpl_client = FPLClient()
        self.is_authenticated = False
        self._simulated_picks: list[dict[str, Any]] | None = None
        self._simulated_transfers: list[dict[str, Any]] | None = None

    @property
    def _cookie_header(self) -> str:
        if not self.auth_cookie:
            return ""
        val = self.auth_cookie.strip()
        if "access_token=" in val or "pl_profile=" in val or ";" in val:
            return val
        return f"access_token={val}; pl_profile={val}"

    def _auth_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RubiesRangers/1.0",
        }
        if self._cookie_header:
            headers["Cookie"] = self._cookie_header
        if self.auth_cookie:
            val = self.auth_cookie.strip()
            # If it looks like a raw JWT access token, pass it as Authorization Bearer header as well
            if val.startswith("eyJ") and " " not in val and ";" not in val:
                headers["Authorization"] = f"Bearer {val}"
        return headers

    async def authenticate(self) -> Color_Session:
        from clients.auth_manager import AuthManager
        auth_mgr = AuthManager()
        now = datetime.now(timezone.utc)

        if self.auth_cookie:
            session_info = auth_mgr.sync_browser_cookie(self.auth_cookie, source="DIRECT_ARG")
        else:
            session_info = auth_mgr.get_active_session()

        if session_info.is_authenticated:
            self.is_authenticated = True
            if session_info.entry_id:
                self.entry_id = session_info.entry_id
            self.auth_cookie = session_info.auth_token
            logger.info(f"[LiveFPLClient] Verified active session for {session_info.first_name} (Entry ID: {self.entry_id})")
            return Color_Session(
                auth_cookie=session_info.auth_token,
                csrf_token="live_csrf_token",
                expires_at=session_info.expires_at,
                is_authenticated=True,
                last_keepalive_utc=now,
            )

        # Fallback to unauthenticated / dry-run session
        self.is_authenticated = False
        logger.info(f"[LiveFPLClient] Operating in {'Dry-Run Simulated' if self.dry_run else 'Unauthenticated Read-Only'} mode (Auth: {session_info.error_message or 'No active session'})")
        return Color_Session(
            auth_cookie=self.auth_cookie or "unauthenticated_dry_run",
            csrf_token="dry_run_csrf",
            expires_at=now + timedelta(hours=4),
            is_authenticated=True if self.dry_run else False,
            last_keepalive_utc=now,
        )

    async def get_bootstrap_static(self) -> dict[str, Any]:
        df = self._fpl_client.get_players_df()
        if "club_id" in df.columns and "team" not in df.columns:
            df["team"] = df["club_id"]
        boot = self._fpl_client.get_bootstrap_data()
        injury_flags: dict[int, dict[str, Any]] = {}
        for el in boot.get("elements", []):
            if el.get("news"):
                injury_flags[el["id"]] = {
                    "chance_of_playing": el.get("chance_of_playing_next_round", 100),
                    "news": el.get("news", "")
                }
        return {"elements": df, "injury_flags": injury_flags}

    async def get_fixtures(self, event: int) -> list[dict[str, Any]]:
        return self._fpl_client.get_gameweek_fixtures(event)

    async def get_market_odds(self, event: int) -> dict[str, Any]:
        from config_manager import get_system_config
        odds = get_system_config("gw4_match_odds") or {}
        return {"event": event, "status": "live_nominal", "odds": odds}

    async def get_my_team(self, squad_entry_id: int | None = None, force_refresh: bool = False) -> dict[str, Any]:
        import requests
        eid = squad_entry_id or self.entry_id
        if self.auth_cookie and self.is_authenticated:
            try:
                r = requests.get(
                    f"https://fantasy.premierleague.com/api/my-team/{eid}/",
                    headers=self._auth_headers(),
                    timeout=10
                )
                if r.status_code == 200:
                    return r.json()
            except Exception as e:
                logger.warning(f"[LiveFPLClient] my-team fetch failed, falling back to public picks: {e}")

        # Public endpoint fallback for entry squad
        current_gw = self._fpl_client.get_current_gameweek() or 4
        url = f"https://fantasy.premierleague.com/api/entry/{eid}/event/{current_gw}/picks/"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = r.json()
        entry_hist = data.get("entry_history", {})
        bank = entry_hist.get("bank", 37)
        picks = self._simulated_picks or data.get("picks", [])
        return {
            "picks": picks,
            "transfers": {"bank": bank, "limit": 1},
            "chips": [
                {"name": "wildcard", "status_for_entry": "available"},
                {"name": "freehit", "status_for_entry": "available"},
                {"name": "3xc", "status_for_entry": "available"},
                {"name": "bboost", "status_for_entry": "available"},
            ],
            "active_chip": None,
            "current_event": current_gw,
        }

    async def post_transfers(self, payload: dict[str, Any]) -> dict[str, Any]:
        import requests
        if self.dry_run or not self.is_authenticated:
            logger.info(f"[LiveFPLClient: DRY RUN] Simulated transfers POST: {len(payload.get('transfers', []))} move(s)")
            self._simulated_transfers = payload.get("transfers", [])
            return {"status_code": 200, "result": "dry_run_success"}
        r = requests.post(
            "https://fantasy.premierleague.com/api/transfers/",
            json=payload,
            headers=self._auth_headers(),
            timeout=10
        )
        return {"status_code": r.status_code, "result": r.text}

    async def post_lineup(self, payload: dict[str, Any]) -> dict[str, Any]:
        import requests
        if self.dry_run or not self.is_authenticated:
            logger.info(f"[LiveFPLClient: DRY RUN] Simulated lineup POST: {len(payload.get('picks', []))} picks")
            self._simulated_picks = payload.get("picks", [])
            return {"status_code": 200, "result": "dry_run_success"}
        r = requests.post(
            f"https://fantasy.premierleague.com/api/my-team/{self.entry_id}/",
            json=payload,
            headers=self._auth_headers(),
            timeout=10
        )
        return {"status_code": r.status_code, "result": r.text}

    async def check_session_alive(self) -> bool:
        return True

    async def listen_for_leak(self, element_id: int) -> dict[str, Any] | None:
        boot = self._fpl_client.get_bootstrap_data()
        for el in boot.get("elements", []):
            if el["id"] == element_id:
                if el.get("chance_of_playing_next_round") == 0:
                    return {"element_id": element_id, "starts": False, "news": el.get("news")}
        return {"element_id": element_id, "starts": True}


class LiveSolverEngine:
    """Production optimizer bridging TwoStageOptimizer & FPLOptimizer with CPN."""
    async def solve_optimal_gameweek(self, squad: Color_SquadState, market: Color_MarketData) -> dict[str, Any]:
        df = market.elements
        squad_df = df[df["id"].isin(squad.squad_ids)].copy()

        # Prioritize available players for starting XI
        avail_squad = squad_df[squad_df["status"] == "a"]
        gkps = avail_squad[avail_squad["position_name"] == "GKP"].sort_values(by="moneyball_score", ascending=False)
        defs = avail_squad[avail_squad["position_name"] == "DEF"].sort_values(by="moneyball_score", ascending=False)
        mids = avail_squad[avail_squad["position_name"] == "MID"].sort_values(by="moneyball_score", ascending=False)
        fwds = avail_squad[avail_squad["position_name"] == "FWD"].sort_values(by="moneyball_score", ascending=False)

        possible_formations = [(4, 4, 2), (3, 5, 2), (3, 4, 3), (4, 3, 3), (5, 3, 2), (5, 4, 1)]
        d_req, m_req, f_req = 4, 4, 2
        for d, m, f in possible_formations:
            if len(defs) >= d and len(mids) >= m and len(fwds) >= f:
                d_req, m_req, f_req = d, m, f
                break

        starters = []
        bench = []

        # 1 GKP
        gkp_picks = gkps if len(gkps) > 0 else squad_df[squad_df["position_name"] == "GKP"]
        starters.append(int(gkp_picks.iloc[0]["id"]))
        all_gkps = squad_df[squad_df["position_name"] == "GKP"]
        if len(all_gkps) > 1:
            bench.append(int(all_gkps.iloc[1]["id"]))

        for _, r in defs.iloc[:d_req].iterrows():
            starters.append(int(r["id"]))
        for _, r in mids.iloc[:m_req].iterrows():
            starters.append(int(r["id"]))
        for _, r in fwds.iloc[:f_req].iterrows():
            starters.append(int(r["id"]))

        # Populate bench with remaining squad assets
        for _, r in squad_df.iterrows():
            pid = int(r["id"])
            if pid not in starters and pid not in bench:
                bench.append(pid)

        starter_df = df[df["id"].isin(starters)].sort_values(by="moneyball_score", ascending=False)
        captain = int(starter_df.iloc[0]["id"]) if len(starter_df) > 0 else starters[0]
        vice_captain = int(starter_df.iloc[1]["id"]) if len(starter_df) > 1 else starters[1]

        return {
            "plan_id": f"live_plan_gw{squad.entry_id}_001",
            "starters": starters,
            "bench": bench,
            "captain": captain,
            "vice_captain": vice_captain,
            "transfers": [],
            "chip": None,
            "expected_utility": float(starter_df["moneyball_score"].sum()),
            "formation_tuple": (d_req, m_req, f_req),
            "fallback_plan": None,
            "contingency_tree": {},
        }


async def run_pipeline(
    gameweek: int | None = None,
    demo_mode: bool = False,
    entry_id: int | None = None,
    auth_cookie: str | None = None,
    dry_run: bool = True,
    target_deadline_mins: int = 5,
) -> None:
    """Runs a complete Timed Coloured Petri Net execution cycle."""
    legal_formations = {(3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3), (5, 3, 2), (5, 4, 1)}

    from config_manager import get_system_config
    resolved_entry_id = entry_id or get_system_config("default_entry_id") or 6173410

    if demo_mode:
        client: Any = DemoFPLClient(entry_id=resolved_entry_id)
        solver: Any = DemoSolverEngine()
        target_gw = gameweek or 1
        mode_label = "Synthetic Demo"
    else:
        client = LiveFPLClient(entry_id=resolved_entry_id, auth_cookie=auth_cookie, dry_run=dry_run)
        solver = LiveSolverEngine()
        from clients.fpl_client import FPLClient
        fpl_helper = FPLClient()
        target_gw = gameweek or fpl_helper.get_current_gameweek() or 5
        mode_label = "Live FPL API (Dry Run)" if dry_run else "Live FPL API (Live Commit)"

    journal = CPNDiagnosticJournal(log_dir="logs/diagnostics")
    await journal.record_event(
        record_type="pipeline_init",
        metrics={"gameweek": target_gw, "demo_mode": demo_mode, "dry_run": dry_run},
        context={"mode": mode_label, "entry_id": resolved_entry_id}
    )

    engine = CPNEngine(fpl_client=client, solver_engine=solver, legal_formations=legal_formations)

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(minutes=target_deadline_mins)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("\n" + "="*70)
    print("  [CPN] RUBIES RANGERS AUTONOMOUS EXECUTION PIPELINE  ")
    print(f"  Mode: {mode_label} | Gameweek: {target_gw} | Entry ID: {resolved_entry_id}")
    print(f"  Target Deadline UTC: {deadline.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")

    logger.info(f"Starting CPN execution cycle in {mode_label} mode...")
    t0 = datetime.now()

    await engine.run_gameweek_cycle(gameweek=target_gw, deadline_utc=deadline)

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

    summary = await journal.get_daily_summary()
    print(f"\n  [DIAGNOSTICS] Daily Journal: {summary.get('total_events', 0)} events recorded.")
    print(f"  [METRICS] Total Duration: {elapsed:.2f}s\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rubies Rangers CPN Autonomous Execution Pipeline")
    parser.add_argument("--live", action="store_true", help="Connect to the live official Premier League API")
    parser.add_argument("--demo", action="store_true", help="Run in local synthetic demonstration mode")
    parser.add_argument("--execute-live", action="store_true", help="Allow real mutating HTTP POST requests (disabled by default)")
    parser.add_argument("--gameweek", "-g", type=int, default=None, help="Target Gameweek (default: auto-detected next GW)")
    parser.add_argument("--entry-id", "-e", type=int, default=None, help="Manager team ID (default: from config.yaml)")
    parser.add_argument("--cookie", "-c", type=str, default=None, help="pl_profile session cookie for live authentication")
    args = parser.parse_args()

    # Determine mode
    is_live = args.live or (not args.demo and not args.live)
    demo_mode = args.demo and not args.live
    dry_run = not args.execute_live

    asyncio.run(run_pipeline(
        gameweek=args.gameweek,
        demo_mode=demo_mode,
        entry_id=args.entry_id,
        auth_cookie=args.cookie,
        dry_run=dry_run
    ))


if __name__ == "__main__":
    main()
