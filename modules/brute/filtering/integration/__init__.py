#!/usr/bin/env python3
"""
Filter Integration Module
Bridges filtering system with search types and recall optimization
"""

from Search_Integration.search_type_adapter import (
    BaseSearchAdapter,
    FileTypeSearchAdapter,
    ProximitySearchAdapter,
    LocationSearchAdapter,
    CorporateSearchAdapter,
    DateSearchAdapter,
    LanguageSearchAdapter,
    get_search_adapter
)

from .recall_filter_bridge import (
    BridgeConfig,
    RecallFilterBridge,
    create_coordinated_system
)

__all__ = [
    # Search Type Adapters
    'BaseSearchAdapter',
    'FileTypeSearchAdapter',
    'ProximitySearchAdapter',
    'LocationSearchAdapter',
    'CorporateSearchAdapter',
    'DateSearchAdapter',
    'LanguageSearchAdapter',
    'get_search_adapter',
    
    # Recall-Filter Bridge
    'BridgeConfig',
    'RecallFilterBridge',
    'create_coordinated_system'
]