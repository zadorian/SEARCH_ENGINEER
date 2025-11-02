#!/usr/bin/env python3
"""
Automated BRAK Lawyer Scraper - Runs without user interaction
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime
import logging
from BRAK_lawyer_scraper import BRAKScraper

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def automated_scrape():
    """Run automated scraping of BRAK database"""
    
    print("""
    ========================================
    Starting BRAK Lawyer Database Scraper
    ========================================
    
    This will automatically scrape lawyer data from major German cities.
    The process respects rate limits and may take some time.
    
    Starting in 3 seconds...
    """)
    
    time.sleep(3)
    
    # Initialize scraper with conservative rate limits
    scraper = BRAKScraper(delay_min=2.0, delay_max=4.0)
    
    # Create output directory
    output_dir = Path("brak_lawyers_data")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Start with a few test cities
    test_cities = ['Berlin', 'München', 'Hamburg', 'Frankfurt', 'Köln']
    
    print(f"\n📍 Scraping lawyers from {len(test_cities)} major cities...")
    print(f"Output directory: {output_dir.absolute()}\n")
    
    all_lawyers = []
    city_stats = {}
    
    for i, city in enumerate(test_cities, 1):
        print(f"\n[{i}/{len(test_cities)}] Processing {city}...")
        print("-" * 40)
        
        try:
            # Search by city
            lawyers = scraper.search_by_city(city)
            
            if lawyers:
                # Save city-specific file
                city_file = output_dir / f"lawyers_{city.lower()}_{timestamp}.json"
                with open(city_file, 'w', encoding='utf-8') as f:
                    json.dump(lawyers, f, ensure_ascii=False, indent=2)
                
                all_lawyers.extend(lawyers)
                city_stats[city] = len(lawyers)
                
                print(f"✅ Found {len(lawyers)} lawyers in {city}")
                print(f"   Saved to: {city_file.name}")
            else:
                print(f"⚠️  No lawyers found in {city} (may need to check HTML parsing)")
                city_stats[city] = 0
                
        except Exception as e:
            print(f"❌ Error processing {city}: {e}")
            city_stats[city] = -1
            continue
        
        # Progress indicator
        if i < len(test_cities):
            print(f"\n⏳ Waiting before next city (rate limiting)...")
            time.sleep(3)
    
    # Summary statistics
    print("\n" + "=" * 50)
    print("SCRAPING COMPLETE - SUMMARY")
    print("=" * 50)
    
    print(f"\n📊 Results by city:")
    for city, count in city_stats.items():
        if count >= 0:
            print(f"   {city:15} : {count:,} lawyers")
        else:
            print(f"   {city:15} : ERROR")
    
    print(f"\n📈 Total lawyers scraped: {len(all_lawyers):,}")
    
    # Save combined results
    if all_lawyers:
        combined_file = output_dir / f"all_lawyers_combined_{timestamp}.json"
        with open(combined_file, 'w', encoding='utf-8') as f:
            json.dump(all_lawyers, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Combined data saved to: {combined_file.name}")
        
        # Also save as CSV for easy viewing
        import csv
        csv_file = output_dir / f"all_lawyers_combined_{timestamp}.csv"
        if all_lawyers:
            keys = all_lawyers[0].keys()
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(all_lawyers)
            print(f"📊 CSV export saved to: {csv_file.name}")
    
    print(f"\n✨ All files saved in: {output_dir.absolute()}")
    
    # Test with alphabetical search for one letter
    print("\n" + "=" * 50)
    print("TESTING ALPHABETICAL SEARCH")
    print("=" * 50)
    
    test_letter = 'M'  # Test with letter M
    print(f"\n🔤 Testing search for lawyers with last name starting with '{test_letter}'...")
    
    try:
        lawyers_m = scraper.search_by_name(last_name=f"{test_letter}*")
        if lawyers_m:
            letter_file = output_dir / f"lawyers_letter_{test_letter}_{timestamp}.json"
            with open(letter_file, 'w', encoding='utf-8') as f:
                json.dump(lawyers_m, f, ensure_ascii=False, indent=2)
            print(f"✅ Found {len(lawyers_m)} lawyers with last name starting with '{test_letter}'")
            print(f"   Saved to: {letter_file.name}")
        else:
            print(f"⚠️  No results for letter '{test_letter}'")
    except Exception as e:
        print(f"❌ Error in alphabetical search: {e}")
    
    print("\n" + "=" * 50)
    print("🏁 Scraping process completed!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        automated_scrape()
    except KeyboardInterrupt:
        print("\n\n⚠️  Scraping interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)