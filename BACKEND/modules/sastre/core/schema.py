"""
SASTRE Entity Schema - Core/Shell/Halo field definitions by entity type.

This defines WHAT goes in each layer for each entity type.
Used for:
1. Completeness checking
2. Gap detection
3. Enrichment routing
"""

from typing import Dict, List, Any, Optional
from .state import Entity, EntityType


# =============================================================================
# FULL ENTITY SCHEMA
# =============================================================================

ENTITY_SCHEMA = {
    'person': {
        'core': {
            'name': {'required': True, 'variations': True, 'description': 'Full name'},
            'dob': {'required': True, 'format': 'YYYY-MM-DD', 'description': 'Date of birth'},
            'nationality': {'required': True, 'description': 'Primary nationality'},
        },
        'shell': {
            'passport': {'required': False, 'description': 'Passport number'},
            'tax_id': {'required': False, 'description': 'Tax identification number'},
            'national_id': {'required': False, 'description': 'National ID number'},
            'address': {'required': False, 'description': 'Current address'},
            'email': {'required': False, 'description': 'Email address'},
            'phone': {'required': False, 'description': 'Phone number'},
            'employer': {'required': False, 'description': 'Current employer'},
            'occupation': {'required': False, 'description': 'Job title/occupation'},
        },
        'halo': {
            'aliases': {'type': 'list', 'description': 'Known aliases and variations'},
            'associates': {'type': 'list', 'edge_type': 'associated_with', 'description': 'Known associates'},
            'family': {'type': 'list', 'edge_type': 'family_of', 'description': 'Family members'},
            'education': {'type': 'list', 'description': 'Educational history'},
            'employment_history': {'type': 'list', 'description': 'Past employers'},
            'social_profiles': {'type': 'list', 'description': 'Social media profiles'},
            'news_mentions': {'type': 'list', 'description': 'News articles mentioning person'},
            'court_records': {'type': 'list', 'description': 'Court case involvement'},
            'property_records': {'type': 'list', 'description': 'Property ownership'},
            'breach_data': {'type': 'list', 'description': 'Data breach appearances'},
        }
    },

    'company': {
        'core': {
            'name': {'required': True, 'variations': True, 'description': 'Registered company name'},
            'registration_number': {'required': True, 'description': 'Company registration number'},
            'jurisdiction': {'required': True, 'description': 'Country/state of incorporation'},
        },
        'shell': {
            'status': {'required': False, 'values': ['active', 'dissolved', 'dormant', 'struck_off'], 'description': 'Company status'},
            'incorporation_date': {'required': False, 'format': 'YYYY-MM-DD', 'description': 'Date of incorporation'},
            'dissolution_date': {'required': False, 'format': 'YYYY-MM-DD', 'description': 'Date of dissolution if applicable'},
            'company_type': {'required': False, 'description': 'Type of company (Ltd, LLC, etc.)'},
            'address': {'required': False, 'description': 'Registered address'},
            'website': {'required': False, 'description': 'Company website'},
            'phone': {'required': False, 'description': 'Contact phone'},
            'email': {'required': False, 'description': 'Contact email'},
            'industry': {'required': False, 'description': 'Industry/SIC code'},
            'capital': {'required': False, 'description': 'Share capital'},
        },
        'halo': {
            'officers': {'type': 'list', 'edge_type': 'officer_of', 'description': 'Directors and officers'},
            'shareholders': {'type': 'list', 'edge_type': 'shareholder_of', 'description': 'Shareholders'},
            'beneficial_owners': {'type': 'list', 'edge_type': 'ubo_of', 'description': 'Ultimate beneficial owners'},
            'subsidiaries': {'type': 'list', 'edge_type': 'parent_of', 'description': 'Subsidiary companies'},
            'parent_company': {'type': 'single', 'edge_type': 'subsidiary_of', 'description': 'Parent company'},
            'filings': {'type': 'list', 'description': 'Company filings'},
            'financials': {'type': 'list', 'description': 'Financial statements'},
            'trademarks': {'type': 'list', 'description': 'Registered trademarks'},
            'domains': {'type': 'list', 'edge_type': 'owns_domain', 'description': 'Owned domains'},
            'news_mentions': {'type': 'list', 'description': 'News articles'},
            'sanctions': {'type': 'list', 'description': 'Sanctions listings'},
            'court_records': {'type': 'list', 'description': 'Legal proceedings'},
        }
    },

    'domain': {
        'core': {
            'domain': {'required': True, 'description': 'Domain name'},
            'registrant': {'required': True, 'description': 'Domain registrant'},
        },
        'shell': {
            'registrar': {'required': False, 'description': 'Domain registrar'},
            'creation_date': {'required': False, 'format': 'YYYY-MM-DD', 'description': 'Domain creation date'},
            'expiry_date': {'required': False, 'format': 'YYYY-MM-DD', 'description': 'Domain expiry date'},
            'nameservers': {'type': 'list', 'description': 'Nameservers'},
            'registrant_email': {'required': False, 'description': 'Registrant email'},
            'registrant_address': {'required': False, 'description': 'Registrant address'},
            'registrant_phone': {'required': False, 'description': 'Registrant phone'},
        },
        'halo': {
            'backlinks': {'type': 'list', 'edge_type': 'links_to', 'description': 'Domains linking to this'},
            'outlinks': {'type': 'list', 'edge_type': 'links_from', 'description': 'Domains this links to'},
            'subdomains': {'type': 'list', 'description': 'Subdomains'},
            'ssl_history': {'type': 'list', 'description': 'SSL certificate history'},
            'dns_history': {'type': 'list', 'description': 'DNS record history'},
            'whois_history': {'type': 'list', 'description': 'WHOIS history'},
            'co_hosted': {'type': 'list', 'edge_type': 'shares_hosting_with', 'description': 'Domains on same IP'},
            'ga_linked': {'type': 'list', 'edge_type': 'shares_ga_with', 'description': 'Domains with same GA code'},
            'archive_snapshots': {'type': 'list', 'description': 'Archive.org snapshots'},
            'technologies': {'type': 'list', 'description': 'Detected technologies'},
        }
    },

    'address': {
        'core': {
            'full_address': {'required': True, 'description': 'Full address string'},
            'country': {'required': True, 'description': 'Country'},
        },
        'shell': {
            'street': {'required': False, 'description': 'Street address'},
            'city': {'required': False, 'description': 'City'},
            'state': {'required': False, 'description': 'State/Province'},
            'postal_code': {'required': False, 'description': 'Postal/ZIP code'},
            'coordinates': {'required': False, 'description': 'GPS coordinates'},
        },
        'halo': {
            'entities_at_address': {'type': 'list', 'edge_type': 'located_at', 'description': 'Entities at this address'},
            'property_records': {'type': 'list', 'description': 'Property records'},
            'historical_occupants': {'type': 'list', 'description': 'Past occupants'},
        }
    },

    'email': {
        'core': {
            'email': {'required': True, 'description': 'Email address'},
        },
        'shell': {
            'domain': {'required': False, 'description': 'Email domain'},
            'provider': {'required': False, 'description': 'Email provider'},
            'valid': {'required': False, 'description': 'Email validity status'},
        },
        'halo': {
            'owner': {'type': 'single', 'edge_type': 'has_email', 'description': 'Email owner'},
            'breaches': {'type': 'list', 'description': 'Data breaches containing this email'},
            'social_profiles': {'type': 'list', 'description': 'Social profiles using this email'},
            'domains_registered': {'type': 'list', 'description': 'Domains registered with this email'},
        }
    },

    'phone': {
        'core': {
            'phone': {'required': True, 'description': 'Phone number'},
            'country_code': {'required': True, 'description': 'Country code'},
        },
        'shell': {
            'type': {'required': False, 'values': ['mobile', 'landline', 'voip'], 'description': 'Phone type'},
            'carrier': {'required': False, 'description': 'Phone carrier'},
            'valid': {'required': False, 'description': 'Phone validity status'},
        },
        'halo': {
            'owner': {'type': 'single', 'edge_type': 'has_phone', 'description': 'Phone owner'},
            'associated_addresses': {'type': 'list', 'description': 'Addresses associated with this phone'},
        }
    }
}


