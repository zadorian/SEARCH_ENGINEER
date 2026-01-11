# EYE-D Web App - API Analysis

**Location:** `/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/EYE-D/web`

**Last Modified:** Nov 11, 2025 18:00

**Technology Stack:** Flask, Python, SQL (SQLite)

---

## Database Files

1. **search_graph.db** - Main graph database
2. **cache/projects.db** - Project management cache

---

## Integrated APIs & Services

### 1. **DeHashed API** (Breach Data)

- **File:** Main search in `server.py`
- **Endpoint:** `/api/search`
- **API URL:** `https://api.dehashed.com/v2/search`
- **Authentication:** `DEHASHED_API_KEY` (environment variable)
- **Purpose:** Search data breach records

**Inputs:**

- `query` (string) - Search term
- `type` (string, optional) - Query type: email, username, phone, domain, name, ip_address, password, hashed_password, database_name, blanket_search
- `size` (int, default: 100) - Results per page
- `page` (int, default: 1) - Page number

**Auto-detection patterns:**

- Email: Contains `@`
- Phone: Matches `^\+?\d[\d\s\-\(\)\.]{6,}$`
- Domain: Matches `^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$`
- IP: Matches `^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$`
- MD5 hash: 32 hex chars
- SHA1 hash: 40 hex chars
- SHA256 hash: 64 hex chars

**Outputs:**

```json
{
  "results": [...],
  "total": 1234,
  "balance": "N/A",
  "query": "example@email.com",
  "query_type": "email"
}
```

**Result fields:**

- `email`, `username`, `password`, `hashed_password`
- `name`, `phone`, `address`, `ip_address`
- `database_name`, `breach_date`

---

### 2. **OSINT Industries** (Social Media OSINT)

- **File:** `osintindustries.py`
- **Endpoint:** `/api/osint`
- **API:** OSINT Industries (hardcoded key in file: `518cf12a370e9e42dde7516098621889`)
- **Purpose:** Search social media profiles, breach data, and OSINT sources

**Inputs:**

- `query` (string) - Email or phone number
- `type` (string) - `email` or `phone`

**Outputs:**

```json
{
  "query": "example@email.com",
  "query_type": "email",
  "entities": [...],  // Claude-extracted entities
  "raw_results": [...],
  "source": "osint"
}
```

**Result fields (OSINTResult dataclass):**

- **Identity:** `name`, `first_name`, `last_name`, `username`, `gender`, `age`, `language`
- **Contact:** `email`, `phone`, `email_hint`, `phone_hint`
- **Profiles:** `profile_url`, `picture_url`, `banner_url`, `website`, `bio`
- **Social:** `followers`, `following`, `verified`, `premium`, `private`
- **Dates:** `creation_date`, `last_seen`, `last_updated`
- **Breach:** `breached`, `breach_info` (name, date, pwn_count, data_classes, description)
- **Location:** `location`, `addresses`, `ip_addresses`
- **Social Profiles:** List of `{platform, url, username, categories}`

**Modules searched:**

- Email: gmail, outlook, microsoft, apple, linkedin, twitter, facebook, instagram, etc.
- Phone: Multiple phone lookup services
- Country code support: 40+ countries

---

### 3. **WhoisXMLAPI** (Domain Intelligence)

- **File:** `whois.py`
- **Endpoint:** `/api/whois`
- **API:** WhoisXMLAPI (hardcoded key: `at_7uD0skEoBXIy7jn5LXSzgTFxsPmfd`)
- **Purpose:** Domain WHOIS lookups, reverse WHOIS, domain history

**Inputs:**

- `query` (string) - Domain, email, phone, or name
- `type` (string) - `domain`, `email`, `phone`, `terms`

**Functions:**

1. **whois_lookup()** - Get WHOIS history for domain
2. **reverse_whois_search()** - Find domains by registrant info
3. **get_whois_history()** - Historical WHOIS records

**Outputs:**

