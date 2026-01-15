"""
Enhanced date extractor with comprehensive pattern support.
Backward compatible with existing date_extractor.py interface.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

# Import our specialized modules
try:
    # Try relative imports first (when used as package)
    from .date_patterns import get_date_patterns, MONTH_NAMES, SEASONS, RELATIVE_TIME_UNITS
    from .archive_date_parser import ArchiveDateParser
except ImportError:
    # Fall back to direct imports (when used standalone)
    from date_patterns import get_date_patterns, MONTH_NAMES, SEASONS, RELATIVE_TIME_UNITS
    from archive_date_parser import ArchiveDateParser

logger = logging.getLogger(__name__)


class EnhancedDateExtractor:
    """Enhanced date extraction with support for multiple formats and sources."""
    
    def __init__(self):
        self.patterns = get_date_patterns()
        self.archive_parser = ArchiveDateParser
        self.current_year = datetime.now().year
        self.current_date = datetime.now()
    
    def extract_all_dates(self, url: str, title: str = '', snippet: str = '') -> Dict[str, Any]:
        """
        Extract all possible dates from the given sources.
        
        Args:
            url: URL to extract dates from
            title: Title text
            snippet: Snippet/description text
            
        Returns:
            Dict containing primary date and all found dates with metadata
        """
        all_dates = []
        
        # First, check if this is an Archive.org URL
        if 'archive.org' in url.lower():
            archive_info = self.archive_parser.get_comprehensive_date_info(url, title, snippet)
            if archive_info['archive_date']:
                all_dates.append({
                    'date': archive_info['archive_date'],
                    'source': 'archive_url',
                    'confidence': archive_info['archive_date']['confidence'],
                    'type': 'archive_date'
                })
        
        # Extract dates from each source
        for source_text, source_name in [(url, 'url'), (title, 'title'), (snippet, 'snippet')]:
            if not source_text:
                continue
            
            found_dates = self._extract_from_text(source_text, source_name)
            all_dates.extend(found_dates)
        
        # Sort by confidence and select primary date
        if all_dates:
            all_dates.sort(key=lambda x: x['confidence'], reverse=True)
            primary_date = all_dates[0]
        else:
            primary_date = None
        
        return {
            'primary_date': primary_date,
            'all_dates': all_dates,
            'date_count': len(all_dates)
        }
    
    def _extract_from_text(self, text: str, source: str) -> List[Dict[str, Any]]:
        """Extract all dates from a text using all patterns."""
        found_dates = []
        
        # Get all patterns with confidence scores
        for pattern, pattern_type, confidence in self.patterns.get_all_patterns():
            matches = pattern.finditer(text)
            
            for match in matches:
                date_info = self._parse_match(match, pattern_type, confidence, source)
                if date_info:
                    date_info['match_start'] = match.start()
                    date_info['match_end'] = match.end()
                    date_info['match_text'] = match.group(0)
                    found_dates.append(date_info)
        
        return found_dates
    
    def _parse_match(self, match: re.Match, pattern_type: str, 
                    confidence: float, source: str) -> Optional[Dict[str, Any]]:
        """Parse a regex match into structured date information."""
        try:
            groups = match.groups()
            
            if pattern_type == 'wayback_timestamp':
                # Already handled by archive parser
                return None
            
            elif pattern_type in ['iso_full', 'us_full', 'eu_full']:
                year, month, day = self._parse_full_date(groups, pattern_type)
                if self._is_valid_date(year, month, day):
                    return self._create_date_info(year, month, day, pattern_type, 
                                                confidence, source)
            
            elif pattern_type in ['long_format', 'medium_format']:
                year, month, day = self._parse_text_date(groups)
                if self._is_valid_date(year, month, day):
                    return self._create_date_info(year, month, day, pattern_type, 
                                                confidence, source)
            
            elif pattern_type == 'year_month':
                year, month = self._parse_year_month(groups)
                if self._is_valid_date(year, month, 1):
                    return self._create_date_info(year, month, None, pattern_type, 
                                                confidence, source)
            
            elif pattern_type == 'quarter':
                year, quarter = self._parse_quarter(groups)
                if year and quarter:
                    month = (quarter - 1) * 3 + 1
                    return self._create_date_info(year, month, None, pattern_type, 
                                                confidence, source, 
                                                extra={'quarter': quarter})
            
            elif pattern_type == 'academic_year':
                start_year, end_year = self._parse_academic_year(groups)
                if start_year and end_year:
                    return self._create_date_info(start_year, 9, None, pattern_type, 
                                                confidence, source,
                                                extra={'end_year': end_year})
            
            elif pattern_type == 'season_year':
                season, year = groups[0].lower(), int(groups[1])
                if season in SEASONS and self._is_valid_year(year):
                    start_month, _ = SEASONS[season]
                    return self._create_date_info(year, start_month, None, pattern_type,
                                                confidence, source,
                                                extra={'season': season})
            
            elif pattern_type == 'iso_week':
                year = int(groups[0])
                week = int(groups[1])
                if self._is_valid_year(year) and 1 <= week <= 53:
                    # Convert ISO week to approximate date
                    date = datetime.strptime(f'{year}-W{week}-1', '%Y-W%W-%w')
                    return self._create_date_info(date.year, date.month, date.day,
                                                pattern_type, confidence, source,
                                                extra={'iso_week': week})
            
            elif pattern_type == 'year_only':
                year = int(groups[0])
                if self._is_valid_year(year):
                    return self._create_date_info(year, None, None, pattern_type,
                                                confidence, source)
            
            elif pattern_type == 'relative_specific':
                # "3 days ago"
                amount = int(groups[0])
                unit = groups[1].lower()
                date = self._calculate_relative_date(amount, unit)
                if date:
                    return self._create_date_info(date.year, date.month, date.day,
                                                pattern_type, confidence, source,
                                                extra={'relative': f'{amount} {unit} ago'})
            
            elif pattern_type == 'relative_general':
                # "yesterday", "last week", etc.
                date = self._parse_relative_general(groups)
                if date:
                    return self._create_date_info(date.year, date.month, date.day,
                                                pattern_type, confidence, source)
            
        except (ValueError, IndexError) as e:
            logger.debug(f"Error parsing date match: {e}")
        
        return None
    
    def _parse_full_date(self, groups: Tuple, pattern_type: str) -> Tuple[int, int, int]:
        """Parse full date formats."""
        if pattern_type == 'iso_full':
            return int(groups[0]), int(groups[1]), int(groups[2])
        elif pattern_type == 'us_full':
            return int(groups[2]), int(groups[0]), int(groups[1])
        elif pattern_type == 'eu_full':
            return int(groups[2]), int(groups[1]), int(groups[0])
        return None, None, None
    
    def _parse_text_date(self, groups: Tuple) -> Tuple[int, int, int]:
        """Parse text-based date formats like 'January 15, 2024'."""
        # Handle both "Month Day, Year" and "Day Month Year"
        if groups[0].lower() in MONTH_NAMES:
            # Month Day, Year
            month = MONTH_NAMES[groups[0].lower()]
            day = int(groups[1]) if len(groups) > 1 else 1
            year = int(groups[2]) if len(groups) > 2 else self.current_year
        else:
            # Day Month Year
            day = int(groups[0])
            month = MONTH_NAMES[groups[1].lower()] if len(groups) > 1 else 1
            year = int(groups[2]) if len(groups) > 2 else self.current_year
        
        return year, month, day
    
    def _parse_year_month(self, groups: Tuple) -> Tuple[int, int]:
        """Parse year-month formats."""
        if len(groups) >= 2:
            # Check if first group is month name
            if groups[0].lower() in MONTH_NAMES:
                month = MONTH_NAMES[groups[0].lower()]
                year = int(groups[1])
            else:
                year = int(groups[0])
                # Second group might be month number or name
                if groups[1].lower() in MONTH_NAMES:
                    month = MONTH_NAMES[groups[1].lower()]
                else:
                    month = int(groups[1])
            return year, month
        return None, None
    
    def _parse_quarter(self, groups: Tuple) -> Tuple[int, int]:
        """Parse quarter formats like Q1 2024."""
        try:
            if groups[0].isdigit():
                # Q1 2024 format
                quarter = int(groups[0])
                year = int(groups[1])
            else:
                # 2024 Q1 format
                year = int(groups[0])
                quarter = int(groups[1])
            return year, quarter
        except Exception as e:
            return None, None
    
    def _parse_academic_year(self, groups: Tuple) -> Tuple[int, int]:
        """Parse academic year formats like 2023-2024."""
        try:
            start_year = int(groups[0])
            if len(groups[1]) == 2:
                # 2023-24 format
                century = start_year // 100
                end_year = century * 100 + int(groups[1])
            else:
                # 2023-2024 format
                end_year = int(groups[1])
            return start_year, end_year
        except Exception as e:
            return None, None
    
    def _calculate_relative_date(self, amount: int, unit: str) -> Optional[datetime]:
        """Calculate date from relative expression like '3 days ago'."""
        unit = unit.rstrip('s').lower()  # Remove plural 's'
        
        if unit in RELATIVE_TIME_UNITS:
            seconds = amount * RELATIVE_TIME_UNITS[unit]
            return self.current_date - timedelta(seconds=seconds)
        
        return None
    
    def _parse_relative_general(self, groups: Tuple) -> Optional[datetime]:
        """Parse general relative dates like 'yesterday', 'last week'."""
        text = ' '.join(groups).lower()
        
        if 'yesterday' in text:
            return self.current_date - timedelta(days=1)
        elif 'today' in text:
            return self.current_date
        elif 'tomorrow' in text:
            return self.current_date + timedelta(days=1)
        elif 'last week' in text:
            return self.current_date - timedelta(weeks=1)
        elif 'this week' in text:
            return self.current_date
        elif 'next week' in text:
            return self.current_date + timedelta(weeks=1)
        elif 'last month' in text:
            # Approximate
            return self.current_date - timedelta(days=30)
        elif 'this month' in text:
            return self.current_date
        elif 'next month' in text:
            return self.current_date + timedelta(days=30)
        
        return None
    
    def _is_valid_date(self, year: int, month: int = None, day: int = None) -> bool:
        """Check if date components are valid."""
        if not self._is_valid_year(year):
            return False
        
        if month is not None and not (1 <= month <= 12):
            return False
        
        if day is not None:
            if month is None:
                return False
            try:
                datetime(year, month, day)
            except ValueError:
                return False
        
        return True
    
    def _is_valid_year(self, year: int) -> bool:
        """Check if year is in reasonable range."""
        return 1900 <= year <= self.current_year + 2  # Allow 2 years in future
    
    def _create_date_info(self, year: int, month: int = None, day: int = None,
                         pattern_type: str = '', confidence: float = 0.5,
                         source: str = '', extra: Dict = None) -> Dict[str, Any]:
        """Create standardized date information dict."""
        info = {
            'year': year,
            'month': month,
            'day': day,
            'pattern_type': pattern_type,
            'confidence': confidence,
            'source': source,
            'age_category': self._categorize_age(year)
        }
        
        # Add formatted dates
        if day and month:
            try:
                date_obj = datetime(year, month, day)
                info['iso_date'] = date_obj.strftime('%Y-%m-%d')
                info['datetime'] = date_obj
                info['days_old'] = (self.current_date - date_obj).days
            except ValueError:
                pass
        elif month:
            info['iso_date'] = f"{year}-{month:02d}"
        else:
            info['iso_date'] = str(year)
        
        # Add extra information if provided
        if extra:
            info['extra'] = extra
        
        return info
    
    def _categorize_age(self, year: int) -> str:
        """Enhanced age categorization."""
        if not year:
            return 'unknown'
        
        age_years = self.current_year - year
        
        if age_years < 0:
            return 'future'
        elif age_years == 0:
            return 'this_year'
        elif age_years == 1:
            return 'last_year'
        elif age_years <= 3:
            return 'recent'
        elif age_years <= 5:
            return '2-5_years'
        elif age_years <= 10:
            return '5-10_years'
        elif age_years <= 20:
            return 'older'
        elif age_years <= 50:
            return 'vintage'
        else:
            return 'historical'


# Backward compatibility function
def extract_date_info(url: str, title: str = '', snippet: str = '') -> Dict[str, Any]:
    """
    Backward compatible interface matching original date_extractor.py.
    
    Returns dict matching the original format.
    """
    extractor = EnhancedDateExtractor()
    result = extractor.extract_all_dates(url, title, snippet)
    
    # Format response to match original interface
    if result['primary_date']:
        primary = result['primary_date']
        date_info = primary.get('date', {}) if isinstance(primary.get('date'), dict) else {}
        
        return {
            'year': primary.get('year') or date_info.get('year'),
            'month': primary.get('month') or date_info.get('month'),
            'day': primary.get('day') or date_info.get('day'),
            'full_date': primary.get('iso_date') or date_info.get('iso_date'),
            'date_source': primary.get('source'),
            'confidence': primary.get('confidence', 0.5),
            'age_category': primary.get('age_category', 'unknown'),
            # Match info for highlighting
            'date_match_text': primary.get('match_text'),
            'date_match_source': primary.get('source'),
            'date_match_start': primary.get('match_start'),
            'date_match_end': primary.get('match_end')
        }
    else:
        # Return empty date info matching original format
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


# Additional convenience function for getting all dates
def extract_all_dates(url: str, title: str = '', snippet: str = '') -> Dict[str, Any]:
    """Get comprehensive date extraction with all found dates."""
    extractor = EnhancedDateExtractor()
    return extractor.extract_all_dates(url, title, snippet)