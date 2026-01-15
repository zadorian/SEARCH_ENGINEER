#!/usr/bin/env python3
"""
Forensic Document Analyzer
===========================

Combines:
- Document context loading (1M token context from gemini_longtext.py)
- Forensic search capabilities (from Forensic_Gemini)
- Complete conversation logging with JSON persistence
- Search query and reasoning logging
- Session memory (remembers previous searches)

Usage:
    python forensic_document_analyzer.py [file_path]

Commands:
    /search <query>  - Force forensic search mode
    /export          - Export conversation to JSON
    /history         - Show search history
    /file <path>     - Load a new document
    /clear           - Clear conversation history
    /quit            - Exit and save

The tool auto-detects intent:
- Questions about the document → Document Q&A mode
- "search", "find", "investigate", "research" → Forensic search mode
"""

import os
import sys
import json
import uuid
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

# Load environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'python-backend' / 'modules'))
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("google-genai not installed. Install with: pip install google-genai")

# Import forensic components
try:
    from forensic_query_constructor import ForensicQueryBuilder, TokenAnalysis, ForensicQuery
    from forensic_gemini import ForensicScorer, AuthenticityValidator, FORENSIC_MASTER_PROMPT
except ImportError:
    # Fallback if running from different directory
    from brute.engines.Forensic_Gemini.forensic_query_constructor import ForensicQueryBuilder, TokenAnalysis, ForensicQuery
    from brute.engines.Forensic_Gemini.forensic_gemini import ForensicScorer, AuthenticityValidator, FORENSIC_MASTER_PROMPT


# ============================================================================
# CONFIGURATION
# ============================================================================

API_KEY = os.getenv("GOOGLE_API_KEY")
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or "trans-411306"
GCP_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"
MODEL = "gemini-3-pro-preview"  # Main reasoning model
MAX_OUTPUT_TOKENS = 65536

# Claude Haiku for entity/relationship extraction
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
EXTRACTION_MODEL = "claude-haiku-4-5-20251001"  # Fast/cheap extraction model

# File store location - all loaded documents are copied here for persistence
FILE_STORE_DIR = PROJECT_ROOT / 'python-backend' / 'data' / 'forensic_file_store'
FILE_STORE_INDEX = FILE_STORE_DIR / 'index.json'

# Gemini Cloud File Search store name prefix
GEMINI_STORE_PREFIX = "forensic-analyzer"

# Graph storage location
GRAPH_STORE_DIR = PROJECT_ROOT / 'python-backend' / 'data' / 'forensic_graphs'


# ============================================================================
# NOTE: No rigid entity/relationship types - Haiku freely determines them
# ============================================================================


# ============================================================================
# CLAUDE HAIKU GRAPH EXTRACTOR
# ============================================================================

class ClaudeGraphExtractor:
    """
    Extracts entities and relationships from text using Claude Haiku 4.5.

    Outputs JSON nodes and edges for graph storage.
    """

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy load Anthropic client"""
        if self._client is None:
            try:
                import anthropic
                if not ANTHROPIC_API_KEY:
                    raise ValueError("ANTHROPIC_API_KEY not set")
                self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            except ImportError:
                raise ImportError("anthropic not installed. Install with: pip install anthropic")
        return self._client

    def extract_entities(self, text: str, max_chars: int = 10000) -> List[Dict[str, Any]]:
        """Extract entities from text using Claude Haiku 4.5."""

        prompt = f"""Extract ALL entities from this text. Return ONLY valid JSON:
{{
  "entities": [
    {{"type": "YOUR_DETERMINED_TYPE", "value": "exact entity text", "context": "brief context"}}
  ]
}}

You determine the entity types based on what makes sense for this content.
Common types include: person, company, organization, location, address, email, phone,
date, money, event, document, account, vessel, vehicle, product, etc.

But you are FREE to use any type that accurately describes the entity.
Be specific - if it's a "bank" say bank, if it's a "law_firm" say law_firm.

Focus on entities relevant to research/investigation. Be precise.

Text:
{text[:max_chars]}"""

        try:
            response = self.client.messages.create(
                model=EXTRACTION_MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text

            # Parse JSON
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(content[json_start:json_end])
            else:
                return []

            # Dedupe entities
            entities = result.get("entities", [])
            seen = set()
            unique = []
            for ent in entities:
                key = (ent.get("type", "").lower(), ent.get("value", "").strip().lower())
                if key not in seen and len(ent.get("value", "").strip()) > 1:
                    seen.add(key)
                    unique.append({
                        "type": ent.get("type", "unknown").lower(),
                        "value": ent.get("value", "").strip(),
                        "context": ent.get("context", ""),
                        "confidence": 0.85
                    })

            return unique

        except Exception as e:
            print(f"  ⚠️ Entity extraction error: {e}")
            return []

    def extract_relationships(self, text: str, entities: List[Dict], max_chars: int = 10000) -> List[Dict[str, Any]]:
        """Extract relationships between entities using Claude Haiku 4.5."""

        if len(entities) < 2:
            return []

        entity_list = "\n".join([f"- {e['type']}: \"{e['value']}\"" for e in entities[:50]])

        prompt = f"""Given these entities, identify relationships between them.

Entities:
{entity_list}

Return ONLY valid JSON:
{{
  "edges": [
    {{
      "source_type": "entity type",
      "source_value": "Exact entity name",
      "relation": "YOUR_DETERMINED_RELATIONSHIP",
      "target_type": "entity type",
      "target_value": "Exact entity name",
      "confidence": 0.0-1.0,
      "evidence": "Brief quote from text"
    }}
  ]
}}

You determine the relationship types based on what makes sense.
Use clear, descriptive verbs like: works_at, owns, controls, funded_by,
married_to, parent_of, acquired, invested_in, located_at, paid, sent_to, etc.

Be SPECIFIC about the relationship. Don't use generic "related_to" if you
can determine the actual relationship type.

Only include relationships with clear evidence. Use exact entity names.

Source text:
{text[:max_chars]}"""

        try:
            response = self.client.messages.create(
                model=EXTRACTION_MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text

            # Handle markdown JSON
            if "```" in content:
                import re
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
                if json_match:
                    content = json_match.group(1).strip()

            # Parse JSON
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(content[json_start:json_end])
            else:
                return []

            # Validate edges
            edges = result.get("edges", [])
            entity_values = {e["value"].lower() for e in entities}
            validated = []

            for edge in edges:
                source_val = edge.get("source_value", "").strip()
                target_val = edge.get("target_value", "").strip()
                relation = edge.get("relation", "").lower()

                # Skip empty relations
                if not relation:
                    continue

                # Validate entities exist
                if source_val.lower() not in entity_values:
                    continue
                if target_val.lower() not in entity_values:
                    continue

                validated.append({
                    "source_type": edge.get("source_type", "").lower(),
                    "source_value": source_val,
                    "relation": relation,
                    "target_type": edge.get("target_type", "").lower(),
                    "target_value": target_val,
                    "confidence": edge.get("confidence", 0.8),
                    "evidence": edge.get("evidence", "")
                })

            return validated

        except Exception as e:
            print(f"  ⚠️ Relationship extraction error: {e}")
            return []

    def extract_all(self, text: str) -> Dict[str, Any]:
        """Extract both entities and relationships from text."""
        entities = self.extract_entities(text)
        edges = self.extract_relationships(text, entities) if entities else []

        return {
            "entities": entities,
            "edges": edges,
            "entity_count": len(entities),
            "edge_count": len(edges)
        }

    def validate_graph(self, graph: 'ProjectGraph') -> List[Dict[str, Any]]:
        """
        Validate the graph for inconsistencies, contradictions, and errors.
        Returns a list of corrections/warnings for Gemini.
        """
        corrections = []

        # Check for contradictory relationships
        edge_pairs = {}
        for edge in graph.edges:
            key = (edge["source_value"].lower(), edge["target_value"].lower())
            reverse_key = (edge["target_value"].lower(), edge["source_value"].lower())

            # Track relationships between same entities
            edge_pairs.setdefault(key, []).append(edge)
            edge_pairs.setdefault(reverse_key, []).append(edge)

        # Look for conflicts
        for (src, tgt), edges in edge_pairs.items():
            if len(edges) > 1:
                relations = [e["relation"] for e in edges]
                # Check for conflicting ownership
                if "subsidiary_of" in relations and "legal_parent_of" in relations:
                    corrections.append({
                        "type": "conflict",
                        "severity": "high",
                        "message": f"Conflicting ownership: {src} is both subsidiary_of and legal_parent_of {tgt}",
                        "entities": [src, tgt]
                    })

        # Check for entities with unusual patterns
        entity_values = list(graph.entities.values())
        for ent in entity_values:
            # Person names that look like company names
            if ent["type"] == "person" and any(corp in ent["value"].lower()
                for corp in ["corp", "inc", "ltd", "llc", "gmbh", "spa", "ag"]):
                corrections.append({
                    "type": "misclassification",
                    "severity": "medium",
                    "message": f"'{ent['value']}' classified as person but looks like a company name",
                    "entity": ent["value"]
                })

            # Company names that might be person names (very short, no corporate suffix)
            if ent["type"] == "company" and len(ent["value"].split()) <= 2:
                words = ent["value"].split()
                if all(w.isalpha() and w[0].isupper() for w in words):
                    # Could be a person name
                    corrections.append({
                        "type": "possible_misclassification",
                        "severity": "low",
                        "message": f"'{ent['value']}' classified as company but might be a person name",
                        "entity": ent["value"]
                    })

        # Check for duplicate entities with different types
        value_types = {}
        for ent in entity_values:
            val = ent["value"].lower()
            if val in value_types and value_types[val] != ent["type"]:
                corrections.append({
                    "type": "duplicate_different_type",
                    "severity": "medium",
                    "message": f"'{ent['value']}' appears as both {value_types[val]} and {ent['type']}",
                    "entity": ent["value"]
                })
            value_types[val] = ent["type"]

        return corrections

    def get_corrections_prompt(self, corrections: List[Dict[str, Any]]) -> str:
        """Format corrections for inclusion in Gemini's context."""
        if not corrections:
            return ""

        lines = ["## ⚠️ Graph Quality Alerts"]

        high = [c for c in corrections if c.get("severity") == "high"]
        medium = [c for c in corrections if c.get("severity") == "medium"]
        low = [c for c in corrections if c.get("severity") == "low"]

        if high:
            lines.append("\n**High Priority Issues:**")
            for c in high:
                lines.append(f"- ❌ {c['message']}")

        if medium:
            lines.append("\n**Medium Priority Issues:**")
            for c in medium:
                lines.append(f"- ⚠️ {c['message']}")

        if low:
            lines.append("\n**Low Priority (verify):**")
            for c in low[:5]:  # Limit low priority
                lines.append(f"- ℹ️ {c['message']}")

        return "\n".join(lines)


