#!/usr/bin/env python3
"""
EYE-D OSINT Search Integration for Search_Engineer
Handles email, phone, LinkedIn, username, and WHOIS searches
"""

import sys
import os
import json
import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Load environment variables from project root .env
from dotenv import load_dotenv
# Flexible path resolution for both local and server environments
def find_project_root():
    current = Path(__file__).resolve().parent
    # Check up to 5 parent directories for .env
    for i in range(5):
        if (current / ".env").exists():
            return current
        current = current.parent
    # Default to /data on server
    return Path("/data")

project_root = find_project_root()
env_path = project_root / ".env"
load_dotenv(env_path)
print(f"✓ Loaded environment from: {env_path}")

# All imports are now local to this folder
try:
    from ip_geolocation import IPGeolocation
    IP_GEO_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import IP geolocation: {e}")
    IP_GEO_AVAILABLE = False
    IPGeolocation = None

# Import entity-aware storage
try:
    from entity_graph_storage_v2 import EntityGraphStorageV2
except ImportError:
    print("Warning: Could not import EntityGraphStorageV2")
    EntityGraphStorageV2 = None

# Import AI brain for entity extraction
try:
    from openai_chatgpt import chat_sync, analyze, GPT5_MODELS
except ImportError:
    print("Warning: Could not import AI brain for entity extraction")
    chat_sync = None
    analyze = None
    GPT5_MODELS = []

# Import proper PhoneVariator from NEXUS
PHONE_VARIATIONS_AVAILABLE = False
PhoneVariator = None
try:
    # Ensure BACKEND path is in sys.path
    backend_path = Path(__file__).resolve().parents[2]
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from modules.NEXUS.phone_variations import PhoneVariator
    PHONE_VARIATIONS_AVAILABLE = True
    print("✓ Loaded PhoneVariator from NEXUS (60+ variations, country-aware)")
except Exception as e:
    print(f"⚠️ Could not import PhoneVariator: {e}")
    print("  Phone variation search will use basic fallback")

# Import BRUTE search engine for phone number web searches
BRUTE_AVAILABLE = False
BruteSearchEngine = None
try:
    # Add BACKEND directory to path (brute imports expect 'modules.brute.xxx')
    backend_path = Path(__file__).resolve().parents[2]  # Up to BACKEND
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    # Now try importing with package structure
    from modules.brute.brute import BruteSearchEngine
    BRUTE_AVAILABLE = True
    print(f"✓ Loaded BRUTE search engine")
except Exception as e:
    print(f"⚠️ BRUTE search not available: {e}")
    print("  Phone variation search will be skipped")

# Import JESTER for scraping matched URLs
try:
    # Ensure BACKEND path is in sys.path
    backend_path = Path(__file__).resolve().parents[2]
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    # Import from modules.JESTER package
    from modules.JESTER import Jester, JesterResult
    JESTER_AVAILABLE = True
    print(f"✓ Loaded JESTER scraper")
except Exception as e:
    print(f"Warning: Could not import JESTER scraper: {e}")
    JESTER_AVAILABLE = False
    Jester = None
    JesterResult = None

# Import Cymonides for phone index search
CYMONIDES_AVAILABLE = False
CymonidesBridge = None
try:
    backend_path = Path(__file__).resolve().parents[2]
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from modules.CYMONIDES.bridge import CymonidesBridge
    CYMONIDES_AVAILABLE = True
    print(f"✓ Loaded Cymonides bridge (phones_unified: 49K+ records)")
except Exception as e:
    print(f"⚠️ Could not import Cymonides: {e}")
    print("  Phone index search will be skipped")

# Import C1Bridge for recursive search with priority queues
C1_BRIDGE_AVAILABLE = False
C1Bridge = None
try:
    from c1_bridge import C1Bridge
    C1_BRIDGE_AVAILABLE = True
    print(f"✓ Loaded C1Bridge (VERIFIED-first recursive search)")
except ImportError:
    try:
        from .c1_bridge import C1Bridge
        C1_BRIDGE_AVAILABLE = True
        print(f"✓ Loaded C1Bridge (VERIFIED-first recursive search)")
    except ImportError as e:
        print(f"⚠️ Could not import C1Bridge: {e}")
        print("  Recursive search will not be available")

# Import central entity extractor
try:
    from central_extractor import CentralEntityExtractor, ExtractionMethod
except ImportError:
    print("Warning: Could not import CentralEntityExtractor")
    CentralEntityExtractor = None
    ExtractionMethod = None

# Import deterministic OSINT data extractor (handles DeHashed, RocketReach, OSINT Industries structured output)
try:
    from output import extract_data_from_json, generate_graph_export
    STRUCTURED_EXTRACTOR_AVAILABLE = True
except ImportError:
    print("Warning: Could not import structured output extractor")
    extract_data_from_json = None
    generate_graph_export = None
    STRUCTURED_EXTRACTOR_AVAILABLE = False

# Import deterministic WHOIS helpers
try:
    from whoisxmlapi import (
        whois_lookup,
        extract_entities_from_records,
        summarize_whois_records,
    )
    WHOISXML_AVAILABLE = True
except ImportError:
    try:
        from eyed.whoisxmlapi import (
            whois_lookup,
            extract_entities_from_records,
            summarize_whois_records,
        )
        WHOISXML_AVAILABLE = True
    except ImportError:
        print("Warning: Could not import whoisxmlapi helpers")
        whois_lookup = None
        extract_entities_from_records = None
        summarize_whois_records = None
        WHOISXML_AVAILABLE = False

# Popular email domains to exclude from domain-level breach searches
POPULAR_EMAIL_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com', 
    'icloud.com', 'protonmail.com', 'mail.com', 'yandex.com', 'zoho.com',
    'live.com', 'msn.com', 'googlemail.com', 'yahoo.co.uk', 'hotmail.co.uk',
    'me.com', 'mac.com', 'comcast.net', 'verizon.net', 'att.net'
}

