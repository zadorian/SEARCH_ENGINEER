"""
PSC (Persons with Significant Control) Module
==============================================

Handles UK PSC data and OpenOwnership beneficial ownership:
- Per-country PSC indices
- Foreign company jurisdiction routing
- Cross-country corporate searches
"""

from .uk_psc_search import UKPSCSearcher
from .jurisdiction_router import JurisdictionRouter
from .psc_indices import PSCIndexManager

__all__ = ["UKPSCSearcher", "JurisdictionRouter", "PSCIndexManager"]
