"""
CC-PDF-2025 Source Configuration
================================

SINGLE FILE containing ALL rules for the cc-pdf-2025 data source.

This is ONE source among many that CYMONIDES ingests. The rules here
define how documents from CommonCrawl PDF 2025 dataset are classified
into tiers and processed.

ARCHITECTURE
------------

CYMONIDES/
├── ingest/
│   ├── __init__.py           # Ingest pipeline
│   ├── classifier.py         # Generic tier classifier
│   ├── patterns.py           # Shared pattern library
│   ├── names.py              # First name library (730k+ names)
│   ├── tripwires.py          # Red flag matching
│   └── sources/              # Source-specific configs
│       ├── cc_pdf_2025.py    # THIS FILE
│       ├── linkedin.py       # LinkedIn companies config
│       ├── wdc.py            # Web Data Commons config
│       └── ...

FUNDAMENTAL RULES
-----------------

1. EVERY URL gets indexed - NO EXCEPTIONS
2. Exclusion = demotion to Tier 3, NOT skipping
3. Content patterns ALWAYS override URL patterns
4. Red flag tripwires = automatic Tier 1 + flagged
5. Context extraction = 5 words before + 5 words after

TIER DEFINITIONS
----------------

TIER 1 (Full):
- URL + Content (full-text indexed)
- 768-dim content_embedding
- Concept extraction (themes, phenomena, red_flags)
- Temporal extraction
- Spatial extraction
- Entity extraction with 5-word context

TIER 2 (Extract):
- URL + Extracted metadata
- NO full-text keyword index
- NO embeddings stored
- Entities extracted but not embedded

TIER 3 (URL-only):
- URL + available metadata only
- No extraction
- No content stored
"""

import re
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Any


# =============================================================================
# SOURCE METADATA
# =============================================================================

SOURCE_ID = "cc-pdf-2025"
SOURCE_NAME = "CommonCrawl PDF 2025"
SOURCE_TYPE = "cc-pdf-2025"
TARGET_INDEX = "cymonides-2"


# =============================================================================
# TIER DEFINITIONS
# =============================================================================

class Tier(IntEnum):
    """Three-tier classification. Everything gets a tier. Nothing is skipped."""
    FULL = 1      # URL + Content + embeddings + all extraction
    EXTRACT = 2   # URL + extracted metadata, NO full-text/embeddings
    URL_ONLY = 3  # URL + available metadata only, no extraction


@dataclass
class TierDecision:
    """Result of tier classification."""
    tier: Tier
    reasons: List[str]
    matched_patterns: List[str] = field(default_factory=list)
    red_flag_matches: List[Dict] = field(default_factory=list)


# =============================================================================
# CONTEXT EXTRACTION
# =============================================================================

CONTEXT_WORDS_BEFORE: int = 5
CONTEXT_WORDS_AFTER: int = 5


def extract_context(text: str, match_start: int, match_end: int) -> str:
    """Extract N words before and after a match."""
    # Get words before
    before_text = text[:match_start]
    before_words = before_text.split()[-CONTEXT_WORDS_BEFORE:]

    # Get words after
    after_text = text[match_end:]
    after_words = after_text.split()[:CONTEXT_WORDS_AFTER]

    # Get the match itself
    match_text = text[match_start:match_end]

    return " ".join(before_words) + " [" + match_text + "] " + " ".join(after_words)


# =============================================================================
# ALLOWED TLDs
# =============================================================================

ALLOWED_TLDS: Set[str] = {
    # Generic
    'org', 'com',

    # European
    'fr', 'de', 'it', 'hu', 'co.uk',

    # Baltic
    'ee', 'lt', 'lv',

    # CIS Region
    'ru', 'kz', 'ua',

    # Other
    'ca',

    # Government (always include)
    'gov', 'gov.uk',
}

# EXCLUDED (academic/scientific per user spec)
EXCLUDED_TLDS: Set[str] = {'edu', 'ac.uk', 'edu.au', 'ac.at', 'edu.cn'}


# =============================================================================
# REGISTRY DOMAINS - Always Tier 1
# =============================================================================

REGISTRY_DOMAINS: Set[str] = {
    # US SEC/EDGAR
    'sec.gov', 'edgar-online.com', 'edgarfilings.com',

    # UK
    'companieshouse.gov.uk', 'find-and-update.company-information.service.gov.uk',

    # EU
    'e-justice.europa.eu',

    # Exchanges
    'nyse.com', 'nasdaq.com', 'londonstockexchange.com', 'lse.co.uk',
    'euronext.com', 'deutsche-boerse.com', 'xetra.com', 'six-group.com', 'borsaitaliana.it',

    # Country Registries
    'e-cegjegyzek.hu', 'sudregister.hrsr.sk', 'firmen.wko.at',
    'handelsregister.de', 'unternehmensregister.de',
    'infogreffe.fr', 'societe.com', 'kvk.nl', 'opencorporates.com',
    'proff.no', 'proff.se', 'proff.dk', 'bisnode.com', 'dun-bradstreet.com',

    # Offshore
    'bvicompanyregistry.vg', 'cayman.gov.ky', 'jerseyfsco.je',
    'guernseyregistry.com', 'iomcompanies.com',

    # CIS
    'egrul.nalog.ru', 'e-gov.kz',
}


