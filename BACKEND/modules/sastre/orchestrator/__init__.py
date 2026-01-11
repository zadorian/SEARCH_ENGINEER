"""SASTRE orchestration layer with complexity scoring and adaptive model routing."""

from .complexity_scouter import ComplexityScouter, ComplexityFactors, assess_complexity
from .thin import ThinOrchestrator, InvestigationState, InvestigationEvent, run_investigation

# IO Client exports (required by tools and agents)
try:
    from .io_client import IOClient, parse_prefix_query, IOResult, get_io_client, execute_io
except ImportError:
    IOClient = None
    parse_prefix_query = None
    IOResult = None
    get_io_client = None
    execute_io = None

__all__ = [
    "ComplexityScouter",
    "ComplexityFactors",
    "assess_complexity",
    "ThinOrchestrator",
    "InvestigationState",
    "InvestigationEvent",
    "run_investigation",
    # IO Client
    "IOClient",
    "parse_prefix_query",
    "IOResult",
    "get_io_client",
    "execute_io",
]
