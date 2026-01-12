"""
Elasticsearch Mapping Definitions for Cymonides
Defines field mappings for each data type across all tiers
"""

# Content mapping for C-2 (scraped pages, documents)
CONTENT_MAPPING = {
    "properties": {
        # Identification
        "url": {"type": "keyword"},
        "url_hash": {"type": "keyword"},
        "domain": {"type": "keyword"},
        
        # Content
        "title": {
            "type": "text",
            "analyzer": "standard",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}
        },
        "content": {"type": "text", "analyzer": "standard"},
        "content_type": {"type": "keyword"},
        "language": {"type": "keyword"},
        
        # Metadata
        "meta": {
            "type": "object",
            "properties": {
                "description": {"type": "text"},
                "keywords": {"type": "keyword"},
                "author": {"type": "keyword"},
            }
        },
        
        # Extraction info
        "outlinks": {"type": "keyword"},
        "outlink_count": {"type": "integer"},
        
        # Source tracking
        "source": {"type": "keyword"},  # e.g., "brute_scraper", "serdavos", "jester"
        "source_query": {"type": "keyword"},
        "project_id": {"type": "keyword"},
        
        # Timestamps
        "crawled_at": {"type": "date"},
        "indexed_at": {"type": "date"},
        "last_modified": {"type": "date"},
        
        # Indexer lineage
        "envelope_id": {"type": "keyword"},
        "job_id": {"type": "keyword"},
    }
}

# Entity mapping for C-3 (persons, companies, emails, phones)
ENTITY_MAPPING = {
    "properties": {
        # Core identification
        "entity_id": {"type": "keyword"},
        "entity_type": {"type": "keyword"},  # person, company, email, phone, etc.

        # Core contract fields for unified schema
        "subject": {"type": "keyword"},  # Entity IDs this record represents
        "concepts": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "dimension_keys": {"type": "keyword"},  # Normalized facets for filtering
        "doc_type": {"type": "keyword"},
        "canonical_value": {"type": "keyword"},  # Primary identifier
        
        # Names and aliases
        "names": {
            "type": "text",
            "analyzer": "standard",
            "fields": {"keyword": {"type": "keyword"}}
        },
        "aliases": {"type": "keyword"},
        
        # Contact info (if applicable)
        "emails": {"type": "keyword"},
        "phones": {"type": "keyword"},
        "addresses": {"type": "text"},
        
        # Structured data
        "properties": {"type": "object", "enabled": False},  # Flexible JSON
        
        # Source tracking
        "sources": {
            "type": "nested",
            "properties": {
                "source_id": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "record_id": {"type": "keyword"},
                "confidence": {"type": "float"},
                "observed_at": {"type": "date"},
            }
        },
        
        # Quality and confidence
        "confidence_score": {"type": "float"},
        "verification_status": {"type": "keyword"},  # verified, unverified, disputed
        
        # Relationships (links to other entities)
        "related_entities": {"type": "keyword"},
        
        # Timestamps
        "first_seen": {"type": "date"},
        "last_seen": {"type": "date"},
        "indexed_at": {"type": "date"},
        
        # Indexer lineage  
        "envelope_id": {"type": "keyword"},
        "job_id": {"type": "keyword"},
    }
}

# Breach record mapping for C-3
BREACH_MAPPING = {
    "properties": {
        # Identification
        "record_hash": {"type": "keyword"},
        "breach_name": {"type": "keyword"},
        "breach_id": {"type": "keyword"},
        
        # Core breach data
        "email": {"type": "keyword"},
        "email_domain": {"type": "keyword"},
        "username": {"type": "keyword"},
        "password_hash": {"type": "keyword"},
        "password_plain": {"type": "keyword"},
        "password_type": {"type": "keyword"},  # plaintext, md5, sha1, bcrypt, etc.
        
        # Personal info
        "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "first_name": {"type": "keyword"},
        "last_name": {"type": "keyword"},
        "phone": {"type": "keyword"},
        "address": {"type": "text"},
        "ip_address": {"type": "ip"},
        "dob": {"type": "date"},
        
        # Additional fields (varies by breach)
        "extra": {"type": "object", "enabled": False},
        
        # Breach metadata
        "breach_date": {"type": "date"},
        "source_file": {"type": "keyword"},
        "line_number": {"type": "long"},
        
        # Timestamps
        "indexed_at": {"type": "date"},
        
        # Indexer lineage
        "envelope_id": {"type": "keyword"},
        "job_id": {"type": "keyword"},
    }
}

