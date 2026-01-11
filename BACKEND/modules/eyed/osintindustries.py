import os
import requests
import json
import argparse
import re
import time
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field # Use field for default_factory
from dotenv import load_dotenv
import datetime
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# API Key (Fallback - kept as requested for testing)
OSINT_API_KEY = '518cf12a370e9e42dde7516098621889'

# Country codes dictionary for phone number formatting helper
COUNTRY_CODES = {
    "united states": "1", "us": "1", "usa": "1",
    "canada": "1", "ca": "1",
    "united kingdom": "44", "uk": "44", "gb": "44",
    "australia": "61", "au": "61",
    "india": "91", "in": "91",
    "germany": "49", "de": "49",
    "france": "33", "fr": "33",
    "italy": "39", "it": "39",
    "spain": "34", "es": "34",
    "brazil": "55", "br": "55",
    "mexico": "52", "mx": "52",
    "china": "86", "cn": "86",
    "japan": "81", "jp": "81",
    "south korea": "82", "kr": "82",
    "russia": "7", "ru": "7",
    "south africa": "27", "za": "27",
    "nigeria": "234", "ng": "234",
    "egypt": "20", "eg": "20",
    "saudi arabia": "966", "sa": "966",
    "uae": "971", "ae": "971",
    "singapore": "65", "sg": "65",
    "malaysia": "60", "my": "60",
    "indonesia": "62", "id": "62",
    "thailand": "66", "th": "66",
    "vietnam": "84", "vn": "84",
    "philippines": "63", "ph": "63",
    "new zealand": "64", "nz": "64"
}

@dataclass
class OSINTSocialProfile:
    """Represents a social profile found"""
    platform: str
    url: Optional[str] = None
    username: Optional[str] = None
    categories: List[str] = field(default_factory=list)

@dataclass
class OSINTBreachInfo:
     """Represents information about a data breach"""
     name: Optional[str] = None # Breach name/title
     domain: Optional[str] = None
     breach_date: Optional[str] = None
     pwn_count: Optional[int] = None
     data_classes: List[str] = field(default_factory=list)
     description: Optional[str] = None


@dataclass
class OSINTResult:
    """Class for storing processed OSINT search results"""
    module: str # Source module name
    raw_data: Dict # Keep raw module data for reference
    # --- Fields derived from Spec Format ---
    registered: Optional[bool] = None
    breached: Optional[bool] = None # If module relates to breaches
    id_str: Optional[str] = None # String IDs
    id_int: Optional[int] = None # Integer IDs
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    picture_url: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None # Often string range
    language: Optional[str] = None
    location: Optional[str] = None
    username: Optional[str] = None
    profile_url: Optional[str] = None
    banner_url: Optional[str] = None
    email: Optional[str] = None # Primary email found
    phone: Optional[str] = None # Primary phone found
    email_hint: Optional[str] = None
    phone_hint: Optional[str] = None
    website: Optional[str] = None
    bio: Optional[str] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    verified: Optional[bool] = None
    premium: Optional[bool] = None
    private: Optional[bool] = None
    last_seen: Optional[str] = None
    creation_date: Optional[str] = None
    platform_variables: Dict[str, Any] = field(default_factory=dict) # Store extra platform vars
    # --- Aggregated/Derived Fields ---
    social_profiles: List[OSINTSocialProfile] = field(default_factory=list)
    breach_info: List[OSINTBreachInfo] = field(default_factory=list)
    category: Optional[str] = None # Category of the module

