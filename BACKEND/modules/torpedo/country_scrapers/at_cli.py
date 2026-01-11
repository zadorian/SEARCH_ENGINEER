#!/usr/bin/env python3
"""
Austria Unified CLI - Single Entry Point for Austrian Public Records
=====================================================================

Combines ALL Austrian public records sources into one unified interface:
1. Firmenbuch (company registry via FirmenABC)
2. FMA Register (financial regulation)
3. Grundbuch (land registry)
4. Ediktsdatei (official gazette - insolvency/enforcement)

Designed to integrate with io_cli.py for unified routing.

OPERATOR SYNTAX:
    cat: <company>      - Austria company search (Firmenbuch + FirmenABC)
    pat: <person>       - Austria person search (directors, shareholders)
    regat: <query>      - Austria regulatory search (FMA)
    litat: <query>      - Austria litigation/insolvency (Ediktsdatei)
    crat: <company>     - Austria direct registry lookup
    propat: <query>     - Austria property search (Grundbuch)

USAGE:
    # From command line
    python at_cli.py "cat: Erste Bank"
    python at_cli.py "pat: Wolfgang Plasser"
    python at_cli.py "regat: hedge fund"
    python at_cli.py "litat: insolvenz"

    # From io_cli.py
    python io_cli.py "cat: Erste Bank"

    # As Python module
    from country_engines.AT.at_cli import ATCLI
    at = ATCLI()
    results = await at.execute("cat: Erste Bank")

ENV VARS:
    ELASTICSEARCH_URL       - Elasticsearch URL (default: http://localhost:9200)
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

logger = logging.getLogger("at_cli")


# =============================================================================
# AT OPERATOR DEFINITIONS
# =============================================================================

AT_OPERATORS = {
    'cat:': {
        'name': 'Austria Company Search',
        'entity_type': 'company',
        'category': 'cr',
        'sources': ['firmenbuch', 'firmenabc', 'elasticsearch'],
        'description': 'Search Austrian company registries (Firmenbuch + FirmenABC)',
    },
    'pat:': {
        'name': 'Austria Person Search',
        'entity_type': 'person',
        'category': 'cr',
        'sources': ['firmenabc_shareholders', 'elasticsearch'],
        'description': 'Search Austrian person records (directors, shareholders)',
    },
    'regat:': {
        'name': 'Austria Regulatory Search',
        'entity_type': 'company',
        'category': 'reg',
        'sources': ['fma_register'],
        'description': 'Search FMA regulated entities',
    },
    'litat:': {
        'name': 'Austria Litigation/Insolvency',
        'entity_type': 'company',
        'category': 'lit',
        'sources': ['ediktsdatei', 'firmenbuch_insolvency'],
        'description': 'Search Ediktsdatei insolvency/enforcement notices',
    },
    'crat:': {
        'name': 'Austria Corporate Registry',
        'entity_type': 'company',
        'category': 'cr',
        'sources': ['firmenbuch'],
        'description': 'Firmenbuch direct search (bypass FirmenABC)',
    },
    'propat:': {
        'name': 'Austria Property Search',
        'entity_type': 'property',
        'category': 'ass',
        'sources': ['grundbuch'],
        'description': 'Search Austrian land registry (Grundbuch)',
    },
    'wikiat:': {
        'name': 'AT Wiki Sources',
        'entity_type': 'source',
        'category': 'wiki',
        'sources': ['wiki_sections', 'edith_injections'],
        'description': 'Austrian jurisdiction guides, tips, source intelligence',
    },
    'newsat:': {
        'name': 'AT News Search',
        'entity_type': 'article',
        'category': 'news',
        'sources': ['news_recipes', 'torpedo_news'],
        'description': 'Search Austrian news sites via Torpedo',
    },
    'tmplat:': {
        'name': 'AT EDITH Templates',
        'entity_type': 'template',
        'category': 'templates',
        'sources': ['edith_templates'],
        'description': 'Austrian writing templates for reports (Firmenbuch, FMA)',
    },
}


# =============================================================================
# RESULT DATACLASS
# =============================================================================

@dataclass
class ATSearchResult:
    """Unified Austria search result."""
    operator: str
    query: str
    entity_type: str
    jurisdiction: str = "AT"

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
# AT UNIFIED CLI CLASS
# =============================================================================

class ATCLI:
    """
    Unified Austrian Public Records CLI.

    Routes AT operators to appropriate sources and aggregates results.
    """

    def __init__(self):
        self._cr = None  # Company Registry module (at_cr)
        self._reg = None  # Regulatory module (at_reg)
        self._lit = None  # Litigation module (at_lit)
        self._ass = None  # Assets module (at_ass)
        self._es_client = None  # Elasticsearch
        self._wiki = None  # Wiki bridge
        self._news = None  # News bridge
        self._templates = None  # EDITH templates bridge
        self._loaded = False

    def _lazy_load(self):
        """Lazy load modules."""
        if self._loaded:
            return

        # Company Registry (FirmenABC wrapper)
        try:
            from .at_cr import ATCompanyRegistry
            self._cr = ATCompanyRegistry()
            logger.info("AT Company Registry loaded")
        except ImportError as e:
            logger.warning(f"AT Company Registry not available: {e}")

        # Regulatory module
        try:
            from .at_reg import ATRegulatory
            self._reg = ATRegulatory()
            logger.info("AT Regulatory module loaded")
        except ImportError as e:
            logger.debug(f"AT Regulatory module not available: {e}")

        # Litigation module
        try:
            from .at_lit import ATLitigation
            self._lit = ATLitigation()
            logger.info("AT Litigation module loaded")
        except ImportError as e:
            logger.debug(f"AT Litigation module not available: {e}")

        # Assets module
        try:
            from .at_ass import ATAssets
            self._ass = ATAssets()
            logger.info("AT Assets module loaded")
        except ImportError as e:
            logger.debug(f"AT Assets module not available: {e}")

        # Elasticsearch
        try:
            from elasticsearch import Elasticsearch
            es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
            self._es_client = Elasticsearch([es_url])
            logger.info("Elasticsearch connected")
        except ImportError:
            logger.warning("Elasticsearch not available")

        self._loaded = True

    def parse_at_operator(self, query: str) -> Tuple[Optional[str], str, Dict]:
        """
        Parse AT operator from query.

        Returns:
            (operator, value, config) or (None, query, {}) if not AT operator
        """
        query_lower = query.strip().lower()

        for op, config in AT_OPERATORS.items():
            if query_lower.startswith(op):
                value = query.strip()[len(op):].strip()
                return op, value, config

        return None, query, {}

    def has_at_operator(self, query: str) -> bool:
        """Check if query has an AT operator."""
        op, _, _ = self.parse_at_operator(query)
        return op is not None

    async def execute(self, query: str) -> ATSearchResult:
        """
        Execute AT query with automatic operator routing.

        Args:
            query: Query with AT operator prefix (e.g., "cat: Erste Bank")

        Returns:
            ATSearchResult with aggregated results from all sources
        """
        self._lazy_load()
        start_time = datetime.now()

        operator, value, config = self.parse_at_operator(query)

        if not operator:
            return ATSearchResult(
                operator="unknown",
                query=query,
                entity_type="unknown",
                errors=["No AT operator found. Use cat:, pat:, regat:, litat:, crat:, propat:, wikiat:, newsat:, or tmplat:"]
            )

        result = ATSearchResult(
            operator=operator,
            query=value,
            entity_type=config.get('entity_type', 'unknown'),
            sources_queried=config.get('sources', [])
        )

        # Route to appropriate handler
        try:
            if operator == 'cat:':
                await self._execute_company_search(value, result)
            elif operator == 'pat:':
                await self._execute_person_search(value, result)
            elif operator == 'regat:':
                await self._execute_regulatory_search(value, result)
            elif operator == 'litat:':
                await self._execute_litigation_search(value, result)
            elif operator == 'crat:':
                await self._execute_registry_search(value, result)
            elif operator == 'propat:':
                await self._execute_property_search(value, result)
            elif operator == 'wikiat:':
                await self._execute_wiki_search(value, result)
            elif operator == 'newsat:':
                await self._execute_news_search(value, result)
            elif operator == 'tmplat:':
                await self._execute_template_search(value, result)
        except Exception as e:
            result.errors.append(f"Execution error: {str(e)}")
            logger.error(f"AT CLI execution error: {e}")

        # Calculate execution time
        result.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return result

    # =========================================================================
    # COMPANY SEARCH (cat:)
    # =========================================================================

    async def _execute_company_search(self, query: str, result: ATSearchResult):
        """
        Full Austrian company search across all sources.

        Sources: Firmenbuch (via FirmenABC), Elasticsearch indices
        """
        # 1. Company Registry (FirmenABC wrapper)
        if self._cr:
            try:
                cr_result = await self._cr.search(query)
                result.results['firmenabc'] = cr_result.get('companies', [])
                result.sources_succeeded.append('firmenabc')

                # Add to aggregated companies
                for company in cr_result.get('companies', []):
                    result.companies.append({
                        'name': company.get('name', ''),
                        'fn_number': company.get('fn_number', ''),  # Firmenbuchnummer
                        'uid': company.get('uid', ''),  # UID/VAT number
                        'status': company.get('status', ''),
                        'legal_form': company.get('legal_form', ''),
                        'address': company.get('address', ''),
                        'jurisdiction': 'AT',
                        'source': 'firmenabc'
                    })

                # Add persons (directors, shareholders)
                for person in cr_result.get('persons', []):
                    result.persons.append(person)

            except Exception as e:
                result.sources_failed.append('firmenabc')
                result.errors.append(f"FirmenABC: {str(e)}")

        # 2. Elasticsearch - Austria companies index
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
                                "filter": [{"term": {"jurisdiction": "AT"}}]
                            }
                        },
                        "size": 20
                    }
                )
                hits = es_result.get('hits', {}).get('hits', [])
                result.results['elasticsearch'] = [h['_source'] for h in hits]
                result.sources_succeeded.append('elasticsearch')

                # Add unique companies
                existing_fns = {c.get('fn_number') for c in result.companies if c.get('fn_number')}
                for hit in hits:
                    src = hit['_source']
                    if src.get('fn_number') not in existing_fns:
                        result.companies.append({
                            'name': src.get('name', ''),
                            'fn_number': src.get('fn_number', ''),
                            'status': src.get('status', ''),
                            'jurisdiction': 'AT',
                            'source': 'elasticsearch'
                        })
            except Exception as e:
                result.sources_failed.append('elasticsearch')
                result.errors.append(f"Elasticsearch: {str(e)}")

    # =========================================================================
    # PERSON SEARCH (pat:)
    # =========================================================================

    async def _execute_person_search(self, query: str, result: ATSearchResult):
        """
        Austrian person search - directors, shareholders.
        """
        # 1. Company Registry (search for persons via FirmenABC shareholders)
        if self._cr:
            try:
                cr_result = await self._cr.search_person(query)
                result.results['firmenabc_shareholders'] = cr_result.get('persons', [])
                result.sources_succeeded.append('firmenabc_shareholders')

                for person in cr_result.get('persons', []):
                    result.persons.append({
                        'name': person.get('name', ''),
                        'role': person.get('role', ''),
                        'company': person.get('company', ''),
                        'share_percentage': person.get('share_percentage'),
                        'source': 'firmenabc'
                    })
            except Exception as e:
                result.sources_failed.append('firmenabc_shareholders')
                result.errors.append(f"FirmenABC person search: {str(e)}")

        # 2. Elasticsearch - persons index
        if self._es_client:
            try:
                es_result = self._es_client.search(
                    index="openownership",
                    body={
                        "query": {
                            "bool": {
                                "must": [{"match": {"name": {"query": query, "fuzziness": "AUTO"}}}],
                                "filter": [
                                    {"term": {"entity_type": "person"}},
                                    {"term": {"jurisdiction": "AT"}}
                                ]
                            }
                        },
                        "size": 50
                    }
                )
                hits = es_result.get('hits', {}).get('hits', [])
                result.results['elasticsearch'] = [h['_source'] for h in hits]
                result.sources_succeeded.append('elasticsearch')

                for hit in hits:
                    src = hit['_source']
                    result.persons.append({
                        'name': src.get('name', ''),
                        'nationality': src.get('nationalities', []),
                        'country_of_residence': src.get('country', ''),
                        'associated_company': src.get('interested_party', ''),
                        'source': 'openownership'
                    })
            except Exception as e:
                result.errors.append(f"Elasticsearch person search: {str(e)}")

    # =========================================================================
    # REGULATORY SEARCH (regat:)
    # =========================================================================

    async def _execute_regulatory_search(self, query: str, result: ATSearchResult):
        """
        Austrian regulatory search - FMA Register.
        """
        if self._reg:
            try:
                reg_result = await self._reg.search(query)
                result.results['fma_register'] = reg_result.get('firms', [])
                result.sources_succeeded.append('fma_register')

                for firm in reg_result.get('firms', []):
                    result.companies.append({
                        'name': firm.get('name', ''),
                        'fma_registered': True,
                        'fma_license': firm.get('license', ''),
                        'fma_status': firm.get('status', ''),
                        'jurisdiction': 'AT',
                        'source': 'fma_register'
                    })
            except Exception as e:
                result.sources_failed.append('fma_register')
                result.errors.append(f"FMA Register: {str(e)}")
        else:
            result.results['fma_register'] = {
                'status': 'pending',
                'note': 'FMA search requires at_reg module',
                'url': f'https://www.fma.gv.at/en/search-company-database/'
            }

    # =========================================================================
    # LITIGATION SEARCH (litat:)
    # =========================================================================

    async def _execute_litigation_search(self, query: str, result: ATSearchResult):
        """
        Austrian litigation/insolvency search - Ediktsdatei.
        """
        if self._lit:
            try:
                lit_result = await self._lit.search(query)
                result.results['ediktsdatei'] = lit_result.get('notices', [])
                result.sources_succeeded.append('ediktsdatei')
            except Exception as e:
                result.sources_failed.append('ediktsdatei')
                result.errors.append(f"Ediktsdatei: {str(e)}")
        else:
            result.results['ediktsdatei'] = {
                'status': 'pending',
                'note': 'Ediktsdatei search requires at_lit module',
                'url': f'https://edikte.justiz.gv.at/'
            }

    # =========================================================================
    # REGISTRY SEARCH (crat:)
    # =========================================================================

    async def _execute_registry_search(self, query: str, result: ATSearchResult):
        """
        Direct Firmenbuch lookup (bypass FirmenABC aggregation).
        """
        if self._cr:
            try:
                cr_result = await self._cr.search(query, direct=True)
                result.results['firmenbuch'] = cr_result.get('companies', [])
                result.sources_succeeded.append('firmenbuch')

                for company in cr_result.get('companies', []):
                    result.companies.append({
                        'name': company.get('name', ''),
                        'fn_number': company.get('fn_number', ''),
                        'uid': company.get('uid', ''),
                        'status': company.get('status', ''),
                        'legal_form': company.get('legal_form', ''),
                        'jurisdiction': 'AT',
                        'source': 'firmenbuch'
                    })
            except Exception as e:
                result.sources_failed.append('firmenbuch')
                result.errors.append(f"Firmenbuch: {str(e)}")
        else:
            result.results['firmenbuch'] = {
                'status': 'pending',
                'note': 'Firmenbuch search requires at_cr module',
                'url': f'https://firmenbuch.at/'
            }

    # =========================================================================
    # PROPERTY SEARCH (propat:)
    # =========================================================================

    async def _execute_property_search(self, query: str, result: ATSearchResult):
        """
        Austrian property search - Grundbuch.
        """
        if self._ass:
            try:
                ass_result = await self._ass.search(query)
                result.results['grundbuch'] = ass_result.get('properties', [])
                result.sources_succeeded.append('grundbuch')

                for prop in ass_result.get('properties', []):
                    result.properties.append(prop)
            except Exception as e:
                result.sources_failed.append('grundbuch')
                result.errors.append(f"Grundbuch: {str(e)}")
        else:
            result.results['grundbuch'] = {
                'status': 'pending',
                'note': 'Grundbuch search requires at_ass module',
                'url': 'https://www.bev.gv.at/'
            }

    # =========================================================================
    # WIKI SEARCH (wikiat:)
    # =========================================================================

    def _get_wiki(self):
        """Lazy load AT wiki bridge."""
        if self._wiki is None:
            try:
                from .at_wiki import ATWiki
                self._wiki = ATWiki()
            except ImportError as e:
                logger.warning(f"AT Wiki not available: {e}")
        return self._wiki

    async def _execute_wiki_search(self, query: str, result: ATSearchResult):
        """
        Get Austrian wiki sources and guides.

        Query can be:
        - Empty: Get all sections
        - Section code: cr, lit, reg, ass
        - Search term: Search wiki content
        """
        wiki = self._get_wiki()
        if not wiki:
            result.errors.append("AT Wiki bridge not available")
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
                    'source': 'at_wiki'
                })

            result.sources_succeeded.append('wiki_sections')
        except Exception as e:
            result.errors.append(f"Wiki search failed: {e}")
            result.sources_failed.append('wiki_sections')

    # =========================================================================
    # NEWS SEARCH (newsat:)
    # =========================================================================

    def _get_news(self):
        """Lazy load AT news bridge."""
        if self._news is None:
            try:
                from .at_news import ATNews
                self._news = ATNews()
            except ImportError as e:
                logger.warning(f"AT News not available: {e}")
        return self._news

    async def _execute_news_search(self, query: str, result: ATSearchResult):
        """
        Search Austrian news sites via Torpedo.

        Uses Austrian news site templates for targeted searching.
        """
        news = self._get_news()
        if not news:
            result.errors.append("AT News bridge not available")
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
                    'source': 'at_news'
                })

            if news_result.errors:
                result.errors.extend(news_result.errors)
            else:
                result.sources_succeeded.append('news_recipes')
        except Exception as e:
            result.errors.append(f"News search failed: {e}")
            result.sources_failed.append('news_recipes')

    # =========================================================================
    # TEMPLATES (tmplat:)
    # =========================================================================

    def _get_templates(self):
        """Lazy load AT templates bridge."""
        if self._templates is None:
            try:
                from .at_templates import ATTemplates
                self._templates = ATTemplates()
            except ImportError as e:
                logger.warning(f"AT Templates not available: {e}")
        return self._templates

    async def _execute_template_search(self, query: str, result: ATSearchResult):
        """
        Get Austrian EDITH writing templates.

        Returns standard phrases, footnote formats, and report templates
        for Austrian jurisdiction.
        """
        templates = self._get_templates()
        if not templates:
            result.errors.append("AT Templates bridge not available")
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

def get_at_operators() -> Dict[str, Dict]:
    """Return AT operators for io_cli.py integration."""
    return AT_OPERATORS


def has_at_operator(query: str) -> bool:
    """Check if query has AT operator."""
    cli = ATCLI()
    return cli.has_at_operator(query)


async def execute_at_query(query: str) -> Dict:
    """Execute AT query and return dict result."""
    cli = ATCLI()
    result = await cli.execute(query)
    return result.to_dict()


# =============================================================================
# CLI MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Austria Unified CLI - Search Austrian Public Records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
OPERATORS:
  cat: <company>      Austria company search (Firmenbuch + FirmenABC)
  pat: <person>       Austria person search (directors, shareholders)
  regat: <query>      Austria regulatory search (FMA)
  litat: <query>      Austria litigation/insolvency (Ediktsdatei)
  crat: <company>     Austria direct registry lookup
  propat: <query>     Austria property search (Grundbuch)

EXAMPLES:
  %(prog)s "cat: Erste Bank"
  %(prog)s "pat: Wolfgang Plasser"
  %(prog)s "regat: hedge fund"
  %(prog)s "litat: insolvenz"
        """
    )

    parser.add_argument("query", nargs="?", help="Query with AT operator prefix")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--list-operators", action="store_true", help="List available AT operators")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.list_operators:
        print("\nAUSTRIA PUBLIC RECORDS OPERATORS")
        print("=" * 60)
        for op, config in AT_OPERATORS.items():
            print(f"\n  {op:<12} {config['name']}")
            print(f"              {config['description']}")
            print(f"              Sources: {', '.join(config['sources'])}")
        print()
        return

    if not args.query:
        parser.print_help()
        return

    async def run():
        cli = ATCLI()
        result = await cli.execute(args.query)

        if args.json:
            print(json.dumps(result.to_dict(), indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"AT SEARCH: {result.operator} {result.query}")
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
                    if c.get('fn_number'):
                        print(f"      FN: {c['fn_number']}")
                    if c.get('status'):
                        print(f"      Status: {c['status']}")
                if len(result.companies) > 10:
                    print(f"   ... and {len(result.companies) - 10} more")

            if result.persons:
                print(f"\nPERSONS ({len(result.persons)})")
                for i, p in enumerate(result.persons[:10], 1):
                    role = p.get('role', 'Unknown')
                    print(f"   {i}. {p.get('name', 'Unknown')} ({role})")
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
