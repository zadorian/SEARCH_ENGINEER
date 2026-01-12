# EYE-D → CYMONIDES C-1 Pipeline (CORRECT ARCHITECTURE)

**Complete mapping of EYE-D OSINT outputs to graph nodes and edges**

---

## Core Principle

**Each EYE-D result creates**:
1. **ONE SOURCE node** (`node_class: "source"`, `node_type: "aggregator_result"`)
   - Contains: Module, Aggregator, Primary, result_id
2. **Multiple ENTITY nodes** (one per extracted entity)
3. **Uniform edges** from SOURCE → ALL entities found in that result

---

## SOURCE Node Structure

```json
{
  "id": "source_abc123",
  "node_class": "source",
  "node_type": "aggregator_result",
  "label": "LinkedIn2021 breach (via dehashed)",
  "canonicalValue": "eyed:dehashed:linkedin2021:result_12345",

  "metadata": {
    "module": "Eye-D",
    "aggregator": "dehashed",
    "primary": "LinkedIn2021",
    "result_id": "result_12345"
  },

  "embedded_edges": [
    {
      "target_id": "email_node",
      "target_class": "entity",
      "target_type": "email",
      "target_label": "john.doe@example.com",
      "relation": "mentions",
      "confidence": 0.95
    },
    {
      "target_id": "username_node",
      "target_class": "entity",
      "target_type": "username",
      "target_label": "johndoe",
      "relation": "mentions",
      "confidence": 0.95
    },
    {
      "target_id": "password_node",
      "target_class": "entity",
      "target_type": "password",
      "target_label": "password123",
      "relation": "mentions",
      "confidence": 0.95
    },
    {
      "target_id": "ip_node",
      "target_class": "entity",
      "target_type": "ip",
      "target_label": "192.168.1.1",
      "relation": "mentions",
      "confidence": 0.95
    }
  ]
}
```

---

## 1. search_email: john.doe@example.com

### EYE-D Raw Output
```json
{
  "query": "john.doe@example.com",
  "subtype": "email",
  "results": [
    {
      "source": "dehashed",
      "result_id": "dehashed_result_001",
      "data": {
        "breach": "LinkedIn2021",
        "email": "john.doe@example.com",
        "username": "johndoe",
        "password": "password123",
        "ip_address": "192.168.1.1",
        "name": "John Doe",
        "phone": "+1-555-1234"
      }
    },
    {
      "source": "dehashed",
      "result_id": "dehashed_result_002",
      "data": {
        "breach": "Adobe2013",
        "email": "john.doe@example.com",
        "password": "adobe2013pass",
        "hint": "my first pet"
      }
    },
    {
      "source": "osint_industries",
      "result_id": "osint_result_001",
      "data": {
        "email": "john.doe@example.com",
        "full_name": "John Doe",
        "phone": "+1-555-1234",
        "linkedin": "https://linkedin.com/in/johndoe",
        "company": "Acme Corp",
        "title": "Senior Engineer"
      }
    }
  ]
}
```

### C-1 Nodes Created

#### SOURCE Node 1: LinkedIn2021 breach (via dehashed)
```json
{
  "id": "source_001",
  "node_class": "source",
  "node_type": "aggregator_result",
  "label": "LinkedIn2021 breach (via dehashed)",
  "canonicalValue": "eyed:dehashed:linkedin2021:dehashed_result_001",

  "metadata": {
    "module": "Eye-D",
    "aggregator": "dehashed",
    "primary": "LinkedIn2021",
    "result_id": "dehashed_result_001",
    "search_query": "john.doe@example.com",
    "search_type": "email"
  },

  "embedded_edges": [
    {"target_id": "entity_email", "target_type": "email", "target_label": "john.doe@example.com", "relation": "mentions"},
    {"target_id": "entity_username", "target_type": "username", "target_label": "johndoe", "relation": "mentions"},
    {"target_id": "entity_password1", "target_type": "password", "target_label": "password123", "relation": "mentions"},
    {"target_id": "entity_ip", "target_type": "ip", "target_label": "192.168.1.1", "relation": "mentions"},
    {"target_id": "entity_person", "target_type": "person", "target_label": "John Doe", "relation": "mentions"},
    {"target_id": "entity_phone", "target_type": "phone", "target_label": "+1-555-1234", "relation": "mentions"}
  ]
}
```

