"""
CyMonides 2.0 - Content Inventory System
Tracks what data has been indexed to enable intelligent routing and dynamic UI
"""

from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from collections import defaultdict, Counter
from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class ContentMetadata:
    """Metadata about indexed content"""
    doc_type: str  # entity, document, relation, observation
    zone_id: str
    count: int
    entity_types: Set[str] = field(default_factory=set)  # person, company, etc.
    available_fields: Set[str] = field(default_factory=set)  # email, phone, address, etc.
    countries: Counter = field(default_factory=Counter)
    tags: Counter = field(default_factory=Counter)
    date_ranges: Dict[str, Any] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "doc_type": self.doc_type,
            "zone_id": self.zone_id,
            "count": self.count,
            "entity_types": list(self.entity_types),
            "available_fields": list(self.available_fields),
            "countries": dict(self.countries),
            "tags": dict(self.tags),
            "date_ranges": self.date_ranges,
            "last_updated": self.last_updated
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContentMetadata':
        """Deserialize from dictionary"""
        return cls(
            doc_type=data["doc_type"],
            zone_id=data["zone_id"],
            count=data["count"],
            entity_types=set(data.get("entity_types", [])),
            available_fields=set(data.get("available_fields", [])),
            countries=Counter(data.get("countries", {})),
            tags=Counter(data.get("tags", {})),
            date_ranges=data.get("date_ranges", {}),
            last_updated=data.get("last_updated", datetime.utcnow().isoformat())
        )


