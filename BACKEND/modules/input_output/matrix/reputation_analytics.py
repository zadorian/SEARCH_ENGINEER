"""
Reputation Analytics Module

Generates quantitative data for multidimensional reputation analysis.
Feeds into REPUTATION_PROFILE_ANALYSIS.skill.md template.

Integrates with LINKLATER/extraction pipeline for AI-powered extraction
of themes, phenomena, and events using Claude Haiku.

Usage:
    from reputation_analytics import ReputationAnalyzer
    analyzer = ReputationAnalyzer(entity_name, entity_type)
    profile = await analyzer.analyze()

    # With AI extraction (uses Haiku backend)
    profile = await analyzer.analyze(use_ai_extraction=True)
"""

import json
import re
import asyncio
import logging
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from pathlib import Path
import hashlib

# Import extraction models for ET3 integration
try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "BACKEND" / "modules"))
    from LINKLATER.extraction.models import (
        Theme as ExtractionTheme,
        Phenomenon as ExtractionPhenomenon,
        Event as ExtractionEvent,
        Edge,
        THEME_CATEGORIES,
        PHENOMENON_CATEGORIES
    )
    from LINKLATER.extraction.backends.haiku import HaikuBackend
    EXTRACTION_AVAILABLE = True
except ImportError:
    EXTRACTION_AVAILABLE = False
    ExtractionTheme = None
    ExtractionPhenomenon = None
    ExtractionEvent = None

logger = logging.getLogger(__name__)


def generate_temporal_hierarchy(iso_date: str, event_id: str = None) -> Dict[str, List]:
    """
    Generate temporal hierarchy nodes and edges from an ISO date string.

    Creates hierarchical LOCATION class nodes: Day (time_point) → Month (time_span) → Year (time_span)
    with part_of edges connecting them.

    Args:
        iso_date: ISO format date (YYYY-MM-DD, YYYY-MM, or YYYY)
        event_id: Optional event ID to create anchored_to edge

    Returns:
        Dict with 'nodes' and 'edges' lists for graph storage
    """
    if not iso_date:
        return {"nodes": [], "edges": []}

    nodes = []
    edges = []

    try:
        parts = iso_date.split('-')
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else None
        day = int(parts[2]) if len(parts) > 2 else None

        # Year node (always created)
        year_id = f"time_span_{year}"
        nodes.append({
            "type": "time_span",
            "class": "location",
            "id": year_id,
            "label": str(year),
            "resolution": "year",
            "value": year,
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31"
        })

        most_granular_id = year_id

        # Month node
        if month:
            month_key = f"{year}-{month:02d}"
            month_id = f"time_span_{month_key}"

            # Calculate month label
            month_names = ["", "January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December"]
            month_label = f"{month_names[month]} {year}"

            # Calculate end date
            if month == 12:
                end_date = f"{year}-12-31"
            else:
                # Last day of month
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                end_date = f"{year}-{month:02d}-{last_day:02d}"

            nodes.append({
                "type": "time_span",
                "class": "location",
                "id": month_id,
                "label": month_label,
                "resolution": "month",
                "value": month,
                "year": year,
                "start_date": f"{year}-{month:02d}-01",
                "end_date": end_date
            })

            # Month part_of Year
            edges.append({
                "source_type": "time_span",
                "source_id": month_id,
                "relation": "part_of",
                "target_type": "time_span",
                "target_id": year_id,
                "confidence": 1.0
            })

            most_granular_id = month_id

        # Day node
        if day:
            day_iso = f"{year}-{month:02d}-{day:02d}"
            day_id = f"time_point_{day_iso}"

            nodes.append({
                "type": "time_point",
                "class": "location",
                "id": day_id,
                "label": day_iso,
                "resolution": "day",
                "value": day_iso,
                "year": year,
                "month": month,
                "day": day
            })

            # Day part_of Month
            edges.append({
                "source_type": "time_point",
                "source_id": day_id,
                "relation": "part_of",
                "target_type": "time_span",
                "target_id": month_id,
                "confidence": 1.0
            })

            most_granular_id = day_id

        # Event anchored_to temporal node
        if event_id:
            edges.append({
                "source_type": "event",
                "source_id": event_id,
                "relation": "anchored_to",
                "target_type": "time_point" if day else "time_span",
                "target_id": most_granular_id,
                "confidence": 1.0
            })

        return {"nodes": nodes, "edges": edges}

    except Exception as e:
        logger.warning(f"Failed to generate temporal hierarchy for {iso_date}: {e}")
        return {"nodes": [], "edges": []}


@dataclass
class MediaMention:
    """Single media mention with metadata."""
    url: str
    title: str
    publication: str
    date: Optional[datetime]
    tier: int  # 1-6
    sentiment: str  # positive, neutral, negative
    content_hash: str  # For deduplication
    category: str  # news, trade, pr, social, aggregator
    language: str
    country: str
    is_original: bool  # vs republished/syndicated
    quotes_subject: bool
    quotes_others_about_subject: bool
    source_engine: str
    # Subject-centric fields
    themes: List[str] = field(default_factory=list)
    phenomena: List[str] = field(default_factory=list)
    snippet: str = ""


@dataclass
class Event:
    """Discrete event constructed from phenomenon + location + time + entity."""
    id: str
    phenomenon: str
    phenomenon_category: str
    entity_primary: str
    entities_related: List[str] = field(default_factory=list)
    location_geographic: str = ""
    location_institutional: str = ""
    date: Optional[datetime] = None
    period: str = ""  # e.g., "Q2 2019" if date unknown
    coverage_count: int = 0
    source_tiers: Dict[int, int] = field(default_factory=dict)
    sentiment: str = "neutral"
    significance: str = ""
    # Four anchors for this event
    typical_mention: Optional[MediaMention] = None
    standout_mention: Optional[MediaMention] = None
    first_mention: Optional[MediaMention] = None
    most_recent_mention: Optional[MediaMention] = None


