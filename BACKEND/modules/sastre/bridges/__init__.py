"""SASTRE bridges to external systems.

NOTE: This package intentionally re-exports the legacy bridge classes that live
in the sibling module `SASTRE/bridges.py`. The repo contains both:
  - `SASTRE/bridges/` (package; thin wrappers + EDITH bridge)
  - `SASTRE/bridges.py` (legacy monolithic bridge module)

Many modules still import from `SASTRE.bridges` expecting those legacy symbols.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from .edith_bridge import EdithBridge
from .action_handlers import (
    ActionHandlerRegistry,
    action_registry,
    execute_action,
    ActionResult,
)

logger = logging.getLogger(__name__)

_BRIDGES_PY = Path(__file__).resolve().parents[1] / "bridges.py"
_bridges_py = None

try:
    if _BRIDGES_PY.exists():
        spec = importlib.util.spec_from_file_location("SASTRE._bridges_py", _BRIDGES_PY)
        if spec and spec.loader:
            _bridges_py = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_bridges_py)
except Exception as e:
    logger.warning(f"Failed to load legacy bridges module at {_BRIDGES_PY}: {e}")
    _bridges_py = None

if _bridges_py:
    CymonidesBridge = _bridges_py.CymonidesBridge
    LinklaterBridge = _bridges_py.LinklaterBridge
    WatcherBridge = _bridges_py.WatcherBridge
    IOBridge = _bridges_py.IOBridge
    TorpedoBridge = _bridges_py.TorpedoBridge
    JesterBridge = _bridges_py.JesterBridge
    CorporellaBridge = _bridges_py.CorporellaBridge
    SearchBridge = _bridges_py.SearchBridge
    DomainIntelBridge = _bridges_py.DomainIntelBridge
    NarrativeBridge = _bridges_py.NarrativeBridge
    EyedBridge = _bridges_py.EyedBridge
    ExtendedLinklaterBridge = _bridges_py.ExtendedLinklaterBridge

    InfrastructureStatus = _bridges_py.InfrastructureStatus
    SastreInfrastructure = _bridges_py.SastreInfrastructure
    FullInfrastructureStatus = _bridges_py.FullInfrastructureStatus
    FullSastreInfrastructure = _bridges_py.FullSastreInfrastructure

    get_infrastructure = _bridges_py.get_infrastructure
    get_full_infrastructure = _bridges_py.get_full_infrastructure

__all__ = [
    "EdithBridge",
    "ActionHandlerRegistry",
    "action_registry",
    "execute_action",
    "ActionResult",
    # Legacy bridge exports (when available)
    "CymonidesBridge",
    "LinklaterBridge",
    "WatcherBridge",
    "IOBridge",
    "TorpedoBridge",
    "JesterBridge",
    "CorporellaBridge",
    "SearchBridge",
    "DomainIntelBridge",
    "NarrativeBridge",
    "EyedBridge",
    "ExtendedLinklaterBridge",
    "InfrastructureStatus",
    "SastreInfrastructure",
    "FullInfrastructureStatus",
    "FullSastreInfrastructure",
    "get_infrastructure",
    "get_full_infrastructure",
]