# ============================================================================
# PROJECT GRAPH STORAGE
# ============================================================================

class ProjectGraph:
    """
    Stores entities and relationships as a knowledge graph for a project.

    Provides graph-based context for Gemini instead of full conversation history.
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.store_dir = GRAPH_STORE_DIR / project_id
        self.store_dir.mkdir(parents=True, exist_ok=True)

        self.graph_file = self.store_dir / "graph.json"
        self.context_file = self.store_dir / "context.json"

        self._load_graph()

    def _load_graph(self):
        """Load graph from disk"""
        if self.graph_file.exists():
            try:
                data = json.loads(self.graph_file.read_text())
                self.entities = data.get("entities", {})  # keyed by value
                self.edges = data.get("edges", [])
                self.project_description = data.get("project_description", "")
                self.round_count = data.get("round_count", 0)
            except Exception as e:
                self._init_empty()
        else:
            self._init_empty()

    def _init_empty(self):
        """Initialize empty graph"""
        self.entities = {}  # {value: {type, value, context, mentions}}
        self.edges = []
        self.project_description = ""
        self.round_count = 0

    def _save_graph(self):
        """Save graph to disk"""
        data = {
            "entities": self.entities,
            "edges": self.edges,
            "project_description": self.project_description,
            "round_count": self.round_count,
            "updated_at": datetime.now().isoformat()
        }
        self.graph_file.write_text(json.dumps(data, indent=2))

    def add_entities(self, entities: List[Dict[str, Any]]):
        """Add or update entities in the graph"""
        for ent in entities:
            key = ent["value"].lower()
            if key in self.entities:
                # Update existing - increment mentions
                self.entities[key]["mentions"] = self.entities[key].get("mentions", 1) + 1
                if ent.get("context") and ent["context"] not in self.entities[key].get("contexts", []):
                    self.entities[key].setdefault("contexts", []).append(ent["context"])
            else:
                # New entity
                self.entities[key] = {
                    "type": ent["type"],
                    "value": ent["value"],
                    "context": ent.get("context", ""),
                    "contexts": [ent.get("context", "")] if ent.get("context") else [],
                    "mentions": 1,
                    "first_seen": datetime.now().isoformat()
                }
        self._save_graph()

    def add_edges(self, edges: List[Dict[str, Any]]):
        """Add edges to the graph (deduped)"""
        existing = {
            (e["source_value"].lower(), e["relation"], e["target_value"].lower())
            for e in self.edges
        }

        for edge in edges:
            key = (edge["source_value"].lower(), edge["relation"], edge["target_value"].lower())
            if key not in existing:
                existing.add(key)
                self.edges.append({
                    **edge,
                    "added_at": datetime.now().isoformat()
                })

        self._save_graph()

    def increment_round(self):
        """Increment conversation round counter"""
        self.round_count += 1
        self._save_graph()
        return self.round_count

    def update_project_description(self, description: str):
        """Update project description"""
        self.project_description = description
        self._save_graph()

    def get_context_summary(self, max_entities: int = 30, max_edges: int = 20) -> str:
        """
        Generate a concise context summary for Gemini.

        Returns a markdown summary of the graph suitable for context injection.
        """
        lines = []

        # Project description
        if self.project_description:
            lines.append("## Project Overview")
            lines.append(self.project_description)
            lines.append("")

        # Key entities (sorted by mentions)
        sorted_entities = sorted(
            self.entities.values(),
            key=lambda x: x.get("mentions", 1),
            reverse=True
        )[:max_entities]

        if sorted_entities:
            lines.append("## Key Entities")

            # Group by type
            by_type = {}
            for e in sorted_entities:
                by_type.setdefault(e["type"], []).append(e)

            for etype, ents in sorted(by_type.items()):
                lines.append(f"\n**{etype.title()}s:**")
                for e in ents[:10]:
                    mentions = f" ({e.get('mentions', 1)}x)" if e.get("mentions", 1) > 1 else ""
                    lines.append(f"- {e['value']}{mentions}")

        # Key relationships
        if self.edges:
            lines.append("\n## Key Relationships")
            for edge in self.edges[:max_edges]:
                lines.append(f"- {edge['source_value']} → [{edge['relation']}] → {edge['target_value']}")

        # Stats
        lines.append(f"\n_Graph: {len(self.entities)} entities, {len(self.edges)} relationships_")

        return "\n".join(lines)

    def get_entity_by_name(self, name: str) -> Optional[Dict]:
        """Get an entity by name (case insensitive)"""
        return self.entities.get(name.lower())

    def get_edges_for_entity(self, entity_value: str) -> List[Dict]:
        """Get all edges involving an entity"""
        value_lower = entity_value.lower()
        return [
            e for e in self.edges
            if e["source_value"].lower() == value_lower or e["target_value"].lower() == value_lower
        ]

    def to_json(self) -> Dict[str, Any]:
        """Export graph as JSON"""
        return {
            "project_id": self.project_id,
            "entities": list(self.entities.values()),
            "edges": self.edges,
            "project_description": self.project_description,
            "round_count": self.round_count
        }


# ============================================================================
# GRAPH CONTEXT MANAGER
# ============================================================================

class GraphContextManager:
    """
    Manages graph-based context for Gemini conversations.

    Instead of full conversation history, uses:
    - Graph summary (entities + relationships)
    - Last N exchanges
    - Project description (created at round 2, updated every 10 rounds)
    """

    def __init__(self, project_id: str, extractor: ClaudeGraphExtractor):
        self.graph = ProjectGraph(project_id)
        self.extractor = extractor
        self.recent_exchanges: List[Dict[str, str]] = []  # Last N exchanges
        self.max_recent = 3  # Keep last 3 exchanges

    def process_gemini_response(self, response_text: str, user_query: str):
        """
        Process a Gemini response:
        1. Extract entities and relationships
        2. Add to graph
        3. Update project description if needed
        """
        # Combine user query and response for extraction
        combined = f"User query: {user_query}\n\nResponse:\n{response_text}"

        # Extract entities and edges
        print("  🔍 Extracting entities...")
        extraction = self.extractor.extract_all(combined)

        if extraction["entities"]:
            self.graph.add_entities(extraction["entities"])
            print(f"  ✓ Added {extraction['entity_count']} entities")

        if extraction["edges"]:
            self.graph.add_edges(extraction["edges"])
            print(f"  ✓ Added {extraction['edge_count']} relationships")

        # Store recent exchange
        self.recent_exchanges.append({
            "user": user_query[:500],  # Truncate for storage
            "assistant": response_text[:1000]
        })
        if len(self.recent_exchanges) > self.max_recent:
            self.recent_exchanges.pop(0)

        # Increment round and check if we need project description update
        round_num = self.graph.increment_round()

        if round_num == 2:
            # Create initial project description
            self._generate_project_description("initial")
        elif round_num > 2 and round_num % 10 == 0:
            # Update every 10 rounds
            self._generate_project_description("update")

    def _generate_project_description(self, mode: str):
        """Generate or update project description using Claude Haiku"""
        print(f"  📝 {'Creating' if mode == 'initial' else 'Updating'} project description...")

        entity_summary = ", ".join([
            f"{e['value']} ({e['type']})"
            for e in list(self.graph.entities.values())[:20]
        ])

        edge_summary = ", ".join([
            f"{e['source_value']}→{e['target_value']}"
            for e in self.graph.edges[:10]
        ])

        prompt = f"""Based on these entities and relationships from a forensic investigation, write a brief (2-3 sentence) project description.

Entities: {entity_summary}
Relationships: {edge_summary}

Current description: {self.graph.project_description or 'None yet'}

