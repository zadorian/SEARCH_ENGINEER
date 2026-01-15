#!/usr/bin/env python3
"""
FORENSIC QUERY CONSTRUCTOR - FINAL INTEGRATED VERSION
======================================================
Rule-based query construction with:
- Mandatory operators (filetype, inurl, before/after)
- Dynamic questioning probes
- Negative fingerprinting
- Token uniqueness analysis
- OR-expansion for common names
- Depth-prioritized scoring
"""

import re
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set, Any
from enum import Enum
from datetime import datetime
import json

# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class TokenUniqueness(Enum):
    """Token uniqueness classification"""
    VERY_HIGH = "very_high"   # Use alone - don't dilute
    HIGH = "high"             # Minimal context (1 pivot max)
    MEDIUM = "medium"         # Moderate expansion
    LOW = "low"               # Aggressive expansion required
    VERY_LOW = "very_low"     # Maximum expansion + strong pivots

class QueryTier(Enum):
    """Query tier classification"""
    T0_NET = "0_Net"                    # Maximum expansion
    T1_INTERSECT = "1_Intersect"        # Minimal AND
    T2_PHRASE = "2_Phrase"              # Exact phrase
    T3_FILTER = "3_Filter"              # Authority exclusion
    T4_ARTIFACT = "4_Artifact"          # filetype/inurl
    T5_TIMEMACHINE = "5_TimeMachine"    # before/after/archive
    T6_EXCLUSION = "6_Exclusion"        # Negative fingerprint

class SourceType(Enum):
    """Source type for scoring"""
    FORUM = "forum"
    PDF = "pdf"
    SPREADSHEET = "spreadsheet"
    PERSONAL_BLOG = "personal_blog"
    DIRECTORY = "directory"
    LOCAL_NEWS = "local_news"
    TRADE_PUB = "trade_publication"
    CORPORATE = "corporate_page"
    LINKEDIN = "linkedin"
    MAJOR_NEWS = "major_news"
    WIKIPEDIA = "wikipedia"
    UNKNOWN = "unknown"

# =============================================================================
# EXPANSION DICTIONARIES
# =============================================================================

# Title/Role expansions for OR-stacking
TITLE_EXPANSIONS = {
    "director": ["Director", "Head of", "Chief", "VP", "Vice President", "Lead", "Senior Manager", "Managing Director"],
    "manager": ["Manager", "Head", "Lead", "Supervisor", "Coordinator", "Administrator", "Team Lead"],
    "ceo": ["CEO", "Chief Executive Officer", "Chief Executive", "Managing Director", "President", "Founder", "Chairman", "MD"],
    "cfo": ["CFO", "Chief Financial Officer", "Finance Director", "VP Finance", "Treasurer", "Controller", "Financial Controller"],
    "cto": ["CTO", "Chief Technology Officer", "VP Engineering", "Head of Engineering", "Tech Lead", "Technical Director"],
    "coo": ["COO", "Chief Operating Officer", "Operations Director", "VP Operations", "Head of Operations"],
    "cmo": ["CMO", "Chief Marketing Officer", "Marketing Director", "VP Marketing", "Head of Marketing"],
    "partner": ["Partner", "Managing Partner", "Senior Partner", "Principal", "Associate Partner", "Equity Partner"],
    "founder": ["Founder", "Co-Founder", "Co-founder", "Founding Partner", "Creator", "Entrepreneur"],
    "engineer": ["Engineer", "Developer", "Programmer", "Architect", "Technical Lead", "SWE", "Software Engineer"],
    "analyst": ["Analyst", "Research Analyst", "Senior Analyst", "Associate", "Researcher", "Investigator"],
    "consultant": ["Consultant", "Advisor", "Adviser", "Specialist", "Expert", "Senior Consultant", "Principal Consultant"],
    "scientist": ["Scientist", "Researcher", "Research Scientist", "Senior Scientist", "Principal Scientist", "Fellow"],
    "professor": ["Professor", "Prof", "Dr", "Associate Professor", "Assistant Professor", "Lecturer", "Faculty"],
    "lawyer": ["Lawyer", "Attorney", "Counsel", "Legal Counsel", "Solicitor", "Barrister", "Partner"],
    "doctor": ["Doctor", "Dr", "Physician", "MD", "Surgeon", "Specialist", "Consultant"],
}

# Corporate suffix expansions by region
CORPORATE_SUFFIXES = {
    "us": ["Inc", "Inc.", "Corp", "Corp.", "Corporation", "LLC", "L.L.C.", "LP", "LLP", "Co", "Co."],
    "uk": ["Ltd", "Ltd.", "Limited", "PLC", "plc", "LLP", "Partners"],
    "de": ["GmbH", "AG", "SE", "KG", "KGaA", "OHG", "e.V.", "GbR", "UG"],
    "fr": ["SA", "SAS", "SARL", "SASU", "SNC", "EURL"],
    "nl": ["BV", "B.V.", "NV", "N.V."],
    "jp": ["KK", "K.K.", "GK", "YK"],
    "generic": ["Group", "Holdings", "International", "Global", "Worldwide", "& Co", "& Associates"]
}

