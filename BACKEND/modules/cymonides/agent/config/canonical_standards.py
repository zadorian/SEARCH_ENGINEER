#!/usr/bin/env python3
"""
Cymonides Canonical Standards Configuration

THE SINGLE SOURCE OF TRUTH for node classes, types, relationships, and indexing rules.

References:
- /data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/entity_class_type_matrix.json
- /data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/relationships.json
- /data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/types.json
- /data/SEARCH_ENGINEER/BACKEND/modules/cymonides/c1/node_classes.json
- /data/SEARCH_ENGINEER/BACKEND/modules/cymonides/edge_types.json
"""

from pathlib import Path

# =============================================================================
# CANONICAL FILE PATHS
# =============================================================================

CANONICAL_PATHS = {
    # Central registry for CLASS > TYPE > SUBTYPE hierarchy
    "entity_class_type_matrix": "/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/entity_class_type_matrix.json",

    # NEXUS relationship ontology (101 relationships with subtypes)
    "relationships": "/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/relationships.json",

    # Quick-lookup I/O node type definitions
    "types": "/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/types.json",

    # C-1 node classes (SUBJECT, LOCATION, NARRATIVE, NEXUS)
    "c1_node_classes": "/data/SEARCH_ENGINEER/BACKEND/modules/cymonides/c1/node_classes.json",

    # C-1 node types
    "c1_node_types": "/data/SEARCH_ENGINEER/BACKEND/modules/cymonides/c1/node_types.json",

    # Edge type definitions
    "edge_types": "/data/SEARCH_ENGINEER/BACKEND/modules/cymonides/edge_types.json",

    # Industries (NAICS/NACE-based)
    "industries": "/data/CLASSES/SUBJECT/industries.json",

    # Professions (SOC/ISCO-based)
    "professions": "/data/CLASSES/SUBJECT/professions.json",
}

# =============================================================================
# INDEX TIER DEFINITIONS
# =============================================================================

INDEX_TIERS = {
    "c-1": {
        "name": "Project Graphs",
        "pattern": "cymonides-1-{projectId}",
        "description": "Per-project investigation graphs with nodes and embedded edges",
        "node_classes": ["SUBJECT", "LOCATION", "NARRATIVE", "NEXUS"],
        "default_index": "cymonides-1-default",
        "bridge_pattern": "{module}_c1_bridge.py"
    },
    "c-2": {
        "name": "Content Corpus",
        "pattern": "cymonides-2",
        "description": "Free-form text corpus from scraped websites",
        "node_types": ["document", "page", "content"],
        "default_index": "cymonides-2"
    },
    "c-3": {
        "name": "Entity Superindex",
        "pattern": "{entity}_unified",
        "description": "Consolidated multi-source entity indices",
        "unified_indices": [
            "domains_unified",
            "persons_unified",
            "companies_unified",
            "emails_unified",
            "phones_unified",
            "geo_unified",
            "temp_unified",
            "credentials_unified"
        ],
        "merge_rules": {
            "default_strategy": "append",  # NEVER overwrite - always append
            "preserve_all_fields": True,   # THE HOLY RULE
            "source_tracking": True        # Track which source each field came from
        }
    }
}

# =============================================================================
# NODE CLASSES (Four Fundamental Classes)
# =============================================================================

