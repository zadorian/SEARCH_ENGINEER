# UK Public Records MCP Server

Comprehensive MCP server for UK official data sources based on the uk_cli consolidated toolkit.

## Features

### 1. **UK Land Registry** (CCOD/OCOD)

Search corporate and overseas property ownership records:

- 🏢 Company-owned properties
- 📍 Postcode-based searches
- 🗺️ Address lookups
- 📊 Full-text search across all fields

### 2. **FCA National Storage Mechanism**

Access UK regulatory filings:

- 📑 Company prospectuses
- 📈 Annual reports
- 🏦 IPO documents
- 📋 Regulatory disclosures

### 3. **Aleph (OCCRP) UK Collections**

Investigative databases including:

- 🚫 Disqualified Directors (Companies House)
- 🏛️ Parliamentary Register of Interests
- ⚖️ UK Court Records
- 💼 Pandora Papers UK entities
- 🏝️ Paradise Papers UK entities
- 🏠 Land Registry data

### 4. **Companies House API** (Status Check)

- ✅ API key validation
- 📊 Integration status

## Available Tools

### 1. `search_uk_land_registry`

Search Land Registry CCOD dataset by postcode, owner, address, or general query.

**Parameters:**

- `query` (optional): Full-text search
- `postcode` (optional): UK postcode filter
- `owner` (optional): Owner/proprietor name
- `address` (optional): Property address
- `limit` (default: 50): Max results
- `csv_path` (optional): Custom CSV path

**Example:**

```json
{
  "owner": "British Land",
  "postcode": "SW1",
  "limit": 100
}
```

### 2. `search_uk_land_registry_by_company`

Specialized search for all properties owned by a company.

**Parameters:**

- `company_name` (required): Company name
- `limit` (default: 100): Max properties

### 3. `search_uk_land_registry_by_postcode`

Search all properties in a UK postcode area.

**Parameters:**

- `postcode` (required): UK postcode/area (e.g., "SW1A 1AA", "EC2")
- `limit` (default: 100): Max results

### 4. `search_fca_documents`

Search FCA NSM for company filings and prospectuses.

**Parameters:**

- `keyword` (required): Company name or search term
- `limit` (default: 50, max: 100): Max documents

**Example:**

```json
{
  "keyword": "Barclays",
  "limit": 20
}
```

### 5. `search_aleph_uk`

Search Aleph UK collections for entities in leaked docs, court records, and watchlists.

**Parameters:**

- `query` (required): Entity name (person or company)
- `limit` (default: 50): Max results
- `collections` (optional): Specific collections to search

**Available Collections:**

- `uk_coh_disqualified` - Disqualified Directors
- `uk_land_registry` - Land Registry
- `uk_parliament` - Parliamentary Interests
- `uk_courts` - Court Records
- `pandora_papers_uk` - Pandora Papers
- `paradise_papers_uk` - Paradise Papers

**Example:**

```json
{
  "query": "John Smith",
  "limit": 30,
  "collections": ["uk_coh_disqualified", "pandora_papers_uk"]
}
```

### 6. `search_uk_comprehensive`

Search ALL UK sources in parallel for maximum coverage.

**Parameters:**

- `entity_name` (required): Company or person name
- `limit_per_source` (default: 20): Results per source

**Returns unified results from:**

- Land Registry
- FCA NSM
- Aleph Collections

**Example:**

```json
{
  "entity_name": "Acme Holdings Ltd",
  "limit_per_source": 25
}
```

### 7. `uk_data_sources_status`

Check availability and configuration status of all UK data sources.

**Parameters:**

- `category` (optional): Filter by category

**Categories:**

- Property
- Corporate
- Transparency
- Regulator
- Courts

## Environment Configuration

### Required

```bash
# Land Registry CSV (auto-detected if in standard location)
export UK_LAND_REGISTRY_CSV="/path/to/CCOD_FULL_2025_08.csv"
```

### Optional

```bash
# Companies House API (for status check)
export COMPANIES_HOUSE_API_KEY="your-key"
# OR
export CH_API_KEY="your-key"
```

## Default Paths

**Land Registry CSV:**

```
/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/Search-Engineer.02/iv. LOCATION/a. KNOWN_UNKNOWN/SOURCE_CATEGORY/PUBLIC-RECORDS/LOCAL/LAND_REGISTRY/LAND_UK/CCOD_FULL_2025_08.csv
```

Set `UK_LAND_REGISTRY_CSV` to override.

## Running the Server

```bash
python uk_public_records_mcp.py
```

The server communicates via stdio following the MCP protocol.

## Integration with Claude Desktop

Add to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "uk-public-records": {
      "command": "python",
      "args": ["/path/to/uk_public_records_mcp.py"],
      "env": {
        "UK_LAND_REGISTRY_CSV": "/path/to/CCOD_FULL_2025_08.csv",
        "COMPANIES_HOUSE_API_KEY": "your-key"
      }
    }
  }
}
```

## Data Sources

### Live APIs (Always Available)

- ✅ **FCA NSM**: `https://www.fca.org.uk/api/national-storage-mechanism/search`
- ✅ **Aleph**: `https://aleph.occrp.org/api/2`

### Local Data (Requires CSV)

- 📁 **Land Registry CCOD**: Corporate ownership dataset
- 📁 **Land Registry OCOD**: Overseas ownership dataset (optional)

### Future Integration

- ⏳ **Companies House API**: Full profile/PSC/officers lookup
- ⏳ **WhatDoTheyKnow**: FOI requests archive
- ⏳ **UK Courts**: BAILII/Registry Trust (requires paid access)

## Performance

- **Land Registry**: Local CSV search, very fast
- **FCA NSM**: REST API, ~1-2 seconds
- **Aleph**: REST API with multiple collections, ~2-5 seconds
- **Comprehensive Search**: Parallel execution, ~3-6 seconds total

## Based On

- `uk_cli.py` - Consolidated UK data toolkit
- `uk_fca_nsm_subs.py` - FCA NSM search implementation
- `uk_adapters.py` - Adapter patterns for UK sources
- Aleph OCCRP UK collections

## Use Cases

### 1. Corporate Due Diligence

```
search_uk_comprehensive("ABC Limited")
```

Returns properties, filings, and watchlist hits.

### 2. Property Portfolio Analysis

```
search_uk_land_registry_by_company("British Land")
```

All properties owned by company.

### 3. Regulatory Filing Search

```
search_fca_documents("IPO prospectus")
```

Recent IPO documents.

### 4. Investigative Research

```
search_aleph_uk("Offshore Company Ltd", collections=["pandora_papers_uk"])
```

Leaked document mentions.

### 5. Area Ownership Analysis

```
search_uk_land_registry_by_postcode("SW1A")
```

All Westminster properties.

## Output Format

All tools return JSON with:

- Standardized structure
- Clear error messages
- Source attribution
- Result counts
- Search parameters

## Error Handling

- Missing CSV files: Clear error with path info
- API failures: Graceful degradation in comprehensive search
- Invalid parameters: Descriptive validation errors
- Network issues: Timeout and retry information
