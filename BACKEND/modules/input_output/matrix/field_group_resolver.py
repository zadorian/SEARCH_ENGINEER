#!/usr/bin/env python3
"""
Field Group Resolver - Maps semantic groups to Elasticsearch fields.

This module provides utilities for resolving semantic field groups
(like EMAIL_RAW, PERSON_NAME, COMPANY_NAME) to actual Elasticsearch
field names across multiple indices.

Usage:
    from field_group_resolver import FieldGroupResolver

    resolver = FieldGroupResolver()

    # Get all fields for a group
    fields = resolver.get_fields_for_group("EMAIL_RAW")
    # -> [("email", ["breach_records"]), ("all_emails", ["kazaword_emails"]), ...]

    # Build ES multi_match query fields
    es_fields = resolver.build_es_fields("PERSON_NAME", indices=["openownership"])
    # -> ["interested_party_name"]

    # Get searchable groups (excluding GARBAGE quality)
    groups = resolver.get_searchable_groups()
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)

MATRIX_DIR = Path(__file__).parent


class FieldGroupResolver:
    """Resolves semantic field groups to ES field names."""

    QUALITY_SEARCHABLE = {"HIGH", "MEDIUM"}
    QUALITY_EXCLUDED = {"GARBAGE", "INTERNAL_ONLY", "UNGROUPABLE"}

    def __init__(self, field_groups_path: Optional[Path] = None):
        self._path = field_groups_path or (MATRIX_DIR / "field_groups.json")
        self._groups: Optional[Dict] = None
        self._load()

    def _load(self):
        """Load field_groups.json."""
        try:
            with open(self._path) as f:
                data = json.load(f)
                self._groups = data.get("field_groups", {})
                meta = data.get("_meta", {})
                logger.info(
                    f"[FieldGroupResolver] Loaded {len(self._groups)} groups "
                    f"(generated: {meta.get('generated', 'unknown')})"
                )
        except Exception as e:
            logger.warning(f"[FieldGroupResolver] Failed to load field groups: {e}")
            self._groups = {}

    def reload(self):
        """Reload the field groups from disk."""
        self._load()

    def get_all_groups(self) -> List[str]:
        """Get all group names."""
        return list(self._groups.keys()) if self._groups else []

    def get_searchable_groups(self) -> List[str]:
        """Get group names that are safe for user search (HIGH/MEDIUM quality)."""
        if not self._groups:
            return []
        return [
            name for name, group in self._groups.items()
            if group.get("quality") in self.QUALITY_SEARCHABLE
        ]

    def get_group(self, group_name: str) -> Optional[Dict]:
        """Get a specific group definition."""
        if not self._groups:
            return None
        return self._groups.get(group_name)

    def get_fields_for_group(
        self,
        group_name: str
    ) -> List[Tuple[str, List[str]]]:
        """
        Get all fields for a semantic group.

        Args:
            group_name: e.g., "EMAIL_RAW", "PERSON_NAME"

        Returns:
            List of (field_name, indices) tuples
        """
        group = self.get_group(group_name)
        if not group:
            return []

        fields = group.get("fields", {})
        return [(field, indices) for field, indices in fields.items()]

    def build_es_fields(
        self,
        group_name: str,
        indices: Optional[List[str]] = None
    ) -> List[str]:
        """
        Build Elasticsearch field list for multi_match query.

        Args:
            group_name: Semantic group name
            indices: Optional list of indices to filter to

        Returns:
            List of field names suitable for ES query
        """
        all_fields = self.get_fields_for_group(group_name)

        if indices:
            # Filter to fields that exist in specified indices
            return [
                field for field, field_indices in all_fields
                if any(idx in indices for idx in field_indices)
            ]

        return [field for field, _ in all_fields]

    def get_quality(self, group_name: str) -> Optional[str]:
        """Get quality rating for a group."""
        group = self.get_group(group_name)
        return group.get("quality") if group else None

    def is_searchable(self, group_name: str) -> bool:
        """Check if a group is safe for user search."""
        quality = self.get_quality(group_name)
        return quality in self.QUALITY_SEARCHABLE

    def get_samples(self, group_name: str) -> List[Any]:
        """Get sample values for a group."""
        group = self.get_group(group_name)
        return group.get("samples", []) if group else []

    def get_notes(self, group_name: str) -> Optional[str]:
        """Get notes/warnings for a group."""
        group = self.get_group(group_name)
        return group.get("notes") if group else None

    def find_group_for_field(self, field_name: str) -> Optional[str]:
        """
        Find which semantic group a field belongs to.

        Args:
            field_name: ES field name (e.g., "email", "interested_party_name")

        Returns:
            Group name or None if not found
        """
        if not self._groups:
            return None

        for group_name, group in self._groups.items():
            if field_name in group.get("fields", {}):
                return group_name

        return None

    def build_multi_group_query(
        self,
        group_names: List[str],
        indices: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """
        Build field lists for multiple groups at once.

        Returns:
            Dict mapping group name to list of ES fields
        """
        result = {}
        for group_name in group_names:
            fields = self.build_es_fields(group_name, indices)
            if fields:
                result[group_name] = fields
        return result

    def get_all_fields_flat(
        self,
        quality_filter: Optional[List[str]] = None
    ) -> List[Tuple[str, str, List[str]]]:
        """
        Get all fields as flat list with their groups.

        Args:
            quality_filter: Optional list of qualities to include

        Returns:
            List of (field_name, group_name, indices) tuples
        """
        if not self._groups:
            return []

        result = []
        for group_name, group in self._groups.items():
            quality = group.get("quality", "")

            if quality_filter and quality not in quality_filter:
                continue

            for field, indices in group.get("fields", {}).items():
                result.append((field, group_name, indices))

        return result


# Singleton instance
_resolver: Optional[FieldGroupResolver] = None


def get_resolver() -> FieldGroupResolver:
    """Get the singleton FieldGroupResolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = FieldGroupResolver()
    return _resolver


