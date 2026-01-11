#!/usr/bin/env python3
"""
SE (Sweden) Unified CLI - Single Entry Point for Swedish Public Records
========================================================================

Combines ALL Swedish public records sources into one unified interface:
1. Bolagsverket API (company registry via Verksamt)
2. Finansinspektionen (financial regulation)
3. Lantmateriet (land registry)
4. Post- och Inrikes Tidningar (official gazette)

Designed to integrate with io_cli.py for unified routing.

OPERATOR SYNTAX:
    cse: <company>      - SE company search (Bolagsverket + Verksamt)
    pse: <person>       - SE person search (directors, beneficial owners)
    regse: <query>      - SE regulatory search (Finansinspektionen)
    litse: <query>      - SE litigation/gazette (Post- och Inrikes Tidningar)
    crse: <company>     - SE corporate registry (Bolagsverket direct)
    propse: <company>   - SE property search (Lantmateriet)

USAGE:
    # From command line
    python se_cli.py "cse: IKEA"
    python se_cli.py "pse: Stefan Persson"
    python se_cli.py "regse: bank"
    python se_cli.py "propse: Stockholm"

    # From io_cli.py
    python io_cli.py "cse: Volvo"

    # As Python module
    from country_engines.SE.se_cli import SECLI
    se = SECLI()
    results = await se.execute("cse: IKEA")

ENV VARS:
    BOLAGSVERKET_API_KEY     - Bolagsverket API key (optional, enhances data)
    FI_API_KEY               - Finansinspektionen API key (optional)
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

logger = logging.getLogger("se_cli")


# =============================================================================
# SE OPERATOR DEFINITIONS
# =============================================================================

SE_OPERATORS = {
    'cse:': {
        'name': 'SE Company Search',
        'entity_type': 'company',
        'sources': ['bolagsverket', 'verksamt', 'opencorporates'],
        'description': 'Search Swedish company registries (Bolagsverket + Verksamt)',
    },
    'pse:': {
        'name': 'SE Person Search',
        'entity_type': 'person',
        'sources': ['bolagsverket_officers', 'bolagsverket_ubo'],
        'description': 'Search Swedish person records (directors, beneficial owners)',
    },
    'regse:': {
        'name': 'SE Regulatory Search',
        'entity_type': 'company',
        'sources': ['finansinspektionen'],
        'description': 'Search Finansinspektionen regulated entities',
    },
    'litse:': {
        'name': 'SE Litigation/Gazette',
        'entity_type': 'notice',
        'sources': ['poit', 'tingsratt'],
        'description': 'Search Post- och Inrikes Tidningar official gazette and courts',
    },
    'crse:': {
        'name': 'SE Corporate Registry',
        'entity_type': 'company',
        'sources': ['bolagsverket'],
        'description': 'Bolagsverket direct search (bypass other sources)',
    },
    'propse:': {
        'name': 'SE Property Search',
        'entity_type': 'property',
        'sources': ['lantmateriet'],
        'description': 'Search Swedish Land Registry (Lantmateriet)',
    },
    'wikise:': {
        'name': 'SE Wiki Sources',
        'entity_type': 'source',
        'category': 'wiki',
        'sources': ['wiki_sections', 'edith_injections'],
        'description': 'SE jurisdiction guides, tips, source intelligence',
    },
    'newsse:': {
        'name': 'SE News Search',
        'entity_type': 'article',
        'category': 'news',
        'sources': ['news_recipes', 'torpedo_news'],
        'description': 'Search Swedish news sites via Torpedo',
    },
    'tmplse:': {
        'name': 'SE EDITH Templates',
        'entity_type': 'template',
        'category': 'templates',
        'sources': ['edith_templates'],
        'description': 'SE writing templates for reports (Bolagsverket, Finansinspektionen)',
    },
}


# =============================================================================
# RESULT DATACLASS
# =============================================================================

@dataclass
class SESearchResult:
    """Unified SE search result."""
    operator: str
    query: str
    entity_type: str
    jurisdiction: str = "SE"

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
# SE UNIFIED CLI CLASS
# =============================================================================

class SECLI:
    """
    Unified Swedish Public Records CLI.

    Routes SE operators to appropriate sources and aggregates results.
    """

    def __init__(self):
        self._verksamt_api = None  # Verksamt API
        self._cr = None  # Company Registry module (se_cr)
        self._reg = None  # Regulatory module (se_reg)
        self._lit = None  # Litigation module (se_lit)
        self._ass = None  # Assets module (se_ass)
        self._es_client = None  # Elasticsearch
        self._wiki = None  # Wiki bridge
        self._news = None  # News bridge
        self._templates = None  # EDITH templates bridge
        self._loaded = False

    def _lazy_load(self):
        """Lazy load API clients."""
        if self._loaded:
            return

        # Verksamt API (existing)
        try:
            from .verksamt_api import SwedenVerksamtAPI
            self._verksamt_api = SwedenVerksamtAPI()
            logger.info("Verksamt API loaded")
        except ImportError as e:
            logger.warning(f"Verksamt API not available: {e}")

        # Company Registry wrapper
        try:
            from .se_cr import SECompanyRegistry
            self._cr = SECompanyRegistry()
            logger.info("SE Company Registry loaded")
        except ImportError as e:
            logger.warning(f"SE Company Registry not available: {e}")

        # Regulatory module
        try:
            from .se_reg import SERegulatory
            self._reg = SERegulatory()
            logger.info("SE Regulatory module loaded")
        except ImportError as e:
            logger.warning(f"SE Regulatory module not available: {e}")

        # Litigation module
        try:
            from .se_lit import SELitigation
            self._lit = SELitigation()
            logger.info("SE Litigation module loaded")
        except ImportError as e:
            logger.warning(f"SE Litigation module not available: {e}")

        # Assets module (Lantmateriet)
        try:
            from .se_ass import SEAssets
            self._ass = SEAssets()
            logger.info("SE Assets module loaded")
        except ImportError as e:
            logger.warning(f"SE Assets module not available: {e}")

        # Elasticsearch
        try:
            from elasticsearch import Elasticsearch
            es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
            self._es_client = Elasticsearch([es_url])
            logger.info("Elasticsearch connected")
        except ImportError:
            logger.warning("Elasticsearch not available")

        self._loaded = True

    def parse_se_operator(self, query: str) -> Tuple[Optional[str], str, Dict]:
        """
        Parse SE operator from query.

        Returns:
            (operator, value, config) or (None, query, {}) if not SE operator
        """
        query_lower = query.strip().lower()

        for op, config in SE_OPERATORS.items():
            if query_lower.startswith(op):
                value = query.strip()[len(op):].strip()
                return op, value, config

        return None, query, {}

    def has_se_operator(self, query: str) -> bool:
        """Check if query has an SE operator."""
        op, _, _ = self.parse_se_operator(query)
        return op is not None

    async def execute(self, query: str) -> SESearchResult:
        """
        Execute SE query with automatic operator routing.

        Args:
            query: Query with SE operator prefix (e.g., "cse: IKEA")

        Returns:
            SESearchResult with aggregated results from all sources
        """
        self._lazy_load()
        start_time = datetime.now()

        operator, value, config = self.parse_se_operator(query)

        if not operator:
            return SESearchResult(
                operator="unknown",
                query=query,
                entity_type="unknown",
                errors=["No SE operator found. Use cse:, pse:, regse:, litse:, crse:, propse:, wikise:, newsse:, or tmplse:"]
            )

        result = SESearchResult(
            operator=operator,
            query=value,
            entity_type=config.get('entity_type', 'unknown'),
            sources_queried=config.get('sources', [])
        )

        # Route to appropriate handler
        try:
            if operator == 'cse:':
                await self._execute_company_search(value, result)
            elif operator == 'pse:':
                await self._execute_person_search(value, result)
            elif operator == 'regse:':
                await self._execute_regulatory_search(value, result)
            elif operator == 'litse:':
                await self._execute_litigation_search(value, result)
            elif operator == 'crse:':
                await self._execute_registry_search(value, result)
            elif operator == 'propse:':
                await self._execute_property_search(value, result)
            elif operator == 'wikise:':
                await self._execute_wiki_search(value, result)
            elif operator == 'newsse:':
                await self._execute_news_search(value, result)
            elif operator == 'tmplse:':
                await self._execute_template_search(value, result)
        except Exception as e:
            result.errors.append(f"Execution error: {str(e)}")
            logger.error(f"SE CLI execution error: {e}")

        # Calculate execution time
        result.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return result

    # =========================================================================
    # COMPANY SEARCH (cse:)
    # =========================================================================

    async def _execute_company_search(self, query: str, result: SESearchResult):
        """
        Full SE company search across all sources.

        Sources: Bolagsverket, Verksamt, OpenCorporates, Elasticsearch indices
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            # 1. Verksamt search (primary)
            if self._verksamt_api:
                try:
                    verksamt_results = await self._verksamt_api.search_company(session, query)
                    result.results['verksamt'] = verksamt_results
                    result.sources_succeeded.append('verksamt')

                    # Convert to unified company format
                    for item in verksamt_results:
                        result.companies.append({
                            'name': item.get('name', ''),
                            'url': item.get('url', ''),
                            'jurisdiction': 'SE',
                            'source': 'verksamt'
                        })
                except Exception as e:
                    result.sources_failed.append('verksamt')
                    result.errors.append(f"Verksamt: {str(e)}")

            # 2. Company Registry wrapper (includes Bolagsverket)
            if self._cr:
                try:
                    cr_result = await self._cr.search_company(query)
                    result.results['bolagsverket'] = cr_result.get('companies', [])
                    result.sources_succeeded.append('bolagsverket')

                    # Add unique companies (dedupe by name)
                    existing_names = {c.get('name', '').upper() for c in result.companies}
                    for item in cr_result.get('companies', []):
                        if item.get('name', '').upper() not in existing_names:
                            result.companies.append({
                                'name': item.get('name', ''),
                                'org_number': item.get('org_number', ''),
                                'status': item.get('status', ''),
                                'type': item.get('company_type', ''),
                                'address': item.get('address', ''),
                                'date_of_registration': item.get('date_of_registration'),
                                'jurisdiction': 'SE',
                                'source': 'bolagsverket'
                            })
                except Exception as e:
                    result.sources_failed.append('bolagsverket')
                    result.errors.append(f"Bolagsverket: {str(e)}")

        # 3. Elasticsearch - companies_unified index
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
                                "filter": [{"term": {"jurisdiction": "SE"}}]
                            }
                        },
                        "size": 20
                    }
                )
                hits = es_result.get('hits', {}).get('hits', [])
                result.results['elasticsearch'] = [h['_source'] for h in hits]
                result.sources_succeeded.append('elasticsearch')

                # Add unique companies
                existing_names = {c.get('name', '').upper() for c in result.companies}
                for hit in hits:
                    src = hit['_source']
                    if src.get('name', '').upper() not in existing_names:
                        result.companies.append({
                            'name': src.get('name', ''),
                            'org_number': src.get('org_number', ''),
                            'status': src.get('status', ''),
                            'jurisdiction': 'SE',
                            'source': 'elasticsearch'
                        })
            except Exception as e:
                result.sources_failed.append('elasticsearch')
                result.errors.append(f"Elasticsearch: {str(e)}")

    # =========================================================================
    # PERSON SEARCH (pse:)
    # =========================================================================

    async def _execute_person_search(self, query: str, result: SESearchResult):
        """
        SE person search - directors, beneficial owners.
        """
        # 1. Elasticsearch person search
        if self._es_client:
            try:
                # Search for Swedish beneficial owners
                es_result = self._es_client.search(
                    index="openownership",
                    body={
                        "query": {
                            "bool": {
                                "must": [{"match": {"name": {"query": query, "fuzziness": "AUTO"}}}],
                                "filter": [{"term": {"entity_type": "person"}}]
                            }
                        },
                        "size": 50
                    }
                )
                hits = es_result.get('hits', {}).get('hits', [])
                result.results['openownership'] = [h['_source'] for h in hits]
                result.sources_succeeded.append('openownership')

                for hit in hits:
                    src = hit['_source']
                    result.persons.append({
                        'name': src.get('name', ''),
                        'nationality': src.get('nationalities', []),
                        'country_of_residence': src.get('country', ''),
                        'birth_date': src.get('birth_date', ''),
                        'role': 'Beneficial Owner',
                        'associated_company': src.get('interested_party', ''),
                        'source': 'openownership'
                    })
            except Exception as e:
                result.errors.append(f"Person search: {str(e)}")

        # 2. Bolagsverket officers (via company registry wrapper)
        if self._cr:
            try:
                # Person search would require direct Bolagsverket access
                # For now, flag as pending
                result.results['bolagsverket_officers'] = {
                    'status': 'pending',
                    'note': 'Direct Bolagsverket person search requires API access'
                }
            except Exception as e:
                result.errors.append(f"Bolagsverket officers: {str(e)}")

    # =========================================================================
    # REGULATORY SEARCH (regse:)
    # =========================================================================

    async def _execute_regulatory_search(self, query: str, result: SESearchResult):
        """
        SE regulatory search - Finansinspektionen regulated entities.
        """
        if self._reg:
            try:
                reg_result = await self._reg.search(query)
                result.results['finansinspektionen'] = reg_result
                result.sources_succeeded.append('finansinspektionen')
            except NotImplementedError:
                result.results['finansinspektionen'] = {
                    'status': 'not_implemented',
                    'note': 'Finansinspektionen search not yet implemented',
                    'url': f'https://www.fi.se/sv/vara-register/foretagsregistret/?q={query}'
                }
            except Exception as e:
                result.errors.append(f"Finansinspektionen: {str(e)}")
        else:
            result.results['finansinspektionen'] = {
                'status': 'not_implemented',
                'url': f'https://www.fi.se/sv/vara-register/foretagsregistret/?q={query}'
            }

    # =========================================================================
    # LITIGATION SEARCH (litse:)
    # =========================================================================

    async def _execute_litigation_search(self, query: str, result: SESearchResult):
        """
        SE litigation/gazette search - Post- och Inrikes Tidningar.
        """
        if self._lit:
            try:
                lit_result = await self._lit.search(query)
                result.results['poit'] = lit_result
                result.sources_succeeded.append('poit')
            except NotImplementedError:
                result.results['poit'] = {
                    'status': 'not_implemented',
                    'note': 'Post- och Inrikes Tidningar search not yet implemented',
                    'url': f'https://poit.bolagsverket.se/poit/PublikPoitIn.do?sokord={query}'
                }
            except Exception as e:
                result.errors.append(f"POIT: {str(e)}")
        else:
            result.results['poit'] = {
                'status': 'not_implemented',
                'url': f'https://poit.bolagsverket.se/poit/PublikPoitIn.do?sokord={query}'
            }

    # =========================================================================
    # REGISTRY SEARCH (crse:)
    # =========================================================================

    async def _execute_registry_search(self, query: str, result: SESearchResult):
        """
        Direct Bolagsverket/Verksamt search (bypass other sources).
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            if self._verksamt_api:
                try:
                    verksamt_results = await self._verksamt_api.search_company(session, query)
                    result.results['verksamt'] = verksamt_results
                    result.sources_succeeded.append('verksamt')

                    for item in verksamt_results:
                        result.companies.append({
                            'name': item.get('name', ''),
                            'url': item.get('url', ''),
                            'jurisdiction': 'SE',
                            'source': 'verksamt'
                        })
                except Exception as e:
                    result.errors.append(f"Verksamt: {str(e)}")

    # =========================================================================
    # PROPERTY SEARCH (propse:)
    # =========================================================================

    async def _execute_property_search(self, query: str, result: SESearchResult):
        """
        SE property search - Lantmateriet (Swedish Land Registry).
        """
        if self._ass:
            try:
                ass_result = await self._ass.search(query)
                result.results['lantmateriet'] = ass_result
                result.sources_succeeded.append('lantmateriet')
            except NotImplementedError:
                result.results['lantmateriet'] = {
                    'status': 'not_implemented',
                    'note': 'Lantmateriet search not yet implemented',
                    'url': 'https://www.lantmateriet.se/sv/fastigheter-och-sok/'
                }
            except Exception as e:
                result.errors.append(f"Lantmateriet: {str(e)}")
        else:
            result.results['lantmateriet'] = {
                'status': 'not_implemented',
                'url': 'https://www.lantmateriet.se/sv/fastigheter-och-sok/'
            }

    # =========================================================================
    # WIKI SEARCH (wikise:)
    # =========================================================================

    def _get_wiki(self):
        """Lazy load SE wiki bridge."""
        if self._wiki is None:
            try:
                from .se_wiki import SEWiki
                self._wiki = SEWiki()
            except ImportError as e:
                logger.warning(f"SE Wiki not available: {e}")
        return self._wiki

    async def _execute_wiki_search(self, query: str, result: SESearchResult):
        """
        Get SE wiki sources and guides.

        Query can be:
        - Empty: Get all sections
        - Section code: cr, lit, reg, ass
        - Search term: Search wiki content
        """
        wiki = self._get_wiki()
        if not wiki:
            result.errors.append("SE Wiki bridge not available")
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
                    'source': 'se_wiki'
                })

            result.sources_succeeded.append('wiki_sections')
        except Exception as e:
            result.errors.append(f"Wiki search failed: {e}")
            result.sources_failed.append('wiki_sections')

    # =========================================================================
    # NEWS SEARCH (newsse:)
    # =========================================================================

    def _get_news(self):
        """Lazy load SE news bridge."""
        if self._news is None:
            try:
                from .se_news import SENews
                self._news = SENews()
            except ImportError as e:
                logger.warning(f"SE News not available: {e}")
        return self._news

    async def _execute_news_search(self, query: str, result: SESearchResult):
        """
        Search SE news sites via Torpedo.

        Uses Swedish news site templates for targeted searching.
        """
        news = self._get_news()
        if not news:
            result.errors.append("SE News bridge not available")
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
                    'source': 'se_news'
                })

            if news_result.errors:
                result.errors.extend(news_result.errors)
            else:
                result.sources_succeeded.append('news_recipes')
        except Exception as e:
            result.errors.append(f"News search failed: {e}")
            result.sources_failed.append('news_recipes')

    # =========================================================================
    # TEMPLATES (tmplse:)
    # =========================================================================

    def _get_templates(self):
        """Lazy load SE templates bridge."""
        if self._templates is None:
            try:
                from .se_templates import SETemplates
                self._templates = SETemplates()
            except ImportError as e:
                logger.warning(f"SE Templates not available: {e}")
        return self._templates

    async def _execute_template_search(self, query: str, result: SESearchResult):
        """
        Get SE EDITH writing templates.

        Returns standard phrases, footnote formats, and report templates
        for SE jurisdiction.
        """
        templates = self._get_templates()
        if not templates:
            result.errors.append("SE Templates bridge not available")
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


# =============================================================================
# INTEGRATION WITH IO_CLI
# =============================================================================

def get_se_operators() -> Dict[str, Dict]:
    """Return SE operators for io_cli.py integration."""
    return SE_OPERATORS


def has_se_operator(query: str) -> bool:
    """Check if query has SE operator."""
    cli = SECLI()
    return cli.has_se_operator(query)


async def execute_se_query(query: str) -> Dict:
    """Execute SE query and return dict result."""
    cli = SECLI()
    result = await cli.execute(query)
    return result.to_dict()


# =============================================================================
# CLI MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="SE Unified CLI - Search Swedish Public Records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
OPERATORS:
  cse: <company>      SE company search (Bolagsverket + Verksamt)
  pse: <person>       SE person search (directors, beneficial owners)
  regse: <query>      SE regulatory search (Finansinspektionen)
  litse: <query>      SE litigation/gazette (Post- och Inrikes Tidningar)
  crse: <company>     SE corporate registry (Bolagsverket direct)
  propse: <company>   SE property search (Lantmateriet)
  wikise: <section>   SE wiki sources and guides
  newsse: <query>     SE news search (Swedish news sites via Torpedo)
  tmplse:             SE EDITH writing templates

EXAMPLES:
  %(prog)s "cse: IKEA"
  %(prog)s "pse: Stefan Persson"
  %(prog)s "regse: bank"
  %(prog)s "propse: Stockholm"
  %(prog)s "wikise: cr"
  %(prog)s "newsse: Volvo scandal"
  %(prog)s "tmplse:"
        """
    )

    parser.add_argument("query", nargs="?", help="Query with SE operator prefix")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--list-operators", action="store_true", help="List available SE operators")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.list_operators:
        print("\nSE PUBLIC RECORDS OPERATORS")
        print("=" * 60)
        for op, config in SE_OPERATORS.items():
            print(f"\n  {op:<12} {config['name']}")
            print(f"              {config['description']}")
            print(f"              Sources: {', '.join(config['sources'])}")
        print()
        return

    if not args.query:
        parser.print_help()
        return

    async def run():
        cli = SECLI()
        result = await cli.execute(args.query)

        if args.json:
            print(json.dumps(result.to_dict(), indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"SE SEARCH: {result.operator} {result.query}")
            print(f"{'='*60}")

            print(f"\nSources: {len(result.sources_succeeded)} succeeded, {len(result.sources_failed)} failed")
            if result.sources_succeeded:
                print(f"   Succeeded: {', '.join(result.sources_succeeded)}")
            if result.sources_failed:
                print(f"   Failed: {', '.join(result.sources_failed)}")

            if result.companies:
                print(f"\nCOMPANIES ({len(result.companies)})")
                for i, c in enumerate(result.companies[:10], 1):
                    print(f"   {i}. {c.get('name', 'Unknown')}")
                    if c.get('org_number'):
                        print(f"      Org Number: {c['org_number']}")
                    if c.get('status'):
                        print(f"      Status: {c['status']}")
                    if c.get('url'):
                        print(f"      URL: {c['url']}")
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
                    print(f"   {i}. {prop.get('address', 'Unknown')}")

            if result.errors:
                print(f"\nERRORS:")
                for err in result.errors:
                    print(f"   - {err}")

            print(f"\nExecution time: {result.execution_time_ms}ms")

    asyncio.run(run())


if __name__ == "__main__":
    main()
