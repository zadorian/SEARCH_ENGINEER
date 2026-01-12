"""
CYMONIDES Unified Search

Single search interface across ALL Elasticsearch indices.
Used when "ALL" is selected in CYMONIDES-SEARCH frontend.

Operators supported:
- Definitional: "[German car manufacturer]"
- Keywords: "fintech startup"
- Filters: "category:news country:DE"

LOCATION FILTERS:
- fr! = SHORTHAND for (lang{fr}! OR geo{fr}! OR dom{fr}!) - matches ANY
- dom{fr}! = DOMAIN TLD ONLY (.fr domains)
- lang{fr}! = LANGUAGE ONLY (French content)
- geo{fr}! = GEOGRAPHIC ONLY (France-based entities)

- Rank: "rank(<1000)" "rank(>10000)"
- Authority: "authority(high)" "authority(medium)" "authority(low)"
- Proximity: '"word1 word2"~3' (words within N positions)
- Fuzzy: "word~2" (edit distance N, max 2)
- Boolean: "term1 AND term2", "term1 OR term2"
- NOT/Exclude: "-term" or "NOT term"
- Entity extraction: "@ent?" "@p?" "@c?" "@e?"
- PDF corpus: "pdf!" searches finepdfs-corporate
"""

import re
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging
import os

from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

# Elasticsearch connection
ES_HOST = os.getenv('ELASTICSEARCH_URL', 'http://localhost:9200')


@dataclass
class CymonidesResult:
    """Standard result format for CYMONIDES queries"""
    query: Dict[str, Any]
    total: int
    results: List[Dict[str, Any]]
    sources_queried: List[str]
    timing_ms: Optional[float] = None


# Authority level definitions (based on tranco_rank)
AUTHORITY_LEVELS = {
    "high": {"max": 1000},      # Top 1K authority
    "medium": {"min": 1001, "max": 50000},
    "low": {"min": 50001}       # Long tail
}


