"""
WDC Materialization Gate - Convert WDC entities to Cymonides-1 nodes

This module is the SINGLE entry point for materializing WDC Schema.org data
into the Cymonides entity graph.

CRITICAL: Uses the MAIN SYSTEM's CymonidesIndexer for ID generation!
- Same ID generation as Grid extraction pipeline
- Same normalization (removes Inc., Ltd., Corp. suffixes)
- Same document schema (canonicalValue, source_urls, etc.)
- Same edge format (embedded_edges)

This ensures WDC entities MERGE with entities from Grid extraction,
rather than creating duplicates.

Usage:
    from CYMONIDES.scripts.wdc.materialization_gate import WDCMaterializer

    materializer = WDCMaterializer()
    await materializer.connect()

    # Materialize WDC search results to C-1
    result = await materializer.materialize(
        wdc_results=[...],
        project_id="proj_123",
        discovery_query="[restaurant] : geo:de"
    )
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

# =============================================================================
# IMPORT MAIN SYSTEM FUNCTIONS (Source of Truth!)
# =============================================================================

# Import ID generation and normalization from cymonides_bridge
try:
    from modules.LINKLATER.cymonides_bridge import (
        CymonidesIndexer,
        normalize_value,
        generate_deterministic_id,
        ENTITY_TYPE_MAP,
    )
    HAS_INDEXER = True
except ImportError:
    HAS_INDEXER = False
    CymonidesIndexer = None
    normalize_value = lambda v, t="": v.lower().strip()
    generate_deterministic_id = lambda v, t: f"{t}:{v}"[:24]
    ENTITY_TYPE_MAP = {}

# Import valid edge types from extraction models
try:
    from modules.LINKLATER.extraction.models import VALID_EDGES, VALID_RELATIONS, Edge
    HAS_EXTRACTION_MODELS = True
except ImportError:
    HAS_EXTRACTION_MODELS = False
    VALID_EDGES = []
    VALID_RELATIONS = []
    Edge = None

# Elasticsearch for edge updates
try:
    from elasticsearch import AsyncElasticsearch
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False
    AsyncElasticsearch = None


# =============================================================================
# TYPE MAPPINGS (Schema.org → Cymonides)
# =============================================================================

# Schema.org type -> Cymonides entity type
SCHEMA_TO_CYMONIDES = {
    # Person types
    "person": "person",
    "author": "person",
    "patient": "person",
    "athlete": "person",
    "politician": "person",

    # Organization types
    "organization": "organization",
    "corporation": "company",
    "company": "company",
    "localbusiness": "company",
    "restaurant": "company",
    "hotel": "company",
    "store": "company",
    "bank": "company",
    "medicalorganization": "organization",
    "educationalorganization": "organization",
    "governmentorganization": "organization",
    "ngo": "organization",
    "sportsorganization": "organization",

    # Identifiers
    "email": "email",
    "emailaddress": "email",
    "telephone": "phone",
    "phone": "phone",
    "postaladdress": "address",
    "address": "address",

    # Others
    "product": "product",
    "event": "event",
}


def map_schema_type(schema_type: str) -> str:
    """Map Schema.org type to Cymonides entity type."""
    normalized = schema_type.lower().replace("schema:", "").replace("schema.org/", "")
    return SCHEMA_TO_CYMONIDES.get(normalized, "entity")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MaterializationResult:
    """Result of materializing WDC entities."""
    materialized: List[str] = field(default_factory=list)
    skipped: int = 0
    total: int = 0
    errors: List[str] = field(default_factory=list)
    edges_created: int = 0

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return len(self.materialized) / self.total


# =============================================================================
# WDC SCHEMA.ORG → EDGE MAPPING
# =============================================================================

# Map Schema.org properties to our VALID_RELATIONS
WDC_PROPERTY_TO_RELATION = {
    # Person relationships
    "worksFor": "employee_of",
    "memberOf": "employee_of",
    "affiliation": "employee_of",

    # Contact info
    "email": "has_email",
    "telephone": "has_phone",
    "address": "has_address",
    "location": "has_address",

    # Company relationships
    "parentOrganization": "subsidiary_of",
    "subOrganization": "legal_parent_of",
}


# =============================================================================
# MATERIALIZER
# =============================================================================

class WDCMaterializer:
    """
    Materialize WDC Schema.org entities into Cymonides-1 graph nodes.

    USES MAIN SYSTEM INDEXER for ID generation!
    This ensures WDC entities merge with Grid extraction entities.

    Same entity from WDC and Grid = same node ID = edges accumulate.
    """

    def __init__(
        self,
        es_url: str = "http://localhost:9200",
        es_user: str = "elastic",
        es_pass: str = "szilvansen",
    ):
        self.es_url = es_url
        self.es_user = es_user
        self.es_pass = es_pass
        self._indexer: Optional[CymonidesIndexer] = None
        self._es: Optional[AsyncElasticsearch] = None

    async def connect(self):
        """Initialize connections."""
        # Use main system indexer
        if HAS_INDEXER and self._indexer is None:
            self._indexer = CymonidesIndexer()
            await self._indexer.connect()

        # Direct ES connection for edge updates
        if ES_AVAILABLE and self._es is None:
            self._es = AsyncElasticsearch(
                [self.es_url],
                basic_auth=(self.es_user, self.es_pass)
            )

    async def close(self):
        """Close connections."""
        if self._indexer:
            await self._indexer.close()
            self._indexer = None
        if self._es:
            await self._es.close()
            self._es = None

    def _get_c1_index(self, project_id: str) -> str:
        """Get C-1 index name for project."""
        return f"cymonides-1-{project_id}"

    async def _create_node(
        self,
        value: str,
        entity_type: str,
        source_url: str,
        project_id: str,
        metadata: Dict[str, Any] = None,
    ) -> Optional[str]:
        """
        Create a C-1 node using MAIN SYSTEM indexer.

        This ensures:
        - Deterministic SHA256-based ID
        - Proper normalization (Inc., Ltd., Corp. removed)
        - Correct document schema
        - Upsert logic (update if exists)
        """
        if not self._indexer:
            await self.connect()

        if not self._indexer:
            return None

        try:
            # Use main system's index_entity - handles everything!
            node_id = await self._indexer.index_entity(
                value=value,
                entity_type=entity_type,
                source_url=source_url,
                project_id=project_id,
                metadata=metadata or {},
            )
            return node_id
        except Exception as e:
            return None

    async def _extract_edges_from_wdc(
        self,
        wdc_entity: Dict[str, Any],
        source_node_id: str,
        source_type: str,
        source_url: str,
        project_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract edges from WDC Schema.org properties.

        Schema.org has embedded relationships like:
        - worksFor (Person → Company)
        - email (Entity → Email)
        - telephone (Entity → Phone)
        - address (Entity → Address)
        """
        edges = []

        # Person → Company (worksFor, memberOf, affiliation)
        for prop in ["worksFor", "memberOf", "affiliation"]:
            if works_for := wdc_entity.get(prop):
                org_name = self._extract_name(works_for)
                if org_name:
                    target_id = await self._create_node(
                        value=org_name,
                        entity_type="company",
                        source_url=source_url,
                        project_id=project_id,
                        metadata={"wdc_source": True, "via_property": prop},
                    )
                    if target_id:
                        edges.append({
                            "source_id": source_node_id,
                            "source_type": source_type,
                            "source_label": wdc_entity.get("name", ""),
                            "relation": "employee_of",
                            "target_id": target_id,
                            "target_type": "company",
                            "target_label": org_name,
                            "confidence": 0.9,  # Schema.org = high confidence
                            "source_url": source_url,
                        })

        # Entity → Email
        for email_prop in ["email", "contactPoint.email"]:
            email = self._get_nested(wdc_entity, email_prop)
            if email:
                # Handle both string and list
                emails = [email] if isinstance(email, str) else email if isinstance(email, list) else []
                for e in emails[:3]:  # Limit to 3 emails
                    if isinstance(e, str) and "@" in e:
                        target_id = await self._create_node(
                            value=e,
                            entity_type="email",
                            source_url=source_url,
                            project_id=project_id,
                            metadata={"wdc_source": True},
                        )
                        if target_id:
                            edges.append({
                                "source_id": source_node_id,
                                "source_type": source_type,
                                "source_label": wdc_entity.get("name", ""),
                                "relation": "has_email",
                                "target_id": target_id,
                                "target_type": "email",
                                "target_label": e,
                                "confidence": 1.0,  # Schema.org email = definite
                                "source_url": source_url,
                            })

        # Entity → Phone
        for phone_prop in ["telephone", "phone", "contactPoint.telephone"]:
            phone = self._get_nested(wdc_entity, phone_prop)
            if phone:
                phones = [phone] if isinstance(phone, str) else phone if isinstance(phone, list) else []
                for p in phones[:3]:
                    if isinstance(p, str) and len(p) >= 7:
                        target_id = await self._create_node(
                            value=p,
                            entity_type="phone",
                            source_url=source_url,
                            project_id=project_id,
                            metadata={"wdc_source": True},
                        )
                        if target_id:
                            edges.append({
                                "source_id": source_node_id,
                                "source_type": source_type,
                                "source_label": wdc_entity.get("name", ""),
                                "relation": "has_phone",
                                "target_id": target_id,
                                "target_type": "phone",
                                "target_label": p,
                                "confidence": 1.0,
                                "source_url": source_url,
                            })

        # Entity → Address
        for addr_prop in ["address", "location"]:
            address = wdc_entity.get(addr_prop)
            if address:
                addr_str = self._format_address(address)
                if addr_str:
                    target_id = await self._create_node(
                        value=addr_str,
                        entity_type="address",
                        source_url=source_url,
                        project_id=project_id,
                        metadata={"wdc_source": True},
                    )
                    if target_id:
                        edges.append({
                            "source_id": source_node_id,
                            "source_type": source_type,
                            "source_label": wdc_entity.get("name", ""),
                            "relation": "has_address",
                            "target_id": target_id,
                            "target_type": "address",
                            "target_label": addr_str,
                            "confidence": 0.9,
                            "source_url": source_url,
                        })

        # Company → Parent Company
        if parent := wdc_entity.get("parentOrganization"):
            parent_name = self._extract_name(parent)
            if parent_name:
                target_id = await self._create_node(
                    value=parent_name,
                    entity_type="company",
                    source_url=source_url,
                    project_id=project_id,
                    metadata={"wdc_source": True, "via_property": "parentOrganization"},
                )
                if target_id:
                    edges.append({
                        "source_id": source_node_id,
                        "source_type": source_type,
                        "source_label": wdc_entity.get("name", ""),
                        "relation": "subsidiary_of",
                        "target_id": target_id,
                        "target_type": "company",
                        "target_label": parent_name,
                        "confidence": 0.95,
                        "source_url": source_url,
                    })

        return edges

    def _extract_name(self, value: Any) -> Optional[str]:
        """Extract name from various Schema.org formats."""
        if isinstance(value, str):
            return value.strip() if len(value.strip()) > 1 else None
        if isinstance(value, dict):
            return value.get("name") or value.get("legalName") or value.get("@value")
        if isinstance(value, list) and value:
            return self._extract_name(value[0])
        return None

    def _get_nested(self, obj: Dict, path: str) -> Any:
        """Get nested property by dot-notation path."""
        parts = path.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _format_address(self, address: Any) -> Optional[str]:
        """Format Schema.org PostalAddress to string."""
        if isinstance(address, str):
            return address.strip() if len(address.strip()) > 5 else None
        if isinstance(address, dict):
            parts = []
            for field in ["streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"]:
                if val := address.get(field):
                    if isinstance(val, dict):
                        val = val.get("name", str(val))
                    parts.append(str(val).strip())
            return ", ".join(parts) if parts else None
        return None

    async def _add_embedded_edge(
        self,
        node_id: str,
        edge: Dict[str, Any],
        project_id: str,
    ) -> bool:
        """
        Add edge to node's embedded_edges array in C-1 format.

        This matches the format used by the main Grid extraction pipeline.
        """
        if not self._es:
            return False

        index = self._get_c1_index(project_id)

        embedded_edge = {
            "edge_id": f"{edge['source_id']}:{edge['relation']}:{edge['target_id']}",
            "relationship": edge["relation"],
            "direction": "outgoing",
            "target_id": edge["target_id"],
            "target_label": edge.get("target_label", ""),
            "target_type": edge.get("target_type", ""),
            "confidence": edge.get("confidence", 0.8),
            "source_url": edge.get("source_url", ""),
            "verified": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "visual": {
                "line_style": "solid",
                "color": "#888888",
                "width": 1,
            }
        }

        try:
            await self._es.update(
                index=index,
                id=node_id,
                body={
                    "script": {
                        "source": """
                            if (ctx._source.embedded_edges == null) {
                                ctx._source.embedded_edges = [];
                            }
                            // Check if edge already exists
                            boolean exists = false;
                            for (edge in ctx._source.embedded_edges) {
                                if (edge.edge_id == params.edge.edge_id) {
                                    exists = true;
                                    break;
                                }
                            }
                            if (!exists) {
                                ctx._source.embedded_edges.add(params.edge);
                            }
                        """,
                        "params": {"edge": embedded_edge}
                    }
                },
                retry_on_conflict=3,
            )
            return True
        except Exception:
            return False

    async def materialize_entity(
        self,
        wdc_entity: Dict[str, Any],
        project_id: str,
        discovery_query: str,
        relevance_score: float = 0.5,
        relevance_threshold: float = 0.7,
        force: bool = False,
        extract_edges: bool = True,
    ) -> Optional[str]:
        """
        Materialize a single WDC entity to C-1.

        Uses MAIN SYSTEM indexer for deterministic IDs!
        Also extracts and creates edges from Schema.org properties.

        Args:
            wdc_entity: WDC entity dict with name, type, properties
            project_id: Target project
            discovery_query: Query that found this entity
            relevance_score: Relevance to the search (0-1)
            relevance_threshold: Minimum score for auto-materialization
            force: If True, ignore relevance threshold
            extract_edges: If True, extract edges from WDC properties

        Returns:
            Node ID if created, None if skipped
        """
        # Check threshold
        if not force and relevance_score < relevance_threshold:
            return None

        # Extract fields
        name = wdc_entity.get("name") or wdc_entity.get("label") or ""
        schema_type = wdc_entity.get("type") or wdc_entity.get("@type") or "Thing"
        source_url = wdc_entity.get("source_url") or wdc_entity.get("url") or ""
        source_domain = wdc_entity.get("source_domain") or wdc_entity.get("domain") or ""

        if not name or len(name) < 2:
            return None

        # Map Schema.org type to Cymonides type
        cymonides_type = map_schema_type(schema_type)

        # Build metadata
        metadata = {
            "wdc_source": True,
            "schema_type": schema_type,
            "source_domain": source_domain,
            "discovery_query": discovery_query,
            "discovery_timestamp": datetime.now(timezone.utc).isoformat(),
            "relevance_score": relevance_score,
            # Preserve original WDC properties (limited)
            "wdc_properties": {
                k: v for k, v in list(wdc_entity.items())[:20]  # Limit to 20 props
                if k not in ("name", "label", "type", "@type", "source_url", "url", "domain", "source_domain")
                and not isinstance(v, (dict, list))  # Skip complex nested
            },
        }

        # Create node using MAIN SYSTEM indexer
        node_id = await self._create_node(
            value=name,
            entity_type=cymonides_type,
            source_url=source_url,
            project_id=project_id,
            metadata=metadata,
        )

        if not node_id:
            return None

        # Extract and create edges from WDC properties
        if extract_edges and node_id:
            edges = await self._extract_edges_from_wdc(
                wdc_entity=wdc_entity,
                source_node_id=node_id,
                source_type=cymonides_type,
                source_url=source_url,
                project_id=project_id,
            )

            # Add edges to source node
            for edge in edges:
                await self._add_embedded_edge(node_id, edge, project_id)

        return node_id

    async def materialize_batch(
        self,
        wdc_entities: List[Dict[str, Any]],
        project_id: str,
        discovery_query: str,
        relevance_scores: Optional[List[float]] = None,
        relevance_threshold: float = 0.7,
        extract_edges: bool = True,
    ) -> MaterializationResult:
        """
        Materialize a batch of WDC entities.

        Args:
            wdc_entities: List of WDC entity dicts
            project_id: Target project
            discovery_query: Query that found these entities
            relevance_scores: Per-entity scores (defaults to 0.5)
            relevance_threshold: Minimum score for materialization
            extract_edges: If True, extract edges from WDC properties

        Returns:
            MaterializationResult with stats
        """
        result = MaterializationResult(total=len(wdc_entities))

        for i, entity in enumerate(wdc_entities):
            score = relevance_scores[i] if relevance_scores and i < len(relevance_scores) else 0.5

            try:
                node_id = await self.materialize_entity(
                    wdc_entity=entity,
                    project_id=project_id,
                    discovery_query=discovery_query,
                    relevance_score=score,
                    relevance_threshold=relevance_threshold,
                    extract_edges=extract_edges,
                )

                if node_id:
                    result.materialized.append(node_id)
                else:
                    result.skipped += 1

            except Exception as e:
                result.errors.append(str(e))
                result.skipped += 1

        return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def materialize_wdc_search(
    wdc_results: List[Dict[str, Any]],
    project_id: str,
    discovery_query: str,
    relevance_threshold: float = 0.7,
    extract_edges: bool = True,
) -> MaterializationResult:
    """
    Convenience function to materialize WDC search results.

    Usage:
        from CYMONIDES.scripts.wdc.materialization_gate import materialize_wdc_search

        result = await materialize_wdc_search(
            wdc_results=search_results,
            project_id="proj_123",
            discovery_query="[restaurant] : geo:de"
        )
        print(f"Materialized {len(result.materialized)} entities")
    """
    materializer = WDCMaterializer()
    await materializer.connect()

    try:
        return await materializer.materialize_batch(
            wdc_entities=wdc_results,
            project_id=project_id,
            discovery_query=discovery_query,
            relevance_threshold=relevance_threshold,
            extract_edges=extract_edges,
        )
    finally:
        await materializer.close()


# =============================================================================
# ID CONSISTENCY HELPERS (for testing/verification)
# =============================================================================

def get_canonical_id(value: str, entity_type: str) -> str:
    """
    Get the canonical ID that would be generated for a value.

    Useful for testing ID consistency between WDC and Grid extraction.

    Usage:
        # These should produce the SAME ID:
        wdc_id = get_canonical_id("Acme Corporation", "company")
        grid_id = get_canonical_id("ACME Corp", "company")
        assert wdc_id == grid_id  # Both normalized to "acme"
    """
    return generate_deterministic_id(value, entity_type)


def get_canonical_value(value: str, entity_type: str) -> str:
    """
    Get the canonical (normalized) value.

    Useful for debugging normalization.

    Usage:
        print(get_canonical_value("Acme Corporation Inc.", "company"))
        # Output: "acme corporation"  (Inc. removed)
    """
    return normalize_value(value, entity_type)
