"""
SASTRE - Strategic Analysis System for Tracking, Research, and Evidence

Investigation orchestrator that combines:
- EDITH skills pipeline for template-driven reports
- Corporella for corporate enrichment
- Linklater for link intelligence
- Matrix for entity routing

Modules:
- bridges: Async bridges to external systems (EDITH, Corporella, etc.)
- narrative: Decision tracing and explainability
- orchestrator: Complexity scoring and adaptive model routing
- execution: Resilience layer with fallback chains
"""

from .bridges.edith_bridge import EdithBridge, route_query, compose_template, validate_content
from .narrative.decision_trace import DecisionTraceCollector, create_trace
from .orchestrator.complexity_scouter import ComplexityScouter, assess_complexity
from .orchestrator.thin import ThinOrchestrator, run_investigation
from .execution.resilience import ResilientExecutor, FallbackChain, FALLBACK_CHAINS

__all__ = [
    # Bridges
    "EdithBridge",
    "route_query",
    "compose_template",
    "validate_content",
    # Narrative
    "DecisionTraceCollector",
    "create_trace",
    # Orchestrator
    "ComplexityScouter",
    "assess_complexity",
    "ThinOrchestrator",
    "run_investigation",
    # Execution
    "ResilientExecutor",
    "FallbackChain",
    "FALLBACK_CHAINS",
]