class OSINTIndustriesClient:
    """Client for the OSINT Industries API v2"""

    def __init__(self, api_key: Optional[str] = None, max_retries: int = 2):
        """Initialize the OSINT Industries API client

        Args:
            api_key: Your OSINT Industries API key. If None, reads from OSINT_API_KEY env var or uses hardcoded fallback.
            max_retries: Max retries on rate limit errors (429).
        """
        self.api_key = api_key or os.getenv('OSINT_API_KEY') or OSINT_API_KEY
        if not self.api_key:
            raise ValueError("API key is required. Either pass it directly or set OSINT_API_KEY environment variable.")
        if self.api_key == OSINT_API_KEY:
             logging.warning("Using hardcoded fallback API key for OSINT Industries. Ensure this is intended for testing.")

        self.base_url = "https://api.osint.industries"
        # Documented v2 endpoints
        self.request_endpoint = "/v2/request"
        self.credits_endpoint = "/misc/credits"
        # Undocumented stream endpoint removed
        # self.stream_endpoint = "/v2/request/stream"

        self.headers = {
            "api-key": self.api_key,
            "Accept": "application/json", # Default, can be overridden for PDF
            "Content-Type": "application/json" # Only needed for POST, but harmless for GET
        }
        self.max_retries = max_retries
        self._last_raw_response = None # Store raw response
        self._last_search_type = None # Store type for error context
        logging.info(f"OSINTIndustriesClient initialized. API Key starts with: {self.api_key[:5]}...")

    # --- Internal Request Helper ---
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, json_data: Optional[Dict] = None, headers: Optional[Dict] = None) -> requests.Response:
         """Internal helper to make requests with rate limit handling and error checking."""
         url = f"{self.base_url}{endpoint}"
         request_headers = self.headers.copy()
         if headers: # Allow overriding headers (e.g., for PDF)
             request_headers.update(headers)

         retries = 0
         while retries <= self.max_retries:
             try:
                 response = requests.request(
                     method,
                     url,
                     headers=request_headers,
                     params=params,
                     json=json_data,
                     timeout=max(65, params.get("timeout", 0) + 5) if params else 65 # Set request timeout slightly longer than API timeout
                 )

                 # Handle Rate Limiting (429)
                 if response.status_code == 429:
                     # Docs don't specify Retry-After, use fixed/incremental backoff
                     wait_time = 3 * (retries + 1) # Simple incremental backoff
                     if retries < self.max_retries:
                         logging.warning(f"Rate limit hit (429) on {endpoint}. Retrying after {wait_time} seconds... (Attempt {retries + 1}/{self.max_retries})")
                         time.sleep(wait_time)
                         retries += 1
                         continue # Retry
                     else:
                         logging.error(f"Rate limit hit (429) on {endpoint}. Max retries ({self.max_retries}) exceeded.")
                         response.raise_for_status() # Raise the 429 error

                 # Handle Auth Errors (401)
                 elif response.status_code == 401:
                     logging.error(f"Unauthorized (401) on {endpoint}. Check API Key and credits.")
                     response.raise_for_status() # Raise error, don't retry

                 # Handle Bad Request (400) - Let caller handle specifics
                 elif response.status_code == 400:
                     logging.warning(f"Bad request (400) on {endpoint}. Response: {response.text}")
                     # Raise or return depending on if caller wants to inspect
                     response.raise_for_status() # Or return response

                 # Handle Not Found (404) - Often just means no data, return response
                 elif response.status_code == 404:
                     logging.info(f"Resource not found (404) on {endpoint}.")
                     return response

                 # Raise other 4xx/5xx errors (including 500 API Error)
                 response.raise_for_status()
                 return response

             except requests.exceptions.Timeout:
                 logging.error(f"Request timed out for {method} {endpoint}")
                 # Optionally retry on timeout? For now, raise.
                 raise
             except requests.exceptions.RequestException as e:
                 logging.error(f"Request failed for {method} {endpoint}: {e}")
                 raise # Re-raise after logging

         # Should only be reached if loop finishes without returning/raising
         raise requests.exceptions.RetryError(f"Max retries ({self.max_retries}) exceeded for request to {url}")


    # --- Public API Methods ---

    def search(self, search_type: str, query: str, timeout: int = 30) -> List[OSINTResult]:
        """
        Perform a search using the OSINT Industries API.
        Based on documentation, only 'email' and 'phone' types are supported for /v2/request.

        Args:
            search_type: The type of search ('email' or 'phone').
            query: The search query (the email address or phone number).
            timeout: Maximum time in seconds for the API to run modules (1-60).

        Returns:
            List of OSINTResult objects containing the processed search results.
            Returns empty list on error or if no results found.
        """
        self._last_search_type = search_type # For error context
        self._last_raw_response = None # Reset raw response

        # Validate search type based on documentation
        if search_type not in ["email", "phone"]:
            logging.error(f"Unsupported search type '{search_type}'. API v2 docs only specify 'email' or 'phone'.")
            # Optionally raise ValueError("Unsupported search type")
            return []

        # Ensure timeout is within valid range
        timeout = max(1, min(timeout, 60))

        params = {
            "type": search_type,
            "query": query,
            "timeout": timeout
        }
        logging.info(f"Performing OSINT search: type='{search_type}', query='{query[:15]}...', timeout={timeout}s")

        try:
            response = self._make_request("GET", self.request_endpoint, params=params)

            # Check for non-JSON response or errors handled by _make_request returning response
            if not response.ok: # Includes 404 Not Found or other errors not raised
                 # Error/Not Found already logged by _make_request or _handle_error_response
                 # Specific handling for 400 if needed
                 if response.status_code == 400 and search_type == "phone":
                      logging.error("Invalid query format for phone number search.")
                      # Optional: Call interactive handler or just return empty
                      # self._handle_phone_number_error() # Removed interactive part from client library method
                 return []

            # Process successful JSON response
            try:
                data = response.json()
                self._last_raw_response = data # Store raw response
                return self._process_api_response(data)
            except json.JSONDecodeError:
                 logging.error("Failed to decode JSON response from API.")
                 return []

        except requests.exceptions.RequestException as e:
             # Error already logged by _make_request
             return [] # Return empty list on request failure
        except Exception as e:
            logging.error(f"Unexpected error during search: {e}", exc_info=True)
            return []

    def search_phone(self, phone: str, timeout: int = 30) -> List[OSINTResult]:
        """
        Search by phone number (wrapper for search('phone', ...))
        
        Args:
            phone: The phone number to search.
            timeout: API timeout in seconds.
            
        Returns:
            List of OSINTResult objects.
        """
        return self.search("phone", phone, timeout)

    def search_email(self, email: str, timeout: int = 30) -> List[OSINTResult]:
        """
        Search by email address (wrapper for search('email', ...))
        
        Args:
            email: The email address to search.
            timeout: API timeout in seconds.
            
        Returns:
            List of OSINTResult objects.
        """
        return self.search("email", email, timeout)

    def get_credits(self) -> Optional[int]:
        """Get the number of remaining API credits."""
        logging.info("Fetching API credits...")
        try:
            response = self._make_request("GET", self.credits_endpoint)
            if not response.ok: # Handle potential 404 or other errors
                 return None
            data = response.json()
            credits = data.get('credits')
            if isinstance(credits, int):
                 logging.info(f"Credits remaining: {credits}")
                 return credits
            else:
                 logging.warning(f"Unexpected format for credits response: {data}")
                 return None
        except requests.exceptions.RequestException as e:
            # Error logged by _make_request
            return None
        except json.JSONDecodeError:
             logging.error("Failed to decode JSON response from credits endpoint.")
             return None
        except Exception as e:
             logging.error(f"Unexpected error fetching credits: {e}", exc_info=True)
             return None

    def get_pdf_report(self, search_type: str, query: str, timeout: int = 30, output_filename: Optional[str] = None) -> Optional[str]:
        """
        Request a PDF report for an email or phone search.

        Args:
            search_type: 'email' or 'phone'.
            query: The email or phone number.
            timeout: API timeout (1-60 seconds).
            output_filename: Path to save the PDF file. If None, defaults to
                             'osint_report_{type}_{query}_{timestamp}.pdf'.

        Returns:
            The filename the PDF was saved to, or None if an error occurred.
        """
        self._last_search_type = search_type
        if search_type not in ["email", "phone"]:
            logging.error("PDF reports only supported for 'email' or 'phone' types.")
            return None

        timeout = max(1, min(timeout, 60))
        params = {"type": search_type, "query": query, "timeout": timeout}
        pdf_headers = {"Accept": "application/pdf"}

        if not output_filename:
             safe_query = re.sub(r'[^\w\-_. ]', '_', query).strip().replace(" ", "_")
             timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
             output_filename = f"osint_report_{search_type}_{safe_query}_{timestamp}.pdf"

        logging.info(f"Requesting PDF report: type='{search_type}', query='{query[:15]}...'. Saving to '{output_filename}'")

        try:
            # Use stream=True to handle potentially large file downloads
            response = self._make_request("GET", self.request_endpoint, params=params, headers=pdf_headers)

            if not response.ok:
                 logging.error(f"PDF request failed with status {response.status_code}")
                 return None

            # Check content type to be sure
            content_type = response.headers.get('content-type', '').lower()
            if 'application/pdf' not in content_type:
                 logging.error(f"Expected PDF response, but got content type: {content_type}")
                 # Try to read error message if it's text/json
                 try:
                      logging.error(f"Error response text: {response.text}")
                 except Exception as e:
                     print(f"[EYE-D] Error: {e}")
                     pass
                 return None

            # Save the PDF stream to file
            try:
                with open(output_filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk: # filter out keep-alive new chunks
                             f.write(chunk)
                logging.info(f"PDF report saved successfully to '{output_filename}'")
                return output_filename
            except IOError as e:
                 logging.error(f"Failed to save PDF file '{output_filename}': {e}")
                 return None

        except requests.exceptions.RequestException as e:
            # Error logged by _make_request
            return None
        except Exception as e:
             logging.error(f"Unexpected error getting PDF report: {e}", exc_info=True)
             return None

    # --- Response Processing ---
    def _process_api_response(self, api_response: Union[Dict, List]) -> List[OSINTResult]:
        """Process the main API JSON response (/v2/request)"""
        results = []
        data_list = None

        # Handle both dict and list responses
        if isinstance(api_response, dict) and 'data' in api_response:
            # Expected format: {'data': [...]}
            data_list = api_response.get('data')
        elif isinstance(api_response, list):
            # Handle case where response is directly the list of results
            logging.warning("API response was a direct list, not a dictionary containing 'data'. Processing list items.")
            data_list = api_response
        else:
            logging.warning(f"API response missing 'data' list or has unexpected format: {type(api_response)}")
            return results # Return empty list if format is wrong

        # Ensure data_list is actually a list before proceeding
        if not isinstance(data_list, list):
             logging.warning(f"Expected 'data' to be a list, but got: {type(data_list)}")
             return results

        logging.info(f"Processing {len(data_list)} items from API response.")
        for item_data in data_list:
            if isinstance(item_data, dict):
                result = self._process_single_result(item_data)
                if result:
                    results.append(result)
            else:
                 logging.warning(f"Skipping non-dict item in response data: {type(item_data)}")
        return results

    def _extract_spec_field(self, spec_list: Optional[List[Dict]], field_name: str) -> Optional[Any]:
        """Safely extract a field's 'value' from the spec_format list."""
        if not spec_list or not isinstance(spec_list, list):
            return None
        for item in spec_list:
            if isinstance(item, dict) and field_name in item:
                field_data = item[field_name]
                if isinstance(field_data, dict) and 'value' in field_data:
                    return field_data['value']
                # Sometimes value might be directly under the key if schema is inconsistent
                # logging.warning(f"Spec field '{field_name}' found but missing 'value' key: {field_data}")
                # return field_data # Optionally return direct value if 'value' missing
        return None

    def _process_single_result(self, item_data: Dict) -> Optional[OSINTResult]:
        """Process one item from the 'data' list in the API response."""
        try:
            module_name = item_data.get('module', 'unknown')
            category_info = item_data.get('category', {})
            category_name = category_info.get('name', 'Uncategorized')
            spec_format_list = item_data.get('spec_format') # Expecting a list based on docs

            # --- Extract fields using Spec Format primarily ---
            result = OSINTResult(
                module=module_name,
                raw_data=item_data, # Store raw data for reference
                category=category_name,
                # --- Direct Spec Fields ---
                registered=self._extract_spec_field(spec_format_list, 'registered'),
                breached=self._extract_spec_field(spec_format_list, 'breach'), # Mapped 'breach' key
                id_str=self._extract_spec_field(spec_format_list, 'idString'),
                id_int=self._extract_spec_field(spec_format_list, 'idInt'),
                name=self._extract_spec_field(spec_format_list, 'name'),
                first_name=self._extract_spec_field(spec_format_list, 'first_name'),
                last_name=self._extract_spec_field(spec_format_list, 'last_name'),
                picture_url=self._extract_spec_field(spec_format_list, 'picture_url'),
                gender=self._extract_spec_field(spec_format_list, 'gender'),
                age=self._extract_spec_field(spec_format_list, 'age'),
                language=self._extract_spec_field(spec_format_list, 'language'),
                location=self._extract_spec_field(spec_format_list, 'location'),
                username=self._extract_spec_field(spec_format_list, 'username'),
                profile_url=self._extract_spec_field(spec_format_list, 'profile_url'),
                banner_url=self._extract_spec_field(spec_format_list, 'banner_url'),
                email=self._extract_spec_field(spec_format_list, 'email'),
                phone=self._extract_spec_field(spec_format_list, 'phone'),
                email_hint=self._extract_spec_field(spec_format_list, 'email_hint'),
                phone_hint=self._extract_spec_field(spec_format_list, 'phone_hint'),
                website=self._extract_spec_field(spec_format_list, 'website'),
                bio=self._extract_spec_field(spec_format_list, 'bio'),
                followers=self._extract_spec_field(spec_format_list, 'followers'),
                following=self._extract_spec_field(spec_format_list, 'following'),
                verified=self._extract_spec_field(spec_format_list, 'verified'),
                premium=self._extract_spec_field(spec_format_list, 'premium'),
                private=self._extract_spec_field(spec_format_list, 'private'),
                last_seen=self._extract_spec_field(spec_format_list, 'last_seen'),
                creation_date=self._extract_spec_field(spec_format_list, 'creation_date'),
                platform_variables=self._extract_platform_vars(spec_format_list)
            )

            # --- Fallback Extraction (if key fields are missing from spec) ---
            raw_module_data = item_data.get('data')
            if not result.name and result.first_name and result.last_name:
                 result.name = f"{result.first_name} {result.last_name}"
            # Add more fallback logic here if needed, checking raw_module_data or front_schemas
            # Example: if not result.email: result.email = raw_module_data.get('email') ... etc.


            # --- Process Specific Structures ---
            result.social_profiles = self._extract_social_profiles(item_data)
            result.breach_info = self._extract_breach_info(item_data)


            # Basic check if the result has any useful info extracted
            if any([result.name, result.email, result.phone, result.username, result.profile_url, result.location, result.breach_info]):
                 return result
            else:
                 # Optionally log modules that returned no useful structured data
                 # logging.debug(f"Module '{module_name}' returned no standard fields.")
                 # Return even if empty, caller might want raw_data
                 return result
                 # return None # If we only want results with data


        except Exception as e:
            logging.error(f"Error processing single result from module '{item_data.get('module', 'unknown')}': {e}", exc_info=True)
            return None

    def _extract_platform_vars(self, spec_list: Optional[List[Dict]]) -> Dict[str, Any]:
        """Extract platform variables from the spec_format list."""
        vars_dict = {}
        if not spec_list or not isinstance(spec_list, list):
            return vars_dict
        for item in spec_list:
            if isinstance(item, dict) and 'platform_variables' in item:
                platform_vars_list = item['platform_variables']
                if isinstance(platform_vars_list, list):
                    for var_item in platform_vars_list:
                         if isinstance(var_item, dict) and 'key' in var_item and 'value' in var_item:
                              vars_dict[var_item['key']] = var_item['value']
                         elif isinstance(var_item, dict) and 'proper_key' in var_item and 'value' in var_item:
                              # Use proper_key if key is missing (based on schema example)
                              vars_dict[var_item['proper_key']] = var_item['value']

        return vars_dict

    def _extract_social_profiles(self, item_data: Dict) -> List[OSINTSocialProfile]:
        """Extract social profile information, often from front_schemas."""
        profiles = []
        # Check spec_format first for profile_url/username
        spec_list = item_data.get('spec_format')
        main_profile_url = self._extract_spec_field(spec_list, 'profile_url')
        main_username = self._extract_spec_field(spec_list, 'username')

        if main_profile_url or main_username:
             profiles.append(OSINTSocialProfile(
                  platform=item_data.get('module', 'unknown'),
                  url=main_profile_url,
                  username=main_username
             ))

        # Also check front_schemas for potentially richer/additional profiles
        front_schemas = item_data.get('front_schemas', [])
        if isinstance(front_schemas, list):
            for schema in front_schemas:
                 if isinstance(schema, dict):
                      platform = schema.get('module', item_data.get('module', 'unknown')) # Use schema module if available
                      url = None
                      username = None
                      tags = []

                      # Look for URLs in body or tags
                      if isinstance(schema.get('body'), dict):
                           body = schema['body']
                           for key, value in body.items():
                                if isinstance(value, str):
                                     if 'url' in key.lower() or 'link' in key.lower(): url = value
                                     if 'user' in key.lower() or 'handle' in key.lower(): username = value

                      if isinstance(schema.get('tags'), list):
                            for tag_info in schema['tags']:
                                 if isinstance(tag_info, dict):
                                      if tag_info.get('tag'): tags.append(tag_info['tag'])
                                      # Overwrite url/username if found in tag and more specific
                                      if tag_info.get('url') and not url: url = tag_info['url']


                      # Avoid adding duplicate of main profile if info is identical
                      is_duplicate = False
                      for p in profiles:
                           if p.platform == platform and p.url == url and p.username == username:
                                p.categories.extend(tags) # Add tags to existing
                                p.categories = sorted(list(set(p.categories)))
                                is_duplicate = True
                                break
                      if not is_duplicate and (url or username):
                            profiles.append(OSINTSocialProfile(platform=platform, url=url, username=username, categories=sorted(list(set(tags)))))

        return profiles

    def _extract_breach_info(self, item_data: Dict) -> List[OSINTBreachInfo]:
        """Extract breach details, typically from HIBP module data."""
        breaches = []
        # Check if this module is breach-related first
        is_breach_module = 'breach' in item_data.get('module', '').lower() or 'hibp' in item_data.get('module', '').lower()
        spec_breached = self._extract_spec_field(item_data.get('spec_format'), 'breach')

        if not is_breach_module and not spec_breached:
             return breaches # Not a breach module/result

        raw_module_data = item_data.get('data')
        if isinstance(raw_module_data, list):
             for breach_item in raw_module_data:
                  if isinstance(breach_item, dict):
                       breaches.append(OSINTBreachInfo(
                           name=breach_item.get('Name') or breach_item.get('Title'),
                           domain=breach_item.get('Domain'),
                           breach_date=breach_item.get('BreachDate'),
                           pwn_count=breach_item.get('PwnCount'),
                           data_classes=breach_item.get('DataClasses', []),
                           description=breach_item.get('Description')
                       ))
        return breaches


    # --- Getters for Internal State ---
    def get_last_raw_response(self) -> Optional[Any]:
        """Get the raw JSON response from the last successful API call."""
        return self._last_raw_response

    # --- Deprecated / Unsupported Methods Placeholder ---
    # Add placeholders or remove methods not supported by documented API v2
    def search_name(self, name: str, **kwargs):
        logging.error("Search by name is not directly supported by the documented /v2/request endpoint type parameter. Use email or phone search.")
        return []
    def search_wallet(self, wallet: str, **kwargs):
        logging.error("Search by wallet is not directly supported by the documented /v2/request endpoint type parameter. Use email or phone search.")
        return []
    def search_social_handle(self, handle: str, **kwargs):
        logging.error("Search by username/handle is not directly supported by the documented /v2/request endpoint type parameter. Use email or phone search.")
        return []
    def search_linkedin(self, linkedin_url: str, **kwargs):
        logging.error("Search by LinkedIn URL is not directly supported by the documented /v2/request endpoint type parameter. Use email or phone search.")
        return []


# --- CLI and Helper Functions ---

def display_results(results: List[OSINTResult]):
    """Display processed OSINT results"""
    if not results:
        print("\nNo results to display.")
        return

    print(f"\n--- Found {len(results)} Total Results ---")
    unique_modules = sorted(list(set(r.module for r in results)))
    print(f"Sources ({len(unique_modules)}): {', '.join(unique_modules)}")

    # Group results by primary identifier (email/phone/username/name) if available
    # For simplicity, just iterate and print details
    for i, result in enumerate(results):
        print("\n" + "="*20 + f" Result {i+1} (Source: {result.module} | Category: {result.category}) " + "="*20)

        if result.name: print(f"Name: {result.name}")
        if result.first_name: print(f"First Name: {result.first_name}")
        if result.last_name: print(f"Last Name: {result.last_name}")
        if result.email: print(f"Email: {result.email}")
        if result.phone: print(f"Phone: {result.phone}")
        if result.username: print(f"Username: {result.username}")
        if result.location: print(f"Location: {result.location}")
        if result.profile_url: print(f"Profile URL: {result.profile_url}")
        if result.website: print(f"Website: {result.website}")
        if result.bio: print(f"Bio/Description: {result.bio}")
        if result.picture_url: print(f"Picture URL: {result.picture_url}")
        if result.gender: print(f"Gender: {result.gender}")
        if result.age: print(f"Age: {result.age}")
        if result.language: print(f"Language: {result.language}")
        if result.followers is not None: print(f"Followers: {result.followers}")
        if result.following is not None: print(f"Following: {result.following}")
        if result.verified is not None: print(f"Verified: {result.verified}")
        if result.premium is not None: print(f"Premium: {result.premium}")
        if result.private is not None: print(f"Private: {result.private}")
        if result.last_seen: print(f"Last Seen: {result.last_seen}")
        if result.creation_date: print(f"Creation Date: {result.creation_date}")
        if result.id_str: print(f"ID (String): {result.id_str}")
        if result.id_int is not None: print(f"ID (Int): {result.id_int}")
        if result.registered is not None: print(f"Registered: {result.registered}")

        if result.social_profiles:
            print("\nAssociated Profiles:")
            for profile in result.social_profiles:
                 cat_str = f" [{', '.join(profile.categories)}]" if profile.categories else ""
                 print(f"  - Platform: {profile.platform}{cat_str}")
                 if profile.username: print(f"    Username: {profile.username}")
                 if profile.url: print(f"    URL: {profile.url}")

        if result.breach_info:
             print("\nBreach Information:")
             if result.breached: print(f"  * Profile Flagged as Breached *")
             for breach in result.breach_info:
                  print(f"  - Breach Name: {breach.name or 'N/A'}")
                  if breach.domain: print(f"    Domain: {breach.domain}")
                  if breach.breach_date: print(f"    Date: {breach.breach_date}")
                  if breach.pwn_count is not None: print(f"    Pwn Count: {breach.pwn_count:,}")
                  if breach.data_classes: print(f"    Data Classes: {', '.join(breach.data_classes)}")
                  # if breach.description: print(f"    Description: {breach.description}") # Often redundant

        if result.platform_variables:
             print("\nPlatform Variables:")
             for key, value in result.platform_variables.items():
                  # Simple display, can be enhanced
                  print(f"  - {key}: {value}")

    print("="*70)


def save_results_to_file(results: List[OSINTResult], query: str, search_type: str, filename: str, format: str, include_raw: bool = False):
    """Saves results to a file in JSON or TXT format."""
    if not results:
        logging.warning("No results to save.")
        return

    logging.info(f"Saving {len(results)} results to '{filename}' in {format} format...")
    try:
        if format == 'json':
            # Save processed data or raw data based on flag
            data_to_save = []
            for r in results:
                 if include_raw:
                      data_to_save.append(r.raw_data)
                 else:
                      # Convert dataclass to dict for saving
                      # Need a robust way to handle nested dataclasses if not using raw
                      # For simplicity now, let's save raw if JSON format chosen
                      data_to_save.append(r.raw_data)
                      # Or implement a recursive dataclass to dict converter if needed

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, default=str)

        else: # TXT format
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"OSINT Industries Search Results\n")
                f.write(f"Query: {query}\n")
                f.write(f"Type: {search_type}\n")
                f.write(f"Date: {datetime.datetime.now().isoformat()}\n")
                f.write(f"Total Results: {len(results)}\n")
                unique_modules = sorted(list(set(r.module for r in results)))
                f.write(f"Sources ({len(unique_modules)}): {', '.join(unique_modules)}\n")
                f.write("="*70 + "\n")

                for i, result in enumerate(results):
                    f.write("\n" + "="*20 + f" Result {i+1} (Source: {result.module} | Category: {result.category}) " + "="*20 + "\n")
                    if result.name: f.write(f"Name: {result.name}\n")
                    if result.first_name: f.write(f"First Name: {result.first_name}\n")
                    if result.last_name: f.write(f"Last Name: {result.last_name}\n")
                    if result.email: f.write(f"Email: {result.email}\n")
                    if result.phone: f.write(f"Phone: {result.phone}\n")
                    if result.username: f.write(f"Username: {result.username}\n")
                    if result.location: f.write(f"Location: {result.location}\n")
                    if result.profile_url: f.write(f"Profile URL: {result.profile_url}\n")
                    if result.website: f.write(f"Website: {result.website}\n")
                    if result.bio: f.write(f"Bio/Description: {result.bio}\n")
                    if result.picture_url: f.write(f"Picture URL: {result.picture_url}\n")
                    if result.gender: f.write(f"Gender: {result.gender}\n")
                    if result.age: f.write(f"Age: {result.age}\n")
                    if result.language: f.write(f"Language: {result.language}\n")
                    if result.followers is not None: f.write(f"Followers: {result.followers}\n")
                    if result.following is not None: f.write(f"Following: {result.following}\n")
                    if result.verified is not None: f.write(f"Verified: {result.verified}\n")
                    if result.premium is not None: f.write(f"Premium: {result.premium}\n")
                    if result.private is not None: f.write(f"Private: {result.private}\n")
                    if result.last_seen: f.write(f"Last Seen: {result.last_seen}\n")
                    if result.creation_date: f.write(f"Creation Date: {result.creation_date}\n")
                    if result.id_str: f.write(f"ID (String): {result.id_str}\n")
                    if result.id_int is not None: f.write(f"ID (Int): {result.id_int}\n")
                    if result.registered is not None: f.write(f"Registered: {result.registered}\n")

                    if result.social_profiles:
                        f.write("\nAssociated Profiles:\n")
                        for profile in result.social_profiles:
                             cat_str = f" [{', '.join(profile.categories)}]" if profile.categories else ""
                             f.write(f"  - Platform: {profile.platform}{cat_str}\n")
                             if profile.username: f.write(f"    Username: {profile.username}\n")
                             if profile.url: f.write(f"    URL: {profile.url}\n")

                    if result.breach_info:
                         f.write("\nBreach Information:\n")
                         if result.breached: f.write(f"  * Profile Flagged as Breached *\n")
                         for breach in result.breach_info:
                              f.write(f"  - Breach Name: {breach.name or 'N/A'}\n")
                              if breach.domain: f.write(f"    Domain: {breach.domain}\n")
                              if breach.breach_date: f.write(f"    Date: {breach.breach_date}\n")
                              if breach.pwn_count is not None: f.write(f"    Pwn Count: {breach.pwn_count:,}\n")
                              if breach.data_classes: f.write(f"    Data Classes: {', '.join(breach.data_classes)}\n")

                    if result.platform_variables:
                         f.write("\nPlatform Variables:\n")
                         for key, value in result.platform_variables.items():
                              f.write(f"  - {key}: {value}\n")

                    f.write("\n" + "-"*70 + "\n") # Separator

        logging.info(f"Results successfully saved to '{filename}'.")

    except IOError as e:
         logging.error(f"Failed to write results to file '{filename}': {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during file saving: {e}", exc_info=True)


