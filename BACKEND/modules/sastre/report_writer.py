"""
SASTRE Report Writer - Nardello-Style Investigation Reports

Generates professional investigation reports from Cymonides-1 graph data.
Uses Core/Shell/Halo organization and proper attribution.

Integration:
- Reads entities and findings from cymonides-1-{projectId}
- Organizes by entity type and attribute layer
- Generates Markdown or Word output
- Proper footnotes and source attribution

Output Format:
- Nardello & Co. professional style
- Core/Shell/Halo entity organization
- Chronological or thematic structure
- Full source attribution
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from .orchestrator import CymonidesClient
from .contracts import get_completeness


# =============================================================================
# REPORT STRUCTURE
# =============================================================================

@dataclass
class Footnote:
    """Source attribution footnote."""
    number: int
    source_url: str
    accessed_date: str
    description: str = ""


@dataclass
class EntitySection:
    """Section about an entity."""
    entity_id: str
    entity_type: str
    label: str
    # Core/Shell/Halo organization
    core_attributes: Dict[str, Any]  # Identity: name, ID, DOB
    shell_attributes: Dict[str, Any]  # Contact: email, phone, address
    halo_attributes: Dict[str, Any]  # Context: news, associations
    # Relationships
    relationships: List[Dict[str, Any]]
    # Sources
    footnotes: List[Footnote] = field(default_factory=list)


@dataclass
class ReportSection:
    """A section of the report."""
    title: str
    content: str
    entities: List[EntitySection] = field(default_factory=list)
    subsections: List['ReportSection'] = field(default_factory=list)
    footnotes: List[Footnote] = field(default_factory=list)


@dataclass
class InvestigationReport:
    """Complete investigation report."""
    title: str
    investigation_id: str
    project_id: str
    generated_at: str
    # Sections
    executive_summary: str
    background: str
    sections: List[ReportSection]
    # All footnotes
    footnotes: List[Footnote]
    # Metadata
    entities_covered: int
    sources_cited: int


# =============================================================================
# ATTRIBUTE CLASSIFICATION
# =============================================================================

# Core attributes (identity - high confidence)
CORE_ATTRIBUTES = {
    "person": ["name", "full_name", "dob", "date_of_birth", "nationality", "national_id", "passport", "tax_id"],
    "company": ["name", "company_name", "registration_number", "vat_id", "incorporation_date", "status", "jurisdiction"],
    "domain": ["domain", "registrant", "registration_date", "expiry_date"],
}

# Shell attributes (contact - medium confidence)
SHELL_ATTRIBUTES = {
    "person": ["email", "phone", "address", "employer", "position", "linkedin", "twitter"],
    "company": ["email", "phone", "address", "website", "industry", "employees", "revenue"],
    "domain": ["whois", "nameservers", "hosting", "ssl_issuer", "technologies"],
}

# Halo attributes (context - supporting)
HALO_ATTRIBUTES = {
    "person": ["news_mentions", "associations", "sanctions", "pep_status", "adverse_media", "social_media"],
    "company": ["news_mentions", "shareholders", "officers", "subsidiaries", "litigation", "adverse_media"],
    "domain": ["backlinks", "outlinks", "similar_sites", "content_topics", "archived_versions"],
}


def classify_attribute(entity_type: str, attr_name: str) -> str:
    """Classify attribute as core, shell, or halo."""
    attr_lower = attr_name.lower()

    if attr_lower in CORE_ATTRIBUTES.get(entity_type, []):
        return "core"
    if attr_lower in SHELL_ATTRIBUTES.get(entity_type, []):
        return "shell"
    if attr_lower in HALO_ATTRIBUTES.get(entity_type, []):
        return "halo"

    # Default classification by pattern
    if any(x in attr_lower for x in ["id", "number", "date", "name"]):
        return "core"
    if any(x in attr_lower for x in ["email", "phone", "address", "url"]):
        return "shell"

    return "halo"


# =============================================================================
# REPORT GENERATOR
# =============================================================================

class ReportGenerator:
    """
    Generates investigation reports from Cymonides-1 data.

    Uses the graph data to produce Nardello-style reports with:
    - Core/Shell/Halo entity organization
    - Proper source attribution
    - Professional tone
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.cymonides = CymonidesClient()
        self.footnote_counter = 0
        self.footnotes: List[Footnote] = []

    async def close(self):
        """Cleanup resources."""
        await self.cymonides.close()

    def _add_footnote(self, source_url: str, description: str = "") -> int:
        """Add footnote and return number."""
        self.footnote_counter += 1
        self.footnotes.append(Footnote(
            number=self.footnote_counter,
            source_url=source_url,
            accessed_date=datetime.now().strftime("%Y-%m-%d"),
            description=description
        ))
        return self.footnote_counter

    async def generate_report(
        self,
        investigation_id: str,
        title: str = None
    ) -> InvestigationReport:
        """
        Generate full investigation report.

        Args:
            investigation_id: Investigation node ID
            title: Report title (defaults to investigation tasking)

        Returns:
            Complete InvestigationReport
        """
        # Get investigation node
        inv_data = await self.cymonides.get_node(
            project_id=self.project_id,
            node_id=investigation_id
        )

        inv_node = inv_data.get("results", [{}])[0] if inv_data.get("results") else {}
        tasking = inv_node.get("properties", {}).get("tasking", "Investigation Report")

        # Get all entities via grid
        entities = await self._get_all_entities()

        # Generate entity sections
        entity_sections = []
        for entity in entities:
            section = await self._generate_entity_section(entity)
            entity_sections.append(section)

        # Group by type
        person_sections = [s for s in entity_sections if s.entity_type == "person"]
        company_sections = [s for s in entity_sections if s.entity_type == "company"]
        other_sections = [s for s in entity_sections if s.entity_type not in ["person", "company"]]

        # Build report sections
        sections = []

        if person_sections:
            sections.append(ReportSection(
                title="Persons of Interest",
                content="The following individuals were identified during the investigation.",
                entities=person_sections
            ))

        if company_sections:
            sections.append(ReportSection(
                title="Corporate Entities",
                content="The following companies were identified during the investigation.",
                entities=company_sections
            ))

        if other_sections:
            sections.append(ReportSection(
                title="Additional Entities",
                content="Additional entities identified during the investigation.",
                entities=other_sections
            ))

        # Generate executive summary
        exec_summary = self._generate_executive_summary(
            tasking=tasking,
            person_count=len(person_sections),
            company_count=len(company_sections),
            other_count=len(other_sections)
        )

        # Generate background
        background = self._generate_background(tasking)

        return InvestigationReport(
            title=title or f"Investigation Report: {tasking[:50]}",
            investigation_id=investigation_id,
            project_id=self.project_id,
            generated_at=datetime.now().isoformat(),
            executive_summary=exec_summary,
            background=background,
            sections=sections,
            footnotes=self.footnotes,
            entities_covered=len(entity_sections),
            sources_cited=len(self.footnotes)
        )

    async def _get_all_entities(self) -> List[Dict[str, Any]]:
        """Get all entity nodes from project."""
        result = await self.cymonides.get_rotated_grid(
            project_id=self.project_id,
            mode="subject",
            filter_type="entity",
            limit=100
        )

        entities = []
        for row in result.get("rows", []):
            primary = row.get("primaryNode", {})
            if primary:
                primary["_related"] = row.get("relatedNodes", [])
                entities.append(primary)

        return entities

    async def _generate_entity_section(
        self,
        entity: Dict[str, Any]
    ) -> EntitySection:
        """Generate section for an entity."""
        entity_id = entity.get("id", "")
        entity_type = entity.get("type", "unknown")
        label = entity.get("label", "Unknown")
        properties = entity.get("properties", {})
        related = entity.get("_related", [])

        # Classify attributes
        core_attrs = {}
        shell_attrs = {}
        halo_attrs = {}

        for key, value in properties.items():
            if value is None or value == "":
                continue

            layer = classify_attribute(entity_type, key)
            if layer == "core":
                core_attrs[key] = value
            elif layer == "shell":
                shell_attrs[key] = value
            else:
                halo_attrs[key] = value

        # Extract relationships
        relationships = []
        for rel in related:
            relationships.append({
                "type": rel.get("relationship", "related_to"),
                "target_label": rel.get("label", "Unknown"),
                "target_type": rel.get("type", "unknown"),
                "confidence": rel.get("confidence", 0.5)
            })

        # Add footnotes for sources
        source_urls = properties.get("source_urls", [])
        if isinstance(source_urls, str):
            source_urls = [source_urls]

        footnotes = []
        for url in source_urls[:5]:  # Max 5 footnotes per entity
            fn_num = self._add_footnote(url, f"Source for {label}")
            footnotes.append(self.footnotes[-1])

        return EntitySection(
            entity_id=entity_id,
            entity_type=entity_type,
            label=label,
            core_attributes=core_attrs,
            shell_attributes=shell_attrs,
            halo_attributes=halo_attrs,
            relationships=relationships,
            footnotes=footnotes
        )

    def _generate_executive_summary(
        self,
        tasking: str,
        person_count: int,
        company_count: int,
        other_count: int
    ) -> str:
        """Generate executive summary paragraph."""
        total = person_count + company_count + other_count

        summary = f"""This report presents the findings of an investigation into {tasking}. """

        if total == 0:
            summary += "No significant entities were identified during the investigation."
        else:
            parts = []
            if person_count:
                parts.append(f"{person_count} individual{'s' if person_count > 1 else ''}")
            if company_count:
                parts.append(f"{company_count} corporate entit{'ies' if company_count > 1 else 'y'}")
            if other_count:
                parts.append(f"{other_count} additional entit{'ies' if other_count > 1 else 'y'}")

            summary += f"The investigation identified {' and '.join(parts)}."

        return summary

    def _generate_background(self, tasking: str) -> str:
        """Generate background section."""
        return f"""The investigation was initiated to examine {tasking}.
This report summarizes publicly available information and should not be
construed as legal advice or a definitive assessment of any individual
or entity's conduct."""


