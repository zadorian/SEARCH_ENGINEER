#!/usr/bin/env python3
"""
Enhanced script to query OSINT Industries API and parse JSON data, extracting ALL available fields with source tracking and formatting them 
neatly.
Supports both API queries (input) and comprehensive data extraction 
(output).
Outputs both JSON and formatted text files.
"""

import json
import sys
import os
import re
import requests
import time
import hashlib
from collections import defaultdict
from typing import Dict, List, Set, Optional, Any

# Try to import OSINT Industries client if available
try:
    try:
        from .osintindustries import OSINTIndustriesClient
    except ImportError:
        from osintindustries import OSINTIndustriesClient
    HAS_OSINT_CLIENT = True
except ImportError:
    HAS_OSINT_CLIENT = False
    # Fallback: simple API client
    OSINT_API_KEY = os.getenv('OSINT_API_KEY', '')

def query_osint_api(query: str, query_type: str = 'email', api_key: 
Optional[str] = None) -> Optional[Dict]:
    """Query OSINT Industries API directly
    
    Args:
        query: The search query (email, phone, username, etc.)
        query_type: Type of query ('email', 'phone', 'username', etc.)
        api_key: API key (if None, uses env var or existing client)
    
    Returns:
        JSON response as dict, or None if error
    """
    if HAS_OSINT_CLIENT:
        try:
            client = OSINTIndustriesClient(api_key=api_key)
            if query_type == 'email':
                result = client.search_email(query)
            elif query_type == 'phone':
                result = client.search_phone(query)
            elif query_type == 'username' or query_type == 'name':
                result = client.search(query_type, query)
            else:
                result = client.search(query_type, query)  # Generic search
            return result
        except Exception as e:
            print(f"Error querying OSINT API with client: {e}")
            return None
    else:
        # Simple direct API call
        api_key = api_key or OSINT_API_KEY
        if not api_key:
            print("Warning: No API key available. Cannot query API directly.")
            return None
        
        url = "https://api.osint.industries/v2/request"
        headers = {
            "api-key": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        payload = {
            "query": query,
            "type": query_type
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=70)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error querying OSINT API: {e}")
            return None

def extract_domain_from_email(email: str) -> Optional[str]:
    """Extract domain from email address"""
    if not email or '@' not in email:
        return None
    try:
        domain = email.split('@')[-1].strip().lower()
        # Basic validation - must have at least one dot and valid characters
        if domain and '.' in domain and len(domain) > 3:
            return domain
    except Exception as e:

        print(f"[EYE-D] Error: {e}")

        pass
    return None

def add_with_source(data_list: List[Dict], value: Any, source: str, validation: Optional[Dict] = None, extract_domain: bool = False, domain_list: Optional[List] = None):
    """Add a value to a list with source tracking, avoiding duplicates
    
    Args:
        data_list: List to add to
        value: Value to add
        source: Source name
        validation: Optional validation/metadata dict to attach
        extract_domain: If True and value is an email, extract domain
        domain_list: List to add extracted domain to (if extract_domain is 
True)
    """
    if not value or value == '':
        return
    value_str = str(value)
    
    # Extract domain from email if requested
    if extract_domain and domain_list is not None and '@' in value_str:
        domain = extract_domain_from_email(value_str)
        if domain:
            # Add domain to domain_list (avoid duplicates)
            domain_exists = False
            for item in domain_list:
                if item['value'] == domain:
                    if source not in item['sources']:
                        item['sources'].append(source)
                    domain_exists = True
                    break
            if not domain_exists:
                domain_list.append({'value': domain, 'sources': [source]})
    
    # Check if this value already exists
    for item in data_list:
        if item['value'] == value_str:
            # Value exists, add source if not already there
            if source not in item['sources']:
                item['sources'].append(source)
            # Merge validation data if provided
            if validation:
                if 'validation' not in item:
                    item['validation'] = {}
                item['validation'].update(validation)
            return
    # New value, add it
    new_item = {'value': value_str, 'sources': [source]}
    if validation:
        new_item['validation'] = validation
    data_list.append(new_item)

def extract_data_from_json(json_file_or_data):
    """Extract ALL relevant data from JSON file or dict with source tracking
    
    Args:
        json_file_or_data: Path to JSON file (str) or dict with JSON data
    
    Returns:
        Dict with all extracted data, where each field is a list of dicts 
with 'value' and 'sources'
    """
    
    # Handle both file path and dict
    if isinstance(json_file_or_data, str):
        with open(json_file_or_data, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = json_file_or_data
    
    # Initialize comprehensive data structures - with source tracking
    # Each field is a list of dicts: [{'value': '...', 'sources': ['RocketReach', 'OSINT Industries']}, ...]
    usernames = []
    emails = []  # Will store: {'value': 'email@example.com', 'sources': [...], 'validation': {...}}
    phones = []  # Will store: {'value': '+1234567890', 'sources': [...], 'validation': {...}}
    linkedin_urls = []
    passwords = []
    registered_domains = []
    breach_domains = []
    account_urls = []
    platform_associations = []
    names = []
    first_names = []
    last_names = []
    locations = []
    bios = []
    job_titles = []
    companies = []
    schools = []
    skills = []
    picture_urls = []
    websites = []
    creation_dates = []
    last_seen_dates = []
    birth_years = []
    ages = []
    genders = []
    languages = []
    followers_counts = []
    following_counts = []
    verified_statuses = []
    premium_statuses = []
    private_statuses = []
    email_hints = []
    phone_hints = []
    banner_urls = []
    ip_addresses = []
    addresses = []
    coordinates = []
    job_history_full = []
    education_full = []
    breach_details = []
    platform_ids = []
    registered_dates = []
    platform_variables_data = []
    categories = []
    
    # Extract from rocketreach
    if 'results_by_source' in data and 'rocketreach' in data['results_by_source']:
        rr = data['results_by_source']['rocketreach']
        source = 'RocketReach'
        
        if rr is not None:
            # Names
            if 'name' in rr and rr['name']:
                add_with_source(names, rr['name'], source)
            
            # Profile picture
            if 'profile_pic' in rr and rr['profile_pic']:
                add_with_source(picture_urls, rr['profile_pic'], source)
            
            # LinkedIn URL
            if 'linkedin_url' in rr and rr['linkedin_url']:
                add_with_source(linkedin_urls, rr['linkedin_url'], source)
            if 'links' in rr and 'linkedin' in rr['links']:
                add_with_source(linkedin_urls, rr['links']['linkedin'], source)
            
            # Current employer details
            if 'current_employer_website' in rr and rr['current_employer_website']:
                add_with_source(websites, rr['current_employer_website'], source)
            if 'current_employer_linkedin_url' in rr and rr['current_employer_linkedin_url']:
                add_with_source(linkedin_urls, rr['current_employer_linkedin_url'], source)
            if 'current_employer_domain' in rr and rr['current_employer_domain']:
                add_with_source(registered_domains, rr['current_employer_domain'], source)
            
            # Location
            if 'location' in rr and rr['location']:
                add_with_source(locations, rr['location'], source)
            if 'city' in rr and rr['city']:
                city = rr['city']
                if 'region' in rr and rr['region']:
                    city += f", {rr['region']}"
                if 'country' in rr and rr['country']:
                    city += f", {rr['country']}"
                add_with_source(locations, city, source)
            
            # Current job
            if 'current_title' in rr and rr['current_title']:
                add_with_source(job_titles, rr['current_title'], source)
            if 'current_employer' in rr and rr['current_employer']:
                add_with_source(companies, rr['current_employer'], source)
            
            # Job history
            if 'job_history' in rr:
                for job in rr['job_history']:
                    if 'title' in job and job['title']:
                        add_with_source(job_titles, job['title'], source)
                    if 'company_name' in job and job['company_name']:
                        add_with_source(companies, job['company_name'], source)
            
            # Education
            if 'education' in rr:
                for edu in rr['education']:
                    if 'school' in edu and edu['school']:
                        add_with_source(schools, edu['school'], source)
            
            # Skills
            if 'skills' in rr:
                for skill in rr['skills']:
                    if skill:
                        add_with_source(skills, skill, source)
            
            # Birth year
            if 'birth_year' in rr and rr['birth_year']:
                add_with_source(birth_years, str(rr['birth_year']), source)
            
            # Coordinates
            if 'region_latitude' in rr and 'region_longitude' in rr:
                if rr['region_latitude'] and rr['region_longitude']:
                    coord = f"{rr['region_latitude']}, {rr['region_longitude']}"
                    add_with_source(coordinates, coord, source)
            
            # Emails (with validation info stored with email)
            if 'emails' in rr:
                for email_obj in rr['emails']:
                    if 'email' in email_obj and email_obj['email']:
                        # Build validation dict
                        validation = {}
                        if 'smtp_valid' in email_obj and email_obj['smtp_valid']:
                            validation['smtp_valid'] = email_obj['smtp_valid']
                        if 'type' in email_obj and email_obj['type']:
                            validation['type'] = email_obj['type']
                        if 'grade' in email_obj and email_obj['grade']:
                            validation['grade'] = email_obj['grade']
                        add_with_source(emails, email_obj['email'], source, validation if validation else None, extract_domain=True, domain_list=registered_domains)
            
            # Phones (with validation info stored with phone)
            if 'phones' in rr:
                for phone_obj in rr['phones']:
                    if 'phone' in phone_obj and phone_obj['phone']:
                        # Build validation dict
                        validation = {}
                        if 'type' in phone_obj and phone_obj['type']:
                            validation['type'] = phone_obj['type']
                        if 'validity' in phone_obj and phone_obj['validity']:
                            validation['validity'] = phone_obj['validity']
                        if 'recommended' in phone_obj and phone_obj['recommended']:
                            validation['recommended'] = phone_obj['recommended']
                        add_with_source(phones, phone_obj['phone'], source, validation if validation else None)
            
            # Full job history with dates
            if 'job_history' in rr:
                for job in rr['job_history']:
                    job_entry = {'sources': [source]}
                    if 'title' in job and job['title']:
                        job_entry['title'] = job['title']
                    if 'company_name' in job and job['company_name']:
                        job_entry['company'] = job['company_name']
                    if 'company_id' in job and job['company_id']:
                        platform_ids.append({
                            'value': f"Company ID: {job['company_id']} ({job.get('company_name', 'Unknown')})",
                            'sources': [source]
                        })
                    if 'start_date' in job and job['start_date']:
                        job_entry['start'] = job['start_date']
                    if 'end_date' in job and job['end_date']:
                        job_entry['end'] = job['end_date']
                    if 'is_current' in job:
                        job_entry['current'] = job['is_current']
                    if 'title' in job_entry or 'company' in job_entry:
                        job_history_full.append(job_entry)
            
            # Current employer ID
            if 'current_employer_id' in rr and rr['current_employer_id']:
                platform_ids.append({
                    'value': f"Current Employer ID: {rr['current_employer_id']} ({rr.get('current_employer', 'Unknown')})",
                    'sources': [source]
                })
            
            # Full education with details
            if 'education' in rr:
                for edu in rr['education']:
                    edu_entry = {'sources': [source]}
                    if 'school' in edu and edu['school']:
                        edu_entry['school'] = edu['school']
                    if 'major' in edu and edu['major']:
                        edu_entry['major'] = edu['major']
                    if 'degree' in edu and edu['degree']:
                        edu_entry['degree'] = edu['degree']
                    if 'start' in edu and edu['start']:
                        edu_entry['start'] = str(edu['start'])
                    if 'end' in edu and edu['end']:
                        edu_entry['end'] = str(edu['end'])
                    if 'school' in edu_entry or 'major' in edu_entry or 'degree' in edu_entry:
                        education_full.append(edu_entry)
    
    # Extract from results_by_source.osint_industries
    source = 'OSINT Industries'
    if 'results_by_source' in data and 'osint_industries' in data['results_by_source']:
        results = data['results_by_source']['osint_industries']
    elif 'results' in data:
        results = data['results']
    else:
        results = []
    
    # Extract from results array - ALL fields with source
    if results:
        for result in results:
            # Basic fields
            if result.get('username'):
                add_with_source(usernames, result['username'], source)
            if result.get('email'):
                add_with_source(emails, result['email'], source, extract_domain=True, domain_list=registered_domains)
            if result.get('phone'):
                add_with_source(phones, result['phone'], source)
            if result.get('name'):
                add_with_source(names, result['name'], source)
            if result.get('first_name'):
                add_with_source(first_names, result['first_name'], source)
            if result.get('last_name'):
                add_with_source(last_names, result['last_name'], source)
            if result.get('location'):
                add_with_source(locations, result['location'], source)
            if result.get('bio'):
                add_with_source(bios, result['bio'], source)
            if result.get('website'):
                add_with_source(websites, result['website'], source)
            if result.get('picture_url'):
                add_with_source(picture_urls, result['picture_url'], source)
            if result.get('creation_date'):
                add_with_source(creation_dates, result['creation_date'], source)
            if result.get('last_seen'):
                add_with_source(last_seen_dates, result['last_seen'], source)
            if result.get('gender'):
                add_with_source(genders, result['gender'], source)
            if result.get('age'):
                add_with_source(ages, result['age'], source)
            if result.get('language'):
                add_with_source(languages, result['language'], source)
            if result.get('followers') is not None:
                add_with_source(followers_counts, str(result['followers']), source)
            if result.get('following') is not None:
                add_with_source(following_counts, str(result['following']), source)
            if result.get('verified') is not None:
                add_with_source(verified_statuses, str(result['verified']), source)
            if result.get('premium') is not None:
                add_with_source(premium_statuses, str(result['premium']), source)
            if result.get('private') is not None:
                add_with_source(private_statuses, str(result['private']), source)
            if result.get('email_hint'):
                add_with_source(email_hints, result['email_hint'], source)
            if result.get('phone_hint'):
                add_with_source(phone_hints, result['phone_hint'], source)
            if result.get('banner_url'):
                add_with_source(banner_urls, result['banner_url'], source)
            
            # Profile URL (only if it's a real profile URL with a path)
            if result.get('profile_url'):
                url = result['profile_url']
                if url and (url.startswith('http://') or url.startswith('https://')):
                    cleaned = clean_url(url)
                    if '/' in cleaned and cleaned.count('/') > 0:
                        add_with_source(account_urls, url, source)
            
            # Module/Platform and Category
            module = result.get('module', '')
            if module:
                add_with_source(platform_associations, module, source)
            if result.get('category'):
                add_with_source(categories, result['category'], source)
            
            # Platform IDs
            if result.get('id_str'):
                add_with_source(platform_ids, f"{result['id_str']} (string)", source)
            if result.get('id_int'):
                add_with_source(platform_ids, f"{result['id_int']} (int)", source)
            
            # Platform variables (additional metadata)
            if result.get('platform_variables') and isinstance(result['platform_variables'], dict):
                for key, value in result['platform_variables'].items():
                    if value is not None and value != '':
                        platform_variables_data.append({
                            'value': f"{key}: {value}",
                            'sources': [source]
                        })
            
            # Breach info from results array
            if 'breach_info' in result and result['breach_info']:
                for breach in result['breach_info']:
                    if isinstance(breach, dict):
                        breach_entry = {'sources': [source]}
                        if 'name' in breach and breach['name']:
                            breach_entry['name'] = breach['name']
                        if 'domain' in breach and breach['domain']:
                            breach_entry['domain'] = breach['domain']
                            add_with_source(breach_domains, breach['domain'], source)
                        if 'date' in breach and breach['date']:
                            breach_entry['breach_date'] = breach['date']
                        if 'description' in breach and breach['description']:
                            breach_entry['description'] = breach['description']
                        if breach_entry:
                            breach_details.append(breach_entry)
            
            # Social profiles
            if 'social_profiles' in result:
                for profile in result['social_profiles']:
                    platform = profile.get('platform', '')
                    if platform:
                        add_with_source(platform_associations, platform, source)
                    
                    if 'url' in profile and profile['url']:
                        url = profile['url']
                        if url and (url.startswith('http://') or url.startswith('https://')):
                            cleaned = clean_url(url)
                            if '/' in cleaned and cleaned.count('/') > 0:
                                add_with_source(account_urls, url, source)
                    
                    if 'username' in profile and profile['username']:
                        add_with_source(usernames, profile['username'], source)
            
            # Raw data - extract domains from Whoxy (registered) and HIBP (breached)
            if 'raw_data' in result:
                raw = result['raw_data']
                module_name = raw.get('module', '').lower()
                
                if 'front_schemas' in raw:
                    for schema in raw['front_schemas']:
                        if 'body' in schema:
                            body = schema['body']
                            
                            # Whoxy module = registered domains
                            if module_name == 'whoxy' or schema.get('module', '').lower() == 'whoxy':
                                if 'Domain Name' in body and body['Domain Name']:
                                    domain_val = body['Domain Name']
                                    if domain_val and domain_val.strip():
                                        add_with_source(registered_domains, domain_val, source)
                                if 'Website' in body and body['Website']:
                                    website_val = body['Website']
                                    if website_val and website_val.strip():
                                        website_val = website_val.replace('https://', '').replace('http://', '').rstrip('/')
                                        add_with_source(registered_domains, website_val, source)
                            
                            # HIBP module = breach domains with full details
                            elif module_name == 'hibp' or schema.get('module', '').lower() == 'haveibeenpwnd!':
                                breach_entry = {'sources': [source]}
                                if 'Domain' in body and body['Domain']:
                                    domain_val = body['Domain']
                                    if domain_val and domain_val.strip():
                                        add_with_source(breach_domains, domain_val, source)
                                        breach_entry['domain'] = domain_val
                                if 'Title' in body and body['Title']:
                                    breach_entry['title'] = body['Title']
                                if 'Breach Date' in body and body['Breach Date']:
                                    breach_entry['breach_date'] = body['Breach Date']
                                if 'Added Date' in body and body['Added Date']:
                                    breach_entry['added_date'] = body['Added Date']
                                if 'Pwn Count' in body and body['Pwn Count']:
                                    breach_entry['pwn_count'] = str(body['Pwn Count'])
                                # Extract tags for breach data types
                                if 'tags' in schema:
                                    breach_data_types = []
                                    for tag in schema['tags']:
                                        if isinstance(tag, dict) and 'tag' in tag:
                                            breach_data_types.append(tag['tag'])
                                    if breach_data_types:
                                        breach_entry['data_types'] = ', '.join(breach_data_types)
                                if breach_entry:
                                    breach_details.append(breach_entry)
                            
                            # Extract URLs from tags (for account URLs) - NOT from Whoxy
                            if module_name != 'whoxy' and schema.get('module', '').lower() != 'whoxy':
                                if 'tags' in schema:
                                    for tag in schema['tags']:
                                        if isinstance(tag, dict):
                                            if 'url' in tag and tag['url']:
                                                url_val = tag['url']
                                                if url_val and (url_val.startswith('http://') or url_val.startswith('https://')):
                                                    cleaned = clean_url(url_val)
                                                    if '/' in cleaned and cleaned.count('/') > 0:
                                                        add_with_source(account_urls, url_val, source)
                        
                        # Extract timeline data (registered_date, last_seen_date)
                        if 'timeline' in schema:
                            timeline = schema['timeline']
                            if isinstance(timeline, dict):
                                if 'registered_date' in timeline and timeline['registered_date']:
                                    add_with_source(registered_dates, timeline['registered_date'], source)
                                if 'last_seen_date' in timeline and timeline['last_seen_date']:
                                    add_with_source(last_seen_dates, timeline['last_seen_date'], source)
                        
                        # Extract platform variables from spec_format
                        if 'platform_variables' in schema and isinstance(schema['platform_variables'], list):
                            for pv in schema['platform_variables']:
                                if isinstance(pv, dict):
                                    key = pv.get('proper_key') or pv.get('key', '')
                                    value = pv.get('value')
                                    if key and value is not None and value != '':
                                        if isinstance(value, dict):
                                            # Handle nested dicts (like statistics)
                                            for sub_key, sub_value in value.items():
                                                if sub_value is not None:
                                                    platform_variables_data.append({
                                                        'value': f"{key}.{sub_key}: {sub_value}",
                                                        'sources': [source]
                                                    })
                                        else:
                                            platform_variables_data.append({
                                                'value': f"{key}: {value}",
                                                'sources': [source]
                                            })
                        
                        # Extract module name for platform associations
                        if 'module' in schema:
                            mod_name = schema['module']
                            if mod_name:
                                add_with_source(platform_associations, mod_name, source)
    
    # Extract domains from domains section
    if 'domains' in data and isinstance(data['domains'], list):
        for domain in data['domains']:
            if domain and domain.strip():
                add_with_source(registered_domains, domain, 'OSINT Industries')
    
    # Extract from rocketreach_via_osint if present
    if 'rocketreach_via_osint' in data:
        source = 'RocketReach'
        for rr_entry in data['rocketreach_via_osint']:
            if 'linkedin_url' in rr_entry and rr_entry['linkedin_url']:
                add_with_source(linkedin_urls, rr_entry['linkedin_url'], source)
            if 'links' in rr_entry and 'linkedin' in rr_entry['links']:
                add_with_source(linkedin_urls, rr_entry['links']['linkedin'], source)
            if 'name' in rr_entry and rr_entry['name']:
                add_with_source(names, rr_entry['name'], source)
            if 'emails' in rr_entry:
                for email_obj in rr_entry['emails']:
                    if 'email' in email_obj and email_obj['email']:
                        add_with_source(emails, email_obj['email'], source, extract_domain=True, domain_list=registered_domains)
            if 'phones' in rr_entry:
                for phone_obj in rr_entry['phones']:
                    if 'phone' in phone_obj and phone_obj['phone']:
                        add_with_source(phones, phone_obj['phone'], source)
    
    # Extract from dehashed_results or complete_dehashed_data if present
    source = 'Dehashed'
    dehashed_entries = []
    
    # Support both old format (dehashed_results) and new format (complete_dehashed_data)
    if 'dehashed_results' in data:
        dehashed_entries = data['dehashed_results']
    elif 'complete_dehashed_data' in data:
        dehashed_entries = data['complete_dehashed_data']
    
    if dehashed_entries:
        for entry in dehashed_entries:
            # Helper function to extract array or single value
            def extract_field(field_name, target_list, transform=None):
                if field_name in entry:
                    value = entry[field_name]
                    if isinstance(value, list):
                        for item in value:
                            if item:
                                final_value = transform(item) if transform else item
                                if final_value:
                                    add_with_source(target_list, final_value, source)
                    elif value:
                        final_value = transform(value) if transform else value
                        if final_value:
                            add_with_source(target_list, final_value, source)
            
            # Username
            extract_field('username', usernames)
            
            # Email (with automatic domain extraction)
            if 'email' in entry:
                email_val = entry['email']
                if isinstance(email_val, list):
                    for e in email_val:
                        if e:
                            add_with_source(emails, e, source, extract_domain=True, domain_list=registered_domains)
                elif email_val:
                    add_with_source(emails, email_val, source, extract_domain=True, domain_list=registered_domains)
            
            # Phone
            extract_field('phone', phones)
            
            # Password (plaintext)
            extract_field('password', passwords)
            
            # Hashed passwords (store as passwords with hash notation)
            if 'hashed_password' in entry:
                hashed_pwds = entry['hashed_password']
                if isinstance(hashed_pwds, list):
                    for hashed_pwd in hashed_pwds:
                        if hashed_pwd:
                            # Extract hash type if available (format: "hash:||TYPE" or "hash:||TYPE||SALT")
                            hash_parts = str(hashed_pwd).split('||')
                            hash_value = hash_parts[0] if hash_parts else hashed_pwd
                            hash_type = hash_parts[1] if len(hash_parts) > 1 else (entry.get('hash_type', 'Unknown'))
                            salt = hash_parts[2] if len(hash_parts) > 2 else None
                            if salt:
                                pwd_entry = f"{hash_value} ({hash_type}, Salt: {salt})"
                            else:
                                pwd_entry = f"{hash_value} ({hash_type})"
                            add_with_source(passwords, pwd_entry, source)
                elif hashed_pwds:
                    hash_parts = str(hashed_pwds).split('||')
                    hash_value = hash_parts[0] if hash_parts else hashed_pwds
                    hash_type = hash_parts[1] if len(hash_parts) > 1 else (entry.get('hash_type', 'Unknown'))
                    salt = hash_parts[2] if len(hash_parts) > 2 else None
                    if salt:
                        pwd_entry = f"{hash_value} ({hash_type}, Salt: {salt})"
                    else:
                        pwd_entry = f"{hash_value} ({hash_type})"
                    add_with_source(passwords, pwd_entry, source)
            
            # Domain
            extract_field('domain', registered_domains)
            
            # Database name (breach source) - add as platform association and breach detail
            if 'database_name' in entry and entry['database_name']:
                db_name = entry['database_name']
                add_with_source(platform_associations, db_name, source)
                
                # Create comprehensive breach detail entry
                breach_entry = {
                    'sources': [source],
                    'title': db_name,
                    'database_name': db_name
                }
                # Add entry ID if available
                if 'id' in entry and entry['id']:
                    breach_entry['id'] = entry['id']
                # Add breach date if available
                if 'breach_date' in entry and entry['breach_date']:
                    breach_entry['breach_date'] = entry['breach_date']
                # Add added date if available
                if 'added_date' in entry and entry['added_date']:
                    breach_entry['added_date'] = entry['added_date']
                # Add obtained_from if available
                if 'obtained_from' in entry and entry['obtained_from']:
                    breach_entry['obtained_from'] = entry['obtained_from']
                # Add source if available
                if 'source' in entry and entry['source']:
                    breach_entry['source'] = entry['source']
                breach_details.append(breach_entry)
            
            # Name
            extract_field('name', names)
            
            # First and Last names (try to split if name contains space)
            if 'name' in entry:
                names_list = entry['name'] if isinstance(entry['name'], list) else [entry['name']] if entry['name'] else []
                for name_val in names_list:
                    if name_val and ' ' in name_val:
                        parts = name_val.strip().split()
                        if len(parts) >= 1:
                            add_with_source(first_names, parts[0], source)
                        if len(parts) >= 2:
                            add_with_source(last_names, ' '.join(parts[1:]), source)
            
            # Social (social media IDs/usernames)
            extract_field('social', platform_ids, lambda x: f"Social ID: {x}")
            
            # IP addresses
            extract_field('ip_address', ip_addresses)
            
            # Addresses
            extract_field('address', addresses)
            
            # Date of Birth
            if 'dob' in entry and entry['dob']:
                dob_val = entry['dob']
                # Try to extract year if it's a date string
                if isinstance(dob_val, str):
                    year_match = re.search(r'\b(19|20)\d{2}\b', dob_val)
                    if year_match:
                        add_with_source(birth_years, year_match.group(0), source)
                elif isinstance(dob_val, (int, float)):
                    # If it's a number, assume it's a year
                    year_str = str(int(dob_val))
                    if len(year_str) == 4 and year_str.startswith(('19', '20')):
                        add_with_source(birth_years, year_str, source)
            
            # Company
            extract_field('company', companies)
            
            # URL
            if 'url' in entry:
                url_val = entry['url']
                if isinstance(url_val, list):
                    for url in url_val:
                        if url and (url.startswith('http://') or url.startswith('https://')):
                            cleaned = clean_url(url)
                            if '/' in cleaned and cleaned.count('/') > 0:
                                add_with_source(account_urls, url, source)
                elif url_val and (url_val.startswith('http://') or url_val.startswith('https://')):
                    cleaned = clean_url(url_val)
                    if '/' in cleaned and cleaned.count('/') > 0:
                        add_with_source(account_urls, url_val, source)
            
            # VIN (Vehicle Identification Number)
            if 'vin' in entry and entry['vin']:
                vin_val = entry['vin']
                if isinstance(vin_val, list):
                    for vin in vin_val:
                        if vin:
                            # Store as platform variable or custom field
                            platform_variables_data.append({
                                'value': f"VIN: {vin}",
                                'sources': [source]
                            })
                elif vin_val:
                    platform_variables_data.append({
                        'value': f"VIN: {vin_val}",
                        'sources': [source]
                    })
            
            # Raw record (complete breach data) - extract additional fields from it
            if 'raw_record' in entry and entry['raw_record']:
                raw = entry['raw_record']
                if isinstance(raw, dict):
                    # Extract any additional fields from raw_record
                    for key, value in raw.items():
                        if value and key not in ['id', 'database_name']:  # Avoid duplicates
                            if key in ['email', 'username', 'password', 'phone', 'name', 'address', 'ip_address']:
                                # These are already handled above, skip
                                continue
                            elif key == 'domain' and value:
                                extract_field('domain', registered_domains)
                            elif key == 'social' and value:
                                extract_field('social', platform_ids, lambda x: f"Social ID: {x}")
                            else:
                                # Store as platform variable
                                if isinstance(value, (str, int, float)) and value:
                                    platform_variables_data.append({
                                        'value': f"{key}: {value}",
                                        'sources': [source]
                                    })
                                elif isinstance(value, list) and value:
                                    for item in value:
                                        if item:
                                            platform_variables_data.append({
                                                'value': f"{key}: {item}",
                                                'sources': [source]
                                            })
    
    # Clean up account URLs
    cleaned_account_urls = []
    seen_urls = set()
    for item in account_urls:
        url = item['value']
        if url and (url.startswith('http://') or url.startswith('https://')):
            cleaned = clean_url(url)
            if '/' in cleaned:
                path_parts = cleaned.split('/')
                if len(path_parts) > 1 and path_parts[1]:
                    if cleaned not in seen_urls:
                        seen_urls.add(cleaned)
                        cleaned_account_urls.append({
                            'value': cleaned,
                            'sources': item['sources']
                        })
    
    # Sort all lists by value for consistency
    def sort_by_value(item):
        return item['value'].lower() if isinstance(item, dict) and 'value' in item else str(item).lower()
    
    return {
        'usernames': sorted(usernames, key=sort_by_value),
        'emails': sorted(emails, key=sort_by_value),
        'phones': sorted(phones, key=sort_by_value),
        'linkedin_urls': sorted(linkedin_urls, key=sort_by_value),
        'passwords': sorted(passwords, key=sort_by_value),
        'registered_domains': sorted(registered_domains, key=sort_by_value),
        'breach_domains': sorted(breach_domains, key=sort_by_value),
        'account_urls': sorted(cleaned_account_urls, key=sort_by_value),
        'platform_associations': sorted(platform_associations, key=sort_by_value),
        # Additional fields
        'names': sorted(names, key=sort_by_value),
        'first_names': sorted(first_names, key=sort_by_value),
        'last_names': sorted(last_names, key=sort_by_value),
        'locations': sorted(locations, key=sort_by_value),
        'bios': sorted(bios, key=sort_by_value),
        'job_titles': sorted(job_titles, key=sort_by_value),
        'companies': sorted(companies, key=sort_by_value),
        'schools': sorted(schools, key=sort_by_value),
        'skills': sorted(skills, key=sort_by_value),
        'picture_urls': sorted(picture_urls, key=sort_by_value),
        'websites': sorted(websites, key=sort_by_value),
        'creation_dates': sorted(creation_dates, key=sort_by_value),
        'last_seen_dates': sorted(last_seen_dates, key=sort_by_value),
        # Additional comprehensive fields
        'birth_years': sorted(birth_years, key=sort_by_value),
        'ages': sorted(ages, key=sort_by_value),
        'genders': sorted(genders, key=sort_by_value),
        'languages': sorted(languages, key=sort_by_value),
        'followers_counts': sorted(followers_counts, key=sort_by_value),
        'following_counts': sorted(following_counts, key=sort_by_value),
        'verified_statuses': sorted(verified_statuses, key=sort_by_value),
        'premium_statuses': sorted(premium_statuses, key=sort_by_value),
        'private_statuses': sorted(private_statuses, key=sort_by_value),
        'email_hints': sorted(email_hints, key=sort_by_value),
        'phone_hints': sorted(phone_hints, key=sort_by_value),
        'banner_urls': sorted(banner_urls, key=sort_by_value),
        'ip_addresses': sorted(ip_addresses, key=sort_by_value),
        'addresses': sorted(addresses, key=sort_by_value),
        'coordinates': sorted(coordinates, key=sort_by_value),
        'job_history_full': job_history_full,
        'education_full': education_full,
        'breach_details': breach_details,
        'platform_ids': sorted(platform_ids, key=sort_by_value),
        'registered_dates': sorted(registered_dates, key=sort_by_value),
        'platform_variables_data': sorted(platform_variables_data, key=sort_by_value),
        'categories': sorted(categories, key=sort_by_value),
    }

def clean_url(url):
    """Remove http://, https://, and www. from URLs"""
    if not url:
        return url
    url = url.replace('https://', '').replace('http://', '')
    if url.startswith('www.'):
        url = url[4:]
    return url.rstrip('/')

def format_output_text(data, primary_email):
    """Format the data as text with email address as header - sections by type, sources as subordinate"""
    
    output = []
    output.append(f"#{primary_email}")
    output.append("")
    
    # Helper to format list items with sources - sources in brackets after value
    def format_list_items(field_name, items, show_validation=False):
        if items:
            output.append(f"##{field_name}")
            output.append("")
            for item in items:
                if isinstance(item, dict) and 'value' in item:
                    value = item['value']
                    sources = item.get('sources', [])
                    sources_str = ', '.join(sources) if sources else 'Unknown'
                    
                    # Show value with source in brackets
                    output.append(f" {value} ({sources_str})")
                    
                    # Show validation details as subordinate (indented)
                    if show_validation and 'validation' in item and item['validation']:
                        validation_parts = []
                        for key, val in item['validation'].items():
                            key_formatted = key.replace('_', ' ').title()
                            if key == 'smtp_valid':
                                key_formatted = 'SMTP'
                            validation_parts.append(f"{key_formatted}: {val}")
                        if validation_parts:
                            output.append(f"   {', '.join(validation_parts)}")
                else:
                    output.append(f" {item}")
            output.append("")
    
    # Name fields
    format_list_items("Name", data['names'])
    format_list_items("First Name", data['first_names'])
    format_list_items("Last Name", data['last_names'])
    format_list_items("Username", data['usernames'])
    format_list_items("Email", data['emails'], show_validation=True)
    format_list_items("Phone", data['phones'], show_validation=True)
    format_list_items("Location", data['locations'])
    format_list_items("LinkedIn", data['linkedin_urls'])
    format_list_items("Job Titles", data['job_titles'])
    format_list_items("Companies", data['companies'])
    format_list_items("Education", data['schools'])
    format_list_items("Skills", data['skills'])
    format_list_items("Bio", data['bios'])
    format_list_items("Passwords", data['passwords'])
    format_list_items("Registered Domains", data['registered_domains'])
    format_list_items("Breach Domains", data['breach_domains'])
    format_list_items("Account URLs", data['account_urls'])
    format_list_items("Websites", data['websites'])
    format_list_items("Picture URLs", [{'value': clean_url(item['value']), 'sources': item['sources']} for item in data['picture_urls']])
    format_list_items("Birth Year", data['birth_years'])
    format_list_items("Age", data['ages'])
    format_list_items("Gender", data['genders'])
    format_list_items("Language", data['languages'])
    format_list_items("Followers", data['followers_counts'])
    format_list_items("Following", data['following_counts'])
    format_list_items("Verified", data['verified_statuses'])
    format_list_items("Premium", data['premium_statuses'])
    format_list_items("Private", data['private_statuses'])
    format_list_items("Email Hints", data['email_hints'])
    format_list_items("Phone Hints", data['phone_hints'])
    format_list_items("Banner URLs", [{'value': clean_url(item['value']), 'sources': item['sources']} for item in data['banner_urls']])
    format_list_items("IP Addresses", data['ip_addresses'])
    format_list_items("Addresses", data['addresses'])
    format_list_items("Coordinates", data['coordinates'])
    format_list_items("Creation Dates", data['creation_dates'])
    format_list_items("Last Seen Dates", data['last_seen_dates'])
    format_list_items("Registered Dates", data['registered_dates'])
    format_list_items("Platform IDs", data['platform_ids'])
    format_list_items("Platform Variables", data['platform_variables_data'])
    format_list_items("Platform Associations", data['platform_associations'])
    format_list_items("Categories", data['categories'])
    
    # Full job history with dates
    if data['job_history_full']:
        output.append("##Job History")
        output.append("")
        for job in data['job_history_full']:
            job_str = ""
            if 'title' in job:
                job_str = job['title']
            if 'company' in job:
                if job_str:
                    job_str += f" at {job['company']}"
                else:
                    job_str = job['company']
            if 'start' in job or 'end' in job:
                dates = []
                if 'start' in job:
                    dates.append(f"from {job['start']}")
                if 'end' in job:
                    dates.append(f"to {job['end']}")
                if dates:
                    job_str += f" ({', '.join(dates)})"
            if 'current' in job and job['current']:
                job_str += " [Current]"
            sources = job.get('sources', [])
            if sources:
                sources_str = ', '.join(sources)
                job_str += f" ({sources_str})"
            if job_str:
                output.append(f" {job_str}")
        output.append("")
    
    # Full education with details
    if data['education_full']:
        output.append("##Education Details")
        output.append("")
        for edu in data['education_full']:
            edu_str = ""
            if 'school' in edu:
                edu_str = edu['school']
            if 'degree' in edu and edu['degree']:
                if edu_str:
                    edu_str += f" - {edu['degree']}"
                else:
                    edu_str = edu['degree']
            if 'major' in edu and edu['major']:
                if edu_str:
                    edu_str += f" in {edu['major']}"
                else:
                    edu_str = edu['major']
            if 'start' in edu or 'end' in edu:
                dates = []
                if 'start' in edu:
                    dates.append(edu['start'])
                if 'end' in edu:
                    dates.append(edu['end'])
                if dates:
                    edu_str += f" ({'-'.join(dates)})"
            sources = edu.get('sources', [])
            if sources:
                sources_str = ', '.join(sources)
                edu_str += f" ({sources_str})"
            if edu_str:
                output.append(f" {edu_str}")
        output.append("")
    
    # Breach details
    if data['breach_details']:
        output.append("##Breach Details")
        output.append("")
        for breach in data['breach_details']:
            breach_str = ""
            if 'title' in breach:
                breach_str = breach['title']
            elif 'domain' in breach:
                breach_str = breach['domain']
            if 'breach_date' in breach:
                if breach_str:
                    breach_str += f" (Breached: {breach['breach_date']})"
                else:
                    breach_str = f"Breached: {breach['breach_date']}"
            if 'pwn_count' in breach:
                if breach_str:
                    breach_str += f" - {breach['pwn_count']} accounts"
                else:
                    breach_str = f"{breach['pwn_count']} accounts"
            if 'data_types' in breach:
                if breach_str:
                    breach_str += f" - Data: {breach['data_types']}"
                else:
                    breach_str = f"Data: {breach['data_types']}"
            sources = breach.get('sources', [])
            if sources:
                sources_str = ', '.join(sources)
                breach_str += f" ({sources_str})"
            if breach_str:
                output.append(f" {breach_str}")
        output.append("")
    
    # Remove trailing empty line
    if output and output[-1] == "":
        output.pop()
    
    return "\n".join(output)

# Global ID mapping across all files and sources - same value = same ID
# Key: (field_type, normalized_value) -> ID
_global_id_map = {}

def normalize_value(value):
    """Normalize value for comparison (lowercase, strip whitespace, collapse internal whitespace, clean URLs/phones)"""
    if value is None:
        return ""
    val_str = str(value).lower().strip()
    
    # Collapse internal whitespace
    val_str = " ".join(val_str.split())
    
    # Remove common punctuation from ends
    val_str = val_str.strip(".,;-")
    
    # Basic URL cleanup if it looks like a URL (strip scheme and www)
    if val_str.startswith(('http:', 'https:', 'www.')):
        val_str = val_str.replace('https://', '').replace('http://', '')
        if val_str.startswith('www.'):
            val_str = val_str[4:]
        val_str = val_str.rstrip('/')
        
    # Basic phone cleanup (if it contains mostly digits and symbols)
    # Only digits, +, -, (, ), spaces. And at least 7 digits.
    if re.match(r'^[\d\+\-\(\)\s]+$', val_str):
        digits = re.sub(r'[^\d]', '', val_str)
        if len(digits) >= 7:
            return digits # Normalized to just digits
            
    return val_str

# Scopes for ID generation to allow cross-field linkage
ID_SCOPES = {
    'registered_domains': 'domain',
    'breach_domains': 'domain',
    'linkedin_urls': 'url',
    'account_urls': 'url',
    'websites': 'url',
    'picture_urls': 'url',
    'banner_urls': 'url',
    'phones': 'phone',
    'emails': 'email',
    'usernames': 'username'
}

def get_or_create_id(field_type, value):
    """Get existing ID for value or create new one (global across all files) using SHA-256 for stability"""
    normalized = normalize_value(value)
    # Use scope if available to allow cross-field ID sharing
    scope = ID_SCOPES.get(field_type, field_type)
    key = (scope, normalized)
    
    if key not in _global_id_map:
        # Use SHA-256 hash of normalized value + scope for deterministic ID
        hash_input = f"{scope}:{normalized}"
        _global_id_map[key] = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()[:8]
    return _global_id_map[key]

def reset_global_id_map():
    """Reset the global ID map (useful for testing or fresh start)"""
    global _global_id_map
    _global_id_map = {}

def merge_extracted_data(data1, data2):
    """Merge two extracted data dictionaries, combining sources and maintaining IDs using global ID map"""
    merged = {}
    
    # Get all unique field names
    all_fields = set(data1.keys()) | set(data2.keys())
    
    for field_name in all_fields:
        items1 = data1.get(field_name, [])
        items2 = data2.get(field_name, [])
        
        # Create a map of normalized value -> item
        value_map = {}
        
        # Process items1
        for item in items1:
            if isinstance(item, dict) and 'value' in item:
                normalized = normalize_value(item['value'])
                # Get or create ID using global map
                item_id = get_or_create_id(field_name, item['value'])
                
                if normalized not in value_map:
                    value_map[normalized] = item.copy()
                    value_map[normalized]['id'] = item_id
                else:
                    # Merge sources
                    existing_sources = set(value_map[normalized].get('sources', []))
                    new_sources = set(item.get('sources', []))
                    value_map[normalized]['sources'] = list(existing_sources | new_sources)
                    # Merge validation if present
                    if 'validation' in item and item['validation']:
                        if 'validation' not in value_map[normalized]:
                            value_map[normalized]['validation'] = {}
                        value_map[normalized]['validation'].update(item['validation'])
                    # Ensure same ID
                    value_map[normalized]['id'] = item_id
        
        # Process items2
        for item in items2:
            if isinstance(item, dict) and 'value' in item:
                normalized = normalize_value(item['value'])
                # Get or create ID using global map
                item_id = get_or_create_id(field_name, item['value'])
                
                if normalized in value_map:
                    # Value exists, merge sources
                    existing_sources = set(value_map[normalized].get('sources', []))
                    new_sources = set(item.get('sources', []))
                    value_map[normalized]['sources'] = list(existing_sources | new_sources)
                    # Merge validation if present
                    if 'validation' in item and item['validation']:
                        if 'validation' not in value_map[normalized]:
                            value_map[normalized]['validation'] = {}
                        value_map[normalized]['validation'].update(item['validation'])
                    # Ensure same ID
                    value_map[normalized]['id'] = item_id
                else:
                    # New value, add it with global ID
                    value_map[normalized] = item.copy()
                    value_map[normalized]['id'] = item_id
        
        merged[field_name] = list(value_map.values())
    
    return merged

def generate_graph_export(data, primary_email):
    """Generate a graph structure (nodes and edges) from the extracted data.
    
    Creates a 'Subject' node anchored to the primary email (or name if available),
    and links all extracted attributes to it. Also creates cross-attribute links
    where explicit (e.g. Email -> Domain).
    """
    nodes = []
    edges = []
    
    # Keep track of created nodes to avoid duplicates
    # Key: ID
    created_node_ids = set()
    
    def add_node(node_type, value, metadata=None):
        if not value: return None
        
        # Use the existing robust ID generation
        node_id = get_or_create_id(node_type, value)
        
        if node_id not in created_node_ids:
            nodes.append({
                'id': node_id,
                'type': node_type,
                'label': str(value),
                'metadata': metadata or {}
            })
            created_node_ids.add(node_id)
        return node_id

    def add_edge(source_id, target_id, relation, metadata=None):
        if not source_id or not target_id or source_id == target_id:
            return
        
        # Deterministic edge ID
        edge_input = f"{source_id}:{target_id}:{relation}"
        edge_id = hashlib.sha256(edge_input.encode('utf-8')).hexdigest()[:8]
        
        edges.append({
            'id': edge_id,
            'source': source_id,
            'target': target_id,
            'relation': relation,
            'metadata': metadata or {}
        })

    # 1. Create the Root/Subject Node
    # Use primary email as label, or name if available in data
    subject_label = primary_email
    if data.get('names') and len(data['names']) > 0:
        subject_label = data['names'][0].get('value', primary_email)
        
    subject_id = add_node('person', subject_label, {'is_root': True, 'primary_email': primary_email})
    
    # 2. Process all fields and link to Subject
    
    # Mapping of internal field names to graph node types and relation names
    field_mappings = {
        'emails': ('email', 'has_email'),
        'phones': ('phone', 'has_phone'),
        'usernames': ('username', 'has_username'),
        'names': ('alias', 'has_alias'),
        'linkedin_urls': ('social_url', 'has_social'),
        'account_urls': ('social_url', 'has_social'),
        'registered_domains': ('domain', 'associated_domain'),
        'breach_domains': ('domain', 'breached_on_domain'),
        'ip_addresses': ('ip', 'associated_ip'),
        'addresses': ('address', 'has_address'),
        'companies': ('company', 'worked_at'),
        'job_titles': ('job_title', 'has_title'),
        'schools': ('school', 'attended'),
        'passwords': ('password', 'exposed_password') # Be careful with PII, maybe just hash?
    }
    
    for field_name, field_data in data.items():
        if field_name in field_mappings and field_data:
            node_type, relation = field_mappings[field_name]
            
            for item in field_data:
                if isinstance(item, dict) and 'value' in item:
                    val = item['value']
                    # Create node for the attribute
                    attr_id = add_node(node_type, val, {'sources': item.get('sources', [])})
                    
                    # Link Subject -> Attribute
                    add_edge(subject_id, attr_id, relation)
                    
                    # Special Case: Link Email -> Domain
                    if node_type == 'email' and '@' in val:
                        try:
                            domain_part = val.split('@')[1]
                            if domain_part:
                                domain_id = add_node('domain', domain_part, {'inferred': True})
                                add_edge(attr_id, domain_id, 'at_domain')
                        except Exception as e:
                            print(f"[EYE-D] Error: {e}")
                            pass

    return {'nodes': nodes, 'edges': edges}

def format_output_json(data, primary_email):
    """Format the data as JSON - sections by type, sources as subordinate keys, with unique IDs for clustering across all sources"""
    
    import uuid
    
    output_data = {
        'primary_email': primary_email,
        'extracted_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sections': {},
        'graph': generate_graph_export(data, primary_email) # Include graph structure
    }
    
    # Field name mappings to section names
    section_names = {
        'emails': 'Email Address',
        'phones': 'Phone Number',
        'passwords': 'Password',
        'usernames': 'Username',
        'names': 'Name',
        'first_names': 'First Name',
        'last_names': 'Last Name',
        'linkedin_urls': 'LinkedIn URL',
        'registered_domains': 'Registered Domain',
        'breach_domains': 'Breach Domain',
        'account_urls': 'Account URL',
        'websites': 'Website',
        'picture_urls': 'Picture URL',
        'banner_urls': 'Banner URL',
        'locations': 'Location',
        'addresses': 'Address',
        'ip_addresses': 'IP Address',
        'coordinates': 'Coordinates',
        'job_titles': 'Job Title',
        'companies': 'Company',
        'schools': 'School',
        'skills': 'Skill',
        'bios': 'Bio',
        'birth_years': 'Birth Year',
        'ages': 'Age',
        'genders': 'Gender',
        'languages': 'Language',
        'followers_counts': 'Followers Count',
        'following_counts': 'Following Count',
        'verified_statuses': 'Verified Status',
        'premium_statuses': 'Premium Status',
        'private_statuses': 'Private Status',
        'email_hints': 'Email Hint',
        'phone_hints': 'Phone Hint',
        'creation_dates': 'Creation Date',
        'last_seen_dates': 'Last Seen Date',
        'registered_dates': 'Registered Date',
        'platform_ids': 'Platform ID',
        'platform_associations': 'Platform Association',
        'categories': 'Category',
    }
    
    # Pre-process: ensure primary email/phone get IDs that match extracted values
    # This ensures the input gets the same ID as matching extracted values
    primary_email_id = None
    if primary_email:
        # Check if primary email appears in extracted emails
        if data.get('emails'):
            for email_item in data['emails']:
                if isinstance(email_item, dict) and 'value' in email_item:
                    if normalize_value(email_item['value']) == normalize_value(primary_email):
                        # Get the ID that will be assigned to this email
                        primary_email_id = get_or_create_id('emails', primary_email)
                        break
        # If not found, still create an ID for it (it will be added to output)
        if primary_email_id is None:
            primary_email_id = get_or_create_id('emails', primary_email)
    
    # Process each field
    for field_name, field_data in data.items():
        if not field_data:
            continue
            
        # Get section name
        section_name = section_names.get(field_name, field_name.replace('_', ' ').title())
        
        # Group by source - items can appear under multiple sources
        by_source = {}
        items_with_ids = []
        
        # First pass: assign IDs to items using global mapping
        for item in field_data:
            if isinstance(item, dict) and 'value' in item:
                value = item['value']
                # Get or create ID using global mapping (same value = same ID across all sources)
                item_id = get_or_create_id(field_name, value)
                item_with_id = item.copy()
                item_with_id['id'] = item_id
                items_with_ids.append(item_with_id)
        
        # Second pass: group by source
        for item in items_with_ids:
            sources = item.get('sources', [])
            for source in sources:
                if source not in by_source:
                    by_source[source] = []
                # Create a copy for this source (but keep same ID)
                item_for_source = item.copy()
                by_source[source].append(item_for_source)
        
        # Structure: section -> source -> items
        if by_source:
            output_data['sections'][section_name] = {}
            for source in sorted(by_source.keys()):
                output_data['sections'][section_name][source] = by_source[source]
    
    # Add primary email to Email Address section if it doesn't already exist
    if primary_email and primary_email_id:
        email_section = output_data['sections'].get('Email Address', {})
        # Check if primary email already exists in any source
        email_exists = False
        for source_items in email_section.values():
            for item in source_items:
                if isinstance(item, dict) and normalize_value(item.get('value', '')) == normalize_value(primary_email):
                    email_exists = True
                    break
            if email_exists:
                break
        
        # If not found, add it as "Input" source
        if not email_exists:
            if 'Email Address' not in output_data['sections']:
                output_data['sections']['Email Address'] = {}
            if 'Input' not in output_data['sections']['Email Address']:
                output_data['sections']['Email Address']['Input'] = []
            output_data['sections']['Email Address']['Input'].append({
                'value': primary_email,
                'sources': ['Input'],
                'id': primary_email_id
            })
    
    # Handle special structured fields (job_history_full, education_full, breach_details, platform_variables_data)
    # These need special handling because they don't have simple 'value' fields
    special_fields = {
        'job_history_full': 'Job History',
        'education_full': 'Education',
        'breach_details': 'Breach Details',
        'platform_variables_data': 'Platform Variables'
    }
    
    for field_name, section_name in special_fields.items():
        if data.get(field_name):
            output_data['sections'][section_name] = {}
            for item in data[field_name]:
                sources = item.get('sources', [])
                # Create a unique key for clustering (based on content)
                if field_name == 'job_history_full':
                    # Use title + company as key for clustering
                    key_parts = []
                    if 'title' in item:
                        key_parts.append(normalize_value(item['title']))
                    if 'company' in item:
                        key_parts.append(normalize_value(item['company']))
                    clustering_key = '|'.join(key_parts) if key_parts else None
                elif field_name == 'education_full':
                    # Use school + degree as key for clustering
                    key_parts = []
                    if 'school' in item:
                        key_parts.append(normalize_value(item['school']))
                    if 'degree' in item:
                        key_parts.append(normalize_value(item['degree']))
                    clustering_key = '|'.join(key_parts) if key_parts else None
                elif field_name == 'breach_details':
                    # Use title or database_name as key
                    clustering_key = normalize_value(item.get('title') or item.get('database_name') or '')
                else:
                    # platform_variables_data - use value field
                    clustering_key = normalize_value(item.get('value', ''))
                
                # Get or create ID using global map
                if clustering_key:
                    item_id = get_or_create_id(field_name, clustering_key)
                else:
                    # Fallback if no key derived
                    import uuid
                    item_id = str(uuid.uuid4())[:8]
                
                for source in sources:
                    if source not in output_data['sections'][section_name]:
                        output_data['sections'][section_name][source] = []
                    item_with_id = item.copy()
                    item_with_id['id'] = item_id
                    output_data['sections'][section_name][source].append(item_with_id)
    
    return json.dumps(output_data, indent=2, default=str, ensure_ascii=False)

def extract_primary_email_from_data(data, filename=None):
    """Extract primary email from data structure"""
    primary_email = data.get('query', '')
    if not primary_email:
        # Check search_metadata for Dehashed files
        if 'search_metadata' in data and data['search_metadata']:
            primary_email = data['search_metadata'].get('query', '')
    if not primary_email:
        if 'results_by_source' in data and data['results_by_source'] and 'rocketreach' in data['results_by_source']:
            rr = data['results_by_source']['rocketreach']
            if rr and 'emails' in rr and len(rr['emails']) > 0:
                primary_email = rr['emails'][0].get('email', '')
    
    if not primary_email and filename:
        email_match = re.search(r'([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z]+)', filename)
        if email_match:
            primary_email = email_match.group(1)
        else:
            primary_email = filename.replace('_', '@').replace('.json', '')
    
    return primary_email

def main():
    import sys
    import os
    import re
    
    # Parse command line arguments
    query_api = False
    query_value = None
    query_type = 'email'
    json_files = []  # Support multiple files
    output_file = None
    api_key = None
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--api' or arg == '-a':
            query_api = True
            if i + 1 < len(sys.argv):
                query_value = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --api requires a query value")
                return
        elif arg == '--type' or arg == '-t':
            if i + 1 < len(sys.argv):
                query_type = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --type requires a type (email, phone, username)")
                return
        elif arg == '--key' or arg == '-k':
            if i + 1 < len(sys.argv):
                api_key = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --key requires an API key")
                return
        elif arg == '--output' or arg == '-o':
            if i + 1 < len(sys.argv):
                output_file = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --output requires a filename")
                return
        elif arg.startswith('-'):
            print(f"Unknown option: {arg}")
            i += 1
        else:
            # Positional argument - assume it's a JSON file (can have multiple)
            json_files.append(arg)
            i += 1
    
    # Reset global ID map for fresh aggregation
    reset_global_id_map()
    
    # If querying API
    if query_api and query_value:
        print(f"Querying OSINT Industries API for {query_type}: {query_value}...")
        data = query_osint_api(query_value, query_type, api_key)
        if not data:
            print("Failed to query API or no data returned.")
            return
        
        # Save raw JSON response
        if not output_file:
            safe_query = re.sub(r'[^\w\-_]', '_', query_value)
            json_output = f"{safe_query}_osint_{int(time.time())}.json"
        else:
            json_output = output_file.replace('.txt', '.json')
        
        with open(json_output, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
        print(f"Raw API response saved to: {json_output}")
        
        # Extract primary email from response
        primary_email = data.get('query', query_value)
        
        print(f"Primary email: {primary_email}")
        print("Extracting data...")
        extracted_data = extract_data_from_json(data)
    else:
        # Process multiple JSON files and aggregate
        if not json_files:
            print("Usage: python3 output.py file1.json [file2.json ...] [--output output_name]")
            print("   or: python3 output.py --api query_value --type email")
            return
        
        all_extracted_data = None
        primary_email = None
        
        print(f"Processing {len(json_files)} file(s)...")
        for json_file in json_files:
            print(f"\nReading JSON file: {json_file}")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Extract primary email from this file
                file_primary_email = extract_primary_email_from_data(data, json_file)
                if not primary_email:
                    primary_email = file_primary_email
                elif file_primary_email and file_primary_email != primary_email:
                    print(f"  Note: Different primary email found: {file_primary_email} (using first: {primary_email})")
                
                print(f"  Primary email: {file_primary_email}")
                print("  Extracting data...")
                file_extracted_data = extract_data_from_json(data)
                
                # Merge with aggregated data
                if all_extracted_data is None:
                    all_extracted_data = file_extracted_data
                else:
                    all_extracted_data = merge_extracted_data(all_extracted_data, file_extracted_data)
                    print(f"  Merged with previous data")
                
            except FileNotFoundError:
                print(f"  ERROR: File not found: {json_file}")
                continue
            except json.JSONDecodeError as e:
                print(f"  ERROR: Invalid JSON in {json_file}: {e}")
                continue
            except Exception as e:
                print(f"  ERROR: Failed to process {json_file}: {e}")
                continue
        
        if all_extracted_data is None:
            print("\nERROR: No data extracted from any files.")
            return
        
        extracted_data = all_extracted_data
    
    if not primary_email:
        primary_email = "unknown@example.com"
        print(f"Warning: Could not determine primary email, using: {primary_email}")
    
    print(f"\nFinal primary email: {primary_email}")
    print("Formatting output...")
    output_text = format_output_text(extracted_data, primary_email)
    output_json = format_output_json(extracted_data, primary_email)
    
    # Save both formats
    if not output_file:
        if len(json_files) == 1:
            base_name = os.path.splitext(os.path.basename(json_files[0]))[0]
            base_name = f"{base_name}_formatted"
        else:
            # Multiple files - use primary email or timestamp
            safe_email = re.sub(r'[^\w\-_]', '_', primary_email)
            base_name = f"{safe_email}_aggregated_{int(time.time())}"
        output_file_txt = os.path.join(os.path.dirname(json_files[0]) if json_files else '.', f"{base_name}.txt")
        output_file_json = os.path.join(os.path.dirname(json_files[0]) if json_files else '.', f"{base_name}.json")
    else:
        output_file_txt = output_file if output_file.endswith('.txt') else f"{output_file}.txt"
        output_file_json = output_file.replace('.txt', '.json') if output_file.endswith('.txt') else f"{output_file}.json"
    
    with open(output_file_txt, 'w', encoding='utf-8') as f:
        f.write(output_text)
    print(f"\nFormatted text saved to: {output_file_txt}")
    
    with open(output_file_json, 'w', encoding='utf-8') as f:
        f.write(output_json)
    print(f"Formatted JSON saved to: {output_file_json}")
    
    print(f"\nTotal sections: {len(json.loads(output_json)['sections'])}")
    print(f"Total unique values across all sources: {sum(len(items) for section in json.loads(output_json)['sections'].values() for items in section.values())}")

if __name__ == "__main__":
    main()
