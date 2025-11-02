#!/usr/bin/env python3
"""
OpenCorporates Profile Screenshot Fetcher
=========================================
Fetches company data from OpenCorporates API and takes screenshots 
of each profile page using Firecrawl.

Usage: python3 opencorporates_screenshot_fetcher.py
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Search_Types.corporate.global.API.opencorporates import OpenCorporatesAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OpenCorporatesScreenshotFetcher:
    """Fetches OpenCorporates profiles and takes screenshots via Firecrawl"""
    
    def __init__(self, firecrawl_api_key: str = None):
        # Initialize OpenCorporates API
        self.oc_api = OpenCorporatesAPI()
        
        # Firecrawl configuration
        self.firecrawl_api_key = firecrawl_api_key or os.getenv('FIRECRAWL_API_KEY')
        if not self.firecrawl_api_key:
            raise ValueError("FIRECRAWL_API_KEY environment variable must be set")
        
        self.firecrawl_base_url = "https://api.firecrawl.dev/v1"
        
        # Create output directories
        self.output_dir = Path("opencorporates_screenshots")
        self.output_dir.mkdir(exist_ok=True)
        
        self.data_dir = Path("opencorporates_data")
        self.data_dir.mkdir(exist_ok=True)
        
        # Track processed URLs to avoid duplicates
        self.processed_urls = set()
        self.load_processed_urls()
        
    def load_processed_urls(self):
        """Load list of already processed URLs"""
        processed_file = self.output_dir / "processed_urls.txt"
        if processed_file.exists():
            with open(processed_file, 'r') as f:
                self.processed_urls = set(line.strip() for line in f)
            logger.info(f"Loaded {len(self.processed_urls)} previously processed URLs")
    
    def save_processed_url(self, url: str):
        """Save a processed URL to the tracking file"""
        self.processed_urls.add(url)
        with open(self.output_dir / "processed_urls.txt", 'a') as f:
            f.write(f"{url}\n")
    
    def search_companies(self, company_name: str, max_results: int = 30) -> List[Dict]:
        """Search for companies and return their data"""
        logger.info(f"Searching OpenCorporates for: {company_name}")
        
        results = self.oc_api.search_companies(company_name, max_results=max_results)
        
        if not results.get('success'):
            logger.error(f"Search failed: {results.get('error', 'Unknown error')}")
            return []
        
        companies = results.get('companies', [])
        logger.info(f"Found {len(companies)} companies")
        
        # Save the raw search results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = self.data_dir / f"search_{company_name.replace(' ', '_')}_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Saved search results to: {results_file}")
        
        return companies
    
    def take_screenshot_with_firecrawl(self, url: str, company_data: Dict) -> Optional[str]:
        """Take a screenshot of a URL using Firecrawl API"""
        
        if url in self.processed_urls:
            logger.info(f"Skipping already processed URL: {url}")
            return None
        
        logger.info(f"Taking screenshot of: {url}")
        
        try:
            # Prepare the Firecrawl scrape request with screenshot
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.firecrawl_api_key}'
            }
            
            # Request body for Firecrawl - requesting screenshot format
            data = {
                'url': url,
                'formats': ['screenshot', 'markdown'],  # Get both screenshot and content
                'onlyMainContent': False,  # Get full page for corporate profiles
                'waitFor': 2000,  # Wait 2 seconds for page to load
                'actions': [
                    {
                        'type': 'wait',
                        'milliseconds': 1000  # Additional wait for dynamic content
                    },
                    {
                        'type': 'screenshot',
                        'fullPage': True  # Full page screenshot
                    }
                ]
            }
            
            # Make the request to Firecrawl
            response = requests.post(
                f"{self.firecrawl_base_url}/scrape",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('success'):
                    data = result.get('data', {})
                    
                    # Extract screenshot URL
                    screenshot_url = data.get('screenshot')
                    markdown_content = data.get('markdown', '')
                    
                    # Generate filename based on company info
                    safe_name = company_data.get('name', 'unknown').replace('/', '_').replace(' ', '_')
                    jurisdiction = company_data.get('jurisdiction', 'unknown')
                    company_number = company_data.get('company_number', 'unknown')
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    base_filename = f"{safe_name}_{jurisdiction}_{company_number}_{timestamp}"
                    
                    # Save screenshot if available
                    if screenshot_url:
                        screenshot_file = self.output_dir / f"{base_filename}.png"
                        
                        # Download the screenshot
                        screenshot_response = requests.get(screenshot_url)
                        if screenshot_response.status_code == 200:
                            with open(screenshot_file, 'wb') as f:
                                f.write(screenshot_response.content)
                            logger.info(f"✅ Saved screenshot: {screenshot_file}")
                        else:
                            logger.error(f"Failed to download screenshot from: {screenshot_url}")
                    
                    # Save markdown content
                    if markdown_content:
                        markdown_file = self.data_dir / f"{base_filename}.md"
                        with open(markdown_file, 'w') as f:
                            f.write(f"# {company_data.get('name', 'Unknown Company')}\n\n")
                            f.write(f"**URL**: {url}\n")
                            f.write(f"**Jurisdiction**: {jurisdiction}\n")
                            f.write(f"**Company Number**: {company_number}\n")
                            f.write(f"**Status**: {company_data.get('status', 'Unknown')}\n\n")
                            f.write("---\n\n")
                            f.write(markdown_content)
                        logger.info(f"✅ Saved content: {markdown_file}")
                    
                    # Save metadata
                    metadata_file = self.data_dir / f"{base_filename}_metadata.json"
                    with open(metadata_file, 'w') as f:
                        json.dump({
                            'url': url,
                            'company_data': company_data,
                            'screenshot_url': screenshot_url,
                            'timestamp': timestamp,
                            'firecrawl_response': data.get('metadata', {})
                        }, f, indent=2)
                    
                    # Mark URL as processed
                    self.save_processed_url(url)
                    
                    return screenshot_file if screenshot_url else None
                else:
                    logger.error(f"Firecrawl returned success=false: {result}")
            else:
                logger.error(f"Firecrawl API error: {response.status_code} - {response.text}")
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout while processing: {url}")
        except Exception as e:
            logger.error(f"Error taking screenshot of {url}: {e}")
        
        return None
    
    def process_company_profiles(self, company_name: str, max_results: int = 10):
        """Main function to search and screenshot company profiles"""
        
        # Search for companies
        companies = self.search_companies(company_name, max_results=max_results)
        
        if not companies:
            logger.warning("No companies found")
            return
        
        # Process each company
        successful_screenshots = 0
        failed_screenshots = 0
        
        for i, company in enumerate(companies, 1):
            # Get the OpenCorporates URL
            oc_url = company.get('opencorporates_url')
            
            if not oc_url:
                # Construct URL if not provided
                jurisdiction = company.get('jurisdiction')
                company_number = company.get('company_number')
                if jurisdiction and company_number:
                    oc_url = f"https://opencorporates.com/companies/{jurisdiction}/{company_number}"
                else:
                    logger.warning(f"No URL available for company: {company.get('name')}")
                    continue
            
            logger.info(f"\n[{i}/{len(companies)}] Processing: {company.get('name')}")
            logger.info(f"  URL: {oc_url}")
            
            # Take screenshot
            screenshot_path = self.take_screenshot_with_firecrawl(oc_url, company)
            
            if screenshot_path:
                successful_screenshots += 1
            else:
                failed_screenshots += 1
            
            # Rate limiting - be respectful to Firecrawl
            if i < len(companies):
                time.sleep(2)  # 2 second delay between requests
        
        # Summary
        logger.info(f"\n{'='*60}")
        logger.info(f"PROCESSING COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"✅ Successful screenshots: {successful_screenshots}")
        logger.info(f"❌ Failed screenshots: {failed_screenshots}")
        logger.info(f"📁 Output directory: {self.output_dir}")
        logger.info(f"📁 Data directory: {self.data_dir}")

def main():
    """Main entry point"""
    
    # Check for Firecrawl API key
    firecrawl_key = os.getenv('FIRECRAWL_API_KEY')
    if not firecrawl_key:
        print("⚠️ FIRECRAWL_API_KEY environment variable not set")
        firecrawl_key = input("Please enter your Firecrawl API key: ").strip()
        if not firecrawl_key:
            print("❌ ERROR: Firecrawl API key is required")
            sys.exit(1)
        # Set it for this session
        os.environ['FIRECRAWL_API_KEY'] = firecrawl_key
    
    # Create fetcher instance
    fetcher = OpenCorporatesScreenshotFetcher()
    
    # Get company name from user
    print("\n" + "="*60)
    print("OpenCorporates Profile Screenshot Fetcher")
    print("="*60)
    
    while True:
        company_name = input("\nEnter company name to search (or 'quit' to exit): ").strip()
        
        if company_name.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        if not company_name:
            print("Please enter a company name")
            continue
        
        # Get max results
        max_results_input = input("Maximum number of profiles to screenshot (default: 10): ").strip()
        max_results = 10
        if max_results_input:
            try:
                max_results = int(max_results_input)
            except ValueError:
                print("Invalid number, using default of 10")
        
        # Process the company
        fetcher.process_company_profiles(company_name, max_results=max_results)
        
        print("\n" + "-"*60)

if __name__ == "__main__":
    main()