NODE_CLASSES = {
    "SUBJECT": {
        "description": "Entities and concepts being investigated",
        "color": "#16a34a",  # Green
        "axis": "Y",
        "types": {
            "ENTITY": [
                "person", "company", "organization", "email", "phone",
                "username", "domain", "url", "ip_address", "document",
                "vehicle", "vessel", "aircraft", "property", "crypto_wallet",
                "bank_account", "password"
            ],
            "CONCEPT": ["litigation", "phenomenon", "topic", "theme"]
        },
        "sub_dimensions": ["ENTITY", "IDENTIFIER", "CLASSIFIER", "CONCEPT"]
    },
    "LOCATION": {
        "description": "Geographic and jurisdictional context",
        "color": "#ffffff",  # White
        "axis": "X",
        "types": {
            "GEOGRAPHIC": ["coordinates", "region", "city", "country", "address"],
            "JURISDICTIONAL": ["jurisdiction", "regulatory_zone"],
            "SOURCE": ["aggregator", "registry", "breach", "platform", "database", "archive"],
            "TEMPORAL": ["date", "year", "month", "period", "timestamp"],
            "FORMAT": ["filetype", "mime_type", "language"],
            "CATEGORY": ["news", "corporate", "government", "academic", "social"]
        },
        "sub_dimensions": ["GEO", "TEMPORAL", "SOURCE", "FORMAT", "LANG", "CATEG"]
    },
    "NEXUS": {
        "description": "Relationships/edges between entities",
        "color": "#a855f7",  # Purple
        "axis": "R",
        "types": {
            "RELATIONSHIP": "All relationship types from relationships.json"
        },
        "root_relationships": [
            "same_as", "related_to", "owns", "controls", "member_of",
            "located_at", "has", "links_to", "party_to", "sanctioned_by",
            "appears_in", "regulated_by", "transacts_with", "searched_with",
            "part_of", "tagged_with", "has_result"
        ]
    },
    "NARRATIVE": {
        "description": "Documentation and coordination",
        "color": "#2563eb",  # Blue
        "axis": "N",
        "types": {
            "DOCUMENTATION": [
                "project", "report", "note", "chat", "tag",
                "finding", "workstream", "evidence_document"
            ]
        },
        "sub_dimensions": ["project", "goals", "notes", "tags", "evidence"]
    }
}

# =============================================================================
# C-1 NODE FORMAT (Canonical Schema)
# =============================================================================

C1_NODE_SCHEMA = {
    # Required fields
    "id": "Deterministic hash: sha256(f'{entity_type}:{canonical_value}')[:24]",
    "node_class": "CLASS dimension: SUBJECT, LOCATION, NARRATIVE, NEXUS",
    "type": "Type within class: person, company, email, domain, etc.",
    "canonicalValue": "Normalized canonical form: lowercase, stripped, hyphenated",
    "label": "Human-readable display label",

    # Standard fields
    "value": "Raw value",
    "sources": "Array of source identifiers",
    "source_system": "Originating module: linklater, eyed, pacman, corporella, etc.",

    # Embedded edges (NO separate edge index)
    "embedded_edges": [
        {
            "edge_id": "Unique edge identifier",
            "relationship": "Relationship type: officer_of, owns, links_to, etc.",
            "direction": "outgoing or incoming",
            "target_id": "Target node ID",
            "target_label": "Target node display label",
            "target_class": "Target node class",
            "target_type": "Target node type",
            "confidence": "0.0-1.0 confidence score",
            "metadata": "Edge-specific metadata dict",
            "created_at": "ISO8601 timestamp"
        }
    ],

    # Timestamps
    "createdAt": "ISO8601 creation timestamp",
    "updatedAt": "ISO8601 last update timestamp",
    "lastSeen": "ISO8601 last seen timestamp",

    # Project scope
    "projectId": "Optional project scope"
}

# =============================================================================
# C-3 UNIFIED INDEX SCHEMA
# =============================================================================

