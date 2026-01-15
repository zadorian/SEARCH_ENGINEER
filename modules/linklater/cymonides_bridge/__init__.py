"""
CYMONIDES Bridge - Auto-index LINKLATER outputs to C-1 and C-2

CRITICAL INFRASTRUCTURE:
- C-2 (linklater_corpus): Free text index for raw scraped content
- C-1 (search_nodes): Entity nodes with DETERMINISTIC IDs

AUTOMATIC INDEXING:
- Every scrape → C-2 immediately
- Every entity extraction → C-1 with stable node IDs
- Every search result → C-2 immediately

DETERMINISTIC NODE IDs:
- Canonical normalization: "John Smith" → "john smith"
- ID = hash(canonical_value + entity_type)
- Same person across 1000 scrapes = same node ID = edges accumulate

Usage:
    from linklater.cymonides_bridge import CymonidesIndexer

    indexer = CymonidesIndexer()

    # Index scraped content to C-2
    await indexer.index_content(
        url="https://example.com/about",
        content="...",
        title="About Us",
        domain="example.com"
    )

    # Index entities to C-1 with deterministic IDs
    await indexer.index_entities(
        entities={"persons": ["John Smith"], "companies": ["ACME Corp"]},
        source_url="https://example.com/about",
        project_id="default"
    )
"""

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

# Elasticsearch client
try:
    from elasticsearch import AsyncElasticsearch
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False

# =============================================================================
# CONFIGURATION
# =============================================================================

ES_URL = "http://localhost:9200"
ES_USER = "elastic"
ES_PASS = "szilvansen"

# Index names - CYMONIDES MANDATE
# C-2: Global corpus index (one index for all scraped content)
C2_INDEX = "cymonides-2"

# C-1: Per-project node indices (pattern: cymonides-1-{projectId})
# NO GLOBAL NODE INDEX - every node must belong to a project
# NO SEPARATE EDGE INDEX - edges are EMBEDDED in nodes as embedded_edges array
def get_c1_index(project_id: str) -> str:
    """Get the CYMONIDES-1 index for a project. Edges are embedded in nodes."""
    if not project_id or project_id == "default":
        raise ValueError("CYMONIDES MANDATE: project_id is REQUIRED for C-1 operations. Cannot use 'default'.")
    return f"cymonides-1-{project_id}"

# REMOVED: C1_NODES_INDEX = "search_nodes"  - VIOLATES MANDATE
# REMOVED: C1_EDGES_INDEX = "search_edges"  - EDGES ARE EMBEDDED

# Entity type mappings for C-1
ENTITY_TYPE_MAP = {
    "person": {"type": "person", "typeName": "Person", "class": "entity", "className": "Entity"},
    "company": {"type": "company", "typeName": "Company", "class": "entity", "className": "Entity"},
    "organization": {"type": "organization", "typeName": "Organization", "class": "entity", "className": "Entity"},
    "email": {"type": "email", "typeName": "Email", "class": "identifier", "className": "Identifier"},
    "phone": {"type": "phone", "typeName": "Phone", "class": "identifier", "className": "Identifier"},
    "address": {"type": "address", "typeName": "Address", "class": "location", "className": "Location"},
    "crypto": {"type": "crypto_address", "typeName": "Crypto Address", "class": "identifier", "className": "Identifier"},
}


# =============================================================================
# CANONICAL NORMALIZATION (for deterministic IDs)
# =============================================================================