# =============================================================================
# OUTPUT FORMATTERS
# =============================================================================

def format_report_markdown(report: InvestigationReport) -> str:
    """Format report as Markdown."""
    lines = []

    # Title
    lines.append(f"# {report.title}")
    lines.append("")
    lines.append(f"*Generated: {report.generated_at}*")
    lines.append(f"*Project: {report.project_id}*")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(report.executive_summary)
    lines.append("")

    # Background
    lines.append("## Background")
    lines.append("")
    lines.append(report.background)
    lines.append("")

    # Sections
    for section in report.sections:
        lines.append(f"## {section.title}")
        lines.append("")
        lines.append(section.content)
        lines.append("")

        for entity in section.entities:
            lines.append(f"### {entity.label}")
            lines.append("")

            # Core attributes
            if entity.core_attributes:
                lines.append("**Identity Information:**")
                lines.append("")
                for key, value in entity.core_attributes.items():
                    lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
                lines.append("")

            # Shell attributes
            if entity.shell_attributes:
                lines.append("**Contact Information:**")
                lines.append("")
                for key, value in entity.shell_attributes.items():
                    lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
                lines.append("")

            # Relationships
            if entity.relationships:
                lines.append("**Relationships:**")
                lines.append("")
                for rel in entity.relationships:
                    confidence = rel.get("confidence", 0.5)
                    conf_str = "high" if confidence > 0.8 else "medium" if confidence > 0.5 else "low"
                    lines.append(f"- {rel['type'].replace('_', ' ')} → {rel['target_label']} ({conf_str} confidence)")
                lines.append("")

            # Halo attributes
            if entity.halo_attributes:
                lines.append("**Additional Context:**")
                lines.append("")
                for key, value in entity.halo_attributes.items():
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value[:5])
                    lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
                lines.append("")

    # Footnotes
    if report.footnotes:
        lines.append("---")
        lines.append("")
        lines.append("## Sources")
        lines.append("")
        for fn in report.footnotes:
            lines.append(f"{fn.number}. {fn.source_url} (accessed {fn.accessed_date})")
        lines.append("")

    return "\n".join(lines)