class CymonidesUnifiedSearch:
    """
    Unified search across ALL CYMONIDES Elasticsearch indices.

    This is the "ALL" mode for CYMONIDES-SEARCH frontend.

    Supports all operators from operators.json with engine: "cymonides"

    Usage:
        search = CymonidesUnifiedSearch()
        results = search.search("[German car manufacturer]", limit=100)
        results = search.search("[finance] de! rank(<1000)", limit=50)
        results = search.search_entities("ent:company:Acme", limit=50)
    """

    # === REGEX PATTERNS (from operators.json) ===

    # Definitional: [category]
    DEFINITIONAL_PATTERN = re.compile(r'\[([^\]]+)\]')

    # Filters: key:value
    FILTER_PATTERN = re.compile(r'(\w+):(\S+)')

    # Rank: rank(<1000) or rank(>10000)
    RANK_PATTERN = re.compile(r'rank\(([<>])(\d+)\)')

    # Authority: authority(high|medium|low)
    AUTHORITY_PATTERN = re.compile(r'authority\((high|medium|low)\)', re.IGNORECASE)

    # LOCATION SHORTHAND: fr! = (lang{fr}! OR geo{fr}! OR dom{fr}!) - matches ANY
    LOCATION_SHORTHAND_PATTERN = re.compile(r'\b(de|uk|us|fr|nl|at|ch|be|it|es|pl|cz|hu|hr|sk|si|ro|bg|se|no|fi|dk|ie|pt|gr|gov|edu|org|com|net)!')

    # SPECIFIC FILTERS (narrow down to just one):
    # dom{fr}! = domain TLD only (.fr domains)
    DOM_BANG_PATTERN = re.compile(r'dom\{(\w{2,3})\}!', re.IGNORECASE)

    # lang{fr}! = language only (French content)
    LANG_BANG_PATTERN = re.compile(r'lang\{(\w{2})\}!', re.IGNORECASE)

    # geo{fr}! = geographic only (France-based entities)
    GEO_BANG_PATTERN = re.compile(r'geo\{(\w{2})\}!', re.IGNORECASE)

    # Advanced text search
    PROXIMITY_PATTERN = re.compile(r'"([^"]+)"~(\d+)')  # "word1 word2"~3
    FUZZY_PATTERN = re.compile(r'(\w+)~(\d)')           # word~2
    NOT_PATTERN = re.compile(r'(?:^|\s)-(\w+)')         # -term
    NOT_KEYWORD_PATTERN = re.compile(r'\bNOT\s+(\w+)', re.IGNORECASE)  # NOT term
    AND_PATTERN = re.compile(r'(\w+)\s+AND\s+(\w+)', re.IGNORECASE)
    OR_PATTERN = re.compile(r'(\w+)\s+OR\s+(\w+)', re.IGNORECASE)

    # Entity extraction operators (from operators.json category: entity_extraction)
    # @ent? @p? @c? @e? @t? @a? @u?
    ENTITY_EXTRACT_PATTERN = re.compile(r'@(ent|p|c|e|t|a|u)\?')

    # PDF filetype operator: pdf!
    PDF_PATTERN = re.compile(r'\bpdf!')

    # === JURISDICTION OPERATORS (from operators.json) ===
    # Company labels: cuk:, cde:, chr:, chu:, cno:, cfi:, cch:, cie:, ccz:, cbe:
    # Person labels: puk:, pde:
    # Phone labels: tuk:
    # Execution: :cuk!, :cruk!, :cde!, :crde!, :chr!, :chu!, :cno!, :cfi!, :cch!, :cie!, :ccz!, :cbe!
    # Registry: :reguk!
    # Litigation: :lituk!
    JURISDICTION_LABEL_PATTERN = re.compile(r'\b(c|p|t)(uk|de|hr|hu|no|fi|ch|ie|cz|be|us|fr|nl|at|es|pl|it):', re.IGNORECASE)
    JURISDICTION_EXEC_PATTERN = re.compile(r':(c|cr|p|reg|lit)(uk|de|hr|hu|no|fi|ch|ie|cz|be|us|fr|nl|at|es|pl|it)!', re.IGNORECASE)

    # === TEMPORAL OPERATORS (from operators.json) ===
    # YYYY! single year (e.g., 2024!) - open web filter
    YEAR_BANG_PATTERN = re.compile(r'\b(\d{4})!')
    # YYYY-YYYY! year range (e.g., 2020-2024!) - open web filter
    YEAR_RANGE_BANG_PATTERN = re.compile(r'\b(\d{4})-(\d{4})!')
    # <- YYYY! before year (e.g., <- 2023!)
    YEAR_BEFORE_PATTERN = re.compile(r'<-\s*(\d{4})!')
    # YYYY ->! after year (e.g., 2020 ->!)
    YEAR_AFTER_PATTERN = re.compile(r'(\d{4})\s*->!')
    # :YYYY! archive single year
    ARCHIVE_YEAR_PATTERN = re.compile(r':(\d{4})!')
    # :YYYY-YYYY! archive year range
    ARCHIVE_YEAR_RANGE_PATTERN = re.compile(r':(\d{4})-(\d{4})!')
    # :<-YYYY! archive back to year
    ARCHIVE_BACK_PATTERN = re.compile(r':<-(\d{4})!')
    # :<-! all historical
    ALL_HISTORICAL_PATTERN = re.compile(r':<-!')

    # === INDEX GROUPS ===

    # Primary domain indices (570M+ domains)
    DOMAIN_INDICES = [
        "atlas",              # 155M - authority, categories, company data
        "domains_unified",    # 180M - WDC company enrichment
        "top_domains"         # 8.6M - Tranco ranked domains
    ]

    # Extended domain sources
    EXTENDED_DOMAIN_INDICES = [
        "atlas",
        "domains_unified",
        "top_domains",
        "cymonides_cc_domain_vertices",  # 100M - CC graph data
        "unified_domain_profiles",        # 5.8M - consolidated profiles
        "wdc-domain-profiles"             # 247K - WDC extractions
    ]

    # Entity indices
    ENTITY_INDICES = [
        "companies_unified",      # 14.9M companies
        "persons_unified",        # 6.3M persons
        "linkedin_unified",       # 2.8M LinkedIn profiles
        "wdc-organization-entities",  # 9.6M orgs
        "wdc-person-entities",    # 6.8M persons
        "emails_unified",         # emails
        "phones_unified",         # phones
    ]

    # PDF corpus
    PDF_INDICES = [
        "finepdfs-corporate"      # 1.75M PDFs with nested entities
    ]

    # C-2: Search results content corpus (scraped web pages, snippets)
    CONTENT_INDICES = [
        "cymonides-2"             # 150K+ scraped web pages from brute searches
    ]

    # C-3: Consolidated corpus alias (528M+ docs)
    # Alias for: atlas, domains_unified, top_domains, companies_unified,
    #            persons_unified, cymonides_cc_domain_vertices, cymonides_cc_domain_edges
    CORPUS_ALIAS = "cymonides-3"

    # ALL indices for unified search
    ALL_INDICES = DOMAIN_INDICES + ENTITY_INDICES + PDF_INDICES + CONTENT_INDICES

    # Corpus-first search (local knowledge before external)
    CORPUS_INDICES = [CORPUS_ALIAS, "cymonides-2"]

    # Entity operator to type mapping (from operators.json)
    ENTITY_OPERATOR_MAP = {
        "ent": "any",           # @ent? = all entities
        "p": "person",          # @p? = persons
        "c": "company",         # @c? = companies
        "e": "email",           # @e? = emails
        "t": "phone",           # @t? = phones (telephone)
        "a": "address",         # @a? = addresses
        "u": "social:",         # @u? = usernames (prefix match for social:*)
    }

    def __init__(self, es: Elasticsearch = None):
        self.es = es or Elasticsearch(
            [ES_HOST],
            timeout=30,  # 30 second timeout for queries
            retry_on_timeout=True
        )

    def _map_entity_operator(self, operator: str) -> str:
        """Map operator letter to entity type."""
        return self.ENTITY_OPERATOR_MAP.get(operator, "any")

    def search(
        self,
        query: str,
        limit: int = 100,
        indices: List[str] = None
    ) -> CymonidesResult:
        """
        Unified search across all CYMONIDES indices.

        Args:
            query: Search query with operators
            limit: Maximum results
            indices: Specific indices (default: ALL)

        Returns:
            CymonidesResult with matching records
        """
        start_time = time.time()

        # Parse query
        parsed = self._parse_query(query)

        # Handle entity extraction operators (@ent?, @p?, @c?, @e?, @t?, @a?, @u?)
        if parsed.get("entity_extract"):
            entity_type = self._map_entity_operator(parsed["entity_extract"])
            # Remaining keywords become the value search
            entity_value = " ".join(parsed.get("keywords", []))
            return self.search_entities(entity_type, entity_value, limit)

        # Determine indices based on query
        if indices:
            indices_to_query = indices
        elif parsed.get("pdf_search"):
            indices_to_query = self.PDF_INDICES
        else:
            indices_to_query = self.DOMAIN_INDICES

        # Build and execute query
        results = self._execute_search(parsed, indices_to_query, limit)

        timing = (time.time() - start_time) * 1000

        return CymonidesResult(
            query=parsed,
            total=len(results),
            results=results[:limit],
            sources_queried=indices_to_query,
            timing_ms=round(timing, 2)
        )

    # Entity type to indices mapping
    # Format: (index_name, name_field, schema_type_filter)
    ENTITY_TYPE_INDICES = {
        "person": [
            ("wdc-person-entities", "name", "Person"),       # 6.8M persons (Schema.org)
            ("persons_unified", "full_name", None),          # 6.3M persons (breach data)
        ],
        "company": [
            ("wdc-organization-entities", "name", "Organization"),  # 9.6M orgs (Schema.org)
            ("companies_unified", "company_name", None),     # 14.9M companies
            ("linkedin_unified", "company_name", None),      # 2.8M LinkedIn companies
        ],
        "email": [
            ("emails_unified", "email", None),
        ],
        "phone": [
            ("phones_unified", "phone", None),
        ],
    }

    def search_entities(
        self,
        entity_type: str,
        entity_value: str,
        limit: int = 100
    ) -> CymonidesResult:
        """
        Search entities across ALL relevant indices.

        For @p? → wdc-person-entities, persons_unified, linkedin_unified, finepdfs-corporate
        For @c? → wdc-organization-entities, companies_unified, finepdfs-corporate
        For @e? → emails_unified, finepdfs-corporate
        For @t? → phones_unified, finepdfs-corporate
        For @ent? → All indices

        Args:
            entity_type: person, company, email, phone, or "any"
            entity_value: Search term
            limit: Maximum results

        Returns:
            CymonidesResult with matching entities from all sources
        """
        start_time = time.time()
        all_results = []
        sources_queried = []

        # Determine which indices to search
        if entity_type == "any":
            indices_to_search = []
            for type_indices in self.ENTITY_TYPE_INDICES.values():
                indices_to_search.extend(type_indices)
        else:
            indices_to_search = self.ENTITY_TYPE_INDICES.get(entity_type, [])

        # Search each WDC/unified index
        for index_name, name_field, schema_type in indices_to_search:
            try:
                results = self._search_entity_index(
                    index_name, name_field, schema_type, entity_value, limit
                )
                all_results.extend(results)
                sources_queried.append(index_name)
            except Exception as e:
                logger.warning(f"Entity search error for {index_name}: {e}")

        # Also search finepdfs-corporate (nested entities)
        try:
            pdf_results = self._search_pdf_entities(entity_type, entity_value, limit)
            all_results.extend(pdf_results)
            sources_queried.append("finepdfs-corporate")
        except Exception as e:
            logger.warning(f"PDF entity search error: {e}")

        # Deduplicate by name (case-insensitive)
        seen_names = set()
        unique_results = []
        for r in all_results:
            name_key = (r.get("name") or "").lower().strip()
            if name_key and name_key not in seen_names:
                seen_names.add(name_key)
                unique_results.append(r)

        # Sort by score
        unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        timing = (time.time() - start_time) * 1000

        return CymonidesResult(
            query={"entity_type": entity_type, "entity_value": entity_value},
            total=len(unique_results),
            results=unique_results[:limit],
            sources_queried=sources_queried,
            timing_ms=round(timing, 2)
        )

    def _search_entity_index(
        self,
        index_name: str,
        name_field: str,
        schema_type: Optional[str],
        entity_value: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Search a specific entity index (WDC or unified)."""
        must_clauses = []

        # Filter by Schema.org type if specified
        if schema_type:
            must_clauses.append({
                "bool": {
                    "should": [
                        {"term": {"type": schema_type}},
                        {"term": {"types": schema_type}},
                    ],
                    "minimum_should_match": 1
                }
            })

        # Search by name/value
        if entity_value:
            must_clauses.append({
                "bool": {
                    "should": [
                        {"match_phrase": {name_field: {"query": entity_value, "boost": 3}}},
                        {"match": {name_field: {"query": entity_value, "boost": 1}}},
                        {"wildcard": {name_field: f"*{entity_value.lower()}*"}},
                    ],
                    "minimum_should_match": 1
                }
            })

        body = {
            "query": {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}},
            "size": limit,
            "_source": True,
        }

        response = self.es.search(index=index_name, body=body, request_timeout=30)

        results = []
        for hit in response["hits"]["hits"]:
            src = hit["_source"]
            # Normalize result format
            name = src.get(name_field)
            if isinstance(name, list):
                name = name[0] if name else None

            results.append({
                "name": name,
                "type": src.get("type") or src.get("types", [None])[0] if isinstance(src.get("types"), list) else src.get("types"),
                "domain": src.get("domain"),
                "url": src.get("url", [None])[0] if isinstance(src.get("url"), list) else src.get("url"),
                "description": src.get("description", "")[:200] if src.get("description") else None,
                "sameAs": src.get("sameAs", [])[:5],  # Social links
                "source_index": index_name,
                "score": hit.get("_score", 0),
            })

        return results

    def _search_pdf_entities(
        self,
        entity_type: str,
        entity_value: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Search nested entities in finepdfs-corporate."""
        must_clauses = []

        # Type filter
        if entity_type and entity_type != "any":
            if entity_type.endswith(":") or ":" in entity_type:
                must_clauses.append({"prefix": {"entities.type": entity_type}})
            else:
                must_clauses.append({"term": {"entities.type": entity_type}})

        # Value search
        if entity_value:
            value_lower = entity_value.lower()
            must_clauses.append({
                "wildcard": {"entities.value": f"*{value_lower}*"}
            })

        body = {
            "query": {
                "nested": {
                    "path": "entities",
                    "query": {
                        "bool": {"must": must_clauses} if must_clauses else {"match_all": {}}
                    },
                    "inner_hits": {
                        "size": 10,
                        "_source": ["entities.type", "entities.value", "entities.context"]
                    }
                }
            },
            "size": limit,
            "_source": ["url", "domain", "detected_sectors"]
        }

        response = self.es.search(index="finepdfs-corporate", body=body, request_timeout=30)
        return self._parse_entity_hits(response["hits"]["hits"])

    def _parse_query(self, query: str) -> Dict[str, Any]:
        """Parse query into structured components."""
        parsed = {
            "raw": query,
            "definitional": None,
            "filters": {},
            "rank": None,
            "authority": None,
            # LOCATION FILTERS:
            # fr! = shorthand for (lang OR geo OR dom) - matches ANY
            "location_any": None,   # fr! = matches lang OR geo OR dom
            # Specific filters (narrow down to just one):
            "dom_filter": None,     # dom{fr}! = domain TLD only
            "lang_filter": None,    # lang{fr}! = language only
            "geo_filter": None,     # geo{fr}! = geographic only
            "proximity": [],
            "fuzzy": [],
            "boolean_and": [],
            "boolean_or": [],
            "exclude": [],
            "entity_extract": None,  # @ent?, @p?, @c?, etc.
            "pdf_search": False,     # pdf!
            # Jurisdiction filters (cuk:, puk:, :cuk!, etc.)
            "jurisdiction_label": None,   # cuk:, puk:, tuk:, chr:, etc.
            "jurisdiction_exec": None,    # :cuk!, :cruk!, :reguk!, :lituk!, etc.
            # Temporal filters (YYYY!, :YYYY!, etc.)
            "year": None,                 # YYYY! or {"start": 2020, "end": 2024}
            "year_before": None,          # <- YYYY!
            "year_after": None,           # YYYY ->!
            "archive_year": None,         # :YYYY!
            "archive_range": None,        # :YYYY-YYYY!
            "archive_back": None,         # :<-YYYY!
            "all_historical": False,      # :<-!
            "keywords": []
        }

        working_query = query

        # Extract definitional [...]
        match = self.DEFINITIONAL_PATTERN.search(working_query)
        if match:
            parsed["definitional"] = match.group(1).strip()
            working_query = self.DEFINITIONAL_PATTERN.sub("", working_query)

        # Extract entity extraction: @ent?, @p?, @c?, etc.
        ent_match = self.ENTITY_EXTRACT_PATTERN.search(working_query)
        if ent_match:
            parsed["entity_extract"] = ent_match.group(1)
            working_query = self.ENTITY_EXTRACT_PATTERN.sub("", working_query)

        # Extract pdf!
        if self.PDF_PATTERN.search(working_query):
            parsed["pdf_search"] = True
            working_query = self.PDF_PATTERN.sub("", working_query)

        # === JURISDICTION EXTRACTION (from operators.json) ===

        # Extract jurisdiction labels: cuk:, puk:, tuk:, chr:, etc.
        jur_label_match = self.JURISDICTION_LABEL_PATTERN.search(working_query)
        if jur_label_match:
            entity_type = jur_label_match.group(1).lower()  # c, p, t
            country = jur_label_match.group(2).lower()      # uk, de, hr, etc.
            parsed["jurisdiction_label"] = {"type": entity_type, "country": country}
            working_query = self.JURISDICTION_LABEL_PATTERN.sub("", working_query)

        # Extract jurisdiction execution: :cuk!, :cruk!, :reguk!, :lituk!, etc.
        jur_exec_match = self.JURISDICTION_EXEC_PATTERN.search(working_query)
        if jur_exec_match:
            op_type = jur_exec_match.group(1).lower()   # c, cr, p, reg, lit
            country = jur_exec_match.group(2).lower()   # uk, de, hr, etc.
            parsed["jurisdiction_exec"] = {"op": op_type, "country": country}
            working_query = self.JURISDICTION_EXEC_PATTERN.sub("", working_query)

        # === TEMPORAL EXTRACTION (from operators.json) ===

        # Extract :<-! (all historical) first
        if self.ALL_HISTORICAL_PATTERN.search(working_query):
            parsed["all_historical"] = True
            working_query = self.ALL_HISTORICAL_PATTERN.sub("", working_query)

        # Extract :<-YYYY! (archive back to year)
        archive_back_match = self.ARCHIVE_BACK_PATTERN.search(working_query)
        if archive_back_match:
            parsed["archive_back"] = int(archive_back_match.group(1))
            working_query = self.ARCHIVE_BACK_PATTERN.sub("", working_query)

        # Extract :YYYY-YYYY! (archive year range)
        archive_range_match = self.ARCHIVE_YEAR_RANGE_PATTERN.search(working_query)
        if archive_range_match:
            parsed["archive_range"] = {
                "start": int(archive_range_match.group(1)),
                "end": int(archive_range_match.group(2))
            }
            working_query = self.ARCHIVE_YEAR_RANGE_PATTERN.sub("", working_query)

        # Extract :YYYY! (archive single year)
        archive_year_match = self.ARCHIVE_YEAR_PATTERN.search(working_query)
        if archive_year_match and not parsed.get("archive_range"):
            parsed["archive_year"] = int(archive_year_match.group(1))
            working_query = self.ARCHIVE_YEAR_PATTERN.sub("", working_query)

        # Extract <- YYYY! (before year)
        year_before_match = self.YEAR_BEFORE_PATTERN.search(working_query)
        if year_before_match:
            parsed["year_before"] = int(year_before_match.group(1))
            working_query = self.YEAR_BEFORE_PATTERN.sub("", working_query)

        # Extract YYYY ->! (after year)
        year_after_match = self.YEAR_AFTER_PATTERN.search(working_query)
        if year_after_match:
            parsed["year_after"] = int(year_after_match.group(1))
            working_query = self.YEAR_AFTER_PATTERN.sub("", working_query)

        # Extract YYYY-YYYY! (year range) - check before single year
        year_range_match = self.YEAR_RANGE_BANG_PATTERN.search(working_query)
        if year_range_match:
            parsed["year"] = {
                "start": int(year_range_match.group(1)),
                "end": int(year_range_match.group(2))
            }
            working_query = self.YEAR_RANGE_BANG_PATTERN.sub("", working_query)

        # Extract YYYY! (single year)
        year_bang_match = self.YEAR_BANG_PATTERN.search(working_query)
        if year_bang_match and not parsed.get("year"):
            parsed["year"] = int(year_bang_match.group(1))
            working_query = self.YEAR_BANG_PATTERN.sub("", working_query)

        # Extract proximity: "word1 word2"~3
        for prox_match in self.PROXIMITY_PATTERN.finditer(working_query):
            parsed["proximity"].append({
                "phrase": prox_match.group(1),
                "slop": int(prox_match.group(2))
            })
        working_query = self.PROXIMITY_PATTERN.sub("", working_query)

        # Extract fuzzy: word~2
        for fuzzy_match in self.FUZZY_PATTERN.finditer(working_query):
            fuzziness = min(int(fuzzy_match.group(2)), 2)
            parsed["fuzzy"].append({
                "term": fuzzy_match.group(1),
                "fuzziness": fuzziness
            })
        working_query = self.FUZZY_PATTERN.sub("", working_query)

        # Extract NOT: -term or NOT term
        for not_match in self.NOT_PATTERN.finditer(working_query):
            parsed["exclude"].append(not_match.group(1))
        working_query = self.NOT_PATTERN.sub("", working_query)

        for not_kw_match in self.NOT_KEYWORD_PATTERN.finditer(working_query):
            parsed["exclude"].append(not_kw_match.group(1))
        working_query = self.NOT_KEYWORD_PATTERN.sub("", working_query)

        # Extract AND/OR
        for and_match in self.AND_PATTERN.finditer(working_query):
            parsed["boolean_and"].append((and_match.group(1), and_match.group(2)))
        working_query = self.AND_PATTERN.sub("", working_query)

        for or_match in self.OR_PATTERN.finditer(working_query):
            parsed["boolean_or"].append((or_match.group(1), or_match.group(2)))
        working_query = self.OR_PATTERN.sub("", working_query)

        # Extract rank(<1000) or rank(>10000)
        rank_match = self.RANK_PATTERN.search(working_query)
        if rank_match:
            parsed["rank"] = {
                "op": rank_match.group(1),
                "value": int(rank_match.group(2))
            }
            working_query = self.RANK_PATTERN.sub("", working_query)

        # Extract authority(high|medium|low)
        auth_match = self.AUTHORITY_PATTERN.search(working_query)
        if auth_match:
            parsed["authority"] = auth_match.group(1).lower()
            working_query = self.AUTHORITY_PATTERN.sub("", working_query)

        # === LOCATION FILTERS ===
        # Extract specific filters FIRST (dom{XX}!, lang{XX}!, geo{XX}!)
        # Then extract shorthand fr! LAST (it matches any)

        # dom{XX}! - DOMAIN TLD ONLY
        dom_match = self.DOM_BANG_PATTERN.search(working_query)
        if dom_match:
            parsed["dom_filter"] = dom_match.group(1).lower()
            working_query = self.DOM_BANG_PATTERN.sub("", working_query)

        # lang{XX}! - LANGUAGE ONLY
        lang_match = self.LANG_BANG_PATTERN.search(working_query)
        if lang_match:
            parsed["lang_filter"] = lang_match.group(1).lower()
            working_query = self.LANG_BANG_PATTERN.sub("", working_query)

        # geo{XX}! - GEOGRAPHIC ONLY
        geo_match = self.GEO_BANG_PATTERN.search(working_query)
        if geo_match:
            parsed["geo_filter"] = geo_match.group(1).lower()
            working_query = self.GEO_BANG_PATTERN.sub("", working_query)

        # fr! - SHORTHAND = (lang{fr}! OR geo{fr}! OR dom{fr}!) - matches ANY
        location_match = self.LOCATION_SHORTHAND_PATTERN.search(working_query)
        if location_match:
            parsed["location_any"] = location_match.group(1).lower()
            working_query = self.LOCATION_SHORTHAND_PATTERN.sub("", working_query)

        # Extract filters (key:value)
        for match in self.FILTER_PATTERN.finditer(working_query):
            key = match.group(1).lower()
            value = match.group(2)
            parsed["filters"][key] = value
        working_query = self.FILTER_PATTERN.sub("", working_query)

        # Remaining text is keywords
        keywords = working_query.strip().split()
        parsed["keywords"] = [k for k in keywords if k]

        return parsed

    def _execute_search(
        self,
        parsed: Dict,
        indices: List[str],
        limit: int
    ) -> List[Dict]:
        """Execute search across specified indices."""

        must = []
        must_not = []

        # Build query clauses
        # NOTE: atlas/domains_unified have NO "text" field!
        # Searchable text fields are: description, title, company_name, company_description
        if parsed.get("definitional"):
            must.append({
                "bool": {
                    "should": [
                        {"match": {"categories": {"query": parsed["definitional"], "boost": 3}}},
                        {"match": {"all_categories": {"query": parsed["definitional"], "boost": 2.5}}},
                        {"match": {"primary_category": {"query": parsed["definitional"], "boost": 2}}},
                        {"match": {"description": {"query": parsed["definitional"], "boost": 1.5}}},
                        {"match": {"title": parsed["definitional"]}},
                        {"match": {"company_industry": {"query": parsed["definitional"], "boost": 1.5}}}
                    ],
                    "minimum_should_match": 1
                }
            })

        if parsed.get("keywords"):
            keyword_query = " ".join(parsed["keywords"])
            must.append({
                "bool": {
                    "should": [
                        {"match": {"domain": {"query": keyword_query, "boost": 3}}},
                        {"match": {"description": {"query": keyword_query, "boost": 2}}},
                        {"match": {"title": {"query": keyword_query, "boost": 2}}},
                        {"match": {"company_name": {"query": keyword_query, "boost": 2}}},
                        {"match": {"company_description": keyword_query}},
                        {"match": {"categories": keyword_query}},
                        {"match": {"all_categories": keyword_query}},
                        # PDF corpus fields (finepdfs-corporate)
                        {"match": {"text": {"query": keyword_query, "boost": 2}}},
                        {"match": {"detected_sectors": keyword_query}}
                    ],
                    "minimum_should_match": 1
                }
            })

        # === LOCATION FILTERS ===

        # Helper to build domain TLD clauses
        def build_dom_clauses(code):
            tld_variants = [code]
            if code == "uk":
                tld_variants = ["uk", "co.uk"]
            return [
                {"terms": {"tld": tld_variants}},
                {"wildcard": {"domain": f"*.{code}"}}
            ]

        # Helper to build language clauses
        def build_lang_clauses(code):
            lang_variants = [code, code.upper()]
            return [
                {"terms": {"language": lang_variants}},
                {"terms": {"lang": lang_variants}},
                {"terms": {"detected_language": lang_variants}}
            ]

        # Helper to build geographic clauses
        def build_geo_clauses(code):
            geo_variants = [code, code.upper()]
            if code == "uk":
                geo_variants.extend(["gb", "GB"])
            return [
                {"terms": {"country": geo_variants}},
                {"terms": {"jurisdiction": geo_variants}},
                {"terms": {"jurisdiction_code": geo_variants}},
                {"terms": {"geo": geo_variants}}
            ]

        # fr! = SHORTHAND (lang OR geo OR dom) - matches ANY
        if parsed.get("location_any"):
            code = parsed["location_any"]
            all_clauses = build_dom_clauses(code) + build_lang_clauses(code) + build_geo_clauses(code)
            must.append({"bool": {"should": all_clauses, "minimum_should_match": 1}})

        # dom{fr}! = DOMAIN TLD ONLY
        if parsed.get("dom_filter"):
            code = parsed["dom_filter"]
            must.append({"bool": {"should": build_dom_clauses(code)}})

        # lang{fr}! = LANGUAGE ONLY
        if parsed.get("lang_filter"):
            code = parsed["lang_filter"]
            must.append({"bool": {"should": build_lang_clauses(code)}})

        # geo{fr}! = GEOGRAPHIC ONLY
        if parsed.get("geo_filter"):
            code = parsed["geo_filter"]
            must.append({"bool": {"should": build_geo_clauses(code)}})

        # Rank filter
        if parsed.get("rank"):
            rank_op = parsed["rank"]["op"]
            rank_val = parsed["rank"]["value"]
            range_key = "lte" if rank_op == "<" else "gte"
            must.append({"range": {"tranco_rank": {range_key: rank_val}}})

        # Authority filter
        if parsed.get("authority"):
            level_def = AUTHORITY_LEVELS.get(parsed["authority"], {})
            range_query = {}
            if "min" in level_def:
                range_query["gte"] = level_def["min"]
            if "max" in level_def:
                range_query["lte"] = level_def["max"]
            if range_query:
                must.append({"range": {"tranco_rank": range_query}})

        # === JURISDICTION FILTERS (from operators.json) ===

        # Jurisdiction label filter (cuk:, puk:, chr:, etc.)
        if parsed.get("jurisdiction_label"):
            jur = parsed["jurisdiction_label"]
            country = jur["country"]
            # Map uk -> GB for internal ES storage
            country_variants = [country, country.upper()]
            if country == "uk":
                country_variants.extend(["gb", "GB"])
            must.append({
                "bool": {
                    "should": [
                        {"terms": {"jurisdiction": country_variants}},
                        {"terms": {"country": country_variants}},
                        {"terms": {"jurisdiction_code": country_variants}},
                        {"wildcard": {"domain": f"*.{country}"}}
                    ]
                }
            })

        # === TEMPORAL FILTERS (from operators.json) ===

        # YYYY! or YYYY-YYYY! (open web year filter)
        if parsed.get("year"):
            year_val = parsed["year"]
            if isinstance(year_val, dict):
                # Year range - check multiple fields including CC dump identifiers
                year_prefixes = [f"CC-MAIN-{y}" for y in range(year_val["start"], year_val["end"] + 1)]
                must.append({
                    "bool": {
                        "should": [
                            {"range": {"date": {"gte": f"{year_val['start']}-01-01", "lte": f"{year_val['end']}-12-31"}}},
                            {"range": {"publishing_year": {"gte": year_val["start"], "lte": year_val["end"]}}},
                            {"terms": {"content_years": [str(y) for y in range(year_val["start"], year_val["end"] + 1)]}},
                            {"bool": {"should": [{"prefix": {"dump": prefix}} for prefix in year_prefixes]}}
                        ]
                    }
                })
            else:
                # Single year
                must.append({
                    "bool": {
                        "should": [
                            {"range": {"date": {"gte": f"{year_val}-01-01", "lte": f"{year_val}-12-31"}}},
                            {"term": {"publishing_year": year_val}},
                            {"term": {"content_years": str(year_val)}},
                            {"prefix": {"dump": f"CC-MAIN-{year_val}"}}
                        ]
                    }
                })

        # <- YYYY! (before year)
        if parsed.get("year_before"):
            year_val = parsed["year_before"]
            must.append({
                "bool": {
                    "should": [
                        {"range": {"date": {"lt": f"{year_val}-01-01"}}},
                        {"range": {"publishing_year": {"lt": year_val}}}
                    ]
                }
            })

        # YYYY ->! (after year)
        if parsed.get("year_after"):
            year_val = parsed["year_after"]
            must.append({
                "bool": {
                    "should": [
                        {"range": {"date": {"gt": f"{year_val}-12-31"}}},
                        {"range": {"publishing_year": {"gt": year_val}}}
                    ]
                }
            })

        # :YYYY! (archive single year)
        if parsed.get("archive_year"):
            year_val = parsed["archive_year"]
            must.append({"prefix": {"dump": f"CC-MAIN-{year_val}"}})

        # :YYYY-YYYY! (archive year range)
        if parsed.get("archive_range"):
            ar = parsed["archive_range"]
            year_prefixes = [f"CC-MAIN-{y}" for y in range(ar["start"], ar["end"] + 1)]
            must.append({
                "bool": {"should": [{"prefix": {"dump": prefix}} for prefix in year_prefixes]}
            })

        # :<-YYYY! (archive back to year)
        if parsed.get("archive_back"):
            # All CC dumps from that year onward
            year_val = parsed["archive_back"]
            current_year = 2026  # Current year
            year_prefixes = [f"CC-MAIN-{y}" for y in range(year_val, current_year + 1)]
            must.append({
                "bool": {"should": [{"prefix": {"dump": prefix}} for prefix in year_prefixes]}
            })

        # Proximity search
        for prox in parsed.get("proximity", []):
            must.append({
                "match_phrase": {
                    "text": {"query": prox["phrase"], "slop": prox["slop"]}
                }
            })

        # Fuzzy search
        for fuz in parsed.get("fuzzy", []):
            must.append({
                "fuzzy": {"text": {"value": fuz["term"], "fuzziness": fuz["fuzziness"]}}
            })

        # Boolean AND
        for term1, term2 in parsed.get("boolean_and", []):
            must.append({
                "bool": {
                    "must": [
                        {"match": {"text": term1}},
                        {"match": {"text": term2}}
                    ]
                }
            })

        # Boolean OR
        for term1, term2 in parsed.get("boolean_or", []):
            must.append({
                "bool": {
                    "should": [
                        {"match": {"text": term1}},
                        {"match": {"text": term2}}
                    ],
                    "minimum_should_match": 1
                }
            })

        # Exclusions
        for term in parsed.get("exclude", []):
            must_not.append({"match": {"text": term}})

        # Build final query
        if not must and not must_not:
            body = {"query": {"match_all": {}}, "size": limit}
        else:
            bool_query = {}
            if must:
                bool_query["must"] = must
            if must_not:
                bool_query["must_not"] = must_not
            body = {
                "query": {"bool": bool_query},
                "size": limit,
                "sort": [
                    {"tranco_rank": {"order": "asc", "unmapped_type": "integer"}},
                    "_score"
                ]
            }

        # Execute
        try:
            index_pattern = ",".join(indices)
            response = self.es.search(index=index_pattern, body=body)
            return self._parse_hits(response["hits"]["hits"])
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def _parse_hits(self, hits: List[Dict]) -> List[Dict]:
        """Parse ES hits into standard format."""
        results = []
        for hit in hits:
            doc = hit["_source"]

            # Build text_preview from available text fields
            # finepdfs-corporate has "text", domain indices have description/title
            text_preview = (
                doc.get("text") or  # PDF corpus
                doc.get("description") or
                doc.get("title") or
                doc.get("company_description") or
                doc.get("company_name") or
                ""
            )[:500]

            results.append({
                "domain": doc.get("domain"),
                "url": doc.get("url") or f"https://{doc.get('domain', '')}",
                "title": doc.get("title"),
                "categories": doc.get("categories") or doc.get("all_categories") or doc.get("primary_category"),
                "detected_sectors": doc.get("detected_sectors") or doc.get("company_industry"),
                "tranco_rank": doc.get("tranco_rank") or doc.get("rank") or doc.get("best_rank"),
                "authority_rank": doc.get("authority_rank"),
                "text_preview": text_preview,
                "entities": doc.get("entities", []),
                "source_index": hit.get("_index"),
                "score": hit.get("_score"),
                # Additional fields for Grid display
                "country": doc.get("country") or doc.get("primary_country"),
                "language": doc.get("lang") or doc.get("language"),
                "company_name": doc.get("company_name"),
                "company_industry": doc.get("company_industry"),
            })
        return results

    def _parse_entity_hits(self, hits: List[Dict]) -> List[Dict]:
        """Parse entity search hits with inner_hits."""
        results = []
        for hit in hits:
            doc = hit["_source"]
            inner_hits = hit.get("inner_hits", {}).get("entities", {}).get("hits", {}).get("hits", [])

            matched_entities = []
            for ih in inner_hits:
                ent = ih["_source"]
                matched_entities.append({
                    "type": ent.get("type"),
                    "value": ent.get("value"),
                    "context": ent.get("context")
                })

            results.append({
                "url": doc.get("url"),
                "domain": doc.get("domain"),
                "detected_sectors": doc.get("detected_sectors"),
                "matched_entities": matched_entities,
                "source_index": hit.get("_index"),
                "score": hit.get("_score"),
            })
        return results


# Convenience function for quick searches
def cymonides_search(query: str, limit: int = 100) -> CymonidesResult:
    """Quick unified search across all CYMONIDES indices."""
    search = CymonidesUnifiedSearch()
    return search.search(query, limit)


def cymonides_entity_search(
    entity_type: str,
    entity_value: str,
    limit: int = 100
) -> CymonidesResult:
    """Quick entity search in PDF corpus."""
    search = CymonidesUnifiedSearch()
    return search.search_entities(entity_type, entity_value, limit)
