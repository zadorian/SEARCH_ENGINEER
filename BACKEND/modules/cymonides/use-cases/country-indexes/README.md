# Country-Specific Indices

**Purpose:** Indices containing data specific to particular countries or jurisdictions

## Overview

Country-specific indices aggregate data from various sources (breaches, leaks, registries, investigations) that pertain to specific countries. These indices support:
- Regional investigations
- Jurisdiction-specific queries
- Cross-border entity tracking
- Country-specific breach analysis

---

## Kazakhstan (KZ) & Russia (RU)

### Kazaword Emails
**Index:** `kazaword_emails`
- **Status:** ✅ Indexed (92,416 docs, 225.7MB)
- **Jurisdictions:** KZ (Kazakhstan), RU (Russia)
- **Content:** Email addresses and associated metadata from Kazakh/Russian sources
- **Source:** Historical data leaks and investigations
- **Use Cases:**
  - Investigate Kazakh entities and individuals
  - Cross-reference Russian connections
  - Email-based attribution for regional actors

**Location:** `/Users/attic/01. DRILL_SEARCH/drill-search-app/cymonides/metadata/kazaword_emails/`

---

## Country Search Engines (Bangs)

### Overview

**Location:** `/Users/attic/01. DRILL_SEARCH/drill-search-app/bangs/countries/`

**Status:** ✅ **File-based** (38 country files, NOT yet indexed in Elasticsearch)

**Total:** 10,649+ global bangs + country-specific bangs

Country bangs are **DuckDuckGo-style search shortcuts** with replaceable keywords in URLs, enabling direct searches of country-specific resources.

### Structure

Each country has a `{country_code}_bangs.json` file containing:

```json
{
  "country": "ru",
  "total_bangs": 89,
  "bangs": [
    {
      "trigger": "24au",
      "url": "https://krsk.au.ru/nextauction/?search={q}",
      "site": "24au.ru",
      "domain": "krsk.au.ru",
      "category": "shopping",
      "country": "ru",
      "description": "Search 24au.ru (Online marketplace)",
      "source": "duckduckgo"
    }
  ]
}
```

### Available Countries (38 total)

| Region | Countries | Files |
|--------|-----------|-------|
| **Europe** | AT, BE, CH, CZ, DE, DK, ES, FI, FR, GR, IE, IT, NL, NO, PL, PT, RU, SE, UK | 19 files |
| **Asia-Pacific** | AU, CN, HK, IN, IL, JP, KR, NZ, SG, TH, TW | 11 files |
| **Americas** | AR, BR, CA, MX, US | 5 files |
| **Africa** | ZA | 1 file |
| **Middle East** | TR | 1 file |
| **Global** | global_bangs.json (10,649 cross-country bangs) | 1 file |

### Example Country Bangs

**Russia (RU) - 89 bangs:**
- Shopping, news, government, business directories
- Corporate registries, auction sites
- Regional search engines

**Kazakhstan (KZ) - TBD:**
- Status: Not yet extracted (would go in `kz_bangs.json`)
- Expected: Government portals, company registries, news

**United States (US) - 4,358,891 bytes:**
- Largest bang collection
- Federal/state resources, court records, business registries

**Germany (DE) - 308,031 bytes:**
- Second largest collection
- Federal resources, Unternehmensregister, regional databases

### Usage

Bangs enable **parameterized URL construction** for country-specific searches:

```python
# Example: Search Russian marketplace
bang = bangs['ru']['24au']
query = "laptop"
url = bang['url'].replace('{q}', query)
# https://krsk.au.ru/nextauction/?search=laptop
```

### Integration with Country Engines

**Module:** `python-backend/modules/country_engines/`

Country-specific APIs and scrapers:
- **Austria (AT):** Firmenabc ingest (93,968 bytes)
- **Belgium/Uruguay:** Combined APIs (20,110 bytes)
- **Denmark:** Virk API (2,549 bytes)
- **Finland:** PRH API (2,288 bytes)
- **France:** Sirene API (3,045 bytes)
- **Germany:** Unternehmensregister API (17,367 bytes)
- **Ireland:** CRO API (1,455 bytes)
- **Netherlands:** KVK API (1,897 bytes)
- **Norway:** Brreg API (2,248 bytes)
- **Sweden:** Verksamt API (2,070 bytes)
- **Switzerland:** Zefix API (1,551 bytes)

