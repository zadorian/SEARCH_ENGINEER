"""
Universal Enrichment Pipeline

For ANY query:
1. GPT-5 Nano generates query variations (name switches, nicknames, transliterations)
2. Firecrawl search with OR queries (4 variations per search) → URLs + markdown
3. Exa search → URLs + text (exclude Firecrawl domains, exact phrase via type='keyword')
4. Extract entities from fetched content (no separate scraping!)
5. Create nodes + edges per relationships.json
6. Index to cymonides-1-{project_id}
"""

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies
_firecrawl_engine = None
_exa_available = False

def _get_firecrawl():
    """Lazy load Firecrawl engine."""
    global _firecrawl_engine
    if _firecrawl_engine is None:
        try:
            from BACKEND.modules.search_engines.firecrawl_search import FirecrawlSearchEngine
            _firecrawl_engine = FirecrawlSearchEngine()
        except ImportError:
            try:
                # Try relative import path
                import sys
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
                from modules.search_engines.firecrawl_search import FirecrawlSearchEngine
                _firecrawl_engine = FirecrawlSearchEngine()
            except ImportError as e:
                logger.error(f"Failed to import FirecrawlSearchEngine: {e}")
    return _firecrawl_engine


def _check_exa():
    """Check if Exa is available."""
    global _exa_available
    try:
        from exa_py import Exa
        _exa_available = bool(os.getenv('EXA_API_KEY'))
    except ImportError:
        _exa_available = False
    return _exa_available