# High authority domains (PENALTY)
HIGH_AUTHORITY_DOMAINS = [
    "wikipedia.org", "linkedin.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "tiktok.com", "pinterest.com",
    "nytimes.com", "bbc.com", "bbc.co.uk", "cnn.com", "foxnews.com",
    "reuters.com", "bloomberg.com", "forbes.com", "fortune.com",
    "wsj.com", "ft.com", "economist.com", "guardian.com", "theguardian.com",
    "washingtonpost.com", "usatoday.com", "huffpost.com", "buzzfeed.com",
    "medium.com", "quora.com", "reddit.com", "tumblr.com",
    "crunchbase.com", "zoominfo.com", "pitchbook.com", "owler.com",
    "glassdoor.com", "indeed.com", "monster.com"
]

# Low authority TLDs (BONUS)
LOW_AUTHORITY_TLDS = [".me", ".io", ".info", ".name", ".blog", ".site", ".online", ".xyz", ".tech", ".club"]

# Common first names (indicates need for expansion)
COMMON_FIRST_NAMES = {
    "john", "james", "michael", "david", "robert", "william", "richard", "joseph", "thomas", "charles",
    "mary", "patricia", "jennifer", "linda", "elizabeth", "barbara", "susan", "jessica", "sarah", "karen",
    "daniel", "matthew", "anthony", "mark", "donald", "steven", "paul", "andrew", "joshua", "kenneth",
    "nancy", "betty", "margaret", "sandra", "ashley", "kimberly", "emily", "donna", "michelle", "dorothy",
    "chris", "christopher", "brian", "kevin", "jason", "jeff", "jeffrey", "ryan", "jacob", "gary",
    "lisa", "nancy", "betty", "helen", "samantha", "katherine", "christine", "deborah", "rachel", "laura",
    "peter", "frank", "scott", "eric", "stephen", "larry", "justin", "brandon", "raymond", "gregory",
    "anna", "marie", "diana", "ruth", "sharon", "michelle", "laura", "sarah", "cynthia", "kathleen",
    "mohammed", "muhammad", "ahmed", "ali", "omar", "hassan", "hussein", "ibrahim", "mustafa", "yusuf",
    "wei", "fang", "li", "wang", "zhang", "chen", "liu", "yang", "huang", "zhao",
    "hans", "peter", "klaus", "wolfgang", "jürgen", "stefan", "andreas", "thomas", "michael", "martin",
    "jean", "pierre", "michel", "françois", "jacques", "philippe", "alain", "bernard", "louis", "marc"
}

# Common last names (indicates need for expansion)
COMMON_LAST_NAMES = {
    "smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis", "rodriguez", "martinez",
    "hernandez", "lopez", "gonzalez", "wilson", "anderson", "thomas", "taylor", "moore", "jackson", "martin",
    "lee", "perez", "thompson", "white", "harris", "sanchez", "clark", "ramirez", "lewis", "robinson",
    "walker", "young", "allen", "king", "wright", "scott", "torres", "nguyen", "hill", "flores",
    "green", "adams", "nelson", "baker", "hall", "rivera", "campbell", "mitchell", "carter", "roberts",
    "kim", "park", "choi", "jung", "kang", "cho", "yoon", "jang", "lim", "han",
    "wang", "li", "zhang", "liu", "chen", "yang", "huang", "zhao", "wu", "zhou",
    "müller", "schmidt", "schneider", "fischer", "weber", "meyer", "wagner", "becker", "schulz", "hoffmann",
    "kumar", "sharma", "singh", "patel", "gupta", "khan", "ali", "ahmed", "shah", "verma"
}

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TokenAnalysis:
    """Result of token uniqueness analysis"""
    original: str
    uniqueness: TokenUniqueness
    common_components: List[str]
    unique_components: List[str]
    expansion_required: bool
    recommended_strategy: str
    risk_factors: List[str]

@dataclass
class DynamicProbes:
    """Dynamic questioning probes"""
    identity_probes: List[str]      # Who else, what role
    reference_probes: List[str]     # Name variations
    context_probes: List[str]       # Nearby words, doc types
    exclusion_probes: List[str]     # Negative fingerprints

@dataclass
class ForensicQuery:
    """A single forensic query"""
    q: str
    tier: str
    logic: str
    operators_used: List[str]
    expected_noise: str
    forensic_value: str
    rationale: str
    hash_id: str = ""
    
    def __post_init__(self):
        if not self.hash_id:
            self.hash_id = hashlib.md5(self.q.lower().encode()).hexdigest()[:8]

@dataclass
class ScoreBreakdown:
    """Forensic score breakdown"""
    base_score: int
    depth_bonus: int
    domain_modifier: int
    low_authority_bonus: int
    authenticity_penalty: int
    total: int

# =============================================================================
# TOKEN ANALYZER
# =============================================================================

