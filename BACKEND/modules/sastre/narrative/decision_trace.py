#!/usr/bin/env python3
"""
SASTRE Decision Trace - Explainability System

Records every search decision and outcome for audit trails.
Citations prove WHERE data came from; decision traces prove WHY
the AI chose that path and what it rejected.

Features:
- Record positive findings (data found)
- Record negative findings (searched but not found)
- Record rejected hypotheses
- Record fallback decisions
- Generate audit section for RESEARCH_METHODOLOGY

Usage:
    trace = DecisionTraceCollector()

    # Record searches
    trace.record_search("SEARCH_OFFICERS", ["Companies House"], "positive", results)
    trace.record_negative("SEARCH_SHAREHOLDERS", ["PSC Register"], "No PSC filings found")
    trace.record_rejected_hypothesis("Subject may be PEP", "No political connections found")

    # Generate audit section
    audit_md = trace.generate_audit_section()
"""

import json
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from enum import Enum


class SearchOutcome(Enum):
    """Outcome of a search action."""
    POSITIVE = "positive"      # Data found
    NEGATIVE = "negative"      # Searched, nothing found
    PARTIAL = "partial"        # Some data found, gaps remain
    ERROR = "error"            # Search failed (API error, timeout)
    SKIPPED = "skipped"        # Intentionally skipped (dead-end)
    FALLBACK = "fallback"      # Primary failed, fallback used


@dataclass
class SearchTrace:
    """Record of a single search action."""
    trace_id: str
    action: str                          # e.g., "SEARCH_OFFICERS"
    jurisdiction: str
    outcome: SearchOutcome
    sources_checked: List[str]           # Registries/sources queried
    results_count: int = 0
    duration_ms: float = 0
    error_message: Optional[str] = None
    notes: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "trace_id": self.trace_id,
            "action": self.action,
            "jurisdiction": self.jurisdiction,
            "outcome": self.outcome.value,
            "sources_checked": self.sources_checked,
            "results_count": self.results_count,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "notes": self.notes,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RejectedHypothesis:
    """Record of a hypothesis that was investigated and rejected."""
    hypothesis_id: str
    hypothesis: str                      # What was suspected
    investigation_actions: List[str]     # Actions taken to investigate
    rejection_reason: str                # Why it was rejected
    confidence: str                      # "high", "medium", "low"
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "hypothesis": self.hypothesis,
            "investigation_actions": self.investigation_actions,
            "rejection_reason": self.rejection_reason,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class FallbackDecision:
    """Record of a fallback path taken."""
    fallback_id: str
    action: str
    primary_source: str
    primary_failure_reason: str
    fallback_source: str
    fallback_outcome: SearchOutcome
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "fallback_id": self.fallback_id,
            "action": self.action,
            "primary_source": self.primary_source,
            "primary_failure_reason": self.primary_failure_reason,
            "fallback_source": self.fallback_source,
            "fallback_outcome": self.fallback_outcome.value,
            "timestamp": self.timestamp.isoformat(),
        }


