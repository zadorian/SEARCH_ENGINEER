"""
SASTRE Wedge Query Generator - Splitting queries to disambiguate entities.

When passive checks are inconclusive, we need ACTIVE disambiguation.
Wedge queries are designed to SPLIT colliding entities:

"If they're different people, Query X will return different results."

Key wedge types:
1. TEMPORAL WEDGE: "X at Company Y [2015-2018]" - Only true person was there then
2. GEOGRAPHIC WEDGE: "X in Cyprus" vs "X in Malta" - Split by location
3. NETWORK WEDGE: "X AND spouse_name" - Only true person has that spouse
4. IDENTIFIER WEDGE: "X passport:ABC123" - Only one will match
5. PROFESSIONAL WEDGE: "X lawyer" vs "X accountant" - Split by profession
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum

from ..core.state import Entity, EntityCollision, EntityType


# =============================================================================
# WEDGE TYPES
# =============================================================================

class WedgeType(Enum):
    """Types of wedge queries for disambiguation."""
    TEMPORAL = "temporal"          # Time-bound queries
    GEOGRAPHIC = "geographic"      # Location-based splitting
    NETWORK = "network"            # Relationship-based splitting
    IDENTIFIER = "identifier"      # Unique ID based
    PROFESSIONAL = "professional"  # Role/occupation based
    LINGUISTIC = "linguistic"      # Name spelling variations
    ORGANIZATIONAL = "organizational"  # Company affiliation


# =============================================================================
# WEDGE QUERY
# =============================================================================

@dataclass
class WedgeQuery:
    """A query designed to split colliding entities."""
    query_string: str
    wedge_type: WedgeType
    expected_if_same: str      # What we expect if they're the same entity
    expected_if_different: str # What we expect if they're different
    confidence_boost: float    # How much this resolves if successful
    collision_id: str
    target_entity: str         # "a" or "b" - which entity this tests
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WedgeQuerySet:
    """Collection of wedge queries for a collision."""
    collision_id: str
    entity_a_id: str
    entity_b_id: str
    queries: List[WedgeQuery]
    recommended_order: List[int]  # Indices in order of expected effectiveness


# =============================================================================
# WEDGE QUERY GENERATOR
# =============================================================================

class WedgeQueryGenerator:
    """
    Generates wedge queries to actively disambiguate entity collisions.

    Philosophy:
    - Passive checks use existing data
    - Wedge queries SEEK new data specifically to split entities
    - Each wedge is designed so same/different entities give different results
    """

    def generate(
        self,
        entity_a: Entity,
        entity_b: Entity,
        collision: EntityCollision
    ) -> WedgeQuerySet:
        """
        Generate wedge queries for a collision.
        """
        queries = []

        # 1. Temporal wedges
        temporal_wedges = self._generate_temporal_wedges(entity_a, entity_b)
        queries.extend(temporal_wedges)

        # 2. Geographic wedges
        geo_wedges = self._generate_geographic_wedges(entity_a, entity_b)
        queries.extend(geo_wedges)

        # 3. Network wedges
        network_wedges = self._generate_network_wedges(entity_a, entity_b)
        queries.extend(network_wedges)

        # 4. Professional wedges
        prof_wedges = self._generate_professional_wedges(entity_a, entity_b)
        queries.extend(prof_wedges)

        # 5. Organizational wedges
        org_wedges = self._generate_organizational_wedges(entity_a, entity_b)
        queries.extend(org_wedges)

        # Set collision ID on all queries
        for q in queries:
            q.collision_id = collision.collision_id

        # Sort by expected effectiveness
        recommended = self._rank_wedges(queries)

        return WedgeQuerySet(
            collision_id=collision.collision_id,
            entity_a_id=entity_a.entity_id,
            entity_b_id=entity_b.entity_id,
            queries=queries,
            recommended_order=recommended,
        )

    def _generate_temporal_wedges(
        self,
        entity_a: Entity,
        entity_b: Entity
    ) -> List[WedgeQuery]:
        """
        Generate time-based wedge queries.

        If A was at Company X in 2015, and B claims to be same person,
        searching "B at Company X [2015]" should find results.
        """
        wedges = []

        # Get temporal anchors from each entity
        a_anchors = self._extract_temporal_anchors(entity_a)
        b_anchors = self._extract_temporal_anchors(entity_b)

        # For each anchor from A, create query testing B
        for anchor in a_anchors:
            if anchor['year'] and anchor['context']:
                query = f'"{entity_b.display_name}" "{anchor["context"]}" {anchor["year"]}'
                wedges.append(WedgeQuery(
                    query_string=query,
                    wedge_type=WedgeType.TEMPORAL,
                    expected_if_same=f"Should find {entity_b.display_name} at {anchor['context']} in {anchor['year']}",
                    expected_if_different=f"Should NOT find {entity_b.display_name} at {anchor['context']} in {anchor['year']}",
                    confidence_boost=0.3,
                    collision_id="",
                    target_entity="b",
                    metadata={'anchor': anchor}
                ))

        # Vice versa for B's anchors testing A
        for anchor in b_anchors:
            if anchor['year'] and anchor['context']:
                query = f'"{entity_a.display_name}" "{anchor["context"]}" {anchor["year"]}'
                wedges.append(WedgeQuery(
                    query_string=query,
                    wedge_type=WedgeType.TEMPORAL,
                    expected_if_same=f"Should find {entity_a.display_name} at {anchor['context']} in {anchor['year']}",
                    expected_if_different=f"Should NOT find {entity_a.display_name} at {anchor['context']} in {anchor['year']}",
                    confidence_boost=0.3,
                    collision_id="",
                    target_entity="a",
                    metadata={'anchor': anchor}
                ))

        return wedges

    def _generate_geographic_wedges(
        self,
        entity_a: Entity,
        entity_b: Entity
    ) -> List[WedgeQuery]:
        """
        Generate location-based wedge queries.

        If A is in Cyprus and B is in Malta, searching each in the
        other's jurisdiction should show absence.
        """
        wedges = []

        # Get locations from each entity
        a_locations = self._extract_locations(entity_a)
        b_locations = self._extract_locations(entity_b)

        # Find non-overlapping locations
        a_unique = a_locations - b_locations
        b_unique = b_locations - a_locations

        # Test B in A's unique locations
        for loc in a_unique:
            query = f'"{entity_b.display_name}" site:*.{loc.lower()} OR "{entity_b.display_name}" "{loc}"'
            wedges.append(WedgeQuery(
                query_string=query,
                wedge_type=WedgeType.GEOGRAPHIC,
                expected_if_same=f"Should find {entity_b.display_name} in {loc}",
                expected_if_different=f"Should NOT find {entity_b.display_name} in {loc}",
                confidence_boost=0.25,
                collision_id="",
                target_entity="b",
                metadata={'location': loc, 'source': 'a'}
            ))

        # Test A in B's unique locations
        for loc in b_unique:
            query = f'"{entity_a.display_name}" site:*.{loc.lower()} OR "{entity_a.display_name}" "{loc}"'
            wedges.append(WedgeQuery(
                query_string=query,
                wedge_type=WedgeType.GEOGRAPHIC,
                expected_if_same=f"Should find {entity_a.display_name} in {loc}",
                expected_if_different=f"Should NOT find {entity_a.display_name} in {loc}",
                confidence_boost=0.25,
                collision_id="",
                target_entity="a",
                metadata={'location': loc, 'source': 'b'}
            ))

        return wedges

    def _generate_network_wedges(
        self,
        entity_a: Entity,
        entity_b: Entity
    ) -> List[WedgeQuery]:
        """
        Generate relationship-based wedge queries.

        If A has spouse "Jane Smith", searching "B AND Jane Smith"
        should find results if same person.
        """
        wedges = []

        # Get network from each entity
        a_network = self._extract_network(entity_a)
        b_network = self._extract_network(entity_b)

        # Test B with A's network
        for person, relationship in a_network:
            query = f'"{entity_b.display_name}" AND "{person}"'
            wedges.append(WedgeQuery(
                query_string=query,
                wedge_type=WedgeType.NETWORK,
                expected_if_same=f"Should find {entity_b.display_name} with {relationship} {person}",
                expected_if_different=f"Should NOT find {entity_b.display_name} with {person}",
                confidence_boost=0.35,  # Network is strong signal
                collision_id="",
                target_entity="b",
                metadata={'network_person': person, 'relationship': relationship}
            ))

        # Test A with B's network
        for person, relationship in b_network:
            query = f'"{entity_a.display_name}" AND "{person}"'
            wedges.append(WedgeQuery(
                query_string=query,
                wedge_type=WedgeType.NETWORK,
                expected_if_same=f"Should find {entity_a.display_name} with {relationship} {person}",
                expected_if_different=f"Should NOT find {entity_a.display_name} with {person}",
                confidence_boost=0.35,
                collision_id="",
                target_entity="a",
                metadata={'network_person': person, 'relationship': relationship}
            ))

        return wedges

    def _generate_professional_wedges(
        self,
        entity_a: Entity,
        entity_b: Entity
    ) -> List[WedgeQuery]:
        """
        Generate profession-based wedge queries.

        If A is a "lawyer" and B is an "accountant", these
        professions can split them.
        """
        wedges = []

        # Only for persons
        if entity_a.entity_type != EntityType.PERSON:
            return wedges

        a_profession = entity_a.get_attribute('profession')
        b_profession = entity_b.get_attribute('profession')

        if a_profession and b_profession:
            a_prof = str(a_profession.value).lower()
            b_prof = str(b_profession.value).lower()

            if a_prof != b_prof:
                # Test B with A's profession
                query = f'"{entity_b.display_name}" "{a_prof}"'
                wedges.append(WedgeQuery(
                    query_string=query,
                    wedge_type=WedgeType.PROFESSIONAL,
                    expected_if_same=f"Should find {entity_b.display_name} as {a_prof}",
                    expected_if_different=f"Should NOT find {entity_b.display_name} as {a_prof}",
                    confidence_boost=0.2,
                    collision_id="",
                    target_entity="b",
                    metadata={'profession': a_prof}
                ))

                # Test A with B's profession
                query = f'"{entity_a.display_name}" "{b_prof}"'
                wedges.append(WedgeQuery(
                    query_string=query,
                    wedge_type=WedgeType.PROFESSIONAL,
                    expected_if_same=f"Should find {entity_a.display_name} as {b_prof}",
                    expected_if_different=f"Should NOT find {entity_a.display_name} as {b_prof}",
                    confidence_boost=0.2,
                    collision_id="",
                    target_entity="a",
                    metadata={'profession': b_prof}
                ))

        return wedges

    def _generate_organizational_wedges(
        self,
        entity_a: Entity,
        entity_b: Entity
    ) -> List[WedgeQuery]:
        """
        Generate company-affiliation wedge queries.

        If A was director at "Acme Corp", searching "B director Acme Corp"
        should find results if same person.
        """
        wedges = []

        # Get company affiliations
        a_companies = self._extract_company_affiliations(entity_a)
        b_companies = self._extract_company_affiliations(entity_b)

        # Test B with A's companies
        for company, role in a_companies:
            query = f'"{entity_b.display_name}" "{company}" {role if role else ""}'
            wedges.append(WedgeQuery(
                query_string=query.strip(),
                wedge_type=WedgeType.ORGANIZATIONAL,
                expected_if_same=f"Should find {entity_b.display_name} at {company}",
                expected_if_different=f"Should NOT find {entity_b.display_name} at {company}",
                confidence_boost=0.3,
                collision_id="",
                target_entity="b",
                metadata={'company': company, 'role': role}
            ))

        # Test A with B's companies
        for company, role in b_companies:
            query = f'"{entity_a.display_name}" "{company}" {role if role else ""}'
            wedges.append(WedgeQuery(
                query_string=query.strip(),
                wedge_type=WedgeType.ORGANIZATIONAL,
                expected_if_same=f"Should find {entity_a.display_name} at {company}",
                expected_if_different=f"Should NOT find {entity_a.display_name} at {company}",
                confidence_boost=0.3,
                collision_id="",
                target_entity="a",
                metadata={'company': company, 'role': role}
            ))

        return wedges

    def _extract_temporal_anchors(self, entity: Entity) -> List[Dict[str, Any]]:
        """Extract temporal anchors (year + context) from entity."""
        anchors = []

        # Check halo for dated relationships
        for attr_name, attr in entity.halo.items():
            if hasattr(attr, 'found_at') and attr.found_at:
                year = None
                if hasattr(attr.found_at, 'year'):
                    year = attr.found_at.year
                elif isinstance(attr.found_at, str) and len(attr.found_at) >= 4:
                    try:
                        year = int(attr.found_at[:4])
                    except ValueError:
                        pass

                if year:
                    anchors.append({
                        'year': year,
                        'context': str(attr.value) if hasattr(attr, 'value') else attr_name,
                        'source': attr.source if hasattr(attr, 'source') else None
                    })

        return anchors

    def _extract_locations(self, entity: Entity) -> set:
        """Extract location names from entity."""
        locations = set()

        # Check core/shell/halo for location fields
        location_fields = ['jurisdiction', 'country', 'nationality', 'address', 'birth_place', 'residence']

        for field in location_fields:
            attr = entity.get_attribute(field)
            if attr:
                value = str(attr.value).strip()
                # Extract country/jurisdiction codes
                if len(value) == 2:
                    locations.add(value.upper())
                else:
                    locations.add(value)

        return locations

    def _extract_network(self, entity: Entity) -> List[Tuple[str, str]]:
        """Extract network relationships from entity."""
        network = []

        # Relationship fields
        rel_fields = [
            ('spouse', 'spouse'),
            ('family', 'family member'),
            ('associate', 'associate'),
            ('partner', 'business partner'),
            ('shareholder_of', 'shareholder in'),
            ('officer_of', 'officer at'),
        ]

        for field, label in rel_fields:
            attr = entity.get_attribute(field)
            if attr:
                if isinstance(attr.value, list):
                    for v in attr.value:
                        network.append((str(v), label))
                else:
                    network.append((str(attr.value), label))

        return network

    def _extract_company_affiliations(self, entity: Entity) -> List[Tuple[str, Optional[str]]]:
        """Extract company affiliations from entity."""
        affiliations = []

        # Check for company relationships in halo
        company_fields = ['employer', 'company', 'officer_of', 'director_of', 'shareholder_of']

        for field in company_fields:
            attr = entity.get_attribute(field)
            if attr:
                role = field.replace('_of', '').replace('_at', '')
                if isinstance(attr.value, list):
                    for v in attr.value:
                        affiliations.append((str(v), role))
                else:
                    affiliations.append((str(attr.value), role))

        return affiliations

    def _rank_wedges(self, wedges: List[WedgeQuery]) -> List[int]:
        """Rank wedges by expected effectiveness."""
        # Score each wedge
        scores = []
        for i, w in enumerate(wedges):
            score = w.confidence_boost

            # Boost network wedges (most discriminating)
            if w.wedge_type == WedgeType.NETWORK:
                score *= 1.3
            # Boost organizational wedges
            elif w.wedge_type == WedgeType.ORGANIZATIONAL:
                score *= 1.2
            # Temporal is good
            elif w.wedge_type == WedgeType.TEMPORAL:
                score *= 1.1

            scores.append((i, score))

        # Sort by score descending
        scores.sort(key=lambda x: -x[1])

        return [i for i, _ in scores]


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def generate_wedge_queries(
    entity_a: Entity,
    entity_b: Entity,
    collision: EntityCollision
) -> WedgeQuerySet:
    """Generate wedge queries for disambiguation."""
    return WedgeQueryGenerator().generate(entity_a, entity_b, collision)
