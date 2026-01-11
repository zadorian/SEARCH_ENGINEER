#!/usr/bin/env python3
"""
Author Search Module - Consolidated Author Search Implementation
================================================================

Unified author search across multiple sources:
1. Academic databases (PubMed, ArXiv, CrossRef, OpenAlex)
2. Book repositories (Archive.org, OpenLibrary, Gutenberg)
3. General search engines with author patterns
4. Publisher databases (JSTOR, SAGE, Project MUSE)

Search operators:
- author:name - Search by author name
- auth:name - Short form
- by:name - Alternative form

Supported Engines:
- AR (Archive.org) - creator/author field
- OA (OpenAlex) - author.display_name field
- CR (Crossref) - author field in API
- PM (PubMed) - [Author] field
- AX (arXiv) - au: field
- SE (Semantic Scholar) - author field
- JS (JSTOR) - author search
- MU (Project MUSE) - author field
- SG (SAGE) - author field
- GU (Gutenberg) - author field
- OL (OpenLibrary) - author field
- GO (Google) - "by Name" patterns

Features:
- Name variation generation (initials, reversed order)
- Co-author search support
- Academic vs. literary author distinction
- Publisher-specific formatting

Note: This module consolidates:
- legacy/author_legacy.py (original implementation)
- legacy/author_search_legacy.py (enhanced version)
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
import time
import requests
import re
from urllib.parse import quote, urlencode
from bs4 import BeautifulSoup

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import event streaming for filtering events
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for author search")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Engines with native author field support
AUTHOR_ENGINES = {
    'academic': ['OA', 'CR', 'PM', 'AX', 'SE'],  # Academic databases
    'books': ['AR', 'GU', 'OL'],  # Book repositories
    'publishers': ['JS', 'MU', 'SG'],  # Publisher databases
    'general': ['GO', 'BI', 'DD']  # General search engines
}

class AuthorSearch(SearchTypeEventEmitter if STREAMING_AVAILABLE else object):
    """Consolidated author search across multiple sources"""
    
    def __init__(self, additional_args: List[str] = None):
        if STREAMING_AVAILABLE:
            super().__init__("author")
        
        self.additional_args = additional_args or []
        logger.info("AuthorSearch initialized")
    
    def generate_name_variations(self, name: str) -> List[str]:
        """Generate author name variations for better recall"""
        variations = [name]
        
        # Split name into parts
        parts = name.split()
        if len(parts) >= 2:
            # Last, First format
            variations.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
            
            # First Last format
            variations.append(f"{parts[0]} {parts[-1]}")
            
            # With initials
            if len(parts[0]) > 1:
                variations.append(f"{parts[0][0]}. {parts[-1]}")
                variations.append(f"{parts[-1]}, {parts[0][0]}.")
            
            # Middle initial handling
            if len(parts) == 3:
                variations.append(f"{parts[0]} {parts[1][0]}. {parts[2]}")
                variations.append(f"{parts[2]}, {parts[0]} {parts[1][0]}.")
        
        return list(set(variations))
    
    async def search_academic(self, author: str, engines: List[str] = None) -> List[Dict]:
        """Search academic databases for author"""
        results = []
        engines = engines or AUTHOR_ENGINES['academic']

        for engine_code in engines:
            try:
                if engine_code == 'PM':  # PubMed
                    # PubMed E-utilities API
                    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={quote(author)}[Author]&retmax=20&retmode=json"
                    try:
                        response = requests.get(search_url, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            id_list = data.get('esearchresult', {}).get('idlist', [])
                            if id_list:
                                # Fetch summaries for the IDs
                                ids_str = ','.join(id_list[:20])
                                summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids_str}&retmode=json"
                                summary_resp = requests.get(summary_url, timeout=10)
                                if summary_resp.status_code == 200:
                                    summary_data = summary_resp.json()
                                    for pmid in id_list[:20]:
                                        article = summary_data.get('result', {}).get(pmid, {})
                                        if article and isinstance(article, dict):
                                            authors = article.get('authors', [])
                                            author_names = ', '.join([a.get('name', '') for a in authors[:3]])
                                            results.append({
                                                'title': article.get('title', 'Untitled'),
                                                'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                                'snippet': f"Authors: {author_names}. {article.get('source', '')} ({article.get('pubdate', '')})",
                                                'source': 'PubMed',
                                                'engine_badge': 'PM'
                                            })
                    except Exception as e:
                        logger.error(f"PubMed search error: {e}")

                elif engine_code == 'AX':  # arXiv
                    # arXiv API
                    url = f"http://export.arxiv.org/api/query?search_query=au:{quote(author)}&start=0&max_results=20"
                    try:
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            # Parse XML response
                            soup = BeautifulSoup(response.text, 'xml')
                            entries = soup.find_all('entry')
                            for entry in entries:
                                title = entry.find('title')
                                link = entry.find('id')
                                summary = entry.find('summary')
                                authors = entry.find_all('author')
                                author_names = ', '.join([a.find('name').text for a in authors[:3] if a.find('name')])

                                results.append({
                                    'title': title.text.strip() if title else 'Untitled',
                                    'url': link.text if link else '',
                                    'snippet': f"Authors: {author_names}. {summary.text[:200] if summary else ''}",
                                    'source': 'arXiv',
                                    'engine_badge': 'AX'
                                })
                    except Exception as e:
                        logger.error(f"arXiv search error: {e}")

                elif engine_code == 'CR':  # CrossRef
                    url = f"https://api.crossref.org/works?query.author={quote(author)}&rows=20"
                    try:
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            for item in data.get('message', {}).get('items', []):
                                results.append({
                                    'title': item.get('title', [''])[0],
                                    'url': item.get('URL', ''),
                                    'snippet': f"Authors: {', '.join([a.get('given', '') + ' ' + a.get('family', '') for a in item.get('author', [])])}",
                                    'source': 'CrossRef',
                                    'engine_badge': 'CR'
                                })
                    except Exception as e:
                        logger.error(f"CrossRef search error: {e}")

                elif engine_code == 'OA':  # OpenAlex
                    # OpenAlex API - use search parameter for author name
                    url = f"https://api.openalex.org/works?search={quote(author)}&per-page=20"
                    try:
                        headers = {'User-Agent': 'SearchEngineer/1.0 (mailto:contact@example.com)'}
                        response = requests.get(url, headers=headers, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            for work in data.get('results', []):
                                authorships = work.get('authorships', [])
                                author_names = ', '.join([a.get('author', {}).get('display_name', '') for a in authorships[:3]])
                                results.append({
                                    'title': work.get('title', 'Untitled'),
                                    'url': work.get('id', '').replace('https://openalex.org/', 'https://openalex.org/works/'),
                                    'snippet': f"Authors: {author_names}. Published: {work.get('publication_year', 'Unknown')}",
                                    'source': 'OpenAlex',
                                    'engine_badge': 'OA'
                                })
                    except Exception as e:
                        logger.error(f"OpenAlex search error: {e}")

                elif engine_code == 'SE':  # Semantic Scholar
                    import os
                    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={quote(author)}&fields=title,url,authors,abstract&limit=20"
                    try:
                        headers = {}
                        se_key = os.getenv('SEMANTIC_SCHOLAR_API_KEY')
                        if se_key:
                            headers['x-api-key'] = se_key
                        response = requests.get(url, headers=headers, timeout=10)
                        if response.status_code == 429:
                            logger.warning("Semantic Scholar rate-limited (429) - needs API key")
                        elif response.status_code == 200:
                            data = response.json()
                            for paper in data.get('data', []):
                                authors = paper.get('authors', [])
                                author_names = ', '.join([a.get('name', '') for a in authors[:3]])
                                results.append({
                                    'title': paper.get('title', 'Untitled'),
                                    'url': paper.get('url', f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}"),
                                    'snippet': f"Authors: {author_names}. {(paper.get('abstract') or '')[:150]}",
                                    'source': 'Semantic Scholar',
                                    'engine_badge': 'SE'
                                })
                    except Exception as e:
                        logger.error(f"Semantic Scholar search error: {e}")

            except Exception as e:
                logger.error(f"Error searching {engine_code}: {e}")

        return results
    
    async def search_books(self, author: str, engines: List[str] = None) -> List[Dict]:
        """Search book repositories for author"""
        results = []
        engines = engines or AUTHOR_ENGINES['books']

        for engine_code in engines:
            try:
                if engine_code == 'AR':  # Archive.org
                    query = f'creator:"{author}" OR author:"{author}"'
                    url = f"https://archive.org/advancedsearch.php?q={quote(query)}&output=json&rows=20"

                    try:
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            for doc in data.get('response', {}).get('docs', []):
                                results.append({
                                    'title': doc.get('title', 'Untitled'),
                                    'url': f"https://archive.org/details/{doc.get('identifier', '')}",
                                    'snippet': f"By {doc.get('creator', author)} - {doc.get('date', 'Unknown date')}",
                                    'source': 'Archive.org',
                                    'engine_badge': 'AR'
                                })
                    except Exception as e:
                        logger.error(f"Archive.org search error: {e}")

                elif engine_code == 'OL':  # OpenLibrary
                    # First search for author to get author key
                    author_url = f"https://openlibrary.org/search/authors.json?q={quote(author)}&limit=1"
                    try:
                        response = requests.get(author_url, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            authors_found = data.get('docs', [])
                            if authors_found:
                                author_key = authors_found[0].get('key', '')
                                author_name = authors_found[0].get('name', author)
                                # Now search for works by this author
                                works_url = f"https://openlibrary.org/search.json?author={quote(author)}&limit=20"
                                works_resp = requests.get(works_url, timeout=10)
                                if works_resp.status_code == 200:
                                    works_data = works_resp.json()
                                    for work in works_data.get('docs', []):
                                        results.append({
                                            'title': work.get('title', 'Untitled'),
                                            'url': f"https://openlibrary.org{work.get('key', '')}",
                                            'snippet': f"By {author_name}. First published: {work.get('first_publish_year', 'Unknown')}",
                                            'source': 'OpenLibrary',
                                            'engine_badge': 'OL'
                                        })
                    except Exception as e:
                        logger.error(f"OpenLibrary search error: {e}")

                elif engine_code == 'GU':  # Gutenberg
                    # Project Gutenberg search via Gutendex API
                    url = f"https://gutendex.com/books/?search={quote(author)}"
                    try:
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            for book in data.get('results', []):
                                authors = book.get('authors', [])
                                author_names = ', '.join([a.get('name', '') for a in authors])
                                # Check if this author matches
                                if any(author.lower() in a.get('name', '').lower() for a in authors):
                                    results.append({
                                        'title': book.get('title', 'Untitled'),
                                        'url': f"https://www.gutenberg.org/ebooks/{book.get('id', '')}",
                                        'snippet': f"By {author_names}. Downloads: {book.get('download_count', 0)}",
                                        'source': 'Gutenberg',
                                        'engine_badge': 'GU'
                                    })
                    except Exception as e:
                        logger.error(f"Gutenberg search error: {e}")

            except Exception as e:
                logger.error(f"Error searching {engine_code}: {e}")

        return results
    
    async def search_general(self, author: str, content_type: str = None) -> List[Dict]:
        """Search general engines with author patterns"""
        results = []
        
        # Build search queries with author patterns
        patterns = [
            f'"by {author}"',
            f'"author {author}"',
            f'"{author}" author',
            f'"{author}" wrote'
        ]
        
        if content_type:
            patterns = [f'{p} {content_type}' for p in patterns]
        
        # Use general search engines
        for pattern in patterns:
            # Import and use relevant search engines
            # This would integrate with existing search infrastructure
            pass
        
        return results
    
    async def search(self, query: str, search_type: str = 'all') -> Dict:
        """Main author search method"""
        start_time = datetime.now()
        
        # Parse query
        author_name = query
        if query.startswith('author:'):
            author_name = query[7:].strip()
        elif query.startswith('auth:'):
            author_name = query[5:].strip()
        elif query.startswith('by:'):
            author_name = query[3:].strip()
        
        # Generate name variations
        name_variations = self.generate_name_variations(author_name)
        
        all_results = []
        
        # Search different sources based on type
        if search_type in ['all', 'academic']:
            for name in name_variations:
                academic_results = await self.search_academic(name)
                all_results.extend(academic_results)
        
        if search_type in ['all', 'books']:
            for name in name_variations:
                book_results = await self.search_books(name)
                all_results.extend(book_results)
        
        if search_type in ['all', 'general']:
            general_results = await self.search_general(author_name)
            all_results.extend(general_results)
        
        # Deduplicate results
        seen_urls = set()
        unique_results = []
        for result in all_results:
            url = result.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        return {
            'query': query,
            'author': author_name,
            'total_results': len(unique_results),
            'results': unique_results,
            'execution_time': elapsed,
            'name_variations': name_variations
        }


# Main search function for integration
async def search_author(query: str, **kwargs) -> Dict:
    """Main entry point for author search"""
    searcher = AuthorSearch()
    return await searcher.search(query, **kwargs)


# CLI interface
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python author_search.py 'author:name'")
        print("Examples:")
        print("  python author_search.py 'author:Stephen King'")
        print("  python author_search.py 'auth:Asimov'")
        print("  python author_search.py 'by:J.K. Rowling'")
        sys.exit(1)
    
    query = sys.argv[1]
    
    async def main():
        results = await search_author(query)
        print(f"\nFound {results['total_results']} results for author: {results['author']}")
        print(f"Name variations searched: {', '.join(results['name_variations'])}")
        print(f"Execution time: {results['execution_time']:.2f}s\n")
        
        for i, result in enumerate(results['results'][:10], 1):
            print(f"{i}. [{result.get('engine_badge', 'UN')}] {result.get('title', 'Untitled')}")
            print(f"   {result.get('url', '')}")
            print(f"   {result.get('snippet', '')[:100]}...")
            print()
    
    asyncio.run(main())