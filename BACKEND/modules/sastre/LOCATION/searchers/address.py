#!/usr/bin/env python3
"""
Address & Geolocation Search Module
====================================

Integrates multiple mapping services, satellite imagery, street view, and geolocation tools.
Based on Bellingcat's Digital Investigation Toolkit recommendations.

Search operators:
- address:query - Search addresses across multiple services
- coords:lat,lng - Search by coordinates
- satellite:location - Get satellite imagery
- streetview:address - Get street-level imagery  
- historical:location,year - Historical maps/imagery
- what3words:word.word.word - Convert to coordinates
- pluscode:code - Convert Plus Code
- marine:vessel - Track ships
- flight:number - Track flights
- measure:point1,point2 - Calculate distances
"""

import json
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import requests
import asyncio
import aiohttp

logger = logging.getLogger(__name__)


class AddressGeolocationSearch:
    """Unified interface for address, mapping, and geolocation services."""
    
    def __init__(self):
        # Load mapping services from datasets
        self.maps_data = self._load_maps_data()
        self.bellingcat_tools = self._load_bellingcat_tools()
        
        # Compile search patterns
        self.search_patterns = self._compile_patterns()
        
    def _load_maps_data(self) -> Dict:
        """Load original maps.json data."""
        maps_file = Path(__file__).parent.parent / "datasets" / "maps.json"
        if maps_file.exists():
            with open(maps_file, 'r') as f:
                return json.load(f)
        return {"location": []}
    
    def _load_bellingcat_tools(self) -> Dict:
        """Load Bellingcat toolkit data."""
        bellingcat_file = Path(__file__).parent.parent / "datasets" / "maps_bellingcat.json"
        if bellingcat_file.exists():
            with open(bellingcat_file, 'r') as f:
                return json.load(f)
        return {"bellingcat_maps_toolkit": {"categories": {}}}
    
    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Compile regex patterns for different search types."""
        return {
            'coordinates': re.compile(r'^coords?:?\s*([-\d.]+)\s*,\s*([-\d.]+)'),
            'address': re.compile(r'^address:?\s*(.+)'),
            'satellite': re.compile(r'^satellite:?\s*(.+)'),
            'streetview': re.compile(r'^streetview:?\s*(.+)'),
            'historical': re.compile(r'^historical:?\s*(.+?)\s*,?\s*(\d{4})?'),
            'what3words': re.compile(r'^what3words:?\s*(\w+\.\w+\.\w+)'),
            'pluscode': re.compile(r'^pluscode:?\s*([\w\+]+)'),
            'marine': re.compile(r'^marine:?\s*(.+)'),
            'flight': re.compile(r'^flight:?\s*(.+)'),
            'measure': re.compile(r'^measure:?\s*(.+?)\s*,\s*(.+)'),
            'crisis': re.compile(r'^crisis:?\s*(.+)'),
            'fire': re.compile(r'^fire:?\s*(.+)'),
            'weather': re.compile(r'^weather:?\s*(.+)')
        }
    
    def parse_query(self, query: str) -> Tuple[str, Dict[str, Any]]:
        """Parse query to determine search type and parameters."""
        
        query = query.strip()
        
        # Check each pattern
        for search_type, pattern in self.search_patterns.items():
            match = pattern.match(query)
            if match:
                groups = match.groups()
                
                if search_type == 'coordinates':
                    return 'coordinates', {
                        'lat': float(groups[0]),
                        'lng': float(groups[1])
                    }
                elif search_type == 'historical':
                    return 'historical', {
                        'location': groups[0],
                        'year': groups[1] if len(groups) > 1 and groups[1] else None
                    }
                elif search_type == 'measure':
                    return 'measure', {
                        'point1': groups[0],
                        'point2': groups[1]
                    }
                else:
                    return search_type, {'query': groups[0]}
        
        # Default to address search
        return 'address', {'query': query}
    
    def generate_map_urls(self, search_type: str, params: Dict) -> List[Dict]:
        """Generate URLs for various mapping services based on search type."""
        
        urls = []
        toolkit = self.bellingcat_tools.get('bellingcat_maps_toolkit', {})
        categories = toolkit.get('categories', {})
        
        if search_type == 'coordinates':
            lat, lng = params['lat'], params['lng']
            
            # General maps
            for service in categories.get('general_maps', []):
                if service.get('search_pattern'):
                    url = service['search_pattern'].format(
                        query=f"{lat},{lng}",
                        lat=lat,
                        lng=lng
                    )
                    urls.append({
                        'name': service['name'],
                        'url': url,
                        'category': 'general_map',
                        'features': service.get('features', [])
                    })
            
            # Satellite imagery
            for service in categories.get('satellite_imagery', []):
                if service.get('search_pattern'):
                    url = service['search_pattern'].format(
                        lat=lat,
                        lng=lng,
                        bbox=f"{lng-0.1},{lat-0.1},{lng+0.1},{lat+0.1}"
                    )
                    urls.append({
                        'name': service['name'],
                        'url': url,
                        'category': 'satellite',
                        'features': service.get('features', [])
                    })
        
        elif search_type == 'address':
            query = urllib.parse.quote(params['query'])
            
            # Search across general maps
            for service in categories.get('general_maps', []):
                if service.get('search_pattern'):
                    url = service['search_pattern'].format(query=query)
                    urls.append({
                        'name': service['name'],
                        'url': url,
                        'category': 'general_map',
                        'features': service.get('features', [])
                    })
        
        elif search_type == 'streetview':
            query = urllib.parse.quote(params['query'])
            
            # Street view services
            for service in categories.get('street_view', []):
                if service.get('search_pattern'):
                    # First geocode the address if needed
                    coords = self.geocode_address(params['query'])
                    if coords:
                        url = service['search_pattern'].format(
                            lat=coords['lat'],
                            lng=coords['lng'],
                            query=query
                        )
                        urls.append({
                            'name': service['name'],
                            'url': url,
                            'category': 'street_view',
                            'features': service.get('features', [])
                        })
        
        elif search_type == 'satellite':
            # Get coordinates first
            coords = self.geocode_address(params['query'])
            if coords:
                lat, lng = coords['lat'], coords['lng']
                
                for service in categories.get('satellite_imagery', []):
                    if service.get('search_pattern'):
                        url = service['search_pattern'].format(
                            lat=lat,
                            lng=lng,
                            bbox=f"{lng-0.1},{lat-0.1},{lng+0.1},{lat+0.1}"
                        )
                        urls.append({
                            'name': service['name'],
                            'url': url,
                            'category': 'satellite',
                            'features': service.get('features', [])
                        })
        
        elif search_type == 'marine':
            vessel = urllib.parse.quote(params['query'])
            
            # Marine tracking services
            for service in categories.get('specialized_tools', []):
                if 'marine' in service.get('name', '').lower() or 'vessel' in service.get('name', '').lower():
                    if service.get('search_pattern'):
                        # For marine, we might need to search by name
                        base_url = service['url']
                        search_url = f"{base_url}/en/ais/index/search/vessel/{vessel}"
                        urls.append({
                            'name': service['name'],
                            'url': search_url,
                            'category': 'marine',
                            'features': service.get('features', [])
                        })
        
        elif search_type == 'flight':
            flight = urllib.parse.quote(params['query'])
            
            # Flight tracking services
            for service in categories.get('specialized_tools', []):
                if 'flight' in service.get('name', '').lower() or 'ads-b' in service.get('name', '').lower():
                    base_url = service['url']
                    search_url = f"{base_url}/data/flights/{flight}"
                    urls.append({
                        'name': service['name'],
                        'url': search_url,
                        'category': 'flight',
                        'features': service.get('features', [])
                    })
        
        elif search_type == 'historical':
            location = params['location']
            year = params.get('year')
            
            # Historical map services
            for service in categories.get('historical_maps', []):
                if service.get('search_pattern'):
                    url = service['search_pattern'].format(
                        query=urllib.parse.quote(location),
                        bbox="-180,-90,180,90"  # Default global bbox
                    )
                    if year:
                        url += f"&year={year}"
                    urls.append({
                        'name': service['name'],
                        'url': url,
                        'category': 'historical',
                        'features': service.get('features', [])
                    })
        
        elif search_type == 'crisis':
            location = params['query']
            coords = self.geocode_address(location)
            
            # Crisis mapping services
            for service in categories.get('crisis_mapping', []):
                if service.get('search_pattern') and coords:
                    url = service['search_pattern'].format(
                        region=urllib.parse.quote(location),
                        lat=coords['lat'],
                        lng=coords['lng']
                    )
                    urls.append({
                        'name': service['name'],
                        'url': url,
                        'category': 'crisis',
                        'features': service.get('features', [])
                    })
        
        elif search_type == 'what3words':
            words = params['query']
            
            # What3Words conversion
            urls.append({
                'name': 'What3Words',
                'url': f"https://what3words.com/{words}",
                'category': 'geolocation',
                'features': ['3_word_address']
            })
            
            # Also try to convert to coordinates
            coords = self.what3words_to_coords(words)
            if coords:
                # Add coordinate-based searches
                lat, lng = coords['lat'], coords['lng']
                for service in categories.get('general_maps', [])[:3]:  # Top 3 services
                    if service.get('search_pattern'):
                        url = service['search_pattern'].format(
                            query=f"{lat},{lng}",
                            lat=lat,
                            lng=lng
                        )
                        urls.append({
                            'name': f"{service['name']} (from W3W)",
                            'url': url,
                            'category': 'general_map',
                            'features': service.get('features', [])
                        })
        
        return urls
    
    def geocode_address(self, address: str) -> Optional[Dict[str, float]]:
        """Geocode an address to coordinates using Nominatim."""
        
        try:
            # Use OpenStreetMap Nominatim
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': address,
                'format': 'json',
                'limit': 1
            }
            headers = {
                'User-Agent': 'SearchEngineer/1.0'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data:
                    return {
                        'lat': float(data[0]['lat']),
                        'lng': float(data[0]['lon']),
                        'display_name': data[0].get('display_name', address)
                    }
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
        
        return None
    
    def reverse_geocode(self, lat: float, lng: float) -> Optional[str]:
        """Reverse geocode coordinates to address."""
        
        try:
            url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                'lat': lat,
                'lon': lng,
                'format': 'json'
            }
            headers = {
                'User-Agent': 'SearchEngineer/1.0'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('display_name', f"{lat},{lng}")
                
        except Exception as e:
            logger.error(f"Reverse geocoding error: {e}")
        
        return None
    
    def what3words_to_coords(self, words: str) -> Optional[Dict[str, float]]:
        """Convert What3Words to coordinates (requires API key)."""
        
        # This would require a What3Words API key
        # For now, return None - in production, implement API call
        logger.info(f"What3Words conversion for {words} requires API key")
        return None
    
    def calculate_distance(self, point1: str, point2: str) -> Optional[Dict]:
        """Calculate distance between two points."""
        
        # Geocode both points
        coords1 = self.geocode_address(point1)
        coords2 = self.geocode_address(point2)
        
        if coords1 and coords2:
            # Haversine formula for distance
            from math import radians, sin, cos, sqrt, atan2
            
            R = 6371  # Earth's radius in kilometers
            
            lat1, lon1 = radians(coords1['lat']), radians(coords1['lng'])
            lat2, lon2 = radians(coords2['lat']), radians(coords2['lng'])
            
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            distance = R * c
            
            return {
                'point1': coords1,
                'point2': coords2,
                'distance_km': round(distance, 2),
                'distance_miles': round(distance * 0.621371, 2)
            }
        
        return None


async def search_address(query: str, event_handler=None, search_id: str = None) -> List[Dict]:
    """Main entry point for address/geolocation searches.
    
    Args:
        query: Search query with operators
        event_handler: WebSocket handler for streaming
        search_id: Search session ID
        
    Returns:
        List of mapping service URLs and results
    """
    
    searcher = AddressGeolocationSearch()
    
    # Parse query
    search_type, params = searcher.parse_query(query)
    
    print(f"🗺️ Address/Geolocation Search")
    print(f"   Type: {search_type}")
    print(f"   Parameters: {params}")
    
    # Generate URLs for mapping services
    urls = searcher.generate_map_urls(search_type, params)
    
    results = []
    
    # Special handling for certain search types
    if search_type == 'measure':
        distance_info = searcher.calculate_distance(params['point1'], params['point2'])
        if distance_info:
            results.append({
                'title': f"Distance: {distance_info['distance_km']} km ({distance_info['distance_miles']} miles)",
                'snippet': f"From: {params['point1']} To: {params['point2']}",
                'url': '',
                'category': 'measurement',
                'data': distance_info
            })
    
    # Add service URLs as results
    for service_info in urls:
        results.append({
            'title': f"{service_info['name']} - {service_info['category']}",
            'url': service_info['url'],
            'snippet': f"Features: {', '.join(service_info['features'][:3])}",
            'category': service_info['category']
        })
    
    # Stream results if handler available
    if event_handler and search_id:
        for result in results:
            await event_handler({
                'type': 'result',
                'search_id': search_id,
                'data': {
                    'title': result['title'],
                    'url': result['url'],
                    'snippet': result.get('snippet', ''),
                    'source': 'MAPS',
                    'category': result.get('category', 'map')
                }
            })
            await asyncio.sleep(0.05)
    
    return results


# CLI interface
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Address & Geolocation Search")
        print("Usage: python address.py <query>")
        print("\nExamples:")
        print("  python address.py 'address:1600 Pennsylvania Avenue'")
        print("  python address.py 'coords:40.7128,-74.0060'")
        print("  python address.py 'satellite:Pentagon'")
        print("  python address.py 'streetview:Times Square'")
        print("  python address.py 'marine:Ever Given'")
        print("  python address.py 'measure:New York,Los Angeles'")
        sys.exit(1)
    
    query = sys.argv[1]
    
    # Run search
    results = asyncio.run(search_address(query))
    
    print(f"\n🗺️ Generated {len(results)} mapping service links:")
    for result in results:
        print(f"\n{result['title']}")
        if result.get('url'):
            print(f"  🔗 {result['url'][:100]}...")
        if result.get('snippet'):
            print(f"  📝 {result['snippet']}")