Write a concise summary of what this investigation appears to be about."""

        try:
            response = self.extractor.client.messages.create(
                model=EXTRACTION_MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            description = response.content[0].text.strip()
            self.graph.update_project_description(description)
            print(f"  ✓ Project description: {description[:100]}...")
        except Exception as e:
            print(f"  ⚠️ Could not generate description: {e}")

    def get_context_for_gemini(self) -> str:
        """
        Build context for Gemini using graph + recent exchanges + corrections.

        This replaces full conversation history with a structured summary.
        """
        parts = []

        # Graph context
        graph_summary = self.graph.get_context_summary()
        if graph_summary:
            parts.append("# Investigation Context")
            parts.append(graph_summary)

        # Check for corrections/issues
        corrections = self.extractor.validate_graph(self.graph)
        if corrections:
            corrections_text = self.extractor.get_corrections_prompt(corrections)
            parts.append(f"\n{corrections_text}")

        # Recent exchanges
        if self.recent_exchanges:
            parts.append("\n# Recent Conversation")
            for ex in self.recent_exchanges[-3:]:
                parts.append(f"\n**User:** {ex['user'][:300]}...")
                parts.append(f"**Assistant:** {ex['assistant'][:500]}...")

        return "\n".join(parts)

    def get_graph(self) -> ProjectGraph:
        """Get the underlying graph"""
        return self.graph


# Intent detection keywords
SEARCH_TRIGGERS = [
    "search", "find", "investigate", "research", "look up", "lookup",
    "discover", "uncover", "trace", "track", "locate", "dig", "explore",
    "what can you find", "search for", "find out", "look into",
    "google", "web search", "online", "internet"
]


# ============================================================================
# FILE STORE MANAGER
# ============================================================================

class FileStoreManager:
    """
    Manages a local file store for documents.
    - Copies loaded files to the store
    - Maintains an index with metadata
    - Allows browsing previously loaded files
    """

    def __init__(self):
        self.store_dir = FILE_STORE_DIR
        self.index_file = FILE_STORE_INDEX
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.index = self._load_index()

    def _load_index(self) -> Dict[str, Any]:
        """Load file index from disk"""
        if self.index_file.exists():
            try:
                return json.loads(self.index_file.read_text())
            except Exception as e:
                return {"files": {}, "last_accessed": None}
        return {"files": {}, "last_accessed": None}

    def _save_index(self):
        """Save file index to disk"""
        self.index_file.write_text(json.dumps(self.index, indent=2))

    def add_file(self, source_path: Path) -> Path:
        """
        Copy a file to the store and index it.
        Returns the path to the stored copy.
        """
        import shutil

        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = source_path.name
        stored_name = f"{timestamp}_{original_name}"
        stored_path = self.store_dir / stored_name

        # Copy file to store
        shutil.copy2(source_path, stored_path)

        # Update index
        file_id = str(uuid.uuid4())[:8]
        self.index["files"][file_id] = {
            "id": file_id,
            "original_name": original_name,
            "original_path": str(source_path),
            "stored_name": stored_name,
            "stored_path": str(stored_path),
            "added_at": datetime.now().isoformat(),
            "last_accessed": datetime.now().isoformat(),
            "size_bytes": stored_path.stat().st_size,
            "access_count": 1
        }
        self.index["last_accessed"] = file_id
        self._save_index()

        print(f"  📁 File copied to store: {stored_name}")
        return stored_path

    def get_file(self, file_id: str) -> Optional[Path]:
        """Get a file from the store by ID"""
        if file_id in self.index["files"]:
            file_info = self.index["files"][file_id]
            stored_path = Path(file_info["stored_path"])
            if stored_path.exists():
                # Update access info
                file_info["last_accessed"] = datetime.now().isoformat()
                file_info["access_count"] = file_info.get("access_count", 0) + 1
                self.index["last_accessed"] = file_id
                self._save_index()
                return stored_path
        return None

    def list_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List files in the store, sorted by last access"""
        files = list(self.index["files"].values())
        # Filter to only existing files
        files = [f for f in files if Path(f["stored_path"]).exists()]
        # Sort by last_accessed descending
        files.sort(key=lambda x: x.get("last_accessed", ""), reverse=True)
        return files[:limit]

    def get_last_accessed(self) -> Optional[Path]:
        """Get the most recently accessed file"""
        if self.index["last_accessed"]:
            return self.get_file(self.index["last_accessed"])
        return None

    def search_files(self, query: str) -> List[Dict[str, Any]]:
        """Search files by name"""
        query_lower = query.lower()
        matches = []
        for file_info in self.index["files"].values():
            if query_lower in file_info["original_name"].lower():
                if Path(file_info["stored_path"]).exists():
                    matches.append(file_info)
        return matches

    def remove_file(self, file_id: str) -> bool:
        """Remove a file from the store"""
        if file_id in self.index["files"]:
            file_info = self.index["files"][file_id]
            stored_path = Path(file_info["stored_path"])
            if stored_path.exists():
                stored_path.unlink()
            del self.index["files"][file_id]
            self._save_index()
            return True
        return False

    def get_store_stats(self) -> Dict[str, Any]:
        """Get statistics about the file store"""
        files = self.list_files(limit=1000)
        total_size = sum(f.get("size_bytes", 0) for f in files)
        return {
            "total_files": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "store_path": str(self.store_dir)
        }


# ============================================================================
# GEMINI CLOUD FILE SEARCH MANAGER
# ============================================================================

class GeminiCloudStore:
    """
    Manages Gemini File Search stores for semantic document search.

    Features:
    - Upload documents to Gemini cloud for RAG-style retrieval
    - Query documents semantically instead of loading full context
    - Free storage, only pay for indexing ($0.15/1M tokens)
    - Automatic chunking and embedding
    """

    def __init__(self, client):
        self.client = client
        self.model = MODEL
        self.store_prefix = GEMINI_STORE_PREFIX
        self._current_store: Optional[str] = None

        # Local index to track cloud stores
        self.cloud_index_file = FILE_STORE_DIR / 'cloud_stores.json'
        self.cloud_index = self._load_cloud_index()

    def _load_cloud_index(self) -> Dict[str, Any]:
        """Load local index of cloud stores"""
        if self.cloud_index_file.exists():
            try:
                return json.loads(self.cloud_index_file.read_text())
            except Exception as e:
                return {"stores": {}, "files": {}}
        return {"stores": {}, "files": {}}

    def _save_cloud_index(self):
        """Save local index of cloud stores"""
        self.cloud_index_file.write_text(json.dumps(self.cloud_index, indent=2))

    def list_stores(self) -> List[Dict[str, Any]]:
        """List all Gemini file search stores"""
        try:
            stores = list(self.client.file_search_stores.list())
            result = []
            for store in stores:
                display_name = getattr(store, 'display_name', None) or store.name
                result.append({
                    "name": store.name,
                    "display_name": display_name,
                    "created": getattr(store, 'create_time', None)
                })
            return result
        except Exception as e:
            print(f"Error listing stores: {e}")
            return []

    def create_store(self, display_name: str) -> Optional[str]:
        """Create a new file search store"""
        try:
            full_name = f"{self.store_prefix}-{display_name}"
            store = self.client.file_search_stores.create(
                config={'display_name': full_name}
            )

            # Track in local index
            self.cloud_index["stores"][store.name] = {
                "display_name": full_name,
                "created_at": datetime.now().isoformat(),
                "files": []
            }
            self._save_cloud_index()

            print(f"✓ Created store: {full_name}")
            print(f"  ID: {store.name}")
            return store.name
        except Exception as e:
            print(f"Error creating store: {e}")
            return None

    def upload_file(self, store_name: str, file_path: Path,
                    max_tokens_per_chunk: int = 2048,
                    max_overlap_tokens: int = 200) -> bool:
        """
        Upload a file to a Gemini file search store.

        Args:
            store_name: The store ID (from create_store)
            file_path: Path to the file to upload
            max_tokens_per_chunk: Chunk size (256-2048)
            max_overlap_tokens: Overlap between chunks (up to 20% of chunk size)
        """
        import time

        try:
            print(f"📤 Uploading to Gemini cloud: {file_path.name}...")

            # Start upload with chunking config
            operation = self.client.file_search_stores.upload_to_file_search_store(
                file=str(file_path),
                file_search_store_name=store_name,
                config={
                    'max_tokens_per_chunk': max_tokens_per_chunk,
                    'max_overlap_tokens': max_overlap_tokens
                }
            )

            # Wait for processing
            while not operation.done:
                print("  ⏳ Processing (creating embeddings)...")
                time.sleep(5)
                operation = self.client.operations.get(operation)

            # Track in local index
            if store_name in self.cloud_index["stores"]:
                self.cloud_index["stores"][store_name]["files"].append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "uploaded_at": datetime.now().isoformat(),
                    "chunk_size": max_tokens_per_chunk
                })

            # Track file → store mapping
            self.cloud_index["files"][str(file_path)] = {
                "store_name": store_name,
                "uploaded_at": datetime.now().isoformat()
            }
            self._save_cloud_index()

            print(f"✓ Upload complete: {file_path.name} → {store_name}")
            return True

        except Exception as e:
            print(f"Error uploading file: {e}")
            return False

    def query(self, store_name: str, query: str, include_citations: bool = True) -> Dict[str, Any]:
        """
        Query a file search store using semantic search.

        Returns:
            Dict with 'response' text and 'citations' list
        """
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=query,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(
                        file_search=types.FileSearch(
                            file_search_store_names=[store_name]
                        )
                    )]
                )
            )

            result = {
                "response": response.text,
                "citations": [],
                "grounding_metadata": None
            }

            # Extract citations from grounding metadata
            if include_citations and hasattr(response, 'candidates'):
                for candidate in response.candidates:
                    if hasattr(candidate, 'grounding_metadata'):
                        metadata = candidate.grounding_metadata
                        result["grounding_metadata"] = str(metadata)

                        # Extract grounding chunks as citations
                        if hasattr(metadata, 'grounding_chunks'):
                            for chunk in metadata.grounding_chunks:
                                citation = {
                                    "text": getattr(chunk, 'text', ''),
                                    "source": getattr(chunk, 'source', '')
                                }
                                result["citations"].append(citation)

            return result

        except Exception as e:
            return {"response": f"Error querying store: {e}", "citations": [], "error": str(e)}

    def get_store_for_file(self, file_path: Path) -> Optional[str]:
        """Check if a file has been uploaded to a cloud store"""
        file_key = str(file_path)
        if file_key in self.cloud_index["files"]:
            return self.cloud_index["files"][file_key]["store_name"]
        return None

    def set_current_store(self, store_name: str):
        """Set the current active store for queries"""
        self._current_store = store_name

    def get_current_store(self) -> Optional[str]:
        """Get the current active store"""
        return self._current_store

    def delete_store(self, store_name: str) -> bool:
        """Delete a file search store"""
        try:
            self.client.file_search_stores.delete(name=store_name)

            # Remove from local index
            if store_name in self.cloud_index["stores"]:
                del self.cloud_index["stores"][store_name]

            # Remove file mappings
            files_to_remove = [f for f, info in self.cloud_index["files"].items()
                             if info.get("store_name") == store_name]
            for f in files_to_remove:
                del self.cloud_index["files"][f]

            self._save_cloud_index()
            print(f"✓ Deleted store: {store_name}")
            return True
        except Exception as e:
            print(f"Error deleting store: {e}")
            return False

    def get_cloud_stats(self) -> Dict[str, Any]:
        """Get statistics about cloud stores"""
        stores = self.list_stores()
        total_files = sum(len(s.get("files", [])) for s in self.cloud_index["stores"].values())
        return {
            "total_stores": len(stores),
            "total_files_uploaded": total_files,
            "current_store": self._current_store
        }


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class SearchRecord:
    """Record of a forensic search"""
    timestamp: str
    query: str
    reasoning: str
    queries_generated: List[Dict[str, Any]]
    tier_distribution: Dict[str, int]
    token_analysis: Optional[Dict[str, Any]] = None
    results_summary: Optional[str] = None


