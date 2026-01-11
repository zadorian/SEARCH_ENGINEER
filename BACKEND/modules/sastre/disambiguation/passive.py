"""
SASTRE Passive Disambiguation - Automatic checks without new queries.

Passive checks can AUTO_FUSE or AUTO_REPEL based on:
1. Temporal impossibility (can't be in two places at once)
2. Identifier collision (same SSN = same person)
3. Exclusive geography (born in X but claims born in Y)
4. Age impossibility (DOB doesn't match claimed age)
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime, date
from enum import Enum

from ..core.state import Entity, EntityCollision, DisambiguationAction


# =============================================================================
# HARD IDENTIFIERS - Definitive proof of same/different
# =============================================================================

HARD_IDENTIFIERS = [
    'ssn', 'social_security_number',
    'passport_number', 'passport',
    'national_id', 'national_identity',
    'tax_id', 'vat_number', 'ein', 'itin',
    'registration_number', 'company_number', 'crn',
    'lei', 'legal_entity_identifier',
    'fingerprint', 'biometric',
    'driver_license', 'driving_license',
    'oib', 'mbs', 'iban',  # Croatian identifiers
    'krs', 'nip', 'regon',  # Polish identifiers
]


# =============================================================================
# LINK STRENGTH HIERARCHY - Weighing connection strength
# =============================================================================

class LinkStrength:
    """
    Link hierarchy for weighing connections between entities.

    Higher values = stronger evidence of relationship.
    Used in disambiguation confidence scoring.
    """
    SHARED_SOURCE = 1       # Both in NYT (coincidence)
    SHARED_MACRO_SPACE = 2  # Both in "New York City"
    SHARED_MICRO_SPACE = 4  # Both at "123 Main St"
    SHARED_ENTITY = 8       # Both linked to "Alice (Wife)"
    SHARED_GHOST = 6        # Both have same pattern of MISSING data
    SHARED_IDENTIFIER = 10  # Both have same identifier (definitive)


# =============================================================================
# PASSIVE CHECK RESULT
# =============================================================================

class PassiveOutcome(Enum):
    """Outcome of passive check."""
    AUTO_FUSE = "auto_fuse"      # Definitely same entity
    AUTO_REPEL = "auto_repel"    # Definitely different entities
    UNCERTAIN = "uncertain"      # Need active disambiguation


@dataclass
class PassiveCheckResult:
    """Result of passive disambiguation check."""
    outcome: PassiveOutcome
    confidence: float
    reason: str
    checks_performed: List[str]
    evidence: List[str]


# =============================================================================
# PASSIVE CHECKER
# =============================================================================

class PassiveChecker:
    """
    Runs passive disambiguation checks.

    These checks don't require new queries - they use existing data
    to automatically determine FUSE or REPEL.
    """

    def check(
        self,
        entity_a: Entity,
        entity_b: Entity,
        collision: EntityCollision
    ) -> PassiveCheckResult:
        """
        Run all passive checks on a collision.
        """
        checks_performed = []
        evidence = []

        # 1. Identifier collision check
        id_result = self._check_identifiers(entity_a, entity_b)
        checks_performed.append("identifier_collision")
        if id_result:
            outcome, conf, reason = id_result
            evidence.append(reason)
            if outcome != PassiveOutcome.UNCERTAIN:
                return PassiveCheckResult(
                    outcome=outcome,
                    confidence=conf,
                    reason=reason,
                    checks_performed=checks_performed,
                    evidence=evidence,
                )

        # 2. Temporal impossibility check
        temporal_result = self._check_temporal(entity_a, entity_b)
        checks_performed.append("temporal_impossibility")
        if temporal_result:
            outcome, conf, reason = temporal_result
            evidence.append(reason)
            if outcome != PassiveOutcome.UNCERTAIN:
                return PassiveCheckResult(
                    outcome=outcome,
                    confidence=conf,
                    reason=reason,
                    checks_performed=checks_performed,
                    evidence=evidence,
                )

        # 3. Geographic exclusivity check
        geo_result = self._check_geography(entity_a, entity_b)
        checks_performed.append("geographic_exclusivity")
        if geo_result:
            outcome, conf, reason = geo_result
            evidence.append(reason)
            if outcome != PassiveOutcome.UNCERTAIN:
                return PassiveCheckResult(
                    outcome=outcome,
                    confidence=conf,
                    reason=reason,
                    checks_performed=checks_performed,
                    evidence=evidence,
                )

        # 4. Age impossibility check
        age_result = self._check_age(entity_a, entity_b)
        checks_performed.append("age_impossibility")
        if age_result:
            outcome, conf, reason = age_result
            evidence.append(reason)
            if outcome != PassiveOutcome.UNCERTAIN:
                return PassiveCheckResult(
                    outcome=outcome,
                    confidence=conf,
                    reason=reason,
                    checks_performed=checks_performed,
                    evidence=evidence,
                )

        # 5. Entity type mismatch
        if entity_a.entity_type != entity_b.entity_type:
            return PassiveCheckResult(
                outcome=PassiveOutcome.AUTO_REPEL,
                confidence=1.0,
                reason=f"Different entity types: {entity_a.entity_type.value} vs {entity_b.entity_type.value}",
                checks_performed=checks_performed,
                evidence=evidence + ["Entity type mismatch"],
            )

        # No definitive result
        return PassiveCheckResult(
            outcome=PassiveOutcome.UNCERTAIN,
            confidence=0.5,
            reason="No passive checks conclusive",
            checks_performed=checks_performed,
            evidence=evidence,
        )

    def _check_identifiers(
        self,
        entity_a: Entity,
        entity_b: Entity
    ) -> Optional[Tuple[PassiveOutcome, float, str]]:
        """
        Check for identifier matches/conflicts.

        Same identifier = AUTO_FUSE
        Different identifiers of same type = AUTO_REPEL
        """
        # Identifier types to check
        id_types = [
            ('passport', 'Passport number'),
            ('tax_id', 'Tax ID'),
            ('national_id', 'National ID'),
            ('registration_number', 'Registration number'),
        ]

        for id_type, label in id_types:
            a_id = entity_a.get_attribute(id_type)
            b_id = entity_b.get_attribute(id_type)

            if a_id and b_id:
                a_val = str(a_id.value).strip().upper()
                b_val = str(b_id.value).strip().upper()

                if a_val == b_val:
                    return (
                        PassiveOutcome.AUTO_FUSE,
                        0.95,
                        f"Same {label}: {a_val}"
                    )
                else:
                    return (
                        PassiveOutcome.AUTO_REPEL,
                        0.90,
                        f"Different {label}: {a_val} vs {b_val}"
                    )

        return None

    def _check_temporal(
        self,
        entity_a: Entity,
        entity_b: Entity
    ) -> Optional[Tuple[PassiveOutcome, float, str]]:
        """
        Check for temporal impossibilities.

        E.g., Company A dissolved 2010, Company B incorporated 2015 (could be revival)
        E.g., Person A died 2010, Person B active 2020 (different people)
        """
        # Check DOB
        a_dob = entity_a.get_attribute('dob')
        b_dob = entity_b.get_attribute('dob')

        if a_dob and b_dob:
            try:
                a_date = self._parse_date(a_dob.value)
                b_date = self._parse_date(b_dob.value)

                if a_date and b_date:
                    # Different DOB = different person
                    diff_days = abs((a_date - b_date).days)
                    if diff_days > 365:  # More than a year difference
                        return (
                            PassiveOutcome.AUTO_REPEL,
                            0.95,
                            f"Different DOB: {a_dob.value} vs {b_dob.value}"
                        )
                    elif diff_days == 0:
                        return (
                            PassiveOutcome.UNCERTAIN,
                            0.7,
                            f"Same DOB: {a_dob.value} (need more evidence)"
                        )
            except Exception:
                pass

        # Check company dissolution/incorporation
        a_dissolved = entity_a.get_attribute('dissolution_date')
        b_inc = entity_b.get_attribute('incorporation_date')

        if a_dissolved and b_inc:
            try:
                dissolved = self._parse_date(a_dissolved.value)
                incorporated = self._parse_date(b_inc.value)

                if dissolved and incorporated and incorporated > dissolved:
                    # B incorporated after A dissolved - could be different
                    # But could also be revival, so not definitive
                    return (
                        PassiveOutcome.UNCERTAIN,
                        0.6,
                        f"A dissolved {a_dissolved.value}, B incorporated {b_inc.value}"
                    )
            except Exception:
                pass

        return None

    def _check_geography(
        self,
        entity_a: Entity,
        entity_b: Entity
    ) -> Optional[Tuple[PassiveOutcome, float, str]]:
        """
        Check for geographic exclusivity.

        E.g., Born in France vs Born in Japan = different people
        E.g., Incorporated in UK vs Incorporated in US = different companies
        """
        # Birth place for persons
        a_birth = entity_a.get_attribute('birth_place') or entity_a.get_attribute('nationality')
        b_birth = entity_b.get_attribute('birth_place') or entity_b.get_attribute('nationality')

        if a_birth and b_birth:
            a_val = str(a_birth.value).strip().lower()
            b_val = str(b_birth.value).strip().lower()

            # Check if clearly different (not just different words for same place)
            if a_val != b_val and not self._are_related_places(a_val, b_val):
                return (
                    PassiveOutcome.UNCERTAIN,  # Nationality can change
                    0.6,
                    f"Different nationality/birthplace: {a_birth.value} vs {b_birth.value}"
                )

        # Jurisdiction for companies
        a_jur = entity_a.get_attribute('jurisdiction')
        b_jur = entity_b.get_attribute('jurisdiction')

        if a_jur and b_jur:
            a_val = str(a_jur.value).strip().upper()
            b_val = str(b_jur.value).strip().upper()

            if a_val != b_val:
                return (
                    PassiveOutcome.AUTO_REPEL,
                    0.85,
                    f"Different jurisdiction: {a_jur.value} vs {b_jur.value}"
                )

        return None

    def _check_age(
        self,
        entity_a: Entity,
        entity_b: Entity
    ) -> Optional[Tuple[PassiveOutcome, float, str]]:
        """
        Check for age impossibilities.

        E.g., DOB 2000 but director in 1995 = impossible
        """
        a_dob = entity_a.get_attribute('dob')
        b_dob = entity_b.get_attribute('dob')

        # If we have DOB and role dates, check for impossibilities
        for entity, dob_attr in [(entity_a, a_dob), (entity_b, b_dob)]:
            if not dob_attr:
                continue

            try:
                dob = self._parse_date(dob_attr.value)
                if not dob:
                    continue

                # Check if entity was director/officer before being born
                # (This would need halo data about appointments)
                # Simplified: check if any activity date is before DOB
                for attr in entity.halo.values():
                    if hasattr(attr, 'found_at'):
                        activity_date = attr.found_at
                        if isinstance(activity_date, date) and activity_date < dob:
                            return (
                                PassiveOutcome.AUTO_REPEL,
                                0.95,
                                f"Activity before DOB: {activity_date} < {dob}"
                            )
            except Exception:
                pass

        return None

    def _parse_date(self, value: str) -> Optional[date]:
        """Parse date from various formats."""
        if isinstance(value, (date, datetime)):
            return value if isinstance(value, date) else value.date()

        formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%Y',
            '%d-%m-%Y',
        ]

        for fmt in formats:
            try:
                return datetime.strptime(str(value).strip(), fmt).date()
            except ValueError:
                continue

        return None

    def _are_related_places(self, place_a: str, place_b: str) -> bool:
        """Check if two place names might refer to same location."""
        # Simple equivalence check
        equivalents = [
            {'uk', 'united kingdom', 'britain', 'great britain', 'england'},
            {'us', 'usa', 'united states', 'america'},
            {'uae', 'united arab emirates', 'dubai'},
        ]

        for equiv_set in equivalents:
            if place_a in equiv_set and place_b in equiv_set:
                return True

        return False


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def check_passive_constraints(
    entity_a: Entity,
    entity_b: Entity,
    collision: EntityCollision
) -> PassiveCheckResult:
    """Run passive disambiguation checks."""
    return PassiveChecker().check(entity_a, entity_b, collision)
