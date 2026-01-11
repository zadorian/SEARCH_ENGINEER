#!/usr/bin/env python3
"""
Comprehensive News Bangs System - ALL 880+ News Sources
======================================================

Complete DuckDuckGo news bangs database with comprehensive country/language indexing,
advanced categorization, and intelligent targeting for global news coverage.

Extracted from comprehensive bangs database with:
- 880+ news sources covering 735+ unique domains
- 50+ countries with proper ISO 3166-1 alpha-2 codes
- 30+ languages with ISO 639-1 codes
- Advanced categorization and regional targeting
- Intelligent bang selection with confidence scoring

Features:
- Complete global news coverage
- Country/language targeting
- Category-based filtering
- Regional focus optimization
- Multi-language support
- Intelligent bang selection
- Legacy compatibility

Usage:
    from brute.infrastructure.news_bangs import ComprehensiveNewsBangs
    
    searcher = ComprehensiveNewsBangs()
    results = searcher.search_news("climate change", country="DE", language="de")
"""

import json
import re
import sys
import argparse
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote_plus
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict

@dataclass
class NewsBang:
    """Enhanced news bang with comprehensive metadata"""
    bang: str
    name: str
    country: str  # ISO 3166-1 alpha-2 code
    language: str  # ISO 639-1 code
    domain: str
    category: str
    url: str
    subcategory: str = ""
    regional_focus: str = ""
    description: str = ""

