"""
Execution Module
================
3-Wave Cascade execution for optimal performance and progressive streaming.

Wave 1: Lightning + Fast engines (30s timeout) - First results in 10-15s
Wave 2: Standard engines (60s timeout) - Additional results
Wave 3: Slow + Very Slow engines (120s timeout) - Maximum recall

Results stream progressively as each wave completes.

Also includes per-engine analytics tracking for self-improvement insights.
"""
from .cascade_executor import (
    CascadeExecutor,
    ExecutionResult,
    WaveResult,
    ProgressCallback,
)

from .engine_analytics import (
    EngineAnalyticsCollector,
    EngineMetrics,
    SearchAnalytics,
    get_historical_stats,
    get_historical_rankings,
    print_historical_rankings,
)

__all__ = [
    # Cascade Executor
    "CascadeExecutor",
    "ExecutionResult",
    "WaveResult",
    "ProgressCallback",
    # Engine Analytics
    "EngineAnalyticsCollector",
    "EngineMetrics",
    "SearchAnalytics",
    "get_historical_stats",
    "get_historical_rankings",
    "print_historical_rankings",
]
