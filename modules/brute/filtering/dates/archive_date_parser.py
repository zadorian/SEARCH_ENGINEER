"""
Specialized parser for Archive.org dates.
Handles Wayback Machine URLs and other Archive.org specific formats.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class ArchiveDateParser:
    """Parse dates from Archive.org URLs and content."""
    
    # Wayback Machine URL patterns
    WAYBACK_PATTERNS = [
        # Standard format: /web/YYYYMMDDhhmmss/url
        re.compile(r'/web/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})/'),
        # Short format: /web/YYYYMMDD*/url (wildcard for time)
        re.compile(r'/web/(\d{4})(\d{2})(\d{2})\*/'),
        # With additional modifiers: /web/YYYYMMDDhhmmssim_/url
        re.compile(r'/web/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})[a-z_]+/'),
        # Just date: /web/YYYYMMDD/url
        re.compile(r'/web/(\d{4})(\d{2})(\d{2})/'),
    ]
    
    # Archive.org item metadata patterns
    ITEM_DATE_PATTERNS = [
        # publicdate field: "2024-01-15 12:34:56"
        re.compile(r'publicdate["\s:]+(\d{4})-(\d{2})-(\d{2})'),
        # date field: "2024-01-15"
        re.compile(r'date["\s:]+(\d{4})-(\d{2})-(\d{2})'),
        # addeddate field
        re.compile(r'addeddate["\s:]+(\d{4})-(\d{2})-(\d{2})'),
    ]
    
    @classmethod
    def parse_wayback_url(cls, url: str) -> Optional[Dict[str, any]]:
        """
        Parse date from Wayback Machine URL.
        
        Args:
            url: Archive.org Wayback Machine URL
            
        Returns:
            Dict with parsed date info or None if not found
        """
        for pattern in cls.WAYBACK_PATTERNS:
            match = pattern.search(url)
            if match:
                groups = match.groups()
                
                # Extract components
                year = int(groups[0])
                month = int(groups[1])
                day = int(groups[2])
                
                # Time components (if available)
                hour = int(groups[3]) if len(groups) > 3 else 0
                minute = int(groups[4]) if len(groups) > 4 else 0
                second = int(groups[5]) if len(groups) > 5 else 0
                
                try:
                    # Create datetime object
                    archive_date = datetime(year, month, day, hour, minute, second)
                    
                    return {
                        'year': year,
                        'month': month,
                        'day': day,
                        'hour': hour,
                        'minute': minute,
                        'second': second,
                        'datetime': archive_date,
                        'timestamp': archive_date.timestamp(),
                        'iso_date': archive_date.strftime('%Y-%m-%d'),
                        'full_iso': archive_date.isoformat(),
                        'confidence': 0.95,  # Very high confidence for Wayback URLs
                        'source': 'wayback_url',
                        'pattern_type': 'wayback_timestamp',
                        'raw_match': match.group(0)
                    }
                except ValueError as e:
                    logger.warning(f"Invalid date components in Wayback URL: {e}")
                    return None
        
        return None
    
    @classmethod
    def extract_original_url_date_hint(cls, wayback_url: str) -> Optional[Tuple[int, int]]:
        """
        Extract the archive date to use as a hint for content date.
        Content must have been created before the archive date.
        
        Args:
            wayback_url: Wayback Machine URL
            
        Returns:
            Tuple of (year, month) representing the latest possible content date
        """
        date_info = cls.parse_wayback_url(wayback_url)
        if date_info:
            return (date_info['year'], date_info['month'])
        return None
    
    @classmethod
    def parse_archive_item_page(cls, content: str) -> Optional[Dict[str, any]]:
        """
        Parse dates from Archive.org item/details page content.
        
        Args:
            content: HTML or text content from Archive.org item page
            
        Returns:
            Dict with parsed date info or None if not found
        """
        for pattern in cls.ITEM_DATE_PATTERNS:
            match = pattern.search(content)
            if match:
                try:
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                    
                    archive_date = datetime(year, month, day)
                    
                    return {
                        'year': year,
                        'month': month,
                        'day': day,
                        'datetime': archive_date,
                        'iso_date': archive_date.strftime('%Y-%m-%d'),
                        'confidence': 0.90,  # High confidence for metadata
                        'source': 'archive_metadata',
                        'pattern_type': 'item_metadata'
                    }
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing Archive.org item date: {e}")
                    continue
        
        return None
    
    @classmethod
    def infer_content_date_range(cls, archive_url: str, 
                                title: str = '', 
                                snippet: str = '') -> Optional[Dict[str, any]]:
        """
        Infer the likely date range of the original content based on archive date.
        
        Args:
            archive_url: Archive.org URL
            title: Content title
            snippet: Content snippet
            
        Returns:
            Dict with inferred date range info
        """
        # First, get the archive date
        archive_date_info = cls.parse_wayback_url(archive_url)
        if not archive_date_info:
            return None
        
        archive_date = archive_date_info['datetime']
        
        # Look for year mentions in title/snippet that are before archive date
        year_pattern = re.compile(r'\b(19\d{2}|20\d{2})\b')
        
        mentioned_years = []
        for text in [title, snippet]:
            if text:
                years = year_pattern.findall(text)
                for year_str in years:
                    year = int(year_str)
                    if year <= archive_date.year:
                        mentioned_years.append(year)
        
        if mentioned_years:
            # Use the most recent year mentioned that's before archive date
            content_year = max(mentioned_years)
            
            return {
                'inferred_year': content_year,
                'archive_year': archive_date.year,
                'confidence': 0.70,  # Moderate confidence for inferred dates
                'source': 'content_inference',
                'note': f'Content likely from {content_year} or earlier (archived {archive_date.year})'
            }
        else:
            # No specific year found, just indicate it's before archive date
            return {
                'latest_possible_year': archive_date.year,
                'latest_possible_month': archive_date.month,
                'confidence': 0.60,
                'source': 'archive_constraint',
                'note': f'Content created before {archive_date.strftime("%B %Y")}'
            }
    
    @classmethod
    def get_comprehensive_date_info(cls, url: str, 
                                   title: str = '', 
                                   snippet: str = '') -> Dict[str, any]:
        """
        Get all available date information from an Archive.org URL.
        
        Args:
            url: Archive.org URL
            title: Content title
            snippet: Content snippet
            
        Returns:
            Comprehensive dict with all extracted date information
        """
        result = {
            'is_archive_url': 'archive.org' in url.lower(),
            'archive_date': None,
            'content_date_range': None,
            'dates_found': []
        }
        
        if not result['is_archive_url']:
            return result
        
        # Parse archive date
        archive_date = cls.parse_wayback_url(url)
        if archive_date:
            result['archive_date'] = archive_date
            result['dates_found'].append({
                'type': 'archive_date',
                'date': archive_date['iso_date'],
                'confidence': archive_date['confidence']
            })
        
        # Infer content date range
        content_range = cls.infer_content_date_range(url, title, snippet)
        if content_range:
            result['content_date_range'] = content_range
            
        return result


# Convenience functions
def parse_archive_date(url: str) -> Optional[Dict[str, any]]:
    """Parse date from Archive.org URL."""
    return ArchiveDateParser.parse_wayback_url(url)


def get_archive_date_info(url: str, title: str = '', snippet: str = '') -> Dict[str, any]:
    """Get comprehensive date info for Archive.org content."""
    return ArchiveDateParser.get_comprehensive_date_info(url, title, snippet)