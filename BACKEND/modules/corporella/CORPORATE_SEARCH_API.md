# Corporate Search API Documentation

## Overview

The Corporate Search API provides RESTful access to the consolidated corporate intelligence system, searching across multiple databases and using GPT-4.1-nano for intelligent consolidation.

## Authentication

All API requests require an API key in the header:

```
X-API-Key: your-api-key-here
```

Demo key for testing: `demo-key-123`

## Base URL

```
http://localhost:5000/api/v1
```

## Endpoints

### 1. Health Check

Check if the API is running:

```bash
GET /api/v1/health
```

Response:

```json
{
  "status": "healthy",
  "timestamp": "2024-12-17T10:30:00",
  "version": "1.0"
}
```

### 2. List Data Sources

Get information about available data sources:

```bash
GET /api/v1/sources
```

Response:

```json
{
  "sources": [
    {
      "name": "OpenCorporates",
      "type": "global_registry",
      "coverage": "worldwide",
      "data_types": ["company_profile", "officers", "filings"]
    },
    {
      "name": "EDGAR (SEC)",
      "type": "official_registry",
      "coverage": "United States",
      "data_types": ["10-K", "10-Q", "8-K", "DEF 14A", "insider_trading"]
    }
    // ... more sources
  ],
  "consolidation": {
    "model": "gpt-4.1-nano-2025-04-14",
    "capabilities": [
      "beneficial_ownership_mapping",
      "risk_assessment",
      "entity_resolution",
      "relationship_extraction"
    ]
  }
}
```

### 3. Search Company (POST)

Perform a comprehensive company search:

```bash
POST /api/v1/search
Content-Type: application/json
X-API-Key: demo-key-123

{
  "company_name": "Apple Inc",
  "include_raw_data": false,
  "output_format": "full"
}
```

Parameters:

- `company_name` (required): Company name to search
- `include_raw_data` (optional): Include raw search results from all sources (default: false)
- `output_format` (optional): Response format - "full", "summary", or "minimal" (default: "full")

Response (full format):

```json
{
  "success": true,
  "data": {
    "company_name": "Apple Inc",
    "consolidated_status": "Active",
    "primary_jurisdiction": "US_CA",
    "uk_company_number": null,
    "beneficial_ownership": {
      "ultimate_owners": [],
      "ownership_structure": "Public company - widely held",
      "transparency_level": "transparent"
    },
    "related_entities": {
      "subsidiaries": ["Apple Sales International", "Apple Retail UK Limited"],
      "affiliates": []
    },
    "key_individuals": {
      "directors": [
        {
          "name": "Tim Cook",
          "role": "CEO",
          "appointed": "2011-08-24"
        }
      ]
    },
    "financial_data": {
      "sec_filings": {
        "is_sec_filer": true,
        "latest_10k_date": "2024-10-31",
        "latest_10q_date": "2024-11-01",
        "filing_frequency": 287,
        "foreign_filer": false,
        "material_events_count": 3
      }
    },
    "risk_assessment": {
      "overall_risk": "low",
      "risk_factors": [],
      "sanctions_exposure": "none",
      "red_flags": []
    },
    "data_sources": {
      "primary_sources": ["OpenCorporates", "EDGAR", "OCCRP Aleph"],
      "data_quality": "high"
    }
  },
  "metadata": {
    "timestamp": "2024-12-17T10:30:00",
    "search_time_seconds": 12.5,
    "options": {
      "include_raw_data": false,
      "output_format": "full"
    }
  }
}
```

Response (minimal format):

```json
{
  "success": true,
  "data": {
    "company_name": "Apple Inc",
    "status": "Active",
    "jurisdiction": "US_CA",
    "risk_level": "low",
    "beneficial_owners": []
  },
  "metadata": {
    "timestamp": "2024-12-17T10:30:00",
    "options": {
      "output_format": "minimal"
    }
  }
}
```

### 4. Search Company (GET)

Simple GET endpoint for basic searches:

```bash
GET /api/v1/search/Apple%20Inc
X-API-Key: demo-key-123
```

## Error Responses

### 401 Unauthorized

```json
{
  "error": "Invalid or missing API key",
  "message": "Please provide valid API key in X-API-Key header"
}
```

### 400 Bad Request

```json
{
  "error": "Missing parameter",
  "message": "company_name is required"
}
```

### 500 Internal Server Error

```json
{
  "success": false,
  "error": "Search failed",
  "message": "Error details here"
}
```

## Rate Limits

- OpenCorporates: 500 requests/month (free tier)
- Companies House: 600 requests/minute
- EDGAR: Built-in delays for SEC compliance
- API Server: No additional limits (but respects upstream limits)

## Examples

### cURL Examples

Basic search:

```bash
curl -X POST http://localhost:5000/api/v1/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-key-123" \
  -d '{"company_name": "Tesla Inc"}'
```

Minimal format search:

```bash
curl -X POST http://localhost:5000/api/v1/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-key-123" \
  -d '{
    "company_name": "Revolut Ltd",
    "output_format": "minimal"
  }'
```

### Python Example

```python
import requests
import json

# API configuration
API_URL = "http://localhost:5000/api/v1/search"
API_KEY = "demo-key-123"

# Search for a company
def search_company(company_name):
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }

    data = {
        "company_name": company_name,
        "output_format": "summary"
    }

    response = requests.post(API_URL, json=data, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        print(response.json())
        return None

# Example usage
result = search_company("Microsoft Corporation")
if result and result['success']:
    company_data = result['data']
    print(f"Company: {company_data['company_name']}")
    print(f"Status: {company_data['consolidated_status']}")
    print(f"Risk Level: {company_data['risk_assessment']['overall_risk']}")
```

### JavaScript Example

```javascript
const API_URL = "http://localhost:5000/api/v1/search";
const API_KEY = "demo-key-123";

async function searchCompany(companyName) {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
    body: JSON.stringify({
      company_name: companyName,
      output_format: "summary",
    }),
  });

  const data = await response.json();

  if (response.ok && data.success) {
    return data.data;
  } else {
    throw new Error(data.message || "Search failed");
  }
}

// Example usage
searchCompany("Amazon.com Inc")
  .then(data => {
    console.log(`Company: ${data.company_name}`);
    console.log(`Jurisdiction: ${data.primary_jurisdiction}`);
    console.log(`SEC Filer: ${data.financial_data.sec_filings.is_sec_filer}`);
  })
  .catch(error => console.error("Error:", error));
```

## Running the API Server

1. Install Flask if not already installed:

```bash
pip install flask flask-cors
```

2. Start the server:

```bash
python3 api_server.py
```

3. The API will be available at `http://localhost:5000`

## Production Considerations

For production use:

1. Implement proper authentication (OAuth2, JWT)
2. Add rate limiting per API key
3. Use environment variables for configuration
4. Deploy behind a reverse proxy (nginx)
5. Add request/response logging
6. Implement caching for frequently searched companies
7. Use a production WSGI server (gunicorn, uWSGI)
8. Add monitoring and alerts

## Support

For issues or questions:

- Check the main documentation: CLAUDE.md
- Review the logs in the API server console
- Ensure all API keys are properly configured