# =============================================================================
# CORPORATE URL KEYWORDS - Promote to Tier 1
# =============================================================================

CORPORATE_URL_KEYWORDS: Set[str] = {
    'annual-report', 'annualreport', 'annual_report',
    'financial-statement', 'financial_statement', 'financials',
    '10-k', '10k', '20-f', '20f', '6-k', '8-k',
    'quarterly-report', 'q1', 'q2', 'q3', 'q4',
    'earnings', 'investor-relations', 'ir',
    'investor', 'shareholders', 'proxy', 'prospectus',
    'offering', 'ipo', 'bond', 'debt',
    'regulatory', 'compliance', 'filing', 'disclosure',
    'registration', 'form-', 'sec-filing',
    'agreement', 'contract', 'terms', 'bylaws',
    'articles-of', 'certificate-of', 'charter',
    'litigation', 'settlement', 'court',
    'governance', 'board', 'management', 'executive',
    'compensation', 'directors', 'officers',
    'corporate-structure', 'org-chart', 'subsidiary',
    'sustainability', 'esg', 'csr', 'environmental',
    'social-responsibility', 'climate', 'carbon',
}


# =============================================================================
# LEGAL SUFFIXES - Promote to Tier 1
# =============================================================================

LEGAL_SUFFIXES: Set[str] = {
    'ltd', 'llc', 'inc', 'corp', 'plc',
    'gmbh', 'ag', 'kg', 'ohg', 'ug',
    'sa', 'sas', 'sarl', 'srl', 'sl',
    'bv', 'nv', 'ab', 'as', 'oy', 'oyj',
    'sp', 'kft', 'zrt', 'nyrt', 'bt',
    'doo', 'dd', 'ad', 'ood', 'eood',
    'jsc', 'pjsc', 'ojsc',
}


# =============================================================================
# FREE HOSTING - Demote to Tier 3
# =============================================================================

FREE_HOSTING_PLATFORMS: Set[str] = {
    'blogspot.com', 'wordpress.com', 'wix.com', 'weebly.com',
    'squarespace.com', 'tumblr.com', 'medium.com', 'substack.com',
    'github.io', 'gitlab.io', 'netlify.app', 'vercel.app',
    'herokuapp.com', 'firebaseapp.com', 'web.app',
    'sites.google.com', 'docs.google.com',
}


# =============================================================================
# CONTENT PATTERNS - Tier 1 Triggers
# =============================================================================

# Annual Report Detection (multilingual)
ANNUAL_REPORT_PATTERNS = [
    re.compile(r'\bannual\s*report\b', re.I),
    re.compile(r'\b(?:10-K|10K|20-F|20F)\b', re.I),
    re.compile(r'\bform\s*(?:10-K|10K|20-F|20F)\b', re.I),
    re.compile(r'\byearly\s*report\b', re.I),
    re.compile(r'\bgeschäftsbericht\b', re.I),      # German
    re.compile(r'\brapport\s*annuel\b', re.I),      # French
    re.compile(r'\binforme\s*anual\b', re.I),       # Spanish
    re.compile(r'\brelazione\s*annuale\b', re.I),   # Italian
    re.compile(r'\béves\s*jelentés\b', re.I),       # Hungarian
]

