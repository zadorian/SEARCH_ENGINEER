#!/usr/bin/env python3
"""
Tripwire System - Percolator-Based Alert Engine
================================================

The "Reverse Search" system. Instead of searching documents with queries,
we index queries and match incoming documents against them.

Architecture:
1. Standing Rules (Percolator queries) are indexed with semantic conditions
2. Incoming documents are pre-extracted using UniversalExtractor
3. Documents are percolated against standing rules
4. Matches trigger alerts/actions

Integration with Embeddings:
- UniversalExtractor extracts themes/phenomena using vector similarity
- Extracted terms are stored as keywords in the document
- Percolator queries match on these extracted keyword terms
- This gives us semantic matching with fast percolation

Example Tripwire:
    "Alert me when any document discusses 'Bankruptcy' (phenomenon)
     + 'Mining' (theme) + 'Russia' (jurisdiction)"

The percolator query would be:
    {
        "bool": {
            "must": [
                {"term": {"extracted.phenomena": "corp_bankruptcy"}},
                {"term": {"extracted.themes": "mining_metals"}},
                {"term": {"spatial.primary_jurisdiction": "RU"}}
            ]
        }
    }
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from elasticsearch import Elasticsearch
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ES_HOST = "http://localhost:9200"
TRIPWIRE_INDEX = "tripwires"

# Index mapping for tripwires (percolator queries)
# MUST include both the percolator field AND the document fields being percolated
TRIPWIRE_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
    },
    "mappings": {
        "properties": {
            # Percolator query field
            "query": {"type": "percolator"},

            # ========================================
            # DOCUMENT FIELDS (for percolation matching)
            # These mirror the UniversalExtractor output
            # ========================================
            "text": {"type": "text"},
            "extracted": {
                "properties": {
                    "themes": {"type": "keyword"},
                    "phenomena": {"type": "keyword"},
                    "red_flag_themes": {"type": "keyword"},
                    "methodologies": {"type": "keyword"},
                    "entities": {"type": "keyword"},
                    "locations": {"type": "keyword"}
                }
            },
            "temporal": {
                "properties": {
                    "published": {"type": "date"},
                    "content_years": {"type": "integer"},
                    "focus": {"type": "keyword"}
                }
            },
            "spatial": {
                "properties": {
                    "primary_jurisdiction": {"type": "keyword"},
                    "locations": {"type": "keyword"}
                }
            },

            # ========================================
            # TRIPWIRE METADATA
            # ========================================
            "name": {"type": "keyword"},
            "description": {"type": "text"},
            "owner": {"type": "keyword"},
            "priority": {"type": "keyword"},  # critical, high, medium, low
            "category": {"type": "keyword"},  # red_flag, topic, entity, ownership

            # Conditions (for reference/display)
            "conditions": {
                "type": "object",
                "properties": {
                    "themes": {"type": "keyword"},
                    "phenomena": {"type": "keyword"},
                    "jurisdictions": {"type": "keyword"},
                    "entities": {"type": "keyword"},
                    "keywords": {"type": "keyword"}
                }
            },

            # Actions to take on match
            "actions": {
                "type": "object",
                "properties": {
                    "notify": {"type": "keyword"},  # email, slack, webhook
                    "tag": {"type": "keyword"},
                    "flag": {"type": "keyword"}
                }
            },

            # Status
            "enabled": {"type": "boolean"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "match_count": {"type": "integer"},
            "last_match": {"type": "date"}
        }
    }
}

# Document mapping that tripwires percolate against
# This should match the UniversalExtractor output structure
DOCUMENT_PERCOLATE_MAPPING = {
    "properties": {
        "text": {"type": "text"},
        "extracted": {
            "properties": {
                "themes": {"type": "keyword"},
                "phenomena": {"type": "keyword"},
                "red_flag_themes": {"type": "keyword"},
                "methodologies": {"type": "keyword"},
                "entities": {"type": "keyword"},
                "locations": {"type": "keyword"}
            }
        },
        "temporal": {
            "properties": {
                "published": {"type": "date"},
                "content_years": {"type": "integer"},
                "focus": {"type": "keyword"}
            }
        },
        "spatial": {
            "properties": {
                "primary_jurisdiction": {"type": "keyword"},
                "locations": {"type": "keyword"}
            }
        }
    }
}


@dataclass
class TripwireMatch:
    """Result of a tripwire match."""
    tripwire_id: str
    tripwire_name: str
    priority: str
    category: str
    conditions: Dict[str, Any]
    actions: Dict[str, Any]
    score: float


class TripwireEngine:
    """
    Percolator-based tripwire engine for real-time document alerting.
    """

    def __init__(self):
        self.es = Elasticsearch([ES_HOST])
        self._ensure_index()

    def _ensure_index(self):
        """Create tripwire index if it doesn't exist."""
        if not self.es.indices.exists(index=TRIPWIRE_INDEX):
            logger.info(f"Creating tripwire index: {TRIPWIRE_INDEX}")
            self.es.indices.create(index=TRIPWIRE_INDEX, body=TRIPWIRE_MAPPING)

    def create_tripwire(
        self,
        name: str,
        themes: List[str] = None,
        phenomena: List[str] = None,
        red_flag_themes: List[str] = None,
        methodologies: List[str] = None,
        jurisdictions: List[str] = None,
        entities: List[str] = None,
        keywords: List[str] = None,
        priority: str = "medium",
        category: str = "topic",
        owner: str = None,
        description: str = None,
        actions: Dict[str, Any] = None
    ) -> str:
        """
        Create a new tripwire (standing alert rule).

        Args:
            name: Human-readable name for the tripwire
            themes: Theme IDs to match (e.g., ["mining_metals", "energy_oil"])
            phenomena: Phenomenon IDs to match (e.g., ["corp_bankruptcy", "reg_sanction"])
            jurisdictions: Country codes to match (e.g., ["RU", "CN"])
            entities: Entity names/IDs to match
            keywords: Raw keywords to match in text
            priority: Alert priority (critical, high, medium, low)
            category: Tripwire category (red_flag, topic, entity, ownership)
            owner: Owner/creator of the tripwire
            description: Human-readable description
            actions: Actions to take on match (notify, tag, flag)

        Returns:
            Tripwire document ID
        """
        # Build the percolator query
        must_clauses = []

        if themes:
            must_clauses.append({
                "terms": {"extracted.themes": themes}
            })

        if phenomena:
            must_clauses.append({
                "terms": {"extracted.phenomena": phenomena}
            })

        if red_flag_themes:
            must_clauses.append({
                "terms": {"extracted.red_flag_themes": red_flag_themes}
            })

        if methodologies:
            must_clauses.append({
                "terms": {"extracted.methodologies": methodologies}
            })

        if jurisdictions:
            must_clauses.append({
                "terms": {"spatial.primary_jurisdiction": jurisdictions}
            })

        if entities:
            must_clauses.append({
                "terms": {"extracted.entities": entities}
            })

        if keywords:
            must_clauses.append({
                "bool": {
                    "should": [{"match": {"text": kw}} for kw in keywords],
                    "minimum_should_match": 1
                }
            })

        # The percolator query
        query = {
            "bool": {
                "must": must_clauses
            }
        } if must_clauses else {"match_all": {}}

        # Build the tripwire document
        doc = {
            "query": query,
            "name": name,
            "description": description or f"Tripwire: {name}",
            "owner": owner,
            "priority": priority,
            "category": category,
            "conditions": {
                "themes": themes or [],
                "phenomena": phenomena or [],
                "red_flag_themes": red_flag_themes or [],
                "methodologies": methodologies or [],
                "jurisdictions": jurisdictions or [],
                "entities": entities or [],
                "keywords": keywords or []
            },
            "actions": actions or {},
            "enabled": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "match_count": 0,
            "last_match": None
        }

        result = self.es.index(index=TRIPWIRE_INDEX, body=doc, refresh=True)
        logger.info(f"Created tripwire '{name}' with ID: {result['_id']}")
        return result["_id"]

    def percolate_document(
        self,
        text: str,
        extracted_themes: List[str] = None,
        extracted_phenomena: List[str] = None,
        extracted_red_flag_themes: List[str] = None,
        extracted_methodologies: List[str] = None,
        extracted_entities: List[str] = None,
        extracted_locations: List[str] = None,
        primary_jurisdiction: str = None,
        content_years: List[int] = None
    ) -> List[TripwireMatch]:
        """
        Percolate a document against all tripwires to find matches.

        This is the "Tripwire Check" - run on every incoming document
        after UniversalExtractor has processed it.

        Args:
            text: Document text
            extracted_themes: Theme IDs from UniversalExtractor
            extracted_phenomena: Phenomenon IDs from UniversalExtractor
            extracted_red_flag_themes: Red-flag theme IDs from UniversalExtractor
            extracted_methodologies: Methodology IDs from UniversalExtractor
            extracted_entities: Entity names from NER
            extracted_locations: Location names
            primary_jurisdiction: Primary country code
            content_years: Years discussed in content

        Returns:
            List of matching tripwires
        """
        # Build the document to percolate
        doc = {
            "text": text[:5000],  # Truncate for percolation
            "extracted": {
                "themes": extracted_themes or [],
                "phenomena": extracted_phenomena or [],
                "red_flag_themes": extracted_red_flag_themes or [],
                "methodologies": extracted_methodologies or [],
                "entities": extracted_entities or [],
                "locations": extracted_locations or []
            },
            "temporal": {
                "content_years": content_years or []
            },
            "spatial": {
                "primary_jurisdiction": primary_jurisdiction,
                "locations": extracted_locations or []
            }
        }

        # Run percolation
        result = self.es.search(
            index=TRIPWIRE_INDEX,
            body={
                "query": {
                    "percolate": {
                        "field": "query",
                        "document": doc
                    }
                }
            }
        )

        matches = []
        for hit in result["hits"]["hits"]:
            source = hit["_source"]
            matches.append(TripwireMatch(
                tripwire_id=hit["_id"],
                tripwire_name=source.get("name", "Unknown"),
                priority=source.get("priority", "medium"),
                category=source.get("category", "topic"),
                conditions=source.get("conditions", {}),
                actions=source.get("actions", {}),
                score=hit["_score"]
            ))

            # Update match count
            self.es.update(
                index=TRIPWIRE_INDEX,
                id=hit["_id"],
                body={
                    "script": {
                        "source": "ctx._source.match_count += 1; ctx._source.last_match = params.now",
                        "params": {"now": datetime.utcnow().isoformat()}
                    }
                }
            )

        logger.info(f"Percolation found {len(matches)} tripwire matches")
        return matches

    def percolate_extracted(self, extraction_result: Dict[str, Any]) -> List[TripwireMatch]:
        """
        Percolate using UniversalExtractor output directly.

        Args:
            extraction_result: Output from UniversalExtractor.extract_all()

        Returns:
            List of matching tripwires
        """
        extracted = extraction_result.get("extracted", {})
        temporal = extraction_result.get("temporal", {})
        spatial = extraction_result.get("spatial", {})

        return self.percolate_document(
            text="",  # Text not needed if we have extracted fields
            extracted_themes=[t.get("id") for t in extracted.get("themes", [])],
            extracted_phenomena=[p.get("id") for p in extracted.get("phenomena", [])],
            extracted_red_flag_themes=[rf.get("id") for rf in extracted.get("red_flag_themes", [])],
            extracted_methodologies=[m.get("id") for m in extracted.get("methodologies", [])],
            extracted_entities=[e.get("value") for e in extracted.get("entities", [])],
            extracted_locations=[loc.get("name") for loc in extracted.get("locations", [])],
            primary_jurisdiction=spatial.get("primary_jurisdiction"),
            content_years=temporal.get("content_years", [])
        )

    def list_tripwires(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """List all tripwires."""
        query = {"term": {"enabled": True}} if enabled_only else {"match_all": {}}
        result = self.es.search(
            index=TRIPWIRE_INDEX,
            body={"query": query, "size": 1000}
        )
        return [
            {"id": hit["_id"], **hit["_source"]}
            for hit in result["hits"]["hits"]
        ]

    def delete_tripwire(self, tripwire_id: str) -> bool:
        """Delete a tripwire."""
        try:
            self.es.delete(index=TRIPWIRE_INDEX, id=tripwire_id, refresh=True)
            return True
        except Exception as e:
            logger.error(f"Failed to delete tripwire {tripwire_id}: {e}")
            return False

    def disable_tripwire(self, tripwire_id: str) -> bool:
        """Disable a tripwire without deleting it."""
        try:
            self.es.update(
                index=TRIPWIRE_INDEX,
                id=tripwire_id,
                body={"doc": {"enabled": False, "updated_at": datetime.utcnow().isoformat()}},
                refresh=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to disable tripwire {tripwire_id}: {e}")
            return False


# Singleton
_engine = None

def get_tripwire_engine() -> TripwireEngine:
    global _engine
    if _engine is None:
        _engine = TripwireEngine()
    return _engine


def check_tripwires(extraction_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convenience function to check tripwires for a document.

    Args:
        extraction_result: Output from UniversalExtractor

    Returns:
        List of tripwire matches as dicts
    """
    engine = get_tripwire_engine()
    matches = engine.percolate_extracted(extraction_result)
    return [
        {
            "id": m.tripwire_id,
            "name": m.tripwire_name,
            "priority": m.priority,
            "category": m.category,
            "conditions": m.conditions,
            "actions": m.actions,
            "score": m.score
        }
        for m in matches
    ]


if __name__ == "__main__":
    # Test the tripwire system
    engine = TripwireEngine()

    # Create some test tripwires
    print("Creating test tripwires...")

    # Red flag: Russian mining bankruptcy
    engine.create_tripwire(
        name="Russian Mining Crisis",
        themes=["mining_metals"],
        phenomena=["corp_bankruptcy", "reg_sanction"],
        jurisdictions=["RU"],
        priority="critical",
        category="red_flag",
        description="Alert on Russian mining sector bankruptcies or sanctions"
    )

    # Topic: AI funding rounds
    engine.create_tripwire(
        name="AI Funding Tracker",
        themes=["tech_ai"],
        phenomena=["corp_funding", "corp_ipo"],
        priority="high",
        category="topic",
        description="Track AI company funding and IPO activity"
    )

    # Entity: Specific company mentions with sanctions
    engine.create_tripwire(
        name="Sanctioned Entity Monitor",
        phenomena=["reg_sanction", "crime_fraud"],
        priority="critical",
        category="entity",
        description="Monitor for sanction and fraud events"
    )

    print("\nActive tripwires:")
    for tw in engine.list_tripwires():
        print(f"  - {tw['name']} ({tw['priority']}) - {tw['category']}")

    # Test percolation
    print("\nTest percolation...")
    matches = engine.percolate_document(
        text="OpenAI raises $6 billion in latest funding round",
        extracted_themes=["tech_ai"],
        extracted_phenomena=["corp_funding"],
        primary_jurisdiction="US"
    )

    print(f"Found {len(matches)} matches:")
    for m in matches:
        print(f"  - {m.tripwire_name} (priority: {m.priority})")
