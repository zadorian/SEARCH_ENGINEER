import json
import argparse
import asyncio
import os
import sys
import re # For operator parsing and placeholder replacement
import requests # Add explicit import for direct HTTP requests
from bs4 import BeautifulSoup # Add BeautifulSoup for more reliable HTML parsing
from typing import Optional, List, Dict
from urllib.parse import urlparse # For domain extraction if needed for logging/debugging
import aiohttp
from datetime import datetime
import traceback

# Adjust path to import from parent directory and then specific modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from SEARCH_ENGINES.variators.firecrawl import FirecrawlScraper, FIRECRAWL_API_KEY
from ai.chatgpt import ChatManager, MODEL_NAME
from SEARCH_ENGINES.whoosh_indexer import WhooshIndexer

# Ensure OpenAI API key is available for ChatManager
if not os.getenv('OPENAI_API_KEY'):
    print("Error: OPENAI_API_KEY environment variable is not set. Please set it before running.")
    # ChatManager will raise an error, so we can let it handle it or exit here.

# --- Site-Specific and Default Prompts for Structured Data Extraction ---
DEFAULT_COMPANY_EXTRACTION_PROMPT = """Extract detailed company information from the provided content. Focus on the primary company discussed in the text.
Present the information in a structured JSON format. If a field is not found or not applicable, use null.
Provide extracted text values in English where possible (e.g., if source is in another language, translate terms like legal forms, roles, or status).

Fields to extract:
- company_name: Full official name of the company.
- name_history: List of previous official names of the company, if available.
- registration_number: Any business registration numbers found (e.g., ICO, VAT ID, Handelsregisternummer, etc.).
- address: Complete registered or primary operational address (street, city, postal code, country).
- incorporation_date: Date of incorporation, registration, or establishment (e.g., DD.MM.YYYY or YYYY-MM-DD).
- legal_form: The legal form of the company (e.g., Ltd., GmbH, s.r.o., Inc.). Translate to common English terms if applicable.
- status: Current operational status if mentioned (e.g., active, dissolved, in liquidation). Translate to English.
- key_people: A list of current key executives, directors, or board members and their roles. Each item should be an object with "name" and "role". Translate roles to English.
- directorship_history: A list of past key executives, directors, or board members, their roles, and tenure if available. Each item should be an object with "name", "role", and "period" (e.g., "2010-2015").
- business_activities: A description of the main business activities or scope of operations. If very long, provide a concise English summary or list the main categories.
- shareholders: Current notable shareholders or parent companies, if mentioned (name, stake if available).
- ownership_history: A list of significant past shareholders or parent companies and their stake/role, including period if available. Each item should be an object with "name", "stake_or_role", and "period".
- capital: Information about registered or share capital, if available (amount and currency).
- financial_info: Any key current financial figures mentioned (e.g., revenue, profit/loss, assets for a recent year). Specify the currency and year if available.
- financial_history: Key financial figures from previous years, if available (e.g., a list of objects with "year", "revenue", "profit", "assets", "currency").
- subsidiaries: List of subsidiary companies, if mentioned (name, registration_number if available).
- contact_details: Publicly listed phone numbers, email addresses, or official website URLs if found in the content.
- additional_info: Any other relevant company details, such as number of employees, significant events, or certifications mentioned.

Content to analyze is provided below.
---
{content}
---
"""

LITIGATION_EXTRACTION_PROMPT = """Extract detailed information about the legal case from the provided content.
Present the information in a structured JSON format. If a field is not found or not applicable, use null.

Fields to extract:
- case_summary: A concise summary of the legal case, its nature, and main allegations/disputes.
- case_id: Any official identifier for the case (e.g., case number, file number).
- court_and_location: The name of the court, tribunal, or body hearing the case, and its geographical location (city, country).
- key_dates: A list of important dates related to the case. Each item should be an object with "event" (e.g., "Filing Date", "Hearing Date", "Judgment Date") and "date" (e.g., DD.MM.YYYY).
- parties_involved: A list of key parties. Each item should be an object with "name" and "role" (e.g., "Plaintiff", "Defendant", "Appellant", "Respondent", "Lawyer for Plaintiff", "Judge").
- case_status: The current status of the case (e.g., "Ongoing", "Decided", "Appealed", "Settled", "Dismissed").
- outcome_or_judgment_summary: If the case is decided or settled, a summary of the outcome, judgment, or settlement terms.
- financial_implications: Any mentioned monetary amounts, fines, damages awarded, or legal costs.
- further_details_availability: A note on whether more detailed information or documents (e.g., full judgments, filings, evidence) are available on the site, and if so, how to access them (e.g., "Full judgment PDF linked", "Requires clicking case ID for details", "No further documents directly available").

Content to analyze is provided below.
---
{content}
---
"""

SITE_SPECIFIC_PROMPTS = {
    "www.orsr.sk": """From the following Slovak Business Register (ORSR) page content, extract the following information into a JSON object.
If a detail is not found, use null for its value. Provide extracted text in English where possible. Pay attention to sections detailing historical changes.

- company_name: (Look for 'Obchodné meno')
- name_history: (Look for 'Staršie názvy' or historical entries under 'Obchodné meno'. List any previous names.)
- registration_number: (Look for 'IČO')
- address: (Look for 'Sídlo' - provide as a structured object with 'street', 'city', 'postal_code', and 'country' which will be 'Slovakia')
- incorporation_date: (Look for 'Deň zápisu' - format DD.MM.YYYY)
- legal_form: (Look for 'Právna forma')
- status: (Look for current status, e.g., 'Aktívny', 'Existujúci', 'Zaniknutý', and translate to English like 'Active', 'Existing', 'Ceased to exist')
- capital: (Look for 'Základné imanie' - include currency and amount, e.g., 'EUR 5000'. Note any changes if detailed.)
- key_people: (Look for current 'Štatutárny orgán' or 'Konatelia'. List each person as an object with 'name', 'role' (e.g., 'Executive Director', 'Konateľ'), and 'address' if available. Translate roles to English.)
- directorship_history: (Look for historical entries for 'Štatutárny orgán', 'Konatelia', or similar sections indicating past directors/officers. List each as an object with 'name', 'role', 'start_date', 'end_date' if available.)
- shareholders: (Look for current 'Spoločníci'. List each shareholder as an object with 'name', 'address', and 'stake' (e.g., 'EUR 5000' or percentage) if available.)
- ownership_history: (Look for historical entries for 'Spoločníci' or changes in stakes. List each past significant shareholder as an object with 'name', 'address', 'stake', 'start_date', 'end_date' if available.)
- business_activities: (Look for 'Predmet činnosti'. Provide a concise English summary or a list of the main categories of activities. Avoid direct long transcription of all items if extensive.)
- financial_information: (Check for any sections like 'Finančné údaje', 'Účtovná závierka', or 'Zbierka listín' that might contain links or summaries of financial statements. Extract key figures like revenue, profit, assets, liabilities for any years available. Specify year and currency.)
- subsidiaries: (Look for any mention of 'dcérske spoločnosti' or investments that imply control over other entities.)
- additional_info: (Note any other significant legal events or information found, e.g., 'Ďalšie právne skutočnosti', 'Likvidácia', 'Konkurz').

Output as JSON with keys: 'company_name', 'name_history', 'registration_number', 'address', 'incorporation_date', 'legal_form', 'status', 'capital', 'key_people', 'directorship_history', 'shareholders', 'ownership_history', 'business_activities', 'financial_information', 'subsidiaries', 'additional_info'.

Page Content:
---
{content}
---
""",
    # Example for another site - can be expanded
    # "www.finstat.sk": """From this FinStat page content, extract: Company Name, ICO, latest available Revenue (Tržby), latest available Profit (Zisk po zdanení), and Sector. If not found, use 'Not found'. Output as JSON.

# Page Content:
# ---
# {content}
# ---
# """
}