def format_report_json(report: InvestigationReport) -> str:
    """Format report as JSON."""
    data = {
        "title": report.title,
        "investigation_id": report.investigation_id,
        "project_id": report.project_id,
        "generated_at": report.generated_at,
        "executive_summary": report.executive_summary,
        "background": report.background,
        "sections": [
            {
                "title": s.title,
                "content": s.content,
                "entities": [
                    {
                        "id": e.entity_id,
                        "type": e.entity_type,
                        "label": e.label,
                        "core": e.core_attributes,
                        "shell": e.shell_attributes,
                        "halo": e.halo_attributes,
                        "relationships": e.relationships
                    }
                    for e in s.entities
                ]
            }
            for s in report.sections
        ],
        "footnotes": [
            {
                "number": fn.number,
                "source_url": fn.source_url,
                "accessed_date": fn.accessed_date
            }
            for fn in report.footnotes
        ],
        "statistics": {
            "entities_covered": report.entities_covered,
            "sources_cited": report.sources_cited
        }
    }

    return json.dumps(data, indent=2, default=str)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def generate_report(
    investigation_id: str,
    project_id: str = "default",
    format: str = "markdown"
) -> str:
    """
    Generate investigation report.

    Args:
        investigation_id: Investigation node ID
        project_id: Project ID
        format: Output format (markdown or json)

    Returns:
        Formatted report string
    """
    generator = ReportGenerator(project_id)
    try:
        report = await generator.generate_report(investigation_id)

        if format == "json":
            return format_report_json(report)
        return format_report_markdown(report)
    finally:
        await generator.close()
