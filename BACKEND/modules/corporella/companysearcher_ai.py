import json
import openai
import re
import subprocess
import sys
import os
from whoosh.index import create_in, open_dir
from whoosh.fields import Schema, TEXT, ID, STORED
from whoosh.analysis import StandardAnalyzer
import whoosh.index as index
from whoosh.qparser import MultifieldParser
from uuid import uuid4
from datetime import datetime
from multiprocessing import Process, Queue
from urllib.parse import urlparse
import scrapy
from scrapy.crawler import CrawlerProcess
import importlib.util

class ContentSpider(scrapy.Spider):
    name = 'content_spider'
    results_file = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/#R&D/Script_Library/Python Library/Woosh/latest_site_search.json"
    
    def __init__(self, urls_queue, specific_words, *args, **kwargs):
        super(ContentSpider, self).__init__(*args, **kwargs)
        self.urls_queue = urls_queue
        self.specific_words = [word.lower() for word in specific_words]
        self.start_urls = []
        self.results = []
        while not self.urls_queue.empty():
            self.start_urls.append(self.urls_queue.get())

    def parse(self, response):
        text_elements = response.css('p::text, span::text, a::text, li::text, td::text, th::text, h1::text, h2::text, h3::text, h4::text, h5::text, h6::text, strong::text, em::text, div::text, label::text, blockquote::text, footer::text, header::text, section::text, article::text, nav::text, aside::text').getall()
        main_content = "\n".join(text_elements).lower()

        # Search for specific words and get context
        found_words = {}
        for word in self.specific_words:
            if word in main_content:
                # Get surrounding context (100 characters before and after)
                instances = []
                start = 0
                while True:
                    pos = main_content.find(word, start)
                    if pos == -1:
                        break
                    context_start = max(0, pos - 100)
                    context_end = min(len(main_content), pos + len(word) + 100)
                    context = main_content[context_start:context_end].replace('\n', ' ').strip()
                    instances.append(context)
                    start = pos + 1
                
                found_words[word] = {
                    'count': main_content.count(word),
                    'contexts': instances[:5]  # Limit to 5 context examples
                }

        if found_words:
            self.results.append({
                'url': response.url,
                'findings': found_words,
                'timestamp': datetime.now().isoformat()
            })

    def closed(self, reason):
        # Save results to JSON
        with open(self.results_file, 'w') as f:
            json.dump({
                'search_terms': self.specific_words,
                'total_urls': len(self.start_urls),
                'results': self.results
            }, f, indent=2)

def setup_whoosh_index():
    """Setup or open the Whoosh index"""
    index_dir = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/#R&D/Script_Library/Python Library/Woosh/index"
    
    if not os.path.exists(index_dir):
        os.makedirs(index_dir)
    
    schema = Schema(
        entry_id=ID(stored=True, unique=True),
        company_name=TEXT(stored=True),
        registration_number=ID(stored=True),
        jurisdiction=TEXT(stored=True),
        address=TEXT(stored=True),
        incorporation_date=STORED,
        source=TEXT(stored=True),
        raw_data=STORED,
        last_modified=STORED
    )
    
    if not index.exists_in(index_dir):
        return create_in(index_dir, schema)
    return open_dir(index_dir)