#### SOURCE Node 2: Adobe2013 breach (via dehashed)
```json
{
  "id": "source_002",
  "node_class": "source",
  "node_type": "aggregator_result",
  "label": "Adobe2013 breach (via dehashed)",
  "canonicalValue": "eyed:dehashed:adobe2013:dehashed_result_002",

  "metadata": {
    "module": "Eye-D",
    "aggregator": "dehashed",
    "primary": "Adobe2013",
    "result_id": "dehashed_result_002"
  },

  "embedded_edges": [
    {"target_id": "entity_email", "target_type": "email", "target_label": "john.doe@example.com", "relation": "mentions"},
    {"target_id": "entity_password2", "target_type": "password", "target_label": "adobe2013pass", "relation": "mentions"}
  ]
}
```

#### SOURCE Node 3: OSINT Industries enrichment
```json
{
  "id": "source_003",
  "node_class": "source",
  "node_type": "aggregator_result",
  "label": "OSINT Industries enrichment",
  "canonicalValue": "eyed:osint_industries:enrichment:osint_result_001",

  "metadata": {
    "module": "Eye-D",
    "aggregator": "osint_industries",
    "primary": "enrichment",
    "result_id": "osint_result_001"
  },

  "embedded_edges": [
    {"target_id": "entity_email", "target_type": "email", "target_label": "john.doe@example.com", "relation": "mentions"},
    {"target_id": "entity_person", "target_type": "person", "target_label": "John Doe", "relation": "mentions"},
    {"target_id": "entity_phone", "target_type": "phone", "target_label": "+1-555-1234", "relation": "mentions"},
    {"target_id": "entity_linkedin", "target_type": "linkedin", "target_label": "https://linkedin.com/in/johndoe", "relation": "mentions"},
    {"target_id": "entity_company", "target_type": "company", "target_label": "Acme Corp", "relation": "mentions"}
  ]
}
```

#### ENTITY Nodes (Deduplicated)

**Entity 1: Email**
```json
{
  "id": "entity_email",
  "node_class": "entity",
  "node_type": "email",
  "label": "john.doe@example.com",
  "canonicalValue": "john.doe@example.com",

  "embedded_edges": [
    {"target_id": "source_001", "relation": "found_in", "confidence": 0.95},
    {"target_id": "source_002", "relation": "found_in", "confidence": 0.95},
    {"target_id": "source_003", "relation": "found_in", "confidence": 0.95}
  ]
}
```

**Entity 2: Username**
```json
{
  "id": "entity_username",
  "node_class": "entity",
  "node_type": "username",
  "label": "johndoe",
  "canonicalValue": "johndoe",

  "embedded_edges": [
    {"target_id": "source_001", "relation": "found_in", "confidence": 0.95}
  ]
}
```

**Entity 3: Password (from LinkedIn2021)**
```json
{
  "id": "entity_password1",
  "node_class": "entity",
  "node_type": "password",
  "label": "password123",
  "canonicalValue": "password123",

  "embedded_edges": [
    {"target_id": "source_001", "relation": "found_in", "confidence": 0.95}
  ]
}
```

**Entity 4: Password (from Adobe2013)**
```json
{
  "id": "entity_password2",
  "node_class": "entity",
  "node_type": "password",
  "label": "adobe2013pass",
  "canonicalValue": "adobe2013pass",

  "embedded_edges": [
    {"target_id": "source_002", "relation": "found_in", "confidence": 0.95}
  ]
}
```

**Entity 5: IP Address**
```json
{
  "id": "entity_ip",
  "node_class": "entity",
  "node_type": "ip",
  "label": "192.168.1.1",
  "canonicalValue": "192.168.1.1",

  "embedded_edges": [
    {"target_id": "source_001", "relation": "found_in", "confidence": 0.95}
  ]
}
```

**Entity 6: Person**
```json
{
  "id": "entity_person",
  "node_class": "entity",
  "node_type": "person",
  "label": "John Doe",
  "canonicalValue": "john doe",

  "embedded_edges": [
    {"target_id": "source_001", "relation": "found_in", "confidence": 0.95},
    {"target_id": "source_003", "relation": "found_in", "confidence": 0.95}
  ]
}
```

