import json
import os
from pathlib import Path
from typing import Dict, Any

CONFIG_PATH = Path(__file__).parent / "data" / "user_config.json"

def _load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"auto_scribe": False}
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"auto_scribe": False}

def _save_config(config: Dict[str, Any]):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def set_auto_scribe(enabled: bool):
    """Enable or disable EDITH Auto-Scribe mode."""
    config = _load_config()
    config["auto_scribe"] = enabled
    _save_config(config)

def is_auto_scribe_enabled() -> bool:
    """Check if EDITH Auto-Scribe mode is active."""
    return _load_config().get("auto_scribe", False)