class DecisionTraceCollector:
    """
    Collect decision traces during investigation.

    Maintains audit trail of all search decisions for:
    - Regulatory compliance
    - Quality assurance
    - Methodology documentation
    - Reproducibility
    """

    def __init__(self, investigation_id: Optional[str] = None):
        self.investigation_id = investigation_id or uuid.uuid4().hex[:12]
        self.traces: List[SearchTrace] = []
        self.rejected_hypotheses: List[RejectedHypothesis] = []
        self.fallback_decisions: List[FallbackDecision] = []
        self.start_time = datetime.utcnow()
        self.metadata: Dict[str, Any] = {}

    def record_search(
        self,
        action: str,
        sources: List[str],
        outcome: str,
        results_count: int = 0,
        duration_ms: float = 0,
        jurisdiction: str = "",
        notes: str = None
    ):
        """Record a search action and its outcome."""
        trace = SearchTrace(
            trace_id=uuid.uuid4().hex[:8],
            action=action,
            jurisdiction=jurisdiction,
            outcome=SearchOutcome(outcome),
            sources_checked=sources,
            results_count=results_count,
            duration_ms=duration_ms,
            notes=notes
        )
        self.traces.append(trace)
        return trace.trace_id

    def record_negative(
        self,
        action: str,
        sources: List[str],
        reason: str,
        jurisdiction: str = ""
    ):
        """Record a search that returned no results."""
        return self.record_search(
            action=action,
            sources=sources,
            outcome="negative",
            results_count=0,
            jurisdiction=jurisdiction,
            notes=reason
        )

    def record_error(
        self,
        action: str,
        sources: List[str],
        error_message: str,
        jurisdiction: str = ""
    ):
        """Record a search that failed with an error."""
        trace = SearchTrace(
            trace_id=uuid.uuid4().hex[:8],
            action=action,
            jurisdiction=jurisdiction,
            outcome=SearchOutcome.ERROR,
            sources_checked=sources,
            error_message=error_message
        )
        self.traces.append(trace)
        return trace.trace_id

    def record_skipped(
        self,
        action: str,
        reason: str,
        jurisdiction: str = ""
    ):
        """Record an action that was intentionally skipped (e.g., dead-end)."""
        trace = SearchTrace(
            trace_id=uuid.uuid4().hex[:8],
            action=action,
            jurisdiction=jurisdiction,
            outcome=SearchOutcome.SKIPPED,
            sources_checked=[],
            notes=f"Skipped: {reason}"
        )
        self.traces.append(trace)
        return trace.trace_id

    def record_rejected_hypothesis(
        self,
        hypothesis: str,
        rejection_reason: str,
        investigation_actions: List[str] = None,
        confidence: str = "medium"
    ):
        """Record a hypothesis that was investigated and rejected."""
        rejected = RejectedHypothesis(
            hypothesis_id=uuid.uuid4().hex[:8],
            hypothesis=hypothesis,
            investigation_actions=investigation_actions or [],
            rejection_reason=rejection_reason,
            confidence=confidence
        )
        self.rejected_hypotheses.append(rejected)
        return rejected.hypothesis_id

    def record_fallback(
        self,
        action: str,
        primary_source: str,
        failure_reason: str,
        fallback_source: str,
        fallback_outcome: str
    ):
        """Record a fallback path that was taken."""
        fallback = FallbackDecision(
            fallback_id=uuid.uuid4().hex[:8],
            action=action,
            primary_source=primary_source,
            primary_failure_reason=failure_reason,
            fallback_source=fallback_source,
            fallback_outcome=SearchOutcome(fallback_outcome)
        )
        self.fallback_decisions.append(fallback)
        return fallback.fallback_id

    def get_summary(self) -> Dict:
        """Get summary statistics of the decision trace."""
        outcomes = {}
        for trace in self.traces:
            key = trace.outcome.value
            outcomes[key] = outcomes.get(key, 0) + 1

        return {
            "investigation_id": self.investigation_id,
            "total_searches": len(self.traces),
            "outcomes": outcomes,
            "rejected_hypotheses": len(self.rejected_hypotheses),
            "fallback_decisions": len(self.fallback_decisions),
            "duration_ms": (datetime.utcnow() - self.start_time).total_seconds() * 1000,
        }

    def generate_audit_section(self) -> str:
        """
        Generate markdown for RESEARCH_METHODOLOGY section.

        Returns formatted markdown suitable for inclusion in reports.
        """
        lines = []

        # Header
        lines.append("## Research Scope and Methodology")
        lines.append("")

        # Sources Consulted
        all_sources = set()
        for trace in self.traces:
            all_sources.update(trace.sources_checked)

        if all_sources:
            lines.append("### Sources Consulted")
            lines.append("")
            for source in sorted(all_sources):
                lines.append(f"- {source}")
            lines.append("")

        # Searches Returning No Results
        negatives = [t for t in self.traces if t.outcome == SearchOutcome.NEGATIVE]
        if negatives:
            lines.append("### Searches Returning No Results")
            lines.append("")
            lines.append("The following searches were conducted but yielded no results:")
            lines.append("")
            lines.append("| Search Type | Sources Checked | Notes |")
            lines.append("|-------------|-----------------|-------|")
            for trace in negatives:
                sources_str = ", ".join(trace.sources_checked[:3])
                if len(trace.sources_checked) > 3:
                    sources_str += f" (+{len(trace.sources_checked)-3} more)"
                notes = trace.notes or "No results found"
                lines.append(f"| {trace.action.replace('SEARCH_', '')} | {sources_str} | {notes} |")
            lines.append("")

        # Skipped Searches (Dead-Ends)
        skipped = [t for t in self.traces if t.outcome == SearchOutcome.SKIPPED]
        if skipped:
            lines.append("### Searches Not Conducted")
            lines.append("")
            lines.append("The following searches were not conducted due to known limitations:")
            lines.append("")
            for trace in skipped:
                lines.append(f"- **{trace.action.replace('SEARCH_', '')}**: {trace.notes}")
            lines.append("")

        # Rejected Hypotheses
        if self.rejected_hypotheses:
            lines.append("### Rejected Hypotheses")
            lines.append("")
            lines.append("The following hypotheses were investigated and rejected:")
            lines.append("")
            for hyp in self.rejected_hypotheses:
                lines.append(f"- **Hypothesis**: {hyp.hypothesis}")
                lines.append(f"  - **Finding**: {hyp.rejection_reason}")
                lines.append(f"  - **Confidence**: {hyp.confidence.title()}")
            lines.append("")

        # Fallback Sources Used
        if self.fallback_decisions:
            lines.append("### Alternative Sources Used")
            lines.append("")
            lines.append("Primary sources were unavailable; alternative sources were used:")
            lines.append("")
            for fb in self.fallback_decisions:
                lines.append(f"- {fb.action.replace('SEARCH_', '')}: {fb.primary_source} unavailable ({fb.primary_failure_reason}), used {fb.fallback_source}")
            lines.append("")

        # Errors (if any)
        errors = [t for t in self.traces if t.outcome == SearchOutcome.ERROR]
        if errors:
            lines.append("### Research Limitations")
            lines.append("")
            lines.append("The following sources could not be accessed:")
            lines.append("")
            for trace in errors:
                lines.append(f"- {', '.join(trace.sources_checked)}: {trace.error_message}")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """Export full trace as dictionary."""
        return {
            "investigation_id": self.investigation_id,
            "start_time": self.start_time.isoformat(),
            "metadata": self.metadata,
            "traces": [t.to_dict() for t in self.traces],
            "rejected_hypotheses": [h.to_dict() for h in self.rejected_hypotheses],
            "fallback_decisions": [f.to_dict() for f in self.fallback_decisions],
            "summary": self.get_summary(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Export as JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# Convenience function
def create_trace(investigation_id: str = None) -> DecisionTraceCollector:
    """Create a new decision trace collector."""
    return DecisionTraceCollector(investigation_id)


if __name__ == "__main__":
    # Demo usage
    trace = DecisionTraceCollector("demo_investigation")

    # Record some searches
    trace.record_search(
        "SEARCH_REGISTRY",
        ["Companies House"],
        "positive",
        results_count=1,
        jurisdiction="UK"
    )

    trace.record_search(
        "SEARCH_OFFICERS",
        ["Companies House"],
        "positive",
        results_count=3,
        jurisdiction="UK"
    )

    trace.record_negative(
        "SEARCH_SANCTIONS",
        ["OFAC", "EU Sanctions", "UK Sanctions"],
        "Subject does not appear on any sanctions lists",
        jurisdiction="UK"
    )

    trace.record_skipped(
        "SEARCH_SHAREHOLDERS",
        "Swiss jurisdiction - shareholders not publicly disclosed",
        jurisdiction="CH"
    )

    trace.record_rejected_hypothesis(
        "Subject may have political connections",
        "No PEP database matches; no media coverage of political involvement",
        investigation_actions=["SEARCH_PEP", "SEARCH_NEWS"],
        confidence="high"
    )

    trace.record_fallback(
        "SEARCH_FINANCIALS",
        "Companies House (accounts overdue)",
        "Latest accounts not filed",
        "D&B Credit Report",
        "partial"
    )

    # Print audit section
    print(trace.generate_audit_section())
    print("\n" + "="*60 + "\n")
    print("Summary:", json.dumps(trace.get_summary(), indent=2))
