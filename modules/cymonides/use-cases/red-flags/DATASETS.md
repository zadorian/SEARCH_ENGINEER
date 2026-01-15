# Red Flag Detection Datasets

Datasets specifically used for risk screening, sanctions checks, and anomaly detection.

## Critical: Sanctions & Watchlist Data

### 1. WorldCheck (5.4M records) - NOT YET INDEXED ⚠️
**Status:** ⏳ **CRITICAL PRIORITY** - File available, indexer ready
- **Source:** `/Volumes/My Book/DOWNLOADS/Free - world-check.com (10.2022).txt`
- **Coverage:** 5.4M records
  - Politically Exposed Persons (PEPs)
  - Global sanctions lists
  - Adverse media mentions
  - Criminal watchlists
- **Indexer:** `python-backend/modules/brute/scripts/index_worldcheck_with_edges.py`
- **Storage:** PostgreSQL graph + Elasticsearch
- **Use:** Screen entities against global watchlists

**Screening Workflow (when indexed):**
```bash
# Check company/person against WorldCheck
curl "http://localhost:9200/worldcheck/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": {
    "multi_match": {
      "query": "John Smith",
      "fields": ["name", "aliases"]
    }
  }
}'
```

### 2. OpenSanctions - NOT YET INDEXED ⚠️
**Status:** ⏳ **CRITICAL PRIORITY** - Ready to download
- **Source:** https://opensanctions.org
- **Coverage:** ~1M entities
  - US OFAC sanctions
  - EU sanctions
  - UN sanctions
  - National watchlists (UK, Canada, etc.)
- **Format:** FTM (FollowTheMoney) entities
- **API:** Available for real-time checks
- **Use:** Real-time sanctions screening

**Implementation:**
```bash
# Download latest dataset
wget https://data.opensanctions.org/datasets/latest/default/entities.ftm.json

# Index to Elasticsearch
python3 scripts/index_opensanctions.py
```

### 3. FollowTheMoney (FTM) Datasets - NOT YET INDEXED
**Status:** ⏳ Planned
- **Source:** ICIJ/OCCRP investigations
  - Panama Papers
  - Paradise Papers
  - Pandora Papers
  - FinCEN Files
- **Coverage:** ~10M entities (companies, people, addresses)
- **Format:** FTM entities with relationships
- **Use:** Check against investigative journalism datasets

## Current Risk Indicators

### 4. Breach Records (197K records) ✅
**Index:** `nexus_breach_records`
- **Status:** ✅ Indexed (197,668 docs, 90MB)
- **Content:** Leaked credentials, emails from data breaches
- **Risk Indicators:**
  - Company email patterns in breaches
  - Compromised accounts
  - Password reuse patterns
  - Domain exposure

**Sample Query:**
```bash
# Find breached emails for domain
curl "http://localhost:9200/nexus_breach_records/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { "wildcard": { "email": "*@example.com" } }
}'
```

### 5. Domain Red Flags (in Cymonides)
Already indexed, see main Red Flags README:
- Zero backlinks (isolated domains)
- Typosquatting patterns
- Link farms
- Fake news networks

## Missing Critical Datasets

### High Priority
1. **INTERPOL Red Notices**
   - International arrest warrants
   - Not publicly bulk-downloadable (need scraping)

2. **Specially Designated Nationals (SDN)**
   - US Treasury OFAC list
   - Available as XML/CSV
   - Updates weekly

3. **EU Consolidated List**
   - EU sanctions
   - XML format
   - Regular updates

4. **UK Sanctions List**
   - HM Treasury list
   - CSV format

5. **Disqualified Directors**
   - UK Companies House
   - Directors banned from serving
   - CSV download available

### Medium Priority
1. **Adverse Media Corpus**
   - News articles about fraud, corruption
   - Could aggregate from news APIs

2. **Court Records**
   - PACER (US federal courts)
   - UK court records
   - International arbitration

3. **Regulatory Enforcement**
   - SEC enforcement actions
   - FCA (UK) enforcement
   - Other financial regulators

## Red Flag Detection Patterns

### Entity-Level Red Flags
**Data Sources:** `C-1-project-{id}`, WorldCheck, OpenSanctions
- Match against sanctions lists
- Check PEP status
- Find adverse media mentions
- Identify disqualified directors

### Domain-Level Red Flags
**Data Sources:** `cymonides_cc_domain_*`, `breach_records`
- Zero backlinks (isolation)
- Typosquatting detection
- Breached credentials
- Link farm patterns

### Content-Level Red Flags
**Data Sources:** `C-2`, FTM datasets
- Contradictory statements
- Matches to investigative datasets
- Document sanitization
- Timeline anomalies

## Implementation Priority

### Phase 1: Sanctions Screening (CRITICAL)
1. ✅ WorldCheck indexer script ready
2. ⏳ Index WorldCheck (5.4M records)
3. ⏳ Download OpenSanctions
4. ⏳ Index OpenSanctions (~1M records)
5. ⏳ Create unified screening API

### Phase 2: Enhanced Risk Data
1. ⏳ Download SDN list (weekly updates)
2. ⏳ Index EU/UK sanctions
3. ⏳ Scrape INTERPOL notices
4. ⏳ Index disqualified directors

### Phase 3: Investigative Datasets
1. ⏳ Download ICIJ FTM data
2. ⏳ Index Panama/Paradise/Pandora Papers
3. ⏳ Create entity matching pipeline

## Screening Workflow (Future)

```
Entity Input (Company/Person)
    ↓
1. Normalize name/aliases
    ↓
2. Screen: WorldCheck (PEP/Sanctions/Adverse Media)
    ↓
3. Screen: OpenSanctions (Global watchlists)
    ↓
4. Check: FTM datasets (ICIJ investigations)
    ↓
5. Check: Breach records (email exposure)
    ↓
6. Check: Disqualified directors
    ↓
7. Flag: Any matches for review
    ↓
8. Store: Risk score + evidence in C-1-project-{id}
```

## Related Documentation

- **Main Red Flags Use Case:** `../README.md`
- **Company Datasets:** `../company-profiles/DATASETS.md`
- **WorldCheck Indexer:** `python-backend/modules/brute/scripts/index_worldcheck_with_edges.py`

## Quick Start: Index WorldCheck

```bash
# 1. Verify file exists
ls -lh "/Volumes/My Book/DOWNLOADS/Free - world-check.com (10.2022).txt"

# 2. Run indexer
cd python-backend/modules/brute/scripts
python3 index_worldcheck_with_edges.py

# 3. Monitor progress
tail -f /tmp/worldcheck_1.log

# 4. Verify indexed
curl "http://localhost:9200/_cat/indices/worldcheck*?v"
```
