"""
Integration wrapper to preserve backward compatibility.
Routes calls to either the original date_extractor.py or the enhanced module.
"""

import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Check if we should use the enhanced extractor
USE_ENHANCED_EXTRACTOR = os.getenv('USE_ENHANCED_DATE_EXTRACTOR', 'true').lower() == 'true'

def extract_date_info(url: str, title: str = '', snippet: str = '') -> Dict[str, Any]:
    """
    Extract date information with automatic routing to enhanced or original extractor.
    
    This function maintains 100% backward compatibility while allowing
    gradual migration to the enhanced extractor.
    """
    try:
        if USE_ENHANCED_EXTRACTOR:
            # Try enhanced extractor first
            from .date_extractor_enhanced import extract_date_info as enhanced_extract
            result = enhanced_extract(url, title, snippet)
            
            # Log that we're using enhanced extractor (for monitoring)
            if result.get('year'):
                logger.debug(f"Enhanced extractor found date: {result.get('full_date', result.get('year'))}")
            
            return result
        else:
            # Use original extractor
            from date_extractor import extract_date_info as original_extract
            return original_extract(url, title, snippet)
            
    except Exception as e:
        logger.warning(f"Date extraction error, falling back to original: {e}")
        
        # Fallback to original extractor on any error
        try:
            from date_extractor import extract_date_info as original_extract
            return original_extract(url, title, snippet)
        except Exception as fallback_error:
            logger.error(f"Original extractor also failed: {fallback_error}")
            
            # Return empty result matching expected format
            return {
                'year': None,
                'month': None,
                'day': None,
                'full_date': None,
                'date_source': None,
                'confidence': 0.0,
                'age_category': 'unknown',
                'date_match_text': None,
                'date_match_source': None,
                'date_match_start': None,
                'date_match_end': None
            }


def get_date_extractor_stats() -> Dict[str, Any]:
    """Get statistics about date extractor usage (for monitoring)."""
    return {
        'enhanced_enabled': USE_ENHANCED_EXTRACTOR,
        'module': 'enhanced' if USE_ENHANCED_EXTRACTOR else 'original'
    }


# Enhanced-only functions (not in original)
def extract_all_dates(url: str, title: str = '', snippet: str = '') -> Dict[str, Any]:
    """
    Extract all dates found (enhanced feature).
    Falls back to single date if enhanced extractor not available.
    """
    if USE_ENHANCED_EXTRACTOR:
        try:
            from .date_extractor_enhanced import extract_all_dates as enhanced_extract_all
            return enhanced_extract_all(url, title, snippet)
        except Exception as e:
            logger.warning(f"Enhanced extract_all_dates failed: {e}")
    
    # Fallback: wrap single date extraction
    single_date = extract_date_info(url, title, snippet)
    if single_date.get('year'):
        return {
            'primary_date': single_date,
            'all_dates': [single_date],
            'date_count': 1
        }
    else:
        return {
            'primary_date': None,
            'all_dates': [],
            'date_count': 0
        }


def parse_archive_date(url: str) -> Dict[str, Any]:
    """
    Parse Archive.org specific dates (enhanced feature).
    Returns None if enhanced extractor not available.
    """
    if USE_ENHANCED_EXTRACTOR:
        try:
            from .archive_date_parser import parse_archive_date as enhanced_parse
            return enhanced_parse(url)
        except Exception as e:
            logger.warning(f"Archive date parsing failed: {e}")
    
    return None