@dataclass
class ReputationProfile:
    """Complete reputation analysis output."""
    entity_name: str
    entity_type: str
    analysis_date: datetime

    # Volume metrics
    raw_mention_count: int = 0
    unique_mention_count: int = 0
    duplication_ratio: float = 0.0

    # Scale & Reach
    geographic_scope: str = ""  # global, national, regional, local, none
    primary_tier: int = 0
    tier_distribution: Dict[int, int] = field(default_factory=dict)
    countries_covered: List[str] = field(default_factory=list)
    languages_covered: List[str] = field(default_factory=list)

    # Domain specificity
    coverage_types: Dict[str, int] = field(default_factory=dict)
    cross_domain_visibility: bool = False

    # Sentiment
    sentiment_distribution: Dict[str, int] = field(default_factory=dict)
    sentiment_trajectory: str = ""  # stable, improving, deteriorating, event-driven

    # Temporal
    first_mention: Optional[MediaMention] = None
    most_recent_mention: Optional[MediaMention] = None
    peak_period: str = ""
    coverage_span_years: float = 0.0
    narrative_arc: str = ""

    # Four Anchors per dimension
    typical_example: Optional[MediaMention] = None
    standout_example: Optional[MediaMention] = None

    # Authenticity
    original_editorial_pct: float = 0.0
    pr_republication_pct: float = 0.0
    third_party_validation_count: int = 0

    # Web presence (for companies/domains)
    referring_domains: int = 0
    domain_authority: int = 0

    # Mismatch detection
    claimed_profile: List[str] = field(default_factory=list)
    mismatches: List[Dict] = field(default_factory=list)
    mismatch_risk: str = "LOW"

    # Comparison
    peer_comparison: Dict[str, Dict] = field(default_factory=dict)
    vs_baseline: str = ""  # above, at, below

    # Subject-centric analysis
    theme_distribution: Dict[str, int] = field(default_factory=dict)
    theme_sentiment: Dict[str, str] = field(default_factory=dict)
    theme_trajectory: Dict[str, str] = field(default_factory=dict)
    events: List[Event] = field(default_factory=list)

    # Dual centricity assessment
    source_richness: str = ""  # high, medium, low
    subject_richness: str = ""  # high, medium, low
    recommended_emphasis: str = ""  # source, subject, both, neither


# Theme taxonomy for subject-centric analysis
THEME_KEYWORDS = {
    "professional": ["executive", "ceo", "director", "appointed", "joined", "expertise",
                    "industry", "career", "role", "position", "conference", "speaking"],
    "financial": ["deal", "investment", "funding", "acquired", "merger", "revenue",
                 "profit", "earnings", "valuation", "IPO", "transaction", "wealth"],
    "legal_regulatory": ["lawsuit", "litigation", "court", "sued", "settlement",
                        "regulatory", "compliance", "fine", "penalty", "license"],
    "reputational": ["award", "recognized", "honored", "ranking", "best", "top",
                    "controversy", "criticism", "praised", "condemned"],
    "personal": ["family", "married", "philanthropy", "donated", "charity",
                "foundation", "lifestyle", "residence"],
    "criminal": ["investigation", "charged", "arrested", "convicted", "fraud",
                "criminal", "indicted", "plea", "prison"],
    "political": ["government", "minister", "politician", "lobbying", "donation",
                 "campaign", "policy", "election", "party"]
}

# Phenomenon taxonomy for event detection
PHENOMENON_KEYWORDS = {
    "corporate": {
        "ipo": ["IPO", "initial public offering", "went public", "listing"],
        "acquisition": ["acquired", "acquisition", "takeover", "bought", "purchased"],
        "merger": ["merger", "merged", "combination"],
        "restructuring": ["restructuring", "reorganization", "spinoff", "spin-off"],
        "bankruptcy": ["bankruptcy", "chapter 11", "insolvency", "liquidation"]
    },
    "career": {
        "hiring": ["hired", "appointed", "joined", "named", "new CEO", "new director"],
        "departure": ["resigned", "stepped down", "left", "departed", "fired", "terminated"],
        "promotion": ["promoted", "elevated", "new role"]
    },
    "legal": {
        "lawsuit_filed": ["filed suit", "lawsuit filed", "sued", "legal action"],
        "settlement": ["settled", "settlement", "agreed to pay"],
        "judgment": ["judgment", "verdict", "ruled", "found liable"],
        "arrest": ["arrested", "taken into custody", "detained"]
    },
    "financial": {
        "funding": ["raised", "funding round", "series A", "series B", "investment"],
        "earnings": ["earnings", "quarterly results", "annual report", "revenue"]
    },
    "recognition": {
        "award": ["award", "won", "honored", "recognized", "prize"]
    },
    "crisis": {
        "scandal": ["scandal", "controversy", "backlash", "outcry"],
        "investigation": ["investigation", "probe", "inquiry", "under investigation"]
    }
}

# Publication tier classification
TIER_1_SOURCES = {
    'ft.com', 'wsj.com', 'nytimes.com', 'reuters.com', 'bloomberg.com',
    'theguardian.com', 'economist.com', 'bbc.com', 'afp.com', 'ap.org',
    'icij.org', 'occrp.org'
}

TIER_2_SOURCES = {
    'thetimes.co.uk', 'telegraph.co.uk', 'forbes.com', 'fortune.com',
    'spiegel.de', 'faz.net', 'handelsblatt.com', 'lemonde.fr', 'lesechos.fr',
    'bellingcat.com', 'politico.com', 'businessinsider.com'
}

TIER_3_TRADE = {
    'insuranceinsider.com', 'lloydslist.com', 'tradewinds.no',
    'law360.com', 'thelawyerdaily.com'
}

TIER_5_AGGREGATORS = {
    'prnewswire.com', 'businesswire.com', 'globenewswire.com',
    'accesswire.com', 'yahoo.com/news', 'finance.yahoo.com'
}

# Baseline expectations by entity type
BASELINES = {
    "fortune_500_ceo": {
        "expected_mentions": (500, 5000),
        "expected_tier1_pct": (20, 50),
        "expected_countries": (3, 20),
        "expected_span_years": (5, 30),
    },
    "mid_market_exec": {
        "expected_mentions": (50, 200),
        "expected_tier1_pct": (0, 10),
        "expected_countries": (1, 3),
        "expected_span_years": (3, 15),
    },
    "startup_founder": {
        "expected_mentions": (10, 100),
        "expected_tier1_pct": (0, 20),
        "expected_countries": (1, 5),
        "expected_span_years": (1, 7),
    },
    "private_individual": {
        "expected_mentions": (0, 20),
        "expected_tier1_pct": (0, 5),
        "expected_countries": (0, 2),
        "expected_span_years": (0, 10),
    },
    "pep_politician": {
        "expected_mentions": (100, 10000),
        "expected_tier1_pct": (10, 40),
        "expected_countries": (1, 50),
        "expected_span_years": (5, 40),
    },
    "sme_company": {
        "expected_mentions": (5, 50),
        "expected_tier1_pct": (0, 5),
        "expected_countries": (1, 2),
        "expected_span_years": (2, 20),
    },
    "large_corporation": {
        "expected_mentions": (1000, 50000),
        "expected_tier1_pct": (15, 40),
        "expected_countries": (5, 100),
        "expected_span_years": (10, 100),
    }
}