```json
{
  "query": "example.com",
  "query_type": "domain",
  "records": [...],
  "count": 5
}
```

**Record fields:**

- **Registrant:** `registrantName`, `registrantOrganization`, `registrantEmail`, `registrantPhone`
- **Admin:** `administrativeContactName`, `administrativeContactEmail`
- **Technical:** `technicalContactName`, `technicalContactEmail`
- **Registrar:** `registrarName`, `registrarIANAID`
- **Dates:** `createdDate`, `updatedDate`, `expiresDate`
- **DNS:** `nameServers`, `domainName`, `status`

**Rate limiting:** Exponential backoff on 429 errors (2s, 4s, 6s...)

---

### 4. **OpenCorporates** (Company Registry)

- **File:** `opencorporates.py`
- **Endpoint:** `/api/opencorporates/search`
- **API URL:** `https://api.opencorporates.com/v0.4`
- **Authentication:** `OPENCORPORATES_API_KEY` (environment variable, optional)
- **Purpose:** Search company registrations, officers, directors

**Inputs:**

- `query` (string) - Company or officer name
- `search_type` (string) - `company` or `officer`
- `jurisdiction` (string, optional) - Jurisdiction code (e.g., `us_ca`, `gb`)

**Functions:**

1. **search_companies()** - Search company names
2. **search_officers()** - Search officers/directors
3. **get_company_details()** - Get detailed company info
4. **get_officer_details()** - Get detailed officer info
5. **get_jurisdictions()** - List available jurisdictions

**Outputs (companies):**

```json
{
  "name": "ACME Corp",
  "jurisdiction": "US_CA",
  "company_number": "C1234567",
  "status": "Active",
  "incorporation_date": "2010-01-01",
  "type": "company",
  "source": "opencorporates",
  "url": "https://opencorporates.com/...",
  "address": "123 Main St, City, State, ZIP",
  "officers": [...]
}
```

**Note:** Free tier has rate limits, paid tier recommended for heavy use

---

### 5. **OCCRP Aleph** (Investigative Data)

- **File:** `occrp_aleph.py`
- **Endpoint:** `/api/aleph/search`
- **API URL:** `https://aleph.occrp.org/api/2`
- **Authentication:** `ALEPH_API_KEY` (environment variable)
- **Purpose:** Search leaks, investigations, government records

**Inputs:**

- `query` (string) - Search query (supports exact phrases with quotes)
- `max_results` (int, default: 100) - Maximum results
- `schemas` (list, optional) - Entity types to search

**Special query formats:**

- `"exact phrase"` - Exact phrase search (preserves quotes)
- `intitle:keyword` - Search in document titles only
- `intitle:"exact title"` - Exact title match

**Outputs:**

```json
{
  "results": [
    {
      "title": "Document title",
      "url": "https://aleph.occrp.org/...",
      "snippet": "Preview text...",
      "schema": "Document",
      "collection": "Panama Papers",
      "score": 0.95
    }
  ],
  "total": 42,
  "query": "example corp"
}
```

**Entity schemas:**

- Person, Company, Organization
- Document, Email, Webpage
- BankAccount, Payment, Contract
- And many more...

---

### 6. **Google Custom Search API**

- **File:** `server.py` (GoogleSearch class)
- **Endpoint:** `/api/google/search`
- **API URL:** `https://www.googleapis.com/customsearch/v1`
- **Authentication:** `GOOGLE_API_KEY` + `GOOGLE_SEARCH_ENGINE_ID`
- **Purpose:** Web search, site-specific search

**Inputs:**

- `query` (string) - Search query
- `max_results` (int, default: 10) - Results to fetch

**Outputs:**

```json
{
  "results": [
    {
      "url": "https://example.com",
      "title": "Page title",
      "snippet": "Description preview",
      "found_by_query": "search query"
    }
  ],
  "estimated_count": 12345
}
```

**Limits:**

- 10 results per API request
- Max 100 results total per query
- Daily quota applies

---

### 7. **Firecrawl** (Web Scraping)

