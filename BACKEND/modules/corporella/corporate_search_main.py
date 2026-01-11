#!/usr/bin/env python3
"""
Corporate Search - Main Consolidated Application
A unified interface for all corporate search tools and data sources
"""

import os
import sys
import json
import asyncio
import requests
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging
from dataclasses import dataclass
from enum import Enum

# Add project paths
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent / "EDGAR-main"))
sys.path.append(str(Path(__file__).parent / "Country_Search"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Available data sources"""
    EDGAR = "SEC EDGAR (US Public Companies)"
    OPENCORPORATES = "OpenCorporates (Global)"
    COMPANIES_HOUSE = "UK Companies House"
    OCCRP_ALEPH = "OCCRP Aleph (Investigative)"
    OPENSANCTIONS = "OpenSanctions (Sanctions/PEPs)"
    ALL = "All Sources"


@dataclass
class SearchResult:
    """Unified search result structure"""
    source: str
    company_name: str
    jurisdiction: Optional[str] = None
    registration_number: Optional[str] = None
    status: Optional[str] = None
    incorporation_date: Optional[str] = None
    officers: Optional[List[Dict]] = None
    filings: Optional[List[Dict]] = None
    sanctions_info: Optional[Dict] = None  # Added for sanctions data
    raw_data: Optional[Dict] = None
    error: Optional[str] = None


class CorporateSearchSystem:
    """Main consolidated corporate search system"""
    
    def __init__(self):
        """Initialize all search modules"""
        self.results_dir = Path("search_results")
        self.results_dir.mkdir(exist_ok=True)
        
        # Initialize modules (with error handling for missing dependencies)
        self._init_modules()
        
    def _init_modules(self):
        """Initialize search modules with error handling"""
        # EDGAR
        try:
            from edgar_integration import EdgarSearchIntegration
            self.edgar = EdgarSearchIntegration()
            self.edgar_available = True
        except Exception as e:
            logger.warning(f"EDGAR module not available: {e}")
            self.edgar_available = False
        
        # OpenCorporates
        try:
            from opencorporates_main import OpenCorporatesAPI
            self.opencorporates = OpenCorporatesAPI()
            self.opencorporates_available = True
        except Exception as e:
            logger.warning(f"OpenCorporates module not available: {e}")
            self.opencorporates_available = False
        
        # Companies House
        try:
            from companies_house import CompaniesHouseAPI
            # You'll need to set CH_API_KEY environment variable
            ch_api_key = os.getenv('CH_API_KEY')
            if ch_api_key:
                self.companies_house = CompaniesHouseAPI(ch_api_key)
                self.companies_house_available = True
            else:
                logger.warning("Companies House API key not found")
                self.companies_house_available = False
        except Exception as e:
            logger.warning(f"Companies House module not available: {e}")
            self.companies_house_available = False
        
        # OCCRP Aleph
        try:
            from occrp_aleph import AlephSearcher
            self.aleph = AlephSearcher()
            self.aleph_available = True
        except Exception as e:
            logger.warning(f"OCCRP Aleph module not available: {e}")
            self.aleph_available = False
        
        # OpenSanctions
        try:
            import requests
            self.opensanctions_api_key = os.getenv('OPENSANCTIONS_API_KEY', '1d6a91c9f96eb9594a3bb81cdcc37bd7')
            self.opensanctions_available = True
            logger.info("OpenSanctions module initialized successfully")
        except Exception as e:
            logger.warning(f"OpenSanctions module not available: {e}")
            self.opensanctions_available = False
            
    def search_all_sources(self, company_name: str) -> Dict[str, List[SearchResult]]:
        """
        Search all available sources for company information
        
        Args:
            company_name: Name of the company to search
            
        Returns:
            Dictionary of results organized by source
        """
        results = {}
        
        # Search each available source
        if self.edgar_available:
            results['EDGAR'] = self._search_edgar(company_name)
            
        if self.opencorporates_available:
            results['OpenCorporates'] = self._search_opencorporates(company_name)
            
        if self.companies_house_available:
            results['Companies House'] = self._search_companies_house(company_name)
            
        if self.aleph_available:
            results['OCCRP Aleph'] = self._search_aleph(company_name)
        
        if self.opensanctions_available:
            results['OpenSanctions'] = self._search_opensanctions(company_name)
        
        return results
    
    def _search_opensanctions(self, company_name: str) -> List[SearchResult]:
        """Search OpenSanctions database"""
        results = []
        try:
            import requests
            
            # OpenSanctions API endpoint
            base_url = 'https://api.opensanctions.org/search/default'
            headers = {
                'Authorization': f'Bearer {self.opensanctions_api_key}'
            }
            params = {
                'q': company_name,
                'nested': 'true',
                'limit': 10
            }
            
            response = requests.get(base_url, headers=headers, params=params)
            response.raise_for_status()
            sanctions_data = response.json()
            
            if sanctions_data.get('results'):
                for entity in sanctions_data['results'][:5]:
                    properties = entity.get('properties', {})
                    
                    # Build sanctions info
                    sanctions_info = {
                        'datasets': entity.get('datasets', []),
                        'score': entity.get('score'),
                        'topics': properties.get('topics', []),
                        'countries': properties.get('country', []),
                        'aliases': properties.get('alias', []),
                        'notes': properties.get('notes', [])
                    }
                    
                    result = SearchResult(
                        source="OpenSanctions",
                        company_name=properties.get('name', [company_name])[0] if properties.get('name') else company_name,
                        jurisdiction=properties.get('jurisdiction', [None])[0] if properties.get('jurisdiction') else None,
                        registration_number=properties.get('registrationNumber', [None])[0] if properties.get('registrationNumber') else None,
                        sanctions_info=sanctions_info,
                        raw_data=entity
                    )
                    results.append(result)
                    
        except Exception as e:
            logger.error(f"OpenSanctions search error: {e}")
            results.append(SearchResult(
                source="OpenSanctions",
                company_name=company_name,
                error=str(e)
            ))
        
        return results
    
    def _search_edgar(self, company_name: str) -> List[SearchResult]:
        """Search SEC EDGAR database"""
        results = []
        try:
            # Search for company filings
            edgar_results = self.edgar.search_company_filings(
                company_name=company_name,
                years_back=3
            )
            
            if edgar_results.get('success') and edgar_results.get('results'):
                # Group by company
                companies = {}
                for filing in edgar_results['results']:
                    entity_name = filing.get('Entity Name', 'Unknown')
                    if entity_name not in companies:
                        companies[entity_name] = []
                    companies[entity_name].append(filing)
                
                # Create SearchResult for each company
                for entity_name, filings in companies.items():
                    result = SearchResult(
                        source="SEC EDGAR",
                        company_name=entity_name,
                        jurisdiction="United States",
                        filings=[{
                            'type': f.get('Filing Type'),
                            'date': f.get('Filed'),
                            'description': f.get('Description', ''),
                            'url': f.get('Filing Html URL')
                        } for f in filings],
                        raw_data={'filings': filings}
                    )
                    results.append(result)
                    
        except Exception as e:
            logger.error(f"EDGAR search error: {e}")
            results.append(SearchResult(
                source="SEC EDGAR",
                company_name=company_name,
                error=str(e)
            ))
        
        return results
    
    def _search_opencorporates(self, company_name: str) -> List[SearchResult]:
        """Search OpenCorporates database"""
        results = []
        try:
            # Call the OpenCorporates API
            oc_results = self.opencorporates.search_companies(company_name)
            
            if oc_results and 'companies' in oc_results:
                companies = oc_results['companies'].get('company', [])
                if isinstance(companies, dict):
                    companies = [companies]  # Single result case
                
                for company in companies[:5]:  # Top 5 results
                    result = SearchResult(
                        source="OpenCorporates",
                        company_name=company.get('name', ''),
                        jurisdiction=company.get('jurisdiction_code'),
                        registration_number=company.get('company_number'),
                        status=company.get('current_status'),
                        incorporation_date=company.get('incorporation_date'),
                        raw_data=company
                    )
                    results.append(result)
                    
        except Exception as e:
            logger.error(f"OpenCorporates search error: {e}")
            results.append(SearchResult(
                source="OpenCorporates",
                company_name=company_name,
                error=str(e)
            ))
        
        return results
    
    def _search_companies_house(self, company_name: str) -> List[SearchResult]:
        """Search UK Companies House"""
        results = []
        try:
            # Search for companies
            ch_results = self.companies_house.search_companies(company_name)
            
            if ch_results and 'items' in ch_results:
                for company in ch_results['items'][:5]:  # Top 5 results
                    result = SearchResult(
                        source="UK Companies House",
                        company_name=company.get('title', ''),
                        jurisdiction="United Kingdom",
                        registration_number=company.get('company_number'),
                        status=company.get('company_status'),
                        incorporation_date=company.get('date_of_creation'),
                        raw_data=company
                    )
                    results.append(result)
                    
        except Exception as e:
            logger.error(f"Companies House search error: {e}")
            results.append(SearchResult(
                source="UK Companies House",
                company_name=company_name,
                error=str(e)
            ))
        
        return results
    
    def _search_aleph(self, company_name: str) -> List[SearchResult]:
        """Search OCCRP Aleph database"""
        results = []
        try:
            aleph_results = self.aleph.search_entities(company_name, schema='Company')
            
            if aleph_results:
                for entity in aleph_results[:5]:  # Top 5 results
                    result = SearchResult(
                        source="OCCRP Aleph",
                        company_name=entity.get('name', company_name),
                        jurisdiction=entity.get('jurisdiction'),
                        registration_number=entity.get('registration_number'),
                        raw_data=entity
                    )
                    results.append(result)
                    
        except Exception as e:
            logger.error(f"OCCRP Aleph search error: {e}")
            results.append(SearchResult(
                source="OCCRP Aleph",
                company_name=company_name,
                error=str(e)
            ))
        
        return results
    
    def generate_report(self, results: Dict[str, List[SearchResult]], 
                       company_name: str) -> str:
        """Generate a comprehensive report from search results"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.results_dir / f"report_{company_name.replace(' ', '_')}_{timestamp}.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"CORPORATE SEARCH REPORT\n")
            f.write(f"{'='*60}\n")
            f.write(f"Search Query: {company_name}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")
            
            # Check if any sanctions hits
            sanctions_hits = results.get('OpenSanctions', [])
            if sanctions_hits and any(not r.error and r.sanctions_info for r in sanctions_hits):
                f.write("⚠️  SANCTIONS ALERT ⚠️\n")
                f.write("This entity appears on sanctions/watchlists.\n")
                f.write("See OpenSanctions section below for details.\n\n")
            
            for source, source_results in results.items():
                f.write(f"\n{source.upper()}\n")
                f.write(f"{'-'*len(source)}\n")
                
                if not source_results:
                    f.write("No results found.\n")
                    continue
                
                for result in source_results:
                    if result.error:
                        f.write(f"Error: {result.error}\n")
                        continue
                    
                    f.write(f"\nCompany: {result.company_name}\n")
                    if result.jurisdiction:
                        f.write(f"Jurisdiction: {result.jurisdiction}\n")
                    if result.registration_number:
                        f.write(f"Registration: {result.registration_number}\n")
                    if result.status:
                        f.write(f"Status: {result.status}\n")
                    if result.incorporation_date:
                        f.write(f"Incorporated: {result.incorporation_date}\n")
                    
                    # Special handling for sanctions info
                    if result.sanctions_info:
                        f.write(f"\nSanctions Information:\n")
                        f.write(f"  Datasets: {', '.join(result.sanctions_info.get('datasets', []))}\n")
                        f.write(f"  Match Score: {result.sanctions_info.get('score', 'N/A')}\n")
                        if result.sanctions_info.get('topics'):
                            f.write(f"  Topics: {', '.join(result.sanctions_info['topics'])}\n")
                        if result.sanctions_info.get('countries'):
                            f.write(f"  Countries: {', '.join(result.sanctions_info['countries'])}\n")
                        if result.sanctions_info.get('aliases'):
                            f.write(f"  Aliases: {', '.join(result.sanctions_info['aliases'][:5])}\n")
                    
                    if result.filings:
                        f.write(f"\nRecent Filings:\n")
                        for filing in result.filings[:5]:
                            f.write(f"  - {filing.get('date', 'N/A')}: "
                                  f"{filing.get('type', 'N/A')} - "
                                  f"{filing.get('description', 'N/A')}\n")
                    
                    f.write("\n")
        
        return str(report_file)
    
    def export_to_json(self, results: Dict[str, List[SearchResult]], 
                       company_name: str) -> str:
        """Export results to JSON format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = self.results_dir / f"results_{company_name.replace(' ', '_')}_{timestamp}.json"
        
        # Convert SearchResult objects to dictionaries
        json_data = {}
        for source, source_results in results.items():
            json_data[source] = []
            for result in source_results:
                result_dict = {
                    'source': result.source,
                    'company_name': result.company_name,
                    'jurisdiction': result.jurisdiction,
                    'registration_number': result.registration_number,
                    'status': result.status,
                    'incorporation_date': result.incorporation_date,
                    'officers': result.officers,
                    'filings': result.filings,
                    'sanctions_info': result.sanctions_info,
                    'error': result.error
                }
                json_data[source].append(result_dict)
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, default=str)
        
        return str(json_file)


class CorporateSearchCLI:
    """Command-line interface for the corporate search system"""
    
    def __init__(self):
        self.system = CorporateSearchSystem()
        
    def run(self):
        """Run the interactive CLI"""
        self.print_header()
        
        while True:
            self.print_menu()
            choice = input("\nEnter your choice: ").strip()
            
            if choice == '1':
                self.search_all_sources()
            elif choice == '2':
                self.search_specific_source()
            elif choice == '3':
                self.search_edgar_keywords()
            elif choice == '4':
                self.monitor_rss_feeds()
            elif choice == '5':
                self.check_sanctions()
            elif choice == '6':
                self.view_recent_searches()
            elif choice == 'q':
                print("\nGoodbye!")
                break
            else:
                print("\nInvalid choice. Please try again.")
    
    def print_header(self):
        """Print application header"""
        print("\n" + "="*60)
        print("       CORPORATE SEARCH - CONSOLIDATED SYSTEM")
        print("="*60)
        print("Integrating: EDGAR, OpenCorporates, Companies House,")
        print("            OCCRP Aleph, OpenSanctions, and more")
        print("="*60)
    
    def print_menu(self):
        """Print main menu"""
        print("\nMAIN MENU")
        print("---------")
        print("1. Search all sources for a company")
        print("2. Search specific data source")
        print("3. Search EDGAR by keywords")
        print("4. Monitor RSS feeds (EDGAR)")
        print("5. Check sanctions lists")
        print("6. View recent searches")
        print("q. Quit")
    
    def search_all_sources(self):
        """Handle searching all sources"""
        company_name = input("\nEnter company name: ").strip()
        if not company_name:
            return
        
        print(f"\nSearching all sources for: {company_name}")
        print("This may take a moment...\n")
        
        results = self.system.search_all_sources(company_name)
        
        # Display summary
        total_results = 0
        for source, source_results in results.items():
            count = len([r for r in source_results if not r.error])
            total_results += count
            print(f"  {source}: {count} results")
        
        print(f"\nTotal results found: {total_results}")
        
        # Ask about report generation
        if total_results > 0:
            generate = input("\nGenerate report? (y/n): ").strip().lower()
            if generate == 'y':
                report_file = self.system.generate_report(results, company_name)
                json_file = self.system.export_to_json(results, company_name)
                print(f"\nReport saved to: {report_file}")
                print(f"JSON data saved to: {json_file}")
        
        input("\nPress Enter to continue...")
    
    def search_specific_source(self):
        """Handle searching a specific source"""
        print("\nSelect data source:")
        print("1. SEC EDGAR (US)")
        print("2. OpenCorporates (Global)")
        print("3. UK Companies House")
        print("4. OCCRP Aleph")
        print("5. OpenSanctions (Sanctions/PEPs)")
        print("6. Back to main menu")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice == '6':
            return
        
        company_name = input("\nEnter company name: ").strip()
        if not company_name:
            return
        
        results = {}
        
        if choice == '1' and self.system.edgar_available:
            results['EDGAR'] = self.system._search_edgar(company_name)
        elif choice == '2' and self.system.opencorporates_available:
            results['OpenCorporates'] = self.system._search_opencorporates(company_name)
        elif choice == '3' and self.system.companies_house_available:
            results['Companies House'] = self.system._search_companies_house(company_name)
        elif choice == '4' and self.system.aleph_available:
            results['OCCRP Aleph'] = self.system._search_aleph(company_name)
        elif choice == '5' and self.system.opensanctions_available:
            results['OpenSanctions'] = self.system._search_opensanctions(company_name)
        else:
            print("\nSource not available or invalid choice.")
            input("Press Enter to continue...")
            return
        
        # Display results
        for source, source_results in results.items():
            print(f"\n{source} Results:")
            print("-" * len(source))
            for result in source_results:
                if result.error:
                    print(f"Error: {result.error}")
                else:
                    print(f"\nCompany: {result.company_name}")
                    if result.jurisdiction:
                        print(f"Jurisdiction: {result.jurisdiction}")
                    if result.registration_number:
                        print(f"Registration: {result.registration_number}")
        
        input("\nPress Enter to continue...")
    
    def search_edgar_keywords(self):
        """Handle EDGAR keyword search"""
        if not self.system.edgar_available:
            print("\nEDGAR module not available.")
            input("Press Enter to continue...")
            return
        
        keywords = input("\nEnter search keywords (comma-separated): ").strip()
        if not keywords:
            return
        
        keyword_list = [k.strip() for k in keywords.split(',')]
        
        date_range = input("Enter date range (1y/3y/5y/all) [default: 1y]: ").strip() or "1y"
        
        print(f"\nSearching EDGAR for: {', '.join(keyword_list)}")
        
        # Calculate date range
        end_date = date.today().strftime('%Y-%m-%d')
        if date_range == '1y':
            start_date = date(date.today().year - 1, 1, 1).strftime('%Y-%m-%d')
        elif date_range == '3y':
            start_date = date(date.today().year - 3, 1, 1).strftime('%Y-%m-%d')
        elif date_range == '5y':
            start_date = date(date.today().year - 5, 1, 1).strftime('%Y-%m-%d')
        else:
            start_date = None
            end_date = None
        
        results = self.system.edgar.text_search(
            search_terms=keyword_list,
            start_date=start_date,
            end_date=end_date,
            output_format='json'
        )
        
        if results.get('success'):
            print(f"\nFound {results['result_count']} results")
            print(f"Results saved to: {results['output_file']}")
        else:
            print(f"\nSearch failed: {results.get('error')}")
        
        input("\nPress Enter to continue...")
    
    def monitor_rss_feeds(self):
        """Handle RSS feed monitoring"""
        if not self.system.edgar_available:
            print("\nEDGAR module not available.")
            input("Press Enter to continue...")
            return
        
        tickers = input("\nEnter tickers to monitor (comma-separated): ").strip()
        if not tickers:
            return
        
        ticker_list = [t.strip().upper() for t in tickers.split(',')]
        
        print(f"\nChecking RSS feeds for: {', '.join(ticker_list)}")
        
        results = self.system.edgar.rss_monitor(
            tickers=ticker_list,
            output_format='json'
        )
        
        if results.get('success'):
            print(f"\nFound {results.get('result_count', 0)} new filings")
            print(f"Results saved to: {results['output_file']}")
        else:
            print(f"\nMonitoring failed: {results.get('error')}")
        
        input("\nPress Enter to continue...")
    
    def check_sanctions(self):
        """Handle sanctions checking"""
        if not self.system.opensanctions_available:
            print("\nOpenSanctions module not available.")
            input("Press Enter to continue...")
            return
        
        entity_name = input("\nEnter entity name to check for sanctions: ").strip()
        if not entity_name:
            return
        
        print(f"\nChecking sanctions lists for: {entity_name}")
        print("This may take a moment...\n")
        
        # Use the existing _search_opensanctions method
        sanctions_results = self.system._search_opensanctions(entity_name)
        
        if not sanctions_results:
            print("No results found.")
        else:
            # Count actual hits (excluding errors)
            hits = [r for r in sanctions_results if not r.error and r.sanctions_info]
            
            if hits:
                print(f"⚠️  SANCTIONS ALERT: Found {len(hits)} potential matches ⚠️\n")
            else:
                print("✅ No sanctions matches found.\n")
            
            for result in sanctions_results:
                if result.error:
                    print(f"Error: {result.error}")
                    continue
                    
                print(f"\nEntity: {result.company_name}")
                if result.sanctions_info:
                    print(f"Match Score: {result.sanctions_info.get('score', 'N/A')}")
                    print(f"Datasets: {', '.join(result.sanctions_info.get('datasets', []))}")
                    if result.sanctions_info.get('topics'):
                        print(f"Topics: {', '.join(result.sanctions_info['topics'])}")
                    if result.sanctions_info.get('countries'):
                        print(f"Countries: {', '.join(result.sanctions_info['countries'])}")
                    if result.sanctions_info.get('aliases'):
                        print(f"Aliases: {', '.join(result.sanctions_info['aliases'][:3])}")
        
        # Ask about generating detailed report
        if hits:
            generate = input("\nGenerate detailed sanctions report? (y/n): ").strip().lower()
            if generate == 'y':
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                report_file = self.system.results_dir / f"sanctions_report_{entity_name.replace(' ', '_')}_{timestamp}.txt"
                
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write(f"SANCTIONS CHECK REPORT\n")
                    f.write(f"{'='*60}\n")
                    f.write(f"Entity: {entity_name}\n")
                    f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"{'='*60}\n\n")
                    
                    for result in sanctions_results:
                        if result.error:
                            continue
                        f.write(f"\nMatch: {result.company_name}\n")
                        if result.sanctions_info:
                            f.write(f"Score: {result.sanctions_info.get('score', 'N/A')}\n")
                            f.write(f"Datasets: {', '.join(result.sanctions_info.get('datasets', []))}\n")
                            if result.sanctions_info.get('notes'):
                                f.write(f"Notes: {'; '.join(result.sanctions_info['notes'])}\n")
                            f.write("\n")
                
                print(f"\nDetailed report saved to: {report_file}")
        
        input("\nPress Enter to continue...")
    
    def view_recent_searches(self):
        """View recent search results"""
        results_files = list(self.system.results_dir.glob("*.txt"))
        results_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not results_files:
            print("\nNo recent searches found.")
            input("Press Enter to continue...")
            return
        
        print("\nRecent Searches:")
        print("-" * 60)
        
        for i, file in enumerate(results_files[:10], 1):
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            print(f"{i}. {file.name} - {mtime.strftime('%Y-%m-%d %H:%M')}")
        
        choice = input("\nEnter number to view (or Enter to go back): ").strip()
        
        if choice.isdigit() and 1 <= int(choice) <= min(10, len(results_files)):
            file_path = results_files[int(choice) - 1]
            print(f"\n{'='*60}")
            with open(file_path, 'r', encoding='utf-8') as f:
                print(f.read())
            print(f"{'='*60}")
        
        input("\nPress Enter to continue...")


def main():
    """Main entry point"""
    cli = CorporateSearchCLI()
    try:
        cli.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Goodbye!")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\nAn error occurred: {e}")
        print("Please check the logs for more details.")


if __name__ == "__main__":
    main()
