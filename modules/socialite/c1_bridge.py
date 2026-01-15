"""
Cymonides-1 Bridge for SOCIALITE
Handles automatic tagging with VERIFIED/UNVERIFIED edges and priority queue recursive search.

Modeled exactly on EYE-D c1_bridge.py pattern.
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
    connection_reason: str  # One of SOCIALITE connection reason types
    additional_reasons: List[str] = field(default_factory=list)
    query_sequence_tag: Optional[str] = None  # e.g., "username_1" (UNVERIFIED only)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class C1Node:
    """C1 Node structure with automatic tagging support"""
    id: str
    node_class: str  # SUBJECT, LOCATION, NARRATIVE, NEXUS (per /data/CLASSES/)
    type: str  # profile, post, username, person, company, platform_url, etc.
    canonicalValue: str
    label: str

    # Core fields
    value: Optional[str] = None
    comment: Optional[str] = None  # Raw output stored here for SOURCE nodes

    # Embedded edges
    embedded_edges: List[Dict] = field(default_factory=list)

    # Verification tags (for SOURCE/NEXUS nodes)
    verification_status: Optional[str] = None  # VERIFIED or UNVERIFIED
    connection_reason: Optional[str] = None
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
    """Bridge to Cymonides-1 for SOCIALITE with priority queue recursive search"""

    # CLASS_MAP for social media entities per /data/CLASSES/
    CLASS_MAP = {
        # SUBJECT - entities (people, identifiers, accounts)
        'person': 'SUBJECT',
        'username': 'SUBJECT',
        'company': 'SUBJECT',
        'profile': 'SUBJECT',
        'connection': 'SUBJECT',  # Social connection between users
        
        # LOCATION - platforms, infrastructure
        'platform': 'LOCATION',
        'facebook_url': 'LOCATION',
        'instagram_url': 'LOCATION',
        'twitter_url': 'LOCATION',
        'threads_url': 'LOCATION',
        'linkedin_url': 'LOCATION',
        'tiktok_url': 'LOCATION',
        
        # NARRATIVE - content, posts
        'post': 'NARRATIVE',
        'comment': 'NARRATIVE',
        'reel': 'NARRATIVE',
        'story': 'NARRATIVE',
        'social_profile_data': 'NARRATIVE',  # Aggregated profile data
    }
    
    # Edge types for SOCIALITE scenarios
    EDGE_TYPES = {
        # Profile discovery
        'finds': 'username finds profile on platform',
        'has_account_on': 'username → platform relationship',
        'has_profile': 'person_name → profile URL',
        
        # Social connections
        'connected_to': 'person → person (bidirectional connection)',
        'follows': 'profile → profile (unidirectional)',
        'followed_by': 'profile → profile (reverse follow)',
        
        # Employment/affiliation
        'has_employee': 'company → person',
        'works_at': 'person → company',
        
        # Content relationships
        'posted': 'profile → post',
        'commented_on': 'profile → post (via comment)',
        'liked': 'profile → post',
        'shared': 'profile → post',
        
        # Identity linking
        'related_to': 'entity → entity (general relation)',
        'same_as': 'profile → profile (same person different platforms)',
        'input_of': 'entity was input to aggregator',
        'output_of': 'entity was output from aggregator',
    }

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

        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"projectId": project_id}},
                        {"exists": {"field": "embedded_edges"}}
                    ]
                }
            },
            "size": 10000
        }

        try:
            response = self.es.search(index=self.es_index, body=query)

            for hit in response['hits']['hits']:
                node = hit['_source']
                canonical_value = node.get('canonicalValue')

                if not canonical_value:
                    continue

                for edge in node.get('embedded_edges', []):
                    verification_status = edge.get('verification_status')
                    query_tag = edge.get('query_sequence_tag')
                    already_searched = edge.get('already_searched', False)

                    if verification_status == 'VERIFIED' and not already_searched:
                        if canonical_value not in verified_queue:
                            verified_queue.append(canonical_value)

                    elif verification_status == 'UNVERIFIED' and query_tag and query_tag.endswith('_1'):
                        if not any(item[0] == canonical_value for item in unverified_queue):
                            unverified_queue.append((canonical_value, query_tag))

            print(f"✓ Priority queues built: {len(verified_queue)} VERIFIED, {len(unverified_queue)} UNVERIFIED")
            return verified_queue, unverified_queue

        except Exception as e:
            print(f"Error building priority queues: {e}")
            return [], []

    def increment_sequence_tag(self, entity_value: str, current_tag: str) -> str:
        """Increment sequence tag when entity is searched."""
        if not current_tag or '_' not in current_tag:
            return f"{entity_value}_1"

        try:
            base, num = current_tag.rsplit('_', 1)
            new_num = int(num) + 1
            return f"{base}_{new_num}"
        except (ValueError, IndexError):
            return f"{entity_value}_1"

    def update_edge_tag(self, project_id: str, entity_value: str, old_tag: str, new_tag: str) -> bool:
        """Update the query_sequence_tag for all edges targeting this entity."""
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

                updated = False
                for edge in node.get('embedded_edges', []):
                    if edge.get('query_sequence_tag') == old_tag:
                        edge['query_sequence_tag'] = new_tag
                        edge['already_searched'] = True
                        updated = True

                if updated:
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

        For SOCIALITE, upgrade when:
        1. Profile URL directly confirms username
        2. Same person appears on multiple platforms with same identifiers
        3. Company record confirms employee
        4. Mutual connections confirm relationship
        """
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

            # Check for social profile confirmations
            source_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"projectId": project_id}},
                            {"term": {"type": "social_profile_data"}},
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

                if source_node.get('verification_status') == 'VERIFIED':
                    verified_cooccurrences += 1
                    upgrade_reasons.append(f"same_profile_data:{source_node.get('id')}")
                    continue

                other_edges = source_node.get('embedded_edges', [])
                for edge in other_edges:
                    target_id = edge.get('target_id')
                    if target_id == entity_node['id']:
                        continue

                    if edge.get('verification_status') == 'VERIFIED':
                        verified_cooccurrences += 1
                        upgrade_reasons.append(f"cooccurs_with_verified:{target_id}")
                        break

            if verified_cooccurrences > 0:
                reason = f"found_with_verified_entities:{verified_cooccurrences}x"
                return True, reason

            return False, "no_verified_connections"

        except Exception as e:
            print(f"Error checking verification upgrade: {e}")
            return False, f"error:{str(e)}"

    def upgrade_to_verified(self, entity_value: str, project_id: str, upgrade_reason: str) -> bool:
        """Upgrade an entity from UNVERIFIED to VERIFIED."""
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

                updated = False
                for edge in node.get('embedded_edges', []):
                    if (edge.get('target_id') == entity_value or
                        entity_value in str(edge.get('query_sequence_tag', ''))):

                        if edge.get('verification_status') == 'UNVERIFIED':
                            edge['verification_status'] = 'VERIFIED'
                            edge['query_sequence_tag'] = None
                            edge['already_searched'] = False
                            edge['upgrade_reason'] = upgrade_reason
                            edge['upgraded_at'] = datetime.utcnow().isoformat()
                            updated = True

                if updated:
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

    def create_profile_node(
        self,
        platform: str,
        username: str,
        profile_url: str,
        raw_data: Dict[str, Any],
        project_id: str,
        input_id: str = None,
        verification_status: str = "VERIFIED"
    ) -> Dict:
        """
        Create a social profile node in C1.
        
        Args:
            platform: facebook, instagram, twitter, linkedin, threads, tiktok
            username: Username on the platform
            profile_url: Full URL to profile
            raw_data: Raw API response data
            project_id: Project ID
            input_id: ID of input entity that led to this profile
            verification_status: VERIFIED or UNVERIFIED
        """
        import hashlib
        import json
        
        node_id = hashlib.sha256(f"profile:{platform}:{username}".lower().encode()).hexdigest()[:16]
        
        edges = []
        
        # Edge to platform
        platform_id = hashlib.sha256(f"platform:{platform}".lower().encode()).hexdigest()[:16]
        edges.append({
            "target_id": platform_id,
            "relation": "has_account_on",
            "verification_status": "VERIFIED",
            "connection_reason": "platform_association"
        })
        
        # Edge to input entity if provided
        if input_id:
            edges.append({
                "target_id": input_id,
                "relation": "output_of",
                "verification_status": verification_status,
                "connection_reason": "search_result",
                "query_sequence_tag": f"{input_id}_1" if verification_status == "UNVERIFIED" else None
            })
        
        # Extract connections if available
        followers = raw_data.get('followers', raw_data.get('followers_count', 0))
        following = raw_data.get('following', raw_data.get('following_count', 0))
        
        node = {
            "id": node_id,
            "node_class": self.CLASS_MAP.get('profile', 'SUBJECT'),
            "type": "profile",
            "_code": 188,  # person_social_profiles
            "canonicalValue": f"{platform}:{username}".lower(),
            "label": f"{username} ({platform})",
            "value": profile_url,
            "comment": json.dumps(raw_data, indent=2, ensure_ascii=False),
            "embedded_edges": edges,
            "verification_status": verification_status,
            "metadata": {
                "platform": platform,
                "username": username,
                "profile_url": profile_url,
                "followers": followers,
                "following": following,
                "verified": raw_data.get('verified', False),
                "bio": raw_data.get('bio', raw_data.get('description', '')),
            },
            "projectId": project_id,
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            "lastSeen": datetime.utcnow().isoformat()
        }
        
        # Index to Elasticsearch
        try:
            self.es.index(index=self.es_index, id=node_id, body=node)
            print(f"✓ Created profile node: {platform}:{username}")
        except Exception as e:
            print(f"Error indexing profile node: {e}")
        
        return node

    def create_connection_edge(
        self,
        source_profile_id: str,
        target_profile_id: str,
        relation: str,  # 'follows', 'followed_by', 'connected_to'
        project_id: str,
        verification_status: str = "VERIFIED"
    ) -> bool:
        """
        Create a connection edge between two profiles.
        
        Args:
            source_profile_id: ID of source profile
            target_profile_id: ID of target profile
            relation: Edge type (follows, followed_by, connected_to)
            project_id: Project ID
            verification_status: VERIFIED or UNVERIFIED
        """
        try:
            # Get source node
            source_node = self.es.get(index=self.es_index, id=source_profile_id)
            node_data = source_node['_source']
            
            # Add edge to embedded_edges
            new_edge = {
                "target_id": target_profile_id,
                "relation": relation,
                "verification_status": verification_status,
                "connection_reason": "social_connection"
            }
            
            if 'embedded_edges' not in node_data:
                node_data['embedded_edges'] = []
            
            # Check if edge already exists
            existing = [e for e in node_data['embedded_edges'] 
                       if e.get('target_id') == target_profile_id and e.get('relation') == relation]
            
            if not existing:
                node_data['embedded_edges'].append(new_edge)
                node_data['updatedAt'] = datetime.utcnow().isoformat()
                
                self.es.update(
                    index=self.es_index,
                    id=source_profile_id,
                    body={"doc": node_data}
                )
                print(f"✓ Created edge: {source_profile_id} --{relation}--> {target_profile_id}")
            
            return True
            
        except Exception as e:
            print(f"Error creating connection edge: {e}")
            return False

    def recursive_socialite_search(
        self,
        initial_query: str,
        project_id: str,
        max_depth: int = 3,
        search_function=None
    ) -> Dict:
        """
        Perform recursive SOCIALITE searches with VERIFIED priority and verification cascade.

        Args:
            initial_query: Starting search value (username, person name, etc.)
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
        print(f"RECURSIVE SOCIALITE SEARCH - Verification Cascade Strategy")
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

                newly_verified = []

                for entity_value, current_tag in unverified_queue:
                    new_tag = self.increment_sequence_tag(entity_value, current_tag)
                    print(f"  → Searching UNVERIFIED entity: {entity_value} (tag: {current_tag} → {new_tag})")

                    self.update_edge_tag(project_id, entity_value, current_tag, new_tag)

                    try:
                        search_function(entity_value)
                        total_searches += 1
                        unverified_searches += 1

                        print(f"  ⚡ Checking verification upgrade for {entity_value}...")
                        should_upgrade, upgrade_reason = self.check_verification_upgrade(
                            entity_value, project_id
                        )

                        if should_upgrade:
                            success = self.upgrade_to_verified(entity_value, project_id, upgrade_reason)
                            if success:
                                upgraded_count += 1
                                newly_verified.insert(0, entity_value)
                                print(f"  🎯 UPGRADED TO VERIFIED: {entity_value}")
                                print(f"     ➜ Will be searched IMMEDIATELY with highest priority")
                        else:
                            print(f"  ○ Remains UNVERIFIED: {upgrade_reason}")

                    except Exception as e:
                        print(f"  ✗ Error: {e}")

                # IMMEDIATE CASCADE: Process newly verified entities
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
