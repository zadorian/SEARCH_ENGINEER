"""
Comprehensive date patterns and formats for enhanced date extraction.
Consolidates all date-related patterns in one place.
"""

import re
from typing import List, Tuple, Dict, Pattern

# Date pattern types with confidence scores
PATTERN_TYPES = {
    'wayback_timestamp': 0.95,      # Archive.org wayback machine URLs
    'iso_full': 0.95,               # YYYY-MM-DD
    'us_full': 0.93,                # MM/DD/YYYY
    'eu_full': 0.93,                # DD.MM.YYYY or DD/MM/YYYY
    'long_format': 0.92,            # January 15, 2024
    'medium_format': 0.90,          # Jan 15, 2024
    'year_month': 0.85,             # YYYY-MM or January 2024
    'quarter': 0.83,                # Q1 2024
    'academic_year': 0.82,          # 2023-2024
    'season_year': 0.80,            # Spring 2024
    'iso_week': 0.80,               # 2024-W03
    'year_only': 0.75,              # 2024
    'relative_specific': 0.90,      # 3 days ago (with specific number)
    'relative_general': 0.70,       # last week, yesterday
}

# Month name mappings (comprehensive)
MONTH_NAMES = {
    # Full names
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    # Common abbreviations
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9,
    'oct': 10, 'nov': 11, 'dec': 12,
    # Other languages (common ones)
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
    # German
    'januar': 1, 'februar': 2, 'märz': 3, 'april': 4,
    'mai': 5, 'juni': 6, 'juli': 7, 'august': 8,
    'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12,
}

# Season mappings
SEASONS = {
    'spring': (3, 6),    # March to June
    'summer': (6, 9),    # June to September
    'fall': (9, 12),     # September to December
    'autumn': (9, 12),   # Same as fall
    'winter': (12, 3),   # December to March (crosses year boundary)
}

# Relative time units
RELATIVE_TIME_UNITS = {
    'second': 1,
    'minute': 60,
    'hour': 3600,
    'day': 86400,
    'week': 604800,
    'month': 2592000,  # Approximate (30 days)
    'year': 31536000,
}