def normalize_value(value: str, entity_type: str = "") -> str:
    """
    Normalize entity value to canonical form for deterministic ID generation.

    The same entity appearing in different sources should produce the same ID.

    Rules:
    - Lowercase
    - Remove accents/diacritics
    - Collapse whitespace
    - Strip punctuation (except for emails)
    - Handle common variations

    Examples:
        "John Smith" → "john smith"
        "ACME Corp." → "acme corp"
        "John.Doe@Example.COM" → "john.doe@example.com" (email preserved)
    """
    if not value:
        return ""

    # Normalize unicode (decompose accents)
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(c for c in value if not unicodedata.combining(c))

    # Lowercase
    value = value.lower()

    # For emails, preserve structure but lowercase
    if entity_type == "email":
        return value.strip()

    # For phones, keep only digits
    if entity_type == "phone":
        return re.sub(r'[^\d]', '', value)

    # For crypto addresses, keep alphanumeric
    if entity_type in ("crypto", "crypto_address"):
        return re.sub(r'[^a-z0-9]', '', value)

    # For names/companies:
    # - Remove common suffixes that cause duplicates
    # - Collapse whitespace
    # - Remove punctuation

    # Remove common company suffixes
    if entity_type in ("company", "organization"):
        suffixes = [
            r'\s+(inc\.?|llc\.?|ltd\.?|corp\.?|corporation|company|co\.?|group|holdings|partners|plc\.?)$',
            r'\s+(gmbh|ag|se|sarl|sas|sa|bv|nv)$',
        ]
        for suffix in suffixes:
            value = re.sub(suffix, '', value, flags=re.IGNORECASE)

    # Remove punctuation
    value = re.sub(r'[^\w\s]', '', value)

    # Collapse whitespace
    value = ' '.join(value.split())

    return value.strip()


def generate_deterministic_id(value: str, entity_type: str) -> str:
    """
    Generate deterministic ID from canonical value + type.

    The same entity will always produce the same ID:
    - "John Smith" (person) → same ID every time
    - "john smith" (person) → same ID (normalized)
    - "JOHN SMITH" (person) → same ID (normalized)

    Args:
        value: Entity value (will be normalized)
        entity_type: Entity type (person, company, email, etc.)

    Returns:
        24-char deterministic ID
    """
    canonical = normalize_value(value, entity_type)
    if not canonical:
        return ""

    # Include type in hash to avoid collisions
    # (e.g., "Apple" the company vs "apple" the fruit)
    hash_input = f"{entity_type}:{canonical}"

    # SHA256, take first 24 chars for readability
    return hashlib.sha256(hash_input.encode()).hexdigest()[:24]


# =============================================================================
# C-2 CONTENT DOCUMENT
# =============================================================================

