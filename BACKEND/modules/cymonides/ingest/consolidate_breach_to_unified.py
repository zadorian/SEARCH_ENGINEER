#!/usr/bin/env python3
"""
consolidate_breach_to_unified.py - Multi-target breach consolidation

Routes fixed breach records to:
- emails_unified (email addresses)
- persons_unified (names with temporal)
- phones_unified (phone numbers)
- geo_unified (addresses with geo extraction)

Preserves:
- source_records[] for full traceability
- embedded_edges[] for cross-entity relationships
- dimension_keys[] for faceted search
- temporal hierarchy (year, decade, era)

Usage:
    python3 consolidate_breach_to_unified.py                    # All fixed breaches
    python3 consolidate_breach_to_unified.py --breach "Voter Databases"  # Single breach
    python3 consolidate_breach_to_unified.py --verify           # Verify only
"""

import hashlib
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, scan

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/consolidate_breach_unified.log')
    ]
)
logger = logging.getLogger(__name__)

ES_HOST = "http://localhost:9200"
BATCH_SIZE = 2000
SCROLL_SIZE = 5000
SCROLL_TIMEOUT = "30m"

# Fixed breaches ready for consolidation
FIXED_BREACHES = [
    "Voter Databases",
    "Nj.gov - New Jersey Voter Database",
    "Texas.gov - Texas BirthDeathMarriageDivorce Database",
    "USA consumer",
    "Usa.gov - USA Boat Owner Database",
    "AshleyMadison.com",
]

# Target indices
TARGETS = {
    "emails": "emails_unified",
    "persons": "persons_unified",
    "phones": "phones_unified",
    "geo": "geo_unified",
    "credentials": "credentials_unified",
}

# Era definitions from plan
ERA_DEFINITIONS = [
    (1947, 1991, "cold_war"),
    (1991, 2000, "post_soviet"),
    (2000, 2008, "pre_2008"),
    (2008, 2019, "post_2008"),
    (2020, 2022, "covid_era"),
    (2023, 2100, "post_covid"),
]

def get_era(year: int) -> str:
    """Get era label for a year."""
    for start, end, era in ERA_DEFINITIONS:
        if start <= year <= end:
            return era
    return "unknown"

def get_decade(year: int) -> str:
    """Get decade label."""
    decade_start = (year // 10) * 10
    return f"{decade_start}s"


def generate_id(entity_type: str, *values) -> str:
    """Generate deterministic ID from entity type and values."""
    composite = f"{entity_type}:" + ":".join(str(v).lower().strip() for v in values if v)
    return hashlib.sha256(composite.encode()).hexdigest()[:24]


def normalize_phone(phone: str) -> Optional[str]:
    """Normalize phone to E.164-ish format."""
    if not phone:
        return None
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) < 7 or len(digits) > 15:
        return None
    if len(digits) == 10:  # US number without country code
        digits = "1" + digits
    return "+" + digits


