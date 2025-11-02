#!/usr/bin/env python3
"""
Advanced BRAK Lawyer Database Scraper using Playwright
Handles JavaScript-rendered content and complex interactions

Installation:
pip install playwright beautifulsoup4 pandas
playwright install chromium
"""

import asyncio
import json
import csv
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
import logging
from dataclasses import dataclass, asdict
import pandas as pd
from bs4 import BeautifulSoup

try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class LawyerEntry:
    """Complete lawyer entry with all available fields"""
    # Basic information
    full_name: str
    title: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    # Contact information
    firm_name: Optional[str] = None
    street_address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "Deutschland"
    
    phone: Optional[str] = None
    mobile: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    
    # Professional information
    bar_association: Optional[str] = None
    bar_number: Optional[str] = None
    admission_date: Optional[str] = None
    specializations: Optional[List[str]] = None
    additional_qualifications: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    
    # Additional details
    profile_url: Optional[str] = None
    last_updated: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for export"""
        data = asdict(self)
        # Convert lists to strings for CSV
        for key in ['specializations', 'additional_qualifications', 'languages']:
            if data.get(key):
                data[key] = '; '.join(data[key])
        return data


class BRAKPlaywrightScraper:
    """Advanced scraper using Playwright for dynamic content"""
    
    def __init__(self, headless: bool = True, slow_mo: int = 100):
        """
        Initialize the Playwright scraper
        
        Args:
            headless: Run browser in headless mode
            slow_mo: Slow down operations by specified milliseconds
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright is required. Install with: pip install playwright")
        
        self.headless = headless
        self.slow_mo = slow_mo
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.base_url = "https://bravsearch.bea-brak.de/bravsearch/index.brak"
        
        # Storage for scraped data
        self.lawyers_data: List[LawyerEntry] = []
        
    async def initialize(self):
        """Initialize browser and page"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo
        )
        
        # Create context with German locale
        context = await self.browser.new_context(
            locale='de-DE',
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        self.page = await context.new_page()
        
        # Enable request/response interception for debugging
        self.page.on("request", lambda request: logger.debug(f"Request: {request.url}"))
        self.page.on("response", lambda response: logger.debug(f"Response: {response.url} - {response.status}"))
        
    async def close(self):
        """Close browser and cleanup"""
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()
    
    async def navigate_to_search(self):
        """Navigate to the search page"""
        logger.info(f"Navigating to {self.base_url}")
        await self.page.goto(self.base_url, wait_until='networkidle')
        await self.page.wait_for_timeout(2000)  # Wait for page to fully load
        
    async def search_by_city(self, city: str, postal_code: str = "") -> List[LawyerEntry]:
        """
        Search for lawyers by city
        
        Args:
            city: City name
            postal_code: Optional postal code
            
        Returns:
            List of LawyerEntry objects
        """
        await self.navigate_to_search()
        
        # Fill in search form
        logger.info(f"Searching for lawyers in {city}")
        
        # Look for city input field (adjust selector based on actual HTML)
        city_input = await self.page.query_selector('input[name="ort"]')
        if city_input:
            await city_input.fill(city)
        
        if postal_code:
            plz_input = await self.page.query_selector('input[name="plz"]')
            if plz_input:
                await plz_input.fill(postal_code)
        
        # Submit search
        submit_button = await self.page.query_selector('input[type="submit"][value*="Suchen"]')
        if submit_button:
            await submit_button.click()
            await self.page.wait_for_load_state('networkidle')
        
        # Parse results
        lawyers = await self._parse_search_results()
        return lawyers
    
    async def search_by_name(self, last_name: str = "", first_name: str = "") -> List[LawyerEntry]:
        """
        Search for lawyers by name
        
        Args:
            last_name: Last name to search
            first_name: First name to search
            
        Returns:
            List of LawyerEntry objects
        """
        await self.navigate_to_search()
        
        logger.info(f"Searching for: {first_name} {last_name}")
        
        # Fill name fields
        if last_name:
            name_input = await self.page.query_selector('input[name="name"]')
            if name_input:
                await name_input.fill(last_name)
        
        if first_name:
            vorname_input = await self.page.query_selector('input[name="vorname"]')
            if vorname_input:
                await vorname_input.fill(first_name)
        
        # Submit search
        submit_button = await self.page.query_selector('input[type="submit"]')
        if submit_button:
            await submit_button.click()
            await self.page.wait_for_load_state('networkidle')
        
        # Parse results
        lawyers = await self._parse_search_results()
        return lawyers
    
    async def _parse_search_results(self) -> List[LawyerEntry]:
        """
        Parse search results from the current page
        
        Returns:
            List of LawyerEntry objects
        """
        lawyers = []
        
        # Get page content
        content = await self.page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find result entries (adjust selectors based on actual HTML structure)
        # This is a template - you'll need to inspect the actual HTML
        
        # Look for result table or list
        results_table = soup.find('table', class_='results')
        if results_table:
            rows = results_table.find_all('tr')[1:]  # Skip header row
            
            for row in rows:
                lawyer = await self._parse_lawyer_row(row)
                if lawyer:
                    lawyers.append(lawyer)
        
        # Check for pagination
        has_next = await self._check_pagination()
        if has_next:
            # Click next page and recursively parse
            next_lawyers = await self._handle_pagination()
            lawyers.extend(next_lawyers)
        
        logger.info(f"Parsed {len(lawyers)} lawyers from current page")
        return lawyers
    
    async def _parse_lawyer_row(self, row) -> Optional[LawyerEntry]:
        """
        Parse a single lawyer entry from a table row
        
        Args:
            row: BeautifulSoup row element
            
        Returns:
            LawyerEntry object or None
        """
        try:
            cells = row.find_all('td')
            if not cells:
                return None
            
            # Extract data from cells (adjust based on actual structure)
            lawyer = LawyerEntry(
                full_name=cells[0].get_text(strip=True) if len(cells) > 0 else "",
                firm_name=cells[1].get_text(strip=True) if len(cells) > 1 else None,
                street_address=cells[2].get_text(strip=True) if len(cells) > 2 else None,
                city=cells[3].get_text(strip=True) if len(cells) > 3 else None,
                phone=cells[4].get_text(strip=True) if len(cells) > 4 else None,
            )
            
            # Extract profile URL if available
            link = row.find('a')
            if link and link.get('href'):
                lawyer.profile_url = f"https://bravsearch.bea-brak.de{link['href']}"
            
            return lawyer
            
        except Exception as e:
            logger.error(f"Error parsing lawyer row: {e}")
            return None
    
    async def _check_pagination(self) -> bool:
        """Check if there are more pages of results"""
        next_button = await self.page.query_selector('a[title="Nächste Seite"]')
        return next_button is not None
    
    async def _handle_pagination(self) -> List[LawyerEntry]:
        """Handle pagination and get results from next pages"""
        lawyers = []
        
        next_button = await self.page.query_selector('a[title="Nächste Seite"]')
        if next_button:
            await next_button.click()
            await self.page.wait_for_load_state('networkidle')
            await self.page.wait_for_timeout(1000)  # Rate limiting
            
            # Parse the new page
            new_lawyers = await self._parse_search_results()
            lawyers.extend(new_lawyers)
        
        return lawyers
    
    async def scrape_lawyer_details(self, profile_url: str) -> Optional[LawyerEntry]:
        """
        Scrape detailed information from a lawyer's profile page
        
        Args:
            profile_url: URL to the lawyer's profile
            
        Returns:
            LawyerEntry with detailed information
        """
        try:
            await self.page.goto(profile_url, wait_until='networkidle')
            content = await self.page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract detailed information (adjust selectors)
            lawyer = LawyerEntry(
                full_name=soup.find('h1').get_text(strip=True) if soup.find('h1') else "",
            )
            
            # Extract contact details
            contact_section = soup.find('div', class_='contact')
            if contact_section:
                lawyer.email = self._extract_email(contact_section)
                lawyer.website = self._extract_website(contact_section)
            
            # Extract specializations
            spec_section = soup.find('div', class_='specializations')
            if spec_section:
                lawyer.specializations = [
                    li.get_text(strip=True) 
                    for li in spec_section.find_all('li')
                ]
            
            return lawyer
            
        except Exception as e:
            logger.error(f"Error scraping profile {profile_url}: {e}")
            return None
    
    def _extract_email(self, section) -> Optional[str]:
        """Extract email from a section"""
        email_link = section.find('a', href=lambda x: x and 'mailto:' in x)
        if email_link:
            return email_link['href'].replace('mailto:', '')
        return None
    
    def _extract_website(self, section) -> Optional[str]:
        """Extract website from a section"""
        website_link = section.find('a', href=lambda x: x and 'http' in x)
        if website_link:
            return website_link['href']
        return None
    
    async def scrape_all_cities(self, cities: List[str]) -> List[LawyerEntry]:
        """
        Scrape lawyers from multiple cities
        
        Args:
            cities: List of city names
            
        Returns:
            Combined list of all lawyers
        """
        all_lawyers = []
        
        for city in cities:
            logger.info(f"Scraping city: {city}")
            try:
                lawyers = await self.search_by_city(city)
                all_lawyers.extend(lawyers)
                logger.info(f"Found {len(lawyers)} lawyers in {city}")
                
                # Rate limiting
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error scraping {city}: {e}")
                continue
        
        return all_lawyers
    
    def save_to_csv(self, lawyers: List[LawyerEntry], filename: str):
        """Save lawyers to CSV file"""
        if not lawyers:
            logger.warning("No lawyers to save")
            return
        
        df = pd.DataFrame([lawyer.to_dict() for lawyer in lawyers])
        df.to_csv(filename, index=False, encoding='utf-8')
        logger.info(f"Saved {len(lawyers)} lawyers to {filename}")
    
    def save_to_json(self, lawyers: List[LawyerEntry], filename: str):
        """Save lawyers to JSON file"""
        if not lawyers:
            logger.warning("No lawyers to save")
            return
        
        data = [lawyer.to_dict() for lawyer in lawyers]
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(lawyers)} lawyers to {filename}")
    
    def save_to_excel(self, lawyers: List[LawyerEntry], filename: str):
        """Save lawyers to Excel file with formatting"""
        if not lawyers:
            logger.warning("No lawyers to save")
            return
        
        df = pd.DataFrame([lawyer.to_dict() for lawyer in lawyers])
        
        # Create Excel writer with formatting
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Lawyers', index=False)
            
            # Auto-adjust column widths
            worksheet = writer.sheets['Lawyers']
            for column in df:
                column_width = max(df[column].astype(str).map(len).max(), len(column))
                col_idx = df.columns.get_loc(column)
                worksheet.column_dimensions[chr(65 + col_idx)].width = min(column_width + 2, 50)
        
        logger.info(f"Saved {len(lawyers)} lawyers to {filename}")


async def main():
    """Main function to run the scraper"""
    
    print("""
    BRAK Lawyer Database Scraper (Playwright Version)
    =================================================
    
    This advanced scraper uses Playwright to handle dynamic content.
    
    Features:
    - Handles JavaScript-rendered content
    - Automatic pagination
    - Detailed profile scraping
    - Multiple export formats (CSV, JSON, Excel)
    
    Note: First run may take time to download browser.
    """)
    
    # German cities to scrape
    cities = [
        'Berlin', 'München', 'Hamburg', 'Köln', 'Frankfurt',
        'Stuttgart', 'Düsseldorf', 'Leipzig', 'Dortmund', 'Essen'
    ]
    
    scraper = BRAKPlaywrightScraper(headless=True)
    
    try:
        await scraper.initialize()
        
        # Example: Search by city
        print("\nScraping lawyers from major cities...")
        all_lawyers = await scraper.scrape_all_cities(cities[:3])  # Start with 3 cities
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("brak_data")
        output_dir.mkdir(exist_ok=True)
        
        # Save in multiple formats
        scraper.save_to_csv(all_lawyers, output_dir / f"lawyers_{timestamp}.csv")
        scraper.save_to_json(all_lawyers, output_dir / f"lawyers_{timestamp}.json")
        scraper.save_to_excel(all_lawyers, output_dir / f"lawyers_{timestamp}.xlsx")
        
        print(f"\nCompleted! Scraped {len(all_lawyers)} lawyer records")
        print(f"Data saved to {output_dir}/")
        
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())