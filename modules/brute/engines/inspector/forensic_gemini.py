#!/usr/bin/env python3
"""
FORENSIC GEMINI SEARCH - FINAL INTEGRATED VERSION
==================================================
Max Recall methodology with:
- Depth-prioritized scoring (page 1 = LOW value)
- Mandatory operators (filetype, inurl, before/after)
- Authenticity validation with severe penalties
- Negative fingerprinting
- Dynamic questioning system
- Maximum output tokens
"""

import os
import json
import asyncio
import hashlib
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Set
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION - MAXIMUM TOKENS
# =============================================================================

GEMINI_MODEL = "gemini-3-pro-preview"  # Latest reasoning model
MAX_OUTPUT_TOKENS = 65536  # Maximum for comprehensive results

# =============================================================================
# MASTER PROMPT (Embedded)
# =============================================================================

FORENSIC_MASTER_PROMPT = '''SYSTEM OVERRIDE: FORENSIC SEARCH PROTOCOL ACTIVE.
Optimization Target: Max Recall & Forensic Probability.
Output Mode: MAXIMUM TOKENS - Comprehensive Discovery.
Constraint: Results on Google Page 1 are LOW VALUE - we seek what's BURIED.

## THE CORE PHILOSOPHY

You are the DETECTIVE, not the Spy.
- The Spy cares WHO is speaking (Authority)
- The Detective cares about RAW FACTS (buried witnesses)

A witness on page 47 has ZERO authority but 100% relevance.
Your job is to find page 47.

## FORENSIC SCORING (INVERTED + DEPTH PENALTY)

Base Scores:
- Forum/Community: 90 | PDF document: 95 | Personal blog: 85
- Obscure directory: 88 | Local news: 75 | Trade publication: 70
- LinkedIn: 40 | Major news: 25 | Wikipedia: 15

Depth Bonus (CRITICAL):
- Page 1 (1-10): -20 PENALTY
- Page 2 (11-20): +0
- Page 3 (21-30): +10
- Page 4+ (31+): +20
- Found via filetype/inurl only: +25

Authenticity Check:
- Hallucinated URL: SCORE = 0, EXCLUDE
- Non-resolving domain: SCORE = 0, EXCLUDE

## MANDATORY OPERATORS (ALWAYS INCLUDE)

1. filetype:pdf, filetype:xls, filetype:csv
2. inurl:directory, inurl:staff, inurl:team, inurl:admin
3. before:YYYY-MM-DD, after:YYYY-MM-DD
4. site:web.archive.org

## DYNAMIC QUESTIONING

For every query, probe:
- WHO else co-occurs? WHAT role variations?
- How ELSE referred to? (names, transliterations)
- What CONTEXT WORD appears nearby?
- What word appears in FALSE POSITIVES but NOT ours? (negative fingerprint)

## THE REDUCTION LADDER

Tier 0 (Net): "[Anchor]" AND ("[PivotA]" OR "[PivotB]")
Tier 1 (Intersect): "[Anchor]" AND [Unique Pivot]
Tier 2 (Phrase): "[Exact Full Name Title]"
Tier 3 (Filter): "[Anchor]" -site:linkedin.com -site:wikipedia.org
Tier 4 (Artifact): "[Anchor]" filetype:pdf | inurl:directory
Tier 5 (TimeMachine): "[Anchor]" before:2015 | site:web.archive.org
Tier 6 (Exclusion): "[Anchor]" -[negative_fingerprint]

## TOKEN UNIQUENESS

VERY HIGH (use alone): Unique terms like "Xylophigous"
HIGH: Uncommon surnames - minimal context
MEDIUM/LOW: Common names - aggressive OR-expansion required

## OUTPUT FORMAT

Return ONLY valid JSON with maximum results. Prioritize DEPTH over AUTHORITY.
If token-limited, show ONLY results from page 3+ or artifact searches.

{
  "meta": {...},
  "queries": [{tier, q, logic, operators_used, forensic_value, rationale}],
  "results": [{url, title, snippet, source_type, estimated_page_position, forensic_score, reasoning}]
}
'''

# =============================================================================
# ENUMS & DATACLASSES
# =============================================================================

class TokenUniqueness(Enum):
    VERY_HIGH = "very_high"  # Use alone
    HIGH = "high"            # Minimal context
    MEDIUM = "medium"        # Moderate expansion
    LOW = "low"              # Aggressive expansion
    VERY_LOW = "very_low"    # Maximum expansion + strong pivot

class QueryTier(Enum):
    T0_NET = "0_Net"
    T1_INTERSECT = "1_Intersect"
    T2_PHRASE = "2_Phrase"
    T3_FILTER = "3_Filter"
    T4_ARTIFACT = "4_Artifact"
    T5_TIMEMACHINE = "5_TimeMachine"
    T6_EXCLUSION = "6_Exclusion"

@dataclass
class ForensicQuery:
    q: str
    tier: str
    logic: str
    operators_used: List[str]
    expected_noise: str
    forensic_value: str
    rationale: str

@dataclass
class ForensicResult:
    url: str
    title: str
    snippet: str
    source_type: str
    estimated_page_position: str
    authenticity_verified: bool
    forensic_score: int
    score_breakdown: Dict[str, int]
    reasoning: str

@dataclass
class DynamicProbes:
    identity_probes: List[str]      # Who else, what role
    reference_probes: List[str]     # Name variations
    context_probes: List[str]       # Nearby words, doc types
    exclusion_probes: List[str]     # Negative fingerprints

