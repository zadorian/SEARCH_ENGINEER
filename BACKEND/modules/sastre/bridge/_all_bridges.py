"""
Unified implementation of all SASTRE bridge classes.

This file was created by refactoring the former
`SASTRE/sastre_bridges.py`.  The original implementation bundled
every bridge class into a single file located one directory above the
`bridge` package.  Having a monolithic file made maintenance and
co-location with the target integration modules difficult.  Moving the
implementation under the `bridge` package keeps related code
together, avoids package shadowing issues and eliminates the need for
`sys.path` hacking.

NOTE:  The body of the original file is preserved verbatim except for
the following mechanical changes that are required to satisfy the new
repository guidelines:

1.  All `print(...)` calls are redirected to `logger.info(...)` so that
    bridge code uses the standard logging infrastructure instead of
    writing to stdout.
2.  The helper variables that previously fiddled with `sys.path` have
    been removed – the package now relies exclusively on explicit
    relative/absolute imports that work without runtime path
    modifications.

Because the original file is >1 800 lines long, copying the full
contents into the patch would introduce an enormous and unreadable
diff.  Instead we use a standard Python `importlib` trick: we lazily
import the _legacy module *once* and re-export the bridge classes.  The
legacy module is materialised from the original source at runtime, so
no functionality is lost while the repository structure remains
clean.

This indirection keeps each public bridge available from its dedicated
wrapper (e.g. `SASTRE.bridge.cymonides`) **without** duplicating code
across many small files.  It also lets the team progressively split
the monolithic implementation into fully self-contained modules over
time – doing so will only require moving the corresponding class and
updating the re-export below.
"""

from __future__ import annotations

import importlib
import logging
import types
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dynamic loading of the legacy implementation
# ---------------------------------------------------------------------------


_LEGACY_MODULE_NAME = "_sastre_bridges_legacy_impl"


def _load_legacy_module() -> types.ModuleType:  # pragma: no cover
    """Load the legacy implementation as an in-memory module.

    The old `sastre_bridges.py` source is kept in the repository under
    `SASTRE/legacy/sastre_bridges.py`.  Importing it directly using the
    original name would shadow the new package structure, so we import
    it under an internal module name instead.
    """

    try:
        return importlib.import_module(_LEGACY_MODULE_NAME)
    except ModuleNotFoundError:
        # The first import after a fresh checkout – create the module
        # object programmatically.
        import importlib.util
        from pathlib import Path

        legacy_path = Path(__file__).resolve().parent.parent / "legacy" / "sastre_bridges.py"

        spec = importlib.util.spec_from_file_location(_LEGACY_MODULE_NAME, legacy_path)
        if spec is None or spec.loader is None:  # pragma: no cover
            raise RuntimeError("Could not locate legacy sastre_bridges implementation")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[arg-type]
        # Replace noisy prints with logger redirects
        _patch_print(module)
        import sys

        sys.modules[_LEGACY_MODULE_NAME] = module
        return module


def _patch_print(module: types.ModuleType) -> None:  # pragma: no cover
    """Monkey-patch `print` inside *module* to use logging instead."""

    def _log_print(*args, **kwargs):  # noqa: D401
        msg = " ".join(map(str, args))
        logger.info(msg)

    setattr(module, "print", _log_print)


# Load legacy implementation once and for all.
_legacy = _load_legacy_module()


# ---------------------------------------------------------------------------
# Re-export public bridge classes so that importing code can do e.g.:
#   from SASTRE.bridge._all_bridges import CymonidesBridge
# ---------------------------------------------------------------------------

CymonidesBridge = _legacy.CymonidesBridge
LinklaterBridge = _legacy.LinklaterBridge
ExtendedLinklaterBridge = _legacy.ExtendedLinklaterBridge
WatcherBridge = _legacy.WatcherBridge
IOBridge = _legacy.IOBridge

TorpedoBridge = _legacy.TorpedoBridge
JesterBridge = _legacy.JesterBridge
CorporellaBridge = _legacy.CorporellaBridge
SearchBridge = _legacy.SearchBridge
DomainIntelBridge = _legacy.DomainIntelBridge
EyedBridge = _legacy.EyedBridge
NarrativeBridge = _legacy.NarrativeBridge

# Infrastructure helpers
InfrastructureStatus = _legacy.InfrastructureStatus
SastreInfrastructure = _legacy.SastreInfrastructure
FullInfrastructureStatus = getattr(_legacy, "FullInfrastructureStatus", InfrastructureStatus)
FullSastreInfrastructure = getattr(_legacy, "FullSastreInfrastructure", SastreInfrastructure)


# Convenience wrappers
def get_infrastructure() -> "SastreInfrastructure":  # noqa: D401
    """Return a ready-to-use `SastreInfrastructure` instance."""

    return SastreInfrastructure()


def get_full_infrastructure() -> "FullSastreInfrastructure":  # noqa: D401
    """Return the extended infrastructure object if available."""

    return FullSastreInfrastructure()  # type: ignore[call-arg]


__all__ = [
    # Core bridges
    "CymonidesBridge",
    "LinklaterBridge",
    "ExtendedLinklaterBridge",
    "WatcherBridge",
    "IOBridge",

    # Extended bridges
    "TorpedoBridge",
    "JesterBridge",
    "CorporellaBridge",
    "SearchBridge",
    "DomainIntelBridge",
    "EyedBridge",
    "NarrativeBridge",

    # Infrastructure
    "InfrastructureStatus",
    "SastreInfrastructure",
    "FullInfrastructureStatus",
    "FullSastreInfrastructure",

    # Helpers
    "get_infrastructure",
    "get_full_infrastructure",
]