# --- Operator Parsing Logic ---
def parse_operation_string(op_string: str, default_country_suffix: str = "") -> dict:
    """
    Parses the operation string (e.g., "p!John Doe", "crro!!Acme Corp")
    Uses default_country_suffix (from loaded JSON, e.g., _sk) but prioritizes country code in operator (e.g., ro in crro).
    Returns a dictionary with: 
        'search_intent': 'person', 'company', or 'general'
        'target_categories': list of category keys from slovakia.json
        'primary_search_term': the term part of the string
        'errors': list of parsing errors, if any
        'mode': 'list_only' for single ! or 'full_scrape' for double !!
        'effective_country_code': the effective country code derived from the operator
    """
    config = {
        'search_intent': 'general',
        'target_categories': [],
        'primary_search_term': '',
        'errors': [],
        'mode': 'list_only',  # Default mode is just listing URLs
        'effective_country_code': default_country_suffix.replace('_','') # Default effective country
    }

    # Check for double !! - full scrape mode
    if '!!' in op_string:
        config['mode'] = 'full_scrape'
        parts = op_string.split('!!', 1)
        operator_part = parts[0]
        if len(parts) > 1:
            term_part_raw = parts[1]
            if not term_part_raw.startswith(' '):
                config['errors'].append("Error: Operator (ending in '!!') and keyword MUST be separated by a space (e.g., 'cr!! term').")
                config['primary_search_term'] = "" # Invalidate search term
            else:
                config['primary_search_term'] = term_part_raw.strip()
        else:
            config['errors'].append("Error: Malformed operator string. Missing keyword after '!!'.")
            config['primary_search_term'] = ""
        operator_code = operator_part.lower()
    # Check for single ! - list only mode
    elif '!' in op_string:
        config['mode'] = 'list_only' # Default mode is just listing URLs
        operator_part, term_part = op_string.split('!', 1)
        # Check if there was no space after the operator
        if op_string.startswith(operator_part + term_part) and term_part and not term_part.startswith(' '):
            config['errors'].append("Warning: Operator and keyword should ideally be separated by a space for clarity (e.g., 'cr! term').")
        config['primary_search_term'] = term_part.strip()
        operator_code = operator_part.lower()
    else:
        config['errors'].append("Operator string must contain '!' or '!!' to separate operator from search term.")
        config['primary_search_term'] = op_string # Assume the whole string is a general term if no '!'
        # Construct default categories using the default_country_suffix if operator is totally malformed
        default_base_keys = ['person', 'cr', 'lit', 'reg', 'ass'] # Temporary list for this fallback
        config['target_categories'] = [f"{key}{default_country_suffix}" for key in default_base_keys]
        config['effective_country_suffix'] = default_country_suffix # For reporting
        return config

    # Determine initial operator-specific suffix and the base code for category matching
    final_op_suffix_to_use = default_country_suffix
    base_op_code_for_cat_match = operator_code.lower() # Work with lowercase
    config['effective_country_code'] = default_country_suffix.replace('_','') # Default effective country

    # Define base operator keys (used for stripping country codes and for mapping)
    # Ensure these are the parts *before* any country code, e.g., 'cr', 'lit'
    known_base_operator_keys = ['person', 'p', 'cr', 'lit', 'reg', 'ass'] 

    if len(base_op_code_for_cat_match) > 2:
        potential_cc = base_op_code_for_cat_match[-2:] # e.g., "ro"
        potential_base = base_op_code_for_cat_match[:-2]   # e.g., "cr"
        # Check if potential_cc is all letters and potential_base is a known operator key
        if potential_cc.isalpha() and potential_base in known_base_operator_keys:
            final_op_suffix_to_use = f"_{potential_cc}"
            base_op_code_for_cat_match = potential_base # Now use "cr" for category matching
            config['effective_country_code'] = potential_cc
            print(f"DEBUG: Operator '{operator_code}' interpreted as base '{base_op_code_for_cat_match}' for country '{potential_cc}'. Using suffix '{final_op_suffix_to_use}'.")
        else:
            print(f"DEBUG: No valid country override in operator '{operator_code}'. Using default suffix '{default_country_suffix}'.")
    else:
        print(f"DEBUG: Operator '{operator_code}' too short for country override. Using default suffix '{default_country_suffix}'.")

    config['effective_country_suffix'] = final_op_suffix_to_use # Store for reporting

    # Determine search intent (p or c) based on the (potentially stripped) base_op_code_for_cat_match
    # More specific check: if the base operator *is* 'p' or starts with 'p' (like 'person')
    if base_op_code_for_cat_match == 'p' or base_op_code_for_cat_match.startswith('person'):
        config['search_intent'] = 'person'
    # If base is 'c' (and not part of 'cr', 'cnsc' etc. - though stripping should handle this)
    # or if it starts with 'c' and is a known company-related base like 'cr'
    elif base_op_code_for_cat_match == 'c' or base_op_code_for_cat_match.startswith('cr'): 
        config['search_intent'] = 'company'
    # Allow combined operators like 'pcr' to also set intent if not already person/company
    elif 'p' in base_op_code_for_cat_match and config['search_intent'] == 'general':
        config['search_intent'] = 'person'
    elif 'c' in base_op_code_for_cat_match and config['search_intent'] == 'general' and not any(op in base_op_code_for_cat_match for op in ['cr','ccr','cnsc']):
        config['search_intent'] = 'company'
    
    # Category mapping: keys are base operator parts (e.g., 'cr'), values are base JSON keys (e.g., 'cr')
    base_category_json_map = {
        'person': 'person', 'p': 'person', # 'p' maps to 'person' json key base
        'cr': 'cr',      
        'lit': 'lit',     
        'reg': 'reg',     
        'ass': 'ass',     
    }

    config['target_categories'] = [] # Reset before populating
    found_category_op_match = False

    # Iterate through the operator string (base_op_code_for_cat_match) to find all category parts
    # E.g., if base_op_code_for_cat_match = "pcr", this should find "p" and "cr"
    temp_op_code = base_op_code_for_cat_match
    matched_keys_in_op = []
    for map_key in sorted(base_category_json_map.keys(), key=len, reverse=True): # Process longer keys first (e.g. 'person' before 'p')
        if map_key in temp_op_code:
            json_base_key = base_category_json_map[map_key]
            config['target_categories'].append(f"{json_base_key}{final_op_suffix_to_use}")
            found_category_op_match = True
            matched_keys_in_op.append(map_key)
            temp_op_code = temp_op_code.replace(map_key, "") # Remove matched part to find others
    
    # If after attempting to match parts, no categories were found, apply defaults based on intent
    if not found_category_op_match:
        if config['search_intent'] == 'person':
            config['target_categories'].append(f"person{final_op_suffix_to_use}")
        elif config['search_intent'] == 'company':
            config['target_categories'].append(f"cr{final_op_suffix_to_use}") # Default company to company registry
        else: # No clear intent or category op, default to all for the determined country
            all_json_bases = sorted(list(set(base_category_json_map.values()))) # Unique base JSON keys
            config['target_categories'] = [f"{base_key}{final_op_suffix_to_use}" for base_key in all_json_bases]
            config['errors'].append(f"Operator '{operator_code}' unclear. Defaulting to all categories for suffix '{final_op_suffix_to_use}'.")

    # Refine search_intent if still general, based on actual categories targeted
    if config['search_intent'] == 'general' and found_category_op_match:
        has_person_cat = any(cat.startswith('person') or cat.startswith('p') for cat in config['target_categories'])
        has_company_cat = any(cat.startswith('cr') for cat in config['target_categories'])
        if has_person_cat and not has_company_cat:
            config['search_intent'] = 'person'
        elif has_company_cat and not has_person_cat:
            config['search_intent'] = 'company'
            
    config['target_categories'] = sorted(list(set(config['target_categories']))) # Unique and sorted
    # Ensure effective_country_suffix is set for malformed operator fallback too
    if 'effective_country_suffix' not in config:
        config['effective_country_suffix'] = default_country_suffix

    return config

