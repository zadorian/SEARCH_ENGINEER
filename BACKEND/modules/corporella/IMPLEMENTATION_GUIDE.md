# Corporella Claude - Implementation Guide

This guide shows you how to wire together the 4 components using only the working code from `_TEMP_STANDALONE_CORPORELLA`.

## Source Files Mapping

### What to Extract from `_TEMP_STANDALONE_CORPORELLA`

| New File | Source File | Lines/Sections | What to Include |
|----------|------------|----------------|-----------------|
| `finder.py` | `corporella.py` | 69-187 | OpenCorporates search functions only |
| `fetcher.py` | `corporella.py` | 703-1354 | Parallel search orchestration |
| `populator.py` | `corporate_entity_populator.py` | Full file | Claude Haiku merger (upgrade to 4.5) |
| `analyzer.py` | `corporella.py` + `company_network_analyzer.py` | 1361-1576 + network functions | Person search + graph analysis (skip UK code) |
| `websocket_server.py` | `corporate_websocket_server.py` | Full file | WebSocket streaming server |
| `client.html` | `corporate_client.html` | Full file | Frontend UI |
| `entity_template.json` | `company_entity_template.json` | Full file | Data structure template |
| `utils/deduplicator.py` | `from_canonical_ENTITY_folder/utils/deduplicator.py` | Full file | Deduplication logic |
| `utils/parallel_executor.py` | Extract from `corporella.py` | Threading utilities | ThreadPoolExecutor wrapper |

### What to SKIP

- ❌ `fast_registry_search.py` (requires pre-downloaded data)
- ❌ `company_network_analyzer.py` lines 1-200 (UK-specific code)
- ❌ Any national/ folder references
- ❌ Risk scoring functions
- ❌ Companies House UK API calls

## Step-by-Step Implementation

### Step 1: Create `finder.py`

Extract the search functions from `corporella.py`:

```python
"""
Component 1: Finder
Search for companies based on various criteria
"""

import requests
from typing import Dict, List, Optional, Any
import os

class CompanyFinder:
    """Search for companies by name, officer, LEI, etc."""

    def __init__(self):
        self.oc_api_key = os.getenv("OPENCORPORATES_API_KEY")
        self.oc_base_url = "https://api.opencorporates.com/v0.4"

    def search_by_name(
        self,
        name: str,
        jurisdiction: Optional[str] = None,
        per_page: int = 10
    ) -> Dict[str, Any]:
        """
        Search OpenCorporates by company name

        Args:
            name: Company name to search
            jurisdiction: ISO country code (e.g., "us_ca", "gb")
            per_page: Results per page (max 100)

        Returns:
            {
                "companies": [...],
                "total_count": int,
                "source": "opencorporates"
            }
        """
        params = {
            "q": name,
            "per_page": per_page
        }

        if jurisdiction:
            params["jurisdiction_code"] = jurisdiction

        if self.oc_api_key:
            params["api_token"] = self.oc_api_key

        try:
            response = requests.get(
                f"{self.oc_base_url}/companies/search",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            companies = []
            for comp in data.get("results", {}).get("companies", []):
                company_data = comp.get("company", {})
                companies.append({
                    "name": company_data.get("name"),
                    "company_number": company_data.get("company_number"),
                    "jurisdiction": company_data.get("jurisdiction_code"),
                    "incorporation_date": company_data.get("incorporation_date"),
                    "company_type": company_data.get("company_type"),
                    "status": company_data.get("current_status"),
                    "registered_address": company_data.get("registered_address_in_full"),
                    "opencorporates_url": company_data.get("opencorporates_url"),
                    "source": "opencorporates"
                })

            return {
                "companies": companies,
                "total_count": data.get("results", {}).get("total_count", 0),
                "source": "opencorporates"
            }

        except Exception as e:
            return {
                "error": str(e),
                "companies": [],
                "total_count": 0,
                "source": "opencorporates"
            }

    def search_by_officer(
        self,
        officer_name: str,
        per_page: int = 10
    ) -> Dict[str, Any]:
        """
        Search OpenCorporates for companies where person is officer/director

        Args:
            officer_name: Name of person to search
            per_page: Results per page

        Returns:
            {
                "officers": [...],
                "total_count": int,
                "source": "opencorporates"
            }
        """
        params = {
            "q": officer_name,
            "per_page": per_page
        }

        if self.oc_api_key:
            params["api_token"] = self.oc_api_key

        try:
            response = requests.get(
                f"{self.oc_base_url}/officers/search",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            officers = []
            for off in data.get("results", {}).get("officers", []):
                officer_data = off.get("officer", {})
                company_data = officer_data.get("company", {})

                officers.append({
                    "officer_name": officer_data.get("name"),
                    "position": officer_data.get("position"),
                    "start_date": officer_data.get("start_date"),
                    "end_date": officer_data.get("end_date"),
                    "company_name": company_data.get("name"),
                    "company_number": company_data.get("company_number"),
                    "jurisdiction": company_data.get("jurisdiction_code"),
                    "opencorporates_url": officer_data.get("opencorporates_url"),
                    "source": "opencorporates"
                })

            return {
                "officers": officers,
                "total_count": data.get("results", {}).get("total_count", 0),
                "source": "opencorporates"
            }

        except Exception as e:
            return {
                "error": str(e),
                "officers": [],
                "total_count": 0,
                "source": "opencorporates"
            }

    def search_by_lei(self, lei: str) -> Dict[str, Any]:
        """
        Search by Legal Entity Identifier

        Args:
            lei: 20-character LEI code

        Returns:
            Company data if found
        """
        # TODO: Implement GLEIF API integration
        return {
            "error": "LEI search not yet implemented",
            "source": "gleif"
        }


# Simple usage example
if __name__ == "__main__":
    finder = CompanyFinder()

    # Search by name
    results = finder.search_by_name("Apple Inc", jurisdiction="us_ca")
    print(f"Found {results['total_count']} companies")
    for company in results['companies'][:3]:
        print(f"  - {company['name']} ({company['jurisdiction']})")

    # Search by officer
    officer_results = finder.search_by_officer("Tim Cook")
    print(f"\nFound {officer_results['total_count']} officer records")
    for officer in officer_results['officers'][:3]:
        print(f"  - {officer['officer_name']} at {officer['company_name']}")
```