@dataclass
class MessageRecord:
    """Record of a conversation message"""
    timestamp: str
    role: str  # "user" or "assistant"
    content: str
    mode: str  # "document_qa" or "forensic_search"
    search_triggered: bool = False
    search_record: Optional[SearchRecord] = None


@dataclass
class SessionLog:
    """Complete session log for JSON export"""
    session_id: str
    start_time: str
    end_time: Optional[str] = None
    document_loaded: Optional[str] = None
    document_chars: int = 0
    messages: List[MessageRecord] = field(default_factory=list)
    searches: List[SearchRecord] = field(default_factory=list)
    total_queries_generated: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export"""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "document_loaded": self.document_loaded,
            "document_chars": self.document_chars,
            "messages": [asdict(m) if isinstance(m.search_record, SearchRecord) else {
                **asdict(m),
                "search_record": asdict(m.search_record) if m.search_record else None
            } for m in self.messages],
            "searches": [asdict(s) for s in self.searches],
            "total_queries_generated": self.total_queries_generated,
            "statistics": {
                "total_messages": len(self.messages),
                "user_messages": sum(1 for m in self.messages if m.role == "user"),
                "assistant_messages": sum(1 for m in self.messages if m.role == "assistant"),
                "total_searches": len(self.searches),
                "document_qa_count": sum(1 for m in self.messages if m.mode == "document_qa" and m.role == "assistant"),
                "forensic_search_count": sum(1 for m in self.messages if m.mode == "forensic_search" and m.role == "assistant"),
            }
        }


# ============================================================================
# CONVERSATION LOGGER
# ============================================================================

class ConversationLogger:
    """Handles all logging and JSON persistence"""

    def __init__(self):
        self.session = SessionLog(
            session_id=str(uuid.uuid4())[:8],
            start_time=datetime.now().isoformat()
        )
        self.export_dir = PROJECT_ROOT / 'python-backend' / 'data' / 'forensic_sessions'
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def set_document(self, filename: str, char_count: int):
        """Record loaded document"""
        self.session.document_loaded = filename
        self.session.document_chars = char_count

    def log_message(self, role: str, content: str, mode: str = "document_qa",
                    search_triggered: bool = False, search_record: Optional[SearchRecord] = None):
        """Log a conversation message"""
        record = MessageRecord(
            timestamp=datetime.now().isoformat(),
            role=role,
            content=content,
            mode=mode,
            search_triggered=search_triggered,
            search_record=search_record
        )
        self.session.messages.append(record)
        return record

    def log_search(self, query: str, reasoning: str, queries: List[Dict[str, Any]],
                   tier_distribution: Dict[str, int], token_analysis: Optional[Dict] = None,
                   results_summary: Optional[str] = None) -> SearchRecord:
        """Log a forensic search operation"""
        record = SearchRecord(
            timestamp=datetime.now().isoformat(),
            query=query,
            reasoning=reasoning,
            queries_generated=queries,
            tier_distribution=tier_distribution,
            token_analysis=token_analysis,
            results_summary=results_summary
        )
        self.session.searches.append(record)
        self.session.total_queries_generated += len(queries)
        return record

    def export_session(self, filename: Optional[str] = None) -> Path:
        """Export session to JSON file"""
        self.session.end_time = datetime.now().isoformat()

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"forensic_session_{self.session.session_id}_{timestamp}.json"

        filepath = self.export_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.session.to_dict(), f, indent=2, ensure_ascii=False)

        return filepath

    def get_search_history_context(self) -> str:
        """Get previous searches as context for new searches"""
        if not self.session.searches:
            return ""

        history = ["## Previous Searches in This Session:"]
        for i, search in enumerate(self.session.searches[-5:], 1):  # Last 5 searches
            history.append(f"\n### Search {i}: {search.query}")
            history.append(f"- Reasoning: {search.reasoning[:200]}...")
            history.append(f"- Queries generated: {len(search.queries_generated)}")
            if search.results_summary:
                history.append(f"- Results: {search.results_summary[:200]}...")

        return "\n".join(history)


# ============================================================================
# FORENSIC DOCUMENT ANALYZER
# ============================================================================

class ForensicDocumentAnalyzer:
    """
    Combined document Q&A and forensic search capabilities.

    Auto-detects user intent:
    - Document questions → Uses document context
    - Search requests → Triggers forensic search generation

    Now with graph-based context management:
    - Extracts entities and relationships from every Gemini response
    - Uses graph + recent exchanges instead of full conversation history
    - Project description created at round 2, updated every 10 rounds
    """

    def __init__(self, project_id: Optional[str] = None):
        self.client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
        self.model = MODEL
        self.logger = ConversationLogger()
        self.query_builder = ForensicQueryBuilder()
        self.scorer = ForensicScorer()
        self.file_store = FileStoreManager()
        self.cloud_store = GeminiCloudStore(self.client)

        # Graph extraction and context management
        self.graph_extractor = ClaudeGraphExtractor()
        self.project_id = project_id or self.logger.session.session_id
        self.graph_context = GraphContextManager(self.project_id, self.graph_extractor)
        self.use_graph_context = True  # Toggle for graph vs full history

        # Conversation state
        self.history: List[Dict[str, Any]] = []
        self.document_content: Optional[str] = None
        self.document_name: Optional[str] = None
        self.document_path: Optional[Path] = None
        self.use_cloud_search: bool = False  # Toggle for cloud vs context search
        self._vision_file_uri: Optional[str] = None  # Cached vision file URI

        print(f"Forensic Document Analyzer initialized")
        print(f"Model: {MODEL}")
        print(f"Session ID: {self.logger.session.session_id}")
        print(f"Project ID: {self.project_id}")
        print(f"Graph Mode: {'Enabled' if self.use_graph_context else 'Disabled'}")

        # Show file store stats
        stats = self.file_store.get_store_stats()
        if stats["total_files"] > 0:
            print(f"File Store: {stats['total_files']} files ({stats['total_size_mb']} MB)")

        # Show cloud store stats
        cloud_stats = self.cloud_store.get_cloud_stats()
        if cloud_stats["total_stores"] > 0:
            print(f"Cloud Stores: {cloud_stats['total_stores']} stores, {cloud_stats['total_files_uploaded']} files")

    def load_document(self, file_path: Path, copy_to_store: bool = True) -> bool:
        """Load document into context and optionally copy to file store"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            self.document_content = content
            self.document_name = file_path.name
            self.document_path = file_path
            self.logger.set_document(file_path.name, len(content))

            # Copy to file store for future access (unless loading from store already)
            if copy_to_store and str(self.file_store.store_dir) not in str(file_path):
                self.file_store.add_file(file_path)

            # Check if this file is already in a cloud store
            cloud_store_name = self.cloud_store.get_store_for_file(file_path)
            if cloud_store_name:
                self.cloud_store.set_current_store(cloud_store_name)
                print(f"  ☁️  File is also in cloud store: {cloud_store_name}")

            # Initialize conversation with document
            self.history = [{
                "role": "user",
                "parts": [{"text": f"""You are a forensic research assistant with two capabilities:

1. DOCUMENT Q&A: When asked about this document, answer from it directly.
2. FORENSIC SEARCH: When asked to search, investigate, or find information, generate forensic search queries.

Here is the document to analyze:

<document name="{file_path.name}">
{content[:500000] if len(content) > 500000 else content}
</document>

Note: Document has {len(content):,} total characters. Showing first 500k for context. Full document stored for detailed queries.

Confirm you've loaded the document."""}]
            }, {
                "role": "model",
                "parts": [{"text": f"I've loaded '{file_path.name}' ({len(content):,} characters). I can:\n\n1. **Answer questions** about the document content\n2. **Generate forensic searches** when you ask me to investigate, search, or find related information\n\nWhat would you like to know?"}]
            }]

            print(f"\n✓ Loaded: {file_path.name} ({len(content):,} chars)")
            return True

        except Exception as e:
            print(f"✗ Error loading document: {e}")
            return False

    def load_from_store(self, file_id: str) -> bool:
        """Load a document from the file store by ID"""
        stored_path = self.file_store.get_file(file_id)
        if stored_path:
            return self.load_document(stored_path, copy_to_store=False)
        print(f"✗ File not found in store: {file_id}")
        return False

    def list_stored_files(self) -> str:
        """List all files in the store"""
        files = self.file_store.list_files(limit=20)
        if not files:
            return "No files in store."

        lines = ["## File Store Contents\n"]
        for i, f in enumerate(files, 1):
            size_kb = f.get("size_bytes", 0) / 1024
            lines.append(f"{i}. [{f['id']}] {f['original_name']} ({size_kb:.1f} KB)")
            lines.append(f"   Added: {f['added_at'][:10]} | Accessed: {f.get('access_count', 1)}x")

        stats = self.file_store.get_store_stats()
        lines.append(f"\n**Total:** {stats['total_files']} files, {stats['total_size_mb']} MB")
        return "\n".join(lines)

    # ==========================================================================
    # CLOUD FILE SEARCH METHODS
    # ==========================================================================

    def list_cloud_stores(self) -> str:
        """List all Gemini cloud file search stores"""
        stores = self.cloud_store.list_stores()
        if not stores:
            return "No cloud stores found. Use /cloud create <name> to create one."

        lines = ["## ☁️ Gemini Cloud File Search Stores\n"]
        for i, s in enumerate(stores, 1):
            current = " ← ACTIVE" if s["name"] == self.cloud_store.get_current_store() else ""
            lines.append(f"{i}. {s['display_name']}{current}")
            lines.append(f"   ID: {s['name']}")

        stats = self.cloud_store.get_cloud_stats()
        lines.append(f"\n**Total:** {stats['total_stores']} stores, {stats['total_files_uploaded']} files uploaded")
        lines.append(f"\n**Mode:** {'☁️ Cloud Search' if self.use_cloud_search else '📄 Full Context'}")
        return "\n".join(lines)

    def create_cloud_store(self, name: str) -> bool:
        """Create a new cloud file search store"""
        store_name = self.cloud_store.create_store(name)
        if store_name:
            self.cloud_store.set_current_store(store_name)
            return True
        return False

    def upload_to_cloud(self, store_name: Optional[str] = None) -> bool:
        """Upload current document to cloud store for semantic search"""
        if not self.document_path:
            print("✗ No document loaded. Load a document first with /file")
            return False

        # Use current store if none specified
        if not store_name:
            store_name = self.cloud_store.get_current_store()

        if not store_name:
            # Create a new store based on document name
            doc_base = self.document_path.stem[:20].replace(" ", "-").lower()
            store_name = self.cloud_store.create_store(doc_base)
            if not store_name:
                print("✗ Failed to create cloud store")
                return False

        success = self.cloud_store.upload_file(store_name, self.document_path)
        if success:
            self.cloud_store.set_current_store(store_name)
            print(f"\n💡 Use /cloudmode to enable cloud-based semantic search")
        return success

    def toggle_cloud_mode(self) -> str:
        """Toggle between cloud file search and full context mode"""
        current_store = self.cloud_store.get_current_store()

        if not current_store and not self.use_cloud_search:
            return "✗ No cloud store active. Upload a file first with /upload"

        self.use_cloud_search = not self.use_cloud_search

        if self.use_cloud_search:
            return f"☁️ Cloud Search Mode ENABLED\n   Using store: {current_store}\n   Queries will use semantic retrieval instead of full context."
        else:
            return f"📄 Full Context Mode ENABLED\n   Queries will use the full document in context window."

    def cloud_query(self, query: str, allow_fallback: bool = True) -> str:
        """
        Query using cloud file search (semantic retrieval).

        If cloud search returns insufficient results, automatically falls back
        to full context mode for better coverage.
        """
        store_name = self.cloud_store.get_current_store()

        if not store_name:
            return "✗ No cloud store active. Use /cloud to manage stores or /upload to upload a file."

        print(f"☁️ Querying cloud store: {store_name}...")

        result = self.cloud_store.query(store_name, query)
        response_text = result.get("response", "")

        # Check if cloud search found insufficient results
        needs_fallback = self._needs_context_fallback(response_text, result)

        if needs_fallback and allow_fallback and self.document_content:
            print("  ⚠️  Cloud search returned limited results, falling back to full context...")
            return self._fallback_to_full_context(query, response_text)

        # Build response with cloud results
        response_parts = [
            "## ☁️ Cloud Search Response\n",
            response_text
        ]

        if result["citations"]:
            response_parts.append("\n\n### Citations")
            for i, cite in enumerate(result["citations"][:5], 1):
                response_parts.append(f"\n{i}. {cite.get('source', 'Unknown')}")
                if cite.get('text'):
                    response_parts.append(f"   > {cite['text'][:200]}...")

        # Log the response
        self.logger.log_message("assistant", response_text, mode="cloud_search")

        return "\n".join(response_parts)

    def upload_pdf_for_vision(self, file_path: Path) -> Optional[str]:
        """
        Upload a PDF to Gemini Files API for vision-based analysis.
        This allows Gemini to SEE images, charts, tables in the PDF.

        Returns the file URI for use in queries.
        """
        import time

        try:
            print(f"📷 Uploading PDF for vision analysis: {file_path.name}...")

            # Upload file to Gemini Files API
            uploaded_file = self.client.files.upload(file=str(file_path))

            # Wait for processing
            while uploaded_file.state.name == "PROCESSING":
                print("  ⏳ Processing PDF...")
                time.sleep(2)
                uploaded_file = self.client.files.get(name=uploaded_file.name)

            if uploaded_file.state.name == "FAILED":
                print(f"✗ PDF processing failed")
                return None

            print(f"✓ PDF ready for vision queries: {uploaded_file.name}")
            return uploaded_file.name

        except Exception as e:
            print(f"Error uploading PDF: {e}")
            return None

    def vision_query(self, query: str, file_uri: Optional[str] = None) -> str:
        """
        Query a PDF using Gemini's vision capabilities.
        Can see images, charts, diagrams, tables, handwriting, etc.
        Uses inline base64 for Vertex AI compatibility with context caching.
        """
        import base64
        import threading
        import sys

        if not self.document_path:
            return "✗ No document loaded. Load a PDF first with /file"

        if not str(self.document_path).lower().endswith('.pdf'):
            return "✗ Vision mode requires a PDF file."

        print(f"📷 Querying PDF with vision...")

        # Show progress spinner
        stop_spinner = threading.Event()
        def spinner():
            dots = 0
            while not stop_spinner.is_set():
                sys.stdout.write(f"\r  Analyzing{'.' * (dots % 4)}   ")
                sys.stdout.flush()
                dots += 1
                stop_spinner.wait(0.5)
            sys.stdout.write("\r" + " " * 20 + "\r")
            sys.stdout.flush()

        spinner_thread = threading.Thread(target=spinner)
        spinner_thread.start()

        try:
            # Check if we have cached PDF data
            if not hasattr(self, '_cached_pdf_base64') or self._cached_pdf_path != self.document_path:
                print("  📥 Loading PDF for caching...")
                with open(self.document_path, "rb") as f:
                    pdf_bytes = f.read()
                self._cached_pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                self._cached_pdf_path = self.document_path
            else:
                print("  ⚡ Using cached PDF")

            # Use cached content with Gemini's context caching
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": "application/pdf",
                                    "data": self._cached_pdf_base64
                                }
                            },
                            {"text": query}
                        ]
                    }
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=MAX_OUTPUT_TOKENS
                )
            )

            response_text = response.text
            self.logger.log_message("assistant", response_text, mode="vision_query")

            return response_text

        except Exception as e:
            return f"✗ Vision query error: {e}"
        finally:
            stop_spinner.set()
            spinner_thread.join()

    def _needs_context_fallback(self, response: str, result: Dict[str, Any]) -> bool:
        """
        Determine if cloud search results are insufficient and need full context fallback.

        Triggers fallback when:
        - Response is too short (< 100 chars)
        - Response contains "I don't have", "not found", "no information"
        - No citations returned
        - Error in result
        """
        if result.get("error"):
            return True

        if len(response) < 100:
            return True

        # Check for "not found" type responses
        not_found_phrases = [
            "i don't have",
            "i do not have",
            "not found",
            "no information",
            "cannot find",
            "unable to find",
            "no relevant",
            "doesn't contain",
            "does not contain",
            "not mentioned",
            "no mention",
            "i couldn't find",
            "i could not find",
        ]
        response_lower = response.lower()
        for phrase in not_found_phrases:
            if phrase in response_lower:
                return True

        # No citations might indicate poor retrieval
        if not result.get("citations") and len(response) < 300:
            return True

        return False

    def _fallback_to_full_context(self, query: str, cloud_response: str) -> str:
        """
        Fall back to full document context when cloud search is insufficient.
        """
        print("  📄 Loading full document context...")

        # Build enhanced prompt that mentions cloud search failed
        enhanced_query = f"""The semantic search didn't find a clear answer. Please search the full document context.

User's question: {query}

Cloud search returned: "{cloud_response[:200]}..."

Please provide a comprehensive answer by searching the complete document."""

        # Use full context Q&A (temporarily disable cloud mode)
        original_cloud_mode = self.use_cloud_search
        self.use_cloud_search = False

        self.history.append({"role": "user", "parts": [{"text": enhanced_query}]})

        response = self.client.models.generate_content(
            model=self.model,
            contents=self.history,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                max_output_tokens=MAX_OUTPUT_TOKENS
            )
        )

        response_text = response.text
        self.history.append({"role": "model", "parts": [{"text": response_text}]})

        # Restore cloud mode
        self.use_cloud_search = original_cloud_mode

        # Log response
        self.logger.log_message("assistant", response_text, mode="fallback_full_context")

        return f"## 📄 Full Context Response (Cloud Search Fallback)\n\n{response_text}"

    def _detect_search_intent(self, message: str) -> bool:
        """Detect if user wants forensic search"""
        message_lower = message.lower()

        # Check for explicit search triggers
        for trigger in SEARCH_TRIGGERS:
            if trigger in message_lower:
                return True

        # Check for question patterns that suggest external research
        search_patterns = [
            r"what else.*about",
            r"can you find",
            r"are there.*other",
            r"look for.*more",
            r"any.*online",
            r"check.*web",
        ]
        for pattern in search_patterns:
            if re.search(pattern, message_lower):
                return True

        return False

    def _extract_search_terms(self, user_message: str) -> str:
        """
        Extract search terms - SIMPLE RULE-BASED, NO AI HALLUCINATION.
        """
        # Noise words to remove
        noise = {'search', 'find', 'look', 'up', 'for', 'about', 'info', 'information',
                 'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'with', 'between',
                 'connection', 'overlap', 'intersection', 'show', 'me', 'give',
                 'please', 'can', 'you', 'i', 'want', 'need', 'get', 'what', 'where',
                 'jesus', 'christ', 'man', 'wtf', 'damn', 'fuck', 'shit', 'hell',
                 'ok', 'okay', 'now', 'just', 'actually', 'really', 'like', 'and'}

        # Clean the message
        text = user_message.lower().strip()
        text = re.sub(r'[^\w\s\'-]', ' ', text)  # Keep only words

        # Split and filter
        words = text.split()
        terms = [w for w in words if w.lower() not in noise and len(w) > 1]

        if not terms:
            return f'"{user_message}"'

        # Format: wrap each term in quotes, join with AND
        formatted = ' AND '.join(f'"{t.title()}"' for t in terms)
        print(f"  📌 Extracted: {formatted}")
        return formatted

    def _generate_forensic_queries(self, user_query: str) -> tuple:
        """Generate forensic search queries with reasoning"""

        # Extract actual search terms from user's natural language
        search_anchor = self._extract_search_terms(user_query)
        print(f"  🎯 PRIMARY SEARCH: {search_anchor}")

        # Create queries list - PRIMARY QUERY FIRST, no AI nonsense
        queries = []

        # PRIMARY: The exact intersection query the user asked for
        primary_query = ForensicQuery(
            q=search_anchor,  # Already formatted: "Kvika" AND "Libya"
            tier="0_Net",
            logic="direct_extraction",
            operators_used=["phrase", "AND"] if " AND " in search_anchor else ["phrase"],
            expected_noise="medium",
            forensic_value="critical",
            rationale=f"EXACT USER REQUEST: {search_anchor}"
        )
        queries.append(primary_query)

        # Extract individual terms for variations
        # "Kvika" AND "Libya" -> ["Kvika", "Libya"]
        terms = [t.strip().strip('"') for t in search_anchor.replace(' AND ', '|||').split('|||')]
        terms = [t for t in terms if t and len(t) > 1]

        # Add filetype variations for the intersection
        if len(terms) >= 2:
            queries.append(ForensicQuery(
                q=f'{search_anchor} filetype:pdf',
                tier="4_Artifact",
                logic="intersection_pdf",
                operators_used=["phrase", "AND", "filetype"],
                expected_noise="low",
                forensic_value="high",
                rationale=f"PDF documents mentioning both terms"
            ))
            queries.append(ForensicQuery(
                q=f'{search_anchor} filetype:xlsx OR filetype:xls',
                tier="4_Artifact",
                logic="intersection_spreadsheet",
                operators_used=["phrase", "AND", "filetype", "OR"],
                expected_noise="low",
                forensic_value="high",
                rationale=f"Spreadsheets mentioning both terms"
            ))

        # Add filter variations (exclude noise sites)
        queries.append(ForensicQuery(
            q=f'{search_anchor} -site:wikipedia.org -site:linkedin.com -site:facebook.com',
            tier="3_Filter",
            logic="intersection_filtered",
            operators_used=["phrase", "AND", "-site"],
            expected_noise="low",
            forensic_value="high",
            rationale=f"Filtered intersection - no social/wiki noise"
        ))

        # For each individual term, add some targeted queries
        for term in terms[:2]:  # Max 2 terms
            queries.append(ForensicQuery(
                q=f'"{term}" filetype:pdf',
                tier="4_Artifact",
                logic="term_pdf",
                operators_used=["phrase", "filetype"],
                expected_noise="medium",
                forensic_value="medium",
                rationale=f"PDF documents for {term}"
            ))

        # Brief reasoning
        ai_reasoning = f"""### SEARCH STRATEGY
**Primary Target:** {search_anchor}
**Terms Identified:** {', '.join(terms)}

Executing intersection search to find documents/pages mentioning ALL specified terms together.
Priority given to exact phrase matching and filtered results."""

        # Minimal token analysis
        token_analysis = None
        try:
            token_analysis = self.query_builder.analyzer.analyze(terms[0] if terms else search_anchor)
        except Exception as e:

            print(f"[BRUTE] Error: {e}")

            pass

        # Convert queries to serializable format
        queries_list = [{
            "tier": q.tier,
            "query": q.q,
            "purpose": q.rationale,
            "mandatory_operators": q.operators_used
        } for q in queries[:20]]  # Limit to top 20

        tier_dist = {}
        for q in queries:
            tier_dist[str(q.tier)] = tier_dist.get(str(q.tier), 0) + 1

        token_dict = asdict(token_analysis) if token_analysis else None
        
        # Fix for JSON serialization of Enum
        if token_dict and "uniqueness" in token_dict and hasattr(token_dict["uniqueness"], "value"):
             token_dict["uniqueness"] = token_dict["uniqueness"].value

        return ai_reasoning, queries_list, tier_dist, token_dict

    def send(self, message: str, force_mode: Optional[str] = None) -> str:
        """
        Process user message with auto intent detection.

        Args:
            message: User's input
            force_mode: Override auto-detection ("search" or "qa")

        Returns:
            Assistant's response
        """
        # Log user message
        is_search = force_mode == "search" or (force_mode != "qa" and self._detect_search_intent(message))
        mode = "forensic_search" if is_search else "document_qa"

        self.logger.log_message("user", message, mode=mode)

        if is_search:
            return self._handle_forensic_search(message)
        else:
            return self._handle_document_qa(message)

    def _handle_document_qa(self, message: str) -> str:
        """Handle document Q&A mode - uses vision for PDFs, cloud search, graph context, or full context"""

        # For PDFs, ALWAYS use vision mode (Gemini can see the actual content)
        if self.document_path and str(self.document_path).lower().endswith('.pdf'):
            return self.vision_query(message, self._vision_file_uri)

        # Use cloud file search if enabled and available
        if self.use_cloud_search and self.cloud_store.get_current_store():
            response_text = self.cloud_query(message)
            # Extract entities from cloud response too
            if self.use_graph_context:
                self.graph_context.process_gemini_response(response_text, message)
            return response_text

        # ALWAYS save to history for the record
        self.history.append({"role": "user", "parts": [{"text": message}]})

        # Build context - either graph-based or full history for Gemini
        if self.use_graph_context and self.graph_context.graph.round_count > 0:
            # Use graph context + document + current query (not full history)
            graph_context = self.graph_context.get_context_for_gemini()

            context_message = f"""You are a forensic research assistant analyzing documents.

{graph_context}

# Document
{self.document_content[:100000] if self.document_content else 'No document loaded.'}

# Current Question
{message}

Answer based on the document and investigation context above."""

            contents = [{"role": "user", "parts": [{"text": context_message}]}]
        else:
            # Standard full-context Q&A - send full history to Gemini
            contents = self.history

        # Show progress indicator while waiting
        import threading
        import sys
        stop_spinner = threading.Event()

        def spinner():
            dots = 0
            while not stop_spinner.is_set():
                sys.stdout.write(f"\rThinking{'.' * (dots % 4)}   ")
                sys.stdout.flush()
                dots += 1
                stop_spinner.wait(0.5)
            sys.stdout.write("\r" + " " * 20 + "\r")
            sys.stdout.flush()

        spinner_thread = threading.Thread(target=spinner)
        spinner_thread.start()

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],  # Enable web search for additional context
                    max_output_tokens=MAX_OUTPUT_TOKENS
                )
            )
            response_text = response.text
        finally:
            stop_spinner.set()
            spinner_thread.join()

        # ALWAYS save response to history for the record
        self.history.append({"role": "model", "parts": [{"text": response_text}]})

        # Log response
        self.logger.log_message("assistant", response_text, mode="document_qa")

        # Extract entities in BACKGROUND thread (don't block response display)
        if self.use_graph_context:
            def extract_in_background():
                try:
                    self.graph_context.process_gemini_response(response_text, message)
                except Exception as e:
                    print(f"\n  ⚠️ Background entity extraction failed: {e}")

            bg_thread = threading.Thread(target=extract_in_background, daemon=True)
            bg_thread.start()

        return response_text

    def _handle_forensic_search(self, message: str) -> str:
        """Handle forensic search mode with ACTUAL search execution"""
        print("\n🔍 FORENSIC SEARCH MODE ACTIVATED\n")
        print("Generating search queries...")

        # Generate forensic queries
        reasoning, queries, tier_dist, token_analysis = self._generate_forensic_queries(message)

        # Log the search
        search_record = self.logger.log_search(
            query=message,
            reasoning=reasoning[:500],  # Truncate for storage
            queries=queries,
            tier_distribution=tier_dist,
            token_analysis=token_analysis
        )

        # Build initial response with reasoning
        response_parts = [
            "## 🔍 FORENSIC SEARCH ANALYSIS\n",
            reasoning,
            "\n---\n",
            f"**Total Queries Generated:** {len(queries)}",
            f"**Tier Distribution:** {json.dumps(tier_dist)}",
        ]

        # Execute top queries with Google Search Grounding
        print("\n🌐 Executing searches with Google Search Grounding...")
        all_urls = set()
        search_results = []

        # Execute top 5 high-value queries
        queries_to_execute = queries[:5]
        for i, q in enumerate(queries_to_execute, 1):
            query_str = q['query']
            print(f"  [{i}/{len(queries_to_execute)}] {query_str[:60]}...")

            try:
                # Execute with Google Search Grounding
                grounded_response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=query_str,
                    config={"tools": [{"google_search": {}}]}
                )

                urls = []
                if grounded_response.candidates and grounded_response.candidates[0].grounding_metadata:
                    metadata = grounded_response.candidates[0].grounding_metadata
                    if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                        for chunk in metadata.grounding_chunks:
                            if hasattr(chunk, 'web') and hasattr(chunk.web, 'uri'):
                                url = chunk.web.uri
                                # Resolve redirects
                                try:
                                    import requests
                                    resp = requests.head(url, allow_redirects=True, timeout=5)
                                    url = resp.url
                                except Exception as e:

                                    print(f"[BRUTE] Error: {e}")

                                    pass
                                if url not in all_urls:
                                    all_urls.add(url)
                                    urls.append(url)

                search_results.append({
                    "tier": q['tier'],
                    "query": query_str,
                    "urls_found": len(urls),
                    "urls": urls
                })
                print(f"      → Found {len(urls)} URLs")

            except Exception as e:
                print(f"      → Error: {e}")
                search_results.append({
                    "tier": q['tier'],
                    "query": query_str,
                    "urls_found": 0,
                    "urls": [],
                    "error": str(e)
                })

        # Add search results to response
        response_parts.append(f"\n### 🌐 SEARCH RESULTS\n")
        response_parts.append(f"Queries: {len(queries_to_execute)} | URLs: {len(all_urls)}\n")

        for result in search_results:
            q = result['query']
            # Show full query if under 60 chars, else truncate
            q_display = q if len(q) <= 60 else q[:57] + "..."
            response_parts.append(f"\n[{result['tier']}] `{q_display}`")
            for url in result['urls']:
                response_parts.append(f"→ {url}")

        if all_urls:
            response_parts.append(f"\n### 📋 ALL URLs ({len(all_urls)})\n")
            for url in sorted(all_urls):
                response_parts.append(f"→ {url}")

        response_text = "\n".join(response_parts)

        # Add to conversation history
        self.history.append({"role": "user", "parts": [{"text": message}]})
        self.history.append({"role": "model", "parts": [{"text": response_text}]})

        # Log response
        self.logger.log_message("assistant", response_text, mode="forensic_search",
                               search_triggered=True, search_record=search_record)

        return response_text

    def show_search_history(self) -> str:
        """Show all searches in this session"""
        if not self.logger.session.searches:
            return "No searches performed yet."

        lines = ["## Search History\n"]
        for i, search in enumerate(self.logger.session.searches, 1):
            lines.append(f"### {i}. {search.query}")
            lines.append(f"   Time: {search.timestamp}")
            lines.append(f"   Queries: {len(search.queries_generated)}")
            lines.append(f"   Tiers: {search.tier_distribution}\n")

        return "\n".join(lines)

    # ==========================================================================
    # GRAPH METHODS
    # ==========================================================================

    def show_graph(self) -> str:
        """Show the current knowledge graph"""
        graph = self.graph_context.get_graph()

        lines = [
            "## 🕸️ Investigation Knowledge Graph",
            f"\n**Project ID:** {graph.project_id}",
            f"**Round:** {graph.round_count}",
        ]

        if graph.project_description:
            lines.append(f"\n**Description:** {graph.project_description}")

        lines.append(f"\n### Entities ({len(graph.entities)})")

        # Group by type
        by_type = {}
        for e in graph.entities.values():
            by_type.setdefault(e["type"], []).append(e)

        for etype, ents in sorted(by_type.items()):
            lines.append(f"\n**{etype.title()}s ({len(ents)}):**")
            for e in sorted(ents, key=lambda x: x.get("mentions", 1), reverse=True)[:10]:
                mentions = f" ({e.get('mentions', 1)}x)" if e.get("mentions", 1) > 1 else ""
                lines.append(f"  - {e['value']}{mentions}")
            if len(ents) > 10:
                lines.append(f"  ... and {len(ents) - 10} more")

        if graph.edges:
            lines.append(f"\n### Relationships ({len(graph.edges)})")
            for edge in graph.edges[:20]:
                lines.append(f"  - {edge['source_value']} → [{edge['relation']}] → {edge['target_value']}")
            if len(graph.edges) > 20:
                lines.append(f"  ... and {len(graph.edges) - 20} more")

        return "\n".join(lines)

    def export_graph(self, format: str = "json") -> str:
        """Export the knowledge graph"""
        graph = self.graph_context.get_graph()
        graph_data = graph.to_json()

        if format == "json":
            output_path = GRAPH_STORE_DIR / self.project_id / "export.json"
            output_path.write_text(json.dumps(graph_data, indent=2))
            return f"Graph exported to: {output_path}"
        else:
            return json.dumps(graph_data, indent=2)

    def toggle_graph_mode(self) -> str:
        """Toggle between graph context and full history mode"""
        self.use_graph_context = not self.use_graph_context

        if self.use_graph_context:
            return "🕸️ Graph Context Mode ENABLED\n   Using entity graph + recent exchanges instead of full history."
        else:
            return "📜 Full History Mode ENABLED\n   Using complete conversation history."

    def search_graph(self, query: str) -> str:
        """Search for an entity in the graph"""
        graph = self.graph_context.get_graph()
        query_lower = query.lower()

        # Search entities
        matching_entities = [
            e for e in graph.entities.values()
            if query_lower in e["value"].lower()
        ]

        # Search edges
        matching_edges = [
            e for e in graph.edges
            if query_lower in e["source_value"].lower() or query_lower in e["target_value"].lower()
        ]

        lines = [f"## Graph Search: '{query}'\n"]

        if matching_entities:
            lines.append(f"### Matching Entities ({len(matching_entities)})")
            for e in matching_entities[:10]:
                lines.append(f"  - [{e['type']}] {e['value']} ({e.get('mentions', 1)}x)")
                if e.get("contexts"):
                    for ctx in e["contexts"][:2]:
                        lines.append(f"    > {ctx[:100]}...")

        if matching_edges:
            lines.append(f"\n### Related Relationships ({len(matching_edges)})")
            for edge in matching_edges[:10]:
                lines.append(f"  - {edge['source_value']} → [{edge['relation']}] → {edge['target_value']}")
                if edge.get("evidence"):
                    lines.append(f"    > {edge['evidence'][:100]}...")

        if not matching_entities and not matching_edges:
            lines.append("No matches found.")

        return "\n".join(lines)

    def export_session(self) -> str:
        """Export session to JSON"""
        filepath = self.logger.export_session()
        return f"Session exported to: {filepath}"

    def clear_history(self):
        """Clear conversation history (keeps document)"""
        if self.document_content:
            self.history = self.history[:2]  # Keep initial document context
        else:
            self.history = []
        print("Conversation history cleared.")


