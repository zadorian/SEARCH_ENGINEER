#!/usr/bin/env python3
"""
ULTIMATE CORPORATE SEARCH WITH GPT-4.1-NANO
ONE FILE THAT DOES EVERYTHING INCLUDING COMPANIES HOUSE
"""

import os
import sys
import json
import asyncio
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional
import openai
from pathlib import Path
import logging
import base64
from edgar_integration import EdgarSearchIntegration

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ API CONFIGURATION ============
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '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')
OPENCORPORATES_API_KEY = 'UvjlNXuBiIeNymveADRR'
OCCRP_API_KEY = '1c0971afa4804c2aafabb125c79b275e'
OPENSANCTIONS_API_KEY = '1d6a91c9f96eb9594a3bb81cdcc37bd7'
COMPANIES_HOUSE_API_KEY = os.getenv('CH_API_KEY', '13ed03e4-3d0b-447e-95c2-b2f397cf1e04')  # Add your key here or set CH_API_KEY env var

# HARD-LOCKED MODEL - DO NOT CHANGE
MODEL_GPT_41_NANO = "gpt-4.1-nano-2025-04-14"

class UltimateCorporateSearch:
    """
    THE ONE CLASS THAT SEARCHES ALL DATABASES AND CONSOLIDATES WITH GPT-4.1-NANO
    """
    
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
        self.results_dir = Path("ultimate_search_results")
        self.results_dir.mkdir(exist_ok=True)
        self.edgar_client = EdgarSearchIntegration()
        
    def search_and_consolidate(self, company_name: str) -> Dict[str, Any]:
        """
        MAIN FUNCTION - Search all databases and consolidate with GPT-4.1-nano
        """
        print(f"\n{'='*80}")
        print(f"ULTIMATE CORPORATE SEARCH: {company_name}")
        print(f"Model: {MODEL_GPT_41_NANO}")
        print(f"{'='*80}\n")
        
        # STEP 1: Search all databases
        all_results = {}
        
        # 1. OpenCorporates
        print("1. Searching OpenCorporates...")
        oc_results = self._search_opencorporates(company_name)
        if oc_results:
            all_results['opencorporates'] = oc_results
            print(f"   ✓ Found {oc_results.get('total_count', 0)} companies")
        
        # 2. OCCRP Aleph
        print("\n2. Searching OCCRP Aleph...")
        aleph_results = self._search_occrp_aleph(company_name)
        if aleph_results:
            all_results['occrp_aleph'] = aleph_results
            print(f"   ✓ Found {aleph_results.get('total', 0)} entities")
        
        # 3. OpenSanctions
        print("\n3. Searching OpenSanctions...")
        sanctions_results = self._search_opensanctions(company_name)
        if sanctions_results:
            all_results['opensanctions'] = sanctions_results
            print(f"   ✓ Found {sanctions_results.get('total', 0)} matches")
        
        # 4. Companies House UK
        print("\n4. Searching UK Companies House...")
        ch_results = self._search_companies_house(company_name)
        if ch_results:
            all_results['companies_house'] = ch_results
            print(f"   ✓ Found {ch_results.get('total_results', 0)} UK companies")
            if ch_results.get('psc_data'):
                print(f"   ✓ Found PSC (beneficial ownership) data")
        
        # 5. Offshore Leaks (if CSV files available)
        print("\n5. Checking Offshore Leaks Database...")
        oldb_results = self._search_offshore_leaks(company_name)
        if oldb_results:
            all_results['offshore_leaks'] = oldb_results
            print(f"   ✓ Found {len(oldb_results)} entities")
        
        # 6. EDGAR (SEC Filings for US Companies)
        print("\n6. Searching EDGAR (SEC Filings)...")
        edgar_results = self._search_edgar(company_name)
        if edgar_results:
            all_results['edgar'] = edgar_results
            print(f"   ✓ Found {edgar_results.get('result_count', 0)} SEC filings")
            if edgar_results.get('recent_filings'):
                print(f"   ✓ Most recent: {edgar_results['recent_filings'][0].get('Filing Type', 'Unknown')} on {edgar_results['recent_filings'][0].get('Filed', 'Unknown')}")
        
        # STEP 2: Consolidate with GPT-4.1-nano
        print(f"\n{'='*80}")
        print(f"CONSOLIDATING WITH GPT-4.1-NANO...")
        print(f"{'='*80}\n")
        
        consolidated = self._consolidate_with_gpt41nano(company_name, all_results)
        
        # STEP 3: Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{company_name.replace(' ', '_')}_{timestamp}_consolidated.json"
        filepath = self.results_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(consolidated, f, indent=2)
        
        print(f"\n✅ Results saved to: {filepath}")
        
        # STEP 4: Print summary
        self._print_summary(consolidated)
        
        return consolidated
    
    def _search_opencorporates(self, company_name: str) -> Dict[str, Any]:
        """Search OpenCorporates API"""
        try:
            url = "https://api.opencorporates.com/v0.4/companies/search"
            params = {
                'q': company_name,
                'api_token': OPENCORPORATES_API_KEY,
                'per_page': 30
            }
            
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', {})
                
                # Extract key data
                companies = []
                for company in results.get('companies', []):
                    co = company.get('company', {})
                    companies.append({
                        'name': co.get('name'),
                        'jurisdiction': co.get('jurisdiction_code'),
                        'company_number': co.get('company_number'),
                        'incorporation_date': co.get('incorporation_date'),
                        'status': co.get('current_status'),
                        'address': co.get('registered_address_in_full'),
                        'industry_codes': co.get('industry_codes', [])
                    })
                
                return {
                    'total_count': results.get('total_count', 0),
                    'companies': companies
                }
                
        except Exception as e:
            logger.error(f"OpenCorporates error: {e}")
        return None
    
    def _search_occrp_aleph(self, company_name: str) -> Dict[str, Any]:
        """Search OCCRP Aleph API"""
        try:
            url = "https://aleph.occrp.org/api/2/entities"
            headers = {'Authorization': f'ApiKey {OCCRP_API_KEY}'}
            params = {
                'q': company_name,
                'filter:schema': 'Company',
                'limit': 30
            }
            
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                
                entities = []
                for result in data.get('results', []):
                    props = result.get('properties', {})
                    entities.append({
                        'id': result.get('id'),
                        'name': self._get_prop(props, 'name'),
                        'schema': result.get('schema'),
                        'countries': self._get_prop(props, 'country'),
                        'dates': self._get_prop(props, 'date'),
                        'aliases': self._get_prop(props, 'alias'),
                        'topics': self._get_prop(props, 'topics')
                    })
                
                return {
                    'total': data.get('total', 0),
                    'entities': entities
                }
                
        except Exception as e:
            logger.error(f"OCCRP Aleph error: {e}")
        return None
    
    def _search_opensanctions(self, company_name: str) -> Dict[str, Any]:
        """Search OpenSanctions API"""
        try:
            url = "https://api.opensanctions.org/search/default"
            headers = {'Authorization': f'Bearer {OPENSANCTIONS_API_KEY}'}
            params = {
                'q': company_name,
                'schema': 'Company',
                'limit': 30
            }
            
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                
                sanctions = []
                for result in data.get('results', []):
                    sanctions.append({
                        'id': result.get('id'),
                        'caption': result.get('caption'),
                        'schema': result.get('schema'),
                        'datasets': result.get('datasets', []),
                        'first_seen': result.get('first_seen'),
                        'last_seen': result.get('last_seen'),
                        'target': result.get('target', False)
                    })
                
                return {
                    'total': data.get('total', 0),
                    'sanctions': sanctions
                }
                
        except Exception as e:
            logger.error(f"OpenSanctions error: {e}")
        return None
    
    def _search_companies_house(self, company_name: str) -> Dict[str, Any]:
        """Search UK Companies House API"""
        if not COMPANIES_HOUSE_API_KEY:
            logger.warning("Companies House API key not configured")
            return None
            
        try:
            # Search for companies
            url = "https://api.company-information.service.gov.uk/search/companies"
            auth = base64.b64encode(f"{COMPANIES_HOUSE_API_KEY}:".encode('utf-8')).decode('utf-8')
            headers = {'Authorization': f'Basic {auth}'}
            params = {
                'q': company_name,
                'items_per_page': 20
            }
            
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                
                companies = []
                psc_data = []
                
                # Process each company found
                for item in data.get('items', [])[:5]:  # Limit to top 5
                    company_number = item.get('company_number')
                    company_info = {
                        'company_name': item.get('title'),
                        'company_number': company_number,
                        'company_status': item.get('company_status'),
                        'company_type': item.get('company_type'),
                        'date_of_creation': item.get('date_of_creation'),
                        'registered_office_address': item.get('address', {}),
                        'sic_codes': []
                    }
                    
                    # Get detailed company profile
                    profile_url = f"https://api.company-information.service.gov.uk/company/{company_number}"
                    profile_response = requests.get(profile_url, headers=headers)
                    if profile_response.status_code == 200:
                        profile = profile_response.json()
                        company_info['sic_codes'] = profile.get('sic_codes', [])
                        company_info['previous_company_names'] = profile.get('previous_company_names', [])
                        company_info['confirmation_statement'] = profile.get('confirmation_statement', {})
                    
                    # Get PSC (Persons with Significant Control) data
                    psc_url = f"https://api.company-information.service.gov.uk/company/{company_number}/persons-with-significant-control"
                    psc_response = requests.get(psc_url, headers=headers)
                    if psc_response.status_code == 200:
                        psc_result = psc_response.json()
                        for psc in psc_result.get('items', []):
                            psc_data.append({
                                'company_number': company_number,
                                'name': psc.get('name'),
                                'nationality': psc.get('nationality'),
                                'country_of_residence': psc.get('country_of_residence'),
                                'notified_on': psc.get('notified_on'),
                                'natures_of_control': psc.get('natures_of_control', []),
                                'kind': psc.get('kind'),
                                'identification': psc.get('identification', {})
                            })
                    
                    # Get officers
                    officers_url = f"https://api.company-information.service.gov.uk/company/{company_number}/officers"
                    officers_response = requests.get(officers_url, headers=headers)
                    if officers_response.status_code == 200:
                        officers_result = officers_response.json()
                        company_info['officers'] = []
                        for officer in officers_result.get('items', [])[:10]:  # Limit to 10 officers
                            company_info['officers'].append({
                                'name': officer.get('name'),
                                'officer_role': officer.get('officer_role'),
                                'appointed_on': officer.get('appointed_on'),
                                'nationality': officer.get('nationality'),
                                'country_of_residence': officer.get('country_of_residence'),
                                'occupation': officer.get('occupation')
                            })
                    
                    companies.append(company_info)
                
                return {
                    'total_results': data.get('total_results', 0),
                    'companies': companies,
                    'psc_data': psc_data
                }
                
        except Exception as e:
            logger.error(f"Companies House error: {e}")
        return None
    
    def _search_offshore_leaks(self, company_name: str) -> List[Dict]:
        """Search Offshore Leaks CSV files if available"""
        # This would search local CSV files from ICIJ Offshore Leaks Database
        # For now, returning empty - you can implement CSV search if needed
        return []
    
    def _search_edgar(self, company_name: str) -> Dict[str, Any]:
        """Search EDGAR SEC filings"""
        try:
            # Search for all filings from the past 3 years
            results = self.edgar_client.search_company_filings(
                company_name=company_name,
                filing_types=['10-K', '10-Q', '8-K', 'DEF 14A', '20-F', '40-F'],
                years_back=3
            )
            
            if results.get('success') and results.get('results'):
                filings = results.get('results', [])
                
                # Group filings by type
                filing_groups = {}
                for filing in filings:
                    form_type = filing.get('Filing Type', 'Unknown')
                    if form_type not in filing_groups:
                        filing_groups[form_type] = []
                    filing_groups[form_type].append(filing)
                
                # Extract key insights from recent filings
                insights = self._extract_edgar_insights(filings[:10])  # Analyze top 10
                
                # Get recent material events (8-K filings)
                material_events = [f for f in filings if f.get('Filing Type', '').startswith('8-K')][:5]
                
                return {
                    'result_count': len(filings),
                    'recent_filings': filings[:5],  # Most recent 5
                    'filing_groups': filing_groups,
                    'material_events': material_events,
                    'insights': insights,
                    'search_details': {
                        'company_name': company_name,
                        'years_back': 3,
                        'filing_types': ['10-K', '10-Q', '8-K', 'DEF 14A', '20-F', '40-F']
                    }
                }
            
            return None
            
        except Exception as e:
            logger.error(f"EDGAR search error: {e}")
            return None
    
    def _extract_edgar_insights(self, filings: List[Dict]) -> Dict[str, Any]:
        """Extract key insights from EDGAR filings"""
        insights = {
            'filing_frequency': len(filings),
            'latest_annual_report': None,
            'latest_quarterly_report': None,
            'recent_events': [],
            'proxy_statements': [],
            'foreign_filer': False
        }
        
        for filing in filings:
            form_type = filing.get('Filing Type', '')
            
            # Annual reports
            if form_type in ['10-K', '20-F', '40-F']:
                if not insights['latest_annual_report']:
                    insights['latest_annual_report'] = {
                        'form': form_type,
                        'date': filing.get('Filed'),
                        'entity': filing.get('Entity Name')
                    }
                if form_type in ['20-F', '40-F']:
                    insights['foreign_filer'] = True
            
            # Quarterly reports
            elif form_type == '10-Q':
                if not insights['latest_quarterly_report']:
                    insights['latest_quarterly_report'] = {
                        'date': filing.get('Filed'),
                        'entity': filing.get('Entity Name')
                    }
            
            # Material events
            elif form_type.startswith('8-K'):
                insights['recent_events'].append({
                    'date': filing.get('Filed'),
                    'form': form_type
                })
            
            # Proxy statements
            elif 'DEF' in form_type:
                insights['proxy_statements'].append({
                    'date': filing.get('Filed'),
                    'form': form_type
                })
        
        return insights
    
    def _consolidate_with_gpt41nano(self, company_name: str, all_results: Dict) -> Dict[str, Any]:
        """Consolidate all results using GPT-4.1-nano"""
        
        # Create consolidation prompt
        prompt = f"""You are consolidating corporate intelligence from multiple databases for: {company_name}

DATA FROM ALL SOURCES:
{json.dumps(all_results, indent=2)[:10000]}  # Limit size

CONSOLIDATION REQUIREMENTS:

1. BENEFICIAL OWNERSHIP (HIGHEST PRIORITY):
   - Identify ALL ultimate beneficial owners with percentages
   - UK Companies House PSC data is AUTHORITATIVE for UK companies
   - Extract ownership percentages from "natures_of_control" field
   - Map complete ownership chains
   - Note any opacity or complex structures

2. RELATED ENTITIES (HIGH PRIORITY):
   - Parent companies
   - Subsidiaries  
   - Sister companies
   - Previous company names
   - Extract from OpenCorporates and Companies House data

3. KEY INDIVIDUALS (HIGH PRIORITY):  
   - Current directors and officers from Companies House
   - PSC individuals with their control percentages
   - Their nationalities and residencies
   - Related individuals from OCCRP data
   - Any sanctions connections

4. REVENUE/FINANCIAL (HIGH PRIORITY):
   - Latest revenue figures with year
   - Financial trends
   - SIC codes and what they mean
   - Any financial red flags
   - SEC filing status from EDGAR
   - Latest 10-K/10-Q dates
   - Foreign filer status (20-F/40-F)

5. RISK ASSESSMENT:
   - Sanctions matches (critical)
   - Offshore connections
   - Regulatory issues
   - Complex ownership structures
   - Multiple companies at same address
   - Foreign PSCs or officers

OUTPUT STRUCTURE (JSON):
{{
  "company_name": "string",
  "consolidated_status": "Active/Inactive/Mixed",
  "primary_jurisdiction": "string",
  "uk_company_number": "string if UK company",
  "beneficial_ownership": {{
    "ultimate_owners": [{{
      "name": "string",
      "percentage": "number or string",
      "source": "which database",
      "confidence": "high/medium/low",
      "natures_of_control": ["from Companies House PSC"]
    }}],
    "ownership_structure": "description of chain",
    "transparency_level": "transparent/opaque/complex"
  }},
  "related_entities": {{
    "parent_companies": [...],
    "subsidiaries": [...],
    "affiliates": [...],
    "previous_names": [...]
  }},
  "key_individuals": {{
    "directors": [{{
      "name": "string",
      "role": "string",
      "appointed": "date",
      "nationality": "string",
      "country_of_residence": "string"
    }}],
    "officers": [...],
    "pscs": [...],
    "other_related": [...]
  }},
  "financial_data": {{
    "sic_codes": [...],
    "latest_revenue": {{...}},
    "trends": "string",
    "sec_filings": {{
      "is_sec_filer": "boolean",
      "latest_10k_date": "date or null",
      "latest_10q_date": "date or null",
      "filing_frequency": "number",
      "foreign_filer": "boolean",
      "material_events_count": "number"
    }}
  }},
  "risk_assessment": {{
    "overall_risk": "high/medium/low",
    "risk_factors": [...],
    "sanctions_exposure": "none/direct/indirect",
    "red_flags": [...]
  }},
  "data_sources": {{
    "primary_sources": [...],
    "data_quality": "high/medium/low",
    "gaps_identified": [...]
  }}
}}

Be precise. Extract actual names and percentages. UK Companies House PSC data is the most authoritative for beneficial ownership."""

        try:
            # Call GPT-4.1-nano with structured output
            response = self.openai_client.chat.completions.create(
                model=MODEL_GPT_41_NANO,
                messages=[
                    {"role": "system", "content": "You are a corporate intelligence analyst. Consolidate data precisely."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=4000
            )
            
            consolidated = json.loads(response.choices[0].message.content)
            
            # Add metadata
            consolidated['consolidation_metadata'] = {
                'model_used': MODEL_GPT_41_NANO,
                'timestamp': datetime.now().isoformat(),
                'sources_searched': list(all_results.keys()),
                'total_raw_results': sum(
                    len(v.get('companies', v.get('entities', v.get('sanctions', v.get('psc_data', [])))))
                    for v in all_results.values() if isinstance(v, dict)
                )
            }
            
            # Add raw results for reference
            consolidated['raw_search_results'] = all_results
            
            return consolidated
            
        except Exception as e:
            logger.error(f"GPT-4.1-nano consolidation error: {e}")
            # Return basic structure on error
            return {
                'error': str(e),
                'company_name': company_name,
                'raw_results': all_results,
                'consolidation_metadata': {
                    'model_used': 'ERROR',
                    'timestamp': datetime.now().isoformat()
                }
            }
    
    def _get_prop(self, props: Dict, key: str) -> Any:
        """Extract property from OCCRP format"""
        value = props.get(key, '')
        if isinstance(value, list):
            return value[0] if value else ''
        return value
    
    def _print_summary(self, consolidated: Dict):
        """Print a summary of the consolidated results"""
        print(f"\n{'='*80}")
        print("CONSOLIDATED INTELLIGENCE SUMMARY")
        print(f"{'='*80}\n")
        
        print(f"Company: {consolidated.get('company_name', 'Unknown')}")
        print(f"Status: {consolidated.get('consolidated_status', 'Unknown')}")
        print(f"Jurisdiction: {consolidated.get('primary_jurisdiction', 'Unknown')}")
        if consolidated.get('uk_company_number'):
            print(f"UK Company Number: {consolidated['uk_company_number']}")
        
        # Beneficial Ownership
        bo = consolidated.get('beneficial_ownership', {})
        if bo.get('ultimate_owners'):
            print("\n📊 BENEFICIAL OWNERSHIP:")
            for owner in bo['ultimate_owners']:
                print(f"  • {owner['name']} ({owner.get('percentage', 'Unknown')}%) - {owner['source']}")
                if owner.get('natures_of_control'):
                    print(f"    Control: {', '.join(owner['natures_of_control'])}")
            print(f"  Transparency: {bo.get('transparency_level', 'Unknown')}")
        
        # Key Individuals
        individuals = consolidated.get('key_individuals', {})
        if individuals.get('pscs'):
            print("\n👤 PERSONS WITH SIGNIFICANT CONTROL (UK):")
            for psc in individuals['pscs'][:5]:
                print(f"  • {psc.get('name', 'Unknown')} - {psc.get('nationality', 'Unknown')}")
        
        # Financial Data & SEC Filings
        financial = consolidated.get('financial_data', {})
        sec_data = financial.get('sec_filings', {})
        if sec_data and sec_data.get('is_sec_filer'):
            print("\n📊 SEC FILINGS (EDGAR):")
            print(f"  Status: {'Foreign Filer' if sec_data.get('foreign_filer') else 'Domestic Filer'}")
            if sec_data.get('latest_10k_date'):
                print(f"  Latest 10-K: {sec_data['latest_10k_date']}")
            if sec_data.get('latest_10q_date'):
                print(f"  Latest 10-Q: {sec_data['latest_10q_date']}")
            if sec_data.get('material_events_count'):
                print(f"  Recent Material Events (8-K): {sec_data['material_events_count']}")
        
        # Risk Assessment
        risk = consolidated.get('risk_assessment', {})
        if risk:
            print(f"\n⚠️ RISK ASSESSMENT: {risk.get('overall_risk', 'Unknown').upper()}")
            if risk.get('sanctions_exposure') != 'none':
                print(f"  🚨 SANCTIONS EXPOSURE: {risk['sanctions_exposure']}")
            if risk.get('red_flags'):
                print("  Red Flags:")
                for flag in risk['red_flags']:
                    print(f"    - {flag}")
        
        # Data Quality
        sources = consolidated.get('data_sources', {})
        if sources:
            print(f"\n📋 DATA QUALITY: {sources.get('data_quality', 'Unknown')}")
            print(f"  Sources: {', '.join(sources.get('primary_sources', []))}")
            if sources.get('gaps_identified'):
                print("  Data Gaps:")
                for gap in sources['gaps_identified']:
                    print(f"    - {gap}")
        
        print(f"\n{'='*80}")


def main():
    """Run the ultimate corporate search"""
    print("\n🚀 ULTIMATE CORPORATE SEARCH WITH GPT-4.1-NANO")
    print("Searches: OpenCorporates, OCCRP Aleph, OpenSanctions, Companies House UK, EDGAR SEC, Offshore Leaks")
    print("Consolidation: GPT-4.1-nano (gpt-4.1-nano-2025-04-14)")
    
    if not COMPANIES_HOUSE_API_KEY:
        print("\n⚠️  WARNING: Companies House API key not set!")
        print("   Set CH_API_KEY environment variable or edit the script")
    
    searcher = UltimateCorporateSearch()
    
    while True:
        print("\n" + "="*80)
        company_name = input("Enter company name (or 'quit' to exit): ").strip()
        
        if company_name.lower() == 'quit':
            break
            
        if not company_name:
            print("❌ Company name cannot be empty")
            continue
        
        try:
            results = searcher.search_and_consolidate(company_name)
            
            # Ask if user wants to see raw results
            show_raw = input("\nShow raw search results? (y/n): ").strip().lower()
            if show_raw == 'y':
                print("\n" + "="*80)
                print("RAW SEARCH RESULTS:")
                print("="*80)
                print(json.dumps(results.get('raw_search_results', {}), indent=2)[:5000])
                
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            logger.error(f"Search error: {e}", exc_info=True)
    
    print("\n👋 Goodbye!")


if __name__ == "__main__":
    main()
