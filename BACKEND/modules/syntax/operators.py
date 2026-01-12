"""
SASTRE Operator Definitions

Central registry of all operators in the unified syntax.
The agent is fluent in these operators but ignorant of the machinery behind them.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set


class OperatorCategory(Enum):
    """Categories of operators by function."""
    EXTRACTION = "extraction"      # ent?, p?, c?, e?, t?, a?
    LINK_ANALYSIS = "link"         # bl?, ?bl, ol?, ?ol
    QUERY = "query"                # sanctions?, registry?, whois? (search FOR results)
    COMMAND = "command"            # /enrich, /scrape, /brute, /clink (imperative DO THIS)
    WATCHER = "watcher"            # /watcher - standing surveillance
    COMPARE = "compare"            # =?
    FILETYPE = "filetype"          # pdf!, doc!, word!, xls!, ppt!, file!
    BULK = "bulk"                  # () selection, => tagging, workstream linking
    TLD_FILTER = "tld_filter"      # de!, uk!, com!, gov!, news!
    IO_PREFIX = "io_prefix"        # p:, c:, e:, t:, d: (Core Entity Investigation)
    REGISTRY_PREFIX = "registry"   # cde:, cuk: (Country Registry Profiles)


class ResultGranularity(Enum):
    """Result granularity based on ? position."""
    ALL = "all"           # op? suffix - returns all/pages
    UNIQUE = "unique"     # ?op prefix - returns unique/domains


@dataclass
class OperatorDef:
    """Definition of a single operator."""
    symbol: str                           # e.g., "ent?", "bl?", "=?"
    name: str                             # Human-readable name
    category: OperatorCategory
    description: str
    applies_to: List[str]                 # Node classes this applies to: @SOURCE, @COMPANY, etc.
    granularity: Optional[ResultGranularity] = None  # For link operators
    supports_bulk: bool = False           # Can take () bulk selection
    supports_filters: bool = False        # Can take {} keyword/TLD filters
    chainable: bool = True                # Can be chained with =>
    example: str = ""


# =============================================================================
# OPERATOR REGISTRY
# =============================================================================

OPERATORS: Dict[str, OperatorDef] = {
    # ------------- IO Prefixes (Core Entity Investigation) -------------
    "p:": OperatorDef(
        symbol="p:",
        name="Person Investigation",
        category=OperatorCategory.IO_PREFIX,
        description="Investigate a person (IOExecutor)",
        applies_to=["@PERSON"],
        example="p: John Smith"
    ),
    "c:": OperatorDef(
        symbol="c:",
        name="Company Investigation",
        category=OperatorCategory.IO_PREFIX,
        description="Investigate a company (IOExecutor)",
        applies_to=["@COMPANY"],
        example="c: Acme Corp :US"
    ),
    "e:": OperatorDef(
        symbol="e:",
        name="Email Investigation",
        category=OperatorCategory.IO_PREFIX,
        description="Investigate an email address (IOExecutor)",
        applies_to=["@PERSON", "@COMPANY"],
        example="e: john@example.com"
    ),
    "t:": OperatorDef(
        symbol="t:",
        name="Phone Investigation",
        category=OperatorCategory.IO_PREFIX,
        description="Investigate a phone number (IOExecutor)",
        applies_to=["@PERSON", "@COMPANY"],
        example="t: +1-555-0123"
    ),
    "d:": OperatorDef(
        symbol="d:",
        name="Domain Investigation",
        category=OperatorCategory.IO_PREFIX,
        description="Investigate a domain (IOExecutor)",
        applies_to=["@DOMAIN"],
        example="d: example.com"
    ),
    "u:": OperatorDef(
        symbol="u:",
        name="Username Investigation",
        category=OperatorCategory.IO_PREFIX,
        description="Investigate a username (IOExecutor)",
        applies_to=["@PERSON"],
        example="u: johnsmith123"
    ),
    "li:": OperatorDef(
        symbol="li:",
        name="LinkedIn Investigation",
        category=OperatorCategory.IO_PREFIX,
        description="Investigate a LinkedIn URL (IOExecutor)",
        applies_to=["@PERSON", "@COMPANY"],
        example="li: linkedin.com/in/johnsmith"
    ),

    # ------------- Extraction Operators (@type?) - lowercase -------------
    # Full forms
    "@entity?": OperatorDef(
        symbol="@entity?",
        name="Extract All Entities",
        category=OperatorCategory.EXTRACTION,
        description="Extract all entity types from source",
        applies_to=["@SOURCE"],
        example="@entity? :!domain.com"
    ),
    "@person?": OperatorDef(
        symbol="@person?",
        name="Extract Persons",
        category=OperatorCategory.EXTRACTION,
        description="Extract person names from source",
        applies_to=["@SOURCE"],
        example="@person? :!#querynode"
    ),
    "@company?": OperatorDef(
        symbol="@company?",
        name="Extract Companies",
        category=OperatorCategory.EXTRACTION,
        description="Extract company names from source",
        applies_to=["@SOURCE"],
        example="@company? :domain.com/page!"
    ),
    "@email?": OperatorDef(
        symbol="@email?",
        name="Extract Emails",
        category=OperatorCategory.EXTRACTION,
        description="Extract email addresses from source",
        applies_to=["@SOURCE"],
        example="@email? :!#querynode"
    ),
    "@phone?": OperatorDef(
        symbol="@phone?",
        name="Extract Telephones",
        category=OperatorCategory.EXTRACTION,
        description="Extract phone numbers from source",
        applies_to=["@SOURCE"],
        example="@phone? :!domain.com"
    ),
    "@address?": OperatorDef(
        symbol="@address?",
        name="Extract Addresses",
        category=OperatorCategory.EXTRACTION,
        description="Extract physical addresses from source",
        applies_to=["@SOURCE"],
        example="@address? :#source!"
    ),
    "@username?": OperatorDef(
        symbol="@username?",
        name="Extract Usernames",
        category=OperatorCategory.EXTRACTION,
        description="Extract social media usernames and handles",
        applies_to=["@SOURCE"],
        example="@username? :!domain.com"
    ),
    # Short forms (lowercase)
    "@ent?": OperatorDef(
        symbol="@ent?",
        name="Extract All Entities (short)",
        category=OperatorCategory.EXTRACTION,
        description="Alias for @entity?",
        applies_to=["@SOURCE"],
        example="@ent? :!domain.com"
    ),
    "@p?": OperatorDef(
        symbol="@p?",
        name="Extract Persons (short)",
        category=OperatorCategory.EXTRACTION,
        description="Alias for @person?",
        applies_to=["@SOURCE"],
        example="@p? :!#querynode"
    ),
    "@c?": OperatorDef(
        symbol="@c?",
        name="Extract Companies (short)",
        category=OperatorCategory.EXTRACTION,
        description="Alias for @company?",
        applies_to=["@SOURCE"],
        example="@c? :domain.com/page!"
    ),
    "@e?": OperatorDef(
        symbol="@e?",
        name="Extract Emails (short)",
        category=OperatorCategory.EXTRACTION,
        description="Alias for @email?",
        applies_to=["@SOURCE"],
        example="@e? :!#querynode"
    ),
    "@t?": OperatorDef(
        symbol="@t?",
        name="Extract Telephones (short)",
        category=OperatorCategory.EXTRACTION,
        description="Alias for @phone?",
        applies_to=["@SOURCE"],
        example="@t? :!domain.com"
    ),
    "@a?": OperatorDef(
        symbol="@a?",
        name="Extract Addresses (short)",
        category=OperatorCategory.EXTRACTION,
        description="Alias for @address?",
        applies_to=["@SOURCE"],
        example="@a? :#source!"
    ),
    "@u?": OperatorDef(
        symbol="@u?",
        name="Extract Usernames (short)",
        category=OperatorCategory.EXTRACTION,
        description="Alias for @username?",
        applies_to=["@SOURCE"],
        example="@u? :!domain.com"
    ),

    # Backwards-compatible short forms (no @ prefix)
    # Many older tools/tests use ent?/p?/c?/e?/t?/a?/u? without @.
    "ent?": OperatorDef(
        symbol="ent?",
        name="Extract All Entities",
        category=OperatorCategory.EXTRACTION,
        description="Backwards-compatible alias for @entity?",
        applies_to=["@SOURCE"],
        example="ent? :!domain.com"
    ),
    "p?": OperatorDef(
        symbol="p?",
        name="Extract Persons",
        category=OperatorCategory.EXTRACTION,
        description="Backwards-compatible alias for @person?",
        applies_to=["@SOURCE"],
        example="p? :!#querynode"
    ),
    "c?": OperatorDef(
        symbol="c?",
        name="Extract Companies",
        category=OperatorCategory.EXTRACTION,
        description="Backwards-compatible alias for @company?",
        applies_to=["@SOURCE"],
        example="c? :domain.com/page!"
    ),
    "e?": OperatorDef(
        symbol="e?",
        name="Extract Emails",
        category=OperatorCategory.EXTRACTION,
        description="Backwards-compatible alias for @email?",
        applies_to=["@SOURCE"],
        example="e? :!#querynode"
    ),
    "t?": OperatorDef(
        symbol="t?",
        name="Extract Telephones",
        category=OperatorCategory.EXTRACTION,
        description="Backwards-compatible alias for @phone?",
        applies_to=["@SOURCE"],
        example="t? :!domain.com"
    ),
    "a?": OperatorDef(
        symbol="a?",
        name="Extract Addresses",
        category=OperatorCategory.EXTRACTION,
        description="Backwards-compatible alias for @address?",
        applies_to=["@SOURCE"],
        example="a? :#source!"
    ),
    "u?": OperatorDef(
        symbol="u?",
        name="Extract Usernames",
        category=OperatorCategory.EXTRACTION,
        description="Backwards-compatible alias for @username?",
        applies_to=["@SOURCE"],
        example="u? :!domain.com"
    ),

    # ------------- Link Analysis Operators -------------
    "bl?": OperatorDef(
        symbol="bl?",
        name="Backlinks (Pages)",
        category=OperatorCategory.LINK_ANALYSIS,
        description="Find pages that link to target",
        applies_to=["@SOURCE", "@DOMAIN"],
        granularity=ResultGranularity.ALL,
        example="bl? :!domain.com"
    ),
    "?bl": OperatorDef(
        symbol="?bl",
        name="Backlinks (Domains)",
        category=OperatorCategory.LINK_ANALYSIS,
        description="Find unique domains that link to target",
        applies_to=["@SOURCE", "@DOMAIN"],
        granularity=ResultGranularity.UNIQUE,
        example="?bl :!domain.com"
    ),
    "ol?": OperatorDef(
        symbol="ol?",
        name="Outlinks (Pages)",
        category=OperatorCategory.LINK_ANALYSIS,
        description="Find pages linked from target",
        applies_to=["@SOURCE", "@DOMAIN"],
        granularity=ResultGranularity.ALL,
        example="ol? :domain.com/page!"
    ),
    "?ol": OperatorDef(
        symbol="?ol",
        name="Outlinks (Domains)",
        category=OperatorCategory.LINK_ANALYSIS,
        description="Find unique domains linked from target",
        applies_to=["@SOURCE", "@DOMAIN"],
        granularity=ResultGranularity.UNIQUE,
        example="?ol :!domain.com"
    ),

    # ------------- Query Operators (search FOR results) -------------
    "sanctions?": OperatorDef(
        symbol="sanctions?",
        name="Sanctions Check",
        category=OperatorCategory.QUERY,
        description="Search sanctions lists for matches",
        applies_to=["@PERSON", "@COMPANY"],
        example="sanctions? :!#person"
    ),
    "registry?": OperatorDef(
        symbol="registry?",
        name="Registry Check",
        category=OperatorCategory.QUERY,
        description="Search corporate registries",
        applies_to=["@COMPANY"],
        example="registry? :#company!"
    ),
    "whois?": OperatorDef(
        symbol="whois?",
        name="WHOIS Lookup",
        category=OperatorCategory.QUERY,
        description="Query domain registration data",
        applies_to=["@DOMAIN"],
        example="whois? :domain.com"
    ),

    # ------------- Compare Operator -------------
    "=?": OperatorDef(
        symbol="=?",
        name="Compare/Similarity",
        category=OperatorCategory.COMPARE,
        description="Compare nodes or find similar entities",
        applies_to=["*"],  # Applies to any node type
        example="=? :#john_smith #john_j_smith"
    ),

    # ------------- Filetype Operators -------------
    "pdf!": OperatorDef(
        symbol="pdf!",
        name="PDF Files",
        category=OperatorCategory.FILETYPE,
        description="Discover PDF files on domain",
        applies_to=["@DOMAIN"],
        example="pdf! :!sebgroup.com"
    ),
    "doc!": OperatorDef(
        symbol="doc!",
        name="All Documents",
        category=OperatorCategory.FILETYPE,
        description="Discover all documents (pdf, doc, xls, ppt, etc.)",
        applies_to=["@DOMAIN"],
        example="doc! :!company.com"
    ),
    "word!": OperatorDef(
        symbol="word!",
        name="Word Documents",
        category=OperatorCategory.FILETYPE,
        description="Discover Word documents (doc, docx)",
        applies_to=["@DOMAIN"],
        example="word! :!company.com"
    ),
    "xls!": OperatorDef(
        symbol="xls!",
        name="Excel Files",
        category=OperatorCategory.FILETYPE,
        description="Discover Excel spreadsheets",
        applies_to=["@DOMAIN"],
        example="xls! :!company.com"
    ),
    "ppt!": OperatorDef(
        symbol="ppt!",
        name="PowerPoint Files",
        category=OperatorCategory.FILETYPE,
        description="Discover PowerPoint presentations",
        applies_to=["@DOMAIN"],
        example="ppt! :!company.com"
    ),
    "file!": OperatorDef(
        symbol="file!",
        name="All Files",
        category=OperatorCategory.FILETYPE,
        description="Discover all file types (alias for doc!)",
        applies_to=["@DOMAIN"],
        example="file! :!domain.com"
    ),
    "document!": OperatorDef(
        symbol="document!",
        name="Documents",
        category=OperatorCategory.FILETYPE,
        description="Discover document files (pdf, doc, txt, etc.)",
        applies_to=["@DOMAIN"],
        example="document! :!domain.com"
    ),
    "spreadsheet!": OperatorDef(
        symbol="spreadsheet!",
        name="Spreadsheets",
        category=OperatorCategory.FILETYPE,
        description="Discover spreadsheet files (xls, csv, numbers)",
        applies_to=["@DOMAIN"],
        example="spreadsheet! :!domain.com"
    ),
    "presentation!": OperatorDef(
        symbol="presentation!",
        name="Presentations",
        category=OperatorCategory.FILETYPE,
        description="Discover presentation files (ppt, key, odp)",
        applies_to=["@DOMAIN"],
        example="presentation! :!domain.com"
    ),
    "text!": OperatorDef(
        symbol="text!",
        name="Text Files",
        category=OperatorCategory.FILETYPE,
        description="Discover text-like files (txt, md, json, xml)",
        applies_to=["@DOMAIN"],
        example="text! :!domain.com"
    ),
    "image!": OperatorDef(
        symbol="image!",
        name="Images",
        category=OperatorCategory.FILETYPE,
        description="Discover image files (jpg, png, svg, etc.)",
        applies_to=["@DOMAIN"],
        example="image! :!domain.com"
    ),
    "audio!": OperatorDef(
        symbol="audio!",
        name="Audio",
        category=OperatorCategory.FILETYPE,
        description="Discover audio files (mp3, wav, flac, etc.)",
        applies_to=["@DOMAIN"],
        example="audio! :!domain.com"
    ),
    "video!": OperatorDef(
        symbol="video!",
        name="Video",
        category=OperatorCategory.FILETYPE,
        description="Discover video files (mp4, mov, mkv, etc.)",
        applies_to=["@DOMAIN"],
        example="video! :!domain.com"
    ),
    "media!": OperatorDef(
        symbol="media!",
        name="Media",
        category=OperatorCategory.FILETYPE,
        description="Discover mixed media files (image + audio + video)",
        applies_to=["@DOMAIN"],
        example="media! :!domain.com"
    ),
    "archive!": OperatorDef(
        symbol="archive!",
        name="Archives",
        category=OperatorCategory.FILETYPE,
        description="Discover archive files (zip, rar, 7z, etc.)",
        applies_to=["@DOMAIN"],
        example="archive! :!domain.com"
    ),
    "code!": OperatorDef(
        symbol="code!",
        name="Code",
        category=OperatorCategory.FILETYPE,
        description="Discover source code files (py, js, go, etc.)",
        applies_to=["@DOMAIN"],
        example="code! :!domain.com"
    ),
    "@doc?": OperatorDef(
        symbol="@doc?",
        name="Documents (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for doc! (all documents)",
        applies_to=["@DOMAIN"],
        example="@doc? :!domain.com"
    ),
    "@file?": OperatorDef(
        symbol="@file?",
        name="All Files (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for file! (all files)",
        applies_to=["@DOMAIN"],
        example="@file? :!domain.com"
    ),
    "@document?": OperatorDef(
        symbol="@document?",
        name="Documents (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for document!",
        applies_to=["@DOMAIN"],
        example="@document? :!domain.com"
    ),
    "@spreadsheet?": OperatorDef(
        symbol="@spreadsheet?",
        name="Spreadsheets (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for spreadsheet!",
        applies_to=["@DOMAIN"],
        example="@spreadsheet? :!domain.com"
    ),
    "@presentation?": OperatorDef(
        symbol="@presentation?",
        name="Presentations (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for presentation!",
        applies_to=["@DOMAIN"],
        example="@presentation? :!domain.com"
    ),
    "@text?": OperatorDef(
        symbol="@text?",
        name="Text Files (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for text!",
        applies_to=["@DOMAIN"],
        example="@text? :!domain.com"
    ),
    "@image?": OperatorDef(
        symbol="@image?",
        name="Images (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for image!",
        applies_to=["@DOMAIN"],
        example="@image? :!domain.com"
    ),
    "@audio?": OperatorDef(
        symbol="@audio?",
        name="Audio (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for audio!",
        applies_to=["@DOMAIN"],
        example="@audio? :!domain.com"
    ),
    "@video?": OperatorDef(
        symbol="@video?",
        name="Video (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for video!",
        applies_to=["@DOMAIN"],
        example="@video? :!domain.com"
    ),
    "@media?": OperatorDef(
        symbol="@media?",
        name="Media (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for media!",
        applies_to=["@DOMAIN"],
        example="@media? :!domain.com"
    ),
    "@archive?": OperatorDef(
        symbol="@archive?",
        name="Archives (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for archive!",
        applies_to=["@DOMAIN"],
        example="@archive? :!domain.com"
    ),
    "@code?": OperatorDef(
        symbol="@code?",
        name="Code (alias)",
        category=OperatorCategory.FILETYPE,
        description="Alias for code!",
        applies_to=["@DOMAIN"],
        example="@code? :!domain.com"
    ),

    # ------------- Command Operators (imperative - DO THIS) -------------
    "/enrich": OperatorDef(
        symbol="/enrich",
        name="Enrich Entity",
        category=OperatorCategory.COMMAND,
        description="Fill entity slots with additional data",
        applies_to=["@PERSON", "@COMPANY", "@ASSET"],
        example="p? => /enrich => sanctions?"
    ),
    "/scrape": OperatorDef(
        symbol="/scrape",
        name="Scrape Content",
        category=OperatorCategory.COMMAND,
        description="Fetch and scrape URL content",
        applies_to=["@SOURCE", "@DOMAIN"],
        example="ol? => /scrape => ent?"
    ),
    "/index": OperatorDef(
        symbol="/index",
        name="Index Content",
        category=OperatorCategory.COMMAND,
        description="Index scraped content into search stores",
        applies_to=["@SOURCE", "@DOMAIN"],
        example="/scrape :#sources => /index"
    ),
    "/brute": OperatorDef(
        symbol="/brute",
        name="Brute Search",
        category=OperatorCategory.COMMAND,
        description="Search entity across 40+ engines to find URL mentions",
        applies_to=["@PERSON", "@COMPANY", "@SUBJECT", "*"],
        supports_bulk=True,
        supports_filters=True,
        example="#john_smith => /brute{de!}"
    ),
    "/submarine": OperatorDef(
        symbol="/submarine",
        name="Submarine Discovery",
        category=OperatorCategory.COMMAND,
        description="Discovery orchestrator (definitional, domain sets/websets, inurl/indom, corpus indices, Atlas ranking/backlinks)",
        applies_to=["*"],
        chainable=True,
        example='/submarine [offshore registries] cy!'
    ),
    "/clink": OperatorDef(
        symbol="/clink",
        name="Clink (N×N Compare)",
        category=OperatorCategory.COMMAND,
        description="Compare all selected entities pairwise, find connections",
        applies_to=["@PERSON", "@COMPANY", "@SUBJECT", "*"],
        supports_bulk=True,
        chainable=True,
        example="(#john AND #jane AND #acme) => /clink"
    ),
    "/tr": OperatorDef(
        symbol="/tr",
        name="Translate",
        category=OperatorCategory.COMMAND,
        description="Translate to language - attach code: /trde, /trfr, /trru",
        applies_to=["*"],
        chainable=True,
        example="/trde :#query"
    ),

    # ------------- Watcher Operators (standing surveillance) -------------
    "/watcher": OperatorDef(
        symbol="/watcher",
        name="Watcher",
        category=OperatorCategory.WATCHER,
        description="Create standing surveillance - AI question evaluated against each search result",
        applies_to=["*"],
        supports_bulk=True,
        chainable=False,
        example="/watcher +##mentions fraud or misconduct"
    ),

    # ------------- TLD Filter Operators -------------
    "de!": OperatorDef(
        symbol="de!",
        name="German TLD Filter",
        category=OperatorCategory.TLD_FILTER,
        description="Restrict to .de domains",
        applies_to=["*"],
        example='brute{"GmbH" AND de!}'
    ),
    "uk!": OperatorDef(
        symbol="uk!",
        name="UK TLD Filter",
        category=OperatorCategory.TLD_FILTER,
        description="Restrict to .uk and .co.uk domains",
        applies_to=["*"],
        example='brute{"Ltd" AND uk!}'
    ),
    "us!": OperatorDef(
        symbol="us!",
        name="US TLD Filter",
        category=OperatorCategory.TLD_FILTER,
        description="Restrict to .us, .com, .gov domains",
        applies_to=["*"],
        example='brute{"LLC" AND us!}'
    ),
    "com!": OperatorDef(
        symbol="com!",
        name="Commercial TLD Filter",
        category=OperatorCategory.TLD_FILTER,
        description="Restrict to .com domains",
        applies_to=["*"],
        example='brute{com!}'
    ),
    "gov!": OperatorDef(
        symbol="gov!",
        name="Government TLD Filter",
        category=OperatorCategory.TLD_FILTER,
        description="Restrict to government domains (.gov, .gov.*)",
        applies_to=["*"],
        example='brute{gov!}'
    ),
    "news!": OperatorDef(
        symbol="news!",
        name="News Sources Filter",
        category=OperatorCategory.TLD_FILTER,
        description="Restrict to news domains (uses news-specific engines)",
        applies_to=["*"],
        example='brute{news!}'
    ),
    "ru!": OperatorDef(
        symbol="ru!",
        name="Russian TLD Filter",
        category=OperatorCategory.TLD_FILTER,
        description="Restrict to .ru domains",
        applies_to=["*"],
        example='brute{ru!}'
    ),
    "cy!": OperatorDef(
        symbol="cy!",
        name="Cyprus TLD Filter",
        category=OperatorCategory.TLD_FILTER,
        description="Restrict to .cy and .com.cy domains",
        applies_to=["*"],
        example='brute{cy!}'
    ),

    # ------------- Aliases for /clink -------------
    "🤝": OperatorDef(
        symbol="🤝",
        name="Clink (emoji alias)",
        category=OperatorCategory.COMMAND,
        description="Alias for /clink - N×N pairwise comparison",
        applies_to=["@PERSON", "@COMPANY", "@SUBJECT", "*"],
        supports_bulk=True,
        chainable=True,
        example="(#john AND #jane AND #acme) => 🤝"
    ),
    "🍺": OperatorDef(
        symbol="🍺",
        name="Clink (emoji alias)",
        category=OperatorCategory.COMMAND,
        description="Alias for /clink - clinking beers together",
        applies_to=["@PERSON", "@COMPANY", "@SUBJECT", "*"],
        supports_bulk=True,
        chainable=True,
        example="(#node1 AND #node2 AND #node3) => 🍺"
    ),
}


# =============================================================================
# CLASS DEFINITIONS
# =============================================================================

# CLASSES (CAPITALISED) and types (lowercase)
CLASS_HIERARCHY: Dict[str, List[str]] = {
    # CLASSES (CAPITALISED)
    "@SUBJECT": ["@person", "@company", "@asset"],
    "@SOURCE": ["@document", "@domain"],
    "@NEXUS": ["@query"],
    "@NARRATIVE": ["@narrative"],
    "@LOCATION": ["@location", "@jurisdiction"],
    # types (lowercase)
    "@person": ["@person"],
    "@company": ["@company"],
    "@asset": ["@asset"],
    "@document": ["@document"],
    "@domain": ["@domain"],
    "@query": ["@query"],
    "@narrative": ["@narrative"],
    "@location": ["@location"],
    "@jurisdiction": ["@jurisdiction"],
    "@email": ["@email"],
    "@phone": ["@phone"],
    "@address": ["@address"],
    "@username": ["@username"],
    "@tag": ["@tag"],
    # Short forms for CLASSES
    "@S": ["@person", "@company", "@asset"],  # @SUBJECT
    "@X": ["@query"],  # @NEXUS
    "@N": ["@narrative"],  # @NARRATIVE
    "@L": ["@location", "@jurisdiction"],  # @LOCATION
    "@SRC": ["@document", "@domain"],  # @SOURCE
    # Short forms for types
    "@p": ["@person"],
    "@c": ["@company"],
    "@a": ["@asset"],
    "@doc": ["@document"],
    "@dom": ["@domain"],
    "@q": ["@query"],
    "@e": ["@email"],
    "@t": ["@phone"],
    "@a": ["@address"],
    "@u": ["@username"],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_operator(symbol: str) -> Optional[OperatorDef]:
    """Get operator definition by symbol."""
    return OPERATORS.get(symbol)


def get_operators_by_category(category: OperatorCategory) -> List[OperatorDef]:
    """Get all operators in a category."""
    return [op for op in OPERATORS.values() if op.category == category]


def get_applicable_operators(node_class: str) -> List[OperatorDef]:
    """Get operators that can act on a specific node class."""
    result = []
    for op in OPERATORS.values():
        if "*" in op.applies_to or node_class in op.applies_to:
            result.append(op)
    return result


def expand_class(class_filter: str) -> Set[str]:
    """Expand a class filter to its concrete classes."""
    normalized = class_filter.upper()
    if not normalized.startswith("@"):
        normalized = f"@{normalized}"
    return set(CLASS_HIERARCHY.get(normalized, [normalized]))


def operator_applies_to(operator: str, node_class: str) -> bool:
    """Check if an operator can act on a node class."""
    op = get_operator(operator)
    if not op:
        return False
    if "*" in op.applies_to:
        return True
    # Expand the node class
    expanded = expand_class(node_class)
    return bool(expanded & set(op.applies_to))


# Pattern list for parsing (order matters - longer patterns first)
OPERATOR_PATTERNS: List[str] = [
    # Extraction operators - full forms (lowercase)
    "@entity?", "@person?", "@company?", "@email?", "@phone?", "@address?", "@username?",
    # Extraction operators - short forms (lowercase)
    "@ent?", "@p?", "@c?", "@e?", "@t?", "@a?", "@u?",
    # Filetype operators
    "word!", "file!", "pdf!", "doc!", "xls!", "ppt!",
    "document!", "spreadsheet!", "presentation!", "text!",
    "image!", "audio!", "video!", "media!", "archive!", "code!",
    "@doc?", "@file?", "@document?", "@spreadsheet?", "@presentation?", "@text?",
    "@image?", "@audio?", "@video?", "@media?", "@archive?", "@code?",
    # Link analysis
    "?bl", "bl?", "?ol", "ol?",
    # Compare
    "=?",
    # Query operators (search FOR results)
    "sanctions?", "registry?", "whois?",
    # Command operators (imperative - DO THIS)
    "/enrich", "/scrape", "/index", "/brute", "/submarine", "/clink", "/tr",
    # Watcher operator (standing surveillance)
    "/watcher",
    # Emoji aliases for /clink
    "🤝", "🍺",
    # TLD filters (used inside {} or as modifiers)
    "de!", "uk!", "us!", "com!", "gov!", "news!", "ru!", "cy!",
]

# Sort by length descending for parsing
OPERATOR_PATTERNS.sort(key=len, reverse=True)


# =============================================================================
# TLD FILTER MAPPINGS
# =============================================================================

TLD_FILTER_TO_SITES: Dict[str, List[str]] = {
    "de!": ["site:.de"],
    "uk!": ["site:.uk", "site:.co.uk"],
    "us!": ["site:.us", "site:.gov"],
    "com!": ["site:.com"],
    "gov!": ["site:.gov", "site:.gov.*"],
    "ru!": ["site:.ru"],
    "cy!": ["site:.cy", "site:.com.cy"],
    "news!": [],  # Special: uses news engine tier instead
}

TLD_FILTER_ENGINE_TIERS: Dict[str, List[str]] = {
    "news!": ["NewsAPI", "GDELT", "Google News", "Bing News"],
}


def get_tld_site_filters(tld_filter: str) -> List[str]:
    """Get site: filters for a TLD filter operator."""
    return TLD_FILTER_TO_SITES.get(tld_filter, [])


def get_tld_engine_tiers(tld_filter: str) -> List[str]:
    """Get specific engine tiers for a TLD filter (e.g., news!)."""
    return TLD_FILTER_ENGINE_TIERS.get(tld_filter, [])


# =============================================================================
# FILETYPE MAPPINGS
# =============================================================================

FILETYPE_EXTENSIONS: Dict[str, Set[str]] = {
    "pdf!": {"pdf"},
    "word!": {"doc", "docx", "odt", "rtf"},
    "xls!": {"xls", "xlsx", "ods", "csv"},
    "ppt!": {"ppt", "pptx", "odp"},
    "doc!": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "rtf", "txt"},
    "file!": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "rtf", "txt", "ods", "csv", "odp"},
    "document!": {"pdf", "doc", "docx", "odt", "rtf", "txt", "pages", "wpd"},
    "spreadsheet!": {"xls", "xlsx", "ods", "csv", "numbers", "tsv"},
    "presentation!": {"ppt", "pptx", "odp", "key"},
    "text!": {"txt", "rtf", "log", "md", "rst", "tex", "json", "xml", "yaml", "yml", "csv", "tsv", "sql", "ini", "cfg"},
    "image!": {"jpg", "jpeg", "png", "gif", "bmp", "svg", "tiff", "tif", "webp", "ico", "psd", "ai", "eps", "raw", "heic"},
    "audio!": {"mp3", "wav", "aac", "flac", "ogg", "wma", "m4a", "opus", "aiff", "au", "ra"},
    "video!": {"mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "ogv", "m4v", "3gp", "mpg", "mpeg", "vob", "ts", "mts"},
    "media!": {"jpg", "jpeg", "png", "gif", "bmp", "svg", "tiff", "webp", "mp3", "wav", "aac", "flac", "ogg", "mp4", "avi", "mkv", "mov", "wmv", "flv", "webm"},
    "archive!": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "cab", "dmg", "iso"},
    "code!": {"py", "js", "java", "cpp", "c", "cs", "rb", "go", "php", "swift", "kt", "html", "css", "sh", "ts", "jsx", "tsx", "vue", "scss", "less", "sql", "r", "scala", "rust", "dart", "lua"},
    "@doc?": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "rtf", "txt"},
    "@file?": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "rtf", "txt", "ods", "csv", "odp"},
    "@document?": {"pdf", "doc", "docx", "odt", "rtf", "txt", "pages", "wpd"},
    "@spreadsheet?": {"xls", "xlsx", "ods", "csv", "numbers", "tsv"},
    "@presentation?": {"ppt", "pptx", "odp", "key"},
    "@text?": {"txt", "rtf", "log", "md", "rst", "tex", "json", "xml", "yaml", "yml", "csv", "tsv", "sql", "ini", "cfg"},
    "@image?": {"jpg", "jpeg", "png", "gif", "bmp", "svg", "tiff", "tif", "webp", "ico", "psd", "ai", "eps", "raw", "heic"},
    "@audio?": {"mp3", "wav", "aac", "flac", "ogg", "wma", "m4a", "opus", "aiff", "au", "ra"},
    "@video?": {"mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "ogv", "m4v", "3gp", "mpg", "mpeg", "vob", "ts", "mts"},
    "@media?": {"jpg", "jpeg", "png", "gif", "bmp", "svg", "tiff", "webp", "mp3", "wav", "aac", "flac", "ogg", "mp4", "avi", "mkv", "mov", "wmv", "flv", "webm"},
    "@archive?": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "cab", "dmg", "iso"},
    "@code?": {"py", "js", "java", "cpp", "c", "cs", "rb", "go", "php", "swift", "kt", "html", "css", "sh", "ts", "jsx", "tsx", "vue", "scss", "less", "sql", "r", "scala", "rust", "dart", "lua"},
}


def get_filetype_extensions(operator: str) -> Set[str]:
    """Get file extensions for a filetype operator."""
    return FILETYPE_EXTENSIONS.get(operator, set())


# =============================================================================
# ENTITY TYPE MAPPINGS
# =============================================================================

ENTITY_OPERATOR_TO_TYPE: Dict[str, str] = {
    # Full forms (lowercase)
    "@person?": "person",
    "@company?": "company",
    "@email?": "email",
    "@phone?": "phone",
    "@address?": "address",
    "@username?": "username",
    # Short forms (lowercase)
    "@p?": "person",
    "@c?": "company",
    "@e?": "email",
    "@t?": "phone",
    "@a?": "address",
    "@u?": "username",
}

ENTITY_ALL_OPERATORS: Set[str] = {"@entity?", "@ent?"}

ENTITY_ALL_TYPES: Set[str] = {"person", "company", "email", "phone", "address", "username"}


def get_entity_types(operators: List[str]) -> Set[str]:
    """Get entity types requested by a list of operators."""
    # Check for "extract all" operators
    if any(op in ENTITY_ALL_OPERATORS for op in operators):
        return ENTITY_ALL_TYPES.copy()

    result = set()
    for op in operators:
        if op in ENTITY_OPERATOR_TO_TYPE:
            result.add(ENTITY_OPERATOR_TO_TYPE[op])
    return result


# =============================================================================
# VALIDATION SYSTEM
# =============================================================================

# All valid @ class references (from CLASS_HIERARCHY)
VALID_CLASS_REFERENCES: Set[str] = set(CLASS_HIERARCHY.keys())

# Reminder prompt for invalid @ usage
CLASS_REMINDER = """BLOCKED: Invalid @ reference.

