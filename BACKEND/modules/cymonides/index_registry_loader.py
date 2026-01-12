"""
Index Registry Loader
=====================
Loads and provides access to the Index Meta-Registry system.
Provides unified interface for querying across index clusters.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
from elasticsearch import Elasticsearch


REGISTRY_DIR = Path(__file__).parent / "metadata" / "index_registry"


@dataclass
class IndexInfo:
    """Information about a single Elasticsearch index."""
    name: str
    alias: str
    tier: str
    description: str
    doc_count: int
    size_gb: float
    key_fields: Dict[str, Dict]
    integration: List[str]
    source_module: str


@dataclass
class ObjectTypeInfo:
    """Information about an object type and its index mappings."""
    name: str
    io_field_code: int
    prefix: str
    description: str
    indices: List[Dict]
    cross_links: Optional[Dict] = None


@dataclass
class ClusterInfo:
    """Information about an index cluster."""
    name: str
    description: str
    indices: List[str]
    primary_index: str
    total_docs: int
    query_strategy: str
    unified_fields: Optional[Dict] = None


class IndexRegistry:
    """
    Central registry for all Elasticsearch indices.

    Usage:
        registry = IndexRegistry()

        # Get indices for an object type
        indices = registry.get_indices_for_object_type("email")

        # Get a cluster
        cluster = registry.get_cluster("corporate")

        # Build a cluster query
        queries = registry.build_cluster_query("corporate", {"query": "Acme Corp"})

        # Route by prefix
        cluster_name = registry.route_by_prefix("c: Acme Corp")
    """

    _instance = None
    _loaded = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not IndexRegistry._loaded:
            self._load_all()
            IndexRegistry._loaded = True

    def _load_all(self):
        """Load all registry JSON files."""
        self._registry: Dict = self._load_json("INDEX_REGISTRY.json")
        self._superindex: Dict = self._load_json("OBJECT_SUPERINDEX.json")
        self._clusters: Dict = self._load_json("INDEX_CLUSTERS.json")
        self._io_integration: Dict = self._load_json("IO_INTEGRATION.json")
        self._queries: Dict = self._load_json("CLUSTER_QUERIES.json")

    def _load_json(self, filename: str) -> Dict:
        """Load a JSON file from the registry directory."""
        path = REGISTRY_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Registry file not found: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def reload(self):
        """Force reload all registry files."""
        IndexRegistry._loaded = False
        self._load_all()
        IndexRegistry._loaded = True

    # -------------------------------------------------------------------------
    # Index Registry Methods
    # -------------------------------------------------------------------------

    def get_index(self, index_name: str) -> Optional[IndexInfo]:
        """Get information about a specific index."""
        indices = self._registry.get("indices", {})
        if index_name not in indices:
            return None
        idx = indices[index_name]
        return IndexInfo(
            name=index_name,
            alias=idx.get("alias", index_name),
            tier=idx.get("tier", "unknown"),
            description=idx.get("description", ""),
            doc_count=idx.get("doc_count", 0),
            size_gb=idx.get("size_gb", 0.0),
            key_fields=idx.get("key_fields", {}),
            integration=idx.get("integration", []),
            source_module=idx.get("source_module", "")
        )

    def list_indices(self, tier: Optional[str] = None) -> List[str]:
        """List all index names, optionally filtered by tier."""
        indices = self._registry.get("indices", {})
        if tier:
            return [name for name, info in indices.items() if info.get("tier") == tier]
        return list(indices.keys())

    def get_indices_by_tier(self, tier: str) -> List[IndexInfo]:
        """Get all indices for a specific tier."""
        return [self.get_index(name) for name in self.list_indices(tier) if self.get_index(name)]

    def list_tiers(self) -> List[str]:
        """List all tier names."""
        return list(self._registry.get("tiers", {}).keys())

    # -------------------------------------------------------------------------
    # Object Superindex Methods
    # -------------------------------------------------------------------------

    def get_object_type(self, object_type: str) -> Optional[ObjectTypeInfo]:
        """Get information about an object type."""
        types = self._superindex.get("object_types", {})
        if object_type not in types:
            return None
        ot = types[object_type]
        return ObjectTypeInfo(
            name=object_type,
            io_field_code=ot.get("io_field_code", 0),
            prefix=ot.get("prefix", ""),
            description=ot.get("description", ""),
            indices=ot.get("indices", []),
            cross_links=ot.get("cross_links")
        )

    def get_indices_for_object_type(self, object_type: str, priority_limit: Optional[int] = None) -> List[str]:
        """
        Get list of index names that contain a specific object type.

        Args:
            object_type: Type name (email, phone, person, company, etc.)
            priority_limit: Only return indices with priority <= this value

        Returns:
            List of index names sorted by priority
        """
        types = self._superindex.get("object_types", {})
        if object_type not in types:
            return []

        indices = types[object_type].get("indices", [])
        if priority_limit:
            indices = [i for i in indices if i.get("priority", 999) <= priority_limit]

        # Sort by priority
        indices = sorted(indices, key=lambda x: x.get("priority", 999))
        return [i["index"] for i in indices]

    def get_field_mapping_for_object_type(self, object_type: str, index_name: str) -> Optional[Dict]:
        """Get the field mapping for an object type in a specific index."""
        types = self._superindex.get("object_types", {})
        if object_type not in types:
            return None

        for idx_info in types[object_type].get("indices", []):
            if idx_info["index"] == index_name:
                return idx_info
        return None

    def list_object_types(self) -> List[str]:
        """List all object type names."""
        return list(self._superindex.get("object_types", {}).keys())

    # -------------------------------------------------------------------------
    # Cluster Methods
    # -------------------------------------------------------------------------

    def get_cluster(self, cluster_name: str) -> Optional[ClusterInfo]:
        """Get information about a cluster."""
        clusters = self._clusters.get("clusters", {})
        if cluster_name not in clusters:
            return None
        cl = clusters[cluster_name]
        return ClusterInfo(
            name=cluster_name,
            description=cl.get("description", ""),
            indices=cl.get("indices", []),
            primary_index=cl.get("primary_index", ""),
            total_docs=cl.get("total_docs_estimate", 0),
            query_strategy=cl.get("query_strategy", "parallel_then_merge"),
            unified_fields=cl.get("unified_fields")
        )

    def list_clusters(self) -> List[str]:
        """List all cluster names."""
        return list(self._clusters.get("clusters", {}).keys())

    def get_cluster_indices(self, cluster_name: str) -> List[str]:
        """Get all index names in a cluster."""
        cluster = self.get_cluster(cluster_name)
        return cluster.indices if cluster else []

    # -------------------------------------------------------------------------
    # IO Integration Methods
    # -------------------------------------------------------------------------

    def get_field_code_mapping(self, field_code: int) -> Optional[Dict]:
        """Get the mapping for an IO field code."""
        mappings = self._io_integration.get("field_code_mappings", {})
        return mappings.get(str(field_code))

    def get_prefix_routing(self, prefix: str) -> Optional[Dict]:
        """Get routing info for a prefix (e.g., 'e:', 'c:')."""
        return self._io_integration.get("prefix_routing", {}).get(prefix)

    def route_by_prefix(self, query: str) -> Optional[str]:
        """
        Determine the cluster to use based on query prefix.

        Args:
            query: Query string like "c: Acme Corp" or "e: user@example.com"

        Returns:
            Cluster name or None if no prefix detected
        """
        # Check for prefix pattern
        match = re.match(r'^([a-z]+:)\s*(.+)$', query.strip(), re.IGNORECASE)
        if not match:
            return None

        prefix = match.group(1).lower()
        routing = self.get_prefix_routing(prefix)
        return routing.get("cluster") if routing else None

    def extract_query_value(self, query: str) -> tuple[Optional[str], str]:
        """
        Extract prefix and value from a prefixed query.

        Args:
            query: Query string like "c: Acme Corp"

        Returns:
            Tuple of (prefix, value) or (None, original_query)
        """
        match = re.match(r'^([a-z]+:)\s*(.+)$', query.strip(), re.IGNORECASE)
        if match:
            return match.group(1).lower(), match.group(2)
        return None, query

    # -------------------------------------------------------------------------
    # Query Building Methods
    # -------------------------------------------------------------------------

    def get_query_template(self, query_name: str) -> Optional[Dict]:
        """Get a named query template."""
        return self._queries.get("queries", {}).get(query_name)

    def list_query_templates(self) -> List[str]:
        """List all available query template names."""
        return list(self._queries.get("queries", {}).keys())

    def build_cluster_query(
        self,
        cluster_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Dict]:
        """
        Build Elasticsearch queries for all indices in a cluster.

        Args:
            cluster_name: Name of the cluster
            params: Query parameters (query, limit, filters, etc.)

        Returns:
            Dict mapping index name to ES query body
        """
        cluster = self.get_cluster(cluster_name)
        if not cluster:
            return {}

        queries = {}
        query_value = params.get("query", "")
        limit = params.get("limit", 50)

        for index_name in cluster.indices:
            # Determine if this is a term or match query based on object type
            # For now, use match for text fields
            query_body = {
                "size": limit,
                "query": {
                    "multi_match": {
                        "query": query_value,
                        "fields": ["name", "name_normalized^2", "email", "domain"],
                        "fuzziness": "AUTO"
                    }
                }
            }
            queries[index_name] = query_body

        return queries

    def build_object_type_query(
        self,
        object_type: str,
        value: str,
        limit: int = 50,
        priority_limit: Optional[int] = None
    ) -> Dict[str, Dict]:
        """
        Build queries for all indices containing an object type.

        Args:
            object_type: Type name (email, phone, person, etc.)
            value: Value to search for
            limit: Max results per index
            priority_limit: Only query indices with priority <= this

        Returns:
            Dict mapping index name to ES query body
        """
        ot_info = self.get_object_type(object_type)
        if not ot_info:
            return {}

        queries = {}
        for idx_info in ot_info.indices:
            if priority_limit and idx_info.get("priority", 999) > priority_limit:
                continue

            index_name = idx_info["index"]
            field = idx_info["field"]
            query_type = idx_info.get("query_type", "term")

            if query_type == "term":
                query_body = {
                    "size": limit,
                    "query": {"term": {field: value}}
                }
            elif query_type == "match":
                query_body = {
                    "size": limit,
                    "query": {"match": {field: {"query": value, "fuzziness": "AUTO"}}}
                }
            else:
                # Default to multi_match
                query_body = {
                    "size": limit,
                    "query": {"multi_match": {"query": value, "fields": [field]}}
                }

            # Add filters if specified
            if "filter" in idx_info:
                query_body["query"] = {
                    "bool": {
                        "must": [query_body["query"]],
                        "filter": [{"term": {k: v}} for k, v in idx_info["filter"].items()]
                    }
                }

            queries[index_name] = query_body

        return queries


class ClusterQueryExecutor:
    """
    Executes queries across index clusters with merge/dedup logic.

    Usage:
        executor = ClusterQueryExecutor(es_client)
        results = executor.query_cluster("corporate", {"query": "Acme Corp"})
    """

    def __init__(self, es_client: Elasticsearch):
        self.es = es_client
        self.registry = IndexRegistry()

    def query_cluster(
        self,
        cluster_name: str,
        params: Dict[str, Any],
        timeout: str = "30s"
    ) -> List[Dict]:
        """
        Execute a query across all indices in a cluster.

        Args:
            cluster_name: Name of the cluster
            params: Query parameters
            timeout: Elasticsearch timeout

        Returns:
            Merged and deduplicated results
        """
        cluster = self.registry.get_cluster(cluster_name)
        if not cluster:
            return []

        queries = self.registry.build_cluster_query(cluster_name, params)
        if not queries:
            return []

        # Execute queries
        all_results = []
        for index_name, query_body in queries.items():
            try:
                response = self.es.search(
                    index=index_name,
                    body=query_body,
                    timeout=timeout
                )
                for hit in response.get("hits", {}).get("hits", []):
                    result = hit["_source"]
                    result["_index"] = index_name
                    result["_score"] = hit.get("_score", 0)
                    result["_id"] = hit["_id"]
                    all_results.append(result)
            except Exception as e:
                print(f"Error querying {index_name}: {e}")

        # Merge and deduplicate based on cluster strategy
        if cluster.query_strategy == "parallel_then_merge":
            return self._merge_results(all_results, cluster)
        elif cluster.query_strategy == "cascade":
            return self._cascade_results(all_results, cluster)

        return all_results

    def query_object_type(
        self,
        object_type: str,
        value: str,
        limit: int = 50,
        priority_limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Query all indices for a specific object type.

        Args:
            object_type: Type name
            value: Value to search
            limit: Max results per index
            priority_limit: Only query high-priority indices

        Returns:
            Results from all matching indices
        """
        queries = self.registry.build_object_type_query(
            object_type, value, limit, priority_limit
        )

        all_results = []
        for index_name, query_body in queries.items():
            try:
                response = self.es.search(index=index_name, body=query_body)
                for hit in response.get("hits", {}).get("hits", []):
                    result = hit["_source"]
                    result["_index"] = index_name
                    result["_score"] = hit.get("_score", 0)
                    all_results.append(result)
            except Exception as e:
                print(f"Error querying {index_name}: {e}")

        return all_results

    def _merge_results(self, results: List[Dict], cluster: ClusterInfo) -> List[Dict]:
        """Merge and deduplicate results from parallel queries."""
        # Group by merge key
        seen: Set[str] = set()
        merged = []

        for result in sorted(results, key=lambda x: -x.get("_score", 0)):
            # Create merge key from available fields
            key_parts = []
            for field in ["company_number", "email", "name_normalized", "name"]:
                if field in result and result[field]:
                    key_parts.append(str(result[field]).lower())
                    break

            key = "|".join(key_parts) if key_parts else result.get("_id", "")
            if key and key not in seen:
                seen.add(key)
                merged.append(result)

        return merged

    def _cascade_results(self, results: List[Dict], cluster: ClusterInfo) -> List[Dict]:
        """Return results from highest-priority index that has matches."""
        # Group by index
        by_index: Dict[str, List[Dict]] = {}
        for result in results:
            idx = result.get("_index", "")
            if idx not in by_index:
                by_index[idx] = []
            by_index[idx].append(result)

        # Return from first index in priority order that has results
        for index_name in cluster.indices:
            if index_name in by_index and by_index[index_name]:
                return by_index[index_name]

        return []


