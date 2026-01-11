# SASTRE

Strategic Analysis System for Tracking, Research, and Evidence - investigation orchestration with adaptive model routing and resilient execution.

## Architecture

```
                              SASTRE
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ┌──────────────┐                                               │
│  │   Query or   │                                               │
│  │    Entity    │                                               │
│  └──────┬───────┘                                               │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                 Orchestration Layer                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ Complexity  │  │    Thin     │  │    Gap      │       │   │
│  │  │   Scouter   │  │ Orchestrator│  │  Analyzer   │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Bridges Layer                         │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐      │   │
│  │  │  EDITH  │  │Corporel.│  │ Matrix  │  │LINKLATER│      │   │
│  │  │ Bridge  │  │ Bridge  │  │ Bridge  │  │ Bridge  │      │   │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘      │   │
│  │       └───────┬────┴───────┬────┴───────┬────┘           │   │
│  │               ▼            ▼            ▼                │   │
│  │  ┌──────────────────────────────────────────────────┐    │   │
│  │  │          External Systems & Modules              │    │   │
│  │  └──────────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Execution Layer                         │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │             Resilient Executor                      │ │   │
│  │  │  • Fallback chains                                  │ │   │
│  │  │  • Decision tracing                                 │ │   │
│  │  │  • Adaptive model routing                           │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│               ┌─────────────────┐                               │
│               │  Investigation  │                               │
│               │     Results     │                               │
│               └─────────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

## Public API

```python
from SASTRE import (
    # Bridges
    EdithBridge, route_query, compose_template, validate_content,
    # Narrative
    DecisionTraceCollector, create_trace,
    # Orchestrator
    ComplexityScouter, assess_complexity, ThinOrchestrator, run_investigation,
    # Execution
    ResilientExecutor, FallbackChain, FALLBACK_CHAINS,
)

# Run investigation
result = await run_investigation(entity="Acme Corp", jurisdiction="UK")

# Assess complexity
complexity = assess_complexity(query)

# Create decision trace
trace = create_trace(decision="route_to_edith", reason="template match")
```

## Structure

```
SASTRE/
├── __init__.py
├── bridges/            # External system bridges
│   ├── edith_bridge.py
│   ├── corporella.py
│   └── linklater.py
├── orchestrator/       # Core orchestration
│   ├── thin.py
│   └── complexity_scouter.py
├── execution/          # Resilient execution
│   └── resilience.py
├── narrative/          # Decision tracing
│   └── decision_trace.py
├── agents/             # Investigation agents
├── disambiguation/     # Entity resolution
├── syntax/             # Operator parsing
├── docs/
└── tests/
```

## Node/Edge Types

| Type | Class | Description |
|------|-------|-------------|
| investigation | NARRATIVE | Investigation instance |
| finding | NARRATIVE | Research finding |
| decision | NARRATIVE | Decision point |
| traced_from | Edge | Decision provenance |
| resulted_in | Edge | Investigation result |

## Dependencies

- EDITH (template-driven reports)
- Corporella (corporate enrichment)
- LINKLATER (link intelligence)
- Matrix (entity routing)
