#!/usr/bin/env python3
"""
AUTOMATED BACKLINK PIPELINE
Given a target domain, automatically:
1. Query Common Crawl Index API to find WARC locations
2. Use GlobalLinks to extract outbound URLs from WARCs
3. Use Majestic in parallel for page-level backlinks with anchor texts
4. Combine and deduplicate results
4b. FILETYPE TRIANGULATION: Score domains by document presence (PDFs boost credibility)
4c. PDF DISCOVERY (optional): Fetch actual PDF URLs from high-scoring domains
5. OPTIONAL: Extract entities from referring pages (know WHO is linking, not just WHERE)

Integration Architecture:
- Phase 4b (our triangulation) identifies domains with good filetype profiles
- Phase 4c (other Claude's discovery) fetches actual PDFs from those domains
- The two systems are complementary: triangulation scores, discovery retrieves
"""
import asyncio
import sys
from pathlib import Path
import requests
from typing import List, Dict, Any, Optional
from collections import defaultdict
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.linklater.api import linklater

# Import entity extraction and scraping
try:
    from modules.linklater.scraping.cc_first_scraper import scrape_urls_with_entities
    from modules.linklater.mapping.entity_extractor import extract_entities
    ENTITY_EXTRACTION_AVAILABLE = True
except ImportError:
    ENTITY_EXTRACTION_AVAILABLE = False
    scrape_urls_with_entities = None
    extract_entities = None

# Import filetype scoring for triangulation
try:
    from modules.linklater.mapping.filetype_index import FiletypeIndexManager
    from modules.linklater.scoring.filetype_scorer import FiletypeCredibilityScorer
    FILETYPE_SCORING_AVAILABLE = True
except ImportError:
    FILETYPE_SCORING_AVAILABLE = False
    FiletypeIndexManager = None
    FiletypeCredibilityScorer = None

# Import unified discovery for PDF discovery (Phase 4c)
try:
    from modules.linklater.mapping.unified_discovery import UnifiedDiscovery
    PDF_DISCOVERY_AVAILABLE = True
except ImportError:
    PDF_DISCOVERY_AVAILABLE = False
    UnifiedDiscovery = None


