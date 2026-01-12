#!/usr/bin/env python3
"""
Apply observation codes from codebook to jurisdictions.json.

Evaluates each jurisdiction against the codebook indicators and assigns
applicable codes to a new 'observations' field.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

MATRIX_DIR = Path(__file__).parent.parent

# Language region mappings
CYRILLIC_JURISDICTIONS = {
    'RU', 'KZ', 'AZ', 'AM', 'BY', 'UA', 'KG', 'TJ', 'UZ', 'TM', 'MN', 'BG', 'RS', 'ME', 'MK', 'BA'
}
ARABIC_JURISDICTIONS = {
    'AE', 'SA', 'EG', 'IQ', 'SY', 'JO', 'LB', 'KW', 'QA', 'BH', 'OM', 'YE', 'LY', 'TN', 'DZ', 'MA'
}
COMMON_LAW_JURISDICTIONS = {
    'UK', 'US', 'AU', 'NZ', 'CA', 'IE', 'IN', 'SG', 'HK', 'MY', 'KY', 'VG', 'BM', 'JE', 'GG', 'IM'
}
EU_MEMBERS = {
    'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE',
    'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE'
}
OFFSHORE_JURISDICTIONS = {
    'VG', 'KY', 'BM', 'PA', 'BZ', 'SC', 'MU', 'JE', 'GG', 'IM', 'GI', 'LI', 'MC', 'AD', 'SM'
}


def evaluate_transparency(jur_data: dict, jur_code: str) -> list:
    """Evaluate transparency codes."""
    codes = []

    cap = jur_data.get('capabilities', {})
    friction = cap.get('friction_profile', {})
    da = jur_data.get('data_availability', {})
    dead_ends = jur_data.get('dead_ends', [])
    legal_notes = jur_data.get('legal_notes', '').lower()

    open_rate = friction.get('open', 0)
    accessible = da.get('accessible', [])

    # Check for opacity indicators
    has_bo_dead_end = any(
        de.get('sought_category') == 'beneficial_ownership' and de.get('permanent', False)
        for de in dead_ends if isinstance(de, dict)
    )

    if open_rate >= 0.8 and len(accessible) >= 4:
        codes.append('TRANSPARENCY_HIGH')
    elif open_rate >= 0.5:
        codes.append('TRANSPARENCY_MEDIUM')
    elif open_rate < 0.5 and friction.get('restricted', 0) > 0.2:
        codes.append('TRANSPARENCY_LOW')

    if has_bo_dead_end or 'no transparency' in legal_notes or jur_code in OFFSHORE_JURISDICTIONS:
        codes.append('TRANSPARENCY_OPAQUE')

    if friction.get('paywalled', 0) > 0.1:
        codes.append('TRANSPARENCY_PAYWALLED')

    return codes


def evaluate_registry(jur_data: dict, jur_code: str) -> list:
    """Evaluate registry codes."""
    codes = []

    wiki = jur_data.get('wiki_sections', {})
    corp_reg = wiki.get('corporate_registry', {})
    content = corp_reg.get('content', '').lower() if isinstance(corp_reg, dict) else str(corp_reg).lower()

    dead_ends = jur_data.get('dead_ends', [])
    legal_notes = jur_data.get('legal_notes', '').lower()
    da = jur_data.get('data_availability', {})

    # Registry access level
    if '(pub)' in content or 'freely accessible' in content or 'public' in content:
        codes.append('REGISTRY_PUBLIC')

    if 'registration' in content or 'login required' in content or '(reg)' in content:
        codes.append('REGISTRY_REGISTRATION_REQUIRED')

    if 'purchase' in content or 'payment' in content or 'must be bought' in content:
        codes.append('REGISTRY_PAID')

    # Multiple registries
    links = corp_reg.get('links', []) if isinstance(corp_reg, dict) else []
    if len(links) > 2 or 'free zone' in content:
        codes.append('REGISTRY_FRAGMENTED')

    # Registry limitations
    registry_limited = any(
        de.get('reason_category') == 'registry_limitation'
        for de in dead_ends if isinstance(de, dict)
    )
    if registry_limited or 'limited' in legal_notes:
        codes.append('REGISTRY_LIMITED')

    # Offline registry
    if 'offline' in content or 'in person' in content or 'physical visit' in content:
        codes.append('REGISTRY_OFFLINE')

    # Historical data gap
    if 'limited historical' in legal_notes:
        codes.append('REGISTRY_HISTORICAL_GAP')

    # Officers available
    cap = jur_data.get('capabilities', {})
    atoms = cap.get('atoms_available', [])
    if 'REGISTRY_OFFICERS' in atoms or 'directors' in str(da.get('accessible', [])).lower():
        codes.append('REGISTRY_OFFICERS_AVAILABLE')

    # Ownership hidden
    ownership_hidden = any(
        de.get('sought_category') == 'beneficial_ownership'
        for de in dead_ends if isinstance(de, dict)
    )
    if ownership_hidden or 'not disclosed' in legal_notes or 'commercial secret' in legal_notes:
        codes.append('REGISTRY_OWNERSHIP_HIDDEN')

    return codes


def evaluate_legal_system(jur_data: dict, jur_code: str) -> list:
    """Evaluate legal system codes."""
    codes = []

    legal_notes = jur_data.get('legal_notes', '').lower()
    wiki = jur_data.get('wiki_sections', {})
    litigation = wiki.get('litigation', {})
    lit_content = litigation.get('content', '').lower() if isinstance(litigation, dict) else ''

    dead_ends = jur_data.get('dead_ends', [])
    cap = jur_data.get('capabilities', {})
    pm = jur_data.get('proven_methods', {})

    # Legal system type
    if jur_code in COMMON_LAW_JURISDICTIONS:
        codes.append('LEGAL_COMMON_LAW')
    elif jur_code in EU_MEMBERS or jur_code in {'CH', 'LI', 'NO', 'IS'}:
        codes.append('LEGAL_CIVIL_LAW')
    elif 'hybrid' in legal_notes or 'mixed' in legal_notes:
        codes.append('LEGAL_HYBRID')

    # Authoritarian
    if 'authoritarian' in legal_notes or 'state capture' in legal_notes:
        codes.append('LEGAL_AUTHORITARIAN')

    # Conflict zone
    if 'conflict' in legal_notes or 'civil war' in legal_notes:
        codes.append('LEGAL_CONFLICT_ZONE')

    # Courts accessibility
    if lit_content and ('database' in lit_content or 'search' in lit_content):
        codes.append('LEGAL_COURTS_ACCESSIBLE')

    lit_restricted = any(
        de.get('sought_category') == 'litigation_records' and de.get('reason_category') == 'access_restricted'
        for de in dead_ends if isinstance(de, dict)
    )
    if lit_restricted:
        codes.append('LEGAL_COURTS_RESTRICTED')

    # Regulatory
    regulatory = wiki.get('regulatory', {})
    if regulatory and (isinstance(regulatory, dict) and regulatory.get('content')):
        codes.append('LEGAL_REGULATORY_ACTIVE')

    return codes


def evaluate_language(jur_data: dict, jur_code: str) -> list:
    """Evaluate language codes."""
    codes = []

    if jur_code in {'UK', 'US', 'AU', 'NZ', 'CA', 'IE', 'KY', 'VG', 'BM'} or jur_code.startswith('US_'):
        codes.append('LANGUAGE_ENGLISH')

    if jur_code in CYRILLIC_JURISDICTIONS:
        codes.append('LANGUAGE_CYRILLIC')
        codes.append('LANGUAGE_LOCAL_ONLY')

    if jur_code in ARABIC_JURISDICTIONS:
        codes.append('LANGUAGE_ARABIC')
        codes.append('LANGUAGE_LOCAL_ONLY')

    # Check for bilingual
    wiki = jur_data.get('wiki_sections', {})
    for section in wiki.values():
        if isinstance(section, dict):
            content = section.get('content', '').lower()
            if '/en/' in content or 'english' in content:
                if 'LANGUAGE_LOCAL_ONLY' in codes:
                    codes.remove('LANGUAGE_LOCAL_ONLY')
                    codes.append('LANGUAGE_BILINGUAL')
                break

    # High barrier
    if ('LANGUAGE_CYRILLIC' in codes or 'LANGUAGE_ARABIC' in codes) and 'LANGUAGE_BILINGUAL' not in codes:
        codes.append('LANGUAGE_BARRIER_HIGH')

    return codes


def evaluate_access(jur_data: dict, jur_code: str) -> list:
    """Evaluate access codes."""
    codes = []

    wiki = jur_data.get('wiki_sections', {})
    pm = jur_data.get('proven_methods', {})
    dead_ends = jur_data.get('dead_ends', [])
    cap = jur_data.get('capabilities', {})
    friction = cap.get('friction_profile', {})

    # Direct online access
    source_domains = jur_data.get('source_domains', [])
    if source_domains or any(isinstance(s, dict) and s.get('links') for s in wiki.values()):
        codes.append('ACCESS_DIRECT_ONLINE')

    # API available
    for section in wiki.values():
        if isinstance(section, dict):
            content = section.get('content', '').lower()
            if 'api' in content or 'machine-readable' in content:
                codes.append('ACCESS_API_AVAILABLE')
                break

    # HUMINT required
    if 'HUMINT' in pm and pm['HUMINT'].get('count', 0) > 5:
        codes.append('ACCESS_HUMINT_REQUIRED')

    # Leaks dependent (offshore jurisdictions)
    if jur_code in OFFSHORE_JURISDICTIONS:
        codes.append('ACCESS_LEAKS_DEPENDENT')

    # Paid services
    if friction.get('paywalled', 0) > 0.05:
        codes.append('ACCESS_PAID_SERVICES')

    # Media route
    if 'MEDIA_MONITORING' in pm and pm['MEDIA_MONITORING'].get('count', 0) > 10:
        codes.append('ACCESS_MEDIA_ROUTE')

    # Court route
    if 'LITIGATION_COURT' in pm and pm['LITIGATION_COURT'].get('count', 0) > 5:
        codes.append('ACCESS_COURT_ROUTE')

    # Blocked access
    permanent_blocked = sum(
        1 for de in dead_ends
        if isinstance(de, dict) and de.get('permanent', False)
    )
    if permanent_blocked > 10:
        codes.append('ACCESS_BLOCKED')

    return codes


def evaluate_coverage(jur_data: dict, jur_code: str) -> list:
    """Evaluate coverage codes."""
    codes = []

    da = jur_data.get('data_availability', {})
    accessible = da.get('accessible', [])
    restricted = da.get('restricted', [])
    unavailable = da.get('unavailable', [])

    wiki = jur_data.get('wiki_sections', {})
    dead_ends = jur_data.get('dead_ends', [])
    cap = jur_data.get('capabilities', {})

    # Comprehensive coverage
    if len(accessible) >= 5:
        codes.append('COVERAGE_COMPREHENSIVE')
    elif len(accessible) <= 2:
        codes.append('COVERAGE_BASIC')

    # Ownership gap
    ownership_sought = any(
        de.get('sought_category') == 'beneficial_ownership'
        for de in dead_ends if isinstance(de, dict)
    )
    if ownership_sought or 'ownership' in str(unavailable).lower():
        codes.append('COVERAGE_OWNERSHIP_GAP')

    # Financial gap
    financial_sought = any(
        de.get('sought_category') == 'financial_information' and de.get('permanent', False)
        for de in dead_ends if isinstance(de, dict)
    )
    if financial_sought or 'financial' in str(unavailable).lower():
        codes.append('COVERAGE_FINANCIAL_GAP')

    # Litigation available
    litigation = wiki.get('litigation', {})
    if litigation and isinstance(litigation, dict) and litigation.get('content'):
        codes.append('COVERAGE_LITIGATION_AVAILABLE')

    # Property available
    asset_reg = wiki.get('asset_registries', {})
    if asset_reg and isinstance(asset_reg, dict):
        content = asset_reg.get('content', '').lower()
        if 'land' in content or 'property' in content or 'cadastre' in content:
            codes.append('COVERAGE_PROPERTY_AVAILABLE')
        if 'trademark' in content or 'patent' in content or 'intellectual' in content:
            codes.append('COVERAGE_IP_AVAILABLE')

    # PEP data
    political = wiki.get('political', {})
    if political and isinstance(political, dict) and political.get('content'):
        codes.append('COVERAGE_PEP_DATA')

    # Sanctions lists
    pm = jur_data.get('proven_methods', {})
    if 'COMPLIANCE_SANCTIONS' in pm:
        codes.append('COVERAGE_SANCTIONS_LISTS')

    return codes


def evaluate_reliability(jur_data: dict, jur_code: str) -> list:
    """Evaluate reliability codes."""
    codes = []

    cap = jur_data.get('capabilities', {})
    success_rate = cap.get('success_rate', 0)
    dead_ends = jur_data.get('dead_ends', [])
    legal_notes = jur_data.get('legal_notes', '').lower()

    # Success rate based reliability
    if success_rate >= 0.8:
        codes.append('RELIABILITY_HIGH')
    elif success_rate >= 0.6:
        codes.append('RELIABILITY_MEDIUM')
    elif success_rate > 0 and success_rate < 0.6:
        codes.append('RELIABILITY_LOW')

    # Corruption risk
    if 'corruption' in legal_notes:
        codes.append('RELIABILITY_CORRUPTION_RISK')

    # Technical issues
    tech_failures = sum(
        1 for de in dead_ends
        if isinstance(de, dict) and de.get('reason_category') == 'technical_failure'
    )
    if tech_failures > 3:
        codes.append('RELIABILITY_TECHNICAL_ISSUES')

    # Nominee structures
    if jur_code in OFFSHORE_JURISDICTIONS or 'nominee' in legal_notes:
        codes.append('RELIABILITY_NOMINEE_PREVALENT')

    # State manipulation
    if 'state-owned media' in legal_notes or 'government control' in legal_notes:
        codes.append('RELIABILITY_STATE_MANIPULATION')

    return codes


def evaluate_special(jur_data: dict, jur_code: str) -> list:
    """Evaluate special observation codes."""
    codes = []

    legal_notes = jur_data.get('legal_notes', '').lower()
    source_domains = jur_data.get('source_domains', [])

    if jur_code in OFFSHORE_JURISDICTIONS or 'offshore' in legal_notes or 'holding company' in legal_notes:
        codes.append('OFFSHORE_STRUCTURE')

    if 'prohibits criticism' in legal_notes or 'state-owned media' in legal_notes:
        codes.append('MEDIA_RESTRICTED')

    if 'conflict' in legal_notes or 'civil war' in legal_notes:
        codes.append('CONFLICT_ZONE')

    if 'bilateral' in legal_notes:
        codes.append('BILATERAL_ONLY')

    if 'banking sector' in legal_notes and 'regulatory' in legal_notes:
        codes.append('BANKING_REGULATED')

    # Free zone fragmentation
    freezone_count = sum(1 for d in source_domains if 'freezone' in str(d).lower() or 'free zone' in str(d).lower())
    if freezone_count >= 2:
        codes.append('FREEZONE_FRAGMENTED')

    if jur_code in EU_MEMBERS:
        codes.append('EU_MEMBER')

    # Sanctions target (check dead_ends)
    dead_ends = jur_data.get('dead_ends', [])
    sanctions_related = any(
        'sanction' in str(de).lower()
        for de in dead_ends
    )
    if sanctions_related or jur_code in {'RU', 'BY', 'IR', 'KP', 'SY', 'VE', 'CU'}:
        codes.append('SANCTIONS_TARGET')

    return codes


def apply_observation_codes():
    """Main function to apply observation codes."""

    # Load jurisdictions
    jur_file = MATRIX_DIR / "jurisdictions.json"
    print(f"Loading {jur_file}...")
    with open(jur_file) as f:
        data = json.load(f)

    jurisdictions = data.get("jurisdictions", {})
    print(f"  Found {len(jurisdictions)} jurisdictions")

    stats = {
        "jurisdictions_processed": 0,
        "total_codes_assigned": 0,
        "codes_distribution": defaultdict(int),
    }

    # Process each jurisdiction
    print("\nApplying observation codes...")
    for jur_code, jur_data in jurisdictions.items():
        observations = []

        # Evaluate all categories
        observations.extend(evaluate_transparency(jur_data, jur_code))
        observations.extend(evaluate_registry(jur_data, jur_code))
        observations.extend(evaluate_legal_system(jur_data, jur_code))
        observations.extend(evaluate_language(jur_data, jur_code))
        observations.extend(evaluate_access(jur_data, jur_code))
        observations.extend(evaluate_coverage(jur_data, jur_code))
        observations.extend(evaluate_reliability(jur_data, jur_code))
        observations.extend(evaluate_special(jur_data, jur_code))

        # Deduplicate
        observations = list(dict.fromkeys(observations))

        # Assign to jurisdiction
        jur_data["observations"] = observations

        # Update stats
        stats["jurisdictions_processed"] += 1
        stats["total_codes_assigned"] += len(observations)
        for code in observations:
            stats["codes_distribution"][code] += 1

    # Update metadata
    data["meta"]["observations_applied"] = True
    data["meta"]["observations_date"] = datetime.now().isoformat()
    data["meta"]["total_observation_codes"] = stats["total_codes_assigned"]
    data["jurisdictions"] = jurisdictions

    # Write back
    print(f"\nWriting updated jurisdictions.json...")
    with open(jur_file, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Print stats
    print(f"\n=== OBSERVATION CODE STATS ===")
    print(f"Jurisdictions processed: {stats['jurisdictions_processed']}")
    print(f"Total codes assigned: {stats['total_codes_assigned']}")
    print(f"Average codes per jurisdiction: {stats['total_codes_assigned'] / max(1, stats['jurisdictions_processed']):.1f}")

    print(f"\nTop 20 most common codes:")
    for code, count in sorted(stats["codes_distribution"].items(), key=lambda x: -x[1])[:20]:
        print(f"  {code}: {count}")

    # Show sample
    print(f"\n=== SAMPLE ASSIGNMENTS ===")
    for sample_code in ['UK', 'VG', 'AZ', 'DE', 'US']:
        if sample_code in jurisdictions:
            obs = jurisdictions[sample_code].get('observations', [])
            print(f"\n{sample_code}: {len(obs)} codes")
            for o in obs[:8]:
                print(f"  - {o}")
            if len(obs) > 8:
                print(f"  ... and {len(obs) - 8} more")


if __name__ == "__main__":
    apply_observation_codes()