**Entity 7: Phone**
```json
{
  "id": "entity_phone",
  "node_class": "entity",
  "node_type": "phone",
  "label": "+1-555-1234",
  "canonicalValue": "+1-555-1234",

  "embedded_edges": [
    {"target_id": "source_001", "relation": "found_in", "confidence": 0.95},
    {"target_id": "source_003", "relation": "found_in", "confidence": 0.95}
  ]
}
```

**Entity 8: LinkedIn**
```json
{
  "id": "entity_linkedin",
  "node_class": "entity",
  "node_type": "linkedin",
  "label": "https://linkedin.com/in/johndoe",
  "canonicalValue": "https://linkedin.com/in/johndoe",

  "embedded_edges": [
    {"target_id": "source_003", "relation": "found_in", "confidence": 0.95}
  ]
}
```

**Entity 9: Company**
```json
{
  "id": "entity_company",
  "node_class": "entity",
  "node_type": "company",
  "label": "Acme Corp",
  "canonicalValue": "acme corp",

  "embedded_edges": [
    {"target_id": "source_003", "relation": "found_in", "confidence": 0.95}
  ]
}
```

### Graph Visualization

```
┌─────────────────────────────────────────────────────────────────┐
│                  EMAIL SEARCH: john.doe@example.com             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   SOURCE 1: LinkedIn2021 breach (via dehashed)                 │
│   [aggregator_result] {module: Eye-D, aggregator: dehashed}    │
│            │                                                    │
│            ├── [mentions] ──► Email: john.doe@example.com      │
│            ├── [mentions] ──► Username: johndoe                │
│            ├── [mentions] ──► Password: password123            │
│            ├── [mentions] ──► IP: 192.168.1.1                  │
│            ├── [mentions] ──► Person: John Doe                 │
│            └── [mentions] ──► Phone: +1-555-1234               │
│                                                                 │
│   SOURCE 2: Adobe2013 breach (via dehashed)                    │
│   [aggregator_result] {module: Eye-D, aggregator: dehashed}    │
│            │                                                    │
│            ├── [mentions] ──► Email: john.doe@example.com      │
│            └── [mentions] ──► Password: adobe2013pass          │
│                                                                 │
│   SOURCE 3: OSINT Industries enrichment                        │
│   [aggregator_result] {module: Eye-D, aggregator: osint_ind.}  │
│            │                                                    │
│            ├── [mentions] ──► Email: john.doe@example.com      │
│            ├── [mentions] ──► Person: John Doe                 │
│            ├── [mentions] ──► Phone: +1-555-1234               │
│            ├── [mentions] ──► LinkedIn: linkedin.com/in/johndoe│
│            └── [mentions] ──► Company: Acme Corp               │
│                                                                 │
│   ENTITIES (with reverse edges to sources):                    │
│   • Email: john.doe@example.com    [found_in: S1, S2, S3]     │
│   • Username: johndoe              [found_in: S1]              │
│   • Password: password123          [found_in: S1]              │
│   • Password: adobe2013pass        [found_in: S2]              │
│   • IP: 192.168.1.1                [found_in: S1]              │
│   • Person: John Doe               [found_in: S1, S3]          │
│   • Phone: +1-555-1234             [found_in: S1, S3]          │
│   • LinkedIn: linkedin/johndoe     [found_in: S3]              │
│   • Company: Acme Corp             [found_in: S3]              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. search_phone: +1-555-1234

### EYE-D Raw Output
```json
{
  "query": "+1-555-1234",
  "subtype": "phone",
  "results": [
    {
      "source": "osint_industries",
      "result_id": "osint_phone_001",
      "data": {
        "phone": "+1-555-1234",
        "owner": "John Doe",
        "carrier": "Verizon",
        "line_type": "mobile",
        "location": "New York, NY",
        "email": "john.doe@example.com"
      }
    }
  ]
}
```

### C-1 Nodes Created

#### SOURCE Node: OSINT Industries phone lookup
```json
{
  "id": "source_phone_001",
  "node_class": "source",
  "node_type": "aggregator_result",
  "label": "OSINT Industries phone lookup",
  "canonicalValue": "eyed:osint_industries:phone_lookup:osint_phone_001",

  "metadata": {
    "module": "Eye-D",
    "aggregator": "osint_industries",
    "primary": "phone_lookup",
    "result_id": "osint_phone_001",
    "carrier": "Verizon",
    "line_type": "mobile",
    "location": "New York, NY"
  },

  "embedded_edges": [
    {"target_id": "phone_entity", "target_type": "phone", "target_label": "+1-555-1234", "relation": "mentions"},
    {"target_id": "person_entity", "target_type": "person", "target_label": "John Doe", "relation": "mentions"},
    {"target_id": "email_entity", "target_type": "email", "target_label": "john.doe@example.com", "relation": "mentions"}
  ]
}
```

#### ENTITY Nodes
```json
{
  "id": "phone_entity",
  "node_class": "entity",
  "node_type": "phone",
  "label": "+1-555-1234",
  "embedded_edges": [
    {"target_id": "source_phone_001", "relation": "found_in"}
  ]
}
```

---

## 3. search_username: johndoe

### EYE-D Raw Output
```json
{
  "query": "johndoe",
  "subtype": "username",
  "results": [
    {
      "source": "sherlock",
      "result_id": "sherlock_001",
      "data": {
        "username": "johndoe",
        "platforms": [
          {"name": "GitHub", "url": "https://github.com/johndoe", "exists": true},
          {"name": "Twitter", "url": "https://twitter.com/johndoe", "exists": true},
          {"name": "Instagram", "url": "https://instagram.com/johndoe", "exists": false}
        ]
      }
    }
  ]
}
```

### C-1 Nodes Created

#### SOURCE Node: Sherlock platform discovery
```json
{
  "id": "source_sherlock_001",
  "node_class": "source",
  "node_type": "aggregator_result",
  "label": "Sherlock platform discovery",
  "canonicalValue": "eyed:sherlock:platform_discovery:sherlock_001",

  "metadata": {
    "module": "Eye-D",
    "aggregator": "sherlock",
    "primary": "platform_discovery",
    "result_id": "sherlock_001",
    "platforms_found": 2
  },

  "embedded_edges": [
    {"target_id": "username_entity", "target_type": "username", "target_label": "johndoe", "relation": "mentions"},
    {"target_id": "github_url", "target_type": "url", "target_label": "https://github.com/johndoe", "relation": "mentions"},
    {"target_id": "twitter_url", "target_type": "url", "target_label": "https://twitter.com/johndoe", "relation": "mentions"}
  ]
}
```

---

## 4. search_linkedin: https://linkedin.com/in/johndoe

### EYE-D Raw Output
```json
{
  "query": "https://linkedin.com/in/johndoe",
  "subtype": "linkedin",
  "results": [
    {
      "source": "proxycurl",
      "result_id": "proxycurl_001",
      "data": {
        "linkedin_url": "https://linkedin.com/in/johndoe",
        "full_name": "John Doe",
        "headline": "Senior Engineer at Acme Corp",
        "current_company": "Acme Corp",
        "current_title": "Senior Engineer",
        "location": "New York, NY",
        "email": "john.doe@example.com",
        "phone": "+1-555-1234"
      }
    }
  ]
}
```

### C-1 Nodes Created

#### SOURCE Node: Proxycurl LinkedIn enrichment
```json
{
  "id": "source_proxycurl_001",
  "node_class": "source",
  "node_type": "aggregator_result",
  "label": "Proxycurl LinkedIn enrichment",
  "canonicalValue": "eyed:proxycurl:linkedin_enrichment:proxycurl_001",

  "metadata": {
    "module": "Eye-D",
    "aggregator": "proxycurl",
    "primary": "linkedin_enrichment",
    "result_id": "proxycurl_001",
    "headline": "Senior Engineer at Acme Corp",
    "location": "New York, NY"
  },

  "embedded_edges": [
    {"target_id": "linkedin_entity", "target_type": "linkedin", "target_label": "https://linkedin.com/in/johndoe", "relation": "mentions"},
    {"target_id": "person_entity", "target_type": "person", "target_label": "John Doe", "relation": "mentions"},
    {"target_id": "company_entity", "target_type": "company", "target_label": "Acme Corp", "relation": "mentions"},
    {"target_id": "email_entity", "target_type": "email", "target_label": "john.doe@example.com", "relation": "mentions"},
    {"target_id": "phone_entity", "target_type": "phone", "target_label": "+1-555-1234", "relation": "mentions"}
  ]
}
```

---

## 5. search_whois: example.com

### EYE-D Raw Output
```json
{
  "query": "example.com",
  "subtype": "domain",
  "results": [
    {
      "source": "whoisxml",
      "result_id": "whoisxml_001",
      "data": {
        "domain": "example.com",
        "registrant_name": "John Doe",
        "registrant_email": "admin@example.com",
        "registrant_org": "Example Inc",
        "registrar": "GoDaddy",
        "created_date": "2010-01-01",
        "expires_date": "2025-01-01",
        "nameservers": ["ns1.example.com", "ns2.example.com"]
      }
    }
  ]
}
```

### C-1 Nodes Created

#### SOURCE Node: WhoisXML domain lookup
```json
{
  "id": "source_whoisxml_001",
  "node_class": "source",
  "node_type": "aggregator_result",
  "label": "WhoisXML domain lookup",
  "canonicalValue": "eyed:whoisxml:domain_lookup:whoisxml_001",

  "metadata": {
    "module": "Eye-D",
    "aggregator": "whoisxml",
    "primary": "domain_lookup",
    "result_id": "whoisxml_001",
    "registrar": "GoDaddy",
    "created_date": "2010-01-01",
    "expires_date": "2025-01-01"
  },

  "embedded_edges": [
    {"target_id": "domain_entity", "target_type": "domain", "target_label": "example.com", "relation": "mentions"},
    {"target_id": "person_entity", "target_type": "person", "target_label": "John Doe", "relation": "mentions"},
    {"target_id": "email_entity", "target_type": "email", "target_label": "admin@example.com", "relation": "mentions"},
    {"target_id": "company_entity", "target_type": "company", "target_label": "Example Inc", "relation": "mentions"}
  ]
}
```

---

## 6. search_ip: 192.168.1.1

### EYE-D Raw Output
```json
{
  "query": "192.168.1.1",
  "subtype": "ip",
  "results": [
    {
      "source": "ipgeolocation",
      "result_id": "ipgeo_001",
      "data": {
        "ip": "192.168.1.1",
        "city": "New York",
        "country": "United States",
        "isp": "Verizon",
        "organization": "Acme Corp",
        "latitude": 40.7128,
        "longitude": -74.0060
      }
    }
  ]
}
```

### C-1 Nodes Created

#### SOURCE Node: IPGeolocation lookup
```json
{
  "id": "source_ipgeo_001",
  "node_class": "source",
  "node_type": "aggregator_result",
  "label": "IPGeolocation lookup",
  "canonicalValue": "eyed:ipgeolocation:ip_lookup:ipgeo_001",

  "metadata": {
    "module": "Eye-D",
    "aggregator": "ipgeolocation",
    "primary": "ip_lookup",
    "result_id": "ipgeo_001",
    "city": "New York",
    "country": "United States",
    "isp": "Verizon"
  },

  "embedded_edges": [
    {"target_id": "ip_entity", "target_type": "ip", "target_label": "192.168.1.1", "relation": "mentions"},
    {"target_id": "company_entity", "target_type": "company", "target_label": "Acme Corp", "relation": "mentions"}
  ]
}
```

---

## 7. search_people: John Doe

### EYE-D Raw Output
```json
{
  "query": "John Doe",
  "subtype": "person",
  "results": [
    {
      "source": "occrp_aleph",
      "result_id": "aleph_001",
      "data": {
        "full_name": "John Doe",
        "addresses": ["123 Main St, New York, NY"],
        "companies": ["Acme Corp", "Example Inc"],
        "roles": ["CEO", "Director"],
        "birth_date": "1980-01-01"
      }
    }
  ]
}
```

### C-1 Nodes Created

#### SOURCE Node: OCCRP Aleph person search
```json
{
  "id": "source_aleph_001",
  "node_class": "source",
  "node_type": "aggregator_result",
  "label": "OCCRP Aleph person search",
  "canonicalValue": "eyed:occrp_aleph:person_search:aleph_001",

  "metadata": {
    "module": "Eye-D",
    "aggregator": "occrp_aleph",
    "primary": "person_search",
    "result_id": "aleph_001",
    "birth_date": "1980-01-01"
  },

  "embedded_edges": [
    {"target_id": "person_entity", "target_type": "person", "target_label": "John Doe", "relation": "mentions"},
    {"target_id": "address_entity", "target_type": "address", "target_label": "123 Main St, New York, NY", "relation": "mentions"},
    {"target_id": "company1_entity", "target_type": "company", "target_label": "Acme Corp", "relation": "mentions"},
    {"target_id": "company2_entity", "target_type": "company", "target_label": "Example Inc", "relation": "mentions"}
  ]
}
```

---

## 8. chain_reaction (Multi-Hop OSINT)

### Input
```json
{
  "start_query": "john.doe@example.com",
  "start_type": "email",
  "depth": 2
}
```

### Chain Execution Flow

```
┌──────────────────────────────────────────────────────────────┐
│ Hop 1: Email Search → john.doe@example.com                  │
├──────────────────────────────────────────────────────────────┤
│ Creates:                                                     │
│ • SOURCE 1: LinkedIn2021 breach (dehashed)                  │
│   ├─► Email: john.doe@example.com                           │
│   ├─► Username: johndoe                                     │
│   ├─► Phone: +1-555-1234                                    │
│   └─► Person: John Doe                                      │
│                                                              │
│ • SOURCE 2: OSINT Industries enrichment                     │
│   ├─► Email: john.doe@example.com                           │
│   ├─► Phone: +1-555-1234                                    │
│   └─► Company: Acme Corp                                    │
└──────────────────────────────────────────────────────────────┘
               │
               ├─► New entities discovered: Phone, Username
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Hop 2a: Phone Search → +1-555-1234                          │
├──────────────────────────────────────────────────────────────┤
│ Creates:                                                     │
│ • SOURCE 3: OSINT Industries phone lookup                   │
│   ├─► Phone: +1-555-1234                                    │
│   ├─► Person: John Doe                                      │
│   └─► Email: john.doe@example.com                           │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Hop 2b: Username Search → johndoe                           │
├──────────────────────────────────────────────────────────────┤
│ Creates:                                                     │
│ • SOURCE 4: Sherlock platform discovery                     │
│   ├─► Username: johndoe                                     │
│   ├─► URL: https://github.com/johndoe                       │
│   └─► URL: https://twitter.com/johndoe                      │
└──────────────────────────────────────────────────────────────┘
```

### Chain Result Structure
```json
{
  "chain_depth": 2,
  "hops": [
    {
      "hop_number": 1,
      "query": "john.doe@example.com",
      "type": "email",
      "sources_created": ["source_001", "source_002"],
      "entities_discovered": ["phone", "username", "person", "company"]
    },
    {
      "hop_number": 2,
      "query": "+1-555-1234",
      "type": "phone",
      "sources_created": ["source_003"],
      "entities_discovered": ["person"]
    },
    {
      "hop_number": 2,
      "query": "johndoe",
      "type": "username",
      "sources_created": ["source_004"],
      "entities_discovered": ["url", "url"]
    }
  ]
}
```

### Special Handling in MCP Server
```python
# mcp_server.py lines 209-215
if name == "chain_reaction":
    # Index each hop individually to preserve A→B→C topology
    for hop_result in result.get("results", []):
        # Each hop creates its own SOURCE nodes
        self.bridge.index_eyed_results(hop_result)
