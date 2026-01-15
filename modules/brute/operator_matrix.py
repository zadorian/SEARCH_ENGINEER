"""
Operator Support Matrix
=======================

Defines how search operators (site:, filetype:, inurl:, etc.) are executed
across different search engines based on their native support.

NOTE: This file defines OPERATOR SUPPORT LEVELS (L1/L2/L3), which is a
SEPARATE concept from search Layers and Tiers:

  - layers.py = Search INTENSITY (how hard: NATIVE, ENHANCED, BRUTE, NUCLEAR)
  - tiers.py = Engine GROUPS (which engines: fast, all, all+slow)
  - operator_matrix.py = OPERATOR SUPPORT per engine (L1/L2/L3)

OPERATOR SUPPORT LEVELS:
  L1 = Engine natively supports the operator (use directly)
  L2 = Engine doesn't support operator natively, use creative workaround
  L3 = Fallback - basic query only, filter results post-hoc
"""

from enum import IntEnum
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass


class OperatorLayer(IntEnum):
    """Operator execution layers."""
    L1 = 1  # Native support - pass operator directly to engine
    L2 = 2  # Creative workaround - transform query for similar effect
    L3 = 3  # Fallback - basic query, post-filter results


@dataclass
class OperatorSupport:
    """Defines an engine's support for a specific operator."""
    operator: str
    layer: OperatorLayer
    native_syntax: Optional[str] = None  # How engine expects it (if L1)
    workaround: Optional[str] = None     # Transformation for L2
    notes: Optional[str] = None


# =============================================================================
# CANONICAL OPERATORS
# =============================================================================
# These are the standard search operators that may be supported across engines.
# Each engine has different native support levels (L1/L2/L3).

OPERATORS = {
    # Core search operators
    "site": "Restrict to domain/subdomain",
    "filetype": "Restrict to file extension",
    "ext": "File extension (alias for filetype)",
    "inurl": "Term must appear in URL",
    "intitle": "Term must appear in title",
    "intext": "Term must appear in body text",
    "inanchor": "Term in anchor text of links pointing to page",

    # Relationship operators
    "related": "Pages similar to URL",
    "cache": "Cached version of page",
    "link": "Pages linking to URL (deprecated in most engines)",

    # Temporal operators
    "before": "Results before date (YYYY-MM-DD)",
    "after": "Results after date (YYYY-MM-DD)",
    "daterange": "Restrict to date range",

    # Localization operators
    "lang": "Language restriction (2-letter code)",
    "loc": "Geographic location",

    # Boolean/logic operators (handled by brute/logic/)
    "AND": "Boolean AND (implicit in most engines)",
    "OR": "Boolean OR",
    "NOT": "Boolean NOT / exclusion",
    "-": "Exclusion (alias for NOT)",

    # Proximity operators (handled by brute/logic/proximity.py)
    "NEAR": "Terms within N words of each other",
    "AROUND": "Google's proximity operator",
    "~": "Fuzzy matching",
}


# =============================================================================
# ENGINE OPERATOR SUPPORT MATRIX (35+ ENGINES)
# =============================================================================
# Comprehensive mapping of which engines support which operators at which layer.
#
# L1 = Native support (pass operator directly, engine handles it)
# L2 = Creative workaround (transform query to achieve similar effect)
# L3 = Fallback (run basic query, filter results post-hoc)
#
# PHILOSOPHY: We use ALL engines for maximum recall. L1 engines give us
# precision, L2/L3 engines add recall with filtering overhead.
# =============================================================================