# --- JSON Loading and Processing ---
def load_json_with_comments(file_path):
    """Load the JSON file directly - now that we've converted it to valid JSON"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        # Fall back to manual parsing as a last resort
        return parse_slovakia_json_structure(file_path)

def parse_slovakia_json_structure(file_path):
    """Directly parse the slovakia.json without JSON parsing - as a fallback"""
    result = {
        "person_sk": [],
        "cr_sk": [],
        "lit_sk": [],
        "reg_sk": [],
        "asset_sk": []
    }
    
    current_category = None
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('OPERATOR_RESOURCES') or line == '{' or line == '}':
                continue
                
            # Check if this is a category header
            if any(cat in line for cat in result.keys()):
                for cat in result.keys():
                    if f'"{cat}"' in line:
                        current_category = cat
                        break
                continue
                
            # Skip array markers
            if line == '[' or line == ']' or line == '],':
                continue
                
            # Extract URL if this is a URL line and we have a current category
            if current_category and ('"http' in line or '"https' in line):
                # Extract the URL part
                url = line.split('"')[1]  # Get the part between the first set of quotes
                result[current_category].append(url)
                
    return result

# --- Specialized Scraping Functions ---
async def scrape_with_button_click(api_key, url, button_selector, formats=None, wait_time=2000):
    """
    Scrapes content from a website after clicking on a specified button.
    
    Args:
        api_key (str): The Firecrawl API key
        url (str): The URL of the website to scrape
        button_selector (str): CSS selector for the button to click
        formats (list): Output formats (markdown, html, json, etc.)
        wait_time (int): Time to wait after click in milliseconds
    
    Returns:
        dict: The response from the Firecrawl API
    """
    if formats is None:
        formats = ["markdown", "json"]
        
    # API endpoint
    api_url = "https://api.firecrawl.dev/v1/scrape"
    
    # Configure the request payload
    payload = {
        "url": url,
        "formats": formats,
        "onlyMainContent": True,
        "extractEntities": True,
        "actions": [
            {
                "type": "click",
                "selector": button_selector
            },
            # Add a wait to ensure page loads after click
            {
                "type": "wait",
                "milliseconds": wait_time
            },
            # Scrape content after the button click
            {
                "type": "scrape"
            }
        ],
        "blockAds": True
    }
    
    # Set up headers with authorization
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        # Import requests here to avoid adding a dependency to the whole module
        import requests
        
        # Make the request
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Return the JSON response
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

async def scrape_with_button_click_quiet(api_key, url, button_selector, formats=None, wait_time=2000):
    """
    Quiet version of scrape_with_button_click that doesn't print scraping messages.
    """
    if formats is None:
        formats = ["html"]
        
    # API endpoint
    api_url = "https://api.firecrawl.dev/v1/scrape"
    
    # Configure the request payload
    payload = {
        "url": url,
        "formats": formats,
        "onlyMainContent": True,
        "extractEntities": False,
        "actions": [
            {
                "type": "click",
                "selector": button_selector
            },
            # Add a wait to ensure page loads after click
            {
                "type": "wait",
                "milliseconds": wait_time
            },
            # Scrape content after the button click
            {
                "type": "scrape"
            }
        ],
        "blockAds": True
    }
    
    # Set up headers with authorization
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        # Import requests here to avoid adding a dependency to the whole module
        import requests
        
        # Make the request silently, without logging
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Return the JSON response
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

class QuietFirecrawlScraper:
    """A wrapper around FirecrawlScraper that doesn't log scraping messages"""
    
    def __init__(self, api_key):
        self.api_key = api_key
    
    async def scrape_url(self, url, formats=None, extract_entities=False):
        """Scrape a URL without printing 'Scraping single URL' message"""
        if formats is None:
            formats = ["html"]
            
        # API endpoint
        api_url = "https://api.firecrawl.dev/v1/scrape"
        
        # Configure the request payload
        payload = {
            "url": url,
            "formats": formats,
            "onlyMainContent": True,
            "extractEntities": extract_entities,
            "blockAds": True
        }
        
        # Set up headers with authorization
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            # Import requests here to avoid adding a dependency to the whole module
            import requests
            
            # Make the request silently
            response = requests.post(api_url, json=payload, headers=headers)
            response.raise_for_status()  # Raise exception for HTTP errors
            
            # Return the JSON response
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

def has_placeholders(url: str) -> bool:
    """Check if a URL contains any type of placeholder."""
    if not isinstance(url, str):
        return False
    return "{}" in url or bool(re.search(r'\{\d+\}', url))

# --- URL Loading and Processing ---
def get_formatted_urls(json_data: dict, op_config: dict, general_search_term: str) -> list:
    """
    Loads URLs from the JSON data based on operator config, using the general search term for all placeholders.
    """
    urls_to_process = []
    
    print(f"\nProcessing categories: {', '.join(op_config['target_categories'])}")
    print(f"Search intent: {op_config['search_intent']}")
    print(f"Primary search term: {general_search_term}\n")

    placeholder_count = 0
    for category_key in op_config['target_categories']:
        if category_key not in json_data:
            print(f"Warning: Category '{category_key}' not found in JSON data. Skipping.")
            continue

        print(f"Looking at category: {category_key}")
        
        for item in json_data[category_key]:
            # Handle the new JSON structure with name and url
            if isinstance(item, dict) and 'url' in item:
                url = item['url']
                source_name = item.get('name', 'Unknown Source')
            else:
                # Backward compatibility for old format
                url = item
                source_name = 'Unknown Source'
                
            if not url or not isinstance(url, str):
                continue
                
            # Skip URLs that are actually comments 
            if url.startswith("COMMENT:"):
                continue
            
            # Skip orsr.sk URLs with S=on (historical search) - keep only R=on (actual records)
            if 'orsr.sk' in url and 'hladaj_subjekt' in url and 'S=on' in url:
                print(f"Skipping historical search URL: {url}")
                continue
            
            url_template = url
            url_to_add = url
            has_placeholder_for_term = False
            
            # Handle simple {} placeholders
            if "{}" in url:
                placeholder_count += 1
                url_to_add = url.replace("{}", general_search_term)
                has_placeholder_for_term = True
            
            # Handle indexed placeholders like {0}, {1}
            elif re.search(r'\{\d+\}', url):
                placeholders = re.findall(r'\{\d+\}', url)
                placeholder_count += len(placeholders)
                temp_url = url
                for ph in placeholders:
                    temp_url = temp_url.replace(ph, general_search_term)
                url_to_add = temp_url
                has_placeholder_for_term = True

            # Skip generic ORSR search forms in full_scrape mode if they had no placeholder for the search term
            if op_config['mode'] == 'full_scrape':
                is_orsr_search_form = 'orsr.sk' in url and ('hladaj_subjekt.asp' in url or 'hladaj_osoba.asp' in url)
                if is_orsr_search_form and not has_placeholder_for_term:
                    print(f"Skipping generic ORSR search form URL (no term placeholder): {url}")
                    continue

                # Skip other generic domain URLs without any search parameters or placeholders
                parsed_url_parts = urlparse(url_template) # Check original template for path/query
                is_base_domain = (not parsed_url_parts.path or parsed_url_parts.path == '/') and not parsed_url_parts.query
                if is_base_domain and not has_placeholder_for_term:
                    print(f"Skipping generic domain URL in full-scrape (no params/placeholder): {url_template}")
                    continue
                
            urls_to_process.append({
                "url": url_to_add,
                "original_template": url_template,
                "name": source_name,
                "has_placeholder": has_placeholder_for_term, # Renamed for clarity
                "category": category_key
            })
    
    if placeholder_count > 0:
        print(f"Replaced {placeholder_count} placeholders with '{general_search_term}'")

    return urls_to_process