class ReputationAnalyzer:
    """Analyzes reputation across all dimensions."""

    def __init__(self, entity_name: str, entity_type: str = "private_individual"):
        self.entity_name = entity_name
        self.entity_type = entity_type
        self.mentions: List[MediaMention] = []
        self.profile = ReputationProfile(
            entity_name=entity_name,
            entity_type=entity_type,
            analysis_date=datetime.now()
        )
        # AI extraction backend
        self._haiku_backend = None
        self._extracted_themes: List[ExtractionTheme] = [] if EXTRACTION_AVAILABLE else []
        self._extracted_phenomena: List[ExtractionPhenomenon] = [] if EXTRACTION_AVAILABLE else []
        self._extracted_events: List[ExtractionEvent] = [] if EXTRACTION_AVAILABLE else []
        self._extraction_edges: List[Edge] = [] if EXTRACTION_AVAILABLE else []

    def _get_haiku_backend(self):
        """Lazy initialization of Haiku backend."""
        if not EXTRACTION_AVAILABLE:
            logger.warning("Extraction pipeline not available - using keyword detection only")
            return None
        if self._haiku_backend is None:
            self._haiku_backend = HaikuBackend()
        return self._haiku_backend

    async def extract_with_ai(self, text: str, url: str = "") -> Dict:
        """
        Use Claude Haiku to extract themes, phenomena, and events from text.

        Returns dict with themes, phenomena, events extracted via AI.
        Falls back to keyword detection if AI unavailable.
        """
        backend = self._get_haiku_backend()
        if not backend:
            # Fallback to keyword detection
            return {
                "themes": self._detect_themes("", text),
                "phenomena": self._detect_phenomena("", text),
                "events": [],
                "backend": "keywords"
            }

        try:
            result = await backend.extract_all(text, url)
            # Store extracted items
            self._extracted_themes.extend(result.get("themes", []))
            self._extracted_phenomena.extend(result.get("phenomena", []))
            self._extracted_events.extend(result.get("events", []))

            return {
                "themes": [t.category for t in result.get("themes", [])],
                "phenomena": [f"{p.category}:{p.phenomenon_type}" for p in result.get("phenomena", [])],
                "events": result.get("events", []),
                "backend": "haiku-4.5"
            }
        except Exception as e:
            logger.warning(f"AI extraction failed, falling back to keywords: {e}")
            return {
                "themes": self._detect_themes("", text),
                "phenomena": self._detect_phenomena("", text),
                "events": [],
                "backend": "keywords"
            }

    async def add_from_brute_result_with_ai(self, result: Dict, source_engine: str):
        """Add mention with AI-powered extraction of themes/phenomena/events."""
        url = result.get('url', '')
        title = result.get('title', '')
        snippet = result.get('snippet', '')

        # Use AI extraction
        text = f"{title}\n\n{snippet}"
        ai_result = await self.extract_with_ai(text, url)

        mention = MediaMention(
            url=url,
            title=title,
            publication=self._extract_domain(url),
            date=self._parse_date(result.get('date')),
            tier=self.classify_tier(url, result.get('source', '')),
            sentiment=self._analyze_sentiment(title, snippet),
            content_hash=self.compute_content_hash(title, snippet),
            category=self._classify_category(url, result),
            language=result.get('language', 'en'),
            country=result.get('country', 'unknown'),
            is_original=self._check_originality(result),
            quotes_subject=self.entity_name.lower() in snippet.lower(),
            quotes_others_about_subject=self._has_third_party_quotes(snippet),
            source_engine=source_engine,
            themes=ai_result["themes"],
            phenomena=ai_result["phenomena"],
            snippet=snippet
        )
        self.mentions.append(mention)

    def get_extraction_nodes_and_edges(self) -> Dict:
        """
        Get all extracted themes/phenomena/events as graph nodes with edges.

        Returns:
            Dict with 'nodes' (list of node dicts) and 'edges' (list of edge dicts)
            formatted for graph storage.
        """
        nodes = []
        edges = []

        # Theme nodes
        for theme in self._extracted_themes:
            nodes.append({
                "type": "theme",
                "id": f"theme_{theme.category}_{self.entity_name}",
                "category": theme.category,
                "label": theme.label,
                "confidence": theme.confidence,
                "evidence": theme.evidence,
                "source_url": theme.source_url
            })
            # Edge: theme -> entity
            edges.append({
                "source_type": "theme",
                "source_id": f"theme_{theme.category}_{self.entity_name}",
                "relation": "characterizes",
                "target_type": self.entity_type.split("_")[0],  # person or company
                "target_id": self.entity_name,
                "confidence": theme.confidence
            })

        # Phenomenon nodes
        for phen in self._extracted_phenomena:
            nodes.append({
                "type": "phenomenon",
                "id": f"phen_{phen.phenomenon_type}_{self.entity_name}",
                "category": phen.category,
                "phenomenon_type": phen.phenomenon_type,
                "label": phen.label,
                "confidence": phen.confidence,
                "evidence": phen.evidence,
                "source_url": phen.source_url
            })

        # Event nodes (with full edge generation)
        # Track seen temporal nodes to avoid duplicates
        seen_temporal_ids = set()

        for event in self._extracted_events:
            nodes.append(event.to_dict())
            # Generate edges for this event
            event_edges = event.generate_edges()
            for edge in event_edges:
                edges.append(edge.to_dict())

            # Generate temporal hierarchy for event date
            if event.date:
                temporal_data = generate_temporal_hierarchy(event.date, event.event_id)

                # Add temporal nodes (deduplicate by ID)
                for temp_node in temporal_data.get("nodes", []):
                    if temp_node["id"] not in seen_temporal_ids:
                        nodes.append(temp_node)
                        seen_temporal_ids.add(temp_node["id"])

                # Add temporal edges (part_of and anchored_to)
                edges.extend(temporal_data.get("edges", []))

                # Source URLs mention the temporal nodes
                # Find the most granular temporal node for this event
                most_granular = None
                for temp_node in temporal_data.get("nodes", []):
                    if temp_node["resolution"] == "day":
                        most_granular = temp_node
                        break
                    elif temp_node["resolution"] == "month" and not most_granular:
                        most_granular = temp_node
                    elif temp_node["resolution"] == "year" and not most_granular:
                        most_granular = temp_node

                # Create mentions edges from source URLs to temporal
                if most_granular and hasattr(event, 'source_urls'):
                    for url in event.source_urls:
                        edges.append({
                            "source_type": "url",
                            "source_id": url,
                            "relation": "mentions",
                            "target_type": most_granular["type"],
                            "target_id": most_granular["id"],
                            "confidence": 0.9,
                            "metadata": {"context": "date_extraction"}
                        })

        logger.debug(f"Generated {len(nodes)} nodes and {len(edges)} edges including temporal hierarchy")
        return {"nodes": nodes, "edges": edges}

    def classify_tier(self, url: str, publication: str) -> int:
        """Classify publication tier 1-6."""
        domain = self._extract_domain(url)

        if domain in TIER_1_SOURCES:
            return 1
        elif domain in TIER_2_SOURCES:
            return 2
        elif domain in TIER_3_TRADE or 'trade' in publication.lower():
            return 3
        elif any(x in domain for x in ['local', 'regional', 'county', 'city']):
            return 4
        elif domain in TIER_5_AGGREGATORS or 'newswire' in domain:
            return 5
        else:
            return 6  # Default to lowest tier

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return url

    def compute_content_hash(self, title: str, content: str = "") -> str:
        """Generate hash for deduplication."""
        # Normalize text
        text = (title + content).lower()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s]', '', text)
        return hashlib.md5(text[:500].encode()).hexdigest()

    def add_mention(self, mention: MediaMention):
        """Add a media mention to analysis."""
        self.mentions.append(mention)

    def add_from_brute_result(self, result: Dict, source_engine: str):
        """Convert Brute search result to MediaMention."""
        url = result.get('url', '')
        title = result.get('title', '')
        snippet = result.get('snippet', '')

        mention = MediaMention(
            url=url,
            title=title,
            publication=self._extract_domain(url),
            date=self._parse_date(result.get('date')),
            tier=self.classify_tier(url, result.get('source', '')),
            sentiment=self._analyze_sentiment(title, snippet),
            content_hash=self.compute_content_hash(title, snippet),
            category=self._classify_category(url, result),
            language=result.get('language', 'en'),
            country=result.get('country', 'unknown'),
            is_original=self._check_originality(result),
            quotes_subject=self.entity_name.lower() in snippet.lower(),
            quotes_others_about_subject=self._has_third_party_quotes(snippet),
            source_engine=source_engine,
            themes=self._detect_themes(title, snippet),
            phenomena=self._detect_phenomena(title, snippet),
            snippet=snippet
        )
        self.mentions.append(mention)

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date from various formats."""
        if not date_str:
            return None
        try:
            # Try common formats
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%B %d, %Y', '%Y']:
                try:
                    return datetime.strptime(date_str, fmt)
                except:
                    continue
            return None
        except:
            return None

    def _analyze_sentiment(self, title: str, snippet: str) -> str:
        """Basic sentiment analysis."""
        text = (title + ' ' + snippet).lower()

        negative_words = ['fraud', 'scandal', 'lawsuit', 'charged', 'accused',
                         'alleged', 'investigation', 'fine', 'penalty', 'violation',
                         'corrupt', 'criminal', 'arrest', 'bankrupt', 'failure']
        positive_words = ['award', 'winner', 'success', 'growth', 'innovation',
                         'leading', 'top', 'best', 'excellence', 'achievement',
                         'praised', 'recognized', 'honored']

        neg_count = sum(1 for w in negative_words if w in text)
        pos_count = sum(1 for w in positive_words if w in text)

        if neg_count > pos_count:
            return 'negative'
        elif pos_count > neg_count:
            return 'positive'
        return 'neutral'

    def _classify_category(self, url: str, result: Dict) -> str:
        """Classify content category."""
        domain = self._extract_domain(url)

        if domain in TIER_5_AGGREGATORS:
            return 'pr'
        if any(x in domain for x in ['linkedin', 'twitter', 'facebook', 'instagram']):
            return 'social'
        if any(x in domain for x in ['news', 'times', 'post', 'journal', 'tribune']):
            return 'news'
        if any(x in domain for x in ['trade', 'industry', 'sector', 'professional']):
            return 'trade'
        return 'general'

    def _check_originality(self, result: Dict) -> bool:
        """Check if content appears original vs syndicated."""
        # Heuristic: if same content appears in multiple results, it's syndicated
        # This will be refined during deduplication
        return True  # Placeholder

    def _has_third_party_quotes(self, snippet: str) -> bool:
        """Check for quotes from others about the subject."""
        quote_patterns = [
            r'"[^"]*said[^"]*"',
            r'according to',
            r'described .* as',
            r'called .* (a|an|the)',
        ]
        return any(re.search(p, snippet, re.I) for p in quote_patterns)

    def _detect_themes(self, title: str, snippet: str) -> List[str]:
        """Detect themes from content."""
        text = (title + ' ' + snippet).lower()
        detected = []
        for theme, keywords in THEME_KEYWORDS.items():
            if any(kw.lower() in text for kw in keywords):
                detected.append(theme)
        return detected

    def _detect_phenomena(self, title: str, snippet: str) -> List[str]:
        """Detect phenomena/events from content."""
        text = (title + ' ' + snippet).lower()
        detected = []
        for category, phenomena in PHENOMENON_KEYWORDS.items():
            for phenomenon, keywords in phenomena.items():
                if any(kw.lower() in text for kw in keywords):
                    detected.append(f"{category}:{phenomenon}")
        return detected

    def deduplicate(self) -> Tuple[List[MediaMention], Dict[str, int]]:
        """Remove duplicate content, return unique + duplication stats."""
        seen_hashes = {}
        unique = []
        duplicates = defaultdict(int)

        for mention in sorted(self.mentions, key=lambda m: m.tier):
            if mention.content_hash not in seen_hashes:
                seen_hashes[mention.content_hash] = mention
                unique.append(mention)
            else:
                duplicates[mention.content_hash] += 1
                # Mark original as not original if we see copies
                seen_hashes[mention.content_hash].is_original = False

        return unique, dict(duplicates)

    async def analyze_async(self, use_ai_extraction: bool = False) -> ReputationProfile:
        """
        Run full analysis asynchronously with optional AI extraction.

        Args:
            use_ai_extraction: If True, use Haiku for theme/phenomenon/event extraction

        Returns:
            Complete ReputationProfile
        """
        return self.analyze(use_ai_extraction=use_ai_extraction)

    def analyze(self, use_ai_extraction: bool = False) -> ReputationProfile:
        """Run full analysis and return profile."""
        if not self.mentions:
            return self.profile

        # Deduplication
        unique_mentions, dup_stats = self.deduplicate()
        self.profile.raw_mention_count = len(self.mentions)
        self.profile.unique_mention_count = len(unique_mentions)
        self.profile.duplication_ratio = (
            len(self.mentions) / len(unique_mentions) if unique_mentions else 0
        )

        # Tier distribution
        tier_counts = defaultdict(int)
        for m in unique_mentions:
            tier_counts[m.tier] += 1
        self.profile.tier_distribution = dict(tier_counts)
        self.profile.primary_tier = max(tier_counts, key=tier_counts.get) if tier_counts else 0

        # Geographic scope
        countries = set(m.country for m in unique_mentions if m.country != 'unknown')
        self.profile.countries_covered = list(countries)
        self.profile.languages_covered = list(set(m.language for m in unique_mentions))

        if len(countries) > 5:
            self.profile.geographic_scope = 'global'
        elif len(countries) > 2:
            self.profile.geographic_scope = 'national'
        elif len(countries) > 0:
            self.profile.geographic_scope = 'regional'
        else:
            self.profile.geographic_scope = 'local'

        # Sentiment
        sentiment_counts = defaultdict(int)
        for m in unique_mentions:
            sentiment_counts[m.sentiment] += 1
        self.profile.sentiment_distribution = dict(sentiment_counts)

        # Temporal analysis
        dated_mentions = [m for m in unique_mentions if m.date]
        if dated_mentions:
            sorted_by_date = sorted(dated_mentions, key=lambda m: m.date)
            self.profile.first_mention = sorted_by_date[0]
            self.profile.most_recent_mention = sorted_by_date[-1]

            span = (sorted_by_date[-1].date - sorted_by_date[0].date).days
            self.profile.coverage_span_years = span / 365.25

            # Find peak period
            year_counts = defaultdict(int)
            for m in dated_mentions:
                year_counts[m.date.year] += 1
            if year_counts:
                peak_year = max(year_counts, key=year_counts.get)
                self.profile.peak_period = str(peak_year)

        # Determine narrative arc
        self.profile.narrative_arc = self._determine_narrative_arc(dated_mentions)

        # Authenticity
        original_count = sum(1 for m in unique_mentions if m.is_original)
        pr_count = sum(1 for m in unique_mentions if m.category == 'pr')
        if unique_mentions:
            self.profile.original_editorial_pct = (original_count / len(unique_mentions)) * 100
            self.profile.pr_republication_pct = (pr_count / len(unique_mentions)) * 100

        self.profile.third_party_validation_count = sum(
            1 for m in unique_mentions if m.quotes_others_about_subject
        )

        # Coverage types
        category_counts = defaultdict(int)
        for m in unique_mentions:
            category_counts[m.category] += 1
        self.profile.coverage_types = dict(category_counts)

        # Find typical and standout examples
        self.profile.typical_example = self._find_typical(unique_mentions)
        self.profile.standout_example = self._find_standout(unique_mentions)

        # Subject-centric analysis: themes
        theme_counts = defaultdict(int)
        theme_sentiments = defaultdict(list)
        for m in unique_mentions:
            for theme in m.themes:
                theme_counts[theme] += 1
                theme_sentiments[theme].append(m.sentiment)
        self.profile.theme_distribution = dict(theme_counts)

        # Theme sentiment aggregation
        for theme, sentiments in theme_sentiments.items():
            pos = sentiments.count('positive')
            neg = sentiments.count('negative')
            if pos > neg * 2:
                self.profile.theme_sentiment[theme] = 'positive'
            elif neg > pos * 2:
                self.profile.theme_sentiment[theme] = 'negative'
            else:
                self.profile.theme_sentiment[theme] = 'mixed'

        # Event construction from phenomena
        self.profile.events = self._construct_events(unique_mentions)

        # Assess dual centricity richness
        self._assess_centricity_richness(unique_mentions)

        # Compare to baseline
        self._compare_to_baseline()

        return self.profile

    def _construct_events(self, mentions: List[MediaMention]) -> List[Event]:
        """Group mentions by phenomenon to construct events."""
        events = []
        phenomenon_groups = defaultdict(list)

        for m in mentions:
            for phen in m.phenomena:
                phenomenon_groups[phen].append(m)

        for phen_key, phen_mentions in phenomenon_groups.items():
            if len(phen_mentions) < 1:
                continue

            category, phenomenon = phen_key.split(':') if ':' in phen_key else ('unknown', phen_key)

            # Get date range for this event
            dated = [m for m in phen_mentions if m.date]
            sorted_dated = sorted(dated, key=lambda m: m.date) if dated else []

            # Aggregate sentiment
            sentiments = [m.sentiment for m in phen_mentions]
            pos = sentiments.count('positive')
            neg = sentiments.count('negative')
            agg_sentiment = 'positive' if pos > neg else ('negative' if neg > pos else 'neutral')

            # Tier distribution
            tier_dist = defaultdict(int)
            for m in phen_mentions:
                tier_dist[m.tier] += 1

            event = Event(
                id=f"{self.entity_name}_{phenomenon}_{len(events)}",
                phenomenon=phenomenon,
                phenomenon_category=category,
                entity_primary=self.entity_name,
                date=sorted_dated[0].date if sorted_dated else None,
                period=str(sorted_dated[0].date.year) if sorted_dated and sorted_dated[0].date else "",
                coverage_count=len(phen_mentions),
                source_tiers=dict(tier_dist),
                sentiment=agg_sentiment,
                first_mention=sorted_dated[0] if sorted_dated else phen_mentions[0],
                most_recent_mention=sorted_dated[-1] if sorted_dated else phen_mentions[-1],
                typical_mention=self._find_typical(phen_mentions),
                standout_mention=self._find_standout(phen_mentions)
            )
            events.append(event)

        return sorted(events, key=lambda e: e.coverage_count, reverse=True)

    def _assess_centricity_richness(self, mentions: List[MediaMention]):
        """Assess which centricity (source or subject) is richer."""
        # Source richness: diversity of tiers, publications, patterns
        unique_pubs = len(set(m.publication for m in mentions))
        tier_diversity = len(set(m.tier for m in mentions))
        t1_t2_count = sum(1 for m in mentions if m.tier <= 2)

        # Subject richness: diversity of themes, events, phenomena
        all_themes = set()
        all_phenomena = set()
        for m in mentions:
            all_themes.update(m.themes)
            all_phenomena.update(m.phenomena)
        theme_count = len(all_themes)
        event_count = len(self.profile.events)

        # Score source richness
        source_score = 0
        if unique_pubs >= 10:
            source_score += 2
        elif unique_pubs >= 5:
            source_score += 1
        if tier_diversity >= 3:
            source_score += 1
        if t1_t2_count >= 3:
            source_score += 2

        # Score subject richness
        subject_score = 0
        if theme_count >= 4:
            subject_score += 2
        elif theme_count >= 2:
            subject_score += 1
        if event_count >= 3:
            subject_score += 2
        elif event_count >= 1:
            subject_score += 1

        # Classify
        self.profile.source_richness = 'high' if source_score >= 4 else ('medium' if source_score >= 2 else 'low')
        self.profile.subject_richness = 'high' if subject_score >= 4 else ('medium' if subject_score >= 2 else 'low')

        # Recommend emphasis
        if source_score >= 4 and subject_score >= 4:
            self.profile.recommended_emphasis = 'both'
        elif source_score > subject_score + 1:
            self.profile.recommended_emphasis = 'source'
        elif subject_score > source_score + 1:
            self.profile.recommended_emphasis = 'subject'
        elif source_score >= 2 or subject_score >= 2:
            self.profile.recommended_emphasis = 'both'
        else:
            self.profile.recommended_emphasis = 'neither'

    def _determine_narrative_arc(self, dated_mentions: List[MediaMention]) -> str:
        """Determine the narrative arc pattern."""
        if not dated_mentions or len(dated_mentions) < 3:
            return "insufficient_data"

        sorted_mentions = sorted(dated_mentions, key=lambda m: m.date)

        # Split into thirds
        third = len(sorted_mentions) // 3
        early = sorted_mentions[:third]
        middle = sorted_mentions[third:2*third]
        late = sorted_mentions[2*third:]

        def avg_sentiment(mentions):
            scores = {'positive': 1, 'neutral': 0, 'negative': -1}
            if not mentions:
                return 0
            return sum(scores.get(m.sentiment, 0) for m in mentions) / len(mentions)

        early_sent = avg_sentiment(early)
        late_sent = avg_sentiment(late)

        # Volume trajectory
        early_vol = len(early)
        late_vol = len(late)

        if late_vol > early_vol * 2:
            if late_sent > early_sent:
                return "rising_star"
            elif late_sent < early_sent:
                return "controversial_growth"
            return "growing_visibility"

        if late_vol < early_vol * 0.5:
            if late_sent < early_sent:
                return "fall_from_grace"
            return "fading_prominence"

        if late_sent < early_sent - 0.5:
            return "deteriorating"
        if late_sent > early_sent + 0.5:
            return "rehabilitation"

        return "steady_professional"

    def _find_typical(self, mentions: List[MediaMention]) -> Optional[MediaMention]:
        """Find most representative/typical mention."""
        if not mentions:
            return None

        # Find the tier that has the most mentions
        tier_counts = defaultdict(list)
        for m in mentions:
            tier_counts[m.tier].append(m)

        most_common_tier = max(tier_counts, key=lambda t: len(tier_counts[t]))
        tier_mentions = tier_counts[most_common_tier]

        # Return most recent from the most common tier
        dated = [m for m in tier_mentions if m.date]
        if dated:
            return max(dated, key=lambda m: m.date)
        return tier_mentions[0]

    def _find_standout(self, mentions: List[MediaMention]) -> Optional[MediaMention]:
        """Find most unusual/noteworthy mention."""
        if not mentions:
            return None

        # Prefer: T1 sources, negative sentiment (more noteworthy), or unique categories
        candidates = []

        # T1 mentions are always noteworthy
        t1_mentions = [m for m in mentions if m.tier == 1]
        if t1_mentions:
            candidates.extend(t1_mentions)

        # Negative coverage is noteworthy
        negative = [m for m in mentions if m.sentiment == 'negative']
        if negative:
            candidates.extend(negative)

        # Third-party validation is noteworthy
        validated = [m for m in mentions if m.quotes_others_about_subject]
        if validated:
            candidates.extend(validated)

        if candidates:
            # Prefer T1 negative with validation
            for c in candidates:
                if c.tier == 1 and c.sentiment == 'negative':
                    return c
            for c in candidates:
                if c.tier == 1:
                    return c
            return candidates[0]

        # If nothing stands out, return lowest tier (unusual to have only low-tier)
        return min(mentions, key=lambda m: m.tier)

    def _compare_to_baseline(self):
        """Compare profile to expected baseline for entity type."""
        baseline = BASELINES.get(self.entity_type, BASELINES["private_individual"])

        mention_range = baseline["expected_mentions"]
        if self.profile.unique_mention_count < mention_range[0]:
            self.profile.vs_baseline = "below"
        elif self.profile.unique_mention_count > mention_range[1]:
            self.profile.vs_baseline = "above"
        else:
            self.profile.vs_baseline = "at"

        # Check for mismatches
        mismatches = []

        if (self.profile.unique_mention_count < mention_range[0] * 0.5 and
            self.entity_type in ['fortune_500_ceo', 'large_corporation', 'pep_politician']):
            mismatches.append({
                "type": "low_visibility",
                "expected": f"{mention_range[0]}+ mentions",
                "actual": self.profile.unique_mention_count,
                "severity": "HIGH"
            })

        if self.profile.pr_republication_pct > 80:
            mismatches.append({
                "type": "pr_dominated",
                "expected": "Mix of editorial and PR",
                "actual": f"{self.profile.pr_republication_pct:.0f}% PR content",
                "severity": "MEDIUM"
            })

        self.profile.mismatches = mismatches
        if any(m["severity"] == "HIGH" for m in mismatches):
            self.profile.mismatch_risk = "HIGH"
        elif mismatches:
            self.profile.mismatch_risk = "MEDIUM"

    def to_dict(self) -> Dict:
        """Export profile as dictionary."""
        profile = self.profile
        return {
            "entity_name": profile.entity_name,
            "entity_type": profile.entity_type,
            "analysis_date": profile.analysis_date.isoformat(),
            "volume": {
                "raw_mentions": profile.raw_mention_count,
                "unique_mentions": profile.unique_mention_count,
                "duplication_ratio": round(profile.duplication_ratio, 2)
            },
            "scale": {
                "geographic_scope": profile.geographic_scope,
                "primary_tier": profile.primary_tier,
                "tier_distribution": profile.tier_distribution,
                "countries": profile.countries_covered,
                "languages": profile.languages_covered
            },
            "sentiment": {
                "distribution": profile.sentiment_distribution,
                "trajectory": profile.sentiment_trajectory
            },
            "temporal": {
                "first_mention": self._mention_to_dict(profile.first_mention),
                "most_recent": self._mention_to_dict(profile.most_recent_mention),
                "coverage_span_years": round(profile.coverage_span_years, 1),
                "peak_period": profile.peak_period,
                "narrative_arc": profile.narrative_arc
            },
            "anchors": {
                "typical": self._mention_to_dict(profile.typical_example),
                "standout": self._mention_to_dict(profile.standout_example)
            },
            "authenticity": {
                "original_editorial_pct": round(profile.original_editorial_pct, 1),
                "pr_republication_pct": round(profile.pr_republication_pct, 1),
                "third_party_validation_count": profile.third_party_validation_count
            },
            "coverage_types": profile.coverage_types,
            "comparison": {
                "vs_baseline": profile.vs_baseline,
                "mismatches": profile.mismatches,
                "mismatch_risk": profile.mismatch_risk
            },
            # ET3: Theme/Phenomenon/Event data
            "subject_analysis": {
                "theme_distribution": profile.theme_distribution,
                "theme_sentiment": profile.theme_sentiment,
                "theme_trajectory": profile.theme_trajectory,
                "events": [self._event_to_dict(e) for e in profile.events]
            },
            "centricity": {
                "source_richness": profile.source_richness,
                "subject_richness": profile.subject_richness,
                "recommended_emphasis": profile.recommended_emphasis
            },
            # Graph data for storage
            "graph_data": self.get_extraction_nodes_and_edges()
        }

    def _event_to_dict(self, event: Event) -> Dict:
        """Convert Event to dictionary."""
        return {
            "id": event.id,
            "phenomenon": event.phenomenon,
            "phenomenon_category": event.phenomenon_category,
            "entity_primary": event.entity_primary,
            "entities_related": event.entities_related,
            "location_geographic": event.location_geographic,
            "location_institutional": event.location_institutional,
            "date": event.date.isoformat() if event.date else None,
            "period": event.period,
            "coverage_count": event.coverage_count,
            "source_tiers": event.source_tiers,
            "sentiment": event.sentiment,
            "significance": event.significance,
            "anchors": {
                "typical": self._mention_to_dict(event.typical_mention),
                "standout": self._mention_to_dict(event.standout_mention),
                "first": self._mention_to_dict(event.first_mention),
                "most_recent": self._mention_to_dict(event.most_recent_mention)
            }
        }

    def _mention_to_dict(self, mention: Optional[MediaMention]) -> Optional[Dict]:
        """Convert mention to dictionary."""
        if not mention:
            return None
        return {
            "url": mention.url,
            "title": mention.title,
            "publication": mention.publication,
            "date": mention.date.isoformat() if mention.date else None,
            "tier": mention.tier,
            "sentiment": mention.sentiment,
            "category": mention.category
        }

    def generate_report_data(self) -> Dict:
        """Generate data formatted for REPUTATION_PROFILE_ANALYSIS template."""
        profile = self.to_dict()

        # Add formatted strings for template insertion
        profile["template_strings"] = {
            "overview": self._generate_overview_string(),
            "reference_points": self._generate_reference_points_string(),
            "assessment": self._generate_assessment_string()
        }

        return profile

    def _generate_overview_string(self) -> str:
        """Generate the comprehensive overview paragraph."""
        p = self.profile

        sentiment_desc = max(p.sentiment_distribution, key=p.sentiment_distribution.get) if p.sentiment_distribution else "neutral"

        return (
            f"Research identified {p.unique_mention_count} unique mentions "
            f"(from {p.raw_mention_count} raw results, duplication ratio {p.duplication_ratio:.1f}x). "
            f"Coverage spans {p.coverage_span_years:.1f} years across {len(p.countries_covered)} countries. "
            f"Profile is {p.geographic_scope} in scope, primarily Tier {p.primary_tier} sources, "
            f"with {sentiment_desc} sentiment predominant."
        )

    def _generate_reference_points_string(self) -> str:
        """Generate the four anchor points string."""
        p = self.profile

        typical = f"Tier {p.typical_example.tier} - {p.typical_example.publication}" if p.typical_example else "N/A"
        standout = f"{p.standout_example.publication}: {p.standout_example.title[:50]}..." if p.standout_example else "N/A"
        recent = f"{p.most_recent_mention.date.strftime('%Y-%m-%d') if p.most_recent_mention and p.most_recent_mention.date else 'N/A'}"
        first = f"{p.first_mention.date.strftime('%Y-%m-%d') if p.first_mention and p.first_mention.date else 'N/A'}"

        return (
            f"- **Typical:** {typical}\n"
            f"- **Standout:** {standout}\n"
            f"- **Most Recent:** {recent}\n"
            f"- **First:** {first}"
        )

    def _generate_assessment_string(self) -> str:
        """Generate the assessment paragraph."""
        p = self.profile

        baseline_desc = {
            "above": "significantly above expectations",
            "at": "consistent with expectations",
            "below": "below expectations"
        }.get(p.vs_baseline, "could not be assessed against baseline")

        arc_desc = {
            "rising_star": "reflecting increasing prominence and positive trajectory",
            "steady_professional": "suggesting established, stable presence",
            "deteriorating": "showing declining sentiment over time",
            "fall_from_grace": "indicating significant reputational damage",
            "fading_prominence": "suggesting reduced relevance",
            "growing_visibility": "showing increasing coverage",
            "rehabilitation": "suggesting recovery from past issues"
        }.get(p.narrative_arc, "")

        risk_note = ""
        if p.mismatch_risk == "HIGH":
            risk_note = " Red flags identified requiring further investigation."
        elif p.mismatch_risk == "MEDIUM":
            risk_note = " Some anomalies noted."

        return (
            f"This profile is {baseline_desc} for {p.entity_type.replace('_', ' ')}. "
            f"Narrative arc: {p.narrative_arc.replace('_', ' ')}, {arc_desc}.{risk_note}"
        )


# Convenience function for direct use
async def analyze_reputation(
    entity_name: str,
    entity_type: str,
    brute_results: List[Dict] = None,
    linklater_data: Dict = None,
    use_ai_extraction: bool = False
) -> Dict:
    """
    Analyze reputation from search results.

    Args:
        entity_name: Name of entity to analyze
        entity_type: Type from BASELINES keys
        brute_results: Results from Brute search
        linklater_data: Domain/backlink data from LINKLATER
        use_ai_extraction: If True, use Haiku for theme/phenomenon/event extraction

    Returns:
        Reputation profile dictionary with graph_data for node/edge storage
    """
    analyzer = ReputationAnalyzer(entity_name, entity_type)

    if brute_results:
        for result in brute_results:
            engine = result.get('engine', 'unknown')
            if use_ai_extraction:
                await analyzer.add_from_brute_result_with_ai(result, engine)
            else:
                analyzer.add_from_brute_result(result, engine)

    if linklater_data:
        analyzer.profile.referring_domains = linklater_data.get('referring_domains', 0)
        analyzer.profile.domain_authority = linklater_data.get('domain_authority', 0)

    analyzer.analyze(use_ai_extraction=use_ai_extraction)
    return analyzer.generate_report_data()


async def analyze_reputation_with_graph_storage(
    entity_name: str,
    entity_type: str,
    brute_results: List[Dict] = None,
    linklater_data: Dict = None,
    graph_storage = None
) -> Dict:
    """
    Analyze reputation AND store extracted nodes/edges in graph.

    Args:
        entity_name: Name of entity to analyze
        entity_type: Type from BASELINES keys
        brute_results: Results from Brute search
        linklater_data: Domain/backlink data from LINKLATER
        graph_storage: EntityGraphStorage instance for persisting nodes/edges

    Returns:
        Reputation profile dictionary
    """
    # Run analysis with AI extraction
    result = await analyze_reputation(
        entity_name, entity_type, brute_results, linklater_data,
        use_ai_extraction=True
    )

    # Store graph data if storage provided
    if graph_storage and result.get("graph_data"):
        graph_data = result["graph_data"]
        for node in graph_data.get("nodes", []):
            try:
                graph_storage.add_node(node)
            except Exception as e:
                logger.warning(f"Failed to store node: {e}")

        for edge in graph_data.get("edges", []):
            try:
                graph_storage.add_edge(edge)
            except Exception as e:
                logger.warning(f"Failed to store edge: {e}")

        logger.info(
            f"Stored {len(graph_data.get('nodes', []))} nodes and "
            f"{len(graph_data.get('edges', []))} edges for {entity_name}"
        )

    return result


if __name__ == "__main__":
    # Test with sample data
    import asyncio

    sample_results = [
        {
            "url": "https://ft.com/article1",
            "title": "CEO John Smith appointed to lead Acme Corp",
            "snippet": "John Smith, former executive at BigCorp, has been appointed CEO of Acme Corp. Smith said the acquisition strategy will focus on growth.",
            "engine": "GO"
        },
        {
            "url": "https://prnewswire.com/release1",
            "title": "Acme Corp Announces Q3 Results",
            "snippet": "John Smith, CEO of Acme Corp, announced record quarterly earnings...",
            "engine": "BR"
        },
        {
            "url": "https://wsj.com/business/scandal",
            "title": "Acme Corp faces SEC investigation",
            "snippet": "The SEC has opened an investigation into Acme Corp's accounting practices. CEO John Smith declined to comment.",
            "engine": "GO"
        },
        {
            "url": "https://localpost.com/news",
            "title": "Local Business Leader Honored",
            "snippet": "John Smith received the Business Leader of the Year award...",
            "engine": "BI"
        },
    ]

    async def test():
        print("=" * 60)
        print("Testing WITHOUT AI extraction (keyword-only)")
        print("=" * 60)
        result = await analyze_reputation("John Smith", "mid_market_exec", sample_results, use_ai_extraction=False)
        print(f"Themes found: {result.get('subject_analysis', {}).get('theme_distribution', {})}")
        print(f"Events found: {len(result.get('subject_analysis', {}).get('events', []))}")
        print(f"Centricity: {result.get('centricity', {})}")
        print()

        if EXTRACTION_AVAILABLE:
            print("=" * 60)
            print("Testing WITH AI extraction (Haiku)")
            print("=" * 60)
            result_ai = await analyze_reputation("John Smith", "mid_market_exec", sample_results, use_ai_extraction=True)
            print(f"Themes found: {result_ai.get('subject_analysis', {}).get('theme_distribution', {})}")
            print(f"Events found: {len(result_ai.get('subject_analysis', {}).get('events', []))}")
            print(f"Graph nodes: {len(result_ai.get('graph_data', {}).get('nodes', []))}")
            print(f"Graph edges: {len(result_ai.get('graph_data', {}).get('edges', []))}")
        else:
            print("Extraction pipeline not available - skipping AI test")

    asyncio.run(test())
