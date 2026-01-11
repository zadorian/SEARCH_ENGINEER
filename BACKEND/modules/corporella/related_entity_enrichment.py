#!/usr/bin/env python3
"""
Related Entity Enrichment System
Intelligently discovers and fetches related entities based on context
Generates dynamic buttons for expanding corporate networks
"""

from typing import Dict, List, Any, Optional
import asyncio
from companies_house_api import CompaniesHouseAPI
from utils.dynamic_flow_router import flow_router
from storage.entity_graph import EntityGraph
import os

class RelatedEntityEnrichment:
    """
    Smart enrichment system that:
    1. Analyzes what we have to predict what else exists
    2. Generates buttons for network expansion
    3. Fetches related entities intelligently
    4. Uses jurisdiction context for targeted searches
    """

    def __init__(self):
        self.ch_api = CompaniesHouseAPI()
        self.entity_graph = EntityGraph()

    def generate_enrichment_buttons(
        self,
        entity: Dict[str, Any],
        focused_element: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate smart enrichment buttons based on entity context

        Args:
            entity: The company entity
            focused_element: What the user clicked on (e.g., "officer:John Smith")

        Returns:
            List of enrichment action buttons
        """
        buttons = []
        jurisdiction = entity.get("about", {}).get("jurisdiction", "").upper()

        # 1. OFFICER NETWORK EXPANSION
        officers = entity.get("officers", [])
        if officers:
            # If UK company, we can fetch all directorships via Companies House
            if jurisdiction == "GB":
                for officer in officers:
                    officer_name = officer.get("name", "")
                    if officer_name:
                        buttons.append({
                            "type": "enrichment",
                            "action": "fetch_officer_network",
                            "label": f"🔍 Find all companies for {officer_name}",
                            "officer_name": officer_name,
                            "jurisdiction": "GB",
                            "api": "companies_house",
                            "description": f"Search UK Companies House for all directorships",
                            "priority": 1
                        })

            # For any jurisdiction, offer OpenCorporates officer search
            buttons.append({
                "type": "enrichment",
                "action": "expand_all_officers",
                "label": "👥 Expand All Officers Network",
                "officers": [o.get("name") for o in officers if o.get("name")],
                "description": "Find all companies connected to these officers",
                "priority": 2
            })

        # 2. OWNERSHIP CHAIN TRAVERSAL
        parent = entity.get("ownership", {}).get("parent_company")
        if parent:
            buttons.append({
                "type": "enrichment",
                "action": "fetch_parent_details",
                "label": f"⬆️ Fetch Parent: {parent.get('name', 'Parent Company')}",
                "parent_id": parent.get("company_number"),
                "parent_name": parent.get("name"),
                "description": "Get detailed parent company information",
                "priority": 1
            })

            buttons.append({
                "type": "enrichment",
                "action": "find_sister_companies",
                "label": "🔄 Find Sister Companies",
                "parent_id": parent.get("company_number"),
                "description": "Find other subsidiaries of the parent",
                "priority": 3
            })

        # 3. ADDRESS-BASED DISCOVERY
        address = entity.get("about", {}).get("registered_address")
        if address:
            buttons.append({
                "type": "enrichment",
                "action": "find_companies_at_address",
                "label": "📍 Find Companies at Same Address",
                "address": address,
                "jurisdiction": jurisdiction,
                "description": "Discover related entities at this address",
                "priority": 4
            })

        # 4. UK-SPECIFIC ENRICHMENTS
        if jurisdiction == "GB":
            company_number = entity.get("about", {}).get("company_number")

            if company_number:
                # PSC (Beneficial Ownership) if not already fetched
                if not entity.get("ownership", {}).get("beneficial_owners"):
                    buttons.append({
                        "type": "enrichment",
                        "action": "fetch_uk_psc",
                        "label": "👤 Fetch UK Beneficial Owners (PSC)",
                        "company_number": company_number,
                        "api": "companies_house",
                        "description": "Get Persons with Significant Control data",
                        "priority": 1
                    })

                # Filing History
                buttons.append({
                    "type": "enrichment",
                    "action": "fetch_uk_filings",
                    "label": "📄 Fetch UK Filing History",
                    "company_number": company_number,
                    "api": "companies_house",
                    "description": "Get recent filings and documents",
                    "priority": 5
                })

        # 5. FINANCIAL SERVICES (if applicable)
        sic_codes = entity.get("about", {}).get("sic_codes", [])
        is_financial = any("64" in str(code) or "65" in str(code) or "66" in str(code) for code in sic_codes)

        if is_financial and jurisdiction == "GB":
            buttons.append({
                "type": "enrichment",
                "action": "check_fca_register",
                "label": "🏦 Check FCA Register",
                "company_name": entity.get("name", {}).get("value"),
                "description": "Check Financial Conduct Authority status",
                "priority": 2
            })

        # 6. FOCUSED ELEMENT ACTIONS
        if focused_element:
            element_type, element_value = focused_element.split(":", 1) if ":" in focused_element else (None, None)

            if element_type == "officer":
                # Officer-specific actions
                buttons.insert(0, {
                    "type": "enrichment",
                    "action": "deep_officer_profile",
                    "label": f"👤 Deep Profile: {element_value}",
                    "officer_name": element_value,
                    "jurisdiction": jurisdiction,
                    "description": "Complete officer investigation",
                    "priority": 0
                })

            elif element_type == "subsidiary":
                # Subsidiary-specific actions
                buttons.insert(0, {
                    "type": "enrichment",
                    "action": "fetch_subsidiary_details",
                    "label": f"📊 Expand: {element_value}",
                    "subsidiary_name": element_value,
                    "description": "Get full subsidiary information",
                    "priority": 0
                })

        # 7. NETWORK GRAPH EXPANSION
        buttons.append({
            "type": "enrichment",
            "action": "expand_network_graph",
            "label": "🕸️ Expand Full Network (1 degree)",
            "entity_id": entity.get("_db_id"),
            "depth": 1,
            "description": "Fetch all directly connected entities",
            "priority": 6
        })

        # Sort by priority
        return sorted(buttons, key=lambda x: x.get("priority", 99))

    async def execute_enrichment(
        self,
        action: Dict[str, Any],
        entity: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute an enrichment action

        Args:
            action: The enrichment action to execute
            entity: The current entity context

        Returns:
            Enrichment results
        """
        action_type = action.get("action")

        if action_type == "fetch_officer_network":
            return await self._fetch_officer_network(
                action.get("officer_name"),
                action.get("jurisdiction")
            )

        elif action_type == "fetch_uk_psc":
            return await self._fetch_uk_psc(action.get("company_number"))

        elif action_type == "fetch_uk_filings":
            return await self._fetch_uk_filings(action.get("company_number"))

        elif action_type == "find_companies_at_address":
            return await self._find_companies_at_address(
                action.get("address"),
                action.get("jurisdiction")
            )

        elif action_type == "expand_all_officers":
            return await self._expand_all_officers(action.get("officers"))

        elif action_type == "deep_officer_profile":
            return await self._deep_officer_profile(
                action.get("officer_name"),
                action.get("jurisdiction")
            )

        elif action_type == "expand_network_graph":
            return await self._expand_network_graph(
                action.get("entity_id"),
                action.get("depth", 1)
            )

        else:
            return {"error": f"Unknown enrichment action: {action_type}"}

    async def _fetch_officer_network(
        self,
        officer_name: str,
        jurisdiction: str
    ) -> Dict[str, Any]:
        """Fetch all companies where a person is an officer"""

        results = {
            "officer_name": officer_name,
            "jurisdiction": jurisdiction,
            "companies": [],
            "source": None
        }

        if jurisdiction == "GB":
            # Use Companies House officer appointments endpoint
            # First need to search for the officer to get their ID
            try:
                # Search for officer
                officer_search = self.ch_api.search_officers(officer_name)

                if officer_search and officer_search.get('items'):
                    # Get first matching officer
                    officer = officer_search['items'][0]
                    officer_id = officer.get('links', {}).get('self', '').split('/')[-1]

                    if officer_id:
                        # Get officer appointments
                        appointments = self.ch_api.get_officer_appointments(officer_id)

                        if appointments and appointments.get('items'):
                            for appointment in appointments['items']:
                                company_info = appointment.get('appointed_to', {})
                                results['companies'].append({
                                    "company_name": company_info.get('company_name'),
                                    "company_number": company_info.get('company_number'),
                                    "company_status": company_info.get('company_status'),
                                    "role": appointment.get('officer_role'),
                                    "appointed_on": appointment.get('appointed_on'),
                                    "resigned_on": appointment.get('resigned_on')
                                })
                            results['source'] = "companies_house"
                            results['total_found'] = len(results['companies'])

            except Exception as e:
                results['error'] = str(e)

        else:
            # For non-UK, use OpenCorporates officer search
            from fetcher import GlobalCompanyFetcher
            fetcher = GlobalCompanyFetcher()

            try:
                # Search via OpenCorporates
                oc_results = await fetcher.search_opencorporates_officers(officer_name, jurisdiction)
                if oc_results.get('ok'):
                    officers = oc_results.get('results', {}).get('officers', [])

                    for officer in officers[:5]:  # Limit to first 5
                        # Each officer result includes company info
                        company = officer.get('company', {})
                        results['companies'].append({
                            "company_name": company.get('name'),
                            "company_number": company.get('company_number'),
                            "jurisdiction": company.get('jurisdiction_code'),
                            "role": officer.get('position'),
                            "status": officer.get('status'),
                            "start_date": officer.get('start_date'),
                            "end_date": officer.get('end_date')
                        })

                    results['source'] = "opencorporates"
                    results['total_found'] = len(results['companies'])

            except Exception as e:
                results['error'] = str(e)

        return results

    async def _fetch_uk_psc(self, company_number: str) -> Dict[str, Any]:
        """Fetch UK PSC (beneficial ownership) data"""

        if not self.ch_api.ch_api_key:
            return {"error": "Companies House API key not configured"}

        psc_data = self.ch_api.get_psc_data(company_number)

        return {
            "source": "companies_house",
            "psc_data": psc_data,
            "count": len(psc_data) if psc_data else 0
        }

    async def _fetch_uk_filings(self, company_number: str) -> Dict[str, Any]:
        """Fetch UK filing history"""

        if not self.ch_api.ch_api_key:
            return {"error": "Companies House API key not configured"}

        filings = self.ch_api.get_filing_history(company_number, items_per_page=10)

        return {
            "source": "companies_house",
            "filings": filings,
            "count": len(filings) if filings else 0
        }

    async def _find_companies_at_address(
        self,
        address: str,
        jurisdiction: str
    ) -> Dict[str, Any]:
        """Find all companies registered at the same address"""

        results = {
            "address": address,
            "jurisdiction": jurisdiction,
            "companies": [],
            "source": None
        }

        if jurisdiction == "GB":
            # For UK, can search via Companies House advanced search
            # Or via OpenCorporates with address filter
            from fetcher import GlobalCompanyFetcher
            fetcher = GlobalCompanyFetcher()

            try:
                # Extract postcode from address if present
                import re
                postcode_match = re.search(r'[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d{1,2}[A-Z]{2}', address)

                if postcode_match:
                    postcode = postcode_match.group()

                    # Search via OpenCorporates with postcode filter
                    oc_params = {
                        'jurisdiction_code': 'gb',
                        'postal_code': postcode,
                        'per_page': 30
                    }

                    oc_results = await fetcher.search_opencorporates("", **oc_params)

                    if oc_results.get('ok'):
                        companies = oc_results.get('results', {}).get('companies', [])

                        for company in companies:
                            # Filter to exact address match if possible
                            company_address = company.get('company', {}).get('registered_address_in_full', '')

                            # Basic address similarity check
                            if postcode in company_address:
                                results['companies'].append({
                                    "company_name": company.get('company', {}).get('name'),
                                    "company_number": company.get('company', {}).get('company_number'),
                                    "status": company.get('company', {}).get('current_status'),
                                    "address": company_address,
                                    "match_type": "postcode"
                                })

                        results['source'] = "opencorporates"
                        results['total_found'] = len(results['companies'])

            except Exception as e:
                results['error'] = str(e)

        else:
            # For non-UK, use OpenCorporates with address search
            from fetcher import GlobalCompanyFetcher
            fetcher = GlobalCompanyFetcher()

            try:
                # Extract key address components
                address_parts = address.split(',')
                street = address_parts[0].strip() if address_parts else ""

                oc_params = {
                    'jurisdiction_code': jurisdiction.lower(),
                    'registered_address': street,
                    'per_page': 20
                }

                oc_results = await fetcher.search_opencorporates("", **oc_params)

                if oc_results.get('ok'):
                    companies = oc_results.get('results', {}).get('companies', [])

                    for company in companies[:10]:
                        results['companies'].append({
                            "company_name": company.get('company', {}).get('name'),
                            "company_number": company.get('company', {}).get('company_number'),
                            "jurisdiction": company.get('company', {}).get('jurisdiction_code'),
                            "status": company.get('company', {}).get('current_status'),
                            "address": company.get('company', {}).get('registered_address_in_full')
                        })

                    results['source'] = "opencorporates"
                    results['total_found'] = len(results['companies'])

            except Exception as e:
                results['error'] = str(e)

        return results

    async def _expand_all_officers(
        self,
        officer_names: List[str]
    ) -> Dict[str, Any]:
        """Expand network for all officers"""

        results = {}
        for name in officer_names:
            # Would fetch each officer's other directorships
            results[name] = {
                "companies": [],
                "message": "Bulk officer expansion to be implemented"
            }

        return results

    async def _deep_officer_profile(
        self,
        officer_name: str,
        jurisdiction: str
    ) -> Dict[str, Any]:
        """Create comprehensive officer profile"""

        profile = {
            "name": officer_name,
            "jurisdiction": jurisdiction,
            "current_directorships": [],
            "past_directorships": [],
            "sanctions_check": None,
            "pep_check": None,
            "total_companies": 0,
            "sources_checked": []
        }

        # 1. Get officer network (all companies)
        network_results = await self._fetch_officer_network(officer_name, jurisdiction)

        if network_results and not network_results.get('error'):
            companies = network_results.get('companies', [])

            for company in companies:
                if company.get('resigned_on') or company.get('end_date'):
                    profile['past_directorships'].append(company)
                else:
                    profile['current_directorships'].append(company)

            profile['total_companies'] = len(companies)
            profile['sources_checked'].append(network_results.get('source'))

        # 2. Check sanctions (via OCCRP Aleph)
        from fetcher import GlobalCompanyFetcher
        fetcher = GlobalCompanyFetcher()

        try:
            # Search in Aleph for sanctions/PEP data
            aleph_results = await fetcher.search_aleph(
                officer_name,
                {"schema": "Person", "countries": [jurisdiction]}
            )

            if aleph_results.get('ok'):
                entities = aleph_results.get('results', [])

                # Check for sanctions/PEP indicators
                for entity in entities:
                    properties = entity.get('properties', {})
                    if 'sanction' in str(entity).lower():
                        profile['sanctions_check'] = {
                            "found": True,
                            "entity": entity.get('caption'),
                            "datasets": entity.get('datasets', [])
                        }
                    if 'pep' in str(entity).lower() or 'politically' in str(entity).lower():
                        profile['pep_check'] = {
                            "found": True,
                            "entity": entity.get('caption'),
                            "datasets": entity.get('datasets', [])
                        }

                profile['sources_checked'].append('aleph')

        except Exception as e:
            profile['aleph_error'] = str(e)

        # 3. Add profile statistics
        profile['statistics'] = {
            "active_directorships": len(profile['current_directorships']),
            "resigned_directorships": len(profile['past_directorships']),
            "jurisdictions": list(set(c.get('jurisdiction', jurisdiction)
                                    for c in profile['current_directorships'] + profile['past_directorships']
                                    if c.get('jurisdiction'))),
            "industries": []  # Could be enriched with SIC codes
        }

        # 4. If UK, add specific UK checks
        if jurisdiction == "GB" and profile['current_directorships']:
            # Could add disqualification checks, etc.
            profile['uk_specific'] = {
                "disqualified": False,  # Would need to check disqualified directors register
                "total_uk_companies": len([c for c in profile['current_directorships']
                                          if c.get('jurisdiction') == 'GB'])
            }

        return profile

    async def _expand_network_graph(
        self,
        entity_id: str,
        depth: int
    ) -> Dict[str, Any]:
        """Expand the network graph to specified depth"""

        # Use entity graph to find connected entities
        relationships = self.entity_graph.get_node_relationships(entity_id)

        expansion_targets = []
        for rel in relationships:
            if rel.get("target_type") == "company":
                expansion_targets.append({
                    "id": rel.get("target_id"),
                    "name": rel.get("target_name"),
                    "relationship": rel.get("relationship_type")
                })

        return {
            "entity_id": entity_id,
            "depth_requested": depth,
            "entities_found": expansion_targets,
            "message": f"Found {len(expansion_targets)} connected entities"
        }

    def predict_data_sources(
        self,
        entity: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """
        Predict what data sources likely have information
        based on entity characteristics

        Returns:
            List of predicted data sources with confidence
        """
        predictions = []
        jurisdiction = entity.get("about", {}).get("jurisdiction", "").upper()

        # UK-specific predictions
        if jurisdiction == "GB":
            predictions.append({
                "source": "companies_house",
                "confidence": "high",
                "reason": "UK company - official registry"
            })

            # Check if financial
            sic_codes = entity.get("about", {}).get("sic_codes", [])
            if any("64" in str(c) or "65" in str(c) or "66" in str(c) for c in sic_codes):
                predictions.append({
                    "source": "fca_register",
                    "confidence": "high",
                    "reason": "Financial services SIC codes detected"
                })

            # Check for property mentions
            if "property" in str(entity).lower() or "real estate" in str(entity).lower():
                predictions.append({
                    "source": "land_registry",
                    "confidence": "medium",
                    "reason": "Property/real estate keywords found"
                })

        # Global predictions
        if entity.get("officers"):
            predictions.append({
                "source": "opencorporates_officers",
                "confidence": "high",
                "reason": "Can search for officers' other companies"
            })

        return predictions


# Singleton instance
enrichment_engine = RelatedEntityEnrichment()