# Data Breaches Use Case

**Purpose:** Search leaked credentials, exposed data, and breach intelligence from major data leaks

## Overview

Data breaches provide critical intelligence for:
- **OSINT Investigations:** Find email/password combinations
- **Credential Analysis:** Password reuse patterns
- **Domain Exposure:** Which companies have been breached
- **Timeline Analysis:** When accounts were created/compromised
- **Network Mapping:** Connect identities across breaches

## Indices Used

### 1. Nexus Breach Records (197K records)
**Index:** `nexus_breach_records`
- **Status:** ✅ Indexed (197,668 docs, 90MB)
- **Content:** Parsed breach records with structured fields
- **Fields:** `breach_name`, `raw_content`, `parsed_fields`, `file_path`, `line_number`, `record_id`, `timestamp`, `node_ids`
- **Use:** Quick search for credentials, emails, usernames

### 2. Nexus Breach Metadata (6 breaches)
**Index:** `nexus_breaches`
- **Status:** ✅ Indexed (6 docs, 21KB)
- **Content:** Breach metadata (name, date, size, source)
- **Use:** Browse available breaches, get statistics

## Data Source

### Raidforums Archive (497GB)
**Location:** `/Volumes/My Book/Raidforums/`
**Status:** ⏳ **NOT YET INDEXED** (Raw data on external drive)

**Contents:**
- `DATABASES/` - Raw breach dumps
- `indices/` - Pre-processed index files
- `checkpoints/` - Indexing progress
- `ingestion/` - Ingestion scripts
- `schemas/` - Data schemas
- `scripts/` - Processing utilities
- `temp_index/` - Temp indexing workspace

**Size:** 497GB of breach data
**Format:** Various (CSV, SQL dumps, plain text combos)
**Source:** Historical Raidforums data leaks

### Current Indexed Status
- ✅ Small subset indexed: 197K records (90MB) in `nexus_breach_records`
- ⏳ Full dataset unindexed: 497GB on My Book drive
- **Gap:** Millions of breach records not yet searchable

## Data Structure

### Breach Record Document
```json
{
  "_id": "breach_record_id",
  "breach_name": "LinkedInBreach2012",
  "raw_content": "user@example.com:password123",
  "parsed_fields": {
    "email": "user@example.com",
    "password": "password123",
    "username": "user123",
    "phone": null,
    "additional": {}
  },
  "file_path": "/DATABASES/linkedin/combo.txt",
  "line_number": 42,
  "record_id": "linkedin_00000042",
  "timestamp": "2012-06-05T00:00:00Z",
  "node_ids": ["email_node_id", "person_node_id"]
}
```

### Breach Metadata Document
```json
{
  "_id": "breach_id",
  "breach_name": "LinkedInBreach2012",
  "breach_date": "2012-06-05",
  "record_count": 6500000,
  "source": "raidforums",
  "data_types": ["email", "password"],
  "indexed": true,
  "index_name": "nexus_breach_records",
  "file_location": "/Volumes/My Book/Raidforums/DATABASES/linkedin/"
}
```

## Query Patterns

### 1. Search by Email
```bash
curl "http://localhost:9200/nexus_breach_records/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": {
    "term": { "parsed_fields.email.keyword": "user@example.com" }
  }
}'
```

### 2. Find Domain Exposure
```bash
# All breached emails from a domain
curl "http://localhost:9200/nexus_breach_records/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": {
    "wildcard": { "parsed_fields.email": "*@example.com" }
  },
  "aggs": {
    "breaches": {
      "terms": { "field": "breach_name.keyword" }
    }
  }
}'
```

### 3. Password Reuse Analysis
```bash
# Find same password across breaches
curl "http://localhost:9200/nexus_breach_records/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": {
    "term": { "parsed_fields.password.keyword": "password123" }
  },
  "aggs": {
    "emails": {
      "terms": { "field": "parsed_fields.email.keyword" }
    }
  }
}'
```

### 4. Username Pivot
```bash
# Find email from username
curl "http://localhost:9200/nexus_breach_records/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": {
    "term": { "parsed_fields.username.keyword": "johndoe123" }
  }
}'
```

### 5. List Available Breaches
```bash
curl "http://localhost:9200/nexus_breaches/_search?size=100"
```

## Integration with Other Use Cases

### Company Profiles
**Cross-Reference:**
1. Find company domain
2. Query breach index: `*@company.com`
3. Show compromised accounts
4. Add to risk profile

**Code:** Link from `company-profiles` → breach search

### Red Flags
**Indicators:**
- Large number of breached accounts → weak security
- Executive emails in breaches → high-value targets
- Recent breach activity → ongoing risk

**Code:** Automated screening in red flag detection

### C-1 Entity Graphs
**Auto-Create Nodes:**
- `EMAIL` nodes from breach data
- `PERSON` nodes (inferred from emails/usernames)
- `has_password` edges (Email → Password)
- `breached_in` edges (Email → Breach)

**Code:** `server/utils/templateAutoPopulation.ts` (breach data auto-population)

## Indexing Workflow

### Current: Partial Index (197K records)
Already indexed, searchable via `nexus_breach_records`

### Future: Full Raidforums Index (497GB)

**Step 1: Inventory**
```bash
ls -lh "/Volumes/My Book/Raidforums/DATABASES/"
# Identify all breach folders and file formats
```

**Step 2: Schema Detection**
```bash
# Check existing schemas
cat "/Volumes/My Book/Raidforums/schemas/*.json"
```

