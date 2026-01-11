# Torpedo - Company Profile Fetcher

## What It Does

```
INPUT:  chr: Podravka d.d.
OUTPUT: { company_name, oib, mbs, status, address, employees, revenue, phone, email, ... }
```

## How To Use It

```python
from TORPEDO.torpedo import Torpedo

torpedo = Torpedo()
await torpedo.load_sources()

result = await torpedo.fetch_profile('Podravka d.d.', 'HR')
# result['profile'] contains all extracted company data
```

## Registry Operators (Frontend Syntax)

| Operator | Jurisdiction | Example |
|----------|--------------|---------|
| `csr:` | Serbia (RS) | `csr: Metal Kovin` |
| `chr:` | Croatia (HR) | `chr: Podravka d.d.` |
| `cuk:` | UK (GB) | `cuk: Tesco` |
| `cde:` | Germany (DE) | `cde: Siemens` |
| `chu:` | Hungary (HU) | `chu: OTP Bank` |
| `cfr:` | France (FR) | `cfr: Carrefour` |

## Architecture

```
User: chr: Podravka
        ↓
lociNexusParser.ts detects "chr:" → jurisdiction=HR
        ↓
Torpedo.fetch_profile("Podravka", "HR")
        ↓
1. Get source from PROFILE_SOURCE_FALLBACKS[HR]
2. Search: https://www.companywall.hr/pretraga?q=Podravka
3. Find profile URL from search results
4. Scrape profile page using experimenter.scrape()
5. Extract data using CSS recipe (output_schema)
        ↓
Return structured profile
```

## Scraping Chain

Torpedo uses the **JESTER chain** with Go crawlers:

1. **JESTER:**
   - a) **Direct HTTP** (httpx) - fastest, works for ~60% of sites
   - b) **Colly crawler** (Go) - high-performance static HTML, 500+ concurrent
   - c) **Rod crawler** (Go) - JS rendering for SPAs, ~100 concurrent browsers
2. **Firecrawl** - if JESTER fails
3. **BrightData** - if Firecrawl fails too (LAST RESORT, costs money)

## Key Files

| File | Purpose |
|------|---------|
| `BACKEND/modules/TORPEDO/torpedo.py` | Main profile fetcher |
| `BACKEND/modules/TORPEDO/experimenter.py` | Proven scraping (USE THIS) |
| `BACKEND/api/seekleech_routes.py` | `/torpedo/profile` API endpoint |
| `server/utils/lociNexusParser.ts` | Registry operator detection |
| `input_output/matrix/scrape_classification.json` | Pre-classified scrape methods |

## Adding New Jurisdictions

1. Add to `PROFILE_SOURCE_FALLBACKS` in torpedo.py:
```python
"XX": {
    "id": "registry-xx",
    "domain": "registry.xx.gov",
    "search_template": "https://registry.xx.gov/search?q={q}",
    "scrape_method": "direct",  # or "blocked" for BrightData
    "output_schema": {
        "fields": [
            {"name": "company_name", "css_selector": "h1"},
            {"name": "reg_id", "css_selector": ".reg-number"},
            # ... more fields
        ]
    }
}
```

2. Add operator to `lociNexusParser.ts`:
```typescript
cxx: { pattern: /^cxx:\s*(.+)/i, jurisdiction: "XX", name: "XX Registry" }
```

## API Endpoint

```bash
POST /api/seekleech/torpedo/profile
{
  "query": "Podravka d.d.",
  "jurisdiction": "HR"
}

Response:
{
  "success": true,
  "profile_url": "https://www.companywall.hr/tvrtka/podravka-dd/MM6XsUC",
  "scrape_method": "live",
  "profile": {
    "company_name": "PODRAVKA d.d.",
    "oib": "18928523252",
    "mbs": "010006549",
    "status": "active",
    "founded_date": "01.10.1993",
    "employees": "3258",
    "revenue": "331125165.57",
    "phone": "048651144",
    "email": "tajnistvo@podravka.hr",
    "website": "www.podravka.hr",
    "directors": "Ljiljana Šapina",
    "owners": "REPUBLIKA HRVATSKA 16,68%"
  },
  "completeness_score": 1.0
}
```

## CRITICAL RULES

1. **USE** the JESTER chain: httpx → colly → rod → Firecrawl → BrightData
2. **DO NOT** touch universal_scraper.py - it converts HTML to markdown (breaks extraction)
3. **USE** the existing scrape_classification.json - 10,000+ sources already classified
4. **CHECK** PROFILE_SOURCE_FALLBACKS first for curated sources
5. **TRUST** the pipeline: JESTER (httpx/colly/rod) → Firecrawl → BrightData
