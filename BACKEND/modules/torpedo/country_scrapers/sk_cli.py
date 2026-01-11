#!/usr/bin/env python3
"""
Slovakia Unified CLI - Single Entry Point for Slovak Public Records
====================================================================

Combines ALL Slovak public records sources into one unified interface:
1. Obchodny register SR (Commercial Register)
2. Register uctovnych zavierok (Financial Statements)
3. Finstat (company intelligence)
4. NBS (National Bank of Slovakia - financial regulation)
5. Kataster (land/property registry)
6. Torpedo fallback (web scraping)

Designed to integrate with io_cli.py for unified routing.

OPERATOR SYNTAX:
    sk: <query>         - Run ALL SK searches in parallel (unified)
    csk: <company>      - SK company search (Obchodny register + Finstat)
    psk: <person>       - SK person search (directors, shareholders, UBOs)
    regsk: <query>      - SK regulatory search (NBS regulated entities)
    litsk: <query>      - SK litigation/enforcement
    crsk: <company>     - SK corporate registry (Obchodny register direct)
    asssk: <company>    - SK property search (Kataster)
    newssk: <query>     - SK news search (Slovak news sites via Torpedo)

USAGE:
    # From command line
    python sk_cli.py "csk: Tatra banka"
    python sk_cli.py "psk: Jan Novak"
    python sk_cli.py "regsk: investicna spolocnost"
    python sk_cli.py "asssk: Slovnaft"

    # From io_cli.py
    python io_cli.py "csk: Tatra banka"

    # As Python module
    from country_engines.SK.sk_cli import SKCLI
    sk = SKCLI()
    results = await sk.execute("csk: Tatra banka")

ENV VARS:
    FINSTAT_API_KEY      - Finstat API key (optional, enhances data)
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
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

logger = logging.getLogger("sk_cli")


# =============================================================================
# SK OPERATOR DEFINITIONS
# =============================================================================

SK_OPERATORS = {
    'sk:': {
        'name': 'Slovakia Unified Search',
        'entity_type': 'all',
        'sources': ['orsr', 'finstat', 'nbs', 'kataster', 'news_recipes'],
        'description': 'Run ALL SK searches in parallel (company, person, regulatory, litigation, assets, news)',
    },
    'csk:': {
        'name': 'SK Company Search',
        'entity_type': 'company',
        'sources': ['orsr', 'finstat', 'registeruz'],
        'description': 'Search Slovak company registries (Obchodny register + Finstat)',
    },
    'psk:': {
        'name': 'SK Person Search',
        'entity_type': 'person',
        'sources': ['orsr_officers', 'finstat_persons', 'rpvs'],
        'description': 'Search Slovak person records (directors, shareholders, UBOs)',
    },
    'regsk:': {
        'name': 'SK Regulatory Search',
        'entity_type': 'company',
        'sources': ['nbs_register', 'nbs_warnings'],
        'description': 'Search NBS regulated entities and warnings',
    },
    'litsk:': {
        'name': 'SK Litigation/Enforcement',
        'entity_type': 'company',
        'sources': ['justice_gov_sk', 'obchodny_vestnik'],
        'description': 'Search Slovak court records and Obchodny vestnik notices',
    },
    'crsk:': {
        'name': 'SK Corporate Registry',
        'entity_type': 'company',
        'sources': ['orsr'],
        'description': 'Obchodny register SR direct search',
    },
    'asssk:': {
        'name': 'SK Property Search',
        'entity_type': 'property',
        'sources': ['kataster'],
        'description': 'Search Slovak Kataster for property ownership',
    },
    'newssk:': {
        'name': 'SK News Search',
        'entity_type': 'article',
        'category': 'news',
        'sources': ['news_recipes', 'torpedo_news'],
        'description': 'Search Slovak news sites via Torpedo',
    },
}


# =============================================================================
# RESULT DATACLASS
# =============================================================================

@dataclass
class SKSearchResult:
    """Unified Slovakia search result."""
    operator: str
    query: str
    entity_type: str
    jurisdiction: str = "SK"

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
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None and v != [] and v != {}}


# =============================================================================
# SK UNIFIED CLI CLASS
# =============================================================================

class SKCLI:
    """
    Unified Slovakia Public Records CLI.

    Routes SK operators to appropriate sources and aggregates results.
    """

    def __init__(self):
        self._orsr_api = None  # Obchodny register API
        self._finstat_api = None  # Finstat API
        self._nbs_api = None  # NBS API
        self._cr = None  # Company Registry module (sk_cr)
        self._lit = None  # Litigation module (sk_lit)
        self._ass = None  # Assets module (sk_ass)
        self._reg = None  # Regulatory module (sk_reg)
        self._torpedo = None  # Fallback scraper
        self._es_client = None  # Elasticsearch
        self._news = None  # News bridge
        self._loaded = False

    def _lazy_load(self):
        """Lazy load API clients."""
        if self._loaded:
            return

        # Company Registry (Obchodny register + Finstat)
        try:
            from .cr import OrSrAPI, FinstatAPI, SKCompanyRegistry
            self._orsr_api = OrSrAPI()
            self._finstat_api = FinstatAPI()
            self._cr = SKCompanyRegistry()
            logger.info("SK Company Registry loaded")
        except ImportError as e:
            logger.warning(f"SK Company Registry not available: {e}")

        # Regulatory module (NBS)
        try:
            from .reg import NBSAPI, SKRegulatory
            self._nbs_api = NBSAPI()
            self._reg = SKRegulatory()
            logger.info("SK Regulatory module loaded")
        except ImportError as e:
            logger.warning(f"SK Regulatory module not available: {e}")

        # Litigation module
        try:
            from .lit import SKLitigation
            self._lit = SKLitigation()
            logger.info("SK Litigation module loaded")
        except ImportError as e:
            logger.warning(f"SK Litigation module not available: {e}")

        # Assets module (Kataster)
        try:
            from .ass import SKAssets
            self._ass = SKAssets()
            logger.info("SK Assets module loaded")
        except ImportError as e:
            logger.warning(f"SK Assets module not available: {e}")

        # Torpedo (fallback scraper)
        try:
            from TORPEDO.torpedo import Torpedo
            self._torpedo = Torpedo()
            logger.info("Torpedo loaded for SK fallback")
        except ImportError as e:
            logger.warning(f"Torpedo not available: {e}")

        # Elasticsearch
        try:
            from elasticsearch import Elasticsearch
            es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
            self._es_client = Elasticsearch([es_url])
            logger.info("Elasticsearch connected")
        except ImportError:
            logger.warning("Elasticsearch not available")

        self._loaded = True

    def parse_sk_operator(self, query: str) -> Tuple[Optional[str], str, Dict]:
        """
        Parse SK operator from query.

        Returns:
            (operator, value, config) or (None, query, {}) if not SK operator
        """
        query_lower = query.strip().lower()

        for op, config in SK_OPERATORS.items():
            if query_lower.startswith(op):
                value = query.strip()[len(op):].strip()
                return op, value, config

        return None, query, {}

    def has_sk_operator(self, query: str) -> bool:
        """Check if query has a SK operator."""
        op, _, _ = self.parse_sk_operator(query)
        return op is not None

    async def execute(self, query: str) -> SKSearchResult:
        """
        Execute SK query with automatic operator routing.

        Args:
            query: Query with SK operator prefix (e.g., "csk: Tatra banka")

        Returns:
            SKSearchResult with aggregated results from all sources
        """
        self._lazy_load()
        start_time = datetime.now(timezone.utc)

        operator, value, config = self.parse_sk_operator(query)

        if not operator:
            return SKSearchResult(
                operator="unknown",
                query=query,
                entity_type="unknown",
                errors=["No SK operator found. Use sk: (all), csk:, psk:, regsk:, litsk:, crsk:, asssk:, or newssk:"]
            )

        result = SKSearchResult(
            operator=operator,
            query=value,
            entity_type=config.get('entity_type', 'unknown'),
            sources_queried=config.get('sources', [])
        )

        # Route to appropriate handler
        try:
            if operator == 'sk:':
                await self._execute_unified_search(value, result)
            elif operator == 'csk:':
                await self._execute_company_search(value, result)
            elif operator == 'psk:':
                await self._execute_person_search(value, result)
            elif operator == 'regsk:':
                await self._execute_regulatory_search(value, result)
            elif operator == 'litsk:':
                await self._execute_litigation_search(value, result)
            elif operator == 'crsk:':
                await self._execute_registry_search(value, result)
            elif operator == 'asssk:':
                await self._execute_property_search(value, result)
            elif operator == 'newssk:':
                await self._execute_news_search(value, result)
        except Exception as e:
            result.errors.append(f"Execution error: {str(e)}")
            logger.error(f"SK CLI execution error: {e}")

        # Calculate execution time
        result.execution_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        return result

    # =========================================================================
    # UNIFIED SEARCH (sk:) - Runs ALL handlers in parallel
    # =========================================================================

    async def _execute_unified_search(self, query: str, result: SKSearchResult):
        """
        Run ALL SK searches in parallel.

        Executes company, person, regulatory, litigation, assets, and news
        searches concurrently for maximum throughput.
        """
        # Create sub-results for each category
        company_result = SKSearchResult(operator='csk:', query=query, entity_type='company')
        person_result = SKSearchResult(operator='psk:', query=query, entity_type='person')
        regulatory_result = SKSearchResult(operator='regsk:', query=query, entity_type='company')
        litigation_result = SKSearchResult(operator='litsk:', query=query, entity_type='company')
        property_result = SKSearchResult(operator='asssk:', query=query, entity_type='property')
        news_result = SKSearchResult(operator='newssk:', query=query, entity_type='article')

        # Run all searches in parallel
        logger.info(f"SK Unified: Running 6 searches in parallel for '{query}'")

        await asyncio.gather(
            self._execute_company_search(query, company_result),
            self._execute_person_search(query, person_result),
            self._execute_regulatory_search(query, regulatory_result),
            self._execute_litigation_search(query, litigation_result),
            self._execute_property_search(query, property_result),
            self._execute_news_search(query, news_result),
            return_exceptions=True  # Don't fail if one search fails
        )

        # Merge all results into main result
        sub_results = [
            ('company', company_result),
            ('person', person_result),
            ('regulatory', regulatory_result),
            ('litigation', litigation_result),
            ('property', property_result),
            ('news', news_result),
        ]

        for category, sub in sub_results:
            # Merge results dict
            for key, value in sub.results.items():
                result.results[f"{category}_{key}"] = value

            # Merge entities
            result.companies.extend(sub.companies)
            result.persons.extend(sub.persons)
            result.properties.extend(sub.properties)
            result.documents.extend(sub.documents)

            # Merge sources
            result.sources_succeeded.extend(sub.sources_succeeded)
            result.sources_failed.extend(sub.sources_failed)
            result.errors.extend(sub.errors)

        # Deduplicate companies by ICO
        seen_icos = set()
        unique_companies = []
        for company in result.companies:
            ico = company.get('ico') or company.get('company_number')
            if ico and ico in seen_icos:
                continue
            if ico:
                seen_icos.add(ico)
            unique_companies.append(company)
        result.companies = unique_companies

        # Deduplicate persons by name
        seen_names = set()
        unique_persons = []
        for person in result.persons:
            name = person.get('name', '').strip().upper()
            if name and name in seen_names:
                continue
            if name:
                seen_names.add(name)
            unique_persons.append(person)
        result.persons = unique_persons

        logger.info(f"SK Unified: {len(result.companies)} companies, {len(result.persons)} persons, "
                   f"{len(result.properties)} properties")

    # =========================================================================
    # COMPANY SEARCH (csk:)
    # =========================================================================

    async def _execute_company_search(self, query: str, result: SKSearchResult):
        """
        Full SK company search across all sources.

        Sources: Obchodny register, Finstat, Register uctovnych zavierok, Elasticsearch
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            # 1. Obchodny register SR search
            if self._orsr_api:
                try:
                    orsr_results = await self._orsr_api.search_companies(session, query)
                    result.results['orsr'] = orsr_results
                    result.sources_succeeded.append('orsr')

                    # Convert to unified company format
                    for item in orsr_results:
                        result.companies.append({
                            'name': item.get('obchodne_meno', ''),
                            'ico': item.get('ico', ''),
                            'company_number': item.get('ico', ''),  # ICO is the company number in SK
                            'status': item.get('stav', ''),
                            'legal_form': item.get('pravna_forma', ''),
                            'address': item.get('sidlo', ''),
                            'date_of_creation': item.get('datum_vzniku'),
                            'jurisdiction': 'SK',
                            'source': 'orsr'
                        })
                except Exception as e:
                    result.sources_failed.append('orsr')
                    result.errors.append(f"Obchodny register: {str(e)}")

            # 2. Finstat search (enhanced company data)
            if self._finstat_api and self._finstat_api.has_credentials():
                try:
                    finstat_results = await self._finstat_api.search_companies(session, query)
                    result.results['finstat'] = finstat_results
                    result.sources_succeeded.append('finstat')

                    # Match Finstat results to ORSR results or add new
                    for finstat_item in finstat_results:
                        matched = False
                        for company in result.companies:
                            if company.get('ico') == finstat_item.get('ico'):
                                # Enrich existing company
                                company['revenue'] = finstat_item.get('trzby')
                                company['profit'] = finstat_item.get('zisk')
                                company['employees'] = finstat_item.get('pocet_zamestnancov')
                                company['finstat_url'] = finstat_item.get('url')
                                company['sources'] = ['orsr', 'finstat']
                                matched = True
                                break

                        if not matched:
                            result.companies.append({
                                'name': finstat_item.get('nazov', ''),
                                'ico': finstat_item.get('ico', ''),
                                'company_number': finstat_item.get('ico', ''),
                                'revenue': finstat_item.get('trzby'),
                                'profit': finstat_item.get('zisk'),
                                'employees': finstat_item.get('pocet_zamestnancov'),
                                'jurisdiction': 'SK',
                                'source': 'finstat'
                            })
                except Exception as e:
                    result.sources_failed.append('finstat')
                    result.errors.append(f"Finstat: {str(e)}")

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
                                "filter": [{"term": {"jurisdiction": "SK"}}]
                            }
                        },
                        "size": 20
                    }
                )
                hits = es_result.get('hits', {}).get('hits', [])
                result.results['elasticsearch'] = [h['_source'] for h in hits]
                result.sources_succeeded.append('elasticsearch')

                # Add unique companies
                existing_icos = {c.get('ico') for c in result.companies if c.get('ico')}
                for hit in hits:
                    src = hit['_source']
                    if src.get('ico') not in existing_icos:
                        result.companies.append({
                            'name': src.get('name', ''),
                            'ico': src.get('ico', ''),
                            'company_number': src.get('ico', ''),
                            'status': src.get('status', ''),
                            'jurisdiction': 'SK',
                            'source': 'elasticsearch'
                        })
            except Exception as e:
                result.sources_failed.append('elasticsearch')
                result.errors.append(f"Elasticsearch: {str(e)}")

    # =========================================================================
    # PERSON SEARCH (psk:)
    # =========================================================================

    async def _execute_person_search(self, query: str, result: SKSearchResult):
        """
        SK person search - directors, shareholders, UBOs.
        """
        import aiohttp

        # 1. Search via Elasticsearch for persons
        if self._es_client:
            try:
                # Search person entities in OpenOwnership or local index
                person_result = self._es_client.search(
                    index="openownership",
                    body={
                        "query": {
                            "bool": {
                                "must": [{"match": {"name": {"query": query, "fuzziness": "AUTO"}}}],
                                "filter": [
                                    {"term": {"entity_type": "person"}},
                                    {"term": {"jurisdiction": "SK"}}
                                ]
                            }
                        },
                        "size": 50
                    }
                )
                hits = person_result.get('hits', {}).get('hits', [])
                result.results['openownership_persons'] = [h['_source'] for h in hits]
                result.sources_succeeded.append('openownership_persons')

                for hit in hits:
                    src = hit['_source']
                    result.persons.append({
                        'name': src.get('name', ''),
                        'nationality': src.get('nationalities', []),
                        'country_of_residence': src.get('country', ''),
                        'birth_date': src.get('birth_date', ''),
                        'role': 'UBO/Shareholder',
                        'associated_company': src.get('interested_party', ''),
                        'source': 'openownership'
                    })
            except Exception as e:
                result.errors.append(f"Person search: {str(e)}")

        # 2. RPVS (Register partnerov verejneho sektora) - beneficial ownership
        async with aiohttp.ClientSession() as session:
            try:
                # RPVS is publicly available at rpvs.gov.sk
                # For now, provide URL for manual lookup
                result.results['rpvs'] = {
                    'status': 'manual',
                    'note': 'RPVS search available at https://rpvs.gov.sk/',
                    'url': f'https://rpvs.gov.sk/rpvs/Partner/Partner/VyhladatPartnera?nazovMeno={query}'
                }
            except Exception as e:
                result.errors.append(f"RPVS: {str(e)}")

    # =========================================================================
    # REGULATORY SEARCH (regsk:)
    # =========================================================================

    async def _execute_regulatory_search(self, query: str, result: SKSearchResult):
        """
        SK regulatory search - NBS regulated entities.
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            # 1. NBS Register
            if self._nbs_api:
                try:
                    nbs_results = await self._nbs_api.search_regulated_entities(session, query)
                    result.results['nbs_register'] = nbs_results
                    result.sources_succeeded.append('nbs_register')

                    for entity in nbs_results:
                        result.companies.append({
                            'name': entity.get('nazov', ''),
                            'ico': entity.get('ico', ''),
                            'nbs_license_type': entity.get('typ_licencie'),
                            'nbs_status': entity.get('stav'),
                            'nbs_registered': True,
                            'jurisdiction': 'SK',
                            'source': 'nbs'
                        })
                except Exception as e:
                    result.errors.append(f"NBS Register: {str(e)}")
            else:
                # Fallback - provide URL
                result.results['nbs_register'] = {
                    'status': 'manual',
                    'note': 'NBS register available at https://subjekty.nbs.sk/',
                    'url': f'https://subjekty.nbs.sk/vyhladavanie?nazov={query}'
                }

    # =========================================================================
    # LITIGATION SEARCH (litsk:)
    # =========================================================================

    async def _execute_litigation_search(self, query: str, result: SKSearchResult):
        """
        SK litigation/enforcement search.
        Routes to sk_lit.py module.
        """
        if self._lit:
            try:
                lit_result = await self._lit.search(query)

                # Transfer results
                result.results['court_cases'] = getattr(lit_result, 'court_cases', [])
                result.results['obchodny_vestnik'] = getattr(lit_result, 'vestnik_notices', [])

                # Track sources
                result.sources_succeeded.extend(lit_result.sources_succeeded)
                result.sources_failed.extend(lit_result.sources_failed)
                result.errors.extend(lit_result.errors)

            except Exception as e:
                result.errors.append(f"Litigation module error: {str(e)}")
        else:
            # Fallback - provide URLs
            result.results['justice_gov_sk'] = {
                'status': 'manual',
                'note': 'Slovak court records at justice.gov.sk',
                'url': f'https://obcan.justice.sk/infosud/-/infosud/zoznam/rozhodnutia?text={query}'
            }
            result.results['obchodny_vestnik'] = {
                'status': 'manual',
                'note': 'Obchodny vestnik (Commercial Gazette)',
                'url': f'https://www.justice.gov.sk/obchodny-vestnik/'
            }

    # =========================================================================
    # REGISTRY SEARCH (crsk:)
    # =========================================================================

    async def _execute_registry_search(self, query: str, result: SKSearchResult):
        """
        Direct Obchodny register search.
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            if self._orsr_api:
                try:
                    orsr_results = await self._orsr_api.search_companies(session, query, limit=50)
                    result.results['orsr'] = orsr_results
                    result.sources_succeeded.append('orsr')

                    for item in orsr_results:
                        result.companies.append({
                            'name': item.get('obchodne_meno', ''),
                            'ico': item.get('ico', ''),
                            'company_number': item.get('ico', ''),
                            'status': item.get('stav', ''),
                            'legal_form': item.get('pravna_forma', ''),
                            'address': item.get('sidlo', ''),
                            'date_of_creation': item.get('datum_vzniku'),
                            'jurisdiction': 'SK',
                            'source': 'orsr'
                        })
                except Exception as e:
                    result.errors.append(f"Obchodny register: {str(e)}")
            else:
                # Fallback to Torpedo
                if self._torpedo:
                    try:
                        await self._torpedo.load_sources()
                        torpedo_result = await self._torpedo.fetch_profile(query, 'SK')
                        result.results['torpedo'] = torpedo_result
                        result.sources_succeeded.append('torpedo')

                        if torpedo_result.get('profile'):
                            result.companies.append({
                                **torpedo_result['profile'],
                                'jurisdiction': 'SK',
                                'source': 'torpedo'
                            })
                    except Exception as e:
                        result.errors.append(f"Torpedo: {str(e)}")

    # =========================================================================
    # ASSETS SEARCH (asssk:) - Kataster
    # =========================================================================

    async def _execute_property_search(self, query: str, result: SKSearchResult):
        """
        SK Kataster (cadastre) property search.
        Routes to sk_ass.py module.
        """
        if self._ass:
            try:
                ass_result = await self._ass.search(query)

                # Transfer results
                result.results['kataster'] = ass_result.properties
                result.results['property_summary'] = ass_result.summary

                # Add properties to result
                for prop in ass_result.properties:
                    result.properties.append(prop)

                # Track sources
                result.sources_succeeded.extend(ass_result.sources_succeeded)
                result.sources_failed.extend(ass_result.sources_failed)
                result.errors.extend(ass_result.errors)

            except Exception as e:
                result.errors.append(f"Assets module error: {str(e)}")
        else:
            result.results['kataster'] = {
                'status': 'manual',
                'note': 'Slovak Kataster portal not integrated. Manual lookup required.',
                'url': 'https://kataster.skgeodesy.sk/eskn-portal/'
            }

    # =========================================================================
    # NEWS SEARCH (newssk:)
    # =========================================================================

    def _get_news(self):
        """Lazy load SK news bridge."""
        if self._news is None:
            try:
                from .sk_news import SKNews
                self._news = SKNews()
            except ImportError:
                # Fallback for when loaded without package context
                try:
                    import importlib.util
                    news_path = Path(__file__).parent / "sk_news.py"
                    spec = importlib.util.spec_from_file_location("sk_news", str(news_path))
                    if spec and spec.loader:
                        sk_news = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(sk_news)
                        self._news = sk_news.SKNews()
                except Exception as e:
                    logger.warning(f"SK News not available: {e}")
        return self._news

    async def _execute_news_search(self, query: str, result: SKSearchResult):
        """
        Search SK news sites via Torpedo.

        Uses Slovak news site templates for targeted searching.
        """
        news = self._get_news()
        if not news:
            result.errors.append("SK News bridge not available")
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
                    'source': 'sk_news'
                })

            if news_result.errors:
                result.errors.extend(news_result.errors)
            else:
                result.sources_succeeded.append('news_recipes')
        except Exception as e:
            result.errors.append(f"News search failed: {e}")
            result.sources_failed.append('news_recipes')

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _names_match(self, name1: str, name2: str) -> bool:
        """Fuzzy name matching for company names."""
        def normalize(s: str) -> str:
            s = s.upper()
            # Remove Slovak legal form designators
            s = re.sub(r'\b(S\.?R\.?O\.?|A\.?S\.?|K\.?S\.?|SPOL\.? S R\.?O\.?|AKCIOVA SPOLOCNOST)\b', '', s)
            s = re.sub(r'[^A-Z0-9]', '', s)
            return s

        n1, n2 = normalize(name1), normalize(name2)
        if not n1 or not n2:
            return False

        return n1 == n2 or n1 in n2 or n2 in n1