@dataclass
class EnrichmentResult:
    """Result of universal enrichment pipeline."""
    query: str
    variations_generated: List[str] = field(default_factory=list)
    urls_discovered: List[str] = field(default_factory=list)
    content_fetched: int = 0
    entities_extracted: List[Dict] = field(default_factory=list)
    nodes_created: List[Dict] = field(default_factory=list)
    edges_created: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class UniversalEnricher:
    """
    Enrichment pipeline:
    Firecrawl search + Exa search → entity extraction → node/edge creation → indexing

    No separate scraping - both search APIs return content directly.
    """

    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self.index_name = f"cymonides-1-{project_id}"
        self._es = None
        self._extractor = None

    async def _get_elastic(self):
        """Lazy load ElasticService."""
        if self._es is None:
            try:
                from BACKEND.modules.brute.services.elastic_service import ElasticService
                self._es = ElasticService(project_id=self.project_id)
            except ImportError:
                from modules.brute.services.elastic_service import ElasticService
                self._es = ElasticService(project_id=self.project_id)
        return self._es

    async def _get_extractor(self):
        """Lazy load EntityExtractor."""
        if self._extractor is None:
            try:
                from BACKEND.modules.LINKLATER.extraction.entity_extractor import EntityExtractor
                self._extractor = EntityExtractor(use_relationships=True)
            except ImportError:
                from modules.LINKLATER.extraction.entity_extractor import EntityExtractor
                self._extractor = EntityExtractor(use_relationships=True)
        return self._extractor

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""

    def _generate_id(self, entity_type: str, value: str) -> str:
        """Generate deterministic node ID."""
        raw = f"{entity_type}:{value.lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _entity_to_class(self, entity_type: str) -> str:
        """Map entity type to node class."""
        mapping = {
            'person': 'subject',
            'company': 'subject',
            'organization': 'subject',
            'email': 'contact',
            'phone': 'contact',
            'address': 'location',
            'domain': 'location',
            'url': 'location',
        }
        return mapping.get(entity_type.lower(), 'subject')

    async def _generate_variations(self, query: str) -> 'QueryVariations':
        """Generate query variations using GPT-5 Nano."""
        try:
            from .query_variations import generate_variations
            return await generate_variations(query, use_llm=True)
        except ImportError:
            # Fallback: return original query only
            from dataclasses import dataclass, field

            @dataclass
            class FallbackVariations:
                original: str
                groups: List[List[str]] = field(default_factory=list)
                all_variations: List[str] = field(default_factory=list)

                def as_or_queries(self) -> List[str]:
                    return [f'"{self.original}"']

            return FallbackVariations(
                original=query,
                groups=[[query]],
                all_variations=[query]
            )

    async def _firecrawl_search(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search via Firecrawl - returns URLs + markdown content in one call.
        Now runs multiple searches with OR queries for variations.
        """
        engine = _get_firecrawl()
        if not engine:
            logger.warning("Firecrawl engine not available")
            return []

        all_results = []
        seen_urls = set()

        try:
            # Generate variations using GPT-5 Nano
            variations = await self._generate_variations(query)
            or_queries = variations.as_or_queries()

            logger.info(f"Generated {variations.total_variations} variations in {len(or_queries)} OR groups")

            # Run search for each OR query group
            for or_query in or_queries:
                try:
                    # FirecrawlSearchEngine.search() is synchronous
                    results = engine.search(or_query, max_results=limit)

                    # Deduplicate by URL
                    for r in results:
                        url = r.get('url', '')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            r['variation_query'] = or_query  # Track which variation found it
                            all_results.append(r)

                    logger.debug(f"Firecrawl OR query returned {len(results)} results: {or_query[:50]}...")

                except Exception as e:
                    logger.warning(f"Firecrawl search failed for variation: {e}")
                    continue

            logger.info(f"Firecrawl total: {len(all_results)} unique results for '{query}' ({len(or_queries)} searches)")
            return all_results

        except Exception as e:
            logger.error(f"Firecrawl search failed: {e}")
            return []

    async def _exa_search(
        self,
        query: str,
        exclude_domains: List[str],
        limit: int = 10,
        variations: Optional['QueryVariations'] = None
    ) -> List[Dict]:
        """
        Search via Exa with:
        - type='keyword' for exact phrase matching (uses variations)
        - exclude_domains to avoid duplicating Firecrawl results
        - Returns text content directly
        """
        if not _check_exa():
            logger.warning("Exa not available (missing exa_py or EXA_API_KEY)")
            return []

        try:
            from exa_py import Exa
            exa = Exa(api_key=os.getenv('EXA_API_KEY'))

            all_output = []
            seen_urls = set()

            # Get all variations to search
            if variations and variations.all_variations:
                search_queries = variations.all_variations
            else:
                search_queries = [query]

            logger.info(f"Exa searching {len(search_queries)} variations")

            # Search each variation as exact phrase
            for var_query in search_queries:
                try:
                    # Build search params
                    search_params = {
                        'query': var_query,
                        'type': 'keyword',  # Exact phrase matching
                        'use_autoprompt': False,
                        'num_results': limit,
                        'text': True,  # Get full text content
                        'highlights': {
                            'num_sentences': 5,
                            'highlights_per_url': 3
                        }
                    }

                    # Add domain exclusions if we have any
                    if exclude_domains:
                        search_params['exclude_domains'] = exclude_domains[:100]

                    results = exa.search_and_contents(**search_params)

                    # Convert to standard format, deduplicate
                    for result in results.results:
                        if result.url in seen_urls:
                            continue
                        seen_urls.add(result.url)

                        # Combine text content
                        content = ""
                        if hasattr(result, 'text') and result.text:
                            content = result.text
                        elif hasattr(result, 'highlights') and result.highlights:
                            content = ' ... '.join(str(h) for h in result.highlights if h)

                        all_output.append({
                            'url': result.url,
                            'title': result.title or '',
                            'content': content,
                            'source': 'exa',
                            'variation_query': var_query
                        })

                except Exception as e:
                    logger.warning(f"Exa search failed for variation '{var_query}': {e}")
                    continue

            logger.info(f"Exa total: {len(all_output)} unique results (excluded {len(exclude_domains)} domains)")
            return all_output

        except Exception as e:
            logger.error(f"Exa search failed: {e}")
            return []

    async def enrich(
        self,
        query: str,
        firecrawl_limit: int = 10,
        exa_limit: int = 10,
        index_results: bool = True
    ) -> EnrichmentResult:
        """
        Main enrichment pipeline.

        Args:
            query: Search query
            firecrawl_limit: Max results from Firecrawl
            exa_limit: Max results from Exa
            index_results: Whether to index to Elasticsearch

        Returns:
            EnrichmentResult with all discovered entities/nodes/edges
        """
        result = EnrichmentResult(query=query)

        # =====================================================================
        # STEP 0: Generate query variations using GPT-5 Nano
        # =====================================================================
        variations = await self._generate_variations(query)
        result.variations_generated = variations.all_variations
        logger.info(f"Query variations: {variations.all_variations}")

        # =====================================================================
        # STEP 1: Firecrawl search (returns URLs + markdown content)
        # Uses OR queries with 4 variations per search
        # =====================================================================
        firecrawl_results = await self._firecrawl_search(query, firecrawl_limit)

        # Collect URLs and content
        url_content_map: Dict[str, Dict] = {}
        firecrawl_domains: Set[str] = set()

        for item in firecrawl_results:
            url = item.get('url', '')
            if not url:
                continue

            content = item.get('markdown') or item.get('snippet') or ''
            if content:
                url_content_map[url] = {
                    'content': content,
                    'title': item.get('title', ''),
                    'source': 'firecrawl',
                    'variation': item.get('variation_query', query)
                }
                result.urls_discovered.append(url)

                # Track domain for exclusion
                domain = self._extract_domain(url)
                if domain:
                    firecrawl_domains.add(domain)

        logger.info(f"Firecrawl: {len(url_content_map)} URLs with content, {len(firecrawl_domains)} unique domains")

        # =====================================================================
        # STEP 2: Exa search (exclude Firecrawl domains, exact phrase per variation)
        # =====================================================================
        exa_results = await self._exa_search(
            query,
            exclude_domains=list(firecrawl_domains),
            limit=exa_limit,
            variations=variations
        )

        for item in exa_results:
            url = item.get('url', '')
            if not url or url in url_content_map:
                continue

            content = item.get('content', '')
            if content:
                url_content_map[url] = {
                    'content': content,
                    'title': item.get('title', ''),
                    'source': 'exa'
                }
                result.urls_discovered.append(url)

        result.content_fetched = len(url_content_map)
        logger.info(f"Total: {result.content_fetched} URLs with content")

        # =====================================================================
        # STEP 3: Entity extraction from content
        # =====================================================================
        extractor = await self._get_extractor()
        url_entities_map: Dict[str, Dict] = {}

        for url, data in url_content_map.items():
            content = data['content']
            if not content or len(content) < 50:
                continue

            try:
                # EntityExtractor expects HTML, but works with plain text too
                # Wrap in basic HTML for consistent processing
                html_content = f"<html><body>{content}</body></html>"
                entities = await extractor.extract(html_content, url)

                if entities:
                    url_entities_map[url] = entities
                    # Flatten for result
                    for person in entities.get('persons', []):
                        result.entities_extracted.append({
                            'type': 'person',
                            'value': person.get('value', ''),
                            'source_url': url
                        })
                    for company in entities.get('companies', []):
                        result.entities_extracted.append({
                            'type': 'company',
                            'value': company.get('value', ''),
                            'source_url': url
                        })
                    for email in entities.get('emails', []):
                        result.entities_extracted.append({
                            'type': 'email',
                            'value': email.get('value', ''),
                            'source_url': url
                        })
                    for phone in entities.get('phones', []):
                        result.entities_extracted.append({
                            'type': 'phone',
                            'value': phone.get('value', ''),
                            'source_url': url
                        })

            except Exception as e:
                logger.warning(f"Entity extraction failed for {url}: {e}")
                result.errors.append(f"Extraction error for {url}: {str(e)}")

        logger.info(f"Extracted {len(result.entities_extracted)} entities from {len(url_entities_map)} pages")

        # =====================================================================
        # STEP 4: Create nodes and edges
        # =====================================================================
        nodes: List[Dict] = []
        edges: List[Dict] = []
        seen_node_ids: Set[str] = set()

        # Create domain nodes (Location class) for each URL
        for url in url_content_map.keys():
            domain = self._extract_domain(url)
            if not domain:
                continue

            node_id = self._generate_id('domain', domain)
            if node_id not in seen_node_ids:
                seen_node_ids.add(node_id)
                domain_node = {
                    'id': node_id,
                    'label': domain,
                    'node_class': 'location',
                    'class': 'location',
                    'type': 'domain',
                    'typeName': 'Domain',
                    'className': 'Location',
                    'urls': [url],
                    'projectId': self.project_id,
                }
                nodes.append(domain_node)
                result.nodes_created.append(domain_node)

        # Create entity nodes + documented_by edges
        for url, entities_data in url_entities_map.items():
            domain = self._extract_domain(url)
            domain_node_id = self._generate_id('domain', domain) if domain else None

            # Process each entity type
            for entity_type, entity_list in [
                ('person', entities_data.get('persons', [])),
                ('company', entities_data.get('companies', [])),
                ('email', entities_data.get('emails', [])),
                ('phone', entities_data.get('phones', []))
            ]:
                for entity in entity_list:
                    value = entity.get('value', '')
                    if not value:
                        continue

                    entity_node_id = self._generate_id(entity_type, value)

                    # Create entity node if not seen
                    if entity_node_id not in seen_node_ids:
                        seen_node_ids.add(entity_node_id)
                        entity_class = self._entity_to_class(entity_type)

                        entity_node = {
                            'id': entity_node_id,
                            'label': value,
                            'node_class': entity_class,
                            'class': entity_class,
                            'type': entity_type,
                            'typeName': entity_type.capitalize(),
                            'className': entity_class.capitalize(),
                            'projectId': self.project_id,
                            'confidence': entity.get('confidence', 0.8),
                            'archive_urls': entity.get('archive_urls', [url]),
                        }
                        nodes.append(entity_node)
                        result.nodes_created.append(entity_node)

                    # Create documented_by edge: entity → domain (source attribution)
                    if domain_node_id:
                        edge = {
                            'source': entity_node_id,
                            'target': domain_node_id,
                            'type': 'documented_by',
                            'projectId': self.project_id,
                            'url': url,
                        }
                        edges.append(edge)
                        result.edges_created.append(edge)

            # Add relationship edges from extraction
            for edge_data in entities_data.get('edges', []):
                edge = {
                    'source': edge_data.get('source', ''),
                    'target': edge_data.get('target', ''),
                    'type': edge_data.get('type', 'related_to'),
                    'projectId': self.project_id,
                }
                edges.append(edge)
                result.edges_created.append(edge)

        logger.info(f"Created {len(nodes)} nodes and {len(edges)} edges")

        # =====================================================================
        # STEP 5: Index to Elasticsearch
        # =====================================================================
        if index_results and nodes:
            try:
                es = await self._get_elastic()

                # Embed edges in source nodes (CYMONIDES MANDATE)
                node_edges_map: Dict[str, List[Dict]] = {}
                for edge in edges:
                    source_id = edge.get('source', '')
                    if source_id:
                        if source_id not in node_edges_map:
                            node_edges_map[source_id] = []
                        node_edges_map[source_id].append(edge)

                # Add embedded_edges to nodes
                for node in nodes:
                    node_id = node.get('id', '')
                    if node_id in node_edges_map:
                        node['embedded_edges'] = node_edges_map[node_id]

                # Index nodes
                await es.index_batch(nodes)
                logger.info(f"Indexed {len(nodes)} nodes to {self.index_name}")

            except Exception as e:
                logger.error(f"Indexing failed: {e}")
                result.errors.append(f"Indexing error: {str(e)}")

        return result

    async def close(self):
        """Clean up resources."""
        if self._es:
            await self._es.close()


# Convenience function for direct usage
async def enrich_query(
    query: str,
    project_id: str = "default",
    firecrawl_limit: int = 10,
    exa_limit: int = 10
) -> EnrichmentResult:
    """
    Quick enrichment for a single query.

    Usage:
        from BACKEND.modules.LINKLATER.enrichment.universal_enricher import enrich_query
        result = await enrich_query("John Smith Acme Corp")
    """
    enricher = UniversalEnricher(project_id=project_id)
    try:
        return await enricher.enrich(
            query,
            firecrawl_limit=firecrawl_limit,
            exa_limit=exa_limit
        )
    finally:
        await enricher.close()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    async def main():
        query = sys.argv[1] if len(sys.argv) > 1 else "Viktor Orban corruption"
        print(f"\nEnriching query: '{query}'\n")

        result = await enrich_query(query, project_id="test")

        print(f"\n{'='*60}")
        print(f"ENRICHMENT RESULT")
        print(f"{'='*60}")
        print(f"Query: {result.query}")
        print(f"URLs discovered: {len(result.urls_discovered)}")
        print(f"Content fetched: {result.content_fetched}")
        print(f"Entities extracted: {len(result.entities_extracted)}")
        print(f"Nodes created: {len(result.nodes_created)}")
        print(f"Edges created: {len(result.edges_created)}")

        if result.entities_extracted:
            print(f"\nSample entities:")
            for e in result.entities_extracted[:10]:
                print(f"  - [{e['type']}] {e['value']}")

        if result.errors:
            print(f"\nErrors: {result.errors}")

    asyncio.run(main())
