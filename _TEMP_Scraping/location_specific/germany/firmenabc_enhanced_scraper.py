#!/usr/bin/env python3
"""
Enhanced FirmenABC Scraper with EntityGraphStorageV2 Integration
Directly stores extracted entities and relationships in the central entity system
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from datetime import datetime

# Import the integration module
from firmenabc_entity_integration import FirmenABCEntityIntegration

# Import original extraction function
from fix_firmenabc_scraper import extract_company_shareholders

logger = logging.getLogger(__name__)


class EnhancedFirmenABCScraper:
    """
    Enhanced scraper that extracts and stores entities directly in EntityGraphStorageV2
    """
    
    def __init__(self, project_id: str = "firmenabc"):
        """Initialize with entity integration"""
        self.integration = FirmenABCEntityIntegration(project_id=project_id)
        self.processed_urls = set()
        self.stats = {
            'companies_processed': 0,
            'persons_extracted': 0,
            'relationships_created': 0,
            'errors': 0
        }
        
        logger.info(f"Initialized enhanced FirmenABC scraper for project: {project_id}")
    
    def extract_company_data(self, html: str, url: str) -> Dict[str, Any]:
        """
        Extract comprehensive company data from HTML
        
        Returns:
            Dictionary with company details
        """
        company_data = {
            'name': None,
            'legal_form': None,
            'registration_number': None,
            'tax_number': None,
            'vat_number': None,
            'founded_date': None,
            'capital': None,
            'address': None,
            'postal_code': None,
            'city': None,
            'region': None,
            'country': 'Austria',
            'industry': None,
            'employees': None,
            'website': None,
            'email': None,
            'phone': None,
            'description': None
        }
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except:
            logger.error(f"Failed to parse HTML for {url}")
            return company_data
        
        # Extract company name from H1
        h1 = soup.find('h1')
        if h1:
            company_data['name'] = h1.get_text(' ', strip=True)
            # Clean up name (remove location suffix)
            company_data['name'] = re.sub(r'\s+in\s+[A-ZÄÖÜ].*$', '', 
                                         company_data['name']).strip()
        
        # Try to extract from JSON-LD structured data
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                json_data = json.loads(script.string)
                
                # Handle both single object and array
                if isinstance(json_data, list):
                    json_data = json_data[0] if json_data else {}
                
                # Extract company details from JSON-LD
                if json_data.get('@type') in ['Organization', 'Corporation', 'LocalBusiness']:
                    company_data['name'] = company_data['name'] or json_data.get('name')
                    company_data['vat_number'] = json_data.get('vatID')
                    company_data['email'] = json_data.get('email')
                    company_data['phone'] = json_data.get('telephone')
                    company_data['website'] = json_data.get('url')
                    
                    # Extract address
                    if 'address' in json_data:
                        addr = json_data['address']
                        if isinstance(addr, dict):
                            company_data['address'] = addr.get('streetAddress')
                            company_data['postal_code'] = addr.get('postalCode')
                            company_data['city'] = addr.get('addressLocality')
                            company_data['region'] = addr.get('addressRegion')
                            company_data['country'] = addr.get('addressCountry', 'Austria')
                    
                    # Extract founding date
                    if 'foundingDate' in json_data:
                        company_data['founded_date'] = json_data['foundingDate']
                    
                    # Extract employees
                    if 'numberOfEmployees' in json_data:
                        emp = json_data['numberOfEmployees']
                        if isinstance(emp, dict):
                            company_data['employees'] = emp.get('value')
                        else:
                            company_data['employees'] = emp
                            
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"Failed to parse JSON-LD: {e}")
                continue
        
        # Extract from info boxes/tables
        info_sections = soup.find_all(['dl', 'table', 'div'], class_=re.compile(r'info|detail|data'))
        
        for section in info_sections:
            text = section.get_text(' ', strip=True)
            
            # Registration number patterns
            fn_match = re.search(r'FN\s*(\d+\s*\w*)', text)
            if fn_match:
                company_data['registration_number'] = fn_match.group(1)
            
            # VAT number
            vat_match = re.search(r'UID[:\s]+([A-Z]{2}\d+)', text)
            if vat_match:
                company_data['vat_number'] = vat_match.group(1)
            
            # Legal form
            legal_forms = ['GmbH', 'AG', 'KG', 'OG', 'e.U.', 'GmbH & Co KG', 'SE', 'GesbR']
            for form in legal_forms:
                if form in text:
                    company_data['legal_form'] = form
                    break
            
            # Capital
            capital_match = re.search(r'Stammkapital[:\s]+€\s*([\d.,]+)', text)
            if capital_match:
                company_data['capital'] = capital_match.group(1)
            
            # Industry/branch
            industry_match = re.search(r'Branche[:\s]+([^,\n]+)', text)
            if industry_match:
                company_data['industry'] = industry_match.group(1).strip()
        
        # Extract contact details from any visible text
        if not company_data['email']:
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', html)
            if email_match:
                company_data['email'] = email_match.group(0)
        
        if not company_data['phone']:
            phone_match = re.search(r'\+43[\s\d]+|\(0\d+\)[\s\d]+', html)
            if phone_match:
                company_data['phone'] = phone_match.group(0).strip()
        
        if not company_data['website']:
            website_match = re.search(r'https?://[^\s<>"]+', html)
            if website_match:
                company_data['website'] = website_match.group(0)
        
        return company_data
    
    def process_company_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        Process a company page and store entities in EntityGraphStorageV2
        
        Args:
            html: Page HTML content
            url: FirmenABC URL
            
        Returns:
            Processing result with entity IDs
        """
        
        if url in self.processed_urls:
            logger.info(f"Already processed: {url}")
            return {'status': 'skipped', 'reason': 'already_processed'}
        
        try:
            # Extract company data
            company_data = self.extract_company_data(html, url)
            
            if not company_data.get('name'):
                logger.warning(f"No company name found for {url}")
                self.stats['errors'] += 1
                return {'status': 'error', 'reason': 'no_company_name'}
            
            # Extract shareholders/directors
            shareholders = extract_company_shareholders(html)
            
            # Store in EntityGraphStorageV2 using integration
            result = self.integration.process_company_extraction(
                company_data=company_data,
                shareholders=shareholders,
                source_url=url
            )
            
            # Update statistics
            self.stats['companies_processed'] += 1
            self.stats['persons_extracted'] += len(shareholders)
            self.stats['relationships_created'] += result['relationships_created']
            
            # Mark as processed
            self.processed_urls.add(url)
            
            # Log success
            logger.info(f"Successfully processed {company_data['name']}: "
                       f"{len(shareholders)} persons, "
                       f"{result['relationships_created']} relationships")
            
            return {
                'status': 'success',
                'company_id': result['company_id'],
                'person_ids': result['person_ids'],
                'entities_created': result['entities_created'],
                'relationships_created': result['relationships_created']
            }
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            self.stats['errors'] += 1
            return {'status': 'error', 'reason': str(e)}
    
    def process_person_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        Process a person/shareholder page
        
        Args:
            html: Page HTML content
            url: FirmenABC person URL
            
        Returns:
            Processing result
        """
        
        if url in self.processed_urls:
            return {'status': 'skipped', 'reason': 'already_processed'}
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract person name
            h1 = soup.find('h1')
            if not h1:
                return {'status': 'error', 'reason': 'no_person_name'}
            
            person_name = h1.get_text(' ', strip=True)
            
            # Extract person details
            person_data = {
                'name': person_name,
                'url': url
            }
            
            # Look for associated companies
            company_links = soup.find_all('a', href=re.compile(r'/firma/'))
            companies = []
            
            for link in company_links:
                company_name = link.get_text(strip=True)
                company_url = 'https://www.firmenabc.at' + link.get('href', '')
                
                # Find role information (usually near the link)
                parent = link.parent
                role_text = parent.get_text(' ', strip=True) if parent else ''
                
                # Determine role
                role = 'shareholder'  # default
                if 'Geschäftsführer' in role_text:
                    role = 'managing_director'
                elif 'Gesellschafter' in role_text:
                    role = 'shareholder'
                elif 'Vorstand' in role_text:
                    role = 'board_member'
                
                companies.append({
                    'name': company_name,
                    'url': company_url,
                    'role': role
                })
            
            # Create person entity
            person_entity = self.integration._create_person_entity(
                person_data, url
            )
            
            # Create relationships to companies
            for company in companies:
                # Create or find company entity
                company_entity = self.integration._create_company_entity(
                    {'name': company['name']},
                    company['url']
                )
                
                # Create relationship
                self.integration._create_relationship(
                    from_entity_id=person_entity['node_id'],
                    to_entity_id=company_entity['node_id'],
                    relationship_type=self.integration.RELATIONSHIP_MAPPINGS.get(
                        company['role'], 'WORKS_FOR'
                    ),
                    evidence={'source_url': url, 'role': company['role']},
                    confidence=0.9
                )
            
            self.processed_urls.add(url)
            self.stats['persons_extracted'] += 1
            
            return {
                'status': 'success',
                'person_id': person_entity['node_id'],
                'companies_linked': len(companies)
            }
            
        except Exception as e:
            logger.error(f"Error processing person {url}: {e}")
            self.stats['errors'] += 1
            return {'status': 'error', 'reason': str(e)}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {
            'companies_processed': self.stats['companies_processed'],
            'persons_extracted': self.stats['persons_extracted'],
            'relationships_created': self.stats['relationships_created'],
            'errors': self.stats['errors'],
            'urls_processed': len(self.processed_urls)
        }
    
    def export_graph(self, output_path: str = "firmenabc_graph.html"):
        """Export the entity graph to HTML visualization"""
        self.integration.export_to_html_graph(output_path)
        logger.info(f"Exported graph to {output_path}")


# Example usage with actual scraping
if __name__ == "__main__":
    import requests
    
    # Initialize scraper
    scraper = EnhancedFirmenABCScraper(project_id="firmenabc_demo")
    
    # Example URLs to process
    test_urls = [
        "https://www.firmenabc.at/red-bull-gmbh_KfZ",
        "https://www.firmenabc.at/swarovski-ag_BKfO"
    ]
    
    for url in test_urls:
        try:
            # Fetch the page (in production, use Firecrawl/Apify)
            response = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; FirmenABC Scraper)'
            })
            
            if response.status_code == 200:
                result = scraper.process_company_page(response.text, url)
                print(f"Processed {url}: {result}")
            else:
                print(f"Failed to fetch {url}: {response.status_code}")
                
        except Exception as e:
            print(f"Error processing {url}: {e}")
    
    # Print statistics
    stats = scraper.get_statistics()
    print(f"\nStatistics:")
    print(f"  Companies: {stats['companies_processed']}")
    print(f"  Persons: {stats['persons_extracted']}")
    print(f"  Relationships: {stats['relationships_created']}")
    print(f"  Errors: {stats['errors']}")
    
    # Export graph
    scraper.export_graph("firmenabc_demo.html")
    print(f"\nEntity graph exported to firmenabc_demo.html")