### Step 2: Create `fetcher.py`

This is the core parallel search orchestrator. Extract from `corporella.py` lines 703-1354:

```python
"""
Component 2: Fetcher
Parallel multi-source company data retrieval
"""

import asyncio
import concurrent.futures
from typing import Dict, List, Optional, Any
import time
from finder import CompanyFinder

class GlobalCompanyFetcher:
    """
    Parallel search across multiple global sources:
    - OpenCorporates (official registries)
    - OCCRP Aleph (investigative data)
    - SEC EDGAR (US filings)
    - OpenOwnership (beneficial ownership)
    - LinkedIn (company profiles)
    """

    def __init__(self):
        self.finder = CompanyFinder()
        self.max_workers = 5

    async def parallel_search(
        self,
        company_name: str,
        country_code: Optional[str] = None,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Execute parallel searches across all sources

        Args:
            company_name: Company name to search
            country_code: Optional ISO country code
            timeout: Timeout per source in seconds

        Returns:
            {
                "raw_results": [...],      # All source results
                "sources_used": [...],     # Which sources returned data
                "processing_time": float,
                "errors": [...]            # Any errors encountered
            }
        """
        start_time = time.time()

        # Define search tasks
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all searches in parallel
            future_oc = executor.submit(
                self._search_opencorporates,
                company_name,
                country_code,
                timeout
            )
            future_aleph = executor.submit(
                self._search_aleph,
                company_name,
                timeout
            )
            future_edgar = executor.submit(
                self._search_edgar,
                company_name,
                timeout
            )
            future_openownership = executor.submit(
                self._search_openownership,
                company_name,
                timeout
            )
            future_linkedin = executor.submit(
                self._search_linkedin,
                company_name,
                timeout
            )

            # Collect results as they complete
            raw_results = []
            sources_used = []
            errors = []

            futures = {
                "opencorporates": future_oc,
                "aleph": future_aleph,
                "edgar": future_edgar,
                "openownership": future_openownership,
                "linkedin": future_linkedin
            }

            for source_name, future in futures.items():
                try:
                    result = future.result(timeout=timeout)
                    if result and not result.get("error"):
                        raw_results.append(result)
                        sources_used.append(source_name)
                    elif result.get("error"):
                        errors.append({
                            "source": source_name,
                            "error": result["error"]
                        })
                except concurrent.futures.TimeoutError:
                    errors.append({
                        "source": source_name,
                        "error": f"Timeout after {timeout}s"
                    })
                except Exception as e:
                    errors.append({
                        "source": source_name,
                        "error": str(e)
                    })

        processing_time = time.time() - start_time

        return {
            "query": company_name,
            "raw_results": raw_results,
            "sources_used": sources_used,
            "processing_time": processing_time,
            "errors": errors
        }

    def _search_opencorporates(
        self,
        company_name: str,
        country_code: Optional[str],
        timeout: float
    ) -> Dict[str, Any]:
        """Search OpenCorporates"""
        try:
            result = self.finder.search_by_name(
                company_name,
                jurisdiction=country_code
            )
            result["timestamp"] = time.time()
            return result
        except Exception as e:
            return {"error": str(e), "source": "opencorporates"}

    def _search_aleph(
        self,
        company_name: str,
        timeout: float
    ) -> Dict[str, Any]:
        """Search OCCRP Aleph"""
        # TODO: Implement using 01aleph.py from _TEMP_STANDALONE_CORPORELLA
        return {
            "source": "aleph",
            "results": [],
            "note": "Aleph integration pending"
        }

    def _search_edgar(
        self,
        company_name: str,
        timeout: float
    ) -> Dict[str, Any]:
        """Search SEC EDGAR"""
        # TODO: Implement using edgar_integration.py
        return {
            "source": "edgar",
            "filings": [],
            "note": "EDGAR integration pending"
        }

    def _search_openownership(
        self,
        company_name: str,
        timeout: float
    ) -> Dict[str, Any]:
        """Search OpenOwnership"""
        # TODO: Implement OpenOwnership API
        return {
            "source": "openownership",
            "ownership": [],
            "note": "OpenOwnership integration pending"
        }

    def _search_linkedin(
        self,
        company_name: str,
        timeout: float
    ) -> Dict[str, Any]:
        """Search LinkedIn (via HuggingFace dataset)"""
        # TODO: Implement LinkedIn dataset search
        return {
            "source": "linkedin",
            "profiles": [],
            "note": "LinkedIn integration pending"
        }


# Usage example
if __name__ == "__main__":
    async def main():
        fetcher = GlobalCompanyFetcher()

        print("Searching for 'Apple Inc'...")
        results = await fetcher.parallel_search("Apple Inc", country_code="us")

        print(f"\nResults from {len(results['sources_used'])} sources:")
        print(f"Processing time: {results['processing_time']:.2f}s")

        for source in results['sources_used']:
            print(f"  ✓ {source}")

        if results['errors']:
            print(f"\nErrors from {len(results['errors'])} sources:")
            for error in results['errors']:
                print(f"  ✗ {error['source']}: {error['error']}")

    asyncio.run(main())
```

