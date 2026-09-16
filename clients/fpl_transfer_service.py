"""
clients/fpl_transfer_service.py
Service for resolving player identities, building official FPL transfer payloads,
and executing transfer dispatch with live authentication or dry-run simulation.
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
import requests

from clients.auth_manager import AuthManager
from clients.fpl_client import FPLClient

logger = logging.getLogger("rubies_rangers.clients.transfers")

FPL_TRANSFERS_ENDPOINT = "https://fantasy.premierleague.com/api/transfers/"


def resolve_player_element(name: str, df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Resolves a player name to a specific element row in the FPL players DataFrame.
    Matches exact web_name, full_name, or substring case-insensitively.
    """
    if df is None or df.empty or not name:
        return None

    clean_name = name.strip().lower()

    # 1. Exact web_name match
    if "web_name" in df.columns:
        m = df[df["web_name"].str.lower() == clean_name]
        if not m.empty:
            return m.iloc[0]

    # 2. Exact full_name match
    if "full_name" in df.columns:
        m = df[df["full_name"].str.lower() == clean_name]
        if not m.empty:
            return m.iloc[0]

    # 3. Substring in web_name
    if "web_name" in df.columns:
        m = df[df["web_name"].str.contains(clean_name, case=False, na=False)]
        if not m.empty:
            return m.iloc[0]

    # 4. Substring in full_name
    if "full_name" in df.columns:
        m = df[df["full_name"].str.contains(clean_name, case=False, na=False)]
        if not m.empty:
            return m.iloc[0]

    return None


def build_transfer_payload(
    transfers_out: List[str],
    transfers_in: List[str],
    df: pd.DataFrame,
    entry_id: int,
    gameweek: int,
    chip: Optional[str] = None
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Builds the official FPL POST /api/transfers/ payload.
    Resolves element IDs and tenth-of-million integer pricing (e.g. 55 for £5.5m).
    Returns (payload_dict, error_list).
    """
    errors: List[str] = []

    if len(transfers_out) != len(transfers_in):
        errors.append(f"Mismatched transfer counts: {len(transfers_out)} out vs {len(transfers_in)} in.")
        return {}, errors

    transfer_items: List[Dict[str, Any]] = []

    for out_name, in_name in zip(transfers_out, transfers_in):
        out_el = resolve_player_element(out_name, df)
        if out_el is None:
            errors.append(f"Could not resolve selling player: '{out_name}'")
            continue

        in_el = resolve_player_element(in_name, df)
        if in_el is None:
            errors.append(f"Could not resolve buying player: '{in_name}'")
            continue

        out_id = int(out_el["id"])
        in_id = int(in_el["id"])

        out_cost_raw = float(out_el.get("now_cost", 5.0))
        in_cost_raw = float(in_el.get("now_cost", 5.0))

        # In FPL API, transfer prices are represented in integer tenths of a million (e.g. 55 = £5.5m)
        selling_price = int(round(out_cost_raw * 10))
        purchase_price = int(round(in_cost_raw * 10))

        transfer_items.append({
            "element_in": in_id,
            "element_out": out_id,
            "purchase_price": purchase_price,
            "selling_price": selling_price
        })

    payload = {
        "chips": chip,
        "entry": int(entry_id),
        "event": int(gameweek),
        "transfers": transfer_items
    }

    return payload, errors


def submit_transfers(
    payload: Dict[str, Any],
    cookie_header: str = "",
    auth_token: str = "",
    dry_run: bool = True
) -> Dict[str, Any]:
    """
    Dispatches transfer payload to FPL API or executes a simulated dry-run.
    """
    transfers_list = payload.get("transfers", [])
    if not transfers_list:
        return {
            "success": False,
            "dry_run": dry_run,
            "status_code": 400,
            "error": "Empty transfer list.",
            "message": "No transfer operations in payload."
        }

    if dry_run:
        logger.info("[fpl_transfer_service] Dry-run simulated transfer for %d player(s).", len(transfers_list))
        return {
            "success": True,
            "dry_run": True,
            "status_code": 200,
            "payload": payload,
            "message": f"🧪 [DRY RUN] Verified {len(transfers_list)} transfer(s) ready for dispatch."
        }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RubiesRangers/1.0",
        "Referer": "https://fantasy.premierleague.com/transfers",
        "Origin": "https://fantasy.premierleague.com",
        "Content-Type": "application/json",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    if auth_token:
        val = auth_token.strip()
        if val.startswith("eyJ") and " " not in val and ";" not in val:
            headers["Authorization"] = f"Bearer {val}"

    try:
        resp = requests.post(
            FPL_TRANSFERS_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=15
        )
        if resp.status_code == 200:
            logger.info("[fpl_transfer_service] Live transfer dispatch SUCCEEDED! Response: %s", resp.text[:200])
            res_data = {}
            try:
                res_data = resp.json()
            except Exception:
                res_data = {"raw": resp.text}
            return {
                "success": True,
                "dry_run": False,
                "status_code": 200,
                "payload": payload,
                "response": res_data,
                "message": f"✅ Successfully executed {len(transfers_list)} transfer(s) on official FPL!"
            }
        else:
            logger.warning("[fpl_transfer_service] FPL API rejected transfer (HTTP %d): %s", resp.status_code, resp.text)
            return {
                "success": False,
                "dry_run": False,
                "status_code": resp.status_code,
                "payload": payload,
                "error": resp.text,
                "message": f"❌ FPL Gateway rejected transfer (HTTP {resp.status_code}): {resp.text}"
            }
    except Exception as e:
        logger.exception("[fpl_transfer_service] Network error during transfer POST: %s", e)
        return {
            "success": False,
            "dry_run": False,
            "status_code": 500,
            "payload": payload,
            "error": str(e),
            "message": f"❌ Connection error during transfer dispatch: {e}"
        }


def execute_two_stage_transfer(
    candidate_out: List[str],
    candidate_in: List[str],
    df: pd.DataFrame,
    dry_run: bool = True,
    custom_gameweek: Optional[int] = None
) -> Dict[str, Any]:
    """
    High-level orchestrator:
    1. Reads manager authentication from AuthManager.
    2. Resolves current gameweek.
    3. Builds payload and resolves IDs.
    4. Executes dispatch (dry-run or live).
    """
    auth_mgr = AuthManager()
    session_info = auth_mgr.get_active_session()

    if not dry_run and not session_info.is_authenticated:
        return {
            "success": False,
            "dry_run": False,
            "status_code": 401,
            "error": "Unauthenticated session.",
            "message": "🚨 No authenticated FPL session found. Please sign in or sync cookies in the Settings tab."
        }

    resolved_entry = session_info.entry_id or 6173410

    if custom_gameweek:
        gameweek = custom_gameweek
    else:
        fpl_client = FPLClient()
        try:
            gameweek = fpl_client.get_current_gameweek() or 5
        except Exception:
            gameweek = 5

    payload, errors = build_transfer_payload(
        transfers_out=candidate_out,
        transfers_in=candidate_in,
        df=df,
        entry_id=resolved_entry,
        gameweek=gameweek
    )

    if errors:
        return {
            "success": False,
            "dry_run": dry_run,
            "status_code": 400,
            "error": "; ".join(errors),
            "message": f"❌ Player mapping failed: {'; '.join(errors)}"
        }

    return submit_transfers(
        payload=payload,
        cookie_header=session_info.cookie_header,
        auth_token=session_info.auth_token,
        dry_run=dry_run
    )
