"""
SASTRE Query Constructor - K-U Matrix determines query shape.

The K-U quadrant doesn't just label the query - it determines HOW the query is constructed:
- TRACE: Subject KNOWN, Location UNKNOWN → Broad sweep across jurisdictions
- EXTRACT: Subject UNKNOWN, Location KNOWN → Deep dive into specific source
- VERIFY: Both KNOWN → Precise confirmation query
- DISCOVER: Both UNKNOWN → Brute search with variations
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from ..core.state import (
    Query,
    KUQuadrant,
    Intent,
    Priority,
)


# =============================================================================
# GAP COORDINATES (3D positioning)
# =============================================================================

@dataclass
class GapCoordinates:
    """
    3D coordinate system for precise gap location.

    SUBJECT axis (Y): What entity/attribute are we looking for?
    LOCATION axis (X): Where are we looking?
    NEXUS axis (Z): What connection type? How certain?
    NARRATIVE layer: Why does this matter?
    """
    # SUBJECT axis
    subject_entity: Optional[str] = None
    subject_attribute: Optional[str] = None
    subject_type: Optional[str] = None  # person, company, domain

    # LOCATION axis
    location_geo: Optional[str] = None  # Jurisdiction: CY, UK, BVI
    location_source: Optional[str] = None  # Source: companieshouse.gov.uk
    location_format: Optional[str] = None  # Format: PDF, registry, news
    location_temporal: Optional[str] = None  # Time range: 2020-2023

    # NEXUS axis
    nexus_connection_type: Optional[str] = None  # officer_of, shareholder_of
    nexus_certainty: str = "uncertain"  # certain, probable, uncertain, unknown

    # NARRATIVE layer
    narrative_intent: Optional[str] = None
    narrative_priority: str = "medium"
    narrative_question: Optional[str] = None


@dataclass
class Gap:
    """A gap in the investigation."""
    id: str
    description: str
    k_u_quadrant: KUQuadrant
    intent: Intent
    priority: int = 50

    # Targets
    target_subject: Optional[str] = None
    target_location: Optional[str] = None
    target_section: Optional[str] = None

    # Coordinates
    coordinates: Optional[GapCoordinates] = None

    # Is this gap looking for new entities or enriching known ones?
    is_looking_for_new_entities: bool = False


# =============================================================================
# QUERY CONSTRUCTOR
# =============================================================================

class QueryConstructor:
    """
    Constructs queries based on K-U quadrant and gap coordinates.

    K-U quadrant determines query SHAPE:
    - TRACE: Broad sweep (many locations, one subject)
    - EXTRACT: Deep dive (one location, find subjects)
    - VERIFY: Precise (one location, one subject, confirm)
    - DISCOVER: Wide net (variations across many sources)
    """

    # Jurisdiction mapping for TRACE queries
    OFFSHORE_JURISDICTIONS = ['cy', 'vg', 'ky', 'bvi', 'pa', 'sc', 'je', 'gg', 'im', 'lu']
    MAJOR_JURISDICTIONS = ['uk', 'us', 'de', 'fr', 'ch', 'nl', 'ie', 'sg', 'hk']

    # Source patterns by type
    SOURCE_PATTERNS = {
        'corporate_registry': 'site:*.gov.* OR site:*.gouv.* OR site:opencorporates.com',
        'news': 'site:reuters.com OR site:bloomberg.com OR site:ft.com',
        'social': 'site:linkedin.com OR site:twitter.com OR site:facebook.com',
        'legal': 'site:*.courts.* OR site:pacer.gov OR site:courtlistener.com',
        'offshore': 'site:*.cy OR site:*.vg OR site:*.ky OR site:icij.org',
    }

    def __init__(self):
        from .variations import VariationGenerator
        self.variation_generator = VariationGenerator()

    def construct(self, gap: Gap, coords: Optional[GapCoordinates] = None) -> Query:
        """
        Construct query from gap based on K-U quadrant.
        """
        coords = coords or gap.coordinates or GapCoordinates()

        if gap.k_u_quadrant == KUQuadrant.TRACE:
            return self._construct_trace_query(gap, coords)
        elif gap.k_u_quadrant == KUQuadrant.EXTRACT:
            return self._construct_extract_query(gap, coords)
        elif gap.k_u_quadrant == KUQuadrant.VERIFY:
            return self._construct_verify_query(gap, coords)
        else:  # DISCOVER
            return self._construct_discover_query(gap, coords)

    def _construct_trace_query(self, gap: Gap, coords: GapCoordinates) -> Query:
        """
        TRACE: Subject KNOWN, Location UNKNOWN
        Query shape: "[subject]" WHERE? (broad location sweep)
        """
        subject = coords.subject_entity or gap.target_subject or gap.description

        # Generate variations
        variations = self.variation_generator.generate(subject, coords.subject_type or 'person')
        subject_component = ' OR '.join([f'"{v}"' for v in variations[:5]])

        # Sweep across jurisdictions
        if coords.subject_type == 'company' or 'company' in gap.description.lower():
            # Corporate search - check registries
            jurisdictions = self.OFFSHORE_JURISDICTIONS + self.MAJOR_JURISDICTIONS
            location_component = ' OR '.join([f'site:*.{j}.*' for j in jurisdictions[:10]])
        else:
            # Person search - broader sweep
            location_component = self.SOURCE_PATTERNS['corporate_registry']

        query_string = f'({subject_component}) ({location_component})'

        # Build MACRO
        macro = f'"{subject}"~ => !* => locations?'

        return Query.create(
            macro=macro,
            query_string=query_string,
            narrative_id=gap.target_section or "unknown",
            k_u_quadrant=KUQuadrant.TRACE,
            intent=gap.intent,
            io_module='brute',
        )

    def _construct_extract_query(self, gap: Gap, coords: GapCoordinates) -> Query:
        """
        EXTRACT: Subject UNKNOWN, Location KNOWN
        Query shape: [location] WHO? (entity extraction from source)
        """
        location = coords.location_source or coords.location_geo or gap.target_location

        if coords.location_geo:
            # Jurisdiction-based extraction
            location_component = f'site:*.{coords.location_geo.lower()}.*'
            macro = f'!{coords.location_geo}_registry => entities?'
            io_module = 'torpedo'
        elif coords.location_source:
            # Specific source
            location_component = f'site:{coords.location_source}'
            macro = f'!{coords.location_source} => entities?'
            io_module = 'linklater'
        else:
            # Generic location
            location_component = f'"{location}"'
            macro = f'!{location} => entities?'
            io_module = 'brute'

        # Add temporal filter if available
        if coords.location_temporal:
            location_component += f' {coords.location_temporal}'

        query_string = location_component

        return Query.create(
            macro=macro,
            query_string=query_string,
            narrative_id=gap.target_section or "unknown",
            k_u_quadrant=KUQuadrant.EXTRACT,
            intent=gap.intent,
            io_module=io_module,
        )

    def _construct_verify_query(self, gap: Gap, coords: GapCoordinates) -> Query:
        """
        VERIFY: Both KNOWN
        Query shape: "[subject]" AT [location] CONFIRM
        """
        subject = coords.subject_entity or gap.target_subject
        location = coords.location_source or coords.location_geo or gap.target_location

        # Precise query - exact match at specific source
        subject_component = f'"{subject}"'

        if coords.location_source:
            location_component = f'site:{coords.location_source}'
        elif coords.location_geo:
            location_component = f'site:*.{coords.location_geo.lower()}.*'
        else:
            location_component = f'"{location}"'

        query_string = f'{subject_component} {location_component}'

        # Build MACRO
        location_label = coords.location_geo or coords.location_source or location
        macro = f'"{subject}" => !{location_label} => verify!'

        return Query.create(
            macro=macro,
            query_string=query_string,
            narrative_id=gap.target_section or "unknown",
            k_u_quadrant=KUQuadrant.VERIFY,
            intent=gap.intent,
            io_module='brute',
        )

    def _construct_discover_query(self, gap: Gap, coords: GapCoordinates) -> Query:
        """
        DISCOVER: Both UNKNOWN
        Query shape: Brute search with variations
        """
        # Use whatever we have
        subject = coords.subject_entity or gap.target_subject or gap.description

        # Generate many variations
        variations = self.variation_generator.generate(subject, coords.subject_type or 'person')

        # Wide net query
        subject_component = ' OR '.join([f'"{v}"' for v in variations])

        # Broad source sweep
        location_component = ''  # Let brute search handle sources

        query_string = f'({subject_component})'

        # Build MACRO
        macro = f'"{subject}"~ => !brute => discover!'

        return Query.create(
            macro=macro,
            query_string=query_string,
            narrative_id=gap.target_section or "unknown",
            k_u_quadrant=KUQuadrant.DISCOVER,
            intent=gap.intent,
            io_module='brute',
        )

    def construct_supplementary_queries(self, gap: Gap, primary: Query) -> List[Query]:
        """
        Generate supplementary queries based on K-U quadrant.
        """
        supplementary = []
        coords = gap.coordinates or GapCoordinates()

        if gap.k_u_quadrant == KUQuadrant.TRACE and coords.subject_entity:
            # Add social media search
            supplementary.append(Query.create(
                macro=f'"{coords.subject_entity}" => !social => profiles?',
                query_string=f'"{coords.subject_entity}" (linkedin OR twitter OR facebook)',
                narrative_id=primary.narrative_id,
                k_u_quadrant=KUQuadrant.TRACE,
                intent=gap.intent,
                io_module='eye-d',
            ))

            # Add breach data search
            supplementary.append(Query.create(
                macro=f'"{coords.subject_entity}" => !breaches => data?',
                query_string=f'"{coords.subject_entity}" breach OR leak',
                narrative_id=primary.narrative_id,
                k_u_quadrant=KUQuadrant.TRACE,
                intent=gap.intent,
                io_module='eye-d',
            ))

        elif gap.k_u_quadrant == KUQuadrant.EXTRACT and coords.location_geo:
            # Add registry-specific query
            supplementary.append(Query.create(
                macro=f'!{coords.location_geo}_registry => officers?',
                query_string=f'site:*.{coords.location_geo.lower()}.* directors officers',
                narrative_id=primary.narrative_id,
                k_u_quadrant=KUQuadrant.EXTRACT,
                intent=gap.intent,
                io_module='torpedo',
            ))

        elif gap.k_u_quadrant == KUQuadrant.VERIFY:
            # Add news verification
            if coords.subject_entity:
                supplementary.append(Query.create(
                    macro=f'"{coords.subject_entity}" => !news => mentions?',
                    query_string=f'"{coords.subject_entity}" {self.SOURCE_PATTERNS["news"]}',
                    narrative_id=primary.narrative_id,
                    k_u_quadrant=KUQuadrant.VERIFY,
                    intent=gap.intent,
                    io_module='brute',
                ))

        return supplementary


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def construct_query_from_gap(gap: Gap) -> List[Query]:
    """
    Construct primary and supplementary queries from a gap.
    """
    constructor = QueryConstructor()

    primary = constructor.construct(gap)
    supplementary = constructor.construct_supplementary_queries(gap, primary)

    return [primary] + supplementary
