"""
DRILL Link Pipeline - Deep GlobalLinks Integration

Instead of just calling GlobalLinks for real-time queries, this module:
1. Runs GlobalLinks extractions for domains of interest
2. Indexes results into Elasticsearch with entity extraction + embeddings
3. Enables instant, enriched queries on pre-extracted link data

This makes DRILL MUCH faster for repeated queries and adds intelligence
(entities, embeddings, categorization) to raw link data.

Architecture:
    GlobalLinks (Go binary)
          │
          ▼
    DRILL LinkPipeline
          │
          ├─→ Entity Extraction (companies, persons in anchor text)
          ├─→ Embeddings (semantic similarity)
          ├─→ Categorization (domain types)
          │
          ▼
    Elasticsearch (drill_links index)
          │
          ▼
    Instant queries with enrichments

Usage:
    pipeline = DrillLinkPipeline()

    # One-time extraction (slow, but comprehensive)
    await pipeline.extract_and_index("example.com", archive="CC-MAIN-2024-10")

    # Fast queries on indexed data
    results = await pipeline.query_links(
        source_domain="example.com",
        target_tlds=[".ru", ".ky"],
        anchor_keywords=["contract", "agreement"]
    )
"""

import asyncio
import json
import hashlib
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse
import os
import sys
from pathlib import Path

# LinkLater imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk


