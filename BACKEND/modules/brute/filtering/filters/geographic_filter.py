"""
Geographic Filter

Analyzes geographic relevance of search results based on location indicators,
geographic keywords, and regional content matching.
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Set, Tuple
import time
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..core.base_filter import BaseFilter, FilterResult, FilterContext

logger = logging.getLogger(__name__)

class GeographicFilter(BaseFilter):
    """
    Filter that analyzes geographic relevance based on location indicators,
    regional content, and geographic keyword matching.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize GeographicFilter.
        
        Args:
            config: Optional configuration dictionary
        """
        super().__init__("GeographicFilter", config)
        
        # Default configuration
        self.default_config = {
            'location_matching_weight': 0.4,    # Weight for direct location matching
            'regional_content_weight': 0.3,     # Weight for regional content analysis
            'domain_location_weight': 0.2,      # Weight for domain geographic indicators
            'language_location_weight': 0.1,    # Weight for language-based location hints
            'min_geographic_score': 30.0,       # Minimum score to not filter
            'strict_location_matching': False,   # Require exact location matches
            'boost_local_results': True,        # Boost locally relevant results
            
            # Geographic keywords and indicators
            'location_keywords': [
                'near', 'in', 'at', 'location', 'address', 'city', 'state',
                'country', 'region', 'area', 'local', 'nearby', 'around'
            ],
            
            # Country codes and domains
            'country_domains': {
                '.us': 'United States', '.uk': 'United Kingdom', '.ca': 'Canada',
                '.au': 'Australia', '.de': 'Germany', '.fr': 'France',
                '.jp': 'Japan', '.cn': 'China', '.ru': 'Russia',
                '.br': 'Brazil', '.in': 'India', '.it': 'Italy',
                '.es': 'Spain', '.nl': 'Netherlands', '.se': 'Sweden',
                '.no': 'Norway', '.dk': 'Denmark', '.fi': 'Finland'
            },
            
            # Major cities worldwide
            'major_cities': {
                'us': ['new york', 'los angeles', 'chicago', 'houston', 'philadelphia',
                       'phoenix', 'san antonio', 'san diego', 'dallas', 'san jose',
                       'austin', 'jacksonville', 'fort worth', 'columbus', 'charlotte',
                       'san francisco', 'indianapolis', 'seattle', 'denver', 'boston'],
                'uk': ['london', 'birmingham', 'manchester', 'glasgow', 'liverpool',
                       'bristol', 'sheffield', 'leeds', 'edinburgh', 'leicester'],
                'canada': ['toronto', 'montreal', 'vancouver', 'calgary', 'edmonton',
                          'ottawa', 'winnipeg', 'quebec city', 'hamilton', 'kitchener'],
                'australia': ['sydney', 'melbourne', 'brisbane', 'perth', 'adelaide',
                             'gold coast', 'newcastle', 'canberra', 'sunshine coast', 'wollongong'],
                'germany': ['berlin', 'hamburg', 'munich', 'cologne', 'frankfurt',
                           'stuttgart', 'düsseldorf', 'dortmund', 'essen', 'leipzig'],
                'global': ['tokyo', 'delhi', 'shanghai', 'são paulo', 'mumbai',
                          'beijing', 'osaka', 'cairo', 'mexico city', 'dhaka',
                          'moscow', 'istanbul', 'paris', 'rome', 'madrid']
            },
            
            # States and provinces
            'states_provinces': {
                'us_states': ['alabama', 'alaska', 'arizona', 'arkansas', 'california',
                             'colorado', 'connecticut', 'delaware', 'florida', 'georgia',
                             'hawaii', 'idaho', 'illinois', 'indiana', 'iowa', 'kansas',
                             'kentucky', 'louisiana', 'maine', 'maryland', 'massachusetts',
                             'michigan', 'minnesota', 'mississippi', 'missouri', 'montana',
                             'nebraska', 'nevada', 'new hampshire', 'new jersey', 'new mexico',
                             'new york', 'north carolina', 'north dakota', 'ohio', 'oklahoma',
                             'oregon', 'pennsylvania', 'rhode island', 'south carolina',
                             'south dakota', 'tennessee', 'texas', 'utah', 'vermont',
                             'virginia', 'washington', 'west virginia', 'wisconsin', 'wyoming'],
                'canadian_provinces': ['ontario', 'quebec', 'british columbia', 'alberta',
                                      'manitoba', 'saskatchewan', 'nova scotia', 'new brunswick',
                                      'newfoundland and labrador', 'prince edward island',
                                      'northwest territories', 'nunavut', 'yukon']
            },
            
            # Regional content indicators
            'regional_indicators': {
                'local_business': ['hours', 'phone', 'address', 'directions', 'map',
                                  'contact', 'visit', 'location', 'store', 'shop'],
                'local_news': ['local', 'regional', 'community', 'neighborhood',
                              'city council', 'mayor', 'local government'],
                'local_events': ['event', 'festival', 'concert', 'meeting',
                               'gathering', 'conference', 'workshop'],
                'tourism': ['visit', 'tourism', 'attractions', 'hotels', 'restaurants',
                           'travel', 'guide', 'things to do', 'sightseeing']
            },
            
            # Language-location mappings
            'language_locations': {
                'en': ['united states', 'united kingdom', 'canada', 'australia'],
                'es': ['spain', 'mexico', 'argentina', 'colombia', 'chile'],
                'fr': ['france', 'canada', 'belgium', 'switzerland'],
                'de': ['germany', 'austria', 'switzerland'],
                'it': ['italy'],
                'pt': ['brazil', 'portugal'],
                'ru': ['russia'],
                'ja': ['japan'],
                'zh': ['china', 'taiwan', 'hong kong'],
                'ko': ['south korea'],
                'ar': ['saudi arabia', 'egypt', 'uae']
            }
        }
        
        # Merge with user config
        self.config = {**self.default_config, **(config or {})}
        
        self.logger.debug(f"GeographicFilter initialized with {len(self.config['major_cities'])} city groups")
    
    async def filter_results(
        self,
        results: List[Dict[str, Any]],
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Filter results based on geographic relevance.
        
        Args:
            results: List of search results to filter
            context: Filtering context
            
        Returns:
            List of FilterResult objects with geographic scores
        """
        if not results:
            return []
        
        filter_results = []
        
        # Extract location intent from query and context
        location_intent = self._extract_location_intent(context.query, context.query_context)
        
        self.logger.debug(
            f"Analyzing geographic relevance for {len(results)} results "
            f"with location intent: {location_intent}"
        )
        
        for i, result in enumerate(results):
            try:
                # Calculate geographic score
                geographic_score = await self._calculate_geographic_score(
                    result, context, location_intent
                )
                
                # Determine tier and classification
                tier, classification = self._classify_result(geographic_score)
                
                # Generate reasoning
                reasoning = self._generate_reasoning(result, geographic_score, location_intent)
                
                # Get detailed geographic analysis
                geo_analysis = self._get_geographic_analysis(result, location_intent)
                
                filter_result = FilterResult(
                    result_id=f"geographic_{i}",
                    score=geographic_score,
                    tier=tier,
                    classification=classification,
                    reasoning=reasoning,
                    metadata={
                        'geographic_analysis': geo_analysis,
                        'location_intent': location_intent,
                        'filter': 'geographic'
                    },
                    processed_at=time.time()
                )
                
                filter_results.append(filter_result)
                
            except Exception as e:
                self.logger.warning(f"Error processing result {i}: {e}")
                filter_results.append(self._create_error_result(i, str(e)))
        
        avg_score = sum(fr.score for fr in filter_results) / len(filter_results)
        self.logger.debug(f"GeographicFilter processed {len(results)} results, average score: {avg_score:.1f}")
        
        return filter_results
    
    def _extract_location_intent(
        self,
        query: str,
        query_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract location intent from query and context.
        
        Args:
            query: Search query
            query_context: Additional query context
            
        Returns:
            Dictionary with location intent analysis
        """
        intent = {
            'has_location_intent': False,
            'specific_locations': [],
            'location_types': [],
            'search_scope': 'global',  # global, national, regional, local
            'language_hint': None,
            'country_hint': None
        }
        
        query_lower = query.lower()
        
        # Check for explicit location keywords
        for keyword in self.config['location_keywords']:
            if keyword in query_lower:
                intent['has_location_intent'] = True
                break
        
        # Extract specific locations mentioned
        
        # Check for cities
        for country, cities in self.config['major_cities'].items():
            for city in cities:
                if city in query_lower:
                    intent['specific_locations'].append({
                        'name': city,
                        'type': 'city',
                        'country': country
                    })
                    intent['has_location_intent'] = True
        
        # Check for states/provinces
        for region_type, locations in self.config['states_provinces'].items():
            for location in locations:
                if location in query_lower:
                    intent['specific_locations'].append({
                        'name': location,
                        'type': 'state' if 'state' in region_type else 'province',
                        'country': 'us' if 'us_' in region_type else 'canada'
                    })
                    intent['has_location_intent'] = True
        
        # Check for country mentions
        for domain, country in self.config['country_domains'].items():
            if country.lower() in query_lower:
                intent['specific_locations'].append({
                    'name': country,
                    'type': 'country',
                    'country': country.lower().replace(' ', '_')
                })
                intent['has_location_intent'] = True
        
        # Determine search scope
        if intent['specific_locations']:
            location_types = [loc['type'] for loc in intent['specific_locations']]
            if 'city' in location_types:
                intent['search_scope'] = 'local'
            elif 'state' in location_types or 'province' in location_types:
                intent['search_scope'] = 'regional'
            elif 'country' in location_types:
                intent['search_scope'] = 'national'
        
        # Extract language hint from query context
        if 'language' in query_context:
            intent['language_hint'] = query_context['language']
        
        # Look for location operators in query context
        if query_context.get('location'):
            intent['has_location_intent'] = True
            intent['specific_locations'].append({
                'name': query_context['location'],
                'type': 'specified',
                'country': 'unknown'
            })
        
        return intent
    
    async def _calculate_geographic_score(
        self,
        result: Dict[str, Any],
        context: FilterContext,
        location_intent: Dict[str, Any]
    ) -> float:
        """
        Calculate comprehensive geographic relevance score.
        
        Args:
            result: Search result to analyze
            context: Filtering context
            location_intent: Extracted location intent
            
        Returns:
            Geographic score (0-100)
        """
        # If no location intent, return neutral score
        if not location_intent['has_location_intent']:
            return 60.0  # Neutral score for non-geographic searches
        
        scores = {}
        
        # 1. Direct location matching
        scores['location_matching'] = self._analyze_location_matching(
            result, location_intent
        ) * self.config['location_matching_weight']
        
        # 2. Regional content analysis
        scores['regional_content'] = self._analyze_regional_content(
            result, location_intent
        ) * self.config['regional_content_weight']
        
        # 3. Domain location indicators
        scores['domain_location'] = self._analyze_domain_location(
            result, location_intent
        ) * self.config['domain_location_weight']
        
        # 4. Language-location correlation
        scores['language_location'] = self._analyze_language_location(
            result, location_intent
        ) * self.config['language_location_weight']
        
        # Calculate total score
        total_score = sum(scores.values())
        
        # Apply location boost if configured
        if self.config['boost_local_results'] and location_intent['search_scope'] == 'local':
            total_score *= 1.1  # 10% boost for local searches
        
        # Normalize to 0-100 range
        geographic_score = min(100.0, max(0.0, total_score))
        
        return geographic_score
    
    def _analyze_location_matching(
        self,
        result: Dict[str, Any],
        location_intent: Dict[str, Any]
    ) -> float:
        """Analyze direct location matching in content."""
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        url = result.get('url', '').lower()
        combined_text = f"{title} {snippet} {url}"
        
        score = 30.0  # Base score for location-intent queries
        
        specific_locations = location_intent.get('specific_locations', [])
        
        if not specific_locations:
            return score
        
        # Check for exact location matches
        exact_matches = 0
        partial_matches = 0
        
        for location in specific_locations:
            location_name = location['name'].lower()
            
            # Exact match in title (highest weight)
            if location_name in title:
                exact_matches += 1
                score += 30.0
            # Exact match in snippet
            elif location_name in snippet:
                exact_matches += 1
                score += 20.0
            # Partial match or related terms
            elif any(word in combined_text for word in location_name.split()):
                partial_matches += 1
                score += 10.0
        
        # Bonus for multiple location matches
        if exact_matches > 1:
            score += exact_matches * 5.0
        
        # Check for location context keywords
        location_context = ['located', 'based', 'situated', 'headquarters', 'office']
        context_matches = sum(1 for keyword in location_context if keyword in combined_text)
        score += context_matches * 3.0
        
        return min(100.0, score)
    
    def _analyze_regional_content(
        self,
        result: Dict[str, Any],
        location_intent: Dict[str, Any]
    ) -> float:
        """Analyze regional content indicators."""
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        combined_text = f"{title} {snippet}"
        
        score = 40.0  # Base score
        
        # Check for regional content types
        for content_type, indicators in self.config['regional_indicators'].items():
            matches = sum(1 for indicator in indicators if indicator in combined_text)
            if matches > 0:
                type_score = min(20.0, matches * 5.0)
                score += type_score
                
                # Bonus for highly regional content types
                if content_type in ['local_business', 'local_news']:
                    score += 10.0
        
        # Check for address-like patterns
        address_patterns = [
            r'\d+\s+\w+\s+(street|st|avenue|ave|road|rd|boulevard|blvd)',
            r'\d+\s+\w+\s+\w+\s+(street|st|avenue|ave)',
            r'phone:\s*\(\d{3}\)\s*\d{3}-\d{4}',
            r'\d{5}(-\d{4})?'  # ZIP codes
        ]
        
        for pattern in address_patterns:
            if re.search(pattern, combined_text):
                score += 15.0
                break
        
        return min(100.0, score)
    
    def _analyze_domain_location(
        self,
        result: Dict[str, Any],
        location_intent: Dict[str, Any]
    ) -> float:
        """Analyze domain geographic indicators."""
        url = result.get('url', '').lower()
        
        score = 50.0  # Neutral base score
        
        # Check for country-specific domains
        for domain_ext, country in self.config['country_domains'].items():
            if url.endswith(domain_ext) or domain_ext in url:
                # Check if this matches the intended location
                specific_locations = location_intent.get('specific_locations', [])
                for location in specific_locations:
                    if (location['type'] == 'country' and 
                        country.lower() in location['name'].lower()):
                        score += 30.0  # Strong match
                        break
                    elif (location['type'] in ['city', 'state', 'province'] and
                          location.get('country', '').replace('_', ' ') == country.lower()):
                        score += 20.0  # Regional match
                        break
                else:
                    score += 5.0  # Generic geographic indicator
                break
        
        # Check for geographic subdomains
        geo_subdomains = ['local', 'regional', 'city', 'state', 'country']
        if any(subdomain in url for subdomain in geo_subdomains):
            score += 10.0
        
        # Check for location-specific paths
        specific_locations = location_intent.get('specific_locations', [])
        for location in specific_locations:
            location_name = location['name'].lower().replace(' ', '-')
            if location_name in url:
                score += 25.0
        
        return min(100.0, score)
    
    def _analyze_language_location(
        self,
        result: Dict[str, Any],
        location_intent: Dict[str, Any]
    ) -> float:
        """Analyze language-location correlation."""
        score = 50.0  # Neutral base score
        
        # This is a simplified implementation
        # In a full implementation, you might use language detection
        # on the content and correlate with expected locations
        
        language_hint = location_intent.get('language_hint')
        if language_hint and language_hint in self.config['language_locations']:
            expected_countries = self.config['language_locations'][language_hint]
            
            # Check if any specific locations match expected countries
            specific_locations = location_intent.get('specific_locations', [])
            for location in specific_locations:
                if location['type'] == 'country':
                    country_name = location['name'].lower()
                    if any(expected in country_name for expected in expected_countries):
                        score += 20.0
                        break
        
        return min(100.0, score)
    
    def _classify_result(self, geographic_score: float) -> tuple:
        """Classify result based on geographic score."""
        if geographic_score >= 85.0:
            return 1, 'primary'
        elif geographic_score >= 70.0:
            return 2, 'primary'
        elif geographic_score >= 50.0:
            return 3, 'secondary'
        elif geographic_score >= self.config['min_geographic_score']:
            return 4, 'secondary'
        else:
            return 4, 'secondary'  # Don't completely filter out
    
    def _generate_reasoning(
        self,
        result: Dict[str, Any],
        score: float,
        location_intent: Dict[str, Any]
    ) -> str:
        """Generate human-readable reasoning for the geographic score."""
        reasons = []
        
        if not location_intent['has_location_intent']:
            return "No geographic intent detected"
        
        if score >= 85:
            reasons.append("Excellent geographic relevance")
        elif score >= 70:
            reasons.append("Good geographic relevance")
        elif score >= 50:
            reasons.append("Moderate geographic relevance")
        else:
            reasons.append("Limited geographic relevance")
        
        # Add specific location matches
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        
        specific_locations = location_intent.get('specific_locations', [])
        matched_locations = []
        
        for location in specific_locations:
            location_name = location['name'].lower()
            if location_name in title or location_name in snippet:
                matched_locations.append(location['name'])
        
        if matched_locations:
            reasons.append(f"Location matches: {', '.join(matched_locations[:3])}")
        
        # Add regional content indicators
        combined_text = f"{title} {snippet}"
        regional_types = []
        
        for content_type, indicators in self.config['regional_indicators'].items():
            if any(indicator in combined_text for indicator in indicators):
                regional_types.append(content_type.replace('_', ' '))
        
        if regional_types:
            reasons.append(f"Regional content: {', '.join(regional_types[:2])}")
        
        return "; ".join(reasons)
    
    def _get_geographic_analysis(
        self,
        result: Dict[str, Any],
        location_intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get detailed geographic analysis for debugging."""
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        url = result.get('url', '').lower()
        
        return {
            'has_location_intent': location_intent['has_location_intent'],
            'search_scope': location_intent['search_scope'],
            'specific_locations': location_intent['specific_locations'],
            'location_matches_in_title': [
                loc['name'] for loc in location_intent.get('specific_locations', [])
                if loc['name'].lower() in title
            ],
            'location_matches_in_snippet': [
                loc['name'] for loc in location_intent.get('specific_locations', [])
                if loc['name'].lower() in snippet
            ],
            'regional_content_types': [
                content_type for content_type, indicators in self.config['regional_indicators'].items()
                if any(indicator in snippet for indicator in indicators)
            ],
            'domain_country_indicators': [
                country for domain_ext, country in self.config['country_domains'].items()
                if domain_ext in url
            ],
            'has_address_pattern': bool(re.search(
                r'\d+\s+\w+\s+(street|st|avenue|ave|road|rd)', 
                snippet
            ))
        }
    
    def _create_error_result(self, index: int, error_msg: str) -> FilterResult:
        """Create result for processing errors."""
        return FilterResult(
            result_id=f"geographic_error_{index}",
            score=50.0,  # Neutral score for errors
            tier=3,
            classification='secondary',
            reasoning=f"Geographic analysis error: {error_msg}",
            metadata={'filter': 'geographic', 'error': True},
            processed_at=time.time()
        )