class ComprehensiveNewsBangs:
    """Comprehensive News Bangs System with ALL 880+ news sources"""
    
    def __init__(self):
        self.bangs = self._initialize_all_bangs()
        self.country_lookup = self._build_country_lookup()
        self.language_lookup = self._build_language_lookup()
        self.category_lookup = self._build_category_lookup()
        self.domain_lookup = self._build_domain_lookup()
        self.country_to_language = self._build_country_language_mapping()
        
        # Legacy compatibility
        self.ALL_NEWS_BANGS = [bang.bang for bang in self.bangs.values()]
        self.PRIORITY_NEWS_BANGS = self._get_priority_bangs()
    
    def _initialize_all_bangs(self) -> Dict[str, NewsBang]:
        """Initialize ALL 880+ news bangs from comprehensive database"""
        bangs = {}
        
        # Load comprehensive news bangs data
        comprehensive_data = self._load_comprehensive_data()
        
        for item in comprehensive_data:
            bang_id = item['bang']
            if bang_id and bang_id not in bangs:  # Avoid duplicates
                bangs[bang_id] = NewsBang(
                    bang=bang_id,
                    name=item['name'],
                    country=item['country'],
                    language=item['language'],
                    domain=item['domain'],
                    category=item['category'],
                    url=item['url'],
                    subcategory=item.get('subcategory', ''),
                    regional_focus=self._determine_regional_focus(item['country']),
                    description=f"{item['name']} - {item['country']} news source"
                )
        
        return bangs
    
    def _load_comprehensive_data(self) -> List[Dict]:
        """Load comprehensive news bangs data from all_bangs.json"""
        try:
            # Try to load from saved file first
            try:
                with open('comprehensive_news_bangs.json', 'r') as f:
                    return json.load(f)
            except FileNotFoundError:
                pass
            
            # Load from all_bangs.json
            with open('all_bangs.json', 'r') as f:
                data = json.load(f)
            
            # Extract all news-related bangs
            news_bangs = []
            for item in data:
                # Check if category is News or subcategory contains newspaper/news
                if (item.get('c') == 'News' or 
                    (item.get('sc') and ('newspaper' in item.get('sc', '').lower() or 'news' in item.get('sc', '').lower())) or
                    ('news' in item.get('s', '').lower() and 'newsletter' not in item.get('s', '').lower())):
                    
                    domain = item.get('d', '')
                    country = self._get_country_from_domain(domain)
                    language = self._get_language_from_country(country)
                    category = self._determine_category(item)
                    
                    news_bangs.append({
                        'bang': item.get('t', ''),
                        'name': item.get('s', ''),
                        'domain': domain,
                        'country': country,
                        'language': language,
                        'category': category,
                        'url': item.get('u', ''),
                        'subcategory': item.get('sc', '')
                    })
            
            return news_bangs
            
        except Exception as e:
            print(f"Error loading comprehensive data: {e}")
            return self._get_fallback_data()
    
    def _get_country_from_domain(self, domain: str) -> str:
        """Determine country from domain"""
        domain = domain.lower()
        
        # Common TLD mappings
        tld_map = {
            '.uk': 'UK', '.co.uk': 'UK', '.org.uk': 'UK',
            '.de': 'DE', '.fr': 'FR', '.it': 'IT', '.es': 'ES',
            '.nl': 'NL', '.be': 'BE', '.at': 'AT', '.ch': 'CH',
            '.se': 'SE', '.no': 'NO', '.dk': 'DK', '.fi': 'FI',
            '.pl': 'PL', '.cz': 'CZ', '.sk': 'SK', '.hu': 'HU',
            '.ru': 'RU', '.ua': 'UA', '.by': 'BY',
            '.jp': 'JP', '.cn': 'CN', '.kr': 'KR', '.tw': 'TW',
            '.in': 'IN', '.au': 'AU', '.nz': 'NZ', '.za': 'ZA',
            '.ca': 'CA', '.mx': 'MX', '.br': 'BR', '.ar': 'AR',
            '.cl': 'CL', '.co': 'CO', '.pe': 'PE', '.ve': 'VE',
            '.tr': 'TR', '.il': 'IL', '.sa': 'SA', '.ae': 'AE',
            '.eg': 'EG', '.ma': 'MA', '.tn': 'TN', '.dz': 'DZ',
            '.ng': 'NG', '.ke': 'KE', '.gh': 'GH', '.tz': 'TZ',
            '.th': 'TH', '.my': 'MY', '.sg': 'SG', '.id': 'ID',
            '.ph': 'PH', '.vn': 'VN', '.bd': 'BD', '.pk': 'PK',
            '.lk': 'LK', '.mm': 'MM', '.kh': 'KH', '.la': 'LA',
            '.hk': 'HK', '.mo': 'MO', '.is': 'IS', '.ie': 'IE',
            '.pt': 'PT', '.gr': 'GR', '.ro': 'RO', '.bg': 'BG',
            '.hr': 'HR', '.rs': 'RS', '.si': 'SI', '.mk': 'MK',
            '.al': 'AL', '.ba': 'BA', '.me': 'ME', '.lt': 'LT',
            '.lv': 'LV', '.ee': 'EE', '.mt': 'MT', '.cy': 'CY'
        }
        
        # Check TLD
        for tld, country in tld_map.items():
            if domain.endswith(tld):
                return country
        
        # Known domain mappings
        domain_map = {
            'bbc.co.uk': 'UK', 'bbc.com': 'UK', 'theguardian.com': 'UK',
            'telegraph.co.uk': 'UK', 'independent.co.uk': 'UK', 'dailymail.co.uk': 'UK',
            'ft.com': 'UK', 'economist.com': 'UK', 'reuters.com': 'UK',
            'cnn.com': 'US', 'nytimes.com': 'US', 'washingtonpost.com': 'US',
            'wsj.com': 'US', 'usatoday.com': 'US', 'nypost.com': 'US',
            'latimes.com': 'US', 'chicagotribune.com': 'US', 'bostonglobe.com': 'US',
            'bloomberg.com': 'US', 'forbes.com': 'US', 'businessinsider.com': 'US',
            'techcrunch.com': 'US', 'theverge.com': 'US', 'wired.com': 'US',
            'lemonde.fr': 'FR', 'lefigaro.fr': 'FR', 'liberation.fr': 'FR',
            'spiegel.de': 'DE', 'zeit.de': 'DE', 'tagesschau.de': 'DE',
            'corriere.it': 'IT', 'repubblica.it': 'IT', 'lastampa.it': 'IT',
            'elpais.com': 'ES', 'elmundo.es': 'ES', 'abc.es': 'ES',
            'asahi.com': 'JP', 'mainichi.jp': 'JP', 'nikkei.com': 'JP',
            'timesofindia.indiatimes.com': 'IN', 'thehindu.com': 'IN',
            'scmp.com': 'HK', 'straitstimes.com': 'SG',
            'smh.com.au': 'AU', 'abc.net.au': 'AU',
            'globo.com': 'BR', 'folha.uol.com.br': 'BR',
            'clarin.com': 'AR', 'lanacion.com.ar': 'AR',
            'dawn.com': 'PK', 'arabnews.com': 'SA', 'aljazeera.com': 'QA',
            'cbc.ca': 'CA', 'globeandmail.com': 'CA'
        }
        
        if domain in domain_map:
            return domain_map[domain]
        
        # Default to US for .com, .org, .net without country indicators
        if domain.endswith('.com') or domain.endswith('.org') or domain.endswith('.net'):
            return 'US'
        
        return 'US'  # Default fallback
    
    def _get_language_from_country(self, country: str) -> str:
        """Get primary language for country"""
        country_to_lang = {
            'US': 'en', 'UK': 'en', 'CA': 'en', 'AU': 'en', 'NZ': 'en', 'IE': 'en',
            'ZA': 'en', 'IN': 'en', 'SG': 'en', 'HK': 'en', 'PH': 'en', 'MY': 'en',
            'DE': 'de', 'AT': 'de', 'CH': 'de',
            'FR': 'fr', 'BE': 'fr', 'LU': 'fr', 'MC': 'fr',
            'ES': 'es', 'MX': 'es', 'AR': 'es', 'CO': 'es', 'PE': 'es', 'CL': 'es',
            'IT': 'it', 'SM': 'it', 'VA': 'it',
            'PT': 'pt', 'BR': 'pt',
            'NL': 'nl', 'SR': 'nl',
            'RU': 'ru', 'BY': 'ru', 'KZ': 'ru',
            'CN': 'zh', 'TW': 'zh',
            'JP': 'ja', 'KR': 'ko', 'NO': 'no', 'SE': 'sv', 'DK': 'da',
            'FI': 'fi', 'PL': 'pl', 'CZ': 'cs', 'SK': 'sk', 'HU': 'hu',
            'RO': 'ro', 'BG': 'bg', 'HR': 'hr', 'RS': 'sr', 'SI': 'sl',
            'EE': 'et', 'LV': 'lv', 'LT': 'lt', 'GR': 'el', 'TR': 'tr',
            'SA': 'ar', 'AE': 'ar', 'QA': 'ar', 'KW': 'ar', 'IL': 'he',
            'TH': 'th', 'VN': 'vi', 'ID': 'id', 'BD': 'bn', 'PK': 'ur',
            'LK': 'ta', 'IR': 'fa'
        }
        return country_to_lang.get(country, 'en')
    
    def _determine_category(self, item: Dict) -> str:
        """Determine category from item data"""
        subcategory = item.get('sc', '').lower()
        name = item.get('s', '').lower()
        
        if 'newspaper' in subcategory:
            return 'newspaper'
        elif 'business' in name or 'financial' in name or 'economic' in name:
            return 'business'
        elif 'tech' in name or 'technology' in name:
            return 'technology'
        elif 'sport' in name or 'sports' in name:
            return 'sports'
        elif 'weather' in name or 'meteo' in name:
            return 'weather'
        elif 'local' in name or 'regional' in name:
            return 'local'
        elif 'international' in subcategory:
            return 'international'
        else:
            return 'general'
    
    def _determine_regional_focus(self, country: str) -> str:
        """Determine regional focus from country"""
        region_map = {
            'US': 'north_america', 'CA': 'north_america', 'MX': 'north_america',
            'UK': 'europe', 'DE': 'europe', 'FR': 'europe', 'IT': 'europe', 'ES': 'europe',
            'NL': 'europe', 'BE': 'europe', 'AT': 'europe', 'CH': 'europe',
            'SE': 'europe', 'NO': 'europe', 'DK': 'europe', 'FI': 'europe',
            'PL': 'europe', 'CZ': 'europe', 'SK': 'europe', 'HU': 'europe',
            'RO': 'europe', 'BG': 'europe', 'HR': 'europe', 'RS': 'europe',
            'SI': 'europe', 'EE': 'europe', 'LV': 'europe', 'LT': 'europe',
            'IE': 'europe', 'GR': 'europe', 'PT': 'europe', 'RU': 'europe',
            'JP': 'asia', 'CN': 'asia', 'KR': 'asia', 'IN': 'asia', 'SG': 'asia',
            'MY': 'asia', 'TH': 'asia', 'ID': 'asia', 'PH': 'asia', 'VN': 'asia',
            'HK': 'asia', 'TW': 'asia', 'BD': 'asia', 'PK': 'asia', 'LK': 'asia',
            'AU': 'oceania', 'NZ': 'oceania',
            'BR': 'south_america', 'AR': 'south_america', 'CL': 'south_america',
            'CO': 'south_america', 'PE': 'south_america', 'VE': 'south_america',
            'ZA': 'africa', 'NG': 'africa', 'KE': 'africa', 'GH': 'africa',
            'EG': 'africa', 'MA': 'africa', 'TN': 'africa',
            'SA': 'middle_east', 'AE': 'middle_east', 'QA': 'middle_east',
            'IL': 'middle_east', 'TR': 'middle_east', 'IR': 'middle_east'
        }
        return region_map.get(country, 'global')
    
    def _get_fallback_data(self) -> List[Dict]:
        """Fallback data in case of loading issues"""
        return [
            {'bang': 'bbc', 'name': 'BBC', 'domain': 'bbc.co.uk', 'country': 'UK', 'language': 'en', 'category': 'general', 'url': 'https://www.bbc.co.uk/search?q={{{s}}}', 'subcategory': ''},
            {'bang': 'cnn', 'name': 'CNN', 'domain': 'cnn.com', 'country': 'US', 'language': 'en', 'category': 'general', 'url': 'https://www.cnn.com/search?q={{{s}}}', 'subcategory': ''},
            {'bang': 'nyt', 'name': 'New York Times', 'domain': 'nytimes.com', 'country': 'US', 'language': 'en', 'category': 'newspaper', 'url': 'https://www.nytimes.com/search?query={{{s}}}', 'subcategory': ''},
            {'bang': 'reuters', 'name': 'Reuters', 'domain': 'reuters.com', 'country': 'UK', 'language': 'en', 'category': 'international', 'url': 'https://www.reuters.com/search/news?blob={{{s}}}', 'subcategory': ''},
            {'bang': 'guardian', 'name': 'The Guardian', 'domain': 'theguardian.com', 'country': 'UK', 'language': 'en', 'category': 'newspaper', 'url': 'https://www.theguardian.com/search?q={{{s}}}', 'subcategory': ''}
        ]
    
    def _build_country_lookup(self) -> Dict[str, List[str]]:
        """Build lookup dictionary for bangs by country"""
        lookup = defaultdict(list)
        for bang_name, bang in self.bangs.items():
            lookup[bang.country].append(bang_name)
        return dict(lookup)
    
    def _build_language_lookup(self) -> Dict[str, List[str]]:
        """Build lookup dictionary for bangs by language"""
        lookup = defaultdict(list)
        for bang_name, bang in self.bangs.items():
            lookup[bang.language].append(bang_name)
        return dict(lookup)
    
    def _build_category_lookup(self) -> Dict[str, List[str]]:
        """Build lookup dictionary for bangs by category"""
        lookup = defaultdict(list)
        for bang_name, bang in self.bangs.items():
            lookup[bang.category].append(bang_name)
        return dict(lookup)
    
    def _build_domain_lookup(self) -> Dict[str, List[str]]:
        """Build lookup dictionary for bangs by domain"""
        lookup = defaultdict(list)
        for bang_name, bang in self.bangs.items():
            lookup[bang.domain].append(bang_name)
        return dict(lookup)
    
    def _build_country_language_mapping(self) -> Dict[str, str]:
        """Build country to language mapping"""
        return {
            'US': 'en', 'UK': 'en', 'CA': 'en', 'AU': 'en', 'NZ': 'en', 'IE': 'en',
            'ZA': 'en', 'IN': 'en', 'SG': 'en', 'HK': 'en', 'PH': 'en', 'MY': 'en',
            'DE': 'de', 'AT': 'de', 'CH': 'de',
            'FR': 'fr', 'BE': 'fr', 'LU': 'fr', 'MC': 'fr',
            'ES': 'es', 'MX': 'es', 'AR': 'es', 'CO': 'es', 'PE': 'es', 'CL': 'es',
            'IT': 'it', 'SM': 'it', 'VA': 'it',
            'PT': 'pt', 'BR': 'pt',
            'NL': 'nl', 'SR': 'nl',
            'RU': 'ru', 'BY': 'ru', 'KZ': 'ru',
            'CN': 'zh', 'TW': 'zh',
            'JP': 'ja', 'KR': 'ko', 'NO': 'no', 'SE': 'sv', 'DK': 'da',
            'FI': 'fi', 'PL': 'pl', 'CZ': 'cs', 'SK': 'sk', 'HU': 'hu',
            'RO': 'ro', 'BG': 'bg', 'HR': 'hr', 'RS': 'sr', 'SI': 'sl',
            'EE': 'et', 'LV': 'lv', 'LT': 'lt', 'GR': 'el', 'TR': 'tr',
            'SA': 'ar', 'AE': 'ar', 'QA': 'ar', 'KW': 'ar', 'IL': 'he',
            'TH': 'th', 'VN': 'vi', 'ID': 'id', 'BD': 'bn', 'PK': 'ur',
            'LK': 'ta', 'IR': 'fa'
        }
    
    def _get_priority_bangs(self) -> List[str]:
        """Get priority bangs for most important news sources"""
        priority_domains = [
            'bbc.co.uk', 'cnn.com', 'nytimes.com', 'washingtonpost.com',
            'reuters.com', 'theguardian.com', 'wsj.com', 'bloomberg.com',
            'ap.com', 'apnews.com', 'ft.com', 'economist.com',
            'lemonde.fr', 'spiegel.de', 'corriere.it', 'elpais.com',
            'asahi.com', 'timesofindia.indiatimes.com', 'scmp.com',
            'smh.com.au', 'globo.com', 'clarin.com', 'aljazeera.com'
        ]
        
        priority_bangs = []
        for bang_name, bang in self.bangs.items():
            if bang.domain in priority_domains:
                priority_bangs.append(bang_name)
        
        return priority_bangs
    
    def get_bangs_by_country(self, country: str) -> List[str]:
        """Get bangs for specific country"""
        country_upper = country.upper()
        return self.country_lookup.get(country_upper, [])
    
    def get_bangs_by_language(self, language: str) -> List[str]:
        """Get bangs for specific language"""
        language_lower = language.lower()
        return self.language_lookup.get(language_lower, [])
    
    def get_bangs_by_category(self, category: str) -> List[str]:
        """Get bangs for specific category"""
        return self.category_lookup.get(category, [])
    
    def get_bangs_by_domain(self, domain: str) -> List[str]:
        """Get bangs for specific domain"""
        return self.domain_lookup.get(domain, [])
    
    def filter_bangs(self, country: str = None, language: str = None, 
                    category: str = None, regional_focus: str = None) -> List[str]:
        """Filter bangs by multiple criteria"""
        result_bangs = set(self.bangs.keys())
        
        if country:
            country_bangs = set(self.get_bangs_by_country(country))
            result_bangs = result_bangs.intersection(country_bangs)
        
        if language:
            language_bangs = set(self.get_bangs_by_language(language))
            result_bangs = result_bangs.intersection(language_bangs)
        
        if category:
            category_bangs = set(self.get_bangs_by_category(category))
            result_bangs = result_bangs.intersection(category_bangs)
        
        if regional_focus:
            regional_bangs = set(bang for bang, data in self.bangs.items() 
                               if data.regional_focus == regional_focus)
            result_bangs = result_bangs.intersection(regional_bangs)
        
        return list(result_bangs)
    
    def get_language_from_country(self, country: str) -> str:
        """Get primary language for country"""
        return self.country_to_language.get(country.upper(), "en")
    
    def intelligent_bang_selection(self, query: str, country: str = None, 
                                 language: str = None, category: str = None,
                                 max_results: int = 20) -> List[Tuple[str, float]]:
        """Intelligent bang selection with confidence scoring"""
        scored_bangs = []
        query_lower = query.lower()
        
        # Base scoring
        base_score = 0.5
        
        # Apply filters if specified
        if country or language or category:
            filtered_bangs = self.filter_bangs(country, language, category)
            if filtered_bangs:
                for bang in filtered_bangs:
                    scored_bangs.append((bang, base_score + 0.4))
            else:
                # No matches, use broader search
                for bang_name, bang in self.bangs.items():
                    score = base_score
                    
                    # Country match
                    if country and bang.country == country.upper():
                        score += 0.3
                    
                    # Language match
                    if language and bang.language == language.lower():
                        score += 0.2
                    
                    # Category match
                    if category and bang.category == category:
                        score += 0.2
                    
                    scored_bangs.append((bang_name, score))
        else:
            # No filters, score all bangs
            for bang_name, bang in self.bangs.items():
                score = base_score
                
                # Priority bang bonus
                if bang_name in self.PRIORITY_NEWS_BANGS:
                    score += 0.3
                
                # Major language bonus
                if bang.language in ['en', 'es', 'fr', 'de', 'zh', 'ja', 'ar']:
                    score += 0.1
                
                # Query relevance
                if any(word in bang.name.lower() for word in query_lower.split()):
                    score += 0.2
                
                scored_bangs.append((bang_name, score))
        
        # Sort by score and return top results
        scored_bangs.sort(key=lambda x: x[1], reverse=True)
        return scored_bangs[:max_results]
    
    def search_news(self, query: str, country: str = None, language: str = None,
                   category: str = None, max_results: int = 20) -> Dict[str, any]:
        """Main search interface for news bangs"""
        
        # Auto-detect language from country if not specified
        if country and not language:
            language = self.get_language_from_country(country)
        
        # Get intelligent bang selection
        selected_bangs = self.intelligent_bang_selection(
            query, country, language, category, max_results
        )
        
        # Generate URLs
        urls = {}
        encoded_query = quote_plus(query)
        
        for bang_name, score in selected_bangs:
            if bang_name in self.bangs:
                bang = self.bangs[bang_name]
                # Replace {{{s}}} with actual query
                url = bang.url.replace('{{{s}}}', encoded_query)
                urls[bang_name] = {
                    'url': url,
                    'name': bang.name,
                    'country': bang.country,
                    'language': bang.language,
                    'domain': bang.domain,
                    'category': bang.category,
                    'score': score,
                    'regional_focus': bang.regional_focus,
                    'description': bang.description
                }
        
        # Generate statistics
        stats = self._generate_statistics(urls)
        
        return {
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'total_bangs': len(urls),
            'filters_applied': {
                'country': country,
                'language': language,
                'category': category
            },
            'bangs': urls,
            'statistics': stats,
            'suggestions': self._generate_suggestions(urls)
        }
    
    def _generate_statistics(self, urls: Dict[str, Dict]) -> Dict[str, any]:
        """Generate statistics about search results"""
        stats = {
            'by_country': defaultdict(int),
            'by_language': defaultdict(int),
            'by_category': defaultdict(int),
            'by_regional_focus': defaultdict(int)
        }
        
        for bang_data in urls.values():
            stats['by_country'][bang_data['country']] += 1
            stats['by_language'][bang_data['language']] += 1
            stats['by_category'][bang_data['category']] += 1
            stats['by_regional_focus'][bang_data['regional_focus']] += 1
        
        # Convert to regular dicts
        for key in stats:
            stats[key] = dict(stats[key])
        
        return stats
    
    def _generate_suggestions(self, urls: Dict[str, Dict]) -> Dict[str, any]:
        """Generate suggestions based on search results"""
        countries = set(data['country'] for data in urls.values())
        languages = set(data['language'] for data in urls.values())
        categories = set(data['category'] for data in urls.values())
        
        return {
            'countries_covered': sorted(countries),
            'languages_covered': sorted(languages),
            'categories_covered': sorted(categories),
            'priority_sources': [name for name, data in urls.items() 
                               if name in self.PRIORITY_NEWS_BANGS],
            'regional_distribution': self._group_by_region(urls)
        }
    
    def _group_by_region(self, urls: Dict[str, Dict]) -> Dict[str, List[str]]:
        """Group bangs by region"""
        regions = defaultdict(list)
        for bang_name, data in urls.items():
            regions[data['regional_focus']].append(bang_name)
        return dict(regions)
    
    def get_available_countries(self) -> List[str]:
        """Get list of available countries"""
        return sorted(self.country_lookup.keys())
    
    def get_available_languages(self) -> List[str]:
        """Get list of available languages"""
        return sorted(self.language_lookup.keys())
    
    def get_available_categories(self) -> List[str]:
        """Get list of available categories"""
        return sorted(self.category_lookup.keys())
    
    def get_bang_info(self, bang_name: str) -> Optional[Dict[str, any]]:
        """Get detailed information about a specific bang"""
        if bang_name not in self.bangs:
            return None
        
        bang = self.bangs[bang_name]
        return {
            'bang': bang.bang,
            'name': bang.name,
            'country': bang.country,
            'language': bang.language,
            'domain': bang.domain,
            'category': bang.category,
            'url': bang.url,
            'subcategory': bang.subcategory,
            'regional_focus': bang.regional_focus,
            'description': bang.description
        }
    
    def get_system_stats(self) -> Dict[str, any]:
        """Get comprehensive system statistics"""
        return {
            'total_bangs': len(self.bangs),
            'countries_covered': len(self.country_lookup),
            'languages_supported': len(self.language_lookup),
            'categories_available': len(self.category_lookup),
            'priority_bangs': len(self.PRIORITY_NEWS_BANGS),
            'domains_covered': len(self.domain_lookup),
            'top_countries': sorted([(country, len(bangs)) for country, bangs in self.country_lookup.items()], 
                                  key=lambda x: x[1], reverse=True)[:10],
            'top_languages': sorted([(lang, len(bangs)) for lang, bangs in self.language_lookup.items()], 
                                  key=lambda x: x[1], reverse=True)[:10],
            'category_distribution': {cat: len(bangs) for cat, bangs in self.category_lookup.items()}
        }

