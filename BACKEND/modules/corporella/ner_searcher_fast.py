"""
Fast NER Searcher with GPT-4.1 nano and batch/parallel processing
"""

import os
import sys
import json
import traceback
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import asyncio
from datetime import datetime
import re
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import GPT-4 NER components
from website_searchers.ner_gpt4 import NERSearcherGPT4, GPT4EntityExtractor
from scraping.current_scraping import content_controller

# Type labels for output formatting
type_labels = {
    'p': 'People',
    '@': 'Emails', 
    'e': 'Emails',
    't': 'Phone Numbers',
    'l': 'Locations',
    'c': 'Companies',
    'ent': 'All Entities',
    'sum': 'Summary'
}

class FastNERSearcher:
    """Fast NER searcher with parallel processing and batch API support"""
    
    def __init__(self):
        self.gpt4_searcher = NERSearcherGPT4()
        self.extractor = GPT4EntityExtractor()
        
    async def search_entities(self, target_url_or_content: str, search_type: str, 
                            use_batch_api: bool = True,
                            parallel_chunk_size: int = 10) -> Dict:
        """Search for entities with optimized processing
        
        Args:
            target_url_or_content: URL to scrape or content dict
            search_type: Entity type to search for (p, c, l, t, @, ent)
            use_batch_api: Use OpenAI Batch API for large content
            parallel_chunk_size: Number of chunks to process in parallel
            
        Returns:
            Dict with results organized by source
        """
        try:
            # Get content
            if isinstance(target_url_or_content, dict):
                content = target_url_or_content
            else:
                logger.info(f"Fetching content from {target_url_or_content}")
                content = await content_controller.get_content(target_url_or_content)
            
            if not content or 'pages' not in content:
                return {'error': 'No content to analyze'}
            
            pages = content.get('pages', [])
            logger.info(f"Processing {len(pages)} pages for {type_labels.get(search_type, search_type)}")
            
            # Prepare page data for batch processing
            page_data = []
            for i, page in enumerate(pages):
                if page.get('content'):
                    page_data.append({
                        'id': f"page_{i}",
                        'url': page.get('url', f'page_{i}'),
                        'content': page['content'],
                        'timestamp': page.get('timestamp', '')
                    })
            
            if not page_data:
                return {'error': 'No text content found in pages'}
            
            
            # Process based on content size
            if len(page_data) > 50 and use_batch_api:
                # Use Batch API for very large content sets
                results = await self._process_with_batch_api(page_data, search_type)
            else:
                # Use parallel processing for moderate content
                results = await self._process_parallel(page_data, search_type, parallel_chunk_size)
            
            # Format results
            return self._format_results(results, search_type)
            
        except Exception as e:
            logger.error(f"Error in fast NER search: {str(e)}")
            logger.error(traceback.format_exc())
            return {'error': str(e)}
    
    async def _process_parallel(self, page_data: List[Dict], search_type: str, 
                              chunk_size: int) -> Dict[str, List[str]]:
        """Process pages in parallel chunks"""
        results = defaultdict(list)
        
        for i in range(0, len(page_data), chunk_size):
            chunk = page_data[i:i+chunk_size]
            
            # Create tasks for parallel processing
            tasks = []
            for page in chunk:
                task = self._extract_from_page(page, search_type)
                tasks.append((page['url'], task))
            
            # Execute in parallel
            chunk_results = await asyncio.gather(*[task for _, task in tasks])
            
            # Collect results
            for (url, _), entities in zip(tasks, chunk_results):
                if entities:
                    results[url].extend(entities)
            
            # Small delay between chunks
            if i + chunk_size < len(page_data):
                await asyncio.sleep(0.2)
        
        return dict(results)
    
    async def _extract_from_page(self, page: Dict, search_type: str) -> List[str]:
        """Extract entities from a single page"""
        try:
            content = page['content']
            
            # Chunk if needed
            chunks = self.extractor.chunk_text(content, max_chunk_size=3000)
            
            # Extract from all chunks
            all_entities = set()
            for chunk in chunks:
                entities = await self.extractor.extract_entities_single(chunk, search_type)
                all_entities.update(entities)
            
            return list(all_entities)
            
        except Exception as e:
            logger.error(f"Error extracting from page {page.get('url')}: {e}")
            return []
    
    async def _process_with_batch_api(self, page_data: List[Dict], search_type: str) -> Dict[str, List[str]]:
        """Process using OpenAI Batch API for cost savings"""
        logger.info(f"Using Batch API to process {len(page_data)} pages")
        
        # Prepare texts for batch processing
        texts = [(page['id'], page['content'][:3000]) for page in page_data]
        
        # Use batch API
        batch_results = await self.extractor.extract_entities_batch_api(texts, search_type)
        
        # Map results back to URLs
        results = defaultdict(list)
        for page in page_data:
            page_id = page['id']
            if page_id in batch_results:
                results[page['url']].extend(list(batch_results[page_id]))
        
        return dict(results)
    
    def _format_results(self, results: Dict[str, List[str]], search_type: str) -> Dict:
        """Format results for output"""
        # Remove duplicates and organize
        formatted_results = {}
        all_entities = set()
        
        for url, entities in results.items():
            unique_entities = sorted(set(entities))
            if unique_entities:
                formatted_results[url] = unique_entities
                all_entities.update(unique_entities)
        
        # Apply entity-specific filtering
        if search_type == 'p':
            # Filter people names
            all_entities = self._filter_people_names(all_entities)
        
        return {
            'entity_type': type_labels.get(search_type, search_type),
            'total_found': len(all_entities),
            'unique_entities': sorted(all_entities),
            'by_source': formatted_results,
            'processing_method': 'parallel_gpt4_nano'
        }
    
    def _filter_people_names(self, names: Set[str]) -> Set[str]:
        """Filter partial names that are part of full names"""
        full_names = {name for name in names if ' ' in name}
        single_names = {name for name in names if ' ' not in name}
        
        # Extract first/last names from full names
        first_names = {name.split()[0].lower() for name in full_names}
        last_names = {name.split()[-1].lower() for name in full_names}
        
        # Keep single names that aren't part of full names
        filtered_single = {name for name in single_names 
                         if name.lower() not in first_names and name.lower() not in last_names}
        
        return full_names.union(filtered_single)
    
    async def extract_from_text(self, text: str, search_type: str) -> List[Dict]:
        """Extract entities from raw text (for compatibility)"""
        entities = await self.extractor.extract_entities_single(text, search_type)
        return [{'text': entity, 'type': search_type} for entity in entities]
    
    async def search_all_types(self, target_url_or_content: str) -> Dict:
        """Extract all entity types in parallel"""
        entity_types = ['p', 'c', 'l', '@', 't']
        
        # Create tasks for all entity types
        tasks = []
        for entity_type in entity_types:
            task = self.search_entities(target_url_or_content, entity_type, 
                                      use_batch_api=False,  # Use parallel for speed
                                      parallel_chunk_size=20)
            tasks.append((entity_type, task))
        
        # Execute all extractions in parallel
        results = await asyncio.gather(*[task for _, task in tasks])
        
        # Combine results
        combined = {
            'all_entities': {},
            'summary': {}
        }
        
        for (entity_type, _), result in zip(tasks, results):
            if 'error' not in result:
                combined['all_entities'][type_labels[entity_type]] = result['unique_entities']
                combined['summary'][type_labels[entity_type]] = result['total_found']
        
        return combined


# Global instance for easy access
fast_ner_searcher = FastNERSearcher()

# Backwards compatibility functions
async def search_entities(target_url: str, search_type: str) -> List[Dict]:
    """Backwards compatible search function"""
    result = await fast_ner_searcher.search_entities(target_url, search_type)
    
    # Convert to old format
    entities = []
    for entity in result.get('unique_entities', []):
        entities.append({
            'text': entity,
            'type': search_type,
            'source_url': target_url
        })
    
    return entities

# Example usage function
async def example_usage():
    """Example of using the fast NER searcher"""
    searcher = FastNERSearcher()
    
    # Search for people on a website
    people_results = await searcher.search_entities(
        "https://example.com",
        'p',  # People
        use_batch_api=True,
        parallel_chunk_size=15
    )
    
    print(f"Found {people_results['total_found']} unique people:")
    for person in people_results['unique_entities'][:10]:
        print(f"  - {person}")
    
    # Extract all entity types
    all_results = await searcher.search_all_types("https://example.com")
    
    print("\nAll entities summary:")
    for entity_type, count in all_results['summary'].items():
        print(f"  {entity_type}: {count}")

if __name__ == "__main__":
    asyncio.run(example_usage())