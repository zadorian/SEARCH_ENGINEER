"""
Stub categorizer when full categorization module is not available.
Provides fallback implementations for basic URL categorization.
"""
import re
from urllib.parse import urlparse
from typing import Dict, List, Any, Optional


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return ""


def categorize_url_basic(url: str, title: str = "", description: str = "") -> Dict[str, Any]:
    """
    Basic URL categorization based on domain patterns and content.
    Returns category, subcategory, filetype, and country.
    """
    result = {
        "category": "miscellaneous",
        "subcategory": None,
        "filetype": None,
        "country": None
    }
    
    try:
        domain = extract_domain(url)
        text = f"{title} {description}".lower()
        
        # Detect filetype from URL
        url_lower = url.lower()
        if url_lower.endswith('.pdf'):
            result["filetype"] = "pdf"
        elif url_lower.endswith(('.doc', '.docx')):
            result["filetype"] = "document"
        elif url_lower.endswith(('.xls', '.xlsx', '.csv')):
            result["filetype"] = "spreadsheet"
        
        # Basic category detection from domain
        if any(x in domain for x in ['news', 'bbc', 'cnn', 'reuters', 'guardian', 'times', 'post']):
            result["category"] = "news"
        elif any(x in domain for x in ['gov', 'government', 'ministry']):
            result["category"] = "government"
        elif any(x in domain for x in ['linkedin', 'facebook', 'twitter', 'instagram']):
            result["category"] = "social_media"
        elif any(x in domain for x in ['court', 'judiciary', 'justice']):
            result["category"] = "legal"
        elif any(x in domain for x in ['company', 'corp', 'business', 'inc']):
            result["category"] = "corporate"
        elif any(x in domain for x in ['edu', 'university', 'academic', 'school']):
            result["category"] = "academic"
        elif any(x in domain for x in ['wiki']):
            result["category"] = "reference"
        
        # Country detection from TLD
        tld = domain.split('.')[-1] if domain else ""
        country_tlds = {
            'uk': 'GB', 'de': 'DE', 'fr': 'FR', 'it': 'IT', 'es': 'ES',
            'nl': 'NL', 'be': 'BE', 'at': 'AT', 'ch': 'CH', 'pl': 'PL',
            'hu': 'HU', 'cz': 'CZ', 'sk': 'SK', 'hr': 'HR', 'si': 'SI',
            'ro': 'RO', 'bg': 'BG', 'gr': 'GR', 'pt': 'PT', 'ie': 'IE',
            'dk': 'DK', 'se': 'SE', 'no': 'NO', 'fi': 'FI', 'ee': 'EE',
            'lv': 'LV', 'lt': 'LT', 'ru': 'RU', 'ua': 'UA', 'rs': 'RS',
            'jp': 'JP', 'cn': 'CN', 'kr': 'KR', 'au': 'AU', 'nz': 'NZ',
            'ca': 'CA', 'mx': 'MX', 'br': 'BR', 'ar': 'AR', 'in': 'IN'
        }
        if tld in country_tlds:
            result["country"] = country_tlds[tld]
        
    except Exception as e:
        pass
    
    return result


async def categorize_results(results: List[Dict[str, Any]], query: str = "") -> List[Dict[str, Any]]:
    """
    Categorize a list of search results.
    Returns list with category information added.
    """
    categorized = []
    for item in results:
        url = item.get('url', '')
        title = item.get('title', '')
        description = item.get('description', item.get('snippet', ''))
        
        cat_info = categorize_url_basic(url, title, description)
        
        categorized.append({
            **item,
            'category': cat_info.get('category', 'miscellaneous'),
            'subcategory': cat_info.get('subcategory'),
            'filetype': cat_info.get('filetype'),
            'country': cat_info.get('country')
        })
    
    return categorized
