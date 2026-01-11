"""
SASTRE Bridge Module - Integration with External Infrastructure

Bridges to:
- Cymonides/WDC: Unknown Knowns check (corpus search before external)
- Linklater: Link intelligence, backlinks, entity extraction
- Watchers: Headers <-> prompts bidirectional (TypeScript)
- IO Matrix: 5,620+ rules for investigation routing
- Additional: Torpedo, Jester, Corporella, Search, Domain Intel, Narrative, EYE-D
"""

# NOTE:
# This package is used as a convenience import surface. Some optional components
# (e.g., hydrator) depend on services that may not be installed/running in every
# deployment. Keep imports resilient so `from SASTRE.bridge.template_bridge import ...`
# works even when those optional integrations are unavailable.

# Import from bridges.py for backward compatibility
from ..bridges import (
    # Core bridges
    CymonidesBridge,
    LinklaterBridge,
    WatcherBridge,
    IOBridge,

    # Extended bridges
    TorpedoBridge,
    JesterBridge,
    CorporellaBridge,
    SearchBridge,
    DomainIntelBridge,
    NarrativeBridge,
    EyedBridge,
    ExtendedLinklaterBridge,

    # Infrastructure
    InfrastructureStatus,
    SastreInfrastructure,
    FullInfrastructureStatus,
    FullSastreInfrastructure,

    # Convenience functions
    get_infrastructure,
    get_full_infrastructure,
)

# Import hydrator (optional)
try:
    from .hydrator import InvestigationHydrator
except Exception:
    InvestigationHydrator = None  # type: ignore[assignment]

# Import IO Result Transformer (bridges IO execution to report generation)
try:
    from .io_transformer import (
        AttributeLayer,
        Finding,
        TransformResult,
        IOResultTransformer,
        transform_io_result,
        findings_to_markdown
    )
except Exception:
    AttributeLayer = None  # type: ignore[assignment]
    Finding = None  # type: ignore[assignment]
    TransformResult = None  # type: ignore[assignment]
    IOResultTransformer = None  # type: ignore[assignment]
    transform_io_result = None  # type: ignore[assignment]
    findings_to_markdown = None  # type: ignore[assignment]


__all__ = [
    # Core bridges (match spec)
    'CymonidesBridge',
    'LinklaterBridge',
    'WatcherBridge',
    'IOBridge',

    # Extended bridges
    'TorpedoBridge',
    'JesterBridge',
    'CorporellaBridge',
    'SearchBridge',
    'DomainIntelBridge',
    'NarrativeBridge',
    'EyedBridge',
    'ExtendedLinklaterBridge',

    # Infrastructure
    'InfrastructureStatus',
    'SastreInfrastructure',
    'FullInfrastructureStatus',
    'FullSastreInfrastructure',

    # Convenience
    'get_infrastructure',
    'get_full_infrastructure',

    # Hydrator
    'InvestigationHydrator',

    # IO Result Transformer
    'AttributeLayer',
    'Finding',
    'TransformResult',
    'IOResultTransformer',
    'transform_io_result',
    'findings_to_markdown',
]
