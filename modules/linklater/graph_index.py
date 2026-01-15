"""
LinkLater Graph Index - Link Relationship Tracking

Adapted from: crawling_common/triple_index.py
Original: AllDOM Bridge prototype (Cymonides v1)
Date: 2025-11-30

Provides fast link relationship queries:
- Backlinks (inlinks): Pages linking TO a URL
- Outlinks: Pages linked FROM a URL
- Related pages: Pages with shared link patterns

Performance:
- Backlink queries: <100ms
- Outlink queries: <50ms
- Related page discovery: <200ms

Storage:
- SQLite with WAL mode for concurrent access
- Indexed on source_url and target_url
- URL metadata for titles and domains

Usage:
    from modules.linklater.graph_index import GraphIndex

    graph = GraphIndex(graph_dir='linklater_data/graph')

    # Add URL with outlinks
    graph.add_url(
        url='https://example.com/page',
        domain='example.com',
        title='Example Page',
        outlinks=['https://other.com/link1', 'https://other.com/link2'],
        crawl_date='2024-01-15'
    )

    # Query backlinks
    backlinks = graph.get_inlinks('https://example.com/page', limit=100)
    # Returns: [(source_url, title, domain), ...]

    # Query outlinks
    outlinks = graph.get_outlinks('https://example.com/page')
    # Returns: [(target_url, anchor_text), ...]

    # Find related pages
    related = graph.get_related_by_links('https://example.com/page', top_k=20)
    # Returns: [(related_url, title, shared_link_count), ...]
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class GraphIndex:
    """
    Graph-based link analysis index.

    Stores inlinks and outlinks for each URL.
    Enables finding:
    - Pages linking to a URL (backlinks)
    - Pages linked from a URL (outlinks)
    - Related pages (shared links)
    """

    def __init__(self, graph_dir: str = 'linklater_data/graph'):
        """
        Initialize graph index.

        Args:
            graph_dir: Directory for graph database
        """
        self.graph_dir = Path(graph_dir)
        self.graph_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.graph_dir / 'links.db'
        self.conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False
        )

        # Enable WAL mode for better concurrent access
        self.conn.execute('PRAGMA journal_mode=WAL')

        self._create_schema()

        logger.info(f"GraphIndex initialized at {self.graph_dir}")

    def _create_schema(self):
        """Create graph schema."""
        # Links table: source_url → target_url
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS links (
                source_url TEXT NOT NULL,
                target_url TEXT NOT NULL,
                anchor_text TEXT,
                crawl_date TEXT,
                PRIMARY KEY (source_url, target_url)
            )
        ''')

        # Indexes for fast lookup
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_source ON links(source_url)
        ''')

        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_target ON links(target_url)
        ''')

        # URL metadata
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS url_metadata (
                url TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                title TEXT,
                crawl_date TEXT
            )
        ''')

        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_domain ON url_metadata(domain)
        ''')

        self.conn.commit()
        logger.debug("Graph schema created/verified")

    def add_url(
        self,
        url: str,
        domain: str,
        title: str,
        outlinks: List[str],
        crawl_date: str,
        anchor_texts: Optional[Dict[str, str]] = None
    ):
        """
        Add URL with its outlinks.

        Args:
            url: Source URL
            domain: Domain name
            title: Page title
            outlinks: List of URLs this page links to
            crawl_date: ISO date string (YYYY-MM-DD)
            anchor_texts: Optional dict mapping target_url -> anchor_text
        """
        # Store URL metadata
        self.conn.execute(
            '''INSERT OR REPLACE INTO url_metadata (url, domain, title, crawl_date)
               VALUES (?, ?, ?, ?)''',
            (url, domain, title, crawl_date)
        )

        # Store outlinks
        for target in outlinks:
            anchor_text = anchor_texts.get(target) if anchor_texts else None

            self.conn.execute(
                '''INSERT OR REPLACE INTO links (source_url, target_url, anchor_text, crawl_date)
                   VALUES (?, ?, ?, ?)''',
                (url, target, anchor_text, crawl_date)
            )

        self.conn.commit()
        logger.debug(f"Added {len(outlinks)} outlinks for {url}")

    def add_urls_batch(self, urls_data: List[Dict]):
        """
        Add multiple URLs in batch for better performance.

        Args:
            urls_data: List of dicts with keys:
                      {url, domain, title, outlinks, crawl_date, anchor_texts}
        """
        # Batch insert metadata
        metadata_rows = [
            (data['url'], data['domain'], data['title'], data['crawl_date'])
            for data in urls_data
        ]

        self.conn.executemany(
            '''INSERT OR REPLACE INTO url_metadata (url, domain, title, crawl_date)
               VALUES (?, ?, ?, ?)''',
            metadata_rows
        )

        # Batch insert links
        link_rows = []
        for data in urls_data:
            url = data['url']
            crawl_date = data['crawl_date']
            anchor_texts = data.get('anchor_texts', {})

            for target in data.get('outlinks', []):
                anchor_text = anchor_texts.get(target)
                link_rows.append((url, target, anchor_text, crawl_date))

        if link_rows:
            self.conn.executemany(
                '''INSERT OR REPLACE INTO links (source_url, target_url, anchor_text, crawl_date)
                   VALUES (?, ?, ?, ?)''',
                link_rows
            )

        self.conn.commit()
        logger.info(f"Batch added {len(urls_data)} URLs with {len(link_rows)} links")

    def get_outlinks(self, url: str) -> List[Tuple[str, Optional[str]]]:
        """
        Get URLs this page links to.

        Args:
            url: Source URL

        Returns:
            List of (target_url, anchor_text) tuples
        """
        cursor = self.conn.execute(
            'SELECT target_url, anchor_text FROM links WHERE source_url = ?',
            (url,)
        )
        return cursor.fetchall()

    def get_inlinks(
        self,
        url: str,
        limit: int = 100
    ) -> List[Tuple[str, Optional[str], Optional[str]]]:
        """
        Get URLs linking to this page (backlinks).

        Args:
            url: Target URL
            limit: Maximum number of results

        Returns:
            List of (source_url, title, domain) tuples
        """
        cursor = self.conn.execute('''
            SELECT l.source_url, m.title, m.domain
            FROM links l
            LEFT JOIN url_metadata m ON l.source_url = m.url
            WHERE l.target_url = ?
            ORDER BY m.crawl_date DESC
            LIMIT ?
        ''', (url, limit))
        return cursor.fetchall()

    def get_related_by_links(
        self,
        url: str,
        top_k: int = 20
    ) -> List[Tuple[str, str, int]]:
        """
        Find pages related by shared outlinks.

        Uses link overlap algorithm:
        - Get outlinks of target URL
        - Find other pages linking to same targets
        - Score by number of shared links

        Args:
            url: Target URL
            top_k: Number of results

        Returns:
            List of (related_url, title, shared_link_count) tuples
        """
        # Get outlinks of target URL
        cursor = self.conn.execute(
            'SELECT target_url FROM links WHERE source_url = ?',
            (url,)
        )
        target_outlinks = {row[0] for row in cursor.fetchall()}

        if not target_outlinks:
            logger.debug(f"No outlinks found for {url}")
            return []

        # Find pages with overlapping outlinks
        related_scores = defaultdict(int)

        for target in target_outlinks:
            # Find other pages linking to same target
            cursor = self.conn.execute(
                'SELECT source_url FROM links WHERE target_url = ? AND source_url != ?',
                (target, url)
            )
            for row in cursor.fetchall():
                related_scores[row[0]] += 1

        # Get metadata for top related
        results = []
        for related_url, score in sorted(
            related_scores.items(),
            key=lambda x: -x[1]
        )[:top_k]:
            cursor = self.conn.execute(
                'SELECT title FROM url_metadata WHERE url = ?',
                (related_url,)
            )
            row = cursor.fetchone()
            title = row[0] if row else 'No title'
            results.append((related_url, title, score))

        logger.debug(f"Found {len(results)} related pages for {url}")
        return results

    def get_domain_links(
        self,
        domain: str,
        link_type: str = 'inlinks',
        limit: int = 100
    ) -> List[Tuple[str, str, str]]:
        """
        Get all inlinks or outlinks for a domain.

        Args:
            domain: Target domain
            link_type: 'inlinks' or 'outlinks'
            limit: Maximum results

        Returns:
            List of (url, title, link_url) tuples
        """
        if link_type == 'inlinks':
            # Get all URLs linking TO this domain
            cursor = self.conn.execute('''
                SELECT DISTINCT l.source_url, m.title, l.target_url
                FROM links l
                LEFT JOIN url_metadata m ON l.source_url = m.url
                WHERE l.target_url LIKE ?
                ORDER BY m.crawl_date DESC
                LIMIT ?
            ''', (f'%{domain}%', limit))
        else:
            # Get all URLs linked FROM this domain
            cursor = self.conn.execute('''
                SELECT DISTINCT m.url, m.title, l.target_url
                FROM url_metadata m
                JOIN links l ON m.url = l.source_url
                WHERE m.domain = ?
                ORDER BY m.crawl_date DESC
                LIMIT ?
            ''', (domain, limit))

        return cursor.fetchall()

    def search_urls(
        self,
        query: str,
        limit: int = 50
    ) -> List[Tuple[str, str, str]]:
        """
        Search URLs by title or URL pattern.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of (url, title, domain) tuples
        """
        cursor = self.conn.execute('''
            SELECT url, title, domain
            FROM url_metadata
            WHERE url LIKE ? OR title LIKE ?
            ORDER BY crawl_date DESC
            LIMIT ?
        ''', (f'%{query}%', f'%{query}%', limit))
        return cursor.fetchall()

    def get_stats(self) -> Dict:
        """
        Get graph statistics.

        Returns:
            Dict with total_urls, total_links, total_domains, db_size_mb
        """
        cursor = self.conn.execute('SELECT COUNT(*) FROM url_metadata')
        total_urls = cursor.fetchone()[0]

        cursor = self.conn.execute('SELECT COUNT(*) FROM links')
        total_links = cursor.fetchone()[0]

        cursor = self.conn.execute('SELECT COUNT(DISTINCT domain) FROM url_metadata')
        total_domains = cursor.fetchone()[0]

        db_size_mb = (
            self.db_path.stat().st_size / (1024 * 1024)
            if self.db_path.exists() else 0
        )

        return {
            'total_urls': total_urls,
            'total_links': total_links,
            'total_domains': total_domains,
            'db_size_mb': round(db_size_mb, 2)
        }

    def close(self):
        """Close database connection."""
        self.conn.close()
        logger.info("GraphIndex connection closed")
