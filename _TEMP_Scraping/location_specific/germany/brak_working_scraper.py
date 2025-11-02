#!/usr/bin/env python3
"""
Working BRAK Scraper with proper HTML parsing
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import random
from pathlib import Path
from datetime import datetime
import logging
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


class BRAKWorkingScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        self.base_url = "https://bravsearch.bea-brak.de"
        self.search_url = f"{self.base_url}/bravsearch/search.brak"
        
    def search_lawyers(self, city="", name="", postal_code="", max_results=100):
        """Search for lawyers with given criteria"""
        
        # First, get the search page to establish session
        logger.info(f"Searching for lawyers in {city or 'all cities'}")
        
        try:
            # Initial GET to establish session
            init_response = self.session.get(f"{self.base_url}/bravsearch/index.brak")
            time.sleep(random.uniform(1, 2))
            
            # Prepare search parameters
            search_data = {
                'name': name,
                'vorname': '',
                'kanzlei': '',
                'strasse': '',
                'plz': postal_code,
                'ort': city,
                'land': 'Deutschland',
                'fachanwalt': '',
                'interessenschwerpunkt': '',
                'sprachkenntnisse': '',
                'submit': 'Suchen'
            }
            
            # Remove empty parameters
            search_data = {k: v for k, v in search_data.items() if v}
            
            # Perform search
            response = self.session.post(
                self.search_url,
                data=search_data,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                logger.error(f"Search failed with status {response.status_code}")
                return []
            
            # Parse results
            soup = BeautifulSoup(response.text, 'html.parser')
            lawyers = self._parse_results(soup)
            
            # Handle pagination if needed
            page_num = 2
            while len(lawyers) < max_results:
                next_page = self._get_next_page(soup, page_num)
                if not next_page:
                    break
                    
                time.sleep(random.uniform(2, 3))
                response = self.session.get(f"{self.base_url}{next_page}")
                soup = BeautifulSoup(response.text, 'html.parser')
                new_lawyers = self._parse_results(soup)
                
                if not new_lawyers:
                    break
                    
                lawyers.extend(new_lawyers)
                page_num += 1
                logger.info(f"Fetched page {page_num}, total lawyers: {len(lawyers)}")
            
            return lawyers[:max_results]
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def _parse_results(self, soup):
        """Parse lawyer entries from search results"""
        lawyers = []
        
        # Look for result entries - common patterns
        # Try different selectors based on typical structures
        
        # Pattern 1: Table-based results
        tables = soup.find_all('table', class_=['ergebnisliste', 'results', 'search-results'])
        for table in tables:
            rows = table.find_all('tr')
            for row in rows[1:]:  # Skip header
                lawyer = self._parse_table_row(row)
                if lawyer:
                    lawyers.append(lawyer)
        
        # Pattern 2: Div-based results
        if not lawyers:
            result_divs = soup.find_all('div', class_=['result', 'lawyer-entry', 'suchergebnis'])
            for div in result_divs:
                lawyer = self._parse_div_entry(div)
                if lawyer:
                    lawyers.append(lawyer)
        
        # Pattern 3: List-based results
        if not lawyers:
            result_lists = soup.find_all(['ul', 'ol'], class_=['results', 'lawyer-list'])
            for lst in result_lists:
                items = lst.find_all('li')
                for item in items:
                    lawyer = self._parse_list_item(item)
                    if lawyer:
                        lawyers.append(lawyer)
        
        # If still no results, try generic approach
        if not lawyers:
            # Look for any structure with names and addresses
            all_text = soup.get_text()
            if "Rechtsanwalt" in all_text or "Rechtsanwältin" in all_text:
                lawyers = self._parse_generic(soup)
        
        return lawyers
    
    def _parse_table_row(self, row):
        """Parse a table row"""
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
            return None
            
        lawyer = {}
        
        # Extract text from each cell
        for i, cell in enumerate(cells):
            text = cell.get_text(strip=True)
            
            # Try to identify what each cell contains
            if i == 0 or 'name' in str(cell).lower():
                lawyer['name'] = text
            elif any(x in text.lower() for x in ['straße', 'str.', 'weg', 'platz']):
                lawyer['address'] = text
            elif re.match(r'\d{5}', text):
                lawyer['postal_code'] = text
            elif any(x in text.lower() for x in ['berlin', 'münchen', 'hamburg', 'köln']):
                lawyer['city'] = text
            elif '@' in text:
                lawyer['email'] = text
            elif re.match(r'[\d\s\-\+\(\)]+', text) and len(text) > 6:
                lawyer['phone'] = text
        
        return lawyer if lawyer else None
    
    def _parse_div_entry(self, div):
        """Parse a div-based entry"""
        lawyer = {}
        
        # Look for name
        name_elem = div.find(['h2', 'h3', 'h4', 'strong', 'b'])
        if name_elem:
            lawyer['name'] = name_elem.get_text(strip=True)
        
        # Look for address
        address_elem = div.find(['address', 'p', 'span'], class_=['address', 'adresse'])
        if address_elem:
            lawyer['address'] = address_elem.get_text(strip=True)
        
        # Extract all text and parse
        full_text = div.get_text(separator='|', strip=True)
        parts = full_text.split('|')
        
        for part in parts:
            part = part.strip()
            if '@' in part:
                lawyer['email'] = part
            elif re.match(r'\d{5}', part):
                lawyer['postal_code'] = part
            elif re.match(r'[\d\s\-\+\(\)]+', part) and len(part) > 6:
                lawyer['phone'] = part
        
        return lawyer if lawyer else None
    
    def _parse_list_item(self, item):
        """Parse a list item"""
        return self._parse_div_entry(item)  # Similar structure
    
    def _parse_generic(self, soup):
        """Generic parsing approach"""
        lawyers = []
        
        # Find all text blocks that might contain lawyer info
        text_blocks = soup.find_all(['p', 'div', 'li', 'td'])
        
        current_lawyer = {}
        for block in text_blocks:
            text = block.get_text(strip=True)
            
            # Check if this might be a name (contains Rechtsanwalt/in)
            if 'Rechtsanwalt' in text or 'Rechtsanwältin' in text:
                if current_lawyer:
                    lawyers.append(current_lawyer)
                current_lawyer = {'name': text}
            elif current_lawyer:
                # Add to current lawyer
                if '@' in text:
                    current_lawyer['email'] = text
                elif re.match(r'\d{5}', text):
                    current_lawyer['postal_code'] = text
                elif any(city in text for city in ['Berlin', 'München', 'Hamburg']):
                    current_lawyer['city'] = text
        
        if current_lawyer:
            lawyers.append(current_lawyer)
        
        return lawyers
    
    def _get_next_page(self, soup, page_num):
        """Find next page link"""
        # Look for pagination
        next_links = soup.find_all('a', text=re.compile(r'(Weiter|Next|→|' + str(page_num) + ')'))
        for link in next_links:
            href = link.get('href')
            if href:
                return href
        return None
    
    def save_results(self, lawyers, filename):
        """Save results to JSON file"""
        output_dir = Path("brak_data")
        output_dir.mkdir(exist_ok=True)
        
        filepath = output_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(lawyers, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(lawyers)} lawyers to {filepath}")
        return filepath


def main():
    """Main execution"""
    print("""
    =====================================
    BRAK Lawyer Database Scraper
    =====================================
    """)
    
    scraper = BRAKWorkingScraper()
    
    # Test with specific cities
    test_searches = [
        {"city": "Berlin", "postal_code": ""},
        {"city": "München", "postal_code": ""},
        {"city": "Hamburg", "postal_code": ""},
        {"city": "", "name": "Schmidt"},
        {"city": "", "name": "Müller"},
    ]
    
    all_lawyers = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for search in test_searches:
        search_desc = search.get('city', '') or f"name:{search.get('name', '')}"
        print(f"\n📍 Searching: {search_desc}")
        print("-" * 40)
        
        lawyers = scraper.search_lawyers(
            city=search.get('city', ''),
            name=search.get('name', ''),
            max_results=50
        )
        
        if lawyers:
            print(f"✅ Found {len(lawyers)} lawyers")
            
            # Save individual search results
            filename = f"lawyers_{search_desc.lower().replace(' ', '_')}_{timestamp}.json"
            scraper.save_results(lawyers, filename)
            
            all_lawyers.extend(lawyers)
            
            # Show sample
            if lawyers:
                print(f"\nSample result:")
                print(json.dumps(lawyers[0], indent=2, ensure_ascii=False))
        else:
            print(f"⚠️  No results found")
        
        # Rate limiting
        time.sleep(random.uniform(3, 5))
    
    # Save combined results
    if all_lawyers:
        scraper.save_results(all_lawyers, f"all_lawyers_combined_{timestamp}.json")
        print(f"\n✨ Total lawyers found: {len(all_lawyers)}")
    else:
        print("\n⚠️  No lawyers found. The website structure might have changed.")
        print("Consider using Playwright for JavaScript-rendered content.")


if __name__ == "__main__":
    main()