# =============================================================================
# FORENSIC SCORING ENGINE
# =============================================================================

class ForensicScorer:
    """Inverted authority scoring with depth priority"""
    
    # Source type base scores
    SOURCE_SCORES = {
        "forum": 90,
        "pdf": 95,
        "spreadsheet": 95,
        "personal_blog": 85,
        "directory": 88,
        "local_news": 75,
        "trade_publication": 70,
        "corporate_page": 60,
        "linkedin": 40,
        "major_news": 25,
        "wikipedia": 15,
        "unknown": 50
    }
    
    # Depth bonuses (CRITICAL - page 1 is PENALIZED)
    DEPTH_BONUSES = {
        "page_1": -20,      # PENALTY
        "page_2": 0,
        "page_3": 10,
        "page_4_plus": 20,
        "artifact_only": 25,
        "archive": 25,
        "unknown": 5
    }
    
    # High authority domains to penalize
    HIGH_AUTHORITY = {
        "wikipedia.org": -30,
        "linkedin.com": -25,
        "facebook.com": -25,
        "twitter.com": -20,
        "nytimes.com": -20,
        "bbc.com": -20,
        "cnn.com": -20,
        "reuters.com": -20,
        "bloomberg.com": -15,
        "forbes.com": -15,
        "medium.com": -10,
        "quora.com": -10
    }
    
    # Low authority indicators (BONUS)
    LOW_AUTHORITY_INDICATORS = {
        ".me": 10,
        ".io": 8,
        ".info": 5,
        ".name": 10,
        ".blog": 8,
        "forum": 15,
        "community": 12,
        "board": 10,
        "archive.org": 20,
        "web.archive.org": 25,
        ".gov": 5,  # Government can be good
        ".edu": 5,  # Academic can be good
    }
    
    @classmethod
    def score(cls, url: str, source_type: str, page_position: str, 
              is_authentic: bool) -> Tuple[int, Dict[str, int]]:
        """
        Calculate forensic score with full breakdown.
        
        Returns:
            Tuple of (total_score, breakdown_dict)
        """
        if not is_authentic:
            return 0, {"authenticity_penalty": -100, "reason": "INVALID_URL"}
        
        breakdown = {}
        
        # Base score from source type
        base = cls.SOURCE_SCORES.get(source_type, 50)
        breakdown["base_score"] = base
        
        # Depth bonus/penalty
        depth_key = cls._classify_depth(page_position)
        depth_bonus = cls.DEPTH_BONUSES.get(depth_key, 0)
        breakdown["depth_bonus"] = depth_bonus
        
        # Domain modifier
        domain_mod = cls._domain_modifier(url)
        breakdown["domain_modifier"] = domain_mod
        
        # Low authority bonus
        low_auth_bonus = cls._low_authority_bonus(url)
        breakdown["low_authority_bonus"] = low_auth_bonus
        
        # Calculate total
        total = base + depth_bonus + domain_mod + low_auth_bonus
        total = max(0, min(100, total))  # Clamp 0-100
        
        return total, breakdown
    
    @classmethod
    def _classify_depth(cls, position: str) -> str:
        """Classify page position into depth category"""
        pos_lower = position.lower()
        
        if "1-10" in pos_lower or "page 1" in pos_lower or position in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]:
            return "page_1"
        elif "11-20" in pos_lower or "page 2" in pos_lower:
            return "page_2"
        elif "21-30" in pos_lower or "page 3" in pos_lower:
            return "page_3"
        elif "31" in pos_lower or "page 4" in pos_lower or "4+" in pos_lower:
            return "page_4_plus"
        elif "artifact" in pos_lower or "filetype" in pos_lower:
            return "artifact_only"
        elif "archive" in pos_lower:
            return "archive"
        else:
            return "unknown"
    
    @classmethod
    def _domain_modifier(cls, url: str) -> int:
        """Calculate domain-based modifier (penalty for high auth)"""
        url_lower = url.lower()
        
        for domain, penalty in cls.HIGH_AUTHORITY.items():
            if domain in url_lower:
                return penalty
        
        return 0
    
    @classmethod
    def _low_authority_bonus(cls, url: str) -> int:
        """Calculate bonus for low-authority indicators"""
        url_lower = url.lower()
        bonus = 0
        
        for indicator, points in cls.LOW_AUTHORITY_INDICATORS.items():
            if indicator in url_lower:
                bonus += points
        
        return min(bonus, 30)  # Cap at 30


# =============================================================================
# AUTHENTICITY VALIDATOR
# =============================================================================