@ is ONLY for node type classes:
  @SUBJECT, @ENTITY, @PERSON, @COMPANY, @ASSET
  @SOURCE, @DOCUMENT, @DOMAIN
  @QUERY, @NARRATIVE, @LOCATION, @JURISDICTION, @TAG

For data references use TAGS:
  +#tagname - save/tag output
  :#tagname - reference saved tag

NOT {variable} template syntax.
"""


def validate_class(token: str) -> Optional[str]:
    """
    Validate @ reference. Returns None if valid, reminder prompt if invalid.
    """
    if not token.startswith("@"):
        return None

    if token.upper() in VALID_CLASS_REFERENCES:
        return None

    return f"BLOCKED: '{token}' is not a valid class.\n\n{CLASS_REMINDER}"


def validate_chain(chain: str) -> Optional[str]:
    """
    Validate operator chain. Returns None if valid, reminder prompt if invalid.
    """
    import re

    # Find @ references
    refs = re.findall(r'@[A-Za-z_]+', chain)
    for ref in refs:
        error = validate_class(ref)
        if error:
            return error

    return None


# =============================================================================
# WATCHER SYNTAX PARSER
# =============================================================================

@dataclass
class WatcherContext:
    """Context configuration for a watcher."""
    nodes: List[str]           # #node references
    text: Optional[str]        # Custom text prompt
    same_header: bool = False  # Include findings from same header in run
    same_run: bool = False     # Include all findings from current run


@dataclass
class WatcherCondition:
    """Conditional configuration for a watcher."""
    query_pattern: Optional[str] = None   # Only for queries matching pattern
    section: Optional[str] = None         # Only under specific section
    criteria: Dict[str, str] = None       # Key-value criteria (e.g., jurisdiction=UK)

    def __post_init__(self):
        if self.criteria is None:
            self.criteria = {}


@dataclass
class WatcherSpec:
    """Parsed watcher specification."""
    action: str                           # "add", "import", "on", "off", "pause", "resume"
    headers: List[str]                    # Header texts (for add/create)
    note_ref: Optional[str] = None        # Note reference (for import)
    context: Optional[WatcherContext] = None
    condition: Optional[WatcherCondition] = None


class WatcherParser:
    """
    Parser for /watcher command syntax.

    Syntax:
        /watcher +##Header
        /watcher add ##Header
        /watcher create ##A, ##B, ##C
        /watcher import #note_name
        /watcher on ##Header
        /watcher off ##Header
        /watcher +##Header context{#entity, "text"}
        /watcher +##Header IF query:"cuk:*" THEN context{#target}
    """

    # Action keywords that mean "add/create"
    ADD_ACTIONS = {"+", "add", "create"}
    TOGGLE_ACTIONS = {"on", "off", "pause", "resume"}

    def __init__(self):
        import re
        self.re = re

    def parse(self, syntax: str) -> Optional[WatcherSpec]:
        """
        Parse watcher syntax string.

        Args:
            syntax: Full watcher command string (without /watcher prefix)

        Returns:
            WatcherSpec or None if invalid
        """
        syntax = syntax.strip()

        # Check for import action
        if syntax.startswith("import "):
            return self._parse_import(syntax[7:].strip())

        # Check for toggle actions
        for action in self.TOGGLE_ACTIONS:
            if syntax.startswith(f"{action} "):
                return self._parse_toggle(action, syntax[len(action)+1:].strip())

        # Check for add/create actions
        for action in self.ADD_ACTIONS:
            if syntax.startswith(f"{action} ") or syntax.startswith(f"{action}#"):
                rest = syntax[len(action):].strip()
                return self._parse_add(rest)

        return None

    def _parse_import(self, rest: str) -> WatcherSpec:
        """Parse import syntax: import #note_name"""
        note_ref = rest.strip()
        if note_ref.startswith("#"):
            note_ref = note_ref[1:]
        return WatcherSpec(action="import", headers=[], note_ref=note_ref)

    def _parse_toggle(self, action: str, rest: str) -> WatcherSpec:
        """Parse toggle syntax: on/off ##Header"""
        headers = self._extract_headers(rest)
        return WatcherSpec(action=action, headers=headers)

    def _parse_add(self, rest: str) -> WatcherSpec:
        """Parse add/create syntax with optional context and conditions."""
        # Check for IF...THEN conditional
        condition = None
        context = None

        if " IF " in rest.upper():
            parts = self.re.split(r'\s+IF\s+', rest, maxsplit=1, flags=self.re.IGNORECASE)
            rest = parts[0]
            condition_str = parts[1] if len(parts) > 1 else ""

            # Parse THEN if present
            if " THEN " in condition_str.upper():
                cond_parts = self.re.split(r'\s+THEN\s+', condition_str, maxsplit=1, flags=self.re.IGNORECASE)
                condition = self._parse_condition(cond_parts[0])
                if len(cond_parts) > 1:
                    context = self._parse_context(cond_parts[1])
            else:
                condition = self._parse_condition(condition_str)

        # Check for context{...} without IF/THEN
        if context is None and "context{" in rest.lower():
            ctx_match = self.re.search(r'context\{([^}]*)\}', rest, self.re.IGNORECASE)
            if ctx_match:
                context = self._parse_context(ctx_match.group(0))
                rest = rest[:ctx_match.start()].strip()

        # Extract headers
        headers = self._extract_headers(rest)

        return WatcherSpec(
            action="add",
            headers=headers,
            context=context,
            condition=condition
        )

    def _extract_headers(self, text: str) -> List[str]:
        """Extract ##header entries from text."""
        # Split by comma for multiple headers
        parts = text.split(",")
        headers = []

        for part in parts:
            part = part.strip()
            # Remove leading ## if present
            if part.startswith("##"):
                part = part[2:].strip()
            elif part.startswith("#"):
                part = part[1:].strip()
            if part:
                headers.append(part)

        return headers

    def _parse_context(self, ctx_str: str) -> WatcherContext:
        """Parse context{...} specification."""
        # Extract content inside context{...}
        match = self.re.search(r'context\{([^}]*)\}', ctx_str, self.re.IGNORECASE)
        if not match:
            return WatcherContext(nodes=[], text=None)

        content = match.group(1).strip()
        nodes = []
        text = None
        same_header = False
        same_run = False

        # Parse comma-separated items
        items = self._split_context_items(content)

        for item in items:
            item = item.strip()
            if item.startswith("#"):
                nodes.append(item[1:])  # Remove # prefix
            elif item.startswith('"') and item.endswith('"'):
                text = item[1:-1]  # Remove quotes
            elif item == "same_header":
                same_header = True
            elif item == "same_run":
                same_run = True

        return WatcherContext(
            nodes=nodes,
            text=text,
            same_header=same_header,
            same_run=same_run
        )

    def _split_context_items(self, content: str) -> List[str]:
        """Split context items, respecting quoted strings."""
        items = []
        current = ""
        in_quotes = False

        for char in content:
            if char == '"':
                in_quotes = not in_quotes
                current += char
            elif char == "," and not in_quotes:
                if current.strip():
                    items.append(current.strip())
                current = ""
            else:
                current += char

        if current.strip():
            items.append(current.strip())

        return items

    def _parse_condition(self, cond_str: str) -> WatcherCondition:
        """Parse condition specification."""
        condition = WatcherCondition()

        # Check for query pattern: query:"pattern"
        query_match = self.re.search(r'query:\s*["\']([^"\']+)["\']', cond_str)
        if query_match:
            condition.query_pattern = query_match.group(1)

        # Check for section: section:## Name
        section_match = self.re.search(r'section:\s*##?\s*([^\s,}]+)', cond_str)
        if section_match:
            condition.section = section_match.group(1)

        # Check for key=value criteria
        criteria_matches = self.re.findall(r'(\w+)\s*=\s*(\w+)', cond_str)
        for key, value in criteria_matches:
            if key not in ("query", "section"):
                condition.criteria[key] = value

        return condition


# Singleton parser instance
_watcher_parser = None


def get_watcher_parser() -> WatcherParser:
    """Get singleton watcher parser instance."""
    global _watcher_parser
    if _watcher_parser is None:
        _watcher_parser = WatcherParser()
    return _watcher_parser


def parse_watcher_command(command: str) -> Optional[WatcherSpec]:
    """
    Parse a /watcher command.

    Args:
        command: Full command string starting with /watcher

    Returns:
        WatcherSpec or None if invalid

    Examples:
        parse_watcher_command("/watcher +##mentions fraud")
        parse_watcher_command("/watcher add ##Officers context{#Acme_Corp}")
        parse_watcher_command("/watcher +##Fraud IF jurisdiction=UK THEN context{#company}")
        parse_watcher_command("/watcher import #investigation_template")
        parse_watcher_command("/watcher on ##Corporate Officers")
    """
    if not command.startswith("/watcher"):
        return None

    rest = command[8:].strip()  # Remove "/watcher"
    return get_watcher_parser().parse(rest)