# Convenience functions
def get_fields_for_group(group_name: str) -> List[Tuple[str, List[str]]]:
    """Get fields for a semantic group."""
    return get_resolver().get_fields_for_group(group_name)


def build_es_fields(
    group_name: str,
    indices: Optional[List[str]] = None
) -> List[str]:
    """Build ES field list for a semantic group."""
    return get_resolver().build_es_fields(group_name, indices)


def get_searchable_groups() -> List[str]:
    """Get groups safe for user search."""
    return get_resolver().get_searchable_groups()


def is_searchable(group_name: str) -> bool:
    """Check if group is safe for user search."""
    return get_resolver().is_searchable(group_name)


# CLI
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Field Group Resolver")
    parser.add_argument("group", nargs="?", help="Group name to query")
    parser.add_argument("--list", "-l", action="store_true", help="List all groups")
    parser.add_argument("--searchable", "-s", action="store_true", help="List searchable groups only")
    parser.add_argument("--indices", "-i", nargs="+", help="Filter to specific indices")
    parser.add_argument("--find-field", "-f", help="Find which group a field belongs to")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    resolver = FieldGroupResolver()

    if args.list:
        groups = resolver.get_all_groups()
        if args.json:
            print(json.dumps(groups, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f" All Field Groups ({len(groups)} total)")
            print(f"{'='*60}")
            for g in sorted(groups):
                quality = resolver.get_quality(g)
                searchable = "✓" if resolver.is_searchable(g) else "✗"
                print(f"  {searchable} {g:30} [{quality}]")

    elif args.searchable:
        groups = resolver.get_searchable_groups()
        if args.json:
            print(json.dumps(groups, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f" Searchable Field Groups ({len(groups)} total)")
            print(f"{'='*60}")
            for g in sorted(groups):
                fields = resolver.build_es_fields(g)
                print(f"  {g:30} [{len(fields)} fields]")

    elif args.find_field:
        group = resolver.find_group_for_field(args.find_field)
        if args.json:
            print(json.dumps({"field": args.find_field, "group": group}))
        else:
            if group:
                print(f"\nField '{args.find_field}' belongs to group: {group}")
                print(f"  Quality: {resolver.get_quality(group)}")
                notes = resolver.get_notes(group)
                if notes:
                    print(f"  Notes: {notes}")
            else:
                print(f"\nField '{args.find_field}' not found in any group")

    elif args.group:
        fields = resolver.build_es_fields(args.group, args.indices)
        all_fields = resolver.get_fields_for_group(args.group)

        if args.json:
            print(json.dumps({
                "group": args.group,
                "quality": resolver.get_quality(args.group),
                "searchable": resolver.is_searchable(args.group),
                "fields": fields,
                "all_fields": [{"field": f, "indices": i} for f, i in all_fields],
                "samples": resolver.get_samples(args.group),
                "notes": resolver.get_notes(args.group)
            }, indent=2))
        else:
            group_data = resolver.get_group(args.group)
            if not group_data:
                print(f"\nGroup '{args.group}' not found")
            else:
                print(f"\n{'='*60}")
                print(f" Group: {args.group}")
                print(f"{'='*60}")
                print(f"  Quality: {group_data.get('quality')}")
                print(f"  Description: {group_data.get('description', 'N/A')}")
                if group_data.get('notes'):
                    print(f"  Notes: {group_data.get('notes')}")
                print(f"\n  Fields ({len(fields)} matching):")
                for field, indices in all_fields:
                    filtered = "(filtered)" if args.indices and field not in fields else ""
                    print(f"    {field:40} [{', '.join(indices[:3])}] {filtered}")

                samples = resolver.get_samples(args.group)
                if samples:
                    print(f"\n  Samples:")
                    for s in samples[:5]:
                        print(f"    → {str(s)[:60]}")

    else:
        print("Usage: python field_group_resolver.py GROUP_NAME")
        print("       python field_group_resolver.py --list")
        print("       python field_group_resolver.py --searchable")
        print("       python field_group_resolver.py --find-field email")
        print("       python field_group_resolver.py EMAIL_RAW --indices breach_records")
