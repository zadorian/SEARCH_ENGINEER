#!/usr/bin/env python3
"""
Axis Analyzer - Multi-dimensional query analysis for intelligent engine routing.

Implements the SWITCHBOARD pattern with four primary axes:
- SUBJECT: Entity types (person, company, phone, email, topic)
- LOCATION: Geographic context and regional engines
- OBJECT: Query operators (site:, filetype:, intitle:, etc.)
- TEMPORAL: Time-based constraints (date ranges, recency)

Each axis influences which engines are most relevant for a query.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class SubjectType(Enum):
    """Entity types detected in queries."""
    PERSON = auto()       # Names, biographies, people search
    COMPANY = auto()      # Organizations, corporations, businesses
    PHONE = auto()        # Phone numbers, reverse lookups
    EMAIL = auto()        # Email addresses
    ADDRESS = auto()      # Physical addresses, locations
    DOMAIN = auto()       # Domain names, websites
    IP_ADDRESS = auto()   # IP addresses
    USERNAME = auto()     # Social media handles, usernames
    TOPIC = auto()        # General topics, concepts
    ACADEMIC = auto()     # Research, papers, scholarly
    NEWS = auto()         # Current events, breaking news
    PRODUCT = auto()      # Products, reviews
    LEGAL = auto()        # Legal documents, court records
    FINANCIAL = auto()    # Financial data, stocks, reports
    MEDICAL = auto()      # Medical, health information
    CODE = auto()         # Code, programming, technical
    BOOK = auto()         # Books, publications, literature
    SOCIAL = auto()       # Social media content


class LocationContext(Enum):
    """Geographic context detected in queries."""
    GLOBAL = auto()       # No specific location
    US = auto()           # United States
    UK = auto()           # United Kingdom
    EU = auto()           # European Union
    RUSSIA = auto()       # Russia, CIS
    CHINA = auto()        # China, Chinese language
    JAPAN = auto()        # Japan
    LATAM = auto()        # Latin America
    AFRICA = auto()       # Africa
    MIDDLE_EAST = auto()  # Middle East
    ASIA_PACIFIC = auto() # Asia Pacific (excluding specific countries)
    LOCAL = auto()        # Local/nearby searches


class ObjectOperator(Enum):
    """Search operators detected in queries."""
    SITE = auto()         # site:domain.com
    FILETYPE = auto()     # filetype:pdf
    INTITLE = auto()      # intitle:keyword
    INURL = auto()        # inurl:keyword
    INTEXT = auto()       # intext:keyword
    LINK = auto()         # link:url
    CACHE = auto()        # cache:url
    RELATED = auto()      # related:url
    EXACT_PHRASE = auto() # "exact phrase"
    EXCLUDE = auto()      # -keyword
    OR_OPERATOR = auto()  # keyword1 OR keyword2
    WILDCARD = auto()     # keyword*
    DATE_RANGE = auto()   # daterange: or before:/after:


class TemporalContext(Enum):
    """Time-based context detected in queries."""
    ANY_TIME = auto()     # No time constraint
    RECENT = auto()       # Last few days/week
    THIS_MONTH = auto()   # Last 30 days
    THIS_YEAR = auto()    # Last 12 months
    HISTORICAL = auto()   # Older content, archives
    SPECIFIC_DATE = auto() # Specific date or range


@dataclass
class AxisAnalysis:
    """Results of multi-axis query analysis."""
    # Subject axis
    subject_types: List[SubjectType] = field(default_factory=list)
    subject_confidence: float = 0.0
    detected_entities: Dict[str, str] = field(default_factory=dict)

    # Location axis
    location_context: LocationContext = LocationContext.GLOBAL
    detected_locations: List[str] = field(default_factory=list)

    # Object axis
    operators: List[ObjectOperator] = field(default_factory=list)
    operator_values: Dict[str, str] = field(default_factory=dict)

    # Temporal axis
    temporal_context: TemporalContext = TemporalContext.ANY_TIME
    date_range: Optional[Tuple[str, str]] = None

    # Query cleanup
    cleaned_query: str = ""
    original_query: str = ""


class AxisAnalyzer:
    """
    Multi-axis query analyzer implementing SWITCHBOARD pattern.

    Analyzes queries across four dimensions to determine optimal
    engine selection strategy.
    """

    # Entity detection patterns
    ENTITY_PATTERNS = {
        SubjectType.PHONE: [
            r'\+?[\d\s\-\(\)]{10,}',  # Phone numbers
            r'\b\d{3}[\s\-\.]\d{3}[\s\-\.]\d{4}\b',  # US format
            r'\b\d{4}[\s\-\.]\d{3}[\s\-\.]\d{3}\b',  # EU format
        ],
        SubjectType.EMAIL: [
            r'\b[\w\.\-]+@[\w\.\-]+\.\w+\b',  # Email addresses
        ],
        SubjectType.IP_ADDRESS: [
            r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',  # IPv4
            r'\b([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b',  # IPv6
        ],
        SubjectType.DOMAIN: [
            r'\b(?:https?://)?(?:www\.)?[\w\-]+\.(?:com|org|net|io|co|gov|edu|uk|de|fr|ru|cn)\b',
        ],
        SubjectType.USERNAME: [
            r'@[\w\-_]+',  # Twitter/social handles
        ],
    }

    # Subject type keyword patterns
    SUBJECT_KEYWORDS = {
        SubjectType.PERSON: [
            r'\b(?:who is|biography|profile of|about)\b',
            r'\b(?:ceo|cfo|founder|director|president|manager)\s+of\b',
            r'\b(?:dr\.|mr\.|mrs\.|ms\.|prof\.)\s+\w+',
        ],
        SubjectType.COMPANY: [
            r'\b(?:inc|corp|llc|ltd|gmbh|ag|sa|plc|co\.)\b',
            r'\b(?:company|corporation|business|firm|enterprise)\b',
            r'\b(?:annual report|sec filing|10-k|10-q)\b',
        ],
        SubjectType.ACADEMIC: [
            r'\b(?:research|study|paper|journal|academic|scholar)\b',
            r'\b(?:university|professor|phd|thesis|dissertation)\b',
            r'\b(?:peer[\s\-]?review|citation|doi|arxiv|pubmed)\b',
        ],
        SubjectType.NEWS: [
            r'\b(?:news|breaking|latest|recent|today|update)\b',
            r'\b(?:headline|reporter|journalist|press release)\b',
        ],
        SubjectType.CODE: [
            r'\b(?:function|class|method|code|programming|api)\b',
            r'\b(?:python|javascript|java|rust|golang|typescript)\b',
            r'\b(?:github|stackoverflow|npm|pip|cargo)\b',
        ],
        SubjectType.BOOK: [
            r'\b(?:book|ebook|pdf|epub|novel|textbook|author)\b',
            r'\b(?:library|gutenberg|libgen|isbn)\b',
        ],
        SubjectType.SOCIAL: [
            r'\b(?:twitter|facebook|reddit|linkedin|instagram)\b',
            r'\b(?:post|tweet|comment|discussion|forum|thread)\b',
        ],
        SubjectType.FINANCIAL: [
            r'\b(?:stock|share|investor|portfolio|dividend)\b',
            r'\b(?:revenue|profit|earnings|market cap|ipo)\b',
        ],
        SubjectType.LEGAL: [
            r'\b(?:court|case|lawsuit|litigation|verdict)\b',
            r'\b(?:attorney|lawyer|legal|law firm|docket)\b',
        ],
        SubjectType.MEDICAL: [
            r'\b(?:medical|health|disease|treatment|symptom)\b',
            r'\b(?:doctor|hospital|diagnosis|medication)\b',
        ],
    }

    # Location patterns
    LOCATION_PATTERNS = {
        LocationContext.US: [
            r'\b(?:united states|usa|america|american)\b',
            r'\b(?:california|texas|florida|new york|illinois)\b',
            r'\b(?:washington dc|los angeles|chicago|houston)\b',
        ],
        LocationContext.UK: [
            r'\b(?:united kingdom|uk|britain|british|england)\b',
            r'\b(?:london|manchester|birmingham|scotland|wales)\b',
        ],
        LocationContext.EU: [
            r'\b(?:europe|european|eu)\b',
            r'\b(?:germany|france|italy|spain|netherlands)\b',
            r'\b(?:berlin|paris|rome|madrid|amsterdam)\b',
        ],
        LocationContext.RUSSIA: [
            r'\b(?:russia|russian|moscow|kremlin)\b',
            r'\b(?:ukraine|kazakhstan|belarus)\b',
        ],
        LocationContext.CHINA: [
            r'\b(?:china|chinese|beijing|shanghai|hong kong)\b',
        ],
        LocationContext.JAPAN: [
            r'\b(?:japan|japanese|tokyo|osaka)\b',
        ],
        LocationContext.LATAM: [
            r'\b(?:latin america|brazil|mexico|argentina)\b',
            r'\b(?:brazil|mexico city|buenos aires|sao paulo)\b',
        ],
    }

    # Operator patterns
    OPERATOR_PATTERNS = {
        ObjectOperator.SITE: r'site:(\S+)',
        ObjectOperator.FILETYPE: r'filetype:(\w+)',
        ObjectOperator.INTITLE: r'intitle:(\S+)',
        ObjectOperator.INURL: r'inurl:(\S+)',
        ObjectOperator.INTEXT: r'intext:(\S+)',
        ObjectOperator.LINK: r'link:(\S+)',
        ObjectOperator.CACHE: r'cache:(\S+)',
        ObjectOperator.RELATED: r'related:(\S+)',
        ObjectOperator.EXACT_PHRASE: r'"([^"]+)"',
        ObjectOperator.EXCLUDE: r'\s-(\S+)',
        ObjectOperator.OR_OPERATOR: r'\bOR\b',
        ObjectOperator.WILDCARD: r'\b\w+\*',
        ObjectOperator.DATE_RANGE: r'(?:daterange:|before:|after:)(\S+)',
    }

    # Temporal patterns
    TEMPORAL_KEYWORDS = {
        TemporalContext.RECENT: [
            r'\b(?:today|yesterday|this week|recent|latest|breaking)\b',
            r'\b(?:just|now|new|current)\b',
        ],
        TemporalContext.THIS_MONTH: [
            r'\b(?:this month|past month|last 30 days)\b',
        ],
        TemporalContext.THIS_YEAR: [
            r'\b(?:this year|202[0-9]|last year)\b',
        ],
        TemporalContext.HISTORICAL: [
            r'\b(?:history|historical|archive|past|old|vintage)\b',
            r'\b(?:19\d{2}|20[01]\d)\b',  # Years before 2020
        ],
    }

    def __init__(self):
        """Initialize the axis analyzer."""
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        self._entity_regex = {
            k: [re.compile(p, re.IGNORECASE) for p in patterns]
            for k, patterns in self.ENTITY_PATTERNS.items()
        }
        self._subject_regex = {
            k: [re.compile(p, re.IGNORECASE) for p in patterns]
            for k, patterns in self.SUBJECT_KEYWORDS.items()
        }
        self._location_regex = {
            k: [re.compile(p, re.IGNORECASE) for p in patterns]
            for k, patterns in self.LOCATION_PATTERNS.items()
        }
        self._operator_regex = {
            k: re.compile(p, re.IGNORECASE)
            for k, p in self.OPERATOR_PATTERNS.items()
        }
        self._temporal_regex = {
            k: [re.compile(p, re.IGNORECASE) for p in patterns]
            for k, patterns in self.TEMPORAL_KEYWORDS.items()
        }

    def analyze(self, query: str) -> AxisAnalysis:
        """
        Perform multi-axis analysis on a query.

        Args:
            query: Search query string

        Returns:
            AxisAnalysis with detected axes and cleaned query
        """
        analysis = AxisAnalysis(original_query=query, cleaned_query=query)

        # Analyze each axis
        self._analyze_subject_axis(query, analysis)
        self._analyze_location_axis(query, analysis)
        self._analyze_object_axis(query, analysis)
        self._analyze_temporal_axis(query, analysis)

        # Clean the query (remove operators)
        analysis.cleaned_query = self._clean_query(query, analysis)

        logger.debug(
            "Axis analysis: subjects=%s, location=%s, operators=%s, temporal=%s",
            [s.name for s in analysis.subject_types],
            analysis.location_context.name,
            [o.name for o in analysis.operators],
            analysis.temporal_context.name
        )

        return analysis

    def _analyze_subject_axis(self, query: str, analysis: AxisAnalysis):
        """Detect entity types in query."""
        detected_types: Set[SubjectType] = set()
        detected_entities: Dict[str, str] = {}

        # Check for explicit entity patterns (high confidence)
        for entity_type, patterns in self._entity_regex.items():
            for pattern in patterns:
                match = pattern.search(query)
                if match:
                    detected_types.add(entity_type)
                    detected_entities[entity_type.name] = match.group(0)
                    break

        # Check for keyword-based subject types
        type_scores: Dict[SubjectType, int] = {}
        for subject_type, patterns in self._subject_regex.items():
            score = 0
            for pattern in patterns:
                if pattern.search(query):
                    score += 1
            if score > 0:
                type_scores[subject_type] = score

        # Add top scoring types
        if type_scores:
            max_score = max(type_scores.values())
            for stype, score in type_scores.items():
                if score >= max_score * 0.7:  # Within 70% of top score
                    detected_types.add(stype)

        # Default to TOPIC if nothing detected
        if not detected_types:
            detected_types.add(SubjectType.TOPIC)

        analysis.subject_types = list(detected_types)
        analysis.detected_entities = detected_entities
        analysis.subject_confidence = len(detected_entities) / len(detected_types) if detected_types else 0.5

    def _analyze_location_axis(self, query: str, analysis: AxisAnalysis):
        """Detect geographic context in query."""
        detected_locations: List[str] = []
        location_context = LocationContext.GLOBAL

        for loc_context, patterns in self._location_regex.items():
            for pattern in patterns:
                match = pattern.search(query)
                if match:
                    location_context = loc_context
                    detected_locations.append(match.group(0))
                    break
            if detected_locations:
                break  # Use first match

        analysis.location_context = location_context
        analysis.detected_locations = detected_locations

    def _analyze_object_axis(self, query: str, analysis: AxisAnalysis):
        """Detect search operators in query."""
        operators: List[ObjectOperator] = []
        operator_values: Dict[str, str] = {}

        for operator, pattern in self._operator_regex.items():
            match = pattern.search(query)
            if match:
                operators.append(operator)
                if match.groups():
                    operator_values[operator.name] = match.group(1)

        analysis.operators = operators
        analysis.operator_values = operator_values

    def _analyze_temporal_axis(self, query: str, analysis: AxisAnalysis):
        """Detect time-based context in query."""
        temporal_context = TemporalContext.ANY_TIME

        for temp_context, patterns in self._temporal_regex.items():
            for pattern in patterns:
                if pattern.search(query):
                    temporal_context = temp_context
                    break
            if temporal_context != TemporalContext.ANY_TIME:
                break

        analysis.temporal_context = temporal_context

    def _clean_query(self, query: str, analysis: AxisAnalysis) -> str:
        """Remove operators from query to get clean search terms."""
        cleaned = query

        # Remove operators
        for operator, pattern in self._operator_regex.items():
            if operator in [ObjectOperator.EXACT_PHRASE, ObjectOperator.EXCLUDE]:
                continue  # Keep these in query
            cleaned = re.sub(pattern, '', cleaned)

        # Clean up whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned


# Singleton for convenience
_analyzer: Optional[AxisAnalyzer] = None

def get_analyzer() -> AxisAnalyzer:
    """Get global AxisAnalyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = AxisAnalyzer()
    return _analyzer


def analyze_query(query: str) -> AxisAnalysis:
    """Quick function to analyze a query."""
    return get_analyzer().analyze(query)


if __name__ == '__main__':
    # Demo axis analysis
    print("Axis Analyzer - Demo")
    print("=" * 60)

    test_queries = [
        "John Smith CEO",
        "Apple Inc annual report 2023",
        "+1-555-123-4567",
        "user@example.com",
        "site:github.com python async",
        "filetype:pdf financial statement",
        "climate change research papers",
        "latest news Ukraine",
        "192.168.1.1 security",
        "@elonmusk twitter",
        "best restaurants in New York",
        "history of Berlin wall 1989",
    ]

    analyzer = AxisAnalyzer()

    for query in test_queries:
        print(f"\nQuery: '{query}'")
        analysis = analyzer.analyze(query)
        print(f"  Subjects: {[s.name for s in analysis.subject_types]}")
        print(f"  Location: {analysis.location_context.name}")
        print(f"  Operators: {[o.name for o in analysis.operators]}")
        print(f"  Temporal: {analysis.temporal_context.name}")
        if analysis.detected_entities:
            print(f"  Entities: {analysis.detected_entities}")
        print(f"  Clean: '{analysis.cleaned_query}'")