class AuthenticityValidator:
    """Validate URLs to prevent hallucinations"""
    
    # Known TLDs
    VALID_TLDS = {
        '.com', '.org', '.net', '.edu', '.gov', '.io', '.co', '.me', 
        '.info', '.biz', '.us', '.uk', '.de', '.fr', '.jp', '.cn',
        '.au', '.ca', '.nl', '.ru', '.br', '.in', '.it', '.es',
        '.name', '.blog', '.site', '.online', '.xyz', '.tech'
    }
    
    # Suspicious patterns
    SUSPICIOUS_PATTERNS = [
        r'example\d+\.com',
        r'test-?site',
        r'fake-?domain',
        r'placeholder',
        r'lorem-?ipsum',
        r'\d{10,}\.com',  # Too many numbers
    ]
    
    @classmethod
    def validate(cls, url: str) -> Tuple[bool, str]:
        """
        Validate URL authenticity.
        
        Returns:
            Tuple of (is_valid, reason)
        """
        if not url:
            return False, "Empty URL"
        
        # Basic URL structure
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception:
            return False, "Invalid URL structure"
        
        # Must have scheme and netloc
        if not parsed.scheme or not parsed.netloc:
            return False, "Missing scheme or domain"
        
        # Check scheme
        if parsed.scheme not in ['http', 'https']:
            return False, f"Invalid scheme: {parsed.scheme}"
        
        # Check for valid TLD
        domain = parsed.netloc.lower()
        has_valid_tld = any(domain.endswith(tld) for tld in cls.VALID_TLDS)
        if not has_valid_tld:
            # Check for country TLDs
            if not re.search(r'\.[a-z]{2}$', domain):
                return False, f"Suspicious TLD in: {domain}"
        
        # Check suspicious patterns
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, url, re.I):
                return False, f"Suspicious pattern detected: {pattern}"
        
        # Check for reasonable domain length
        if len(domain) > 100:
            return False, "Domain too long"
        
        # Check for hallucination patterns
        if cls._looks_hallucinated(url):
            return False, "Appears to be hallucinated"
        
        return True, "Valid"
    
    @classmethod
    def _looks_hallucinated(cls, url: str) -> bool:
        """Detect common hallucination patterns"""
        url_lower = url.lower()
        
        # Too perfect/generic
        generic_patterns = [
            'official-website.com',
            'company-directory.com',
            'person-database.com',
            'information-portal',
        ]
        
        for pattern in generic_patterns:
            if pattern in url_lower:
                return True
        
        # Unrealistic subdomain chains
        if url_lower.count('.') > 5:
            return True
        
        # Check for excessive hyphens in domain
        domain = urllib.parse.urlparse(url).netloc
        if domain.count('-') > 4:
            return True
        
        return False


# =============================================================================
# DYNAMIC QUESTIONING ENGINE
# =============================================================================

class DynamicQuestioner:
    """Generate probing questions for comprehensive query coverage"""
    
    # Role variations for OR-stacking
    ROLE_EXPANSIONS = {
        "director": ["Director", "Head of", "Chief", "VP", "Vice President", "Lead", "Senior Manager"],
        "manager": ["Manager", "Head", "Lead", "Supervisor", "Coordinator", "Administrator"],
        "ceo": ["CEO", "Chief Executive", "Managing Director", "President", "Founder", "Chairman"],
        "cfo": ["CFO", "Chief Financial Officer", "Finance Director", "Treasurer", "Controller"],
        "cto": ["CTO", "Chief Technology Officer", "Tech Lead", "VP Engineering", "Head of Tech"],
        "engineer": ["Engineer", "Developer", "Programmer", "Architect", "Technical Lead", "SWE"],
        "consultant": ["Consultant", "Advisor", "Adviser", "Specialist", "Expert", "Freelance"],
        "analyst": ["Analyst", "Researcher", "Investigator", "Examiner", "Associate"],
        "partner": ["Partner", "Managing Partner", "Senior Partner", "Principal", "Associate Partner"],
    }
    
    # Common name variations by culture
    NAME_PATTERNS = {
        "western": ["First Last", "F. Last", "First M. Last", "Last, First"],
        "eastern": ["Last First", "LAST First", "First LAST"],
        "hispanic": ["First Last1 Last2", "First Last1-Last2"],
    }
    
    @classmethod
    def generate_probes(cls, anchor: str, pivot: Optional[str] = None, 
                        context: Optional[str] = None) -> DynamicProbes:
        """Generate comprehensive probing questions"""
        
        identity = cls._identity_probes(anchor, pivot)
        reference = cls._reference_probes(anchor)
        context_probes = cls._context_probes(anchor, pivot, context)
        exclusion = cls._exclusion_probes(anchor)
        
        return DynamicProbes(
            identity_probes=identity,
            reference_probes=reference,
            context_probes=context_probes,
            exclusion_probes=exclusion
        )
    
    @classmethod
    def _identity_probes(cls, anchor: str, pivot: Optional[str]) -> List[str]:
        """Who else? What role?"""
        probes = []
        
        # Role expansion if pivot looks like a title
        if pivot:
            pivot_lower = pivot.lower()
            for key, expansions in cls.ROLE_EXPANSIONS.items():
                if key in pivot_lower:
                    probes.extend(expansions)
        
        # Common co-occurrence questions
        probes.extend([
            f"Who works with {anchor}?",
            f"What organization is {anchor} part of?",
            f"What events feature {anchor}?"
        ])
        
        return probes[:10]
    
    @classmethod
    def _reference_probes(cls, anchor: str) -> List[str]:
        """How else referred to?"""
        probes = []
        words = anchor.split()
        
        if len(words) >= 2:
            # Name variations
            first, last = words[0], words[-1]
            
            # Initials
            probes.append(f"{first[0]}. {last}")
            
            # Reversed
            probes.append(f"{last}, {first}")
            probes.append(f"{last} {first}")
            
            # Last name only
            probes.append(last)
            
            # With middle initial placeholder
            if len(words) == 2:
                probes.append(f"{first} ?. {last}")
        
        return probes
    
    @classmethod
    def _context_probes(cls, anchor: str, pivot: Optional[str], 
                        context: Optional[str]) -> List[str]:
        """What words appear nearby?"""
        probes = []
        
        # Document types
        probes.extend([
            "annual report",
            "press release", 
            "meeting minutes",
            "conference proceedings",
            "court filing",
            "regulatory submission",
            "directory listing",
            "membership list",
            "staff page",
            "about us"
        ])
        
        # If we have context, extract key terms
        if context:
            # Simple keyword extraction
            words = re.findall(r'\b[A-Za-z]{4,}\b', context)
            unique_words = list(set(words))[:5]
            probes.extend(unique_words)
        
        return probes
    
    @classmethod
    def _exclusion_probes(cls, anchor: str) -> List[str]:
        """What words appear in false positives but not ours?"""
        exclusions = []
        
        anchor_lower = anchor.lower()
        
        # Common false positive patterns
        if "apple" in anchor_lower:
            exclusions.extend(["iPhone", "Mac", "iOS", "Cupertino", "Tim Cook"])
        
        if "amazon" in anchor_lower:
            exclusions.extend(["AWS", "Bezos", "Prime", "ecommerce", "Seattle"])
        
        if "jaguar" in anchor_lower:
            exclusions.extend(["car", "vehicle", "automotive", "feline", "animal", "XJ"])
        
        if "python" in anchor_lower:
            exclusions.extend(["programming", "code", "snake", "reptile"])
        
        if "mercury" in anchor_lower:
            exclusions.extend(["planet", "element", "thermometer", "Ford"])
        
        # General exclusions for people searches
        if len(anchor.split()) >= 2:  # Looks like a name
            exclusions.extend([
                "celebrity", "actor", "actress", "singer", "athlete",
                "obituary", "death", "died"  # Unless specifically searching for these
            ])
        
        return exclusions