class AutomatedBacklinkPipeline:
    """Fully automated backlink discovery pipeline with optional entity extraction"""

    def __init__(
        self,
        target_domain: str,
        extract_entities: bool = False,
        max_entity_pages: int = 50,
        entity_method: str = "gpt5nano",
        discover_pdfs: bool = False,
        pdf_score_threshold: float = 80.0,
        max_pdf_domains: int = 10,
        pdf_years: List[int] = None
    ):
        """
        Initialize backlink pipeline.

        Args:
            target_domain: Domain to find backlinks for
            extract_entities: Whether to extract entities from referring pages
            max_entity_pages: Max pages to scrape for entity extraction (to control costs)
            entity_method: Entity extraction method ('gpt5nano' or 'regex')
            discover_pdfs: Whether to discover PDFs from high-scoring domains (Phase 4c)
            pdf_score_threshold: Minimum triangulated score to trigger PDF discovery
            max_pdf_domains: Max domains to search for PDFs
            pdf_years: Years to search for annual reports (default: [2024, 2023, 2022])
        """
        self.target_domain = target_domain
        # Use November 2025 archive (matches Sep-Oct-Nov domain graph)
        self.cc_index_url = "https://index.commoncrawl.org/CC-MAIN-2025-47-index"
        self.extract_entities = extract_entities and ENTITY_EXTRACTION_AVAILABLE
        self.max_entity_pages = max_entity_pages
        self.entity_method = entity_method

        # PDF discovery settings (Phase 4c)
        self.discover_pdfs = discover_pdfs and PDF_DISCOVERY_AVAILABLE
        self.pdf_score_threshold = pdf_score_threshold
        self.max_pdf_domains = max_pdf_domains
        self.pdf_years = pdf_years or [2024, 2023, 2022]

        if extract_entities and not ENTITY_EXTRACTION_AVAILABLE:
            print("⚠️  Entity extraction requested but not available (missing imports)")

        if discover_pdfs and not PDF_DISCOVERY_AVAILABLE:
            print("⚠️  PDF discovery requested but not available (missing imports)")

    async def run(self, max_results: int = 100):
        """Execute full pipeline"""
        
        print("=" * 100)
        print(f"AUTOMATED BACKLINK PIPELINE: {self.target_domain}")
        print("=" * 100)
        print()
        
        # PHASE 1: Common Crawl Index Lookup
        print("PHASE 1: Common Crawl Index Lookup")
        print("-" * 100)
        warc_locations = await self.find_warc_locations()
        print(f"✅ Found {len(warc_locations)} WARC locations containing {self.target_domain}")
        print()
        
        # PHASE 2 & 3: Run in parallel
        print("PHASE 2 & 3: Parallel Backlink Discovery")
        print("-" * 100)
        print("  - GlobalLinks (WAT file processing)")
        print("  - Majestic Fresh + Historic (page-level with anchors)")
        print()
        
        # Run GlobalLinks and Majestic in parallel
        globallinks_task = self.get_globallinks_backlinks(max_results)
        majestic_task = self.get_majestic_backlinks(max_results)
        
        globallinks_results, majestic_results = await asyncio.gather(
            globallinks_task,
            majestic_task,
            return_exceptions=True
        )
        
        # Handle errors
        if isinstance(globallinks_results, Exception):
            print(f"⚠️  GlobalLinks error: {globallinks_results}")
            globallinks_results = []
        
        if isinstance(majestic_results, Exception):
            print(f"⚠️  Majestic error: {majestic_results}")
            majestic_results = []
        
        # PHASE 4: Combine and deduplicate
        print("\nPHASE 4: Combining Results")
        print("-" * 100)
        combined = self.combine_results(globallinks_results, majestic_results)

        # PHASE 4b: Filetype Triangulation (boost domains with PDFs)
        if FILETYPE_SCORING_AVAILABLE:
            print("\nPHASE 4b: Filetype Triangulation")
            print("-" * 100)
            combined = await self.apply_filetype_triangulation(combined)
        else:
            print("\n⚠️  Filetype scoring not available (missing imports)")

        # PHASE 4c: PDF Discovery from High-Scoring Domains (optional)
        if self.discover_pdfs:
            print("\nPHASE 4c: PDF Discovery from High-Scoring Domains")
            print("-" * 100)
            combined = await self.discover_pdfs_from_sources(combined)

        # PHASE 5: Entity Extraction (optional)
        if self.extract_entities:
            print("\nPHASE 5: Entity Extraction from Referring Pages")
            print("-" * 100)
            combined = await self.extract_entities_from_backlinks(combined)

        # PHASE 6: Analysis
        print("\nPHASE 6: Analysis")
        print("-" * 100)
        self.analyze_results(combined, globallinks_results, majestic_results)

        return combined
    
    async def find_warc_locations(self) -> List[Dict[str, Any]]:
        """Query Common Crawl Index API to find WARC locations"""
        
        print(f"🔍 Querying CC Index API for: {self.target_domain}")
        
        # Query CC Index
        url = f"{self.cc_index_url}?url={self.target_domain}&output=json"
        
        try:
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                # Parse JSONL response
                warc_records = []
                for line in response.text.strip().split('\n'):
                    if line:
                        import json
                        record = json.loads(line)
                        warc_records.append({
                            'url': record.get('url'),
                            'filename': record.get('filename'),
                            'offset': record.get('offset'),
                            'length': record.get('length'),
                            'timestamp': record.get('timestamp')
                        })
                
                print(f"   Found {len(warc_records)} WARC records")
                return warc_records[:10]  # Limit to first 10
            else:
                print(f"   ⚠️  HTTP {response.status_code}")
                return []
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return []
    
    async def get_globallinks_backlinks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get backlinks from GlobalLinks (WAT processing)"""
        
        print("\n📊 GlobalLinks: Querying WAT files...")
        
        try:
            backlinks = await linklater.get_backlinks(
                self.target_domain,
                limit=limit,
                use_globallinks=True
            )
            
            # Filter for GlobalLinks only
            gl_backlinks = [b for b in backlinks if b.provider == 'globallinks']
            
            print(f"   ✅ Found {len(gl_backlinks)} backlinks from GlobalLinks")
            
            return [{
                'source': b.source,
                'target': b.target,
                'provider': 'globallinks',
                'anchor_text': getattr(b, 'anchor_text', None)
            } for b in gl_backlinks]
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            raise
    
    async def get_majestic_backlinks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get backlinks from Majestic (Fresh + Historic)"""
        
        print("\n📊 Majestic: Querying Fresh + Historic indexes...")
        
        try:
            # Query both Fresh and Historic in parallel
            fresh_task = linklater.get_majestic_backlinks(
                self.target_domain,
                mode="fresh",
                result_type="pages",
                max_results=limit
            )
            
            historic_task = linklater.get_majestic_backlinks(
                self.target_domain,
                mode="historic",
                result_type="pages",
                max_results=limit
            )
            
            fresh, historic = await asyncio.gather(fresh_task, historic_task)
            
            print(f"   ✅ Majestic Fresh: {len(fresh)} backlinks")
            print(f"   ✅ Majestic Historic: {len(historic)} backlinks")
            
            # Combine and normalize
            all_majestic = []
            
            for bl in fresh + historic:
                all_majestic.append({
                    'source': bl.get('source_url', ''),
                    'target': bl.get('target_url', ''),
                    'provider': 'majestic',
                    'anchor_text': bl.get('anchor_text', ''),
                    'source_domain': bl.get('source_domain', ''),
                    'trust_flow': bl.get('trust_flow', 0),
                    'citation_flow': bl.get('citation_flow', 0)
                })
            
            return all_majestic
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            raise
    
    def combine_results(
        self,
        globallinks: List[Dict],
        majestic: List[Dict]
    ) -> Dict[str, Any]:
        """Combine and deduplicate results from all sources"""
        
        # Deduplicate by source URL
        by_source = defaultdict(lambda: {'providers': set(), 'data': {}})
        
        for bl in globallinks:
            source = bl['source']
            by_source[source]['providers'].add('globallinks')
            by_source[source]['data'].update(bl)
        
        for bl in majestic:
            source = bl['source']
            by_source[source]['providers'].add('majestic')
            
            # Merge data (prefer Majestic for anchor text/metrics)
            existing = by_source[source]['data']
            by_source[source]['data'] = {**existing, **bl}
        
        # Convert to list
        combined = []
        for source, info in by_source.items():
            combined.append({
                **info['data'],
                'found_in': list(info['providers'])
            })
        
        print(f"\n✅ Combined: {len(combined)} unique backlinks")
        print(f"   - GlobalLinks only: {len([c for c in combined if c['found_in'] == ['globallinks']])}")
        print(f"   - Majestic only: {len([c for c in combined if c['found_in'] == ['majestic']])}")
        print(f"   - Both sources: {len([c for c in combined if len(c['found_in']) == 2])}")
        
        return {
            'target_domain': self.target_domain,
            'total_backlinks': len(combined),
            'globallinks_count': len(globallinks),
            'majestic_count': len(majestic),
            'backlinks': combined
        }

    async def apply_filetype_triangulation(self, combined: Dict[str, Any]) -> Dict[str, Any]:
        """
        PHASE 4b: Boost credibility scores based on filetype presence.

        Domains hosting PDFs and structured documents (especially annual reports)
        are more likely to be authoritative sources. This phase:
        1. Extracts unique source domains from backlinks
        2. Batch lookups filetype profiles from cc_domain_filetypes index
        3. Applies credibility bonuses based on document presence
        4. Re-sorts results by triangulated score

        Scoring Bonuses:
        - Has any PDFs: +10
        - Has 20+ PDFs: +15
        - Has 100+ PDFs: +18
        - Has annual reports: +20
        - Has 3+ filetype categories: +5
        - Authority score bonuses: +2-10

        Args:
            combined: Combined backlink results from Phase 4

        Returns:
            Updated combined dict with filetype-boosted scores
        """
        backlinks = combined['backlinks']

        if not backlinks:
            print("⚠️  No backlinks to triangulate")
            return combined

        # Extract unique source domains
        source_domains = set()
        for bl in backlinks:
            domain = bl.get('source_domain', '')
            if not domain and bl.get('source'):
                parsed = urlparse(
                    bl['source'] if bl['source'].startswith('http') else f"http://{bl['source']}"
                )
                domain = parsed.netloc.lower()
            if domain:
                source_domains.add(domain)

        print(f"🔍 Looking up filetype profiles for {len(source_domains)} unique domains...")

        # Initialize filetype index manager and scorer
        index_manager = FiletypeIndexManager()
        scorer = FiletypeCredibilityScorer()

        # Batch lookup filetype profiles
        try:
            profiles = await index_manager.batch_lookup(list(source_domains))
            print(f"   ✅ Found {len(profiles)} filetype profiles in index")
        except Exception as e:
            print(f"   ❌ Filetype lookup error: {e}")
            profiles = {}

        # Apply scores to each backlink
        boosted_count = 0
        total_bonus = 0

        for bl in backlinks:
            # Get domain
            domain = bl.get('source_domain', '')
            if not domain and bl.get('source'):
                parsed = urlparse(
                    bl['source'] if bl['source'].startswith('http') else f"http://{bl['source']}"
                )
                domain = parsed.netloc.lower()

            # Get base score (from Majestic TrustFlow or default)
            base_score = bl.get('trust_flow', 0) or 40

            # Look up profile and score
            profile = profiles.get(domain)
            result = scorer.score(profile, base_score)

            # Update backlink with scores
            bl['base_score'] = result.base_score
            bl['filetype_bonus'] = result.filetype_bonus
            bl['triangulated_score'] = result.total_score
            bl['filetype_explanation'] = result.explanation
            bl['filetype_profile_found'] = result.profile_found

            if result.filetype_bonus > 0:
                boosted_count += 1
                total_bonus += result.filetype_bonus

        # Sort by triangulated score (highest first)
        backlinks.sort(key=lambda x: x.get('triangulated_score', 0), reverse=True)

        # Print summary
        avg_bonus = total_bonus / boosted_count if boosted_count else 0

        print(f"\n✅ Filetype Triangulation Complete:")
        print(f"   - Domains with profiles: {len(profiles)}/{len(source_domains)}")
        print(f"   - Backlinks boosted: {boosted_count}/{len(backlinks)}")
        if boosted_count:
            print(f"   - Average bonus: +{avg_bonus:.1f} points")

        # Show top 5 boosted domains
        if boosted_count:
            print(f"\n📄 Top PDF-Rich Referring Domains:")
            seen_domains = set()
            top_shown = 0
            for bl in backlinks:
                if bl.get('filetype_bonus', 0) > 0 and top_shown < 5:
                    domain = bl.get('source_domain', '')
                    if not domain:
                        parsed = urlparse(bl.get('source', ''))
                        domain = parsed.netloc
                    if domain and domain not in seen_domains:
                        seen_domains.add(domain)
                        print(f"   • {domain:<40} +{bl['filetype_bonus']:.0f} ({bl['filetype_explanation'][:50]}...)")
                        top_shown += 1

        # Add triangulation stats to combined
        combined['filetype_triangulation'] = {
            'enabled': True,
            'domains_looked_up': len(source_domains),
            'profiles_found': len(profiles),
            'backlinks_boosted': boosted_count,
            'total_bonus_applied': total_bonus,
            'average_bonus': avg_bonus
        }

        combined['backlinks'] = backlinks
        return combined

    async def discover_pdfs_from_sources(self, combined: Dict[str, Any]) -> Dict[str, Any]:
        """
        PHASE 4c: Discover PDFs from high-scoring referring domains.

        Uses UnifiedDiscovery.discover_annual_reports() to find actual PDF documents
        from domains that scored well in Phase 4b triangulation. This connects our
        scoring system with the actual document discovery.

        Integration Point:
        - Phase 4b identifies domains with good filetype profiles (scoring)
        - Phase 4c uses those scores to fetch actual PDF URLs (discovery)

        Args:
            combined: Combined results from Phase 4b with triangulated scores

        Returns:
            Updated combined dict with discovered PDFs attached
        """
        backlinks = combined.get('backlinks', [])

        # Find high-scoring domains with filetype profiles
        high_value_domains = []
        seen_domains = set()

        for bl in backlinks:
            score = bl.get('triangulated_score', 0)
            profile_found = bl.get('filetype_profile_found', False)

            if score >= self.pdf_score_threshold and profile_found:
                domain = bl.get('source_domain', '')
                if not domain and bl.get('source'):
                    parsed = urlparse(
                        bl['source'] if bl['source'].startswith('http') else f"http://{bl['source']}"
                    )
                    domain = parsed.netloc.lower()

                if domain and domain not in seen_domains:
                    seen_domains.add(domain)
                    high_value_domains.append({
                        'domain': domain,
                        'score': score,
                        'filetype_bonus': bl.get('filetype_bonus', 0)
                    })

        # Sort by score and take top N
        high_value_domains.sort(key=lambda x: x['score'], reverse=True)
        high_value_domains = high_value_domains[:self.max_pdf_domains]

        if not high_value_domains:
            print(f"   No domains scored >= {self.pdf_score_threshold} with filetype profiles")
            combined['pdf_discovery'] = {
                'enabled': True,
                'threshold': self.pdf_score_threshold,
                'domains_searched': 0,
                'pdfs_found': 0,
                'pdfs_by_domain': {}
            }
            return combined

        print(f"🔍 Searching for PDFs on {len(high_value_domains)} high-scoring domains...")
        print(f"   Score threshold: >= {self.pdf_score_threshold}")
        print(f"   Years to search: {self.pdf_years}")

        # Initialize unified discovery
        discovery = UnifiedDiscovery()
        pdfs_by_domain = {}
        total_pdfs = 0

        for item in high_value_domains:
            domain = item['domain']
            print(f"\n   📄 {domain} (score: {item['score']:.0f})...")

            try:
                response = await discovery.discover_annual_reports(
                    domain=domain,
                    years=self.pdf_years,
                    verify=True,
                    top_n=20
                )

                if response.total_found > 0:
                    pdfs_by_domain[domain] = {
                        'count': response.total_found,
                        'pdfs': [
                            {
                                'url': r.value,
                                'confidence': r.confidence,
                                'score': r.metadata.get('score', 0),
                                'year': r.metadata.get('extracted_year'),
                                'verified': r.metadata.get('verified', False)
                            }
                            for r in response.results[:10]  # Top 10 per domain
                        ]
                    }
                    total_pdfs += response.total_found
                    print(f"      ✅ Found {response.total_found} PDFs")

                    # Show top 3 PDFs
                    for pdf in pdfs_by_domain[domain]['pdfs'][:3]:
                        year_str = f" ({pdf['year']})" if pdf['year'] else ""
                        verified = " ✓" if pdf['verified'] else ""
                        print(f"         • {pdf['url'][:60]}...{year_str}{verified}")
                else:
                    print(f"      No PDFs found")

            except Exception as e:
                print(f"      ❌ Error: {e}")

        # Summary
        print(f"\n✅ PDF Discovery Complete:")
        print(f"   - Domains searched: {len(high_value_domains)}")
        print(f"   - Domains with PDFs: {len(pdfs_by_domain)}")
        print(f"   - Total PDFs found: {total_pdfs}")

        # Attach PDF URLs to backlinks
        for bl in backlinks:
            domain = bl.get('source_domain', '')
            if not domain and bl.get('source'):
                parsed = urlparse(bl.get('source', ''))
                domain = parsed.netloc.lower()

            if domain in pdfs_by_domain:
                bl['discovered_pdfs'] = pdfs_by_domain[domain]['pdfs']
                bl['pdf_count'] = pdfs_by_domain[domain]['count']

        combined['backlinks'] = backlinks
        combined['pdf_discovery'] = {
            'enabled': True,
            'threshold': self.pdf_score_threshold,
            'years_searched': self.pdf_years,
            'domains_searched': len(high_value_domains),
            'domains_with_pdfs': len(pdfs_by_domain),
            'pdfs_found': total_pdfs,
            'pdfs_by_domain': pdfs_by_domain
        }

        return combined

    async def extract_entities_from_backlinks(self, combined: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract entities from referring pages to know WHO is linking, not just WHERE.

        This fetches content from the top referring pages (by TrustFlow or random
        if no metrics) and extracts persons, companies, emails, phones, addresses.

        Args:
            combined: Combined backlink results from Phase 4

        Returns:
            Updated combined dict with entities attached to backlinks
        """
        backlinks = combined['backlinks']

        if not backlinks:
            print("⚠️  No backlinks to extract entities from")
            return combined

        # Prioritize pages with higher TrustFlow, then random
        sorted_backlinks = sorted(
            backlinks,
            key=lambda x: (x.get('trust_flow', 0), x.get('citation_flow', 0)),
            reverse=True
        )

        # Limit to max_entity_pages
        urls_to_scrape = []
        url_to_backlink_idx = {}

        for i, bl in enumerate(sorted_backlinks[:self.max_entity_pages]):
            source_url = bl.get('source')
            if source_url and source_url.startswith('http'):
                urls_to_scrape.append(source_url)
                url_to_backlink_idx[source_url] = i

        if not urls_to_scrape:
            print("⚠️  No valid URLs to scrape for entities")
            return combined

        print(f"🔍 Scraping {len(urls_to_scrape)} referring pages for entity extraction...")
        print(f"   (Limited to top {self.max_entity_pages} by TrustFlow)")

        # Batch scrape with entity extraction
        try:
            scrape_results = await scrape_urls_with_entities(
                urls_to_scrape,
                max_concurrent=10  # Conservative to avoid rate limits
            )

            # Attach entities to backlinks
            entities_found = 0
            pages_with_entities = 0

            for url, result in scrape_results.items():
                idx = url_to_backlink_idx.get(url)
                if idx is None:
                    continue

                # Get entities from scrape result
                entities = []
                if hasattr(result, 'entities') and result.entities:
                    entities = result.entities
                elif result.content:
                    # Fallback: extract from content directly
                    extraction = extract_entities(
                        result.content,
                        source_url=url,
                        method=self.entity_method
                    )
                    entities = extraction.get('entities', [])

                # Attach to backlink
                sorted_backlinks[idx]['entities'] = entities
                sorted_backlinks[idx]['entity_count'] = len(entities)
                sorted_backlinks[idx]['content_fetched'] = bool(result.content)

                if entities:
                    pages_with_entities += 1
                    entities_found += len(entities)

            print(f"\n✅ Entity Extraction Complete:")
            print(f"   - Pages scraped: {len(scrape_results)}")
            print(f"   - Pages with entities: {pages_with_entities}")
            print(f"   - Total entities found: {entities_found}")

            # Update combined with entity stats
            combined['entity_extraction'] = {
                'enabled': True,
                'pages_scraped': len(scrape_results),
                'pages_with_entities': pages_with_entities,
                'total_entities': entities_found,
                'method': self.entity_method
            }

            # Re-order backlinks to put entity-enriched ones first
            combined['backlinks'] = sorted_backlinks

        except Exception as e:
            print(f"❌ Entity extraction error: {e}")
            combined['entity_extraction'] = {
                'enabled': True,
                'error': str(e)
            }

        return combined

    def analyze_results(
        self,
        combined: Dict,
        globallinks: List[Dict],
        majestic: List[Dict]
    ):
        """Analyze combined results"""
        
        backlinks = combined['backlinks']
        
        # Group by domain
        by_domain = defaultdict(list)
        for bl in backlinks:
            domain = bl.get('source_domain', '')
            if not domain and bl.get('source'):
                # Extract domain from URL
                from urllib.parse import urlparse
                parsed = urlparse(bl['source'] if bl['source'].startswith('http') else f"http://{bl['source']}")
                domain = parsed.netloc
            
            by_domain[domain].append(bl)
        
        print(f"\n📊 Unique Referring Domains: {len(by_domain)}")
        
        # Top domains
        top_domains = sorted(by_domain.items(), key=lambda x: len(x[1]), reverse=True)[:10]
        
        print("\nTop 10 Referring Domains:")
        for domain, links in top_domains:
            print(f"   {domain:<40} {len(links):>3} backlinks")
        
        # Anchor text analysis (from Majestic)
        anchors = defaultdict(int)
        for bl in backlinks:
            anchor = bl.get('anchor_text', '') or ''
            anchor_clean = anchor.strip() if anchor else ''
            if anchor_clean:
                anchors[anchor_clean] += 1
        
        if anchors:
            print(f"\n📝 Unique Anchor Texts: {len(anchors)}")
            top_anchors = sorted(anchors.items(), key=lambda x: x[1], reverse=True)[:10]
            print("\nTop 10 Anchor Texts:")
            for anchor, count in top_anchors:
                print(f"   \"{anchor[:50]:<50}\" {count:>3}x")
        
        # TrustFlow distribution (from Majestic)
        tf_scores = [bl.get('trust_flow', 0) for bl in backlinks if bl.get('trust_flow')]
        if tf_scores:
            avg_tf = sum(tf_scores) / len(tf_scores)
            max_tf = max(tf_scores)
            print(f"\n📈 TrustFlow: Avg={avg_tf:.1f}, Max={max_tf}")

        # Entity analysis (if extraction was performed)
        entity_extraction = combined.get('entity_extraction', {})
        if entity_extraction.get('enabled') and not entity_extraction.get('error'):
            # Aggregate entities across all backlinks
            all_persons = defaultdict(int)
            all_companies = defaultdict(int)
            all_emails = defaultdict(int)
            all_phones = defaultdict(int)
            all_addresses = defaultdict(int)

            for bl in backlinks:
                entities = bl.get('entities', [])
                for entity in entities:
                    entity_type = entity.get('type', '').lower()
                    value = entity.get('value', '').strip()
                    if not value:
                        continue

                    if entity_type == 'person':
                        all_persons[value] += 1
                    elif entity_type == 'company':
                        all_companies[value] += 1
                    elif entity_type == 'email':
                        all_emails[value.lower()] += 1
                    elif entity_type == 'phone':
                        all_phones[value] += 1
                    elif entity_type == 'address':
                        all_addresses[value] += 1

            print(f"\n👥 ENTITIES DISCOVERED (WHO is linking):")
            print("-" * 50)

            if all_persons:
                print(f"\n🧑 Persons ({len(all_persons)} unique):")
                top_persons = sorted(all_persons.items(), key=lambda x: x[1], reverse=True)[:10]
                for person, count in top_persons:
                    print(f"   • {person:<40} (mentioned {count}x)")

            if all_companies:
                print(f"\n🏢 Companies ({len(all_companies)} unique):")
                top_companies = sorted(all_companies.items(), key=lambda x: x[1], reverse=True)[:10]
                for company, count in top_companies:
                    print(f"   • {company:<40} (mentioned {count}x)")

            if all_emails:
                print(f"\n📧 Emails ({len(all_emails)} unique):")
                top_emails = sorted(all_emails.items(), key=lambda x: x[1], reverse=True)[:10]
                for email, count in top_emails:
                    print(f"   • {email:<40} (mentioned {count}x)")

            if all_phones:
                print(f"\n📞 Phones ({len(all_phones)} unique):")
                top_phones = sorted(all_phones.items(), key=lambda x: x[1], reverse=True)[:10]
                for phone, count in top_phones:
                    print(f"   • {phone:<40} (mentioned {count}x)")

            if all_addresses:
                print(f"\n📍 Addresses ({len(all_addresses)} unique):")
                top_addresses = sorted(all_addresses.items(), key=lambda x: x[1], reverse=True)[:5]
                for address, count in top_addresses:
                    print(f"   • {address[:60]:<60} (mentioned {count}x)")

            # Store aggregated entities in combined
            combined['aggregated_entities'] = {
                'persons': dict(all_persons),
                'companies': dict(all_companies),
                'emails': dict(all_emails),
                'phones': dict(all_phones),
                'addresses': dict(all_addresses),
            }


# Convenience function for API integration
async def discover_backlinks_with_entities(
    target_domain: str,
    max_results: int = 100,
    max_entity_pages: int = 50,
    entity_method: str = "gpt5nano"
) -> Dict[str, Any]:
    """
    Discover backlinks AND extract entities from referring pages.

    This is the main integration point for the backlink pipeline with
    entity extraction. Use this to know WHO is linking, not just WHERE.

    Args:
        target_domain: Domain to find backlinks for
        max_results: Max backlinks to retrieve
        max_entity_pages: Max pages to scrape for entities (costs API calls)
        entity_method: 'gpt5nano' (AI) or 'regex' (fast/free)

    Returns:
        Dict with:
        - backlinks: List with entities attached
        - aggregated_entities: Persons, companies, emails, phones found
        - entity_extraction: Stats about extraction
    """
    pipeline = AutomatedBacklinkPipeline(
        target_domain,
        extract_entities=True,
        max_entity_pages=max_entity_pages,
        entity_method=entity_method
    )
    return await pipeline.run(max_results=max_results)


async def main():
    """CLI for backlink pipeline with entity extraction"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Automated Backlink Pipeline with Entity Extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic backlink discovery
  python automated_backlink_pipeline.py example.com

  # With entity extraction (GPT-5-nano)
  python automated_backlink_pipeline.py example.com --entities

  # With entity extraction (regex only - faster, free)
  python automated_backlink_pipeline.py example.com --entities --method regex

  # Limit entity extraction to top 20 pages
  python automated_backlink_pipeline.py example.com --entities --max-entity-pages 20
        """
    )

    parser.add_argument("domain", help="Target domain to find backlinks for")
    parser.add_argument("-n", "--max-results", type=int, default=100,
                       help="Max backlinks to retrieve (default: 100)")
    parser.add_argument("-e", "--entities", action="store_true",
                       help="Extract entities from referring pages")
    parser.add_argument("--max-entity-pages", type=int, default=50,
                       help="Max pages to scrape for entities (default: 50)")
    parser.add_argument("-m", "--method", choices=["gpt5nano", "regex"],
                       default="gpt5nano", help="Entity extraction method")
    parser.add_argument("-o", "--output", help="Save JSON results to file")
    parser.add_argument("-f", "--filter", nargs="+",
                       help="Filter results to specific domains")

    args = parser.parse_args()

    # Print availability
    print(f"\n🔧 Entity Extraction: {'Available' if ENTITY_EXTRACTION_AVAILABLE else 'NOT Available'}")

    # Create and run pipeline
    pipeline = AutomatedBacklinkPipeline(
        args.domain,
        extract_entities=args.entities,
        max_entity_pages=args.max_entity_pages,
        entity_method=args.method
    )

    results = await pipeline.run(max_results=args.max_results)

    # Filter for specific domains if requested
    if args.filter:
        print("\n" + "=" * 100)
        print("FILTERING FOR SPECIFIC DOMAINS")
        print("=" * 100)

        for domain in args.filter:
            print(f"\n{'=' * 80}")
            print(f"DOMAIN: {domain}")
            print("=" * 80)

            matches = [
                bl for bl in results['backlinks']
                if domain in bl.get('source', '').lower() or domain in bl.get('source_domain', '').lower()
            ]

            if matches:
                print(f"\n✅ Found {len(matches)} referring page(s):\n")

                for i, bl in enumerate(matches, 1):
                    print(f"{i}. SOURCE: {bl.get('source', 'N/A')}")
                    if bl.get('anchor_text'):
                        print(f"   Anchor: \"{bl.get('anchor_text')}\"")
                    if bl.get('trust_flow'):
                        print(f"   TrustFlow: {bl.get('trust_flow')}, CitationFlow: {bl.get('citation_flow')}")
                    print(f"   Found in: {', '.join(bl.get('found_in', []))}")

                    # Show entities if extracted
                    entities = bl.get('entities', [])
                    if entities:
                        print(f"   Entities ({len(entities)}):")
                        for ent in entities[:5]:
                            print(f"      • [{ent.get('type')}] {ent.get('value')}")
                        if len(entities) > 5:
                            print(f"      ... and {len(entities) - 5} more")
                    print()
            else:
                print(f"\n⚠️  No backlinks found from {domain}")

    # Save to file if requested
    if args.output:
        import json
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n💾 Results saved to: {args.output}")

    return results


if __name__ == "__main__":
    asyncio.run(main())
