#!/usr/bin/env python3
"""
Simple BRAK Scraper using Playwright
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


async def scrape_brak():
    """Simple scraper for BRAK website"""
    
    output_dir = Path("brak_data")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    async with async_playwright() as p:
        # Launch browser
        logger.info("Launching browser...")
        browser = await p.chromium.launch(
            headless=False,  # Set to False to see what's happening
            slow_mo=500  # Slow down for debugging
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='de-DE'
        )
        
        page = await context.new_page()
        
        try:
            # Navigate to BRAK search
            logger.info("Navigating to BRAK search page...")
            await page.goto('https://bravsearch.bea-brak.de/bravsearch/index.brak', 
                          wait_until='networkidle')
            
            # Take screenshot of search page
            await page.screenshot(path=output_dir / f'brak_search_page_{timestamp}.png')
            logger.info("Screenshot of search page saved")
            
            # Wait for page to load
            await page.wait_for_timeout(2000)
            
            # Try to find search fields
            logger.info("Looking for search fields...")
            
            # Search by city - Berlin
            city_field = await page.query_selector('input[name="ort"]')
            if city_field:
                logger.info("Found city field, entering 'Berlin'")
                await city_field.fill("Berlin")
            else:
                logger.warning("City field not found")
            
            # Submit search
            submit_button = await page.query_selector('input[type="submit"]')
            if submit_button:
                logger.info("Clicking submit button...")
                await submit_button.click()
                
                # Wait for results
                await page.wait_for_timeout(5000)
                
                # Take screenshot of results
                await page.screenshot(path=output_dir / f'brak_results_{timestamp}.png')
                logger.info("Screenshot of results saved")
                
                # Get page content
                content = await page.content()
                
                # Save raw HTML for analysis
                html_file = output_dir / f'brak_results_{timestamp}.html'
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"Raw HTML saved to {html_file}")
                
                # Try to extract any visible text
                text_content = await page.evaluate('() => document.body.innerText')
                
                text_file = output_dir / f'brak_text_{timestamp}.txt'
                with open(text_file, 'w', encoding='utf-8') as f:
                    f.write(text_content)
                logger.info(f"Text content saved to {text_file}")
                
                # Look for result elements
                # Try different selectors
                selectors_to_try = [
                    'table.ergebnisliste',
                    'table.results',
                    'div.result',
                    'div.lawyer',
                    'tr.result-row',
                    'div[class*="ergebnis"]',
                    'div[class*="result"]',
                    'table[class*="result"]'
                ]
                
                for selector in selectors_to_try:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        logger.info(f"Found {len(elements)} elements with selector: {selector}")
                        break
                else:
                    logger.warning("No result elements found with known selectors")
                
                # Try to extract structured data
                lawyers = []
                
                # Method 1: Look for tables
                tables = await page.query_selector_all('table')
                logger.info(f"Found {len(tables)} tables on page")
                
                for i, table in enumerate(tables):
                    rows = await table.query_selector_all('tr')
                    logger.info(f"Table {i+1} has {len(rows)} rows")
                    
                    for row in rows[:5]:  # First 5 rows as sample
                        cells = await row.query_selector_all('td')
                        if cells:
                            row_data = []
                            for cell in cells:
                                text = await cell.inner_text()
                                row_data.append(text.strip())
                            
                            if any(row_data):  # If row has content
                                lawyers.append({
                                    'raw_data': row_data,
                                    'source': f'table_{i+1}'
                                })
                
                # Save any extracted data
                if lawyers:
                    json_file = output_dir / f'brak_lawyers_{timestamp}.json'
                    with open(json_file, 'w', encoding='utf-8') as f:
                        json.dump(lawyers, f, ensure_ascii=False, indent=2)
                    logger.info(f"Extracted {len(lawyers)} entries saved to {json_file}")
                
            else:
                logger.error("Submit button not found")
                
                # Save page source for debugging
                content = await page.content()
                debug_file = output_dir / f'brak_debug_{timestamp}.html'
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"Debug HTML saved to {debug_file}")
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            
            # Take error screenshot
            await page.screenshot(path=output_dir / f'brak_error_{timestamp}.png')
            
        finally:
            await browser.close()
    
    logger.info(f"Scraping complete. Check {output_dir} for results.")


async def main():
    print("""
    ======================================
    BRAK Playwright Scraper
    ======================================
    
    This will open a browser window and attempt to scrape
    the BRAK lawyer database.
    
    Watch the browser to see what's happening...
    """)
    
    await scrape_brak()


if __name__ == "__main__":
    asyncio.run(main())