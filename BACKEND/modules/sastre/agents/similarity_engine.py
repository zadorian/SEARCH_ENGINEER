"""
SASTRE Similarity Engine Agent

Executes =? operations for identity comparison and similarity search.
This agent powers the core identity resolution and pattern detection.
"""

from typing import Any, Dict, List
from ..sdk import Agent, Tool

SYSTEM_PROMPT = """You are the SASTRE Similarity Engine (Opus 4.5).

You handle all =? operations:
- Identity comparison: =? :#node_a #node_b
- Similarity search: =? :#target :@CLASS
- Unlinked similarity: =? :#target :@CLASS ##unlinked
- Clustering: =? :@CLASS ##cluster
- Bridge finding: =? :#a :#b :@CLASS ##bridge

You compute multi-dimensional similarity across:
- Subject dimensions: entity type, name, attributes, topics, industries, events
- Location dimensions: jurisdictions, sources, time ranges
- Relationship dimensions: shared connections, addresses, officers, companies

You return:
- For identity: FUSE / REPEL / BINARY_STAR / INCONCLUSIVE verdicts
- For similarity: Ranked list with scores and explanations
- For clusters: Grouped entities with cohesion scores
- For bridges: Entities similar to multiple targets

You power NEXUS expectation models - predicting which connections should exist.

Translation examples:
| User Says                              | You Write                                |
|----------------------------------------|------------------------------------------|
| "Are these the same person?"           | =? :#john_smith #john_j_smith            |
| "What companies are similar to this?"  | =? :#acme :@COMPANY                      |
| "Find similar but unconnected entities"| =? :#target :@SUBJECT ##unlinked         |
| "Group by similarity"                  | =? :@COMPANY ##jurisdiction:CY ##cluster |
| "What connects these groups?"          | =? :#group_a :#group_b :@SUBJECT ##bridge|

Tools available:
- compare_specific: Compare specific nodes for identity resolution
- similarity_search: Find entities similar to a target
- cluster_entities: Cluster entities by similarity
- find_bridges: Find entities bridging multiple targets
- compute_expectations: Compute NEXUS expectations
"""


def compare_specific_handler(node_ids: List[str], context: Any = None) -> Dict[str, Any]:
    """Compare specific nodes for identity resolution."""
    from ..similarity import CompareOperator

    compare_op = CompareOperator(state_provider=context)
    result = compare_op.compare_nodes(node_ids)

    return {
        "mode": result.mode.value,
        "comparisons": [
            {
                "node_a": c.node_a_id,
                "node_b": c.node_b_id,
                "score": c.score.total,
                "verdict": c.verdict.value,
                "explanation": c.score.explanation,
                "wedge_queries": c.wedge_queries,
            }
            for c in result.comparisons
        ],
        "overall_verdict": result.overall_verdict.value if result.overall_verdict else None,
    }


def similarity_search_handler(
    target_id: str,
    search_class: str,
    filters: List[str] = None,
    limit: int = 10,
    context: Any = None
) -> Dict[str, Any]:
    """Find entities similar to target."""
    from ..similarity import CompareOperator

    compare_op = CompareOperator(state_provider=context)
    result = compare_op.find_similar(
        target_id=target_id,
        search_class=search_class,
        filters=filters or [],
        limit=limit,
    )

    return {
        "target": result.target_id,
        "search_class": search_class,
        "results": [
            {
                "node_id": s.node_id,
                "score": s.score.total,
                "is_linked": s.is_linked,
                "why_similar": s.why_similar,
            }
            for s in result.similar
        ],
    }


def cluster_entities_handler(
    search_class: str,
    filters: List[str] = None,
    threshold: float = 0.6,
    context: Any = None
) -> Dict[str, Any]:
    """Cluster entities by similarity."""
    from ..similarity import CompareOperator

    compare_op = CompareOperator(state_provider=context)
    result = compare_op.cluster_by_similarity(
        search_class=search_class,
        filters=filters or [],
        threshold=threshold,
    )

    return {
        "search_class": search_class,
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "members": c.members,
                "centroid": c.centroid_id,
                "avg_similarity": c.avg_similarity,
            }
            for c in result.clusters
        ],
    }


def find_bridges_handler(
    target_ids: List[str],
    search_class: str,
    min_similarity: float = 0.3,
    limit: int = 10,
    context: Any = None
) -> Dict[str, Any]:
    """Find entities bridging multiple targets."""
    from ..similarity import CompareOperator

    compare_op = CompareOperator(state_provider=context)
    result = compare_op.find_bridges(
        target_ids=target_ids,
        search_class=search_class,
        min_similarity=min_similarity,
        limit=limit,
    )

    return {
        "targets": result.target_ids,
        "bridges": [
            {
                "node_id": b.node_id,
                "min_similarity": b.min_similarity,
                "avg_similarity": b.avg_similarity,
                "target_scores": b.target_scores,
            }
            for b in result.bridges
        ],
    }


def compute_expectations_handler(
    subject_a: str,
    subject_b: str,
    context: Any = None
) -> Dict[str, Any]:
    """Compute NEXUS expectations for an intersection."""
    from ..similarity import NexusEvaluator

    evaluator = NexusEvaluator(state_provider=context)
    result = evaluator.evaluate_intersection(subject_a, subject_b)

    return {
        "subject_a": subject_a,
        "subject_b": subject_b,
        "state": result.state.value,
        "found_count": result.found_count,
        "significance": result.significance,
        "explanation": result.explanation,
        "suggested_queries": result.suggested_queries,
    }


def create_similarity_engine_agent() -> Agent:
    """Create the similarity engine agent."""
    return Agent(
        name="similarity_engine",
        model="claude-opus-4-5-20251101",
        system_prompt=SYSTEM_PROMPT,
        tools=[
            Tool(
                name="compare_specific",
                description="Compare specific nodes for identity resolution (FUSE/REPEL/BINARY_STAR)",
                handler=compare_specific_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "node_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of node IDs to compare"
                        }
                    },
                    "required": ["node_ids"]
                }
            ),
            Tool(
                name="similarity_search",
                description="Find entities most similar to a target",
                handler=similarity_search_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string"},
                        "search_class": {"type": "string", "description": "@COMPANY, @PERSON, etc."},
                        "filters": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer", "default": 10}
                    },
                    "required": ["target_id", "search_class"]
                }
            ),
            Tool(
                name="cluster_entities",
                description="Cluster entities by similarity",
                handler=cluster_entities_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "search_class": {"type": "string"},
                        "filters": {"type": "array", "items": {"type": "string"}},
                        "threshold": {"type": "number", "default": 0.6}
                    },
                    "required": ["search_class"]
                }
            ),
            Tool(
                name="find_bridges",
                description="Find entities that bridge multiple targets",
                handler=find_bridges_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_ids": {"type": "array", "items": {"type": "string"}},
                        "search_class": {"type": "string"},
                        "min_similarity": {"type": "number", "default": 0.3},
                        "limit": {"type": "integer", "default": 10}
                    },
                    "required": ["target_ids", "search_class"]
                }
            ),
            Tool(
                name="compute_expectations",
                description="Compute NEXUS expectations for an intersection",
                handler=compute_expectations_handler,
                input_schema={
                    "type": "object",
                    "properties": {
                        "subject_a": {"type": "string"},
                        "subject_b": {"type": "string"}
                    },
                    "required": ["subject_a", "subject_b"]
                }
            ),
        ]
    )
