"""
Domain Filetype Index Manager

Elasticsearch index for storing domain filetype profiles.
Enables instant lookups during link discovery to prioritize
domains hosting PDFs and other documents.

Usage:
    from modules.linklater.mapping.filetype_index import (
        FiletypeIndexManager,
        FiletypeProfile
    )

    manager = FiletypeIndexManager()
    await manager.ensure_index()

    # Upsert profile
    profile = FiletypeProfile(
        domain="example.com",
        filetypes={"pdf": 45, "doc": 12},
        pdf_count=45,
        total_documents=57,
        has_annual_reports=True,
        document_authority_score=75.0
    )
    await manager.upsert_profile(profile)

    # Batch lookup during link discovery
    profiles = await manager.batch_lookup(["example.com", "test.org"])
"""

import os
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
import aiohttp

logger = logging.getLogger(__name__)

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
INDEX_NAME = "cc_domain_filetypes"


@dataclass
class FiletypeProfile:
    """
    Domain filetype profile for credibility scoring.

    Attributes:
        domain: The domain (e.g., "example.com")
        filetypes: Dict mapping extension to count (e.g., {"pdf": 45, "doc": 12})
        pdf_count: Number of PDFs found (convenience field)
        doc_count: Number of DOC/DOCX files
        xls_count: Number of XLS/XLSX files
        total_documents: Total document count across all types
        has_annual_reports: Whether annual reports were detected
        document_authority_score: Computed authority score (0-100)
        sample_urls: Sample document URLs for verification
        first_indexed: When domain was first indexed
        last_updated: Last update timestamp
        source: Data source (e.g., "cc_index", "discovery")
    """
    domain: str
    filetypes: Dict[str, int] = field(default_factory=dict)
    pdf_count: int = 0
    doc_count: int = 0
    xls_count: int = 0
    total_documents: int = 0
    has_annual_reports: bool = False
    document_authority_score: float = 0.0
    sample_urls: List[str] = field(default_factory=list)
    first_indexed: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ES indexing."""
        return {
            "domain": self.domain,
            "filetypes": self.filetypes,
            "pdf_count": self.pdf_count,
            "doc_count": self.doc_count,
            "xls_count": self.xls_count,
            "total_documents": self.total_documents,
            "has_annual_reports": self.has_annual_reports,
            "document_authority_score": self.document_authority_score,
            "sample_urls": self.sample_urls[:10],  # Limit to 10
            "first_indexed": self.first_indexed,
            "last_updated": self.last_updated,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FiletypeProfile":
        """Create from ES document."""
        return cls(
            domain=data.get("domain", ""),
            filetypes=data.get("filetypes", {}),
            pdf_count=data.get("pdf_count", 0),
            doc_count=data.get("doc_count", 0),
            xls_count=data.get("xls_count", 0),
            total_documents=data.get("total_documents", 0),
            has_annual_reports=data.get("has_annual_reports", False),
            document_authority_score=data.get("document_authority_score", 0.0),
            sample_urls=data.get("sample_urls", []),
            first_indexed=data.get("first_indexed", ""),
            last_updated=data.get("last_updated", ""),
            source=data.get("source", "unknown"),
        )


# ES Index Mapping
INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 2,
        "number_of_replicas": 1,
        "index": {
            "refresh_interval": "5s"
        }
    },
    "mappings": {
        "properties": {
            "domain": {"type": "keyword"},
            "filetypes": {"type": "object", "enabled": True},
            "pdf_count": {"type": "integer"},
            "doc_count": {"type": "integer"},
            "xls_count": {"type": "integer"},
            "total_documents": {"type": "integer"},
            "has_annual_reports": {"type": "boolean"},
            "document_authority_score": {"type": "float"},
            "sample_urls": {"type": "keyword", "index": False},
            "first_indexed": {"type": "date"},
            "last_updated": {"type": "date"},
            "source": {"type": "keyword"}
        }
    }
}


class FiletypeIndexManager:
    """
    Elasticsearch index manager for domain filetype profiles.

    Provides:
    - Index creation and management
    - Profile upsert (insert or update)
    - Batch lookup for efficient discovery integration
    - Statistics and monitoring
    """

    def __init__(self, es_url: str = None, index_name: str = None):
        """
        Initialize index manager.

        Args:
            es_url: Elasticsearch URL (default: from env)
            index_name: Index name (default: cc_domain_filetypes)
        """
        self.es_url = es_url or ES_URL
        self.index_name = index_name or INDEX_NAME

    async def ensure_index(self) -> bool:
        """
        Create the index if it doesn't exist.

        Returns:
            True if index exists or was created successfully
        """
        async with aiohttp.ClientSession() as session:
            # Check if exists
            async with session.head(f"{self.es_url}/{self.index_name}") as resp:
                if resp.status == 200:
                    logger.debug(f"Index {self.index_name} already exists")
                    return True

            # Create index
            async with session.put(
                f"{self.es_url}/{self.index_name}",
                json=INDEX_MAPPING,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status in (200, 201):
                    logger.info(f"Created index {self.index_name}")
                    return True
                else:
                    error = await resp.text()
                    logger.error(f"Failed to create index: {error}")
                    return False

    async def upsert_profile(self, profile: FiletypeProfile) -> bool:
        """
        Insert or update a domain profile.

        Uses domain as document ID for idempotent updates.

        Args:
            profile: FiletypeProfile to upsert

        Returns:
            True if successful
        """
        await self.ensure_index()

        # Update timestamp
        profile.last_updated = datetime.utcnow().isoformat()

        doc = profile.to_dict()

        async with aiohttp.ClientSession() as session:
            # Use _doc endpoint with domain as ID
            url = f"{self.es_url}/{self.index_name}/_doc/{profile.domain}"

            async with session.put(
                url,
                json=doc,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status in (200, 201):
                    logger.debug(f"Upserted profile for {profile.domain}")
                    return True
                else:
                    error = await resp.text()
                    logger.error(f"Failed to upsert {profile.domain}: {error}")
                    return False

    async def get_profile(self, domain: str) -> Optional[FiletypeProfile]:
        """
        Get a single domain's profile.

        Args:
            domain: Domain to lookup

        Returns:
            FiletypeProfile or None if not found
        """
        async with aiohttp.ClientSession() as session:
            url = f"{self.es_url}/{self.index_name}/_doc/{domain}"

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    source = data.get("_source", {})
                    return FiletypeProfile.from_dict(source)
                elif resp.status == 404:
                    return None
                else:
                    logger.error(f"Error fetching profile for {domain}: {resp.status}")
                    return None

    async def batch_lookup(self, domains: List[str]) -> Dict[str, FiletypeProfile]:
        """
        Batch lookup filetype profiles for multiple domains.

        This is the primary method used during link discovery to
        efficiently score many linking domains at once.

        Args:
            domains: List of domains to lookup

        Returns:
            Dict mapping domain -> FiletypeProfile (only found domains)

        Example:
            profiles = await manager.batch_lookup([
                "example.com",
                "test.org",
                "unknown.net"
            ])
            # profiles = {"example.com": FiletypeProfile(...), "test.org": ...}
            # "unknown.net" not in dict because not found
        """
        if not domains:
            return {}

        # Remove duplicates and normalize
        unique_domains = list(set(d.lower().strip() for d in domains if d))

        if not unique_domains:
            return {}

        query = {
            "query": {
                "terms": {
                    "domain": unique_domains
                }
            },
            "size": len(unique_domains)
        }

        async with aiohttp.ClientSession() as session:
            url = f"{self.es_url}/{self.index_name}/_search"

            async with session.post(
                url,
                json=query,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    logger.error(f"Batch lookup failed: {error}")
                    return {}

                data = await resp.json()
                hits = data.get("hits", {}).get("hits", [])

                profiles = {}
                for hit in hits:
                    source = hit.get("_source", {})
                    profile = FiletypeProfile.from_dict(source)
                    profiles[profile.domain] = profile

                logger.debug(f"Batch lookup: {len(profiles)}/{len(unique_domains)} found")
                return profiles

    async def delete_profile(self, domain: str) -> bool:
        """Delete a domain's profile."""
        async with aiohttp.ClientSession() as session:
            url = f"{self.es_url}/{self.index_name}/_doc/{domain}"

            async with session.delete(url) as resp:
                return resp.status in (200, 204)

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get index statistics.

        Returns:
            Dict with count, coverage, and other metrics
        """
        async with aiohttp.ClientSession() as session:
            # Get document count
            count_url = f"{self.es_url}/{self.index_name}/_count"
            async with session.get(count_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    doc_count = data.get("count", 0)
                else:
                    doc_count = 0

            # Get aggregations
            agg_query = {
                "size": 0,
                "aggs": {
                    "avg_pdf_count": {"avg": {"field": "pdf_count"}},
                    "avg_authority": {"avg": {"field": "document_authority_score"}},
                    "with_annual_reports": {
                        "filter": {"term": {"has_annual_reports": True}}
                    },
                    "by_source": {
                        "terms": {"field": "source", "size": 10}
                    }
                }
            }

            search_url = f"{self.es_url}/{self.index_name}/_search"
            async with session.post(
                search_url,
                json=agg_query,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    aggs = data.get("aggregations", {})

                    return {
                        "total_domains": doc_count,
                        "avg_pdf_count": aggs.get("avg_pdf_count", {}).get("value", 0),
                        "avg_authority_score": aggs.get("avg_authority", {}).get("value", 0),
                        "domains_with_annual_reports": aggs.get("with_annual_reports", {}).get("doc_count", 0),
                        "by_source": {
                            bucket["key"]: bucket["doc_count"]
                            for bucket in aggs.get("by_source", {}).get("buckets", [])
                        }
                    }
                else:
                    return {"total_domains": doc_count}

    async def search_domains(
        self,
        min_pdf_count: int = 0,
        min_authority: float = 0,
        has_annual_reports: Optional[bool] = None,
        limit: int = 100
    ) -> List[FiletypeProfile]:
        """
        Search for domains matching criteria.

        Args:
            min_pdf_count: Minimum PDF count
            min_authority: Minimum authority score
            has_annual_reports: Filter by annual report presence
            limit: Maximum results

        Returns:
            List of matching profiles
        """
        must_clauses = []

        if min_pdf_count > 0:
            must_clauses.append({"range": {"pdf_count": {"gte": min_pdf_count}}})

        if min_authority > 0:
            must_clauses.append({"range": {"document_authority_score": {"gte": min_authority}}})

        if has_annual_reports is not None:
            must_clauses.append({"term": {"has_annual_reports": has_annual_reports}})

        query = {
            "query": {
                "bool": {"must": must_clauses} if must_clauses else {"match_all": {}}
            },
            "size": limit,
            "sort": [{"document_authority_score": "desc"}]
        }

        async with aiohttp.ClientSession() as session:
            url = f"{self.es_url}/{self.index_name}/_search"

            async with session.post(
                url,
                json=query,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                hits = data.get("hits", {}).get("hits", [])

                return [
                    FiletypeProfile.from_dict(hit.get("_source", {}))
                    for hit in hits
                ]


# Convenience functions
async def get_filetype_profile(domain: str) -> Optional[FiletypeProfile]:
    """Get a single domain's filetype profile."""
    manager = FiletypeIndexManager()
    return await manager.get_profile(domain)


async def batch_lookup_filetypes(domains: List[str]) -> Dict[str, FiletypeProfile]:
    """Batch lookup filetype profiles."""
    manager = FiletypeIndexManager()
    return await manager.batch_lookup(domains)
