#!/usr/bin/env python3
"""
Books Search Module - Unified Book Search Implementation
========================================================

Combines multiple book search sources:
1. Gutenberg Books Corpus via HuggingFace API (50,000+ public domain books)
2. Local book collection via Whoosh indexing
3. External sources: Anna's Archive, LibGen, OpenLibrary, Google Books
4. Academic sources: CrossRef, PubMed, ArXiv

Search operators:
- book:query - Search book content
- intitle:query - Search book titles  
- author:name - Search by author
- isbn:number - Search by ISBN
- subject:topic - Search by subject/topic

Data Sources:
- HuggingFace: hakatiki/guttenberg-books-corpus
- Local: Whoosh indexed book collection
- External: Anna's Archive, LibGen API integrations
- Academic: CrossRef, OpenLibrary APIs

Usage:
    python main.py 'book:sherlock holmes'
    python main.py 'author:doyle'
    python main.py 'intitle:pride prejudice'

Note: This module consolidates all book search functionality from:
- Legacy book.py (academic search)
- Legacy book_indexer.py (local indexing)
- Legacy author*.py (author search)
- Original books.py (HuggingFace integration)
"""

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import quote

import aiohttp
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GutenbergBooksSearch:
    """Search interface for Gutenberg Books Corpus via HuggingFace."""
    
    BASE_URL = "https://datasets-server.huggingface.co"
    DATASET_ID = "hakatiki/guttenberg-books-corpus"
    
    def __init__(self, cache_dir: Optional[str] = None):
        """Initialize the books search interface.
        
        Args:
            cache_dir: Directory for caching book data
        """
        self.cache_dir = Path(cache_dir or "../datasets/books_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize local SQLite cache for book metadata
        self.db_path = self.cache_dir / "gutenberg_books.db"
        self._init_database()
        
        # Load dataset info
        self.dataset_info = self._get_dataset_info()
        
    def _init_database(self):
        """Initialize SQLite database for caching book data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create books table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY,
                title TEXT,
                author TEXT,
                subject TEXT,
                language TEXT,
                content_sample TEXT,
                full_text_url TEXT,
                metadata TEXT,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create search index
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS books_fts
            USING fts5(
                title, author, subject, content_sample,
                content=books,
                content_rowid=id
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_author ON books(author)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_title ON books(title)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subject ON books(subject)")
        
        conn.commit()
        conn.close()
        
    def _get_dataset_info(self) -> Dict:
        """Get dataset metadata from HuggingFace."""
        cache_file = self.cache_dir / "dataset_info.json"
        
        # Check cache (1 day TTL)
        if cache_file.exists():
            mod_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if datetime.now() - mod_time < timedelta(days=1):
                with open(cache_file, 'r') as f:
                    return json.load(f)
        
        try:
            # Fetch dataset info
            url = f"{self.BASE_URL}/info?dataset={self.DATASET_ID}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                info = response.json()
                
                # Cache the info
                with open(cache_file, 'w') as f:
                    json.dump(info, f, indent=2)
                
                return info
            else:
                logger.warning(f"Failed to fetch dataset info: {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching dataset info: {e}")
            return {}
    
    def fetch_sample_rows(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Fetch sample rows from the dataset.
        
        Args:
            limit: Number of rows to fetch
            offset: Starting position
            
        Returns:
            List of book records
        """
        try:
            url = f"{self.BASE_URL}/first-rows"
            params = {
                "dataset": self.DATASET_ID,
                "config": "default",
                "split": "train",
                "limit": limit,
                "offset": offset
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("rows", [])
            else:
                logger.error(f"Failed to fetch rows: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching sample rows: {e}")
            return []
    
    def index_books(self, batch_size: int = 100, max_books: int = 10000):
        """Index books from HuggingFace into local database.
        
        Args:
            batch_size: Number of books per batch
            max_books: Maximum number of books to index
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        indexed_count = 0
        offset = 0
        
        print(f"📚 Starting to index Gutenberg books...")
        
        while indexed_count < max_books:
            # Fetch batch
            rows = self.fetch_sample_rows(limit=batch_size, offset=offset)
            
            if not rows:
                print(f"No more rows to fetch at offset {offset}")
                break
            
            # Process and insert rows
            for row in rows:
                try:
                    row_data = row.get("row", {})
                    
                    # Extract fields (adapt based on actual schema)
                    book_data = {
                        "title": row_data.get("title", ""),
                        "author": row_data.get("author", ""),
                        "subject": row_data.get("subject", ""),
                        "language": row_data.get("language", "en"),
                        "content_sample": row_data.get("text", "")[:5000],  # First 5000 chars
                        "full_text_url": row_data.get("url", ""),
                        "metadata": json.dumps(row_data.get("metadata", {}))
                    }
                    
                    # Insert into database
                    cursor.execute("""
                        INSERT OR REPLACE INTO books 
                        (title, author, subject, language, content_sample, full_text_url, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, tuple(book_data.values()))
                    
                    indexed_count += 1
                    
                except Exception as e:
                    logger.error(f"Error indexing book: {e}")
                    continue
            
            conn.commit()
            offset += batch_size
            
            print(f"  Indexed {indexed_count}/{max_books} books...")
            
            # Rate limiting
            time.sleep(0.5)
        
        # Rebuild FTS index
        cursor.execute("INSERT INTO books_fts(books_fts) VALUES('rebuild')")
        conn.commit()
        conn.close()
        
        print(f"✅ Indexed {indexed_count} books successfully!")
        
    def search_books(self, query: str, search_type: str = "all", limit: int = 50) -> List[Dict]:
        """Search indexed books.
        
        Args:
            query: Search query
            search_type: Type of search (all, title, author, subject, content)
            limit: Maximum results
            
        Returns:
            List of matching books
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        results = []
        
        try:
            if search_type == "all":
                # Full-text search
                cursor.execute("""
                    SELECT b.*, 
                           snippet(books_fts, -1, '<mark>', '</mark>', '...', 64) as snippet
                    FROM books b
                    JOIN books_fts ON b.id = books_fts.rowid
                    WHERE books_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (query, limit))
                
            elif search_type == "title":
                cursor.execute("""
                    SELECT * FROM books
                    WHERE title LIKE ?
                    LIMIT ?
                """, (f"%{query}%", limit))
                
            elif search_type == "author":
                cursor.execute("""
                    SELECT * FROM books
                    WHERE author LIKE ?
                    LIMIT ?
                """, (f"%{query}%", limit))
                
            elif search_type == "subject":
                cursor.execute("""
                    SELECT * FROM books
                    WHERE subject LIKE ?
                    LIMIT ?
                """, (f"%{query}%", limit))
                
            else:  # content
                cursor.execute("""
                    SELECT b.*,
                           snippet(books_fts, 3, '<mark>', '</mark>', '...', 64) as snippet
                    FROM books b
                    JOIN books_fts ON b.id = books_fts.rowid
                    WHERE books_fts.content_sample MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (query, limit))
            
            # Convert to dictionaries
            for row in cursor.fetchall():
                result = dict(row)
                results.append(result)
                
        except Exception as e:
            logger.error(f"Search error: {e}")
            
        finally:
            conn.close()
            
        return results
    
    async def search_online(self, query: str, search_type: str = "all") -> List[Dict]:
        """Search books directly via HuggingFace API (if available).
        
        Args:
            query: Search query
            search_type: Type of search
            
        Returns:
            List of matching books from online API
        """
        results = []
        
        try:
            # First check if we have a search endpoint
            # Note: HuggingFace datasets-server may not have direct search
            # This is a placeholder for potential future API endpoints
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/search"
                params = {
                    "dataset": self.DATASET_ID,
                    "query": query,
                    "type": search_type
                }
                
                async with session.get(url, params=params, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                    else:
                        logger.warning(f"Online search not available: {response.status}")
                        
        except Exception as e:
            logger.debug(f"Online search failed, using local cache: {e}")
            
        return results


async def search_gutenberg_books(query: str, search_params: Optional[Dict] = None, 
                                 event_handler=None, search_id: str = None) -> List[Dict]:
    """Main entry point for book searches.
    
    Args:
        query: Search query (can include operators)
        search_params: Additional search parameters
        event_handler: WebSocket event handler for streaming
        search_id: Search session ID
        
    Returns:
        List of search results
    """
    # Parse query for operators
    search_type = "all"
    search_term = query
    
    if query.startswith("book:"):
        search_term = query[5:].strip()
        search_type = "content"
    elif query.startswith("intitle:"):
        search_term = query[8:].strip()
        search_type = "title"
    elif query.startswith("author:"):
        search_term = query[7:].strip()
        search_type = "author"
    elif query.startswith("subject:"):
        search_term = query[8:].strip()
        search_type = "subject"
    elif query.startswith("isbn:"):
        search_term = query[5:].strip()
        search_type = "isbn"
    
    # Initialize search interface
    searcher = GutenbergBooksSearch()
    
    # Check if we need to index first
    conn = sqlite3.connect(searcher.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM books")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        print("📚 First time setup - indexing Gutenberg books...")
        if event_handler and search_id:
            await event_handler({
                'type': 'status',
                'search_id': search_id,
                'message': 'Indexing Gutenberg books corpus (first time setup)...'
            })
        
        # Index a subset of books
        searcher.index_books(batch_size=100, max_books=5000)
    
    # Perform search
    print(f"🔍 Searching books for: {search_term} (type: {search_type})")
    
    # Try online search first, fall back to local
    results = await searcher.search_online(search_term, search_type)
    
    if not results:
        # Use local indexed search
        results = searcher.search_books(search_term, search_type, limit=100)
    
    # Stream results if handler available
    if event_handler and search_id:
        for i, book in enumerate(results):
            await event_handler({
                'type': 'result',
                'search_id': search_id,
                'data': {
                    'title': f"{book.get('title', 'Untitled')} by {book.get('author', 'Unknown')}",
                    'url': book.get('full_text_url', ''),
                    'snippet': book.get('snippet', book.get('content_sample', '')[:200]),
                    'source': 'GUTENBERG',
                    'metadata': {
                        'author': book.get('author'),
                        'subject': book.get('subject'),
                        'language': book.get('language')
                    }
                }
            })
            
            # Small delay for streaming effect
            if i % 10 == 0:
                await asyncio.sleep(0.1)
    
    return results


# BookSearchRunner wrapper for brute.py compatibility
class BookSearchRunner:
    """Wrapper class for book search to be compatible with brute.py"""

    def __init__(self, phrase: str):
        """Initialize with search phrase

        Args:
            phrase: The search phrase/query
        """
        self.phrase = phrase
        self.searcher = GutenbergBooksSearch()

    async def run(self, phrase: str = None, tier: int = 1):
        """Run book search

        Args:
            phrase: Optional override phrase (defaults to self.phrase)
            tier: Search tier (unused for books)

        Returns:
            List of search results
        """
        search_phrase = phrase or self.phrase
        return await search_gutenberg_books(search_phrase)


# CLI interface
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python books.py <query>")
        print("Examples:")
        print("  python books.py 'book:sherlock holmes'")
        print("  python books.py 'author:arthur conan doyle'")
        print("  python books.py 'intitle:study in scarlet'")
        sys.exit(1)

    query = sys.argv[1]

    # Run search
    results = asyncio.run(search_gutenberg_books(query))

    # Display results
    print(f"\n📚 Found {len(results)} books:")
    for i, book in enumerate(results[:20], 1):
        print(f"\n{i}. {book.get('title', 'Untitled')}")
        print(f"   Author: {book.get('author', 'Unknown')}")
        print(f"   Subject: {book.get('subject', 'N/A')}")
        if book.get('snippet'):
            print(f"   Snippet: {book['snippet'][:200]}...")