# =============================================================================
# QUERY BUILDER WITH MANDATORY OPERATORS
# =============================================================================

class ForensicQueryBuilder:
    """Build queries with mandatory operators and dynamic probes"""
    
    # Mandatory operators - ALWAYS include queries with these
    MANDATORY_FILETYPES = ["pdf", "xls", "xlsx", "csv", "doc", "docx"]
    MANDATORY_INURL = ["directory", "staff", "team", "about", "members", "list", "admin"]
    
    # Authority exclusions
    AUTHORITY_EXCLUSIONS = [
        "linkedin.com", "wikipedia.org", "facebook.com", "twitter.com",
        "instagram.com", "youtube.com", "nytimes.com", "bbc.com",
        "cnn.com", "reuters.com", "bloomberg.com", "forbes.com"
    ]
    
    def __init__(self):
        self.questioner = DynamicQuestioner()
        self.validator = AuthenticityValidator()
        self.scorer = ForensicScorer()
    
    def build_comprehensive_queries(
        self,
        anchor: str,
        pivot: Optional[str] = None,
        company: Optional[str] = None,
        title: Optional[str] = None,
        location: Optional[str] = None,
        context: Optional[str] = None,
        negative_fingerprints: Optional[List[str]] = None
    ) -> Tuple[List[ForensicQuery], DynamicProbes]:
        """
        Build comprehensive query set with all mandatory operators.
        
        Returns:
            Tuple of (queries, probes_applied)
        """
        queries = []
        
        # Generate dynamic probes
        probes = self.questioner.generate_probes(anchor, pivot, context)
        
        # Auto-detect negative fingerprints if not provided
        if not negative_fingerprints:
            negative_fingerprints = probes.exclusion_probes[:3]
        
        # === TIER 0: THE NET ===
        queries.extend(self._build_tier0(anchor, pivot, title, probes))
        
        # === TIER 1: INTERSECTION ===
        queries.extend(self._build_tier1(anchor, pivot, company, location))
        
        # === TIER 2: PHRASE ===
        queries.extend(self._build_tier2(anchor, pivot, title, company))
        
        # === TIER 3: FILTER ===
        queries.extend(self._build_tier3(anchor, pivot))
        
        # === TIER 4: ARTIFACT HUNT (MANDATORY) ===
        queries.extend(self._build_tier4_mandatory(anchor, pivot))
        
        # === TIER 5: TIME MACHINE (MANDATORY) ===
        queries.extend(self._build_tier5_mandatory(anchor, pivot))
        
        # === TIER 6: EXCLUSION ===
        queries.extend(self._build_tier6(anchor, pivot, negative_fingerprints))
        
        return queries, probes
    
    def _build_tier0(self, anchor: str, pivot: Optional[str], 
                     title: Optional[str], probes: DynamicProbes) -> List[ForensicQuery]:
        """Tier 0: Maximum expansion with OR-stacking"""
        queries = []
        
        # Get role variations
        role_variations = []
        if title:
            title_lower = title.lower()
            for key, expansions in DynamicQuestioner.ROLE_EXPANSIONS.items():
                if key in title_lower:
                    role_variations = expansions[:5]
                    break
        
        if role_variations:
            or_clause = " OR ".join(f'"{r}"' for r in role_variations)
            queries.append(ForensicQuery(
                q=f'"{anchor}" AND ({or_clause})',
                tier="0_Net",
                logic="OR_expansion",
                operators_used=["AND", "OR", "phrase"],
                expected_noise="high",
                forensic_value="critical",
                rationale=f"Maximum expansion: anchor + OR-stacked role variations"
            ))
        
        # Basic anchor search
        queries.append(ForensicQuery(
            q=f'"{anchor}"',
            tier="0_Net",
            logic="phrase_anchor",
            operators_used=["phrase"],
            expected_noise="high",
            forensic_value="critical",
            rationale="Raw anchor phrase search"
        ))
        
        return queries
    
    def _build_tier1(self, anchor: str, pivot: Optional[str],
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
                rationale="Anchor + pivot intersection"
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
    
    def _build_tier2(self, anchor: str, pivot: Optional[str],
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
                rationale="Exact anchor + title phrase"
            ))
        
        if company and title:
            queries.append(ForensicQuery(
                q=f'"{anchor}" "{title}" "{company}"',
                tier="2_Phrase",
                logic="phrase_match",
                operators_used=["phrase"],
                expected_noise="low",
                forensic_value="medium",
                rationale="Triple phrase - maximum precision"
            ))
        
        return queries
    
    def _build_tier3(self, anchor: str, pivot: Optional[str]) -> List[ForensicQuery]:
        """Tier 3: Authority exclusion"""
        queries = []
        
        # Build exclusion string
        exclusions = " ".join(f"-site:{d}" for d in self.AUTHORITY_EXCLUSIONS[:6])
        
        queries.append(ForensicQuery(
            q=f'"{anchor}" {exclusions}',
            tier="3_Filter",
            logic="authority_exclusion",
            operators_used=["-site:"],
            expected_noise="medium",
            forensic_value="high",
            rationale="Anchor with high-authority exclusions"
        ))
        
        if pivot:
            queries.append(ForensicQuery(
                q=f'"{anchor}" AND {pivot} {exclusions}',
                tier="3_Filter",
                logic="authority_exclusion",
                operators_used=["AND", "-site:"],
                expected_noise="low",
                forensic_value="high",
                rationale="Intersection with authority exclusions"
            ))
        
        return queries
    
    def _build_tier4_mandatory(self, anchor: str, pivot: Optional[str]) -> List[ForensicQuery]:
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
            rationale="MANDATORY: PDF documents often contain detailed intel"
        ))
        
        # MANDATORY: filetype:xls/xlsx/csv
        queries.append(ForensicQuery(
            q=f'"{anchor}" (filetype:xls OR filetype:xlsx OR filetype:csv)',
            tier="4_Artifact",
            logic="filetype_forcing",
            operators_used=["filetype:xls", "filetype:xlsx", "filetype:csv"],
            expected_noise="low",
            forensic_value="critical",
            rationale="MANDATORY: Spreadsheets contain raw data"
        ))
        
        # MANDATORY: inurl variations
        for inurl_term in ["directory", "staff", "team", "members"]:
            queries.append(ForensicQuery(
                q=f'"{anchor}" inurl:{inurl_term}',
                tier="4_Artifact",
                logic="inurl_forcing",
                operators_used=[f"inurl:{inurl_term}"],
                expected_noise="low",
                forensic_value="high",
                rationale=f"MANDATORY: inurl:{inurl_term} targets functional pages"
            ))
        
        # Combined filetype + inurl
        queries.append(ForensicQuery(
            q=f'"{anchor}" filetype:pdf inurl:directory',
            tier="4_Artifact",
            logic="combined_artifact",
            operators_used=["filetype:pdf", "inurl:directory"],
            expected_noise="low",
            forensic_value="critical",
            rationale="Combined artifact search - highest forensic value"
        ))
        
        return queries
    
    def _build_tier5_mandatory(self, anchor: str, pivot: Optional[str]) -> List[ForensicQuery]:
        """Tier 5: MANDATORY time machine - before/after and archives"""
        queries = []
        
        # MANDATORY: Historical search
        queries.append(ForensicQuery(
            q=f'"{anchor}" before:2020-01-01',
            tier="5_TimeMachine",
            logic="temporal_forcing",
            operators_used=["before:"],
            expected_noise="variable",
            forensic_value="critical",
            rationale="MANDATORY: Historical content is less curated"
        ))
        
        queries.append(ForensicQuery(
            q=f'"{anchor}" before:2015-01-01',
            tier="5_TimeMachine",
            logic="temporal_forcing",
            operators_used=["before:"],
            expected_noise="variable",
            forensic_value="critical",
            rationale="MANDATORY: Deep historical search"
        ))
        
        # MANDATORY: Date range
        queries.append(ForensicQuery(
            q=f'"{anchor}" after:2010-01-01 before:2018-01-01',
            tier="5_TimeMachine",
            logic="temporal_forcing",
            operators_used=["after:", "before:"],
            expected_noise="variable",
            forensic_value="high",
            rationale="MANDATORY: Specific time window"
        ))
        
        # MANDATORY: Archive.org
        queries.append(ForensicQuery(
            q=f'site:web.archive.org "{anchor}"',
            tier="5_TimeMachine",
            logic="archive",
            operators_used=["site:web.archive.org"],
            expected_noise="low",
            forensic_value="critical",
            rationale="MANDATORY: Wayback Machine catches deleted content"
        ))
        
        queries.append(ForensicQuery(
            q=f'site:archive.org "{anchor}" filetype:pdf',
            tier="5_TimeMachine",
            logic="archive",
            operators_used=["site:archive.org", "filetype:pdf"],
            expected_noise="low",
            forensic_value="critical",
            rationale="MANDATORY: Archive.org PDF search"
        ))
        
        return queries
    
    def _build_tier6(self, anchor: str, pivot: Optional[str],
                     negative_fingerprints: List[str]) -> List[ForensicQuery]:
        """Tier 6: Exclusion based on negative fingerprints"""
        queries = []
        
        if negative_fingerprints:
            exclusions = " ".join(f"-{term}" for term in negative_fingerprints[:5])
            queries.append(ForensicQuery(
                q=f'"{anchor}" {exclusions}',
                tier="6_Exclusion",
                logic="negative_fingerprint",
                operators_used=[f"-{t}" for t in negative_fingerprints[:5]],
                expected_noise="low",
                forensic_value="high",
                rationale=f"Negative fingerprinting: exclude false positive markers"
            ))
        
        return queries