# Legal Entity Identifiers
LEGAL_ID_PATTERNS = [
    # LEI - Legal Entity Identifier (20 chars)
    (re.compile(r'\b[A-Z0-9]{4}00[A-Z0-9]{12}\d{2}\b'), 'LEI'),

    # UK Company Registration Number
    (re.compile(r'\b(?:CRN|Company\s*(?:No|Number|Reg)\.?)[:\s]*([A-Z]{0,2}\d{6,8})\b', re.I), 'UK_CRN'),

    # German Handelsregister
    (re.compile(r'\b(HR[AB])\s*(\d{3,8})\b'), 'DE_HRB'),

    # US SEC CIK
    (re.compile(r'\bCIK[:\s]*(\d{10})\b', re.I), 'SEC_CIK'),

    # French SIREN/SIRET
    (re.compile(r'\b(?:SIREN|RCS)[:\s]*(\d{3}\s*\d{3}\s*\d{3})\b', re.I), 'FR_SIREN'),
    (re.compile(r'\bSIRET[:\s]*(\d{3}\s*\d{3}\s*\d{3}\s*\d{5})\b', re.I), 'FR_SIRET'),

    # Dutch KvK
    (re.compile(r'\b(?:KvK|Handelsregister|Chamber\s*of\s*Commerce)[:\s]*(\d{8})\b', re.I), 'NL_KVK'),

    # Belgian BCE/KBO
    (re.compile(r'\b(?:BCE|KBO|BTW)[:\s]*(?:BE)?[\s.]?(\d{4}[\s.]?\d{3}[\s.]?\d{3})\b', re.I), 'BE_BCE'),

    # Swiss UID
    (re.compile(r'\b(?:UID|CHE)[:\s-]*(\d{3}[\s.]?\d{3}[\s.]?\d{3})\b', re.I), 'CH_UID'),

    # Austrian FN
    (re.compile(r'\b(?:FN|Firmenbuch)[:\s]*(\d{5,6}\s*[a-z])\b', re.I), 'AT_FN'),

    # Italian
    (re.compile(r'\b(?:C\.?F\.?|Codice\s*Fiscale)[:\s]*([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b', re.I), 'IT_CF'),
    (re.compile(r'\b(?:P\.?\s*IVA|Partita\s*IVA)[:\s]*(?:IT)?(\d{11})\b', re.I), 'IT_PIVA'),

    # Spanish CIF/NIF
    (re.compile(r'\b(?:CIF|NIF)[:\s]*([A-Z]\d{7}[A-Z0-9])\b', re.I), 'ES_CIF'),

    # Polish
    (re.compile(r'\bREGON[:\s]*(\d{9}|\d{14})\b', re.I), 'PL_REGON'),
    (re.compile(r'\bNIP[:\s]*(\d{3}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2})\b', re.I), 'PL_NIP'),
    (re.compile(r'\bKRS[:\s]*(\d{10})\b', re.I), 'PL_KRS'),

    # Czech
    (re.compile(r'\b(?:IČO?|ICO)[:\s]*(\d{8})\b', re.I), 'CZ_ICO'),

    # Hungarian
    (re.compile(r'\b(\d{2}-\d{2}-\d{6})\b'), 'HU_CEGJSZ'),

    # Croatian OIB
    (re.compile(r'\bOIB[:\s]*(\d{11})\b', re.I), 'HR_OIB'),

    # DUNS
    (re.compile(r'\b(?:DUNS|D-U-N-S)[:\s#]*(\d{2}-\d{3}-\d{4}|\d{9})\b', re.I), 'DUNS'),

    # ISIN
    (re.compile(r'\b([A-Z]{2}[A-Z0-9]{9}\d)\b'), 'ISIN'),
]

# Aircraft Registration / Tail Numbers
AIRCRAFT_PATTERNS = [
    (re.compile(r'\b(N[1-9][0-9]{0,4}[A-Z]{0,2})\b'), 'US_FAA'),
    (re.compile(r'\b(G-[A-Z]{4})\b'), 'UK_CAA'),
    (re.compile(r'\b(D-[A-Z]{4})\b'), 'DE_LBA'),
    (re.compile(r'\b(F-[A-Z]{4})\b'), 'FR_DGAC'),
    (re.compile(r'\b(C-[A-Z]{4})\b'), 'CA_TC'),
    (re.compile(r'\b(VH-[A-Z]{3})\b'), 'AU_CASA'),
    (re.compile(r'\b(HB-[A-Z]{3})\b'), 'CH_FOCA'),
    (re.compile(r'\b(PH-[A-Z]{3})\b'), 'NL_ILT'),
    (re.compile(r'\b(I-[A-Z]{4})\b'), 'IT_ENAC'),
    (re.compile(r'\b(EC-[A-Z]{3})\b'), 'ES_AESA'),
    (re.compile(r'\b(OE-[A-Z]{3})\b'), 'AT_ACG'),
    (re.compile(r'\b(OO-[A-Z]{3})\b'), 'BE_BCAA'),
    (re.compile(r'\b(EI-[A-Z]{3})\b'), 'IE_IAA'),
    (re.compile(r'\b(RA-\d{5})\b'), 'RU_FATA'),
    (re.compile(r'\b(B-\d{4})\b'), 'CN_CAAC'),
]

# Vessel / Ship Numbers
VESSEL_PATTERNS = [
    (re.compile(r'\b(?:IMO\s*(?:No\.?|Number)?[:\s]*)(\d{7})\b', re.I), 'IMO'),
    (re.compile(r'\bIMO[:\s]*(\d{7})\b', re.I), 'IMO'),
    (re.compile(r'\b(?:MMSI\s*(?:No\.?)?[:\s]*)(\d{9})\b', re.I), 'MMSI'),
]

# Court Case Numbers
COURT_PATTERNS = [
    (re.compile(r'\b(\d{1,2}:\d{2}-[a-z]{2,4}-\d{3,6}(?:-[A-Z]{2,4})?)\b'), 'US_FED'),
    (re.compile(r'\b(\[\d{4}\]\s*[A-Z]{2,6}\s*\d{1,5})\b'), 'UK_NEUTRAL'),
    (re.compile(r'\b(Case\s*[TC]-\d{1,4}/\d{2})\b', re.I), 'EU_CASE'),
]

# Bank Account Patterns
BANK_PATTERNS = [
    (re.compile(r'\b([A-Z]{2}\d{2}[A-Z0-9]{4,30})\b'), 'IBAN'),
    (re.compile(r'\b([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b'), 'SWIFT'),
]