**Hidden APIs:** `hidden_apis.json` (16,635 bytes)
- Additional country-specific data sources
- Corporate registries, government databases

### Bang Categories

Common categories across all countries:
- **Business:** Corporate registries, company databases
- **Government:** Official portals, legislation, regulations
- **News:** Local news sites, media outlets
- **Shopping:** E-commerce, marketplaces
- **Social:** Social media, forums
- **Search:** Regional search engines

### Sample Queries

#### Find Kazakh Government Emails
```bash
curl "http://localhost:9200/kazaword_emails/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": {
    "wildcard": { "email": "*@gov.kz" }
  },
  "size": 100
}'
```

#### Search by Domain
```bash
curl "http://localhost:9200/kazaword_emails/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": {
    "wildcard": { "email": "*@kazatomprom.kz" }
  }
}'
```

#### Email Pattern Analysis
```bash
curl "http://localhost:9200/kazaword_emails/_search" \
  -H 'Content-Type: application/json' -d '{
  "size": 0,
  "aggs": {
    "domains": {
      "terms": {
        "script": "doc[\"email.keyword\"].value.substring(doc[\"email.keyword\"].value.indexOf(\"@\") + 1)",
        "size": 50
      }
    }
  }
}'
```

---

## Integration with Other Use Cases

### Company Profiles
**Cross-Reference:**
1. Find company domain from company-profiles
2. Query kazaword_emails: `*@company.kz`
3. Identify associated email accounts
4. Link to entity graphs in C-1

### Red Flags
**Indicators:**
- Kazakh emails in international breaches → exposure risk
- Government emails in non-official contexts → potential corruption
- Pattern matching for shell companies (shared email domains)

### Data Breaches
**Cross-Reference:**
1. Query kazaword_emails for entity
2. Check nexus_breach_records for password exposure
3. Assess credential compromise risk

---

## Data Structure

### Kazaword Email Document
```json
{
  "_id": "email_record_id",
  "email": "user@example.kz",
  "domain": "example.kz",
  "source": "kazaword_dataset",
  "jurisdiction": ["KZ", "RU"],
  "metadata": {
    "discovered_at": "2024-01-01T00:00:00Z",
    "verification_status": "unverified"
  }
}
```

---

## Future Country Indices

### Planned Expansions:
1. **Uzbekistan (UZ)** - Central Asian investigations
2. **Kyrgyzstan (KG)** - Regional connectivity
3. **Turkmenistan (TM)** - Energy sector focus
4. **Ukraine (UA)** - Post-Soviet transitions
5. **Azerbaijan (AZ)** - Caspian region

### Naming Convention:
- Pattern: `{country_code}_{data_type}`
- Examples: `uz_companies`, `kg_emails`, `ua_breach_records`

---

## Workflow: Regional Investigation

```
1. Input: Entity name or company (Kazakh)
2. Search: kazaword_emails for email addresses
3. Pivot: Email → nexus_breach_records (password exposure)
4. Enrich: Email domain → cymonides_cc_domain_edges (backlinks)
5. Map: Create entity graph in C-1 for project
6. Profile: Compile in company-profiles use case
```

---

## Related Documentation

- **Data Breaches:** `../data-breaches/README.md` (email in breaches)
- **Company Profiles:** `../company-profiles/README.md` (entity enrichment)
- **Red Flags:** `../red-flags/README.md` (anomaly detection)

---

## Performance Notes

- **Email lookups:** Fast (keyword match on 92K docs)
- **Domain aggregations:** Use scripting for @ parsing
- **Wildcard queries:** Efficient with .keyword fields

---

## Metadata Location

`/Users/attic/01. DRILL_SEARCH/drill-search-app/cymonides/metadata/kazaword_emails/metadata.json`
