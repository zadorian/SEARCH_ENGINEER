"""
SASTRE IO Result Transformer

Transforms IO execution results into Finding objects for auto-report generation.
Bridges the gap between IO Matrix execution and SASTRE report writer.

Gap solved:
    IO Execution → [THIS TRANSFORMER] → Finding Objects → Report Writer

Features:
- Entity extraction from IO results
- Core/Shell/Halo attribute classification
- Finding object creation
- Source attribution tracking
- Streaming integration with document sections
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Local imports
from ..core.state import EntityType, Query, QueryState
from ..report_writer import EntitySection, Footnote, CORE_ATTRIBUTES, SHELL_ATTRIBUTES


class AttributeLayer(Enum):
    """Core/Shell/Halo classification for entity attributes."""
    CORE = "core"       # Identity: name, ID, DOB - highest confidence
    SHELL = "shell"     # Contact: email, phone, address - medium confidence
    HALO = "halo"       # Context: news, associations - lowest confidence


class EntityRole(Enum):
    """Role of entity in investigation."""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    PERIPHERAL = "peripheral"


@dataclass
class Entity:
    """Simple entity representation for transformer output."""
    id: str
    type: str
    label: str
    role: EntityRole = EntityRole.PRIMARY
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Finding:
    """A finding from IO execution."""
    entity_type: str
    entity_value: str
    attribute: str
    value: Any
    layer: AttributeLayer
    source_url: str = ""
    source_name: str = ""
    confidence: float = 0.8
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())
    rule_id: str = ""


@dataclass
class TransformResult:
    """Result of transforming IO execution output."""
    entities: List[Entity]
    findings: List[Finding]
    sections: List[EntitySection]
    footnotes: List[Footnote]
    raw_data: Dict[str, Any]
    transform_time_ms: int = 0


class IOResultTransformer:
    """
    Transforms IO execution results into structured findings for reports.

    Workflow:
    1. Receive raw IO execution result
    2. Extract entities (persons, companies, domains, etc.)
    3. Classify attributes into Core/Shell/Halo
    4. Create Finding objects with source attribution
    5. Generate EntitySection objects for report writer
    6. Return findings ready for streaming to document
    """

    # Field code to attribute name mapping (from legend.json)
    FIELD_MAPPINGS = {
        # Person fields
        7: ("person_name", "person", AttributeLayer.CORE),
        31: ("person_name", "person", AttributeLayer.CORE),
        32: ("person_email", "person", AttributeLayer.SHELL),
        33: ("person_phone", "person", AttributeLayer.SHELL),
        35: ("person_address", "person", AttributeLayer.SHELL),
        38: ("person_profile_url", "person", AttributeLayer.SHELL),
        40: ("person_role_job", "person", AttributeLayer.CORE),

        # Company fields
        13: ("company_name", "company", AttributeLayer.CORE),
        42: ("company_name", "company", AttributeLayer.CORE),
        14: ("company_reg_id", "company", AttributeLayer.CORE),
        15: ("company_vat_id", "company", AttributeLayer.CORE),
        47: ("company_address", "company", AttributeLayer.SHELL),
        48: ("company_country", "company", AttributeLayer.CORE),
        49: ("company_status", "company", AttributeLayer.CORE),
        50: ("company_incorporation_date", "company", AttributeLayer.CORE),
        58: ("company_officers", "company", AttributeLayer.SHELL),
        59: ("company_officer_name", "company", AttributeLayer.SHELL),
        66: ("company_beneficial_owners", "company", AttributeLayer.SHELL),

        # Domain fields
        6: ("domain_url", "domain", AttributeLayer.CORE),
        129: ("domain_url", "domain", AttributeLayer.CORE),
        130: ("domain_ip", "domain", AttributeLayer.SHELL),
        191: ("domain_backlinks", "domain", AttributeLayer.HALO),
        203: ("domain_outlinks", "domain", AttributeLayer.HALO),

        # Email fields
        1: ("email", "email", AttributeLayer.CORE),
        187: ("person_email_breaches", "email", AttributeLayer.HALO),

        # Events/Topics/Themes
        267: ("extracted_events", "event", AttributeLayer.HALO),
        268: ("extracted_topics", "topic", AttributeLayer.HALO),
        269: ("extracted_themes", "theme", AttributeLayer.HALO),
    }

    def __init__(self):
        self._footnote_counter = 0

    def transform(self, io_result: Dict[str, Any], rule_id: str = "") -> TransformResult:
        """
        Transform IO execution result into structured findings.

        Args:
            io_result: Raw result from IOExecutor.execute()
            rule_id: ID of the rule that was executed

        Returns:
            TransformResult with entities, findings, and sections
        """
        import time
        start_time = time.time()

        entities: List[Entity] = []
        findings: List[Finding] = []
        footnotes: List[Footnote] = []

        # Handle error results
        if "error" in io_result:
            return TransformResult(
                entities=[],
                findings=[],
                sections=[],
                footnotes=[],
                raw_data=io_result,
                transform_time_ms=int((time.time() - start_time) * 1000)
            )

        # Extract results from IO response
        results = io_result.get("results", [])
        if not isinstance(results, list):
            results = [io_result]

        for result in results:
            result_rule_id = result.get("rule_id", rule_id)
            source_url = result.get("source_url", "")
            source_name = result.get("source_name", result_rule_id)
            data = result.get("data", result)

            # Extract findings from data
            for key, value in self._flatten_dict(data):
                if value is None or value == "" or value == []:
                    continue

                # Try to classify the attribute
                layer = self._classify_attribute(key)
                entity_type = self._infer_entity_type(key)

                finding = Finding(
                    entity_type=entity_type,
                    entity_value=str(value)[:500],  # Truncate long values
                    attribute=key,
                    value=value,
                    layer=layer,
                    source_url=source_url,
                    source_name=source_name,
                    rule_id=result_rule_id
                )
                findings.append(finding)

                # Create footnote if we have source
                if source_url:
                    self._footnote_counter += 1
                    footnotes.append(Footnote(
                        number=self._footnote_counter,
                        source_url=source_url,
                        accessed_date=datetime.now().strftime("%Y-%m-%d"),
                        description=f"Retrieved via {source_name}"
                    ))

            # Extract entities
            extracted_entities = self._extract_entities(data)
            entities.extend(extracted_entities)

        # Generate entity sections for report
        sections = self._generate_sections(entities, findings, footnotes)

        transform_time = int((time.time() - start_time) * 1000)

        return TransformResult(
            entities=entities,
            findings=findings,
            sections=sections,
            footnotes=footnotes,
            raw_data=io_result,
            transform_time_ms=transform_time
        )

    def _flatten_dict(self, d: Dict, parent_key: str = "") -> List[Tuple[str, Any]]:
        """Flatten nested dict into key-value pairs."""
        items = []
        if not isinstance(d, dict):
            return [(parent_key, d)] if parent_key else []

        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key))
            elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                for i, item in enumerate(v):
                    items.extend(self._flatten_dict(item, f"{new_key}[{i}]"))
            else:
                items.append((new_key, v))
        return items

    def _classify_attribute(self, attr_name: str) -> AttributeLayer:
        """Classify attribute into Core/Shell/Halo layer."""
        attr_lower = attr_name.lower()

        # Core attributes (identity)
        core_patterns = ["name", "id", "number", "date", "dob", "status", "type", "country", "jurisdiction"]
        if any(p in attr_lower for p in core_patterns):
            return AttributeLayer.CORE

        # Shell attributes (contact)
        shell_patterns = ["email", "phone", "address", "url", "profile", "officer", "owner", "shareholder"]
        if any(p in attr_lower for p in shell_patterns):
            return AttributeLayer.SHELL

        # Halo attributes (context)
        halo_patterns = ["news", "breach", "backlink", "outlink", "event", "topic", "theme", "mention", "association"]
        if any(p in attr_lower for p in halo_patterns):
            return AttributeLayer.HALO

        # Default to shell
        return AttributeLayer.SHELL

    def _infer_entity_type(self, attr_name: str) -> str:
        """Infer entity type from attribute name."""
        attr_lower = attr_name.lower()

        if "person" in attr_lower or "officer" in attr_lower or "owner" in attr_lower:
            return "person"
        elif "company" in attr_lower or "organization" in attr_lower or "business" in attr_lower:
            return "company"
        elif "domain" in attr_lower or "url" in attr_lower or "website" in attr_lower:
            return "domain"
        elif "email" in attr_lower:
            return "email"
        elif "phone" in attr_lower:
            return "phone"
        elif "event" in attr_lower:
            return "event"
        elif "topic" in attr_lower:
            return "topic"
        else:
            return "unknown"

    def _extract_entities(self, data: Dict[str, Any]) -> List[Entity]:
        """Extract Entity objects from data."""
        entities = []

        # Look for common entity patterns
        if "company_name" in data or "name" in data:
            name = data.get("company_name") or data.get("name", "")
            if name:
                entities.append(Entity(
                    id=f"company_{hash(name) % 10000}",
                    type="company",
                    label=str(name),
                    role=EntityRole.PRIMARY,
                    attributes=data
                ))

        if "person_name" in data:
            name = data.get("person_name", "")
            if name:
                entities.append(Entity(
                    id=f"person_{hash(name) % 10000}",
                    type="person",
                    label=str(name),
                    role=EntityRole.PRIMARY,
                    attributes=data
                ))

        if "domain_url" in data or "domain" in data:
            domain = data.get("domain_url") or data.get("domain", "")
            if domain:
                entities.append(Entity(
                    id=f"domain_{hash(domain) % 10000}",
                    type="domain",
                    label=str(domain),
                    role=EntityRole.PRIMARY,
                    attributes=data
                ))

        return entities

    def _generate_sections(
        self,
        entities: List[Entity],
        findings: List[Finding],
        footnotes: List[Footnote]
    ) -> List[EntitySection]:
        """Generate EntitySection objects for report writer."""
        sections = []

        # Group findings by entity type
        entity_findings: Dict[str, List[Finding]] = {}
        for finding in findings:
            key = finding.entity_type
            if key not in entity_findings:
                entity_findings[key] = []
            entity_findings[key].append(finding)

        # Create sections for each entity type
        for entity in entities:
            entity_type = entity.type
            relevant_findings = entity_findings.get(entity_type, [])

            # Classify findings into Core/Shell/Halo
            core_attrs = {}
            shell_attrs = {}
            halo_attrs = {}

            for finding in relevant_findings:
                if finding.layer == AttributeLayer.CORE:
                    core_attrs[finding.attribute] = finding.value
                elif finding.layer == AttributeLayer.SHELL:
                    shell_attrs[finding.attribute] = finding.value
                else:
                    halo_attrs[finding.attribute] = finding.value

            section = EntitySection(
                entity_id=entity.id,
                entity_type=entity_type,
                label=entity.label,
                core_attributes=core_attrs,
                shell_attributes=shell_attrs,
                halo_attributes=halo_attrs,
                relationships=[],
                footnotes=footnotes
            )
            sections.append(section)

        return sections

    def to_markdown(self, result: TransformResult) -> str:
        """Convert transform result to markdown for narrative."""
        lines = []

        for section in result.sections:
            lines.append(f"### {section.label}")
            lines.append("")

            # Core attributes
            if section.core_attributes:
                lines.append("**Identity (Core)**")
                for k, v in section.core_attributes.items():
                    lines.append(f"- {k}: {v}")
                lines.append("")

            # Shell attributes
            if section.shell_attributes:
                lines.append("**Contact (Shell)**")
                for k, v in section.shell_attributes.items():
                    if isinstance(v, list):
                        lines.append(f"- {k}:")
                        for item in v[:5]:  # Limit to 5 items
                            lines.append(f"  - {item}")
                    else:
                        lines.append(f"- {k}: {v}")
                lines.append("")

            # Halo attributes
            if section.halo_attributes:
                lines.append("**Context (Halo)**")
                for k, v in section.halo_attributes.items():
                    if isinstance(v, list):
                        lines.append(f"- {k}: {len(v)} items")
                    else:
                        lines.append(f"- {k}: {v}")
                lines.append("")

        # Footnotes
        if result.footnotes:
            lines.append("---")
            lines.append("**Sources:**")
            for fn in result.footnotes[:10]:  # Limit to 10 footnotes
                lines.append(f"[{fn.number}] {fn.source_url} (accessed {fn.accessed_date})")

        return "\n".join(lines)

    async def transform_and_stream(
        self,
        io_result: Dict[str, Any],
        section_title: str,
        document_id: str,
        bridges: 'SastreInfrastructure'
    ) -> TransformResult:
        """
        Transform IO result and stream findings to document section.

        This is the main integration point between IO execution and report writing.

        Args:
            io_result: Raw IO execution result
            section_title: Target document section header
            document_id: Target document ID
            bridges: SASTRE infrastructure for streaming

        Returns:
            TransformResult with streamed findings
        """
        # Transform the result
        result = self.transform(io_result)

        # Convert to markdown
        markdown = self.to_markdown(result)

        # Stream to document section via watchers bridge
        if bridges.watchers_bridge and markdown:
            await bridges.watchers_bridge.stream_finding_to_section(
                document_id=document_id,
                section_title=section_title,
                content=markdown
            )

        return result


# Convenience functions
def transform_io_result(io_result: Dict[str, Any], rule_id: str = "") -> TransformResult:
    """Transform IO execution result to structured findings."""
    transformer = IOResultTransformer()
    return transformer.transform(io_result, rule_id)


def findings_to_markdown(findings: List[Finding]) -> str:
    """Convert list of findings to markdown."""
    lines = []
    for finding in findings:
        lines.append(f"- **{finding.attribute}**: {finding.value} ({finding.layer.value})")
    return "\n".join(lines)


__all__ = [
    'AttributeLayer',
    'EntityRole',
    'Entity',
    'Finding',
    'TransformResult',
    'IOResultTransformer',
    'transform_io_result',
    'findings_to_markdown'
]
