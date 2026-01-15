# Red Flags Use Case

**Purpose:** Risk indicators, anomaly detection, suspicious patterns in investigations

## Indices Used

> **🚨 See [DATASETS.md](DATASETS.md) for red flag datasets: WorldCheck (5.4M PEPs/sanctions), OpenSanctions, FTM collections, breach records**

### All Cymonides Indices (Cross-Referenced)
Red flag detection draws from ALL indices with specific query patterns to identify:
- Unusual entity relationships
- Suspicious domain patterns
- Hidden ownership structures
- Document contradictions
- Timeline anomalies

## Red Flag Categories

### 1. Entity Red Flags
**Sources:** `cymonides-1-project-{id}`, `cymonides_source_entities`

**Patterns:**
- **Multiple Officers with Same Address** → Shell company indicator
  ```bash
  # Aggregate officers by address
  GET /cymonides-1-project-{id}/_search
  {
    "aggs": {
      "by_address": {
        "terms": { "field": "officers.address.keyword", "min_doc_count": 3 }
      }
    }
  }
  ```

- **Director Recycling** → Same person in 10+ companies
  ```bash
  # Find serial directors
  GET /cymonides-1-project-{id}/_search
  {
    "query": { "term": { "officers.name.keyword": "John Smith" } }
  }
  ```

- **Circular Ownership** → Company A owns B owns A
  ```bash
  # Trace shareholder chains
  GET /cymonides-1-project-{id}/_search
  {
    "query": { "terms": { "shareholders.name.keyword": ["Company A", "Company B"] } }
  }
  ```

### 2. Domain Red Flags
**Sources:** `cymonides_cc_domain_*`, `cymonides_source_enrichments`, `cymonides_bangs`

**Patterns:**
- **Zero Backlinks** → Isolated/hidden site
  ```bash
  # Find domains with no inbound links
  POST /cymonides_cc_domain_edges/_search
  {
    "size": 0,
    "aggs": {
      "isolated": {
        "terms": { "field": "target_domain", "min_doc_count": 1 },
        "aggs": { "link_count": { "sum": { "field": "count" } } }
      }
    }
  }
  ```

- **Fake News Network** → Multiple domains linking to each other but nowhere else
  ```bash
  # Find closed link clusters
  GET /cymonides_cc_domain_edges/_search
  {
    "query": {
      "bool": {
        "must": [
          { "terms": { "source_domain": ["site1.com", "site2.com"] } },
          { "terms": { "target_domain": ["site1.com", "site2.com"] } }
        ]
      }
    }
  }
  ```

- **Domain Age Mismatch** → "Established 1995" but domain registered 2023
  ```bash
  # Check CC coverage dates
  GET /cymonides_source_enrichments/_doc/{source_id}
  # Compare cc_coverage.checked_at with claimed history
  ```

- **Typosquatting** → Domains similar to known brands
  ```bash
  # Fuzzy match on domain names
  GET /cymonides_cc_domain_vertices/_search
  {
    "query": { "fuzzy": { "domain": { "value": "microsoft.com", "fuzziness": 2 } } }
  }
  ```

### 3. Content Red Flags
**Sources:** `cymonides-2`, `cymonides_source_entities`

**Patterns:**
- **Contradictory Statements** → Document A says X, Document B says NOT X
  ```bash
  # Search for opposing claims
  GET /cymonides-2/_search
  {
    "query": {
      "bool": {
        "must": [ { "match": { "content": "John Smith CEO" } } ],
        "must_not": [ { "match": { "content": "John Smith resigned" } } ]
      }
    }
  }
  ```

- **Duplicated Content** → Same text across multiple domains
  ```bash
  # Find identical content_hash
  GET /cymonides-2/_search
  {
    "aggs": {
      "duplicates": {
        "terms": { "field": "content_hash", "min_doc_count": 2 }
      }
    }
  }
  ```

- **Sanitized Records** → Entity mentions removed from pages
  ```bash
  # Compare historical snapshots
  GET /cymonides_source_entities/_search
  {
    "query": {
      "bool": {
        "must": [ { "term": { "domain": "example.com" } } ],
        "filter": [ { "term": { "cleaned": true } } ]
      }
    }
  }
  ```

