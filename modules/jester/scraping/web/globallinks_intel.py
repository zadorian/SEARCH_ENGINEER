"""
GlobalLinks Intelligence for DRILL

Enhances the DRILL crawler with pre-flight intelligence from GlobalLinks/CC.
Makes crawling smarter, not just faster.

Key Enhancements:
1. Pre-flight Intel - Know domain's link profile before crawling
2. Smart Seeds - Use backlinks as discovery seeds
3. Anchor Keywords - Extract investigation keywords from anchor texts
4. Domain Categorization - Apply special extraction for offshore/gov domains
5. Crawl Prioritization - Authority-based page ordering
6. Skip Redundant - Don't re-crawl what CC already has
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import Counter
from urllib.parse import urlparse
import re

# Local imports - use absolute imports since moved from drill/
from modules.linklater.linkgraph.globallinks import GlobalLinksClient, find_globallinks_binary
from modules.linklater.linkgraph.cc_graph import CCGraphClient


# Domain categories for special handling
DOMAIN_CATEGORIES = {
    "offshore": {
        "tlds": [".ky", ".vg", ".bz", ".pa", ".tc", ".ai", ".bs", ".je", ".gg", ".im", ".gi"],
        "keywords": ["offshore", "trust", "foundation", "holdings", "international", "nominee"],
        "extraction_priority": ["companies", "addresses", "officers"],
    },
    "government": {
        "tlds": [".gov", ".gov.uk", ".gouv.fr", ".gob.es", ".gov.ru", ".gov.cn"],
        "keywords": ["ministry", "department", "agency", "official", "government"],
        "extraction_priority": ["persons", "organizations", "dates"],
    },
    "russia_cis": {
        "tlds": [".ru", ".by", ".kz", ".ua", ".uz", ".am", ".az", ".ge", ".md", ".kg", ".tj", ".tm"],
        "keywords": ["llc", "ooo", "pjsc", "cjsc", "zao", "oao"],
        "extraction_priority": ["companies", "persons", "phones"],
    },
    "china_hk": {
        "tlds": [".cn", ".hk", ".tw", ".mo"],
        "keywords": ["limited", "ltd", "holdings", "group", "trading"],
        "extraction_priority": ["companies", "addresses", "persons"],
    },
    "financial": {
        "tlds": [".bank", ".finance"],
        "keywords": ["bank", "credit", "investment", "fund", "capital", "asset", "management"],
        "extraction_priority": ["companies", "amounts", "dates"],
    },
}


@dataclass
class DomainIntelligence:
    """Intelligence gathered about a domain before crawling."""
    domain: str

    # Link profile
    backlink_count: int = 0
    outlink_count: int = 0
    top_referring_domains: List[str] = field(default_factory=list)
    top_target_domains: List[str] = field(default_factory=list)

    # Anchor text analysis
    anchor_keywords: List[str] = field(default_factory=list)
    anchor_entities: Dict[str, List[str]] = field(default_factory=dict)

    # Categorization
    categories: List[str] = field(default_factory=list)
    tld: str = ""

    # Suggested crawl strategy
    suggested_max_depth: int = 5
    suggested_extraction_focus: List[str] = field(default_factory=list)
    high_priority_patterns: List[str] = field(default_factory=list)

    # Pre-discovered URLs (from backlinks)
    seed_urls_from_backlinks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "backlink_count": self.backlink_count,
            "outlink_count": self.outlink_count,
            "top_referring_domains": self.top_referring_domains[:20],
            "top_target_domains": self.top_target_domains[:20],
            "anchor_keywords": self.anchor_keywords[:50],
            "categories": self.categories,
            "suggested_extraction_focus": self.suggested_extraction_focus,
            "seed_urls_count": len(self.seed_urls_from_backlinks),
        }


class GlobalLinksIntelligence:
    """
    Pre-flight intelligence gatherer using GlobalLinks/CC.

    Use before crawling to:
    - Understand domain's link ecosystem
    - Extract investigation keywords from anchor texts
    - Categorize domain for special handling
    - Discover additional seed URLs
    """

    def __init__(self):
        """Initialize with GlobalLinks and CC Graph clients."""
        self.globallinks = GlobalLinksClient()
        self.cc_graph = CCGraphClient()

        # Check what's available
        self.has_globallinks = find_globallinks_binary("outlinker") is not None
        self.has_cc_graph = True  # CC Graph is always available (API-based)

    async def gather_intelligence(
        self,
        domain: str,
        archive: str = "CC-MAIN-2024-10",
        deep_analysis: bool = True,
    ) -> DomainIntelligence:
        """
        Gather pre-flight intelligence about a domain.

        Args:
            domain: Target domain to analyze
            archive: Common Crawl archive for GlobalLinks queries
            deep_analysis: If True, extract anchor keywords and entities

        Returns:
            DomainIntelligence with comprehensive analysis
        """
        intel = DomainIntelligence(domain=domain)
        intel.tld = self._extract_tld(domain)

        # Categorize by TLD and domain patterns
        intel.categories = self._categorize_domain(domain)

        # Parallel queries for speed
        tasks = []

        # 1. Get backlinks from CC Graph (domain-level)
        tasks.append(self._get_backlinks_intel(domain))

        # 2. Get outlinks from CC Graph (domain-level)
        tasks.append(self._get_outlinks_intel(domain))

        # 3. If GlobalLinks available, get page-level data with anchors
        if self.has_globallinks and deep_analysis:
            tasks.append(self._get_anchor_analysis(domain, archive))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process backlinks result
        if not isinstance(results[0], Exception):
            backlinks_data = results[0]
            intel.backlink_count = backlinks_data.get("count", 0)
            intel.top_referring_domains = backlinks_data.get("top_domains", [])
            intel.seed_urls_from_backlinks = backlinks_data.get("seed_urls", [])

        # Process outlinks result
        if not isinstance(results[1], Exception):
            outlinks_data = results[1]
            intel.outlink_count = outlinks_data.get("count", 0)
            intel.top_target_domains = outlinks_data.get("top_domains", [])

        # Process anchor analysis
        if len(results) > 2 and not isinstance(results[2], Exception):
            anchor_data = results[2]
            intel.anchor_keywords = anchor_data.get("keywords", [])
            intel.anchor_entities = anchor_data.get("entities", {})

        # Determine suggested strategy based on intelligence
        intel = self._suggest_crawl_strategy(intel)

        return intel

    async def _get_backlinks_intel(self, domain: str) -> Dict[str, Any]:
        """Get backlink intelligence from CC Graph."""
        try:
            result = await self.cc_graph.get_backlinks(domain, limit=500)

            if not result.get("records"):
                return {"count": 0, "top_domains": [], "seed_urls": []}

            records = result["records"]

            # Count unique referring domains
            domain_counter = Counter(r.get("src_domain", "") for r in records)

            return {
                "count": len(records),
                "top_domains": [d for d, _ in domain_counter.most_common(20)],
                # Construct likely seed URLs from referring domains
                "seed_urls": [f"https://{d}" for d, _ in domain_counter.most_common(10)],
            }
        except Exception as e:
            print(f"[GlobalLinksIntel] Backlinks error: {e}")
            return {"count": 0, "top_domains": [], "seed_urls": []}

    async def _get_outlinks_intel(self, domain: str) -> Dict[str, Any]:
        """Get outlink intelligence from CC Graph."""
        try:
            result = await self.cc_graph.get_outlinks(domain, limit=500)

            if not result.get("records"):
                return {"count": 0, "top_domains": []}

            records = result["records"]

            # Count target domains
            domain_counter = Counter(r.get("target_domain", "") for r in records)

            return {
                "count": len(records),
                "top_domains": [d for d, _ in domain_counter.most_common(20)],
            }
        except Exception as e:
            print(f"[GlobalLinksIntel] Outlinks error: {e}")
            return {"count": 0, "top_domains": []}

    async def _get_anchor_analysis(
        self,
        domain: str,
        archive: str,
    ) -> Dict[str, Any]:
        """
        Get anchor text analysis from GlobalLinks (page-level data).
        Extract keywords and entities from how others link to this domain.
        """
        try:
            # Search for pages linking TO this domain
            records = await self.globallinks.search_outlinks(
                target_domain=domain,
                data_path="data/links/"
            )

            if not records:
                return {"keywords": [], "entities": {}}

            # Extract anchor texts
            anchor_texts = []
            for record in records:
                if record.anchor_text:
                    anchor_texts.append(record.anchor_text)

            # Analyze anchor texts for keywords
            keywords = self._extract_keywords_from_anchors(anchor_texts)

            # Extract entities from anchors
            entities = self._extract_entities_from_anchors(anchor_texts)

            return {
                "keywords": keywords,
                "entities": entities,
            }
        except Exception as e:
            print(f"[GlobalLinksIntel] Anchor analysis error: {e}")
            return {"keywords": [], "entities": {}}

    def _extract_keywords_from_anchors(self, anchors: List[str]) -> List[str]:
        """Extract meaningful keywords from anchor texts."""
        # Word frequency
        word_freq = Counter()

        # Stop words to ignore
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
            "this", "that", "these", "those", "click", "here", "more", "read",
            "view", "see", "learn", "visit", "website", "site", "page", "link",
            "http", "https", "www", "com", "org", "net",
        }

        for anchor in anchors:
            if not anchor:
                continue

            # Tokenize and clean
            words = re.findall(r'\b[a-zA-Z]{3,}\b', anchor.lower())

            for word in words:
                if word not in stop_words and len(word) > 2:
                    word_freq[word] += 1

        # Return most common keywords
        return [word for word, count in word_freq.most_common(50) if count >= 2]

    def _extract_entities_from_anchors(self, anchors: List[str]) -> Dict[str, List[str]]:
        """Extract entity-like patterns from anchor texts."""
        entities = {
            "companies": [],
            "persons": [],
            "products": [],
        }

        # Simple patterns for entities
        company_patterns = [
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Ltd|LLC|Inc|Corp|PLC|SA|AG|GmbH|BV))\b',
            r'\b([A-Z][A-Z0-9]+)\b',  # Acronyms like "BBC", "IBM"
        ]

        person_patterns = [
            r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b',  # "John Smith"
        ]

        seen_companies = set()
        seen_persons = set()

        for anchor in anchors:
            if not anchor:
                continue

            # Extract companies
            for pattern in company_patterns:
                matches = re.findall(pattern, anchor)
                for match in matches:
                    if match not in seen_companies and len(match) > 3:
                        entities["companies"].append(match)
                        seen_companies.add(match)

            # Extract persons (simple two-word names)
            for pattern in person_patterns:
                matches = re.findall(pattern, anchor)
                for match in matches:
                    # Filter out common non-names
                    if match not in seen_persons and not any(
                        w in match.lower() for w in ["click here", "read more", "view all"]
                    ):
                        entities["persons"].append(match)
                        seen_persons.add(match)

        return entities

    def _extract_tld(self, domain: str) -> str:
        """Extract TLD from domain."""
        parts = domain.lower().split('.')
        if len(parts) >= 2:
            # Handle compound TLDs like .co.uk, .gov.uk
            if len(parts) >= 3 and parts[-2] in ("co", "gov", "org", "ac", "net"):
                return f".{parts[-2]}.{parts[-1]}"
            return f".{parts[-1]}"
        return ""

    def _categorize_domain(self, domain: str) -> List[str]:
        """Categorize domain by TLD and patterns."""
        categories = []
        domain_lower = domain.lower()
        tld = self._extract_tld(domain)

        for category, config in DOMAIN_CATEGORIES.items():
            # Check TLD
            if any(tld.endswith(t) for t in config["tlds"]):
                categories.append(category)
                continue

            # Check domain name keywords
            if any(kw in domain_lower for kw in config["keywords"]):
                categories.append(category)

        return categories if categories else ["general"]

    def _suggest_crawl_strategy(self, intel: DomainIntelligence) -> DomainIntelligence:
        """
        Suggest crawl strategy based on gathered intelligence.
        """
        # Determine extraction focus based on categories
        focus = set()
        patterns = []

        for category in intel.categories:
            if category in DOMAIN_CATEGORIES:
                focus.update(DOMAIN_CATEGORIES[category]["extraction_priority"])

        # Add focus based on anchor keywords
        if intel.anchor_keywords:
            # If investment/money keywords, focus on amounts
            money_keywords = {"investment", "fund", "capital", "million", "billion", "usd", "eur"}
            if money_keywords & set(intel.anchor_keywords):
                focus.add("amounts")

            # If people names in anchors, focus on persons
            if intel.anchor_entities.get("persons"):
                focus.add("persons")

        intel.suggested_extraction_focus = list(focus) if focus else ["companies", "persons", "emails"]

        # Suggest depth based on link profile
        if intel.backlink_count > 1000:
            intel.suggested_max_depth = 3  # Large site, stay shallow
        elif intel.backlink_count < 100:
            intel.suggested_max_depth = 7  # Small site, go deep
        else:
            intel.suggested_max_depth = 5

        # High priority patterns based on anchor keywords
        if intel.anchor_keywords:
            intel.high_priority_patterns = [
                f"/{kw}" for kw in intel.anchor_keywords[:10]
            ]

        return intel


class GlobalLinksEnhancedCrawler:
    """
    Wrapper that enhances DRILL crawler with GlobalLinks intelligence.

    Usage:
        enhanced = GlobalLinksEnhancedCrawler()
        intel, stats = await enhanced.crawl_with_intelligence("target.com")
    """

    def __init__(self):
        self.intelligence = GlobalLinksIntelligence()

    async def crawl_with_intelligence(
        self,
        domain: str,
        archive: str = "CC-MAIN-2024-10",
        **crawl_kwargs,
    ) -> Tuple[DomainIntelligence, Any]:
        """
        Crawl a domain with pre-flight GlobalLinks intelligence.

        1. Gather intelligence first
        2. Configure crawler based on intelligence
        3. Run enhanced crawl
        4. Return both intel and stats
        """
        from .crawler import Drill, DrillConfig

        print(f"\n[GlobalLinksEnhanced] Gathering pre-flight intelligence for {domain}...")

        # Phase 1: Gather intelligence
        intel = await self.intelligence.gather_intelligence(
            domain,
            archive=archive,
            deep_analysis=True,
        )

        print(f"[GlobalLinksEnhanced] Intelligence gathered:")
        print(f"  - Backlinks: {intel.backlink_count}")
        print(f"  - Outlinks: {intel.outlink_count}")
        print(f"  - Categories: {intel.categories}")
        print(f"  - Anchor keywords: {intel.anchor_keywords[:10]}...")
        print(f"  - Suggested depth: {intel.suggested_max_depth}")
        print(f"  - Extraction focus: {intel.suggested_extraction_focus}")

        # Phase 2: Configure crawler based on intelligence
        config_overrides = {
            "max_depth": intel.suggested_max_depth,
        }
        config_overrides.update(crawl_kwargs)

        config = DrillConfig(**config_overrides)

        # Phase 3: Create enhanced crawl with additional seeds
        drill = Drill(config)

        # Add extra keywords from anchor analysis to extractor
        if intel.anchor_keywords:
            drill.extractor.add_keywords(intel.anchor_keywords[:20])

        # Combine normal seeds with backlink-discovered seeds
        seed_urls = intel.seed_urls_from_backlinks[:10]  # Add up to 10 backlink-discovered seeds

        # Phase 4: Run crawl
        stats = await drill.crawl(domain, seed_urls=seed_urls if seed_urls else None)

        return intel, stats


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def get_domain_intelligence(domain: str) -> DomainIntelligence:
    """Quick intelligence check for a domain."""
    intel = GlobalLinksIntelligence()
    return await intel.gather_intelligence(domain)


async def crawl_with_intel(domain: str, **kwargs) -> Tuple[DomainIntelligence, Any]:
    """Crawl a domain with pre-flight GlobalLinks intelligence."""
    crawler = GlobalLinksEnhancedCrawler()
    return await crawler.crawl_with_intelligence(domain, **kwargs)


# ============================================================================
# CLI
# ============================================================================

async def main():
    """CLI for testing GlobalLinks intelligence."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="GlobalLinks Intelligence for DRILL")
    parser.add_argument("domain", help="Domain to analyze")
    parser.add_argument("--crawl", action="store_true", help="Also run enhanced crawl")
    parser.add_argument("--archive", default="CC-MAIN-2024-10", help="CC archive")
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"GlobalLinks Intelligence: {args.domain}")
    print(f"{'='*60}\n")

    if args.crawl:
        intel, stats = await crawl_with_intel(args.domain, archive=args.archive)
        result = {
            "intelligence": intel.to_dict(),
            "crawl_stats": stats.to_dict(),
        }
    else:
        intel = await get_domain_intelligence(args.domain)
        result = intel.to_dict()

    print(f"\n{'='*60}")
    print("INTELLIGENCE REPORT")
    print(f"{'='*60}")
    print(json.dumps(result, indent=2))

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved to: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