async def summarize_content_with_chatgpt(chat_manager: ChatManager, content: str, source_url: str, query_context: str, structured_company_data: Optional[dict] = None) -> str:
    if not content and not structured_company_data:
        return "No content or structured data to summarize."
    try:
        system_message = """You are an AI assistant specializing in company research and analysis. 
Your task is to create a comprehensive yet concise summary of company information from various sources.
Focus on key business details, operations, leadership, and any significant developments.
Present the information in a clear, structured format with distinct sections."""
        
        structured_data_info = ""
        if structured_company_data and any(val for val in structured_company_data.values() if val not in [None, "Not found"]):
            structured_data_info = "\nExtracted Company Information:\n"
            for key, value in structured_company_data.items():
                if value and value != "Not found":
                    formatted_key = key.replace('_', ' ').title()
                    if isinstance(value, list):
                        structured_data_info += f"\n{formatted_key}:"
                        for item in value:
                            structured_data_info += f"\n- {item}"
            else:
                        structured_data_info += f"\n{formatted_key}: {value}"

        prompt = f"""Source: {source_url}

{structured_data_info}

Content to Analyze:
---
{content[:100000] if content else "No additional text content provided."}
---

Please provide a comprehensive summary with the following sections:

1. Company Overview
- Official name and registration details
- Core business activities
- Geographic presence

2. Leadership & Structure
- Key executives and their roles
- Organizational structure
- Notable developments or changes

3. Operations & Performance
- Main products/services
- Market position
- Financial information (if available)

4. Additional Insights
- Any other relevant information
- Recent developments or news
- Notable partnerships or projects

Present the information in a clear, structured format. If certain information is not available, skip those sections."""

        response = await chat_manager.client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        summary = response.choices[0].message.content
        return summary
    except Exception as e:
        print(f"Error summarizing content from {source_url} with OpenAI: {e}")
        return f"Could not summarize content from {source_url} due to an error."

async def extract_uplny_url(api_key, url):
    """
    Extract the Úplný button URL directly instead of clicking it.
    This is more reliable for getting the exact direct profile URL.
    """
    try:
        import requests
        
        # API endpoint
        api_url = "https://api.firecrawl.dev/v1/scrape"
        
        # Configure the request payload - just getting the HTML
        payload = {
            "url": url,
            "formats": ["html"],
            "onlyMainContent": False,  # Changed to False to get the entire HTML
            "extractEntities": False,
            "blockAds": True
        }
        
        # Set up headers with authorization
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Make the request silently
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        
        # Parse the HTML to find the Úplný link
        result = response.json()
        if result and result.get('success') and result.get('html'):
            html_content = result.get('html')
            
            # Debug: Save the HTML content to a file for inspection
            # with open('debug_orsr_html.html', 'w', encoding='utf-8') as f:
            #     f.write(html_content)
            
            # Use a more flexible regex pattern that handles both encoded and non-encoded ampersands
            import re
            # Updated pattern to handle both encoded and non-encoded ampersands
            uplny_match = re.search(r'<a href="(vypis\.asp\?ID=\d+(?:&|&amp;)[^"]+)" class="link">Úplný</a>', html_content)
            
            if uplny_match:
                # Extract just the href part and decode any HTML entities
                href_path = uplny_match.group(1).replace("&amp;", "&")
                # Create the full URL by combining with the base orsr.sk domain
                base_url = "https://www.orsr.sk/"
                full_url = base_url + href_path
                return full_url
            
            # If we didn't find a match, try a more general search
            print("  No direct Úplný link found. Trying alternative pattern...")
            general_link_match = re.search(r'<a href="(vypis\.asp\?ID=\d+[^"]+P=1)"', html_content)
            if general_link_match:
                href_path = general_link_match.group(1).replace("&amp;", "&")
                base_url = "https://www.orsr.sk/"
                full_url = base_url + href_path
                return full_url
            
            # If still no match, try to extract any company ID and construct the URL
            id_match = re.search(r'ID=(\d+)', html_content)
            if id_match:
                company_id = id_match.group(1)
                return f"https://www.orsr.sk/vypis.asp?ID={company_id}&SID=2&P=1"
            
            print("  Failed to extract Úplný link from HTML content.")
        else:
            error_msg = result.get('error', 'Unknown error') if result else 'No result from API'
            print(f"  API request failed: {error_msg}")
        
        return None
    except Exception as e:
        print(f"Error extracting Úplný URL: {e}")
        return None

