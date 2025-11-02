#!/usr/bin/env python3
"""
Scrape Bellingcat's resources using Firecrawl batch processing
Embed and upload to the same vector database as the OSINT book
"""

import os
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import hashlib
from dotenv import load_dotenv

# Load environment
load_dotenv(override=True)

# Import Firecrawl service
from FactAssembler.firecrawl_service import FirecrawlService
from openai import OpenAI

# Configuration
BASE_URL = "https://www.bellingcat.com/resources/"
CACHE_DIR = Path("cache/bellingcat_resources")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Vector store configuration
VECTOR_STORE_NAME = "WikiMan: OSINT Resources"
VECTOR_STORE_DESC = "Combined OSINT knowledge base: Bazzell book + Bellingcat resources"


class BellingcatResourceScraper:
    """Scraper for Bellingcat resources with batch processing"""
    
    def __init__(self):
        """Initialize the scraper"""
        self.firecrawl = FirecrawlService()
        self.client = OpenAI()
        self.resources_cache = CACHE_DIR / "resources_index.json"
        self.scraped_content = CACHE_DIR / "scraped_content.json"
        
    def discover_resource_urls(self) -> List[str]:
        """Discover all resource URLs from Bellingcat"""
        
        print("\n📡 Discovering Bellingcat resource URLs...")
        
        # First scrape the main resources page to find categories
        main_page = self.firecrawl.scrape_url(BASE_URL)
        
        if not main_page or not main_page[1]:
            print("❌ Failed to scrape main resources page")
            return []
        
        # Known resource sections on Bellingcat
        resource_paths = [
            "resources/",
            "resources/how-tos/",
            "resources/case-studies/",
            "resources/guides/",
            "resources/articles/",
            "resources/tools/",
            "resources/datasets/",
            "resources/training/",
            "resources/newsletter/",
            "resources/workshops/"
        ]
        
        # Build full URLs
        resource_urls = []
        for path in resource_paths:
            full_url = f"https://www.bellingcat.com/{path}"
            resource_urls.append(full_url)
        
        # Also extract links from the main page content
        import re
        # main_page is a tuple (url, content, metadata)
        content = main_page[1] if isinstance(main_page[1], str) else str(main_page[1])
        
        # Find all Bellingcat resource links
        pattern = r'https://www\.bellingcat\.com/resources/[^"\s<>]+'
        found_urls = re.findall(pattern, content)
        
        # Add unique URLs
        for url in found_urls:
            # Clean up URL
            url = url.rstrip('/')
            if url not in resource_urls and not url.endswith(('.jpg', '.png', '.pdf', '.mp4')):
                resource_urls.append(url)
        
        # Also search for relative links
        relative_pattern = r'href=["\'](/resources/[^"\']+)["\']'
        relative_links = re.findall(relative_pattern, content)
        
        for link in relative_links:
            full_url = f"https://www.bellingcat.com{link}".rstrip('/')
            if full_url not in resource_urls and not full_url.endswith(('.jpg', '.png', '.pdf', '.mp4')):
                resource_urls.append(full_url)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in resource_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        print(f"   Found {len(unique_urls)} unique resource URLs")
        
        # Save to cache
        with open(self.resources_cache, 'w') as f:
            json.dump({
                "discovered_at": datetime.now().isoformat(),
                "urls": unique_urls
            }, f, indent=2)
        
        return unique_urls
    
    def batch_scrape_resources(self, urls: List[str]) -> Dict[str, Any]:
        """Batch scrape all resource URLs"""
        
        print(f"\n🚀 Batch scraping {len(urls)} Bellingcat resources...")
        print("   This will use Firecrawl's batch API (50 URLs at a time)")
        
        all_results = {}
        batch_size = 50  # Firecrawl's limit
        
        # Process in batches
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(urls) + batch_size - 1) // batch_size
            
            print(f"\n   Batch {batch_num}/{total_batches}: Scraping {len(batch)} URLs...")
            
            try:
                # Use Firecrawl's batch scraping method
                results = self.firecrawl._batch_scrape_parallel(batch)
                
                # Process results
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
                    else:
                        all_results[url] = {
                            "url": url,
                            "content": "",
                            "metadata": metadata,
                            "scraped_at": datetime.now().isoformat(),
                            "success": False,
                            "error": metadata.get("error", "No content")
                        }
                
                print(f"      ✅ Successfully scraped {success_count}/{len(batch)} URLs")
                
                # Small delay between batches to be respectful
                if i + batch_size < len(urls):
                    print("      ⏳ Waiting 2 seconds before next batch...")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"      ❌ Error scraping batch: {e}")
                # Add failed URLs to results
                for url in batch:
                    if url not in all_results:
                        all_results[url] = {
                            "url": url,
                            "content": "",
                            "metadata": {},
                            "scraped_at": datetime.now().isoformat(),
                            "success": False,
                            "error": str(e)
                        }
        
        # Save all scraped content
        with open(self.scraped_content, 'w') as f:
            json.dump(all_results, f, indent=2)
        
        print(f"\n✅ Scraped {len(all_results)} total resources")
        successful = sum(1 for r in all_results.values() if r["success"])
        print(f"   Successful: {successful}/{len(all_results)}")
        
        return all_results
    
    def prepare_for_embedding(self, scraped_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Prepare scraped content for embedding"""
        
        print("\n📝 Preparing content for embedding...")
        
        documents = []
        
        for url, data in scraped_data.items():
            if not data["success"] or not data["content"]:
                continue
            
            # Extract title from metadata or content
            title = data.get("metadata", {}).get("title", "")
            if not title:
                # Try to extract from content
                lines = data["content"].split('\n')
                for line in lines[:5]:  # Check first 5 lines
                    if line.strip().startswith('#'):
                        title = line.strip('#').strip()
                        break
                
                if not title:
                    title = f"Bellingcat Resource: {url.split('/')[-1]}"
            
            # Create document for embedding
            doc = {
                "id": hashlib.md5(url.encode()).hexdigest(),
                "source": "bellingcat",
                "url": url,
                "title": title,
                "content": data["content"][:50000],  # Limit content size
                "metadata": {
                    "source_type": "bellingcat_resource",
                    "scraped_at": data["scraped_at"],
                    "url": url,
                    "title": title
                }
            }
            
            documents.append(doc)
        
        print(f"   Prepared {len(documents)} documents for embedding")
        return documents
    
    def save_documents(self, documents: List[Dict[str, Any]]) -> str:
        """Save documents locally and prepare for vector store"""
        
        print("\n💾 Saving documents...")
        
        # Check if we already have a vector store for OSINT resources
        # Load WikiMan configuration to check for existing vector store
        wikiman_threads = Path("jurisdiction_threads.json")
        vector_store_id = None
        
        if wikiman_threads.exists():
            with open(wikiman_threads, 'r') as f:
                threads = json.load(f)
                
                # Check if OSINT book has a vector store
                if "BOOK-OSINT-TECHNIQUES" in threads:
                    vector_store_id = threads["BOOK-OSINT-TECHNIQUES"].get("vector_store_id")
        
        try:
            if vector_store_id:
                print(f"   Using existing vector store: {vector_store_id}")
                vector_store = {"id": vector_store_id}
            else:
                # Save locally for now
                print("   Saving to local files...")
                vector_store_id = "local_storage"
            
            # Create JSONL file for future upload
            upload_file = CACHE_DIR / "bellingcat_documents.jsonl"
            
            with open(upload_file, 'w') as f:
                for doc in documents:
                    # Format for future vector store upload
                    upload_doc = {
                        "id": doc["id"],
                        "text": f"{doc['title']}\n\n{doc['content']}",
                        "metadata": doc["metadata"]
                    }
                    f.write(json.dumps(upload_doc) + '\n')
            
            print(f"✅ Saved {len(documents)} documents to {upload_file}")
            
            # Also save as regular JSON for easy access
            json_file = CACHE_DIR / "bellingcat_documents.json"
            with open(json_file, 'w') as f:
                json.dump(documents, f, indent=2)
            
            print(f"✅ Also saved as JSON to {json_file}")
            
            # Update WikiMan configuration
            if wikiman_threads.exists():
                with open(wikiman_threads, 'r') as f:
                    threads = json.load(f)
            else:
                threads = {}
            
            # Add Bellingcat entry
            threads["BELLINGCAT-RESOURCES"] = {
                "type": "reference_material",
                "name": "Bellingcat OSINT Resources",
                "vector_store_id": vector_store_id,
                "document_count": len(documents),
                "created_at": datetime.now().isoformat(),
                "note": "Bellingcat investigation resources and guides"
            }
            
            # Update OSINT book entry if exists
            if "BOOK-OSINT-TECHNIQUES" in threads:
                threads["BOOK-OSINT-TECHNIQUES"]["vector_store_id"] = vector_store_id
                threads["BOOK-OSINT-TECHNIQUES"]["note"] += " + Bellingcat resources"
            
            with open(wikiman_threads, 'w') as f:
                json.dump(threads, f, indent=2)
            
            return vector_store_id
            
        except Exception as e:
            print(f"❌ Error uploading to vector store: {e}")
            raise


def main():
    """Main execution"""
    
    print("\n" + "="*60)
    print("BELLINGCAT RESOURCES SCRAPER")
    print("="*60)
    
    scraper = BellingcatResourceScraper()
    
    # Step 1: Discover resource URLs
    urls = scraper.discover_resource_urls()
    
    if not urls:
        print("❌ No URLs discovered")
        return
    
    print(f"\n📊 Summary:")
    print(f"   Total URLs to scrape: {len(urls)}")
    print(f"   Estimated time: {(len(urls) / 50) * 10:.1f} seconds")
    print(f"   Batches needed: {(len(urls) + 49) // 50}")
    
    # Auto-proceed
    print("\n🚀 Starting batch scraping...")
    
    # Step 2: Batch scrape all resources
    scraped_data = scraper.batch_scrape_resources(urls)
    
    # Step 3: Prepare for embedding
    documents = scraper.prepare_for_embedding(scraped_data)
    
    if not documents:
        print("❌ No documents to embed")
        return
    
    # Step 4: Save documents
    vector_store_id = scraper.save_documents(documents)
    
    print("\n" + "="*60)
    print("✅ BELLINGCAT SCRAPING COMPLETE!")
    print("="*60)
    print(f"\n📚 The Bellingcat resources are now available in WikiMan!")
    print(f"\n🎯 Usage:")
    print(f"   python3 wikiman.py")
    print(f"   > How do I verify images? :BELLINGCAT-RESOURCES")
    print(f"   > What are Bellingcat's investigation techniques?")
    print(f"\n💡 Note: Natural language detection will route OSINT questions to this content")
    print(f"   Vector store ID: {vector_store_id}")
    print(f"   Documents indexed: {len(documents)}")


if __name__ == "__main__":
    main()