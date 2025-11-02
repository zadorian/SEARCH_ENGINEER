#!/usr/bin/env python3
"""
Final BRAK Scraper - Working version with correct selectors
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


async def scrape_brak_lawyers():
    """Scrape BRAK lawyer database with correct form fields"""
    
    output_dir = Path("brak_data")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    all_lawyers = []
    
    async with async_playwright() as p:
        # Launch browser (set headless=False to watch it work)
        logger.info("Launching browser...")
        browser = await p.chromium.launch(
            headless=False,  # Watch the browser
            slow_mo=100  # Slow down actions
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='de-DE',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()
        
        # Cities to search
        cities = ['Berlin', 'München', 'Hamburg', 'Köln', 'Frankfurt']
        
        for city in cities:
            try:
                logger.info(f"\n{'='*50}")
                logger.info(f"Searching for lawyers in {city}")
                logger.info('='*50)
                
                # Navigate to search page
                await page.goto('https://bravsearch.bea-brak.de/bravsearch/index.brak', 
                              wait_until='networkidle', timeout=30000)
                
                await page.wait_for_timeout(2000)
                
                # Fill in the city field using the correct ID
                logger.info(f"Filling city field with '{city}'")
                city_field = await page.query_selector('#searchForm\\:txtOrt')
                if city_field:
                    await city_field.fill(city)
                    logger.info("✓ City field filled")
                else:
                    # Try alternative selector
                    await page.fill('input[id="searchForm:txtOrt"]', city)
                    logger.info("✓ City field filled (alternative)")
                
                await page.wait_for_timeout(500)
                
                # Click the search button
                logger.info("Clicking search button...")
                search_button = await page.query_selector('#searchForm\\:cmdSearch')
                if search_button:
                    await search_button.click()
                else:
                    # Try alternative
                    await page.click('button[id="searchForm:cmdSearch"]')
                
                logger.info("Waiting for results...")
                
                # Wait for navigation or results to load
                try:
                    await page.wait_for_load_state('networkidle', timeout=10000)
                except:
                    pass
                
                await page.wait_for_timeout(3000)
                
                # Take screenshot
                screenshot_path = output_dir / f'results_{city}_{timestamp}.png'
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"Screenshot saved: {screenshot_path.name}")
                
                # Get page content
                content = await page.content()
                
                # Save HTML for debugging
                html_path = output_dir / f'results_{city}_{timestamp}.html'
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"HTML saved: {html_path.name}")
                
                # Parse results with BeautifulSoup
                soup = BeautifulSoup(content, 'html.parser')
                
                # Look for result elements
                # Check if we have results or error messages
                if 'Keine Treffer' in content or 'keine Ergebnisse' in content.lower():
                    logger.warning(f"No results found for {city}")
                    continue
                
                # Extract lawyer data from various possible structures
                lawyers_found = []
                
                # Method 1: Look for result tables
                tables = soup.find_all('table')
                for table in tables:
                    # Skip navigation/layout tables
                    if 'ui-panelgrid' in str(table.get('class', [])):
                        continue
                    
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            # Extract text from cells
                            lawyer_data = {
                                'city_search': city,
                                'raw_data': [cell.get_text(strip=True) for cell in cells if cell.get_text(strip=True)]
                            }
                            
                            # Try to identify specific fields
                            for i, cell in enumerate(cells):
                                text = cell.get_text(strip=True)
                                if text:
                                    if 'Rechtsanwalt' in text or 'Rechtsanwältin' in text:
                                        lawyer_data['name'] = text
                                    elif '@' in text:
                                        lawyer_data['email'] = text
                                    elif any(c.isdigit() for c in text) and len(text) == 5:
                                        lawyer_data['postal_code'] = text
                                    elif 'straße' in text.lower() or 'str.' in text.lower():
                                        lawyer_data['address'] = text
                            
                            if lawyer_data.get('raw_data'):
                                lawyers_found.append(lawyer_data)
                
                # Method 2: Look for specific result divs
                result_divs = soup.find_all('div', class_=['result', 'lawyer-entry', 'search-result'])
                for div in result_divs:
                    lawyer_text = div.get_text(separator=' | ', strip=True)
                    if lawyer_text:
                        lawyers_found.append({
                            'city_search': city,
                            'text': lawyer_text
                        })
                
                # Method 3: Extract all visible text and look for patterns
                if not lawyers_found:
                    # Get all text
                    page_text = await page.evaluate('() => document.body.innerText')
                    
                    # Save text for analysis
                    text_path = output_dir / f'text_{city}_{timestamp}.txt'
                    with open(text_path, 'w', encoding='utf-8') as f:
                        f.write(page_text)
                    logger.info(f"Page text saved: {text_path.name}")
                    
                    # Look for lawyer patterns in text
                    lines = page_text.split('\n')
                    for line in lines:
                        if 'Rechtsanwalt' in line or 'Rechtsanwältin' in line:
                            lawyers_found.append({
                                'city_search': city,
                                'text_line': line.strip()
                            })
                
                if lawyers_found:
                    logger.info(f"✅ Found {len(lawyers_found)} potential lawyer entries")
                    all_lawyers.extend(lawyers_found)
                    
                    # Save city results
                    city_json = output_dir / f'lawyers_{city}_{timestamp}.json'
                    with open(city_json, 'w', encoding='utf-8') as f:
                        json.dump(lawyers_found, f, ensure_ascii=False, indent=2)
                    logger.info(f"Data saved: {city_json.name}")
                else:
                    logger.warning(f"⚠️ No lawyer data extracted for {city}")
                
            except Exception as e:
                logger.error(f"Error searching {city}: {e}")
                
                # Take error screenshot
                try:
                    await page.screenshot(path=output_dir / f'error_{city}_{timestamp}.png')
                except:
                    pass
            
            # Rate limiting between cities
            if city != cities[-1]:
                logger.info("\n⏳ Waiting before next search (rate limiting)...")
                await page.wait_for_timeout(3000)
        
        await browser.close()
    
    # Save all results
    if all_lawyers:
        final_path = output_dir / f'all_lawyers_final_{timestamp}.json'
        with open(final_path, 'w', encoding='utf-8') as f:
            json.dump(all_lawyers, f, ensure_ascii=False, indent=2)
        
        logger.info(f"\n{'='*50}")
        logger.info(f"✨ COMPLETE: Found {len(all_lawyers)} total lawyer entries")
        logger.info(f"📁 All data saved in: {output_dir.absolute()}")
        logger.info('='*50)
    else:
        logger.warning("\n⚠️ No lawyers found. Check the screenshots and HTML files for debugging.")
    
    return all_lawyers


async def main():
    print("""
    ╔══════════════════════════════════════════╗
    ║    BRAK Lawyer Database Scraper         ║
    ║    Final Working Version                 ║
    ╚══════════════════════════════════════════╝
    
    This scraper will:
    1. Open a browser window (watch it work!)
    2. Search for lawyers in major German cities
    3. Save screenshots and data for each city
    4. Export results to JSON format
    
    Starting in 3 seconds...
    """)
    
    await asyncio.sleep(3)
    
    lawyers = await scrape_brak_lawyers()
    
    print(f"\n✅ Scraping complete!")
    print(f"📊 Total entries found: {len(lawyers)}")
    print(f"📁 Check the 'brak_data' folder for results")


if __name__ == "__main__":
    asyncio.run(main())