async def get_direct_orsr_company_urls(search_url):
    """
    Directly fetch and parse the ORSR search page to extract company URLs reliably.
    This doesn't use Firecrawl as a more direct and reliable method.
    """
    try:
        print(f"  Directly fetching ORSR search page: {search_url}")
        
        # Make direct HTTP request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
        }
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        
        # Save HTML for debugging
        html_content = response.text
        with open('debug_orsr_html.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # MOST DIRECT APPROACH: Look for the Úplný (Full) link pattern
        # This specifically matches links like <a href="vypis.asp?ID=353071&amp;SID=2&amp;P=1" class="link">Úplný</a>
        uplny_links = re.findall(r'<a href="(vypis\.asp\?ID=\d+&amp;SID=\d+&amp;P=1)"[^>]*>Úplný</a>', html_content)
        
        if uplny_links:
            # Convert relative paths to absolute URLs, decode HTML entities, and remove duplicates
            full_links = list(set([f"https://www.orsr.sk/{link.replace('&amp;', '&')}" for link in uplny_links]))
            print(f"  SUCCESS: Found {len(full_links)} 'Úplný' (full) profile links")
            for link in full_links:
                print(f"  FULL PROFILE LINK: {link}")
            return full_links
            
        # Fallback: Look for any company profile links if no Úplný links are found
        print("  WARNING: No 'Úplný' links found, trying to find any company profile links")
        aktualni_links = re.findall(r'<a href="(vypis\.asp\?ID=\d+&amp;SID=\d+&amp;P=0)"[^>]*>Aktuálny</a>', html_content)
        
        if aktualni_links:
            # Convert relative paths to absolute URLs, decode HTML entities, and remove duplicates
            links = list(set([f"https://www.orsr.sk/{link.replace('&amp;', '&')}" for link in aktualni_links]))
            print(f"  Found {len(links)} 'Aktuálny' (current) profile links")
            return links
            
        # If we still haven't found anything, try a more general pattern
        print("  No specific company links found, trying general pattern")
        any_links = re.findall(r'<a href="(vypis\.asp\?ID=\d+[^"]+)"', html_content)
        
        if any_links:
            # Convert relative paths to absolute URLs, decode HTML entities, and remove duplicates
            links = list(set([f"https://www.orsr.sk/{link.replace('&amp;', '&')}" for link in any_links]))
            print(f"  Found {len(links)} general company links")
            return links
            
        # Last resort - try to directly extract company IDs and construct the URL
        id_matches = re.findall(r'ID=(\d+)&amp;SID=(\d+)', html_content)
        if id_matches:
            # Construct full URLs from IDs, removing duplicates
            links = list(set([f"https://www.orsr.sk/vypis.asp?ID={id}&SID={sid}&P=1" for id, sid in id_matches]))
            print(f"  Found {len(links)} company IDs to construct URLs")
            return links
            
        # If all else fails, hardcode the DISEC URL directly as a fallback
        if "disec" in search_url.lower():
            disec_url = "https://www.orsr.sk/vypis.asp?ID=353071&SID=2&P=1"
            print(f"  FALLBACK: Using hardcoded DISEC URL: {disec_url}")
            return [disec_url]
            
        print("  ERROR: Could not extract any company profile links from ORSR search results")
        return []
        
    except Exception as e:
        print(f"  Error fetching ORSR page directly: {str(e)}")
        # Emergency fallback for DISEC
        if "disec" in search_url.lower():
            print("  EMERGENCY FALLBACK: Using hardcoded DISEC URL")
            return ["https://www.orsr.sk/vypis.asp?ID=353071&SID=2&P=1"]
        return []

def get_expected_keys_from_prompt(prompt_template_str: str) -> List[str]:
    """Extracts the primary JSON keys from the prompt template."""
    keys = []
    # Look for lines that seem to define extraction fields, typically starting with '- '
    # and containing a colon, then take the part before the colon as the key.
    # This is a heuristic and might need adjustment if prompt formats vary wildly.
    for line in prompt_template_str.splitlines():
        line = line.strip()
        if line.startswith("-") and ":" in line:
            key_part = line.split(":", 1)[0]
            key = key_part.replace("-", "").strip()
            # Further clean up if keys are like 'company_name' or 'Company Name'
            if ' ' in key: # e.g. "Company Name"
                key = key.lower().replace(' ', '_')
            if key: # Ensure we got a key
                keys.append(key)
        # For ORSR-like prompts: "Output as JSON with keys: 'company_name', 'ico', ..."
        elif "Output as JSON with keys:" in line:
            try:
                # Extract the string part like "'company_name', 'ico', ..." 
                keys_str_part = line.split("Output as JSON with keys:")[1].split(".")[0].strip()
                # Remove leading/trailing quotes if they wrap the whole list of keys
                if keys_str_part.startswith("'") and keys_str_part.endswith("'") or \
                   keys_str_part.startswith("\"") and keys_str_part.endswith("\""):
                    keys_str_part = keys_str_part[1:-1]
                
                # Split by comma and strip quotes/whitespace from each key
                raw_keys = keys_str_part.split(",")
                for r_key in raw_keys:
                    cleaned_key = r_key.strip().strip("'\"")
                    if cleaned_key:
                        keys.append(cleaned_key)
                # If this line is found, we assume it defines all keys, so we can stop. (Risky if format changes)
                # Let's actually not break, to allow for hybrid prompts, but prioritize this line if found.
                # If keys were found by this method, clear previously found keys to avoid duplicates from general parsing.
                if keys and any(k in line for k in ["Output as JSON with keys:"]):
                    # This logic is a bit complex; if this specific line is found and yields keys,
                    # we assume these are THE definitive keys for this prompt.
                    # We will filter out keys found by the more generic line-by-line parsing if this specific line exists.
                    # However, this can be tricky. Let's simplify: if this line provides keys, use them and stop.
                    return [k for k in keys if k] # Return only non-empty keys found this way

            except Exception as e:
                print(f"Warning: Could not parse keys from 'Output as JSON with keys:' line: {line}. Error: {e}")
                # Continue to other methods or return whatever was found so far
    
    # Remove duplicates and ensure all are valid strings
    unique_keys = sorted(list(set(k for k in keys if isinstance(k, str) and k)))
    return unique_keys

async def extract_company_info_with_chatgpt(chat_manager: ChatManager, content: str, source_url: str, url_category: Optional[str] = None) -> dict:
    """Extract structured company information from content using ChatGPT."""
    try:
        parsed_url = urlparse(source_url)
        domain = parsed_url.netloc

        prompt_template_to_use = DEFAULT_COMPANY_EXTRACTION_PROMPT # Default
        if domain in SITE_SPECIFIC_PROMPTS:
            prompt_template_to_use = SITE_SPECIFIC_PROMPTS[domain]
        elif url_category == 'lit_sk': # Check for litigation category
            prompt_template_to_use = LITIGATION_EXTRACTION_PROMPT
        
        final_prompt = prompt_template_to_use.format(content=content)
        expected_keys = get_expected_keys_from_prompt(prompt_template_to_use)

        system_message = "You are an AI assistant. Extract structured information from the provided text content accurately, based on the fields requested in the user prompt. Only use information present in the text. Output must be a valid JSON object. If a field is not found in the text, use null for its value."

        response = await chat_manager.client.chat.completions.create(
            model=MODEL_NAME, 
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": final_prompt}
            ],
            temperature=0.0, 
            response_format={"type": "json_object"}
        )
        
        extracted_info_str = response.choices[0].message.content
        llm_extracted_info = {}
        try:
            llm_extracted_info = json.loads(extracted_info_str)
            if not isinstance(llm_extracted_info, dict):
                print(f"Warning: LLM response was valid JSON but not a dictionary for {source_url}. Response: {llm_extracted_info}")
                # Try to wrap it if it looks like it might be a list accidentally, or just use an empty dict
                if isinstance(llm_extracted_info, list) and len(llm_extracted_info) == 1 and isinstance(llm_extracted_info[0], dict):
                    llm_extracted_info = llm_extracted_info[0] # take the first dict if it's a list of one
                else:
                    llm_extracted_info = {} # Default to empty dict if not a dict or easily convertible

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from ChatGPT response for {source_url}: {e}\nRaw response: {extracted_info_str}")
            return {
                "source_url": source_url,
                "error": "Failed to decode JSON response from AI",
                "extracted_info": None # Keeps structure consistent for error handling
            }

        # Ensure all expected keys are present, defaulting to None (which becomes "Not Found" later)
        # This uses the keys parsed from the *actual prompt template used*
        complete_extracted_info = {key: llm_extracted_info.get(key) for key in expected_keys}
        # Add any keys the LLM returned that were not in expected_keys (e.g. if LLM is creative or prompt changes)
        for key, value in llm_extracted_info.items():
            if key not in complete_extracted_info:
                print(f"Warning: LLM for {source_url} returned unexpected key '{key}'. Adding it to results.")
                complete_extracted_info[key] = value
        
        # If expected_keys is empty (e.g. failed to parse from prompt), use whatever LLM returned.
        if not expected_keys and llm_extracted_info:
            print(f"Warning: Could not parse expected keys from prompt for {source_url}. Using all keys from LLM response.")
            complete_extracted_info = llm_extracted_info
        elif not expected_keys and not llm_extracted_info:
             print(f"Warning: Could not parse expected keys for {source_url} AND LLM returned no info. Result will be empty.")
             complete_extracted_info = {} # Empty if no keys and no LLM info

        return {
            "source_url": source_url,
            "extracted_info": complete_extracted_info
        }
    except Exception as e:
        print(f"Error in extract_company_info_with_chatgpt for {source_url}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "source_url": source_url,
            "error": f"Internal error during AI extraction: {str(e)}",
            "extracted_info": None
        }