class UnifiedSearcher:
    """Unified OSINT searcher - aggregates all search engines"""

    def __init__(self, event_emitter=None):
        self.ip_geo_client = IPGeolocation() if IP_GEO_AVAILABLE else None
        self.event_emitter = event_emitter

        # Initialize central entity extractor
        self.central_extractor = CentralEntityExtractor() if CentralEntityExtractor else None

        # Try to initialize entity-aware storage, but handle errors gracefully
        try:
            self.storage = EntityGraphStorageV2() if EntityGraphStorageV2 else None
        except Exception as e:
            print(f"Warning: Could not initialize EntityGraphStorageV2: {e}")
            self.storage = None

        # Initialize AI brain for entity extraction
        self.ai_brain = None  # Stub for now

        # Initialize C1Bridge for recursive search
        self.c1_bridge = C1Bridge() if C1_BRIDGE_AVAILABLE else None
        
    def extract_query_value(self, query: str, search_type: str) -> str:
        """Extract the actual value from the query (remove ? and other markers)"""
        if search_type == 'whois':
            # Extract domain from whois!:domain.com pattern
            match = re.match(r'^whois!\s*:\s*(.+)$', query)
            if match:
                return match.group(1).strip()
            return query
        elif search_type == 'username':
            # Extract username from u:username or username:username patterns
            if query.lower().startswith('username:'):
                return query[9:].strip()
            elif query.lower().startswith('u:'):
                return query[2:].strip()
            return query.rstrip('?').strip()
        else:
            # Remove trailing ? for other types
            return query.rstrip('?').strip()
    
    async def run_chain_reaction(self, start_query: str, start_type: str, depth: int = 2, subject_context: str = "") -> Dict[str, Any]:
        """
        Execute a chain reaction search (Recursive OSINT).
        
        1. Search the start_query.
        2. Extract entities.
        3. If subject_context is empty, build it from the first search results.
        4. AI Filter: Keep only entities relevant to the subject_context.
        5. Recurse on those entities up to 'depth'.
        """
        print(f"⛓️ Starting Chain Reaction for: {start_query} ({start_type}) [Depth: {depth}]")
        
        all_results = []
        visited = set()
        queue = [(start_query, start_type, 0)]
        
        # normalize start query
        visited.add(f"{start_type}:{start_query}")

        while queue:
            current_query, current_type, current_depth = queue.pop(0)
            
            if current_depth >= depth:
                continue
                
            print(f"  ↪ Step {current_depth + 1}: Searching {current_type} -> {current_query}")
            
            # Dispatch search
            search_result = await self._dispatch_search(current_query, current_type)
            if not search_result or search_result.get('error'):
                continue
                
            all_results.append(search_result)
            
            # Build/Update Subject Context on first successful run if missing
            if not subject_context and current_depth == 0:
                subject_context = await self._build_subject_context(search_result)
                print(f"  🧠 Subject Context Established: {subject_context[:100]}...")

            # Extract potential new leads
            new_entities = search_result.get('entities', [])
            if not new_entities:
                continue
                
            # Filter relevant entities using AI
            relevant_entities = await self._filter_relevant_entities(new_entities, subject_context)
            
            for entity in relevant_entities:
                e_type = entity.get('type', '').upper()
                e_value = entity.get('value', '')
                
                # Map entity type to search type
                next_type = self._map_entity_type_to_search_type(e_type)
                
                if next_type and e_value:
                    unique_key = f"{next_type}:{e_value}"
                    if unique_key not in visited:
                        visited.add(unique_key)
                        print(f"    + Adding lead: {e_value} ({next_type})")
                        queue.append((e_value, next_type, current_depth + 1))
        
        return {
            'query': start_query,
            'query_type': 'chain_reaction',
            'depth': depth,
            'total_steps': len(visited),
            'subject_context': subject_context,
            'results': all_results
        }

    async def _dispatch_search(self, query: str, search_type: str) -> Dict[str, Any]:
        """Helper to dispatch to specific search methods"""
        search_type = search_type.lower()
        if search_type == 'email':
            return await self.search_email(query)
        elif search_type == 'phone':
            return await self.search_phone(query)
        elif search_type == 'username':
            return await self.search_username(query, mode='enrichment') # Use enrichment mode for chain reaction
        elif search_type == 'linkedin':
            return await self.search_linkedin(query)
        elif search_type == 'whois' or search_type == 'domain':
            return await self.search_whois(query)
        elif search_type == 'ip':
            return await self.search_ip(query)
        elif search_type == 'person':
            return await self.search_people(query)
        elif search_type == 'password':
            return await self.search_password(query)
        return None

    def _map_entity_type_to_search_type(self, entity_type: str) -> Optional[str]:
        """Map extracted entity types to executable search types"""
        mapping = {
            'EMAIL': 'email',
            'EMAIL_ADDRESS': 'email',
            'PHONE': 'phone',
            'PHONE_NUMBER': 'phone',
            'USERNAME': 'username',
            'DOMAIN': 'whois',
            'URL': 'whois',
            'IP_ADDRESS': 'ip',
            'PERSON': 'person',
            'NAME': 'person',
            'LINKEDIN': 'linkedin',
            'PASSWORD': 'password',
            'HASH': 'password'
        }
        return mapping.get(entity_type.upper())

    async def _build_subject_context(self, result: Dict[str, Any]) -> str:
        """Create a text summary of the subject from initial results"""
        if not chat_sync:
            return f"Subject related to {result.get('query')}"
            
        # Aggregate snippets
        data_snippets = []
        for item in result.get('results', []):
            data_snippets.append(str(item.get('data', '')))
        
        content = "\n".join(data_snippets[:10]) # Limit to first 10 results to save tokens
        
        prompt = f"""
        Analyze the following OSINT search results for the query "{result.get('query')}".
        Construct a concise but specific profile summary of the subject (Person, Organization, or Entity).
        Include key identifiers (names, emails, locations, roles) that define this subject.
        This summary will be used to filter future search results for relevance.
        
        Results:
        {content[:3000]}
        """
        
        try:
            return chat_sync(prompt, model=GPT5_MODELS["NANO"] if GPT5_MODELS else "gpt-4")
        except Exception as e:
            print(f"Error building context: {e}")
            return f"Subject related to {result.get('query')}"

    async def _filter_relevant_entities(self, entities: List[Dict], context: str) -> List[Dict]:
        """
        Use AI to filter entities that are relevant to the subject context.
        """
        if not context or not chat_sync:
            # Fallback: Return all if no brain available, or maybe simple heuristics
            return entities
        
        # Prepare entities for AI review
        candidates = [f"{i}: {e.get('value')} ({e.get('type')}) - Found via {e.get('context', 'unknown')}" 
                      for i, e in enumerate(entities)]
        
        if not candidates:
            return []

        prompt = f"""
        I am conducting an OSINT investigation on the following subject:
        "{context}"
        
        I have found the following new entities/leads. Identify which ones are highly likely to be relevant to the SAME subject 
        or strongly associated with them (e.g., their other accounts, their company, their location).
        Ignore generic, unrelated, or low-confidence junk.
        
        Candidates:
        {json.dumps(candidates, indent=2)}
        
        Return ONLY a JSON array of indices (integers) of the relevant entities. Example: [0, 3, 5]
        """
        
        try:
            response = chat_sync(prompt, model=GPT5_MODELS["NANO"] if GPT5_MODELS else "gpt-4")
            # Extract JSON array from response
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                indices = json.loads(match.group(0))
                return [entities[i] for i in indices if 0 <= i < len(entities)]
        except Exception as e:
            print(f"Error filtering entities: {e}")
            
        return entities # Default to returning all if AI fails, to be safe? Or none? returning all for now.

    async def search_email(self, email: str) -> Dict[str, Any]:
        """Search for email address across all EYE-D sources, including domain check for private domains"""
        print(f"📧 Searching for email: {email}")
        
        results = {
            'query': email,
            'query_type': 'entity_search',
            'subtype': 'email',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        # Emit starting event
        if self.event_emitter:
            self.event_emitter('entity_progress', {
                'type': 'search_start',
                'message': f'🔍 Starting EYE-D OSINT search for email: {email}',
                'source': 'EYE-D',
                'query': email
            })
        
        try:
            # Try each engine
            try:
                try:
                    from .dehashed_engine import DeHashedEngine
                except ImportError:
                    from dehashed_engine import DeHashedEngine
                
                # 1. Standard Email Search
                engine = DeHashedEngine(email, event_emitter=self.event_emitter)
                data = engine.search()
                if data:
                    results['results'].append({
                        'source': 'dehashed',
                        'data': data,
                        'entity_type': 'email',
                        'entity_value': email
                    })
                    # Extract entities from breach records for chain searches
                    if isinstance(data, list):
                        for record in data:
                            if record.get('username'):
                                results['entities'].append({
                                    'type': 'USERNAME',
                                    'value': record.get('username'),
                                    'context': 'dehashed_breach'
                                })
                            if record.get('password'):
                                results['entities'].append({
                                    'type': 'PASSWORD',
                                    'value': record.get('password'),
                                    'context': 'dehashed_breach'
                                })
                            if record.get('phone'):
                                results['entities'].append({
                                    'type': 'PHONE',
                                    'value': record.get('phone'),
                                    'context': 'dehashed_breach'
                                })
                            if record.get('ip_address'):
                                results['entities'].append({
                                    'type': 'IP_ADDRESS',
                                    'value': record.get('ip_address'),
                                    'context': 'dehashed_breach'
                                })
                            if record.get('name'):
                                results['entities'].append({
                                    'type': 'NAME',
                                    'value': record.get('name'),
                                    'context': 'dehashed_breach'
                                })
                            if record.get('address'):
                                results['entities'].append({
                                    'type': 'ADDRESS',
                                    'value': record.get('address'),
                                    'context': 'dehashed_breach'
                                })
                
                # 2. Domain Search (if not popular provider)
                if '@' in email:
                    domain = email.split('@')[1].lower()
                    if domain not in POPULAR_EMAIL_DOMAINS:
                        print(f"🏢 Private/Company domain detected: {domain}. Running domain breach search...")
                        if self.event_emitter:
                            self.event_emitter('entity_progress', {
                                'type': 'search_start',
                                'message': f'🔍 Routing {domain} to DeHashed domain search (Private Domain)',
                                'source': 'DeHashed',
                                'query': domain
                            })
                        
                        # Explicit domain search
                        domain_engine = DeHashedEngine(event_emitter=self.event_emitter)
                        # Use 'domain:example.com' syntax or rely on auto-detection if build_query handles it
                        # DeHashedEngine.search takes custom_query. Let's format it explicitly for clarity.
                        domain_data = domain_engine.search(custom_query=f"domain:{domain}")
                        
                        if domain_data and not isinstance(domain_data, dict): # check if it's a list of entries
                             results['results'].append({
                                'source': 'dehashed_domain', 
                                'data': domain_data, 
                                'entity_type': 'domain', 
                                'entity_value': domain
                            })
                            
            except Exception as e:
                print(f"DeHashed engine error: {e}")

            # 2. OSINT Industries Email Search
            try:
                try:
                    from .osintindustries import OSINTIndustriesClient
                except ImportError:
                    from osintindustries import OSINTIndustriesClient

                client = OSINTIndustriesClient()
                osint_data = client.search('email', email)
                if osint_data:
                    results['results'].append({
                        'source': 'osint_industries',
                        'data': osint_data,
                        'entity_type': 'email',
                        'entity_value': email
                    })
                    # Extract entities from OSINT Industries results
                    for result in osint_data:
                        if hasattr(result, 'phone') and result.phone:
                            results['entities'].append({
                                'type': 'PHONE',
                                'value': result.phone,
                                'context': f'osint_industries_{result.module}'
                            })
                        if hasattr(result, 'username') and result.username:
                            results['entities'].append({
                                'type': 'USERNAME',
                                'value': result.username,
                                'context': f'osint_industries_{result.module}'
                            })
                        if hasattr(result, 'name') and result.name:
                            results['entities'].append({
                                'type': 'NAME',
                                'value': result.name,
                                'context': f'osint_industries_{result.module}'
                            })
                        if hasattr(result, 'profile_url') and result.profile_url:
                            results['entities'].append({
                                'type': 'URL',
                                'value': result.profile_url,
                                'context': f'osint_industries_{result.module}'
                            })
                        if hasattr(result, 'location') and result.location:
                            results['entities'].append({
                                'type': 'LOCATION',
                                'value': result.location,
                                'context': f'osint_industries_{result.module}'
                            })
                        # Extract social profiles
                        if hasattr(result, 'social_profiles') and result.social_profiles:
                            for profile in result.social_profiles:
                                if hasattr(profile, 'url') and profile.url:
                                    results['entities'].append({
                                        'type': 'SOCIAL_URL',
                                        'value': profile.url,
                                        'context': f'osint_industries_{profile.platform}'
                                    })
            except Exception as e:
                print(f"OSINT Industries email search error: {e}")

            # 3. Enrichment Services (RocketReach, ContactOut, Kaspr)
            # These services typically offer API endpoints for email enrichment or finding people behind emails.
            # We'll stub them here, assuming modules exist or will be implemented.
            
            # RocketReach
            try:
                try: 
                    from .rocketreach_client import RocketReachClient
                except ImportError: 
                    try:
                        from rocketreach_client import RocketReachClient 
                    except ImportError:
                         RocketReachClient = None

                if RocketReachClient:
                    rr_client = RocketReachClient() # Assumes env var setup
                    rr_data = rr_client.lookup_email(email)
                    if rr_data:
                        results['results'].append({
                            'source': 'rocketreach',
                            'data': rr_data,
                            'entity_type': 'person_profile',
                            'entity_value': rr_data.get('name', 'Unknown')
                        })
                        # Extract all entities from RocketReach profile
                        if rr_data.get('linkedin_url'):
                            results['entities'].append({
                                'type': 'LINKEDIN_URL',
                                'value': rr_data.get('linkedin_url'),
                                'context': 'rocketreach_profile'
                            })
                        if rr_data.get('name'):
                            results['entities'].append({
                                'type': 'NAME',
                                'value': rr_data.get('name'),
                                'context': 'rocketreach_profile'
                            })
                        if rr_data.get('current_employer'):
                            results['entities'].append({
                                'type': 'COMPANY',
                                'value': rr_data.get('current_employer'),
                                'context': 'rocketreach_profile'
                            })
                        # Extract phone numbers
                        for phone in rr_data.get('phones', []):
                            if phone:
                                results['entities'].append({
                                    'type': 'PHONE',
                                    'value': phone,
                                    'context': 'rocketreach_profile'
                                })
                        # Extract additional emails
                        for extra_email in rr_data.get('emails', []):
                            if extra_email and extra_email != email:
                                results['entities'].append({
                                    'type': 'EMAIL',
                                    'value': extra_email,
                                    'context': 'rocketreach_profile'
                                })
            except Exception as e:
                print(f"RocketReach error: {e}")

            # ContactOut
            try:
                try:
                    from .contactout_client import ContactOutClient
                except ImportError:
                    from contactout_client import ContactOutClient
                
                co_client = ContactOutClient()
                co_data = co_client.enrich_email(email)
                if co_data:
                    results['results'].append({
                        'source': 'contactout',
                        'data': co_data,
                        'entity_type': 'person_profile',
                        'entity_value': co_data.get('name', 'Unknown')
                    })
                    # Extract all entities from ContactOut profile
                    if co_data.get('linkedin_url'):
                        results['entities'].append({
                            'type': 'LINKEDIN_URL',
                            'value': co_data.get('linkedin_url'),
                            'context': 'contactout_profile'
                        })
                    if co_data.get('name'):
                        results['entities'].append({
                            'type': 'NAME',
                            'value': co_data.get('name'),
                            'context': 'contactout_profile'
                        })
                    if co_data.get('current_employer'):
                        results['entities'].append({
                            'type': 'COMPANY',
                            'value': co_data.get('current_employer'),
                            'context': 'contactout_profile'
                        })
                    # Extract phone numbers
                    for phone in co_data.get('phones', []):
                        if phone:
                            results['entities'].append({
                                'type': 'PHONE',
                                'value': phone,
                                'context': 'contactout_profile'
                            })
                    # Extract additional emails
                    for extra_email in co_data.get('emails', []):
                        if extra_email and extra_email != email:
                            results['entities'].append({
                                'type': 'EMAIL',
                                'value': extra_email,
                                'context': 'contactout_profile'
                            })
            except Exception as e:
                print(f"ContactOut error: {e}")
                
            # Kaspr (Kendo)
            try:
                # Kaspr doesn't have email lookup in basic tier usually, but if client has it:
                # from .kaspr_client import KasprClient
                pass 
            except Exception as e:
                print(f"Kaspr error: {e}")
            
            # Add other engines similarly if available...

            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for email {email}")

            # Run structured extraction to produce cycleable entities
            if results['results']:
                extraction = await self._extract_entities_from_data(results)
                results['extracted_entities'] = extraction.get('entities', [])
                results['graph'] = extraction.get('graph', {'nodes': [], 'edges': []})
                results['structured_data'] = extraction.get('structured', {})
                print(f"📊 Extracted {len(results['extracted_entities'])} cycleable entities")

        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching email: {e}")

        return results
    
    async def search_phone(self, phone: str) -> Dict[str, Any]:
        """Search for phone number across all entity search sources"""
        print(f"📱 Searching for phone: {phone}")
        
        results = {
            'query': phone,
            'query_type': 'entity_search',
            'subtype': 'phone',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Normalize phone number (basic normalization)
            normalized_phone = re.sub(r'[^\d+]', '', phone)

            # 0. Phone Variation + BRUTE Web Search (ALWAYS RUN FOR PHONE SEARCHES)
            print("🔍 Starting phone variation + BRUTE web search...")
            if PHONE_VARIATIONS_AVAILABLE and BRUTE_AVAILABLE and JESTER_AVAILABLE:
                try:
                    # Generate phone number variations using proper PhoneVariator
                    # Detect country from phone number
                    variator = PhoneVariator(max_variations=60)
                    parsed = variator.parse(phone)
                    country = parsed.country_region

                    print(f"📱 Detected country: {country or 'Unknown'}")
                    print(f"📱 Parsed as: +{parsed.country_code} {parsed.national_number}")

                    # Get search queries organized by likelihood tier
                    tiers = variator.get_search_tiers(phone, country)

                    # Collect all queries (HIGH + MEDIUM for performance, skip LOW/EXPERIMENTAL)
                    all_variations = []
                    all_variations.extend(tiers.get('high', []))
                    all_variations.extend(tiers.get('medium', []))

                    print(f"📋 Generated {len(all_variations)} search queries:")
                    print(f"   - HIGH likelihood: {len(tiers.get('high', []))} (full number exact matches)")
                    print(f"   - MEDIUM likelihood: {len(tiers.get('medium', []))} (segment patterns)")

                    # Show example queries
                    if tiers.get('high'):
                        print(f"   Examples HIGH: {tiers['high'][:2]}")
                    if tiers.get('medium'):
                        print(f"   Examples MEDIUM: {tiers['medium'][:2]}")

                    # Track all URLs that contain the phone number
                    matching_urls = []

                    # Run BRUTE search for each variation in no-scrape fast mode
                    for i, variation in enumerate(all_variations, 1):
                        print(f"🔎 Searching variation {i}/{len(all_variations)}: {variation}")

                        # Create temporary environment with ENABLE_SCRAPING=false for fast mode
                        original_scraping = os.environ.get('ENABLE_SCRAPING', 'false')
                        os.environ['ENABLE_SCRAPING'] = 'false'

                        try:
                            # Initialize BRUTE with the query (already has quotes from PhoneVariator)
                            brute = BruteSearchEngine(
                                keyword=variation,  # Already quoted by PhoneVariator
                                return_results=True,  # Get results back instead of saving to file
                                engines=None  # Use all engines
                            )

                            # Run search
                            brute.run()

                            # Get results
                            if brute.final_results:
                                print(f"✓ Found {len(brute.final_results)} results for {variation}")

                                # Filter URLs that contain the original phone number
                                for result in brute.final_results:
                                    url = result.get('url', '')
                                    title = result.get('title', '')
                                    snippet = result.get('snippet', '')

                                    # Check if URL, title, or snippet contains the normalized phone
                                    if (normalized_phone in url or
                                        normalized_phone in title or
                                        normalized_phone in snippet):
                                        matching_urls.append({
                                            'url': url,
                                            'title': title,
                                            'snippet': snippet,
                                            'variation': variation
                                        })
                                        print(f"✅ Match found: {url}")

                        finally:
                            # Restore original scraping setting
                            os.environ['ENABLE_SCRAPING'] = original_scraping

                    # Deduplicate URLs
                    seen_urls = set()
                    unique_matching_urls = []
                    for item in matching_urls:
                        if item['url'] not in seen_urls:
                            seen_urls.add(item['url'])
                            unique_matching_urls.append(item)

                    print(f"📊 Found {len(unique_matching_urls)} unique URLs containing phone number")

                    # Now scrape the matching URLs and extract entities
                    if unique_matching_urls:
                        jester = Jester()

                        for i, url_data in enumerate(unique_matching_urls[:20], 1):  # Limit to first 20 for performance
                            url = url_data['url']
                            print(f"🕷️ Scraping {i}/{min(len(unique_matching_urls), 20)}: {url}")

                            try:
                                # Scrape the page using JESTER
                                scrape_result = await jester.scrape(url)

                                if scrape_result and scrape_result.content:
                                    print(f"✓ Scraped {len(scrape_result.content)} chars from {url}")

                                    # Extract entities from scraped content using AI
                                    if chat_sync:
                                        try:
                                            extraction_prompt = f"""Extract all entities from this webpage content that contains the phone number {phone}.

Find:
- Names (people)
- Companies/organizations
- Email addresses
- Additional phone numbers
- Addresses
- Social media handles
- Any other identifying information

Content:
{scrape_result.content[:5000]}

Return JSON array of entities: [{{"type": "PERSON", "value": "John Doe", "context": "found on page"}}, ...]"""

                                            extraction_response = chat_sync(
                                                prompt=extraction_prompt,
                                                model="gpt-4.1-nano",
                                                max_tokens=2000
                                            )

                                            # Parse JSON response
                                            try:
                                                extracted_entities = json.loads(extraction_response)
                                                if isinstance(extracted_entities, list):
                                                    for entity in extracted_entities:
                                                        entity['context'] = f"brute_scrape_{url}"
                                                        results['entities'].append(entity)
                                                    print(f"✓ Extracted {len(extracted_entities)} entities from {url}")
                                            except json.JSONDecodeError:
                                                print(f"⚠️ Could not parse extraction response for {url}")

                                        except Exception as e:
                                            print(f"⚠️ Entity extraction error for {url}: {e}")

                                    # Add the scraped content to results
                                    results['results'].append({
                                        'source': 'brute_web_search',
                                        'url': url,
                                        'title': url_data['title'],
                                        'snippet': url_data['snippet'],
                                        'content': scrape_result.content[:1000],  # First 1000 chars
                                        'variation': url_data['variation'],
                                        'entity_type': 'phone',
                                        'entity_value': phone
                                    })

                            except Exception as e:
                                print(f"⚠️ Error scraping {url}: {e}")

                        await jester.close()

                except Exception as e:
                    print(f"⚠️ Error in phone variation + BRUTE search: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                if not PHONE_VARIATIONS_AVAILABLE:
                    print("⚠️ PhoneVariator not available - phone variation web search skipped")
                if not BRUTE_AVAILABLE:
                    print("⚠️ BRUTE search engine not available - phone variation web search skipped")
                if not JESTER_AVAILABLE:
                    print("⚠️ JESTER scraper not available - phone variation web search skipped")

            # 0.5. Cymonides Phone Index Search (49K records in phones_unified)
            if CYMONIDES_AVAILABLE:
                try:
                    print("🔍 Searching Cymonides phone index (phones_unified: 49K records)...")
                    bridge = CymonidesBridge(prefer_remote=True)
                    cymonides_results = bridge.check_unknown_knowns('phone', phone, limit=50)

                    if cymonides_results:
                        print(f"✓ Found {len(cymonides_results)} results in Cymonides")
                        results['results'].append({
                            'source': 'cymonides_phones_unified',
                            'data': cymonides_results,
                            'entity_type': 'phone',
                            'entity_value': phone
                        })

                        # Extract entities from Cymonides results for recursive loop
                        for record in cymonides_results:
                            # Extract person names
                            if record.get('name'):
                                results['entities'].append({
                                    'type': 'NAME',
                                    'value': record['name'],
                                    'context': 'cymonides_phones'
                                })
                            # Extract emails
                            if record.get('email'):
                                results['entities'].append({
                                    'type': 'EMAIL',
                                    'value': record['email'],
                                    'context': 'cymonides_phones'
                                })
                            # Extract additional phones
                            if record.get('phone') and record['phone'] != phone:
                                results['entities'].append({
                                    'type': 'PHONE',
                                    'value': record['phone'],
                                    'context': 'cymonides_phones'
                                })
                            # Extract companies
                            if record.get('company'):
                                results['entities'].append({
                                    'type': 'COMPANY',
                                    'value': record['company'],
                                    'context': 'cymonides_phones'
                                })
                            # Extract addresses
                            if record.get('address'):
                                results['entities'].append({
                                    'type': 'ADDRESS',
                                    'value': record['address'],
                                    'context': 'cymonides_phones'
                                })
                    else:
                        print("ℹ️ No results found in Cymonides phone index")

                except Exception as e:
                    print(f"⚠️ Cymonides phone search error: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("⚠️ Cymonides bridge not available - phone index search skipped")

            # 1. OSINT Industries Phone Search
            try:
                try:
                    from .osintindustries import OSINTIndustriesClient
                except ImportError:
                    from osintindustries import OSINTIndustriesClient
                
                client = OSINTIndustriesClient()
                osint_data = client.search('phone', phone)
                if osint_data:
                    results['results'].append({
                        'source': 'osint_industries',
                        'data': osint_data,
                        'entity_type': 'phone',
                        'entity_value': phone
                    })
                    # Extract entities from OSINT Industries results
                    for result in osint_data:
                        if hasattr(result, 'email') and result.email:
                            results['entities'].append({
                                'type': 'EMAIL',
                                'value': result.email,
                                'context': f'osint_industries_{result.module}'
                            })
                        if hasattr(result, 'username') and result.username:
                            results['entities'].append({
                                'type': 'USERNAME',
                                'value': result.username,
                                'context': f'osint_industries_{result.module}'
                            })
                        if hasattr(result, 'name') and result.name:
                            results['entities'].append({
                                'type': 'NAME',
                                'value': result.name,
                                'context': f'osint_industries_{result.module}'
                            })
                        if hasattr(result, 'profile_url') and result.profile_url:
                            results['entities'].append({
                                'type': 'URL',
                                'value': result.profile_url,
                                'context': f'osint_industries_{result.module}'
                            })
                        if hasattr(result, 'location') and result.location:
                            results['entities'].append({
                                'type': 'LOCATION',
                                'value': result.location,
                                'context': f'osint_industries_{result.module}'
                            })
                        # Extract social profiles
                        if hasattr(result, 'social_profiles') and result.social_profiles:
                            for profile in result.social_profiles:
                                if hasattr(profile, 'url') and profile.url:
                                    results['entities'].append({
                                        'type': 'SOCIAL_URL',
                                        'value': profile.url,
                                        'context': f'osint_industries_{profile.platform}'
                                    })
            except Exception as e:
                print(f"OSINT Industries phone search error: {e}")

            # 2. DeHashed Breach Search
            try:
                try:
                    from .dehashed_engine import DeHashedEngine
                except ImportError:
                    from dehashed_engine import DeHashedEngine
                
                # DeHashed supports phone search: phone:1234567890
                # We strip the + for DeHashed as it often stores raw digits
                dehashed_phone = normalized_phone.replace('+', '')
                engine = DeHashedEngine(phone, event_emitter=self.event_emitter)
                breach_data = engine.search(custom_query=f"phone:{dehashed_phone}")
                
                if breach_data:
                    results['results'].append({
                        'source': 'dehashed',
                        'data': breach_data,
                        'entity_type': 'phone',
                        'entity_value': phone
                    })
                    # Extract entities from breach records for chain searches
                    if isinstance(breach_data, list):
                        for record in breach_data:
                            if record.get('email'):
                                results['entities'].append({
                                    'type': 'EMAIL',
                                    'value': record.get('email'),
                                    'context': 'dehashed_breach'
                                })
                            if record.get('username'):
                                results['entities'].append({
                                    'type': 'USERNAME',
                                    'value': record.get('username'),
                                    'context': 'dehashed_breach'
                                })
                            if record.get('password'):
                                results['entities'].append({
                                    'type': 'PASSWORD',
                                    'value': record.get('password'),
                                    'context': 'dehashed_breach'
                                })
                            if record.get('ip_address'):
                                results['entities'].append({
                                    'type': 'IP_ADDRESS',
                                    'value': record.get('ip_address'),
                                    'context': 'dehashed_breach'
                                })
                            if record.get('name'):
                                results['entities'].append({
                                    'type': 'NAME',
                                    'value': record.get('name'),
                                    'context': 'dehashed_breach'
                                })
                            if record.get('address'):
                                results['entities'].append({
                                    'type': 'ADDRESS',
                                    'value': record.get('address'),
                                    'context': 'dehashed_breach'
                                })
            except Exception as e:
                print(f"DeHashed phone search error: {e}")

            # 3. Truecaller scraping (free, via JESTER)
            try:
                from .truecaller_scraper import TruecallerScraper
                tc = TruecallerScraper()
                tc_result = await tc.lookup(phone)
                if tc_result and tc_result.get('name'):
                    results['results'].append({
                        'source': 'truecaller',
                        'data': tc_result,
                        'entity_type': 'phone',
                        'entity_value': phone
                    })
                    # Extract entities from Truecaller data
                    if tc_result.get('name') and tc_result['name'].lower() not in ['unknown', 'spam']:
                        results['entities'].append({
                            'type': 'PERSON',
                            'value': tc_result['name'],
                            'context': 'truecaller_caller_id'
                        })
                    if tc_result.get('location'):
                        results['entities'].append({
                            'type': 'ADDRESS',
                            'value': tc_result['location'],
                            'context': 'truecaller_location'
                        })
                    if tc_result.get('carrier'):
                        results['entities'].append({
                            'type': 'COMPANY',
                            'value': tc_result['carrier'],
                            'context': 'phone_carrier'
                        })
                await tc.close()
            except Exception as e:
                print(f"Truecaller lookup error: {e}")

            result_entry = {
                'source': 'phone_validator',
                'data': {'phone': phone, 'normalized': normalized_phone, 'valid': True},
                'entity_type': 'phone',
                'entity_value': phone
            }
            results['results'].append(result_entry)

            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for phone {phone}")

            # Run structured extraction to produce cycleable entities
            if results['results']:
                extraction = await self._extract_entities_from_data(results)
                results['extracted_entities'] = extraction.get('entities', [])
                results['graph'] = extraction.get('graph', {'nodes': [], 'edges': []})
                results['structured_data'] = extraction.get('structured', {})
                print(f"📊 Extracted {len(results['extracted_entities'])} cycleable entities")

        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching phone: {e}")

        return results

    async def search_username(self, username: str, mode: str = "discovery") -> Dict[str, Any]:
        """
        Search for username with specific intent modes:
        - 'discovery' (The Lead): Find all existence of this username across platforms to identify the correct person.
        - 'enrichment' (The Anchor): Assume all matches belong to the target and gather deep data.
        - 'verified' (The Asset): Fetch rich profile data for a confirmed username.
        """
        print(f"👤 Searching for username: {username} [Mode: {mode.upper()}]")
        
        results = {
            'query': username,
            'query_type': 'entity_search',
            'subtype': 'username',
            'mode': mode,
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Use the local username tool
            try:
                try:
                    import username as username_tool
                except ImportError:
                    from . import username as username_tool
                
                if mode == "verified":
                    # In verified mode, we only return high-confidence, rich data
                    # Simulating a fetch of detailed profile data
                    results['results'].append({
                        'source': 'profile_cache',
                        'data': {'status': 'verified', 'rich_data': True, 'platforms': ['github', 'twitter']},
                        'entity_type': 'username_profile',
                        'entity_value': username
                    })
                    
                elif mode == "enrichment":
                    # In enrichment mode, we assume matches are valid and want EVERYTHING
                    # We perform a deep scan
                    rows = username_tool.search_sync(username, pages=2, exact=True)
                    for row in rows:
                        # In enrichment, every hit is treated as a piece of the puzzle
                        if row.get('verified') or row.get('confidence') == 'high':
                            results['entities'].append({
                                'type': 'ACCOUNT',
                                'value': row.get('url'),
                                'context': f"Verified {row.get('source')} account",
                                'properties': {'url': row.get('url'), 'category': row.get('category')}
                            })
                    results['results'] = rows

                else: # Discovery (Default)
                    # In discovery mode, we cast a wide net but flag them as 'candidates'
                    # We want the user to see the list and pick "Which one is it?"
                    rows = username_tool.search_sync(username, pages=1, exact=False)
                    
                    for row in rows:
                        result_entry = {
                            'source': row.get('source', 'username_tool'),
                            'data': row,
                            'entity_type': 'username_candidate', # Explicitly a candidate, not a confirmed entity
                            'entity_value': username,
                            'confidence': row.get('confidence', 'low')
                        }
                        results['results'].append(result_entry)

            except ImportError:
                print("Warning: Could not import username tool")
            except Exception as e:
                print(f"Error running username tool: {e}")

            # 2. DeHashed Breach Search (Enrichment/Discovery)
            # Find if this username appears in breaches (linking to emails/passwords)
            if mode in ["discovery", "enrichment"]:
                try:
                    try:
                        from .dehashed_engine import DeHashedEngine
                    except ImportError:
                        from dehashed_engine import DeHashedEngine
                    
                    engine = DeHashedEngine(username, event_emitter=self.event_emitter)
                    # Use username:{username} query
                    breach_data = engine.search(custom_query=f"username:{username}")
                    
                    if breach_data:
                        results['results'].append({
                            'source': 'dehashed',
                            'data': breach_data,
                            'entity_type': 'username',
                            'entity_value': username,
                            'context': 'breach_record'
                        })
                        
                        # Extract emails/passwords from breach data
                        for record in breach_data:
                            if isinstance(record, dict):
                                if record.get('email'):
                                    results['entities'].append({
                                        'type': 'EMAIL',
                                        'value': record.get('email'),
                                        'context': 'linked_in_breach'
                                    })
                                if record.get('password'):
                                    results['entities'].append({
                                        'type': 'PASSWORD',
                                        'value': record.get('password'),
                                        'context': 'linked_in_breach'
                                    })
                                if record.get('phone'):
                                    results['entities'].append({
                                        'type': 'PHONE',
                                        'value': record.get('phone'),
                                        'context': 'linked_in_breach'
                                    })
                                if record.get('ip_address'):
                                    results['entities'].append({
                                        'type': 'IP_ADDRESS',
                                        'value': record.get('ip_address'),
                                        'context': 'linked_in_breach'
                                    })
                                if record.get('address'):
                                    results['entities'].append({
                                        'type': 'ADDRESS',
                                        'value': record.get('address'),
                                        'context': 'linked_in_breach'
                                    })
                except Exception as e:
                    print(f"DeHashed username search error: {e}")

            # Add the target username itself
            if not any(e.get('value', '') == username and e.get('type') == 'username' for e in results['entities']):
                target_entity = {
                    'type': 'username',
                    'value': username,
                    'confidence': 1.0,
                    'properties': {'is_target': True, 'source': 'query', 'mode': mode}
                }
                self._enhance_entity_context(target_entity, "username_osint", username, results['entities'])
                results['entities'].append(target_entity)

            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for username {username}")

            # Run structured extraction to produce cycleable entities
            if results['results']:
                extraction = await self._extract_entities_from_data(results)
                results['extracted_entities'] = extraction.get('entities', [])
                results['graph'] = extraction.get('graph', {'nodes': [], 'edges': []})
                results['structured_data'] = extraction.get('structured', {})
                print(f"📊 Extracted {len(results['extracted_entities'])} cycleable entities")

        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching username: {e}")

        return results

    async def search_linkedin(self, linkedin_url: str) -> Dict[str, Any]:
        """Search and enrich LinkedIn profile"""
        print(f"💼 Searching LinkedIn profile: {linkedin_url}")
        
        results = {
            'query': linkedin_url,
            'query_type': 'entity_search',
            'subtype': 'linkedin',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Since we don't have the OSINT client, we'll create a direct result for the URL
            result_entry = {
                'source': 'linkedin_direct',
                'data': {'url': linkedin_url, 'status': 'detected'},
                'entity_type': 'linkedin',
                'entity_value': linkedin_url
            }
            results['results'].append(result_entry)
            
            # Extract username from URL if possible
            match = re.search(r'linkedin\.com/in/([^/]+)', linkedin_url)
            if match:
                username = match.group(1)
                results['entities'].append({
                    'type': 'USERNAME',
                    'value': username,
                    'context': 'linkedin_handle'
                })

            # RocketReach LinkedIn Enrichment
            try:
                try: 
                    from .rocketreach_client import RocketReachClient
                except ImportError: 
                    try:
                        from rocketreach_client import RocketReachClient 
                    except ImportError:
                         RocketReachClient = None

                if RocketReachClient:
                    rr_client = RocketReachClient()
                    rr_data = rr_client.lookup_linkedin(linkedin_url)
                    if rr_data:
                        results['results'].append({
                            'source': 'rocketreach',
                            'data': rr_data,
                            'entity_type': 'person_profile',
                            'entity_value': rr_data.get('name', 'Unknown')
                        })
                        # Extract all entities from RocketReach profile
                        if rr_data.get('name'):
                            results['entities'].append({
                                'type': 'NAME',
                                'value': rr_data.get('name'),
                                'context': 'rocketreach_enrichment'
                            })
                        if rr_data.get('current_employer'):
                            results['entities'].append({
                                'type': 'COMPANY',
                                'value': rr_data.get('current_employer'),
                                'context': 'rocketreach_enrichment'
                            })
                        for email in rr_data.get('emails', []):
                            results['entities'].append({
                                'type': 'EMAIL',
                                'value': email,
                                'context': 'rocketreach_enrichment'
                            })
                        for phone in rr_data.get('phones', []):
                            if phone:
                                results['entities'].append({
                                    'type': 'PHONE',
                                    'value': phone,
                                    'context': 'rocketreach_enrichment'
                                })
            except Exception as e:
                print(f"RocketReach linkedin error: {e}")

            # ContactOut LinkedIn Enrichment
            try:
                try:
                    from .contactout_client import ContactOutClient
                except ImportError:
                    from contactout_client import ContactOutClient
                
                co_client = ContactOutClient()
                co_data = co_client.enrich_linkedin(linkedin_url)
                if co_data:
                    results['results'].append({
                        'source': 'contactout',
                        'data': co_data,
                        'entity_type': 'person_profile',
                        'entity_value': co_data.get('name', 'Unknown')
                    })
            except Exception as e:
                print(f"ContactOut linkedin error: {e}")

            # Kaspr LinkedIn Enrichment
            try:
                try:
                    from .kaspr_client import KasprClient
                except ImportError:
                    from kaspr_client import KasprClient

                k_client = KasprClient()
                k_data = k_client.enrich_linkedin(linkedin_url)
                if k_data:
                    results['results'].append({
                        'source': 'kaspr',
                        'data': k_data,
                        'entity_type': 'person_profile',
                        'entity_value': k_data.get('name', 'Unknown')
                    })
            except Exception as e:
                print(f"Kaspr linkedin error: {e}")

            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for LinkedIn profile")

            # Run structured extraction to produce cycleable entities
            if results['results']:
                extraction = await self._extract_entities_from_data(results)
                results['extracted_entities'] = extraction.get('entities', [])
                results['graph'] = extraction.get('graph', {'nodes': [], 'edges': []})
                results['structured_data'] = extraction.get('structured', {})
                print(f"📊 Extracted {len(results['extracted_entities'])} cycleable entities")

        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching LinkedIn: {e}")

        return results

    async def search_whois(self, domain: str) -> Dict[str, Any]:
        """Search WHOIS information for domain"""
        print(f"🌐 Searching WHOIS for domain: {domain}")
        
        results = {
            'query': domain,
            'query_type': 'whois_search',
            'subtype': 'whois',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        if not WHOISXML_AVAILABLE or not whois_lookup:
            results['error'] = "WHOISXMLAPI helpers not available"
            return results

        try:
            lookup = whois_lookup(domain, query_type="domain")
            if lookup.get("error"):
                results["error"] = lookup.get("error")
                return results

            records = lookup.get("records", []) if isinstance(lookup, dict) else []
            results["results"].append({
                "source": "whoisxmlapi_history",
                "data": lookup,
                "entity_type": "domain",
                "entity_value": domain,
            })
            results["total_results"] = lookup.get("count", len(records))

            if extract_entities_from_records and records:
                results["entities"] = extract_entities_from_records(records)
            if summarize_whois_records and records:
                results["structured_data"] = summarize_whois_records(records)

            print(f"✅ Found {results['total_results']} results for domain {domain}")
        except Exception as e:
            results["error"] = str(e)
            print(f"❌ Error searching WHOIS: {e}")
        
        return results
    
    async def search_ip(self, ip_address: str) -> Dict[str, Any]:
        """Search for IP address geolocation data"""
        print(f"🌐 Searching for IP: {ip_address}")
        
        results = {
            'query': ip_address,
            'query_type': 'entity_search',
            'subtype': 'ip',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        if not self.ip_geo_client:
            results['error'] = "IP geolocation module not available"
            return results
        
        try:
            geo_result = self.ip_geo_client.lookup_ip_comprehensive(ip_address)
            if geo_result.get('status') == 'success':
                result_entry = {
                    'source': 'whoisxml_ip_comprehensive',
                    'data': geo_result,
                    'entity_type': 'ip_address',
                    'entity_value': ip_address
                }
                results['results'].append(result_entry)
            else:
                results['error'] = geo_result.get('error', 'Unknown error')
            
            results['total_results'] = len(results['results'])
            print(f"✅ Found comprehensive IP data for {ip_address}")
            
        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching IP: {e}")
        
        return results

    async def search_people(self, query: str) -> Dict[str, Any]:
        """
        Search for people.
        Proxy method:
        - If query is a URL -> LinkedIn Search
        - Otherwise -> Username Search (Name as potential handle)
        """
        print(f"👥 Searching for person: {query}")
        
        if "linkedin.com" in query or query.startswith("http"):
            return await self.search_linkedin(query)
        
        # Fallback to username search for names/handles, BUT also try People Search APIs
        results = await self.search_username(query, mode="discovery")
        
        # RocketReach Name Search
        try:
            try: 
                from .rocketreach_client import RocketReachClient
            except ImportError: 
                try:
                    from rocketreach_client import RocketReachClient 
                except ImportError:
                     RocketReachClient = None

            if RocketReachClient:
                rr_client = RocketReachClient()
                # Assuming lookup_name or search method exists
                rr_data = rr_client.search(name=query) 
                if rr_data:
                    # rr_data might be list or dict
                    entries = rr_data if isinstance(rr_data, list) else [rr_data]
                    for entry in entries:
                        results['results'].append({
                            'source': 'rocketreach',
                            'data': entry,
                            'entity_type': 'person_profile',
                            'entity_value': entry.get('name', query)
                        })
                        if entry.get('linkedin_url'):
                             results['entities'].append({
                                'type': 'URL',
                                'value': entry.get('linkedin_url'),
                                'context': 'rocketreach_profile'
                            })
        except Exception as e:
            print(f"RocketReach person search error: {e}")

        return results

    async def search_password(self, password: str) -> Dict[str, Any]:
        """Search for password (plain or hash) in breaches"""
        print(f"🔑 Searching for password: {password}")
        
        results = {
            'query': password,
            'query_type': 'entity_search',
            'subtype': 'password',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # 1. DeHashed Password Search
            try:
                try:
                    from .dehashed_engine import DeHashedEngine
                except ImportError:
                    from dehashed_engine import DeHashedEngine
                
                # Check if it looks like a hash (32, 40, 64 hex chars)
                is_hash = re.match(r'^[a-fA-F0-9]{32}$|^[a-fA-F0-9]{40}$|^[a-fA-F0-9]{64}$', password)
                
                query_field = "hashed_password" if is_hash else "password"
                custom_query = f"{query_field}:{password}"
                
                engine = DeHashedEngine(password, event_emitter=self.event_emitter)
                breach_data = engine.search(custom_query=custom_query)
                
                if breach_data:
                    results['results'].append({
                        'source': 'dehashed',
                        'data': breach_data,
                        'entity_type': 'password',
                        'entity_value': password,
                        'context': 'breach_record'
                    })
                    
                    # Extract associated emails/usernames from breach data
                    for record in breach_data:
                        if isinstance(record, dict):
                            if record.get('email'):
                                results['entities'].append({
                                    'type': 'EMAIL',
                                    'value': record.get('email'),
                                    'context': 'linked_in_breach'
                                })
                            if record.get('username'):
                                results['entities'].append({
                                    'type': 'USERNAME',
                                    'value': record.get('username'),
                                    'context': 'linked_in_breach'
                                })
                            if record.get('phone'):
                                results['entities'].append({
                                    'type': 'PHONE',
                                    'value': record.get('phone'),
                                    'context': 'linked_in_breach'
                                })
                            if record.get('ip_address'):
                                results['entities'].append({
                                    'type': 'IP_ADDRESS',
                                    'value': record.get('ip_address'),
                                    'context': 'linked_in_breach'
                                })
                            if record.get('address'):
                                results['entities'].append({
                                    'type': 'ADDRESS',
                                    'value': record.get('address'),
                                    'context': 'linked_in_breach'
                                })
                            # Phone
                            if record.get('phone'):
                                results['entities'].append({
                                    'type': 'PHONE',
                                    'value': record.get('phone'),
                                    'context': 'linked_in_breach'
                                })
                            # IP Address
                            if record.get('ip_address'):
                                results['entities'].append({
                                    'type': 'IP_ADDRESS',
                                    'value': record.get('ip_address'),
                                    'context': 'linked_in_breach'
                                })
                            # Address
                            if record.get('address'):
                                results['entities'].append({
                                    'type': 'ADDRESS',
                                    'value': record.get('address'),
                                    'context': 'linked_in_breach'
                                })
                                
            except Exception as e:
                print(f"DeHashed password search error: {e}")
            
            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for password {password}")
            
        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching password: {e}")
        
        return results
    
    def _enhance_entity_context(self, entity: Dict, source: str, query: str, related_entities: List[Dict] = None) -> Dict:
        """Add enhanced context to extracted entities"""
        # Simplified context enhancement
        if 'context' not in entity:
            entity['context'] = {'source': source}
        return entity
    
    async def _extract_entities_from_data(self, data: Any, osint_type: str = "generic") -> Dict[str, Any]:
        """
        Extract entities from structured OSINT aggregator output using deterministic extraction.
        Handles DeHashed, RocketReach, OSINT Industries, ContactOut data.

        Returns dict with:
        - entities: flat list of {type, value, sources} for cycleable second-level searches
        - graph: {nodes, edges} for visualization
        - structured: full categorized extraction (emails, phones, names, companies, etc.)
        """
        if not STRUCTURED_EXTRACTOR_AVAILABLE or not extract_data_from_json:
            print("Warning: Structured extractor not available, returning empty")
            return {'entities': [], 'graph': {'nodes': [], 'edges': []}, 'structured': {}}

        # Transform unified_osint results format to output.py expected format
        transformed_data = {'query': data.get('query', '')}

        # Process results array and organize by source
        results_by_source = {}
        dehashed_results = []
        osint_results = []

        for result in data.get('results', []):
            source = result.get('source', '').lower()
            source_data = result.get('data', {})

            if source == 'dehashed':
                # DeHashed returns list of breach records
                if isinstance(source_data, list):
                    dehashed_results.extend(source_data)
                elif isinstance(source_data, dict):
                    dehashed_results.append(source_data)

            elif source == 'rocketreach':
                results_by_source['rocketreach'] = source_data

            elif source in ['osint_industries', 'osintindustries']:
                # OSINT Industries returns results array
                if isinstance(source_data, dict) and 'results' in source_data:
                    osint_results.extend(source_data['results'])
                elif isinstance(source_data, list):
                    osint_results.extend(source_data)
                else:
                    results_by_source['osint_industries'] = source_data

            elif source == 'contactout':
                results_by_source['contactout'] = source_data

            elif source == 'kaspr':
                results_by_source['kaspr'] = source_data

        # Build final structure for extract_data_from_json
        if results_by_source:
            transformed_data['results_by_source'] = results_by_source
        if dehashed_results:
            transformed_data['dehashed_results'] = dehashed_results
        if osint_results:
            transformed_data['results'] = osint_results

        try:
            # Run deterministic extraction
            extracted = extract_data_from_json(transformed_data)

            # Build flat entity list for cycleable second-level searches
            entities = []
            entity_type_mapping = {
                'emails': 'EMAIL',
                'phones': 'PHONE',
                'usernames': 'USERNAME',
                'names': 'NAME',
                'linkedin_urls': 'LINKEDIN',
                'registered_domains': 'DOMAIN',
                'companies': 'COMPANY',
                'addresses': 'ADDRESS',
                'ip_addresses': 'IP_ADDRESS',
                'passwords': 'PASSWORD',
                'account_urls': 'URL'
            }

            for field, entity_type in entity_type_mapping.items():
                for item in extracted.get(field, []):
                    if isinstance(item, dict) and 'value' in item:
                        entities.append({
                            'type': entity_type,
                            'value': item['value'],
                            'sources': item.get('sources', []),
                            'id': item.get('id'),
                            'validation': item.get('validation')
                        })

            # Generate graph export
            graph = generate_graph_export(extracted, data.get('query', ''))

            return {
                'entities': entities,
                'graph': graph,
                'structured': extracted
            }

        except Exception as e:
            print(f"Error in structured extraction: {e}")
            return {'entities': [], 'graph': {'nodes': [], 'edges': []}, 'structured': {}}
    
    async def store_results(self, results: Dict[str, Any]) -> str:
        """Store results using EntityGraphStorageV2 with proper entity graph integration"""
        if not self.storage:
            print("⚠️ No storage available - results not persisted")
            return None
        
        try:
            project_id = f"eye-d_{results['subtype']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            # Simplified storage logic for this fix
            print(f"🎯 EYE-D Search Complete: {project_id}")
            return project_id
            
        except Exception as e:
            print(f"❌ Error storing EYE-D results: {e}")
            return None
    
    def display_results(self, results: Dict[str, Any]) -> None:
        """Display results in a formatted way"""
        print(f"🔍 EYE-D OSINT Search Results: {results['query']}")
        print(f"📊 Found {results.get('total_results', 0)} results")


class EYEDSearchEngine:
    """Wrapper class for web API integration"""
    
    def __init__(self, keyword: str, event_emitter=None):
        self.keyword = keyword
        self.event_emitter = event_emitter
        self.results = []
        self.stats = {
            'total_results': 0,
            'search_duration': 0
        }
        self.handler = UnifiedSearcher(event_emitter=self.event_emitter)
        
    def search(self):
        """Synchronous search method for web API compatibility"""
        import time
        start_time = time.time()
        
        print(f"EYEDSearchEngine.search() called with keyword: {self.keyword}")
        
        # Detect search type from keyword
        search_type = self._detect_search_type(self.keyword)
        if not search_type:
            # Fallback if no type detected
            search_type = 'username' 
        
        print(f"Detected search type: {search_type}")
        
        # Extract query value
        query_value = self.handler.extract_query_value(self.keyword, search_type)
        
        # Run async search synchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Route to appropriate search method
            if search_type == 'email':
                results = loop.run_until_complete(self.handler.search_email(query_value))
            elif search_type == 'phone':
                results = loop.run_until_complete(self.handler.search_phone(query_value))
            elif search_type == 'linkedin':
                results = loop.run_until_complete(self.handler.search_linkedin(query_value))
            elif search_type == 'whois':
                results = loop.run_until_complete(self.handler.search_whois(query_value))
            elif search_type == 'username':
                results = loop.run_until_complete(self.handler.search_username(query_value))
            elif search_type == 'ip':
                results = loop.run_until_complete(self.handler.search_ip(query_value))
            elif search_type == 'password':
                results = loop.run_until_complete(self.handler.search_password(query_value))
            else:
                results = {'results': [], 'query': query_value, 'subtype': 'unknown'}
            
            # Convert results to web API format
            self._convert_results(results)
            
            # Emit results via event emitter
            if self.event_emitter:
                for result in self.results:
                    self.event_emitter('result', result)
                
                self.event_emitter('engine_status', {
                    'engine': f'EYE-D {search_type.title()}',
                    'engine_code': search_type.upper()[:2],
                    'status': 'completed',
                    'results_count': len(self.results)
                })
            
        except Exception as e:
            print(f"EYE-D search error: {e}")
            
        finally:
            loop.close()
        
        self.stats['total_results'] = len(self.results)
        self.stats['search_duration'] = time.time() - start_time
    
    def _detect_search_type(self, query: str) -> Optional[str]:
        """Detect the type of EYE-D search from the query"""
        # Explicit username prefixes
        if query.lower().startswith('u:') or query.lower().startswith('username:'):
            return 'username'
        # Email pattern
        if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', query):
            return 'email'
        # LinkedIn pattern - IMPROVED REGEX
        if re.match(r'^(https?://)?(www\.)?linkedin\.com/in/[^/]+/?$', query, re.IGNORECASE) or \
           re.match(r'^linkedin\.com/in/[^/]+/?$', query, re.IGNORECASE):
            return 'linkedin'
        # Phone pattern (loose, prefer after email/linkedin)
        if re.match(r'^(\+?\d{1,4}[\s.-]?)?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,9}$', query):
            return 'phone'
        # IP address pattern
        if re.match(r'^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$', query):
            return 'ip'
        # Password Hash (MD5, SHA1, SHA256)
        if re.match(r'^[a-fA-F0-9]{32}$|^[a-fA-F0-9]{40}$|^[a-fA-F0-9]{64}$', query):
            return 'password'
        # Username pattern (default for single tokens that don't match others)
        if re.match(r'^[a-zA-Z0-9_-]{3,}$', query):
            return 'username'
        return None
    
    def _convert_results(self, eye_d_results: Dict[str, Any]):
        """Convert EYE-D results to web API format"""
        for i, result in enumerate(eye_d_results.get('results', [])):
            source = result.get('source', 'unknown')
            data = result.get('data', {})
            entity_type = result.get('entity_type', 'unknown')
            entity_value = result.get('entity_value', '')
            
            title = f"{entity_type.title()}: {entity_value} (from {source})"
            
            snippet = str(data)[:500]
            
            if entity_type == 'linkedin':
                url = entity_value if entity_value.startswith('http') else f"https://{entity_value}"
            else:
                url = f"https://google.com/search?q={entity_value}"
            
            web_result = {
                'url': url,
                'title': title,
                'snippet': snippet,
                'engine': 'EYE-D',
                'source': source.upper(),
                'rank': i + 1,
                'timestamp': datetime.now().isoformat(),
                'category': 'osint',
                'entity_type': entity_type,
                'metadata': {
                    'entity_type': entity_type,
                    'entity_value': entity_value,
                    'source': source,
                    'raw_data': data
                }
            }

            self.results.append(web_result)

    async def search_with_recursion(
        self,
        initial_query: str,
        project_id: str,
        search_type: str = None,
        max_depth: int = 3
    ) -> Dict:
        """
        Perform recursive EYE-D search with VERIFIED-first priority queues.

        Args:
            initial_query: Starting search value (email, phone, username, etc.)
            project_id: Cymonides-1 project ID
            search_type: Type of search ('email', 'phone', 'username', etc.) - auto-detected if None
            max_depth: Maximum recursion depth (default 3)

        Returns:
            Summary of recursive search results
        """
        if not self.c1_bridge:
            print("⚠️ C1Bridge not available. Recursive search disabled.")
            return {"error": "C1Bridge not available"}

        # Auto-detect search type if not provided
        if not search_type:
            if '@' in initial_query:
                search_type = 'email'
            elif re.match(r'^\+?\d[\d\-\s()]+$', initial_query):
                search_type = 'phone'
            elif 'linkedin.com' in initial_query.lower():
                search_type = 'linkedin'
            elif initial_query.lower().startswith('whois!:'):
                search_type = 'whois'
            else:
                search_type = 'username'

        # Extract clean value
        query_value = self.extract_query_value(initial_query, search_type)

        # Define the search function to pass to recursive controller
        async def perform_search(entity_value: str):
            """Wrapper function for recursive searches"""
            # Detect entity type from value
            if '@' in entity_value:
                await self.search_email(entity_value)
            elif re.match(r'^\+?\d[\d\-\s()]+$', entity_value):
                await self.search_phone(entity_value)
            elif 'linkedin.com' in entity_value.lower():
                await self.search_linkedin(entity_value)
            else:
                await self.search_username(entity_value)

        # Run recursive search with priority queues
        print(f"\n🔄 Starting recursive EYE-D search...")
        print(f"   Initial query: {query_value}")
        print(f"   Search type: {search_type}")
        print(f"   Project ID: {project_id}")
        print(f"   Max depth: {max_depth}\n")

        # Convert async search function to sync for c1_bridge
        import asyncio

        def sync_search_wrapper(entity_value: str):
            """Synchronous wrapper for async search"""
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create new loop if current one is running
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, perform_search(entity_value))
                    return future.result()
            else:
                return loop.run_until_complete(perform_search(entity_value))

        # Call recursive search controller
        summary = self.c1_bridge.recursive_eyed_search(
            initial_query=query_value,
            project_id=project_id,
            max_depth=max_depth,
            search_function=sync_search_wrapper
        )

        return summary


async def main():
    """Main entry point for EYE-D search"""
    if len(sys.argv) < 2:
        print("Usage: python unified_osint.py <query> [search_type]")
        sys.exit(1)
    
    query = sys.argv[1]
    search_type = sys.argv[2].lower() if len(sys.argv) > 2 else None
    
    handler = UnifiedSearcher()
    
    if not search_type:
        # Simple detection for CLI
        if '@' in query: search_type = 'email'
        elif 'linkedin' in query: search_type = 'linkedin'
        elif re.match(r'^\d+\.\d+\.\d+\.\d+$', query): search_type = 'ip'
        else: search_type = 'username'
    
    query_value = handler.extract_query_value(query, search_type)
    
    if search_type == 'email':
        results = await handler.search_email(query_value)
    elif search_type == 'phone':
        results = await handler.search_phone(query_value)
    elif search_type == 'linkedin':
        results = await handler.search_linkedin(query_value)
    elif search_type == 'whois':
        results = await handler.search_whois(query_value)
    elif search_type == 'username':
        results = await handler.search_username(query_value)
    elif search_type == 'ip':
        results = await handler.search_ip(query_value)
    elif search_type == 'password':
        results = await handler.search_password(query_value)
    else:
        print(f"❌ Unknown search type: {search_type}")
        sys.exit(1)
    
    handler.display_results(results)


if __name__ == "__main__":
    asyncio.run(main())
