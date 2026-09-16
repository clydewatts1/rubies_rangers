"""
automation/challenge_cpn/diagnostics.py
Structured diagnostic logging and audit journal for the Challenge Coloured Petri Net.
Appends immutable audit events to JSONL files in logs/diagnostics/.
Provides real-time inspection for Streamlit UI and diagnostic debugging.
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DEFAULT_LOG_DIR = os.path.join(_PROJECT_ROOT, "logs", "diagnostics")

logger = logging.getLogger("rubies_rangers.challenge.diagnostics")


class ChallengeCPNDiagnosticJournal:
    """Thread-safe, append-only diagnostic journal for FPL Challenge CPN execution."""

    def __init__(self, log_dir: str = _DEFAULT_LOG_DIR) -> None:
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self._memory_buffer: List[Dict[str, Any]] = []

    def _get_log_filepath(self) -> str:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"challenge_cpn_journal_{today_str}.jsonl")

    def log_event(self, record_type: str, data: Dict[str, Any]) -> None:
        """Persists a structured diagnostic entry to memory and disk."""
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "record_type": record_type,
            "data": data,
        }
        self._memory_buffer.append(entry)
        filepath = self._get_log_filepath()
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning("[ChallengeJournal] Could not write to journal file: %s", e)

    def record_transition(
        self,
        transition_name: str,
        status: str,
        duration_ms: float = 0.0,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Logs a CPN transition firing event."""
        self.log_event("transition_firing", {
            "transition": transition_name,
            "status": status,
            "duration_ms": round(duration_ms, 2),
            "context": context or {}
        })

    def record_model_validation(
        self,
        plan_id: str,
        is_valid: bool,
        error_count: int,
        warning_count: int,
        errors: List[str],
        warnings: List[str],
        setting_comparison: Dict[str, Any]
    ) -> None:
        """Logs the model error & configuration setting comparison report."""
        self.log_event("model_validation", {
            "plan_id": plan_id,
            "is_valid": is_valid,
            "error_count": error_count,
            "warning_count": warning_count,
            "errors": errors,
            "warnings": warnings,
            "setting_comparison": setting_comparison
        })

    def record_saga_step(
        self,
        transaction_id: str,
        attempt: int,
        max_retries: int,
        action: str,
        status: str,
        diff: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Logs a Saga submission or verification attempt."""
        self.log_event("saga_step", {
            "transaction_id": transaction_id,
            "attempt": attempt,
            "max_retries": max_retries,
            "action": action,
            "status": status,
            "diff": diff,
            "error_message": error_message,
        })

    def record_receipt(self, receipt_dict: Dict[str, Any]) -> None:
        """Logs a terminal confirmed execution receipt."""
        self.log_event("confirmed_receipt", receipt_dict)

    def record_alert(self, level: str, source: str, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Logs an operational alert or warning."""
        self.log_event("operational_alert", {
            "level": level,
            "source": source,
            "message": message,
            "context": context or {}
        })

    def get_recent_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the most recent in-memory log entries for UI display."""
        return list(reversed(self._memory_buffer[-limit:]))

    def tail(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Reads the most recent diagnostic journal records.
        Prefers in-memory buffer, falling back to reading the JSONL file on disk if buffer is empty.
        """
        if self._memory_buffer:
            return self._memory_buffer[-limit:]
        filepath = self._get_log_filepath()
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
                return [json.loads(line.strip()) for line in lines[-limit:] if line.strip()]
        except Exception as e:
            logger.warning("[ChallengeJournal] Could not read tail from disk: %s", e)
            return []