# Domain mapping for domains_unified
DOMAIN_MAPPING = {
    "properties": {
        # Core
        "domain": {"type": "keyword"},
        "tld": {"type": "keyword"},
        "registered_domain": {"type": "keyword"},

        # Core contract fields
        "subject": {"type": "keyword"},
        "concepts": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "dimension_keys": {"type": "keyword"},
        "doc_type": {"type": "keyword"},
        
        # WHOIS data
        "whois": {
            "type": "object",
            "properties": {
                "registrar": {"type": "keyword"},
                "registrant_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "registrant_org": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "registrant_email": {"type": "keyword"},
                "admin_email": {"type": "keyword"},
                "tech_email": {"type": "keyword"},
                "nameservers": {"type": "keyword"},
                "created_date": {"type": "date"},
                "updated_date": {"type": "date"},
                "expiry_date": {"type": "date"},
                "status": {"type": "keyword"},
            }
        },
        
        # DNS
        "dns": {
            "type": "object",
            "properties": {
                "a_records": {"type": "ip"},
                "aaaa_records": {"type": "keyword"},
                "mx_records": {"type": "keyword"},
                "ns_records": {"type": "keyword"},
                "txt_records": {"type": "text"},
                "cname": {"type": "keyword"},
            }
        },
        
        # Hosting
        "hosting": {
            "type": "object",
            "properties": {
                "ip": {"type": "ip"},
                "asn": {"type": "keyword"},
                "isp": {"type": "keyword"},
                "country": {"type": "keyword"},
                "city": {"type": "keyword"},
            }
        },
        
        # Classification
        "category": {"type": "keyword"},
        "tags": {"type": "keyword"},
        "risk_score": {"type": "float"},
        
        # Graph metrics (from CC)
        "inbound_links": {"type": "integer"},
        "outbound_links": {"type": "integer"},
        "pagerank": {"type": "float"},
        
        # Timestamps
        "first_seen": {"type": "date"},
        "last_seen": {"type": "date"},
        "whois_updated": {"type": "date"},
        "indexed_at": {"type": "date"},
        
        # Indexer lineage
        "envelope_id": {"type": "keyword"},
        "job_id": {"type": "keyword"},
    }
}

# Graph vertex mapping for CC domain graph
GRAPH_VERTEX_MAPPING = {
    "properties": {
        "domain": {"type": "keyword"},
        "tld": {"type": "keyword"},
        
        # Metrics
        "in_degree": {"type": "integer"},
        "out_degree": {"type": "integer"},
        "pagerank": {"type": "float"},
        "harmonic_centrality": {"type": "float"},
        
        # Classification
        "category": {"type": "keyword"},
        "is_hub": {"type": "boolean"},
        
        # CC crawl info
        "cc_crawl_id": {"type": "keyword"},
        "url_count": {"type": "integer"},
        
        # Timestamps
        "first_seen": {"type": "date"},
        "last_seen": {"type": "date"},
        "indexed_at": {"type": "date"},
        
        # Indexer lineage
        "envelope_id": {"type": "keyword"},
        "job_id": {"type": "keyword"},
    }
}

# Graph edge mapping for CC domain links
GRAPH_EDGE_MAPPING = {
    "properties": {
        "edge_id": {"type": "keyword"},
        
        # Source and target
        "source_domain": {"type": "keyword"},
        "target_domain": {"type": "keyword"},
        
        # Edge properties
        "weight": {"type": "integer"},  # Number of links
        "edge_type": {"type": "keyword"},  # hyperlink, redirect, etc.
        
        # Sample URLs
        "sample_source_urls": {"type": "keyword"},
        "sample_target_urls": {"type": "keyword"},
        
        # Anchor text
        "anchor_texts": {"type": "text"},
        
        # CC crawl info
        "cc_crawl_id": {"type": "keyword"},
        
        # Timestamps
        "first_seen": {"type": "date"},
        "last_seen": {"type": "date"},
        "indexed_at": {"type": "date"},
        
        # Indexer lineage
        "envelope_id": {"type": "keyword"},
        "job_id": {"type": "keyword"},
    }
}

# Project node mapping for C-1 investigation graphs
PROJECT_NODE_MAPPING = {
    "properties": {
        "node_id": {"type": "keyword"},
        "node_class": {"type": "keyword"},  # entity, narrative, source, query
        "node_type": {"type": "keyword"},  # person, company, document, domain
        "label": {
            "type": "text",
            "analyzer": "standard",
            "fields": {"keyword": {"type": "keyword"}}
        },
        
        # Properties (flexible)
        "properties": {"type": "object", "enabled": False},
        
        # Links to C-3 entities
        "c3_entity_ids": {"type": "keyword"},
        
        # Project metadata
        "project_id": {"type": "keyword"},
        "created_by": {"type": "keyword"},
        
        # Timestamps
        "created_at": {"type": "date"},
        "updated_at": {"type": "date"},
        
        # Indexer lineage
        "envelope_id": {"type": "keyword"},
        "job_id": {"type": "keyword"},
    }
}

# Project edge mapping for C-1
PROJECT_EDGE_MAPPING = {
    "properties": {
        "edge_id": {"type": "keyword"},
        "source_node": {"type": "keyword"},
        "target_node": {"type": "keyword"},
        "relation_type": {"type": "keyword"},
        
        # Properties (flexible)
        "properties": {"type": "object", "enabled": False},
        
        # Project metadata
        "project_id": {"type": "keyword"},
        "created_by": {"type": "keyword"},
        
        # Timestamps
        "created_at": {"type": "date"},
        "updated_at": {"type": "date"},
        
        # Indexer lineage
        "envelope_id": {"type": "keyword"},
        "job_id": {"type": "keyword"},
    }
}