# Legacy compatibility exports
def create_news_bangs_system():
    """Create the comprehensive news bangs system"""
    return ComprehensiveNewsBangs()

# Initialize the system
_news_system = None

def get_news_bangs_system():
    """Get or create the news bangs system"""
    global _news_system
    if _news_system is None:
        _news_system = ComprehensiveNewsBangs()
    return _news_system

# Legacy compatibility functions
def get_news_bangs_by_country(country_code: str) -> List[str]:
    """Get news bangs for a specific country"""
    system = get_news_bangs_system()
    return system.get_bangs_by_country(country_code)

def get_news_bangs_by_language(language_code: str) -> List[str]:
    """Get news bangs for a specific language"""
    system = get_news_bangs_system()
    return system.get_bangs_by_language(language_code)

def get_news_bangs_by_category(category: str) -> List[str]:
    """Get news bangs for a specific category"""
    system = get_news_bangs_system()
    return system.get_bangs_by_category(category)

# Legacy compatibility exports
ALL_NEWS_BANGS = []
PRIORITY_NEWS_BANGS = []
NEWS_BANGS_BY_COUNTRY = {}
NEWS_BANGS_BY_LANGUAGE = {}
NEWS_BANGS_BY_CATEGORY = {}

def _initialize_legacy_exports():
    """Initialize legacy exports"""
    global ALL_NEWS_BANGS, PRIORITY_NEWS_BANGS, NEWS_BANGS_BY_COUNTRY
    global NEWS_BANGS_BY_LANGUAGE, NEWS_BANGS_BY_CATEGORY
    
    system = get_news_bangs_system()
    ALL_NEWS_BANGS = system.ALL_NEWS_BANGS
    PRIORITY_NEWS_BANGS = system.PRIORITY_NEWS_BANGS
    NEWS_BANGS_BY_COUNTRY = system.country_lookup
    NEWS_BANGS_BY_LANGUAGE = system.language_lookup
    NEWS_BANGS_BY_CATEGORY = system.category_lookup