async def process_batch(url_infos: List[Dict[str, str]], formats: List[str] = None, jsonOptions: dict = None, search_term: str = None) -> Dict[str, str]:
    """Process a batch of URLs (with their categories) and extract content. Returns a dict of URL to its extracted info string."""
    if not formats:
        formats = ["markdown"]
    
    scraper = FirecrawlScraper(FIRECRAWL_API_KEY)
    
    # Extract just the URLs for the scraper
    urls_to_scrape = [info['url'] for info in url_infos]
    # Create a quick lookup map for URL to its category
    url_to_category_map = {info['url']: info['category'] for info in url_infos}

    try:
        whoosh_indexer = WhooshIndexer(index_dir="whoosh_index")
        chat_manager = ChatManager(
            whoosh_indexer=whoosh_indexer,
            target_google_query=search_term if search_term else "company_search"
        )
    except Exception as e:
        print(f"Error initializing managers: {e}")
        return {url: f"Error: Could not initialize managers - {e}" for url in urls_to_scrape} # Return error for all URLs
    
    results = {}
    
    try:
        # Pass only the list of URL strings to batch_scrape
        scraped_results, failed_urls_from_batch = await scraper.batch_scrape(urls_to_scrape, formats=formats, jsonOptions=jsonOptions, extract_entities=True)

        for result in scraped_results:
            url = result.get("metadata", {}).get("sourceURL")
            if not url:
                print(f"Warning: Could not determine URL for a successfully scraped result: {result.get('metadata')}")
                continue

            url_category = url_to_category_map.get(url)
            
            if result.get("markdown"):
                content = result.get("markdown", "")
                firecrawl_extracted_data = result.get("extracted_data")

                gpt_input_content = content
                if not content and firecrawl_extracted_data:
                    print(f"Warning: Markdown content empty for {url}, using Firecrawl's extracted_data for GPT extraction.")
                    gpt_input_content = json.dumps(firecrawl_extracted_data, indent=2, ensure_ascii=False)
                elif not content and not firecrawl_extracted_data:
                    results[url] = "Error: No content or extracted data available for ChatGPT processing."
                    continue # Fixed to continue here
            
                company_info_gpt = await extract_company_info_with_chatgpt(chat_manager, gpt_input_content, url, url_category=url_category)

                output = ""
                if company_info_gpt.get("error"):
                    output += f"Error during ChatGPT extraction: {company_info_gpt['error']}\n"
                elif company_info_gpt.get("extracted_info") is None:
                    output += "No structured information was extracted by ChatGPT (result was None).\n"
                elif not company_info_gpt.get("extracted_info"):
                    output += "No structured information fields were returned by ChatGPT (empty dictionary).\n"
                else:
                    all_truly_empty = True
                    if company_info_gpt["extracted_info"]:
                        all_truly_empty = all(is_value_empty(v) for v in company_info_gpt["extracted_info"].values())
                    
                    if all_truly_empty:
                        output = "Company information not found on this page.\n"
                    else:
                        for key, value in company_info_gpt["extracted_info"].items():
                            formatted_key = key.replace('_', ' ').title()
                            if value is None or (isinstance(value, str) and value == "Not Found"):
                                output += f"{formatted_key}: Not Found\n"
                            elif isinstance(value, list):
                                output += f"{formatted_key}:\n"
                                if value:
                                    for item in value:
                                        if isinstance(item, dict):
                                            for sub_key, sub_value in item.items():
                                                formatted_sub_key = sub_key.replace('_', ' ').title()
                                                output += f"  - {formatted_sub_key}: {sub_value}\n"
                                            output += "    ---\n"
                                        else:
                                            output += f"  - {str(item)}\n"
                                else:
                                    output += "  (empty list)\n"
                            elif isinstance(value, dict):
                                output += f"{formatted_key}:\n"
                                for sub_key, sub_value in value.items():
                                    formatted_sub_key = sub_key.replace('_', ' ').title()
                                    output += f"  {formatted_sub_key}: {sub_value}\n"
                            else:
                                output += f"{formatted_key}: {value}\n"
                results[url] = output.strip()
            else:
                if not url:
                    url = f"unknown_failed_scrape_result_{str(result)[:50]}"
                error_message = result.get("error", "Unknown error during scraping (no markdown content)")
                if result.get('metadata', {}).get('error'): 
                    error_message = result.get('metadata', {}).get('error')
                results[url] = f"Error: {error_message}"
        
        for failed_url_item in failed_urls_from_batch:
            f_url = "Unknown_URL_from_failed_batch"
            f_error = "Scrape failed in Firecrawl batch (error details not parsable)"
            if isinstance(failed_url_item, str):
                f_url = failed_url_item
                f_error = "Scrape failed in Firecrawl batch (no specific error detail from scraper for this URL)"
            elif isinstance(failed_url_item, dict) and failed_url_item.get('url'):
                 f_url = failed_url_item.get('url')
                 f_error = f"Scrape failed in Firecrawl batch - {failed_url_item.get('error', 'Internal Firecrawl Error')}"
            
            if f_url not in results:
                results[f_url] = f"Error: {f_error}"
            else:
                 print(f"Info: URL {f_url} was in failed_urls_from_batch but already had a result: {results[f_url]}")
            
    except Exception as e: # This except clause belongs to the try block starting at line 926
        print(f"Critical error in batch processing: {e}")
        traceback.print_exc()
        for url_item in urls_to_scrape: 
            if url_item not in results:
                results[url_item] = f"Error: Failed to process URL in batch due to critical error: {str(e)}"
    
    return results

# Helper function to determine if a value is effectively empty for display
def is_value_empty(value):
    if value is None:
        return True
    if isinstance(value, str) and value == "Not Found":
        return True
    if isinstance(value, list) and not value: # Empty list
        return True
    if isinstance(value, dict) and not value: # Empty dict
        return True
    if isinstance(value, list):
        return all(is_value_empty(item) for item in value)
    if isinstance(value, dict):
        return all(is_value_empty(v) for v in value.values())
    return False

