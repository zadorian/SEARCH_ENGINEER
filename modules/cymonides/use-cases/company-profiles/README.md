# Company Profiles Use Case

**Purpose:** Complete company intelligence - ownership, officers, financials, public records

## Indices Used

> **📊 See [DATASETS.md](DATASETS.md) for complete inventory of all company datasets (LinkedIn, WorldCheck, OpenSanctions, breach records, etc.)**

### Primary Entity Storage
- **`cymonides-1-project-{id}`** 
  - Location: `../metadata/cymonides-1-project-*/`
  - Purpose: Structured company entities with relationships
  - Fields: name, country, registration_number, officers, shareholders
  
### Enrichment Data
- **`cymonides_source_enrichments`**
  - Location: `../metadata/cymonides_source_enrichments/`
  - Purpose: Domain-level enrichment (CC coverage, API endpoints)
  - Used for: Website analysis, technical footprint

- **`cymonides_source_entities`**
  - Location: `../metadata/cymonides_source_entities/`
  - Purpose: Entity extraction results from web scraping
  - Fields: name, entity_type, snippet, page_url, domain

### Text Corpus (Supporting Evidence)
- **`cymonides-2`** (filtered by project)
  - Location: `../metadata/cymonides-2/`
  - Purpose: Full-text documents mentioning the company
  - Query: `project_ids:{PROJECT_ID} AND content:"Company Name"`

### LinkedIn Enrichment
- **`affiliate_linkedin_companies`** (2.85M companies)
  - Location: `../../metadata/` (needs metadata export)
  - Purpose: Domain → Company name, industry, LinkedIn URL
  - Fields: company_name, domain, website_url, linkedin_url, industry
  - Used for: Instant company identification from domain

### Other Company Datasets
- **`company_profiles`** (496 companies)
  - Enriched company profiles with additional context

- **`unified_domain_profiles`** (5.8M domains)
  - Aggregated domain intelligence

- **`nexus_breach_records`** (197K records)
  - Leaked credentials, email patterns from breaches

### Link Graph (Network Analysis)
- **`cymonides_cc_domain_vertices`**
  - Location: `../metadata/cymonides_cc_domain_vertices/`
  - Purpose: Company website domain vertex in link graph
  - Used for: Connectivity ranking, authority scoring

- **`cymonides_cc_domain_edges`**
  - Location: `../metadata/cymonides_cc_domain_edges/`
  - Purpose: Inbound/outbound links to company domain
  - Used for: Related entities, network mapping

## Typical Workflow

1. **Entity Creation** → `cymonides-1-project-{id}`
2. **Domain Enrichment** → `cymonides_source_enrichments` (CC coverage, APIs)
3. **Web Scraping** → `cymonides_source_entities` (extract entities from company site)
4. **Document Collection** → `cymonides-2` (reports, news, filings about company)
5. **Network Analysis** → `cymonides_cc_domain_*` (who links to/from company)

## Example Queries

### Get company entity
```bash
curl "http://localhost:9200/cymonides-1-project-ge13t70tq8v0hw0h994z1v64/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { "term": { "name.keyword": "Acme Corp" } }
}'
```

### Get all documents about company
```bash
curl "http://localhost:9200/cymonides-2/_search?q=content:\"Acme Corp\"&size=100"
```

### Get domain enrichment
```bash
curl "http://localhost:9200/cymonides_source_enrichments/_doc/acme_corp_com"
```

### Find related domains (inbound links)
```bash
curl "http://localhost:9200/cymonides_cc_domain_edges/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { "term": { "target_domain": "acme-corp.com" } },
  "size": 100
}'
```

## Data Flow

```
Company Name → Corporella/OpenCorporates API → cymonides-1-project-{id}
                                              ↓
Company Domain → Web Scraping → cymonides_source_entities
                              ↓
                Domain Drill → cymonides_source_enrichments
                              ↓
              Document Upload → cymonides-2 (tagged with project_id)
                              ↓
          Link Graph Lookup → cymonides_cc_domain_* (network context)
```

## Related Modules

- **Corporella** (`python-backend/modules/corporella/`) - Company data fetching
- **AllDom** (`python-backend/modules/alldom/`) - Domain intelligence
- **LinkLater** (`python-backend/modules/linklater/`) - Web scraping & extraction
- **Entity Resolution** (`server/services/entityResolutionService.ts`) - Deduplication

## Cross-Reference

This use case overlaps with:
- **`domains-list`** (for domain-centric queries)
- **`red-flags`** (for risk indicators in company profiles)