C3_UNIFIED_SCHEMA = {
    # THE HOLY RULE: Preserve EVERYTHING from each dataset
    "preservation_rules": {
        "all_fields": "Keep ALL original fields",
        "all_metadata": "Keep ALL original metadata",
        "source_attribution": "Track which source contributed which data",
        "temporal_hierarchy": "year, decade, era from dates"
    },

    # Merge strategy
    "merge_strategy": {
        "default": "append",  # NEVER overwrite
        "overlapping_fields": {
            "description": "When multiple datasets have the same field",
            "strategy": "Create subfields for each source",
            "example": {
                "ranking": {
                    "tranco": {"rank": 1234, "date": "2024-01"},
                    "majestic": {"rank": 5678, "trust_flow": 45},
                    "umbrella": {"rank": 9012}
                }
            }
        },
        "deduplication": {
            "strategy": "keep_all_with_links",
            "same_as_edges": "Create same_as edges between duplicates",
            "canonical_selection": "Use highest confidence as canonical"
        }
    },

    # Standard unified fields
    "standard_fields": {
        "id": "Deterministic hash",
        "canonical_value": "Primary normalized value",
        "entity_type": "person, company, domain, email, etc.",

        # Multi-source tracking
        "source_records": [
            {
                "source": "Source identifier",
                "source_type": "registry, breach, scrape, api",
                "original_id": "ID in original source",
                "fields": "Original field values",
                "ingested_at": "When this source was ingested"
            }
        ],

        # Dimension keys for faceted search
        "dimension_keys": ["tld:com", "jur:gb", "auth:top10k", "year:2024"],

        # Temporal hierarchy
        "temporal": {
            "year": 2024,
            "decade": "2020s",
            "era": "post_covid"
        },

        # Embedded edges
        "embedded_edges": [],

        # Timestamps
        "first_seen": "Earliest appearance across all sources",
        "last_seen": "Most recent appearance",
        "updated_at": "Last update to this record"
    }
}

# =============================================================================
# C-3 TEST PROTOCOL
# =============================================================================

C3_TEST_PROTOCOL = {
    "phase_1": {
        "name": "Initial Test",
        "batch_size": "100-1000 docs",
        "actions": [
            "Index small batch",
            "Verify field mappings",
            "Check for data loss",
            "Validate merge behavior",
            "Inspect sample documents"
        ],
        "success_criteria": {
            "no_data_loss": True,
            "correct_field_types": True,
            "source_tracking_works": True,
            "merge_appends_not_overwrites": True
        }
    },
    "phase_2": {
        "name": "Adjustment",
        "actions": [
            "Review phase_1 results",
            "Adjust field mappings if needed",
            "Refine merge strategy",
            "Update transformation rules"
        ]
    },
    "phase_3": {
        "name": "Larger Test",
        "batch_size": "1000 docs",
        "actions": [
            "Index 1k docs",
            "Verify at scale",
            "Check for edge cases",
            "Performance baseline"
        ]
    },
    "phase_4": {
        "name": "Full Indexing",
        "actions": [
            "Index remaining docs",
            "Monitor progress",
            "Handle errors",
            "Final verification"
        ]
    }
}

# =============================================================================
# ERA DEFINITIONS (Temporal)
# =============================================================================

ERA_DEFINITIONS = [
    (1947, 1991, "cold_war"),
    (1991, 2000, "post_soviet"),
    (2000, 2008, "pre_2008"),
    (2008, 2019, "post_2008"),
    (2020, 2022, "covid_era"),
    (2023, 2100, "post_covid"),
]

# =============================================================================
# C-1 BRIDGE TEMPLATE
# =============================================================================

