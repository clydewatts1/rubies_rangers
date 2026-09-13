"""
automation/cpn/diagnostics.py
Continuous daily diagnostic journal and profiling recorder for the CPN Engine.
Zero-overhead, asynchronous, non-blocking disk persistence.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone, date
import json
import os
import psutil
from typing import Any


class CPNDiagnosticJournal:
    """
    Asynchronous daily diagnostic recorder.
    Buffers events in memory and periodically flushes to logs/diagnostics/cpn_journal_YYYY-MM-DD.jsonl.
    """
    def __init__(self, log_dir: str = "logs/diagnostics") -> None:
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._process = psutil.Process()

    def _get_daily_filepath(self, target_date: date | None = None) -> str:
        today_str = (target_date or date.today()).isoformat()
        return os.path.join(self.log_dir, f"cpn_journal_{today_str}.jsonl")

    async def record_event(
        self,
        record_type: str,
        metrics: dict[str, Any],
        context: dict[str, Any] | None = None,
        invariants: dict[str, Any] | None = None
    ) -> None:
        """Asynchronously appends a diagnostic event."""
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "record_type": record_type,
            "metrics": metrics,
            "context": context or {},
            "invariants_checked": invariants or {},
            "runtime_health": {
                "memory_rss_mb": round(self._process.memory_info().rss / (1024 * 1024), 2),
                "cpu_percent": self._process.cpu_percent(interval=None)
            }
        }
        should_flush = False
        async with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= 10:
                should_flush = True
        if should_flush:
            await self.flush()

    async def flush(self) -> None:
        """Flushes buffered diagnostic records to the daily JSONL file."""
        if not self._buffer:
            return
        async with self._lock:
            filepath = self._get_daily_filepath()
            records_to_write = list(self._buffer)
            self._buffer.clear()

        def _write() -> None:
            with open(filepath, "a", encoding="utf-8") as f:
                for r in records_to_write:
                    f.write(json.dumps(r) + "\n")

        await asyncio.to_thread(_write)

    async def get_daily_summary(self, target_date: date | None = None) -> dict[str, Any]:
        """Aggregates daily events from the journal into a health summary scorecard."""
        await self.flush()
        target = target_date or date.today()
        filepath = self._get_daily_filepath(target)

        summary: dict[str, Any] = {
            "date": target.isoformat(),
            "total_events": 0,
            "event_counts": {},
            "max_memory_rss_mb": 0.0,
        }

        if not os.path.exists(filepath):
            return summary

        def _read() -> list[dict[str, Any]]:
            records = []
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            return records

        records = await asyncio.to_thread(_read)
        summary["total_events"] = len(records)
        for r in records:
            rtype = r.get("record_type", "unknown")
            summary["event_counts"][rtype] = summary["event_counts"].get(rtype, 0) + 1
            rss = r.get("runtime_health", {}).get("memory_rss_mb", 0.0)
            if rss > summary["max_memory_rss_mb"]:
                summary["max_memory_rss_mb"] = rss

        summary_filepath = os.path.join(self.log_dir, f"cpn_health_summary_{target.isoformat()}.json")
        def _write_summary() -> None:
            with open(summary_filepath, "w", encoding="utf-8") as sf:
                json.dump(summary, sf, indent=2)

        await asyncio.to_thread(_write_summary)
        return summary
