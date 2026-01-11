#!/usr/bin/env python3
"""
Product Search Operator - Searches e-commerce sites and product listings
Supports product:, shopping:, buy: operators with schema integration
Leverages e-commerce platforms and Schema.org Product/Offer structured data
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
import time
import re
from urllib.parse import quote
from brute.engines.startpage import sp_shopping
# Simple URL builder for Facebook Marketplace (no scraping)
def _fb_q(query: str) -> str:
    return quote(f'"{query}"')

def fb_marketplace(query: str) -> str:
    return f"https://www.facebook.com/search/marketplace/?q={_fb_q(query)}"

FB_URL_BUILDERS_AVAILABLE = True

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import event streaming for filtering events
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for product search")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Product search engines
PRODUCT_ENGINES = [
    'GO',  # Google - with schema search and Google Shopping
    'BI',  # Bing - with Bing Shopping
    'BR',  # Brave
    'DD',  # DuckDuckGo
    'YA',  # Yandex
]

# Major e-commerce platforms (curated from shopping_domains_clean.txt)
PRODUCT_PLATFORMS = {
    # Major global marketplaces
    'amazon': 'site:amazon.com OR site:amazon.co.uk OR site:amazon.de OR site:amazon.fr',
    'ebay': 'site:ebay.com OR site:ebay.co.uk OR site:ebay.de',
    'alibaba': 'site:alibaba.com OR site:aliexpress.com',
    'etsy': 'site:etsy.com',
    'walmart': 'site:walmart.com',
    'target': 'site:target.com',
    
    # Department stores
    'bestbuy': 'site:bestbuy.com',
    'costco': 'site:costco.com',
    'homedepot': 'site:homedepot.com',
    'lowes': 'site:lowes.com',
    'macys': 'site:macys.com',
    'kohls': 'site:kohls.com',
    
    # Specialty retailers
    'newegg': 'site:newegg.com',
    'bhphoto': 'site:bhphotovideo.com',
    'rei': 'site:rei.com',
    'wayfair': 'site:wayfair.com',
    'overstock': 'site:overstock.com',
    
    # Fashion
    'nordstrom': 'site:nordstrom.com OR site:shop.nordstrom.com',
    'zappos': 'site:zappos.com',
    'asos': 'site:asos.com',
    'shein': 'site:shein.com',
    
    # International
    'rakuten': 'site:rakuten.com',
    'mercadolibre': 'site:mercadolibre.com',
    'flipkart': 'site:flipkart.com',
    'shopee': 'site:shopee.com',
}

# Schema.org structured data queries for products
PRODUCT_SCHEMAS = [
    'more:pagemap:product',
    'more:pagemap:product-name',
    'more:pagemap:product-brand',
    'more:pagemap:product-price',
    'more:pagemap:product-description',
    'more:pagemap:offer',
    'more:pagemap:offer-price',
    'more:pagemap:offer-availability',
    'more:pagemap:aggregateoffer',
    'more:pagemap:shoppingwebsite',
    'more:pagemap:vehicle',  # For car shopping
    'more:pagemap:productmodel',
]

class ProductSearch:
    """
    Product search operator implementation.
    Routes searches to e-commerce platforms and uses schema-enhanced queries.
    """
    
    def __init__(self, event_emitter=None):
        """Initialize product search with optional event streaming."""
        self.event_emitter = event_emitter
        self.available_engines = self._check_available_engines()
        self.shopping_domains = self._load_shopping_domains()
        
        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None
    
    def _load_shopping_domains(self) -> Dict[str, List[str]]:
        """Load shopping domains from file if available."""
        domains = {}
        try:
            shopping_file = PROJECT_ROOT / "shopping_domains_clean.txt"
            if shopping_file.exists():
                with open(shopping_file, 'r') as f:
                    for line in f:
                        if '|' in line:
                            category, domain = line.strip().split('|', 1)
                            if category not in domains:
                                domains[category] = []
                            domains[category].append(domain)
                logger.info(f"Loaded {sum(len(v) for v in domains.values())} shopping domains")
        except Exception as e:
            logger.warning(f"Could not load shopping domains: {e}")
        return domains
    
    def _check_available_engines(self) -> List[str]:
        """Check which product-supporting engines are available in the system."""
        available = []
        
        # Check ENGINE_CONFIG from brute.py
        try:
            from brute.targeted_searches.brute import ENGINE_CONFIG
            
            for engine_code in PRODUCT_ENGINES:
                if engine_code in ENGINE_CONFIG:
                    available.append(engine_code)
                    logger.info(f"Product engine {engine_code} available")
                else:
                    logger.debug(f"Product engine {engine_code} not configured")
        except ImportError:
            logger.error("Could not import ENGINE_CONFIG from brute.py")
            # Use fallback engines
            available = ['GO', 'BI', 'BR']
        
        if not available:
            logger.warning("No product engines available, using fallback engines")
            available = ['GO', 'BI', 'BR']
        
        logger.info(f"Available product engines: {available}")
        return available
    
    def _extract_price_filter(self, query: str) -> Tuple[str, Optional[Dict]]:
        """
        Extract price filters from query.
        
        Patterns:
        - price<100
        - price>50
        - price:50-100
        - under $100
        - above $50
        
        Returns:
            Tuple of (cleaned_query, price_filters)
        """
        price_filters = {}
        cleaned_query = query
        
        # Pattern for price<X or price>X
        price_pattern = r'\bprice\s*([<>])\s*(\d+)'
        match = re.search(price_pattern, query, re.IGNORECASE)
        if match:
            operator = match.group(1)
            value = int(match.group(2))
            if operator == '<':
                price_filters['max'] = value
            else:
                price_filters['min'] = value
            cleaned_query = re.sub(price_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Pattern for price:X-Y
        range_pattern = r'\bprice\s*:\s*(\d+)\s*-\s*(\d+)'
        match = re.search(range_pattern, query, re.IGNORECASE)
        if match:
            price_filters['min'] = int(match.group(1))
            price_filters['max'] = int(match.group(2))
            cleaned_query = re.sub(range_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Pattern for "under $X"
        under_pattern = r'\bunder\s*\$?\s*(\d+)'
        match = re.search(under_pattern, query, re.IGNORECASE)
        if match:
            price_filters['max'] = int(match.group(1))
            cleaned_query = re.sub(under_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        # Pattern for "above $X" or "over $X"
        over_pattern = r'\b(above|over)\s*\$?\s*(\d+)'
        match = re.search(over_pattern, query, re.IGNORECASE)
        if match:
            price_filters['min'] = int(match.group(2))
            cleaned_query = re.sub(over_pattern, '', cleaned_query, flags=re.IGNORECASE)
        
        return cleaned_query.strip(), price_filters if price_filters else None
    
    def _build_product_queries(self, query: str, include_platforms: bool = True, 
                              include_schemas: bool = True, price_filters: Optional[Dict] = None) -> List[str]:
        """
        Build comprehensive product search queries.
        
        Args:
            query: The search query
            include_platforms: Whether to include platform-specific searches
            include_schemas: Whether to include schema-enhanced searches
            price_filters: Optional price filtering
            
        Returns:
            List of search queries optimized for product content
        """
        queries = []
        
        # Base queries
        queries.append(f'buy {query}')
        queries.append(f'"{query}" price')
        queries.append(f'"{query}" for sale')
        queries.append(f'shop {query}')
        queries.append(f'"{query}" review')
        
        # Platform-specific searches
        if include_platforms:
            # Focus on top platforms for efficiency
            top_platforms = ['amazon', 'ebay', 'walmart', 'target', 'bestbuy', 
                           'etsy', 'alibaba', 'newegg']
            for platform_name in top_platforms:
                if platform_name in PRODUCT_PLATFORMS:
                    platform_filter = PRODUCT_PLATFORMS[platform_name]
                    base_query = f'{platform_filter} {query}'
                    if price_filters:
                        if 'max' in price_filters:
                            base_query += f' under ${price_filters["max"]}'
                    queries.append(base_query)
        
        # Schema-enhanced searches (Google API only)
        if include_schemas and 'GO' in self.available_engines:
            for schema in PRODUCT_SCHEMAS:
                schema_query = f'{schema} {query}'
                queries.append(schema_query)
            
            # Specific product schema combinations with price filters
            if price_filters:
                if 'max' in price_filters:
                    queries.append(f'more:pagemap:offer-price:<{price_filters["max"]} {query}')
                if 'min' in price_filters:
                    queries.append(f'more:pagemap:offer-price:>{price_filters["min"]} {query}')
            
            queries.extend([
                f'more:pagemap:product-name:"{query}"',
                f'more:pagemap:product {query}',
                f'more:pagemap:offer {query} available',
                f'more:pagemap:product-brand {query}',
            ])
        
        # Product-specific patterns
        queries.extend([
            f'"{query}" specifications',
            f'"{query}" features',
            f'best {query}',
            f'cheap {query}',
            f'"{query}" comparison',
            f'"{query}" deals',
            f'"{query}" discount',
            f'"{query}" coupon',
        ])
        
        # Category-specific searches from shopping_domains
        if self.shopping_domains:
            # Check for relevant categories
            relevant_categories = []
            query_lower = query.lower()
            
            # Simple category detection
            if any(term in query_lower for term in ['laptop', 'computer', 'phone', 'tablet', 'tech']):
                relevant_categories.extend(['Electronics', 'Tech'])
            if any(term in query_lower for term in ['shirt', 'dress', 'shoes', 'clothing', 'fashion']):
                relevant_categories.extend(['Fashion', 'Clothing'])
            if any(term in query_lower for term in ['book', 'novel', 'textbook']):
                relevant_categories.append('Books')
            
            # Add searches for relevant category domains
            for category in relevant_categories:
                if category in self.shopping_domains:
                    # Use top 3 domains from category
                    for domain in self.shopping_domains[category][:3]:
                        queries.append(f'site:{domain} {query}')
        
        return queries
    
    async def search(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """
        Execute product search across available engines.
        
        Args:
            query: The search query (without the product: operator)
            max_results: Maximum results to return
            
        Returns:
            List of search results from product/e-commerce sources
        """
        # Extract price filters and clean query
        cleaned_query, price_filters = self._extract_price_filter(query)
        
        logger.info(f"Starting product search for: '{cleaned_query}'")
        if price_filters:
            logger.info(f"Price filters: {price_filters}")
        logger.info(f"Using engines: {self.available_engines}")
        
        if self.streamer:
            await self.streamer.emit_search_started('product', cleaned_query, self.available_engines)
        
        # Build comprehensive product queries
        product_queries = self._build_product_queries(cleaned_query, price_filters=price_filters)

        # Prepend a direct Facebook Marketplace link row (on request), no scraping
        fb_rows: List[Dict[str, Any]] = []
        if FB_URL_BUILDERS_AVAILABLE:
            fb_rows.append({
                'title': f'Facebook Marketplace: {cleaned_query}',
                'url': fb_marketplace(cleaned_query),
                'source': 'facebook_marketplace',
                'snippet': 'Open Marketplace results on Facebook.'
            })
        # Add Startpage shopping link row
        fb_rows.append({
            'title': f'Startpage Shopping: {cleaned_query}',
            'url': sp_shopping(cleaned_query),
            'source': 'startpage_shopping'
        })
        
        # Import and run brute search with product queries
        try:
            from brute.targeted_searches.brute import BruteSearchEngine
            
            # Create output file for results
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"results/product_{timestamp}.json"
            
            all_results = []
            
            # Run searches for each product query variant (limit to prevent overload)
            for product_query in product_queries[:15]:  # Top 15 queries
                logger.info(f"Searching with query: '{product_query}'")
                
                # Initialize brute search
                searcher = BruteSearchEngine(
                    keyword=product_query,
                    output_file=output_file,
                    engines=self.available_engines,
                    max_workers=min(len(self.available_engines), 5),
                    event_emitter=self.event_emitter,
                    return_results=True
                )
                
                # Run the search
                searcher.search()
                
                # Get results
                if hasattr(searcher, 'final_results'):
                    results = searcher.final_results
                    # Tag results with product search metadata
                    for result in results:
                        result['search_type'] = 'product'
                        result['product_query'] = cleaned_query
                        result['query_variant'] = product_query
                        if price_filters:
                            result['price_filters'] = price_filters
                    all_results.extend(results)
            
            # Deduplicate results by URL
            seen_urls = set()
            unique_results = []
            for result in all_results:
                url = result.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(result)
            
            # Score and sort results
            scored_results = self._score_product_results(unique_results, cleaned_query, price_filters)
            
            if self.streamer:
                await self.streamer.emit_search_completed('product', len(scored_results))
            
            logger.info(f"Product search completed with {len(scored_results)} unique results")
            
            # Include FB link row at the top if present
            final = (fb_rows + scored_results)[:max_results]
            return final
            
        except ImportError as e:
            logger.error(f"Failed to import BruteSearchEngine: {e}")
            return []
        except Exception as e:
            logger.error(f"Product search failed: {e}")
            return []
    
    def _score_product_results(self, results: List[Dict], query: str, 
                               price_filters: Optional[Dict] = None) -> List[Dict]:
        """
        Score and sort product results by relevance.
        
        Prioritizes:
        1. Results from known e-commerce platforms
        2. Results with product schema markup
        3. Results with price information
        4. Results with product-related keywords
        """
        query_lower = query.lower()
        
        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # Check if from known e-commerce platform (highest priority)
            major_platforms = ['amazon.com', 'ebay.com', 'walmart.com', 'target.com',
                             'bestbuy.com', 'etsy.com', 'aliexpress.com', 'newegg.com',
                             'homedepot.com', 'lowes.com', 'costco.com']
            for platform in major_platforms:
                if platform in url:
                    score += 60
                    break
            
            # Check for product schema markup (from query variant)
            if 'query_variant' in result:
                variant = result['query_variant']
                if 'more:pagemap:product' in variant:
                    score += 50
                elif 'more:pagemap:offer' in variant:
                    score += 45
            
            # Price information in snippet (very valuable for products)
            price_pattern = r'\$\d+|\d+\.\d{2}|price|cost|buy|sale'
            if re.search(price_pattern, snippet, re.IGNORECASE):
                score += 35
            
            # Product keywords in title
            product_keywords = ['buy', 'shop', 'price', 'sale', 'deal', 'review', 
                              'specifications', 'features', 'model', 'brand']
            for keyword in product_keywords:
                if keyword in title:
                    score += 20
                    break
            
            # Query appears in title
            if query_lower in title:
                score += 30
            
            # Availability indicators
            availability_keywords = ['in stock', 'available', 'ships', 'delivery', 'free shipping']
            for keyword in availability_keywords:
                if keyword in snippet.lower():
                    score += 15
                    break
            
            # Rating/review indicators
            rating_pattern = r'\d+(\.\d+)?\s*(star|rating)|★|☆|\d+\s*review'
            if re.search(rating_pattern, snippet, re.IGNORECASE):
                score += 12
            
            # Query appears in snippet
            if query_lower in snippet:
                score += 15
            
            # Product number/SKU indicators
            sku_pattern = r'\b(SKU|Model|Part|Item)\s*[:#]?\s*[\w-]+\b'
            if re.search(sku_pattern, snippet, re.IGNORECASE):
                score += 8
            
            # Discount/deal indicators
            if any(word in snippet.lower() for word in ['discount', 'save', 'off', 'coupon', 'promo']):
                score += 10
            
            return score
        
        # Score all results
        for result in results:
            result['product_score'] = score_result(result)
        
        # Sort by score (highest first)
        results.sort(key=lambda x: x.get('product_score', 0), reverse=True)
        
        return results
    
    def search_sync(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, max_results))
        finally:
            loop.close()

# Adapter to match web_api.api.search expectation
def search(query: str, max_results: int = 200):
    searcher = ProductSearch()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(searcher.search(query, max_results))
    finally:
        loop.close()

def detect_product_query(query: str) -> bool:
    """
    Detect if a query should be routed to product search.
    
    Patterns:
    - product:query or product:"query"
    - shopping:query
    - buy:query
    - shop:query
    - purchase:query
    """
    query_lower = query.lower()
    
    # Check for product operators
    product_patterns = [
        'product:',
        'shopping:',
        'buy:',
        'shop:',
        'purchase:',
        'products:',
        'ecommerce:',
        'store:',
    ]
    
    for pattern in product_patterns:
        if pattern in query_lower:
            return True
    
    return False

def extract_product_query(query: str) -> str:
    """Extract the actual search query from a product search query."""
    # Remove operators
    query = query.strip()
    
    # Remove common operator prefixes (case-insensitive)
    prefixes = [
        'product:', 'shopping:', 'buy:', 'shop:', 'purchase:', 
        'products:', 'ecommerce:', 'store:',
        'Product:', 'Shopping:', 'Buy:', 'Shop:', 'Purchase:',
        'Products:', 'Ecommerce:', 'Store:'
    ]
    
    for prefix in prefixes:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            # Remove quotes if present
            if query.startswith('"') and query.endswith('"'):
                query = query[1:-1]
            elif query.startswith("'") and query.endswith("'"):
                query = query[1:-1]
            return query
    
    # If no prefix found, return the query as-is
    return query.strip()

# Main entry point for product search
async def run_product_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """
    Main entry point for product search.
    
    Args:
        query: The full query including product:/shopping: operator
        event_emitter: Optional event emitter for streaming updates
        
    Returns:
        List of product search results
    """
    # Extract the actual query
    clean_query = extract_product_query(query)
    
    # Create product searcher
    searcher = ProductSearch(event_emitter)
    
    # Run search
    return await searcher.search(clean_query)

def run_product_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for product search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_product_search(query, event_emitter))
    finally:
        loop.close()


def main():
    """Main entry point for Product/shopping search - compatible with SearchRouter"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Product/shopping search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    args = parser.parse_args()
    
    query = args.query
    
    # Extract clean query by removing operator prefix
    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query
    
    print(f"\n🔍 Product/shopping search: {clean_query}")
    
    # Try to use existing search function if available
    try:
        if 'run_product_search_sync' in globals():
            results = globals()['run_product_search_sync'](clean_query)
        elif 'search' in globals():
            results = search(clean_query)
        else:
            print("Note: This search type needs full implementation")
            results = []
    except Exception as e:
        print(f"Search implementation in progress: {e}")
        results = []
    
    if results:
        print(f"\nFound {len(results)} results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            if result.get('snippet'):
                print(f"   {result['snippet'][:200]}...")
    else:
        print("\nNo results found (implementation may be pending).")
    
    return results

if __name__ == "__main__":
    # Test product search
    import sys
    
    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "product:laptop price<1000"
    
    print(f"Testing product search with: {test_query}")
    
    if detect_product_query(test_query):
        print("Product query detected!")
        clean_query = extract_product_query(test_query)
        print(f"Extracted query: '{clean_query}'")
        
        results = run_product_search_sync(test_query)
        
        print(f"\nFound {len(results)} product results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
            print(f"   Product Score: {result.get('product_score', 0)}")
            if 'price_filters' in result:
                print(f"   Price Filters: {result['price_filters']}")
            snippet = result.get('snippet', '')
            if snippet:
                print(f"   Snippet: {snippet[:150]}...")
    else:
        print("Not a product query")