"""
SASTRE Query Lab - Match + Test + Fuse methodology with K-U Matrix Axis Distinction.

FUNDAMENTAL ARCHITECTURE:
=========================

The K-U Matrix has TWO AXES that must be distinguished:

LOCATION AXIS (X) - STATIC:
    Borders don't move. Jurisdictions are fixed. Domains have owners.
    - Jurisdiction: country, state, legal zone
    - Domain: website, source URL, registry
    - Temporal-Location: date of record, archive snapshot year
    - Physical: address, coordinates, postal code
    - Format: document type, source category

SUBJECT AXIS (Y) - DYNAMIC:
    People move. Companies merge. Entities evolve.
    - Identity: name, aliases, transliterations
    - Identifiers: SSN, tax ID, OIB, registration number
    - Temporal-Subject: DOB, age, incorporation date, active period
    - Attributes: role, profession, status, title
    - Network: relationships, connections, affiliations

CROSS-AXIS RELATIONSHIPS (False Friend Detection):
==================================================

For two entities A and B with the same name:

| Location Match | Subject Match | Verdict | Reason |
|---------------|---------------|---------|--------|
| SAME          | SAME          | FUSE    | Same entity, same context |
| SAME          | DIFFERENT     | REPEL   | Different entities in same place |
| DIFFERENT     | SAME          | FUSE?   | Same entity, different contexts (travels/expands) |
| DIFFERENT     | DIFFERENT     | REPEL   | Completely different entities |

The key insight: CONFLICTING HARD IDENTIFIERS always REPEL, regardless of location.
But SAME LOCATION + DIFFERENT SOFT ATTRIBUTES is the classic "false friend" pattern.

Usage:
    lab = QueryLab()

    # Match operation with axis-aware comparison
    match_result = lab.match(entity_a, entity_b)

    # Test operation
    test_result = lab.test(entity, hypothesis, corpus_results)

    # Fuse operation
    fuse_result = lab.fuse([match_result1, match_result2], [test_result1])
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple, Set
from enum import Enum
import re

from ..contracts import Intent, KUQuadrant
from .variations import VariationGenerator


# =============================================================================
# AXIS-AWARE DIMENSION CLASSIFICATION
# =============================================================================

class Axis(Enum):
    """The two fundamental axes of the K-U Matrix."""
    LOCATION = "location"  # X-axis: Static (where/when/from)
    SUBJECT = "subject"    # Y-axis: Dynamic (who/what)


class LocationDimension(Enum):
    """LOCATION axis dimensions (STATIC - borders don't move)."""
    JURISDICTION = "jurisdiction"       # Country, state, legal zone
    DOMAIN = "domain"                   # Website, source URL, registry
    TEMPORAL_LOCATION = "temporal_loc"  # Date of record, archive year
    PHYSICAL = "physical"               # Address, coordinates
    FORMAT = "format"                   # Document type, source category


class SubjectDimension(Enum):
    """SUBJECT axis dimensions (DYNAMIC - entities evolve)."""
    IDENTITY = "identity"               # Name, aliases
    IDENTIFIER = "identifier"           # Hard IDs: SSN, tax ID, OIB
    TEMPORAL_SUBJECT = "temporal_subj"  # DOB, age, incorporation date
    ATTRIBUTE = "attribute"             # Role, profession, status
    NETWORK = "network"                 # Relationships, connections


class FuseVerdict(Enum):
    """Possible fusion verdicts."""
    FUSE = "fuse"                # Confirmed same entity - merge
    REPEL = "repel"              # Confirmed different entities - separate
    BINARY_STAR = "binary_star"  # Linked but distinct (e.g., family members)
    UNCERTAIN = "uncertain"      # Need more evidence


# =============================================================================
# SCORE DATACLASSES
# =============================================================================

@dataclass
class DimensionScore:
    """Score for a single dimension comparison."""
    axis: Axis
    dimension: str                     # LocationDimension or SubjectDimension value
    score: float                       # 0.0 (conflict) to 1.0 (match)
    confidence: float = 0.8            # How confident in this score
    evidence: List[str] = field(default_factory=list)
    is_hard_identifier: bool = False   # Hard IDs are definitive

    @property
    def weighted_score(self) -> float:
        return self.score * self.confidence


@dataclass
class AxisScore:
    """Aggregated score for an entire axis."""
    axis: Axis
    dimension_scores: List[DimensionScore] = field(default_factory=list)
    overall_score: float = 0.0
    has_conflicts: bool = False
    has_hard_conflict: bool = False  # Definitive mismatch (e.g., different DOB)

    def __post_init__(self):
        if self.dimension_scores:
            self._compute()

    def _compute(self):
        if not self.dimension_scores:
            return

        # Check for hard conflicts first
        for ds in self.dimension_scores:
            if ds.is_hard_identifier and ds.score <= 0.2:
                self.has_hard_conflict = True
            if ds.score <= 0.3 and ds.confidence >= 0.7:
                self.has_conflicts = True

        # Weighted average
        total_weight = sum(d.confidence for d in self.dimension_scores)
        if total_weight > 0:
            self.overall_score = sum(d.weighted_score for d in self.dimension_scores) / total_weight


@dataclass
class MatchResult:
    """Result of matching two entities across both axes."""
    entity_a_id: str
    entity_b_id: str
    location_score: AxisScore = field(default_factory=lambda: AxisScore(axis=Axis.LOCATION))
    subject_score: AxisScore = field(default_factory=lambda: AxisScore(axis=Axis.SUBJECT))
    cross_axis_pattern: str = ""       # Describes the pattern
    suggested_verdict: FuseVerdict = FuseVerdict.UNCERTAIN
    confidence: float = 0.0
    reasoning: str = ""
    notes: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.location_score.dimension_scores or self.subject_score.dimension_scores:
            self._analyze_cross_axis()

    def _analyze_cross_axis(self):
        """Analyze cross-axis patterns for false friend detection."""
        loc = self.location_score
        subj = self.subject_score

        # Pattern detection
        loc_match = loc.overall_score >= 0.6
        loc_conflict = loc.has_conflicts or loc.overall_score <= 0.3
        subj_match = subj.overall_score >= 0.6
        subj_conflict = subj.has_conflicts or subj.overall_score <= 0.3

        # HARD IDENTIFIER CONFLICTS ARE DEFINITIVE
        if subj.has_hard_conflict:
            self.suggested_verdict = FuseVerdict.REPEL
            self.confidence = 0.95
            self.cross_axis_pattern = "HARD_ID_CONFLICT"
            self.reasoning = "Conflicting hard identifiers (DOB, tax ID, etc.) - definitive REPEL"
            return

        if loc.has_hard_conflict:
            # Location hard conflict (same registry, different entities)
            self.suggested_verdict = FuseVerdict.REPEL
            self.confidence = 0.90
            self.cross_axis_pattern = "SAME_SOURCE_DIFFERENT_ENTITY"
            self.reasoning = "Same source contains both as distinct entries - REPEL"
            return

        # CROSS-AXIS PATTERN ANALYSIS
        if loc_match and subj_match:
            # Same location + Same subject = FUSE
            self.cross_axis_pattern = "SAME_LOC_SAME_SUBJ"
            self.suggested_verdict = FuseVerdict.FUSE
            self.confidence = min(0.9, (loc.overall_score + subj.overall_score) / 2)
            self.reasoning = "Matching location and subject attributes - likely same entity"

        elif loc_match and subj_conflict:
            # Same location + Different subject = FALSE FRIEND (REPEL)
            self.cross_axis_pattern = "SAME_LOC_DIFF_SUBJ"
            self.suggested_verdict = FuseVerdict.REPEL
            self.confidence = 0.85
            self.reasoning = "Same location context but conflicting subject attributes - FALSE FRIEND"

        elif loc_conflict and subj_match:
            # Different location + Same subject = Possible FUSE (entity in multiple places)
            self.cross_axis_pattern = "DIFF_LOC_SAME_SUBJ"
            self.suggested_verdict = FuseVerdict.FUSE
            self.confidence = 0.7
            self.reasoning = "Subject attributes match across different locations - same entity, different contexts"

        elif loc_conflict and subj_conflict:
            # Different location + Different subject = REPEL
            self.cross_axis_pattern = "DIFF_LOC_DIFF_SUBJ"
            self.suggested_verdict = FuseVerdict.REPEL
            self.confidence = 0.8
            self.reasoning = "Different location and subject - distinct entities"

        else:
            # Mixed signals - check for binary star pattern
            if self._check_binary_star_pattern():
                self.cross_axis_pattern = "BINARY_STAR"
                self.suggested_verdict = FuseVerdict.BINARY_STAR
                self.confidence = 0.6
                self.reasoning = "Related but distinct entities (e.g., family members, subsidiaries)"
            else:
                self.cross_axis_pattern = "UNCERTAIN"
                self.suggested_verdict = FuseVerdict.UNCERTAIN
                self.confidence = 0.3
                self.reasoning = "Insufficient evidence to determine relationship"

    def _check_binary_star_pattern(self) -> bool:
        """Check for binary star pattern: related but distinct entities."""
        # Binary star indicators:
        # - Same surname, different first name
        # - Same company group, different subsidiary
        # - Same address, different unit/apartment
        # - Overlapping network connections

        subj_scores = self.subject_score.dimension_scores
        for ds in subj_scores:
            if ds.dimension == SubjectDimension.NETWORK.value and ds.score >= 0.5:
                # Shared network connections suggest relationship
                return True
            if ds.dimension == SubjectDimension.IDENTITY.value:
                # Check for partial name match
                evidence_str = " ".join(ds.evidence)
                if "partial" in evidence_str.lower() or "surname" in evidence_str.lower():
                    return True

        return False

    @property
    def overall_score(self) -> float:
        """Combined score for backwards compatibility."""
        return (self.location_score.overall_score + self.subject_score.overall_score) / 2


# =============================================================================
# TEST AND FUSE DATACLASSES
# =============================================================================

@dataclass
class TestResult:
    """Result of testing a hypothesis against corpus."""
    hypothesis: str
    expected_terms: List[str]
    found_terms: List[str] = field(default_factory=list)
    missing_terms: List[str] = field(default_factory=list)
    unexpected_terms: List[str] = field(default_factory=list)
    support_score: float = 0.0
    contradiction_score: float = 0.0


@dataclass
class FuseResult:
    """Final fusion decision combining all evidence."""
    verdict: FuseVerdict
    confidence: float
    match_evidence: List[MatchResult] = field(default_factory=list)
    test_evidence: List[TestResult] = field(default_factory=list)
    reasoning: str = ""


# =============================================================================
# QUERY LAB INPUT/OUTPUT
# =============================================================================

@dataclass
class QueryLabInput:
    """Input for query construction."""
    intent: Intent = Intent.DISCOVER_SUBJECT
    ku_quadrant: KUQuadrant = KUQuadrant.DISCOVER
    subject_name: Optional[str] = None
    subject_type: Optional[str] = None
    subject_attribute: Optional[str] = None
    location_domain: Optional[str] = None
    location_jurisdiction: Optional[str] = None
    location_source_type: Optional[str] = None
    expected_terms: List[str] = field(default_factory=list)
    narrative_question: Optional[str] = None


@dataclass
class QueryLabResult:
    """Output from query construction."""
    primary_query: str
    variation_queries: List[str] = field(default_factory=list)
    intent: Intent = Intent.DISCOVER_SUBJECT
    ku_quadrant: KUQuadrant = KUQuadrant.DISCOVER
    operators: List[str] = field(default_factory=list)
    notes: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# QUERY LAB - MAIN CLASS
# =============================================================================

class QueryLab:
    """
    Query Lab with K-U Matrix axis-aware matching.

    Properly distinguishes:
    - LOCATION dimensions (static: jurisdiction, domain, temporal-location, physical, format)
    - SUBJECT dimensions (dynamic: identity, identifier, temporal-subject, attribute, network)

    Cross-axis analysis enables accurate false friend detection.
    """

    # Field mappings for each dimension
    LOCATION_FIELDS = {
        LocationDimension.JURISDICTION: [
            "country", "jurisdiction", "state", "province", "legal_zone", "territory"
        ],
        LocationDimension.DOMAIN: [
            "domain", "source_url", "registry", "source", "website", "database"
        ],
        LocationDimension.TEMPORAL_LOCATION: [
            "record_date", "archive_year", "snapshot_date", "filing_date", "publication_date"
        ],
        LocationDimension.PHYSICAL: [
            "address", "city", "postal_code", "zip", "coordinates", "headquarters", "location"
        ],
        LocationDimension.FORMAT: [
            "source_type", "document_type", "format", "category", "registry_type"
        ],
    }

    SUBJECT_FIELDS = {
        SubjectDimension.IDENTITY: [
            "name", "full_name", "alias", "aka", "trading_name", "former_name"
        ],
        SubjectDimension.IDENTIFIER: [
            "oib", "ssn", "tax_id", "vat", "registration_number", "company_number",
            "passport", "id_number", "ein", "duns", "lei"
        ],
        SubjectDimension.TEMPORAL_SUBJECT: [
            "dob", "birth_date", "date_of_birth", "incorporation_date", "founded",
            "start_date", "end_date", "age", "death_date"
        ],
        SubjectDimension.ATTRIBUTE: [
            "role", "title", "profession", "status", "position", "occupation",
            "industry", "sector", "type", "category"
        ],
        SubjectDimension.NETWORK: [
            "director_of", "shareholder_of", "related_to", "parent_company",
            "subsidiary", "affiliated_with", "employed_by"
        ],
    }

    # Hard identifiers that definitively distinguish entities
    HARD_IDENTIFIERS = {
        "oib", "ssn", "tax_id", "vat", "registration_number", "company_number",
        "passport", "id_number", "ein", "dob", "birth_date", "date_of_birth"
    }

    def __init__(self):
        self.variation_generator = VariationGenerator()

    # =========================================================================
    # MATCH Operation - Axis-Aware Entity Comparison
    # =========================================================================

    def match(
        self,
        entity_a: Dict[str, Any],
        entity_b: Dict[str, Any],
    ) -> MatchResult:
        """
        Compare two entities with axis-aware dimension scoring.

        Args:
            entity_a: First entity with 'id', 'name', 'properties', 'edges'
            entity_b: Second entity

        Returns:
            MatchResult with separate location/subject scores and cross-axis analysis
        """
        props_a = entity_a.get("properties", {})
        props_b = entity_b.get("properties", {})

        # Score LOCATION axis dimensions
        location_scores = []
        for dim in LocationDimension:
            score = self._score_location_dimension(props_a, props_b, dim)
            if score:
                location_scores.append(score)

        # Score SUBJECT axis dimensions
        subject_scores = []
        for dim in SubjectDimension:
            if dim == SubjectDimension.IDENTITY:
                score = self._score_identity(entity_a, entity_b)
            elif dim == SubjectDimension.NETWORK:
                score = self._score_network(entity_a, entity_b)
            else:
                score = self._score_subject_dimension(props_a, props_b, dim)
            if score:
                subject_scores.append(score)

        # Build axis scores
        location_axis = AxisScore(axis=Axis.LOCATION, dimension_scores=location_scores)
        subject_axis = AxisScore(axis=Axis.SUBJECT, dimension_scores=subject_scores)

        # Create result with cross-axis analysis
        return MatchResult(
            entity_a_id=entity_a.get("id", "unknown_a"),
            entity_b_id=entity_b.get("id", "unknown_b"),
            location_score=location_axis,
            subject_score=subject_axis,
            notes={
                "entity_a_name": entity_a.get("name", ""),
                "entity_b_name": entity_b.get("name", ""),
            }
        )

    def _score_location_dimension(
        self,
        props_a: Dict,
        props_b: Dict,
        dimension: LocationDimension
    ) -> Optional[DimensionScore]:
        """Score a LOCATION axis dimension."""
        fields = self.LOCATION_FIELDS.get(dimension, [])
        matches = []
        mismatches = []

        for field in fields:
            val_a = props_a.get(field)
            val_b = props_b.get(field)
            if val_a and val_b:
                if self._normalize(val_a) == self._normalize(val_b):
                    matches.append(f"{field}={val_a}")
                else:
                    mismatches.append(f"{field}: {val_a} ≠ {val_b}")

        if not matches and not mismatches:
            return DimensionScore(
                axis=Axis.LOCATION,
                dimension=dimension.value,
                score=0.5,
                confidence=0.2,
                evidence=["No location data to compare"]
            )

        if matches and not mismatches:
            score = min(1.0, 0.6 + len(matches) * 0.15)
            return DimensionScore(
                axis=Axis.LOCATION,
                dimension=dimension.value,
                score=score,
                confidence=0.8,
                evidence=[f"Match: {', '.join(matches[:3])}"]
            )

        if mismatches:
            score = max(0.0, 0.4 - len(mismatches) * 0.15)
            return DimensionScore(
                axis=Axis.LOCATION,
                dimension=dimension.value,
                score=score,
                confidence=0.8,
                evidence=[f"Conflict: {', '.join(mismatches[:3])}"]
            )

        return None

    def _score_subject_dimension(
        self,
        props_a: Dict,
        props_b: Dict,
        dimension: SubjectDimension
    ) -> Optional[DimensionScore]:
        """Score a SUBJECT axis dimension."""
        fields = self.SUBJECT_FIELDS.get(dimension, [])
        matches = []
        mismatches = []
        is_hard = False

        for field in fields:
            val_a = props_a.get(field)
            val_b = props_b.get(field)
            if val_a and val_b:
                is_hard_field = field in self.HARD_IDENTIFIERS
                if is_hard_field:
                    is_hard = True

                if self._normalize(val_a) == self._normalize(val_b):
                    matches.append(f"{field}={val_a}")
                else:
                    mismatches.append(f"{field}: {val_a} ≠ {val_b}")

        if not matches and not mismatches:
            return DimensionScore(
                axis=Axis.SUBJECT,
                dimension=dimension.value,
                score=0.5,
                confidence=0.2,
                evidence=["No subject data to compare"]
            )

        if matches and not mismatches:
            score = min(1.0, 0.6 + len(matches) * 0.15)
            confidence = 0.95 if is_hard else 0.75
            return DimensionScore(
                axis=Axis.SUBJECT,
                dimension=dimension.value,
                score=score,
                confidence=confidence,
                evidence=[f"Match: {', '.join(matches[:3])}"],
                is_hard_identifier=is_hard
            )

        if mismatches:
            score = max(0.0, 0.3 - len(mismatches) * 0.15)
            confidence = 0.95 if is_hard else 0.75
            return DimensionScore(
                axis=Axis.SUBJECT,
                dimension=dimension.value,
                score=score,
                confidence=confidence,
                evidence=[f"Conflict: {', '.join(mismatches[:3])}"],
                is_hard_identifier=is_hard
            )

        return None

    def _score_identity(self, entity_a: Dict, entity_b: Dict) -> DimensionScore:
        """Score identity (name) similarity with variation awareness."""
        name_a = (entity_a.get("name") or "").strip()
        name_b = (entity_b.get("name") or "").strip()

        if not name_a or not name_b:
            return DimensionScore(
                axis=Axis.SUBJECT,
                dimension=SubjectDimension.IDENTITY.value,
                score=0.5,
                confidence=0.2,
                evidence=["Missing name for comparison"]
            )

        # Normalize for comparison
        norm_a = self._normalize(name_a)
        norm_b = self._normalize(name_b)

        # Exact match
        if norm_a == norm_b:
            return DimensionScore(
                axis=Axis.SUBJECT,
                dimension=SubjectDimension.IDENTITY.value,
                score=1.0,
                confidence=0.9,
                evidence=[f"Exact match: {name_a}"]
            )

        # Check if one is variation of other
        variations_a = set(self._normalize(v) for v in self.variation_generator.generate(name_a, "unknown"))
        variations_b = set(self._normalize(v) for v in self.variation_generator.generate(name_b, "unknown"))

        if norm_b in variations_a or norm_a in variations_b:
            return DimensionScore(
                axis=Axis.SUBJECT,
                dimension=SubjectDimension.IDENTITY.value,
                score=0.85,
                confidence=0.8,
                evidence=[f"Variation match: {name_a} ~ {name_b}"]
            )

        # Check for partial match (surname only, initials)
        words_a = norm_a.split()
        words_b = norm_b.split()
        common = set(words_a) & set(words_b)

        if common:
            overlap_ratio = len(common) / max(len(words_a), len(words_b))
            score = 0.3 + (overlap_ratio * 0.4)
            return DimensionScore(
                axis=Axis.SUBJECT,
                dimension=SubjectDimension.IDENTITY.value,
                score=score,
                confidence=0.6,
                evidence=[f"Partial match (surname/words): {common}"]
            )

        # No match
        return DimensionScore(
            axis=Axis.SUBJECT,
            dimension=SubjectDimension.IDENTITY.value,
            score=0.1,
            confidence=0.7,
            evidence=[f"Name mismatch: {name_a} vs {name_b}"]
        )

    def _score_network(self, entity_a: Dict, entity_b: Dict) -> DimensionScore:
        """Score network/relationship overlap."""
        edges_a = set(
            e.get("target_id", "") for e in entity_a.get("edges", [])
            if e.get("target_id")
        )
        edges_b = set(
            e.get("target_id", "") for e in entity_b.get("edges", [])
            if e.get("target_id")
        )

        if not edges_a and not edges_b:
            return DimensionScore(
                axis=Axis.SUBJECT,
                dimension=SubjectDimension.NETWORK.value,
                score=0.5,
                confidence=0.2,
                evidence=["No network data to compare"]
            )

        overlap = edges_a & edges_b
        union = edges_a | edges_b

        if overlap:
            jaccard = len(overlap) / len(union) if union else 0
            score = min(0.9, 0.4 + jaccard * 0.5)
            return DimensionScore(
                axis=Axis.SUBJECT,
                dimension=SubjectDimension.NETWORK.value,
                score=score,
                confidence=0.7,
                evidence=[f"Shared connections: {len(overlap)} of {len(union)}"]
            )

        return DimensionScore(
            axis=Axis.SUBJECT,
            dimension=SubjectDimension.NETWORK.value,
            score=0.3,
            confidence=0.5,
            evidence=["No shared network connections"]
        )

    def _normalize(self, value: Any) -> str:
        """Normalize a value for comparison."""
        if value is None:
            return ""
        s = str(value).lower().strip()
        # Remove punctuation and extra whitespace
        s = re.sub(r'[^\w\s]', '', s)
        s = re.sub(r'\s+', ' ', s)
        return s

    # =========================================================================
    # TEST Operation - Hypothesis Testing Against Corpus
    # =========================================================================

    def test(
        self,
        entity: Dict[str, Any],
        hypothesis: str,
        corpus_results: List[Dict[str, Any]],
        expected_terms: Optional[List[str]] = None
    ) -> TestResult:
        """
        Test a hypothesis about an entity against corpus search results.

        Args:
            entity: The entity being tested
            hypothesis: The hypothesis to test (e.g., "is director of Acme Corp")
            corpus_results: Search results from corpus
            expected_terms: Terms we expect to find if hypothesis is true

        Returns:
            TestResult with support/contradiction scores
        """
        if expected_terms is None:
            # Extract key terms from hypothesis
            expected_terms = [
                w for w in hypothesis.lower().split()
                if len(w) > 3 and w not in {"the", "and", "for", "with", "from"}
            ]

        found = []
        missing = []
        unexpected = []

        # Check each corpus result
        for result in corpus_results:
            content = (result.get("content", "") + " " + result.get("snippet", "")).lower()

            for term in expected_terms:
                if term.lower() in content:
                    if term not in found:
                        found.append(term)
                else:
                    if term not in missing and term not in found:
                        missing.append(term)

            # Check for contradictory terms
            entity_name = entity.get("name", "").lower()
            if "not " + entity_name in content or "former " in content:
                unexpected.append("Contradiction indicator found")

        # Calculate scores
        total = len(expected_terms) if expected_terms else 1
        support = len(found) / total if total > 0 else 0
        contradiction = len(unexpected) / (len(corpus_results) + 1)

        return TestResult(
            hypothesis=hypothesis,
            expected_terms=expected_terms,
            found_terms=found,
            missing_terms=missing,
            unexpected_terms=unexpected,
            support_score=support,
            contradiction_score=contradiction
        )

    # =========================================================================
    # FUSE Operation - Combine Evidence for Final Decision
    # =========================================================================

    def fuse(
        self,
        match_results: List[MatchResult],
        test_results: Optional[List[TestResult]] = None
    ) -> FuseResult:
        """
        Combine match and test evidence into a final verdict.

        The fusion logic:
        1. Hard identifier conflicts → REPEL (definitive)
        2. Cross-axis pattern analysis → weighted vote
        3. Test results → support/contradict
        4. Accumulate evidence → final decision

        Args:
            match_results: Results from match() operations
            test_results: Results from test() operations

        Returns:
            FuseResult with final verdict and reasoning
        """
        test_results = test_results or []

        # Check for hard conflicts first
        for mr in match_results:
            if mr.subject_score.has_hard_conflict:
                return FuseResult(
                    verdict=FuseVerdict.REPEL,
                    confidence=0.95,
                    match_evidence=match_results,
                    test_evidence=test_results,
                    reasoning="Hard identifier conflict detected - definitive REPEL"
                )

        # Accumulate evidence
        fuse_score = 0.0
        repel_score = 0.0
        binary_star_score = 0.0

        for mr in match_results:
            if mr.suggested_verdict == FuseVerdict.FUSE:
                fuse_score += mr.confidence
            elif mr.suggested_verdict == FuseVerdict.REPEL:
                repel_score += mr.confidence
            elif mr.suggested_verdict == FuseVerdict.BINARY_STAR:
                binary_star_score += mr.confidence

        # Factor in test results
        for tr in test_results:
            if tr.support_score > 0.6:
                fuse_score += tr.support_score * 0.3
            if tr.contradiction_score > 0.3:
                repel_score += tr.contradiction_score * 0.5

        # Normalize
        total = fuse_score + repel_score + binary_star_score + 0.01

        # Determine verdict
        if fuse_score / total > 0.5:
            return FuseResult(
                verdict=FuseVerdict.FUSE,
                confidence=fuse_score / total,
                match_evidence=match_results,
                test_evidence=test_results,
                reasoning=f"Evidence supports FUSE: {fuse_score:.2f} vs REPEL: {repel_score:.2f}"
            )
        elif repel_score / total > 0.5:
            return FuseResult(
                verdict=FuseVerdict.REPEL,
                confidence=repel_score / total,
                match_evidence=match_results,
                test_evidence=test_results,
                reasoning=f"Evidence supports REPEL: {repel_score:.2f} vs FUSE: {fuse_score:.2f}"
            )
        elif binary_star_score > 0.3 * total:
            return FuseResult(
                verdict=FuseVerdict.BINARY_STAR,
                confidence=0.6,
                match_evidence=match_results,
                test_evidence=test_results,
                reasoning="Evidence suggests related but distinct entities"
            )
        else:
            return FuseResult(
                verdict=FuseVerdict.UNCERTAIN,
                confidence=0.3,
                match_evidence=match_results,
                test_evidence=test_results,
                reasoning="Insufficient evidence for confident decision"
            )

    # =========================================================================
    # CONSTRUCT Operation - Build Query from Gap/Intent
    # =========================================================================

    def construct(self, request: QueryLabInput) -> QueryLabResult:
        """Build executable query from intent and coordinates."""
        subject = request.subject_name or ""
        match_terms = []

        # Add subject with appropriate prefix
        if subject:
            prefix = self._prefix_for_type(request.subject_type)
            if prefix:
                match_terms.append(f"{prefix} {subject}")
            else:
                match_terms.append(f'"{subject}"')

        # Add attribute if specified
        if request.subject_attribute:
            match_terms.append(f'"{request.subject_attribute}"')

        # Add LOCATION constraints
        location_terms = []
        if request.location_jurisdiction:
            location_terms.append(f":{request.location_jurisdiction}")
        if request.location_domain:
            location_terms.append(f"site:{request.location_domain}")
        if request.location_source_type:
            location_terms.append(request.location_source_type)

        # Expected terms for testing
        expected_terms = request.expected_terms or []
        if expected_terms:
            match_terms.append("(" + " OR ".join(expected_terms[:5]) + ")")

        if location_terms:
            match_terms.extend(location_terms[:3])

        # Fallback
        if not match_terms and request.narrative_question:
            match_terms.append(request.narrative_question.strip())

        primary_query = " ".join(match_terms).strip()

        # Generate variations
        variations = self._build_variations(subject, request.subject_type)
        variation_queries = []
        if primary_query and variations:
            for var in variations[:5]:
                if subject:
                    variation_queries.append(primary_query.replace(f'"{subject}"', f'"{var}"', 1))
                else:
                    variation_queries.append(var)

        return QueryLabResult(
            primary_query=primary_query,
            variation_queries=variation_queries,
            intent=request.intent,
            ku_quadrant=request.ku_quadrant,
            operators=self._operators_for_intent(request.intent),
            notes={
                "subject": subject,
                "location_terms": location_terms,
                "expected_terms": expected_terms,
            },
        )

    def _operators_for_intent(self, intent: Intent) -> List[str]:
        """Map intent to preferred operator hints."""
        if intent in (Intent.ENRICH_SUBJECT, Intent.ENRICH_LOCATION):
            return ["exact_match", "site:", "registry_hint"]
        return ["free_terms", "or_expansion"]

    def _build_variations(self, value: str, entity_type: Optional[str]) -> List[str]:
        """Generate free-OR variations for the subject."""
        if not value:
            return []

        entity_type = (entity_type or "").lower()
        if entity_type in ("company", "organization"):
            return self.variation_generator.generate_company_variations(value)
        if entity_type in ("person", "individual"):
            return self.variation_generator.generate_person_variations(value)
        if entity_type in ("domain", "url"):
            return self.variation_generator.generate_domain_variations(value)
        return self.variation_generator.generate(value, entity_type or "unknown")

    def _prefix_for_type(self, entity_type: Optional[str]) -> Optional[str]:
        """Return IO prefix for a given subject type."""
        if not entity_type:
            return None
        entity_type = entity_type.lower()
        if entity_type in ("person", "individual"):
            return "p:"
        if entity_type in ("company", "organization"):
            return "c:"
        if entity_type in ("domain", "url", "website"):
            return "d:"
        if entity_type in ("email",):
            return "e:"
        if entity_type in ("phone", "telephone"):
            return "t:"
        return None