**Step 3: Batch Indexing**
```bash
# Use ingestion scripts
cd "/Volumes/My Book/Raidforums/ingestion/"
python3 index_breach.py --breach LinkedInBreach2012 --batch-size 10000
```

**Step 4: Checkpointing**
```bash
# Resume interrupted indexing
python3 index_breach.py --resume-from-checkpoint
```

**Step 5: Verification**
```bash
# Verify record counts
curl "http://localhost:9200/nexus_breach_records/_count"
```

## Storage Considerations

### Current State
- **Indexed:** 90MB (197K records)
- **Unindexed:** 497GB (millions of records)

### Full Index Estimates
**If all Raidforums data indexed:**
- Raw data: 497GB
- Elasticsearch index: ~150-200GB (compressed, with metadata)
- Record count: 100M-500M (estimate)

**Storage Requirements:**
- Elasticsearch needs 200GB+ free
- Recommend: Index to separate ES instance or dedicated node
- Alternative: Index selectively (high-value breaches only)

## High-Value Breaches (Priority List)

Based on investigative value:

1. **LinkedIn (2012, 2016)** - Professional network, real names
2. **Adobe (2013)** - Password hints, names, emails
3. **Dropbox (2012)** - Cloud storage users
4. **MySpace (2008)** - Usernames, DOBs, locations
5. **Tumblr (2013)** - Email/password combos
6. **Twitter (2023)** - Email/phone verification
7. **Facebook (2021)** - Phone numbers, names, locations
8. **Telegram (2023)** - Phone numbers
9. **Gravatar (2020)** - Email/username links
10. **Pastebin Compilations** - Various combo lists

## Security & Legal Considerations

### Usage Guidelines
- ✅ **Legitimate Use:** OSINT investigations, security research, victim notification
- ❌ **Prohibited:** Credential stuffing, unauthorized access, harassment
- ⚠️ **Data Sensitivity:** Contains PII (emails, passwords, phones)
- 🔒 **Access Control:** Limit to authorized investigators only

### Data Handling
- Store on encrypted drives
- Do not upload to cloud services
- Do not share raw breach data
- Redact credentials in reports
- Follow data protection regulations

### Responsible Disclosure
- If breach contains new data → notify affected parties
- Report active breaches to authorities
- Use data to improve security posture
- Avoid public exposure of credentials

## Related Modules

**Python:**
- Breach ingestion scripts: `/Volumes/My Book/Raidforums/ingestion/`
- Schema parsers: `/Volumes/My Book/Raidforums/schemas/`

**Node.js:**
- Breach search API: `server/services/breachSearchService.ts` (if exists)
- Auto-population: `server/utils/templateAutoPopulation.ts`

**Frontend:**
- Breach lookup UI: `client/src/components/BreachSearch.tsx` (if exists)

## Common Workflows

### 1. Investigate Individual
```
1. Collect: Email addresses, usernames, phone
2. Query: nexus_breach_records for each identifier
3. Pivot: Find additional accounts via password reuse
4. Timeline: Chart account creation dates
5. Report: Compromised accounts summary
```

### 2. Company Security Assessment
```
1. Input: Company domain (example.com)
2. Query: *@example.com in breach index
3. Aggregate: Breaches by date, count by department
4. Analyze: Password patterns, high-value targets
5. Report: Domain exposure risk score
```

### 3. Attribution via Breach Data
```
1. Find: Username in breach A
2. Extract: Associated email
3. Search: Email in breach B
4. Discover: Real name, additional accounts
5. Link: Create entity graph connecting identities
```

## Future Enhancements

1. **Full Raidforums Indexing**
   - Index all 497GB to Elasticsearch
   - Estimated: 100M-500M records
   - Priority: High-value breaches first

2. **Real-Time Breach Monitoring**
   - Monitor paste sites (Pastebin, GitHub Gists)
   - Auto-index new breaches
   - Alert on domains of interest

3. **Breach API Integration**
   - HaveIBeenPwned API
   - DeHashed API
   - Snusbase API
   - LeakCheck API

4. **Advanced Analytics**
   - Password cracking statistics
   - Credential reuse scoring
   - Email domain risk profiling
   - Network clustering of identities

5. **Integration with C-1**
   - Auto-create EMAIL/PERSON nodes from breaches
   - `breached_in` edges (Email → Breach name)
   - `has_password` edges (Email → Password hash)
   - Timeline view of account compromises

## Related Documentation

- **Company Profiles:** `../company-profiles/DATASETS.md` (mentions breach records)
- **Red Flags:** `../red-flags/DATASETS.md` (breach data as risk indicator)
- **Raidforums Archive:** `/Volumes/My Book/Raidforums/docs/`
- **Nexus Breaches:** `cymonides/metadata/nexus_breach_records/` (needs metadata.json)

## Quick Start

### Search for Email
```bash
curl "http://localhost:9200/nexus_breach_records/_search?q=parsed_fields.email:user@example.com"
```

### Get Breach Stats
```bash
curl "http://localhost:9200/nexus_breaches/_search?size=100" | jq '.hits.hits[]._source'
```

### Count Records per Breach
```bash
curl -X POST "http://localhost:9200/nexus_breach_records/_search?size=0" \
  -H 'Content-Type: application/json' -d '{
  "aggs": {
    "by_breach": {
      "terms": { "field": "breach_name.keyword", "size": 100 }
    }
  }
}'
```
