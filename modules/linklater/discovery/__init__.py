from .majestic_discovery import (
    get_related_sites,
    get_hosted_domains,
    get_ref_domains,
    get_backlink_data,
    discover_similar_domains
)

from .whois_discovery import (
    cluster_domains_by_whois,
    whois_lookup,
    reverse_whois_by_registrant,
    find_domains_by_nameserver
)

from .filetype_discovery import (
    discover_filetypes,
    batch_discover_filetypes,
    FiletypeDiscoveryResponse,
    FiletypeResult
)

# Tech stack discovery (Wappalyzer/BuiltWith equivalent)
from .tech_discovery import discover_tech_stack

# Similar domains (content-based similarity)
from .similar_discovery import find_similar_content

__all__ = [
    # Majestic
    'get_related_sites',
    'get_hosted_domains',
    'get_ref_domains',
    'get_backlink_data',
    'discover_similar_domains',
    # Whois
    'cluster_domains_by_whois',
    'whois_lookup',
    'reverse_whois_by_registrant',
    'find_domains_by_nameserver',
    # Filetype
    'discover_filetypes',
    'batch_discover_filetypes',
    'FiletypeDiscoveryResponse',
    'FiletypeResult',
    # Tech
    'discover_tech_stack',
    # Similar
    'find_similar_content',
]