@dataclass
class EnrichedLink:
    """A link record enriched with DRILL intelligence."""
    source_url: str
    source_domain: str
    target_url: str
    target_domain: str
    target_tld: str
    anchor_text: Optional[str]
    # DRILL enrichments
    anchor_entities: Dict[str, List[str]] = field(default_factory=dict)  # {companies: [], persons: []}
    anchor_embedding: Optional[List[float]] = None
    target_category: Optional[str] = None  # news, government, offshore, etc.
    # Metadata
    archive: str = ""
    extracted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # Temporal metadata (Feature 1: Temporal + Link Graph Integration)
    first_seen_wayback: Optional[str] = None
    last_seen_wayback: Optional[str] = None
    first_seen_commoncrawl: Optional[str] = None
    last_seen_commoncrawl: Optional[str] = None
    first_seen: Optional[str] = None  # Earliest across all archives
    last_archived: Optional[str] = None  # Most recent across all archives
    link_age_days: Optional[int] = None  # Days since first_seen

    @property
    def doc_id(self) -> str:
        """Unique ID for deduplication."""
        return hashlib.md5(f"{self.source_url}:{self.target_url}".encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        doc = {
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "target_url": self.target_url,
            "target_domain": self.target_domain,
            "target_tld": self.target_tld,
            "anchor_text": self.anchor_text,
            "anchor_entities": self.anchor_entities,
            "target_category": self.target_category,
            "archive": self.archive,
            "extracted_at": self.extracted_at,
        }
        if self.anchor_embedding:
            doc["anchor_embedding"] = self.anchor_embedding
        # Temporal fields (Feature 1)
        if self.first_seen_wayback:
            doc["first_seen_wayback"] = self.first_seen_wayback
        if self.last_seen_wayback:
            doc["last_seen_wayback"] = self.last_seen_wayback
        if self.first_seen_commoncrawl:
            doc["first_seen_commoncrawl"] = self.first_seen_commoncrawl
        if self.last_seen_commoncrawl:
            doc["last_seen_commoncrawl"] = self.last_seen_commoncrawl
        if self.first_seen:
            doc["first_seen"] = self.first_seen
        if self.last_archived:
            doc["last_archived"] = self.last_archived
        if self.link_age_days is not None:
            doc["link_age_days"] = self.link_age_days
        return doc


class DrillLinkPipeline:
    """
    Deep GlobalLinks integration for DRILL.

    Extracts links using GlobalLinks, enriches them with DRILL intelligence,
    and indexes to Elasticsearch for instant, smart queries.
    """

    INDEX_NAME = "drill_links_enriched"

    INDEX_MAPPING = {
        "mappings": {
            "properties": {
                "source_url": {"type": "keyword"},
                "source_domain": {"type": "keyword"},
                "target_url": {"type": "keyword"},
                "target_domain": {"type": "keyword"},
                "target_tld": {"type": "keyword"},
                "anchor_text": {"type": "text", "analyzer": "standard"},
                "anchor_entities": {
                    "properties": {
                        "companies": {"type": "keyword"},
                        "persons": {"type": "keyword"},
                        "locations": {"type": "keyword"},
                    }
                },
                "anchor_embedding": {
                    "type": "dense_vector",
                    "dims": 384,
                    "index": True,
                    "similarity": "cosine",
                },
                "target_category": {"type": "keyword"},
                "archive": {"type": "keyword"},
                "extracted_at": {"type": "date"},
                # Temporal fields (Feature 1: Temporal + Link Graph Integration)
                "first_seen_wayback": {"type": "date"},
                "last_seen_wayback": {"type": "date"},
                "first_seen_commoncrawl": {"type": "date"},
                "last_seen_commoncrawl": {"type": "date"},
                "first_seen": {"type": "date"},
                "last_archived": {"type": "date"},
                "link_age_days": {"type": "integer"},
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    }

    # Domain categorization patterns
    CATEGORY_PATTERNS = {
        "offshore": [".ky", ".vg", ".pa", ".bs", ".je", ".gg", ".im", ".lu", ".li", ".mc", ".bvi"],
        "government": [".gov", ".gov.uk", ".gouv.fr", ".gob", ".govt", ".mil"],
        "russia_cis": [".ru", ".su", ".by", ".kz", ".ua", ".uz", ".az"],
        "china": [".cn", ".hk", ".tw"],
        "news_media": ["reuters", "bloomberg", "bbc", "cnn", "guardian", "nytimes", "wsj"],
        "social": ["facebook", "twitter", "linkedin", "instagram", "youtube", "tiktok"],
        "financial": ["bank", "exchange", "securities", "nasdaq", "nyse", "lse"],
    }

    def __init__(
        self,
        elasticsearch_url: Optional[str] = None,
        enable_embeddings: bool = True,
        enable_entity_extraction: bool = True,
    ):
        self.es_url = elasticsearch_url or os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
        self.es = Elasticsearch([self.es_url])
        self.enable_embeddings = enable_embeddings
        self.enable_entity_extraction = enable_entity_extraction

        # Lazy-loaded components
        self._globallinks = None
        self._embedder = None
        self._entity_extractor = None

    @property
    def globallinks(self):
        """Lazy load GlobalLinks client."""
        if self._globallinks is None:
            try:
                from modules.linklater.linkgraph.globallinks import GlobalLinksClient
                self._globallinks = GlobalLinksClient()
            except ImportError:
                pass
        return self._globallinks

    @property
    def embedder(self):
        """Lazy load DRILL embedder."""
        if self._embedder is None and self.enable_embeddings:
            try:
                from .embedder import DrillEmbedder
                self._embedder = DrillEmbedder()
            except ImportError:
                pass
        return self._embedder

    @property
    def entity_extractor(self):
        """Lazy load entity extractor."""
        if self._entity_extractor is None and self.enable_entity_extraction:
            try:
                from .extractors import EntityExtractor
                self._entity_extractor = EntityExtractor()
            except ImportError:
                pass
        return self._entity_extractor

    def ensure_index(self):
        """Create index if it doesn't exist."""
        if not self.es.indices.exists(index=self.INDEX_NAME):
            self.es.indices.create(index=self.INDEX_NAME, body=self.INDEX_MAPPING)
            print(f"[LinkPipeline] Created index: {self.INDEX_NAME}")

    def categorize_domain(self, domain: str) -> Optional[str]:
        """Categorize a domain based on patterns."""
        domain_lower = domain.lower()

        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if pattern in domain_lower or domain_lower.endswith(pattern):
                    return category
        return None

    def get_tld(self, domain: str) -> str:
        """Extract TLD from domain."""
        parts = domain.lower().split('.')
        if len(parts) >= 2:
            # Handle compound TLDs like .co.uk, .gov.uk
            if len(parts) >= 3 and parts[-2] in ['co', 'gov', 'ac', 'org', 'net']:
                return f".{parts[-2]}.{parts[-1]}"
            return f".{parts[-1]}"
        return ""

    async def extract_and_index(
        self,
        domain: str,
        archive: str = "CC-MAIN-2024-10",
        country_tlds: Optional[List[str]] = None,
        url_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        max_results: int = 5000,
        batch_size: int = 100,
        enrich_temporal: bool = True,  # Enable temporal enrichment by default
    ) -> Dict[str, Any]:
        """
        Extract links using GlobalLinks and index with enrichments.

        This is the main integration point - runs GlobalLinks, enriches results,
        and indexes to Elasticsearch for fast future queries.

        Args:
            domain: Source domain to extract from
            archive: CC archive to use
            country_tlds: Filter to specific country TLDs
            url_keywords: Filter URLs containing keywords
            exclude_keywords: Exclude URLs with these keywords
            max_results: Max links to extract
            batch_size: Elasticsearch bulk batch size
            enrich_temporal: If True, lookup first_seen/last_seen from archives (slower but adds historical context)

        Returns:
            Stats dict with extraction results
        """
        if not self.globallinks or not self.globallinks.outlinker:
            return {"error": "GlobalLinks not available", "indexed": 0}

        self.ensure_index()

        print(f"[LinkPipeline] Extracting links from {domain} using {archive}...")

        # Run GlobalLinks extraction
        try:
            records = await self.globallinks.extract_outlinks(
                domains=[domain],
                archive=archive,
                country_tlds=country_tlds,
                url_keywords=url_keywords,
                exclude_keywords=exclude_keywords,
                max_results=max_results,
            )
        except Exception as e:
            return {"error": f"GlobalLinks extraction failed: {e}", "indexed": 0}

        print(f"[LinkPipeline] Got {len(records)} raw links, enriching...")

        # Enrich and prepare for indexing
        enriched_links = []
        anchor_texts = []

        for record in records:
            source = record.source if hasattr(record, 'source') else ""
            target = record.target if hasattr(record, 'target') else ""
            anchor = record.anchor_text if hasattr(record, 'anchor_text') else ""

            # Parse domains
            source_parsed = urlparse(source if source.startswith('http') else f"http://{source}")
            target_parsed = urlparse(target if target.startswith('http') else f"http://{target}")

            source_domain = source_parsed.netloc or source.split('/')[0]
            target_domain = target_parsed.netloc or target.split('/')[0]

            # Create enriched link
            enriched = EnrichedLink(
                source_url=source,
                source_domain=source_domain,
                target_url=target,
                target_domain=target_domain,
                target_tld=self.get_tld(target_domain),
                anchor_text=anchor,
                archive=archive,
                target_category=self.categorize_domain(target_domain),
            )

            # Extract entities from anchor text
            if anchor and self.entity_extractor:
                try:
                    # Wrap anchor in HTML-like format for extractor
                    fake_html = f"<p>{anchor}</p>"
                    entities = self.entity_extractor.extract(fake_html, target)
                    enriched.anchor_entities = {
                        "companies": entities.companies[:5],
                        "persons": entities.persons[:5],
                        "locations": [],  # Not extracted by default
                    }
                except Exception:
                    pass

            enriched_links.append(enriched)
            if anchor:
                anchor_texts.append(anchor)

        # Batch embed anchor texts
        if anchor_texts and self.embedder:
            try:
                print(f"[LinkPipeline] Embedding {len(anchor_texts)} anchor texts...")
                embeddings = self.embedder.embed_batch(anchor_texts)

                anchor_idx = 0
                for link in enriched_links:
                    if link.anchor_text:
                        link.anchor_embedding = embeddings[anchor_idx]
                        anchor_idx += 1
            except Exception as e:
                print(f"[LinkPipeline] Embedding failed: {e}")

        # Temporal enrichment (Feature 1: When did X start linking to Y?)
        temporal_enriched = 0
        if enrich_temporal:
            try:
                from modules.LINKLATER.temporal import TemporalAnalyzer
                temporal = TemporalAnalyzer()

                # Get unique target URLs for batch lookup
                target_urls = list({link.target_url for link in enriched_links if link.target_url})
                print(f"[LinkPipeline] Enriching temporal data for {len(target_urls)} unique targets...")

                # Batch fetch timelines (20 concurrent, no live checks for speed)
                # Returns Dict[str, URLTimeline] directly
                timelines = await temporal.get_url_timelines_batch(
                    urls=target_urls,
                    check_live=False,
                    max_concurrent=20
                )

                # timelines is already a Dict[str, URLTimeline], use directly
                # Apply temporal data to each enriched link
                for link in enriched_links:
                    tl = timelines.get(link.target_url)
                    if tl:
                        link.first_seen_wayback = tl.first_seen_wayback
                        link.last_seen_wayback = tl.last_seen_wayback
                        link.first_seen_commoncrawl = tl.first_seen_commoncrawl
                        link.last_seen_commoncrawl = tl.last_seen_commoncrawl
                        link.first_seen = tl.get_first_seen()
                        link.last_archived = tl.get_last_archived()
                        link.link_age_days = tl.age_days()
                        temporal_enriched += 1

                print(f"[LinkPipeline] Temporal data added to {temporal_enriched}/{len(enriched_links)} links")
            except ImportError:
                print("[LinkPipeline] TemporalAnalyzer not available, skipping temporal enrichment")
            except Exception as e:
                print(f"[LinkPipeline] Temporal enrichment failed: {e}")

        # Bulk index to Elasticsearch
        print(f"[LinkPipeline] Indexing {len(enriched_links)} enriched links...")

        def generate_actions():
            for link in enriched_links:
                yield {
                    "_index": self.INDEX_NAME,
                    "_id": link.doc_id,
                    "_source": link.to_dict(),
                }

        success, errors = bulk(
            self.es,
            generate_actions(),
            chunk_size=batch_size,
            raise_on_error=False,
        )

        # Aggregate stats
        categories = {}
        tlds = {}
        for link in enriched_links:
            if link.target_category:
                categories[link.target_category] = categories.get(link.target_category, 0) + 1
            if link.target_tld:
                tlds[link.target_tld] = tlds.get(link.target_tld, 0) + 1

        return {
            "domain": domain,
            "archive": archive,
            "extracted": len(records),
            "indexed": success,
            "errors": len(errors) if errors else 0,
            "categories": categories,
            "tlds": dict(sorted(tlds.items(), key=lambda x: -x[1])[:20]),
            "with_entities": sum(1 for l in enriched_links if l.anchor_entities.get("companies") or l.anchor_entities.get("persons")),
            "with_embeddings": sum(1 for l in enriched_links if l.anchor_embedding),
            "with_temporal": temporal_enriched,
        }

    async def query_links(
        self,
        source_domain: Optional[str] = None,
        target_domain: Optional[str] = None,
        target_tlds: Optional[List[str]] = None,
        target_category: Optional[str] = None,
        anchor_text: Optional[str] = None,
        anchor_keywords: Optional[List[str]] = None,
        entity_name: Optional[str] = None,
        size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query indexed links with filters.

        Much faster than real-time GlobalLinks queries because data is pre-indexed.
        Plus you get entity and category enrichments.

        Args:
            source_domain: Filter by source domain
            target_domain: Filter by target domain
            target_tlds: Filter by target TLDs (e.g., [".ru", ".ky"])
            target_category: Filter by category (offshore, government, etc.)
            anchor_text: Full-text search on anchor text
            anchor_keywords: Match any of these keywords in anchor
            entity_name: Match entity in anchor_entities
            size: Max results

        Returns:
            List of enriched link records
        """
        must = []
        should = []

        if source_domain:
            must.append({"term": {"source_domain": source_domain}})

        if target_domain:
            must.append({"term": {"target_domain": target_domain}})

        if target_tlds:
            must.append({"terms": {"target_tld": target_tlds}})

        if target_category:
            must.append({"term": {"target_category": target_category}})

        if anchor_text:
            must.append({"match": {"anchor_text": anchor_text}})

        if anchor_keywords:
            for kw in anchor_keywords:
                should.append({"match": {"anchor_text": kw}})

        if entity_name:
            should.extend([
                {"term": {"anchor_entities.companies": entity_name}},
                {"term": {"anchor_entities.persons": entity_name}},
            ])

        query = {"bool": {}}
        if must:
            query["bool"]["must"] = must
        if should:
            query["bool"]["should"] = should
            query["bool"]["minimum_should_match"] = 1 if not must else 0

        if not must and not should:
            query = {"match_all": {}}

        result = self.es.search(
            index=self.INDEX_NAME,
            body={"query": query, "size": size},
        )

        return [hit["_source"] for hit in result["hits"]["hits"]]

    async def query_similar_anchors(
        self,
        query_text: str,
        source_domain: Optional[str] = None,
        k: int = 20,
        min_score: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search on anchor texts using embeddings.

        Find links with semantically similar anchor text to your query.

        Args:
            query_text: Text to find similar anchors for
            source_domain: Optional filter by source
            k: Number of results
            min_score: Minimum similarity score

        Returns:
            Similar links with scores
        """
        if not self.embedder:
            return []

        # Embed query
        query_embedding = self.embedder.embed(query_text)

        # kNN search
        knn_query = {
            "knn": {
                "field": "anchor_embedding",
                "query_vector": query_embedding,
                "k": k,
                "num_candidates": k * 10,
            }
        }

        if source_domain:
            knn_query["knn"]["filter"] = {"term": {"source_domain": source_domain}}

        result = self.es.search(index=self.INDEX_NAME, body=knn_query)

        return [
            {**hit["_source"], "score": hit["_score"]}
            for hit in result["hits"]["hits"]
            if hit["_score"] >= min_score
        ]

    async def get_domain_stats(self, source_domain: str) -> Dict[str, Any]:
        """Get statistics for a domain's extracted links."""

        aggs = {
            "by_tld": {"terms": {"field": "target_tld", "size": 50}},
            "by_category": {"terms": {"field": "target_category", "size": 20}},
            "by_archive": {"terms": {"field": "archive", "size": 10}},
        }

        result = self.es.search(
            index=self.INDEX_NAME,
            body={
                "query": {"term": {"source_domain": source_domain}},
                "size": 0,
                "aggs": aggs,
            },
        )

        return {
            "domain": source_domain,
            "total_links": result["hits"]["total"]["value"],
            "tlds": {b["key"]: b["doc_count"] for b in result["aggregations"]["by_tld"]["buckets"]},
            "categories": {b["key"]: b["doc_count"] for b in result["aggregations"]["by_category"]["buckets"]},
            "archives": {b["key"]: b["doc_count"] for b in result["aggregations"]["by_archive"]["buckets"]},
        }

    async def query_links_by_age(
        self,
        source_domain: Optional[str] = None,
        target_domain: Optional[str] = None,
        min_age_days: Optional[int] = None,
        max_age_days: Optional[int] = None,
        first_seen_after: Optional[str] = None,
        first_seen_before: Optional[str] = None,
        target_category: Optional[str] = None,
        size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query links by temporal criteria (Feature 1: Temporal + Link Graph).

        Answer questions like:
        - "When did example.com start linking to offshore.ky?"
        - "Find links that appeared in the last 30 days"
        - "Find old links (> 2 years) to Russian domains"

        Args:
            source_domain: Filter by source domain
            target_domain: Filter by target domain
            min_age_days: Minimum link age in days (e.g., 365 for > 1 year old)
            max_age_days: Maximum link age in days (e.g., 30 for < 1 month old)
            first_seen_after: ISO date string, find links first seen after this date
            first_seen_before: ISO date string, find links first seen before this date
            target_category: Filter by target category (offshore, russia_cis, etc.)
            size: Max results

        Returns:
            List of enriched link records with temporal metadata
        """
        must = []

        if source_domain:
            must.append({"term": {"source_domain": source_domain}})

        if target_domain:
            must.append({"term": {"target_domain": target_domain}})

        if target_category:
            must.append({"term": {"target_category": target_category}})

        # Age-based filtering
        if min_age_days is not None or max_age_days is not None:
            age_range = {}
            if min_age_days is not None:
                age_range["gte"] = min_age_days
            if max_age_days is not None:
                age_range["lte"] = max_age_days
            must.append({"range": {"link_age_days": age_range}})

        # Date-based filtering
        if first_seen_after or first_seen_before:
            date_range = {}
            if first_seen_after:
                date_range["gte"] = first_seen_after
            if first_seen_before:
                date_range["lte"] = first_seen_before
            must.append({"range": {"first_seen": date_range}})

        # Must have first_seen to be useful for temporal queries
        must.append({"exists": {"field": "first_seen"}})

        query = {"bool": {"must": must}} if must else {"match_all": {}}

        result = self.es.search(
            index=self.INDEX_NAME,
            body={
                "query": query,
                "size": size,
                "sort": [{"first_seen": {"order": "asc"}}],  # Oldest first
            },
        )

        return [hit["_source"] for hit in result["hits"]["hits"]]

    async def get_link_timeline(
        self,
        source_domain: str,
        target_domain: str,
    ) -> Dict[str, Any]:
        """
        Get the timeline of when source_domain linked to target_domain.

        This answers the core question: "When did X start linking to Y?"

        Args:
            source_domain: The linking domain
            target_domain: The linked-to domain

        Returns:
            Timeline info including first_seen, last_archived, and all links
        """
        result = self.es.search(
            index=self.INDEX_NAME,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"source_domain": source_domain}},
                            {"term": {"target_domain": target_domain}},
                        ]
                    }
                },
                "size": 100,
                "sort": [{"first_seen": {"order": "asc"}}],
                "aggs": {
                    "first_seen_min": {"min": {"field": "first_seen"}},
                    "last_archived_max": {"max": {"field": "last_archived"}},
                },
            },
        )

        links = [hit["_source"] for hit in result["hits"]["hits"]]
        aggs = result.get("aggregations", {})

        return {
            "source_domain": source_domain,
            "target_domain": target_domain,
            "total_links": result["hits"]["total"]["value"],
            "first_seen": aggs.get("first_seen_min", {}).get("value_as_string"),
            "last_archived": aggs.get("last_archived_max", {}).get("value_as_string"),
            "links": links,
        }

    async def find_shared_targets(
        self,
        domains: List[str],
        min_sources: int = 2,
    ) -> Dict[str, List[str]]:
        """
        Find target domains linked by multiple source domains.

        Use case: "Which domains do companies A, B, and C all link to?"

        Args:
            domains: Source domains to analyze
            min_sources: Minimum number of sources that must link to target

        Returns:
            Dict of target_domain -> list of source domains
        """
        # Get all targets for each source
        targets_by_source: Dict[str, Set[str]] = {}

        for domain in domains:
            result = self.es.search(
                index=self.INDEX_NAME,
                body={
                    "query": {"term": {"source_domain": domain}},
                    "size": 0,
                    "aggs": {"targets": {"terms": {"field": "target_domain", "size": 10000}}},
                },
            )

            targets_by_source[domain] = {
                b["key"] for b in result["aggregations"]["targets"]["buckets"]
            }

        # Find shared targets
        all_targets: Dict[str, Set[str]] = {}
        for source, targets in targets_by_source.items():
            for target in targets:
                if target not in all_targets:
                    all_targets[target] = set()
                all_targets[target].add(source)

        # Filter by min_sources
        shared = {
            target: sorted(sources)
            for target, sources in all_targets.items()
            if len(sources) >= min_sources
        }

        return dict(sorted(shared.items(), key=lambda x: -len(x[1])))

    async def calculate_link_velocity(
        self,
        source_domain: str,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Calculate link acquisition velocity for a domain (Feature 5).

        Measures how fast new links are appearing based on first_seen timestamps.

        Args:
            source_domain: Domain to analyze
            period_days: Period to calculate velocity over

        Returns:
            Velocity metrics including new links, category breakdown, top targets
        """
        from datetime import datetime, timedelta

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period_days)

        # Query links with first_seen in the period
        query = {
            "bool": {
                "must": [
                    {"term": {"source_domain": source_domain}},
                    {"range": {"first_seen": {
                        "gte": start_date.isoformat(),
                        "lte": end_date.isoformat()
                    }}},
                ]
            }
        }

        try:
            result = self.es.search(
                index=self.INDEX_NAME,
                body={
                    "query": query,
                    "size": 0,
                    "aggs": {
                        "by_category": {"terms": {"field": "target_category", "size": 20}},
                        "by_target": {"terms": {"field": "target_domain", "size": 20}},
                        "by_tld": {"terms": {"field": "target_tld", "size": 20}},
                    },
                },
            )

            total = result["hits"]["total"]["value"]
            aggs = result.get("aggregations", {})

            categories = {
                b["key"]: b["doc_count"]
                for b in aggs.get("by_category", {}).get("buckets", [])
            }

            top_targets = [
                {"domain": b["key"], "count": b["doc_count"]}
                for b in aggs.get("by_target", {}).get("buckets", [])
            ]

            top_tlds = {
                b["key"]: b["doc_count"]
                for b in aggs.get("by_tld", {}).get("buckets", [])
            }

            return {
                "domain": source_domain,
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat(),
                "period_days": period_days,
                "new_links_count": total,
                "new_offshore_links": categories.get("offshore", 0),
                "new_government_links": categories.get("government", 0),
                "new_russia_cis_links": categories.get("russia_cis", 0),
                "avg_links_per_day": round(total / period_days, 2) if period_days > 0 else 0,
                "top_new_targets": top_targets,
                "categories": categories,
                "tlds": top_tlds,
            }
        except Exception as e:
            return {
                "domain": source_domain,
                "error": str(e),
                "new_links_count": 0,
            }


# Convenience functions
async def extract_and_index_domain(
    domain: str,
    archive: str = "CC-MAIN-2024-10",
    **kwargs
) -> Dict[str, Any]:
    """Quick extraction and indexing for a domain."""
    pipeline = DrillLinkPipeline()
    return await pipeline.extract_and_index(domain, archive, **kwargs)


async def query_offshore_links(source_domain: str) -> List[Dict[str, Any]]:
    """Query for offshore jurisdiction links."""
    pipeline = DrillLinkPipeline()
    return await pipeline.query_links(
        source_domain=source_domain,
        target_category="offshore",
    )


async def query_russian_links(source_domain: str) -> List[Dict[str, Any]]:
    """Query for Russian/CIS links."""
    pipeline = DrillLinkPipeline()
    return await pipeline.query_links(
        source_domain=source_domain,
        target_tlds=[".ru", ".su", ".by", ".kz", ".ua"],
    )