# ============================================================================
# CLI INTERFACE
# ============================================================================

HISTORY_FILE = Path.home() / '.forensic_analyzer_history.json'

def load_file_history() -> List[str]:
    """Load recent files"""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())[:10]
        except Exception as e:
            return []
    return []

def save_file_history(file_path: str):
    """Save file to history"""
    history = load_file_history()
    if file_path in history:
        history.remove(file_path)
    history.insert(0, file_path)
    HISTORY_FILE.write_text(json.dumps(history[:10]))


def print_help():
    """Print help message"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║           FORENSIC DOCUMENT ANALYZER                         ║
╠══════════════════════════════════════════════════════════════╣
║  DOCUMENT COMMANDS:                                          ║
║    /file <path>     - Load a new document (copies to store)  ║
║    /store           - List all files in local store          ║
║    /load <id>       - Load file from store by ID             ║
║                                                              ║
║  🕸️ KNOWLEDGE GRAPH (Claude Haiku extraction):               ║
║    /graph           - Show current entity graph              ║
║    /graphsearch <q> - Search entities in graph               ║
║    /graphexport     - Export graph to JSON                   ║
║    /graphmode       - Toggle graph vs full history mode      ║
║                                                              ║
║  ☁️ CLOUD FILE SEARCH (Gemini RAG - text only):              ║
║    /cloud           - List cloud stores                      ║
║    /cloud create <n>- Create new cloud store                 ║
║    /upload          - Upload current doc to cloud            ║
║    /cloudmode       - Toggle cloud vs full-context mode      ║
║    /cloudqa <query> - Force cloud search query               ║
║                                                              ║
║  📷 VISION MODE (sees images in PDFs):                       ║
║    /vision <query>  - Query PDF with vision (sees images!)   ║
║                                                              ║
║  SEARCH COMMANDS:                                            ║
║    /search <query>  - Force forensic search mode             ║
║    /qa <question>   - Force document Q&A mode                ║
║    /history         - Show search history                    ║
║                                                              ║
║  SESSION COMMANDS:                                           ║
║    /export          - Export conversation to JSON            ║
║    /clear           - Clear conversation history             ║
║    /help            - Show this help                         ║
║    /quit            - Exit and save                          ║
║                                                              ║
║  MODES:                                                      ║
║    📄 Full Context  - Load entire doc (1M tokens)            ║
║    🕸️ Graph Context - Entities + recent exchanges (default)  ║
║    ☁️ Cloud Search  - Semantic RAG via Gemini File Search    ║
║                                                              ║
║  AUTO-FEATURES:                                              ║
║    - Entities/relationships extracted from EVERY response    ║
║    - Project description created at round 2, updates x10     ║
║    - "search", "find", "investigate" → Forensic mode         ║
║    - Other questions → Document Q&A mode                     ║
╚══════════════════════════════════════════════════════════════╝
""")