def index_search_results(results_file: str):
    """Index the latest company search results"""
    print("\nIndexing search results...")
    
    try:
        # Load the results
        with open(results_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Results file '{results_file}' not found")
        return
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in results file '{results_file}'")
        return
    except Exception as e:
        print(f"Error loading results file: {str(e)}")
        return

    try:
        # Open the index
        ix = setup_whoosh_index()
        
        # Index the results
        writer = ix.writer()
        
        for group in data.get('results', []):
            primary = group.get('primary_match', {})
            
            # Add primary match
            writer.add_document(
                company_name=primary.get('name', ''),
                registration_number=primary.get('registration_number', ''),
                jurisdiction=primary.get('jurisdiction', ''),
                address=primary.get('address', ''),
                incorporation_date=primary.get('incorporation_date', ''),
                source=primary.get('source', ''),
                raw_data=json.dumps(primary.get('raw_data', {}))
            )
            
            # Add similar matches
            for similar in group.get('similar_matches', []):
                writer.add_document(
                    company_name=similar.get('name', ''),
                    registration_number=similar.get('registration_number', ''),
                    jurisdiction=similar.get('jurisdiction', ''),
                    address=similar.get('address', ''),
                    incorporation_date=similar.get('incorporation_date', ''),
                    source=similar.get('source', ''),
                    raw_data=json.dumps(similar.get('raw_data', {}))
                )
        
        writer.commit()
        print("✓ Search results indexed successfully")
        
    except Exception as e:
        print(f"Error indexing results: {str(e)}")

def trigger_company_search(company_name: str):
    """Trigger companyprofilesearch.py with the company name"""
    script_path = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/#R&D/Script_Library/Python Library/companyprofilesearch.py"
    results_file = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/#R&D/Script_Library/Python Library/Woosh/latest_company_search.json"
    
    print(f"\nExecuting: python3 {script_path} {company_name}")
    
    try:
        # Run the script with the company name as argument
        result = subprocess.run(
            [sys.executable, script_path, company_name],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)
        
        # Index the results if file exists
        if os.path.exists(results_file):
            index_search_results(results_file)
            
        return True
    except Exception as e:
        print(f"Error executing search: {str(e)}")
        return False
    finally:
        print("Search execution attempt completed.")

def trigger_site_search(url: str, keywords: list):
    """Search website content using Scrapy spider"""
    print(f"\nInitiating website search at {url} for keywords: {', '.join(keywords)}")
    
    try:
        # Create a queue to pass URLs to spider
        urls_queue = Queue()
        urls_queue.put(url)
        
        # Configure and run the crawler process
        process = CrawlerProcess({
            'USER_AGENT': 'Mozilla/5.0 (compatible; CompanySearchBot/1.0)',
            'LOG_LEVEL': 'ERROR'
        })
        
        process.crawl(ContentSpider, urls_queue=urls_queue, specific_words=keywords)
        process.start()
        
        # Analyze results
        results_file = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/#R&D/Script_Library/Python Library/Woosh/latest_site_search.json"
        
        with open(results_file, 'r') as f:
            data = json.load(f)
            
        total_mentions = 0
        locations = []
        contexts = []
        
        for result in data.get('results', []):
            for word, findings in result.get('findings', {}).items():
                total_mentions += findings.get('count', 0)
                for context in findings.get('contexts', []):
                    contexts.append(context)
                    locations.append(result['url'])
                    
        if total_mentions == 0:
            return "No mentions of the search terms were found on this website."
            
        summary = f"\nFound {total_mentions} mentions across {len(set(locations))} pages.\n"
        if contexts:
            summary += "\nSample contexts:\n"
            for i, ctx in enumerate(contexts[:3], 1):
                summary += f"\n{i}. ...{ctx}...\n"
                
        return summary
        
    except Exception as e:
        return f"Error executing website search: {str(e)}"

def ask_gpt(client, conversation_history, user_input):
    """Chat with GPT and handle company search requests"""
    try:
        # Check for memory/remember patterns
        memory_patterns = [
            r"(?:do you |)remember (?:anything about |about |)([^?\.]+)",
            r"what do you remember about ([^?\.]+)",
            r"have you heard of ([^?\.]+)",
            r"do you know anything about ([^?\.]+)",
            r"what do you know about ([^?\.]+)"
        ]
        
        for pattern in memory_patterns:
            match = re.search(pattern, user_input.lower())
            if match:
                query = match.group(1).strip()
                print(f"\nSearching index for: {query}")
                return search_companies(query)
        
        # Check for update command
        if "update" in user_input.lower() and "with" in user_input.lower():
            parts = user_input.lower().split("with")
            if len(parts) == 2:
                old_name = parts[0].replace("update", "").strip()
                new_name = parts[1].strip().strip('"').strip("'")
                return modify_index_entry("update", {"name": new_name}, old_name)
        
        # Check for explicit index search
        if user_input.lower().startswith(('search index', 'query index', 'look up index')):
            query = user_input.split(' ', 2)[2]
            return search_companies(query)
        
        # Check for new company search
        search_patterns = [
            r"search (?:for |)(?:company |)(?:called |named |)?([^\.]+)",
            r"find (?:company |)(?:called |named |)([^\.]+)",
            r"look up (?:company |)(?:called |named |)([^\.]+)"
        ]
        
        for pattern in search_patterns:
            match = re.search(pattern, user_input.lower())
            if match:
                company_name = match.group(1).strip()
                print(f"\nrun companyprofilesearch.py {company_name}")
                trigger_company_search(company_name)
                
                results_file = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/#R&D/Script_Library/Python Library/Woosh/latest_company_search.json"
                try:
                    with open(results_file, 'r') as f:
                        results = json.load(f)
                    return f"I've completed the search for {company_name}. What would you like to know about the results?"
                except Exception as e:
                    return f"The search was triggered but I couldn't read the results: {str(e)}"
        
        # Check for website search patterns
        site_search_patterns = [
            r"search (?:the |)(?:website|site|url) ([^\s]+) for (?:the |)(?:word|words|keywords?|terms?) ([^\.]+)",
            r"look (?:up|for) ([^\.]+) (?:on|at|in) (?:the |)(?:website|site|url) ([^\s]+)",
            r"find ([^\.]+) (?:on|at|in) (?:the |)(?:website|site|url) ([^\s]+)"
        ]
        
        # Check for website search requests
        for pattern in site_search_patterns:
            match = re.search(pattern, user_input.lower())
            if match:
                if "search the website" in pattern:
                    url = match.group(1)
                    keywords = [k.strip() for k in match.group(2).split(',')]
                else:
                    keywords = [k.strip() for k in match.group(1).split(',')]
                    url = match.group(2)
                
                return trigger_site_search(url, keywords)
        
        # Add enhanced website analysis patterns
        website_analysis_patterns = [
            r"analyze (?:the |)(?:website|site|url) ([^\s]+)(?: about |: |for |)([^\.]+)?",
            r"tell me about (?:the |)(?:website|site|url) ([^\s]+)",
            r"what (?:does|is on) (?:the |)(?:website|site|url) ([^\s]+)(?: about|show|contain|say)?",
        ]
        
        for pattern in website_analysis_patterns:
            match = re.search(pattern, user_input.lower())
            if match:
                url = match.group(1)
                question = match.group(2) if len(match.groups()) > 1 else None
                return analyze_website_content(client, url, question)
        
        # If no special commands, continue with normal conversation
        conversation_history.append({"role": "user", "content": user_input})
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant specializing in company research. You can analyze company data and trigger new searches when asked. Be concise but informative."},
                *conversation_history
            ]
        )
        
        reply = response.choices[0].message.content.strip()
        conversation_history.append({"role": "assistant", "content": reply})
        return reply
        
    except Exception as e:
        return f"Error: {str(e)}"