def create_c2_document(
    url: str,
    content: str,
    title: str = None,
    domain: str = None,
    entities: Dict[str, List] = None,
    outlinks: List[str] = None,
    backlinks: List[str] = None,
    archive_url: str = None,
    timestamp: str = None,
    source: str = "linklater",
    project_id: str = "default",
    query: str = None,
    **extra
) -> Dict[str, Any]:
    """
    Create C-2 (linklater_corpus) document for free-text indexing.

    This is the raw content index - everything scraped goes here immediately.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Parse domain from URL if not provided
    if not domain and url:
        try:
            domain = urlparse(url).netloc
        except Exception as e:
            domain = None

    # Generate deterministic doc ID from URL
    doc_id = hashlib.sha256(url.encode()).hexdigest()[:24] if url else None

    doc = {
        "url": url,
        "domain": domain,
        "title": title[:500] if title else None,
        "content": content[:100000] if content else None,  # Cap at 100K
        "content_length": len(content) if content else 0,
        "word_count": len(content.split()) if content else 0,

        # Entities (flattened for search)
        "entity_persons": entities.get("persons", []) if entities else [],
        "entity_organizations": entities.get("companies", []) if entities else [],
        "entity_locations": entities.get("addresses", []) if entities else [],
        "entities": entities if entities else {},

        # Links
        "outlinks": outlinks[:500] if outlinks else [],
        "backlinks": backlinks[:500] if backlinks else [],

        # Archive metadata
        "archive_url": archive_url,
        "timestamp": timestamp,

        # Source tracking
        "source": source,
        "source_url": url,
        "project_id": project_id,
        "query": query,

        # Timestamps
        "scraped_at": timestamp or now,
        "indexed_at": now,
    }

    # Add any extra fields
    doc.update(extra)

    return doc_id, doc


# =============================================================================
# C-1 ENTITY NODE
# =============================================================================

def create_c1_node(
    value: str,
    entity_type: str,
    source_url: str = None,
    source_urls: List[str] = None,
    project_id: str = "default",
    metadata: Dict = None,
    **extra
) -> tuple:
    """
    Create C-1 (search_nodes) entity node with deterministic ID.

    The ID is deterministic based on canonical value + type:
    - Same person from different sources → same node
    - Edges accumulate over time
    """
    # Map entity type
    type_info = ENTITY_TYPE_MAP.get(entity_type, {
        "type": entity_type,
        "typeName": entity_type.title(),
        "class": "entity",
        "className": "Entity"
    })

    # Generate deterministic ID
    node_id = generate_deterministic_id(value, entity_type)
    if not node_id:
        return None, None

    canonical = normalize_value(value, entity_type)
    now = datetime.now(timezone.utc).isoformat()

    # Collect source URLs
    all_sources = list(source_urls or [])
    if source_url and source_url not in all_sources:
        all_sources.append(source_url)

    node = {
        "id": node_id,
        "canonicalValue": canonical,
        "label": value,  # Original form for display

        # Type info
        "type": type_info["type"],
        "typeName": type_info["typeName"],
        "class": type_info["class"],
        "className": type_info["className"],

        # Content for search
        "content": value,

        # Source tracking
        "source_urls": all_sources[:100],
        "projectId": project_id,

        # Timestamps
        "createdAt": now,
        "timestamp": now,
        "lastSeen": now,

        # Status
        "status": "active",

        # Metadata
        "metadata": metadata or {},
    }

    # Add extra fields
    node.update(extra)

    return node_id, node


# =============================================================================
# CYMONIDES INDEXER
# =============================================================================

class CymonidesIndexer:
    """
    Bridge to auto-index LINKLATER outputs to CYMONIDES.

    Usage:
        indexer = CymonidesIndexer()
        await indexer.connect()

        # Index content to C-2
        await indexer.index_content(url=url, content=html, ...)

        # Index entities to C-1
        await indexer.index_entities(entities={"persons": [...], ...}, source_url=url)

        await indexer.close()
    """

    def __init__(
        self,
        es_url: str = ES_URL,
        es_user: str = ES_USER,
        es_pass: str = ES_PASS,
        c2_index: str = C2_INDEX,
    ):
        self.es_url = es_url
        self.es_user = es_user
        self.es_pass = es_pass
        self.c2_index = c2_index
        # CYMONIDES MANDATE: C1 index is per-project, use get_c1_index(project_id)
        # CYMONIDES MANDATE: NO separate edge index - edges are embedded in nodes
        self._es: Optional[AsyncElasticsearch] = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to Elasticsearch."""
        if not ES_AVAILABLE:
            return False

        if self._connected and self._es:
            return True

        try:
            self._es = AsyncElasticsearch(
                [self.es_url],
                basic_auth=(self.es_user, self.es_pass)
            )
            # Test connection
            await self._es.info()
            self._connected = True
            return True
        except Exception as e:
            self._connected = False
            return False

    async def close(self):
        """Close Elasticsearch connection."""
        if self._es:
            await self._es.close()
            self._es = None
            self._connected = False

    async def _ensure_connected(self):
        """Ensure connection is established."""
        if not self._connected:
            await self.connect()
        if not self._connected:
            raise RuntimeError("Failed to connect to Elasticsearch")

    # =========================================================================
    # C-2: FREE TEXT INDEX
    # =========================================================================

    async def index_content(
        self,
        url: str,
        content: str,
        title: str = None,
        domain: str = None,
        entities: Dict[str, List] = None,
        outlinks: List[str] = None,
        backlinks: List[str] = None,
        archive_url: str = None,
        timestamp: str = None,
        source: str = "linklater",
        project_id: str = "default",
        query: str = None,
        **extra
    ) -> Optional[str]:
        """
        Index scraped content to C-2 (linklater_corpus).

        This should be called IMMEDIATELY after any scrape operation.

        Args:
            url: Source URL
            content: Raw text content (HTML stripped)
            title: Page title
            domain: Domain (auto-detected from URL if not provided)
            entities: Extracted entities {"persons": [], "companies": [], ...}
            outlinks: Outbound links found
            backlinks: Inbound links (if known)
            archive_url: Wayback/CC archive URL if historical
            timestamp: Archive timestamp if historical
            source: Source identifier (linklater, wayback, cc, etc.)
            project_id: Project ID for filtering
            query: Original query that triggered this scrape

        Returns:
            Document ID if successful, None otherwise
        """
        await self._ensure_connected()

        doc_id, doc = create_c2_document(
            url=url,
            content=content,
            title=title,
            domain=domain,
            entities=entities,
            outlinks=outlinks,
            backlinks=backlinks,
            archive_url=archive_url,
            timestamp=timestamp,
            source=source,
            project_id=project_id,
            query=query,
            **extra
        )

        if not doc_id:
            return None

        try:
            await self._es.index(
                index=self.c2_index,
                id=doc_id,
                document=doc
            )
            return doc_id
        except Exception as e:
            return None

    async def index_search_results(
        self,
        results: List[Dict],
        query: str,
        source: str = "search",
        project_id: str = "default"
    ) -> List[str]:
        """
        Index search results to C-2.

        Each search result gets indexed immediately for future retrieval.

        Args:
            results: List of search results [{"url": ..., "title": ..., "snippet": ...}, ...]
            query: Original search query
            source: Search source (google, bing, exa, etc.)
            project_id: Project ID

        Returns:
            List of indexed document IDs
        """
        await self._ensure_connected()

        indexed_ids = []
        for result in results:
            url = result.get("url")
            if not url:
                continue

            doc_id = await self.index_content(
                url=url,
                content=result.get("snippet", ""),
                title=result.get("title"),
                source=source,
                project_id=project_id,
                query=query,
                # Add search-specific metadata
                search_snippet=result.get("snippet"),
                search_rank=result.get("rank"),
            )
            if doc_id:
                indexed_ids.append(doc_id)

        return indexed_ids

    # =========================================================================
    # C-1: ENTITY NODES
    # =========================================================================

    async def index_entity(
        self,
        value: str,
        entity_type: str,
        project_id: str,  # REQUIRED - CYMONIDES MANDATE
        source_url: str = None,
        source_urls: List[str] = None,
        metadata: Dict = None,
        **extra
    ) -> Optional[str]:
        """
        Index single entity to CYMONIDES-1-{project_id} with deterministic ID.

        CYMONIDES MANDATE: project_id is REQUIRED. All nodes go to per-project index.

        If entity already exists, updates lastSeen and adds source_url.

        Args:
            value: Entity value (e.g., "John Smith")
            entity_type: Entity type (person, company, email, etc.)
            project_id: Project ID (REQUIRED)
            source_url: URL where entity was found
            source_urls: Multiple source URLs
            metadata: Additional metadata

        Returns:
            Node ID if successful, None otherwise
        """
        await self._ensure_connected()

        # CYMONIDES MANDATE: Get per-project index
        c1_index = get_c1_index(project_id)

        node_id, node = create_c1_node(
            value=value,
            entity_type=entity_type,
            source_url=source_url,
            source_urls=source_urls,
            project_id=project_id,
            metadata=metadata,
            **extra
        )

        if not node_id:
            return None

        try:
            # Check if node exists in project-specific index
            exists = await self._es.exists(index=c1_index, id=node_id)

            if exists:
                # Update existing node - add source URL and update lastSeen
                update_script = {
                    "script": {
                        "source": """
                            if (ctx._source.source_urls == null) {
                                ctx._source.source_urls = [];
                            }
                            for (url in params.new_urls) {
                                if (!ctx._source.source_urls.contains(url)) {
                                    ctx._source.source_urls.add(url);
                                }
                            }
                            // Limit to 100 URLs
                            if (ctx._source.source_urls.size() > 100) {
                                ctx._source.source_urls = ctx._source.source_urls.subList(0, 100);
                            }
                            ctx._source.lastSeen = params.now;
                        """,
                        "params": {
                            "new_urls": node.get("source_urls", []),
                            "now": datetime.now(timezone.utc).isoformat()
                        }
                    }
                }
                await self._es.update(
                    index=c1_index,
                    id=node_id,
                    body=update_script
                )
            else:
                # Create new node in project-specific index
                await self._es.index(
                    index=c1_index,
                    id=node_id,
                    document=node
                )

            return node_id
        except Exception as e:
            return None

    async def index_entities(
        self,
        entities: Dict[str, List],
        project_id: str,  # REQUIRED - CYMONIDES MANDATE
        source_url: str = None,
    ) -> Dict[str, List[str]]:
        """
        Index multiple entities to CYMONIDES-1-{project_id}.

        CYMONIDES MANDATE: project_id is REQUIRED.

        Args:
            entities: {"persons": [...], "companies": [...], "emails": [...], ...}
            project_id: Project ID (REQUIRED)
            source_url: Source URL where entities were found

        Returns:
            Dict of entity type → list of indexed node IDs
        """
        await self._ensure_connected()

        # CYMONIDES MANDATE: Validate project_id
        get_c1_index(project_id)  # Will raise if invalid

        indexed = {}

        # Map entity keys to types
        type_map = {
            "persons": "person",
            "companies": "company",
            "organizations": "organization",
            "emails": "email",
            "phones": "phone",
            "addresses": "address",
            "crypto_wallets": "crypto",
        }

        for key, values in entities.items():
            entity_type = type_map.get(key, key.rstrip('s'))  # Remove plural
            indexed[key] = []

            for value in values:
                if isinstance(value, dict):
                    value = value.get("value", str(value))

                if not value or len(str(value)) < 2:
                    continue

                node_id = await self.index_entity(
                    value=str(value),
                    entity_type=entity_type,
                    project_id=project_id,  # REQUIRED
                    source_url=source_url,
                )
                if node_id:
                    indexed[key].append(node_id)

        return indexed

    # =========================================================================
    # COMBINED: INDEX EVERYTHING
    # =========================================================================

    async def index_scrape_result(
        self,
        url: str,
        content: str,
        project_id: str,  # REQUIRED - CYMONIDES MANDATE
        title: str = None,
        entities: Dict[str, List] = None,
        outlinks: List[str] = None,
        archive_url: str = None,
        timestamp: str = None,
        source: str = "linklater",
        query: str = None,
    ) -> Dict[str, Any]:
        """
        Index a complete scrape result to BOTH CYMONIDES-1 and CYMONIDES-2.

        CYMONIDES MANDATE: project_id is REQUIRED for C-1 operations.

        This is the main method to call after any LINKLATER operation.

        Args:
            url: Source URL
            content: Scraped content
            project_id: Project ID (REQUIRED)
            title: Page title
            entities: Extracted entities
            outlinks: Outbound links
            archive_url: Archive URL if historical
            timestamp: Archive timestamp
            source: Source identifier
            query: Original query

        Returns:
            {
                "c2_doc_id": "...",
                "c1_node_ids": {"persons": [...], "companies": [...], ...},
                "indexed_at": "..."
            }
        """
        await self._ensure_connected()

        result = {
            "c2_doc_id": None,
            "c1_node_ids": {},
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }

        # 1. Index content to CYMONIDES-2 (global corpus)
        c2_id = await self.index_content(
            url=url,
            content=content,
            title=title,
            entities=entities,
            outlinks=outlinks,
            archive_url=archive_url,
            timestamp=timestamp,
            source=source,
            project_id=project_id,
            query=query,
        )
        result["c2_doc_id"] = c2_id

        # 2. Index entities to CYMONIDES-1-{project_id}
        if entities:
            c1_ids = await self.index_entities(
                entities=entities,
                project_id=project_id,  # REQUIRED
                source_url=archive_url or url,
            )
            result["c1_node_ids"] = c1_ids

        return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_default_indexer: Optional[CymonidesIndexer] = None