def validate_email(email: str) -> bool:
    """Basic email validation."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    if len(email) < 5 or len(email) > 320 or '@' not in email:
        return False
    local, domain = email.split('@', 1)
    return bool(local and domain and '.' in domain)


def normalize_dim(value: str) -> str:
    """Normalize value for dimension_keys."""
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def parse_year(value: Any) -> Optional[int]:
    """Extract year from various formats."""
    if not value:
        return None
    if isinstance(value, int):
        if 1900 <= value <= 2100:
            return value
        return None
    s = str(value)
    # Try direct parse
    if s.isdigit() and len(s) == 4:
        y = int(s)
        if 1900 <= y <= 2100:
            return y
    # Try date format
    match = re.search(r'(19|20)\d{2}', s)
    if match:
        return int(match.group())
    return None


def build_temporal(year: Optional[int]) -> Dict:
    """Build temporal hierarchy from year."""
    if not year:
        return {}
    return {
        "year": year,
        "decade": get_decade(year),
        "era": get_era(year),
        "temporal_focus": "historical" if year < 2020 else "current",
    }


def build_source_record(doc: dict, breach_name: str) -> Dict:
    """Build source record for traceability."""
    return {
        "index": "breach_records",
        "id": doc.get("_id", ""),
        "breach_name": breach_name,
        "indexed_at": datetime.utcnow().isoformat(),
    }


class BreachConsolidator:
    def __init__(self, es: Elasticsearch):
        self.es = es
        self.stats = {target: {"indexed": 0, "skipped": 0, "failed": 0} for target in TARGETS}
        self.pending = {target: [] for target in TARGETS}
        self.seen = {target: set() for target in TARGETS}

    def ensure_indices(self):
        """Create target indices if they don't exist."""
        # emails_unified
        if not self.es.indices.exists(index=TARGETS["emails"]):
            self.es.indices.create(index=TARGETS["emails"], body={
                "settings": {"number_of_shards": 5, "number_of_replicas": 0, "refresh_interval": "60s"},
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "email": {"type": "keyword"},
                        "email_domain": {"type": "keyword"},
                        "local_part": {"type": "keyword"},
                        "source_records": {"type": "nested", "properties": {
                            "index": {"type": "keyword"},
                            "id": {"type": "keyword"},
                            "breach_name": {"type": "keyword"},
                            "indexed_at": {"type": "date"},
                        }},
                        "embedded_edges": {"type": "nested", "properties": {
                            "target_id": {"type": "keyword"},
                            "target_index": {"type": "keyword"},
                            "relationship": {"type": "keyword"},
                            "confidence": {"type": "float"},
                        }},
                        "dimension_keys": {"type": "keyword"},
                        "doc_type": {"type": "keyword"},
                        "indexed_at": {"type": "date"},
                    }
                }
            })
            logger.info(f"Created {TARGETS['emails']}")

        # persons_unified
        if not self.es.indices.exists(index=TARGETS["persons"]):
            self.es.indices.create(index=TARGETS["persons"], body={
                "settings": {"number_of_shards": 5, "number_of_replicas": 0, "refresh_interval": "60s"},
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "names": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        "first_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        "last_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        "source_records": {"type": "nested", "properties": {
                            "index": {"type": "keyword"},
                            "id": {"type": "keyword"},
                            "breach_name": {"type": "keyword"},
                            "indexed_at": {"type": "date"},
                        }},
                        "embedded_edges": {"type": "nested", "properties": {
                            "target_id": {"type": "keyword"},
                            "target_index": {"type": "keyword"},
                            "relationship": {"type": "keyword"},
                            "confidence": {"type": "float"},
                        }},
                        "temporal": {"type": "object", "properties": {
                            "year": {"type": "integer"},
                            "decade": {"type": "keyword"},
                            "era": {"type": "keyword"},
                            "temporal_focus": {"type": "keyword"},
                        }},
                        "metadata": {"type": "object", "properties": {
                            "birth_year": {"type": "integer"},
                            "birth_date": {"type": "keyword"},
                            "gender": {"type": "keyword"},
                            "voter_id": {"type": "keyword"},
                            "voter_status": {"type": "keyword"},
                            "party": {"type": "keyword"},
                            "race": {"type": "keyword"},
                            "county": {"type": "keyword"},
                            "registration_date": {"type": "keyword"},
                        }},
                        "dimension_keys": {"type": "keyword"},
                        "doc_type": {"type": "keyword"},
                        "indexed_at": {"type": "date"},
                    }
                }
            })
            logger.info(f"Created {TARGETS['persons']}")

        # phones_unified
        if not self.es.indices.exists(index=TARGETS["phones"]):
            self.es.indices.create(index=TARGETS["phones"], body={
                "settings": {"number_of_shards": 3, "number_of_replicas": 0, "refresh_interval": "60s"},
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "phone_e164": {"type": "keyword"},
                        "phone_raw": {"type": "keyword"},
                        "source_records": {"type": "nested", "properties": {
                            "index": {"type": "keyword"},
                            "id": {"type": "keyword"},
                            "breach_name": {"type": "keyword"},
                            "indexed_at": {"type": "date"},
                        }},
                        "embedded_edges": {"type": "nested", "properties": {
                            "target_id": {"type": "keyword"},
                            "target_index": {"type": "keyword"},
                            "relationship": {"type": "keyword"},
                            "confidence": {"type": "float"},
                        }},
                        "dimension_keys": {"type": "keyword"},
                        "doc_type": {"type": "keyword"},
                        "indexed_at": {"type": "date"},
                    }
                }
            })
            logger.info(f"Created {TARGETS['phones']}")

        # geo_unified
        if not self.es.indices.exists(index=TARGETS["geo"]):
            self.es.indices.create(index=TARGETS["geo"], body={
                "settings": {"number_of_shards": 5, "number_of_replicas": 0, "refresh_interval": "60s"},
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "address": {"type": "text"},
                        "city": {"type": "keyword"},
                        "state": {"type": "keyword"},
                        "zip": {"type": "keyword"},
                        "country": {"type": "keyword"},
                        "geo_point": {"type": "geo_point"},
                        "temporal": {"type": "object", "properties": {
                            "year": {"type": "integer"},
                            "decade": {"type": "keyword"},
                            "era": {"type": "keyword"},
                        }},
                        "source_records": {"type": "nested", "properties": {
                            "index": {"type": "keyword"},
                            "id": {"type": "keyword"},
                            "breach_name": {"type": "keyword"},
                            "indexed_at": {"type": "date"},
                        }},
                        "embedded_edges": {"type": "nested", "properties": {
                            "target_id": {"type": "keyword"},
                            "target_index": {"type": "keyword"},
                            "relationship": {"type": "keyword"},
                            "confidence": {"type": "float"},
                        }},
                        "dimension_keys": {"type": "keyword"},
                        "doc_type": {"type": "keyword"},
                        "indexed_at": {"type": "date"},
                    }
                }
            })
            logger.info(f"Created {TARGETS['geo']}")

        # credentials_unified
        if not self.es.indices.exists(index=TARGETS["credentials"]):
            self.es.indices.create(index=TARGETS["credentials"], body={
                "settings": {"number_of_shards": 5, "number_of_replicas": 0, "refresh_interval": "60s"},
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "username": {"type": "keyword"},
                        "password_hash": {"type": "keyword", "index": False},  # Don't index for security
                        "password_hint": {"type": "text"},
                        "hash_type": {"type": "keyword"},
                        "email": {"type": "keyword"},
                        "source_records": {"type": "nested", "properties": {
                            "index": {"type": "keyword"},
                            "id": {"type": "keyword"},
                            "breach_name": {"type": "keyword"},
                            "indexed_at": {"type": "date"},
                        }},
                        "embedded_edges": {"type": "nested", "properties": {
                            "target_id": {"type": "keyword"},
                            "target_index": {"type": "keyword"},
                            "relationship": {"type": "keyword"},
                            "confidence": {"type": "float"},
                        }},
                        "dimension_keys": {"type": "keyword"},
                        "doc_type": {"type": "keyword"},
                        "indexed_at": {"type": "date"},
                    }
                }
            })
            logger.info(f"Created {TARGETS['credentials']}")

    def process_record(self, doc: dict, breach_name: str):
        """Process a single breach record, routing to appropriate unified indices."""
        source_record = build_source_record(doc, breach_name)
        entity_ids = {}  # Track generated IDs for edge creation

        # === EMAIL ===
        email = doc.get("email", "")
        if validate_email(email):
            email = email.lower().strip()
            email_id = generate_id("email", email)
            entity_ids["email"] = email_id

            if email_id not in self.seen["emails"]:
                self.seen["emails"].add(email_id)
                local_part, email_domain = email.split('@', 1) if '@' in email else ("", "")

                dim_keys = [
                    "source:breach",
                    f"breach:{normalize_dim(breach_name)}",
                    f"emaildom:{normalize_dim(email_domain)}",
                ]

                self.pending["emails"].append({
                    "_index": TARGETS["emails"],
                    "_id": email_id,
                    "_source": {
                        "id": email_id,
                        "email": email,
                        "email_domain": email_domain,
                        "local_part": local_part,
                        "source_records": [source_record],
                        "embedded_edges": [],  # Will be updated with person/phone links
                        "dimension_keys": dim_keys,
                        "doc_type": "email",
                        "indexed_at": datetime.utcnow().isoformat(),
                    }
                })

        # === PERSON ===
        first_name = doc.get("first_name", "")
        last_name = doc.get("last_name", "")
        middle_name = doc.get("middle_name", "")
        # Also check for combined name fields
        if not first_name and not last_name:
            # Try groom/bride names from Texas records
            groom = doc.get("groom_name", "")
            bride = doc.get("bride_name", "")
            if groom:
                parts = groom.strip().split()
                if len(parts) >= 2:
                    first_name = parts[0]
                    last_name = parts[-1]
            elif bride:
                parts = bride.strip().split()
                if len(parts) >= 2:
                    first_name = parts[0]
                    last_name = parts[-1]

        if first_name or last_name:
            full_name = f"{first_name} {last_name}".strip()
            if full_name and len(full_name) > 2:
                person_id = generate_id("person", first_name, last_name)
                entity_ids["person"] = person_id

                if person_id not in self.seen["persons"]:
                    self.seen["persons"].add(person_id)

                    # Parse birth_year from various fields
                    birth_year = (
                        parse_year(doc.get("birth_year")) or
                        parse_year(doc.get("birth_date"))
                    )
                    # Construct birth_date string if we have day/month/year components
                    birth_date_str = doc.get("birth_date")
                    if not birth_date_str and doc.get("birth_year"):
                        bd, bm, by = doc.get("birth_day", ""), doc.get("birth_month", ""), doc.get("birth_year", "")
                        if bd and bm and by:
                            birth_date_str = f"{bm}/{bd}/{by}"

                    reg_year = parse_year(doc.get("registration_date")) or parse_year(doc.get("record_date"))
                    temporal = build_temporal(birth_year)
                    if reg_year:
                        temporal["registration_year"] = reg_year
                        temporal["registration_decade"] = get_decade(reg_year)
                        temporal["registration_era"] = get_era(reg_year)

                    dim_keys = [
                        "source:breach",
                        f"breach:{normalize_dim(breach_name)}",
                    ]
                    if temporal.get("era"):
                        dim_keys.append(f"era:{temporal['era']}")
                    if temporal.get("decade"):
                        dim_keys.append(f"decade:{temporal['decade']}")

                    state = doc.get("state", "")
                    if state:
                        dim_keys.append(f"state:{normalize_dim(state)}")

                    gender = doc.get("gender", "")
                    if gender:
                        dim_keys.append(f"gender:{normalize_dim(gender)}")

                    self.pending["persons"].append({
                        "_index": TARGETS["persons"],
                        "_id": person_id,
                        "_source": {
                            "id": person_id,
                            "names": [full_name],
                            "first_name": first_name,
                            "last_name": last_name,
                            "source_records": [source_record],
                            "embedded_edges": [],
                            "temporal": temporal,
                            "metadata": {
                                "birth_year": birth_year,
                                "birth_date": birth_date_str,
                                "gender": gender if gender else None,
                                "voter_id": doc.get("voter_id"),
                                "voter_status": doc.get("voter_status"),
                                "party": doc.get("party"),
                                "race": doc.get("race"),
                                "county": doc.get("county") or doc.get("county_name"),
                                "registration_date": doc.get("registration_date") or doc.get("record_date"),
                            },
                            "dimension_keys": dim_keys,
                            "doc_type": "person",
                            "indexed_at": datetime.utcnow().isoformat(),
                        }
                    })

        # === PHONE ===
        phone_raw = doc.get("phone", "")
        phone_e164 = normalize_phone(phone_raw)
        if phone_e164:
            phone_id = generate_id("phone", phone_e164)
            entity_ids["phone"] = phone_id

            if phone_id not in self.seen["phones"]:
                self.seen["phones"].add(phone_id)

                dim_keys = [
                    "source:breach",
                    f"breach:{normalize_dim(breach_name)}",
                ]

                self.pending["phones"].append({
                    "_index": TARGETS["phones"],
                    "_id": phone_id,
                    "_source": {
                        "id": phone_id,
                        "phone_e164": phone_e164,
                        "phone_raw": phone_raw,
                        "source_records": [source_record],
                        "embedded_edges": [],
                        "dimension_keys": dim_keys,
                        "doc_type": "phone",
                        "indexed_at": datetime.utcnow().isoformat(),
                    }
                })

        # === GEO ===
        # Handle multiple address field formats
        address = doc.get("address", "") or doc.get("address1", "")
        address2 = doc.get("address2", "")
        if address2:
            address = f"{address} {address2}".strip()
        # Also try house_num + street_name format
        if not address:
            house_num = doc.get("house_num", "")
            street_name = doc.get("street_name", "")
            if house_num and street_name:
                address = f"{house_num} {street_name}".strip()
        city = doc.get("city", "")
        state = doc.get("state", "")
        zip_code = doc.get("zip", "")

        if address or (city and state):
            geo_key = f"{address}|{city}|{state}|{zip_code}".lower()
            geo_id = generate_id("geo", geo_key)
            entity_ids["geo"] = geo_id

            if geo_id not in self.seen["geo"]:
                self.seen["geo"].add(geo_id)

                dim_keys = [
                    "source:breach",
                    f"breach:{normalize_dim(breach_name)}",
                ]
                if state:
                    dim_keys.append(f"state:{normalize_dim(state)}")
                if city:
                    dim_keys.append(f"city:{normalize_dim(city)}")
                if zip_code:
                    dim_keys.append(f"zip:{normalize_dim(zip_code[:5])}")

                # Build temporal for when this address was valid
                addr_year = parse_year(doc.get("registration_date")) or parse_year(doc.get("record_date"))
                addr_temporal = {}
                if addr_year:
                    addr_temporal = {
                        "year": addr_year,
                        "decade": get_decade(addr_year),
                        "era": get_era(addr_year),
                    }
                    dim_keys.append(f"year:{addr_year}")
                    dim_keys.append(f"decade:{get_decade(addr_year)}")

                # Determine address type based on breach
                if "Voter" in breach_name or "voter" in breach_name:
                    addr_type = "residential"
                    addr_context = "voter_registration"
                elif "consumer" in breach_name.lower() or "Boat" in breach_name:
                    addr_type = "residential"
                    addr_context = "consumer_record"
                else:
                    addr_type = "unknown"
                    addr_context = "breach_record"

                dim_keys.append(f"addr_type:{addr_type}")
                dim_keys.append(f"context:{addr_context}")

                self.pending["geo"].append({
                    "_index": TARGETS["geo"],
                    "_id": geo_id,
                    "_source": {
                        "id": geo_id,
                        "address": address,
                        "city": city,
                        "state": state,
                        "zip": zip_code,
                        "country": "US",
                        "address_type": addr_type,
                        "address_context": addr_context,
                        "geo_point": None,  # To be enriched later via geocoding
                        "temporal": addr_temporal,
                        "source_records": [source_record],
                        "embedded_edges": [],
                        "dimension_keys": dim_keys,
                        "doc_type": "location",
                        "indexed_at": datetime.utcnow().isoformat(),
                    }
                })

        # === CREDENTIALS ===
        username = doc.get("username") or doc.get("am_username") or doc.get("adobe_user_id")
        password_hash = doc.get("password_hash") or doc.get("password") or doc.get("encrypted_password")
        password_hint = doc.get("password_hint")
        hash_type = doc.get("hash_type")

        if username or password_hash:
            # Create credential ID from username+email combo
            cred_key = f"{username or ''}|{email or ''}"
            cred_id = generate_id("credential", cred_key, breach_name)
            entity_ids["credential"] = cred_id

            if cred_id not in self.seen["credentials"]:
                self.seen["credentials"].add(cred_id)

                dim_keys = [
                    "source:breach",
                    f"breach:{normalize_dim(breach_name)}",
                ]
                if hash_type:
                    dim_keys.append(f"hashtype:{normalize_dim(hash_type)}")
                if username:
                    dim_keys.append("has:username")
                if password_hash:
                    dim_keys.append("has:password")
                if password_hint:
                    dim_keys.append("has:hint")

                self.pending["credentials"].append({
                    "_index": TARGETS["credentials"],
                    "_id": cred_id,
                    "_source": {
                        "id": cred_id,
                        "username": username,
                        "password_hash": password_hash,
                        "password_hint": password_hint,
                        "hash_type": hash_type,
                        "email": email if validate_email(email) else None,
                        "source_records": [source_record],
                        "embedded_edges": [],
                        "dimension_keys": dim_keys,
                        "doc_type": "credential",
                        "indexed_at": datetime.utcnow().isoformat(),
                    }
                })

        # === CREATE EMBEDDED EDGES ===
        # Link entities that came from the same source record
        edges_to_add = []
        if "email" in entity_ids and "person" in entity_ids:
            edges_to_add.append(("emails", entity_ids["email"], {
                "target_id": entity_ids["person"],
                "target_index": TARGETS["persons"],
                "relationship": "belongs_to",
                "confidence": 0.95,
            }))
            edges_to_add.append(("persons", entity_ids["person"], {
                "target_id": entity_ids["email"],
                "target_index": TARGETS["emails"],
                "relationship": "has_email",
                "confidence": 0.95,
            }))

        if "phone" in entity_ids and "person" in entity_ids:
            edges_to_add.append(("phones", entity_ids["phone"], {
                "target_id": entity_ids["person"],
                "target_index": TARGETS["persons"],
                "relationship": "belongs_to",
                "confidence": 0.95,
            }))
            edges_to_add.append(("persons", entity_ids["person"], {
                "target_id": entity_ids["phone"],
                "target_index": TARGETS["phones"],
                "relationship": "has_phone",
                "confidence": 0.95,
            }))

        if "geo" in entity_ids and "person" in entity_ids:
            edges_to_add.append(("geo", entity_ids["geo"], {
                "target_id": entity_ids["person"],
                "target_index": TARGETS["persons"],
                "relationship": "residence_of",
                "confidence": 0.9,
            }))
            edges_to_add.append(("persons", entity_ids["person"], {
                "target_id": entity_ids["geo"],
                "target_index": TARGETS["geo"],
                "relationship": "lives_at",
                "confidence": 0.9,
            }))

        if "credential" in entity_ids and "email" in entity_ids:
            edges_to_add.append(("credentials", entity_ids["credential"], {
                "target_id": entity_ids["email"],
                "target_index": TARGETS["emails"],
                "relationship": "authenticates",
                "confidence": 0.99,
            }))
            edges_to_add.append(("emails", entity_ids["email"], {
                "target_id": entity_ids["credential"],
                "target_index": TARGETS["credentials"],
                "relationship": "has_credential",
                "confidence": 0.99,
            }))

        if "credential" in entity_ids and "person" in entity_ids:
            edges_to_add.append(("credentials", entity_ids["credential"], {
                "target_id": entity_ids["person"],
                "target_index": TARGETS["persons"],
                "relationship": "belongs_to",
                "confidence": 0.9,
            }))
            edges_to_add.append(("persons", entity_ids["person"], {
                "target_id": entity_ids["credential"],
                "target_index": TARGETS["credentials"],
                "relationship": "has_credential",
                "confidence": 0.9,
            }))

        # Add edges to pending docs
        for target, entity_id, edge in edges_to_add:
            for pending_doc in self.pending[target]:
                if pending_doc["_id"] == entity_id:
                    pending_doc["_source"]["embedded_edges"].append(edge)
                    break

    def flush_batch(self, target: str):
        """Flush pending documents to Elasticsearch."""
        if not self.pending[target]:
            return

        actions = self.pending[target]
        try:
            success, errors = bulk(self.es, actions, raise_on_error=False, stats_only=True)
            self.stats[target]["indexed"] += success
            self.stats[target]["failed"] += errors if isinstance(errors, int) else len(errors)
        except Exception as e:
            logger.error(f"Bulk error for {target}: {e}")
            self.stats[target]["failed"] += len(actions)

        self.pending[target] = []

        # Memory management
        if len(self.seen[target]) > 5000000:
            self.seen[target].clear()

    def process_breach(self, breach_name: str):
        """Process all records for a single breach."""
        count = self.es.count(index="breach_records", body={
            "query": {"term": {"breach_name": breach_name}}
        })["count"]

        logger.info(f"Processing {breach_name}: {count:,} records")

        processed = 0
        for doc in scan(self.es, index="breach_records",
                       query={"query": {"term": {"breach_name": breach_name}}},
                       scroll=SCROLL_TIMEOUT, size=SCROLL_SIZE):
            doc["_source"]["_id"] = doc["_id"]
            self.process_record(doc["_source"], breach_name)
            processed += 1

            # Flush batches
            for target in TARGETS:
                if len(self.pending[target]) >= BATCH_SIZE:
                    self.flush_batch(target)

            if processed % 500000 == 0:
                logger.info(f"  {breach_name}: {processed:,}/{count:,} ({100*processed/count:.1f}%)")

        # Final flush
        for target in TARGETS:
            self.flush_batch(target)

        logger.info(f"  {breach_name} complete")

    def verify(self):
        """Verify unified indices."""
        logger.info("\n" + "="*60)
        logger.info("VERIFICATION")
        logger.info("="*60)

        for name, index in TARGETS.items():
            if self.es.indices.exists(index=index):
                count = self.es.count(index=index)["count"]
                logger.info(f"{index}: {count:,} docs")
            else:
                logger.info(f"{index}: does not exist")

    def run(self, breaches: List[str]):
        """Run consolidation for specified breaches."""
        self.ensure_indices()

        for breach in breaches:
            self.process_breach(breach)

        # Refresh all indices
        for index in TARGETS.values():
            self.es.indices.refresh(index=index)

        logger.info("\n" + "="*60)
        logger.info("CONSOLIDATION COMPLETE")
        logger.info("="*60)
        for target, stats in self.stats.items():
            logger.info(f"{TARGETS[target]}: {stats['indexed']:,} indexed, {stats['failed']:,} failed")

        self.verify()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--breach", type=str, help="Process single breach")
    parser.add_argument("--verify", action="store_true", help="Verify only")
    args = parser.parse_args()

    es = Elasticsearch([ES_HOST], request_timeout=120, retry_on_timeout=True)
    if not es.ping():
        logger.error("Cannot connect to Elasticsearch")
        sys.exit(1)

    consolidator = BreachConsolidator(es)

    if args.verify:
        consolidator.verify()
        return

    breaches = [args.breach] if args.breach else FIXED_BREACHES
    consolidator.run(breaches)


if __name__ == "__main__":
    main()