class TokenAnalyzer:
    """Analyze token uniqueness to determine search strategy"""
    
    @classmethod
    def analyze(cls, target: str) -> TokenAnalysis:
        """
        Analyze target string for uniqueness.
        
        Args:
            target: The search target (name, company, term)
            
        Returns:
            TokenAnalysis with recommendations
        """
        words = target.split()
        common_parts = []
        unique_parts = []
        risk_factors = []
        
        for word in words:
            word_lower = word.lower()
            
            # Check against common names
            if word_lower in COMMON_FIRST_NAMES:
                common_parts.append(word)
                risk_factors.append(f"Common first name: {word}")
            elif word_lower in COMMON_LAST_NAMES:
                common_parts.append(word)
                risk_factors.append(f"Common last name: {word}")
            elif len(word) <= 3:
                common_parts.append(word)
                risk_factors.append(f"Short token: {word}")
            else:
                unique_parts.append(word)
        
        # Determine uniqueness level
        total_words = len(words)
        common_ratio = len(common_parts) / total_words if total_words > 0 else 0
        
        if common_ratio == 0 and total_words == 1 and len(target) >= 8:
            uniqueness = TokenUniqueness.VERY_HIGH
            strategy = "Use alone. Do NOT add extra words - every word is exclusion risk."
            expansion_required = False
        elif common_ratio == 0:
            uniqueness = TokenUniqueness.HIGH
            strategy = "Minimal context. Add at most 1 pivot term."
            expansion_required = False
        elif common_ratio < 0.5:
            uniqueness = TokenUniqueness.MEDIUM
            strategy = "Moderate expansion. Use OR-stacking for secondary identifiers."
            expansion_required = True
        elif common_ratio < 1.0:
            uniqueness = TokenUniqueness.LOW
            strategy = "Aggressive expansion. OR-stack roles/titles and use strong pivots."
            expansion_required = True
        else:
            uniqueness = TokenUniqueness.VERY_LOW
            strategy = "Maximum expansion required. Use all available context + OR-stacking + multiple pivots."
            expansion_required = True
            risk_factors.append("ALL components are common - high false positive risk")
        
        return TokenAnalysis(
            original=target,
            uniqueness=uniqueness,
            common_components=common_parts,
            unique_components=unique_parts,
            expansion_required=expansion_required,
            recommended_strategy=strategy,
            risk_factors=risk_factors
        )
    
    @classmethod
    def suggest_variations(cls, name: str) -> List[str]:
        """Generate realistic name variations"""
        variations = [name]
        words = name.split()
        
        if len(words) >= 2:
            first = words[0]
            last = words[-1]
            
            # Initial + Last
            variations.append(f"{first[0]}. {last}")
            
            # Last, First
            variations.append(f"{last}, {first}")
            
            # Last First (no comma)
            variations.append(f"{last} {first}")
            
            # Last only (if unique enough)
            if last.lower() not in COMMON_LAST_NAMES:
                variations.append(last)
            
            # Handle middle names
            if len(words) == 3:
                middle = words[1]
                variations.append(f"{first} {middle[0]}. {last}")
                variations.append(f"{first[0]}. {middle[0]}. {last}")
        
        return list(set(variations))

# =============================================================================
# DYNAMIC QUESTIONER
# =============================================================================