C1_BRIDGE_TEMPLATE = '''#!/usr/bin/env python3
"""
{module_name} -> Cymonides-1 Bridge

Indexes {module_name} results to cymonides-1-{{projectId}} with:
- Entity nodes ({node_types_list})
- Embedded edges ({edge_types_list})

Generated by Cymonides Agent.
"""

import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

from elasticsearch import Elasticsearch, helpers

DEFAULT_INDEX = "cymonides-1-{default_project}"


@dataclass
class EmbeddedEdge:
    """Edge embedded within a node document."""
    target_id: str
    target_class: str
    target_type: str
    target_label: str
    relation: str
    direction: str = "outgoing"
    confidence: float = 0.85
    metadata: Dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class C1Node:
    """Node for cymonides-1-{{projectId}} index."""
    id: str
    node_class: str = "SUBJECT"
    type: str = "entity"
    label: str = ""
    canonicalValue: str = ""
    metadata: Dict = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)
    source_system: str = "{module_name_lower}"
    embedded_edges: List[Dict] = field(default_factory=list)
    createdAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updatedAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    lastSeen: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    projectId: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


class C1Bridge:
    """Bridge from {module_name} to Cymonides-1 graph storage."""

    TYPE_MAP = {type_map_entries}

    def __init__(self, project_id: str = None, es_host: str = "http://localhost:9200"):
        self.project_id = project_id
        self.index_name = f"cymonides-1-{{project_id or 'default'}}"
        self._es = None
        self.es_host = es_host

    @property
    def es(self):
        if self._es is None:
            self._es = Elasticsearch([self.es_host])
        return self._es

    def generate_id(self, entity_type: str, value: str) -> str:
        """Generate deterministic node ID."""
        canonical = f"{{entity_type}}:{{str(value).lower().strip()}}"
        return hashlib.sha256(canonical.encode()).hexdigest()[:24]

    def create_node(
        self,
        entity_type: str,
        value: str,
        label: str = None,
        metadata: Dict = None,
        edges: List[EmbeddedEdge] = None
    ) -> C1Node:
        """Create a C1 node."""
        node_type = self.TYPE_MAP.get(entity_type.lower(), entity_type)
        node_class = self._get_node_class(node_type)

        return C1Node(
            id=self.generate_id(node_type, value),
            node_class=node_class,
            type=node_type,
            label=label or str(value),
            canonicalValue=str(value).lower().strip(),
            metadata=metadata or {{}},
            sources=["{module_name_lower}"],
            embedded_edges=[asdict(e) for e in (edges or [])],
            projectId=self.project_id
        )

    def _get_node_class(self, node_type: str) -> str:
        """Determine node class from type."""
        subject_types = {{"person", "company", "organization", "email", "phone", "username", "domain"}}
        location_types = {{"address", "country", "region", "city", "jurisdiction"}}
        if node_type in subject_types:
            return "SUBJECT"
        elif node_type in location_types:
            return "LOCATION"
        return "SUBJECT"

    def index_results(self, results: List[Dict], batch_size: int = 500) -> Dict:
        """Index results to Elasticsearch."""
        nodes = []
        for result in results:
            node = self._transform_result(result)
            if node:
                nodes.append(node)

        # Bulk index
        actions = [
            {{
                "_index": self.index_name,
                "_id": node.id,
                "_source": node.to_dict()
            }}
            for node in nodes
        ]

        success, failed = helpers.bulk(self.es, actions, raise_on_error=False)
        return {{"success": success, "failed": len(failed) if failed else 0}}

    def _transform_result(self, result: Dict) -> Optional[C1Node]:
        """Transform a module result to C1Node. Override in subclass."""
        # Implement transformation logic here
        raise NotImplementedError("Implement _transform_result in subclass")
'''

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_era(year: int) -> str:
    """Get era label for a year."""
    for start, end, era in ERA_DEFINITIONS:
        if start <= year <= end:
            return era
    return "unknown"


def get_decade(year: int) -> str:
    """Get decade label."""
    decade_start = (year // 10) * 10
    return f"{decade_start}s"


def get_node_class(node_type: str) -> str:
    """Determine node class from type."""
    for class_name, class_def in NODE_CLASSES.items():
        for type_category, types in class_def.get("types", {}).items():
            if isinstance(types, list) and node_type in types:
                return class_name
            elif isinstance(types, str) and node_type == types:
                return class_name
    return "SUBJECT"  # Default


def canonical_value(value: str, entity_type: str = None) -> str:
    """Generate canonical value."""
    import re
    if not value:
        return ""
    v = str(value).lower().strip()
    # Replace non-alphanumeric with hyphens
    v = re.sub(r"[^a-z0-9]+", "-", v)
    # Remove leading/trailing hyphens
    v = v.strip("-")
    return v


def generate_node_id(entity_type: str, value: str) -> str:
    """Generate deterministic node ID."""
    import hashlib
    canonical = f"{entity_type}:{canonical_value(value)}"
    return hashlib.sha256(canonical.encode()).hexdigest()[:24]