# =============================================================================
# GEMINI CLIENT WITH MAX TOKENS
# =============================================================================

class ForensicGeminiClient:
    """Gemini client optimized for forensic search with maximum tokens"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY required")
        
        self._init_client()
    
    def _init_client(self):
        """Initialize Gemini with max token configuration"""
        try:
            from google import genai
            from google.genai import types
            self.genai = genai
            self.types = types
            self.client = genai.Client(api_key=self.api_key)
            logger.info("✓ Gemini client initialized with max tokens config")
        except ImportError:
            raise ImportError("pip install google-generativeai")
    
    async def generate_queries(
        self,
        target: str,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate forensic queries using Gemini with max tokens"""
        
        user_prompt = f"""INVESTIGATION TARGET: {target}

{f"ADDITIONAL CONTEXT: {context}" if context else ""}

Execute the Forensic Search Protocol:
1. Analyze anchor uniqueness
2. Generate dynamic probes (identity/reference/context/exclusion)
3. Build queries for ALL 6 tiers (mandatory operators required)
4. Ensure filetype:pdf, inurl:, before:/after: are included
5. Apply negative fingerprinting
6. Output maximum results, prioritizing DEPTH over AUTHORITY

If token-limited, show ONLY results from page 3+ or artifact searches."""

        try:
            config = self.types.GenerateContentConfig(
                temperature=0.3,  # Deterministic for forensic work
                max_output_tokens=MAX_OUTPUT_TOKENS,  # MAXIMUM
                thinking_config=self.types.ThinkingConfig(
                    thinking_level="HIGH"
                )
            )
            
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    {"role": "user", "parts": [{"text": FORENSIC_MASTER_PROMPT}]},
                    {"role": "model", "parts": [{"text": "FORENSIC PROTOCOL ACTIVE. Operating as Detective. Optimizing for Max Recall with depth priority. Page 1 results will be penalized. Mandatory operators (filetype:pdf, inurl:, before:/after:) will be included. Ready for target."}]},
                    {"role": "user", "parts": [{"text": user_prompt}]}
                ],
                config=config
            )
            
            result_text = response.text
            
            # Parse JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            
            return json.loads(result_text.strip())
            
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return self._fallback_response(target)
    
    async def execute_grounded_search(
        self,
        query: str
    ) -> Dict[str, Any]:
        """
        Execute a single query with Google Search Grounding.
        This ACTUALLY runs the search and returns real URLs.
        """
        try:
            import requests

            # Use grounding config
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",  # Flash is better for grounded search
                contents=query,
                config={"tools": [{"google_search": {}}]}
            )

            urls = []
            snippets = []

            if response.candidates and response.candidates[0].grounding_metadata:
                metadata = response.candidates[0].grounding_metadata
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    for chunk in metadata.grounding_chunks:
                        if hasattr(chunk, 'web') and hasattr(chunk.web, 'uri'):
                            url = chunk.web.uri
                            # Resolve redirects
                            try:
                                resp = requests.head(url, allow_redirects=True, timeout=5)
                                url = resp.url
                            except Exception as e:

                                print(f"[BRUTE] Error: {e}")

                                pass

                            if url not in urls:
                                urls.append(url)
                                title = getattr(chunk.web, 'title', '') if hasattr(chunk.web, 'title') else ''
                                snippets.append({
                                    "url": url,
                                    "title": title
                                })

            return {
                "query": query,
                "urls": urls,
                "results": snippets,
                "count": len(urls),
                "grounded": True,
                "response_text": response.text if response.text else ""
            }

        except Exception as e:
            logger.error(f"Grounded search error for '{query}': {e}")
            return {
                "query": query,
                "urls": [],
                "results": [],
                "count": 0,
                "grounded": False,
                "error": str(e)
            }

    async def execute_forensic_investigation(
        self,
        target: str,
        context: Optional[str] = None,
        max_queries: int = 20
    ) -> Dict[str, Any]:
        """
        Full forensic investigation: generate queries AND execute them with grounding.

        This is the method that actually RUNS searches, not just generates queries.
        """
        logger.info(f"Starting forensic investigation for: {target}")

        # Step 1: Generate forensic queries
        builder = ForensicQueryBuilder()
        queries, probes = builder.build_comprehensive_queries(anchor=target)

        # Step 2: Execute each query with grounding
        all_results = []
        all_urls = set()

        # Prioritize high-value queries
        priority_queries = [q for q in queries if q.forensic_value in ["critical", "high"]][:max_queries]

        logger.info(f"Executing {len(priority_queries)} priority queries with Google Search Grounding...")

        for i, fq in enumerate(priority_queries):
            logger.info(f"[{i+1}/{len(priority_queries)}] {fq.tier}: {fq.q[:60]}...")

            result = await self.execute_grounded_search(fq.q)
            result["tier"] = fq.tier
            result["forensic_value"] = fq.forensic_value
            result["rationale"] = fq.rationale

            # Track unique URLs
            new_urls = [u for u in result.get("urls", []) if u not in all_urls]
            all_urls.update(new_urls)
            result["new_urls"] = new_urls

            all_results.append(result)

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        # Step 3: Compile results
        return {
            "meta": {
                "target": target,
                "strategy": "forensic_grounded_investigation",
                "queries_executed": len(priority_queries),
                "total_unique_urls": len(all_urls),
                "grounding_enabled": True
            },
            "probes_applied": {
                "identity": probes.identity_probes[:5],
                "reference": probes.reference_probes[:5],
                "context": probes.context_probes[:5],
                "exclusion": probes.exclusion_probes[:5]
            },
            "query_results": all_results,
            "all_unique_urls": list(all_urls),
            "url_count_by_tier": self._count_urls_by_tier(all_results)
        }

    def _count_urls_by_tier(self, results: List[Dict]) -> Dict[str, int]:
        """Count URLs found per tier"""
        counts = {}
        for r in results:
            tier = r.get("tier", "unknown")
            counts[tier] = counts.get(tier, 0) + len(r.get("new_urls", []))
        return counts

    def _fallback_response(self, target: str) -> Dict[str, Any]:
        """Fallback using rule-based builder"""
        builder = ForensicQueryBuilder()
        queries, probes = builder.build_comprehensive_queries(anchor=target)

        return {
            "meta": {
                "intent": "forensic_investigation",
                "strategy": "max_recall_depth_priority",
                "anchor": target,
                "fallback_mode": True
            },
            "queries": [
                {
                    "tier": q.tier,
                    "q": q.q,
                    "logic": q.logic,
                    "operators_used": q.operators_used,
                    "forensic_value": q.forensic_value,
                    "rationale": q.rationale
                }
                for q in queries
            ]
        }


