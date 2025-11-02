#!/usr/bin/env python3
"""
Scrape Intel Techniques podcast show notes (episodes 105-306)
Since audio was removed, we'll get the detailed show notes from each episode page
"""

import os
import json
import time
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

load_dotenv(override=True)

FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')
CACHE_DIR = Path("cache/inteltechniques_podcasts")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_episode_urls():
    """Get all episode URLs from the podcast page"""
    
    print("📡 Fetching episode list from podcast page...")
    
    response = requests.get("https://inteltechniques.com/podcast.html")
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find all episode links
    episode_links = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if 'episode-' in href and href.startswith('https://inteltechniques.com/blog/'):
            episode_links.append(href)
    
    # Remove duplicates and sort
    episode_links = sorted(list(set(episode_links)))
    
    print(f"   Found {len(episode_links)} episode pages")
    
    return episode_links

def scrape_episode(url):
    """Scrape a single episode page using Firecrawl"""
    
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": True
    }
    
    # Extract episode number from URL
    match = re.search(r'episode-(\d+)', url)
    episode_num = match.group(1) if match else "unknown"
    
    print(f"   Episode {episode_num}...", end="")
    
    try:
        response = requests.post(
            "https://api.firecrawl.dev/v2/scrape",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("data"):
                content = data["data"].get("markdown", "")
                title = data["data"].get("metadata", {}).get("title", f"Episode {episode_num}")
                
                # Extract date from URL
                date_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
                if date_match:
                    date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                else:
                    date = "unknown"
                
                print(f" ✓ {len(content)} chars")
                
                return {
                    "episode": episode_num,
                    "title": title,
                    "date": date,
                    "content": content,
                    "url": url
                }
            else:
                print(f" ✗ No content")
                return None
        else:
            print(f" ✗ HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f" ✗ Error: {e}")
        return None

def main():
    print("\n" + "="*60)
    print("INTEL TECHNIQUES PODCAST NOTES SCRAPER")
    print("="*60)
    
    # Get episode URLs
    episode_urls = get_episode_urls()
    
    if not episode_urls:
        print("❌ No episode URLs found")
        return
    
    # Limit to avoid overwhelming the API
    # Start with recent episodes
    episode_urls = episode_urls[:50]  # Get the 50 most recent episodes
    
    print(f"\n📚 Scraping {len(episode_urls)} episode show notes...")
    print("   (Most recent 50 episodes)")
    
    all_episodes = []
    
    for i, url in enumerate(episode_urls, 1):
        episode_data = scrape_episode(url)
        
        if episode_data:
            all_episodes.append(episode_data)
        
        # Small delay between requests
        if i < len(episode_urls):
            time.sleep(1)
    
    print(f"\n✅ Successfully scraped {len(all_episodes)}/{len(episode_urls)} episodes")
    
    if not all_episodes:
        print("❌ No episodes were scraped successfully")
        return
    
    # Sort by episode number
    all_episodes.sort(key=lambda x: int(x["episode"]) if x["episode"].isdigit() else 0, reverse=True)
    
    # Save raw data
    raw_file = CACHE_DIR / "podcast_episodes_raw.json"
    with open(raw_file, 'w') as f:
        json.dump(all_episodes, f, indent=2)
    print(f"   Saved raw content to: {raw_file}")
    
    # Show what we got
    print("\n📊 Episodes scraped:")
    print(f"   Latest: Episode {all_episodes[0]['episode']} ({all_episodes[0]['date']})")
    print(f"   Earliest: Episode {all_episodes[-1]['episode']} ({all_episodes[-1]['date']})")
    
    # Prepare for vector store
    print("\n📝 Preparing for vector store...")
    
    documents = []
    for episode in all_episodes:
        doc_title = f"Privacy, Security & OSINT Show - Episode {episode['episode']}"
        
        documents.append({
            "text": f"{doc_title}\n\nDate: {episode['date']}\nURL: {episode['url']}\n\n{episode['title']}\n\n{episode['content'][:100000]}",
            "metadata": {
                "source": "inteltechniques_podcast",
                "url": episode['url'],
                "title": doc_title,
                "episode": episode['episode'],
                "date": episode['date'],
                "type": "podcast_notes",
                "author": "Michael Bazzell"
            }
        })
    
    # Save for upload
    upload_file = CACHE_DIR / "podcast_for_upload.json"
    with open(upload_file, 'w') as f:
        json.dump(documents, f, indent=2)
    
    print(f"   Prepared {len(documents)} documents")
    print(f"   Ready for upload: {upload_file}")
    
    # Upload to OpenAI
    from openai import OpenAI
    client = OpenAI()
    
    print("\n📤 Uploading to OpenAI...")
    
    try:
        with open(upload_file, 'rb') as f:
            file_response = client.files.create(
                file=f,
                purpose="assistants"
            )
        
        print(f"   ✅ File uploaded: {file_response.id}")
        
        # Update WikiMan config
        wikiman_threads = Path("jurisdiction_threads.json")
        if wikiman_threads.exists():
            with open(wikiman_threads, 'r') as f:
                threads = json.load(f)
        else:
            threads = {}
        
        threads["INTELTECHNIQUES-PODCASTS"] = {
            "type": "reference_material",
            "name": "Privacy, Security & OSINT Show Notes",
            "vector_store_id": "vs_68a670d6a234819194fe0bebe3d9794d",
            "file_id": file_response.id,
            "document_count": len(documents),
            "episodes": f"{all_episodes[-1]['episode']}-{all_episodes[0]['episode']}",
            "date_range": f"{all_episodes[-1]['date']} to {all_episodes[0]['date']}",
            "created_at": datetime.now().isoformat(),
            "note": "Podcast show notes from The Privacy, Security & OSINT Show"
        }
        
        with open(wikiman_threads, 'w') as f:
            json.dump(threads, f, indent=2)
        
        print("\n" + "="*60)
        print("✅ SUCCESS!")
        print("="*60)
        print(f"   Added {len(documents)} podcast episode show notes")
        print(f"   Episodes: {all_episodes[-1]['episode']}-{all_episodes[0]['episode']}")
        print(f"   Date range: {all_episodes[-1]['date']} to {all_episodes[0]['date']}")
        print("   All in the same OSINT vector store!")
        
    except Exception as e:
        print(f"❌ Upload error: {e}")
        print(f"   Content saved at: {upload_file}")

if __name__ == "__main__":
    main()