async def get_indexer() -> CymonidesIndexer:
    """Get or create default indexer."""
    global _default_indexer
    if _default_indexer is None:
        _default_indexer = CymonidesIndexer()
        await _default_indexer.connect()
    return _default_indexer


async def push_to_c2(
    url: str,
    content: str,
    title: str = None,
    entities: Dict[str, List] = None,
    archive_url: str = None,
    **kwargs
) -> Optional[str]:
    """
    Push content to C-2 (convenience function).

    Usage:
        doc_id = await push_to_c2(url="...", content="...", title="...")
    """
    indexer = await get_indexer()
    return await indexer.index_content(
        url=url,
        content=content,
        title=title,
        entities=entities,
        archive_url=archive_url,
        **kwargs
    )


async def push_to_c1(
    entities: Dict[str, List],
    project_id: str,  # REQUIRED - CYMONIDES MANDATE
    source_url: str = None,
) -> Dict[str, List[str]]:
    """
    Push entities to CYMONIDES-1-{project_id} (convenience function).

    CYMONIDES MANDATE: project_id is REQUIRED.

    Usage:
        node_ids = await push_to_c1(
            entities={"persons": ["John Smith"], "companies": ["ACME"]},
            project_id="my-project",
            source_url="https://example.com"
        )
    """
    indexer = await get_indexer()
    return await indexer.index_entities(
        entities=entities,
        project_id=project_id,  # REQUIRED
        source_url=source_url,
    )