```

---

## Edge Types

### 1. mentions (SOURCE → ENTITY)
- **Direction**: SOURCE to ENTITY
- **Confidence**: 0.95
- **Meaning**: "This source mentions/contains this entity"
- **Created**: One edge per entity found in that result

### 2. found_in (ENTITY → SOURCE)
- **Direction**: ENTITY to SOURCE
- **Confidence**: 0.95
- **Meaning**: "This entity was found in this source"
- **Created**: Reverse edge for bidirectional relationship

---

## SOURCE Node Metadata Fields

```json
{
  "module": "Eye-D",                    // Always "Eye-D"
  "aggregator": "dehashed",             // osint_industries, proxycurl, sherlock, etc.
  "primary": "LinkedIn2021",            // Breach name, lookup type, etc.
  "result_id": "dehashed_result_001",   // Unique result identifier

  // Additional context fields (varies by result):
  "search_query": "john.doe@example.com",
  "search_type": "email",
  "carrier": "Verizon",
  "line_type": "mobile",
  "location": "New York, NY",
  "registrar": "GoDaddy",
  "created_date": "2010-01-01"
}
```

---

## Node ID Generation

### SOURCE Nodes
```python
# Format: eyed:{aggregator}:{primary}:{result_id}
canonical = f"eyed:{aggregator}:{primary}:{result_id}"
node_id = hashlib.sha256(canonical.encode()).hexdigest()[:16]