ENGINE_OPERATOR_MATRIX: Dict[str, Dict[str, OperatorSupport]] = {

    # =========================================================================
    # TIER 1 ENGINES (Fast, primary search)
    # =========================================================================

    "GO": {  # Google - Strong but some deprecated operators
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, "filetype:{ext}"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L1, "inurl:{term}"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "intitle:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L1, "intext:{term}"),
        # NOTE: Google's inanchor: is DEPRECATED/UNRELIABLE - use LINKLATER sources instead
        "inanchor": OperatorSupport("inanchor", OperatorLayer.L3, notes="DEPRECATED - route to LINKLATER"),
        "related": OperatorSupport("related", OperatorLayer.L1, "related:{url}"),
        "cache": OperatorSupport("cache", OperatorLayer.L2, notes="Unreliable, use Archive.org"),
        "before": OperatorSupport("before", OperatorLayer.L1, "before:{date}"),
        "after": OperatorSupport("after", OperatorLayer.L1, "after:{date}"),
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="Use lr= param"),
        "AROUND": OperatorSupport("AROUND", OperatorLayer.L1, "AROUND({n})"),
        "OR": OperatorSupport("OR", OperatorLayer.L1, "OR"),
        "-": OperatorSupport("-", OperatorLayer.L1, "-{term}"),
    },

    "BI": {  # Bing - Strong operator support
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, "filetype:{ext}"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L1, "inurl:{term}"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "intitle:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L2, workaround='"{term}"'),
        "inanchor": OperatorSupport("inanchor", OperatorLayer.L3),
        "related": OperatorSupport("related", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L1, notes="Use freshness param"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="Use freshness param"),
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="Use setlang param"),
        "NEAR": OperatorSupport("NEAR", OperatorLayer.L1, "NEAR:{n}"),
        "OR": OperatorSupport("OR", OperatorLayer.L1, "OR"),
        "-": OperatorSupport("-", OperatorLayer.L1, "-{term}"),
    },

    "BR": {  # Brave - Good operator support, strong privacy
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, "filetype:{ext}"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L2, workaround="site:*{term}*"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "intitle:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L2, workaround='"{term}"'),
        "inanchor": OperatorSupport("inanchor", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L1, notes="Use freshness API param"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="Use freshness API param"),
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="Use search_lang param"),
        "OR": OperatorSupport("OR", OperatorLayer.L1, "OR"),
        "-": OperatorSupport("-", OperatorLayer.L1, "-{term}"),
    },

    "DD": {  # DuckDuckGo - Privacy focused, limited operators
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, "filetype:{ext}"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L2, workaround="site:*{term}*"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "intitle:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
        "inanchor": OperatorSupport("inanchor", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
        "OR": OperatorSupport("OR", OperatorLayer.L1, "OR"),
        "-": OperatorSupport("-", OperatorLayer.L1, "-{term}"),
    },

    "EX": {  # Exa - Semantic search, API-based operators
        "site": OperatorSupport("site", OperatorLayer.L1, notes="includeDomains API param"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L3),
        "inurl": OperatorSupport("inurl", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L2, workaround="title:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L1, notes="Semantic by default"),
        "before": OperatorSupport("before", OperatorLayer.L1, notes="endPublishedDate param"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="startPublishedDate param"),
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="language param"),
    },

    # =========================================================================
    # TIER 2 ENGINES (Secondary, broader coverage)
    # =========================================================================

    "YA": {  # Yandex - EXCELLENT operator support, different syntax
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, "mime:{ext}"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L1, "inurl:{term}"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "title:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L2, workaround='"{term}"'),
        "inanchor": OperatorSupport("inanchor", OperatorLayer.L1, "inlink:{term}"),  # RARE L1!
        "related": OperatorSupport("related", OperatorLayer.L1, notes="Use related: param"),
        "before": OperatorSupport("before", OperatorLayer.L1, "date:<{date}"),
        "after": OperatorSupport("after", OperatorLayer.L1, "date:>{date}"),
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="lr param"),
        "OR": OperatorSupport("OR", OperatorLayer.L1, "|"),
        "-": OperatorSupport("-", OperatorLayer.L1, "~~{term}"),
    },

    "QW": {  # Qwant - European, decent support
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, "filetype:{ext}"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "intitle:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
        "related": OperatorSupport("related", OperatorLayer.L1, notes="related param"),
        "OR": OperatorSupport("OR", OperatorLayer.L1, "OR"),
        "-": OperatorSupport("-", OperatorLayer.L1, "-{term}"),
    },

    "YE": {  # Yep - Privacy search
        "site": OperatorSupport("site", OperatorLayer.L3),
        "filetype": OperatorSupport("filetype", OperatorLayer.L3),
        "inurl": OperatorSupport("inurl", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
    },

    "YO": {  # You.com - AI-enhanced search
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, notes="file_type param"),
        "before": OperatorSupport("before", OperatorLayer.L1, notes="freshness API"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="freshness API"),
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="language param"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
    },

    "BA": {  # Baidu - Chinese search giant
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, "filetype:{ext}"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L1, "inurl:{term}"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "intitle:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
        "-": OperatorSupport("-", OperatorLayer.L1, "-{term}"),
    },

    "SO": {  # Sogou - Chinese search
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, "filetype:{ext}"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
    },

    "MO": {  # Mojeek - Independent index
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L3),
        "inurl": OperatorSupport("inurl", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="lb param"),
    },

    "ME": {  # MetaGer - German meta-search
        "site": OperatorSupport("site", OperatorLayer.L2, workaround="site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L3),
        "inurl": OperatorSupport("inurl", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
    },

    "SZ": {  # Seznam - Czech search
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L3),
        "inurl": OperatorSupport("inurl", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
    },

    # =========================================================================
    # ARCHIVE & HISTORICAL ENGINES
    # =========================================================================

    "AR": {  # Archive.org / Wayback - EXCELLENT temporal support
        "site": OperatorSupport("site", OperatorLayer.L1, "url:{domain}*"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, "mimetype:{mime}"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L1, "url:*{term}*"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L1, notes="to: param"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="from: param"),
    },

    "PW": {  # PublicWWW - Source code search (searches raw HTML!)
        "site": OperatorSupport("site", OperatorLayer.L2, workaround='site="{domain}"'),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, notes="Uses URL pattern"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L1, notes="Primary function"),
        # HACK: Search for HTML link patterns to find anchor text!
        # ">annual report</a>" finds pages with outlinks containing that anchor text
        "inanchor": OperatorSupport("inanchor", OperatorLayer.L2,
            workaround='">{term}</a>"',
            notes="HTML source search - finds outlinks with anchor text"),
    },

    # =========================================================================
    # ACADEMIC & SCHOLARLY ENGINES
    # =========================================================================

    "AX": {  # ArXiv - Preprints
        "before": OperatorSupport("before", OperatorLayer.L1, notes="submittedDate API"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="submittedDate API"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "ti:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L1, "abs:{term}"),
        "site": OperatorSupport("site", OperatorLayer.L3),
        "filetype": OperatorSupport("filetype", OperatorLayer.L3),  # Always PDF
    },

    "PM": {  # PubMed - Medical literature
        "before": OperatorSupport("before", OperatorLayer.L1, notes="PDAT filter"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="PDAT filter"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "[Title]"),
        "intext": OperatorSupport("intext", OperatorLayer.L1, "[Abstract]"),
        "site": OperatorSupport("site", OperatorLayer.L3),
        "filetype": OperatorSupport("filetype", OperatorLayer.L3),
    },

    "OA": {  # OpenAlex - Academic papers
        "before": OperatorSupport("before", OperatorLayer.L1, notes="to_publication_date"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="from_publication_date"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, notes="filter by title"),
        "site": OperatorSupport("site", OperatorLayer.L3),
        "filetype": OperatorSupport("filetype", OperatorLayer.L3),
    },

    "SS": {  # Semantic Scholar
        "before": OperatorSupport("before", OperatorLayer.L1, notes="year filter"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="year filter"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
        "site": OperatorSupport("site", OperatorLayer.L3),
    },

    "CR": {  # Crossref - DOI/citations
        "before": OperatorSupport("before", OperatorLayer.L1, notes="until-created-date"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="from-created-date"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, notes="query.title"),
        "site": OperatorSupport("site", OperatorLayer.L3),
        "filetype": OperatorSupport("filetype", OperatorLayer.L3),
    },

    "JS": {  # JSTOR - Academic journals
        "before": OperatorSupport("before", OperatorLayer.L1, notes="pub_date filter"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="pub_date filter"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "ti:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L1, "ab:{term}"),
        "site": OperatorSupport("site", OperatorLayer.L3),
    },

    "NA": {  # Nature - Nature journals
        "before": OperatorSupport("before", OperatorLayer.L1, notes="date_range"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="date_range"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
        "site": OperatorSupport("site", OperatorLayer.L3),
    },

    "SA": {  # SAGE Journals
        "before": OperatorSupport("before", OperatorLayer.L1, notes="date filter"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="date filter"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "site": OperatorSupport("site", OperatorLayer.L3),
    },

    "MU": {  # MUSE - Humanities
        "before": OperatorSupport("before", OperatorLayer.L1, notes="pubyear"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="pubyear"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "site": OperatorSupport("site", OperatorLayer.L3),
    },

    # =========================================================================
    # NEWS & MEDIA ENGINES
    # =========================================================================

    "GD": {  # GDELT - News archive
        "after": OperatorSupport("after", OperatorLayer.L1, notes="startdatetime"),
        "before": OperatorSupport("before", OperatorLayer.L1, notes="enddatetime"),
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="sourcelang"),
        "site": OperatorSupport("site", OperatorLayer.L2, workaround="domain:{domain}"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
    },

    "NW": {  # NewsAPI - Aggregated news
        "before": OperatorSupport("before", OperatorLayer.L1, notes="to param"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="from param"),
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="language param"),
        "site": OperatorSupport("site", OperatorLayer.L1, notes="domains param"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, notes="qintitle param"),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
    },

    # =========================================================================
    # SOCIAL & COMMUNITY ENGINES
    # =========================================================================

    "RD": {  # Reddit
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "inurl": OperatorSupport("inurl", OperatorLayer.L2, workaround="url:{term}"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "title:{term}"),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L1, "selftext:{term}"),
    },

    "SC": {  # SocialSearcher
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="language filter"),
        "site": OperatorSupport("site", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
    },

    "BR_V": {  # Brave Videos
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L3),  # N/A
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
    },

    "YT": {  # YouTube Search
        "before": OperatorSupport("before", OperatorLayer.L1, notes="publishedBefore"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="publishedAfter"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L2, workaround="allintitle:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
        "site": OperatorSupport("site", OperatorLayer.L3),  # N/A
    },

    "FB": {  # Facebook (limited)
        "site": OperatorSupport("site", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
    },

    # =========================================================================
    # SPECIALIZED ENGINES
    # =========================================================================

    "WK": {  # Wikipedia
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="Use {lang}.wikipedia.org"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, "intitle:{term}"),
        "intext": OperatorSupport("intext", OperatorLayer.L1, notes="Default behavior"),
        "site": OperatorSupport("site", OperatorLayer.L3),  # N/A
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
    },

    "WL": {  # WikiLeaks
        "before": OperatorSupport("before", OperatorLayer.L1, notes="date filter"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="date filter"),
        "site": OperatorSupport("site", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
    },

    "GU": {  # Project Gutenberg
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="language param"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, notes="title param"),
        "site": OperatorSupport("site", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
    },

    "OL": {  # OpenLibrary
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="language param"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, notes="title param"),
        "site": OperatorSupport("site", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
    },

    "LG": {  # LibGen
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, notes="extension filter"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, notes="title column"),
        "site": OperatorSupport("site", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
    },

    "AN": {  # Anna's Archive
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, notes="format filter"),
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="language filter"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "site": OperatorSupport("site", OperatorLayer.L3),
    },

    "HF": {  # HuggingFace
        "site": OperatorSupport("site", OperatorLayer.L1, notes="filter by repo"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
    },

    "GR": {  # Grok
        "site": OperatorSupport("site", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L1, notes="AI understands context"),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
    },

    "PE": {  # Perplexity
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L1, notes="AI extraction"),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L3),
    },

    "AL": {  # Aleph
        "site": OperatorSupport("site", OperatorLayer.L3),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, notes="title field"),
        "intext": OperatorSupport("intext", OperatorLayer.L1, notes="body field"),
        "before": OperatorSupport("before", OperatorLayer.L3),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="date filters"),
        "related": OperatorSupport("related", OperatorLayer.L1, notes="entity links"),
    },

    "TO": {  # Tor search
        "site": OperatorSupport("site", OperatorLayer.L1, "site:{domain}"),
        "before": OperatorSupport("before", OperatorLayer.L1, notes="date filter"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="date filter"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L3),
        "intext": OperatorSupport("intext", OperatorLayer.L3),
    },

    # =========================================================================
    # CYMONIDES - Elasticsearch Unified Search (570M+ domains, 14.9M entities)
    # =========================================================================
    # Local ES indices with rich operator support. THIS IS L1 FOR EVERYTHING.

    "CY": {  # CYMONIDES - Elasticsearch unified search
        # Domain/content operators
        "site": OperatorSupport("site", OperatorLayer.L1, notes="domain field match"),
        "filetype": OperatorSupport("filetype", OperatorLayer.L1, notes="pdf! operator"),
        "intitle": OperatorSupport("intitle", OperatorLayer.L1, notes="title field"),
        "intext": OperatorSupport("intext", OperatorLayer.L1, notes="text field - default"),
        # Temporal - FULL L1 SUPPORT
        "before": OperatorSupport("before", OperatorLayer.L1, notes="<- YYYY! or date range"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="YYYY ->! or date range"),
        # LOCATION FILTERS:
        # fr! = SHORTHAND for (dom{fr}! OR lang{fr}! OR geo{fr}!) - matches ANY
        # dom{fr}! = domain TLD only, lang{fr}! = language only, geo{fr}! = country only
        "lang": OperatorSupport("lang", OperatorLayer.L1, notes="lang{XX}! - language ONLY"),
        "loc": OperatorSupport("loc", OperatorLayer.L1, notes="geo{XX}! - geographic ONLY"),
        "related": OperatorSupport("related", OperatorLayer.L1, notes="[category] definitional"),
        # Advanced text
        "NEAR": OperatorSupport("NEAR", OperatorLayer.L1, notes='"word1 word2"~N proximity'),
        "OR": OperatorSupport("OR", OperatorLayer.L1, "OR"),
        "-": OperatorSupport("-", OperatorLayer.L1, "-{term}"),
        # Also: rank(<1000), authority(high|medium|low)
    },

    # =========================================================================
    # LINKLATER / BACKLINK ENGINES - The REAL inanchor: sources
    # =========================================================================
    # These are the proper L1 sources for anchor text search.
    # Google's inanchor: is deprecated - route queries HERE instead.

    "MJ": {  # Majestic - Commercial backlink database
        # L1 for anchor text - GetAnchorText and SearchByKeyword APIs
        "inanchor": OperatorSupport("inanchor", OperatorLayer.L1,
            notes="GetAnchorText + SearchByKeyword APIs via LINKLATER"),
        "site": OperatorSupport("site", OperatorLayer.L1, notes="Filter by target domain"),
    },

    "GL": {  # GlobalLinks - Go binaries + WAT files (fastest anchor text search)
        # Uses WAT (WARC metadata) files for massive parallel anchor text search
        "inanchor": OperatorSupport("inanchor", OperatorLayer.L1,
            notes="WAT processing via Go binaries - FASTEST for bulk anchor search"),
        "site": OperatorSupport("site", OperatorLayer.L1, notes="Filter by target domain"),
        "before": OperatorSupport("before", OperatorLayer.L1, notes="CC collection date filter"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="CC collection date filter"),
    },

    "WG": {  # Elasticsearch cc_web_graph_edges (14.9M records)
        # Local ES index with anchor_text field from Common Crawl webgraph
        "inanchor": OperatorSupport("inanchor", OperatorLayer.L1,
            native_syntax="anchor_text:{term}",
            notes="ES query on anchor_text field - 14.9M edge records"),
        "site": OperatorSupport("site", OperatorLayer.L1,
            native_syntax="target_url:*{domain}*",
            notes="Filter by target domain"),
    },

    "BD": {  # BacklinkDiscovery - WARC range requests
        # Makes range requests to WARC files for specific records
        "inanchor": OperatorSupport("inanchor", OperatorLayer.L1,
            notes="WARC range request parsing extracts anchor text"),
        "site": OperatorSupport("site", OperatorLayer.L1, notes="Filter by target domain"),
        "before": OperatorSupport("before", OperatorLayer.L1, notes="WARC timestamp filter"),
        "after": OperatorSupport("after", OperatorLayer.L1, notes="WARC timestamp filter"),
    },
}

# Default for engines not in matrix - assume L3 for all operators
DEFAULT_LAYER = OperatorLayer.L3


def get_operator_layer(engine: str, operator: str) -> OperatorLayer:
    """Get the execution layer for an operator on a specific engine."""
    engine_support = ENGINE_OPERATOR_MATRIX.get(engine, {})
    op_support = engine_support.get(operator)
    if op_support:
        return op_support.layer
    return DEFAULT_LAYER


def get_operator_support(engine: str, operator: str) -> Optional[OperatorSupport]:
    """Get full operator support details for an engine."""
    engine_support = ENGINE_OPERATOR_MATRIX.get(engine, {})
    return engine_support.get(operator)


def get_l1_engines(operator: str) -> List[str]:
    """Get all engines that natively support an operator (L1)."""
    engines = []
    for engine, ops in ENGINE_OPERATOR_MATRIX.items():
        if operator in ops and ops[operator].layer == OperatorLayer.L1:
            engines.append(engine)
    return engines


def get_l2_engines(operator: str) -> List[str]:
    """Get all engines that can handle an operator with workarounds (L2)."""
    engines = []
    for engine, ops in ENGINE_OPERATOR_MATRIX.items():
        if operator in ops and ops[operator].layer == OperatorLayer.L2:
            engines.append(engine)
    return engines


def get_supported_operators(engine: str) -> Dict[str, OperatorLayer]:
    """Get all operators supported by an engine with their layers."""
    engine_support = ENGINE_OPERATOR_MATRIX.get(engine, {})
    return {op: support.layer for op, support in engine_support.items()}


def transform_query_for_engine(
    query: str,
    operator: str,
    value: str,
    engine: str
) -> str:
    """
    Transform a query with an operator for a specific engine based on its layer.

    Args:
        query: Base query string
        operator: Operator name (e.g., "site", "filetype")
        value: Operator value (e.g., "example.com", "pdf")
        engine: Engine code (e.g., "GO", "BI")

    Returns:
        Transformed query string appropriate for the engine
    """
    support = get_operator_support(engine, operator)

    if not support:
        # L3 fallback - just append to query, will filter post-hoc
        return query

    if support.layer == OperatorLayer.L1:
        # Native support - use engine's syntax
        if support.native_syntax:
            op_str = support.native_syntax.format(
                domain=value, ext=value, term=value, url=value, date=value, mime=value
            )
            return f"{query} {op_str}"
        else:
            # Standard syntax
            return f"{query} {operator}:{value}"

    elif support.layer == OperatorLayer.L2:
        # Workaround - use transformation
        if support.workaround:
            workaround = support.workaround.format(term=value)
            return f"{query} {workaround}"
        else:
            return query

    else:
        # L3 - no transformation, filter post-hoc
        return query


class LayerRouter:
    """
    Routes queries to appropriate engines based on operator layer support.

    Strategy:
    1. For L1 operators, prefer engines with native support
    2. For L2 operators, include engines with workarounds
    3. For L3, run on all engines and filter results afterward
    """

    def __init__(self, all_engines: Optional[List[str]] = None):
        self.all_engines = all_engines or list(ENGINE_OPERATOR_MATRIX.keys())

    def route_by_operators(
        self,
        operators_used: List[str],
        prefer_native: bool = True
    ) -> Dict[str, List[str]]:
        """
        Determine which engines to use based on operators in query.

        Args:
            operators_used: List of operators in the query
            prefer_native: If True, prioritize L1 engines

        Returns:
            Dict with 'l1', 'l2', 'l3' keys containing engine lists
        """
        if not operators_used:
            # No operators - use all engines
            return {"l1": self.all_engines, "l2": [], "l3": []}

        l1_engines: Set[str] = set(self.all_engines)
        l2_engines: Set[str] = set()
        l3_engines: Set[str] = set()

        for op in operators_used:
            op_l1 = set(get_l1_engines(op))
            op_l2 = set(get_l2_engines(op))

            if prefer_native and op_l1:
                # Intersect with engines that support this operator natively
                l1_engines &= op_l1
            else:
                # Include L2 as acceptable
                l1_engines &= (op_l1 | op_l2)

            l2_engines |= op_l2
            # Remaining engines are L3
            l3_engines |= (set(self.all_engines) - op_l1 - op_l2)

        # Remove L1 engines from L2/L3
        l2_engines -= l1_engines
        l3_engines -= l1_engines
        l3_engines -= l2_engines

        return {
            "l1": list(l1_engines),
            "l2": list(l2_engines),
            "l3": list(l3_engines),
        }

    def get_execution_plan(
        self,
        query: str,
        operators_used: List[str],
        include_l3: bool = True
    ) -> List[Dict[str, any]]:
        """
        Create an execution plan for a query with operators.

        Returns list of {engine, transformed_query, layer, post_filter} dicts
        """
        routing = self.route_by_operators(operators_used)
        plan = []

        # L1 engines - native support
        for engine in routing["l1"]:
            transformed = query
            for op in operators_used:
                # Extract value from query (simplified)
                transformed = transform_query_for_engine(
                    transformed, op, "", engine  # Value extraction needed
                )
            plan.append({
                "engine": engine,
                "query": transformed,
                "layer": OperatorLayer.L1,
                "post_filter": False,
            })

        # L2 engines - workarounds
        for engine in routing["l2"]:
            transformed = query
            for op in operators_used:
                support = get_operator_support(engine, op)
                if support and support.workaround:
                    transformed = transform_query_for_engine(
                        transformed, op, "", engine
                    )
            plan.append({
                "engine": engine,
                "query": transformed,
                "layer": OperatorLayer.L2,
                "post_filter": True,  # May need post-filtering
            })

        # L3 engines - basic query, post-filter
        if include_l3:
            for engine in routing["l3"]:
                plan.append({
                    "engine": engine,
                    "query": query,  # No transformation
                    "layer": OperatorLayer.L3,
                    "post_filter": True,  # Must filter results
                })

        return plan


# =============================================================================
# CROSS-DIMENSION ROUTING
# =============================================================================
# The core insight: Different engines have different native support.
# Solution: Whatever CAN be native WILL be native. The rest gets filtered.
#
# CASCADE PRINCIPLE:
# 1. L1 engines first - Send full query with native syntax
# 2. L2 engines second - Apply creative workarounds (quoted phrases, wildcards)
# 3. L3 engines third - Send minimal query, post-filter results
#
# EXAMPLE: Query with [site, filetype, inanchor]
# - Google: all L1 → send full query, no filtering
# - Yandex: all L1 (inanchor → inlink:) → send transformed query, no filtering
# - Bing, Brave, DD: L3 for inanchor → send site+filetype, POST-FILTER for inanchor
# =============================================================================

import re
from dataclasses import field


@dataclass
class ParsedOperator:
    """A parsed operator from a query string."""
    name: str
    value: str
    raw: str  # Original string like "site:example.com"


@dataclass
class EngineExecutionPlan:
    """Execution plan for a single engine."""
    engine: str
    transformed_query: str
    native_operators: List[str]  # Operators handled natively (L1)
    workaround_operators: List[str]  # Operators with workarounds (L2)
    filter_operators: List[str]  # Operators requiring post-filter (L3)
    effective_layer: OperatorLayer  # Worst layer among all operators
    requires_post_filter: bool
    filter_rules: Dict[str, str] = field(default_factory=dict)  # op -> value for filtering


@dataclass
class CrossDimensionPlan:
    """Complete execution plan across all engines."""
    base_query: str
    operators: List[ParsedOperator]
    engine_plans: List[EngineExecutionPlan]

    # Summary stats
    fully_native_engines: List[str]  # Engines where ALL operators are L1
    partial_native_engines: List[str]  # Engines with mix of L1/L2/L3
    filter_only_engines: List[str]  # Engines where ALL operators need filtering


class CrossDimensionRouter:
    """
    Routes queries across engines with different operator support levels.

    THE PRINCIPLE:
    - Whatever CAN be native WILL be native
    - The rest gets filtered (L2 workaround + filter, or L3 pure filter)
    - We MAXIMIZE recall by using ALL engines, not just L1-capable ones

    THE TRADE-OFF:
    - L1 engines: Fast, accurate, no false positives
    - L2 engines: Good, may have edge case misses
    - L3 engines: Slower (filter overhead), but adds recall
    """

    # Operator patterns for parsing
    OPERATOR_PATTERNS = {
        "site": re.compile(r'\bsite:([^\s]+)', re.I),
        "filetype": re.compile(r'\bfiletype:([^\s]+)', re.I),
        "inurl": re.compile(r'\binurl:([^\s]+)', re.I),
        "intitle": re.compile(r'\bintitle:([^\s]+)', re.I),
        "intext": re.compile(r'\bintext:([^\s]+)', re.I),
        "inanchor": re.compile(r'\binanchor:([^\s]+)', re.I),
        "related": re.compile(r'\brelated:([^\s]+)', re.I),
        "cache": re.compile(r'\bcache:([^\s]+)', re.I),
        "before": re.compile(r'\bbefore:([^\s]+)', re.I),
        "after": re.compile(r'\bafter:([^\s]+)', re.I),
        "ext": re.compile(r'\bext:([^\s]+)', re.I),
        "lang": re.compile(r'\blang:([^\s]+)', re.I),
    }

    # LINKLATER engines - proper L1 sources for anchor text search
    # These are auto-included when inanchor: operator is detected
    LINKLATER_ENGINES = ["WG", "MJ", "GL", "BD"]

    # Operators that require special engine routing
    OPERATOR_ENGINE_ROUTING = {
        "inanchor": LINKLATER_ENGINES,  # Route to LINKLATER, not deprecated Google
    }

    def __init__(self, engines: Optional[List[str]] = None):
        """
        Initialize with list of engines to use.

        Args:
            engines: List of engine codes. If None, uses all in ENGINE_OPERATOR_MATRIX.
        """
        self.engines = engines or list(ENGINE_OPERATOR_MATRIX.keys())

    def parse_operators(self, query: str) -> tuple[str, List[ParsedOperator]]:
        """
        Parse operators from a query string.

        Returns:
            Tuple of (base_query_without_operators, list_of_parsed_operators)
        """
        operators = []
        base_query = query

        for op_name, pattern in self.OPERATOR_PATTERNS.items():
            for match in pattern.finditer(query):
                operators.append(ParsedOperator(
                    name=op_name,
                    value=match.group(1),
                    raw=match.group(0)
                ))
                # Remove from base query
                base_query = base_query.replace(match.group(0), "").strip()

        # Handle filetype alias
        for op in operators:
            if op.name == "ext":
                op.name = "filetype"

        # Clean up multiple spaces
        base_query = re.sub(r'\s+', ' ', base_query).strip()

        return base_query, operators

    def classify_operator_for_engine(
        self,
        operator: str,
        engine: str
    ) -> tuple[OperatorLayer, Optional[str]]:
        """
        Classify how an engine handles an operator.

        Returns:
            Tuple of (layer, transformed_syntax_or_None)
        """
        support = get_operator_support(engine, operator)

        if not support:
            return OperatorLayer.L3, None

        if support.layer == OperatorLayer.L1:
            return OperatorLayer.L1, support.native_syntax
        elif support.layer == OperatorLayer.L2:
            return OperatorLayer.L2, support.workaround
        else:
            return OperatorLayer.L3, None

    def build_engine_plan(
        self,
        engine: str,
        base_query: str,
        operators: List[ParsedOperator]
    ) -> EngineExecutionPlan:
        """
        Build execution plan for a single engine.
        """
        native_ops = []
        workaround_ops = []
        filter_ops = []
        filter_rules = {}

        transformed_query = base_query

        for op in operators:
            layer, syntax = self.classify_operator_for_engine(op.name, engine)

            if layer == OperatorLayer.L1:
                native_ops.append(op.name)
                # Add native syntax to query
                if syntax:
                    op_str = syntax.format(
                        domain=op.value, ext=op.value, term=op.value,
                        url=op.value, date=op.value, mime=op.value
                    )
                    transformed_query = f"{transformed_query} {op_str}"
                else:
                    # Default syntax
                    transformed_query = f"{transformed_query} {op.name}:{op.value}"

            elif layer == OperatorLayer.L2:
                workaround_ops.append(op.name)
                # Apply workaround
                if syntax:
                    workaround = syntax.format(
                        domain=op.value, ext=op.value, term=op.value,
                        url=op.value, date=op.value, mime=op.value, n="5"
                    )
                    transformed_query = f"{transformed_query} {workaround}"
                # Still needs filtering as backup
                filter_rules[op.name] = op.value

            else:  # L3
                filter_ops.append(op.name)
                # Store filter rule
                filter_rules[op.name] = op.value

        # Determine effective layer (worst case)
        if filter_ops:
            effective_layer = OperatorLayer.L3
        elif workaround_ops:
            effective_layer = OperatorLayer.L2
        else:
            effective_layer = OperatorLayer.L1

        return EngineExecutionPlan(
            engine=engine,
            transformed_query=transformed_query.strip(),
            native_operators=native_ops,
            workaround_operators=workaround_ops,
            filter_operators=filter_ops,
            effective_layer=effective_layer,
            requires_post_filter=bool(filter_ops or workaround_ops),
            filter_rules=filter_rules
        )

    def create_cross_dimension_plan(self, query: str) -> CrossDimensionPlan:
        """
        Create a complete execution plan for a query across all engines.

        This is the main entry point for cross-dimension routing.

        SMART ROUTING:
        - When inanchor: is detected, auto-includes LINKLATER engines (WG, MJ, GL, BD)
        - Google's deprecated inanchor: is NOT used - we route to proper sources
        """
        base_query, operators = self.parse_operators(query)

        # Determine which engines to use
        engines_to_use = set(self.engines)

        # Auto-include specialized engines for certain operators
        for op in operators:
            if op.name in self.OPERATOR_ENGINE_ROUTING:
                required_engines = self.OPERATOR_ENGINE_ROUTING[op.name]
                engines_to_use.update(required_engines)

        engine_plans = []
        fully_native = []
        partial_native = []
        filter_only = []

        for engine in engines_to_use:
            plan = self.build_engine_plan(engine, base_query, operators)
            engine_plans.append(plan)

            # Classify engine
            if plan.effective_layer == OperatorLayer.L1:
                fully_native.append(engine)
            elif plan.native_operators:
                partial_native.append(engine)
            else:
                filter_only.append(engine)

        return CrossDimensionPlan(
            base_query=base_query,
            operators=operators,
            engine_plans=engine_plans,
            fully_native_engines=fully_native,
            partial_native_engines=partial_native,
            filter_only_engines=filter_only
        )

    def get_execution_summary(self, plan: CrossDimensionPlan) -> str:
        """
        Get a human-readable summary of the execution plan.
        """
        lines = [
            f"Query: {plan.base_query}",
            f"Operators: {[f'{op.name}:{op.value}' for op in plan.operators]}",
            "",
            "ENGINE CLASSIFICATION:",
            f"  L1 (fully native): {plan.fully_native_engines}",
            f"  L1+L2 (partial native): {plan.partial_native_engines}",
            f"  L3 (filter only): {plan.filter_only_engines}",
            "",
            "PER-ENGINE BREAKDOWN:"
        ]

        for ep in plan.engine_plans:
            lines.append(f"  {ep.engine}:")
            lines.append(f"    Query: {ep.transformed_query}")
            lines.append(f"    Layer: L{ep.effective_layer.value}")
            if ep.native_operators:
                lines.append(f"    Native (L1): {ep.native_operators}")
            if ep.workaround_operators:
                lines.append(f"    Workaround (L2): {ep.workaround_operators}")
            if ep.filter_operators:
                lines.append(f"    Filter (L3): {ep.filter_operators}")
            if ep.filter_rules:
                lines.append(f"    Post-filter: {ep.filter_rules}")

        return "\n".join(lines)


# =============================================================================
# POST-FILTER IMPLEMENTATIONS
# =============================================================================
# When an engine returns results without native operator support,
# we filter the results to enforce the operator constraints.
# =============================================================================

class PostFilter:
    """
    Filters search results to enforce operator constraints.

    Used for L2 (as backup) and L3 (as primary) operator handling.
    """

    @staticmethod
    def filter_results(
        results: List[Dict],
        filter_rules: Dict[str, str]
    ) -> List[Dict]:
        """
        Filter results based on operator rules.

        Args:
            results: List of search results with 'url', 'title', 'snippet' keys
            filter_rules: Dict of operator -> value to filter by

        Returns:
            Filtered list of results
        """
        filtered = results

        for operator, value in filter_rules.items():
            if operator == "site":
                filtered = PostFilter._filter_site(filtered, value)
            elif operator == "filetype":
                filtered = PostFilter._filter_filetype(filtered, value)
            elif operator == "inurl":
                filtered = PostFilter._filter_inurl(filtered, value)
            elif operator == "intitle":
                filtered = PostFilter._filter_intitle(filtered, value)
            elif operator == "intext":
                filtered = PostFilter._filter_intext(filtered, value)
            elif operator == "inanchor":
                # Can't filter inanchor without scraping - mark as unverified
                for r in filtered:
                    r["_inanchor_unverified"] = True
            elif operator in ("before", "after"):
                # Date filtering requires parsing dates from results
                filtered = PostFilter._filter_date(filtered, operator, value)

        return filtered

    @staticmethod
    def _filter_site(results: List[Dict], domain: str) -> List[Dict]:
        """Filter to only results from specified domain."""
        domain = domain.lower().lstrip("*.")
        return [
            r for r in results
            if domain in r.get("url", "").lower()
        ]

    @staticmethod
    def _filter_filetype(results: List[Dict], ext: str) -> List[Dict]:
        """Filter to only results with specified file extension."""
        ext = ext.lower().lstrip(".")
        return [
            r for r in results
            if r.get("url", "").lower().endswith(f".{ext}")
        ]

    @staticmethod
    def _filter_inurl(results: List[Dict], term: str) -> List[Dict]:
        """Filter to only results with term in URL."""
        term = term.lower()
        return [
            r for r in results
            if term in r.get("url", "").lower()
        ]

    @staticmethod
    def _filter_intitle(results: List[Dict], term: str) -> List[Dict]:
        """Filter to only results with term in title."""
        term = term.lower()
        return [
            r for r in results
            if term in r.get("title", "").lower()
        ]

    @staticmethod
    def _filter_intext(results: List[Dict], term: str) -> List[Dict]:
        """Filter to only results with term in snippet/text."""
        term = term.lower()
        return [
            r for r in results
            if term in r.get("snippet", "").lower() or
               term in r.get("text", "").lower()
        ]

    @staticmethod
    def _filter_date(
        results: List[Dict],
        operator: str,
        date_str: str
    ) -> List[Dict]:
        """Filter by date (before/after). Requires 'date' field in results."""
        from datetime import datetime

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            # Can't parse date - return all (mark as unverified)
            for r in results:
                r["_date_unverified"] = True
            return results

        filtered = []
        for r in results:
            result_date_str = r.get("date") or r.get("published_date")
            if not result_date_str:
                r["_date_unverified"] = True
                filtered.append(r)  # Keep but mark unverified
                continue

            try:
                result_date = datetime.strptime(result_date_str[:10], "%Y-%m-%d")
                if operator == "before" and result_date < target_date:
                    filtered.append(r)
                elif operator == "after" and result_date > target_date:
                    filtered.append(r)
            except ValueError:
                r["_date_unverified"] = True
                filtered.append(r)  # Keep but mark unverified

        return filtered


# =============================================================================
# CROSS-DIMENSION ANALYTICS
# =============================================================================
# Functions to understand the operator support landscape across all engines.
# =============================================================================

def get_matrix_stats() -> Dict[str, Any]:
    """
    Get comprehensive statistics about the ENGINE_OPERATOR_MATRIX.

    Returns dict with:
    - total_engines: Number of engines in matrix
    - engines_by_l1_count: Engines sorted by L1 operator count
    - operator_coverage: Per-operator L1/L2/L3 engine counts
    - rare_operators: Operators with <5 L1 engines
    - universal_operators: Operators with >15 L1 engines
    """
    stats = {
        "total_engines": len(ENGINE_OPERATOR_MATRIX),
        "engines_by_l1_count": {},
        "operator_coverage": {},
        "rare_operators": [],
        "universal_operators": [],
    }

    # Count L1/L2/L3 per engine
    for engine, ops in ENGINE_OPERATOR_MATRIX.items():
        l1 = sum(1 for o in ops.values() if o.layer == OperatorLayer.L1)
        l2 = sum(1 for o in ops.values() if o.layer == OperatorLayer.L2)
        l3 = sum(1 for o in ops.values() if o.layer == OperatorLayer.L3)
        stats["engines_by_l1_count"][engine] = {"l1": l1, "l2": l2, "l3": l3}

    # Count engines per operator
    core_operators = ["site", "filetype", "inurl", "intitle", "intext",
                      "inanchor", "before", "after", "lang", "related"]

    for op in core_operators:
        l1_engines = [e for e, ops in ENGINE_OPERATOR_MATRIX.items()
                      if op in ops and ops[op].layer == OperatorLayer.L1]
        l2_engines = [e for e, ops in ENGINE_OPERATOR_MATRIX.items()
                      if op in ops and ops[op].layer == OperatorLayer.L2]

        stats["operator_coverage"][op] = {
            "l1_count": len(l1_engines),
            "l2_count": len(l2_engines),
            "l1_engines": l1_engines,
            "l2_engines": l2_engines,
        }

        if len(l1_engines) < 5:
            stats["rare_operators"].append(op)
        if len(l1_engines) > 15:
            stats["universal_operators"].append(op)

    return stats


def print_operator_heatmap():
    """
    Print a visual heatmap of operator support across engines.
    """
    operators = ["site", "file", "inurl", "intit", "intxt", "inanc", "befor", "after", "lang"]
    op_map = {
        "site": "site", "file": "filetype", "inurl": "inurl",
        "intit": "intitle", "intxt": "intext", "inanc": "inanchor",
        "befor": "before", "after": "after", "lang": "lang"
    }

    # Header
    print("ENGINE  " + " ".join(f"{o:5}" for o in operators))
    print("-" * 60)

    # Sort engines by L1 count
    engines = sorted(
        ENGINE_OPERATOR_MATRIX.keys(),
        key=lambda e: sum(1 for o in ENGINE_OPERATOR_MATRIX[e].values()
                          if o.layer == OperatorLayer.L1),
        reverse=True
    )

    for engine in engines[:20]:  # Top 20 engines
        row = f"{engine:7} "
        for short_op in operators:
            op = op_map[short_op]
            if op in ENGINE_OPERATOR_MATRIX[engine]:
                layer = ENGINE_OPERATOR_MATRIX[engine][op].layer
                if layer == OperatorLayer.L1:
                    row += "  L1  "
                elif layer == OperatorLayer.L2:
                    row += "  L2  "
                else:
                    row += "  --  "
            else:
                row += "      "
        print(row)


def get_best_engines_for_query(operators_used: List[str]) -> Dict[str, List[str]]:
    """
    Given a list of operators, return engines categorized by how well they support them.

    Returns:
        {
            "fully_native": [...],  # All operators L1
            "mostly_native": [...],  # >50% L1
            "partial": [...],  # Some L1
            "filter_only": [...]  # No L1
        }
    """
    results = {"fully_native": [], "mostly_native": [], "partial": [], "filter_only": []}

    for engine, ops in ENGINE_OPERATOR_MATRIX.items():
        l1_count = sum(1 for op in operators_used
                       if op in ops and ops[op].layer == OperatorLayer.L1)
        total = len(operators_used)

        if l1_count == total:
            results["fully_native"].append(engine)
        elif l1_count > total / 2:
            results["mostly_native"].append(engine)
        elif l1_count > 0:
            results["partial"].append(engine)
        else:
            results["filter_only"].append(engine)

    return results


# =============================================================================
# TIER + OPERATOR SUPPORT INTEGRATION
# =============================================================================
# How TIERS (engine groups) interact with OPERATOR SUPPORT (L1/L2/L3).
#
# NOTE: This section integrates:
#   - TIERS (from tiers.py) = which engines to use
#   - OPERATOR SUPPORT = L1/L2/L3 per engine per operator
#
# TIER 1 (Fast engines):
#   - Use FAST engines only (GO, BI, BR, DD, EX, CY)
#   - Prefer L1 operator support
#   - Skip engines where operators are L3
#
# TIER 2 (All standard engines):
#   - Use ALL standard engines
#   - Accept L1 and L2 operators
#   - Post-filter L3 operators
#
# TIER 3 (All engines including slow):
#   - Use ALL+SLOW engines
#   - Accept all operator support levels
#   - Aggressive post-filtering
# =============================================================================

def get_tier_operator_strategy(tier: int, operators_used: List[str]) -> Dict[str, Any]:
    """
    Determine the optimal engine strategy based on tier and operator support.

    Args:
        tier: Engine tier (1=fast, 2=all, 3=all+slow)
        operators_used: List of operators in the query

    Returns:
        Strategy dict with engines to use and filtering requirements
    """
    from .tiers import ENGINE_GROUPS

    strategy = {
        "tier": tier,
        "operators": operators_used,
        "engines": [],
        "skip_engines": [],
        "post_filter_engines": [],
        "rationale": "",
    }

    if tier == 1:
        # Tier 1: Fast engines only, prefer L1 operator support
        fast = ENGINE_GROUPS.get("fast", ["GO", "BI", "BR", "DD", "EX"])
        best = get_best_engines_for_query(operators_used)
        # Use fast engines that have full or mostly L1 operator support
        strategy["engines"] = [e for e in fast if e in best["fully_native"] + best["mostly_native"]]
        strategy["skip_engines"] = [e for e in fast if e in best["filter_only"]]
        strategy["post_filter_engines"] = [e for e in fast if e in best["partial"]]
        strategy["rationale"] = "Tier 1: Fast engines with L1 operator support priority"

    elif tier == 2:
        # Tier 2: All standard engines, accept L2 operator support
        all_engines = ENGINE_GROUPS.get("all", list(ENGINE_OPERATOR_MATRIX.keys())[:15])
        best = get_best_engines_for_query(operators_used)
        strategy["engines"] = all_engines
        strategy["post_filter_engines"] = [e for e in all_engines if e not in best["fully_native"]]
        strategy["rationale"] = "Tier 2: All standard engines, L2 acceptable, post-filter L3"

    elif tier >= 3:
        # Tier 3: All engines including slow, accept all operator support levels
        all_slow = ENGINE_GROUPS.get("all+slow", list(ENGINE_OPERATOR_MATRIX.keys()))
        strategy["engines"] = all_slow
        strategy["post_filter_engines"] = all_slow  # Filter everything for safety
        strategy["rationale"] = f"Tier {tier}: All engines, maximum recall, aggressive filtering"

    return strategy


# Backward compatibility alias
get_tier_layer_strategy = get_tier_operator_strategy
