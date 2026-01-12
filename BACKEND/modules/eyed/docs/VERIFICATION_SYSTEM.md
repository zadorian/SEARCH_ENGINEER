# EYE-D Verification System

## Overview

The VERIFIED/UNVERIFIED system is a priority queue-based search architecture that tags all graph nodes and relationships based on the reliability of the evidence chain.

## Core Principle

**Verification status is determined by what TYPE of entity you SEARCH ON, not what you extract.**

- Searching ON **unique identifiers** (email, phone, domain, IP) → **VERIFIED** results
- Searching ON **ambiguous identifiers** (name, username) → **UNVERIFIED** results

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EYE-D VERIFICATION FLOW                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INPUT: emails, phones, names, usernames                                    │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 1: SEED QUEUES (by entity TYPE)                                  │  │
│  │                                                                       │  │
│  │   ┌─────────────────┐              ┌─────────────────┐                │  │
│  │   │ VERIFIED QUEUE  │              │ UNVERIFIED QUEUE│                │  │
│  │   │ (Priority: 1)   │              │ (Priority: 2)   │                │  │
│  │   ├─────────────────┤              ├─────────────────┤                │  │
│  │   │ • emails        │              │ • names         │                │  │
│  │   │ • phones        │              │ • usernames     │                │  │
│  │   │ • domains       │              │                 │                │  │
│  │   │ • IPs           │              │                 │                │  │
│  │   └─────────────────┘              └─────────────────┘                │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 2: EXHAUST VERIFIED QUEUE                                        │  │
│  │                                                                       │  │
│  │   FOR EACH entity IN verified_queue:                                  │  │
│  │     1. Search via UnifiedSearcher (OSINT, DeHashed, WHOIS, etc.)      │  │
│  │     2. Tag ALL results as VERIFIED                                    │  │
│  │     3. Extract entities from results                                  │  │
│  │     4. Route extracted entities:                                      │  │
│  │        • email/phone/domain/IP → VERIFIED queue                       │  │
│  │        • name/username → UNVERIFIED queue                             │  │
│  │     5. Store RAW DATA for Haiku verification pass                     │  │
│  │     6. Persist to Cymonides with VERIFIED NARRATIVE tag               │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 3: HAIKU VERIFICATION PASS                                       │  │
│  │                                                                       │  │
│  │   ┌─────────────────────────────────────────────────────────────┐     │  │
│  │   │ HAIKU AI analyzes:                                          │     │  │
│  │   │                                                             │     │  │
│  │   │ "Do any UNVERIFIED entities (names/usernames) appear       │     │  │
│  │   │  in the VERIFIED raw data?"                                 │     │  │
│  │   │                                                             │     │  │
│  │   │ IF FOUND → PROMOTE to VERIFIED queue (evidence exists!)     │     │  │
│  │   │ IF NOT   → Remains in UNVERIFIED queue                      │     │  │
│  │   └─────────────────────────────────────────────────────────────┘     │  │
│  │                                                                       │  │
│  │   Example:                                                            │  │
│  │   • Search "john@acme.com" returns "Account holder: John D. Smith"    │  │
│  │   • "John Smith" was in UNVERIFIED queue                              │  │
│  │   • Haiku finds match → PROMOTES "John Smith" to VERIFIED             │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 4: PROCESS PROMOTED ENTITIES                                     │  │
│  │                                                                       │  │
│  │   FOR EACH promoted entity IN verified_queue:                         │  │
│  │     1. Search (even though it's a name, we have EVIDENCE!)            │  │
│  │     2. Tag ALL results as VERIFIED                                    │  │
│  │     3. Persist with VERIFIED NARRATIVE tag                            │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 5: PROCESS REMAINING UNVERIFIED                                  │  │
│  │                                                                       │  │
│  │   FOR EACH entity IN unverified_queue (no evidence found):            │  │
│  │     1. Search                                                         │  │
│  │     2. Tag ALL results as UNVERIFIED                                  │  │
│  │     3. Persist with UNVERIFIED NARRATIVE tag                          │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Graph Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CYMONIDES GRAPH STRUCTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  NARRATIVE TAG NODES (Singletons - only 2 exist in entire graph):           │
│                                                                             │
│  ┌──────────────────────────┐       ┌──────────────────────────┐            │
│  │ id: narrative_tag_       │       │ id: narrative_tag_       │            │
│  │     VERIFIED             │       │     UNVERIFIED           │            │
│  │ class: NARRATIVE         │       │ class: NARRATIVE         │            │
│  │ type: verification_tag   │       │ type: verification_tag   │            │
│  │ comment: "High-confidence│       │ comment: "Lower-confidence│           │
│  │  unique identifiers"     │       │  ambiguous identifiers"  │            │
│  └──────────────────────────┘       └──────────────────────────┘            │
│              ↑                                  ↑                           │
│              │ HAS_TAG                          │ HAS_TAG                   │
│              │                                  │                           │
│  ════════════╪══════════════════════════════════╪═══════════════════════    │
│              │                                  │                           │
│  FOR EACH SEARCH, CREATE 4 NODE TYPES:          │                           │
│              │                                  │                           │
│  ┌───────────┴────────────┐     ┌───────────────┴──────────────┐            │
│  │                        │     │                              │            │
│  │  1. SOURCE ENTITY      │     │  1. SOURCE ENTITY            │            │
│  │     (what we searched) │     │     (what we searched)       │            │
│  │     class: ENTITY      │     │     class: ENTITY            │            │
│  │     HAS_TAG → VERIFIED │     │     HAS_TAG → UNVERIFIED     │            │
│  │                        │     │                              │            │
│  │  2. FOUND ENTITIES     │     │  2. FOUND ENTITIES           │            │
│  │     (extracted)        │     │     (extracted)              │            │
│  │     class: ENTITY      │     │     class: ENTITY            │            │
│  │     HAS_TAG → VERIFIED │     │     HAS_TAG → UNVERIFIED     │            │
│  │                        │     │                              │            │
│  │  3. NEXUS RELATIONSHIP │     │  3. NEXUS RELATIONSHIP       │            │
│  │     (reified edge)     │     │     (reified edge)           │            │
│  │     class: NEXUS       │     │     class: NEXUS             │            │
│  │     CONNECTS_FROM →    │     │     CONNECTS_FROM →          │            │
│  │     CONNECTS_TO →      │     │     CONNECTS_TO →            │            │
│  │     HAS_TAG → VERIFIED │     │     HAS_TAG → UNVERIFIED     │            │
│  │                        │     │                              │            │
│  │  4. AGGREGATOR RESULT  │     │  4. AGGREGATOR RESULT        │            │
│  │     (raw output)       │     │     (raw output)             │            │
│  │     class: LOCATION    │     │     class: LOCATION          │            │
│  │     comment: {JSON}    │     │     comment: {JSON}          │            │
│  │     HAS_TAG → VERIFIED │     │     HAS_TAG → UNVERIFIED     │            │
│  │                        │     │                              │            │
│  └────────────────────────┘     └──────────────────────────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Input Recognition

### Supported Input Types

| Type | CLI Flag | File Prefix | Auto-Detection |
|------|----------|-------------|----------------|
| email | `--emails`, `-e` | `email:` | Contains `@` and `.` |
| phone | `--phones`, `-p` | `phone:` | Digits with `+`, `-`, `()` |
| name | `--names`, `-n` | `name:` | Default (anything else) |
| domain | `--domains`, `-d` | `domain:` | Has `.`, no `@`, no spaces |
| IP | `--ips` | `ip:` | IPv4/IPv6 pattern |
| username | `--usernames`, `-u` | `username:` | Starts with `@` or short no-space |

### Input File Format

```
# Comments start with #
email:john@example.com
phone:+1-555-1234
name:John Smith
domain:example.com
ip:192.168.1.1
username:jsmith

# Or auto-detected:
jane@company.org
+44-20-7946-0958
Sarah Connor
acme.com
10.0.0.1
@johndoe
```

## Verification Rules

### Queue Assignment (by Entity Type)

| Entity Type | Queue | Reason |
|-------------|-------|--------|
| email | VERIFIED | Unique identifier - one person per email |
| phone | VERIFIED | Unique identifier - traceable to owner |
| domain | VERIFIED | Unique identifier - DNS records exist |
| IP | VERIFIED | Unique identifier - network traceable |
| **name** | **UNVERIFIED** | Ambiguous - many people share names |
| **username** | **UNVERIFIED** | Ambiguous - can be reused, common |

### Tag Assignment (based on what you SEARCH ON)

| Search ON | Results Tagged | All Extracted Entities Tagged |
|-----------|----------------|-------------------------------|
| email | VERIFIED | VERIFIED |
| phone | VERIFIED | VERIFIED |
| domain | VERIFIED | VERIFIED |
| IP | VERIFIED | VERIFIED |
| name | UNVERIFIED | UNVERIFIED |
| username | UNVERIFIED | UNVERIFIED |
| **name (PROMOTED)** | **VERIFIED** | **VERIFIED** |

### Tag Transition Rules (NEVER DOWNGRADE)

```
UNVERIFIED → VERIFIED   ✅ ALLOWED (evidence found via Haiku)
VERIFIED   → VERIFIED   ✅ ALLOWED (stays verified)
VERIFIED   → UNVERIFIED ❌ FORBIDDEN (preserve original trust)
UNVERIFIED → UNVERIFIED ✅ ALLOWED (stays unverified)
```

## Code Locations

### full_osint_report.py

| Lines | Function | Purpose |
|-------|----------|---------|
| 112-124 | `__init__` | Initialize queues and stats |
| 159-270 | `haiku_verify_unverified()` | Haiku AI verification pass |
| 436-447 | `process_result()` | Route entities to correct queue |
| 520-547 | Seed queues | Initial queue assignment |
| 553-582 | Step 2 | Exhaust VERIFIED queue |
| 584-592 | Step 3 | Haiku verification pass |
| 594-621 | Step 4 | Process promoted entities |
| 623-649 | Step 5 | Process remaining UNVERIFIED |

### c1_bridge.py

| Lines | Function | Purpose |
|-------|----------|---------|
| 66-68 | Class constants | NARRATIVE tag node IDs |
| 75-127 | `_ensure_narrative_tags()` | Create singleton tag nodes |
| 131-243 | `index_eyed_results()` | Create all graph nodes |
| 168-243 | Section 1 | Source entity (no-downgrade) |
| 245-285 | Section 2 | Aggregator result node |
| 287-361 | Section 3 | Found entities (no-downgrade) |
| 363-420 | Section 3 | NEXUS relationship nodes |

## Example Flow

```
INPUT:
  emails: ["john@acme.com"]
  names: ["John Smith"]

STEP 1 - SEED:
  VERIFIED queue: ["john@acme.com"]
  UNVERIFIED queue: ["John Smith", "Smith, John", "J. Smith"]

STEP 2 - SEARCH VERIFIED:
  Search "john@acme.com" via OSINT Industries
  → Returns: {name: "John D. Smith", phone: "+1-555-1234"}
  → Tag results: VERIFIED
  → Route extracted:
      "+1-555-1234" (phone) → VERIFIED queue
      "John D. Smith" (name) → UNVERIFIED queue
  → Store raw data

STEP 3 - HAIKU VERIFICATION:
  UNVERIFIED queue: ["John Smith", "Smith, John", "J. Smith", "John D. Smith"]

  Haiku checks: "Does 'John Smith' appear in verified raw data?"
  → FOUND: "John D. Smith" in email search results
  → SIMILAR: "John Smith" matches "John D. Smith"

  PROMOTE: "John Smith" → VERIFIED queue
  PROMOTE: "John D. Smith" → VERIFIED queue

STEP 4 - SEARCH PROMOTED:
  Search "John Smith" (PROMOTED→VERIFIED)
  → Tag results: VERIFIED (we have evidence!)
  → All nodes get VERIFIED NARRATIVE tag

STEP 5 - SEARCH REMAINING UNVERIFIED:
  Search "Smith, John" (no evidence)
  → Tag results: UNVERIFIED

FINAL STATS:
  Total searches: 5
  VERIFIED searches: 3 (email + phone + promoted name)
  UNVERIFIED searches: 2
  Promoted to VERIFIED: 2
```

## Querying the Graph

### Find all VERIFIED entities
```json
{
  "query": {
    "nested": {
      "path": "embedded_edges",
      "query": {
        "bool": {
          "must": [
            {"term": {"embedded_edges.target_id": "narrative_tag_VERIFIED"}},
            {"term": {"embedded_edges.relation": "HAS_TAG"}}
          ]
        }
      }
    }
  }
}
```

### Find all VERIFIED relationships for an entity
```json
{
  "query": {
    "bool": {
      "must": [
        {"term": {"class": "NEXUS"}},
        {"nested": {
          "path": "embedded_edges",
          "query": {
            "bool": {
              "must": [
                {"term": {"embedded_edges.target_id": "ent_abc123"}},
                {"term": {"embedded_edges.relation": "CONNECTS_FROM"}}
              ]
            }
          }
        }},
        {"nested": {
          "path": "embedded_edges",
          "query": {
            "term": {"embedded_edges.target_id": "narrative_tag_VERIFIED"}
          }
        }}
      ]
    }
  }
}
```

## Integration Points

- **NEXUS Variations**: Phone/name variations via `/data/NEXUS/`
- **PACMAN Extraction**: Entity extraction via `/data/PACMAN/`
- **BRUTE Search**: Multi-engine search via `/data/BRUTE/`
- **Cymonides Graph**: Elasticsearch persistence via `c1_bridge.py`
- **EDITH Reports**: Markdown reports via `edith_writeup.py`
