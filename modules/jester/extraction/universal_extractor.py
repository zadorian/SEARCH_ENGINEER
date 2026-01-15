"""
Universal Extractor stub - provides minimal interface for JESTER compatibility.
"""

import logging

logger = logging.getLogger(__name__)

class UniversalExtractor:
    """Minimal UniversalExtractor for JESTER compatibility."""
    
    def __init__(self, *args, **kwargs):
        logger.debug("UniversalExtractor stub initialized")
    
    def extract(self, text: str, **kwargs):
        """Returns empty extraction - full implementation in CYMONIDES."""
        return {}
    
    async def extract_async(self, text: str, **kwargs):
        """Async extraction stub."""
        return {}

def get_model(*args, **kwargs):
    return None

def get_golden_embeddings(*args, **kwargs):
    return []

def get_red_flag_entities(*args, **kwargs):
    return []
