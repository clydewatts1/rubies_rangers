"""
Safe Configuration Updater for rubies_rangers
Updates the tuned: profile and tuning_metadata: in config.yaml while preserving
file structure and clearing config_manager caches.
"""

from __future__ import annotations
import datetime
import logging
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from config_manager import get_config

logger = logging.getLogger("tuner.updater")
CONFIG_PATH = Path("config.yaml")


def update_config_with_tuned(
    tuned_params: Dict,
    metadata: Optional[Dict] = None,
    config_path: Optional[Path | str] = None
) -> bool:
    """
    Overwrites the `tuned:` block in config.yaml with newly discovered optimal parameters,
    records audit metadata under `tuning_metadata:`, and resets the cached config.
    """
    target = Path(config_path) if config_path else CONFIG_PATH
    if not target.exists():
        logger.error("Target config file does not exist: %s", target)
        return False

    try:
        with open(target, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f) or {}

        # Update tuned section
        raw_cfg["tuned"] = tuned_params

        # Update metadata section
        now_str = datetime.datetime.now().isoformat()
        current_meta = raw_cfg.get("tuning_metadata", {})
        if metadata:
            current_meta.update(metadata)
        current_meta["last_tuned_at"] = now_str
        raw_cfg["tuning_metadata"] = current_meta

        # Write back to config.yaml cleanly
        with open(target, "w", encoding="utf-8") as f:
            yaml.dump(raw_cfg, f, default_flow_style=False, sort_keys=False)

        # Clear in-memory config cache
        try:
            get_config.cache_clear()
        except Exception:
            pass

        logger.info("Successfully updated tuned: parameters in %s at %s", target, now_str)
        return True
    except Exception as e:
        logger.error("Failed to update config file %s: %s", target, e)
        return False