# =============================================================================
# MAIN AGENT
# =============================================================================

class ForensicSearchAgent:
    """Main forensic search agent with all integrated features"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.builder = ForensicQueryBuilder()
        self.scorer = ForensicScorer()
        self.validator = AuthenticityValidator()
        self.gemini = None
        
        if api_key or os.getenv("GOOGLE_API_KEY"):
            try:
                self.gemini = ForensicGeminiClient(api_key)
            except Exception as e:
                logger.warning(f"Gemini not available: {e}")
    
    def build_queries(
        self,
        target: str,
        pivot: Optional[str] = None,
        company: Optional[str] = None,
        title: Optional[str] = None,
        negative_fingerprints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Build comprehensive queries with all mandatory operators"""
        
        queries, probes = self.builder.build_comprehensive_queries(
            anchor=target,
            pivot=pivot,
            company=company,
            title=title,
            negative_fingerprints=negative_fingerprints
        )
        
        return {
            "meta": {
                "intent": "forensic_investigation",
                "strategy": "max_recall_depth_priority",
                "anchor": target,
                "anchor_uniqueness": self._assess_uniqueness(target),
                "negative_fingerprints": negative_fingerprints or probes.exclusion_probes[:3],
                "dynamic_probes_applied": {
                    "identity": probes.identity_probes[:5],
                    "reference": probes.reference_probes[:5],
                    "context": probes.context_probes[:5],
                    "exclusion": probes.exclusion_probes[:5]
                },
                "mandatory_operators_included": {
                    "filetype": True,
                    "inurl": True,
                    "temporal": True,
                    "archive": True
                }
            },
            "queries": [
                {
                    "tier": q.tier,
                    "q": q.q,
                    "logic": q.logic,
                    "operators_used": q.operators_used,
                    "expected_noise": q.expected_noise,
                    "forensic_value": q.forensic_value,
                    "rationale": q.rationale
                }
                for q in queries
            ],
            "total_queries": len(queries),
            "tier_distribution": self._count_tiers(queries)
        }
    
    async def investigate_ai(
        self,
        target: str,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run AI-powered investigation with Gemini (QUERY GENERATION ONLY - no actual search)"""
        if not self.gemini:
            raise ValueError("Gemini client not available")

        return await self.gemini.generate_queries(target, context)

    async def investigate_grounded(
        self,
        target: str,
        context: Optional[str] = None,
        max_queries: int = 20
    ) -> Dict[str, Any]:
        """
        Run FULL forensic investigation with Google Search Grounding.
        This actually EXECUTES searches and returns real URLs.

        Use this instead of investigate_ai() if you want actual search results.
        """
        if not self.gemini:
            raise ValueError("Gemini client not available")

        return await self.gemini.execute_forensic_investigation(target, context, max_queries)
    
    def score_result(
        self,
        url: str,
        source_type: str = "unknown",
        page_position: str = "unknown"
    ) -> Dict[str, Any]:
        """Score a result with full breakdown"""
        
        # Validate first
        is_valid, reason = self.validator.validate(url)
        
        # Score
        score, breakdown = self.scorer.score(
            url=url,
            source_type=source_type,
            page_position=page_position,
            is_authentic=is_valid
        )
        
        return {
            "url": url,
            "forensic_score": score,
            "score_breakdown": breakdown,
            "authenticity": {
                "verified": is_valid,
                "reason": reason
            },
            "recommendation": "HIGH VALUE" if score >= 70 else "MEDIUM VALUE" if score >= 40 else "LOW VALUE"
        }
    
    def _assess_uniqueness(self, anchor: str) -> str:
        """Quick uniqueness assessment"""
        words = anchor.split()
        
        # Common name lists
        common_first = {"john", "james", "michael", "david", "robert", "mary", "jennifer", "lisa"}
        common_last = {"smith", "johnson", "williams", "brown", "jones", "garcia", "miller"}
        
        if len(words) >= 2:
            first_lower = words[0].lower()
            last_lower = words[-1].lower()
            
            if first_lower in common_first and last_lower in common_last:
                return "very_low"
            elif first_lower in common_first or last_lower in common_last:
                return "low"
        
        if len(anchor) >= 10 and len(words) == 1:
            return "high"
        
        return "medium"
    
    def _count_tiers(self, queries: List[ForensicQuery]) -> Dict[str, int]:
        """Count queries by tier"""
        counts = {}
        for q in queries:
            tier = q.tier
            counts[tier] = counts.get(tier, 0) + 1
        return counts
    
    def export(self, data: Dict[str, Any], filename: Optional[str] = None) -> str:
        """Export to JSON"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"forensic_investigation_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        return filename


# =============================================================================
# CLI
# =============================================================================

async def main():
    """CLI entry point"""
    import sys
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║   FORENSIC GEMINI SEARCH - FINAL INTEGRATED VERSION          ║
║                                                              ║
║   Max Recall | Depth Priority | Mandatory Operators          ║
║   "We seek the Witness buried on page 47"                    ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    if len(sys.argv) < 2:
        print("Usage: python forensic_gemini.py \"<target>\" [options]")
        print("\nOptions:")
        print("  --company <name>    Company context")
        print("  --title <role>      Job title (will be OR-expanded)")
        print("  --exclude <terms>   Negative fingerprints (comma-separated)")
        print("  --ai                Use Gemini AI (query generation only - NO actual search)")
        print("  --grounded          Use Google Search Grounding (ACTUALLY runs searches!)")
        print("  --max-queries <n>   Max queries to execute in grounded mode (default: 20)")
        print("  --export            Export to JSON")
        print("\nExamples:")
        print('  python forensic_gemini.py "John Smith" --company "Acme Corp" --title "Director"')
        print('  python forensic_gemini.py "Xylophigous Holdings" --ai --export')
        print('  python forensic_gemini.py "John Smith" --grounded --max-queries 15')
        return

    target = sys.argv[1]

    # Parse args
    company = None
    title = None
    exclude = None
    max_queries = 20
    use_ai = "--ai" in sys.argv
    use_grounded = "--grounded" in sys.argv
    export = "--export" in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--company" and i + 1 < len(sys.argv):
            company = sys.argv[i + 1]
        elif arg == "--title" and i + 1 < len(sys.argv):
            title = sys.argv[i + 1]
        elif arg == "--exclude" and i + 1 < len(sys.argv):
            exclude = sys.argv[i + 1].split(",")
        elif arg == "--max-queries" and i + 1 < len(sys.argv):
            max_queries = int(sys.argv[i + 1])

    agent = ForensicSearchAgent()

    mode_str = "Grounded (Real Searches)" if use_grounded else ("AI (Query Gen Only)" if use_ai else "Rule-Based")
    print(f"\n🔍 Target: {target}")
    print(f"   Company: {company or 'N/A'}")
    print(f"   Title: {title or 'N/A'}")
    print(f"   Mode: {mode_str}")
    print("─" * 60)

    if use_grounded and agent.gemini:
        print(f"\n🌐 Running GROUNDED investigation (executing {max_queries} queries with Google Search)...")
        result = await agent.investigate_grounded(target, max_queries=max_queries)

        # Display grounded results
        print(f"\n✓ Executed {result['meta']['queries_executed']} queries")
        print(f"✓ Found {result['meta']['total_unique_urls']} unique URLs")

        print("\nURLs by Tier:")
        for tier, count in result.get("url_count_by_tier", {}).items():
            print(f"  {tier}: {count} URLs")

        print("\nSample URLs Found:")
        for url in result.get("all_unique_urls", [])[:15]:
            print(f"  → {url}")

    elif use_ai and agent.gemini:
        print("\n🤖 Running AI-powered query generation (NO actual search)...")
        result = await agent.investigate_ai(target)

        print(f"\n✓ Generated {len(result.get('queries', []))} queries")
        print("\nSample Queries:")
        for q in result.get("queries", [])[:10]:
            print(f"\n[{q.get('tier', 'N/A')}] {q.get('q', '')[:70]}...")

    else:
        print("\n📋 Building queries with mandatory operators...")
        result = agent.build_queries(
            target=target,
            company=company,
            title=title,
            negative_fingerprints=exclude
        )

        print(f"\n✓ Generated {result.get('total_queries', len(result.get('queries', [])))} queries")

        if "tier_distribution" in result:
            print("\nTier Distribution:")
            for tier, count in result["tier_distribution"].items():
                print(f"  {tier}: {count}")

        print("\nSample Queries:")
        for q in result.get("queries", [])[:10]:
            print(f"\n[{q['tier']}] {q['q'][:70]}...")
            print(f"   Operators: {', '.join(q.get('operators_used', []))}")
            print(f"   Value: {q.get('forensic_value', 'N/A')}")

    if export:
        filename = agent.export(result)
        print(f"\n📄 Exported to: {filename}")

    print("\n" + "═" * 60)
    print("✓ Investigation complete")


if __name__ == "__main__":
    asyncio.run(main())