"""
Cymonides-1 Bridge for EYE-D
Handles automatic tagging with VERIFIED/UNVERIFIED edges and priority queue recursive search
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from elasticsearch import Elasticsearch

# Elasticsearch configuration
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
ES_INDEX = os.getenv("CYMONIDES_1_INDEX", "cymonides-1")


@dataclass
class EmbeddedEdge:
    """Embedded edge in C1 nodes with automatic tagging"""
    target_id: str
    relation: str
    verification_status: str  # VERIFIED or UNVERIFIED
    connection_reason: str  # One of 44 connection reason types
    additional_reasons: List[str] = field(default_factory=list)
    query_sequence_tag: Optional[str] = None  # e.g., "email@address.com_1" (UNVERIFIED only)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class C1Node:
    """C1 Node structure with automatic tagging support"""
    id: str
    node_class: str  # ENTITY, NARRATIVE, NEXUS, LOCATION
    type: str  # email, phone, person, company, aggregator_result, etc.
    canonicalValue: str
    label: str

    # Core fields
    value: Optional[str] = None
    comment: Optional[str] = None  # Raw output stored here for SOURCE nodes

    # Embedded edges
    embedded_edges: List[Dict] = field(default_factory=list)

    # Verification tags (for SOURCE/NEXUS nodes like aggregator_result)
    verification_status: Optional[str] = None  # VERIFIED or UNVERIFIED
    connection_reason: Optional[str] = None  # One of 44 connection reason types
    additional_reasons: List[str] = field(default_factory=list)
    query_sequence_tag: Optional[str] = None  # Sequential tag for UNVERIFIED results

    # Timestamps
    createdAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updatedAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    lastSeen: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Project
    projectId: Optional[str] = None

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


class C1Bridge:
    """Bridge to Cymonides-1 for EYE-D with priority queue recursive search"""

    def __init__(self, es_host: str = ES_HOST, es_index: str = ES_INDEX):
        self.es = Elasticsearch([es_host])
        self.es_index = es_index

    def get_priority_queues(self, project_id: str) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        Build VERIFIED and UNVERIFIED priority queues from Elasticsearch.

        Returns:
            (verified_queue, unverified_queue)
            verified_queue: List of entity canonical values to search
            unverified_queue: List of (canonical_value, current_tag) tuples
        """
        verified_queue = []
        unverified_queue = []

        # Query all nodes in this project
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"projectId": project_id}},
                        {"exists": {"field": "embedded_edges"}}
                    ]
                }
            },
            "size": 10000  # Adjust based on expected node count
        }

        try:
            response = self.es.search(index=self.es_index, body=query)

            for hit in response['hits']['hits']:
                node = hit['_source']
                canonical_value = node.get('canonicalValue')

                if not canonical_value:
                    continue

                # Check all incoming edges (embedded_edges)
                for edge in node.get('embedded_edges', []):
                    verification_status = edge.get('verification_status')
                    query_tag = edge.get('query_sequence_tag')
                    already_searched = edge.get('already_searched', False)

                    # VERIFIED entities go to priority queue immediately
                    if verification_status == 'VERIFIED' and not already_searched:
                        if canonical_value not in verified_queue:
                            verified_queue.append(canonical_value)

                    # UNVERIFIED _1 entities wait in queue
                    elif verification_status == 'UNVERIFIED' and query_tag and query_tag.endswith('_1'):
                        if not any(item[0] == canonical_value for item in unverified_queue):
                            unverified_queue.append((canonical_value, query_tag))

            print(f"✓ Priority queues built: {len(verified_queue)} VERIFIED, {len(unverified_queue)} UNVERIFIED")
            return verified_queue, unverified_queue

        except Exception as e:
            print(f"Error building priority queues: {e}")
            return [], []

    def increment_sequence_tag(self, entity_value: str, current_tag: str) -> str:
        """
        Increment sequence tag when entity is searched.

        Args:
            entity_value: The entity being searched (e.g., "john_smith")
            current_tag: Current tag (e.g., "email@address.com_1")

        Returns:
            New tag with incremented number (e.g., "email@address.com_2")
        """
        if not current_tag or '_' not in current_tag:
            return f"{entity_value}_1"

        # Parse current tag: "base_N" → extract base and N
        try:
            base, num = current_tag.rsplit('_', 1)
            new_num = int(num) + 1
            return f"{base}_{new_num}"
        except (ValueError, IndexError):
            # If parsing fails, start from _1
            return f"{entity_value}_1"

    def update_edge_tag(self, project_id: str, entity_value: str, old_tag: str, new_tag: str) -> bool:
        """
        Update the query_sequence_tag for all edges targeting this entity.

        Args:
            project_id: Project ID
            entity_value: Canonical value of the entity
            old_tag: Current tag
            new_tag: New incremented tag

        Returns:
            True if successful
        """
        # Find all nodes with edges pointing to this entity
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"projectId": project_id}},
                        {"nested": {
                            "path": "embedded_edges",
                            "query": {
                                "term": {"embedded_edges.query_sequence_tag": old_tag}
                            }
                        }}
                    ]
                }
            },
            "size": 1000
        }

        try:
            response = self.es.search(index=self.es_index, body=query)

            for hit in response['hits']['hits']:
                node_id = hit['_id']
                node = hit['_source']

                # Update embedded edges
                updated = False
                for edge in node.get('embedded_edges', []):
                    if edge.get('query_sequence_tag') == old_tag:
                        edge['query_sequence_tag'] = new_tag
                        edge['already_searched'] = True  # Mark as searched
                        updated = True

                if updated:
                    # Update the node
                    self.es.update(
                        index=self.es_index,
                        id=node_id,
                        body={
                            "doc": {
                                "embedded_edges": node['embedded_edges'],
                                "updatedAt": datetime.utcnow().isoformat()
                            }
                        }
                    )

            print(f"✓ Updated tags: {old_tag} → {new_tag}")
            return True

        except Exception as e:
            print(f"Error updating edge tags: {e}")
            return False

    def check_verification_upgrade(self, entity_value: str, project_id: str) -> Tuple[bool, str]:
        """
        Check if an UNVERIFIED entity should be upgraded to VERIFIED.

        An UNVERIFIED entity can be upgraded if:
        1. It appears in same breach record (aggregator_result) with VERIFIED entities
        2. It connects to VERIFIED entities through strong entity type pairs
        3. Multiple VERIFIED contexts confirm it

        Args:
            entity_value: Canonical value of the entity to check
            project_id: Project ID

        Returns:
            (should_upgrade: bool, reason: str)
        """
        # Find the entity node
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"projectId": project_id}},
                        {"term": {"canonicalValue": entity_value}}
                    ]
                }
            }
        }

        try:
            response = self.es.search(index=self.es_index, body=query)

            if response['hits']['total']['value'] == 0:
                return False, "entity_not_found"

            entity_node = response['hits']['hits'][0]['_source']

            # Check all SOURCE nodes (aggregator_result) that mention this entity
            source_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"projectId": project_id}},
                            {"term": {"type": "aggregator_result"}},
                            {"nested": {
                                "path": "embedded_edges",
                                "query": {
                                    "term": {"embedded_edges.target_id": entity_node['id']}
                                }
                            }}
                        ]
                    }
                },
                "size": 100
            }

            source_response = self.es.search(index=self.es_index, body=source_query)

            verified_cooccurrences = 0
            upgrade_reasons = []

            for source_hit in source_response['hits']['hits']:
                source_node = source_hit['_source']

                # Check if this SOURCE node has VERIFIED status
                if source_node.get('verification_status') == 'VERIFIED':
                    verified_cooccurrences += 1
                    upgrade_reasons.append(f"same_breach_record:{source_node.get('id')}")
                    continue

                # Check if other entities in same SOURCE are VERIFIED
                other_edges = source_node.get('embedded_edges', [])
                has_verified_sibling = False

                for edge in other_edges:
                    target_id = edge.get('target_id')
                    if target_id == entity_node['id']:
                        continue  # Skip self

                    # Check if target is VERIFIED
                    if edge.get('verification_status') == 'VERIFIED':
                        has_verified_sibling = True
                        verified_cooccurrences += 1
                        upgrade_reasons.append(f"cooccurs_with_verified:{target_id}")
                        break

            # Upgrade if found with VERIFIED entities in same results
            if verified_cooccurrences > 0:
                reason = f"found_with_verified_entities:{verified_cooccurrences}x"
                return True, reason

            return False, "no_verified_connections"

        except Exception as e:
            print(f"Error checking verification upgrade: {e}")
            return False, f"error:{str(e)}"

    def upgrade_to_verified(self, entity_value: str, project_id: str, upgrade_reason: str) -> bool:
        """
        Upgrade an entity from UNVERIFIED to VERIFIED.

        Updates:
        - verification_status: UNVERIFIED → VERIFIED
        - Removes query_sequence_tag (no longer needed)
        - Updates connection_reason to reflect upgrade
        - Sets already_searched = False (allow re-searching as VERIFIED)

        Args:
            entity_value: Canonical value of the entity
            project_id: Project ID
            upgrade_reason: Reason for upgrade

        Returns:
            True if successful
        """
        # Find all edges targeting this entity
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"projectId": project_id}},
                        {"nested": {
                            "path": "embedded_edges",
                            "query": {
                                "bool": {
                                    "must": [
                                        {"match": {"embedded_edges.target_id": entity_value}},
                                        {"term": {"embedded_edges.verification_status": "UNVERIFIED"}}
                                    ]
                                }
                            }
                        }}
                    ]
                }
            },
            "size": 1000
        }

        try:
            response = self.es.search(index=self.es_index, body=query)

            updated_count = 0

            for hit in response['hits']['hits']:
                node_id = hit['_id']
                node = hit['_source']

                # Update all edges to this entity
                updated = False
                for edge in node.get('embedded_edges', []):
                    # Match by target or by canonical value in tag
                    if (edge.get('target_id') == entity_value or
                        entity_value in str(edge.get('query_sequence_tag', ''))):

                        if edge.get('verification_status') == 'UNVERIFIED':
                            # Upgrade to VERIFIED
                            edge['verification_status'] = 'VERIFIED'
                            edge['query_sequence_tag'] = None  # Remove tag
                            edge['already_searched'] = False  # Allow re-search
                            edge['upgrade_reason'] = upgrade_reason
                            edge['upgraded_at'] = datetime.utcnow().isoformat()
                            updated = True

                if updated:
                    # Update the node
                    self.es.update(
                        index=self.es_index,
                        id=node_id,
                        body={
                            "doc": {
                                "embedded_edges": node['embedded_edges'],
                                "updatedAt": datetime.utcnow().isoformat()
                            }
                        }
                    )
                    updated_count += 1

            print(f"🔄 VERIFICATION UPGRADE: {entity_value}")
            print(f"   Reason: {upgrade_reason}")
            print(f"   Updated {updated_count} edges")
            print(f"   Status: UNVERIFIED → VERIFIED")

            return True

        except Exception as e:
            print(f"Error upgrading to verified: {e}")
            return False

    def recursive_eyed_search(
        self,
        initial_query: str,
        project_id: str,
        max_depth: int = 3,
        search_function=None
    ) -> Dict:
        """
        Perform recursive EYE-D searches with VERIFIED priority and verification cascade.

        Args:
            initial_query: Starting search value
            project_id: Project ID
            max_depth: Maximum recursion depth (default 3)
            search_function: Function to call for each search (must be provided)

        Returns:
            Summary of searches performed including upgrade statistics
        """
        if not search_function:
            raise ValueError("search_function must be provided")

        depth = 1
        total_searches = 0
        verified_searches = 0
        unverified_searches = 0
        upgraded_count = 0

        print(f"\n{'='*60}")
        print(f"RECURSIVE EYE-D SEARCH - Verification Cascade Strategy")
        print(f"Initial Query: {initial_query}")
        print(f"Max Depth: {max_depth}")
        print(f"{'='*60}\n")

        # Initial search
        print(f"[Depth {depth}] Searching initial query: {initial_query}")
        try:
            search_function(initial_query)
            total_searches += 1
        except Exception as e:
            print(f"Error in initial search: {e}")
            return {"error": str(e)}

        # Recursive loop with priority queues and verification cascade
        while depth <= max_depth:
            print(f"\n{'─'*60}")
            print(f"[Depth {depth}] Building priority queues...")
            print(f"{'─'*60}")

            verified_queue, unverified_queue = self.get_priority_queues(project_id)

            if not verified_queue and not unverified_queue:
                print(f"✓ No more entities to search. Stopping at depth {depth}.")
                break

            # PHASE 1: Exhaust VERIFIED queue first
            if verified_queue:
                print(f"\n🟢 VERIFIED QUEUE: {len(verified_queue)} entities")
                for entity in verified_queue:
                    print(f"  → Searching VERIFIED entity: {entity}")
                    try:
                        search_function(entity)
                        total_searches += 1
                        verified_searches += 1
                    except Exception as e:
                        print(f"  ✗ Error: {e}")

            # PHASE 2: Only after VERIFIED queue is empty, process UNVERIFIED with cascade
            if not verified_queue and unverified_queue:
                print(f"\n🔵 UNVERIFIED QUEUE: {len(unverified_queue)} entities")
                print(f"   Checking for verification upgrades...\n")

                newly_verified = []  # Track upgrades for immediate processing

                for entity_value, current_tag in unverified_queue:
                    # Increment tag before searching
                    new_tag = self.increment_sequence_tag(entity_value, current_tag)
                    print(f"  → Searching UNVERIFIED entity: {entity_value} (tag: {current_tag} → {new_tag})")

                    # Update tag in Elasticsearch
                    self.update_edge_tag(project_id, entity_value, current_tag, new_tag)

                    # Search the entity
                    try:
                        search_function(entity_value)
                        total_searches += 1
                        unverified_searches += 1

                        # ✨ VERIFICATION CASCADE: Check if this entity should be upgraded
                        print(f"  ⚡ Checking verification upgrade for {entity_value}...")
                        should_upgrade, upgrade_reason = self.check_verification_upgrade(
                            entity_value, project_id
                        )

                        if should_upgrade:
                            # UPGRADE to VERIFIED
                            success = self.upgrade_to_verified(entity_value, project_id, upgrade_reason)
                            if success:
                                upgraded_count += 1
                                # 🚀 IMMEDIATE PRIORITY: Add to front of newly_verified list
                                newly_verified.insert(0, entity_value)
                                print(f"  🎯 UPGRADED TO VERIFIED: {entity_value}")
                                print(f"     ➜ Will be searched IMMEDIATELY with highest priority")
                        else:
                            print(f"  ○ Remains UNVERIFIED: {upgrade_reason}")

                    except Exception as e:
                        print(f"  ✗ Error: {e}")

                # 🔄 IMMEDIATE CASCADE: Process newly verified entities RIGHT NOW
                if newly_verified:
                    print(f"\n{'─'*60}")
                    print(f"🎯 VERIFICATION CASCADE: {len(newly_verified)} entities upgraded!")
                    print(f"   Processing immediately with HIGHEST PRIORITY...")
                    print(f"{'─'*60}\n")

                    for entity in newly_verified:
                        print(f"  🟢 [NEWLY VERIFIED] Searching: {entity}")
                        try:
                            search_function(entity)
                            total_searches += 1
                            verified_searches += 1
                        except Exception as e:
                            print(f"  ✗ Error: {e}")

                    print(f"\n  ✓ Cascade complete. Returning to main loop...")

            depth += 1

        print(f"\n{'='*60}")
        print(f"RECURSIVE SEARCH COMPLETE - VERIFICATION CASCADE")
        print(f"{'='*60}")
        print(f"Total searches: {total_searches}")
        print(f"VERIFIED searches: {verified_searches}")
        print(f"UNVERIFIED searches: {unverified_searches}")
        print(f"🎯 Entities upgraded: {upgraded_count}")
        print(f"Final depth: {depth - 1}")
        print(f"{'='*60}\n")

        return {
            "total_searches": total_searches,
            "verified_searches": verified_searches,
            "unverified_searches": unverified_searches,
            "upgraded_count": upgraded_count,
            "final_depth": depth - 1
        }


__all__ = ['C1Bridge', 'C1Node', 'EmbeddedEdge']