# Examples:
# "eyed:dehashed:linkedin2021:result_001" → abc123def456
# "eyed:osint_industries:enrichment:result_002" → xyz789ghi012
```

### ENTITY Nodes
```python
# Format: {type}:{canonical_value}
canonical = f"{type}:{value.lower().strip()}"
node_id = hashlib.sha256(canonical.encode()).hexdigest()[:16]

# Examples:
# "email:john.doe@example.com" → def456ghi789
# "phone:+1-555-1234" → ghi789jkl012
```

---

## Complete Example Summary

### Query: search_email("john.doe@example.com")

**Nodes Created**: 12 total
- 3 SOURCE nodes (aggregator_result)
- 9 ENTITY nodes (deduplicated)

**Edges Created**: 26 total
- 15 [mentions] edges (SOURCE → ENTITY)
- 11 [found_in] edges (ENTITY → SOURCE)

**Index**: `cymonides-1-{projectId}`

**Graph Structure**:
```
3 SOURCE nodes (star topology)
   ├─► Each SOURCE connects to all entities found in that result
   └─► Each ENTITY connects back to all sources that found it

Deduplication:
   - Email appears in 3 sources: 3 reverse edges
   - Phone appears in 2 sources: 2 reverse edges
   - Username appears in 1 source: 1 reverse edge
