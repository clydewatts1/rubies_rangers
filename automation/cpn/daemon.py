"""
automation/cpn/daemon.py
Autonomous 24/7 Background Daemon for the Rubies Rangers CPN Pipeline.
Monitors Premier League fixture deadlines, schedules preflight and execution windows,
and autonomously dispatches transfers and lineups without manual intervention.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Optional

from clients.fpl_client import FPLClient
from config_manager import get_system_config

logger = logging.getLogger("rubies_rangers.cpn.daemon")


def _format_seconds(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 0:
        return "Passed"
    total_secs = int(seconds)
    days = total_secs // 86400
    hours = (total_secs % 86400) // 3600
    mins = (total_secs % 3600) // 60
    secs = total_secs % 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    if days == 0 and hours == 0:
        parts.append(f"{secs}s")
    return " ".join(parts)


class CPNDaemon:
    """
    Autonomous CPN Background Daemon.
    Maintains a continuous loop watching FPL deadlines and executing gameweek cycles.
    """

    def __init__(self) -> None:
        self.is_running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self.fpl_client = FPLClient()

        # Configuration options
        self.live: bool = True
        self.dry_run: bool = True
        self.check_interval_seconds: int = 60
        self.preflight_lead_minutes: int = 35
        self.entry_id: Optional[int] = None

        # State tracking
        self.status: str = "STOPPED"  # STOPPED, WATCHING_DEADLINE, EXECUTING_CYCLE, WAITING_FOR_ROLLOVER, ERROR
        self.started_at_utc: Optional[datetime] = None
        self.last_heartbeat_utc: Optional[datetime] = None
        self.last_run_at_utc: Optional[datetime] = None
        self.last_run_gameweek: Optional[int] = None
        self.last_run_result: Optional[dict[str, Any]] = None
        self.total_cycles_completed: int = 0
        self.executed_gameweeks: set[int] = set()
        self.next_gameweek: Optional[int] = None
        self.next_deadline_utc: Optional[datetime] = None
        self.error_message: Optional[str] = None

    def _get_next_event(self) -> tuple[Optional[int], Optional[datetime], Optional[str]]:
        """Query FPL bootstrap data for next upcoming event and deadline."""
        try:
            boot = self.fpl_client.get_bootstrap_data()
            events = boot.get("events", [])
            now = datetime.now(timezone.utc)

            # Search for is_next == True
            for event in events:
                if event.get("is_next"):
                    eid = event.get("id")
                    name = event.get("name", f"Gameweek {eid}")
                    dl_str = event.get("deadline_time")
                    if dl_str:
                        dl = datetime.fromisoformat(dl_str.replace("Z", "+00:00"))
                        return eid, dl, name

            # Fallback to any future event
            for event in events:
                dl_str = event.get("deadline_time")
                if dl_str:
                    dl = datetime.fromisoformat(dl_str.replace("Z", "+00:00"))
                    if dl > now:
                        return event.get("id"), dl, event.get("name")

            # Fallback to next calculated gameweek
            curr_gw = self.fpl_client.get_current_gameweek() or 5
            fallback_dl = now + timedelta(days=5)
            return curr_gw, fallback_dl, f"Gameweek {curr_gw}"
        except Exception as ex:
            logger.warning(f"[CPNDaemon] Could not resolve next event from FPL API: {ex}")
            curr_gw = get_system_config("target_gameweek") or 5
            return curr_gw, datetime.now(timezone.utc) + timedelta(days=5), f"Gameweek {curr_gw}"

    async def start(
        self,
        live: bool = True,
        dry_run: bool = True,
        check_interval_seconds: int = 60,
        preflight_lead_minutes: int = 35,
        entry_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Start the background daemon watcher."""
        async with self._lock:
            if self.is_running:
                return {"success": False, "message": "CPN Daemon is already running.", "status": self.get_status()}

            self.live = live
            self.dry_run = dry_run
            self.check_interval_seconds = max(10, check_interval_seconds)
            self.preflight_lead_minutes = max(5, preflight_lead_minutes)
            self.entry_id = entry_id or get_system_config("default_entry_id") or 6173410
            self.is_running = True
            self.started_at_utc = datetime.now(timezone.utc)
            self.status = "WATCHING_DEADLINE"
            self.error_message = None

            eid, dl, name = self._get_next_event()
            self.next_gameweek = eid
            self.next_deadline_utc = dl

            self._task = asyncio.create_task(self._daemon_loop())
            logger.info(f"[CPNDaemon] Started autonomous background daemon. Watching GW {eid} (Deadline: {dl}).")
            return {"success": True, "message": f"Autonomous CPN Daemon started for {name}.", "status": self.get_status()}

    async def stop(self) -> dict[str, Any]:
        """Stop the background daemon watcher."""
        async with self._lock:
            if not self.is_running:
                return {"success": False, "message": "CPN Daemon is not running.", "status": self.get_status()}

            self.is_running = False
            self.status = "STOPPED"
            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

            logger.info("[CPNDaemon] Autonomous background daemon stopped.")
            return {"success": True, "message": "Autonomous CPN Daemon stopped.", "status": self.get_status()}

    async def _daemon_loop(self) -> None:
        """Continuous background execution and monitoring loop."""
        from automation.runner import LiveFPLClient, LiveSolverEngine, DemoFPLClient, DemoSolverEngine
        from automation.cpn import CPNEngine, CPNDiagnosticJournal

        legal_formations = {(3, 5, 2), (3, 4, 3), (4, 4, 2), (4, 3, 3), (5, 3, 2), (5, 4, 1)}

        while self.is_running:
            try:
                now = datetime.now(timezone.utc)
                self.last_heartbeat_utc = now

                # Refresh next event and deadline
                eid, dl, name = self._get_next_event()
                self.next_gameweek = eid
                self.next_deadline_utc = dl

                if dl:
                    seconds_to_deadline = (dl - now).total_seconds()
                    minutes_to_deadline = seconds_to_deadline / 60.0

                    # Check if we have entered the preflight execution window
                    # Window: 0 < minutes_to_deadline <= preflight_lead_minutes
                    if 0 < minutes_to_deadline <= self.preflight_lead_minutes:
                        if eid not in self.executed_gameweeks:
                            logger.info(
                                f"[CPNDaemon] Approaching {name} deadline ({minutes_to_deadline:.1f}m remaining). "
                                f"Triggering autonomous CPN cycle!"
                            )
                            self.status = f"EXECUTING_CYCLE_GW{eid}"

                            # Initialize client & solver
                            if self.live:
                                client: Any = LiveFPLClient(entry_id=self.entry_id, dry_run=self.dry_run)
                                solver: Any = LiveSolverEngine()
                            else:
                                client = DemoFPLClient(entry_id=self.entry_id)
                                solver = DemoSolverEngine()

                            journal = CPNDiagnosticJournal(log_dir="logs/diagnostics")
                            engine = CPNEngine(
                                fpl_client=client,
                                solver_engine=solver,
                                legal_formations=legal_formations,
                                journal=journal,
                            )

                            t0 = datetime.now(timezone.utc)
                            await engine.run_gameweek_cycle(gameweek=eid, deadline_utc=dl)
                            duration_s = (datetime.now(timezone.utc) - t0).total_seconds()

                            receipt_dict = None
                            if not engine.marking.P_Committed.empty():
                                r = await engine.marking.P_Committed.get()
                                receipt_dict = {
                                    "confirmation_id": r.confirmation_id,
                                    "payload_hash": r.payload_hash,
                                    "http_status": r.http_status,
                                    "timestamp": r.timestamp.isoformat(),
                                }

                            alert_dict = None
                            if not engine.marking.P_DeadLetter.empty():
                                a = await engine.marking.P_DeadLetter.get()
                                alert_dict = {
                                    "severity": a.severity,
                                    "reason": a.reason,
                                    "context": a.context,
                                }

                            await engine.shutdown()

                            self.executed_gameweeks.add(eid)
                            self.total_cycles_completed += 1
                            self.last_run_at_utc = datetime.now(timezone.utc)
                            self.last_run_gameweek = eid
                            self.last_run_result = {
                                "success": receipt_dict is not None,
                                "gameweek": eid,
                                "duration_seconds": round(duration_s, 2),
                                "receipt": receipt_dict,
                                "alert": alert_dict,
                                "executed_at": self.last_run_at_utc.isoformat(),
                            }
                            logger.info(
                                f"[CPNDaemon] Concluded cycle for {name}. "
                                f"Result: {'SUCCESS' if receipt_dict else 'ALERT'}"
                            )
                        else:
                            self.status = f"CYCLE_COMPLETED_GW{eid}"
                    elif minutes_to_deadline <= 0:
                        self.status = f"WAITING_FOR_GW_ROLLOVER"
                    else:
                        self.status = f"WATCHING_GW{eid}_DEADLINE"
                else:
                    self.status = "IDLE_AWAITING_SCHEDULE"

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.error_message = str(e)
                logger.error(f"[CPNDaemon] Error in daemon loop: {e}", exc_info=True)

            try:
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                break

    def get_status(self) -> dict[str, Any]:
        """Provide real-time telemetry snapshot of the autonomous daemon."""
        now = datetime.now(timezone.utc)
        time_to_dl_s: Optional[float] = None
        time_to_dl_human = "N/A"

        if self.next_deadline_utc:
            time_to_dl_s = (self.next_deadline_utc - now).total_seconds()
            time_to_dl_human = _format_seconds(time_to_dl_s)

        mode_str = ("Live FPL API (Dry Run)" if self.dry_run else "Live FPL API (Live Commit)") if self.live else "Synthetic Demo"

        indicator_badge = "🟢 ACTIVE" if self.is_running else "⚪ STOPPED"
        indicator_html = (
            "<span style='color: #4ade80; font-weight: bold;'>🟢 ACTIVE (WATCHING)</span>"
            if self.is_running
            else "<span style='color: #94a3b8; font-weight: bold;'>⚪ STOPPED (IDLE)</span>"
        )

        return {
            "is_running": self.is_running,
            "indicator": indicator_badge,
            "indicator_html": indicator_html,
            "status": self.status,
            "mode": mode_str,
            "target_entry_id": self.entry_id,
            "current_time_utc": now.isoformat(),
            "started_at_utc": self.started_at_utc.isoformat() if self.started_at_utc else None,
            "last_heartbeat_utc": self.last_heartbeat_utc.isoformat() if self.last_heartbeat_utc else None,
            "next_gameweek": self.next_gameweek,
            "next_deadline_utc": self.next_deadline_utc.isoformat() if self.next_deadline_utc else None,
            "time_until_deadline_seconds": round(time_to_dl_s, 1) if time_to_dl_s is not None else None,
            "time_until_deadline_human": time_to_dl_human,
            "preflight_lead_minutes": self.preflight_lead_minutes,
            "check_interval_seconds": self.check_interval_seconds,
            "total_cycles_completed": self.total_cycles_completed,
            "executed_gameweeks": list(self.executed_gameweeks),
            "last_run": self.last_run_result,
            "error_message": self.error_message,
        }


# Global daemon singleton instance
_cpn_daemon_instance: Optional[CPNDaemon] = None


def get_cpn_daemon() -> CPNDaemon:
    """Retrieve the global CPNDaemon singleton instance."""
    global _cpn_daemon_instance
    if _cpn_daemon_instance is None:
        _cpn_daemon_instance = CPNDaemon()
    return _cpn_daemon_instance