class DatePatterns:
    """Collection of compiled regex patterns for date extraction."""
    
    def __init__(self):
        self.patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> Dict[str, List[Tuple[Pattern, str]]]:
        """Compile all date patterns for efficient matching."""
        patterns = {
            'primary': [],      # High-confidence patterns to try first
            'secondary': [],    # Medium-confidence patterns
            'fallback': []      # Low-confidence patterns
        }
        
        # Wayback Machine timestamp pattern (highest confidence)
        # Format: /web/YYYYMMDDhhmmss/ or /web/YYYYMMDD*/
        patterns['primary'].append((
            re.compile(r'/web/(\d{4})(\d{2})(\d{2})(?:\d{6})?(?:\*)?/', re.IGNORECASE),
            'wayback_timestamp'
        ))
        
        # ISO date: YYYY-MM-DD
        patterns['primary'].append((
            re.compile(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b'),
            'iso_full'
        ))
        
        # US date: MM/DD/YYYY or MM-DD-YYYY
        patterns['primary'].append((
            re.compile(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b'),
            'us_full'
        ))
        
        # European date: DD.MM.YYYY or DD/MM/YYYY
        patterns['primary'].append((
            re.compile(r'\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b'),
            'eu_full'
        ))
        
        # Long format: January 15, 2024 or 15 January 2024
        month_pattern = '|'.join(MONTH_NAMES.keys())
        patterns['primary'].append((
            re.compile(rf'\b({month_pattern})\s+(\d{{1,2}}),?\s+(\d{{4}})\b', re.IGNORECASE),
            'long_format'
        ))
        patterns['primary'].append((
            re.compile(rf'\b(\d{{1,2}})\s+({month_pattern})\s+(\d{{4}})\b', re.IGNORECASE),
            'long_format'
        ))
        
        # Medium format: Jan 15, 2024
        patterns['secondary'].append((
            re.compile(rf'\b({month_pattern})\s+(\d{{1,2}}),?\s+(\d{{4}})\b', re.IGNORECASE),
            'medium_format'
        ))
        
        # Year-Month: YYYY-MM or YYYY/MM
        patterns['secondary'].append((
            re.compile(r'\b(\d{4})[-/](\d{1,2})\b'),
            'year_month'
        ))
        
        # Month Year: January 2024
        patterns['secondary'].append((
            re.compile(rf'\b({month_pattern})\s+(\d{{4}})\b', re.IGNORECASE),
            'year_month'
        ))
        
        # Quarter: Q1 2024, 1Q2024, etc.
        patterns['secondary'].append((
            re.compile(r'\b[Qq]([1-4])\s*[-/]?\s*(\d{4})\b'),
            'quarter'
        ))
        patterns['secondary'].append((
            re.compile(r'\b(\d{4})\s*[-/]?\s*[Qq]([1-4])\b'),
            'quarter'
        ))
        
        # Academic year: 2023-2024, 2023/2024, 2023-24
        patterns['secondary'].append((
            re.compile(r'\b(\d{4})[-/](\d{4})\b'),
            'academic_year'
        ))
        patterns['secondary'].append((
            re.compile(r'\b(\d{4})[-/](\d{2})\b'),
            'academic_year'
        ))
        
        # Season + Year: Spring 2024
        season_pattern = '|'.join(SEASONS.keys())
        patterns['secondary'].append((
            re.compile(rf'\b({season_pattern})\s+(\d{{4}})\b', re.IGNORECASE),
            'season_year'
        ))
        
        # ISO Week: 2024-W03
        patterns['secondary'].append((
            re.compile(r'\b(\d{4})-W(\d{1,2})\b', re.IGNORECASE),
            'iso_week'
        ))
        
        # URL path dates: /2024/01/15/ or /blog/2024-01-15/
        patterns['secondary'].append((
            re.compile(r'/(\d{4})/(\d{1,2})/(\d{1,2})/'),
            'iso_full'
        ))
        
        # Standalone year (fallback)
        patterns['fallback'].append((
            re.compile(r'\b(19\d{2}|20\d{2})\b'),
            'year_only'
        ))
        
        # Relative dates with specific numbers: "3 days ago", "2 weeks ago"
        unit_pattern = '|'.join(RELATIVE_TIME_UNITS.keys())
        patterns['secondary'].append((
            re.compile(rf'\b(\d+)\s+({unit_pattern})s?\s+ago\b', re.IGNORECASE),
            'relative_specific'
        ))
        
        # General relative dates: "yesterday", "last week", "this month"
        patterns['fallback'].append((
            re.compile(r'\b(yesterday|today|tomorrow)\b', re.IGNORECASE),
            'relative_general'
        ))
        patterns['fallback'].append((
            re.compile(rf'\b(this|last|next)\s+({unit_pattern})\b', re.IGNORECASE),
            'relative_general'
        ))
        
        return patterns
    
    def get_all_patterns(self) -> List[Tuple[Pattern, str, float]]:
        """Get all patterns with their types and confidence scores."""
        all_patterns = []
        
        # Add patterns in priority order
        for pattern, pattern_type in self.patterns['primary']:
            confidence = PATTERN_TYPES.get(pattern_type, 0.5)
            all_patterns.append((pattern, pattern_type, confidence))
        
        for pattern, pattern_type in self.patterns['secondary']:
            confidence = PATTERN_TYPES.get(pattern_type, 0.5)
            all_patterns.append((pattern, pattern_type, confidence))
        
        for pattern, pattern_type in self.patterns['fallback']:
            confidence = PATTERN_TYPES.get(pattern_type, 0.5)
            all_patterns.append((pattern, pattern_type, confidence))
        
        return all_patterns
    
    def get_patterns_by_priority(self, priority: str) -> List[Tuple[Pattern, str]]:
        """Get patterns by priority level ('primary', 'secondary', 'fallback')."""
        return self.patterns.get(priority, [])


# Singleton instance
_date_patterns = None

def get_date_patterns() -> DatePatterns:
    """Get singleton DatePatterns instance."""
    global _date_patterns
    if _date_patterns is None:
        _date_patterns = DatePatterns()
    return _date_patterns