def search_companies(query: str):
    """Search the indexed company data"""
    ix = setup_whoosh_index()
    
    try:
        with ix.searcher() as searcher:
            parser = MultifieldParser(["company_name", "jurisdiction"], ix.schema)
            q = parser.parse(query)
            results = searcher.search(q, limit=10)
            
            if not results:
                return "No matching companies found in the index."
            
            output = "\nSearch Results:\n"
            for i, hit in enumerate(results, 1):
                output += f"\n{i}. Entry ID: {hit.get('entry_id', 'N/A')}"
                output += f"\n   Company: {hit.get('company_name', 'N/A')}"
                output += f"\n   Registration: {hit.get('registration_number', 'N/A')}"
                output += f"\n   Jurisdiction: {hit.get('jurisdiction', 'N/A')}"
                output += f"\n   Source: {hit.get('source', 'N/A')}"
                output += f"\n   Last Modified: {hit.get('last_modified', 'N/A')}"
                
                if hit.get('address'):
                    output += f"\n   Address: {hit['address']}"
                if hit.get('incorporation_date'):
                    output += f"\n   Incorporated: {hit['incorporation_date']}"
                output += "\n"
            
            return output
    except Exception as e:
        return f"Error searching index: {str(e)}"

def modify_index_entry(command: str, entry_data: dict = None, entry_id: str = None):
    """Add, update, or delete entries in the Whoosh index"""
    try:
        ix = setup_whoosh_index()
        writer = ix.writer()
        
        if command == "add":
            if not entry_data:
                return "Error: No entry data provided"
                
            new_id = str(uuid4())
            writer.add_document(
                entry_id=new_id,
                company_name=entry_data.get("name", ""),
                registration_number=entry_data.get("registration_number", ""),
                jurisdiction=entry_data.get("jurisdiction", ""),
                address=entry_data.get("address", ""),
                incorporation_date=entry_data.get("incorporation_date", ""),
                source=entry_data.get("source", "Manual Entry"),
                raw_data=json.dumps(entry_data.get("raw_data", {})),
                last_modified=datetime.now().isoformat()
            )
            writer.commit()
            return f"✓ Added new entry with ID: {new_id}"
            
        elif command == "update":
            if not entry_id or not entry_data:
                return "Error: Need both entry_id and update data"
                
            writer.delete_by_term('entry_id', entry_id)
            writer.add_document(
                entry_id=entry_id,
                company_name=entry_data.get("name", ""),
                registration_number=entry_data.get("registration_number", ""),
                jurisdiction=entry_data.get("jurisdiction", ""),
                address=entry_data.get("address", ""),
                incorporation_date=entry_data.get("incorporation_date", ""),
                source=entry_data.get("source", "Manual Entry"),
                raw_data=json.dumps(entry_data.get("raw_data", {})),
                last_modified=datetime.now().isoformat()
            )
            writer.commit()
            return f"✓ Updated entry {entry_id}"
            
        elif command == "delete":
            if not entry_id:
                return "Error: Need entry_id to delete"
                
            writer.delete_by_term('entry_id', entry_id)
            writer.commit()
            return f"✓ Deleted entry {entry_id}"
            
    except Exception as e:
        return f"Error modifying index: {str(e)}"

