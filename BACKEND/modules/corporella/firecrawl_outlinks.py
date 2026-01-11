from firecrawl import FirecrawlApp
from urllib.parse import urlparse
from collections import defaultdict

def clean_url(url: str) -> str:
    """Remove http://, https://, and www. from URLs."""
    try:
        # Parse the URL
        parsed = urlparse(url)
        # Get domain and path
        domain = parsed.netloc.replace('www.', '')
        path = parsed.path
        # Combine them, removing trailing slashes
        cleaned = (domain + path).rstrip('/')
        return cleaned if cleaned else domain
    except Exception as e:
        return url

def get_external_links_by_page(domain: str, api_key: str) -> dict:
    """Get external links organized by source page using Firecrawl crawl."""
    app = FirecrawlApp(api_key=api_key)
    target_domain = urlparse(domain).netloc.lower().replace('www.', '')
    links_by_page = defaultdict(set)
    
    try:
        print("\nStarting crawl (this may take a few minutes)...")
        crawl_result = app.crawl_url(
            target_domain,
            params={
                'limit': 100,
                'maxDepth': 3,
                'scrapeOptions': {
                    'formats': ['links'],
                    'onlyMainContent': False
                }
            },
            poll_interval=5
        )
        
        if crawl_result and 'data' in crawl_result:
            total_pages = len(crawl_result['data'])
            print(f"\nCrawled {total_pages} pages. Analyzing results...")
            
            for page_data in crawl_result['data']:
                source_url = page_data.get('metadata', {}).get('sourceURL', 'Unknown Page')
                source_url_clean = clean_url(source_url)
                
                if 'links' in page_data:
                    for link in page_data['links']:
                        try:
                            link_domain = urlparse(link).netloc.lower().replace('www.', '')
                            # STRICT domain comparison
                            if link_domain and link_domain != target_domain:
                                links_by_page[source_url_clean].add(clean_url(link))
                        except Exception as e:
                            continue
                            
        return dict(links_by_page)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {}

def print_results(links_by_page: dict):
    """Print results in an organized format."""
    total_links = sum(len(links) for links in links_by_page.values())
    pages_with_links = sum(1 for links in links_by_page.values() if links)
    
    print(f"\nResults Summary:")
    print(f"Total external links found: {total_links}")
    print(f"Pages with external links: {pages_with_links}")
    print(f"Pages crawled: {len(links_by_page)}\n")
    
    print("Detailed Results:")
    print("-" * 80)
    
    for page_url, external_links in links_by_page.items():
        print(f"\nPage: {page_url}")
        if external_links:
            print(f"Found {len(external_links)} external links:")
            for link in sorted(external_links):
                print(f"  → {link}")
        else:
            print("No external links found on this page")
        print("-" * 80)

def main():
    api_key = "fc-64eb8af5ed3944d99bc1c0411ee12bc2"
    
    while True:
        domain = input("\nEnter domain (without http://, https://, or www) or 'quit' to exit: ").strip().lower()
        
        if domain == 'quit':
            break
            
        print(f"\nAnalyzing {domain}...")
        links_by_page = get_external_links_by_page(domain, api_key)
        
        if links_by_page:
            print_results(links_by_page)
        else:
            print("No results found or an error occurred.")

if __name__ == "__main__":
    main()