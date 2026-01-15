"""
Enhanced date filtering module for Search_Engineer.
Provides comprehensive date extraction with backward compatibility.
"""

# Import main functions for easy access
from .date_extractor_enhanced import (
    extract_date_info,  # Backward compatible function
    extract_all_dates,  # Enhanced function with all dates
    EnhancedDateExtractor
)

from .archive_date_parser import (
    parse_archive_date,
    get_archive_date_info,
    ArchiveDateParser
)

from .date_patterns import (
    get_date_patterns,
    MONTH_NAMES,
    SEASONS,
    RELATIVE_TIME_UNITS,
    PATTERN_TYPES
)

# Version info
__version__ = '1.0.0'
__all__ = [
    'extract_date_info',
    'extract_all_dates', 
    'EnhancedDateExtractor',
    'parse_archive_date',
    'get_archive_date_info',
    'ArchiveDateParser',
    'get_date_patterns',
    'MONTH_NAMES',
    'SEASONS',
    'RELATIVE_TIME_UNITS',
    'PATTERN_TYPES'
]