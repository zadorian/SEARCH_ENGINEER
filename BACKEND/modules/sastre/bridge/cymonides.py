"""
SASTRE Cymonides Bridge

Bridge to Cymonides entity storage and WDC indices.
This is the UNKNOWN KNOWNS check - search what we already have
before going to external sources.

Uses:
- wdc-person-entities: Person records from Schema.org
- wdc-organization-entities: Company/org records
- wdc-localbusiness-entities: Local business records
- wdc-product-entities: Product records
"""

# Re-export from bridges.py
from ..bridges import CymonidesBridge

__all__ = ['CymonidesBridge']