class DynamicQuestioner:
    """Generate probing questions for comprehensive coverage"""
    
    @classmethod
    def generate_probes(cls, anchor: str, pivot: Optional[str] = None,
                        context: Optional[str] = None) -> DynamicProbes:
        """Generate all probe types"""
        return DynamicProbes(
            identity_probes=cls._identity_probes(anchor, pivot),
            reference_probes=cls._reference_probes(anchor),
            context_probes=cls._context_probes(anchor, context),
            exclusion_probes=cls._exclusion_probes(anchor)
        )
    
    @classmethod
    def _identity_probes(cls, anchor: str, pivot: Optional[str]) -> List[str]:
        """Who else? What role?"""
        probes = []
        
        # Role variations
        if pivot:
            pivot_lower = pivot.lower()
            for key, expansions in TITLE_EXPANSIONS.items():
                if key in pivot_lower:
                    probes.extend(expansions[:6])
                    break
        
        # Generic identity probes
        probes.extend([
            "board member", "advisory board", "committee member",
            "speaker", "panelist", "presenter", "keynote"
        ])
        
        return probes[:12]
    
    @classmethod
    def _reference_probes(cls, anchor: str) -> List[str]:
        """How else referred to?"""
        return TokenAnalyzer.suggest_variations(anchor)
    
    @classmethod
    def _context_probes(cls, anchor: str, context: Optional[str]) -> List[str]:
        """What words appear nearby?"""
        probes = [
            # Document types
            "annual report", "press release", "meeting minutes",
            "conference proceedings", "court filing", "regulatory submission",
            "directory listing", "membership list", "staff page",
            "about us", "team page", "leadership", "board of directors",
            # Data indicators
            "contact", "email", "phone", "address", "bio", "biography",
            "cv", "resume", "curriculum vitae", "profile"
        ]
        
        if context:
            # Extract keywords from context
            words = re.findall(r'\b[A-Za-z]{5,}\b', context)
            probes.extend(list(set(words))[:5])
        
        return probes[:15]
    
    @classmethod
    def _exclusion_probes(cls, anchor: str) -> List[str]:
        """What words appear in false positives but NOT ours?"""
        anchor_lower = anchor.lower()
        exclusions = []
        
        # Ambiguous name patterns
        ambiguous_patterns = {
            "apple": ["iPhone", "Mac", "iOS", "Cupertino", "Tim Cook", "App Store"],
            "amazon": ["AWS", "Bezos", "Prime", "ecommerce", "Seattle", "Alexa"],
            "jaguar": ["car", "vehicle", "automotive", "feline", "animal", "XJ", "Land Rover"],
            "python": ["programming", "code", "snake", "reptile", "django", "flask"],
            "mercury": ["planet", "element", "thermometer", "Ford", "freddie"],
            "oracle": ["database", "java", "software", "Larry Ellison"],
            "shell": ["oil", "gas", "petroleum", "command line", "bash"],
            "delta": ["airline", "flight", "greek letter", "river"],
            "tesla": ["electric car", "Elon Musk", "EV", "Nikola"],
            "ford": ["car", "automotive", "vehicle", "motor company"],
            "wells": ["fargo", "bank", "water"],
            "chase": ["bank", "jpmorgan", "credit card"],
        }
        
        for pattern, terms in ambiguous_patterns.items():
            if pattern in anchor_lower:
                exclusions.extend(terms)
        
        # Generic exclusions for person searches
        words = anchor.split()
        if len(words) >= 2:  # Looks like a name
            exclusions.extend([
                "celebrity", "actor", "actress", "singer", "athlete",
                "fictional", "character", "movie", "tv show"
            ])
        
        return exclusions[:10]

# =============================================================================
# FORENSIC QUERY BUILDER
# =============================================================================

