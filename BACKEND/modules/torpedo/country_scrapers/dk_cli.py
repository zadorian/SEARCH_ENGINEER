#!/usr/bin/env python3
"""
Denmark Unified CLI - Single Entry Point for Denmark Public Records
====================================================================

Combines ALL Denmark public records sources into one unified interface:
1. CVR (Central Business Register) via Virk API
2. Finanstilsynet (Financial Regulator)
3. Statstidende (Official Gazette)
4. Tinglysning (Land Registry)

Designed to integrate with io_cli.py for unified routing.

OPERATOR SYNTAX:
    cdk: <company>      - Denmark company search (CVR/Virk)
    pdk: <person>       - Denmark person search (directors, beneficial owners)
    regdk: <query>      - Denmark regulatory search (Finanstilsynet)
    litdk: <query>      - Denmark litigation/gazette (Statstidende)
    crdk: <company>     - Denmark corporate registry (CVR direct lookup)
    propdk: <company>   - Denmark property search (Tinglysning)

USAGE:
    # From command line
    python dk_cli.py "cdk: Novo Nordisk"
    python dk_cli.py "pdk: Lars Jensen"
    python dk_cli.py "regdk: bank"
    python dk_cli.py "propdk: Carlsberg"

    # From io_cli.py
    python io_cli.py "cdk: Novo Nordisk"

    # As Python module
    from country_engines.DK.dk_cli import DKCLI
    dk = DKCLI()
    results = await dk.execute("cdk: Novo Nordisk")

ENV VARS:
    VIRK_API_KEY         - Virk API key (optional, enhances data)
    FINANSTILSYNET_KEY   - Finanstilsynet API key (optional)
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict

# Project root for imports
PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_PATH = PROJECT_ROOT / "BACKEND" / "modules"

# Add paths
sys.path.insert(0, str(BACKEND_PATH))
sys.path.insert(0, str(PROJECT_ROOT / "input_output" / "matrix"))

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger("dk_cli")


# =============================================================================
# DK OPERATOR DEFINITIONS
# =============================================================================

DK_OPERATORS = {
    'cdk:': {
        'name': 'Denmark Company Search',
        'entity_type': 'company',
        'category': 'cr',
        'sources': ['cvr_virk', 'opencorporates'],
        'description': 'Search Denmark company registries (CVR/Virk)',
    },
    'pdk:': {
        'name': 'Denmark Person Search',
        'entity_type': 'person',
        'category': 'cr',
        'sources': ['cvr_virk_directors', 'cvr_virk_owners'],
        'description': 'Search Denmark person records (directors, beneficial owners)',
    },
    'regdk:': {
        'name': 'Denmark Regulatory Search',
        'entity_type': 'company',
        'category': 'reg',
        'sources': ['finanstilsynet'],
        'description': 'Search Finanstilsynet regulated entities',
    },
    'litdk:': {
        'name': 'Denmark Litigation/Gazette',
        'entity_type': 'company',
        'category': 'lit',
        'sources': ['statstidende'],
        'description': 'Search Statstidende (official gazette) for insolvency and legal notices',
    },
    'crdk:': {
        'name': 'Denmark Corporate Registry',
        'entity_type': 'company',
        'category': 'cr',
        'sources': ['cvr_virk'],
        'description': 'CVR direct lookup by CVR number or company name',
    },
    'propdk:': {
        'name': 'Denmark Property Search',
        'entity_type': 'company',
        'category': 'ass',
        'sources': ['tinglysning'],
        'description': 'Search Tinglysning (land registry) for property ownership',
    },
    'wikidk:': {
        'name': 'DK Wiki Sources',
        'entity_type': 'source',
        'category': 'wiki',
        'sources': ['wiki_sections', 'edith_injections'],
        'description': 'DK jurisdiction guides, tips, source intelligence',
    },
    'newsdk:': {
        'name': 'DK News Search',
        'entity_type': 'article',
        'category': 'news',
        'sources': ['news_recipes', 'torpedo_news'],
        'description': 'Search Denmark news sites via Torpedo',
    },
    'tmpldk:': {
        'name': 'DK EDITH Templates',
        'entity_type': 'template',
        'category': 'templates',
        'sources': ['edith_templates'],
        'description': 'DK writing templates for reports (CVR, Finanstilsynet)',
    },
}


# =============================================================================
# RESULT DATACLASS
# =============================================================================

@dataclass
class DKSearchResult:
    """Unified Denmark search result."""
    operator: str
    query: str
    entity_type: str
    jurisdiction: str = "DK"

    # Results from each source
    results: Dict[str, List[Dict]] = field(default_factory=dict)

    # Aggregated entities
    companies: List[Dict] = field(default_factory=list)
    persons: List[Dict] = field(default_factory=list)
    properties: List[Dict] = field(default_factory=list)
    documents: List[Dict] = field(default_factory=list)

    # Execution metadata
    sources_queried: List[str] = field(default_factory=list)
    sources_succeeded: List[str] = field(default_factory=list)
    sources_failed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Timing
    execution_time_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None and v != [] and v != {}}


# =============================================================================
# DK UNIFIED CLI CLASS
# =============================================================================

class DKCLI:
    """
    Unified Denmark Public Records CLI.

    Routes DK operators to appropriate sources and aggregates results.
    """

    def __init__(self):
        self._virk_api = None  # Virk API (CVR)
        self._cr = None  # Company Registry module (dk_cr)
        self._reg = None  # Regulatory module (dk_reg)
        self._lit = None  # Litigation module (dk_lit)
        self._ass = None  # Assets module (dk_ass)
        self._es_client = None  # Elasticsearch
        self._wiki = None  # Wiki bridge
        self._news = None  # News bridge
        self._templates = None  # EDITH templates bridge
        self._loaded = False

    def _lazy_load(self):
        """Lazy load API clients."""
        if self._loaded:
            return

        # Company Registry (CVR/Virk)
        try:
            from .virk_api import DenmarkVirkAPI
            self._virk_api = DenmarkVirkAPI()
            logger.info("Loaded Denmark Virk API")
        except ImportError as e:
            logger.warning(f"Virk API not available: {e}")

        # Company Registry wrapper
        try:
            from .dk_cr import DKCompanyRegistry
            self._cr = DKCompanyRegistry()
            logger.info("Loaded DK Company Registry")
        except ImportError as e:
            logger.warning(f"DK Company Registry not available: {e}")

        # Regulatory module
        try:
            from .dk_reg import DKRegulatory
            self._reg = DKRegulatory()
            logger.info("Loaded DK Regulatory module")
        except ImportError as e:
            logger.debug(f"DK Regulatory module not available: {e}")

        # Litigation module
        try:
            from .dk_lit import DKLitigation
            self._lit = DKLitigation()
            logger.info("Loaded DK Litigation module")
        except ImportError as e:
            logger.debug(f"DK Litigation module not available: {e}")

        # Assets module
        try:
            from .dk_ass import DKAssets
            self._ass = DKAssets()
            logger.info("Loaded DK Assets module")
        except ImportError as e:
            logger.debug(f"DK Assets module not available: {e}")

        # Elasticsearch
        try:
            from elasticsearch import Elasticsearch
            es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
            self._es_client = Elasticsearch([es_url])
            logger.info("Elasticsearch connected")
        except ImportError:
            logger.warning("Elasticsearch not available")

        self._loaded = True

    def parse_dk_operator(self, query: str) -> Tuple[Optional[str], str, Dict]:
        """
        Parse DK operator from query.

        Returns:
            (operator, value, config) or (None, query, {}) if not DK operator
        """
        query_lower = query.strip().lower()

        for op, config in DK_OPERATORS.items():
            if query_lower.startswith(op):
                value = query.strip()[len(op):].strip()
                return op, value, config

        return None, query, {}

    def has_dk_operator(self, query: str) -> bool:
        """Check if query has a DK operator."""
        op, _, _ = self.parse_dk_operator(query)
        return op is not None

    async def execute(self, query: str) -> DKSearchResult:
        """
        Execute DK query with automatic operator routing.

        Args:
            query: Query with DK operator prefix (e.g., "cdk: Novo Nordisk")

        Returns:
            DKSearchResult with aggregated results from all sources
        """
        self._lazy_load()
        start_time = datetime.now()

        operator, value, config = self.parse_dk_operator(query)

        if not operator:
            return DKSearchResult(
                operator="unknown",
                query=query,
                entity_type="unknown",
                errors=["No DK operator found. Use cdk:, pdk:, regdk:, litdk:, crdk:, propdk:, wikidk:, newsdk:, or tmpldk:"]
            )

        result = DKSearchResult(
            operator=operator,
            query=value,
            entity_type=config.get('entity_type', 'unknown'),
            sources_queried=config.get('sources', [])
        )

        # Route to appropriate handler
        try:
            if operator == 'cdk:':
                await self._execute_company_search(value, result)
            elif operator == 'pdk:':
                await self._execute_person_search(value, result)
            elif operator == 'regdk:':
                await self._execute_regulatory_search(value, result)
            elif operator == 'litdk:':
                await self._execute_litigation_search(value, result)
            elif operator == 'crdk:':
                await self._execute_registry_search(value, result)
            elif operator == 'propdk:':
                await self._execute_property_search(value, result)
            elif operator == 'wikidk:':
                await self._execute_wiki_search(value, result)
            elif operator == 'newsdk:':
                await self._execute_news_search(value, result)
            elif operator == 'tmpldk:':
                await self._execute_template_search(value, result)
        except Exception as e:
            result.errors.append(f"Execution error: {str(e)}")
            logger.error(f"DK CLI execution error: {e}")

        # Calculate execution time
        result.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return result

    # =========================================================================
    # COMPANY SEARCH (cdk:)
    # =========================================================================

    async def _execute_company_search(self, query: str, result: DKSearchResult):
        """
        Full DK company search across all sources.

        Sources: CVR/Virk, Elasticsearch indices
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            # 1. Virk API search
            if self._virk_api:
                try:
                    virk_results = await self._virk_api.search_company(session, query)
                    result.results['cvr_virk'] = virk_results
                    result.sources_succeeded.append('cvr_virk')

                    # Convert to unified company format
                    for item in virk_results:
                        result.companies.append({
                            'name': item.get('name', ''),
                            'cvr_number': self._extract_cvr_from_url(item.get('url', '')),
                            'status': item.get('status', ''),
                            'jurisdiction': 'DK',
                            'url': item.get('url', ''),
                            'source': 'cvr_virk'
                        })
                except Exception as e:
                    result.sources_failed.append('cvr_virk')
                    result.errors.append(f"CVR/Virk: {str(e)}")

        # 2. Elasticsearch - companies_unified index
        if self._es_client:
            try:
                es_result = self._es_client.search(
                    index="companies_unified",
                    body={
                        "query": {
                            "bool": {
                                "should": [
                                    {"match": {"name": {"query": query, "boost": 3}}},
                                    {"match": {"name_normalized": {"query": query, "boost": 2}}}
                                ],
                                "filter": [{"term": {"jurisdiction": "DK"}}]
                            }
                        },
                        "size": 20
                    }
                )
                hits = es_result.get('hits', {}).get('hits', [])
                result.results['elasticsearch'] = [h['_source'] for h in hits]
                result.sources_succeeded.append('elasticsearch')

                # Add unique companies
                existing_cvrs = {c.get('cvr_number') for c in result.companies if c.get('cvr_number')}
                for hit in hits:
                    src = hit['_source']
                    cvr = src.get('cvr_number') or src.get('company_number', '')
                    if cvr not in existing_cvrs:
                        result.companies.append({
                            'name': src.get('name', ''),
                            'cvr_number': cvr,
                            'status': src.get('status', ''),
                            'jurisdiction': 'DK',
                            'source': 'elasticsearch'
                        })
            except Exception as e:
                result.sources_failed.append('elasticsearch')
                result.errors.append(f"Elasticsearch: {str(e)}")

    # =========================================================================
    # PERSON SEARCH (pdk:)
    # =========================================================================

    async def _execute_person_search(self, query: str, result: DKSearchResult):
        """
        DK person search - directors, beneficial owners.
        """
        # 1. Elasticsearch - openownership index for DK persons
        if self._es_client:
            try:
                psc_result = self._es_client.search(
                    index="openownership",
                    body={
                        "query": {
                            "bool": {
                                "must": [{"match": {"name": {"query": query, "fuzziness": "AUTO"}}}],
                                "filter": [
                                    {"term": {"entity_type": "person"}},
                                    {"term": {"jurisdiction": "DK"}}
                                ]
                            }
                        },
                        "size": 50
                    }
                )
                hits = psc_result.get('hits', {}).get('hits', [])
                result.results['openownership'] = [h['_source'] for h in hits]
                result.sources_succeeded.append('openownership')

                for hit in hits:
                    src = hit['_source']
                    result.persons.append({
                        'name': src.get('name', ''),
                        'nationality': src.get('nationalities', []),
                        'country_of_residence': src.get('country', ''),
                        'birth_date': src.get('birth_date', ''),
                        'role': 'Owner/Director',
                        'associated_company': src.get('interested_party', ''),
                        'source': 'openownership'
                    })
            except Exception as e:
                result.errors.append(f"Person search: {str(e)}")

    # =========================================================================
    # REGULATORY SEARCH (regdk:)
    # =========================================================================

    async def _execute_regulatory_search(self, query: str, result: DKSearchResult):
        """
        DK regulatory search - Finanstilsynet (Danish FSA).
        """
        if self._reg:
            try:
                reg_result = await self._reg.search(query)
                result.results['finanstilsynet'] = reg_result
                result.sources_succeeded.append('finanstilsynet')
            except NotImplementedError:
                result.results['finanstilsynet'] = {
                    'status': 'not_implemented',
                    'note': 'Finanstilsynet module pending implementation',
                    'url': f'https://www.finanstilsynet.dk/en/Search?search={query}'
                }
            except Exception as e:
                result.errors.append(f"Finanstilsynet: {str(e)}")
        else:
            result.results['finanstilsynet'] = {
                'status': 'pending',
                'note': 'dk_reg module not loaded',
                'url': f'https://www.finanstilsynet.dk/en/Search?search={query}'
            }

    # =========================================================================
    # LITIGATION SEARCH (litdk:)
    # =========================================================================

    async def _execute_litigation_search(self, query: str, result: DKSearchResult):
        """
        DK litigation/gazette search - Statstidende.
        """
        if self._lit:
            try:
                lit_result = await self._lit.search(query)
                result.results['statstidende'] = lit_result
                result.sources_succeeded.append('statstidende')
            except NotImplementedError:
                result.results['statstidende'] = {
                    'status': 'not_implemented',
                    'note': 'Statstidende module pending implementation',
                    'url': f'https://www.telefonbog.dk/statstidende?search={query}'
                }
            except Exception as e:
                result.errors.append(f"Statstidende: {str(e)}")
        else:
            result.results['statstidende'] = {
                'status': 'pending',
                'note': 'dk_lit module not loaded',
                'url': f'https://www.telefonbog.dk/statstidende?search={query}'
            }

    # =========================================================================
    # REGISTRY SEARCH (crdk:)
    # =========================================================================

    async def _execute_registry_search(self, query: str, result: DKSearchResult):
        """
        Direct CVR registry search.
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            if self._virk_api:
                try:
                    virk_results = await self._virk_api.search_company(session, query)
                    result.results['cvr_virk'] = virk_results
                    result.sources_succeeded.append('cvr_virk')

                    for item in virk_results:
                        result.companies.append({
                            'name': item.get('name', ''),
                            'cvr_number': self._extract_cvr_from_url(item.get('url', '')),
                            'status': item.get('status', ''),
                            'jurisdiction': 'DK',
                            'url': item.get('url', ''),
                            'source': 'cvr_virk'
                        })
                except Exception as e:
                    result.errors.append(f"CVR/Virk: {str(e)}")

    # =========================================================================
    # PROPERTY SEARCH (propdk:)
    # =========================================================================

    async def _execute_property_search(self, query: str, result: DKSearchResult):
        """
        DK Land Registry search - Tinglysning.
        """
        if self._ass:
            try:
                ass_result = await self._ass.search(query)
                result.results['tinglysning'] = ass_result
                result.sources_succeeded.append('tinglysning')
            except NotImplementedError:
                result.results['tinglysning'] = {
                    'status': 'not_implemented',
                    'note': 'Tinglysning module pending implementation',
                    'url': 'https://www.tinglysning.dk'
                }
            except Exception as e:
                result.errors.append(f"Tinglysning: {str(e)}")
        else:
            result.results['tinglysning'] = {
                'status': 'pending',
                'note': 'dk_ass module not loaded',
                'url': 'https://www.tinglysning.dk'
            }

    # =========================================================================
    # WIKI SEARCH (wikidk:)
    # =========================================================================

    def _get_wiki(self):
        """Lazy load DK wiki bridge."""
        if self._wiki is None:
            try:
                from .dk_wiki import DKWiki
                self._wiki = DKWiki()
            except ImportError as e:
                logger.warning(f"DK Wiki not available: {e}")
        return self._wiki

    async def _execute_wiki_search(self, query: str, result: DKSearchResult):
        """
        Get DK wiki sources and guides.

        Query can be:
        - Empty: Get all sections
        - Section code: cr, lit, reg, ass
        - Search term: Search wiki content
        """
        wiki = self._get_wiki()
        if not wiki:
            result.errors.append("DK Wiki bridge not available")
            return

        try:
            wiki_result = await wiki.execute(query)
            result.results['wiki'] = {
                'sections': list(wiki_result.sections.keys()),
                'total_links': wiki_result.total_links,
                'sources_count': len(wiki_result.all_sources),
            }

            # Add wiki sources as documents
            for source in wiki_result.all_sources:
                result.documents.append({
                    'title': source.title,
                    'url': source.url,
                    'section': source.section,
                    'type': 'wiki_source',
                    'source': 'dk_wiki'
                })

            result.sources_succeeded.append('wiki_sections')
        except Exception as e:
            result.errors.append(f"Wiki search failed: {e}")
            result.sources_failed.append('wiki_sections')

    # =========================================================================
    # NEWS SEARCH (newsdk:)
    # =========================================================================

    def _get_news(self):
        """Lazy load DK news bridge."""
        if self._news is None:
            try:
                from .dk_news import DKNews
                self._news = DKNews()
            except ImportError as e:
                logger.warning(f"DK News not available: {e}")
        return self._news

    async def _execute_news_search(self, query: str, result: DKSearchResult):
        """
        Search DK news sites via Torpedo.

        Uses Denmark news site templates for targeted searching.
        """
        news = self._get_news()
        if not news:
            result.errors.append("DK News bridge not available")
            return

        try:
            news_result = await news.execute(query)
            result.results['news'] = {
                'articles_count': len(news_result.articles),
                'sites_searched': news_result.sites_searched,
                'total_results': news_result.total_results,
            }

            # Add articles as documents
            for article in news_result.articles:
                result.documents.append({
                    'title': article.title,
                    'url': article.url,
                    'snippet': article.snippet,
                    'source_domain': article.source_domain,
                    'date': article.date,
                    'type': 'news_article',
                    'source': 'dk_news'
                })

            if news_result.errors:
                result.errors.extend(news_result.errors)
            else:
                result.sources_succeeded.append('news_recipes')
        except Exception as e:
            result.errors.append(f"News search failed: {e}")
            result.sources_failed.append('news_recipes')

    # =========================================================================
    # TEMPLATES (tmpldk:)
    # =========================================================================

    def _get_templates(self):
        """Lazy load DK templates bridge."""
        if self._templates is None:
            try:
                from .dk_templates import DKTemplates
                self._templates = DKTemplates()
            except ImportError as e:
                logger.warning(f"DK Templates not available: {e}")
        return self._templates

    async def _execute_template_search(self, query: str, result: DKSearchResult):
        """
        Get DK EDITH writing templates.

        Returns standard phrases, footnote formats, and report templates
        for Denmark jurisdiction.
        """
        templates = self._get_templates()
        if not templates:
            result.errors.append("DK Templates bridge not available")
            return

        try:
            template = await templates.execute(query)
            result.results['templates'] = {
                'jurisdiction': template.jurisdiction,
                'registries_count': len(template.registries),
                'standard_phrases_count': len(template.standard_phrases),
                'footnote_examples_count': len(template.footnote_examples),
                'arbitrage_routes_count': len(template.arbitrage_routes),
                'sources_count': len(template.sources),
                'has_content': bool(template.raw_content),
            }

            # Add template info as document
            if template.raw_content:
                result.documents.append({
                    'title': f'EDITH Template: {template.jurisdiction}',
                    'content_preview': template.raw_content[:500] + '...' if len(template.raw_content) > 500 else template.raw_content,
                    'type': 'edith_template',
                    'source': 'edith_templates'
                })

            result.sources_succeeded.append('edith_templates')
        except Exception as e:
            result.errors.append(f"Template search failed: {e}")
            result.sources_failed.append('edith_templates')

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _extract_cvr_from_url(self, url: str) -> str:
        """Extract CVR number from Virk URL."""
        # URLs like: https://datacvr.virk.dk/enhed/virksomhed/12345678
        match = re.search(r'/(\d{8})(?:[/?]|$)', url)
        if match:
            return match.group(1)
        return ''


# =============================================================================
# INTEGRATION WITH IO_CLI
# =============================================================================

def get_dk_operators() -> Dict[str, Dict]:
    """Return DK operators for io_cli.py integration."""
    return DK_OPERATORS


def has_dk_operator(query: str) -> bool:
    """Check if query has DK operator."""
    cli = DKCLI()
    return cli.has_dk_operator(query)


async def execute_dk_query(query: str) -> Dict:
    """Execute DK query and return dict result."""
    cli = DKCLI()
    result = await cli.execute(query)
    return result.to_dict()


# =============================================================================
# CLI MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Denmark Unified CLI - Search Denmark Public Records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
OPERATORS:
  cdk: <company>      Denmark company search (CVR/Virk)
  pdk: <person>       Denmark person search (directors, beneficial owners)
  regdk: <query>      Denmark regulatory search (Finanstilsynet)
  litdk: <query>      Denmark litigation/gazette (Statstidende)
  crdk: <company>     Denmark corporate registry (CVR direct)
  propdk: <company>   Denmark property search (Tinglysning)
  wikidk: <section>   DK wiki sources and guides
  newsdk: <query>     DK news search via Torpedo
  tmpldk:             DK EDITH writing templates

EXAMPLES:
  %(prog)s "cdk: Novo Nordisk"
  %(prog)s "pdk: Lars Jensen"
  %(prog)s "regdk: bank"
  %(prog)s "propdk: Carlsberg"
  %(prog)s "wikidk: cr"
  %(prog)s "newsdk: Maersk"
  %(prog)s "tmpldk:"
        """
    )

    parser.add_argument("query", nargs="?", help="Query with DK operator prefix")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--list-operators", action="store_true", help="List available DK operators")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.list_operators:
        print("\nDENMARK PUBLIC RECORDS OPERATORS")
        print("=" * 60)
        for op, config in DK_OPERATORS.items():
            print(f"\n  {op:<12} {config['name']}")
            print(f"              {config['description']}")
            print(f"              Sources: {', '.join(config['sources'])}")
        print()
        return

    if not args.query:
        parser.print_help()
        return

    async def run():
        cli = DKCLI()
        result = await cli.execute(args.query)

        if args.json:
            print(json.dumps(result.to_dict(), indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"DK SEARCH: {result.operator} {result.query}")
            print(f"{'='*60}")

            print(f"\nSources: {len(result.sources_succeeded)} succeeded, {len(result.sources_failed)} failed")
            if result.sources_succeeded:
                print(f"   {', '.join(result.sources_succeeded)}")
            if result.sources_failed:
                print(f"   Failed: {', '.join(result.sources_failed)}")

            if result.companies:
                print(f"\nCOMPANIES ({len(result.companies)})")
                for i, c in enumerate(result.companies[:10], 1):
                    print(f"   {i}. {c.get('name', 'Unknown')}")
                    if c.get('cvr_number'):
                        print(f"      CVR: {c['cvr_number']}")
                    if c.get('status'):
                        print(f"      Status: {c['status']}")
                if len(result.companies) > 10:
                    print(f"   ... and {len(result.companies) - 10} more")

            if result.persons:
                print(f"\nPERSONS ({len(result.persons)})")
                for i, p in enumerate(result.persons[:10], 1):
                    print(f"   {i}. {p.get('name', 'Unknown')} ({p.get('role', 'Unknown')})")
                if len(result.persons) > 10:
                    print(f"   ... and {len(result.persons) - 10} more")

            if result.properties:
                print(f"\nPROPERTIES ({len(result.properties)})")
                for i, prop in enumerate(result.properties[:10], 1):
                    print(f"   {i}. {prop.get('property_address', 'Unknown')}")

            if result.errors:
                print(f"\nERRORS:")
                for err in result.errors:
                    print(f"   - {err}")

            print(f"\nExecution time: {result.execution_time_ms}ms")

    asyncio.run(run())


if __name__ == "__main__":
    main()
