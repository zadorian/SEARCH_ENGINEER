"""
Reverse Embedding Storage

SQLite storage for related queries, suggested searches, and People Also Ask data.
Enables query expansion and search intent reverse engineering.
"""

import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Default storage location
DEFAULT_DB_PATH = Path("/data/SEARCH_ENGINEER/modules/brute/reverse_embedding/reverse_embeddings.db")


class ReverseEmbeddingStorage:
    """
    SQLite storage for reverse embedding data from search engines.
    
    Stores:
    - Related queries (suggestions from search engines)
    - People Also Ask questions
    - Search suggestions/autocomplete
    - Query-to-query relationships for expansion
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Main queries table - original search queries
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                normalized_query TEXT NOT NULL,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                search_count INTEGER DEFAULT 1,
                UNIQUE(normalized_query)
            )
        """)
        
        # Related queries from search results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS related_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_query_id INTEGER NOT NULL,
                related_query TEXT NOT NULL,
                normalized_related TEXT NOT NULL,
                source_engine TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                position INTEGER,
                confidence REAL DEFAULT 1.0,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                occurrence_count INTEGER DEFAULT 1,
                FOREIGN KEY (source_query_id) REFERENCES queries(id),
                UNIQUE(source_query_id, normalized_related, source_engine, relation_type)
            )
        """)
        
        # People Also Ask questions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS people_also_ask (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_query_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT,
                answer_url TEXT,
                source_engine TEXT NOT NULL,
                position INTEGER,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_query_id) REFERENCES queries(id),
                UNIQUE(source_query_id, question, source_engine)
            )
        """)
        
        # Raw JSON storage for full responses
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_query_id INTEGER NOT NULL,
                source_engine TEXT NOT NULL,
                response_type TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_query_id) REFERENCES queries(id)
            )
        """)
        
        # Indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queries_normalized ON queries(normalized_query)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_related_source ON related_queries(source_query_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_related_engine ON related_queries(source_engine)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_paa_source ON people_also_ask(source_query_id)")
        
        conn.commit()
        conn.close()
        logger.info(f"Initialized reverse embedding storage at {self.db_path}")
    
    def _normalize_query(self, query: str) -> str:
        """Normalize query for deduplication."""
        return query.lower().strip().replace('"', '').replace("'", "")
    
    def get_or_create_query(self, query: str) -> int:
        """Get or create a query record, return query_id."""
        normalized = self._normalize_query(query)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Try to find existing
        cursor.execute(
            "SELECT id FROM queries WHERE normalized_query = ?",
            (normalized,)
        )
        row = cursor.fetchone()
        
        if row:
            query_id = row[0]
            # Update last_seen and count
            cursor.execute(
                "UPDATE queries SET last_seen = ?, search_count = search_count + 1 WHERE id = ?",
                (datetime.now().isoformat(), query_id)
            )
        else:
            cursor.execute(
                "INSERT INTO queries (query, normalized_query) VALUES (?, ?)",
                (query, normalized)
            )
            query_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        return query_id
    
    def store_related_queries(
        self,
        source_query: str,
        related_queries: List[str],
        source_engine: str,
        relation_type: str = "related"
    ) -> int:
        """
        Store related queries from a search result.
        
        Args:
            source_query: The original search query
            related_queries: List of related query strings
            source_engine: Engine that provided these (AP, GO, BI, etc.)
            relation_type: Type of relation (related, suggested, autocomplete)
        
        Returns:
            Number of new relations stored
        """
        query_id = self.get_or_create_query(source_query)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        stored = 0
        for position, related in enumerate(related_queries):
            if not related or not related.strip():
                continue
                
            normalized = self._normalize_query(related)
            try:
                cursor.execute("""
                    INSERT INTO related_queries 
                    (source_query_id, related_query, normalized_related, source_engine, relation_type, position)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_query_id, normalized_related, source_engine, relation_type) 
                    DO UPDATE SET 
                        last_seen = CURRENT_TIMESTAMP,
                        occurrence_count = occurrence_count + 1,
                        position = MIN(position, excluded.position)
                """, (query_id, related, normalized, source_engine, relation_type, position))
                stored += 1
            except Exception as e:
                logger.warning(f"Error storing related query '{related}': {e}")
        
        conn.commit()
        conn.close()
        logger.debug(f"Stored {stored} related queries for '{source_query}' from {source_engine}")
        return stored
    
    def store_people_also_ask(
        self,
        source_query: str,
        paa_items: List[Dict[str, Any]],
        source_engine: str
    ) -> int:
        """
        Store People Also Ask questions.
        
        Args:
            source_query: The original search query
            paa_items: List of PAA dicts with 'question', 'answer', 'url'
            source_engine: Engine that provided these
        
        Returns:
            Number of PAA items stored
        """
        query_id = self.get_or_create_query(source_query)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        stored = 0
        for position, item in enumerate(paa_items):
            question = item.get('question') or item.get('title', '')
            if not question:
                continue
                
            answer = item.get('answer') or item.get('snippet', '')
            url = item.get('url') or item.get('link', '')
            
            try:
                cursor.execute("""
                    INSERT INTO people_also_ask 
                    (source_query_id, question, answer, answer_url, source_engine, position)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_query_id, question, source_engine) 
                    DO UPDATE SET 
                        last_seen = CURRENT_TIMESTAMP,
                        answer = COALESCE(excluded.answer, answer),
                        answer_url = COALESCE(excluded.answer_url, answer_url)
                """, (query_id, question, answer, url, source_engine, position))
                stored += 1
            except Exception as e:
                logger.warning(f"Error storing PAA '{question}': {e}")
        
        conn.commit()
        conn.close()
        logger.debug(f"Stored {stored} PAA items for '{source_query}' from {source_engine}")
        return stored
    
    def store_raw_response(
        self,
        source_query: str,
        source_engine: str,
        response_type: str,
        raw_data: Any
    ):
        """Store raw JSON response for later analysis."""
        query_id = self.get_or_create_query(source_query)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO raw_responses (source_query_id, source_engine, response_type, raw_json)
            VALUES (?, ?, ?, ?)
        """, (query_id, source_engine, response_type, json.dumps(raw_data)))
        
        conn.commit()
        conn.close()
    
    def get_related_queries(
        self,
        query: str,
        limit: int = 50,
        min_occurrences: int = 1
    ) -> List[Dict[str, Any]]:
        """Get all related queries for expansion."""
        normalized = self._normalize_query(query)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                rq.related_query,
                rq.source_engine,
                rq.relation_type,
                rq.occurrence_count,
                rq.confidence,
                rq.position
            FROM related_queries rq
            JOIN queries q ON rq.source_query_id = q.id
            WHERE q.normalized_query = ?
            AND rq.occurrence_count >= ?
            ORDER BY rq.occurrence_count DESC, rq.position ASC
            LIMIT ?
        """, (normalized, min_occurrences, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'query': row[0],
                'engine': row[1],
                'type': row[2],
                'occurrences': row[3],
                'confidence': row[4],
                'position': row[5]
            })
        
        conn.close()
        return results
    
    def get_expansion_queries(self, query: str, max_expansions: int = 20) -> List[str]:
        """Get unique related queries for search expansion."""
        related = self.get_related_queries(query, limit=max_expansions * 2)
        seen = set()
        expansions = []
        
        for r in related:
            normalized = self._normalize_query(r['query'])
            if normalized not in seen and normalized != self._normalize_query(query):
                seen.add(normalized)
                expansions.append(r['query'])
                if len(expansions) >= max_expansions:
                    break
        
        return expansions
    
    def get_stats(self) -> Dict[str, int]:
        """Get storage statistics."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM queries")
        total_queries = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM related_queries")
        total_related = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM people_also_ask")
        total_paa = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT source_engine) FROM related_queries")
        unique_engines = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_queries': total_queries,
            'total_related': total_related,
            'total_paa': total_paa,
            'unique_engines': unique_engines
        }