# Command line interface
def main():
    """Command-line interface for comprehensive news search"""
    parser = argparse.ArgumentParser(
        description='Comprehensive news search with 880+ sources across 50+ countries',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 news_bangs.py "climate change"
  python3 news_bangs.py "election results" --country US
  python3 news_bangs.py "technology news" --language de --country DE
  python3 news_bangs.py "sports" --category sports --max-results 10
  python3 news_bangs.py --list-countries
  python3 news_bangs.py --stats
        """
    )
    
    parser.add_argument('query', nargs='?', help='News search query')
    parser.add_argument('--country', '-c', help='Filter by country (ISO 3166-1 alpha-2)')
    parser.add_argument('--language', '-l', help='Filter by language (ISO 639-1)')
    parser.add_argument('--category', help='Filter by category')
    parser.add_argument('--max-results', '-m', type=int, default=20, help='Maximum results')
    parser.add_argument('--list-countries', action='store_true', help='List available countries')
    parser.add_argument('--list-languages', action='store_true', help='List available languages')
    parser.add_argument('--list-categories', action='store_true', help='List available categories')
    parser.add_argument('--stats', action='store_true', help='Show system statistics')
    parser.add_argument('--bang-info', help='Get info about specific bang')
    
    args = parser.parse_args()
    
    # Initialize system
    system = ComprehensiveNewsBangs()
    
    # Handle list commands
    if args.list_countries:
        countries = system.get_available_countries()
        print(f"Available countries ({len(countries)}):")
        for country in countries:
            count = len(system.get_bangs_by_country(country))
            print(f"  {country}: {count} sources")
        return
    
    if args.list_languages:
        languages = system.get_available_languages()
        print(f"Available languages ({len(languages)}):")
        for language in languages:
            count = len(system.get_bangs_by_language(language))
            print(f"  {language}: {count} sources")
        return
    
    if args.list_categories:
        categories = system.get_available_categories()
        print(f"Available categories ({len(categories)}):")
        for category in categories:
            count = len(system.get_bangs_by_category(category))
            print(f"  {category}: {count} sources")
        return
    
    if args.stats:
        stats = system.get_system_stats()
        print("Comprehensive News Bangs System Statistics:")
        print(f"  Total bangs: {stats['total_bangs']}")
        print(f"  Countries covered: {stats['countries_covered']}")
        print(f"  Languages supported: {stats['languages_supported']}")
        print(f"  Categories available: {stats['categories_available']}")
        print(f"  Priority bangs: {stats['priority_bangs']}")
        print(f"  Domains covered: {stats['domains_covered']}")
        print()
        print("Top countries by source count:")
        for country, count in stats['top_countries']:
            print(f"  {country}: {count} sources")
        return
    
    if args.bang_info:
        info = system.get_bang_info(args.bang_info)
        if info:
            print(f"Bang: {info['bang']}")
            print(f"Name: {info['name']}")
            print(f"Country: {info['country']}")
            print(f"Language: {info['language']}")
            print(f"Domain: {info['domain']}")
            print(f"Category: {info['category']}")
            print(f"URL: {info['url']}")
        else:
            print(f"Bang '{args.bang_info}' not found")
        return
    
    if not args.query:
        parser.print_help()
        return
    
    # Perform search
    try:
        results = system.search_news(
            args.query,
            country=args.country,
            language=args.language,
            category=args.category,
            max_results=args.max_results
        )
        
        print(f"Query: {results['query']}")
        print(f"Results: {results['total_bangs']} sources")
        
        if results['filters_applied']['country']:
            print(f"Country filter: {results['filters_applied']['country']}")
        if results['filters_applied']['language']:
            print(f"Language filter: {results['filters_applied']['language']}")
        if results['filters_applied']['category']:
            print(f"Category filter: {results['filters_applied']['category']}")
        
        print()
        print("Sources:")
        for i, (bang_name, data) in enumerate(results['bangs'].items(), 1):
            print(f"{i:2d}. {bang_name} - {data['name']} ({data['country']}, {data['language']})")
            print(f"     {data['url']}")
            print(f"     Category: {data['category']}, Score: {data['score']:.2f}")
            print()
        
        # Show statistics
        stats = results['statistics']
        print("Coverage Statistics:")
        print(f"  Countries: {dict(stats['by_country'])}")
        print(f"  Languages: {dict(stats['by_language'])}")
        print(f"  Categories: {dict(stats['by_category'])}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 