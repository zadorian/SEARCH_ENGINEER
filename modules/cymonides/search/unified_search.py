"""
CYMONIDES Unified Search Layer

CYMONIDES 3-TIER ARCHITECTURE:
- C-1: Project nodes (search_nodes) - Investigation entities, relationships
- C-2: Website content (submarine-scrapes) - Scraped page content, extracted entities
- C-3: Domain graph (cymonides_cc_domain_edges) - Domain link structure from CommonCrawl

ADDITIONAL INDICES (not Cymonides tiers):
- breach_records: Breach/leak data (2.69B records)
- persons_unified: Person records from multiple sources
- domains_unified: Domain metadata and rankings
- companies_unified: Company registry data
- voters_unified: Voter registration data
- emails_unified: Email-to-entity mappings
- phones_unified: Phone-to-entity mappings
- linkedin_unified: LinkedIn profile data

Provides standardized search with canonical field names:
- domain (+url)
- email
- username
- real_name
- phone
- password
- location
- timestamp

Translates canonical fields to index-specific fields and aggregates results.
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from elasticsearch import Elasticsearch
import os
import logging

logger = logging.getLogger(__name__)

# Cymonides tier indices
CYMONIDES_C1 = "search_nodes"           # Project entities
CYMONIDES_C2 = "submarine-scrapes"       # Website content
CYMONIDES_C3 = "cymonides_cc_domain_edges"  # Domain graph (edges only)

# Canonical field mappings per index
FIELD_MAPPINGS = {
    # === CYMONIDES TIERS ===
    "search_nodes": {  # C-1: Project nodes
        "domain": [],
        "url": ["source_url"],
        "email": [],  # In metadata if extracted
        "username": [],
        "real_name": ["name", "name_normalized"],
        "phone": [],
        "password": [],
        "location": [],
        "timestamp": ["indexed_at", "statement_date"],
        "ip": [],
        "_meta": {
            "tier": "C-1",
            "description": "Project investigation entities",
            "searchable_fields": ["name", "name_normalized", "entity_type", "subject", "concepts"]
        }
    },
    "submarine-scrapes": {  # C-2: Website content
        "domain": ["domain"],
        "url": ["url", "input_url"],
        "email": [],  # In entities.emails
        "username": [],
        "real_name": ["persons", "companies"],
        "phone": [],  # In entities.phones
        "password": [],
        "location": [],
        "timestamp": ["crawled_at", "scraped_at"],
        "ip": ["scraper_ip"],
        "_nested_entities": {
            "email": "entities.emails",
            "phone": "entities.phones",
        },
        "_meta": {
            "tier": "C-2",
            "description": "Scraped website content with extracted entities",
            "searchable_fields": ["domain", "url", "content", "text", "title", "persons", "companies"]
        }
    },
    # C-3 (cymonides_cc_domain_edges) is graph structure only - not field-searchable

    # === BREACH DATA ===
    "breach_records": {
        "domain": ["email_domain"],
        "url": [],
        "email": ["email"],
        "username": ["username", "am_username"],
        "real_name": ["first_name", "last_name", "name"],
        "phone": ["phone"],
        "password": ["password", "password_hash", "encrypted_password"],
        "location": ["address", "address1", "address2", "city", "state", "country", "zip"],
        "timestamp": ["record_date", "registration_date", "birth_date"],
        "ip": ["ip_address"],
    },
    "persons_unified": {
        "domain": ["domain", "employer_domains"],
        "url": ["linkedin_url", "image_url"],
        "email": ["email", "emails", "email_ids"],
        "username": [],
        "real_name": ["canonical_name", "full_name", "name", "first_name", "last_name", "given_name", "family_name"],
        "phone": [],  # Only has has_phone_exposed flag
        "password": [],
        "location": ["address", "addresses", "address_locality", "countries", "citizenship"],
        "timestamp": ["last_updated", "birth_date"],
        "ip": [],
    },
    "domains_unified": {
        "domain": ["domain"],
        "url": ["url", "website_url", "search_url", "linkedin_url"],
        "email": [],
        "username": [],
        "real_name": ["company_name", "company_names", "wdc_entity_names"],
        "phone": [],
        "password": [],
        "location": ["city", "country", "company_city", "company_country", "primary_country"],
        "timestamp": ["last_updated"],
        "ip": [],
    },
    "companies_unified": {
        "domain": [],
        "url": [],
        "email": [],
        "username": [],
        "real_name": ["company_name", "canonical_name", "alternate_names", "alternative_names"],
        "phone": [],
        "password": [],
        "location": ["address", "addresses", "city", "country", "countries", "county"],
        "timestamp": ["created_at", "compliance_updated_at"],
        "ip": [],
    },
    # Note: submarine-scrapes is defined above as C-2
    "voters_unified": {
        "domain": [],
        "url": [],
        "email": ["email"],
        "username": [],
        "real_name": ["first_name", "last_name", "middle_name", "full_name"],
        "phone": ["phone"],
        "password": [],
        "location": ["address", "city", "state", "county", "zip"],
        "timestamp": ["registration_date", "last_voted"],
        "ip": [],
    },
    "emails_unified": {
        "domain": ["domain"],
        "url": [],
        "email": ["email"],
        "username": [],
        "real_name": ["name", "owner_name"],
        "phone": [],
        "password": [],
        "location": [],
        "timestamp": ["created_at", "last_seen"],
        "ip": [],
    },
    "phones_unified": {
        "domain": [],
        "url": [],
        "email": [],
        "username": [],
        "real_name": ["name", "owner_name"],
        "phone": ["phone", "phone_number"],
        "password": [],
        "location": ["city", "state", "country", "carrier"],
        "timestamp": ["created_at", "last_seen"],
        "ip": [],
    },
    "linkedin_unified": {
        "domain": [],
        "url": ["linkedin_url", "profile_url"],
        "email": ["email"],
        "username": ["linkedin_id", "username"],
        "real_name": ["full_name", "first_name", "last_name", "name"],
        "phone": [],
        "password": [],
        "location": ["location", "city", "country"],
        "timestamp": ["last_updated", "scraped_at"],
        "ip": [],
    },
}

# Cymonides tier groupings
CYMONIDES_TIERS = {
    "C-1": "search_nodes",        # Project entities
    "C-2": "submarine-scrapes",   # Website content
    "C-3": "cymonides_cc_domain_edges",  # Domain graph (edges only, not field-searchable)
}

# Default indices to search (excludes C-3 graph edges)
DEFAULT_INDICES = [
    # Cymonides C-1 and C-2
    "search_nodes",
    "submarine-scrapes",
    # Core unified indices
    "breach_records",
    "persons_unified",
    "domains_unified",
    "companies_unified",
]

# Extended indices (all searchable)
EXTENDED_INDICES = DEFAULT_INDICES + [
    "voters_unified",
    "emails_unified",
    "phones_unified",
    "linkedin_unified",
]

# All available indices with field mappings
ALL_INDICES = list(FIELD_MAPPINGS.keys())


@dataclass
class UnifiedSearchResult:
    """Normalized search result"""
    source_index: str
    score: float
    # Canonical fields
    domain: Optional[str] = None
    url: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    real_name: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    location: Optional[str] = None
    timestamp: Optional[str] = None
    ip: Optional[str] = None
    # Raw source for additional fields
    raw: Dict[str, Any] = field(default_factory=dict)


class UnifiedSearch:
    """
    Unified search across all Cymonides indices.

    Translates canonical field names to index-specific fields,
    queries multiple indices, and normalizes results.
    """

    def __init__(
        self,
        es_host: str = None,
        indices: List[str] = None,
    ):
        """
        Initialize unified search.

        Args:
            es_host: Elasticsearch host (default: sastre server)
            indices: List of indices to search (default: DEFAULT_INDICES)
        """
        # Default to localhost (assumes SSH tunnel to sastre: ssh -L 9200:localhost:9200 root@176.9.2.153)
        self.es_host = es_host or os.getenv("ES_HOST", "http://localhost:9200")
        self.es = Elasticsearch([self.es_host])
        self.indices = indices or DEFAULT_INDICES

    def _build_field_query(
        self,
        canonical_field: str,
        value: str,
        index: str,
        match_type: str = "match"
    ) -> Optional[Dict]:
        """
        Build ES query clause for a canonical field on a specific index.

        Args:
            canonical_field: Canonical field name (email, domain, etc.)
            value: Value to search for
            index: Target index name
            match_type: "match", "term", "wildcard", "prefix"

        Returns:
            ES query clause or None if field not available
        """
        if index not in FIELD_MAPPINGS:
            return None

        mapping = FIELD_MAPPINGS[index]
        fields = mapping.get(canonical_field, [])

        if not fields:
            # Check nested entities for submarine-scrapes
            if "_nested_entities" in mapping:
                nested_field = mapping["_nested_entities"].get(canonical_field)
                if nested_field:
                    fields = [nested_field]

        if not fields:
            return None

        # Build multi_match for multiple possible fields
        if match_type == "match":
            return {
                "multi_match": {
                    "query": value,
                    "fields": fields,
                    "type": "best_fields"
                }
            }
        elif match_type == "term":
            # Use should clause for multiple fields
            return {
                "bool": {
                    "should": [{"term": {f: value}} for f in fields],
                    "minimum_should_match": 1
                }
            }
        elif match_type == "wildcard":
            return {
                "bool": {
                    "should": [{"wildcard": {f: f"*{value}*"}} for f in fields],
                    "minimum_should_match": 1
                }
            }
        elif match_type == "prefix":
            return {
                "bool": {
                    "should": [{"prefix": {f: value}} for f in fields],
                    "minimum_should_match": 1
                }
            }

        return None

    def _normalize_result(
        self,
        hit: Dict,
        index: str
    ) -> UnifiedSearchResult:
        """
        Normalize an ES hit to UnifiedSearchResult.

        Args:
            hit: ES search hit
            index: Source index name

        Returns:
            Normalized result
        """
        source = hit.get("_source", {})
        mapping = FIELD_MAPPINGS.get(index, {})

        def get_first(fields: List[str]) -> Optional[str]:
            """Get first non-null value from field list"""
            for f in fields:
                if "." in f:
                    # Handle nested fields
                    parts = f.split(".")
                    val = source
                    for p in parts:
                        if isinstance(val, dict):
                            val = val.get(p)
                        else:
                            val = None
                            break
                    if val:
                        if isinstance(val, list):
                            return val[0] if val else None
                        return str(val)
                else:
                    val = source.get(f)
                    if val:
                        if isinstance(val, list):
                            return val[0] if val else None
                        return str(val)
            return None

        def build_name() -> Optional[str]:
            """Build full name from parts if needed"""
            fields = mapping.get("real_name", [])
            # Try canonical/full name first
            for f in ["canonical_name", "full_name", "name", "company_name"]:
                if f in fields:
                    val = source.get(f)
                    if val:
                        return str(val)
            # Build from parts
            first = source.get("first_name", "")
            last = source.get("last_name", "")
            if first or last:
                return f"{first} {last}".strip()
            return get_first(fields)

        def build_location() -> Optional[str]:
            """Build location string from parts"""
            parts = []
            for f in ["address", "city", "state", "country"]:
                val = source.get(f)
                if val:
                    parts.append(str(val))
            return ", ".join(parts) if parts else get_first(mapping.get("location", []))

        return UnifiedSearchResult(
            source_index=index,
            score=hit.get("_score", 0.0),
            domain=get_first(mapping.get("domain", [])),
            url=get_first(mapping.get("url", [])),
            email=get_first(mapping.get("email", [])),
            username=get_first(mapping.get("username", [])),
            real_name=build_name(),
            phone=get_first(mapping.get("phone", [])),
            password=get_first(mapping.get("password", [])),
            location=build_location(),
            timestamp=get_first(mapping.get("timestamp", [])),
            ip=get_first(mapping.get("ip", [])),
            raw=source,
        )

    def search(
        self,
        query: str = None,
        *,
        domain: str = None,
        url: str = None,
        email: str = None,
        username: str = None,
        real_name: str = None,
        phone: str = None,
        password: str = None,
        location: str = None,
        ip: str = None,
        indices: List[str] = None,
        size: int = 100,
        match_type: str = "match",
    ) -> List[UnifiedSearchResult]:
        """
        Search across indices with canonical field names.

        Args:
            query: Free-text query (searches all text fields)
            domain: Domain to search
            url: URL to search
            email: Email to search
            username: Username to search
            real_name: Name to search
            phone: Phone to search
            password: Password/hash to search
            location: Location to search
            ip: IP address to search
            indices: Indices to search (default: self.indices)
            size: Max results per index
            match_type: "match", "term", "wildcard", "prefix"

        Returns:
            List of normalized results sorted by score
        """
        target_indices = indices or self.indices
        all_results = []

        # Keyword fields use term matching, text fields use match
        KEYWORD_FIELDS = {"domain", "url", "email", "username", "phone", "password", "ip"}
        TEXT_FIELDS = {"real_name", "location"}

        def get_match_type(field_name: str) -> str:
            if match_type != "match":
                return match_type  # Use explicit override
            return "term" if field_name in KEYWORD_FIELDS else "match"

        # Build field-specific queries
        field_queries = {}
        if domain:
            field_queries["domain"] = domain
        if url:
            field_queries["url"] = url
        if email:
            field_queries["email"] = email
        if username:
            field_queries["username"] = username
        if real_name:
            field_queries["real_name"] = real_name
        if phone:
            field_queries["phone"] = phone
        if password:
            field_queries["password"] = password
        if location:
            field_queries["location"] = location
        if ip:
            field_queries["ip"] = ip

        for index in target_indices:
            if index not in FIELD_MAPPINGS:
                logger.warning(f"Unknown index: {index}")
                continue

            # Build query for this index
            must_clauses = []

            # Add field-specific queries with smart match type
            for field_name, value in field_queries.items():
                effective_match_type = get_match_type(field_name)
                clause = self._build_field_query(field_name, value, index, effective_match_type)
                if clause:
                    must_clauses.append(clause)

            # Add free-text query
            if query:
                # Search all text fields
                all_fields = []
                for field_list in FIELD_MAPPINGS[index].values():
                    if isinstance(field_list, list):
                        all_fields.extend(field_list)
                if all_fields:
                    must_clauses.append({
                        "multi_match": {
                            "query": query,
                            "fields": all_fields,
                            "type": "best_fields"
                        }
                    })

            if not must_clauses:
                continue

            # Build final query
            es_query = {
                "query": {
                    "bool": {
                        "must": must_clauses
                    }
                },
                "size": size
            }

            # Exclude corrupted fields for breach_records
            if index == "breach_records":
                es_query["query"]["bool"]["must"].append({
                    "exists": {"field": "email"}
                })

            try:
                response = self.es.search(index=index, body=es_query)
                hits = response.get("hits", {}).get("hits", [])

                for hit in hits:
                    result = self._normalize_result(hit, index)
                    all_results.append(result)

            except Exception as e:
                logger.error(f"Error searching {index}: {e}")
                continue

        # Sort by score
        all_results.sort(key=lambda r: r.score, reverse=True)

        return all_results

    def search_email(self, email: str, **kwargs) -> List[UnifiedSearchResult]:
        """Search by email across all indices"""
        return self.search(email=email, **kwargs)

    def search_domain(self, domain: str, **kwargs) -> List[UnifiedSearchResult]:
        """Search by domain across all indices"""
        return self.search(domain=domain, **kwargs)

    def search_phone(self, phone: str, **kwargs) -> List[UnifiedSearchResult]:
        """Search by phone across all indices"""
        return self.search(phone=phone, **kwargs)

    def search_name(self, name: str, **kwargs) -> List[UnifiedSearchResult]:
        """Search by name across all indices"""
        return self.search(real_name=name, **kwargs)

    def search_username(self, username: str, **kwargs) -> List[UnifiedSearchResult]:
        """Search by username across all indices"""
        return self.search(username=username, **kwargs)

    def get_index_stats(self) -> Dict[str, int]:
        """Get document counts for all indices"""
        stats = {}
        for index in ALL_INDICES:
            try:
                response = self.es.count(index=index)
                stats[index] = response.get("count", 0)
            except Exception:
                stats[index] = -1  # Index doesn't exist or error
        return stats


# Convenience function
def unified_search(
    query: str = None,
    **kwargs
) -> List[UnifiedSearchResult]:
    """
    Quick unified search across all default indices.

    Args:
        query: Free-text query
        **kwargs: Field-specific queries (email=, domain=, phone=, etc.)

    Returns:
        List of normalized results
    """
    searcher = UnifiedSearch()
    return searcher.search(query=query, **kwargs)


if __name__ == "__main__":
    # Test
    import sys

    searcher = UnifiedSearch()

    # Print stats
    print("Index Stats:")
    stats = searcher.get_index_stats()
    for idx, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {idx}: {count:,}")

    # Test search if query provided
    if len(sys.argv) > 1:
        q = sys.argv[1]
        print(f"\nSearching for: {q}")

        # Detect query type
        if "@" in q:
            results = searcher.search_email(q, size=10)
        elif "." in q and "/" not in q:
            results = searcher.search_domain(q, size=10)
        elif q.replace("+", "").replace("-", "").replace(" ", "").isdigit():
            results = searcher.search_phone(q, size=10)
        else:
            results = searcher.search_name(q, size=10)

        print(f"\nFound {len(results)} results:")
        for r in results[:5]:
            print(f"  [{r.source_index}] {r.email or r.domain or r.real_name} (score: {r.score:.2f})")