async def index_linklater_result(
    url: str,
    content: str,
    project_id: str,  # REQUIRED - CYMONIDES MANDATE
    title: str = None,
    entities: Dict[str, List] = None,
    outlinks: List[str] = None,
    archive_url: str = None,
    timestamp: str = None,
    source: str = "linklater",
    query: str = None,
) -> Dict[str, Any]:
    """
    Index complete LINKLATER result to CYMONIDES-1 and CYMONIDES-2 (convenience function).

    CYMONIDES MANDATE: project_id is REQUIRED.

    This should be called from QueryExecutor after every operation.

    Usage:
        result = await index_linklater_result(
            url="https://example.com",
            content="...",
            project_id="my-project",
            entities={"persons": [...], ...}
        )
    """
    indexer = await get_indexer()
    return await indexer.index_scrape_result(
        url=url,
        content=content,
        project_id=project_id,  # REQUIRED
        title=title,
        entities=entities,
        outlinks=outlinks,
        archive_url=archive_url,
        timestamp=timestamp,
        source=source,
        query=query,
    )


async def query_c2(
    query: str,
    domain: str = None,
    years: List[int] = None,
    limit: int = 100,
    **kwargs
) -> List[Dict]:
    """
    Query C-2 (linklater_corpus) for content.

    Args:
        query: Search query
        domain: Filter by domain (optional)
        years: Filter by years (optional)
        limit: Max results

    Returns:
        List of matching documents
    """
    indexer = await get_indexer()
    await indexer._ensure_connected()

    # Build ES query
    must = [{"match": {"content": query}}]

    if domain:
        must.append({"term": {"domain": domain}})

    if years:
        should_year = [{"range": {"timestamp": {"gte": f"{y}-01-01", "lte": f"{y}-12-31"}}} for y in years]
        must.append({"bool": {"should": should_year, "minimum_should_match": 1}})

    try:
        response = await indexer._es.search(
            index=indexer.c2_index,
            body={
                "query": {"bool": {"must": must}},
                "size": limit,
                "_source": ["url", "title", "domain", "content", "entities", "archive_url", "timestamp", "source"]
            }
        )

        return [hit["_source"] for hit in response["hits"]["hits"]]
    except Exception:
        return []


__all__ = [
    "CymonidesIndexer",
    "get_c1_index",  # CYMONIDES MANDATE: Use this to get per-project index name
    "C2_INDEX",      # Global corpus index
    "push_to_c2",
    "push_to_c1",
    "index_linklater_result",
    "query_c2",
    "normalize_value",
    "generate_deterministic_id",
]