- **Configuration:** `FIRECRAWL_API_KEY`, `FIRECRAWL_API_URL`
- **API URL:** `https://api.firecrawl.dev/v1/scrape`
- **Purpose:** Extract clean content from web pages

**Usage:** Used internally for content extraction from URLs

---

### 8. **Anthropic Claude** (AI Processing)

- **Configuration:** `ANTHROPIC_API_KEY`
- **Endpoints:** `/api/ai-suggestions`, `/api/ai-chat`, `/api/vision`
- **Purpose:** Entity extraction, data cleaning, chat interface

**Functions:**

1. **Entity Extraction** - Extract people, companies, emails, phones, addresses from text
2. **Data Cleaning** - Clean and normalize addresses, names, etc.
3. **AI Chat** - Conversational interface for queries
4. **Vision Analysis** - Image/screenshot analysis

**Entity Extraction Input:**

- `text` (string) - Text to analyze
- Source: OSINT results, WHOIS data, web scraping

**Entity Extraction Output:**

```json
{
  "people": ["John Smith", "Jane Doe"],
  "companies": ["ACME Corp", "XYZ Inc"],
  "emails": ["contact@example.com"],
  "phones": ["+1-555-0100"],
  "addresses": ["123 Main St, City, State"],
  "locations": ["New York", "London"],
  "misc": ["Other entities"]
}
```

---

### 9. **Ahrefs** (Backlinks)

- **Endpoint:** `/api/ahrefs/backlinks`
- **Purpose:** Get backlinks for a domain (if API key available)

---

### 10. **Screenshot Service**

- **Endpoint:** `/api/screenshot/capture`
- **Purpose:** Capture screenshots of web pages

---

### 11. **Unified Corporate Search**

- **Endpoint:** `/api/corporate/unified`
- **Purpose:** Search across OpenCorporates + Aleph simultaneously
- **Combines:** Company registrations + investigative records

**Inputs:**

- `query` (string) - Company name
- `jurisdiction` (string, optional) - Jurisdiction filter

**Outputs:** Merged results from both sources with unified format

---

## Additional Features

### Project Management

- **Endpoint:** `/api/projects`
- **Methods:** GET, POST, DELETE
- **Database:** `cache/projects.db`
- **Purpose:** Organize investigations into projects

### Graph Database

- **Database:** `search_graph.db`
- **Purpose:** Store entities and relationships
- **Sync:** Bidirectional sync with Search_Engineer (SE) grid

### Entity Extraction from URLs

- **Endpoint:** `/api/url/extract-entities`
- **Purpose:** Scrape URL and extract entities with Claude

### Entity Extraction from Files

- **Endpoint:** `/api/file/extract-entities`
- **Supported:** PDF, DOCX, TXT, CSV
- **Purpose:** Extract entities from uploaded documents

### Outlink Extraction

- **Endpoint:** `/api/url/outlinks`
- **Purpose:** Extract all outbound links from a URL

### Exhaustive Search

- **Module:** `ExactPhraseRecallRunner`
- **Purpose:** Comprehensive search across multiple engines with exact phrase matching
- **Chunking:** Processes large site lists in chunks

---

## Data Flow Summary

### 1. **Person Search Flow**

```
User Input → Auto-detect type → Multiple APIs
  ↓
  ├─ DeHashed (breach data)
  ├─ OSINT Industries (social profiles)
  ├─ WhoisXML (if email domain)
  └─ Claude (entity extraction & consolidation)
  ↓
Unified Result → Graph Database → Frontend Display
```

### 2. **Company Search Flow**

```
User Input → Company name
  ↓
  ├─ OpenCorporates (official registration)
  ├─ Aleph (investigations/leaks)
  ├─ Google (web presence)
  └─ WHOIS (domain ownership)
  ↓
Unified Result → Entity Graph → Related Officers/Addresses
```

### 3. **Domain Search Flow**