def main():
    """Main function for command-line usage"""
    load_dotenv()
    logging.info("Starting OSINT Industries CLI Tool v2")

    parser = argparse.ArgumentParser(description='OSINT Industries API v2 Client')
    parser.add_argument('--api-key', '-k', help='OSINT Industries API key (overrides environment variable)')
    parser.add_argument('query', nargs='?', help='Search query (email or phone number)') # Make query optional for credits check
    parser.add_argument('--type', '-t', choices=['email', 'phone'], help='Specify the search type (email or phone)')
    parser.add_argument('--timeout', '-to', type=int, default=30, help='API timeout in seconds (1-60)')
    parser.add_argument('--output', '-o', help='Save results to this file (e.g., results.json or results.txt)')
    parser.add_argument('--format', '-f', choices=['json', 'txt'], default='txt', help='Output file format (default: txt)')
    parser.add_argument('--raw', '-r', action='store_true', help='Include raw API JSON data in the output file (only for json format)')
    parser.add_argument('--pdf', '-p', action='store_true', help='Request and save a PDF report instead of JSON/TXT')
    parser.add_argument('--check-credits', '-c', action='store_true', help='Only check API credits and exit')
    args = parser.parse_args()

    try:
        # Use command line API key first, then env var, then fallback
        api_key = args.api_key or os.getenv('OSINT_API_KEY') or OSINT_API_KEY
        client = OSINTIndustriesClient(api_key=api_key)
    except ValueError as e:
        print(f"Error: {e}")
        print("\nProvide API key via --api-key argument or OSINT_API_KEY environment variable.")
        return

    # --- Check Credits ---
    if args.check_credits:
         credits = client.get_credits()
         if credits is not None:
              print(f"\nRemaining API Credits: {credits}")
         else:
              print("\nFailed to retrieve credit balance.")
         return # Exit after checking credits

    # --- Perform Search ---
    if not args.query:
        # If no query provided and not checking credits, prompt the user
        args.query = input("Enter the search query (email or phone number): ")
        if not args.query:
             print("Error: Search query cannot be empty.")
             return

    # Determine search type
    search_type = args.type
    if not search_type:
        # Basic auto-detection for email/phone
        if '@' in args.query and '.' in args.query.split('@')[-1]:
            search_type = 'email'
        elif re.match(r'^\+?[\d\s\-\(\).]{7,}$', args.query):
             search_type = 'phone'
        else:
             print(f"Error: Could not auto-detect type for query '{args.query}'. Use --type email or --type phone.")
             return
    logging.info(f"Determined search type: {search_type}")


    # Handle PDF request
    if args.pdf:
         if search_type not in ['email', 'phone']:
              print("Error: PDF reports are only supported for email and phone searches.")
              return
         output_filename = args.output # Use specified output or default in function
         saved_pdf = client.get_pdf_report(search_type, args.query, args.timeout, output_filename)
         if saved_pdf:
              print(f"\nPDF report saved to: {saved_pdf}")
         else:
              print("\nFailed to generate or save PDF report.")
         return # Exit after PDF attempt

    # Perform standard JSON search
    results = client.search(search_type, args.query, args.timeout)

    # Display results
    display_results(results)

    # Save results if requested and results exist
    if args.output and results:
        save_results_to_file(results, args.query, search_type, args.output, args.format, args.raw)
    elif args.output:
         print("\nNo results to save.")


if __name__ == "__main__":
    main()