# Cryptocurrency
CRYPTO_PATTERNS = [
    (re.compile(r'\b([13][a-km-zA-HJ-NP-Z1-9]{25,34})\b'), 'BTC'),
    (re.compile(r'\b(bc1[ac-hj-np-z02-9]{39,59})\b'), 'BTC_BECH32'),
    (re.compile(r'\b(0x[a-fA-F0-9]{40})\b'), 'ETH'),
]


def check_content_patterns(content: str) -> Tuple[bool, List[str]]:
    """Check content for Tier 1 trigger patterns. Returns (has_match, pattern_labels)."""
    if not content:
        return False, []

    matches = []

    # Annual reports
    for pattern in ANNUAL_REPORT_PATTERNS:
        if pattern.search(content):
            matches.append('ANNUAL_REPORT')
            break

    # All identifier patterns
    for pattern_list in [LEGAL_ID_PATTERNS, AIRCRAFT_PATTERNS, VESSEL_PATTERNS,
                         COURT_PATTERNS, BANK_PATTERNS, CRYPTO_PATTERNS]:
        for pattern, label in pattern_list:
            if pattern.search(content):
                matches.append(label)

    return len(matches) > 0, matches


# =============================================================================
# RED FLAG TRIPWIRES
# =============================================================================

# =============================================================================
# DOMAIN SET LOADERS
# =============================================================================

from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan

ES_HOST = "http://localhost:9200"

def load_domain_set(index: str, field: str = "domain", batch_size: int = 10000) -> Set[str]:
    """
    Load all domains from an Elasticsearch index into a set.

    Args:
        index: Index name (e.g., 'affiliate_linkedin_companies')
        field: Field containing domain (default: 'domain')
        batch_size: Scroll batch size

    Returns:
        Set of domain strings
    """
    es = Elasticsearch([ES_HOST])
    domains = set()

    try:
        # Use scan for efficient iteration
        for hit in scan(
            es,
            index=index,
            query={"query": {"exists": {"field": field}}},
            _source=[field],
            size=batch_size,
        ):
            domain = hit["_source"].get(field)
            if domain:
                domains.add(domain.lower())
    except Exception as e:
        print(f"⚠️  Failed to load domains from {index}: {e}")

    return domains


def load_all_domain_sets() -> Dict[str, Set[str]]:
    """
    Load all domain sets needed for tier classification.

    Returns dict with:
        - linkedin_domains: 2.8M domains from affiliate_linkedin_companies
        - wdc_domains: 478K domains from wdc-localbusiness-entities
        - top_domains: 8.6M domains from top_domains (Majestic/Tranco)
    """
    print("📂 Loading domain sets from Elasticsearch...")

    sets = {}

    # LinkedIn companies
    print("   Loading LinkedIn domains...", end=" ", flush=True)
    sets["linkedin_domains"] = load_domain_set("affiliate_linkedin_companies", "domain")
    print(f"{len(sets['linkedin_domains']):,}")

    # WDC LocalBusiness
    print("   Loading WDC LocalBusiness domains...", end=" ", flush=True)
    sets["wdc_domains"] = load_domain_set("wdc-localbusiness-entities", "domain")
    print(f"{len(sets['wdc_domains']):,}")

    # Top domains (Majestic/Tranco)
    print("   Loading top domains...", end=" ", flush=True)
    sets["top_domains"] = load_domain_set("top_domains", "domain")
    print(f"{len(sets['top_domains']):,}")

    print(f"✅ Domain sets loaded: {sum(len(s) for s in sets.values()):,} total")
    return sets


def load_tripwire_entities() -> List[Tuple[str, str]]:
    """
    Load all entities from red_flag index for Aho-Corasick automaton.

    Returns list of (entity_name, flag_type) tuples.
    """
    es = Elasticsearch([ES_HOST])
    entities = []

    print("📂 Loading red_flag entities for tripwire matching...")

    try:
        count = 0
        for hit in scan(
            es,
            index="red_flag",
            query={"query": {"match_all": {}}},
            _source=["name", "type", "source"],
            size=10000,
        ):
            source = hit["_source"]
            name = source.get("name", "")
            flag_type = source.get("type") or source.get("source") or "red_flag"
            if name:
                entities.append((name.lower(), flag_type))
                count += 1
                if count % 100000 == 0:
                    print(f"   Loaded {count:,}...", flush=True)
    except Exception as e:
        print(f"⚠️  Failed to load red_flag entities: {e}")

    print(f"✅ Loaded {len(entities):,} tripwire entities")
    return entities


def build_tripwire_automaton():
    """
    Build Aho-Corasick automaton from red_flag entities.

    Returns automaton ready for find_all() calls.
    """
    try:
        import ahocorasick
    except ImportError:
        print("⚠️  pyahocorasick not installed. Run: pip install pyahocorasick")
        return None

    entities = load_tripwire_entities()

    print("🔨 Building Aho-Corasick automaton...")
    automaton = ahocorasick.Automaton()

    for idx, (name, flag_type) in enumerate(entities):
        automaton.add_word(name, (name, flag_type))

    automaton.make_automaton()
    print(f"✅ Automaton built: {len(entities):,} patterns")

    return automaton


