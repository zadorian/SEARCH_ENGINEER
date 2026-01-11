# Corporate Search System - Technical Documentation

## Overview

`corporate_search.py` is a unified corporate intelligence gathering system that searches multiple databases and uses OpenAI's GPT-4.1-nano model to consolidate findings into actionable intelligence reports.

## Architecture

### Core Components

1. **UltimateCorporateSearch Class**
   - Main orchestrator for all search operations
   - Handles API communications
   - Manages result consolidation
   - Provides formatted output

2. **Search Modules**
   - `_search_opencorporates()` - Global corporate registry data
   - `_search_occrp_aleph()` - Investigative journalism database
   - `_search_opensanctions()` - Sanctions and PEP screening
   - `_search_offshore_leaks()` - Offshore entity detection (CSV-based)

3. **AI Consolidation Engine**
   - `_consolidate_with_gpt41nano()` - Intelligent data fusion
   - Uses OpenAI's structured output format
   - Temperature set to 0.3 for consistency
   - Max tokens: 4000

## API Integrations

### OpenCorporates

- **Endpoint**: `https://api.opencorporates.com/v0.4/companies/search`
- **Rate Limit**: 500 requests/month (free tier)
- **Data Retrieved**:
  - Company name and variations
  - Jurisdiction and registration numbers
  - Incorporation dates
  - Current status
  - Registered addresses
  - Industry codes

### OCCRP Aleph

- **Endpoint**: `https://aleph.occrp.org/api/2/entities`
- **Authentication**: ApiKey header
- **Data Retrieved**:
  - Entity names and aliases
  - Countries of operation
  - Related dates
  - Topics and tags
  - Cross-references

### OpenSanctions

- **Endpoint**: `https://api.opensanctions.org/search/default`
- **Authentication**: Bearer token
- **Data Retrieved**:
  - Sanctions listings
  - PEP status
  - Dataset sources
  - First/last seen dates
  - Target designation

### GPT-4.1-nano Configuration

```python
Model: gpt-4.1-nano-2025-04-14
Temperature: 0.3
Max Tokens: 4000
Response Format: JSON Object
System Role: "Corporate intelligence analyst"
```

## Data Flow

```
User Input (Company Name)
    ↓
Parallel API Searches
    ├── OpenCorporates
    ├── OCCRP Aleph
    ├── OpenSanctions
    └── Offshore Leaks
    ↓
Raw Results Collection
    ↓
GPT-4.1-nano Consolidation
    ├── Beneficial Ownership Analysis
    ├── Related Entity Mapping
    ├── Key Individual Identification
    ├── Financial Data Extraction
    └── Risk Assessment
    ↓
Structured JSON Output
    ↓
File Storage + Console Summary
```

## Consolidation Logic

The GPT-4.1-nano model is instructed to prioritize:

1. **Beneficial Ownership** (Highest Priority)
   - Ultimate beneficial owners with percentages
   - Complete ownership chains
   - Transparency assessment

2. **Related Entities** (High Priority)
   - Parent companies
   - Subsidiaries
   - Affiliates and joint ventures

3. **Key Individuals** (High Priority)
   - Current directors and officers
   - Cross-appointments
   - Sanctions connections

4. **Financial Data** (High Priority)
   - Latest revenue figures
   - Financial trends
   - Red flags

5. **Risk Assessment**
   - Overall risk rating
   - Specific risk factors
   - Sanctions exposure
   - Structural red flags

## Output Schema

```json
{
  "company_name": "string",
  "consolidated_status": "Active|Inactive|Mixed",
  "primary_jurisdiction": "string",
  "beneficial_ownership": {
    "ultimate_owners": [
      {
        "name": "string",
        "percentage": "number|string",
        "source": "string",
        "confidence": "high|medium|low"
      }
    ],
    "ownership_structure": "string",
    "transparency_level": "transparent|opaque|complex"
  },
  "related_entities": {
    "parent_companies": [{ "name": "string", "jurisdiction": "string" }],
    "subsidiaries": [{ "name": "string", "jurisdiction": "string" }],
    "affiliates": [{ "name": "string", "relationship": "string" }]
  },
  "key_individuals": {
    "directors": [
      { "name": "string", "position": "string", "appointed": "date" }
    ],
    "officers": [
      { "name": "string", "position": "string", "appointed": "date" }
    ],
    "other_related": [{ "name": "string", "relationship": "string" }]
  },
  "financial_data": {
    "latest_revenue": {
      "amount": "number",
      "currency": "string",
      "year": "number",
      "source": "string"
    },
    "trends": "string"
  },
  "risk_assessment": {
    "overall_risk": "high|medium|low",
    "risk_factors": ["string"],
    "sanctions_exposure": "none|direct|indirect",
    "red_flags": ["string"]
  },
  "data_sources": {
    "primary_sources": ["string"],
    "data_quality": "high|medium|low",
    "gaps_identified": ["string"]
  },
  "consolidation_metadata": {
    "model_used": "gpt-4.1-nano-2025-04-14",
    "timestamp": "ISO 8601",
    "sources_searched": ["string"],
    "total_raw_results": "number"
  },
  "raw_search_results": {}
}
```

## Error Handling

1. **API Failures**: Logged and skipped, search continues
2. **GPT-4.1-nano Failures**: Returns raw results with error message
3. **Network Issues**: Caught and reported per API
4. **Invalid Input**: Validated before search begins

## File Storage

- **Directory**: `ultimate_search_results/`
- **Naming**: `{CompanyName}_{YYYYMMDD}_{HHMMSS}_consolidated.json`
- **Content**: Full consolidated results + raw API responses

## Usage Examples

### Basic Search

```bash
python3 corporate_search.py
> Enter company name: Apple Inc
```

### Batch Processing

```python
from corporate_search import UltimateCorporateSearch

searcher = UltimateCorporateSearch()
companies = ["Apple Inc", "Microsoft Corp", "Tesla Inc"]

for company in companies:
    results = searcher.search_and_consolidate(company)
    print(f"Completed: {company}")
```

### Programmatic Access

```python
# Import and use directly
from corporate_search import UltimateCorporateSearch

searcher = UltimateCorporateSearch()
results = searcher.search_and_consolidate("Revolut Ltd")

# Access specific data
beneficial_owners = results['beneficial_ownership']['ultimate_owners']
risk_level = results['risk_assessment']['overall_risk']
```

## Performance Considerations

- **Search Time**: ~5-10 seconds per company
- **API Calls**: 4 parallel searches
- **Token Usage**: ~2000-3000 tokens per consolidation
- **Memory**: Minimal, results streamed to disk

## Security Notes

1. API keys are embedded (consider environment variables for production)
2. No sensitive data is logged
3. Results stored locally only
4. HTTPS used for all API communications

## Maintenance

### Updating API Keys

```python
# Line 20-23 in corporate_search.py
OPENAI_API_KEY = 'your-new-key'
OPENCORPORATES_API_KEY = 'your-new-key'
OCCRP_API_KEY = 'your-new-key'
OPENSANCTIONS_API_KEY = 'your-new-key'
```

### Adding New Data Sources

1. Create new `_search_xyz()` method
2. Add to main search flow in `search_and_consolidate()`
3. Update consolidation prompt with new data structure
4. Document in this file

## Version History

- **v1.0** (Feb 15, 2025): Initial release with 4 data sources and GPT-4.1-nano
- All previous experimental versions deleted

---

**Remember: This is the ONLY corporate search implementation. Use `gpt-4.1-nano-2025-04-14` model exclusively.**