```

---

## Implementation Requirements

### C1Bridge Changes Needed

```python
# /data/EYE-D/c1_bridge.py

def index_eyed_results(self, eyed_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Index EYE-D OSINT results to Cymonides-1.

    For EACH result in eyed_results['results']:
    1. Create ONE SOURCE node (aggregator_result)
    2. Extract ALL entities from that result
    3. Create ENTITY nodes for each (deduplicated)
    4. Create edges: SOURCE --[mentions]--> ENTITY
    5. Create edges: ENTITY --[found_in]--> SOURCE
    """

    nodes_to_index = {}

    # Process each result individually
    for result in eyed_results.get('results', []):
        source_name = result.get('source')        # e.g., "dehashed"
        result_id = result.get('result_id')       # e.g., "dehashed_result_001"
        data = result.get('data', {})

        # Determine primary source (breach name, lookup type, etc.)
        primary = data.get('breach') or data.get('lookup_type') or 'enrichment'

        # Create SOURCE node
        source_node = self.create_source_node(
            module="Eye-D",
            aggregator=source_name,
            primary=primary,
            result_id=result_id,
            metadata=data
        )
        nodes_to_index[source_node.id] = source_node

        # Extract entities from this result
        entities = self.extract_entities_from_result(data)

        for entity in entities:
            # Create ENTITY node (or get existing)
            entity_node = self.create_entity_node(
                value=entity['value'],
                entity_type=entity['type']
            )

            if entity_node.id not in nodes_to_index:
                nodes_to_index[entity_node.id] = entity_node
            else:
                entity_node = nodes_to_index[entity_node.id]

            # Create edges: SOURCE --[mentions]--> ENTITY
            self.add_edge(
                source_node,
                entity_node,
                relation="mentions",
                confidence=0.95
            )

            # Create edges: ENTITY --[found_in]--> SOURCE
            self.add_edge(
                entity_node,
                source_node,
                relation="found_in",
                confidence=0.95
            )

    # Bulk upsert to Elasticsearch
    self._bulk_upsert_nodes(list(nodes_to_index.values()))
```

---

## Code References

| Component                  | File Path                                   | Key Function                              |
|----------------------------|---------------------------------------------|-------------------------------------------|
| MCP Server                 | `/data/EYE-D/mcp_server.py`                | `call_tool()` (line 175-227)             |
| C1 Bridge                  | `/data/EYE-D/c1_bridge.py`                 | `index_eyed_results()` (needs update)    |
| SOURCE Node Creation       | `/data/EYE-D/c1_bridge.py`                 | `create_source_node()` (needs creation)  |
| Entity Extraction          | `/data/EYE-D/c1_bridge.py`                 | `extract_entities_from_result()` (new)   |