def main():
    """Main CLI interface"""
    analyzer = ForensicDocumentAnalyzer()

    # Check for file argument
    if len(sys.argv) > 1:
        file_path = Path(" ".join(sys.argv[1:])).expanduser()
        if not file_path.exists():
            # Try unescaping
            unescaped = re.sub(r'\\(.)', r'\1', str(file_path))
            file_path = Path(unescaped).expanduser()

        if file_path.exists():
            analyzer.load_document(file_path)
        else:
            print(f"File not found: {file_path}")
            sys.exit(1)
    else:
        # Show file store menu
        stored_files = analyzer.file_store.list_files(limit=10)

        print("\n" + "="*60)
        print("  FORENSIC DOCUMENT ANALYZER")
        print("="*60)

        if stored_files:
            print("\n📁 FILE STORE (previously loaded documents):")
            for i, f in enumerate(stored_files, 1):
                size_kb = f.get("size_bytes", 0) / 1024
                print(f"  {i}. {f['original_name']} ({size_kb:.1f} KB)")
                print(f"     ID: {f['id']} | Accessed: {f.get('access_count', 1)}x")
            print()
            print("  N. Load NEW file (will be copied to store)")
            print("  S. Start without document (search only)")
            print()

            choice = input("Select (1-{}, N, or S): ".format(len(stored_files))).strip().lower()

            if choice == 's':
                print("\nStarting in search-only mode...")
            elif choice == 'n' or choice == '':
                file_input = input("File path: ").strip().strip("'\"")
                file_input = re.sub(r'\\(.)', r'\1', file_input)
                file_path = Path(file_input).expanduser()

                if file_path.exists():
                    analyzer.load_document(file_path)
                else:
                    print(f"File not found: {file_path}")
                    sys.exit(1)
            elif choice.isdigit() and 1 <= int(choice) <= len(stored_files):
                # Load from store by index
                file_id = stored_files[int(choice) - 1]["id"]
                analyzer.load_from_store(file_id)
            else:
                # Maybe they entered a file ID directly
                if any(f["id"] == choice for f in stored_files):
                    analyzer.load_from_store(choice)
                else:
                    print("Invalid choice")
                    sys.exit(1)
        else:
            print("\n📁 FILE STORE is empty. Enter a file path to load and store.")
            file_input = input("File path (or Enter for search-only): ").strip().strip("'\"")

            if file_input:
                file_input = re.sub(r'\\(.)', r'\1', file_input)
                file_path = Path(file_input).expanduser()

                if file_path.exists():
                    analyzer.load_document(file_path)
                else:
                    print(f"File not found: {file_path}")
                    sys.exit(1)

    # Print help
    print_help()

    # Main loop
    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSaving session...")
            filepath = analyzer.logger.export_session()
            print(f"Session saved: {filepath}")
            print("Goodbye!")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd in ["/quit", "/exit", "/q"]:
                print("\nSaving session...")
                filepath = analyzer.logger.export_session()
                print(f"Session saved: {filepath}")
                print("Goodbye!")
                break

            elif cmd == "/search":
                if not arg:
                    arg = input("Search query: ").strip()
                if arg:
                    response = analyzer.send(arg, force_mode="search")
                    print(f"\n{response}")

            elif cmd == "/qa":
                if not arg:
                    arg = input("Question: ").strip()
                if arg:
                    response = analyzer.send(arg, force_mode="qa")
                    print(f"\n{response}")

            elif cmd == "/history":
                print(analyzer.show_search_history())

            elif cmd == "/export":
                print(analyzer.export_session())

            elif cmd == "/file":
                if not arg:
                    arg = input("File path: ").strip()
                arg = arg.strip("'\"")
                arg = re.sub(r'\\(.)', r'\1', arg)
                file_path = Path(arg).expanduser()

                if file_path.exists():
                    analyzer.load_document(file_path)
                else:
                    print(f"File not found: {file_path}")

            elif cmd == "/store":
                print(analyzer.list_stored_files())

            elif cmd == "/load":
                if not arg:
                    # Show store and ask for ID
                    print(analyzer.list_stored_files())
                    arg = input("\nEnter file ID or number: ").strip()

                # Check if it's a number (index) or ID
                stored_files = analyzer.file_store.list_files(limit=20)
                if arg.isdigit() and 1 <= int(arg) <= len(stored_files):
                    file_id = stored_files[int(arg) - 1]["id"]
                    analyzer.load_from_store(file_id)
                else:
                    analyzer.load_from_store(arg)

            # ============================================================
            # KNOWLEDGE GRAPH COMMANDS
            # ============================================================

            elif cmd == "/graph":
                # Show knowledge graph
                print(analyzer.show_graph())

            elif cmd == "/graphsearch":
                # Search in graph
                if not arg:
                    arg = input("Search entity: ").strip()
                if arg:
                    print(analyzer.search_graph(arg))

            elif cmd == "/graphexport":
                # Export graph
                print(analyzer.export_graph())

            elif cmd == "/graphmode":
                # Toggle graph context mode
                print(analyzer.toggle_graph_mode())

            # ============================================================
            # CLOUD FILE SEARCH COMMANDS
            # ============================================================

            elif cmd == "/cloud":
                if not arg:
                    # List stores
                    print(analyzer.list_cloud_stores())
                elif arg.startswith("create "):
                    # Create new store
                    store_name = arg[7:].strip()
                    if store_name:
                        analyzer.create_cloud_store(store_name)
                    else:
                        print("Usage: /cloud create <store-name>")
                elif arg.startswith("delete "):
                    # Delete store
                    store_id = arg[7:].strip()
                    if store_id:
                        confirm = input(f"Delete store '{store_id}'? (y/N): ").strip().lower()
                        if confirm == 'y':
                            analyzer.cloud_store.delete_store(store_id)
                    else:
                        print("Usage: /cloud delete <store-id>")
                elif arg.startswith("use "):
                    # Set active store
                    store_id = arg[4:].strip()
                    if store_id:
                        analyzer.cloud_store.set_current_store(store_id)
                        print(f"✓ Active store set to: {store_id}")
                    else:
                        print("Usage: /cloud use <store-id>")
                else:
                    print("Cloud commands:")
                    print("  /cloud           - List all stores")
                    print("  /cloud create <n>- Create new store")
                    print("  /cloud use <id>  - Set active store")
                    print("  /cloud delete <id> - Delete a store")

            elif cmd == "/upload":
                # Upload current document to cloud
                if arg:
                    # Upload to specific store
                    analyzer.upload_to_cloud(arg)
                else:
                    # Upload to current/new store
                    analyzer.upload_to_cloud()

            elif cmd == "/cloudmode":
                # Toggle cloud search mode
                print(analyzer.toggle_cloud_mode())

            elif cmd == "/cloudqa":
                # Force cloud search query
                if not arg:
                    arg = input("Cloud search query: ").strip()
                if arg:
                    response = analyzer.cloud_query(arg)
                    print(f"\n{response}")

            elif cmd == "/vision":
                # Vision query for PDFs (sees images, charts, diagrams)
                if not arg:
                    arg = input("Vision query (asks about images in PDF): ").strip()
                if arg:
                    # Use cached file URI if available, otherwise will upload
                    file_uri = getattr(analyzer, '_vision_file_uri', None)
                    response = analyzer.vision_query(arg, file_uri)
                    print(f"\n{response}")

            elif cmd == "/clear":
                analyzer.clear_history()

            elif cmd == "/help":
                print_help()

            else:
                print(f"Unknown command: {cmd}")
                print("Type /help for available commands")

        # Regular message - auto-detect intent
        else:
            response = analyzer.send(user_input)
            print(f"\n{response}")


if __name__ == '__main__':
    main()
