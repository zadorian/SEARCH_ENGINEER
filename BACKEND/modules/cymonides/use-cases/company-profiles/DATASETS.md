# Company Profile Datasets

Complete inventory of company-related datasets available for enrichment and analysis.

## Elasticsearch Indices

### 1. LinkedIn Companies (2.85M companies)
**Index:** `affiliate_linkedin_companies`
- **Status:** ✅ Indexed (2,851,571 docs, 705MB)
- **Source:** LinkedIn company dataset (4.8GB CSV)
- **Fields:** `company_name`, `domain`, `website_url`, `linkedin_url`, `industry`
- **Location (CSV):** `python-backend/datasets/linkedin-company-dataset.csv` (archived to Google Drive)
- **Use:** Domain → Company name/industry lookup, LinkedIn URL enrichment

**Sample Query:**
```bash
# Find company by domain
curl "http://localhost:9200/affiliate_linkedin_companies/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { "term": { "domain": "example.com" } }
}'
```

### 2. Company Profiles Index (496 companies)
**Index:** `company_profiles`
- **Status:** ✅ Indexed (496 docs, 312KB)
- **Fields:** `company_name`, `domain`, `country`, `industry`, `linkedin_url`, `content`, `source_flags`
- **Use:** Enriched company profiles with additional context

### 3. Report Library (45K documents)
**Index:** `C-2` (source_type: "report")
- **Status:** ✅ Indexed (45,030 docs in C-2)
- **Location:** `cymonides/metadata/C-2/sources/reports/`
- **Content:** PDFs, Word docs, investigative reports uploaded to system
- **Use:** Full-text search for companies mentioned in reports

**Sample Query:**
```bash
# Find all reports mentioning a company
curl "http://localhost:9200/C-2/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": {
    "bool": {
      "must": [
        { "term": { "source_type": "report" } },
        { "match": { "content": "Acme Corporation" } }
      ]
    }
  }
}'
```

## Red Flag / Sanctions Datasets

### 4. WorldCheck (5.4M records)
**Index:** NOT YET INDEXED (planned)
- **Status:** ⏳ File available, indexer script ready
- **Source File:** `/Volumes/My Book/DOWNLOADS/Free - world-check.com (10.2022).txt`
- **Size:** ~5.4M records (PEPs, sanctions, adverse media)
- **Indexer:** `python-backend/modules/brute/scripts/index_worldcheck_with_edges.py`
- **Target:** Graph storage (PostgreSQL) + Elasticsearch
- **Use:** Check companies/individuals against sanctions, PEPs, adverse media

**Fields (when indexed):**
- Entity name, aliases, countries
- Categories (PEP, Sanctions, Adverse Media)
- Relationships, sources

### 5. OpenSanctions
**Index:** NOT YET INDEXED
- **Status:** ⏳ Planned
- **Source:** https://opensanctions.org (API/bulk download)
- **Coverage:** Global sanctions lists, PEPs, criminal watchlists
- **Use:** Real-time sanctions screening

### 6. FollowTheMoney (FTM)
**Index:** NOT YET INDEXED
- **Status:** ⏳ Planned
- **Source:** OCCRP/ICIJ datasets
- **Format:** FTM entities (structured)
- **Use:** Investigative journalism datasets (Panama Papers, etc.)

## Other Company Datasets

### 7. Breach Records (197K records)
**Index:** `nexus_breach_records`
- **Status:** ✅ Indexed (197,668 docs, 90MB)
- **Content:** Leaked credentials, emails from data breaches
- **Use:** Find company email patterns, leaked data

### 8. Domain Profiles (5.8M domains)
**Index:** `unified_domain_profiles`
- **Status:** ✅ Indexed (5,851,357 docs, 885MB)
- **Content:** Aggregated domain intelligence
- **Use:** Domain-to-company mapping, domain metadata

### 9. Top Domains (8.6M domains)
**Index:** `top_domains`
- **Status:** ✅ Indexed (8,671,244 docs, 1.5GB)
- **Content:** Ranked domains by various metrics
- **Use:** Authority scoring, domain importance

## Dataset Status Summary

| Dataset | Status | Docs | Size | Priority |
|---------|--------|------|------|----------|
| LinkedIn Companies | ✅ Indexed | 2.85M | 705MB | HIGH |
| Report Library | ✅ Indexed | 45K | In C-2 | HIGH |
| Company Profiles | ✅ Indexed | 496 | 312KB | MEDIUM |
| Domain Profiles | ✅ Indexed | 5.8M | 885MB | HIGH |
| Top Domains | ✅ Indexed | 8.6M | 1.5GB | MEDIUM |
| Breach Records | ✅ Indexed | 197K | 90MB | MEDIUM |
| **WorldCheck** | ⏳ Pending | 5.4M | N/A | **CRITICAL** |
| **OpenSanctions** | ⏳ Pending | ~1M | N/A | **CRITICAL** |
| **FTM Datasets** | ⏳ Pending | ~10M | N/A | HIGH |

## Integration Workflows

### Complete Company Profile Assembly
```
1. Start with: Company Name or Domain
2. Lookup: LinkedIn Companies (affiliate_linkedin_companies)
3. Enrich: Domain Profiles (unified_domain_profiles)
4. Check: WorldCheck/OpenSanctions (when indexed)
5. Search: Report Library (C-2, source_type:report)
6. Find: Breach Records (nexus_breach_records)
7. Store: Cymonides-1-project-{id} (entity storage)
```

### Red Flag Screening
```
1. Extract: Company name, officers, domains
2. Screen: WorldCheck (PEPs, sanctions)
3. Screen: OpenSanctions (watchlists)
4. Cross-ref: FTM datasets (ICIJ investigations)
5. Check: Breach records (leaked data)
6. Flag: Matches for manual review
```

## Missing Datasets (Suggestions)

Based on common investigative needs:

1. **Corporate Registry Dumps**
   - UK Companies House (12M+ companies)
   - OpenCorporates API data
   - EU Business Register

2. **Financial Data**
   - Orbis company financials
   - SEC EDGAR filings
   - Annual reports corpus

3. **News & Media**
   - Factiva archives
   - News API aggregations
   - Press release databases

4. **Social Media**
   - Company LinkedIn profiles (full data)
   - Twitter/X company accounts
   - Facebook business pages

5. **Legal Records**
   - Court cases mentioning companies
   - Litigation databases
   - Regulatory enforcement actions

## Implementation Notes

### Indexing WorldCheck (Priority)
```bash
# Run the indexer (creates ~5.4M records)
cd python-backend/modules/brute/scripts
python3 index_worldcheck_with_edges.py

# Monitor progress
tail -f /tmp/worldcheck_1.log
```

### LinkedIn CSV Management
- ✅ Original CSV (4.8GB) archived to Google Drive
- ✅ Data fully indexed in `affiliate_linkedin_companies`
- Can safely delete local CSV if needed

### Report Library Location
All uploaded reports are in `C-2` with:
- `source_type: "report"`
- Full-text indexed
- Can filter by project_id if needed

## Related Documentation

- **Use Case:** `../README.md` (Company Profiles workflow)
- **Index Metadata:** `../../metadata/affiliate_linkedin_companies/metadata.json`
- **Cymonides-2 Sources:** `../../metadata/C-2/SOURCES_README.md`
- **Red Flags:** `../red-flags/README.md`