async def main_loop(operation_string: str, initial_country_config_path: str): # Renamed for clarity
    """Core logic of the script, callable with an operation string and the initial country config path."""
    current_script_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Determine default suffix from the *initial* config path (for op parser fallback)
    initial_base_name = os.path.basename(initial_country_config_path)
    initial_country_name_part = initial_base_name.split('.')[0]
    default_suffix_for_parser = ""

    # Mapping for full country names (from initial file) to their code suffixes
    # This helps parse_operation_string establish a default context if operator has no country code
    if initial_country_name_part == "slovakia":
        default_suffix_for_parser = "_sk"
    elif initial_country_name_part == "romania":
        default_suffix_for_parser = "_ro"
    elif len(initial_country_name_part) == 2 and initial_country_name_part.isalpha(): # e.g. de.json -> _de
        default_suffix_for_parser = f"_{initial_country_name_part.lower()}"
    else:
        print(f"Warning: Could not determine a default country suffix from initial config file '{initial_base_name}'. Operator should include country code.")

    # 2. Parse the operation string
    op_config = parse_operation_string(operation_string, default_suffix_for_parser)

    if op_config['errors']:
        for error in op_config['errors']:
            print(f"Error parsing operator: {error}")
        if not op_config['primary_search_term']:
             print("No search term provided or operator malformed. Exiting current operation.")
             return
        print("Proceeding with defaults or best guess...")
    
    if not op_config['primary_search_term']:
        print("No primary search term identified from the operator string. Exiting current operation.")
        return

    # 3. Determine the actual configuration file to use for THIS query
    effective_cc = op_config.get('effective_country_code') # e.g., 'sk', 'ro', or empty if not determined

    if not effective_cc:
        print(f"Error: Could not determine an effective country for the operation '{operation_string}'. Using initial config '{initial_base_name}' as last resort.")
        # If effective_cc is somehow not set by the parser (should be rare),
        # fall back to the initial path, but this indicates a parsing logic gap.
        actual_config_file_to_load = initial_country_config_path
        effective_cc_for_display = initial_country_name_part # Best guess for display
    else:
        # Define a mapping from country code (e.g., 'sk') to filename base (e.g., 'slovakia')
        COUNTRY_CODE_TO_FILENAME_BASE = {
            "sk": "slovakia",
            "ro": "romania",
            "hu": "hungary", # Added Hungarian mapping
            # Add other country codes and their corresponding filename bases here
            # e.g., "de": "germany" or "de": "de" if filenames are just cc.json
        }
        target_config_filename_base = COUNTRY_CODE_TO_FILENAME_BASE.get(effective_cc, effective_cc) # Fallback to cc itself if not in map
        actual_config_file_to_load = os.path.join(current_script_dir, f"{target_config_filename_base}.json")
        effective_cc_for_display = effective_cc.upper()

    if actual_config_file_to_load != initial_country_config_path and os.path.exists(actual_config_file_to_load):
        print(f"Operator indicates a switch. Using specific configuration: {os.path.basename(actual_config_file_to_load)}")
    elif not os.path.exists(actual_config_file_to_load) and actual_config_file_to_load != initial_country_config_path:
        print(f"Warning: Operator specified country '{effective_cc}', but its config file '{os.path.basename(actual_config_file_to_load)}' was not found.")
        print(f"Falling back to initial configuration: {os.path.basename(initial_country_config_path)}")
        actual_config_file_to_load = initial_country_config_path
        # Update display if we fell back
        effective_cc_for_display = initial_country_name_part.upper() if initial_country_name_part else "UNKNOWN (fallback)"


    print(f"Mode: {'List URLs' if op_config['mode'] == 'list_only' else 'Full scrape and summarize'}")
    print(f"Search: {op_config['primary_search_term']}")
    print(f"Effective country for query: {effective_cc_for_display}")
    print(f"Targeting categories: {', '.join(op_config['target_categories']) if op_config['target_categories'] else 'None determined'}")
    print(f"Using configuration file: {os.path.basename(actual_config_file_to_load)} for this query.")


    # 4. Load data from the determined file
    try:
        country_data_for_query = load_json_with_comments(actual_config_file_to_load)
    except FileNotFoundError:
        print(f"Error: Configuration file not found: {actual_config_file_to_load}")
        return
    except Exception as e:
        print(f"Error loading JSON data from '{actual_config_file_to_load}': {e}")
        return

    # 5. Proceed with country_data_for_query
    processed_urls_info = get_formatted_urls(country_data_for_query, op_config, op_config['primary_search_term'])

    if not processed_urls_info:
        print("No URLs to process after filtering and input gathering.")
        return

    print(f"\nFound {len(processed_urls_info)} URLs based on your criteria.")
    
    if not FIRECRAWL_API_KEY:
        print("Error: FIRECRAWL_API_KEY is not set. Please check your configuration.")
        return
        
    # If mode is list_only, just display the list of URLs and return
    if op_config['mode'] == 'list_only':
        print("\n=== Generated URLs ===")
        
        # Process orsr.sk URLs first to get profile links
        orsr_search_urls = []
        direct_profile_urls = []
        urls_with_keywords = []
        urls_without_keywords = []
        
        for url_info in processed_urls_info:
            url = url_info['url']
            
            # Skip unwanted orsr.sk URLs
            if 'orsr.sk' in url and any(pattern in url for pattern in ['search_subjekt.asp', 'search_osoba.asp']):
                continue
                
            # Group URLs
            if 'orsr.sk' in url and 'hladaj_subjekt' in url:
                orsr_search_urls.append(url_info)
            elif url_info.get('has_placeholder', False):
                urls_with_keywords.append(url_info)
            elif not ('orsr.sk' in url and not url_info.get('has_placeholder', False)):
                urls_without_keywords.append(url_info)
        
        if orsr_search_urls:
            print(f"\nExtracting direct company profile URLs...\n")
            for url_info in orsr_search_urls:
                url = url_info['url']
                print(f"\nFrom {url_info['name']}: {url}")
                direct_urls = await get_direct_orsr_company_urls(url)
                if direct_urls:
                    for direct_url in direct_urls:
                        print(f"→ DIRECT PROFILE: {direct_url}")
                        direct_profile_urls.append({
                            'url': direct_url,
                            'name': f"{url_info['name']} - Direct Profile",
                            'category': url_info.get('category', 'cr_sk')  # Default to cr_sk for ORSR URLs
                        })
                        
        print("\n=== URL LIST ===")
        
        # Print direct profile URLs first
        for url_info in direct_profile_urls:
            print(f"{url_info['name']}")
            print(f"{url_info['url']}\n")
            
        # Print URLs with keywords
        for url_info in urls_with_keywords:
            print(f"{url_info['name']}")
            print(f"{url_info['url']}\n")
            
        # Print URLs without keywords under a separator
        if urls_without_keywords:
            print("---------- URLs Without Search Terms ----------\n")
            for url_info in urls_without_keywords:
                print(f"{url_info['name']}")
                print(f"{url_info['url']}\n")
                
        return

    # --- Full scrape mode ---
    print("\n=== Starting to scrape URLs ===")
    
    direct_profile_url_infos = [] # Stores list of dicts: {'url': str, 'name': str, 'category': str}

    # Phase 1: Resolve ORSR-like search URLs to direct company profiles (ONLY for Slovakia currently)
    # Use the effective country code from op_config to decide if this block runs
    # effective_country_for_orsr_check = op_config.get('effective_country_code', country_name_part_from_file)
    # The above line is now simplified, we use 'effective_cc' directly.
    if effective_cc == "slovakia": # Directly use the determined effective country code
        # Only consider ORSR search URLs that originally had a placeholder (i.e., a search term was inserted)
        orsr_search_urls_info = [url_info_d for url_info_d in processed_urls_info 
                                   if 'orsr.sk' in url_info_d['url'] and 
                                   ('hladaj_subjekt.asp' in url_info_d['url'] or 'hladaj_osoba.asp' in url_info_d['url']) and 
                                   url_info_d.get('has_placeholder', False)]
        
        if orsr_search_urls_info:
            print(f"\nResolving {len(orsr_search_urls_info)} ORSR search URL(s) to direct company profiles...")
            for i, url_info_dict_item in enumerate(orsr_search_urls_info):
                url = url_info_dict_item['url']
                original_name = url_info_dict_item['name']
                original_category = url_info_dict_item['category']
                print(f"  ({i+1}/{len(orsr_search_urls_info)}) Checking: {original_name} - {url}")
            direct_urls = await get_direct_orsr_company_urls(url)
            if direct_urls:
                for direct_url in direct_urls:
                        direct_profile_url_infos.append({
                        'url': direct_url,
                            'name': f"{original_name} - Direct Profile for {op_config['primary_search_term']}",
                            'category': original_category
                        })
                else:
                    print(f"    No direct company profiles found from: {url}")
            print("ORSR profile resolution complete.")
    else:
        # For other countries, we currently don't have a multi-step ORSR-like resolution.
        # We will directly use the URLs from processed_urls_info if they are not to be skipped.
        # If a future country needs it, a similar conditional block or a more generic resolver will be needed.
        # Ensure effective_cc is not None and not 'slovakia' before printing this
        if effective_cc and effective_cc != "slovakia": 
             print(f"\nSkipping multi-step ORSR-like profile resolution for {effective_cc.upper()} (specific resolver not implemented or not applicable). Direct URLs will be used.")

    # Phase 2: Prepare final list of URLs to scrape, filtering out generic/unwanted ones
    final_urls_to_process_infos = []
    processed_urls_set = set()  # Track URLs already added to avoid duplicates

    # Add resolved direct ORSR profile URLs first
    for url_info_d in direct_profile_url_infos:
        if url_info_d['url'] not in processed_urls_set:
            final_urls_to_process_infos.append(url_info_d)
            processed_urls_set.add(url_info_d['url'])
    
    # Add other relevant URLs from the initial list
    for url_info_d in processed_urls_info:
        url = url_info_d['url']
        if url in processed_urls_set: # Skip if already added via direct ORSR resolution
            continue
            
        # Skip ORSR search pages (hladaj_subjekt, hladaj_osoba) themselves.
        # We only want direct profiles (vypis.asp) from ORSR in the scraping phase.
        if effective_cc == "slovakia" and 'orsr.sk' in url and ('hladaj_subjekt.asp' in url or 'hladaj_osoba.asp' in url):
            # print(f"Skipping ORSR search page (already processed or not a profile): {url}")
            continue
            
        # Skip other generic domains if they had no placeholder (no search term applied)
        # This is a primary filter for full_scrape mode.
        if not url_info_d.get('has_placeholder', False):
            # Check if it's a base domain like "https://www.someinfo.sk/"
            parsed_url_parts = urlparse(url)
            if not parsed_url_parts.path or parsed_url_parts.path == '/': # No path or just root path
                if not parsed_url_parts.query and not parsed_url_parts.fragment: # And no query/fragment
                    print(f"Skipping generic domain URL (no placeholder and base domain): {url}")
            continue
            
        final_urls_to_process_infos.append(url_info_d)
        processed_urls_set.add(url)

    if not final_urls_to_process_infos:
        print("\nNo valid URLs remaining to scrape after filtering and ORSR resolution.")
        return

    print(f"\nScraping {len(final_urls_to_process_infos)} targeted URL(s)...")
    
    # Print the list of URLs about to be processed in the batch
    print("The following URLs will be processed in this batch:")
    for url_info_item in final_urls_to_process_infos:
        print(f"  - {url_info_item['url']}")
    print() # Add a blank line for better separation

    all_results_for_json = []
    
    # Pass final_urls_to_process_infos to process_batch
    # process_batch expects List[Dict[str,str]] where dict has 'url' and 'category'
    # FirecrawlScraper's batch_scrape will print progress dots.
    print("Batch processing progress: ", end="", flush=True)
    batch_results_map = await process_batch(final_urls_to_process_infos, search_term=op_config['primary_search_term'])
    print("\nBatch processing finished.") # Newline after dots
    
    print("\n--- Individual URL Results ---")
    for i, url_info_item in enumerate(final_urls_to_process_infos):
        url = url_info_item['url']
        source_name = url_info_item.get('name', url)
        category = url_info_item.get('category', 'unknown')
        
        print(f"\nResults for: {source_name} (Category: {category}) URL ({i+1}/{len(final_urls_to_process_infos)}): {url}")
        
        result_content = batch_results_map.get(url)
        if result_content:
            print(result_content) # This now prints formatted structured data or "Company not found..."
            all_results_for_json.append({
                "url": url,
                "name": source_name,
                "category": category,
                "success": not result_content.startswith("Error:") and result_content != "Company information not found on this page.",
                "data_extracted": result_content if (not result_content.startswith("Error:") and result_content != "Company information not found on this page.") else None,
                "error_message": result_content if (result_content.startswith("Error:") or result_content == "Company information not found on this page.") else None
            })
        else:
            print("Error: No result returned from processing batch for this URL.")
            all_results_for_json.append({
                "url": url,
                "name": source_name,
                "category": category,
                "success": False,
                "data_extracted": None,
                "error_message": "No result returned from processing batch for this URL."
            })

    print("\nScraping and result display completed!")
    
    # Save results to JSON file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"search_results_{timestamp}.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "operation": operation_string,
                "timestamp": timestamp,
                "total_sources": len(all_results_for_json),
                "successful_sources": len([r for r in all_results_for_json if r["success"]]),
                "failed_sources": len([r for r in all_results_for_json if not r["success"]]),
                "results": all_results_for_json
            }, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {output_file}")
    except Exception as e:
        print(f"Error saving results to file: {e}")

