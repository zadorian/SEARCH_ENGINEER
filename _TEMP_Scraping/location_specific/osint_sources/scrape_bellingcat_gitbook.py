#!/usr/bin/env python3
"""
Scrape Bellingcat's new GitBook toolkit resources
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
from openai import OpenAI

# Cache directory
CACHE_DIR = Path("cache/bellingcat_gitbook")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Bellingcat GitBook toolkit URLs
BELLINGCAT_GITBOOK_URLS = [
    # Main pages
    "https://bellingcat.gitbook.io/toolkit",
    "https://bellingcat.gitbook.io/toolkit/resources",
    
    # Resource categories from the GitBook
    "https://bellingcat.gitbook.io/toolkit/resources/geolocation",
    "https://bellingcat.gitbook.io/toolkit/resources/chronolocation",
    "https://bellingcat.gitbook.io/toolkit/resources/satellite-and-aerial-imagery",
    "https://bellingcat.gitbook.io/toolkit/resources/maps",
    "https://bellingcat.gitbook.io/toolkit/resources/social-media-platforms",
    "https://bellingcat.gitbook.io/toolkit/resources/websites",
    "https://bellingcat.gitbook.io/toolkit/resources/companies",
    "https://bellingcat.gitbook.io/toolkit/resources/transport",
    "https://bellingcat.gitbook.io/toolkit/resources/people-search",
    "https://bellingcat.gitbook.io/toolkit/resources/data-and-statistics",
    "https://bellingcat.gitbook.io/toolkit/resources/weapons-identification",
    "https://bellingcat.gitbook.io/toolkit/resources/archives",
    "https://bellingcat.gitbook.io/toolkit/resources/leaked-data",
    "https://bellingcat.gitbook.io/toolkit/resources/phone-numbers",
    "https://bellingcat.gitbook.io/toolkit/resources/email-addresses",
    "https://bellingcat.gitbook.io/toolkit/resources/infrastructure",
    "https://bellingcat.gitbook.io/toolkit/resources/academic-research",
    "https://bellingcat.gitbook.io/toolkit/resources/ai-and-machine-learning",
    "https://bellingcat.gitbook.io/toolkit/resources/miscellaneous",
    
    # How-to guides section
    "https://bellingcat.gitbook.io/toolkit/how-to-guides",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/geolocation",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/chronolocation",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/reverse-image-search",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/metadata-extraction",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/social-media-investigation",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/satellite-imagery-analysis",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/flight-tracking",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/maritime-tracking",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/cryptocurrency-investigation",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/facial-recognition",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/archive-tools",
    "https://bellingcat.gitbook.io/toolkit/how-to-guides/verification-techniques",
    
    # Case studies
    "https://bellingcat.gitbook.io/toolkit/case-studies",
    "https://bellingcat.gitbook.io/toolkit/case-studies/mh17-investigation",
    "https://bellingcat.gitbook.io/toolkit/case-studies/skripal-poisoning",
    "https://bellingcat.gitbook.io/toolkit/case-studies/navalny-poisoning",
    "https://bellingcat.gitbook.io/toolkit/case-studies/ukraine-conflict",
    "https://bellingcat.gitbook.io/toolkit/case-studies/syria-chemical-attacks",
    
    # Tools and scripts
    "https://bellingcat.gitbook.io/toolkit/tools-and-scripts",
    "https://bellingcat.gitbook.io/toolkit/tools-and-scripts/python-scripts",
    "https://bellingcat.gitbook.io/toolkit/tools-and-scripts/browser-extensions",
    "https://bellingcat.gitbook.io/toolkit/tools-and-scripts/command-line-tools",
    
    # Training materials
    "https://bellingcat.gitbook.io/toolkit/training",
    "https://bellingcat.gitbook.io/toolkit/training/beginners-guide",
    "https://bellingcat.gitbook.io/toolkit/training/advanced-techniques",
    "https://bellingcat.gitbook.io/toolkit/training/workshops"
]

def main():
    print("\n" + "="*60)
    print("BELLINGCAT GITBOOK TOOLKIT SCRAPER")
    print("="*60)
    
    print(f"\n📚 Will scrape {len(BELLINGCAT_GITBOOK_URLS)} GitBook pages")
    print("   From: https://bellingcat.gitbook.io/toolkit/")
    
    # Initialize Firecrawl
    firecrawl = FirecrawlService()
    client = OpenAI()
    
    # Batch scrape all pages
    print(f"\n🚀 Batch scraping {len(BELLINGCAT_GITBOOK_URLS)} pages...")
    print("   Using Firecrawl v2 API with batch processing")
    
    all_results = {}
    batch_size = 50
    
    for i in range(0, len(BELLINGCAT_GITBOOK_URLS), batch_size):
        batch = BELLINGCAT_GITBOOK_URLS[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(BELLINGCAT_GITBOOK_URLS) + batch_size - 1) // batch_size
        
        print(f"\n   Batch {batch_num}/{total_batches}: Scraping {len(batch)} URLs...")
        
        try:
            results = firecrawl._batch_scrape_parallel(batch)
            
            success_count = 0
            for url, (_, content, metadata) in results.items():
                if content:
                    all_results[url] = {
                        "url": url,
                        "content": content,
                        "metadata": metadata,
                        "scraped_at": datetime.now().isoformat(),
                        "success": True
                    }
                    success_count += 1
                    
                    # Extract title
                    title = metadata.get('title', '')
                    if not title:
                        lines = content.split('\n')
                        for line in lines[:5]:
                            if line.strip():
                                title = line.strip()[:100]
                                break
                    
                    print(f"      ✓ {title[:60]}")
            
            print(f"      ✅ Successfully scraped {success_count}/{len(batch)} URLs")
            
        except Exception as e:
            print(f"      ❌ Error scraping batch: {e}")
    
    # Save scraped content
    scraped_file = CACHE_DIR / "gitbook_scraped.json"
    with open(scraped_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    successful = sum(1 for r in all_results.values() if r["success"])
    print(f"\n✅ Scraped {successful}/{len(BELLINGCAT_GITBOOK_URLS)} pages successfully")
    print(f"   Saved to: {scraped_file}")
    
    # Prepare for vector store
    print("\n📝 Preparing content for vector store...")
    
    documents = []
    for url, data in all_results.items():
        if not data["success"] or not data["content"]:
            continue
        
        title = data.get("metadata", {}).get("title", "")
        if not title:
            # Extract from URL
            title = url.split('/')[-1].replace('-', ' ').title()
            if title == "Toolkit":
                title = "Bellingcat Toolkit: " + url.split('/')[-2].replace('-', ' ').title()
        
        documents.append({
            "text": f"{title}\n\nURL: {url}\n\n{data['content'][:100000]}",
            "metadata": {
                "source": "bellingcat_gitbook",
                "url": url,
                "title": title,
                "type": "toolkit_resource"
            }
        })
    
    # Save as JSON for upload
    upload_file = CACHE_DIR / "gitbook_for_upload.json"
    with open(upload_file, 'w') as f:
        json.dump(documents, f, indent=2)
    
    print(f"   Prepared {len(documents)} documents")
    print(f"   Ready for upload: {upload_file}")
    
    # Upload to vector store
    print("\n📤 Uploading to OpenAI vector store...")
    
    try:
        # Upload the JSON file
        with open(upload_file, 'rb') as f:
            file_response = client.files.create(
                file=f,
                purpose="assistants"
            )
        
        print(f"   ✅ File uploaded: {file_response.id}")
        
        # Add to existing vector store (from previous uploads)
        VECTOR_STORE_ID = "vs_68a670d6a234819194fe0bebe3d9794d"
        
        # Try to add to vector store
        try:
            client.beta.vector_stores.files.create(
                vector_store_id=VECTOR_STORE_ID,
                file_id=file_response.id
            )
            print(f"   ✅ Added to vector store: {VECTOR_STORE_ID}")
        except:
            print(f"   ⚠️ Could not add to vector store directly")
            print(f"   File ID for manual addition: {file_response.id}")
        
        # Update WikiMan configuration
        wikiman_threads = Path("jurisdiction_threads.json")
        if wikiman_threads.exists():
            with open(wikiman_threads, 'r') as f:
                threads = json.load(f)
        else:
            threads = {}
        
        threads["BELLINGCAT-GITBOOK"] = {
            "type": "reference_material",
            "name": "Bellingcat GitBook Toolkit",
            "vector_store_id": VECTOR_STORE_ID,
            "file_id": file_response.id,
            "document_count": len(documents),
            "created_at": datetime.now().isoformat(),
            "note": "Latest Bellingcat toolkit from GitBook - comprehensive OSINT resources"
        }
        
        with open(wikiman_threads, 'w') as f:
            json.dump(threads, f, indent=2)
        
        print("\n" + "="*60)
        print("✅ BELLINGCAT GITBOOK TOOLKIT ADDED!")
        print("="*60)
        print(f"\n📚 Your OSINT vector store now contains:")
        print("   1. Bazzell's OSINT Techniques book (322 images)")
        print("   2. Original Bellingcat resources (34 documents)")
        print(f"   3. NEW: Bellingcat GitBook Toolkit ({len(documents)} pages)")
        print("\n🎯 All searchable together in WikiMan!")
        print("   Natural language OSINT queries will search ALL sources")
        print("   and synthesize overlapping information!")
        
    except Exception as e:
        print(f"\n❌ Upload error: {e}")
        print(f"   Content saved locally at: {upload_file}")

if __name__ == "__main__":
    main()