# ACTUAL TRIPWIRE INDICES (verified from Elasticsearch 2025-01-02)
RED_FLAG_INDICES: Dict[str, Dict] = {
    "red_flag": {
        "entity_field": "name",
        "docs": 1950406,
        "ram_estimate": "~1GB",
        "note": "Consolidated sanctions, PEPs, ICIJ, adverse media, enforcement"
    },
    "wdc-localbusiness-entities": {
        "entity_field": "name",
        "docs": 478341,
        "ram_estimate": "~250MB",
        "note": "Schema.org LocalBusiness - optional tripwire"
    },
    "wdc-governmentorganization-entities": {
        "entity_field": "name",
        "docs": 25229,
        "ram_estimate": "~15MB",
        "note": "Government organizations"
    },
}
# Total: ~2.45M entities, ~1.3GB RAM for Aho-Corasick


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_tld(domain: str) -> str:
    """Extract TLD from domain."""
    parts = domain.lower().split('.')
    if len(parts) >= 2:
        if parts[-2] in ('co', 'gov', 'ac', 'org') and parts[-1] in ('uk', 'au', 'nz'):
            return f"{parts[-2]}.{parts[-1]}"
        return parts[-1]
    return ''


def is_allowed_tld(domain: str) -> bool:
    """Check if domain has an allowed TLD."""
    return get_tld(domain) in ALLOWED_TLDS


def is_registry_domain(domain: str) -> bool:
    """Check if domain is a registry domain."""
    domain_lower = domain.lower()
    for reg in REGISTRY_DOMAINS:
        if domain_lower == reg or domain_lower.endswith('.' + reg):
            return True
    return False


def is_free_hosting(domain: str) -> bool:
    """Check if domain is a free hosting platform."""
    domain_lower = domain.lower()
    for platform in FREE_HOSTING_PLATFORMS:
        if domain_lower == platform or domain_lower.endswith('.' + platform):
            return True
    return False


def has_corporate_url_keywords(url: str) -> bool:
    """Check if URL contains corporate keywords."""
    url_lower = url.lower()
    return any(kw in url_lower for kw in CORPORATE_URL_KEYWORDS)


def has_legal_suffix(domain: str) -> bool:
    """Check if domain contains a legal entity suffix."""
    parts = domain.lower().replace('.', '-').replace('_', '-').split('-')
    return any(part in LEGAL_SUFFIXES for part in parts)


# =============================================================================
# MAIN CLASSIFICATION FUNCTION
# =============================================================================

def classify(
    url: str,
    domain: str,
    content: Optional[str] = None,
    is_linkedin_domain: bool = False,
    is_wdc_domain: bool = False,
    is_majestic_million: bool = False,
    red_flag_matches: Optional[List[Dict]] = None,
) -> TierDecision:
    """
    Classify a document into a tier.

    THIS FUNCTION NEVER RETURNS "SKIP". Everything gets a tier.

    Priority order (first match wins):
    1. Red flag tripwires → Tier 1
    2. Registry domains → Tier 1
    3. Content patterns (LEI, tail numbers, etc.) → Tier 1
    4. Corporate URL keywords → Tier 1
    5. Legal suffix in domain → Tier 1
    6. LinkedIn/WDC domain → Tier 1
    7. Majestic Million (no override) → Tier 3
    8. Non-allowed TLD (no override) → Tier 3
    9. Free hosting → Tier 3
    10. Default → Tier 2
    """
    reasons = []
    matched_patterns = []
    red_flags = red_flag_matches or []

    # 1. RED FLAG TRIPWIRES
    if red_flags:
        reasons.append("red_flag_tripwire")
        matched_patterns = [f"RED_FLAG:{m.get('flag_type', 'unknown')}" for m in red_flags]
        return TierDecision(Tier.FULL, reasons, matched_patterns, red_flags)

    # 2. REGISTRY DOMAINS
    if is_registry_domain(domain):
        reasons.append("registry_domain")
        return TierDecision(Tier.FULL, reasons)

    # 3. CONTENT PATTERNS
    if content:
        has_patterns, patterns = check_content_patterns(content)
        if has_patterns:
            reasons.append("content_patterns")
            return TierDecision(Tier.FULL, reasons, patterns)

    # 4. CORPORATE URL KEYWORDS
    if has_corporate_url_keywords(url):
        reasons.append("corporate_url_keywords")
        return TierDecision(Tier.FULL, reasons)

    # 5. LEGAL SUFFIX IN DOMAIN
    if has_legal_suffix(domain):
        reasons.append("legal_suffix_domain")
        return TierDecision(Tier.FULL, reasons)

    # 6. LINKEDIN/WDC OVERRIDE
    if is_linkedin_domain:
        reasons.append("linkedin_company_domain")
        return TierDecision(Tier.FULL, reasons)
    if is_wdc_domain:
        reasons.append("wdc_schema_domain")
        return TierDecision(Tier.FULL, reasons)

    # 7. MAJESTIC MILLION (no override)
    if is_majestic_million and not is_linkedin_domain:
        reasons.append("majestic_million_no_override")
        return TierDecision(Tier.URL_ONLY, reasons)

    # 8. NON-ALLOWED TLD
    if not is_allowed_tld(domain) and not is_linkedin_domain and not is_wdc_domain:
        reasons.append(f"non_allowed_tld:{get_tld(domain)}")
        return TierDecision(Tier.URL_ONLY, reasons)

    # 9. FREE HOSTING
    if is_free_hosting(domain):
        reasons.append("free_hosting_platform")
        return TierDecision(Tier.URL_ONLY, reasons)

    # 10. DEFAULT → Tier 2
    reasons.append("default")
    return TierDecision(Tier.EXTRACT, reasons)


