#!/usr/bin/env python3
"""
Component 2: Fetcher
Parallel multi-source company data retrieval
"""

import asyncio
import concurrent.futures
from typing import Dict, List, Optional, Any
import time
from pathlib import Path
from finder import CompanyFinder
from aleph import UnifiedAleph

# Load environment variables from project root .env
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")


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
        self.aleph = UnifiedAleph()
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
                "query": str,
                "raw_results": [...],      # All source results
                "sources_used": [...],     # Which sources returned data
                "processing_time": float,
                "execution_times": {...},  # Time per source
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
                country_code,
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
            execution_times = {}
            errors = []

            futures = {
                "opencorporates": future_oc,
                "aleph": future_aleph,
                "edgar": future_edgar,
                "openownership": future_openownership,
                "linkedin": future_linkedin
            }

            for source_name, future in futures.items():
                source_start = time.time()
                try:
                    result = future.result(timeout=timeout)
                    exec_time = time.time() - source_start
                    execution_times[source_name] = exec_time

                    if result and result.get("ok"):
                        result["execution_time"] = exec_time
                        raw_results.append(result)
                        sources_used.append(source_name)
                    elif result and result.get("error"):
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
            "execution_times": execution_times,
            "errors": errors
        }

    def _search_opencorporates(
        self,
        company_name: str,
        country_code: Optional[str],
        timeout: float
    ) -> Dict[str, Any]:
        """Search OpenCorporates with full company details including officers"""
        try:
            # First get search results
            result = self.finder.search_by_name(
                company_name,
                jurisdiction=country_code
            )

            # For each company, fetch full details including officers
            if result.get("ok") and result.get("companies"):
                for company in result["companies"]:
                    jurisdiction = company.get("jurisdiction_code")
                    company_number = company.get("company_number")

                    if jurisdiction and company_number:
                        # Fetch full company record with officers
                        full_data = self._get_opencorporates_full_record(jurisdiction, company_number)
                        if full_data:
                            company["officers"] = full_data.get("officers", [])
                            company["previous_names"] = full_data.get("previous_names", [])
                            company["ultimate_beneficial_owners"] = full_data.get("ultimate_beneficial_owners")

            result["timestamp"] = time.time()
            return result
        except Exception as e:
            return {"ok": False, "error": str(e), "source": "opencorporates"}

    def _get_opencorporates_full_record(self, jurisdiction: str, company_number: str) -> Optional[Dict]:
        """Fetch full OpenCorporates company record including officers"""
        try:
            import requests
            base_url = f"https://api.opencorporates.com/v0.4/companies/{jurisdiction}/{company_number}"
            token = self.finder.oc_api_key

            params = {}
            if token:
                params["api_token"] = token

            response = requests.get(base_url, params=params, timeout=10)
            if response.status_code == 401 and params.get("api_token"):
                params.pop("api_token")
                response = requests.get(base_url, params=params, timeout=10)

            response.raise_for_status()
            data = response.json()
            company_data = data.get("results", {}).get("company", {})

            # Extract officers
            officers = []
            for entry in company_data.get("officers", []):
                officer = entry.get("officer", {})
                if officer:
                    officers.append({
                        "name": officer.get("name"),
                        "position": officer.get("position"),
                        "start_date": officer.get("start_date"),
                        "end_date": officer.get("end_date"),
                        "nationality": officer.get("nationality"),
                        "occupation": officer.get("occupation"),
                        "address": officer.get("address")
                    })

            return {
                "officers": officers,
                "previous_names": [item.get("company_name") for item in (company_data.get("previous_names") or [])],
                "ultimate_beneficial_owners": company_data.get("ultimate_beneficial_owners")
            }
        except Exception as e:
            return None

    def _search_aleph(
        self,
        company_name: str,
        country_code: Optional[str],
        timeout: float
    ) -> Dict[str, Any]:
        """
        Search OCCRP Aleph and fetch EVERYTHING related to each company:
        - Directors (Directorship schema)
        - Ownership (Ownership schema)
        - Addresses (all address properties)
        - Previous names
        - All connected entities
        """
        try:
            # Search with country-based routing if available
            # DO NOT FILTER BY SCHEMA - We want ALL results!
            result = self.aleph.search_entity(
                query=company_name,
                country=country_code,
                schema=None  # Get ALL schemas, not just Company!
            )

            # For each company, fetch ALL related data
            if result.get("results"):
                for entity in result["results"]:
                    entity["source_badge"] = "[AL]"
                    entity_id = entity.get("id")

                    # Get full enriched entity data
                    enriched = self._fetch_full_aleph_entity(entity_id, country_code, timeout)
                    if enriched:
                        # Merge enriched data into entity
                        entity.update(enriched)

            # Add source tagging
            result["ok"] = True
            result["timestamp"] = time.time()

            return result

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "source": "aleph"
            }

    def _fetch_full_aleph_entity(self, entity_id: str, country_code: Optional[str], timeout: float) -> Optional[Dict]:
        """Fetch EVERYTHING about an Aleph entity including all relationships"""
        try:
            import requests
            import os

            api_key = os.getenv('ALEPH_API_KEY', '1c0971afa4804c2aafabb125c79b275e')
            base_url = "https://aleph.occrp.org/api/2"
            headers = {"Authorization": f"ApiKey {api_key}"}

            enriched_data = {}

            # 1. Get the full entity details
            entity_url = f"{base_url}/entities/{entity_id}"
            response = requests.get(entity_url, headers=headers, timeout=timeout)
            if response.ok:
                full_entity = response.json()
                enriched_data["full_properties"] = full_entity

            # 2. Fetch ALL related entities (directors, ownership, etc)
            related_url = f"{base_url}/entities/{entity_id}/similar"
            params = {"limit": 100}
            if country_code:
                params["filter:countries"] = country_code.upper()

            response = requests.get(related_url, params=params, headers=headers, timeout=timeout)
            if response.ok:
                related = response.json()
                enriched_data["related_entities"] = related.get("results", [])

            # 3. Fetch directors specifically
            directors = self._fetch_aleph_directors_by_entity_id(entity_id, country_code, timeout)
            if directors:
                enriched_data["officers"] = directors

            # 4. Fetch ownership data
            ownership = self._fetch_aleph_ownership(entity_id, country_code, timeout)
            if ownership:
                enriched_data["ownership"] = ownership

            return enriched_data

        except Exception as e:
            return None

    def _fetch_aleph_directors_by_entity_id(self, entity_id: str, country_code: Optional[str], timeout: float) -> List[Dict]:
        """Fetch directors using entity ID"""
        try:
            import requests
            import os

            api_key = os.getenv('ALEPH_API_KEY', '1c0971afa4804c2aafabb125c79b275e')
            base_url = "https://aleph.occrp.org/api/2/entities"

            params = {
                "filter:schemata": "Directorship",
                "filter:properties.organization": entity_id,
                "limit": 100
            }

            if country_code:
                params["filter:countries"] = country_code.upper()

            headers = {"Authorization": f"ApiKey {api_key}"}
            response = requests.get(base_url, params=params, headers=headers, timeout=timeout)

            if not response.ok:
                return []

            data = response.json()
            directors = []

            for directorship in data.get("results", []):
                props = directorship.get("properties", {})

                # Extract director info
                director_name = props.get("director", [None])[0] if props.get("director") else None
                role = props.get("role", [None])[0] if props.get("role") else "Director"
                start_date = props.get("startDate", [None])[0] if props.get("startDate") else None
                end_date = props.get("endDate", [None])[0] if props.get("endDate") else None

                if director_name:
                    directors.append({
                        "name": director_name,
                        "position": role,
                        "start_date": start_date,
                        "end_date": end_date,
                        "source": "[AL]"
                    })

            return directors

        except Exception as e:
            return []

    def _fetch_aleph_ownership(self, entity_id: str, country_code: Optional[str], timeout: float) -> List[Dict]:
        """Fetch ownership/shareholding data"""
        try:
            import requests
            import os

            api_key = os.getenv('ALEPH_API_KEY', '1c0971afa4804c2aafabb125c79b275e')
            base_url = "https://aleph.occrp.org/api/2/entities"

            params = {
                "filter:schemata": "Ownership",
                "filter:properties.asset": entity_id,
                "limit": 100
            }

            if country_code:
                params["filter:countries"] = country_code.upper()

            headers = {"Authorization": f"ApiKey {api_key}"}
            response = requests.get(base_url, params=params, headers=headers, timeout=timeout)

            if not response.ok:
                return []

            data = response.json()
            ownership = []

            for own in data.get("results", []):
                props = own.get("properties", {})

                owner_name = props.get("owner", [None])[0] if props.get("owner") else None
                percentage = props.get("percentage", [None])[0] if props.get("percentage") else None
                start_date = props.get("startDate", [None])[0] if props.get("startDate") else None

                if owner_name:
                    ownership.append({
                        "owner": owner_name,
                        "percentage": percentage,
                        "start_date": start_date
                    })

            return ownership

        except Exception as e:
            return []

    def _fetch_aleph_directors(self, registration_number: str, country_code: Optional[str]) -> List[Dict]:
        """Fetch directors from Aleph using Directorship schema"""
        try:
            import requests
            import os

            api_key = os.getenv('ALEPH_API_KEY', '1c0971afa4804c2aafabb125c79b275e')
            base_url = "https://aleph.occrp.org/api/2/entities"

            params = {
                "filter:schemata": "Directorship",
                "filter:properties.organization": registration_number,
                "limit": 50
            }

            if country_code:
                params["filter:countries"] = country_code.upper()

            headers = {"Authorization": f"ApiKey {api_key}"}
            response = requests.get(base_url, params=params, headers=headers, timeout=timeout)

            if not response.ok:
                return []

            data = response.json()
            directors = []

            for directorship in data.get("results", []):
                props = directorship.get("properties", {})

                # Extract director info
                director_name = props.get("director", [None])[0] if props.get("director") else None
                role = props.get("role", [None])[0] if props.get("role") else "Director"
                start_date = props.get("startDate", [None])[0] if props.get("startDate") else None
                end_date = props.get("endDate", [None])[0] if props.get("endDate") else None

                if director_name:
                    directors.append({
                        "name": director_name,
                        "position": role,
                        "start_date": start_date,
                        "end_date": end_date,
                        "source": "[AL]"
                    })

            return directors

        except Exception as e:
            return []

    def _search_edgar(
        self,
        company_name: str,
        timeout: float
    ) -> Dict[str, Any]:
        """Search SEC EDGAR for US public company filings"""
        try:
            import requests

            # Search for company CIK
            search_url = "https://www.sec.gov/cgi-bin/browse-edgar"
            params = {
                "company": company_name,
                "owner": "exclude",
                "action": "getcompany",
                "count": 10
            }

            headers = {
                "User-Agent": "Corporella-Claude contact@example.com"
            }

            response = requests.get(search_url, params=params, headers=headers, timeout=timeout)

            if not response.ok:
                return {"ok": False, "error": "EDGAR search failed", "source": "edgar"}

            # Parse CIK from response
            import re
            cik_match = re.search(r'CIK=(\d+)', response.text)

            if not cik_match:
                return {"ok": True, "source": "edgar", "results": [], "note": "No SEC filings found"}

            cik = cik_match.group(1).zfill(10)

            # Get company submissions using modern API
            submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            response = requests.get(submissions_url, headers=headers, timeout=timeout)

            if not response.ok:
                return {"ok": True, "source": "edgar", "results": [], "cik": cik}

            data = response.json()

            # Extract recent filings (last 20)
            filings = data.get("filings", {}).get("recent", {})
            results = []

            for i in range(min(20, len(filings.get("form", [])))):
                results.append({
                    "form": filings["form"][i],
                    "filing_date": filings["filingDate"][i],
                    "accession_number": filings["accessionNumber"][i],
                    "primary_document": filings.get("primaryDocument", [None] * len(filings["form"]))[i],
                    "url": f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={cik}&accession_number={filings['accessionNumber'][i]}&xbrl_type=v"
                })

            return {
                "ok": True,
                "source": "edgar",
                "cik": cik,
                "company_name": data.get("name"),
                "sic": data.get("sic"),
                "sic_description": data.get("sicDescription"),
                "ein": data.get("ein"),
                "state_of_incorporation": data.get("stateOfIncorporation"),
                "filings": results,
                "timestamp": time.time()
            }

        except Exception as e:
            return {"ok": False, "error": str(e), "source": "edgar"}

    def _search_openownership(
        self,
        company_name: str,
        timeout: float
    ) -> Dict[str, Any]:
        """Search OpenOwnership for beneficial ownership data"""
        try:
            import requests

            # Search for entities
            search_url = "https://api.openownership.org/v0.2/entities"
            params = {
                "q": company_name,
                "limit": 10
            }

            response = requests.get(search_url, params=params, timeout=timeout)

            if not response.ok:
                return {"ok": False, "error": "OpenOwnership API error", "source": "openownership"}

            data = response.json()
            entities = data.get("data", [])

            if not entities:
                return {"ok": True, "source": "openownership", "results": [], "note": "No ownership data found"}

            # For each entity, get ownership statements
            results = []
            for entity in entities[:3]:  # Limit to top 3 matches
                entity_id = entity.get("id")

                # Get ownership statements
                statements_url = f"https://api.openownership.org/v0.2/statements"
                statements_params = {
                    "entity_id": entity_id,
                    "limit": 50
                }

                statements_response = requests.get(statements_url, params=statements_params, timeout=timeout)

                if statements_response.ok:
                    statements_data = statements_response.json()

                    # Extract beneficial owners
                    beneficial_owners = []
                    for statement in statements_data.get("data", []):
                        if statement.get("statementType") == "ownershipOrControlStatement":
                            interests = statement.get("interests", [])
                            for interest in interests:
                                beneficial_owners.append({
                                    "name": statement.get("interestedParty", {}).get("name"),
                                    "type": interest.get("type"),
                                    "share": interest.get("share", {}).get("exact"),
                                    "start_date": interest.get("startDate")
                                })

                    results.append({
                        "entity_id": entity_id,
                        "name": entity.get("name"),
                        "jurisdiction": entity.get("jurisdiction_code"),
                        "identifiers": entity.get("identifiers", []),
                        "beneficial_owners": beneficial_owners,
                        "statements_count": len(statements_data.get("data", []))
                    })

            return {
                "ok": True,
                "source": "openownership",
                "results": results,
                "timestamp": time.time()
            }

        except Exception as e:
            return {"ok": False, "error": str(e), "source": "openownership"}

    def _search_linkedin(
        self,
        company_name: str,
        timeout: float
    ) -> Dict[str, Any]:
        """
        Search LinkedIn via Google site search (public data only)
        Note: This is a lightweight fallback. For production, use LinkedIn API or scraping service.
        """
        try:
            import requests
            from urllib.parse import quote

            # Use Google site search as lightweight alternative
            query = f"site:linkedin.com/company {company_name}"
            search_url = "https://www.google.com/search"
            params = {
                "q": query,
                "num": 5
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }

            response = requests.get(search_url, params=params, headers=headers, timeout=timeout)

            if not response.ok:
                return {"ok": False, "error": "LinkedIn search failed", "source": "linkedin"}

            # Extract LinkedIn company URLs from Google results
            import re
            urls = re.findall(r'https://(?:www\.)?linkedin\.com/company/([^/\s"]+)', response.text)

            results = []
            for company_slug in list(set(urls))[:3]:  # Top 3 unique results
                results.append({
                    "company_slug": company_slug,
                    "url": f"https://www.linkedin.com/company/{company_slug}",
                    "note": "Use LinkedIn API for detailed profile data"
                })

            return {
                "ok": True,
                "source": "linkedin",
                "results": results,
                "note": "Basic LinkedIn discovery via site search. Upgrade to LinkedIn API for full data.",
                "timestamp": time.time()
            }

        except Exception as e:
            return {"ok": False, "error": str(e), "source": "linkedin"}


# Usage example
if __name__ == "__main__":
    async def main():
        fetcher = GlobalCompanyFetcher()

        print("=== Searching for 'Apple Inc' ===")
        results = await fetcher.parallel_search("Apple Inc", country_code="us")

        print(f"\n✓ Results from {len(results['sources_used'])} sources")
        print(f"  Processing time: {results['processing_time']:.2f}s\n")

        for source in results['sources_used']:
            exec_time = results['execution_times'].get(source, 0)
            print(f"  ✓ {source} ({exec_time:.2f}s)")

        if results['errors']:
            print(f"\n✗ Errors from {len(results['errors'])} sources:")
            for error in results['errors']:
                print(f"  ✗ {error['source']}: {error['error']}")

        print(f"\n=== Raw Results ===")
        for result in results['raw_results']:
            source = result.get('source', 'unknown')
            print(f"\n{source}:")
            if source == "opencorporates" and result.get('companies'):
                for company in result['companies'][:2]:
                    print(f"  - {company.get('name')}")
                    print(f"    Number: {company.get('company_number')}")
                    print(f"    Jurisdiction: {company.get('jurisdiction_code')}")

    asyncio.run(main())
