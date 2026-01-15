#!/usr/bin/env python3
"""
JESTER C-1 Bridge - Index crawled URLs to Cymonides-1 project graph.

JESTER maps/crawls live sites. That's all it does.
- Scrapes current sites
- Crawls them
- Outputs URLs it found

Links (in/outbound) are LINKLATER's job.
Entity extraction is PACMAN's job.
Archive pulls (CC/Wayback) are BACKDRILL's job.
ALLDOM orchestrates everything.

Node Types:
- url (LOCATION): Web pages crawled/mapped
- domain (LOCATION): Domain cluster parent for URLs

Edge Types:
- url_of: URL -> domain (cluster membership)
"""

import json
import hashlib
import os
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import urlparse

try:
    from elasticsearch import Elasticsearch
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JESTER.C1Bridge")


@dataclass
class EmbeddedEdge:
    """Edge embedded within a node for C-1 indexing."""
    target_id: str
    target_class: str
    target_type: str
    target_label: str
    relation: str
    direction: str = "outgoing"
    confidence: float = 1.0
    verification_status: str = "VERIFIED"
    connection_reason: str = ""


@dataclass
class C1Node:
    """Node for C-1 graph index."""
    id: str
    node_class: str  # LOCATION
    type: str  # url, domain
    canonicalValue: str
    label: str
    value: str
    embedded_edges: List[Dict] = None
    metadata: Dict = None
    source_system: str = "jester"
    comment: str = None
    createdAt: str = None
    updatedAt: str = None
    lastSeen: str = None

    def __post_init__(self):
        if self.embedded_edges is None:
            self.embedded_edges = []
        if self.metadata is None:
            self.metadata = {}
        now = datetime.utcnow().isoformat()
        if self.createdAt is None:
            self.createdAt = now
        if self.updatedAt is None:
            self.updatedAt = now
        if self.lastSeen is None:
            self.lastSeen = now


class JesterC1Bridge:
    """Bridge JESTER crawl results to Cymonides-1 project index. URLs only."""

    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self.index_name = f"cymonides-1-{project_id}"
        self.es = None

        if ES_AVAILABLE:
            es_host = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
            try:
                self.es = Elasticsearch([es_host])
                if not self.es.indices.exists(index=self.index_name):
                    self.es.indices.create(index=self.index_name, body={
                        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                        "mappings": {
                            "properties": {
                                "id": {"type": "keyword"},
                                "node_class": {"type": "keyword"},
                                "type": {"type": "keyword"},
                                "canonicalValue": {"type": "keyword"},
                                "label": {"type": "text"},
                                "value": {"type": "text"},
                                "source_system": {"type": "keyword"},
                                "embedded_edges": {"type": "nested"},
                                "metadata": {"type": "object"},
                                "createdAt": {"type": "date"},
                                "updatedAt": {"type": "date"},
                                "lastSeen": {"type": "date"},
                            }
                        }
                    })
            except Exception as e:
                logger.warning(f"Elasticsearch connection failed: {e}")
                self.es = None

        self.results_root = Path(__file__).resolve().parent / 'results' / 'c1_nodes'
        self.results_root.mkdir(parents=True, exist_ok=True)

    def _generate_id(self, type_prefix: str, value: str) -> str:
        """Generate deterministic node ID."""
        raw = f"{type_prefix}:{str(value).lower().strip()}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    def _extract_domain(self, url: str) -> Optional[str]:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain if domain else None
        except Exception:
            return None

    def create_domain_node(self, domain: str, metadata: Dict = None) -> C1Node:
        """Create a domain node (LOCATION class, cluster parent)."""
        node_id = self._generate_id('domain', domain)
        return C1Node(
            id=node_id,
            node_class="LOCATION",
            type="domain",
            canonicalValue=domain.lower().strip(),
            label=domain,
            value=domain,
            metadata=metadata or {},
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
        node_id = self._generate_id('url', url)

        if not domain:
            domain = self._extract_domain(url)

        url_node = C1Node(
            id=node_id,
            node_class="LOCATION",
            type="url",
            canonicalValue=url.lower().strip(),
            label=title or url,
            value=url,
            metadata=metadata or {},
        )

        domain_node = None
        if domain:
            domain_node = self.create_domain_node(domain)

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
        """Save node to Elasticsearch and file backup."""
        node_dict = asdict(node)

        try:
            filename = f"{node.type}_{node.id}_{int(time.time())}.json"
            file_path = self.results_root / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(node_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"File save failed: {e}")

        if self.es:
            try:
                self.es.index(index=self.index_name, id=node.id, body=node_dict)
                return True
            except Exception as e:
                logger.warning(f"ES index failed for {node.id}: {e}")
                return False

        return True

    def index_crawl_result(
        self,
        urls: List[str],
        titles: Dict[str, str] = None,
        metadata: Dict = None
    ) -> Dict[str, Any]:
        """
        Index JESTER crawl results. URLs only.

        Args:
            urls: List of URLs crawled/mapped
            titles: Optional dict mapping URL -> page title
            metadata: Additional metadata (crawl timestamp, etc.)

        Returns:
            Dict with indexing stats
        """
        titles = titles or {}
        metadata = metadata or {}

        stats = {
            "urls_indexed": 0,
            "domains_indexed": 0,
            "errors": []
        }

        seen_domains = set()

        for url in urls:
            try:
                title = titles.get(url, "")
                url_node, domain_node = self.create_url_node(
                    url,
                    title=title,
                    metadata=metadata
                )

                if self._save_node(url_node):
                    stats["urls_indexed"] += 1

                if domain_node and domain_node.canonicalValue not in seen_domains:
                    if self._save_node(domain_node):
                        stats["domains_indexed"] += 1
                    seen_domains.add(domain_node.canonicalValue)

            except Exception as e:
                stats["errors"].append(f"{url}: {str(e)}")
                logger.error(f"Index failed for {url}: {e}")

        return stats

    def index_single_url(
        self,
        url: str,
        title: str = "",
        metadata: Dict = None
    ) -> Dict[str, Any]:
        """Index a single URL from jester crawl."""
        return self.index_crawl_result(
            urls=[url],
            titles={url: title} if title else None,
            metadata=metadata
        )


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="JESTER C-1 Bridge - URLs only")
    parser.add_argument("--url", help="Single URL to index")
    parser.add_argument("--urls", help="Comma-separated URLs to index")
    parser.add_argument("--title", help="Page title (for single URL)", default="")
    parser.add_argument("--project", help="Project ID", default="default")

    args = parser.parse_args()

    bridge = JesterC1Bridge(project_id=args.project)

    if args.url:
        result = bridge.index_single_url(url=args.url, title=args.title)
    elif args.urls:
        urls = [u.strip() for u in args.urls.split(",") if u.strip()]
        result = bridge.index_crawl_result(urls=urls)
    else:
        print("Provide --url or --urls")
        exit(1)

    print(json.dumps(result, indent=2))