# =============================================================================
# DOCUMENT BUILDERS
# =============================================================================

def build_document(record: dict, decision: TierDecision, content: Optional[str] = None) -> dict:
    """Build document for indexing based on tier decision."""
    doc = {
        "source_url": record.get("url"),
        "source_domain": record.get("domain"),
        "source_type": SOURCE_TYPE,
        "tier": decision.tier,
        "classification_reasons": decision.reasons,
        "metadata": {
            "language": record.get("language"),
        }
    }

    if decision.tier == Tier.FULL:
        doc["content"] = content or ""
        doc["matched_patterns"] = decision.matched_patterns
        doc["metadata"]["token_count"] = record.get("token_count")
        doc["metadata"]["priority_score"] = record.get("priority_score")

        if decision.red_flag_matches:
            doc["red_flags"] = {
                "has_matches": True,
                "match_count": len(decision.red_flag_matches),
                "flag_types": list(set(m.get("flag_type", "") for m in decision.red_flag_matches)),
                "matches": decision.red_flag_matches,
            }

    elif decision.tier == Tier.EXTRACT:
        doc["content"] = ""  # No full-text stored
        doc["metadata"]["token_count"] = record.get("token_count")

    else:  # Tier.URL_ONLY
        doc["content"] = ""
        doc["metadata"]["demotion_reasons"] = decision.reasons

    return doc


# =============================================================================
# PROGRESS & CHECKPOINTING
# =============================================================================

import json
import time
import signal
import sys
from pathlib import Path
from datetime import datetime, timedelta
from threading import Lock

# Checkpoint configuration
CHECKPOINT_DIR = Path(__file__).parent / "checkpoints"
CHECKPOINT_INTERVAL = 1000  # Save every N documents
CHECKPOINT_TIME_INTERVAL = 60  # Save every N seconds

