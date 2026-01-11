#!/usr/bin/env python3
"""
Matrix-Based Query Router
Routes queries to appropriate NSOL components using the unified matrix
This is the main orchestrator that analyzes queries and delegates to the right search modules
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Any, Iterator
from pathlib import Path
import sys
from datetime import datetime

# Import the matrix - use relative imports when used as package
try:
    from .matrix_registry import UNIFIED_MATRIX, load_engine_matrix
except ImportError:
    # Fallback for direct execution
    from matrix_registry import UNIFIED_MATRIX, load_engine_matrix

logger = logging.getLogger(__name__)


class MatrixQueryRouter:
    """
    Main query router that uses the UNIFIED_MATRIX to route queries
    to appropriate NSOL (Narrative-Subject-Object-Location) components
    """
    
    def __init__(self):
        """Initialize the matrix router"""
        self.matrix = UNIFIED_MATRIX
        self.flattened_matrix = load_engine_matrix()
        self.operator_patterns = self._build_operator_patterns()
        logger.info("MatrixQueryRouter initialized with UNIFIED_MATRIX")
    
    def _build_operator_patterns(self) -> Dict[str, re.Pattern]:
        """
        Build regex patterns for detecting operators in queries
        
        Returns:
            Dictionary mapping operator names to compiled regex patterns
        """
        patterns = {
            # SUBJECT operators
            'person': re.compile(r'\bp:([^:\s]+)', re.IGNORECASE),
            'company': re.compile(r'\bc:([^:\s]+)', re.IGNORECASE),
            'username': re.compile(r'\busername:([^:\s]+)', re.IGNORECASE),
            
            # OBJECT operators (query modifiers)
            'proximity': re.compile(r'(\w+)\s+~(\d+)\s+(\w+)', re.IGNORECASE),
            'not': re.compile(r'\s+-(\w+)', re.IGNORECASE),
            'or': re.compile(r'\s+(OR|\/)\s+', re.IGNORECASE),
            'translation': re.compile(r'tr([a-z]{2,3})!', re.IGNORECASE),
            'variation': re.compile(r"'([^']+)'", re.IGNORECASE),
            'handshake': re.compile(r'handshake\{([^}]+)\}', re.IGNORECASE),
            'wildcard': re.compile(r'\*+', re.IGNORECASE),
            
            # LOCATION operators
            # Temporal
            'date': re.compile(r'(\d{4})!', re.IGNORECASE),
            'date_range': re.compile(r'(\d{4})-(\d{4})!', re.IGNORECASE),
            'event': re.compile(r'event:', re.IGNORECASE),
            
            # Geographic
            'site': re.compile(r'site:([^\s]+)', re.IGNORECASE),
            'location': re.compile(r'(loc|near):([A-Z]{2})!', re.IGNORECASE),
            'language': re.compile(r'(lang|language):([a-z]{2,3})!', re.IGNORECASE),
            'language_short': re.compile(r'\b([a-z]{2,3})!', re.IGNORECASE),
            
            # Textual
            'intitle': re.compile(r'intitle:([^:\s]+)', re.IGNORECASE),
            'author': re.compile(r'(author|by):([^:\s]+)', re.IGNORECASE),
            'anchor': re.compile(r'anchor:([^:\s]+)', re.IGNORECASE),
            
            # Address (URL)
            'inurl': re.compile(r'inurl:([^:\s]+)', re.IGNORECASE),
            'indom': re.compile(r'indom:([^:\s]+)', re.IGNORECASE),
            'alldom': re.compile(r'alldom:([^:\s]+)', re.IGNORECASE),
            
            # Format
            'filetype': re.compile(r'filetype:([^:\s]+)', re.IGNORECASE),
            'pdf': re.compile(r'\bpdf!', re.IGNORECASE),
            'document': re.compile(r'\b(document|doc)!', re.IGNORECASE),
            'image': re.compile(r'\b(image|img)!', re.IGNORECASE),
            'audio': re.compile(r'\baudio!', re.IGNORECASE),
            'video': re.compile(r'\b(video|vid)!', re.IGNORECASE),
            'code': re.compile(r'\b(code|programming)!', re.IGNORECASE),
            
            # Category
            'news': re.compile(r'\bnews!', re.IGNORECASE),
            'academic': re.compile(r'\b(academic|scholar)!', re.IGNORECASE),
            'social': re.compile(r'\bsocial!', re.IGNORECASE),
            'forum': re.compile(r'\bforum!', re.IGNORECASE),
            'book': re.compile(r'\bbook!', re.IGNORECASE),
        }
        return patterns
    
    def detect_operators(self, query: str) -> Dict[str, List[Tuple[str, Any]]]:
        """
        Detect all operators present in a query
        
        Args:
            query: Search query to analyze
            
        Returns:
            Dictionary mapping NSOL categories to detected operators and values
        """
        detected = {
            'SUBJECT': [],
            'OBJECT': [],
            'LOCATION': {
                'temporal': [],
                'geographic': [],
                'textual': [],
                'address': [],
                'format': [],
                'category': []
            }
        }
        
        # Check SUBJECT operators
        if self.operator_patterns['person'].search(query):
            detected['SUBJECT'].append(('person', self.operator_patterns['person'].findall(query)))
        if self.operator_patterns['company'].search(query):
            detected['SUBJECT'].append(('company', self.operator_patterns['company'].findall(query)))
        if self.operator_patterns['username'].search(query):
            detected['SUBJECT'].append(('username', self.operator_patterns['username'].findall(query)))
        
        # Check OBJECT operators
        if self.operator_patterns['proximity'].search(query):
            detected['OBJECT'].append(('proximity', True))
        if self.operator_patterns['not'].search(query):
            detected['OBJECT'].append(('not_search', True))
        if self.operator_patterns['or'].search(query):
            detected['OBJECT'].append(('or_search', True))
        if self.operator_patterns['translation'].search(query):
            detected['OBJECT'].append(('translation', self.operator_patterns['translation'].findall(query)))
        if self.operator_patterns['variation'].search(query):
            detected['OBJECT'].append(('variation', self.operator_patterns['variation'].findall(query)))
        if self.operator_patterns['handshake'].search(query):
            detected['OBJECT'].append(('handshake', True))
        if self.operator_patterns['wildcard'].search(query):
            detected['OBJECT'].append(('wildcards', True))
        
        # Check LOCATION operators
        # Temporal
        if self.operator_patterns['date'].search(query) or self.operator_patterns['date_range'].search(query):
            detected['LOCATION']['temporal'].append(('date', True))
        if self.operator_patterns['event'].search(query):
            detected['LOCATION']['temporal'].append(('event', True))
        
        # Geographic
        if self.operator_patterns['site'].search(query):
            detected['LOCATION']['geographic'].append(('site', self.operator_patterns['site'].findall(query)))
        if self.operator_patterns['location'].search(query):
            detected['LOCATION']['geographic'].append(('address', True))
        if self.operator_patterns['language'].search(query):
            detected['LOCATION']['geographic'].append(('language', self.operator_patterns['language'].findall(query)))
        
        # Textual
        if self.operator_patterns['intitle'].search(query):
            detected['LOCATION']['textual'].append(('intitle', self.operator_patterns['intitle'].findall(query)))
        if self.operator_patterns['author'].search(query):
            detected['LOCATION']['textual'].append(('author', self.operator_patterns['author'].findall(query)))
        if self.operator_patterns['anchor'].search(query):
            detected['LOCATION']['textual'].append(('anchor', True))
        
        # Address
        if self.operator_patterns['inurl'].search(query):
            detected['LOCATION']['address'].append(('inurl', self.operator_patterns['inurl'].findall(query)))
        if self.operator_patterns['indom'].search(query):
            detected['LOCATION']['address'].append(('indom', self.operator_patterns['indom'].findall(query)))
        if self.operator_patterns['alldom'].search(query):
            detected['LOCATION']['address'].append(('alldom', self.operator_patterns['alldom'].findall(query)))
        
        # Format
        if self.operator_patterns['filetype'].search(query):
            detected['LOCATION']['format'].append(('filetype', self.operator_patterns['filetype'].findall(query)))
        if self.operator_patterns['pdf'].search(query):
            detected['LOCATION']['format'].append(('pdf', True))
        if self.operator_patterns['document'].search(query):
            detected['LOCATION']['format'].append(('document', True))
        if self.operator_patterns['image'].search(query):
            detected['LOCATION']['format'].append(('image', True))
        if self.operator_patterns['audio'].search(query):
            detected['LOCATION']['format'].append(('audio', True))
        if self.operator_patterns['video'].search(query):
            detected['LOCATION']['format'].append(('media', True))
        if self.operator_patterns['code'].search(query):
            detected['LOCATION']['format'].append(('text', True))
        
        # Category
        if self.operator_patterns['news'].search(query):
            detected['LOCATION']['category'].append(('news', True))
        if self.operator_patterns['academic'].search(query):
            detected['LOCATION']['category'].append(('academic', True))
        if self.operator_patterns['social'].search(query):
            detected['LOCATION']['category'].append(('social', True))
        if self.operator_patterns['forum'].search(query):
            detected['LOCATION']['category'].append(('forum', True))
        if self.operator_patterns['book'].search(query):
            detected['LOCATION']['category'].append(('book', True))
        
        return detected
    
    def get_engines_for_operators(self, detected: Dict) -> Dict[str, List[str]]:
        """
        Get the appropriate engines for detected operators
        
        Args:
            detected: Dictionary of detected operators
            
        Returns:
            Dictionary mapping layers (L1, L2, L3) to engine codes
        """
        engines = {
            'L1': set(),
            'L2': set(),
            'L3': set()
        }
        
        # Process SUBJECT operators
        for operator, _ in detected.get('SUBJECT', []):
            if operator in self.matrix['SUBJECT']:
                for layer, engine_list in self.matrix['SUBJECT'][operator].items():
                    engines[layer].update(engine_list)
        
        # Process OBJECT operators
        for operator, _ in detected.get('OBJECT', []):
            if operator in self.matrix['OBJECT']:
                for layer, engine_list in self.matrix['OBJECT'][operator].items():
                    engines[layer].update(engine_list)
        
        # Process LOCATION operators
        location_detected = detected.get('LOCATION', {})
        for dimension, operators in location_detected.items():
            if dimension in self.matrix['LOCATION']:
                for operator, _ in operators:
                    if operator in self.matrix['LOCATION'][dimension]:
                        for layer, engine_list in self.matrix['LOCATION'][dimension][operator].items():
                            engines[layer].update(engine_list)
        
        # Convert sets to lists
        return {
            'L1': list(engines['L1']),
            'L2': list(engines['L2']),
            'L3': list(engines['L3'])
        }
    
    def route_to_modules(self, query: str, detected: Dict) -> List[Dict]:
        """
        Route query to appropriate search modules
        
        Args:
            query: Original query
            detected: Detected operators
            
        Returns:
            List of routing decisions
        """
        routes = []
        
        # Route SUBJECT searches
        for operator, values in detected.get('SUBJECT', []):
            if operator == 'person':
                routes.append({
                    'module': 'ii.SUBJECT.ENTITY.person',
                    'operator': operator,
                    'values': values,
                    'family': 'SUBJECT'
                })
            elif operator == 'company':
                routes.append({
                    'module': 'ii.SUBJECT.ENTITY.company',
                    'operator': operator,
                    'values': values,
                    'family': 'SUBJECT'
                })
            elif operator == 'username':
                routes.append({
                    'module': 'ii.SUBJECT.ENTITY.username',
                    'operator': operator,
                    'values': values,
                    'family': 'SUBJECT'
                })
        
        # Route OBJECT modifiers
        for operator, values in detected.get('OBJECT', []):
            if operator == 'translation':
                routes.append({
                    'module': 'iii.OBJECT.OPERATORS.translation',
                    'operator': operator,
                    'values': values,
                    'family': 'OBJECT'
                })
            elif operator == 'variation':
                routes.append({
                    'module': 'iii.OBJECT.OPERATORS.variation',
                    'operator': operator,
                    'values': values,
                    'family': 'OBJECT'
                })
        
        # Route LOCATION searches
        location_detected = detected.get('LOCATION', {})
        
        # Format searches
        for operator, values in location_detected.get('format', []):
            routes.append({
                'module': 'iv.LOCATION.a.KNOWN_UNKNOWN.FORMAT.filetypes',
                'operator': operator,
                'values': values,
                'family': 'LOCATION',
                'dimension': 'format'
            })
        
        # Geographic searches
        for operator, values in location_detected.get('geographic', []):
            if operator == 'language':
                routes.append({
                    'module': 'iv.LOCATION.a.KNOWN_UNKNOWN.GEOGRAPHIC.LANGUAGE.language',
                    'operator': operator,
                    'values': values,
                    'family': 'LOCATION',
                    'dimension': 'geographic'
                })
        
        # Address searches
        for operator, values in location_detected.get('address', []):
            routes.append({
                'module': 'iv.LOCATION.a.KNOWN_UNKNOWN.ADDRESS.' + operator,
                'operator': operator,
                'values': values,
                'family': 'LOCATION',
                'dimension': 'address'
            })
        
        # Textual searches
        for operator, values in location_detected.get('textual', []):
            routes.append({
                'module': 'iv.LOCATION.a.KNOWN_UNKNOWN.TEXTUAL.' + operator,
                'operator': operator,
                'values': values,
                'family': 'LOCATION',
                'dimension': 'textual'
            })
        
        return routes
    
    def route_query(self, query: str) -> Dict[str, Any]:
        """
        Main routing method - analyzes query and returns routing decisions
        
        Args:
            query: Search query to route
            
        Returns:
            Dictionary with routing information
        """
        logger.info(f"Routing query: {query}")
        
        # Detect operators
        detected = self.detect_operators(query)
        
        # Get appropriate engines
        engines = self.get_engines_for_operators(detected)
        
        # Get module routes
        routes = self.route_to_modules(query, detected)
        
        # Build response
        response = {
            'query': query,
            'detected_operators': detected,
            'engines': engines,
            'routes': routes,
            'timestamp': datetime.now().isoformat(),
            'has_routing': bool(routes)
        }
        
        # Log routing decision
        if routes:
            logger.info(f"Query routed to {len(routes)} modules")
            for route in routes:
                logger.debug(f"  -> {route['module']} ({route['operator']})")
        else:
            logger.info("No specific routing detected, will use default search")
        
        return response
    
    def execute_routes(self, routing: Dict) -> Iterator[Dict]:
        """
        Execute the routing decisions and yield results
        
        Args:
            routing: Routing information from route_query
            
        Yields:
            Search results from various modules
        """
        query = routing['query']
        routes = routing['routes']
        
        if not routes:
            # No specific routing - use default brute search
            logger.info("Executing default brute search")
            yield {
                'type': 'default',
                'message': 'No specific operators detected, using default search',
                'query': query
            }
            return
        
        # Execute each route
        for route in routes:
            try:
                module_path = route['module']
                operator = route['operator']
                
                logger.info(f"Executing route: {module_path}")
                
                # Import and execute the module
                # This is simplified - in reality would need dynamic imports
                yield {
                    'type': 'route_execution',
                    'module': module_path,
                    'operator': operator,
                    'status': 'executing'
                }
                
                # Module execution would go here
                # results = import_and_execute(module_path, query, operator)
                # for result in results:
                #     yield result
                
            except Exception as e:
                logger.error(f"Error executing route {module_path}: {e}")
                yield {
                    'type': 'error',
                    'module': module_path,
                    'error': str(e)
                }


def analyze_query(query: str) -> Dict[str, Any]:
    """
    Analyze a query and return routing information
    
    Args:
        query: Search query to analyze
        
    Returns:
        Routing information
    """
    router = MatrixQueryRouter()
    return router.route_query(query)


def route_and_execute(query: str) -> Iterator[Dict]:
    """
    Route a query and execute the search
    
    Args:
        query: Search query
        
    Yields:
        Search results
    """
    router = MatrixQueryRouter()
    routing = router.route_query(query)
    
    for result in router.execute_routes(routing):
        yield result


# Command-line interface
def main():
    """Command-line interface for matrix router"""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='Matrix-based query router')
    parser.add_argument('query', type=str, help='Search query to route')
    parser.add_argument('--analyze-only', action='store_true', 
                       help='Only analyze, do not execute')
    parser.add_argument('--json', action='store_true',
                       help='Output as JSON')
    
    args = parser.parse_args()
    
    if args.analyze_only:
        # Just analyze the query
        routing = analyze_query(args.query)
        
        if args.json:
            print(json.dumps(routing, indent=2))
        else:
            print(f"\nQuery: {routing['query']}")
            print(f"Has routing: {routing['has_routing']}")
            
            if routing['detected_operators']:
                print("\nDetected operators:")
                for family, ops in routing['detected_operators'].items():
                    if ops:
                        print(f"  {family}:")
                        if isinstance(ops, dict):
                            for dim, dim_ops in ops.items():
                                if dim_ops:
                                    print(f"    {dim}: {dim_ops}")
                        else:
                            print(f"    {ops}")
            
            if routing['engines']:
                print("\nRecommended engines:")
                for layer, engines in routing['engines'].items():
                    if engines:
                        print(f"  {layer}: {', '.join(engines)}")
            
            if routing['routes']:
                print("\nRouting to modules:")
                for route in routing['routes']:
                    print(f"  -> {route['module']} ({route['operator']})")
    else:
        # Execute the routing
        print(f"Routing and executing: {args.query}\n")
        
        for result in route_and_execute(args.query):
            if args.json:
                print(json.dumps(result))
            else:
                if result['type'] == 'route_execution':
                    print(f"Executing: {result['module']}")
                elif result['type'] == 'error':
                    print(f"Error in {result['module']}: {result['error']}")
                else:
                    print(result)


if __name__ == '__main__':
    main()