```
User Input → Domain name
  ↓
  ├─ WHOIS History (registration records)
  ├─ Reverse WHOIS (related domains)
  ├─ Google (site search)
  └─ Outlinks (connected sites)
  ↓
Timeline View → Registrant History → Entity Graph
```

---

## Input Types & Auto-Detection

| Input Pattern                      | Detected As | APIs Used                                   |
| ---------------------------------- | ----------- | ------------------------------------------- |
| `john@example.com`                 | Email       | DeHashed, OSINT Industries, WHOIS (reverse) |
| `+1-555-0100`                      | Phone       | DeHashed, OSINT Industries, WHOIS (reverse) |
| `example.com`                      | Domain      | WHOIS, Google, Reverse WHOIS                |
| `192.168.1.1`                      | IP Address  | DeHashed                                    |
| `John Smith`                       | Name        | DeHashed, WHOIS (reverse), OpenCorporates   |
| `ACME Corp`                        | Company     | OpenCorporates, Aleph, Google               |
| `5d41402abc4b2a76b9719d911017c592` | MD5 Hash    | DeHashed                                    |
| `username123`                      | Username    | DeHashed, OSINT Industries                  |

---

## Output Format

### Unified Entity Result

```json
{
  "entity_type": "person|company|domain",
  "primary_identifier": "john@example.com",
  "names": ["John Smith", "J. Smith"],
  "emails": ["john@example.com"],
  "phones": ["+1-555-0100"],
  "addresses": ["123 Main St, City, State"],
  "social_profiles": [
    {
      "platform": "linkedin",
      "url": "https://linkedin.com/in/johnsmith",
      "username": "johnsmith"
    }
  ],
  "breaches": [
    {
      "database": "LinkedInBreach2021",
      "date": "2021-06-01",
      "exposed_fields": ["email", "password_hash"]
    }
  ],
  "companies": [
    {
      "name": "ACME Corp",
      "role": "CEO",
      "jurisdiction": "US_CA"
    }
  ],
  "domains": ["example.com", "personal-site.com"],
  "metadata": {
    "sources": ["dehashed", "osint_industries", "whois"],
    "confidence": 0.95,
    "last_updated": "2025-11-11T18:00:00Z"
  }
}
```

---

## API Keys Required

1. **DEHASHED_API_KEY** - DeHashed API
2. **OSINT_API_KEY** - OSINT Industries (hardcoded in file)
3. **WHOISXMLAPI_KEY** - WhoisXMLAPI (hardcoded in file)
4. **OPENCORPORATES_API_KEY** - OpenCorporates (optional)
5. **ALEPH_API_KEY** - OCCRP Aleph
6. **GOOGLE_API_KEY** - Google Custom Search
7. **GOOGLE_SEARCH_ENGINE_ID** - Google CSE ID
8. **FIRECRAWL_API_KEY** - Firecrawl scraping
9. **ANTHROPIC_API_KEY** - Claude AI

All stored in `.env` file (except hardcoded ones in `osintindustries.py` and `whois.py`)

---

## Frontend Integration

**Frontend Location:** `web/` directory (HTML/JS/CSS)

**Backend Server:** Flask on port 5000 (default)

**CORS:** Restricted to localhost origins:

- `http://localhost:5000` (EYE-D)
- `http://localhost:5173` (WIKIMAN-PRO)
- `http://localhost:8002` (Search Engineer)

---

## Key Files Reference

```
web/
├── server.py                      # Main Flask server (135KB, 3097 lines)
├── osintindustries.py             # OSINT Industries client (43KB)
├── opencorporates.py              # OpenCorporates client (15KB)
├── occrp_aleph.py                 # Aleph searcher (38KB)
├── whois.py                       # WhoisXML client (24KB)
├── projects.py                    # Project management (7KB)
├── exact_phrase_recall_runner.py  # Exhaustive search (20KB)
├── search_graph.db                # Main graph database
├── cache/projects.db              # Project cache
└── .env                           # API keys configuration
```

---

**Analysis Date:** 2025-11-12
**Document Version:** 1.0