class ContentInventory:
    """
    Content Inventory System

    Tracks what data has been indexed to enable:
    - Smart filtering (only show filters for data that exists)
    - Dynamic UI generation (show buttons relevant to current content)
    - Tool routing (match tool requirements with available data)
    - Pipeline suggestions (suggest workflows based on content)
    """

    def __init__(self, backend, cache_file: Optional[str] = None):
        """
        Initialize content inventory

        Args:
            backend: ElasticsearchBackend instance for querying
            cache_file: Optional file to cache inventory metadata
        """
        self.backend = backend
        self.cache_file = Path(cache_file) if cache_file else None

        # In-memory inventory cache
        # Structure: {zone_id: {doc_type: ContentMetadata}}
        self.inventory: Dict[str, Dict[str, ContentMetadata]] = defaultdict(dict)

        # Load cache if exists
        if self.cache_file and self.cache_file.exists():
            self._load_cache()

    def track_document(self, doc: Dict[str, Any], zone_id: str = "default"):
        """
        Track a newly indexed document

        Args:
            doc: Document that was indexed
            zone_id: Memory zone
        """
        doc_type = doc.get("doc_type", "document")

        # Get or create metadata
        if doc_type not in self.inventory[zone_id]:
            self.inventory[zone_id][doc_type] = ContentMetadata(
                doc_type=doc_type,
                zone_id=zone_id,
                count=0
            )

        meta = self.inventory[zone_id][doc_type]

        # Update count
        meta.count += 1

        # Track entity type
        if entity_type := doc.get("entity_type"):
            meta.entity_types.add(entity_type)

        # Track available fields
        for field in doc.keys():
            if field not in ["_id", "doc_type", "created_at", "zone_id"]:
                meta.available_fields.add(field)

        # Track country
        if country := doc.get("country"):
            meta.countries[country] += 1

        # Track tags
        if tags := doc.get("tags"):
            if isinstance(tags, list):
                for tag in tags:
                    meta.tags[tag] += 1
            elif isinstance(tags, str):
                meta.tags[tags] += 1

        # Update date range
        if created_at := doc.get("created_at"):
            if not meta.date_ranges or created_at < meta.date_ranges.get("earliest", ""):
                meta.date_ranges["earliest"] = created_at
            if not meta.date_ranges or created_at > meta.date_ranges.get("latest", ""):
                meta.date_ranges["latest"] = created_at

        meta.last_updated = datetime.utcnow().isoformat()

        # Save cache
        if self.cache_file:
            self._save_cache()

    def rebuild_from_backend(self, zone_id: Optional[str] = None):
        """
        Rebuild inventory by scanning backend

        Args:
            zone_id: Specific zone to rebuild, or None for all zones
        """
        print(f"🔄 Rebuilding content inventory{f' for zone: {zone_id}' if zone_id else ''}...")

        # Clear existing inventory for the zone(s)
        if zone_id:
            self.inventory[zone_id] = {}
        else:
            self.inventory.clear()

        # Query all documents from backend
        try:
            # Get all doc types
            for doc_type in ["entity", "document", "relation", "observation"]:
                query = {
                    "query": {
                        "bool": {
                            "must": [{"term": {"doc_type": doc_type}}]
                        }
                    },
                    "size": 10000  # Adjust based on data size
                }

                if zone_id:
                    query["query"]["bool"]["must"].append({"term": {"zone_id": zone_id}})

                results = self.backend.client.search(
                    index=self.backend.index_name,
                    body=query
                )

                # Process each document
                for hit in results["hits"]["hits"]:
                    doc = hit["_source"]
                    doc["_id"] = hit["_id"]
                    doc_zone = doc.get("zone_id", "default")
                    self.track_document(doc, doc_zone)

            print(f"✅ Inventory rebuilt: {self.get_summary()}")

        except Exception as e:
            print(f"⚠️  Error rebuilding inventory: {e}")

    def get_zone_inventory(self, zone_id: str = "default") -> Dict[str, ContentMetadata]:
        """Get inventory for a specific zone"""
        return self.inventory.get(zone_id, {})

    def get_all_zones(self) -> List[str]:
        """Get list of all zones with data"""
        return list(self.inventory.keys())

    def get_summary(self, zone_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get inventory summary

        Args:
            zone_id: Specific zone, or None for all zones

        Returns:
            Summary dictionary with counts and metadata
        """
        if zone_id:
            zones_to_summarize = {zone_id: self.inventory.get(zone_id, {})}
        else:
            zones_to_summarize = self.inventory

        summary = {
            "total_zones": len(zones_to_summarize),
            "zones": {}
        }

        for zid, zone_data in zones_to_summarize.items():
            zone_summary = {
                "total_documents": sum(meta.count for meta in zone_data.values()),
                "by_type": {}
            }

            for doc_type, meta in zone_data.items():
                zone_summary["by_type"][doc_type] = {
                    "count": meta.count,
                    "entity_types": list(meta.entity_types),
                    "available_fields": list(meta.available_fields),
                    "top_countries": meta.countries.most_common(5),
                    "top_tags": meta.tags.most_common(5)
                }

            summary["zones"][zid] = zone_summary

        return summary

    def generate_smart_filters(self, zone_id: str = "default", doc_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Generate smart filters based on actual data

        Args:
            zone_id: Zone to generate filters for
            doc_type: Specific doc type, or None for all

        Returns:
            List of filter definitions with actual values
        """
        filters = []
        zone_data = self.inventory.get(zone_id, {})

        if not zone_data:
            return filters

        # Determine which metadata to use
        if doc_type:
            metadata_list = [zone_data.get(doc_type)]
        else:
            metadata_list = zone_data.values()

        # Aggregate across metadata
        all_entity_types = set()
        all_countries = Counter()
        all_tags = Counter()
        all_fields = set()

        for meta in metadata_list:
            if meta:
                all_entity_types.update(meta.entity_types)
                all_countries.update(meta.countries)
                all_tags.update(meta.tags)
                all_fields.update(meta.available_fields)

        # Generate entity type filter
        if all_entity_types:
            filters.append({
                "type": "select",
                "field": "entity_type",
                "label": "Entity Type",
                "options": [
                    {"value": et, "label": et.replace("_", " ").title()}
                    for et in sorted(all_entity_types)
                ]
            })

        # Generate country filter (top 10)
        if all_countries:
            filters.append({
                "type": "multiselect",
                "field": "country",
                "label": "Country",
                "options": [
                    {"value": country, "label": f"{country} ({count})"}
                    for country, count in all_countries.most_common(10)
                ]
            })

        # Generate tags filter (top 20)
        if all_tags:
            filters.append({
                "type": "multiselect",
                "field": "tags",
                "label": "Tags",
                "options": [
                    {"value": tag, "label": f"{tag} ({count})"}
                    for tag, count in all_tags.most_common(20)
                ]
            })

        # Generate field existence filters
        field_filters = []
        for field in ["email", "phone", "address", "linkedin", "website"]:
            if field in all_fields:
                field_filters.append({
                    "value": field,
                    "label": field.title()
                })

        if field_filters:
            filters.append({
                "type": "multiselect",
                "field": "has_field",
                "label": "Has Field",
                "options": field_filters
            })

        return filters

    def can_support_tool(self, tool_requirements: Dict[str, Any], zone_id: str = "default") -> bool:
        """
        Check if current inventory can support a tool's requirements

        Args:
            tool_requirements: Tool's data requirements
                {
                    "required_types": ["entity:person"],
                    "required_fields": ["email"],
                    "min_count": 1
                }
            zone_id: Zone to check

        Returns:
            True if requirements are met
        """
        zone_data = self.inventory.get(zone_id, {})

        if not zone_data:
            return False

        # Check required types
        if required_types := tool_requirements.get("required_types"):
            for req_type in required_types:
                if ":" in req_type:
                    doc_type, entity_type = req_type.split(":", 1)
                    meta = zone_data.get(doc_type)
                    if not meta or entity_type not in meta.entity_types:
                        return False
                else:
                    if req_type not in zone_data:
                        return False

        # Check required fields
        if required_fields := tool_requirements.get("required_fields"):
            # Check if any metadata has all required fields
            has_all_fields = False
            for meta in zone_data.values():
                if all(field in meta.available_fields for field in required_fields):
                    has_all_fields = True
                    break
            if not has_all_fields:
                return False

        # Check minimum count
        if min_count := tool_requirements.get("min_count"):
            total_count = sum(meta.count for meta in zone_data.values())
            if total_count < min_count:
                return False

        return True

    def get_matching_content(self, criteria: Dict[str, Any], zone_id: str = "default") -> Dict[str, Any]:
        """
        Find content matching specific criteria

        Args:
            criteria: Search criteria
                {
                    "doc_type": "entity",
                    "entity_type": "person",
                    "has_fields": ["email", "phone"],
                    "country": "US"
                }
            zone_id: Zone to search

        Returns:
            Matching content summary
        """
        zone_data = self.inventory.get(zone_id, {})

        doc_type = criteria.get("doc_type")
        if not doc_type or doc_type not in zone_data:
            return {"count": 0, "matches": False}

        meta = zone_data[doc_type]

        # Check entity type
        if entity_type := criteria.get("entity_type"):
            if entity_type not in meta.entity_types:
                return {"count": 0, "matches": False}

        # Check has_fields
        if has_fields := criteria.get("has_fields"):
            if not all(field in meta.available_fields for field in has_fields):
                return {"count": 0, "matches": False}

        # Check country (approximate count)
        if country := criteria.get("country"):
            count = meta.countries.get(country, 0)
            return {"count": count, "matches": count > 0}

        return {"count": meta.count, "matches": True}

    def _save_cache(self):
        """Save inventory to cache file"""
        if not self.cache_file:
            return

        try:
            cache_data = {
                zone_id: {
                    doc_type: meta.to_dict()
                    for doc_type, meta in zone_data.items()
                }
                for zone_id, zone_data in self.inventory.items()
            }

            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

        except Exception as e:
            print(f"⚠️  Error saving inventory cache: {e}")

    def _load_cache(self):
        """Load inventory from cache file"""
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            for zone_id, zone_data in cache_data.items():
                self.inventory[zone_id] = {
                    doc_type: ContentMetadata.from_dict(meta_dict)
                    for doc_type, meta_dict in zone_data.items()
                }

            print(f"✅ Loaded inventory cache from {self.cache_file}")

        except Exception as e:
            print(f"⚠️  Error loading inventory cache: {e}")

    def stats(self) -> str:
        """Get human-readable stats"""
        total_zones = len(self.inventory)
        total_docs = sum(
            sum(meta.count for meta in zone_data.values())
            for zone_data in self.inventory.values()
        )

        lines = [
            f"Content Inventory Stats",
            f"======================",
            f"Total Zones: {total_zones}",
            f"Total Documents: {total_docs}",
            f"",
        ]

        for zone_id, zone_data in self.inventory.items():
            zone_total = sum(meta.count for meta in zone_data.values())
            lines.append(f"Zone: {zone_id} ({zone_total} docs)")

            for doc_type, meta in zone_data.items():
                lines.append(f"  {doc_type}: {meta.count}")
                if meta.entity_types:
                    lines.append(f"    Types: {', '.join(meta.entity_types)}")
                if meta.countries:
                    top_countries = ', '.join(f"{c}({n})" for c, n in meta.countries.most_common(3))
                    lines.append(f"    Countries: {top_countries}")

        return "\n".join(lines)
