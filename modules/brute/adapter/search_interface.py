"""
CyMonides 2.0 - User-Friendly Search Interface
Convenient syntax for quick searches and tagging
"""

from typing import Dict, List, Any, Optional, Union
import re
from datetime import datetime


class SearchInterface:
    """
    User-Friendly Search Interface

    Provides convenient syntax:
    - /cym: "keyword" → Exact keyword search
    - /cym: tell me about X → AI interprets and answers
    - #tag filtering → Narrow search by tags
    - List indices and tags → Discovery
    """

    def __init__(self, backend, inventory):
        """
        Initialize search interface

        Args:
            backend: UnifiedBackend instance
            inventory: ContentInventory instance
        """
        self.backend = backend
        self.inventory = inventory

    def parse_and_search(self, query: str, zone_id: str = "default") -> Dict[str, Any]:
        """
        Parse search query and execute

        Supports:
        - /cym: "keyword" → Exact keyword search
        - /cym: tell me about X → Natural language query
        - /cym: #tag1 #tag2 keyword → Tag-filtered search
        - /cym: @zone_id keyword → Zone-specific search

        Args:
            query: Search query (with or without /cym: prefix)
            zone_id: Default zone

        Returns:
            Search results with metadata
        """
        # Remove /cym: prefix if present
        query = query.strip()
        if query.lower().startswith("/cym:"):
            query = query[5:].strip()

        # Parse query components
        parsed = self._parse_query(query, zone_id)

        # Determine search type
        if parsed["is_question"]:
            # Natural language query - return results for AI to interpret
            return self._nl_search(parsed)
        else:
            # Direct keyword search
            return self._keyword_search(parsed)

    def _parse_query(self, query: str, default_zone: str) -> Dict[str, Any]:
        """
        Parse query into components

        Extracts:
        - Tags: #tag1 #tag2
        - Zone: @zone_id
        - Keywords: remaining text
        - Question detection: starts with who/what/when/where/why/how/tell/show/find
        """
        parsed = {
            "original": query,
            "tags": [],
            "zone_id": default_zone,
            "keywords": [],
            "is_question": False,
            "is_exact": False
        }

        # Extract tags (#tag)
        tags = re.findall(r'#(\w+)', query)
        parsed["tags"] = tags
        query = re.sub(r'#\w+', '', query).strip()

        # Extract zone (@zone)
        zone_match = re.search(r'@(\w+)', query)
        if zone_match:
            parsed["zone_id"] = zone_match.group(1)
            query = re.sub(r'@\w+', '', query).strip()

        # Check if exact match requested (quoted)
        exact_match = re.search(r'"([^"]+)"', query)
        if exact_match:
            parsed["is_exact"] = True
            parsed["keywords"] = [exact_match.group(1)]
        else:
            # Check if it's a question
            question_starters = [
                "who", "what", "when", "where", "why", "how",
                "tell me", "show me", "find", "list", "explain",
                "describe", "summarize", "what is", "what are"
            ]
            query_lower = query.lower()
            if any(query_lower.startswith(starter) for starter in question_starters):
                parsed["is_question"] = True

            parsed["keywords"] = [query]

        return parsed

    def _keyword_search(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Execute direct keyword search"""
        keywords = " ".join(parsed["keywords"])
        zone_id = parsed["zone_id"]
        tags = parsed["tags"]

        # Search with tags filter
        results = self.backend.search_keyword(
            query=keywords,
            zone_id=zone_id,
            limit=50
        )

        # Filter by tags if specified
        if tags:
            results = [
                r for r in results
                if any(tag in r.get("tags", []) for tag in tags)
            ]

        return {
            "type": "direct",
            "query": parsed["original"],
            "zone": zone_id,
            "tags": tags,
            "count": len(results),
            "results": results[:20],  # Limit to top 20
            "search_type": "exact" if parsed["is_exact"] else "keyword",
            "timestamp": datetime.utcnow().isoformat()
        }

    def _nl_search(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Execute natural language search for AI interpretation"""
        keywords = " ".join(parsed["keywords"])
        zone_id = parsed["zone_id"]
        tags = parsed["tags"]

        # Use hybrid search for better results
        results = self.backend.search_keyword(
            query=keywords,
            zone_id=zone_id,
            limit=50
        )

        # Filter by tags
        if tags:
            results = [
                r for r in results
                if any(tag in r.get("tags", []) for tag in tags)
            ]

        # Get context for AI
        context = self._extract_context(results[:10])

        return {
            "type": "natural_language",
            "query": parsed["original"],
            "zone": zone_id,
            "tags": tags,
            "count": len(results),
            "results": results[:10],
            "context": context,
            "interpretation_needed": True,
            "timestamp": datetime.utcnow().isoformat()
        }

    def _extract_context(self, results: List[Dict[str, Any]]) -> str:
        """Extract context from results for AI interpretation"""
        lines = []

        for i, result in enumerate(results, 1):
            doc_type = result.get("doc_type", "unknown")

            if doc_type == "entity":
                name = result.get("name", "Unknown")
                entity_type = result.get("entity_type", "")
                lines.append(f"{i}. [{entity_type}] {name}")

                # Add key observations
                if obs := result.get("observations", []):
                    for ob in obs[:2]:
                        if isinstance(ob, dict):
                            lines.append(f"   - {ob.get('text', '')}")

            elif doc_type == "document":
                title = result.get("title", "Untitled")
                content = result.get("content", "")[:200]
                lines.append(f"{i}. [doc] {title}")
                lines.append(f"   {content}...")

            elif doc_type == "relation":
                from_e = result.get("from_entity", "?")
                to_e = result.get("to_entity", "?")
                rel_type = result.get("relation_type", "?")
                lines.append(f"{i}. {from_e} --[{rel_type}]--> {to_e}")

        return "\n".join(lines)

    def tag_dataset(
        self,
        doc_ids: Union[str, List[str]],
        tags: Union[str, List[str]],
        zone_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Tag documents for organization

        Args:
            doc_ids: Document ID(s) to tag
            tags: Tag(s) to add (e.g., "#osint", "#important")
            zone_id: Zone

        Returns:
            Tagging result
        """
        # Normalize inputs
        if isinstance(doc_ids, str):
            doc_ids = [doc_ids]
        if isinstance(tags, str):
            tags = [tags]

        # Clean tags (remove # if present)
        tags = [tag.lstrip("#") for tag in tags]

        tagged_count = 0
        errors = []

        for doc_id in doc_ids:
            try:
                # Get document
                doc = self.backend.get_by_id(doc_id)
                if not doc:
                    errors.append(f"Document not found: {doc_id}")
                    continue

                # Add tags (merge with existing)
                existing_tags = doc.get("tags", [])
                if isinstance(existing_tags, str):
                    existing_tags = [existing_tags]

                new_tags = list(set(existing_tags + tags))
                doc["tags"] = new_tags

                # Re-index
                doc_type = doc.get("doc_type", "document")
                if doc_type == "entity":
                    self.backend.index_entity(doc, zone_id)
                elif doc_type == "document":
                    self.backend.index_document(doc, zone_id)

                tagged_count += 1

            except Exception as e:
                errors.append(f"Error tagging {doc_id}: {e}")

        return {
            "tagged": tagged_count,
            "total": len(doc_ids),
            "tags": tags,
            "errors": errors
        }

    def list_indices(self) -> Dict[str, Any]:
        """
        List all available search indices

        Returns:
            Index information with counts
        """
        zones = self.inventory.get_all_zones()

        indices = []
        for zone_id in zones:
            zone_data = self.inventory.get_zone_inventory(zone_id)

            total_docs = sum(meta.count for meta in zone_data.values())

            doc_types = {
                doc_type: meta.count
                for doc_type, meta in zone_data.items()
            }

            indices.append({
                "zone_id": zone_id,
                "total_documents": total_docs,
                "doc_types": doc_types
            })

        return {
            "total_zones": len(indices),
            "indices": indices,
            "timestamp": datetime.utcnow().isoformat()
        }

    def list_tags(self, zone_id: Optional[str] = None, min_count: int = 1) -> Dict[str, Any]:
        """
        List all available tags

        Args:
            zone_id: Optional zone filter
            min_count: Minimum document count for tag

        Returns:
            Tag statistics
        """
        zone_data = {}

        if zone_id:
            zone_data[zone_id] = self.inventory.get_zone_inventory(zone_id)
        else:
            for zid in self.inventory.get_all_zones():
                zone_data[zid] = self.inventory.get_zone_inventory(zid)

        # Aggregate tags
        all_tags = {}

        for zone_id, zone_inv in zone_data.items():
            for doc_type, meta in zone_inv.items():
                for tag, count in meta.tags.items():
                    if tag not in all_tags:
                        all_tags[tag] = {"count": 0, "zones": set()}
                    all_tags[tag]["count"] += count
                    all_tags[tag]["zones"].add(zone_id)

        # Filter by min_count
        filtered_tags = {
            tag: {
                "count": data["count"],
                "zones": list(data["zones"])
            }
            for tag, data in all_tags.items()
            if data["count"] >= min_count
        }

        # Sort by count
        sorted_tags = dict(
            sorted(filtered_tags.items(), key=lambda x: x[1]["count"], reverse=True)
        )

        return {
            "total_tags": len(sorted_tags),
            "tags": sorted_tags,
            "min_count": min_count,
            "timestamp": datetime.utcnow().isoformat()
        }

    def search_by_tags(
        self,
        tags: Union[str, List[str]],
        zone_id: Optional[str] = None,
        match_all: bool = False
    ) -> Dict[str, Any]:
        """
        Search documents by tags

        Args:
            tags: Tag(s) to search for
            zone_id: Optional zone filter
            match_all: If True, require all tags; if False, any tag

        Returns:
            Tagged documents
        """
        # Normalize tags
        if isinstance(tags, str):
            tags = [tags]
        tags = [tag.lstrip("#") for tag in tags]

        # Build query - search for documents with these tags
        # This is a simplified version - real implementation would use Elasticsearch
        # tag field filtering

        results = []

        # For now, do keyword search and filter
        for tag in tags:
            tag_results = self.backend.search_keyword(
                query=tag,
                zone_id=zone_id,
                limit=100
            )
            results.extend(tag_results)

        # Filter by tags
        filtered = []
        for result in results:
            result_tags = result.get("tags", [])
            if isinstance(result_tags, str):
                result_tags = [result_tags]

            if match_all:
                if all(tag in result_tags for tag in tags):
                    filtered.append(result)
            else:
                if any(tag in result_tags for tag in tags):
                    filtered.append(result)

        # Deduplicate by ID
        seen = set()
        unique_results = []
        for result in filtered:
            doc_id = result.get("_id")
            if doc_id not in seen:
                seen.add(doc_id)
                unique_results.append(result)

        return {
            "type": "tag_search",
            "tags": tags,
            "match_all": match_all,
            "zone": zone_id,
            "count": len(unique_results),
            "results": unique_results,
            "timestamp": datetime.utcnow().isoformat()
        }


# Convenience functions for slash command integration

def cym_search(query: str, backend, inventory, zone_id: str = "default") -> Dict[str, Any]:
    """
    Convenience function for /cym: searches

    Usage:
        /cym: "quantum computing"
        /cym: tell me about John Smith
        /cym: #osint #important find connections
        /cym: @corporate_intel executives
    """
    interface = SearchInterface(backend, inventory)
    return interface.parse_and_search(query, zone_id)


def cym_tag(doc_ids: Union[str, List[str]], tags: Union[str, List[str]], backend, inventory) -> Dict[str, Any]:
    """
    Tag documents

    Usage:
        cym_tag("doc_123", "#important")
        cym_tag(["doc_1", "doc_2"], ["#osint", "#verified"])
    """
    interface = SearchInterface(backend, inventory)
    return interface.tag_dataset(doc_ids, tags)


def cym_list_indices(inventory) -> Dict[str, Any]:
    """List all search indices"""
    interface = SearchInterface(None, inventory)
    return interface.list_indices()


def cym_list_tags(inventory, zone_id: Optional[str] = None) -> Dict[str, Any]:
    """List all tags"""
    interface = SearchInterface(None, inventory)
    return interface.list_tags(zone_id)
