"""
Schema Registry - Tier definitions and schema management for Cymonides
Manages the 3-tier architecture:
  C-1: cymonides-1-{projectId} - Project-specific graph indices
  C-2: cymonides-2 - Free-form text corpus, scraped website contents
  C-3: cymonides-3 alias -> Entity superindex (atlas, domains_unified, companies_unified, persons_unified)
  CC Graph: cc_refdom alias -> cymonides_cc_domain_edges, cymonides_cc_domain_vertices
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from datetime import datetime
import json


class Tier(Enum):
    """Cymonides data tiers"""
    C1 = "c1"  # Project-specific graphs
    C2 = "c2"  # Content corpus
    C3 = "c3"  # Entity superindex
    CC_GRAPH = "cc_graph"  # Common Crawl domain graph


class DataType(Enum):
    """Data types within tiers"""
    # C-1 types
    PROJECT_NODE = "project_node"
    PROJECT_EDGE = "project_edge"
    
    # C-2 types
    CONTENT = "content"
    ONION_PAGE = "onion_page"
    
    # C-3 types (entity superindex)
    PERSON = "person"
    COMPANY = "company"
    DOMAIN = "domain"
    EMAIL = "email"
    PHONE = "phone"
    LOCATION = "location"
    TEMPORAL = "temporal"
    BREACH_RECORD = "breach_record"
    
    # CC Graph types
    DOMAIN_VERTEX = "domain_vertex"
    DOMAIN_EDGE = "domain_edge"


@dataclass
class TierConfig:
    """Configuration for a Cymonides tier"""
    tier: Tier
    alias: str  # The alias to use (e.g., cymonides-3)
    underlying_indices: List[str]  # Actual indices behind the alias
    description: str
    data_types: List[DataType]
    default_shards: int = 5
    default_replicas: int = 1
    refresh_interval: str = "30s"


@dataclass
class SchemaDefinition:
    """Schema definition for a data type"""
    data_type: DataType
    tier: Tier
    index_pattern: str  # e.g., "cymonides-1-{project_id}" or "atlas"
    mapping: Dict[str, Any]
    settings: Dict[str, Any] = field(default_factory=dict)
    doc_id_field: Optional[str] = None  # Field to use as _id
    routing_field: Optional[str] = None  # Field for routing
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=datetime.utcnow)


class SchemaRegistry:
    """
    Central registry for all Cymonides schemas and tier configurations.
    Manages ES mappings, aliases, and data type routing.
    """
    
    # Tier configurations
    TIER_CONFIGS: Dict[Tier, TierConfig] = {
        Tier.C1: TierConfig(
            tier=Tier.C1,
            alias="cymonides-1-*",  # Wildcard pattern
            underlying_indices=[],  # Dynamic per project
            description="Project-specific investigation graphs",
            data_types=[DataType.PROJECT_NODE, DataType.PROJECT_EDGE],
            default_shards=1,  # Small per-project indices
            default_replicas=0,
        ),
        Tier.C2: TierConfig(
            tier=Tier.C2,
            alias="cymonides-2",
            underlying_indices=["cymonides-2"],
            description="Content corpus - scraped websites, documents, text",
            data_types=[DataType.CONTENT, DataType.ONION_PAGE],
            default_shards=5,
            default_replicas=1,
            refresh_interval="60s",
        ),
        Tier.C3: TierConfig(
            tier=Tier.C3,
            alias="cymonides-3",
            underlying_indices=[
                "emails_unified",
                "phones_unified",
                "geo_unified",
                "domains_unified",
                "companies_unified", 
                "persons_unified",
                "breach_compilation",
                "breach_compilation_2022",
            ],
            description="Entity superindex - consolidated entities from all sources",
            data_types=[
                DataType.PERSON,
                DataType.COMPANY,
                DataType.DOMAIN,
                DataType.EMAIL,
                DataType.PHONE,
                DataType.LOCATION,
                DataType.BREACH_RECORD,
            ],
            default_shards=10,
            default_replicas=1,
            refresh_interval="60s",
        ),
        Tier.CC_GRAPH: TierConfig(
            tier=Tier.CC_GRAPH,
            alias="cc_refdom",
            underlying_indices=[
                "cymonides_cc_domain_vertices",
                "cymonides_cc_domain_edges",
            ],
            description="Common Crawl domain reference graph",
            data_types=[DataType.DOMAIN_VERTEX, DataType.DOMAIN_EDGE],
            default_shards=20,
            default_replicas=1,
            refresh_interval="120s",
        ),
    }
    
    # Data type to index routing
    DATA_TYPE_INDEX: Dict[DataType, str] = {
        # C-3 entity types -> specific indices
        DataType.PERSON: "persons_unified",
        DataType.COMPANY: "companies_unified",
        DataType.DOMAIN: "domains_unified",
        DataType.EMAIL: "emails_unified",
        DataType.PHONE: "phones_unified",
        DataType.LOCATION: "geo_unified",
        DataType.TEMPORAL: "temp_unified",
        DataType.BREACH_RECORD: "breach_compilation",
        
        # C-2 content types
        DataType.CONTENT: "cymonides-2",
        DataType.ONION_PAGE: "onion-pages",
        
        # CC Graph
        DataType.DOMAIN_VERTEX: "cymonides_cc_domain_vertices",
        DataType.DOMAIN_EDGE: "cymonides_cc_domain_edges",
    }
    
    def __init__(self, es_client=None):
        self.es = es_client
        self._schemas: Dict[DataType, SchemaDefinition] = {}
        self._load_default_schemas()
    
    def _load_default_schemas(self):
        """Load default schema definitions"""
        from .mappings import (
            CONTENT_MAPPING,
            ENTITY_MAPPING,
            BREACH_MAPPING,
            DOMAIN_MAPPING,
            GRAPH_EDGE_MAPPING,
            GRAPH_VERTEX_MAPPING,
        )
        
        # C-2 schemas
        self._schemas[DataType.CONTENT] = SchemaDefinition(
            data_type=DataType.CONTENT,
            tier=Tier.C2,
            index_pattern="cymonides-2",
            mapping=CONTENT_MAPPING,
            doc_id_field="url_hash",
        )
        
        self._schemas[DataType.ONION_PAGE] = SchemaDefinition(
            data_type=DataType.ONION_PAGE,
            tier=Tier.C2,
            index_pattern="onion-pages",
            mapping=CONTENT_MAPPING,
            doc_id_field="url_hash",
        )
        
        # C-3 entity schemas
        for dtype in [DataType.PERSON, DataType.COMPANY, DataType.EMAIL, 
                      DataType.PHONE, DataType.LOCATION]:
            self._schemas[dtype] = SchemaDefinition(
                data_type=dtype,
                tier=Tier.C3,
                index_pattern=self.DATA_TYPE_INDEX[dtype],
                mapping=ENTITY_MAPPING,
                doc_id_field="entity_id",
            )
        
        self._schemas[DataType.DOMAIN] = SchemaDefinition(
            data_type=DataType.DOMAIN,
            tier=Tier.C3,
            index_pattern="domains_unified",
            mapping=DOMAIN_MAPPING,
            doc_id_field="domain",
        )
        
        self._schemas[DataType.BREACH_RECORD] = SchemaDefinition(
            data_type=DataType.BREACH_RECORD,
            tier=Tier.C3,
            index_pattern="breach_compilation",
            mapping=BREACH_MAPPING,
            doc_id_field="record_hash",
        )
        
        # CC Graph schemas
        self._schemas[DataType.DOMAIN_VERTEX] = SchemaDefinition(
            data_type=DataType.DOMAIN_VERTEX,
            tier=Tier.CC_GRAPH,
            index_pattern="cymonides_cc_domain_vertices",
            mapping=GRAPH_VERTEX_MAPPING,
            doc_id_field="domain",
        )
        
        self._schemas[DataType.DOMAIN_EDGE] = SchemaDefinition(
            data_type=DataType.DOMAIN_EDGE,
            tier=Tier.CC_GRAPH,
            index_pattern="cymonides_cc_domain_edges",
            mapping=GRAPH_EDGE_MAPPING,
            doc_id_field="edge_id",
        )
    
    def get_tier_config(self, tier: Tier) -> TierConfig:
        """Get configuration for a tier"""
        return self.TIER_CONFIGS[tier]
    
    def get_schema(self, data_type: DataType) -> Optional[SchemaDefinition]:
        """Get schema definition for a data type"""
        return self._schemas.get(data_type)
    
    def get_target_index(self, data_type: DataType, project_id: Optional[str] = None) -> str:
        """
        Get the target index for a data type.
        For C-1 types, requires project_id.
        """
        if data_type in [DataType.PROJECT_NODE, DataType.PROJECT_EDGE]:
            if not project_id:
                raise ValueError(f"project_id required for {data_type}")
            return f"cymonides-1-{project_id}"
        
        return self.DATA_TYPE_INDEX.get(data_type)
    
    def get_tier_for_type(self, data_type: DataType) -> Tier:
        """Get the tier a data type belongs to"""
        for tier, config in self.TIER_CONFIGS.items():
            if data_type in config.data_types:
                return tier
        raise ValueError(f"Unknown data type: {data_type}")
    
    def get_c1_index(self, project_id: str) -> str:
        """Get C-1 index name for a project"""
        return f"cymonides-1-{project_id}"
    
    def list_data_types(self, tier: Optional[Tier] = None) -> List[DataType]:
        """List all data types, optionally filtered by tier"""
        if tier:
            return list(self.TIER_CONFIGS[tier].data_types)
        return list(DataType)
    
    async def ensure_alias(self, tier: Tier) -> bool:
        """Ensure alias exists for a tier"""
        if not self.es:
            raise RuntimeError("ES client not configured")
        
        config = self.TIER_CONFIGS[tier]
        
        # Check if alias exists
        alias_exists = await self.es.indices.exists_alias(name=config.alias)
        if alias_exists:
            return True
        
        # Create alias pointing to underlying indices
        actions = []
        for idx in config.underlying_indices:
            if await self.es.indices.exists(index=idx):
                actions.append({"add": {"index": idx, "alias": config.alias}})
        
        if actions:
            await self.es.indices.update_aliases(body={"actions": actions})
            return True
        
        return False
    
    async def create_index_if_not_exists(
        self, 
        data_type: DataType,
        project_id: Optional[str] = None
    ) -> str:
        """Create index for data type if it doesn't exist"""
        if not self.es:
            raise RuntimeError("ES client not configured")
        
        index_name = self.get_target_index(data_type, project_id)
        schema = self.get_schema(data_type)
        tier_config = self.get_tier_config(self.get_tier_for_type(data_type))
        
        if not await self.es.indices.exists(index=index_name):
            settings = {
                "number_of_shards": tier_config.default_shards,
                "number_of_replicas": tier_config.default_replicas,
                "refresh_interval": tier_config.refresh_interval,
            }
            
            if schema and schema.settings:
                settings.update(schema.settings)
            
            body = {
                "settings": settings,
                "mappings": schema.mapping if schema else {},
            }
            
            await self.es.indices.create(index=index_name, body=body)
        
        return index_name
    
    def to_dict(self) -> Dict[str, Any]:
        """Export registry configuration as dict"""
        return {
            "tiers": {
                tier.value: {
                    "alias": config.alias,
                    "underlying_indices": config.underlying_indices,
                    "description": config.description,
                    "data_types": [dt.value for dt in config.data_types],
                }
                for tier, config in self.TIER_CONFIGS.items()
            },
            "data_type_routing": {
                dt.value: idx for dt, idx in self.DATA_TYPE_INDEX.items()
            },
            "schemas": {
                dt.value: {
                    "tier": schema.tier.value,
                    "index_pattern": schema.index_pattern,
                    "doc_id_field": schema.doc_id_field,
                    "version": schema.version,
                }
                for dt, schema in self._schemas.items()
            },
        }
