#!/usr/bin/env python3
"""
Enhance sources.json with intelligence metadata:
- exposes_related_entities
- related_entity_types
- classification
- arbitrage_opportunities
"""

import json
from pathlib import Path

MATRIX = Path(__file__).parent / 'matrix'
SOURCES_FILE = MATRIX / 'sources.json'

def infer_related_entities(source):
    """Infer what related entities a source exposes based on outputs"""
    outputs = source.get('outputs', [])
    notes = source.get('notes', '').lower()
    name = source.get('name', '').lower()

    related_types = set()

    # Check outputs for entity type keywords
    output_str = ' '.join(outputs).lower()

    # UBO (Ultimate Beneficial Owner)
    if any(kw in output_str for kw in ['beneficial', 'ubo', 'ultimate_owner']):
        related_types.add('UBO')

    # Directors/Officers
    if any(kw in output_str for kw in ['officer', 'director', 'manager', 'executive']):
        related_types.add('directors')

    # Shareholders
    if any(kw in output_str for kw in ['shareholder', 'ownership', 'shares']):
        related_types.add('shareholders')

    # Subsidiaries
    if any(kw in output_str for kw in ['subsidiary', 'subsidiaries', 'child_compan']):
        related_types.add('subsidiaries')

    # Parent companies
    if any(kw in output_str for kw in ['parent', 'holding_company', 'group']):
        related_types.add('parent_company')

    # Affiliated entities
    if any(kw in output_str for kw in ['affiliated', 'related_part', 'associate']):
        related_types.add('affiliated_entities')

    # Foreign entities
    if any(kw in notes for kw in ['foreign', 'cross-border', 'international']):
        related_types.add('foreign_entities')

    # Historical entities
    if any(kw in notes for kw in ['historical', 'former', 'previous']):
        related_types.add('historical_entities')

    return list(related_types)

def classify_source(source):
    """Determine source classification"""
    source_type = source.get('type', '')
    access = source.get('access', '')
    domain = source.get('domain', '')
    notes = source.get('notes', '').lower()
    metadata = source.get('metadata', {})

    # Official Registries (government)
    if source_type == 'corporate_registry' and access == 'public' and any(tld in domain for tld in ['.gov', '.go.', '.gob', '.gouv']):
        return "Official Registry"

    # ALEPH datasets
    if metadata.get('source') == 'aleph':
        if 'leak' in notes or 'panama' in notes or 'paradise' in notes:
            return "Leak Dataset"
        return "Structured Dataset"

    # Drill modules
    if metadata.get('source') == 'drill_module':
        module_type = metadata.get('module_type', '')
        if module_type == 'osint':
            return "OSINT Platform"
        elif module_type == 'corporate_intel':
            return "Intelligence Aggregator"
        elif module_type == 'domain_intel':
            return "Technical Intelligence"

    # Court records
    if source_type in ['court_records', 'litigation']:
        return "Court System"

    # Private aggregators
    if source_type == 'commercial_aggregator' or access == 'paywalled':
        return "Private Aggregator"

    # Public databases
    if access == 'public' and source_type in ['public_records', 'dataset']:
        return "Public Database"

    # Regulatory filings
    if source_type in ['regulatory', 'compliance']:
        return "Regulatory Authority"

    # Default
    return "Other"

def detect_arbitrage_opportunities(source):
    """Detect specific intelligence arbitrage strategies"""
    opportunities = []

    outputs = source.get('outputs', [])
    notes = source.get('notes', '').lower()
    classification = source.get('classification', '')
    related_entities = source.get('related_entity_types', [])
    jurisdiction = source.get('jurisdiction', '')

    # Foreign Branch Reveal
    if 'foreign' in notes and ('branch' in notes or 'manager' in notes or 'director' in notes):
        opportunities.append("Foreign Branch Reveal: Lists managers of foreign entities")

    # Cross-Border UBO Discovery
    if 'UBO' in related_entities and jurisdiction != 'GLOBAL':
        opportunities.append(f"UBO Transparency: {jurisdiction} reveals ultimate beneficial owners")

    # Historical Officer Tracking
    if 'historical_entities' in related_entities or 'historical' in notes:
        opportunities.append("Historical Officer Tracking: Reveals former directors/shareholders")

    # Asset Declaration Linkage
    if any(kw in notes for kw in ['asset', 'property', 'real estate']) and 'officer' in ' '.join(outputs).lower():
        opportunities.append("Asset-Officer Linkage: Cross-reference property ownership with corporate roles")

    # Leak-to-Registry Correlation
    if classification == "Leak Dataset":
        opportunities.append("Leak Correlation: Compare leaked data with official registry for discrepancies")

    # Free UBO Access (rare)
    if 'UBO' in related_entities and source.get('access') == 'public':
        opportunities.append(f"Free UBO Access: {jurisdiction} provides free beneficial ownership data")

    # Subsidiary Network Mapping
    if 'subsidiaries' in related_entities:
        opportunities.append("Subsidiary Network Mapping: Trace corporate group structure")

    # Regulatory Arbitrage Detection
    if classification == "Regulatory Authority" and 'foreign' in notes:
        opportunities.append("Regulatory Arbitrage: Identify entities regulated in multiple jurisdictions")

    # OSINT to Registry Validation
    if classification == "OSINT Platform":
        opportunities.append("OSINT-to-Registry: Validate leaked/scraped data against official sources")

    # Bulk Download for Pattern Analysis
    if 'bulk' in notes or 'api' in notes:
        opportunities.append("Bulk Pattern Analysis: Download full dataset for network analysis")

    return opportunities

def enhance_sources():
    """Add intelligence metadata to all sources"""

    with open(SOURCES_FILE) as f:
        sources = json.load(f)

    total_enhanced = 0

    for jurisdiction, source_list in sources.items():
        for source in source_list:
            # Infer related entities
            related_types = infer_related_entities(source)
            source['exposes_related_entities'] = len(related_types) > 0
            source['related_entity_types'] = related_types

            # Classify source
            source['classification'] = classify_source(source)

            # Detect arbitrage opportunities
            source['arbitrage_opportunities'] = detect_arbitrage_opportunities(source)

            total_enhanced += 1

    # Save enhanced version
    with open(SOURCES_FILE, 'w') as f:
        json.dump(sources, f, indent=2, ensure_ascii=False)

    print(f"✅ Enhanced {total_enhanced} sources")

    # Stats
    with_related = sum(1 for j in sources.values() for s in j if s['exposes_related_entities'])
    with_arb = sum(1 for j in sources.values() for s in j if len(s.get('arbitrage_opportunities', [])) > 0)

    print(f"   Sources exposing related entities: {with_related}")
    print(f"   Sources with arbitrage opportunities: {with_arb}")

    # Classification breakdown
    classifications = {}
    for j in sources.values():
        for s in j:
            c = s.get('classification', 'Unknown')
            classifications[c] = classifications.get(c, 0) + 1

    print("\n📊 Classification Breakdown:")
    for c, count in sorted(classifications.items(), key=lambda x: -x[1]):
        print(f"   {c}: {count}")

if __name__ == '__main__':
    enhance_sources()