### Step 3: Create `populator.py`

This is the Claude Haiku AI component. Use `corporate_entity_populator.py` as-is, but upgrade to Haiku 4.5:

**Key changes:**
1. Change model from `"claude-3-haiku-20240307"` to `"claude-3-5-haiku-20241022"`
2. Keep all the deduplication, contradiction detection, and merging logic
3. Keep source badge tagging

```python
# In populator.py, change line ~175:
response = self.client.messages.create(
    model="claude-3-5-haiku-20241022",  # ← Haiku 4.5
    max_tokens=4000,
    temperature=0.1,
    messages=[{"role": "user", "content": prompt}]
)
```

### Step 4: Wire Components Together

Create a simple example showing how all 4 components work together:

```python
"""
example_usage.py - How to use all 4 components together
"""

import asyncio
from finder import CompanyFinder
from fetcher import GlobalCompanyFetcher
from populator import CorporateEntityPopulator
# from analyzer import NetworkAnalyzer  # Step 5

async def search_company_complete(company_name: str):
    """
    Complete workflow:
    1. Finder: Quick search to validate company exists
    2. Fetcher: Parallel multi-source data retrieval
    3. Populator: AI-powered merging and deduplication
    4. Analyzer: Network analysis (optional)
    """

    print(f"=== Searching for: {company_name} ===\n")

    # Step 1: Quick validation search
    print("Step 1: Quick search validation...")
    finder = CompanyFinder()
    quick_results = finder.search_by_name(company_name, per_page=5)

    if quick_results['total_count'] == 0:
        print("  ✗ Company not found in OpenCorporates")
        return None

    print(f"  ✓ Found {quick_results['total_count']} matches")
    print(f"    Top match: {quick_results['companies'][0]['name']}\n")

    # Step 2: Parallel fetch from all sources
    print("Step 2: Fetching from all sources...")
    fetcher = GlobalCompanyFetcher()
    raw_results = await fetcher.parallel_search(company_name)

    print(f"  ✓ Retrieved data from {len(raw_results['sources_used'])} sources")
    print(f"    Processing time: {raw_results['processing_time']:.2f}s")
    print(f"    Sources: {', '.join(raw_results['sources_used'])}\n")

    # Step 3: AI-powered merging
    print("Step 3: AI merging with Claude Haiku...")
    populator = CorporateEntityPopulator()

    merged_entity = {}
    for result in raw_results['raw_results']:
        merged_entity = await populator.process_streaming_result(result)
        print(f"  ✓ Processed {result['source']}")

    print(f"\n  Final merged entity:")
    print(f"    Name: {merged_entity.get('name', 'N/A')}")
    print(f"    Jurisdiction: {merged_entity.get('about', {}).get('jurisdiction', 'N/A')}")
    print(f"    Officers: {len(merged_entity.get('officers', []))}")
    print(f"    Sources: {', '.join(merged_entity.get('_sources', []))}")

    if merged_entity.get('_contradictions'):
        print(f"    ⚠️  Contradictions detected: {len(merged_entity['_contradictions'])}")

    return merged_entity


# Run example
if __name__ == "__main__":
    asyncio.run(search_company_complete("Apple Inc"))
```