@dataclass
class IngestionProgress:
    """Track ingestion progress with full stats."""
    source_id: str
    total_docs: int = 0
    processed: int = 0
    tier_1_count: int = 0
    tier_2_count: int = 0
    tier_3_count: int = 0
    red_flag_hits: int = 0
    errors: int = 0
    last_offset: int = 0
    start_time: float = field(default_factory=time.time)
    last_checkpoint_time: float = field(default_factory=time.time)
    last_url: str = ""

    def update(self, decision: TierDecision, url: str):
        """Update progress after processing a document."""
        self.processed += 1
        self.last_url = url

        if decision.tier == Tier.FULL:
            self.tier_1_count += 1
        elif decision.tier == Tier.EXTRACT:
            self.tier_2_count += 1
        else:
            self.tier_3_count += 1

        if decision.red_flag_matches:
            self.red_flag_hits += len(decision.red_flag_matches)

    def increment_error(self):
        self.errors += 1

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def rate(self) -> float:
        """Documents per second."""
        if self.elapsed == 0:
            return 0
        return self.processed / self.elapsed

    @property
    def eta_seconds(self) -> float:
        """Estimated time remaining in seconds."""
        if self.rate == 0:
            return float('inf')
        remaining = self.total_docs - self.processed
        return remaining / self.rate

    @property
    def eta_formatted(self) -> str:
        """Human-readable ETA."""
        seconds = self.eta_seconds
        if seconds == float('inf'):
            return "∞"
        return str(timedelta(seconds=int(seconds)))

    @property
    def percent_complete(self) -> float:
        if self.total_docs == 0:
            return 0
        return (self.processed / self.total_docs) * 100

    def display(self) -> str:
        """Progress bar and stats for terminal."""
        bar_width = 40
        filled = int(bar_width * self.percent_complete / 100)
        bar = "█" * filled + "░" * (bar_width - filled)

        return (
            f"\r[{bar}] {self.percent_complete:.1f}% "
            f"| {self.processed:,}/{self.total_docs:,} "
            f"| {self.rate:.1f}/s "
            f"| ETA: {self.eta_formatted} "
            f"| T1:{self.tier_1_count:,} T2:{self.tier_2_count:,} T3:{self.tier_3_count:,} "
            f"| 🚩:{self.red_flag_hits:,} "
            f"| ❌:{self.errors}"
        )

    def to_dict(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "source_id": self.source_id,
            "total_docs": self.total_docs,
            "processed": self.processed,
            "tier_1_count": self.tier_1_count,
            "tier_2_count": self.tier_2_count,
            "tier_3_count": self.tier_3_count,
            "red_flag_hits": self.red_flag_hits,
            "errors": self.errors,
            "last_offset": self.last_offset,
            "start_time": self.start_time,
            "last_checkpoint_time": time.time(),
            "last_url": self.last_url,
            "checkpoint_created": datetime.now().isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IngestionProgress":
        """Restore from checkpoint."""
        progress = cls(source_id=data["source_id"])
        progress.total_docs = data["total_docs"]
        progress.processed = data["processed"]
        progress.tier_1_count = data["tier_1_count"]
        progress.tier_2_count = data["tier_2_count"]
        progress.tier_3_count = data["tier_3_count"]
        progress.red_flag_hits = data["red_flag_hits"]
        progress.errors = data["errors"]
        progress.last_offset = data["last_offset"]
        progress.start_time = data["start_time"]
        progress.last_checkpoint_time = data.get("last_checkpoint_time", time.time())
        progress.last_url = data.get("last_url", "")
        return progress


class CheckpointManager:
    """Manage checkpoint save/restore with atomic writes."""

    def __init__(self, source_id: str):
        self.source_id = source_id
        self.checkpoint_dir = CHECKPOINT_DIR
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.checkpoint_dir / f"{source_id}_checkpoint.json"
        self.lock = Lock()
        self._last_save_time = time.time()
        self._docs_since_save = 0

    def should_save(self) -> bool:
        """Check if we should save a checkpoint."""
        time_elapsed = time.time() - self._last_save_time >= CHECKPOINT_TIME_INTERVAL
        docs_threshold = self._docs_since_save >= CHECKPOINT_INTERVAL
        return time_elapsed or docs_threshold

    def save(self, progress: IngestionProgress, force: bool = False):
        """Save checkpoint atomically."""
        if not force and not self.should_save():
            self._docs_since_save += 1
            return

        with self.lock:
            temp_file = self.checkpoint_file.with_suffix('.tmp')
            try:
                with open(temp_file, 'w') as f:
                    json.dump(progress.to_dict(), f, indent=2)
                temp_file.replace(self.checkpoint_file)
                self._last_save_time = time.time()
                self._docs_since_save = 0
            except Exception as e:
                print(f"\n⚠️  Checkpoint save failed: {e}")

    def load(self) -> Optional[IngestionProgress]:
        """Load checkpoint if exists."""
        if not self.checkpoint_file.exists():
            return None
        try:
            with open(self.checkpoint_file, 'r') as f:
                data = json.load(f)
            progress = IngestionProgress.from_dict(data)
            print(f"📂 Resuming from checkpoint: {progress.processed:,} docs processed")
            print(f"   Last URL: {progress.last_url[:80]}...")
            return progress
        except Exception as e:
            print(f"⚠️  Failed to load checkpoint: {e}")
            return None

    def clear(self):
        """Remove checkpoint after successful completion."""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
            print("✅ Checkpoint cleared after successful completion")


class PacmanRunner:
    """
    Main ingestion runner with progress tracking and checkpointing.

    Usage:
        runner = PacmanRunner(source_id="cc-pdf-2025")
        await runner.run(documents_iterator, total_count=1000000)
    """

    def __init__(self, source_id: str = SOURCE_ID):
        self.source_id = source_id
        self.checkpoint_manager = CheckpointManager(source_id)
        self.progress: Optional[IngestionProgress] = None
        self._shutdown_requested = False

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle CTRL+C gracefully."""
        print("\n\n⚠️  Shutdown requested - saving checkpoint...")
        self._shutdown_requested = True
        if self.progress:
            self.checkpoint_manager.save(self.progress, force=True)
            print(f"✅ Checkpoint saved at {self.progress.processed:,} documents")
        sys.exit(0)

    def load_resources(self):
        """Load all domain sets and tripwire automaton at startup."""
        print("\n" + "=" * 60)
        print("PACMAN RESOURCE LOADING")
        print("=" * 60)

        # Load domain sets
        domain_sets = load_all_domain_sets()
        self.linkedin_domains = domain_sets["linkedin_domains"]
        self.wdc_domains = domain_sets["wdc_domains"]
        self.top_domains = domain_sets["top_domains"]

        # Build tripwire automaton
        self.tripwire_matcher = build_tripwire_automaton()

        print("=" * 60 + "\n")

    async def run(
        self,
        documents,  # Async iterator of documents
        total_count: int,
        index_callback=None,  # async fn(doc, tier) -> bool
        skip_resource_loading: bool = False,
    ):
        """
        Run the ingestion pipeline.

        Args:
            documents: Async iterator yielding document dicts with 'url', 'domain', 'content'
            total_count: Total documents to process (for progress calculation)
            index_callback: Async function to index document, returns success bool
            skip_resource_loading: Skip loading if already loaded (for resume)
        """
        # Load resources if not already loaded
        if not skip_resource_loading and not hasattr(self, 'linkedin_domains'):
            self.load_resources()

        linkedin_domains = getattr(self, 'linkedin_domains', set())
        wdc_domains = getattr(self, 'wdc_domains', set())
        top_domains = getattr(self, 'top_domains', set())

        # Try to resume from checkpoint
        self.progress = self.checkpoint_manager.load()
        if self.progress:
            start_offset = self.progress.last_offset
            self.progress.total_docs = total_count
        else:
            self.progress = IngestionProgress(source_id=self.source_id, total_docs=total_count)
            start_offset = 0

        tripwire_matcher = getattr(self, 'tripwire_matcher', None)

        print(f"\n🎮 PACMAN starting ingestion: {total_count:,} documents")
        print(f"   Source: {self.source_id}")
        print(f"   Target: {TARGET_INDEX}")
        print(f"   Tripwires loaded: {tripwire_matcher is not None}")
        print(f"   LinkedIn domains: {len(linkedin_domains):,}")
        print(f"   WDC domains: {len(wdc_domains):,}")
        print(f"   Top domains: {len(top_domains):,}")
        print()

        doc_index = 0
        async for doc in documents:
            # Skip to resume point
            if doc_index < start_offset:
                doc_index += 1
                continue

            # Check for shutdown
            if self._shutdown_requested:
                break

            try:
                url = doc.get("url", "")
                domain = doc.get("domain", "")
                content = doc.get("content", "")

                # Check tripwires
                red_flag_matches = []
                if tripwire_matcher and content:
                    matches = tripwire_matcher.find_all(content)
                    red_flag_matches = [{"entity": m[0], "flag_type": m[1]} for m in matches]

                # Classify
                decision = classify(
                    url=url,
                    domain=domain,
                    content=content,
                    is_linkedin_domain=domain in linkedin_domains,
                    is_wdc_domain=domain in wdc_domains,
                    is_majestic_million=domain in top_domains,
                    red_flag_matches=red_flag_matches,
                )

                # Build document
                indexed_doc = build_document(doc, decision, content if decision.tier == Tier.FULL else None)

                # Index
                if index_callback:
                    success = await index_callback(indexed_doc, decision.tier)
                    if not success:
                        self.progress.increment_error()

                # Update progress
                self.progress.update(decision, url)
                self.progress.last_offset = doc_index + 1

                # Display progress
                print(self.progress.display(), end="", flush=True)

                # Checkpoint
                self.checkpoint_manager.save(self.progress)

            except Exception as e:
                self.progress.increment_error()
                print(f"\n❌ Error processing doc {doc_index}: {e}")

            doc_index += 1

        # Final save and cleanup
        self.checkpoint_manager.save(self.progress, force=True)

        if not self._shutdown_requested:
            self.checkpoint_manager.clear()
            print(f"\n\n✅ PACMAN ingestion complete!")

        self._print_final_stats()

    def _print_final_stats(self):
        """Print final statistics."""
        p = self.progress
        print("\n" + "=" * 60)
        print("PACMAN INGESTION STATS")
        print("=" * 60)
        print(f"Total processed:  {p.processed:,}")
        print(f"Tier 1 (Full):    {p.tier_1_count:,} ({p.tier_1_count/max(p.processed,1)*100:.1f}%)")
        print(f"Tier 2 (Extract): {p.tier_2_count:,} ({p.tier_2_count/max(p.processed,1)*100:.1f}%)")
        print(f"Tier 3 (URL):     {p.tier_3_count:,} ({p.tier_3_count/max(p.processed,1)*100:.1f}%)")
        print(f"Red flag hits:    {p.red_flag_hits:,}")
        print(f"Errors:           {p.errors:,}")
        print(f"Duration:         {timedelta(seconds=int(p.elapsed))}")
        print(f"Avg rate:         {p.rate:.1f} docs/sec")
        print("=" * 60)


# =============================================================================
# SUMMARY
# =============================================================================
"""
TIER 1 (FULL) TRIGGERS:
- Red flag tripwires (sanctions, PEP, ICIJ, enforcement, adverse media)
- Registry domains (sec.gov, companieshouse.gov.uk, etc.)
- Content patterns (LEI, CRN, aircraft tail numbers, vessel IMO, etc.)
- Annual report detection (multilingual)
- Corporate URL keywords
- Legal suffix in domain
- LinkedIn/WDC domain overlap

TIER 2 (EXTRACT) - Default for:
- Allowed TLDs without Tier 1 triggers
- Gambling/Crypto sites
- News sites
- Forums/blogs (content-dependent)

TIER 3 (URL-ONLY) - Demoted items:
- Non-allowed TLDs without override
- Majestic Million without LinkedIn override
- Free hosting platforms
- Academic/scientific (edu, ac.uk)

CRITICAL RULES:
1. EVERY URL gets indexed - no exceptions
2. Exclusion = demotion to Tier 3, NOT skipping
3. LinkedIn/WDC membership overrides exclusion rules
4. Content patterns ALWAYS override URL-based demotion
5. Annual reports = ALWAYS Tier 1
6. Red flag tripwires = automatic Tier 1 + flagged

CONTEXT EXTRACTION:
- 5 words before + 5 words after each entity mention
"""
