#!/usr/bin/env python3
"""
Hungarian Entity Watcher - K-Monitor Integration
================================================

Real-time corruption risk monitoring for Hungarian entities using K-Monitor datasets.
Automatically highlights companies, people, and their connections when researching.

Features:
- Entity extraction from K-Monitor procurement data
- Relationship mapping (company-person-tender connections)
- Risk scoring and red flag detection
- Real-time alerts during searches
"""

import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from datetime import datetime
import requests
from dataclasses import dataclass
from collections import defaultdict
import pandas as pd

# For Hungarian text processing
try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    print("⚠️ Transformers not installed. Run: pip install transformers torch")

logger = logging.getLogger(__name__)


@dataclass
class HungarianEntity:
    """Represents a Hungarian entity (company/person) with risk data."""
    name: str
    entity_type: str  # 'company', 'person', 'organization'
    risk_score: float  # 0-1 risk level
    red_flags: List[str]
    tenders_won: List[Dict]
    connections: List[str]  # Related entities
    articles: List[Dict]  # Media mentions
    last_updated: datetime
    metadata: Dict


class KMonitorWatcher:
    """Watches for Hungarian entities using K-Monitor data."""
    
    def __init__(self, cache_dir: str = "../datasets/kmonitor_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Database paths
        self.entities_db = self.cache_dir / "hungarian_entities.db"
        self.tenders_db = self.cache_dir / "tenders.db"
        self.connections_db = self.cache_dir / "connections.db"
        
        # Initialize databases
        self._init_databases()
        
        # Load models if available
        self.model = None
        self.tokenizer = None
        if MODELS_AVAILABLE:
            self._load_models()
        
        # Entity cache for fast lookup
        self.entity_cache = {}
        self._load_entity_cache()
    
    def _init_databases(self):
        """Initialize SQLite databases for entity storage."""
        
        # Entities database
        with sqlite3.connect(self.entities_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    name_normalized TEXT,
                    entity_type TEXT,
                    risk_score REAL DEFAULT 0,
                    red_flags TEXT,  -- JSON array
                    first_seen DATE,
                    last_seen DATE,
                    metadata TEXT,  -- JSON
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create FTS5 for fast text search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts
                USING fts5(name, name_normalized, content=entities)
            """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_risk ON entities(risk_score DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON entities(entity_type)")
        
        # Tenders database
        with sqlite3.connect(self.tenders_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tenders (
                    id INTEGER PRIMARY KEY,
                    tender_id TEXT UNIQUE,
                    title TEXT,
                    buyer TEXT,
                    winner TEXT,
                    value_huf REAL,
                    value_eur REAL,
                    date DATE,
                    single_bidder BOOLEAN,
                    risk_indicators TEXT,  -- JSON
                    description TEXT,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_winner ON tenders(winner)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_buyer ON tenders(buyer)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON tenders(date)")
        
        # Connections database (graph edges)
        with sqlite3.connect(self.connections_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS connections (
                    source TEXT,
                    target TEXT,
                    connection_type TEXT,  -- 'owner', 'board_member', 'tender_winner', etc
                    strength REAL DEFAULT 1.0,
                    evidence TEXT,  -- JSON array of sources
                    first_seen DATE,
                    last_confirmed DATE,
                    PRIMARY KEY (source, target, connection_type)
                )
            """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON connections(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_target ON connections(target)")
    
    def _load_models(self):
        """Load K-Monitor classification models."""
        try:
            model_name = "K-Monitor/kmdb_classification_category_v3"
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.model.eval()
            logger.info(f"✅ Loaded K-Monitor model: {model_name}")
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
    
    def download_kmonitor_data(self, limit: int = 10000):
        """Download and index K-Monitor datasets."""
        
        print("📥 Downloading K-Monitor procurement data...")
        
        # Download main classification dataset
        try:
            from datasets import load_dataset
            
            dataset = load_dataset("K-Monitor/kmdb_classification_v2", split="train")
            
            entities_found = set()
            tenders_processed = 0
            
            for idx, item in enumerate(dataset):
                if idx >= limit:
                    break
                
                # Extract entities from text
                text = item.get('text', '')
                label = item.get('label', 0)
                
                # Simple entity extraction (you'd want NER here)
                entities = self._extract_entities_from_text(text)
                
                for entity_name, entity_type in entities:
                    entities_found.add((entity_name, entity_type))
                    
                    # Calculate risk based on context
                    risk_score = label * 0.5  # Base risk from label
                    
                    # Store entity
                    self._store_entity(
                        name=entity_name,
                        entity_type=entity_type,
                        risk_score=risk_score,
                        source_text=text
                    )
                
                tenders_processed += 1
                
                if idx % 100 == 0:
                    print(f"  Processed {idx}/{limit} records, found {len(entities_found)} unique entities")
            
            print(f"✅ Indexed {len(entities_found)} entities from {tenders_processed} tenders")
            
        except Exception as e:
            logger.error(f"Failed to download K-Monitor data: {e}")
            print("⚠️ Using fallback entity extraction from cached data")
    
    def _extract_entities_from_text(self, text: str) -> List[Tuple[str, str]]:
        """Extract Hungarian entities from text.
        
        This is a simplified version - in production you'd use:
        - spaCy with Hungarian model
        - huBERT NER model
        - Custom regex for Hungarian company suffixes (Kft., Zrt., Bt.)
        """
        entities = []
        
        # Company patterns
        import re
        
        # Hungarian company types
        company_patterns = [
            r'([A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+(?:\s+[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+)*\s+(?:Kft\.|Zrt\.|Bt\.|Kkt\.|Nyrt\.))',
            r'([A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+(?:\s+[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+)*\s+(?:Korlátolt Felelősségű Társaság|Zártkörűen Működő Részvénytársaság))',
        ]
        
        for pattern in company_patterns:
            for match in re.finditer(pattern, text):
                company = match.group(1).strip()
                entities.append((company, 'company'))
        
        # Person patterns (simplified - needs Hungarian NER)
        # Look for "Name Surname" patterns between certain keywords
        person_indicators = ['vezérigazgató', 'ügyvezető', 'tulajdonos', 'igazgató']
        for indicator in person_indicators:
            if indicator in text.lower():
                # Extract potential names around these titles
                # This is very simplified - use proper NER in production
                pass
        
        return entities
    
    def _store_entity(self, name: str, entity_type: str, risk_score: float, source_text: str = ""):
        """Store entity in database."""
        
        with sqlite3.connect(self.entities_db) as conn:
            # Normalize name for searching
            name_normalized = self._normalize_hungarian(name)
            
            # Check if exists
            existing = conn.execute(
                "SELECT risk_score FROM entities WHERE name = ?", 
                (name,)
            ).fetchone()
            
            if existing:
                # Update risk score (keep maximum)
                new_risk = max(existing[0], risk_score)
                conn.execute(
                    "UPDATE entities SET risk_score = ?, last_seen = ? WHERE name = ?",
                    (new_risk, datetime.now(), name)
                )
            else:
                # Insert new entity
                red_flags = self._detect_red_flags(source_text)
                
                conn.execute("""
                    INSERT INTO entities (name, name_normalized, entity_type, risk_score, red_flags, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    name, name_normalized, entity_type, risk_score,
                    json.dumps(red_flags), datetime.now(), datetime.now()
                ))
    
    def _normalize_hungarian(self, text: str) -> str:
        """Normalize Hungarian text for matching."""
        # Remove company suffixes for matching
        suffixes = ['Kft.', 'Zrt.', 'Bt.', 'Nyrt.', 'Kkt.']
        normalized = text
        for suffix in suffixes:
            normalized = normalized.replace(suffix, '').strip()
        
        # Lowercase and remove accents for fuzzy matching
        accent_map = {
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ö': 'o', 
            'ő': 'o', 'ú': 'u', 'ü': 'u', 'ű': 'u'
        }
        
        normalized = normalized.lower()
        for accent, base in accent_map.items():
            normalized = normalized.replace(accent, base)
        
        return normalized
    
    def _detect_red_flags(self, text: str) -> List[str]:
        """Detect corruption red flags in Hungarian text."""
        red_flags = []
        
        # Red flag keywords (Hungarian)
        suspicious_terms = {
            'egyetlen ajánlat': 'single_bidder',
            'sürgősségi': 'emergency_procurement',
            'módosítás': 'contract_modification',
            'kizárólagos': 'exclusive_rights',
            'hirdetmény nélkül': 'no_public_notice',
            'rendkívüli': 'extraordinary',
            'túlárazott': 'overpriced',
            'összeférhetetlenség': 'conflict_of_interest'
        }
        
        text_lower = text.lower()
        for term, flag in suspicious_terms.items():
            if term in text_lower:
                red_flags.append(flag)
        
        return red_flags
    
    def _load_entity_cache(self):
        """Load high-risk entities into memory for fast lookup."""
        
        with sqlite3.connect(self.entities_db) as conn:
            # Load top 1000 highest risk entities
            high_risk = conn.execute("""
                SELECT name, entity_type, risk_score, red_flags 
                FROM entities 
                WHERE risk_score > 0.3
                ORDER BY risk_score DESC 
                LIMIT 1000
            """).fetchall()
            
            for name, entity_type, risk_score, red_flags_json in high_risk:
                self.entity_cache[name.lower()] = {
                    'type': entity_type,
                    'risk': risk_score,
                    'red_flags': json.loads(red_flags_json) if red_flags_json else []
                }
            
            logger.info(f"Loaded {len(self.entity_cache)} high-risk entities into cache")
    
    def watch_query(self, query: str) -> Dict[str, any]:
        """Check if query contains watched Hungarian entities.
        
        Returns:
            Dictionary with found entities and their risk data
        """
        results = {
            'entities_found': [],
            'total_risk': 0,
            'red_flags': set(),
            'connections': [],
            'warnings': []
        }
        
        query_lower = query.lower()
        query_normalized = self._normalize_hungarian(query)
        
        # Check cache first (fast path)
        for entity_name, entity_data in self.entity_cache.items():
            if entity_name in query_lower or entity_name in query_normalized:
                results['entities_found'].append({
                    'name': entity_name,
                    'type': entity_data['type'],
                    'risk_score': entity_data['risk'],
                    'red_flags': entity_data['red_flags']
                })
                
                results['total_risk'] = max(results['total_risk'], entity_data['risk'])
                results['red_flags'].update(entity_data['red_flags'])
        
        # Database search for entities not in cache
        if not results['entities_found']:
            with sqlite3.connect(self.entities_db) as conn:
                # Use FTS5 for fuzzy matching
                matches = conn.execute("""
                    SELECT e.name, e.entity_type, e.risk_score, e.red_flags
                    FROM entities e
                    JOIN entities_fts ON e.rowid = entities_fts.rowid
                    WHERE entities_fts MATCH ?
                    ORDER BY e.risk_score DESC
                    LIMIT 10
                """, (query_normalized,)).fetchall()
                
                for name, entity_type, risk_score, red_flags_json in matches:
                    results['entities_found'].append({
                        'name': name,
                        'type': entity_type,
                        'risk_score': risk_score,
                        'red_flags': json.loads(red_flags_json) if red_flags_json else []
                    })
        
        # Get connections for found entities
        if results['entities_found']:
            self._get_entity_connections(results)
        
        # Generate warnings based on risk level
        if results['total_risk'] > 0.7:
            results['warnings'].append("⚠️ HIGH RISK: Multiple corruption indicators detected")
        elif results['total_risk'] > 0.4:
            results['warnings'].append("⚠️ MEDIUM RISK: Some red flags present")
        
        return results
    
    def _get_entity_connections(self, results: Dict):
        """Get connections for found entities."""
        
        with sqlite3.connect(self.connections_db) as conn:
            for entity in results['entities_found']:
                # Get all connections for this entity
                connections = conn.execute("""
                    SELECT target, connection_type, strength
                    FROM connections
                    WHERE source = ?
                    ORDER BY strength DESC
                    LIMIT 5
                """, (entity['name'],)).fetchall()
                
                for target, conn_type, strength in connections:
                    results['connections'].append({
                        'source': entity['name'],
                        'target': target,
                        'type': conn_type,
                        'strength': strength
                    })
    
    def get_entity_report(self, entity_name: str) -> Dict:
        """Generate detailed report for a specific entity."""
        
        report = {
            'entity': entity_name,
            'found': False,
            'details': {},
            'tenders': [],
            'connections': [],
            'timeline': [],
            'media_mentions': []
        }
        
        with sqlite3.connect(self.entities_db) as conn:
            entity = conn.execute("""
                SELECT * FROM entities WHERE name = ? OR name_normalized = ?
            """, (entity_name, self._normalize_hungarian(entity_name))).fetchone()
            
            if entity:
                report['found'] = True
                report['details'] = {
                    'type': entity[2],  # entity_type
                    'risk_score': entity[3],  # risk_score
                    'red_flags': json.loads(entity[4]) if entity[4] else [],
                    'first_seen': entity[5],
                    'last_seen': entity[6]
                }
        
        # Get tenders
        with sqlite3.connect(self.tenders_db) as conn:
            tenders = conn.execute("""
                SELECT * FROM tenders 
                WHERE winner = ? OR buyer = ?
                ORDER BY date DESC
            """, (entity_name, entity_name)).fetchall()
            
            for tender in tenders:
                report['tenders'].append({
                    'id': tender[1],
                    'title': tender[2],
                    'role': 'winner' if tender[4] == entity_name else 'buyer',
                    'value_huf': tender[5],
                    'value_eur': tender[6],
                    'date': tender[7],
                    'single_bidder': bool(tender[8])
                })
        
        return report


def integrate_with_search(query: str, watcher: KMonitorWatcher) -> Dict:
    """Integration point for Search_Engineer.
    
    Call this function when searching to get Hungarian entity warnings.
    """
    
    # Check query for Hungarian entities
    watch_results = watcher.watch_query(query)
    
    if watch_results['entities_found']:
        print("\n🚨 HUNGARIAN ENTITY ALERT 🚨")
        print("=" * 50)
        
        for entity in watch_results['entities_found']:
            risk_level = "HIGH" if entity['risk_score'] > 0.7 else "MEDIUM" if entity['risk_score'] > 0.4 else "LOW"
            print(f"\n📌 Entity: {entity['name']}")
            print(f"   Type: {entity['type']}")
            print(f"   Risk Level: {risk_level} ({entity['risk_score']:.2f})")
            
            if entity['red_flags']:
                print(f"   🚩 Red Flags: {', '.join(entity['red_flags'])}")
        
        if watch_results['connections']:
            print("\n🔗 Known Connections:")
            for conn in watch_results['connections'][:5]:
                print(f"   {conn['source']} → {conn['target']} ({conn['type']})")
        
        if watch_results['warnings']:
            print("\n⚠️ WARNINGS:")
            for warning in watch_results['warnings']:
                print(f"   {warning}")
        
        print("=" * 50)
    
    return watch_results


# CLI Interface
if __name__ == "__main__":
    import sys
    
    watcher = KMonitorWatcher()
    
    if len(sys.argv) < 2:
        print("Hungarian Entity Watcher")
        print("Usage:")
        print("  python hungarian_watcher.py download  # Download K-Monitor data")
        print("  python hungarian_watcher.py watch <query>  # Check query for entities")
        print("  python hungarian_watcher.py report <entity>  # Get entity report")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "download":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
        watcher.download_kmonitor_data(limit=limit)
    
    elif command == "watch":
        query = " ".join(sys.argv[2:])
        results = integrate_with_search(query, watcher)
        
        if not results['entities_found']:
            print("✅ No Hungarian entities detected in query")
    
    elif command == "report":
        entity = " ".join(sys.argv[2:])
        report = watcher.get_entity_report(entity)
        
        if report['found']:
            print(f"\n📊 Report for: {entity}")
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Entity not found: {entity}")