## Integration with WebSocket Server

The WebSocket server (Component 4) coordinates everything:

```python
# In websocket_server.py

class CorporateWebSocketServer:
    async def handle_search_request(self, websocket, message):
        query = message.get("query")

        # Initialize components
        fetcher = GlobalCompanyFetcher()
        populator = CorporateEntityPopulator()

        # Start parallel fetch
        results = await fetcher.parallel_search(query)

        # Stream raw results immediately (Fast Path)
        for raw_result in results['raw_results']:
            await websocket.send(json.dumps({
                "type": "raw_result",
                "result": raw_result
            }))

        # Process with Haiku (Smart Path) - runs in parallel
        merged_entity = {}
        for raw_result in results['raw_results']:
            merged_entity = await populator.process_streaming_result(raw_result)

            # Send progressive updates
            await websocket.send(json.dumps({
                "type": "entity_update",
                "entity": merged_entity
            }))

        # Final result
        await websocket.send(json.dumps({
            "type": "search_complete",
            "entity": merged_entity,
            "processing_time": results['processing_time']
        }))
```

## Next Steps

1. **Copy files from `_TEMP_STANDALONE_CORPORELLA`** following the mapping table above
2. **Upgrade Claude Haiku** from 3.0 to 4.5 in `populator.py`
3. **Implement TODOs** in `fetcher.py` (Aleph, EDGAR, OpenOwnership, LinkedIn)
4. **Test each component** independently first
5. **Wire together** using `example_usage.py` pattern
6. **Deploy WebSocket server** for full real-time UI

## Testing Checklist

- [ ] `finder.py` - Can search OpenCorporates by name and officer
- [ ] `fetcher.py` - Parallel execution works, handles timeouts gracefully
- [ ] `populator.py` - Claude Haiku merges correctly, detects duplicates
- [ ] `websocket_server.py` - Streams results in real-time
- [ ] `client.html` - Displays raw + merged results side-by-side
- [ ] Full workflow - All 4 components work together seamlessly