# Convenience functions
def get_registry() -> IndexRegistry:
    """Get the singleton IndexRegistry instance."""
    return IndexRegistry()


def list_all_indices() -> List[str]:
    """List all known index names."""
    return get_registry().list_indices()


def get_indices_for_email() -> List[str]:
    """Get indices that contain email data."""
    return get_registry().get_indices_for_object_type("email")


def get_indices_for_company() -> List[str]:
    """Get indices that contain company data."""
    return get_registry().get_indices_for_object_type("company")


def get_indices_for_person() -> List[str]:
    """Get indices that contain person data."""
    return get_registry().get_indices_for_object_type("person")


if __name__ == "__main__":
    # Demo usage
    registry = IndexRegistry()

    print("=== Index Registry Demo ===\n")

    print("Tiers:", registry.list_tiers())
    print("\nClusters:", registry.list_clusters())
    print("\nObject Types:", registry.list_object_types())

    print("\n--- Email Object Type ---")
    email_indices = registry.get_indices_for_object_type("email")
    print(f"Indices: {email_indices}")

    print("\n--- Corporate Cluster ---")
    corp_cluster = registry.get_cluster("corporate")
    if corp_cluster:
        print(f"Description: {corp_cluster.description}")
        print(f"Indices: {corp_cluster.indices}")
        print(f"Strategy: {corp_cluster.query_strategy}")

    print("\n--- Prefix Routing ---")
    for prefix in ["c:", "e:", "p:", "d:"]:
        routing = registry.get_prefix_routing(prefix)
        if routing:
            print(f"  {prefix} -> {routing['cluster']} ({routing['description']})")

    print("\n--- Building Cluster Query ---")
    queries = registry.build_cluster_query("corporate", {"query": "Acme Corp", "limit": 10})
    for idx, q in queries.items():
        print(f"  {idx}: {json.dumps(q['query'], indent=2)[:100]}...")