class ForensicQueryBuilder:
    """Build comprehensive forensic queries with mandatory operators"""
    
    def __init__(self):
        self.analyzer = TokenAnalyzer()
        self.questioner = DynamicQuestioner()
        self._seen_hashes: Set[str] = set()
    
    def build_all_tiers(
        self,
        anchor: str,
        pivot: Optional[str] = None,
        company: Optional[str] = None,
        title: Optional[str] = None,
        location: Optional[str] = None,
        context: Optional[str] = None,
        negative_fingerprints: Optional[List[str]] = None
    ) -> Tuple[List[ForensicQuery], TokenAnalysis, DynamicProbes]:
        """
        Build comprehensive query set across all tiers.
        
        Returns:
            Tuple of (queries, token_analysis, probes)
        """
        self._seen_hashes.clear()
        
        # Analyze anchor
        analysis = self.analyzer.analyze(anchor)
        
        # Generate probes
        probes = self.questioner.generate_probes(anchor, pivot, context)
        
        # Auto-generate negative fingerprints if not provided
        if not negative_fingerprints:
            negative_fingerprints = probes.exclusion_probes[:5]
        
        queries = []
        
        # Build each tier
        queries.extend(self._tier0_net(anchor, pivot, title, analysis, probes))
        queries.extend(self._tier1_intersect(anchor, pivot, company, location))
        queries.extend(self._tier2_phrase(anchor, pivot, title, company))
        queries.extend(self._tier3_filter(anchor, pivot))
        queries.extend(self._tier4_artifact_mandatory(anchor, pivot))
        queries.extend(self._tier5_timemachine_mandatory(anchor, pivot))
        queries.extend(self._tier6_exclusion(anchor, pivot, negative_fingerprints))
        
        # Deduplicate
        queries = self._deduplicate(queries)
        
        return queries, analysis, probes
    
    def _add_query(self, queries: List[ForensicQuery], query: ForensicQuery) -> None:
        """Add query if not duplicate"""
        if query.hash_id not in self._seen_hashes:
            self._seen_hashes.add(query.hash_id)
            queries.append(query)
    
    def _deduplicate(self, queries: List[ForensicQuery]) -> List[ForensicQuery]:
        """Remove duplicate queries"""
        seen = set()
        unique = []
        for q in queries:
            normalized = re.sub(r'\s+', ' ', q.q.lower().strip())
            h = hashlib.md5(normalized.encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                unique.append(q)
        return unique
    
    def _tier0_net(self, anchor: str, pivot: Optional[str], title: Optional[str],
                   analysis: TokenAnalysis, probes: DynamicProbes) -> List[ForensicQuery]:
        """Tier 0: Maximum expansion with OR-stacking"""
        queries = []
        
        # Base anchor search
        queries.append(ForensicQuery(
            q=f'"{anchor}"',
            tier="0_Net",
            logic="phrase_anchor_only",
            operators_used=["phrase"],
            expected_noise="high",
            forensic_value="critical",
            rationale="Raw anchor phrase - maximum recall baseline"
        ))
        
        # OR-expanded role search if title provided
        if title:
            title_lower = title.lower()
            for key, expansions in TITLE_EXPANSIONS.items():
                if key in title_lower:
                    or_clause = " OR ".join(f'"{exp}"' for exp in expansions[:5])
                    queries.append(ForensicQuery(
                        q=f'"{anchor}" AND ({or_clause})',
                        tier="0_Net",
                        logic="OR_expansion_title",
                        operators_used=["AND", "OR", "phrase"],
                        expected_noise="high",
                        forensic_value="critical",
                        rationale=f"OR-stacked title variations for '{key}'"
                    ))
                    break
        
        # Name variations if expansion required
        if analysis.expansion_required:
            variations = TokenAnalyzer.suggest_variations(anchor)
            if len(variations) > 1:
                or_names = " OR ".join(f'"{v}"' for v in variations[:4])
                queries.append(ForensicQuery(
                    q=f'({or_names})',
                    tier="0_Net",
                    logic="OR_expansion_name",
                    operators_used=["OR", "phrase"],
                    expected_noise="high",
                    forensic_value="high",
                    rationale="OR-stacked name variations"
                ))
        
        return queries
    
    def _tier1_intersect(self, anchor: str, pivot: Optional[str],
                         company: Optional[str], location: Optional[str]) -> List[ForensicQuery]:
        """Tier 1: Minimal AND intersection"""
        queries = []
        
        if pivot:
            queries.append(ForensicQuery(
                q=f'"{anchor}" AND {pivot}',
                tier="1_Intersect",
                logic="AND_intersection",
                operators_used=["AND", "phrase"],
                expected_noise="medium",
                forensic_value="high",
                rationale="Anchor + pivot loose AND intersection"
            ))
        
        if company:
            queries.append(ForensicQuery(
                q=f'"{anchor}" AND "{company}"',
                tier="1_Intersect",
                logic="AND_intersection",
                operators_used=["AND", "phrase"],
                expected_noise="medium",
                forensic_value="high",
                rationale="Anchor + company intersection"
            ))
            
            # Triple intersection
            if pivot:
                queries.append(ForensicQuery(
                    q=f'"{anchor}" AND "{company}" AND {pivot}',
                    tier="1_Intersect",
                    logic="triple_AND",
                    operators_used=["AND", "phrase"],
                    expected_noise="low",
                    forensic_value="high",
                    rationale="Triple intersection - anchor + company + pivot"
                ))
        
        if location:
            queries.append(ForensicQuery(
                q=f'"{anchor}" AND {location}',
                tier="1_Intersect",
                logic="AND_intersection",
                operators_used=["AND", "phrase"],
                expected_noise="medium",
                forensic_value="medium",
                rationale="Anchor + location intersection"
            ))
        
        return queries
    
    def _tier2_phrase(self, anchor: str, pivot: Optional[str],
                      title: Optional[str], company: Optional[str]) -> List[ForensicQuery]:
        """Tier 2: Exact phrase matches"""
        queries = []
        
        if title:
            queries.append(ForensicQuery(
                q=f'"{anchor}" "{title}"',
                tier="2_Phrase",
                logic="phrase_match",
                operators_used=["phrase"],
                expected_noise="low",
                forensic_value="medium",
                rationale="Exact anchor + title phrase match"
            ))
        
        if company:
            queries.append(ForensicQuery(
                q=f'"{anchor}" "{company}"',
                tier="2_Phrase",
                logic="phrase_match",
                operators_used=["phrase"],
                expected_noise="low",
                forensic_value="medium",
                rationale="Exact anchor + company phrase match"
            ))
        
        # Proximity search
        if pivot:
            queries.append(ForensicQuery(
                q=f'"{anchor}" AROUND(5) "{pivot}"' if pivot else f'"{anchor}"',
                tier="2_Phrase",
                logic="proximity",
                operators_used=["AROUND()"],
                expected_noise="low",
                forensic_value="medium",
                rationale="Proximity search - terms within 5 words"
            ))
        
        return queries
    
    def _tier3_filter(self, anchor: str, pivot: Optional[str]) -> List[ForensicQuery]:
        """Tier 3: Authority exclusion filters"""
        queries = []
        
        # Main exclusions
        main_exclusions = " ".join(f"-site:{d}" for d in HIGH_AUTHORITY_DOMAINS[:8])
        
        queries.append(ForensicQuery(
            q=f'"{anchor}" {main_exclusions}',
            tier="3_Filter",
            logic="authority_exclusion",
            operators_used=["-site:"],
            expected_noise="medium",
            forensic_value="high",
            rationale="Anchor with high-authority domain exclusions"
        ))
        
        # Social media exclusion only
        social_exclusions = "-site:linkedin.com -site:facebook.com -site:twitter.com -site:instagram.com"
        queries.append(ForensicQuery(
            q=f'"{anchor}" {social_exclusions}',
            tier="3_Filter",
            logic="social_exclusion",
            operators_used=["-site:"],
            expected_noise="medium",
            forensic_value="high",
            rationale="Anchor excluding social media platforms"
        ))
        
        # News exclusion
        news_exclusions = "-site:nytimes.com -site:bbc.com -site:cnn.com -site:reuters.com -site:bloomberg.com"
        if pivot:
            queries.append(ForensicQuery(
                q=f'"{anchor}" AND {pivot} {news_exclusions}',
                tier="3_Filter",
                logic="news_exclusion",
                operators_used=["AND", "-site:"],
                expected_noise="low",
                forensic_value="high",
                rationale="Intersection with news source exclusions"
            ))
        
        return queries
    
    def _tier4_artifact_mandatory(self, anchor: str, pivot: Optional[str]) -> List[ForensicQuery]:
        """Tier 4: MANDATORY artifact hunt - filetype and inurl"""
        queries = []
        
        # MANDATORY: filetype:pdf
        queries.append(ForensicQuery(
            q=f'"{anchor}" filetype:pdf',
            tier="4_Artifact",
            logic="filetype_forcing",
            operators_used=["filetype:pdf"],
            expected_noise="low",
            forensic_value="critical",
            rationale="MANDATORY: PDF search - documents contain detailed intel"
        ))
        
        # MANDATORY: spreadsheets
        queries.append(ForensicQuery(
            q=f'"{anchor}" (filetype:xls OR filetype:xlsx OR filetype:csv)',
            tier="4_Artifact",
            logic="filetype_forcing",
            operators_used=["filetype:xls", "filetype:xlsx", "filetype:csv"],
            expected_noise="low",
            forensic_value="critical",
            rationale="MANDATORY: Spreadsheet search - raw data sources"
        ))
        
        # MANDATORY: Word documents
        queries.append(ForensicQuery(
            q=f'"{anchor}" (filetype:doc OR filetype:docx)',
            tier="4_Artifact",
            logic="filetype_forcing",
            operators_used=["filetype:doc", "filetype:docx"],
            expected_noise="low",
            forensic_value="high",
            rationale="MANDATORY: Word document search"
        ))
        
        # MANDATORY: inurl variations
        inurl_terms = ["directory", "staff", "team", "members", "about", "people", "leadership"]
        for term in inurl_terms[:4]:
            queries.append(ForensicQuery(
                q=f'"{anchor}" inurl:{term}',
                tier="4_Artifact",
                logic="inurl_forcing",
                operators_used=[f"inurl:{term}"],
                expected_noise="low",
                forensic_value="high",
                rationale=f"MANDATORY: inurl:{term} - functional page targeting"
            ))
        
        # Combined artifacts
        queries.append(ForensicQuery(
            q=f'"{anchor}" filetype:pdf inurl:directory',
            tier="4_Artifact",
            logic="combined_artifact",
            operators_used=["filetype:pdf", "inurl:directory"],
            expected_noise="low",
            forensic_value="critical",
            rationale="Combined PDF + directory - maximum forensic value"
        ))
        
        queries.append(ForensicQuery(
            q=f'"{anchor}" filetype:pdf site:gov',
            tier="4_Artifact",
            logic="gov_pdf",
            operators_used=["filetype:pdf", "site:gov"],
            expected_noise="low",
            forensic_value="critical",
            rationale="Government PDF search - official records"
        ))
        
        return queries
    
    def _tier5_timemachine_mandatory(self, anchor: str, pivot: Optional[str]) -> List[ForensicQuery]:
        """Tier 5: MANDATORY temporal searches"""
        queries = []
        current_year = datetime.now().year
        
        # MANDATORY: Historical searches
        queries.append(ForensicQuery(
            q=f'"{anchor}" before:{current_year - 5}-01-01',
            tier="5_TimeMachine",
            logic="temporal_before",
            operators_used=["before:"],
            expected_noise="variable",
            forensic_value="critical",
            rationale="MANDATORY: Historical search (5+ years ago) - less curated content"
        ))
        
        queries.append(ForensicQuery(
            q=f'"{anchor}" before:{current_year - 10}-01-01',
            tier="5_TimeMachine",
            logic="temporal_before_deep",
            operators_used=["before:"],
            expected_noise="variable",
            forensic_value="critical",
            rationale="MANDATORY: Deep historical search (10+ years ago)"
        ))
        
        # MANDATORY: Date range
        queries.append(ForensicQuery(
            q=f'"{anchor}" after:{current_year - 10}-01-01 before:{current_year - 5}-01-01',
            tier="5_TimeMachine",
            logic="temporal_range",
            operators_used=["after:", "before:"],
            expected_noise="variable",
            forensic_value="high",
            rationale="MANDATORY: Specific time window search"
        ))
        
        # MANDATORY: Archive.org
        queries.append(ForensicQuery(
            q=f'site:web.archive.org "{anchor}"',
            tier="5_TimeMachine",
            logic="archive_wayback",
            operators_used=["site:web.archive.org"],
            expected_noise="low",
            forensic_value="critical",
            rationale="MANDATORY: Wayback Machine - deleted/changed content"
        ))
        
        queries.append(ForensicQuery(
            q=f'site:archive.org "{anchor}" filetype:pdf',
            tier="5_TimeMachine",
            logic="archive_pdf",
            operators_used=["site:archive.org", "filetype:pdf"],
            expected_noise="low",
            forensic_value="critical",
            rationale="MANDATORY: Archive.org PDF search"
        ))
        
        return queries
    
    def _tier6_exclusion(self, anchor: str, pivot: Optional[str],
                         negative_fingerprints: List[str]) -> List[ForensicQuery]:
        """Tier 6: Negative fingerprint exclusions"""
        queries = []
        
        if negative_fingerprints:
            # Single query with all exclusions
            exclusions = " ".join(f'-"{term}"' for term in negative_fingerprints[:5])
            queries.append(ForensicQuery(
                q=f'"{anchor}" {exclusions}',
                tier="6_Exclusion",
                logic="negative_fingerprint",
                operators_used=[f"-\"{t}\"" for t in negative_fingerprints[:5]],
                expected_noise="low",
                forensic_value="high",
                rationale=f"Negative fingerprinting: excluding false positive markers"
            ))
            
            # Separate queries for risky exclusions
            if len(negative_fingerprints) > 3:
                for term in negative_fingerprints[:3]:
                    queries.append(ForensicQuery(
                        q=f'"{anchor}" -"{term}"',
                        tier="6_Exclusion",
                        logic="single_exclusion",
                        operators_used=[f"-\"{term}\""],
                        expected_noise="medium",
                        forensic_value="medium",
                        rationale=f"Single exclusion: -{term} (safer than combined)"
                    ))
        
        return queries


# =============================================================================
# FORENSIC SCORER
# =============================================================================

class ForensicScorer:
    """Inverted authority scoring with depth priority"""
    
    # Base scores by source type
    SOURCE_SCORES = {
        SourceType.FORUM: 90,
        SourceType.PDF: 95,
        SourceType.SPREADSHEET: 95,
        SourceType.PERSONAL_BLOG: 85,
        SourceType.DIRECTORY: 88,
        SourceType.LOCAL_NEWS: 75,
        SourceType.TRADE_PUB: 70,
        SourceType.CORPORATE: 60,
        SourceType.LINKEDIN: 40,
        SourceType.MAJOR_NEWS: 25,
        SourceType.WIKIPEDIA: 15,
        SourceType.UNKNOWN: 50
    }
    
    # Depth bonuses (page 1 is PENALIZED)
    DEPTH_BONUSES = {
        "page_1": -20,
        "page_2": 0,
        "page_3": 10,
        "page_4_plus": 20,
        "artifact_only": 25,
        "archive": 25,
        "unknown": 5
    }
    
    @classmethod
    def score(cls, url: str, source_type: SourceType, page_position: str,
              is_authentic: bool) -> ScoreBreakdown:
        """Calculate forensic score with full breakdown"""
        
        if not is_authentic:
            return ScoreBreakdown(
                base_score=0, depth_bonus=0, domain_modifier=0,
                low_authority_bonus=0, authenticity_penalty=-100, total=0
            )
        
        base = cls.SOURCE_SCORES.get(source_type, 50)
        depth = cls._get_depth_bonus(page_position)
        domain_mod = cls._get_domain_modifier(url)
        low_auth = cls._get_low_authority_bonus(url)
        
        total = max(0, min(100, base + depth + domain_mod + low_auth))
        
        return ScoreBreakdown(
            base_score=base,
            depth_bonus=depth,
            domain_modifier=domain_mod,
            low_authority_bonus=low_auth,
            authenticity_penalty=0,
            total=total
        )
    
    @classmethod
    def _get_depth_bonus(cls, position: str) -> int:
        pos_lower = position.lower()
        
        if any(x in pos_lower for x in ["1-10", "page 1", "top 10"]):
            return cls.DEPTH_BONUSES["page_1"]
        elif any(x in pos_lower for x in ["11-20", "page 2"]):
            return cls.DEPTH_BONUSES["page_2"]
        elif any(x in pos_lower for x in ["21-30", "page 3"]):
            return cls.DEPTH_BONUSES["page_3"]
        elif any(x in pos_lower for x in ["31", "page 4", "4+", "deep"]):
            return cls.DEPTH_BONUSES["page_4_plus"]
        elif "artifact" in pos_lower or "filetype" in pos_lower:
            return cls.DEPTH_BONUSES["artifact_only"]
        elif "archive" in pos_lower:
            return cls.DEPTH_BONUSES["archive"]
        
        return cls.DEPTH_BONUSES["unknown"]
    
    @classmethod
    def _get_domain_modifier(cls, url: str) -> int:
        url_lower = url.lower()
        
        for domain in HIGH_AUTHORITY_DOMAINS:
            if domain in url_lower:
                return -25
        
        return 0
    
    @classmethod
    def _get_low_authority_bonus(cls, url: str) -> int:
        url_lower = url.lower()
        bonus = 0
        
        for tld in LOW_AUTHORITY_TLDS:
            if tld in url_lower:
                bonus += 8
        
        indicators = ["forum", "community", "board", "discussion", "blog", "personal"]
        for ind in indicators:
            if ind in url_lower:
                bonus += 10
        
        if "archive.org" in url_lower or "web.archive.org" in url_lower:
            bonus += 20
        
        return min(bonus, 30)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def analyze_target(target: str) -> TokenAnalysis:
    """Quick analysis of target uniqueness"""
    return TokenAnalyzer.analyze(target)

def build_queries(
    target: str,
    pivot: Optional[str] = None,
    company: Optional[str] = None,
    title: Optional[str] = None,
    location: Optional[str] = None,
    negative_fingerprints: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Build comprehensive forensic queries"""
    builder = ForensicQueryBuilder()
    queries, analysis, probes = builder.build_all_tiers(
        anchor=target,
        pivot=pivot,
        company=company,
        title=title,
        location=location,
        negative_fingerprints=negative_fingerprints
    )
    
    return {
        "target": target,
        "analysis": {
            "uniqueness": analysis.uniqueness.value,
            "expansion_required": analysis.expansion_required,
            "strategy": analysis.recommended_strategy,
            "risk_factors": analysis.risk_factors
        },
        "probes": {
            "identity": probes.identity_probes[:5],
            "reference": probes.reference_probes,
            "context": probes.context_probes[:5],
            "exclusion": probes.exclusion_probes[:5]
        },
        "queries": [
            {
                "tier": q.tier,
                "q": q.q,
                "logic": q.logic,
                "operators": q.operators_used,
                "noise": q.expected_noise,
                "value": q.forensic_value,
                "rationale": q.rationale
            }
            for q in queries
        ],
        "total_queries": len(queries),
        "mandatory_operators_included": {
            "filetype": any("filetype:" in q.q for q in queries),
            "inurl": any("inurl:" in q.q for q in queries),
            "temporal": any("before:" in q.q or "after:" in q.q for q in queries),
            "archive": any("archive.org" in q.q for q in queries)
        }
    }

def expand_title(title: str) -> List[str]:
    """Get OR-expansion variations for a title"""
    title_lower = title.lower()
    for key, expansions in TITLE_EXPANSIONS.items():
        if key in title_lower:
            return expansions
    return [title]

def get_exclusions() -> List[str]:
    """Get high-authority domain exclusion list"""
    return HIGH_AUTHORITY_DOMAINS.copy()


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point"""
    import sys
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║        FORENSIC QUERY CONSTRUCTOR - FINAL VERSION            ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    if len(sys.argv) < 2:
        print("Usage: python forensic_query_constructor.py \"<target>\" [options]")
        print("\nOptions:")
        print("  --company <name>    Company context")
        print("  --title <role>      Job title (will be OR-expanded)")
        print("  --location <place>  Location context")
        print("  --exclude <terms>   Negative fingerprints (comma-separated)")
        print("  --export            Export to JSON file")
        print("\nExample:")
        print('  python forensic_query_constructor.py "John Smith" --company "Acme" --title "Director"')
        return
    
    target = sys.argv[1]
    
    # Parse args
    company = None
    title = None
    location = None
    exclude = None
    export = "--export" in sys.argv
    
    for i, arg in enumerate(sys.argv):
        if arg == "--company" and i + 1 < len(sys.argv):
            company = sys.argv[i + 1]
        elif arg == "--title" and i + 1 < len(sys.argv):
            title = sys.argv[i + 1]
        elif arg == "--location" and i + 1 < len(sys.argv):
            location = sys.argv[i + 1]
        elif arg == "--exclude" and i + 1 < len(sys.argv):
            exclude = sys.argv[i + 1].split(",")
    
    # Build queries
    result = build_queries(
        target=target,
        company=company,
        title=title,
        location=location,
        negative_fingerprints=exclude
    )
    
    # Display
    print(f"\n🔍 Target: {target}")
    print(f"   Uniqueness: {result['analysis']['uniqueness']}")
    print(f"   Expansion: {'Required' if result['analysis']['expansion_required'] else 'Not required'}")
    print(f"   Strategy: {result['analysis']['strategy']}")
    
    print(f"\n📋 Generated {result['total_queries']} queries")
    print("\nMandatory Operators:")
    for op, included in result['mandatory_operators_included'].items():
        status = "✓" if included else "✗"
        print(f"   {status} {op}")
    
    print("\nSample Queries by Tier:")
    tiers_shown = set()
    for q in result['queries']:
        if q['tier'] not in tiers_shown:
            tiers_shown.add(q['tier'])
            print(f"\n[{q['tier']}] {q['q'][:70]}...")
            print(f"   Logic: {q['logic']} | Value: {q['value']}")
    
    if export:
        filename = f"forensic_queries_{target.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n📄 Exported to: {filename}")


if __name__ == "__main__":
    main()