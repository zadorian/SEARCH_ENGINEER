#!/usr/bin/env python3
"""
Scrape specific Bellingcat articles and guides
"""

import os
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv(override=True)

# Import Firecrawl service
from FactAssembler.firecrawl_service import FirecrawlService

# Cache directory
CACHE_DIR = Path("cache/bellingcat_resources")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Known important Bellingcat resources and guides
BELLINGCAT_ARTICLES = [
    # Recent 2024 guides
    "https://www.bellingcat.com/resources/2024/11/08/geolocation-geoguessr-google-earth/",
    "https://www.bellingcat.com/resources/2024/10/31/osint-time-travel-wayback-machine-google-earth/",
    "https://www.bellingcat.com/resources/2024/09/26/telegram-phone-number-lookup-guide/",
    "https://www.bellingcat.com/resources/2024/08/21/ai-osint-tools-investigation/",
    
    # Key how-to guides
    "https://www.bellingcat.com/resources/how-tos/2024/10/15/geolocation-basics-tips-verification/",
    "https://www.bellingcat.com/resources/how-tos/2024/09/10/satellite-imagery-analysis/",
    "https://www.bellingcat.com/resources/how-tos/2024/08/05/social-media-investigation-guide/",
    "https://www.bellingcat.com/resources/how-tos/2024/07/20/reverse-image-search-techniques/",
    
    # Case studies
    "https://www.bellingcat.com/resources/case-studies/2024/11/01/ukraine-geolocation-case/",
    "https://www.bellingcat.com/resources/case-studies/2024/10/15/syria-verification-study/",
    
    # The famous toolkit
    "https://www.bellingcat.com/resources/toolkit/",
    "https://docs.google.com/spreadsheets/d/18rtqh8EG2q1xBo2cLNyhIDuK9jrPGwYr9DI2UncoqJQ/",
    
    # Some classic guides
    "https://www.bellingcat.com/resources/2023/03/08/ukraine-war-osint-guide/",
    "https://www.bellingcat.com/resources/2023/06/23/chronolocation-guide/",
    "https://www.bellingcat.com/resources/2023/08/15/metadata-analysis-guide/",
    "https://www.bellingcat.com/resources/2023/09/20/reverse-image-search-guide/",
    "https://www.bellingcat.com/resources/2023/10/05/social-media-investigation-guide/",
    "https://www.bellingcat.com/resources/2023/11/10/satellite-imagery-guide/",
    "https://www.bellingcat.com/resources/2023/12/15/flight-tracking-guide/",
    
    # Add main pages again for completeness
    "https://www.bellingcat.com/resources/",
    "https://www.bellingcat.com/resources/how-tos/",
    "https://www.bellingcat.com/resources/case-studies/"
]

def main():
    print("\n" + "="*60)
    print("BELLINGCAT ARTICLES SCRAPER")
    print("="*60)
    
    print(f"\n📚 Will scrape {len(BELLINGCAT_ARTICLES)} specific articles")
    
    # Initialize Firecrawl
    firecrawl = FirecrawlService()
    
    # Batch scrape all articles
    print(f"\n🚀 Batch scraping {len(BELLINGCAT_ARTICLES)} articles...")
    
    try:
        results = firecrawl._batch_scrape_parallel(BELLINGCAT_ARTICLES)
        
        # Count successes
        successful = sum(1 for url, (_, content, _) in results.items() if content)
        print(f"\n✅ Successfully scraped {successful}/{len(BELLINGCAT_ARTICLES)} articles")
        
        # Save all content
        articles_file = CACHE_DIR / "bellingcat_articles.json"
        articles_data = {}
        
        for url, (_, content, metadata) in results.items():
            if content:
                # Extract title from metadata or content
                title = metadata.get('title', '')
                if not title:
                    lines = content.split('\n')
                    for line in lines[:5]:
                        if line.strip():
                            title = line.strip()[:100]
                            break
                
                articles_data[url] = {
                    "url": url,
                    "title": title,
                    "content": content[:100000],  # Limit to 100k chars
                    "metadata": metadata,
                    "scraped_at": datetime.now().isoformat()
                }
                
                print(f"   ✓ {title[:60]}")
        
        # Save to file
        with open(articles_file, 'w') as f:
            json.dump(articles_data, f, indent=2)
        
        print(f"\n💾 Saved to {articles_file}")
        print(f"   Total articles: {len(articles_data)}")
        print(f"   File size: {articles_file.stat().st_size / 1024 / 1024:.1f} MB")
        
        # Create combined JSONL for vector store
        combined_file = CACHE_DIR / "bellingcat_all.jsonl"
        
        with open(combined_file, 'w') as f:
            # Add previous documents
            if (CACHE_DIR / "bellingcat_documents.jsonl").exists():
                with open(CACHE_DIR / "bellingcat_documents.jsonl", 'r') as prev:
                    f.write(prev.read())
            
            # Add new articles
            for url, data in articles_data.items():
                doc = {
                    "text": f"{data['title']}\n\nURL: {url}\n\n{data['content']}",
                    "metadata": {
                        "source": "bellingcat",
                        "url": url,
                        "title": data['title'],
                        "type": "article"
                    }
                }
                f.write(json.dumps(doc) + '\n')
        
        print(f"\n✅ Combined file ready: {combined_file}")
        print("\n🎯 Next steps:")
        print("   1. Upload to OpenAI vector store when API is fixed")
        print("   2. Or use local embeddings with the JSONL file")
        print("   3. Content is ready for WikiMan integration")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()