# =============================================================================
# INTEGRATION WITH IO_CLI
# =============================================================================

def get_sk_operators() -> Dict[str, Dict]:
    """Return SK operators for io_cli.py integration."""
    return SK_OPERATORS


def has_sk_operator(query: str) -> bool:
    """Check if query has SK operator."""
    cli = SKCLI()
    return cli.has_sk_operator(query)


async def execute_sk_query(query: str) -> Dict:
    """Execute SK query and return dict result."""
    cli = SKCLI()
    result = await cli.execute(query)
    return result.to_dict()


# =============================================================================
# CLI MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Slovakia Unified CLI - Search Slovak Public Records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
OPERATORS:
  sk: <query>         Run ALL SK searches in parallel (unified)
  csk: <company>      SK company search (Obchodny register + Finstat)
  psk: <person>       SK person search (directors, shareholders, UBOs)
  regsk: <query>      SK regulatory search (NBS regulated)
  litsk: <query>      SK litigation/enforcement
  crsk: <company>     SK corporate registry (Obchodny register direct)
  asssk: <company>    SK property search (Kataster)
  newssk: <query>     SK news search

EXAMPLES:
  %(prog)s "sk: Tatra banka"         # Full investigation
  %(prog)s "csk: Slovnaft"           # Company only
  %(prog)s "psk: Jan Novak"          # Person only
  %(prog)s "newssk: korupcia"        # News only
  %(prog)s "asssk: VUB"              # Property only
        """
    )

    parser.add_argument("query", nargs="?", help="Query with SK operator prefix")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--list-operators", action="store_true", help="List available SK operators")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.list_operators:
        print("\nSLOVAKIA PUBLIC RECORDS OPERATORS")
        print("=" * 60)
        for op, config in SK_OPERATORS.items():
            print(f"\n  {op:<12} {config['name']}")
            print(f"              {config['description']}")
            print(f"              Sources: {', '.join(config['sources'])}")
        print()
        return

    if not args.query:
        parser.print_help()
        return

    async def run():
        cli = SKCLI()
        result = await cli.execute(args.query)

        if args.json:
            print(json.dumps(result.to_dict(), indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"SK SEARCH: {result.operator} {result.query}")
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
                    if c.get('ico'):
                        print(f"      ICO: {c['ico']}")
                    if c.get('status'):
                        print(f"      Status: {c['status']}")
                    if c.get('nbs_registered'):
                        print(f"      NBS Regulated: Yes")
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
                    print(f"      Owner: {prop.get('owner', 'Unknown')}")

            if result.errors:
                print(f"\nERRORS:")
                for err in result.errors:
                    print(f"   - {err}")

            print(f"\nExecution time: {result.execution_time_ms}ms")

    asyncio.run(run())


if __name__ == "__main__":
    main()