def analyze_website_content(client, url: str, specific_question: str = None):
    """Analyze website content with enhanced temporal and factual tracking"""
    script_path = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/#R&D/Script_Library/Python Library/#Site_search/scrapy_sitesearch.py"
    try:
        # Import the script as a module
        import importlib.util
        spec = importlib.util.spec_from_file_location("scrapy_sitesearch", script_path)
        scraper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scraper)
        
        # Use the scraper to get website content
        content = scraper.scrape_website(url)
        
        if not content:
            return "Unable to retrieve website content"
            
        # Analyze the content based on specific question or general analysis
        if specific_question:
            analysis = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant specializing in company research. Analyze the following content."},
                    {"role": "user", "content": content},
                    {"role": "user", "content": specific_question}
                ]
            ).choices[0].message.content.strip()
        else:
            analysis = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant specializing in company research. Analyze the following content."},
                    {"role": "user", "content": content},
                    {"role": "user", "content": "What are the key business activities and notable information about this company?"}
                ]
            ).choices[0].message.content.strip()
            
        return analysis
        
    except Exception as e:
        print(f"Error analyzing website content: {str(e)}")
        return str(e)

def analyze_site_search_results():
    """Analyze the latest website search results"""
    results_file = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/#R&D/Script_Library/Python Library/Woosh/latest_site_search.json"
    
    try:
        with open(results_file, 'r') as f:
            data = json.load(f)
        
        total_mentions = 0
        locations = []
        contexts = []
        
        for result in data.get('results', []):
            for word, findings in result.get('findings', {}).items():
                total_mentions += findings['count']
                for instance in findings.get('instances', []):
                    contexts.append({
                        'section': instance.get('section_title', 'Unknown section'),
                        'context': f"{instance['before']} {instance['word']} {instance['after']}"
                    })
                    locations.append(result['url'])
        
        if total_mentions == 0:
            return "No mentions of the search term on this website."
        
        # Create a concise summary
        summary = f"\nFound {total_mentions} mentions across {len(set(locations))} pages. "
        
        if contexts:
            summary += "Here are the most relevant mentions:\n"
            for i, ctx in enumerate(contexts[:3], 1):  # Show top 3 most relevant
                summary += f"\n{i}. In {ctx['section']}:\n   ...{ctx['context']}...\n"
        
        return summary
        
    except Exception as e:
        return f"Error analyzing results: {str(e)}"

def main():
    print("\n=== C0GN1T0: Corporate Intelligence System ===")
    print("\nI can help you investigate companies and analyze websites.")
    print("Try asking things like:")
    print("- 'Search for company called Apple Inc'")
    print("- 'What do you remember about Microsoft?'")
    print("- 'Search index Apple'")
    print("\nWebsite Investigation:")
    print("- 'Search website example.com for keywords data, privacy'")
    print("- 'Look for acquisition, merger on website company.com'")
    print("- 'Find specific terms on website target.com'")
    print("\nIndex Management:")
    print("- 'Add entry name: New Corp, jurisdiction: us_de, registration: NC123'")
    print("- 'Update entry [ID] name: Updated Name, address: New Address'")
    print("- 'Delete entry [ID]'")
    print("\nType 'exit' to quit.")
    
    client = openai.OpenAI(api_key="sk-proj-RMoKUzCBj7LrVacv9Sj2T3BlbkFJ87eZRGhTgH21CwIEwvWo")
    conversation_history = []
    
    while True:
        user_input = input("\nYou: ").strip()
        
        if user_input.lower() in ['exit', 'quit']:
            print("\nGoodbye!")
            break
        
        print("\nAssistant: ", end="")
        response = ask_gpt(client, conversation_history, user_input)
        print(response)

if __name__ == "__main__":
    main()