# =============================================================================
# SIMPLIFIED FIELD LISTS (for quick checks)
# =============================================================================

EXPECTED_FIELDS = {
    'person': ['name', 'dob', 'nationality'],
    'company': ['name', 'registration_number', 'jurisdiction'],
    'domain': ['domain', 'registrant'],
    'address': ['full_address', 'country'],
    'email': ['email'],
    'phone': ['phone', 'country_code'],
}

POSSIBLE_FIELDS = {
    'person': ['passport', 'tax_id', 'national_id', 'address', 'email', 'phone', 'employer', 'occupation'],
    'company': ['status', 'incorporation_date', 'company_type', 'address', 'website', 'phone', 'email', 'industry'],
    'domain': ['registrar', 'creation_date', 'expiry_date', 'nameservers', 'registrant_email'],
    'address': ['street', 'city', 'state', 'postal_code', 'coordinates'],
    'email': ['domain', 'provider', 'valid'],
    'phone': ['type', 'carrier', 'valid'],
}

ENRICHMENT_FIELDS = {
    'person': ['aliases', 'associates', 'family', 'education', 'employment_history', 'social_profiles',
               'news_mentions', 'court_records', 'property_records', 'breach_data'],
    'company': ['officers', 'shareholders', 'beneficial_owners', 'subsidiaries', 'parent_company',
                'filings', 'financials', 'trademarks', 'domains', 'news_mentions', 'sanctions', 'court_records'],
    'domain': ['backlinks', 'outlinks', 'subdomains', 'ssl_history', 'dns_history', 'whois_history',
               'co_hosted', 'ga_linked', 'archive_snapshots', 'technologies'],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_required_fields(entity_type: str) -> List[str]:
    """Get required Core fields for entity type."""
    return EXPECTED_FIELDS.get(entity_type, [])


def get_optional_fields(entity_type: str) -> List[str]:
    """Get optional Shell fields for entity type."""
    return POSSIBLE_FIELDS.get(entity_type, [])


def get_enrichment_fields(entity_type: str) -> List[str]:
    """Get Halo enrichment fields for entity type."""
    return ENRICHMENT_FIELDS.get(entity_type, [])


def get_schema(entity_type: str) -> Dict[str, Any]:
    """Get full schema for entity type."""
    return ENTITY_SCHEMA.get(entity_type, {})


def check_completeness(entity: Entity) -> Dict[str, Any]:
    """
    Check entity completeness against schema.

    Returns:
        {
            'core_complete': bool,
            'shell_complete': bool,
            'halo_started': bool,
            'core_missing': List[str],
            'shell_missing': List[str],
            'core_percent': float,
            'shell_percent': float,
        }
    """
    entity_type = entity.entity_type.value if isinstance(entity.entity_type, EntityType) else entity.entity_type
    schema = get_schema(entity_type)

    if not schema:
        return {
            'core_complete': False,
            'shell_complete': False,
            'halo_started': False,
            'core_missing': [],
            'shell_missing': [],
            'core_percent': 0.0,
            'shell_percent': 0.0,
        }

    # Check Core
    core_schema = schema.get('core', {})
    required_core = [k for k, v in core_schema.items() if v.get('required', False)]
    core_present = [k for k in required_core if entity.has_attribute(k)]
    core_missing = [k for k in required_core if k not in core_present]
    core_complete = len(core_missing) == 0
    core_percent = len(core_present) / len(required_core) if required_core else 1.0

    # Check Shell
    shell_schema = schema.get('shell', {})
    shell_fields = list(shell_schema.keys())
    shell_present = [k for k in shell_fields if entity.has_attribute(k)]
    shell_missing = [k for k in shell_fields if k not in shell_present]
    shell_complete = len(shell_present) >= len(shell_fields) * 0.5  # 50% threshold
    shell_percent = len(shell_present) / len(shell_fields) if shell_fields else 1.0

    # Check Halo
    halo_schema = schema.get('halo', {})
    halo_fields = list(halo_schema.keys())
    halo_present = [k for k in halo_fields if entity.has_attribute(k)]
    halo_started = len(halo_present) > 0

    return {
        'core_complete': core_complete,
        'shell_complete': shell_complete,
        'halo_started': halo_started,
        'core_missing': core_missing,
        'shell_missing': shell_missing,
        'core_percent': core_percent,
        'shell_percent': shell_percent,
    }


def get_enrichment_routes(entity: Entity) -> List[Dict[str, Any]]:
    """
    Get enrichment routes for an entity based on what's missing.

    Returns list of route suggestions:
    [
        {'field': 'officers', 'io_module': 'corporella', 'priority': 'high'},
        {'field': 'email', 'io_module': 'eye-d', 'priority': 'medium'},
    ]
    """
    entity_type = entity.entity_type.value if isinstance(entity.entity_type, EntityType) else entity.entity_type
    completeness = check_completeness(entity)
    routes = []

    # Route mappings by entity type and field
    ROUTE_MAP = {
        'person': {
            'email': {'io_module': 'eye-d', 'priority': 'high'},
            'phone': {'io_module': 'eye-d', 'priority': 'medium'},
            'employer': {'io_module': 'corporella', 'priority': 'medium'},
            'social_profiles': {'io_module': 'eye-d', 'priority': 'medium'},
            'breach_data': {'io_module': 'eye-d', 'priority': 'low'},
            'associates': {'io_module': 'corporella', 'priority': 'medium'},
        },
        'company': {
            'officers': {'io_module': 'corporella', 'priority': 'high'},
            'shareholders': {'io_module': 'corporella', 'priority': 'high'},
            'beneficial_owners': {'io_module': 'corporella', 'priority': 'high'},
            'filings': {'io_module': 'corporella', 'priority': 'medium'},
            'subsidiaries': {'io_module': 'corporella', 'priority': 'medium'},
            'domains': {'io_module': 'linklater', 'priority': 'low'},
        },
        'domain': {
            'backlinks': {'io_module': 'linklater', 'priority': 'high'},
            'whois_history': {'io_module': 'linklater', 'priority': 'medium'},
            'ssl_history': {'io_module': 'linklater', 'priority': 'low'},
            'archive_snapshots': {'io_module': 'linklater', 'priority': 'medium'},
        },
    }

    entity_routes = ROUTE_MAP.get(entity_type, {})

    # Add routes for missing shell fields
    for field in completeness['shell_missing']:
        if field in entity_routes:
            routes.append({
                'field': field,
                **entity_routes[field]
            })

    # Add routes for halo fields if shell is complete
    if completeness['shell_complete'] and not completeness['halo_started']:
        halo_fields = get_enrichment_fields(entity_type)
        for field in halo_fields[:5]:  # Top 5 halo fields
            if field in entity_routes:
                routes.append({
                    'field': field,
                    **entity_routes[field]
                })

    return sorted(routes, key=lambda r: {'high': 0, 'medium': 1, 'low': 2}.get(r['priority'], 3))


# =============================================================================
# EDGE TYPE DEFINITIONS
# =============================================================================

EDGE_TYPES = {
    # Entity relationships
    'associated_with': {'description': 'Two entities are associated', 'bidirectional': True},
    'family_of': {'description': 'Family relationship', 'bidirectional': True},
    'officer_of': {'description': 'Person is officer of company', 'bidirectional': False},
    'shareholder_of': {'description': 'Entity is shareholder of company', 'bidirectional': False},
    'ubo_of': {'description': 'Ultimate beneficial owner of company', 'bidirectional': False},
    'parent_of': {'description': 'Parent company of subsidiary', 'bidirectional': False},
    'subsidiary_of': {'description': 'Subsidiary of parent company', 'bidirectional': False},
    'owns_domain': {'description': 'Entity owns domain', 'bidirectional': False},
    'has_email': {'description': 'Entity has email', 'bidirectional': False},
    'has_phone': {'description': 'Entity has phone', 'bidirectional': False},
    'located_at': {'description': 'Entity located at address', 'bidirectional': False},

    # Link analysis
    'links_to': {'description': 'Source links to target', 'bidirectional': False},
    'links_from': {'description': 'Source linked from target', 'bidirectional': False},
    'shares_hosting_with': {'description': 'Domains share hosting/IP', 'bidirectional': True},
    'shares_ga_with': {'description': 'Domains share Google Analytics', 'bidirectional': True},

    # Bulk operation edges
    'mentioned_on': {
        'description': 'Entity mentioned on source URL (discovered via brute search)',
        'bidirectional': False,
        'source_class': ['@PERSON', '@COMPANY', '@SUBJECT'],
        'target_class': ['@SOURCE', '@DOCUMENT'],
    },
    'tagged_with': {
        'description': 'Node tagged with tag',
        'bidirectional': False,
        'source_class': ['*'],
        'target_class': ['@TAG'],
    },
    'part_of_batch': {
        'description': 'Node was part of bulk selection batch',
        'bidirectional': False,
        'source_class': ['*'],
        'target_class': ['@QUERY'],
    },
    'part_of_workstream': {
        'description': 'Query contributes to workstream narrative',
        'bidirectional': False,
        'source_class': ['@QUERY'],
        'target_class': ['@NARRATIVE'],
    },
    'related_at_time': {
        'description': 'Nodes were related at time of batch selection (temporal snapshot)',
        'bidirectional': True,
        'source_class': ['*'],
        'target_class': ['*'],
    },

    # Handshake/pairwise comparison edges
    'similar_to': {
        'description': 'Entities are similar (from handshake/beer N×N comparison)',
        'bidirectional': True,
        'source_class': ['@PERSON', '@COMPANY', '@SUBJECT', '*'],
        'target_class': ['@PERSON', '@COMPANY', '@SUBJECT', '*'],
    },
    'part_of_cluster': {
        'description': 'Entity is part of a similarity cluster',
        'bidirectional': False,
        'source_class': ['*'],
        'target_class': ['@QUERY'],
    },
}


def get_edge_type(edge_type: str) -> Optional[Dict[str, Any]]:
    """Get edge type definition."""
    return EDGE_TYPES.get(edge_type)


def is_valid_edge(source_class: str, target_class: str, edge_type: str) -> bool:
    """Check if edge is valid for given source and target classes."""
    defn = EDGE_TYPES.get(edge_type)
    if not defn:
        return False

    source_classes = defn.get('source_class', ['*'])
    target_classes = defn.get('target_class', ['*'])

    source_ok = '*' in source_classes or source_class in source_classes
    target_ok = '*' in target_classes or target_class in target_classes

    return source_ok and target_ok
