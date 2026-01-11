"""
SeekLeech Engine v2.0 - Schema Definitions

Dataclasses for enhanced source metadata, input/output schemas,
and structured extraction results.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime


# ─────────────────────────────────────────────────────────────
# Input Schema - What {q} accepts
# ─────────────────────────────────────────────────────────────

@dataclass
class InputSchema:
    """
    Describes what input a search template accepts.
    Critical for automation - knowing format constraints.
    """
    input_type: str = "company_name"  # company_name, person_name, reg_id, case_number, address, date_range
    format: str = "free_text"  # free_text, numeric, alphanumeric, formatted
    format_pattern: Optional[str] = None  # Regex pattern e.g., r"^\d{8}$" for 8-digit IDs
    examples: List[str] = field(default_factory=list)  # ["12345678", "ABC-123"]
    accepts_wildcards: bool = False  # True if * or % work
    case_sensitive: bool = False
    max_length: Optional[int] = None
    min_length: Optional[int] = None
    encoding: str = "utf-8"  # utf-8, latin-1, url-encoded
    requires_translation: bool = False  # True if local language input required

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> 'InputSchema':
        return cls(
            input_type=d.get("input_type", "company_name"),
            format=d.get("format", "free_text"),
            format_pattern=d.get("format_pattern"),
            examples=d.get("examples", []),
            accepts_wildcards=d.get("accepts_wildcards", False),
            case_sensitive=d.get("case_sensitive", False),
            max_length=d.get("max_length"),
            min_length=d.get("min_length"),
            encoding=d.get("encoding", "utf-8"),
            requires_translation=d.get("requires_translation", False)
        )


# ─────────────────────────────────────────────────────────────
# Output Schema - What the source returns
# ─────────────────────────────────────────────────────────────

@dataclass
class OutputField:
    """A single field in the output schema."""
    name: str  # company_name, registration_number, status, etc.
    field_code: int = 0  # Maps to Matrix field codes (13=company_name, 43=reg_id)
    css_selector: Optional[str] = None  # Where to find in HTML
    json_path: Optional[str] = None  # JSONPath if API response
    example_value: str = ""  # "ABC Corporation"
    data_type: str = "string"  # string, number, date, boolean
    always_present: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class OutputSchema:
    """
    What the source returns - learned from experimentation.
    Used for structured extraction.
    """
    result_type: str = "table"  # table, list, single_record, pdf, json_api, cards
    pagination: bool = False  # Does it paginate?
    max_results_per_page: int = 25

    fields: List[OutputField] = field(default_factory=list)

    # Extraction hints (CSS selectors)
    results_container: Optional[str] = None  # Container for all results
    table_selector: Optional[str] = None  # CSS selector for results table
    row_selector: Optional[str] = None  # CSS selector for each result row

    # For JSON APIs
    json_results_path: Optional[str] = None  # JSONPath to results array

    # Sample data (anonymized)
    sample_structure: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['fields'] = [f.to_dict() if hasattr(f, 'to_dict') else f for f in self.fields]
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> 'OutputSchema':
        # Parse fields with flexible key mapping
        fields = []
        for f in d.get("fields", []):
            if isinstance(f, dict):
                fields.append(OutputField(
                    name=f.get("name", ""),
                    field_code=f.get("field_code", 0),
                    css_selector=f.get("css_selector"),
                    json_path=f.get("json_path"),
                    example_value=f.get("example_value") or f.get("example", ""),
                    data_type=f.get("data_type", "string"),
                    always_present=f.get("always_present", False),
                ))
            else:
                fields.append(f)
        return cls(
            result_type=d.get("result_type", "table"),
            pagination=d.get("pagination", False),
            max_results_per_page=d.get("max_results_per_page", 25),
            fields=fields,
            results_container=d.get("results_container"),
            table_selector=d.get("table_selector"),
            row_selector=d.get("row_selector"),
            json_results_path=d.get("json_results_path"),
            sample_structure=d.get("sample_structure", {})
        )


# ─────────────────────────────────────────────────────────────
# Reliability Metrics
# ─────────────────────────────────────────────────────────────

@dataclass
class ReliabilityMetrics:
    """Tracks source health over time."""
    success_rate: float = 0.0  # 0.0 - 1.0
    avg_latency: float = 0.0  # seconds
    last_tested: str = ""  # ISO timestamp
    test_count: int = 0
    consecutive_failures: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> 'ReliabilityMetrics':
        return cls(
            success_rate=d.get("success_rate", 0.0),
            avg_latency=d.get("avg_latency", 0.0),
            last_tested=d.get("last_tested", ""),
            test_count=d.get("test_count", 0),
            consecutive_failures=d.get("consecutive_failures", 0),
            last_error=d.get("last_error")
        )

    def record_success(self, latency: float):
        """Record a successful request."""
        self.test_count += 1
        self.consecutive_failures = 0
        # Rolling average
        self.avg_latency = (self.avg_latency * (self.test_count - 1) + latency) / self.test_count
        self.success_rate = (self.success_rate * (self.test_count - 1) + 1.0) / self.test_count
        self.last_tested = datetime.now().isoformat()
        self.last_error = None

    def record_failure(self, error: str):
        """Record a failed request."""
        self.test_count += 1
        self.consecutive_failures += 1
        self.success_rate = (self.success_rate * (self.test_count - 1) + 0.0) / self.test_count
        self.last_tested = datetime.now().isoformat()
        self.last_error = error


# ─────────────────────────────────────────────────────────────
# Enhanced Source - The full schema for sources_v3.json
# ─────────────────────────────────────────────────────────────

@dataclass
class EnhancedSource:
    """
    Full enhanced source with I/O schemas.
    This is what sources_v3.json contains.
    """
    # Core identifiers
    id: str
    domain: str
    jurisdiction: str
    url: str
    name: str = ""

    # Templates
    search_template: Optional[str] = None  # URL with {q} placeholder
    search_page: Optional[str] = None  # Form-based search (no template)

    # Classification
    section: str = "cr"  # cr=corporate, lit=litigation, reg=regulatory, at=asset, misc
    type: str = "corporate_registry"  # Specific type within section
    thematic_tags: List[str] = field(default_factory=list)  # ["corporate_registry", "officers"]

    # Access
    access: str = "public"  # public, paywalled, registration, restricted
    requires_browser: bool = False  # True if POST form or JS-heavy

    # Language & Localization
    language: str = "en"
    requires_translation: bool = False

    # I/O Schemas (NEW in v3)
    input_schema: Optional[InputSchema] = None
    output_schema: Optional[OutputSchema] = None

    # Reliability (NEW in v3)
    reliability: Optional[ReliabilityMetrics] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        d = {
            "id": self.id,
            "domain": self.domain,
            "jurisdiction": self.jurisdiction,
            "url": self.url,
            "name": self.name,
            "search_template": self.search_template,
            "search_page": self.search_page,
            "section": self.section,
            "type": self.type,
            "thematic_tags": self.thematic_tags,
            "access": self.access,
            "requires_browser": self.requires_browser,
            "language": self.language,
            "requires_translation": self.requires_translation,
            "input_schema": self.input_schema.to_dict() if self.input_schema else None,
            "output_schema": self.output_schema.to_dict() if self.output_schema else None,
            "reliability": self.reliability.to_dict() if self.reliability else None,
            "metadata": self.metadata
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> 'EnhancedSource':
        return cls(
            id=d.get("id", d.get("domain", "")),
            domain=d.get("domain", ""),
            jurisdiction=d.get("jurisdiction", ""),
            url=d.get("url", ""),
            name=d.get("name", ""),
            search_template=d.get("search_template"),
            search_page=d.get("search_page"),
            section=d.get("section", "cr"),
            type=d.get("type", "corporate_registry"),
            thematic_tags=d.get("thematic_tags", []),
            access=d.get("access", "public"),
            requires_browser=d.get("requires_browser", False),
            language=d.get("language", "en"),
            requires_translation=d.get("requires_translation", False),
            input_schema=InputSchema.from_dict(d["input_schema"]) if d.get("input_schema") else None,
            output_schema=OutputSchema.from_dict(d["output_schema"]) if d.get("output_schema") else None,
            reliability=ReliabilityMetrics.from_dict(d["reliability"]) if d.get("reliability") else None,
            metadata=d.get("metadata", {})
        )

    def score(self) -> float:
        """
        Calculate source quality score for ranking.
        Higher is better.
        """
        if not self.reliability:
            return 0.5  # No data, neutral score

        # Base score from success rate
        score = self.reliability.success_rate

        # Penalize slow sources
        if self.reliability.avg_latency > 5.0:
            score *= 0.8
        elif self.reliability.avg_latency > 10.0:
            score *= 0.5

        # Penalize consecutive failures
        if self.reliability.consecutive_failures > 3:
            score *= 0.5
        elif self.reliability.consecutive_failures > 5:
            score *= 0.1

        return score


# ─────────────────────────────────────────────────────────────
# Experiment Result
# ─────────────────────────────────────────────────────────────

@dataclass
class ExperimentResult:
    """Result of experimenting with a source."""
    source_id: str
    success: bool
    output_schema: Optional[OutputSchema] = None
    input_schema: Optional[InputSchema] = None  # Refined input schema
    thematic_tags: List[str] = field(default_factory=list)

    # Metrics from experiment
    success_rate: float = 0.0
    avg_latency: float = 0.0

    # Samples (for debugging)
    sample_responses: List[Dict] = field(default_factory=list)

    # Timing
    tested_at: str = ""
    notes: str = ""

    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id,
            "success": self.success,
            "output_schema": self.output_schema.to_dict() if self.output_schema else None,
            "input_schema": self.input_schema.to_dict() if self.input_schema else None,
            "thematic_tags": self.thematic_tags,
            "success_rate": self.success_rate,
            "avg_latency": self.avg_latency,
            "sample_responses": self.sample_responses,
            "tested_at": self.tested_at,
            "notes": self.notes
        }


# ─────────────────────────────────────────────────────────────
# Structured Extraction Result
# ─────────────────────────────────────────────────────────────

@dataclass
class StructuredResult:
    """A single extracted record from a source."""
    source_id: str
    source_url: str
    query: str

    # Extracted data
    fields: Dict[str, Any] = field(default_factory=dict)  # Extracted field values
    field_codes: Dict[str, int] = field(default_factory=dict)  # Maps to Matrix field codes

    # Quality indicators
    confidence: float = 1.0
    match_score: float = 0.0  # How well it matches the query

    # Debug
    raw_html: Optional[str] = None
    extracted_at: str = ""

    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id,
            "source_url": self.source_url,
            "query": self.query,
            "fields": self.fields,
            "field_codes": self.field_codes,
            "confidence": self.confidence,
            "match_score": self.match_score,
            "extracted_at": self.extracted_at
        }


@dataclass
class SearchResponse:
    """Response from SeekLeech executor search."""
    query: str
    input_type: str
    jurisdiction: str

    # Results
    results: List[StructuredResult] = field(default_factory=list)

    # Metadata
    sources_queried: int = 0
    sources_succeeded: int = 0
    total_results: int = 0

    # Timing
    total_latency: float = 0.0
    started_at: str = ""
    completed_at: str = ""

    # Errors
    errors: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "query": self.query,
            "input_type": self.input_type,
            "jurisdiction": self.jurisdiction,
            "results": [r.to_dict() for r in self.results],
            "sources_queried": self.sources_queried,
            "sources_succeeded": self.sources_succeeded,
            "total_results": self.total_results,
            "total_latency": self.total_latency,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "errors": self.errors
        }


# ─────────────────────────────────────────────────────────────
# Field Code Mappings (Matrix compatibility)
# ─────────────────────────────────────────────────────────────

FIELD_CODES = {
    # Entity identifiers
    "company_name": 13,
    "company_reg_id": 43,
    "person_name": 7,
    "email": 1,
    "phone": 2,
    "domain": 6,
    "address": 8,

    # Company fields
    "company_status": 201,
    "company_type": 202,
    "incorporation_date": 203,
    "registered_address": 204,
    "company_officers": 58,
    "beneficial_owners": 66,
    "shareholders": 67,

    # Financial
    "capital": 210,
    "revenue": 211,
    "employees": 212,

    # Legal
    "court_case_number": 220,
    "judgment_date": 221,
    "filing_date": 222,

    # Property
    "property_address": 230,
    "property_owner": 231,
    "property_value": 232
}

def get_field_code(field_name: str) -> int:
    """Get Matrix field code for a field name."""
    # Normalize name
    normalized = field_name.lower().replace(" ", "_").replace("-", "_")
    return FIELD_CODES.get(normalized, 0)
