#!/usr/bin/env python3
"""
LINKLATER -> Cymonides-1 Bridge

LINKLATER finds link relationships:
- Outbound links (from target domain to external)
- Inbound links/backlinks (from external to target domain)

Uses: JESTER for scraping, BACKDRILL for archives, Majestic for backlinks.
Entity extraction is PACMAN's job - NOT here.

Node Types:
- url (LOCATION): Web pages
- domain (LOCATION): Domain cluster parent for URLs

Edge Types:
- url_of: URL -> domain (cluster membership)
- backlink: URL -> URL (external page links TO target)
- outlink: URL -> URL (target page links TO external)

Usage:
    from c1_bridge import LinklaterC1Bridge

    bridge = LinklaterC1Bridge(project_id="my-project")

    # Index backlinks found for a domain
    stats = bridge.index_backlinks(target_domain="example.com", backlinks=[...])

    # Index outlinks from a page
    stats = bridge.index_outlinks(source_url="https://example.com/page", outlinks=[...])
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse

try:
    from elasticsearch import Elasticsearch, helpers
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False

logger = logging.getLogger(__name__)

DEFAULT_INDEX = "cymonides-1-linklater"


@dataclass
class EmbeddedEdge:
    """Edge embedded within a node document."""
    target_id: str
    target_class: str
    target_type: str
    target_label: str
    relation: str
    direction: str = "outgoing"
    confidence: float = 1.0
    verification_status: str = "VERIFIED"
    connection_reason: str = ""
    metadata: Dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class C1Node:
    """Node for cymonides-1-{projectId} index."""
    id: str
    node_class: str = "LOCATION"
    type: str = "url"
    label: str = ""
    canonicalValue: str = ""
    value: str = ""
    metadata: Dict = field(default_factory=dict)
    source_system: str = "linklater"
    embedded_edges: List[Dict] = field(default_factory=list)
    createdAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updatedAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    lastSeen: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    projectId: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


class LinklaterC1Bridge:
    """
    Bridge from linklater link discovery to Cymonides-1 graph.

    ONLY handles:
    - URL nodes (LOCATION/url)
    - Domain nodes (LOCATION/domain)
    - Link edges (backlink, outlink)

    Does NOT handle entities - that's PACMAN's job.
    """

    MAPPING = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "node_class": {"type": "keyword"},
                "type": {"type": "keyword"},
                "label": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "canonicalValue": {"type": "keyword"},
                "value": {"type": "text"},
                "source_system": {"type": "keyword"},
                "projectId": {"type": "keyword"},
                "createdAt": {"type": "date"},
                "updatedAt": {"type": "date"},
                "lastSeen": {"type": "date"},
                "metadata": {"type": "object", "enabled": False},
                "embedded_edges": {
                    "type": "nested",
                    "properties": {
                        "target_id": {"type": "keyword"},
                        "target_class": {"type": "keyword"},
                        "target_type": {"type": "keyword"},
                        "target_label": {"type": "text"},
                        "relation": {"type": "keyword"},
                        "direction": {"type": "keyword"},
                        "confidence": {"type": "float"},
                        "verification_status": {"type": "keyword"},
                        "connection_reason": {"type": "keyword"},
                        "created_at": {"type": "date"}
                    }
                }
            }
        }
    }

    def __init__(self, project_id: str = None):
        self.project_id = project_id
        self.es = None

        if ES_AVAILABLE:
            es_host = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
            try:
                self.es = Elasticsearch([es_host])
                self._ensure_index()
            except Exception as e:
                logger.warning(f"Elasticsearch connection failed: {e}")

    def _get_index_name(self) -> str:
        if self.project_id:
            return f"cymonides-1-{self.project_id}"
        return DEFAULT_INDEX

    def _ensure_index(self) -> None:
        if not self.es:
            return
        index_name = self._get_index_name()
        if not self.es.indices.exists(index=index_name):
            logger.info(f"Creating index: {index_name}")
            self.es.indices.create(index=index_name, body=self.MAPPING)

    def _generate_id(self, type_prefix: str, value: str) -> str:
        """Generate deterministic node ID."""
        key = f"{type_prefix}:{value.lower().strip()}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _extract_domain(self, url: str) -> Optional[str]:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain if domain else None
        except:
            return None

    def create_domain_node(self, domain: str, metadata: Dict = None) -> C1Node:
        """Create a domain node (LOCATION class, cluster parent)."""
        node_id = self._generate_id("domain", domain)
        return C1Node(
            id=node_id,
            node_class="LOCATION",
            type="domain",
            label=domain,
            canonicalValue=domain.lower().strip(),
            value=domain,
            metadata=metadata or {},
            projectId=self.project_id
        )

    def create_url_node(
        self,
        url: str,
        title: str = "",
        domain: str = None,
        metadata: Dict = None
    ) -> Tuple[C1Node, Optional[C1Node]]:
        """
        Create URL node with url_of edge to domain.

        Returns:
            Tuple of (url_node, domain_node)
        """
        if not domain:
            domain = self._extract_domain(url)

        node_id = self._generate_id("url", url)

        url_node = C1Node(
            id=node_id,
            node_class="LOCATION",
            type="url",
            label=title or url,
            canonicalValue=url.lower().strip(),
            value=url,
            metadata=metadata or {},
            projectId=self.project_id
        )

        domain_node = None
        if domain:
            domain_node = self.create_domain_node(domain)

            # Add url_of edge
            url_of_edge = EmbeddedEdge(
                target_id=domain_node.id,
                target_class="LOCATION",
                target_type="domain",
                target_label=domain,
                relation="url_of",
                direction="outgoing",
                confidence=1.0,
                verification_status="VERIFIED",
                connection_reason="url_domain_membership"
            )
            url_node.embedded_edges.append(asdict(url_of_edge))

        return url_node, domain_node

    def _save_node(self, node: C1Node) -> bool:
        """Save node to Elasticsearch."""
        if not self.es:
            return False
        try:
            self.es.index(
                index=self._get_index_name(),
                id=node.id,
                body=node.to_dict()
            )
            return True
        except Exception as e:
            logger.warning(f"ES index failed for {node.id}: {e}")
            return False

    def index_backlinks(
        self,
        target_domain: str,
        backlinks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Index backlinks pointing TO a target domain.

        Args:
            target_domain: Domain receiving the backlinks
            backlinks: List of backlink dicts with 'source_url', optionally 'target_url', 'anchor_text'

        Returns:
            Stats dict
        """
        stats = {
            "target_domain": target_domain,
            "urls_indexed": 0,
            "domains_indexed": 0,
            "backlink_edges": 0,
            "errors": []
        }

        seen_domains = set()

        # Create target domain node
        target_domain_node = self.create_domain_node(target_domain)
        if self._save_node(target_domain_node):
            stats["domains_indexed"] += 1
        seen_domains.add(target_domain)

        for bl in backlinks:
            source_url = bl.get('source_url') or bl.get('url', '')
            target_url = bl.get('target_url', f"https://{target_domain}/")
            anchor_text = bl.get('anchor_text', '')

            if not source_url:
                continue

            try:
                # Create source URL node (the page linking TO target)
                source_url_node, source_domain_node = self.create_url_node(
                    url=source_url,
                    title=bl.get('title', ''),
                    metadata={
                        "anchor_text": anchor_text,
                        "source": bl.get('source', 'linklater'),
                        "discovered_at": bl.get('timestamp')
                    }
                )

                # Add backlink edge: source_url -> target_domain (or target_url)
                target_id = self._generate_id("url", target_url) if target_url else target_domain_node.id
                target_type = "url" if target_url else "domain"
                target_label = target_url if target_url else target_domain

                backlink_edge = EmbeddedEdge(
                    target_id=target_id,
                    target_class="LOCATION",
                    target_type=target_type,
                    target_label=target_label,
                    relation="backlink",
                    direction="outgoing",
                    confidence=0.95,
                    verification_status="VERIFIED",
                    connection_reason="backlink_discovery",
                    metadata={"anchor_text": anchor_text}
                )
                source_url_node.embedded_edges.append(asdict(backlink_edge))

                # Save source URL node
                if self._save_node(source_url_node):
                    stats["urls_indexed"] += 1
                    stats["backlink_edges"] += 1

                # Save source domain node if new
                if source_domain_node:
                    source_domain = source_domain_node.canonicalValue
                    if source_domain not in seen_domains:
                        if self._save_node(source_domain_node):
                            stats["domains_indexed"] += 1
                        seen_domains.add(source_domain)

            except Exception as e:
                stats["errors"].append(f"{source_url}: {str(e)}")

        return stats

    def index_outlinks(
        self,
        source_url: str,
        outlinks: List[str],
        source_title: str = "",
        metadata: Dict = None
    ) -> Dict[str, Any]:
        """
        Index outlinks FROM a source URL to external URLs.

        Args:
            source_url: URL that contains the outlinks
            outlinks: List of external URLs linked from source
            source_title: Title of source page
            metadata: Additional metadata

        Returns:
            Stats dict
        """
        stats = {
            "source_url": source_url,
            "urls_indexed": 0,
            "domains_indexed": 0,
            "outlink_edges": 0,
            "errors": []
        }

        seen_domains = set()

        # Create source URL node
        source_url_node, source_domain_node = self.create_url_node(
            url=source_url,
            title=source_title,
            metadata=metadata or {}
        )

        # Add outlink edges
        for outlink in outlinks[:100]:  # Limit
            try:
                target_id = self._generate_id("url", outlink)
                target_domain = self._extract_domain(outlink) or ""

                outlink_edge = EmbeddedEdge(
                    target_id=target_id,
                    target_class="LOCATION",
                    target_type="url",
                    target_label=outlink,
                    relation="outlink",
                    direction="outgoing",
                    confidence=1.0,
                    verification_status="VERIFIED",
                    connection_reason="outlink_extraction"
                )
                source_url_node.embedded_edges.append(asdict(outlink_edge))
                stats["outlink_edges"] += 1

            except Exception as e:
                stats["errors"].append(f"{outlink}: {str(e)}")

        # Save source URL node
        if self._save_node(source_url_node):
            stats["urls_indexed"] += 1

        # Save source domain
        if source_domain_node:
            if self._save_node(source_domain_node):
                stats["domains_indexed"] += 1
            seen_domains.add(source_domain_node.canonicalValue)

        # Create target URL/domain nodes for outlinks
        for outlink in outlinks[:50]:
            try:
                out_url_node, out_domain_node = self.create_url_node(
                    url=outlink,
                    metadata={"source": "outlink", "found_on": source_url}
                )

                if self._save_node(out_url_node):
                    stats["urls_indexed"] += 1

                if out_domain_node and out_domain_node.canonicalValue not in seen_domains:
                    if self._save_node(out_domain_node):
                        stats["domains_indexed"] += 1
                    seen_domains.add(out_domain_node.canonicalValue)

            except Exception as e:
                stats["errors"].append(f"{outlink}: {str(e)}")

        return stats

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        if not self.es:
            return {"error": "No ES connection"}

        index_name = self._get_index_name()

        if not self.es.indices.exists(index=index_name):
            return {"exists": False}

        total = self.es.count(index=index_name)["count"]

        stats = {
            "exists": True,
            "index": index_name,
            "total_nodes": total,
            "by_type": {}
        }

        for typ in ["url", "domain"]:
            count = self.es.count(
                index=index_name,
                body={"query": {"term": {"type": typ}}}
            )["count"]
            if count > 0:
                stats["by_type"][typ] = count

        return stats


# Backward compatibility alias
C1Bridge = LinklaterC1Bridge


# CLI
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="LINKLATER C-1 Bridge - Links only")
    parser.add_argument("--project", "-p", help="Project ID")
    parser.add_argument("--stats", action="store_true", help="Show index stats")
    parser.add_argument("--test", action="store_true", help="Run test indexing")

    args = parser.parse_args()

    bridge = LinklaterC1Bridge(project_id=args.project)

    if args.stats:
        stats = bridge.get_stats()
        print(json.dumps(stats, indent=2))

    elif args.test:
        # Test backlinks
        backlinks = [
            {"source_url": "https://techcrunch.com/article", "anchor_text": "example site"},
            {"source_url": "https://news.ycombinator.com/item?id=123", "anchor_text": "link"},
        ]
        stats = bridge.index_backlinks("example.com", backlinks)
        print("Backlinks indexed:")
        print(json.dumps(stats, indent=2))

        # Test outlinks
        stats = bridge.index_outlinks(
            source_url="https://example.com/page",
            outlinks=["https://nytimes.com/story", "https://github.com/repo"],
            source_title="Example Page"
        )
        print("\nOutlinks indexed:")
        print(json.dumps(stats, indent=2))