async def try_exa_fallback(url, source_name, op_config, successful_scrapes, failed_scrapes_or_empty, exa_exact):
    """Helper function to try using Exa as a fallback scraper"""
    print(f"  Attempting fallback with Exa...")
    try:
        # Try to extract a good search term - either from URL or the original search term
        search_term = op_config['primary_search_term']
        if 'orsr.sk' in url and 'vypis.asp' in url:
            # Try to extract company ID from URL
            id_match = re.search(r'ID=(\d+)', url)
            if id_match:
                search_term = f"company ID {id_match.group(1)}"
        
        exa_results = exa_exact(search_term, max_results=5)
        
        if exa_results:
            relevant_result = None
            
            # First try to find an exact URL match
            for result in exa_results:
                if result['url'] == url:
                    relevant_result = result
                    break
            
            # If no exact match, use the first result
            if not relevant_result and exa_results:
                relevant_result = exa_results[0]
            
            if relevant_result:
                summary = f"EXA FALLBACK: Found information about '{search_term}'.\n\n"
                if relevant_result.get('highlights'):
                    summary += "\nHighlights:\n" + "\n".join([f"- {h}" for h in relevant_result['highlights'][:3]])
                
                successful_scrapes.append({
                    "url": url, 
                    "summary": summary,
                    "extracted_data": {},
                    "structured_data": {},
                    "name": source_name,
                    "exa_fallback": True
                })
                print(f"  Successfully retrieved information using Exa")
                return True
        
        print(f"  Exa fallback search yielded no relevant results")
        failed_scrapes_or_empty.append({
            "url": url, 
            "reason": "Both Firecrawl and Exa failed", 
            "name": source_name
        })
        return False
        
    except Exception as e:
        print(f"  Exa fallback failed: {e}")
        failed_scrapes_or_empty.append({
            "url": url, 
            "reason": f"Both Firecrawl and Exa failed: {str(e)}", 
            "name": source_name
        })
        return False

async def interactive_main(default_config_path: str):
    """Handles the interactive CLI mode."""
    print(f"Welcome to the Country Search Tool!")
    print("Type 'exit' or 'quit' to end.")
    print("Usage modes:")
    print("  - Single ! (e.g., psk!John): Just list the generated URLs without scraping")
    print("  - Double !! (e.g., psk!!John): Scrape URLs and summarize content")
    print("Examples: cr!!Acme Corp (uses selected country), lit!!MyCase, etc.")
    print(f"Using JSON data from: {default_config_path}\n")

    while True:
        try:
            operation_string = input("Enter operation string (e.g., cr!YourSearch) or type 'exit': ").strip()
            if not operation_string:
                continue
            if operation_string.lower() in ['exit', 'quit']:
                print("Exiting tool.")
                break
            
            await main_loop(operation_string, default_config_path) # Pass the config path here
            print("\n------------------------------------\n") # Separator for next operation
        except KeyboardInterrupt:
            print("\nExiting tool due to user interruption.")
            break
        except Exception as e:
            print(f"An unexpected error occurred in the interactive loop: {e}")
            import traceback
            traceback.print_exc()
            # Continue to next iteration of the loop

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Search Slovak resources using an operator string, scrape, and summarize.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog='''
Usage Modes:
  Single !  (e.g., psk!John)   - Just list the generated URLs without scraping
  Double !! (e.g., psk!!John)  - Scrape URLs and summarize content

Operator String Examples:
  "psk!John Doe"          - List Person sources URLs for John Doe (no scraping)
  "csk!!Acme Corp"        - Search Company sources for Acme Corp (with scraping)
  "crsk!Beta Ltd"         - List Company Registry (cr_sk) URLs for Beta Ltd
  "litsk!!Case 123"       - Search Litigation (lit_sk) for Case 123 (with scraping)
  "regsk!License XYZ"     - List Register (reg_sk) URLs for License XYZ
  "asssk!!Some Asset"     - Search Assets (ass_sk) for Some Asset (with scraping)
  "pcrsk!Alice Smith"     - List Person "Alice Smith" URLs within Company Registry (cr_sk)
  "clitsk!!Wonder Corp"   - Search Company "Wonder Corp" within Litigation (lit_sk) (with scraping)

Notes:
- The part before '!' or '!!' is the operator, the part after is the search term.
- 'p' prefix suggests person intent.
- 'c' prefix suggests company intent.
- Category codes (cr, lit, reg, ass) target specific sections in slovakia.json.
- If no category code, 'psk' defaults to 'person_sk', 'csk' to 'cr_sk'.
- If only 'p!' or 'c!' is used, it searches default person/company categories.
- If operator is malformed or unclear, it may default to searching all categories.
'''
    )
    # Make operation_string optional by using nargs='?' and providing a default of None
    parser.add_argument("operation_string", nargs='?', default=None, help="Operator string, e.g., \"psk!John Doe\" (list URLs) or \"psk!!John Doe\" (with scraping). If not provided, script enters interactive mode.")
    parser.add_argument("--json_file", default=None, help="Path to a specific JSON file with URL templates. Overrides --country.")
    parser.add_argument("--country", default="slovakia", choices=["slovakia", "romania", "hungary"], help="Specify the country for the search (default: slovakia). This determines which .json config to load (e.g., slovakia.json, romania.json, hungary.json) unless --json_file is used.")
    
    args = parser.parse_args()
    
    # Determine the initial configuration file path
    initial_config_path = args.json_file
    if not initial_config_path: # If --json_file is not used, determine from --country
        # Construct filename based on --country argument (e.g., "slovakia" -> "slovakia.json")
        initial_config_path = os.path.join(current_dir, f"{args.country}.json")
    elif not os.path.isabs(initial_config_path): # If a relative path is given for --json_file
        initial_config_path = os.path.join(current_dir, initial_config_path)

    if not os.path.exists(initial_config_path):
        print(f"Error: The initial configuration file was not found: {initial_config_path}")
        print("Please ensure the --country name matches a .json file (e.g., 'slovakia' for 'slovakia.json') or --json_file points to a valid file.")
        sys.exit(1)


    if args.operation_string:
        asyncio.run(main_loop(args.operation_string, initial_config_path))
    else:
        # Interactive mode uses the determined initial_config_path
        print(f"Starting interactive mode. Initial country configuration: {os.path.basename(initial_config_path)}")
        asyncio.run(interactive_main(initial_config_path))
