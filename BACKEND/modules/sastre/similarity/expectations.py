"""
SASTRE NEXUS Expectations

NEXUS mode evaluates three states for every potential intersection:

1. Expected AND Found - Confirms hypothesis
2. Expected AND NOT Found - Suspicious absence
3. Unexpected AND Found - The Surprising AND (real intelligence)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple
from enum import Enum


class ExpectationState(Enum):
    """NEXUS intersection states."""
    EXPECTED_FOUND = "expected_found"           # Confirmed hypothesis
    EXPECTED_NOT_FOUND = "expected_not_found"   # Suspicious absence
    UNEXPECTED_FOUND = "unexpected_found"       # Surprising AND (intelligence!)
    UNKNOWN = "unknown"                         # Not yet evaluated


class ExpectationBasis(Enum):
    """Why something is expected or unexpected."""
    ROLE = "role"                   # CEO should appear in filings
    JURISDICTION = "jurisdiction"   # Cyprus company should have Cyprus registry
    TIME = "time"                   # Active during period should appear
    RELATIONSHIP = "relationship"   # Officer should appear with company
    PATTERN = "pattern"             # Typical structure should exist
    ABSENCE = "absence"             # Missing typical element


@dataclass
class Expectation:
    """An expectation about an intersection."""
    subject_a: str                    # First element (node ID or query)
    subject_b: str                    # Second element
    relationship: Optional[str] = None  # Expected relationship type
    basis: ExpectationBasis = ExpectationBasis.PATTERN
    reason: str = ""                  # Why this is expected
    confidence: float = 0.5           # How confident in this expectation (0-1)


@dataclass
class IntersectionResult:
    """Result of checking an intersection."""
    expectation: Expectation
    state: ExpectationState
    found_count: int = 0              # Number of results found
    found_examples: List[str] = field(default_factory=list)  # Sample node IDs
    significance: float = 0.0         # How significant is this result (0-1)
    explanation: str = ""             # Human-readable explanation
    suggested_queries: List[str] = field(default_factory=list)  # Follow-up queries


@dataclass
class SurprisingAnd:
    """
    The Surprising AND - unexpected connection that reveals intelligence.

    Example: #respected_banker AND #sanctioned_oligarch AND ##2019 → RESULT
    Shouldn't be connected. But they are. Flag it.
    """
    entity_a: str
    entity_b: str
    connection_type: str              # How they're connected
    discovered_at: str                # Where/how discovered
    significance: float               # How surprising (0-1)
    explanation: str                  # Why this is surprising
    evidence: List[str] = field(default_factory=list)  # Supporting evidence


class NexusEvaluator:
    """
    Evaluates intersection expectations.

    For each query intersection, determines:
    - What we expected to find
    - What we actually found
    - Whether the result is confirmatory, suspicious, or surprising
    """

    # Default expectations by entity type
    DEFAULT_EXPECTATIONS: Dict[str, List[Dict]] = {
        # CEO should appear in company filings
        "ceo": [
            {"with": "company_filings", "basis": "role", "reason": "CEOs should appear in official filings"},
            {"with": "annual_reports", "basis": "role", "reason": "CEOs are typically mentioned in annual reports"},
        ],
        # Directors should appear with company
        "director": [
            {"with": "company_registry", "basis": "role", "reason": "Directors are registered"},
            {"with": "company_filings", "basis": "role", "reason": "Directors should sign filings"},
        ],
        # Company should have registry entry
        "company": [
            {"with": "company_registry", "basis": "jurisdiction", "reason": "Registered companies have registry entries"},
            {"with": "registered_address", "basis": "pattern", "reason": "Companies have registered addresses"},
        ],
        # Active entity should appear in time period
        "active_entity": [
            {"with": "contemporaneous_records", "basis": "time", "reason": "Active entities leave records"},
        ],
    }

    # Surprising combinations (shouldn't normally be connected)
    SURPRISING_COMBINATIONS: List[Tuple[str, str, str]] = [
        # (entity_type_a, entity_type_b, why_surprising)
        ("legitimate_institution", "sanctioned_entity", "Sanctioned entities shouldn't have banking access"),
        ("charity", "shell_company", "Charities shouldn't route through shell companies"),
        ("law_enforcement", "criminal_organization", "Should not have legitimate business relationships"),
        ("compliance_officer", "sanctions_violation", "Compliance officers should prevent violations"),
    ]

    def __init__(self, state_provider: Optional[Any] = None):
        """
        Initialize evaluator.

        Args:
            state_provider: Provider for getting nodes and running queries
        """
        self.state = state_provider

    def evaluate_intersection(
        self,
        subject_a: str,
        subject_b: str,
        expectation: Optional[Expectation] = None,
        found_results: Optional[List[Dict]] = None
    ) -> IntersectionResult:
        """
        Evaluate an intersection between two subjects.

        Args:
            subject_a: First subject (node ID or concept)
            subject_b: Second subject (node ID or concept)
            expectation: Optional pre-defined expectation
            found_results: Results already found (if query was run)

        Returns:
            IntersectionResult with state and significance
        """
        # Build or use expectation
        if not expectation:
            expectation = self._infer_expectation(subject_a, subject_b)

        # Determine state
        found = found_results is not None and len(found_results) > 0
        expected = expectation.confidence > 0.5

        if expected and found:
            state = ExpectationState.EXPECTED_FOUND
            significance = 0.3  # Confirmatory, low significance
            explanation = f"Confirmed: {expectation.reason}"

        elif expected and not found:
            state = ExpectationState.EXPECTED_NOT_FOUND
            significance = 0.7  # Suspicious absence, high significance
            explanation = f"Suspicious absence: {expectation.reason}, but not found"

        elif not expected and found:
            state = ExpectationState.UNEXPECTED_FOUND
            significance = 0.9  # Surprising AND, very high significance
            explanation = f"Surprising connection found between {subject_a} and {subject_b}"

        else:
            state = ExpectationState.UNKNOWN
            significance = 0.1
            explanation = "No expectation, no results"

        # Generate follow-up queries
        suggested = self._suggest_follow_up(subject_a, subject_b, state)

        return IntersectionResult(
            expectation=expectation,
            state=state,
            found_count=len(found_results) if found_results else 0,
            found_examples=[r.get("id", "") for r in (found_results or [])[:5]],
            significance=significance,
            explanation=explanation,
            suggested_queries=suggested,
        )

    def detect_surprising_and(
        self,
        entity_a: str,
        entity_b: str,
        connection: Dict[str, Any]
    ) -> Optional[SurprisingAnd]:
        """
        Check if a connection is a Surprising AND.

        Args:
            entity_a: First entity ID
            entity_b: Second entity ID
            connection: Connection data (edge, shared source, etc.)

        Returns:
            SurprisingAnd if surprising, None otherwise
        """
        # Get entity types
        a_type = self._get_entity_type(entity_a)
        b_type = self._get_entity_type(entity_b)

        # Check against known surprising combinations
        for type_a, type_b, reason in self.SURPRISING_COMBINATIONS:
            if (a_type == type_a and b_type == type_b) or (a_type == type_b and b_type == type_a):
                return SurprisingAnd(
                    entity_a=entity_a,
                    entity_b=entity_b,
                    connection_type=connection.get("type", "unknown"),
                    discovered_at=connection.get("source", ""),
                    significance=0.9,
                    explanation=reason,
                    evidence=[connection.get("id", "")],
                )

        # Check for other surprising patterns
        if self._is_jurisdictionally_surprising(entity_a, entity_b):
            return SurprisingAnd(
                entity_a=entity_a,
                entity_b=entity_b,
                connection_type=connection.get("type", "unknown"),
                discovered_at=connection.get("source", ""),
                significance=0.7,
                explanation="Entities from unexpected jurisdictions connected",
                evidence=[],
            )

        return None

    def find_suspicious_absences(
        self,
        entity_id: str,
        expected_connections: Optional[List[str]] = None
    ) -> List[IntersectionResult]:
        """
        Find Expected AND NOT Found cases for an entity.

        Args:
            entity_id: Entity to check
            expected_connections: Optional list of expected connection types

        Returns:
            List of suspicious absences
        """
        absences = []

        # Get entity type and determine expectations
        entity_type = self._get_entity_type(entity_id)
        expectations = self.DEFAULT_EXPECTATIONS.get(entity_type, [])

        for exp_def in expectations:
            expectation = Expectation(
                subject_a=entity_id,
                subject_b=exp_def["with"],
                basis=ExpectationBasis[exp_def["basis"].upper()],
                reason=exp_def["reason"],
                confidence=0.8,
            )

            # Check if this connection exists
            found = self._check_connection(entity_id, exp_def["with"])

            if not found:
                result = self.evaluate_intersection(
                    entity_id,
                    exp_def["with"],
                    expectation=expectation,
                    found_results=[],
                )
                absences.append(result)

        return absences

    def _infer_expectation(self, subject_a: str, subject_b: str) -> Expectation:
        """Infer an expectation for two subjects."""
        # Simple heuristics - in practice this would be more sophisticated

        # If one looks like a role and one like a document type
        role_keywords = ["ceo", "director", "officer", "shareholder", "owner"]
        doc_keywords = ["filing", "report", "registry", "record"]

        a_lower = subject_a.lower()
        b_lower = subject_b.lower()

        if any(k in a_lower for k in role_keywords) and any(k in b_lower for k in doc_keywords):
            return Expectation(
                subject_a=subject_a,
                subject_b=subject_b,
                basis=ExpectationBasis.ROLE,
                reason=f"{subject_a} should appear in {subject_b}",
                confidence=0.7,
            )

        # Default: low confidence expectation
        return Expectation(
            subject_a=subject_a,
            subject_b=subject_b,
            basis=ExpectationBasis.PATTERN,
            reason="General intersection check",
            confidence=0.3,
        )

    def _suggest_follow_up(
        self,
        subject_a: str,
        subject_b: str,
        state: ExpectationState
    ) -> List[str]:
        """Suggest follow-up queries based on state."""
        queries = []

        if state == ExpectationState.EXPECTED_NOT_FOUND:
            # Try alternative queries to find the missing connection
            queries.append(f'"{subject_a}" "{subject_b}" alternative names')
            queries.append(f'"{subject_a}" related documents')
            queries.append(f'why is "{subject_a}" not in {subject_b}')

        elif state == ExpectationState.UNEXPECTED_FOUND:
            # Investigate the surprising connection
            queries.append(f'"{subject_a}" AND "{subject_b}" history')
            queries.append(f'"{subject_a}" "{subject_b}" relationship')
            queries.append(f'verify "{subject_a}" "{subject_b}" connection')

        return queries[:3]

    def _get_entity_type(self, entity_id: str) -> str:
        """Get entity type for classification."""
        if self.state:
            node = self.state.get_node(entity_id)
            return node.get("type", "unknown") if node else "unknown"
        return "unknown"

    def _check_connection(self, entity_a: str, entity_b: str) -> bool:
        """Check if two entities are connected."""
        if self.state:
            return self.state.has_edge(entity_a, entity_b)
        return False

    def _is_jurisdictionally_surprising(self, entity_a: str, entity_b: str) -> bool:
        """Check if entities being connected is jurisdictionally surprising."""
        if not self.state:
            return False

        a_node = self.state.get_node(entity_a)
        b_node = self.state.get_node(entity_b)

        if not a_node or not b_node:
            return False

        a_jurs = set(a_node.get("jurisdictions", []))
        b_jurs = set(b_node.get("jurisdictions", []))

        # Surprising if no jurisdictional overlap but connected
        return bool(a_jurs and b_jurs and not (a_jurs & b_jurs))


# Dimension evaluation matrix
DIMENSION_MATRIX: Dict[str, Dict[str, str]] = {
    # Entity + Entity
    "entity_entity": {
        "expected": "Direct relationship in records",
        "not_found": "No documented relationship",
        "surprising": "Unexpected connection",
    },
    # Entity + Topic
    "entity_topic": {
        "expected": "Entity associated with topic",
        "not_found": "Entity not linked to topic",
        "surprising": "Unexpected topic association",
    },
    # Entity + Jurisdiction
    "entity_jurisdiction": {
        "expected": "Entity present in jurisdiction",
        "not_found": "Entity not found in jurisdiction",
        "surprising": "Unexpected jurisdictional presence",
    },
    # Entity + Time
    "entity_time": {
        "expected": "Entity active during period",
        "not_found": "Entity not active during period",
        "surprising": "Unexpected temporal activity",
    },
    # Topic + Jurisdiction
    "topic_jurisdiction": {
        "expected": "Topic prevalent in jurisdiction",
        "not_found": "Topic not found in jurisdiction",
        "surprising": "Unexpected topic-jurisdiction link",
    },
}


def evaluate_dimension_intersection(
    dim_a: str,
    dim_b: str,
    found: bool,
    expected: bool
) -> str:
    """Get description for dimension intersection."""
    key = f"{dim_a}_{dim_b}"
    if key not in DIMENSION_MATRIX:
        key = f"{dim_b}_{dim_a}"

    matrix = DIMENSION_MATRIX.get(key, {})

    if expected and found:
        return matrix.get("expected", "Expected and found")
    elif expected and not found:
        return matrix.get("not_found", "Expected but not found")
    elif not expected and found:
        return matrix.get("surprising", "Surprising find")
    else:
        return "Not expected, not found"