### 4. Timeline Red Flags
**Sources:** `cymonides-2` (document dates), `cymonides-1-project-{id}` (entity history)

**Patterns:**
- **Retroactive Documents** → File dated before company existed
- **Gap Periods** → No records for suspicious timeframes
- **Timestamp Manipulation** → Extracted_at vs claimed publication date

```bash
# Find date anomalies
GET /cymonides-2/_search
{
  "query": {
    "script": {
      "script": {
        "source": "doc['indexed_at'].value.toInstant().toEpochMilli() < doc['claimed_date'].value.toInstant().toEpochMilli()"
      }
    }
  }
}
```

### 5. Network Red Flags
**Sources:** `cymonides_cc_domain_edges`, `cymonides-1-project-{id}`

**Patterns:**
- **Link Farms** → 1000+ outlinks from single domain
  ```bash
  GET /cymonides_cc_domain_edges/_search
  {
    "aggs": {
      "link_farms": {
        "terms": { "field": "source_domain", "min_doc_count": 1000 }
      }
    }
  }
  ```

- **Hidden Ownership Networks** → Common officers across unrelated companies
  ```bash
  # Find officer overlap across companies
  GET /cymonides-1-project-{id}/_search
  {
    "query": {
      "more_like_this": {
        "fields": ["officers.name"],
        "like": [ { "_id": "company_A_id" } ],
        "min_term_freq": 1
      }
    }
  }
  ```

## Automated Red Flag Detection

### Current Implementation
- **Location:** `server/services/narrativeContextService.ts`
- **Function:** `detectRedFlags(entities, documents)`
- **Triggers:** Auto-runs on narrative save, entity update

### Planned Indices
- **`red_flags`** (not yet created)
  - Purpose: Store detected anomalies
  - Fields: `flag_type`, `severity`, `entity_ids`, `evidence_docs`, `detected_at`

## Related Modules

- **Disambiguator** (planned) - Contradiction detection
- **Entity Resolution** (`server/services/entityResolutionService.ts`) - Duplicate detection
- **Narrative Context** (`server/services/narrativeContextService.ts`) - Gap detection

## Example Red Flag Queries

### Find shell companies (same address pattern)
```bash
POST /cymonides-1-project-ge13t70tq8v0hw0h994z1v64/_search
{
  "size": 0,
  "aggs": {
    "shared_addresses": {
      "terms": { 
        "script": "doc['officers.address.keyword'].value",
        "min_doc_count": 5
      }
    }
  }
}
```

### Find domains with no backlinks but claiming authority
```bash
POST /_search
{
  "query": {
    "bool": {
      "must": [
        { "term": { "_index": "cymonides_source_enrichments" } },
        { "exists": { "field": "cc_coverage" } }
      ],
      "must_not": [
        { "range": { "cc_coverage.inlink_count": { "gte": 1 } } }
      ]
    }
  }
}
```

### Find contradictory officer records
```bash
# Search for "John Smith" as both CEO and "resigned"
POST /cymonides-2/_search
{
  "query": {
    "bool": {
      "must": [ { "match": { "content": "John Smith" } } ],
      "should": [
        { "match": { "content": "appointed CEO" } },
        { "match": { "content": "resigned" } }
      ],
      "minimum_should_match": 2
    }
  },
  "aggs": {
    "by_date": {
      "date_histogram": { "field": "indexed_at", "interval": "month" }
    }
  }
}
```

## Cross-Reference

Red flags detection overlaps with ALL use cases:
- **`company-profiles`** - Entity and ownership red flags
- **`domains-list`** - Domain and network red flags
- Plus: Document contradictions, timeline anomalies

## Severity Levels

- 🔴 **CRITICAL** - Clear fraud indicators (circular ownership, fake dates)
- 🟡 **WARNING** - Suspicious patterns (unusual networks, gaps)
- 🟢 **INFO** - Anomalies for review (duplicate content, typos)

## Future Enhancements

1. **ML-based anomaly detection** on entity graphs
2. **Automated contradiction finder** (Disambiguator module)
3. **Temporal analysis** of entity changes
4. **Network visualization** of red flag clusters
5. **Scoring system** - composite risk score per entity
