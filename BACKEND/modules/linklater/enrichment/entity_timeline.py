"""
LinkLater Entity Timeline Tracker

Feature 2: Track when entities first appeared in a domain's pages.

This module enables:
- Tracking first/last appearance of entities (companies, persons) across domain snapshots
- Finding new entities that appeared after a specific date
- Building entity appearance timelines across multiple domains

Usage:
    tracker = EntityTimelineTracker()

    # Track entity appearances for a domain
    appearances = await tracker.track_entity_appearances("example.com", years=[2023, 2024])

    # Get timeline for a specific entity
    timeline = await tracker.get_entity_timeline("Acme Corp", domain="example.com")

    # Find entities that first appeared after a date
    new_entities = await tracker.find_new_entities("example.com", since_date="2024-01-01")
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk


@dataclass
class EntityAppearance:
    """Tracks when an entity appeared in archived content."""
    entity_type: str  # company, person, email, phone
    entity_value: str
    domain: str
    first_seen_url: str
    first_seen_timestamp: str
    last_seen_url: Optional[str] = None
    last_seen_timestamp: Optional[str] = None
    occurrence_count: int = 1
    sources: List[str] = field(default_factory=list)  # wayback, cc, live

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_value": self.entity_value,
            "domain": self.domain,
            "first_seen_url": self.first_seen_url,
            "first_seen_timestamp": self.first_seen_timestamp,
            "last_seen_url": self.last_seen_url or self.first_seen_url,
            "last_seen_timestamp": self.last_seen_timestamp or self.first_seen_timestamp,
            "occurrence_count": self.occurrence_count,
            "sources": self.sources,
        }

    @property
    def doc_id(self) -> str:
        """Unique ID for this entity-domain pair."""
        import hashlib
        return hashlib.md5(f"{self.entity_type}:{self.entity_value}:{self.domain}".encode()).hexdigest()


class EntityTimelineTracker:
    """Track when entities first appeared in domain content."""

    INDEX_NAME = "drill_entity_timeline"

    INDEX_MAPPING = {
        "mappings": {
            "properties": {
                "entity_type": {"type": "keyword"},
                "entity_value": {"type": "keyword"},
                "entity_value_text": {"type": "text"},  # For fuzzy matching
                "domain": {"type": "keyword"},
                "first_seen_url": {"type": "keyword"},
                "first_seen_timestamp": {"type": "date"},
                "last_seen_url": {"type": "keyword"},
                "last_seen_timestamp": {"type": "date"},
                "occurrence_count": {"type": "integer"},
                "sources": {"type": "keyword"},
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    }

    def __init__(self, elasticsearch_url: Optional[str] = None):
        self.es_url = elasticsearch_url or os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
        self.es = Elasticsearch([self.es_url])
        self._extractor = None

    @property
    def extractor(self):
        """Lazy load entity extractor."""
        if self._extractor is None:
            try:
                from ..scraping.web.extractors import EntityExtractor
                self._extractor = EntityExtractor()
            except ImportError:
                pass
        return self._extractor

    def ensure_index(self):
        """Create index if it doesn't exist."""
        if not self.es.indices.exists(index=self.INDEX_NAME):
            self.es.indices.create(index=self.INDEX_NAME, body=self.INDEX_MAPPING)
            print(f"[EntityTimeline] Created index: {self.INDEX_NAME}")

    async def track_entity_appearances(
        self,
        domain: str,
        years: Optional[List[int]] = None,
        max_snapshots_per_year: int = 12,
    ) -> Dict[str, EntityAppearance]:
        """
        Scan archive snapshots for a domain, extract entities, track first/last appearance.

        Args:
            domain: Domain to analyze
            years: Years to scan (default: 2020-2025)
            max_snapshots_per_year: Max snapshots to check per year

        Returns:
            Dict mapping entity_key to EntityAppearance
        """
        if years is None:
            years = list(range(2020, 2026))

        self.ensure_index()

        # Get snapshots for each year
        from ..archives.snapshot_differ import SnapshotDiffer
        from ..scraping.cc_first_scraper import CCFirstScraper

        differ = SnapshotDiffer()
        scraper = CCFirstScraper()

        # Track appearances: entity_key -> EntityAppearance
        appearances: Dict[str, EntityAppearance] = {}

        try:
            # Get snapshot timestamps
            url = f"https://{domain}/"
            all_snapshots = await differ.get_snapshot_digests(
                url,
                start_year=min(years),
                end_year=max(years)
            )

            # Sample snapshots (one per month roughly)
            sampled = self._sample_snapshots(all_snapshots, max_snapshots_per_year * len(years))

            print(f"[EntityTimeline] Processing {len(sampled)} snapshots for {domain}...")

            for timestamp, digest in sampled:
                # Fetch content
                content = await differ.fetch_wayback_content(url, timestamp)
                if not content:
                    continue

                # Extract entities
                if not self.extractor:
                    continue

                try:
                    entities = self.extractor.extract(content, url)
                except Exception:
                    continue

                # Parse timestamp to ISO format
                try:
                    dt = datetime.strptime(timestamp[:14], "%Y%m%d%H%M%S")
                    iso_timestamp = dt.isoformat()
                except ValueError:
                    continue

                # Track companies
                for company in entities.companies:
                    key = f"company:{company}"
                    if key not in appearances:
                        appearances[key] = EntityAppearance(
                            entity_type="company",
                            entity_value=company,
                            domain=domain,
                            first_seen_url=url,
                            first_seen_timestamp=iso_timestamp,
                            sources=["wayback"],
                        )
                    else:
                        appearances[key].last_seen_url = url
                        appearances[key].last_seen_timestamp = iso_timestamp
                        appearances[key].occurrence_count += 1

                # Track persons
                for person in entities.persons:
                    key = f"person:{person}"
                    if key not in appearances:
                        appearances[key] = EntityAppearance(
                            entity_type="person",
                            entity_value=person,
                            domain=domain,
                            first_seen_url=url,
                            first_seen_timestamp=iso_timestamp,
                            sources=["wayback"],
                        )
                    else:
                        appearances[key].last_seen_url = url
                        appearances[key].last_seen_timestamp = iso_timestamp
                        appearances[key].occurrence_count += 1

                # Track emails
                for email in entities.emails:
                    key = f"email:{email}"
                    if key not in appearances:
                        appearances[key] = EntityAppearance(
                            entity_type="email",
                            entity_value=email,
                            domain=domain,
                            first_seen_url=url,
                            first_seen_timestamp=iso_timestamp,
                            sources=["wayback"],
                        )
                    else:
                        appearances[key].occurrence_count += 1

            # Index to Elasticsearch
            await self._index_appearances(list(appearances.values()))

            print(f"[EntityTimeline] Tracked {len(appearances)} unique entities for {domain}")

        finally:
            await differ.close()

        return appearances

    def _sample_snapshots(
        self,
        snapshots: List[tuple],
        max_count: int,
    ) -> List[tuple]:
        """Sample snapshots evenly across the timeline."""
        if len(snapshots) <= max_count:
            return snapshots

        # Take evenly spaced samples
        step = len(snapshots) / max_count
        indices = [int(i * step) for i in range(max_count)]
        return [snapshots[i] for i in indices]

    async def _index_appearances(self, appearances: List[EntityAppearance]):
        """Bulk index entity appearances."""
        def generate_actions():
            for app in appearances:
                doc = app.to_dict()
                doc["entity_value_text"] = app.entity_value  # For text search
                yield {
                    "_index": self.INDEX_NAME,
                    "_id": app.doc_id,
                    "_source": doc,
                }

        success, errors = bulk(
            self.es,
            generate_actions(),
            chunk_size=100,
            raise_on_error=False,
        )
        print(f"[EntityTimeline] Indexed {success} appearances, {len(errors) if errors else 0} errors")

    async def get_entity_timeline(
        self,
        entity_value: str,
        entity_type: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get appearance timeline for an entity.

        Args:
            entity_value: Entity to search for
            entity_type: Optional filter by type (company, person, email)
            domain: Optional filter by domain

        Returns:
            List of appearance records sorted by first_seen
        """
        must = [{"term": {"entity_value": entity_value}}]

        if entity_type:
            must.append({"term": {"entity_type": entity_type}})

        if domain:
            must.append({"term": {"domain": domain}})

        result = self.es.search(
            index=self.INDEX_NAME,
            body={
                "query": {"bool": {"must": must}},
                "size": 100,
                "sort": [{"first_seen_timestamp": {"order": "asc"}}],
            },
        )

        return [hit["_source"] for hit in result["hits"]["hits"]]

    async def find_new_entities(
        self,
        domain: str,
        since_date: str,
        entity_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find entities that first appeared after a specific date.

        Args:
            domain: Domain to search
            since_date: ISO date string (e.g., "2024-01-01")
            entity_types: Optional filter by types (company, person, email)

        Returns:
            List of newly appeared entities
        """
        must = [
            {"term": {"domain": domain}},
            {"range": {"first_seen_timestamp": {"gte": since_date}}},
        ]

        if entity_types:
            must.append({"terms": {"entity_type": entity_types}})

        result = self.es.search(
            index=self.INDEX_NAME,
            body={
                "query": {"bool": {"must": must}},
                "size": 500,
                "sort": [{"first_seen_timestamp": {"order": "asc"}}],
            },
        )

        return [hit["_source"] for hit in result["hits"]["hits"]]

    async def search_entities_fuzzy(
        self,
        query: str,
        entity_type: Optional[str] = None,
        domain: Optional[str] = None,
        size: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fuzzy search for entities.

        Args:
            query: Search query
            entity_type: Optional filter by type
            domain: Optional filter by domain
            size: Max results

        Returns:
            Matching entity appearances
        """
        must = [{"match": {"entity_value_text": {"query": query, "fuzziness": "AUTO"}}}]

        if entity_type:
            must.append({"term": {"entity_type": entity_type}})

        if domain:
            must.append({"term": {"domain": domain}})

        result = self.es.search(
            index=self.INDEX_NAME,
            body={
                "query": {"bool": {"must": must}},
                "size": size,
            },
        )

        return [hit["_source"] for hit in result["hits"]["hits"]]

    async def get_entity_stats(
        self,
        domain: str,
    ) -> Dict[str, Any]:
        """Get entity statistics for a domain."""
        result = self.es.search(
            index=self.INDEX_NAME,
            body={
                "query": {"term": {"domain": domain}},
                "size": 0,
                "aggs": {
                    "by_type": {"terms": {"field": "entity_type", "size": 10}},
                    "first_entity": {"min": {"field": "first_seen_timestamp"}},
                    "last_entity": {"max": {"field": "last_seen_timestamp"}},
                    "total_occurrences": {"sum": {"field": "occurrence_count"}},
                },
            },
        )

        aggs = result.get("aggregations", {})

        return {
            "domain": domain,
            "total_unique_entities": result["hits"]["total"]["value"],
            "by_type": {b["key"]: b["doc_count"] for b in aggs.get("by_type", {}).get("buckets", [])},
            "first_entity_seen": aggs.get("first_entity", {}).get("value_as_string"),
            "last_entity_seen": aggs.get("last_entity", {}).get("value_as_string"),
            "total_occurrences": int(aggs.get("total_occurrences", {}).get("value", 0)),
        }


# Convenience functions
async def track_domain_entities(
    domain: str,
    years: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Track entity appearances for a domain."""
    tracker = EntityTimelineTracker()
    appearances = await tracker.track_entity_appearances(domain, years)
    return {
        "domain": domain,
        "entities_tracked": len(appearances),
        "entities": [a.to_dict() for a in appearances.values()],
    }


async def find_new_domain_entities(
    domain: str,
    since_date: str,
) -> List[Dict[str, Any]]:
    """Find entities that appeared after a date."""
    tracker = EntityTimelineTracker()
    return await tracker.find_new_entities(domain, since_date)
