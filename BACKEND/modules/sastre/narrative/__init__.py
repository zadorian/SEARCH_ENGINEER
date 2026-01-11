"""SASTRE narrative generation and decision tracing."""

from .decision_trace import DecisionTraceCollector, create_trace

__all__ = ["DecisionTraceCollector", "create_trace"]
