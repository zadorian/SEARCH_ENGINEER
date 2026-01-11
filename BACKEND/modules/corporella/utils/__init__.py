"""
Corporella Claude Utilities
Shared utilities for ID decoding, entity manipulation, and data enrichment
"""

from .wikiman_id_decoder import decode_id, DecodedID

__all__ = ['decode_id', 'DecodedID']
