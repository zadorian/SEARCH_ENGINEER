#!/usr/bin/env python3
"""
Web server for DeHashed visualization
Acts as a proxy to handle DeHashed API requests
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json
import re
import os
import time
import hashlib
import anthropic
import pickle
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
import urllib.parse
import logging
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
from dotenv import load_dotenv
import aiohttp
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor

# Ensure repo root is importable for in-repo modules (LINKLATER, BRUTE, etc.)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Cymonides-1 (C-1) graph integration (Elasticsearch-backed)
try:
    from LINKLATER.c1_bridge import C1Bridge, C1Node
    C1_AVAILABLE = True
except Exception as e:
    print(f"Warning: C1Bridge not available. C-1 integration disabled. Error: {e}")
    C1_AVAILABLE = False
    C1Bridge = None
    C1Node = None

# Add parent directory to path to import whois module
try:
    import whois
except ImportError:
    print("Warning: whois module not found. WHOIS functionality will be disabled.")
    whois = None

# Import ExactPhraseRecallRunner
try:
    from exact_phrase_recall_runner import ExactPhraseRecallRunner, chunk_sites, generate_base_queries
except ImportError:
    print("Warning: ExactPhraseRecallRunner not found. Exhaustive search will be disabled.")
    ExactPhraseRecallRunner = None

# Import OSINT Industries module
try:
    import osintindustries
except ImportError:
    print("Warning: osintindustries module not found. OSINT functionality will be disabled.")
    osintindustries = None

# Import people search modules
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import rocketreach
    ROCKETREACH_AVAILABLE = True
except ImportError:
    print("Warning: rocketreach module not found. RocketReach functionality will be disabled.")
    rocketreach = None
    ROCKETREACH_AVAILABLE = False

try:
    import kaspr
    KASPR_AVAILABLE = True
except ImportError:
    print("Warning: kaspr module not found. Kaspr functionality will be disabled.")
    kaspr = None
    KASPR_AVAILABLE = False

try:
    import contactout
    CONTACTOUT_AVAILABLE = True
except ImportError:
    print("Warning: contactout module not found. ContactOut functionality will be disabled.")
    contactout = None
    CONTACTOUT_AVAILABLE = False

# Import project management module
from projects import ProjectManager

# Import SE's EntityGraphStorageV2 for bidirectional sync
try:
    sys.path.insert(0, '/Users/attic/SE/WEBAPP')
    from Indexer.entity_graph_storage_v2 import EntityGraphStorageV2
    SE_STORAGE_AVAILABLE = True
    print("✓ EntityGraphStorageV2 imported successfully for SE Grid sync")
except ImportError as e:
    print(f"Warning: EntityGraphStorageV2 not available. SE Grid sync disabled. Error: {e}")
    SE_STORAGE_AVAILABLE = False

# Import entity project manager if available
try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / 'GARSON' / 'cog_chatbot' / 'cont_int'))
    from entity_project_manager import EntityProjectManager
    entity_pm = EntityProjectManager()
except ImportError:
    print("Warning: EntityProjectManager not found. Entity features will be disabled.")
    entity_pm = None

# Import LINKLATER for ownership-linked domains (?owl operator)
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from modules.LINKLATER.discovery.whois_discovery import cluster_domains_by_whois
    LINKLATER_AVAILABLE = True
    print("✓ LINKLATER imported successfully for ownership-linked discovery")
except ImportError as e:
    print(f"Warning: LINKLATER not available. ?owl operator disabled. Error: {e}")
    cluster_domains_by_whois = None
    LINKLATER_AVAILABLE = False

# Load environment variables from .env file FIRST (before any os.getenv calls)
load_dotenv()

# Google Custom Search API
# Required: Set GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID in .env file
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID') or os.getenv('GOOGLE_CX')

if not GOOGLE_API_KEY:
    print("⚠️  WARNING: GOOGLE_API_KEY not set in environment variables")
if not GOOGLE_SEARCH_ENGINE_ID:
    print("⚠️  WARNING: GOOGLE_SEARCH_ENGINE_ID not set in environment variables")

# USER'S WORKING GOOGLE SEARCH CLASS
class GoogleSearch:
    """
    Your proven GoogleSearch class that works in other applications
    """
    def __init__(self):
        self.api_key = GOOGLE_API_KEY
        self.search_engine_id = GOOGLE_SEARCH_ENGINE_ID
        
    def google_base(self, query: str, max_results: int = 10) -> Tuple[List[Dict], Optional[int]]:
        """
        Your proven google_base method that returns rich results
        Returns: (hits_list, estimated_count)
        hits_list contains: {'url': '...', 'title': '...', 'snippet': '...'}
        """
        try:
            all_results = []
            
            # Google allows max 10 results per request, so paginate if needed
            for start_index in range(1, min(max_results + 1, 101), 10):  # API limit is 100 results
                search_url = 'https://www.googleapis.com/customsearch/v1'
                params = {
                    'key': self.api_key,
                    'cx': self.search_engine_id,
                    'q': query,
                    'start': start_index,
                    'num': min(10, max_results - len(all_results))
                }
                
                print(f"🔍 Google API request {start_index//10 + 1}: {search_url}")
                print(f"📊 Params: {params}")
                
                response = requests.get(search_url, params=params, timeout=30)
                response.raise_for_status()
                
                results = response.json()
                
                # Extract results in your proven format
                if 'items' in results:
                    for item in results['items']:
                        result = {
                            'url': item.get('link', ''),
                            'title': item.get('title', '[No Title]'),
                            'snippet': item.get('snippet', '[No Snippet]'),
                            'found_by_query': query
                        }
                        all_results.append(result)
                        print(f"📌 Found result: {result['title']}")
                        print(f"   URL: {result['url']}")
                        print(f"   Snippet: {result['snippet']}")
                
                # Get estimated count from first response
                estimated_count = results.get('searchInformation', {}).get('totalResults')
                if estimated_count:
                    estimated_count = int(estimated_count)
                
                # Stop if we have enough results or no more available
                if len(all_results) >= max_results or 'items' not in results or len(results['items']) < 10:
                    break
                    
            print(f"✅ Google search completed: {len(all_results)} results for '{query}'")
            return all_results, estimated_count
            
        except Exception as e:
            print(f"❌ Google search failed: {e}")
            return [], None

# Firecrawl API Configuration
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')
FIRECRAWL_API_URL = 'https://api.firecrawl.dev/v1/scrape'

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent

# SECURITY: Restrict CORS to specific origins only
# Add your frontend URLs here
ALLOWED_ORIGINS = [
    'http://localhost:5000',  # EYE-D frontend
    'http://localhost:5173',  # WIKIMAN-PRO frontend
    'http://localhost:8002',  # SE (Search Engineer) frontend
    'http://127.0.0.1:5000',
    'http://127.0.0.1:5173',
    'http://127.0.0.1:8002'  # SE (Search Engineer) frontend
]
CORS(app, origins=ALLOWED_ORIGINS)

# DeHashed API Configuration
# Required: Set DEHASHED_API_KEY in .env file
DEHASHED_API_KEY = os.getenv('DEHASHED_API_KEY')

if not DEHASHED_API_KEY:
    print("⚠️  WARNING: DEHASHED_API_KEY not set in environment variables")

# Anthropic Claude API Configuration
# Required: Set ANTHROPIC_API_KEY in .env file
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

if not ANTHROPIC_API_KEY:
    print("⚠️  WARNING: ANTHROPIC_API_KEY not set in environment variables")
    anthropic_client = None
else:
    try:
        # Create httpx client without proxy support to avoid compatibility issues
        import httpx
        http_client = httpx.Client(
            timeout=60.0,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
        anthropic_client = anthropic.Anthropic(
            api_key=ANTHROPIC_API_KEY,
            http_client=http_client,
            max_retries=2
        )
        print("✓ Anthropic client initialized successfully")
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize Anthropic client: {e}")
        anthropic_client = None

# Corporate search API keys
# OpenCorporates - Works without API key but with rate limits
# DEPRECATED: OpenCorporates removed - use Corporella at /data/corporella/
# Required: Set OPENCORPORATES_API_KEY in .env file
OPENCORPORATES_API_KEY = os.getenv('OPENCORPORATES_API_KEY')
if OPENCORPORATES_API_KEY:
    os.environ['OPENCORPORATES_API_KEY'] = OPENCORPORATES_API_KEY
else:
    print("⚠️  WARNING: OPENCORPORATES_API_KEY not set - API rate limits will apply")

# OCCRP Aleph - Get your API key from https://aleph.occrp.org/
# Required: Set ALEPH_API_KEY in .env file
ALEPH_API_KEY = os.getenv('ALEPH_API_KEY')
if ALEPH_API_KEY:
    os.environ['ALEPH_API_KEY'] = ALEPH_API_KEY
else:
    print("⚠️  WARNING: ALEPH_API_KEY not set - Aleph searches will fail")

# Ahrefs API configuration
AHREFS_API_KEY = os.getenv('AHREFS_API_KEY')
AHREFS_ENDPOINT = "https://apiv2.ahrefs.com"

# Cache file paths
CACHE_DIR = Path(__file__).parent / 'cache'
CACHE_DIR.mkdir(exist_ok=True)
SEARCH_CACHE_FILE = CACHE_DIR / 'search_cache.pkl'
GRAPH_STATE_FILE = CACHE_DIR / 'graph_state.json'

# Initialize project manager
project_manager = ProjectManager(db_path=str(CACHE_DIR / 'projects.db'))

# -----------------------------------------------------------------------------
# Cymonides-1 (C-1) Elasticsearch graph helpers
# -----------------------------------------------------------------------------

def _c1_validate_project_id(project_id: str) -> str:
    """Validate and normalize projectId used in cymonides-1-{projectId} index names."""
    if not project_id or not isinstance(project_id, str):
        raise ValueError("projectId is required")

    project_id = project_id.strip()
    if not project_id:
        raise ValueError("projectId is required")

    # Elasticsearch index name must be lowercase and cannot contain certain chars.
    # We allow common UUID-ish / slug-ish IDs.
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,127}$", project_id):
        raise ValueError("projectId contains invalid characters")

    return project_id


def _c1_generate_id(value: str, node_type: str) -> str:
    key = f"{node_type}:{(value or '').lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _c1_ui_type_to_c1(ui_type: str, node_data: Optional[Dict] = None) -> Tuple[str, str, str]:
    """
    Map EYE-D UI node type -> (node_class, c1_type, original_type).

    Returns:
      node_class: "entity" | "source"
      c1_type: cymonides-1 typeName
      original_type: original UI type string (for metadata)
    """
    original = (ui_type or "unknown").strip().lower()
    if original in ("url", "webpage"):
        return ("source", "webpage", original)
    if original in ("ip", "ip_address"):
        return ("entity", "ip", original)
    if original in ("name", "person"):
        return ("entity", "person", original)
    if original in ("company", "organization", "org"):
        return ("entity", "company", original)
    if original in ("email", "phone", "username", "domain"):
        return ("entity", original, original)
    if original in ("password", "hashed_password", "hash"):
        return ("entity", "password", original)

    # Fallback: keep as generic entity
    return ("entity", "entity", original)


def _c1_c1_type_to_ui(c1_type: str, metadata: Optional[Dict] = None, label: str = "") -> str:
    """Map cymonides-1 typeName -> EYE-D UI node type."""
    t = (c1_type or "entity").strip().lower()
    if t == "webpage":
        return "url"
    if t == "ip":
        return "ip_address"
    if t == "person":
        return "name"
    if t == "password":
        # Preserve hashed vs plain when we can.
        original_type = ""
        if isinstance(metadata, dict):
            original_type = str(metadata.get("original_type") or metadata.get("ui_type") or "")
        if original_type.lower() in ("hashed_password", "hash", "hashed"):
            return "hashed_password"
        if re.fullmatch(r"[a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", (label or "").strip()):
            return "hashed_password"
        return "password"
    if t in ("email", "phone", "username", "domain", "company"):
        return t

    return "unknown"


def _c1_extract_position(metadata: Optional[Dict]) -> Tuple[Optional[float], Optional[float]]:
    if not isinstance(metadata, dict):
        return (None, None)

    pos = metadata.get("position")
    if isinstance(pos, dict):
        x = pos.get("x")
        y = pos.get("y")
        try:
            return (float(x) if x is not None else None, float(y) if y is not None else None)
        except Exception:
            return (None, None)

    # Also accept flat x/y keys for backward compatibility
    try:
        x = metadata.get("x")
        y = metadata.get("y")
        if x is None or y is None:
            return (None, None)
        return (float(x), float(y))
    except Exception:
        return (None, None)


def should_clean_with_claude(text):
    """
    Check if text contains malformed characters that need Claude cleaning.
    Returns True if text has } or ] or other malformed patterns.
    """
    if not text or not isinstance(text, str):
        return False
    
    # Check for malformed patterns that indicate corrupted data
    malformed_patterns = [
        r'[}\]]',  # Contains } or ]
        r':\w+=>',  # Contains key-value patterns like :Kod_statu=>
        r'[{\[].*[}\]]',  # Contains bracket/brace pairs
        r'^["\'>:=]+',  # Starts with quotes/special chars
    ]
    
    for pattern in malformed_patterns:
        if re.search(pattern, text):
            return True
    
    return False

def clean_with_claude(malformed_text):
    """
    Use Claude to clean malformed address/node text and make it comprehensible.
    """
    try:
        message = f"""Please clean this malformed address/location text and make it comprehensible. 
The text appears to be corrupted data from OpenCorporates or similar sources.
Return ONLY the cleaned, readable address without any explanation:

Malformed text: {malformed_text}"""

        response = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": message}]
        )
        
        cleaned = response.content[0].text.strip()
        print(f"Claude cleaned: '{malformed_text}' -> '{cleaned}'")
        return cleaned
        
    except Exception as e:
        print(f"Error cleaning with Claude: {e}")
        # Fallback: just remove obvious malformed parts
        fallback = re.sub(r'[}\]\[\{:=>"\'>]', '', malformed_text).strip()
        return fallback if fallback else 'Cleaned Address'

def normalize_phone_number(phone):
    """
    Normalize phone number for OSINT Industries search.
    Returns multiple variants to try: with/without country code, with/without leading zero.
    """
    # Remove all non-digit characters
    digits_only = re.sub(r'[^\d]', '', phone)
    
    variants = []
    
    # If it starts with + or country code, try multiple formats
    if phone.startswith('+1') or phone.startswith('1') and len(digits_only) == 11:
        # US number
        if digits_only.startswith('1'):
            us_number = digits_only[1:]  # Remove leading 1
        else:
            us_number = digits_only
        
        variants.extend([
            digits_only,           # Full number with country code
            us_number,            # Without country code
            f"1{us_number}",      # With 1 prefix
        ])
    
    elif phone.startswith('+44') or (phone.startswith('44') and len(digits_only) > 10):
        # UK number
        if digits_only.startswith('44'):
            uk_number = digits_only[2:]  # Remove 44
        else:
            uk_number = digits_only
            
        # UK numbers might start with 0 when dialed domestically
        if uk_number.startswith('0'):
            uk_without_zero = uk_number[1:]
        else:
            uk_without_zero = uk_number
            uk_number = f"0{uk_number}"
            
        variants.extend([
            digits_only,           # Full international
            uk_number,            # With leading 0
            uk_without_zero,      # Without leading 0
            f"44{uk_without_zero}", # International format
        ])
    
    elif len(digits_only) >= 10:
        # Generic international or long domestic number
        variants.append(digits_only)
        
        # Try with/without leading zero
        if digits_only.startswith('0') and len(digits_only) > 10:
            variants.append(digits_only[1:])
        elif not digits_only.startswith('0'):
            variants.append(f"0{digits_only}")
            
        # Try common country codes
        if len(digits_only) == 10:
            variants.extend([
                f"1{digits_only}",    # US
                f"44{digits_only}",   # UK  
                f"49{digits_only}",   # Germany
                f"33{digits_only}",   # France
            ])
    
    else:
        # Short number, just use as-is
        variants.append(digits_only)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variants = []
    for variant in variants:
        if variant and variant not in seen:
            seen.add(variant)
            unique_variants.append(variant)
    
    print(f"Phone normalization: '{phone}' -> {unique_variants}")
    return unique_variants

@app.route('/')
def serve_index():
    return send_from_directory(str(BASE_DIR), 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(str(BASE_DIR), path)

@app.route('/api/search', methods=['POST'])
def search():
    try:
        data = request.json
        query = data.get('query', '')
        query_type = data.get('type', None)
        size = data.get('size', 100)  # Smaller default for web display
        page = data.get('page', 1)
        
        if not query:
            return jsonify({'error': 'Query parameter is required'}), 400
        
        # Auto-detect query type if not provided
        if not query_type:
            if '@' in query:
                query_type = 'email'
            elif re.match(r'^\+?\d[\d\s\-\(\)\.]{6,}$', query.strip()):
                query_type = 'phone'
            elif re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$', query):
                query_type = 'domain'
            elif re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', query):
                query_type = 'ip_address'
            elif re.match(r'^[a-fA-F0-9]{32}$', query):
                query_type = 'hashed_password'
            elif re.match(r'^[a-fA-F0-9]{40}$', query):
                query_type = 'hashed_password'
            elif re.match(r'^[a-fA-F0-9]{64}$', query):
                query_type = 'hashed_password'
            else:
                query_type = 'blanket_search'
        
        # Construct search query string
        search_query_string = ''
        if query_type == 'email':
            search_query_string = f'email:"{query}"'
        elif query_type == 'username':
            search_query_string = f'username:"{query}"'
        elif query_type == 'phone':
            clean_phone = re.sub(r'[^\d]', '', query)
            search_query_string = f'phone:"{clean_phone}"'
        elif query_type == 'domain':
            search_query_string = f'domain:"{query}"'
        elif query_type == 'name':
            search_query_string = f'name:"{query}"'
        elif query_type == 'ip_address':
            search_query_string = f'ip_address:"{query}"'
        elif query_type == 'password':
            search_query_string = f'password:"{query}"'
        elif query_type == 'hashed_password':
            search_query_string = f'hashed_password:"{query}"'
        elif query_type == 'database_name':
            search_query_string = f'database_name:"{query}"'
        elif query_type == 'blanket_search':
            search_query_string = f'"{query}"'
        else:
            search_query_string = f'"{query}"'
        
        # Make request to DeHashed API
        url = 'https://api.dehashed.com/v2/search'
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Dehashed-Api-Key': DEHASHED_API_KEY
        }
        payload = {
            "query": search_query_string,
            "page": page,
            "size": size,
            "regex": False,
            "wildcard": False,
            "de_dupe": False
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'entries' not in data:
                return jsonify({'error': 'No entries found', 'results': []})
            
            results = data.get('entries', [])
            total = data.get('total', len(results))
            balance = data.get('balance', 'N/A')
            
            return jsonify({
                'results': results,
                'total': total,
                'balance': balance,
                'query': query,
                'query_type': query_type
            })
            
        elif response.status_code == 401:
            return jsonify({'error': 'Authentication failed'}), 401
        elif response.status_code == 429:
            return jsonify({'error': 'Rate limit exceeded'}), 429
        else:
            return jsonify({'error': f'API Error: {response.status_code}'}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-suggestions', methods=['POST'])
def ai_suggestions():
    try:
        data = request.json
        
        # Extract the messages from the request
        messages = data.get('messages', [])
        model = data.get('model', 'claude-sonnet-4-5-20250929')
        max_tokens = data.get('max_tokens', 1000)
        temperature = data.get('temperature', 0.7)
        
        if not messages:
            return jsonify({'error': 'No messages provided'}), 400
        
        # Extract system message if present
        system_message = None
        user_messages = []
        
        for msg in messages:
            if msg.get('role') == 'system':
                system_message = msg.get('content', '')
            else:
                user_messages.append(msg)
        
        # Call Anthropic API with system as a parameter
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_message if system_message else None,
            messages=user_messages
        )
        
        return jsonify({
            'content': response.content,
            'usage': response.usage.model_dump() if hasattr(response, 'usage') else None
        })
        
    except anthropic.APIError as e:
        return jsonify({'error': f'Anthropic API error: {str(e)}'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-chat', methods=['POST'])
def ai_chat():
    try:
        data = request.json
        
        # Extract the messages from the request
        messages = data.get('messages', [])
        model = data.get('model', 'claude-opus-4-20250514')
        max_tokens = data.get('max_tokens', 800)
        temperature = data.get('temperature', 0.7)
        
        if not messages:
            return jsonify({'error': 'No messages provided'}), 400
        
        # Extract system message if present
        system_message = None
        user_messages = []
        
        for msg in messages:
            if msg.get('role') == 'system':
                system_message = msg.get('content', '')
            else:
                user_messages.append(msg)
        
        # Call Anthropic API for chat with system as a parameter
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_message if system_message else None,
            messages=user_messages
        )
        
        return jsonify({
            'content': [{'text': response.content[0].text}] if response.content else [],
            'usage': response.usage.model_dump() if hasattr(response, 'usage') else None
        })
        
    except anthropic.APIError as e:
        return jsonify({'error': f'Anthropic API error: {str(e)}'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/load', methods=['GET'])
def load_cache():
    """Load cache from disk"""
    try:
        cache_data = {
            'search_cache': {},
            'graph_state': {}
        }
        
        # Load search cache
        if SEARCH_CACHE_FILE.exists():
            with open(SEARCH_CACHE_FILE, 'rb') as f:
                cache_data['search_cache'] = pickle.load(f)
                
        # Load graph state
        if GRAPH_STATE_FILE.exists():
            with open(GRAPH_STATE_FILE, 'r') as f:
                cache_data['graph_state'] = json.load(f)
                
        return jsonify({
            'success': True,
            'data': cache_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/save', methods=['POST'])
def save_cache():
    """Save cache to disk"""
    try:
        data = request.json
        
        # Save search cache
        if 'search_cache' in data:
            with open(SEARCH_CACHE_FILE, 'wb') as f:
                pickle.dump(data['search_cache'], f)
                
        # Save graph state
        if 'graph_state' in data:
            with open(GRAPH_STATE_FILE, 'w') as f:
                json.dump(data['graph_state'], f)
                
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """Clear cache files"""
    try:
        if SEARCH_CACHE_FILE.exists():
            SEARCH_CACHE_FILE.unlink()
        if GRAPH_STATE_FILE.exists():
            GRAPH_STATE_FILE.unlink()
            
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vision', methods=['POST'])
def analyze_image():
    """Analyze an image using Claude's vision capabilities with tool calling"""
    try:
        data = request.json
        image_data = data.get('image_data', '')
        
        if not image_data:
            return jsonify({'error': 'No image data provided'}), 400
        
        try:
            # Extract base64 data and detect media type
            if ',' in image_data:
                header, base64_data = image_data.split(',', 1)
                if 'jpeg' in header or 'jpg' in header:
                    media_type = 'image/jpeg'
                elif 'png' in header:
                    media_type = 'image/png'
                elif 'gif' in header:
                    media_type = 'image/gif'
                elif 'webp' in header:
                    media_type = 'image/webp'
                else:
                    media_type = 'image/png'  # Default
            else:
                base64_data = image_data
                media_type = 'image/png'  # Default
                
            # Define tool for structured entity extraction
            tools = [
                {
                    "name": "extract_entities_and_relationships",
                    "description": "Extract entities and relationships from an image for investigation purposes",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "entities": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "value": {
                                            "type": "string",
                                            "description": "The exact extracted text/information as it appears"
                                        },
                                        "type": {
                                            "type": "string",
                                            "enum": ["name", "company", "email", "phone", "address", "ip_address", "domain", "username", "account", "license_plate", "url", "other"],
                                            "description": "Type of entity - use 'company' for organizations/businesses, 'name' for individual people only"
                                        },
                                        "confidence": {
                                            "type": "string",
                                            "enum": ["high", "medium", "low"],
                                            "description": "Confidence level in the extraction"
                                        },
                                        "notes": {
                                            "type": "string", 
                                            "description": "Brief description of where/how this was found and any relevant context"
                                        }
                                    },
                                    "required": ["value", "type", "confidence", "notes"]
                                },
                                "description": "All entities extracted from the image"
                            },
                            "relationships": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "source": {
                                            "type": "string",
                                            "description": "Source entity (must match an entity value exactly)"
                                        },
                                        "target": {
                                            "type": "string", 
                                            "description": "Target entity (must match an entity value exactly)"
                                        },
                                        "relationship": {
                                            "type": "string",
                                            "description": "Type of relationship (e.g., 'CEO', 'Employee', 'Email Address', 'Phone Number', 'Located At')"
                                        },
                                        "confidence": {
                                            "type": "string",
                                            "enum": ["high", "medium", "low"],
                                            "description": "Confidence level in this relationship"
                                        },
                                        "notes": {
                                            "type": "string",
                                            "description": "Additional context about this relationship"
                                        }
                                    },
                                    "required": ["source", "target", "relationship", "confidence", "notes"]
                                },
                                "description": "Relationships between the extracted entities"
                            }
                        },
                        "required": ["entities", "relationships"]
                    }
                }
            ]
                
            # Call Anthropic API with vision and tools
            response = anthropic_client.messages.create(
                model='claude-sonnet-4-5-20250929',
                max_tokens=2000,
                temperature=0.1,
                tools=tools,
                tool_choice={"type": "tool", "name": "extract_entities_and_relationships"},
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'image',
                                'source': {
                                    'type': 'base64',
                                    'media_type': media_type,
                                    'data': base64_data
                                }
                            },
                            {
                                'type': 'text',
                                'text': '''Analyze this image EXHAUSTIVELY and extract EVERY SINGLE entity and relationship for investigation purposes. 

CRITICAL EXTRACTION REQUIREMENTS:
1. ENTITY TYPES:
   - Use "company" for ANY organization, business, agency, department, corporation, institution, firm, group - NEVER use "name" for companies
   - Use "name" ONLY for individual people's names (first names, last names, full names, nicknames)
   
2. MUST EXTRACT ALL OF THESE:
   - Every person mentioned, referenced, or implied (including family members like mother, father, spouse, children, siblings, relatives)
   - Every organization, company, business, agency mentioned
   - All contact information (emails, phones, addresses, social media handles)
   - All dates, times, locations, places
   - All account numbers, IDs, references, case numbers
   - All URLs, domains, websites mentioned
   - Any usernames, handles, or online identities
   
3. FAMILY & RELATIONSHIPS - PAY SPECIAL ATTENTION TO:
   - Family relationships (mother of, father of, spouse of, child of, sibling of, related to)
   - Professional relationships (works at, employed by, CEO of, manager of, reports to)
   - Associations (member of, affiliated with, connected to, knows)
   - Ownership (owns, belongs to, registered to)
   
4. EXTRACTION APPROACH:
   - Read EVERY word in the image multiple times
   - Look for implied entities (e.g., "his mother" implies existence of a mother entity)
   - Extract partial information (even just first names are valuable)
   - Include context clues and inferences
   - If someone is mentioned as "the mother of John", create TWO entities: "John" and "[Mother of John]" with a relationship between them
   
5. RELATIONSHIP CREATION:
   - Create relationships between ALL connected entities
   - Use descriptive relationship labels (not just generic connections)
   - Include family relationships, professional relationships, ownership, contact info belonging to people/companies
   
BE EXTREMELY THOROUGH - Missing entities is unacceptable. When in doubt, include it. Extract everything that could possibly be relevant to an investigation.

Use the extract_entities_and_relationships tool.'''
                            }
                        ]
                    }
                ]
            )
            
            # Parse the tool response
            tool_result = None
            for content in response.content:
                if content.type == "tool_use" and content.name == "extract_entities_and_relationships":
                    tool_result = content.input
                    break
            
            if tool_result:
                print(f"Tool result: {tool_result}")
                return jsonify({
                    'success': True,
                    'entities': tool_result.get('entities', []),
                    'relationships': tool_result.get('relationships', [])
                })
            else:
                print("No tool result found in response")
                return jsonify({
                    'success': True,
                    'entities': [],
                    'relationships': []
                })
            
        except anthropic.APIError as e:
            print(f"Anthropic API Error in vision endpoint: {e}")
            return jsonify({'error': f'Claude API error: {str(e)}'}), 503
            
    except Exception as e:
        print(f"General Error in vision endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/whois', methods=['POST'])
def whois_search():
    """Handle WHOIS searches - EXACTLY like the Python script"""
    try:
        if whois is None:
            return jsonify({'error': 'WHOIS functionality is not available'}), 503
            
        data = request.json
        query = data.get('query', '')
        query_type = data.get('type', None)
        
        if not query:
            return jsonify({'error': 'Query parameter is required'}), 400
        
        # For domains, ALWAYS get full history like the Python script
        if query_type == 'domain':
            # Call the EXACT same function from whois.py
            records = whois.get_whois_history(query)
            structured = whois.structured_whois_history(query)
            print(f"Got {len(records)} WHOIS history records for {query}")
            
            # Return ALL the raw records for Claude to process
            return jsonify({
                'query': query,
                'query_type': 'domain',
                'records': records,
                'structured_history': structured,
                'count': len(records),
                'source': 'whois'
            })
        
        # Auto-detect query type if not provided
        if not query_type:
            if '@' in query:
                query_type = 'email'
            elif re.match(r'^\+?\d[\d\s\-\(\)\.]{6,}$', query.strip()):
                query_type = 'phone'
            else:
                # Default to terms search for names/companies
                query_type = 'terms'
        
        # Perform the WHOIS lookup using the exact same function
        results = whois.whois_lookup(query, query_type)
        
        # Format results for frontend
        formatted_results = []
        
        if results.get('error'):
            return jsonify({'error': results.get('error')}), 500
        
        if query_type == 'domain':
            # Domain history results - just pass ALL raw data to client
            records = results.get('records', [])
            for record in records:
                if isinstance(record, dict):
                    # Get ALL the raw text
                    raw_text = record.get('rawText', '') or record.get('cleanText', '')
                    
                    formatted_results.append({
                        'domain': record.get('domainName', query),
                        'registrar': record.get('registrarName', ''),
                        'created': record.get('createdDateISO8601', ''),
                        'updated': record.get('updatedDateISO8601', ''),
                        'expires': record.get('expiresDateISO8601', ''),
                        # Send the FULL raw text to client for Claude to process
                        'raw_whois_text': raw_text,
                        # Also include all structured data in case it exists
                        'full_record': record,
                        'type': 'whois_domain'
                    })
        else:
            # Reverse WHOIS results (email, phone, terms)
            domains = results.get('domains', [])
            search_term = results.get('search_term', query)
            
            # For each domain found, get its FULL WHOIS data
            for domain in domains[:20]:  # Increased limit to show more results
                try:
                    # Get the full WHOIS history for this domain
                    print(f"\n=== FETCHING WHOIS HISTORY FOR: {domain} ===")
                    domain_records = whois.get_whois_history(domain)
                    print(f"Got {len(domain_records) if domain_records else 0} records")
                    
                    if domain_records and len(domain_records) > 0:
                        # Use the most recent record
                        record = domain_records[0]
                        print(f"First record type: {type(record)}")
                        print(f"Record keys: {list(record.keys()) if isinstance(record, dict) else 'NOT A DICT'}")
                        
                        # Build comprehensive raw text from all available sources
                        raw_parts = []
                        
                        # ALWAYS add cleanText FIRST - it often has the most data
                        if record.get('cleanText'):
                            raw_parts.append("=== CLEAN TEXT (MAIN WHOIS DATA) ===")
                            raw_parts.append(record['cleanText'])
                        
                        # Add raw text if it exists and has content
                        if record.get('rawText') and len(record.get('rawText', '')) > 10:
                            raw_parts.append("\n=== RAW TEXT ===")
                            raw_parts.append(record['rawText'])
                        
                        # Extract ALL contact information from structured fields
                        contact_info = []
                        
                        # Add small delay to avoid rate limiting
                        time.sleep(0.3)
                        
                        # Domain info header
                        contact_info.append(f"\n=== DOMAIN: {domain} ===")
                        contact_info.append(f"Search Term: {search_term}")
                        if record.get('domainName'):
                            contact_info.append(f"Domain Name: {record['domainName']}")
                        
                        # Log what we're extracting
                        print(f"Processing domain {domain} - record has keys: {list(record.keys())}")
                        
                        # Registrant contact - GET ALL FIELDS
                        if record.get('registrantContact'):
                            reg = record['registrantContact']
                            print(f"  Registrant contact fields: {list(reg.keys())}")
                            contact_info.append("\n--- REGISTRANT CONTACT ---")
                            for field, value in reg.items():
                                if value and not any(term in str(value).upper() for term in ['REDACTED', 'PRIVACY']):
                                    field_name = field.replace('_', ' ').title()
                                    contact_info.append(f"{field_name}: {value}")
                                    print(f"    {field_name}: {value}")
                        
                        # Administrative contact - GET ALL FIELDS
                        if record.get('administrativeContact'):
                            admin = record['administrativeContact']
                            contact_info.append("\n--- ADMINISTRATIVE CONTACT ---")
                            for field, value in admin.items():
                                if value and not any(term in str(value).upper() for term in ['REDACTED', 'PRIVACY']):
                                    field_name = field.replace('_', ' ').title()
                                    contact_info.append(f"{field_name}: {value}")
                        
                        # Technical contact - GET ALL FIELDS
                        if record.get('technicalContact'):
                            tech = record['technicalContact']
                            contact_info.append("\n--- TECHNICAL CONTACT ---")
                            for field, value in tech.items():
                                if value and not any(term in str(value).upper() for term in ['REDACTED', 'PRIVACY']):
                                    field_name = field.replace('_', ' ').title()
                                    contact_info.append(f"{field_name}: {value}")
                        
                        # Billing contact if exists
                        if record.get('billingContact'):
                            billing = record['billingContact']
                            contact_info.append("\n--- BILLING CONTACT ---")
                            for field, value in billing.items():
                                if value and not any(term in str(value).upper() for term in ['REDACTED', 'PRIVACY']):
                                    field_name = field.replace('_', ' ').title()
                                    contact_info.append(f"{field_name}: {value}")
                        
                        # Zone contact if exists
                        if record.get('zoneContact'):
                            zone = record['zoneContact']
                            contact_info.append("\n--- ZONE CONTACT ---")
                            for field, value in zone.items():
                                if value and not any(term in str(value).upper() for term in ['REDACTED', 'PRIVACY']):
                                    field_name = field.replace('_', ' ').title()
                                    contact_info.append(f"{field_name}: {value}")
                        
                        # Add domain dates
                        date_info = []
                        if record.get('createdDateISO8601'):
                            date_info.append(f"Created: {record['createdDateISO8601']}")
                        if record.get('updatedDateISO8601'):
                            date_info.append(f"Updated: {record['updatedDateISO8601']}")
                        if record.get('expiresDateISO8601'):
                            date_info.append(f"Expires: {record['expiresDateISO8601']}")
                        if date_info:
                            contact_info.append("\n--- DOMAIN DATES ---")
                            contact_info.extend(date_info)
                        
                        # Add registrar info
                        if record.get('registrarName'):
                            contact_info.append(f"\nRegistrar: {record['registrarName']}")
                        if record.get('registrarIANAID'):
                            contact_info.append(f"Registrar IANA ID: {record['registrarIANAID']}")
                        
                        # Add name servers
                        ns_data = record.get('nameServers')
                        if ns_data:
                            contact_info.append("\n--- NAME SERVERS ---")
                            if isinstance(ns_data, dict) and ns_data.get('hostNames'):
                                for ns in ns_data['hostNames']:
                                    contact_info.append(f"NS: {ns}")
                            elif isinstance(ns_data, list):
                                for ns in ns_data:
                                    contact_info.append(f"NS: {ns}")
                        
                        # Add contact info to raw text
                        if contact_info:
                            raw_parts.append("\n=== STRUCTURED CONTACT DATA ===\n" + "\n".join(contact_info))
                        
                        # Combine all parts
                        raw_text = "\n\n".join(raw_parts)
                        
                        result_entry = {
                            'domain': domain,
                            'search_term': search_term,
                            'search_type': query_type,
                            'created': record.get('createdDateISO8601', ''),
                            'updated': record.get('updatedDateISO8601', ''),
                            'expires': record.get('expiresDateISO8601', ''),
                            'registrar': record.get('registrarName', ''),
                            'raw_whois_text': raw_text,
                            'full_record': record,
                            'type': 'whois_domain'  # Change type so it gets processed properly
                        }
                        print(f"\n=== FORMATTED RESULT FOR {domain} ===")
                        print(f"raw_whois_text length: {len(raw_text)}")
                        print(f"raw_whois_text preview: {raw_text[:500]}...")
                        formatted_results.append(result_entry)
                    else:
                        # Fallback if no history available
                        print(f"NO WHOIS HISTORY FOUND FOR {domain}")
                        formatted_results.append({
                            'domain': domain,
                            'search_term': search_term,
                            'search_type': query_type,
                            'type': 'whois_reverse',
                            'raw_whois_text': f"No WHOIS history available for {domain}",
                            'created': '',
                            'expires': ''
                        })
                        
                except Exception as e:
                    print(f"ERROR getting WHOIS data for {domain}: {e}")
                    import traceback
                    traceback.print_exc()
                    # Add basic result on error
                    formatted_results.append({
                        'domain': domain,
                        'search_term': search_term,
                        'search_type': query_type,
                        'type': 'whois_reverse',
                        'raw_whois_text': f"Error fetching WHOIS: {str(e)}",
                        'created': '',
                        'expires': ''
                    })
        
        return jsonify({
            'results': formatted_results,
            'total': len(formatted_results),
            'query': query,
            'query_type': query_type,
            'source': 'whois'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract-whois', methods=['POST'])
def extract_whois():
    """Extract entities from WHOIS text using AI"""
    try:
        data = request.json
        whois_text = data.get('whois_text', '')
        domain = data.get('domain', 'unknown')
        
        if not whois_text:
            return jsonify({'error': 'No WHOIS text provided'}), 400
            
        # Use Claude to extract entities
        prompt = f"""You are analyzing WHOIS data for domain: {domain}

Extract ALL entities that should become nodes in an investigation graph. Look for:
1. Email addresses (ALL of them, skip only technical ones like abuse@, whois@, dns@)
2. Phone numbers (ALL formats)
3. Person names (registrant, admin, tech, billing contacts)
4. Company/organization names
5. Physical addresses (full or partial)
6. Any other identifying information that could link to people or organizations

BE THOROUGH - extract EVERYTHING that could be useful for investigation.
Look through the ENTIRE text, not just structured fields.
Many WHOIS records have unstructured text with valuable information.

Return ONLY a JSON array, no other text:
[{{"value": "extracted_value", "type": "email|phone|name|company|address|other", "context": "where found"}}]

WHOIS DATA TO ANALYZE:
{whois_text}"""

        response = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse the response
        content = response.content[0].text
        try:
            # Find JSON array in response
            import re
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                entities = json.loads(json_match.group())
                return jsonify({'entities': entities})
        except Exception as e:

            print(f"[EYE-D] Error: {e}")

            pass
            
        return jsonify({'entities': []})
        
    except Exception as e:
        print(f"WHOIS extraction error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/owl', methods=['POST'])
def owl_search():
    """
    Ownership-Linked Domains (?owl operator)

    Finds domains owned by the same registrant(s) using LINKLATER's
    cluster_domains_by_whois which searches ALL distinct historic registrants.

    Request body:
        {
            "domain": "target-domain.com",
            "include_nameserver": true  // optional, also search by shared nameservers
        }

    Response:
        {
            "success": true,
            "domain": "target-domain.com",
            "results": [
                {
                    "domain": "related-domain.com",
                    "match_type": "registrant_name",
                    "match_value": "John Smith",
                    "confidence": 0.95
                },
                ...
            ],
            "distinct_registrants": ["SOAX LTD", "Nicholas Mercader"],
            "total_found": 117,
            "api_calls": 5,
            "method": "whois_cluster_all_historic"
        }
    """
    try:
        if not LINKLATER_AVAILABLE or cluster_domains_by_whois is None:
            return jsonify({'error': 'LINKLATER not available. ?owl operator disabled.'}), 503

        data = request.json
        domain = data.get('domain', '')
        include_nameserver = data.get('include_nameserver', True)

        if not domain:
            return jsonify({'error': 'Domain parameter is required'}), 400

        print(f"🦉 OWL search for: {domain} (include_nameserver: {include_nameserver})")

        # Run the async function in the event loop
        import asyncio

        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Call LINKLATER's cluster_domains_by_whois
        response = loop.run_until_complete(
            cluster_domains_by_whois(
                domain=domain,
                include_nameserver=include_nameserver,
                limit=500  # High limit for comprehensive discovery
            )
        )

        # Format results for frontend
        results = []
        for r in response.results:
            results.append({
                'domain': r.domain,
                'match_type': r.match_type,
                'match_value': r.match_value,
                'confidence': r.confidence,
            })

        # Extract distinct registrants from metadata
        distinct_registrants = response.metadata.get('distinct_registrants', [])

        print(f"🦉 OWL found {len(results)} domains via {len(distinct_registrants)} registrants")

        return jsonify({
            'success': True,
            'domain': domain,
            'results': results,
            'distinct_registrants': distinct_registrants,
            'total_found': response.total_found,
            'api_calls': response.api_calls,
            'method': response.method
        })

    except Exception as e:
        print(f"OWL search error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/osint', methods=['POST'])
def osint_search():
    """Handle OSINT Industries searches with Claude AI extraction"""
    try:
        if osintindustries is None:
            return jsonify({'error': 'OSINT Industries functionality is not available'}), 503
            
        data = request.json
        query = data.get('query', '')
        query_type = data.get('type', None)
        
        if not query:
            return jsonify({'error': 'Query parameter is required'}), 400
        
        print(f"OSINT search for: {query} (type: {query_type})")
        
        # Create OSINT client and perform search
        client = osintindustries.OSINTIndustriesClient()
        
        # Auto-detect type if not provided
        if not query_type:
            if '@' in query:
                query_type = 'email'
            elif re.match(r'^\+?\d[\d\s\-\(\)\.]{6,}$', query.strip()):
                query_type = 'phone'
            else:
                query_type = 'email'  # Default to email
        
        # Perform OSINT search using the main search method
        if query_type == 'email':
            results_list = client.search('email', query)
        elif query_type == 'phone':
            # Normalize phone number and try multiple variants
            normalized_numbers = normalize_phone_number(query)
            results_list = []
            
            for phone_variant in normalized_numbers:
                print(f"Searching OSINT for phone variant: {phone_variant}")
                variant_results = client.search('phone', phone_variant)
                if variant_results:
                    results_list.extend(variant_results)
            
            # Remove duplicates based on profile URL or unique identifier
            seen_profiles = set()
            unique_results = []
            for result in results_list:
                identifier = result.profile_url or f"{result.module}_{result.username}_{result.email}"
                if identifier not in seen_profiles:
                    seen_profiles.add(identifier)
                    unique_results.append(result)
            results_list = unique_results
            
        else:
            return jsonify({'error': f'Unsupported query type: {query_type}'}), 400
        
        if not results_list:
            return jsonify({
                'query': query,
                'query_type': query_type,
                'entities': [],
                'raw_results': [],
                'source': 'osint'
            })
        
        print(f"Found {len(results_list)} OSINT results")
        
        # Convert results to text for Claude analysis
        osint_text = f"OSINT Industries Search Results for {query_type}: {query}\n\n"
        osint_text += f"Total Results Found: {len(results_list)}\n\n"
        
        for i, result in enumerate(results_list[:50], 1):  # Limit to first 50 results
            osint_text += f"=== Result {i} (Module: {result.module}) ===\n"
            if result.name:
                osint_text += f"Name: {result.name}\n"
            if result.username:
                osint_text += f"Username: {result.username}\n"
            if result.email:
                osint_text += f"Email: {result.email}\n"
            if result.phone:
                osint_text += f"Phone: {result.phone}\n"
            if result.location:
                osint_text += f"Location: {result.location}\n"
            if result.profile_url:
                osint_text += f"Profile URL: {result.profile_url}\n"
            if result.picture_url:
                osint_text += f"Picture URL: {result.picture_url}\n"
            if result.bio:
                osint_text += f"Bio: {result.bio}\n"
            if result.verified is not None:
                osint_text += f"Verified: {result.verified}\n"
            if result.followers is not None:
                osint_text += f"Followers: {result.followers}\n"
            if result.following is not None:
                osint_text += f"Following: {result.following}\n"
            if result.creation_date:
                osint_text += f"Creation Date: {result.creation_date}\n"
            if result.last_seen:
                osint_text += f"Last Seen: {result.last_seen}\n"
            
            # Add social profiles
            if result.social_profiles:
                osint_text += "Social Profiles:\n"
                for profile in result.social_profiles:
                    osint_text += f"  - {profile.platform}: {profile.username} ({profile.url})\n"
            
            # Add breach info
            if result.breach_info:
                osint_text += "Breach Information:\n"
                for breach in result.breach_info:
                    osint_text += f"  - {breach.name}: {breach.description}\n"
            
            osint_text += "\n"
        
        print(f"Sending OSINT data to Claude for entity extraction (text length: {len(osint_text)})")
        
        # Use Claude to extract entities from OSINT data
        try:
            prompt = f"""You are analyzing OSINT Industries search results for: {query}

CRITICAL: Only extract entities that should become SEPARATE NODES, not metadata details.

CREATE NEW NODES FOR:
1. Email addresses (ALL of them, even from different platforms)
2. Phone numbers (ALL formats) 
3. Person names (full names, first names, last names)
4. Usernames/handles (from all platforms)
5. Company/organization names
6. Physical addresses/locations (city, state, country if substantial)
7. Website URLs and profile URLs (main profiles only)

DO NOT CREATE NODES FOR METADATA (these should be notes on existing nodes):
- Account creation dates, join dates
- Follower/following counts
- Verification status, premium status
- Bio text, descriptions
- Profile picture URLs, banner URLs
- Account settings (private/public)
- Platform-specific IDs
- Last seen dates, activity dates
- Age, gender (unless person's name)

For profile URLs, extract the USERNAME as a separate node, and suggest the metadata as notes.

Return a JSON object with two arrays:
{{
  "nodes": [
    {{"value": "extracted_value", "type": "email|phone|name|username|company|address|url", "context": "source platform"}}
  ],
  "notes": [
    {{"for_node": "node_value", "note": "metadata detail", "context": "source platform"}}
  ]
}}

OSINT DATA TO ANALYZE:
{osint_text}"""

            response = anthropic_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse Claude's response
            content = response.content[0].text
            entities = []
            notes = []
            
            try:
                # Try to parse as JSON object with nodes and notes
                import re
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    parsed = json.loads(json_match.group())
                    entities = parsed.get('nodes', [])
                    notes = parsed.get('notes', [])
                else:
                    # Fallback: try to parse as array (old format)
                    array_match = re.search(r'\[[\s\S]*\]', content)
                    if array_match:
                        entities = json.loads(array_match.group())
            except Exception as e:
                print(f"Failed to parse Claude response: {content[:500]}...")
                pass
            
            print(f"Claude extracted {len(entities)} entities and {len(notes)} notes from OSINT data")
            
            return jsonify({
                'query': query,
                'query_type': query_type,
                'entities': entities,
                'notes': notes,
                'raw_results': [result.__dict__ for result in results_list[:50]],
                'total_results': len(results_list),
                'source': 'osint'
            })
            
        except Exception as e:
            print(f"Claude extraction failed: {e}")
            # Return raw results without AI extraction
            return jsonify({
                'query': query,
                'query_type': query_type,
                'entities': [],
                'raw_results': [result.__dict__ for result in results_list[:50]],
                'total_results': len(results_list),
                'source': 'osint',
                'extraction_error': str(e)
            })
        
    except Exception as e:
        print(f"OSINT search error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/people/enrich', methods=['POST'])
def enrich_people():
    """Unified people enrichment using all available services"""
    try:
        data = request.json
        name = data.get('name', '')

        if not name:
            return jsonify({'error': 'Name parameter is required'}), 400

        print(f"People enrichment for: {name}")

        all_results = []
        services_used = []

        # 1. OSINT Industries
        if osintindustries:
            try:
                client = osintindustries.OSINTIndustriesClient()
                osint_results = client.search('email', name)  # Will search by name
                if osint_results:
                    for result in osint_results:
                        all_results.append({
                            'source': 'OSINT Industries',
                            'name': result.name,
                            'email': result.email,
                            'phone': result.phone,
                            'username': result.username,
                            'profile_url': result.profile_url,
                            'module': result.module
                        })
                    services_used.append('OSINT Industries')
                    print(f"OSINT Industries: {len(osint_results)} results")
            except Exception as e:
                print(f"OSINT Industries error: {e}")

        # 2. RocketReach
        if ROCKETREACH_AVAILABLE and rocketreach:
            try:
                client = rocketreach.RocketReachClient()
                rr_results = client.search_by_name(name, page_size=10)
                if rr_results:
                    for result in rr_results:
                        all_results.append({
                            'source': 'RocketReach',
                            'name': result.name,
                            'emails': [e.email for e in result.emails if e.email],
                            'phones': [p.phone for p in result.phones if p.phone],
                            'current_title': result.current_title,
                            'current_employer': result.current_employer,
                            'linkedin_url': result.linkedin_url,
                            'location': f"{result.city}, {result.region}" if result.city else None
                        })
                    services_used.append('RocketReach')
                    print(f"RocketReach: {len(rr_results)} results")
            except Exception as e:
                print(f"RocketReach error: {e}")

        # 3. Kaspr
        # Note: Kaspr requires LinkedIn URL + name, not just name
        # We'll skip Kaspr in name-only enrichment since we don't have LinkedIn URLs
        # Kaspr will be used when we have LinkedIn URLs in the LinkedIn enrichment flow

        # 4. ContactOut
        if CONTACTOUT_AVAILABLE and contactout:
            try:
                client = contactout.ContactOutClient()
                # Search for people by name
                profiles, metadata = client.search_people(
                    name=name,
                    reveal_info=True,  # Get contact details
                    page_size=10
                )
                if profiles:
                    for profile in profiles:
                        result = {
                            'source': 'ContactOut',
                            'name': profile.full_name,
                            'emails': profile.email + profile.work_email + profile.personal_email,
                            'phones': profile.phone,
                            'linkedin_url': profile.url,
                            'headline': profile.headline,
                            'location': profile.location or profile.country,
                        }
                        # Add company info if available
                        if profile.company and profile.company.name:
                            result['current_employer'] = profile.company.name
                            result['company_domain'] = profile.company.domain
                            result['company_industry'] = profile.company.industry
                        # Add experience info
                        if profile.experience and len(profile.experience) > 0:
                            current_exp = profile.experience[0]
                            result['current_title'] = current_exp.title
                        all_results.append(result)
                    services_used.append('ContactOut')
                    print(f"ContactOut: {len(profiles)} results")
            except Exception as e:
                print(f"ContactOut error: {e}")

        return jsonify({
            'name': name,
            'results': all_results,
            'total_results': len(all_results),
            'services_used': services_used,
            'services_available': {
                'osint': osintindustries is not None,
                'rocketreach': ROCKETREACH_AVAILABLE,
                'kaspr': KASPR_AVAILABLE,
                'contactout': CONTACTOUT_AVAILABLE
            }
        })

    except Exception as e:
        print(f"People enrichment error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/people/enrich-linkedin', methods=['POST'])
def enrich_linkedin():
    """Enrich LinkedIn profile using all available services"""
    try:
        data = request.json
        linkedin_url = data.get('url', '')
        full_name = data.get('name', '')

        if not linkedin_url:
            return jsonify({'error': 'LinkedIn URL is required'}), 400

        print(f"LinkedIn enrichment for: {linkedin_url}, Name: {full_name}")

        all_results = []
        services_used = []

        # 1. Kaspr (requires LinkedIn URL + name)
        if KASPR_AVAILABLE and kaspr and full_name:
            try:
                client = kaspr.KasprClient()
                # Extract LinkedIn ID from URL (e.g., "john-doe" from linkedin.com/in/john-doe)
                linkedin_id = linkedin_url.split('/in/')[-1].split('?')[0].rstrip('/')

                kaspr_profile = client.get_linkedin_profile_details(
                    linkedin_id_or_url=linkedin_id,
                    full_name=full_name,
                    data_to_get=["phone", "workEmail", "directEmail"]
                )
                if kaspr_profile:
                    result = {
                        'source': 'Kaspr',
                        'name': kaspr_profile.name or full_name,
                        'emails': [],
                        'phones': kaspr_profile.phones or [],
                        'linkedin_url': linkedin_url,
                        'title': kaspr_profile.title,
                        'location': kaspr_profile.location
                    }
                    # Consolidate emails
                    if kaspr_profile.professionalEmails:
                        result['emails'].extend(kaspr_profile.professionalEmails)
                    if kaspr_profile.personalEmails:
                        result['emails'].extend(kaspr_profile.personalEmails)
                    if kaspr_profile.starryProfessionalEmail:
                        result['primary_work_email'] = kaspr_profile.starryProfessionalEmail
                    if kaspr_profile.starryPhone:
                        result['primary_phone'] = kaspr_profile.starryPhone
                    # Add company info
                    if kaspr_profile.company and kaspr_profile.company.name:
                        result['current_employer'] = kaspr_profile.company.name
                        result['company_domain'] = kaspr_profile.company.domains[0] if kaspr_profile.company.domains else None
                        result['company_industry'] = kaspr_profile.company.industryName or (kaspr_profile.company.industries[0] if kaspr_profile.company.industries else None)
                    all_results.append(result)
                    services_used.append('Kaspr')
                    print(f"Kaspr: Enriched profile")
            except Exception as e:
                print(f"Kaspr error: {e}")
                import traceback
                traceback.print_exc()

        # 2. ContactOut LinkedIn enrichment
        if CONTACTOUT_AVAILABLE and contactout:
            try:
                client = contactout.ContactOutClient()
                contact_profile = client.enrich_linkedin_profile(linkedin_url)
                if contact_profile:
                    result = {
                        'source': 'ContactOut',
                        'name': contact_profile.full_name or full_name,
                        'emails': contact_profile.email + contact_profile.work_email + contact_profile.personal_email,
                        'phones': contact_profile.phone,
                        'linkedin_url': contact_profile.url or linkedin_url,
                        'headline': contact_profile.headline,
                        'location': contact_profile.location or contact_profile.country,
                        'summary': contact_profile.summary,
                        'skills': contact_profile.skills
                    }
                    # Add company info
                    if contact_profile.company and contact_profile.company.name:
                        result['current_employer'] = contact_profile.company.name
                        result['company_domain'] = contact_profile.company.domain
                        result['company_industry'] = contact_profile.company.industry
                    # Add current title from experience
                    if contact_profile.experience and len(contact_profile.experience) > 0:
                        current_exp = contact_profile.experience[0]
                        result['current_title'] = current_exp.title
                    all_results.append(result)
                    services_used.append('ContactOut')
                    print(f"ContactOut: Enriched profile")
            except Exception as e:
                print(f"ContactOut error: {e}")
                import traceback
                traceback.print_exc()

        # 3. OSINT Industries (extract name from URL and search)
        if osintindustries and full_name:
            try:
                client = osintindustries.OSINTIndustriesClient()
                osint_results = client.search('email', full_name)
                if osint_results:
                    for result in osint_results:
                        all_results.append({
                            'source': 'OSINT Industries',
                            'name': result.name,
                            'email': result.email,
                            'phone': result.phone,
                            'username': result.username,
                            'profile_url': result.profile_url,
                            'module': result.module
                        })
                    services_used.append('OSINT Industries')
                    print(f"OSINT Industries: {len(osint_results)} results")
            except Exception as e:
                print(f"OSINT Industries error: {e}")

        return jsonify({
            'linkedin_url': linkedin_url,
            'name': full_name,
            'results': all_results,
            'total_results': len(all_results),
            'services_used': services_used,
            'services_available': {
                'osint': osintindustries is not None,
                'kaspr': KASPR_AVAILABLE,
                'contactout': CONTACTOUT_AVAILABLE
            }
        })

    except Exception as e:
        print(f"LinkedIn enrichment error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# Helper function to get PostgreSQL projects
def get_postgresql_projects():
    """Get projects from PostgreSQL database (only nodes with typeName='project')"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        return None

    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Query to get ONLY project nodes (filter by typeName='project')
        query = """
            SELECT n.id, n.label, n.created_at as "createdAt", n.updated_at as "updatedAt", n.metadata
            FROM nodes n
            INNER JOIN node_types nt ON n.type_id = nt.id
            WHERE nt.name = 'project' AND n.status = 'active'
            ORDER BY n.updated_at DESC
        """
        cur.execute(query)
        projects = cur.fetchall()

        # Convert to list of dicts
        result = [dict(p) for p in projects]

        cur.close()
        conn.close()

        return result
    except Exception as e:
        print(f"[PostgreSQL] Error fetching projects: {e}")
        return None

# Project Management Endpoints
@app.route('/api/projects', methods=['GET'])
def get_projects():
    """Get all projects from PostgreSQL (filters to ONLY typeName='project')"""
    try:
        # Try to get projects from PostgreSQL first
        pg_projects = get_postgresql_projects()
        if pg_projects is not None:
            print(f"[PostgreSQL] Returning {len(pg_projects)} projects")
            return jsonify({'projects': pg_projects})

        # Fall back to SQLite project manager if PostgreSQL not available
        print("[SQLite] Falling back to SQLite project manager")
        projects = project_manager.get_all_projects()
        return jsonify({'projects': projects})
    except Exception as e:
        print(f"[Projects] Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects', methods=['POST'])
def create_project():
    """Create a new project"""
    try:
        data = request.json
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        
        if not name:
            return jsonify({'error': 'Project name is required'}), 400
        
        project = project_manager.create_project(name, description)
        return jsonify({'project': project})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    """Delete a project"""
    try:
        success = project_manager.delete_project(project_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Project not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_id>/switch', methods=['POST'])
def switch_project(project_id):
    """Switch to a different project"""
    try:
        success = project_manager.switch_project(project_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Project not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/active', methods=['GET'])
def get_active_project():
    """Get the currently active project"""
    try:
        project = project_manager.get_active_project()
        if project:
            return jsonify({'project': project})
        else:
            # Create a default project if none exists
            project = project_manager.create_project("Default Project", "Automatically created project")
            return jsonify({'project': project})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_id>/graph', methods=['POST'])
def update_project_graph(project_id):
    """Update the graph data for a project"""
    try:
        data = request.json
        graph_data = data.get('graph_data', {})

        success = project_manager.update_project_graph(project_id, graph_data)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Project not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------
# Cymonides-1 (C-1) Elasticsearch graph endpoints (NO SQL GRAPH)
# -----------------------------------------------------------------------------

@app.route('/api/c1/export', methods=['GET'])
def c1_export_graph():
    """
    Export a project graph from cymonides-1-{projectId} in vis.js-compatible format.

    Query params:
      - projectId (required)
      - limit (optional, default: 2000)
    """
    if not C1_AVAILABLE:
        return jsonify({'error': 'C-1 integration not available'}), 503

    try:
        project_id = _c1_validate_project_id(request.args.get('projectId', ''))
        limit = int(request.args.get('limit', 2000))
        if limit <= 0:
            limit = 2000
        limit = min(limit, 10000)

        bridge = C1Bridge(project_id=project_id)
        index_name = bridge._get_index_name()

        # If index is missing, return empty graph
        if not bridge.es.indices.exists(index=index_name):
            return jsonify({
                'success': True,
                'projectId': project_id,
                'index': index_name,
                'graph_state': {'nodes': [], 'edges': [], 'nodeIdCounter': 0, 'valueToNodeMap': []},
            })

        resp = bridge.es.search(
            index=index_name,
            body={
                "query": {"match_all": {}},
                "size": limit,
                "sort": [{"updatedAt": {"order": "desc"}}],
            },
        )

        hits = resp.get("hits", {}).get("hits", [])
        node_sources: Dict[str, Dict] = {}
        node_ids = set()

        for h in hits:
            doc_id = h.get("_id")
            src = h.get("_source") or {}
            if not doc_id:
                continue
            node_ids.add(doc_id)
            node_sources[doc_id] = src

        nodes_out = []
        value_map_entries = []
        max_node_counter = 0

        for node_id, src in node_sources.items():
            label = src.get("label") or src.get("canonicalValue") or node_id
            metadata = src.get("metadata") if isinstance(src.get("metadata"), dict) else {}
            ui_type = _c1_c1_type_to_ui(src.get("type"), metadata=metadata, label=label)
            x, y = _c1_extract_position(metadata)

            # Track max node_N for legacy counter compatibility
            if isinstance(node_id, str) and node_id.startswith("node_"):
                try:
                    n = int(node_id.split("_", 1)[1])
                    max_node_counter = max(max_node_counter, n + 1)
                except Exception:
                    pass

            canonical = src.get("canonicalValue") or label
            if isinstance(canonical, str):
                key = f"{ui_type}_{canonical.lower().strip()}"
                value_map_entries.append([key, node_id])

            node_obj = {
                "id": node_id,
                "label": label,
                "type": ui_type,
                "data": {
                    "c1": {
                        "node_class": src.get("node_class"),
                        "type": src.get("type"),
                        "canonicalValue": src.get("canonicalValue"),
                        "sources": src.get("sources", []),
                        "source_system": src.get("source_system"),
                        "projectId": src.get("projectId"),
                    },
                    **(metadata or {}),
                },
            }
            if x is not None and y is not None:
                node_obj["x"] = x
                node_obj["y"] = y
                node_obj["physics"] = False

            nodes_out.append(node_obj)

        # Build edges from embedded_edges (dedupe)
        edges_out = []
        seen_edges = set()

        def _is_undirected(rel: str) -> bool:
            return rel in {"co_occurs_with", "related_to", "same_breach", "hypothetical"}

        for node_id, src in node_sources.items():
            embedded = src.get("embedded_edges") or []
            if not isinstance(embedded, list):
                continue

            for e in embedded:
                if not isinstance(e, dict):
                    continue
                target_id = e.get("target_id")
                if not target_id or target_id not in node_ids:
                    continue

                # Support both C-1 embedded edge schemas:
                # - LINKLATER/EYE-D: {"relation": "..."}
                # - IO CountryGraphAdapter: {"relationship": "..."}
                relation = str(e.get("relation") or e.get("relationship") or "related_to")
                direction = str(e.get("direction") or "outgoing").lower()

                if direction == "incoming":
                    from_id, to_id = target_id, node_id
                else:
                    from_id, to_id = node_id, target_id

                if _is_undirected(relation):
                    a, b = sorted([from_id, to_id])
                    key = f"{relation}|{a}|{b}"
                else:
                    key = f"{relation}|{from_id}|{to_id}"

                if key in seen_edges:
                    continue
                seen_edges.add(key)

                edges_out.append({
                    "id": f"c1:{key}",
                    "from": from_id,
                    "to": to_id,
                    "label": relation,
                    "title": relation,
                    "arrows": {"to": {"enabled": False}},
                })

        graph_state = {
            "nodes": nodes_out,
            "edges": edges_out,
            "nodeIdCounter": max_node_counter,
            "valueToNodeMap": value_map_entries,
        }

        return jsonify({
            'success': True,
            'projectId': project_id,
            'index': index_name,
            'graph_state': graph_state,
            'counts': {'nodes': len(nodes_out), 'edges': len(edges_out)},
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"[C-1] Export error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/c1/sync-node', methods=['POST'])
def c1_sync_node():
    """Upsert a single vis.js node into cymonides-1-{projectId}."""
    if not C1_AVAILABLE:
        return jsonify({'error': 'C-1 integration not available'}), 503

    try:
        payload = request.json or {}
        project_id = _c1_validate_project_id(payload.get('projectId', ''))
        node = payload.get('node') or {}
        if not isinstance(node, dict):
            return jsonify({'error': 'node must be an object'}), 400

        node_id = str(node.get('id') or '').strip()
        ui_type = (node.get('type') or (node.get('data') or {}).get('type') or 'unknown')
        label = str(node.get('label') or (node.get('data') or {}).get('value') or '').strip()

        # Skip empty / non-meaningful nodes
        if not node_id or not label:
            return jsonify({'error': 'node.id and node.label are required'}), 400

        node_class, c1_type, original_type = _c1_ui_type_to_c1(ui_type, node_data=node.get('data') if isinstance(node.get('data'), dict) else None)
        canonical = str((node.get('data') or {}).get('value') or label).lower().strip()

        # Position is stored in metadata.position
        x = node.get('x')
        y = node.get('y')
        pos = None
        try:
            if x is not None and y is not None:
                pos = {"x": float(x), "y": float(y)}
        except Exception:
            pos = None

        # Keep metadata lightweight (avoid huge blobs like base64 images)
        incoming_data = node.get('data') if isinstance(node.get('data'), dict) else {}
        sanitized_data = {}
        for k, v in incoming_data.items():
            if k in ("dataURL", "image", "embedded_edges"):
                continue
            sanitized_data[k] = v

        metadata = {
            "original_type": original_type,
            "ui_type": str(ui_type),
            "ui_id": node_id,
        }
        if pos is not None:
            metadata["position"] = pos
        if sanitized_data:
            metadata["ui_data"] = sanitized_data

        c1_node = C1Node(
            id=node_id,
            node_class=node_class,
            type=c1_type,
            label=label,
            canonicalValue=canonical,
            metadata=metadata,
            sources=[],
            source_system="eyed",
            embedded_edges=[],
            projectId=project_id,
        )

        bridge = C1Bridge(project_id=project_id)
        index_name = bridge._get_index_name()
        success, errors = bridge._bulk_upsert_nodes([c1_node], index_name)
        bridge.es.indices.refresh(index=index_name)

        return jsonify({
            'success': True,
            'projectId': project_id,
            'index': index_name,
            'node_id': node_id,
            'indexed': success,
            'errors': len(errors) if errors else 0,
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"[C-1] Sync node error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/c1/sync-edge', methods=['POST'])
def c1_sync_edge():
    """Upsert a single vis.js edge into cymonides-1-{projectId} as embedded_edges."""
    if not C1_AVAILABLE:
        return jsonify({'error': 'C-1 integration not available'}), 503

    try:
        payload = request.json or {}
        project_id = _c1_validate_project_id(payload.get('projectId', ''))
        edge = payload.get('edge') or {}
        if not isinstance(edge, dict):
            return jsonify({'error': 'edge must be an object'}), 400

        from_id = str(edge.get('from') or '').strip()
        to_id = str(edge.get('to') or '').strip()
        if not from_id or not to_id:
            return jsonify({'error': 'edge.from and edge.to are required'}), 400

        # Node snapshots help ensure correct type/label if the edge arrives first.
        from_node = payload.get('fromNode')
        to_node = payload.get('toNode')

        if not isinstance(from_node, dict) or not isinstance(to_node, dict):
            return jsonify({'error': 'fromNode and toNode are required'}), 400

        # Derive relation from label/title (fallback to related_to)
        relation = str(edge.get('label') or '').strip()
        title = str(edge.get('title') or '').strip()
        if not relation:
            if title.lower().startswith("same breach:"):
                relation = "co_occurs_with"
            elif title.lower().startswith("whois connection:"):
                relation = "whois_related"
            else:
                relation = "related_to"

        relation = relation.strip() or "related_to"

        undirected = relation in {"co_occurs_with", "related_to", "hypothetical", "same_breach"}
        now = datetime.utcnow().isoformat()

        # Build C1Node objects from snapshots (without clobbering existing docs)
        def _node_from_snapshot(snapshot: Dict) -> C1Node:
            node_id = str(snapshot.get('id') or '').strip()
            ui_type = snapshot.get('type') or (snapshot.get('data') or {}).get('type') or 'unknown'
            label = str(snapshot.get('label') or (snapshot.get('data') or {}).get('value') or '').strip()
            node_class, c1_type, original_type = _c1_ui_type_to_c1(ui_type, node_data=snapshot.get('data') if isinstance(snapshot.get('data'), dict) else None)
            canonical = str((snapshot.get('data') or {}).get('value') or label).lower().strip()

            incoming_data = snapshot.get('data') if isinstance(snapshot.get('data'), dict) else {}
            sanitized_data = {}
            for k, v in incoming_data.items():
                if k in ("dataURL", "image", "embedded_edges"):
                    continue
                sanitized_data[k] = v

            metadata = {
                "original_type": str(original_type),
                "ui_type": str(ui_type),
                "ui_id": node_id,
            }
            if sanitized_data:
                metadata["ui_data"] = sanitized_data

            return C1Node(
                id=node_id,
                node_class=node_class,
                type=c1_type,
                label=label,
                canonicalValue=canonical,
                metadata=metadata,
                sources=[],
                source_system="eyed",
                embedded_edges=[],
                projectId=project_id,
            )

        from_c1 = _node_from_snapshot(from_node)
        to_c1 = _node_from_snapshot(to_node)

        # Create embedded edge from -> to
        edge_meta = {}
        if title:
            edge_meta["title"] = title
        if edge.get("color") is not None:
            edge_meta["color"] = edge.get("color")

        outgoing = {
            "target_id": to_id,
            "target_class": to_c1.node_class,
            "target_type": to_c1.type,
            "target_label": to_c1.label,
            "relation": relation,
            "direction": "outgoing",
            "confidence": 0.85,
            "metadata": edge_meta,
            "created_at": now,
        }
        from_c1.embedded_edges.append(outgoing)

        nodes_to_upsert = [from_c1]

        if undirected and from_id != to_id:
            incoming = {
                "target_id": from_id,
                "target_class": from_c1.node_class,
                "target_type": from_c1.type,
                "target_label": from_c1.label,
                "relation": relation,
                "direction": "outgoing",
                "confidence": 0.85,
                "metadata": edge_meta,
                "created_at": now,
            }
            to_c1.embedded_edges.append(incoming)
            nodes_to_upsert.append(to_c1)

        bridge = C1Bridge(project_id=project_id)
        index_name = bridge._get_index_name()
        success, errors = bridge._bulk_upsert_nodes(nodes_to_upsert, index_name)
        bridge.es.indices.refresh(index=index_name)

        return jsonify({
            'success': True,
            'projectId': project_id,
            'index': index_name,
            'edge': {'from': from_id, 'to': to_id, 'relation': relation, 'undirected': undirected},
            'indexed': success,
            'errors': len(errors) if errors else 0,
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"[C-1] Sync edge error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/c1/sync-position', methods=['POST'])
def c1_sync_position():
    """Persist node position into metadata.position for cymonides-1-{projectId}."""
    if not C1_AVAILABLE:
        return jsonify({'error': 'C-1 integration not available'}), 503

    try:
        payload = request.json or {}
        project_id = _c1_validate_project_id(payload.get('projectId', ''))
        node_id = str(payload.get('nodeId') or '').strip()
        x = payload.get('x')
        y = payload.get('y')

        if not node_id:
            return jsonify({'error': 'nodeId is required'}), 400
        if x is None or y is None:
            return jsonify({'error': 'x and y are required'}), 400

        try:
            pos = {"x": float(x), "y": float(y)}
        except Exception:
            return jsonify({'error': 'x and y must be numbers'}), 400

        bridge = C1Bridge(project_id=project_id)
        index_name = bridge._get_index_name()
        now = datetime.utcnow().isoformat()

        bridge.es.update(
            index=index_name,
            id=node_id,
            retry_on_conflict=3,
            body={
                "script": {
                    "lang": "painless",
                    "source": """
                        if (ctx._source.metadata == null) { ctx._source.metadata = [:]; }
                        ctx._source.metadata.position = params.position;
                        ctx._source.updatedAt = params.now;
                        ctx._source.lastSeen = params.now;
                    """,
                    "params": {"position": pos, "now": now},
                }
            },
        )

        return jsonify({'success': True, 'projectId': project_id, 'nodeId': node_id, 'position': pos})

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"[C-1] Sync position error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/graph/import', methods=['POST'])
def import_se_graph():
    """
    Import graph data from SE (Search Engineer) in vis.js format

    Expects:
    {
        "nodes": [{id, type, value, label, data}, ...],
        "edges": [{id, from, to, label, data}, ...],
        "project_id": "se_project_name" (optional),
        "merge": true/false (optional, default: false)
    }

    Returns:
    {
        "success": true,
        "project_id": "...",
        "nodes_imported": count,
        "edges_imported": count
    }
    """
    try:
        data = request.json
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        se_project_id = data.get('project_id', 'SE Import')
        merge = data.get('merge', False)

        if not nodes:
            return jsonify({'error': 'No nodes provided'}), 400

        # Create or get project for SE import
        projects = project_manager.get_all_projects()
        target_project = None

        # Look for existing SE import project
        for proj in projects:
            if proj['name'] == f'SE: {se_project_id}':
                target_project = proj
                break

        # Create new project if not found
        if not target_project:
            target_project = project_manager.create_project(
                name=f'SE: {se_project_id}',
                description=f'Imported from Search Engineer project: {se_project_id}'
            )

        project_id = target_project['id']

        # Get existing graph data if merging
        existing_graph = {}
        if merge:
            # Get current graph data for this project
            current_projects = project_manager.get_all_projects()
            for proj in current_projects:
                if proj['id'] == project_id and proj.get('graph_data'):
                    try:
                        existing_graph = json.loads(proj['graph_data'])
                    except Exception as e:
                        existing_graph = {}
                    break

        # Prepare graph data in EYE-D format
        graph_data = {
            'nodes': [],
            'edges': []
        }

        # Convert SE nodes to EYE-D format
        if merge and existing_graph.get('nodes'):
            graph_data['nodes'] = existing_graph['nodes']

        # Add new nodes (with deduplication by ID)
        existing_node_ids = {node['id'] for node in graph_data['nodes']}
        for node in nodes:
            if node['id'] not in existing_node_ids:
                # SE vis.js format is already compatible with EYE-D
                graph_data['nodes'].append(node)

        # Convert SE edges to EYE-D format
        if merge and existing_graph.get('edges'):
            graph_data['edges'] = existing_graph['edges']

        # Add new edges (with deduplication by ID)
        existing_edge_ids = {edge.get('id', f"{edge['from']}-{edge['to']}") for edge in graph_data['edges']}
        for edge in edges:
            edge_id = edge.get('id', f"{edge['from']}-{edge['to']}")
            if edge_id not in existing_edge_ids:
                graph_data['edges'].append(edge)

        # Update project with new graph data
        success = project_manager.update_project_graph(project_id, graph_data)

        if success:
            # Also store in SE's search_graph.db for bidirectional sync
            se_nodes_stored = 0
            se_edges_stored = 0

            if SE_STORAGE_AVAILABLE:
                try:
                    # Use SE Grid's database - absolute path
                    se_db_path = "/Users/attic/SE/WEBAPP/search_graph.db"
                    storage = EntityGraphStorageV2(db_path=se_db_path)
                    print(f"[SE Grid Sync] Storing {len(nodes)} nodes and {len(edges)} edges in search_graph.db")

                    # Store nodes
                    for node in nodes:
                        try:
                            node_id = node.get('id')
                            node_type = node.get('type', 'unknown')
                            value = node.get('value') or node.get('label', '')

                            # Extract metadata
                            meta_data = node.get('data', {})
                            if not isinstance(meta_data, dict):
                                meta_data = {}

                            # Add source info
                            meta_data['imported_from'] = 'EYE-D'
                            meta_data['eyed_project_id'] = project_id
                            meta_data['import_time'] = datetime.now().isoformat()

                            # Store node
                            storage.add_node(
                                node_id=node_id,
                                node_type=node_type,
                                value=value,
                                project_id=se_project_id,
                                meta=json.dumps(meta_data)
                            )
                            se_nodes_stored += 1

                        except Exception as e:
                            print(f"[SE Grid Sync] Error storing node {node.get('id')}: {e}")

                    # Store edges
                    for edge in edges:
                        try:
                            edge_id = edge.get('id', f"{edge['from']}-{edge['to']}")
                            source_id = edge.get('from')
                            target_id = edge.get('to')
                            edge_label = edge.get('label', 'connected_to')

                            # Extract edge metadata
                            edge_data = edge.get('data', {})
                            if not isinstance(edge_data, dict):
                                edge_data = {}

                            # Add source info
                            edge_data['imported_from'] = 'EYE-D'
                            edge_data['eyed_project_id'] = project_id
                            edge_data['import_time'] = datetime.now().isoformat()

                            # Store edge
                            storage.add_edge(
                                edge_id=edge_id,
                                source_id=source_id,
                                target_id=target_id,
                                edge_type=edge_label,
                                meta=json.dumps(edge_data)
                            )
                            se_edges_stored += 1

                        except Exception as e:
                            print(f"[SE Grid Sync] Error storing edge {edge.get('id')}: {e}")

                    print(f"[SE Grid Sync] Successfully stored {se_nodes_stored} nodes and {se_edges_stored} edges")

                except Exception as e:
                    print(f"[SE Grid Sync] Error during SE storage: {e}")
                    import traceback
                    traceback.print_exc()

            return jsonify({
                'success': True,
                'project_id': project_id,
                'project_name': target_project['name'],
                'nodes_imported': len(nodes),
                'edges_imported': len(edges),
                'total_nodes': len(graph_data['nodes']),
                'total_edges': len(graph_data['edges']),
                'se_sync': {
                    'enabled': SE_STORAGE_AVAILABLE,
                    'nodes_stored': se_nodes_stored,
                    'edges_stored': se_edges_stored
                }
            })
        else:
            return jsonify({'error': 'Failed to update project graph'}), 500

    except Exception as e:
        print(f"Error importing SE graph: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# Replaced by Corporella - /data/corporella/
# # Replaced by Corporella - /data/corporella/
# @app.route('/api/opencorporates/search', methods=['POST'])
def _deprecated_opencorporates_search():
    """DEPRECATED: Use Corporella at /data/corporella/ for company searches"""
    return jsonify({
        'error': 'OpenCorporates endpoint deprecated. Use Corporella at /data/corporella/',
        'success': False
    }), 410

# Original opencorporates_search function commented out:
# @app.route('/api/opencorporates/search', methods=['POST'])
# def opencorporates_search():
    """Search OpenCorporates for company and officer information"""
    try:
        from opencorporates import OpenCorporatesAPI
        
        data = request.json
        query = data.get('query', '')
        search_type = data.get('search_type', 'company')  # 'company' or 'officer'
        jurisdiction = data.get('jurisdiction', None)
        
        if not query:
            return jsonify({'error': 'Query parameter is required'}), 400
        
        # OpenCorporates works without API key but with rate limits
        # You can get a free API key at https://opencorporates.com/api_accounts/new
        api = OpenCorporatesAPI()
        results = []
        
        print(f"OpenCorporates search - Query: {query}, Type: {search_type}, Jurisdiction: {jurisdiction}")
        
        if search_type == 'company':
            response = api.search_companies(query=query, jurisdiction_code=jurisdiction)
            print(f"OpenCorporates API response: {response}")
            
            # If we get an authorization error, try web scraping as fallback
            if 'error' in response and '401' in str(response.get('error')):
                print("OpenCorporates API requires authentication. Using web search fallback...")
                # Return a message to the user
                return jsonify({
                    'success': False,
                    'results': [],
                    'error': 'OpenCorporates now requires an API key. Please get a free key at https://opencorporates.com/api_accounts/new',
                    'query': query,
                    'source': 'opencorporates'
                })
            
            if 'results' in response and 'companies' in response['results']:
                for company_wrapper in response['results']['companies']:
                    company = company_wrapper.get('company', {})
                    
                    # Extract company data
                    company_name = company.get('name', '').strip()
                    if not company_name:
                        print(f"WARNING: OpenCorporates returned company without name: {company}")
                        continue  # Skip companies without names
                        
                    result = {
                        'name': company_name,
                        'jurisdiction': company.get('jurisdiction_code', '').upper(),
                        'company_number': company.get('company_number', ''),
                        'status': company.get('current_status', ''),
                        'incorporation_date': company.get('incorporation_date', ''),
                        'type': 'company',
                        'source': 'opencorporates',
                        'url': company.get('opencorporates_url', ''),
                        'raw_data': company
                    }
                    
                    # Extract address if available
                    if 'registered_address' in company and company['registered_address']:
                        address_parts = []
                        addr = company['registered_address']
                        if addr:  # Check if addr is not None
                            for field in ['street_address', 'locality', 'region', 'postal_code', 'country']:
                                if field in addr and addr[field]:
                                    address_parts.append(addr[field])
                            if address_parts:
                                raw_address = ', '.join(address_parts)
                                if should_clean_with_claude(raw_address):
                                    result['address'] = clean_with_claude(raw_address)
                                else:
                                    result['address'] = raw_address
                    
                    # Extract officers if available
                    if 'officers' in company and company['officers']:
                        result['officers'] = []
                        for officer_wrapper in company['officers']:
                            officer = officer_wrapper.get('officer', {})
                            result['officers'].append({
                                'name': officer.get('name', 'Unknown'),
                                'position': officer.get('position', ''),
                                'start_date': officer.get('start_date', ''),
                                'end_date': officer.get('end_date', '')
                            })
                    
                    # Try to get officers via a separate API call if not included
                    if 'officers' not in result or not result['officers']:
                        # OpenCorporates often requires a separate call to get officers
                        print(f"No officers in initial result, fetching details for {company.get('name')} - {company.get('jurisdiction_code')}/{company.get('company_number')}")
                        officers_response = api.get_company_details(
                            company.get('jurisdiction_code', ''), 
                            company.get('company_number', '')
                        )
                        print(f"Officer detail response: {officers_response}")
                        if 'results' in officers_response and 'company' in officers_response['results']:
                            detailed_company = officers_response['results']['company']
                            if 'officers' in detailed_company and detailed_company['officers']:
                                result['officers'] = []
                                for officer_wrapper in detailed_company['officers']:
                                    officer = officer_wrapper.get('officer', {})
                                    result['officers'].append({
                                        'name': officer.get('name', 'Unknown'),
                                        'position': officer.get('position', ''),
                                        'start_date': officer.get('start_date', ''),
                                        'end_date': officer.get('end_date', '')
                                    })
                                print(f"Found {len(result['officers'])} officers in detailed response")
                    
                    results.append(result)
                    
        elif search_type == 'officer':
            response = api.search_officers(query=query, jurisdiction_code=jurisdiction)
            if 'results' in response and 'officers' in response['results']:
                for officer_wrapper in response['results']['officers']:
                    officer = officer_wrapper.get('officer', {})
                    
                    result = {
                        'name': officer.get('name', 'Unknown'),
                        'position': officer.get('position', ''),
                        'company_name': officer.get('company', {}).get('name', '') if officer.get('company') else '',
                        'company_number': officer.get('company', {}).get('company_number', '') if officer.get('company') else '',
                        'jurisdiction': officer.get('jurisdiction_code', '').upper(),
                        'start_date': officer.get('start_date', ''),
                        'end_date': officer.get('end_date', ''),
                        'type': 'person',
                        'source': 'opencorporates',
                        'raw_data': officer
                    }
                    
                    results.append(result)
        
        return jsonify({
            'success': True,
            'results': results,
            'total': len(results),
            'query': query,
            'source': 'opencorporates'
        })
        
    except Exception as e:
        print(f"OpenCorporates search error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/aleph/search', methods=['POST'])
def aleph_search():
    """Search OCCRP Aleph for investigative data including offshore leaks"""
    try:
        from occrp_aleph import AlephSearcher
        import asyncio
        
        data = request.json
        query = data.get('query', '')
        max_results = data.get('max_results', 50)
        schemas = data.get('schemas', None)  # Optional: filter by schema types
        
        if not query:
            return jsonify({'error': 'Query parameter is required'}), 400
        
        searcher = AlephSearcher()
        
        # Run the async search
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Use parallel search for better performance
            raw_results = loop.run_until_complete(
                searcher.search_parallel(query=query, max_results=max_results, schemas=schemas)
            )
        finally:
            loop.close()
        
        # Process results for our node format
        results = []
        relationships = []  # Track relationships to create connections later
        
        for item in raw_results:
            props = item.get('properties', {})
            schema = item.get('schema', '')
            
            # Enhanced debug logging
            print(f"\n=== Aleph result #{len(results)+1} ===")
            print(f"Schema: {schema}")
            print(f"Title: {item.get('title', 'NO TITLE')}")
            print(f"Caption: {item.get('caption', 'NO CAPTION')}")
            print(f"Name: {item.get('name', 'NO NAME')}")
            print(f"Available top-level fields: {list(item.keys())}")
            print(f"Full item data: {json.dumps(item, indent=2, ensure_ascii=False)}")
            
            # Log relationship data
            if 'links' in item and item['links']:
                print(f"Links found: {item['links']}")
            if 'edge' in item and item['edge']:
                print(f"Edge data: {item['edge']}")
            if 'roles' in item and item['roles']:
                print(f"Roles found: {item['roles']}")
                
            if props:
                print(f"Properties available: {list(props.keys())}")
                # Log name-related properties
                for name_field in ['name', 'label', 'alias', 'aliases', 'legalName', 'tradingName', 'previousName']:
                    if name_field in props:
                        print(f"  {name_field}: {props[name_field]}")
                        
            # Log if this is a relationship entity
            if schema in ['Directorship', 'Ownership', 'Membership', 'Employment']:
                print(f"RELATIONSHIP ENTITY FOUND: {schema}")
                if 'director' in props:
                    print(f"  Director: {props['director']}")
                if 'organization' in props:
                    print(f"  Organization: {props['organization']}")
                if 'person' in props:
                    print(f"  Person: {props['person']}")
                if 'company' in props:
                    print(f"  Company: {props['company']}")
            
            # Base result structure
            result = {
                'title': item.get('title', 'Unknown'),
                'url': item.get('url', ''),
                'snippet': item.get('snippet', ''),
                'schema': schema,
                'source': 'aleph',
                'raw_data': item
            }
            
            # Map to our node types based on schema
            if schema in ['Company', 'LegalEntity', 'Organization']:
                result['type'] = 'company'
                
                # Enhanced company name extraction - check multiple fields
                company_name = None
                
                # 1. Try top-level fields
                for field in ['title', 'caption', 'name', 'label']:
                    if field in item and item[field]:
                        company_name = item[field]
                        print(f"  Found company name in {field}: {company_name}")
                        break
                
                # 2. Try properties if no top-level name found
                if not company_name and props:
                    # Check various name properties
                    name_props = ['name', 'legalName', 'label', 'tradingName', 'alias', 'previousName', 'registeredName']
                    for prop in name_props:
                        if prop in props and props[prop]:
                            prop_value = props[prop]
                            if isinstance(prop_value, list) and prop_value:
                                company_name = prop_value[0]
                            elif isinstance(prop_value, str):
                                company_name = prop_value
                            if company_name:
                                print(f"  Found company name in property {prop}: {company_name}")
                                break
                
                # 3. Try to extract from highlights if still no name
                if not company_name and 'highlight' in item:
                    highlights = item.get('highlight', {})
                    if isinstance(highlights, dict):
                        for field, values in highlights.items():
                            if values and isinstance(values, list):
                                # Extract text from highlight (remove HTML tags)
                                import re
                                clean_text = re.sub('<[^>]+>', '', str(values[0]))
                                if clean_text and len(clean_text) > 3:
                                    company_name = clean_text
                                    print(f"  Extracted company name from highlight {field}: {company_name}")
                                    break
                
                # 4. Last resort - use any available identifier
                if not company_name:
                    # Try registration number or other identifiers
                    if 'registrationNumber' in props and props['registrationNumber']:
                        reg_num = props['registrationNumber'][0] if isinstance(props['registrationNumber'], list) else props['registrationNumber']
                        company_name = f"Company {reg_num}"
                        print(f"  Using registration number as name: {company_name}")
                    elif 'id' in item:
                        company_name = f"Entity {item['id'][:8]}"
                        print(f"  Using ID as name: {company_name}")
                
                result['name'] = company_name or 'Unknown Company'
                result['jurisdiction'] = props.get('jurisdiction', [''])[0] if isinstance(props.get('jurisdiction'), list) else props.get('jurisdiction', '')
                
            elif schema in ['Person']:
                result['type'] = 'person'
                
                # Enhanced person name extraction
                person_name = None
                
                # 1. Try top-level fields
                for field in ['title', 'caption', 'name', 'label']:
                    if field in item and item[field]:
                        person_name = item[field]
                        print(f"  Found person name in {field}: {person_name}")
                        break
                
                # 2. Try properties if no top-level name found
                if not person_name and props:
                    name_props = ['name', 'fullName', 'label', 'alias', 'aliases', 'firstName', 'lastName']
                    for prop in name_props:
                        if prop in props and props[prop]:
                            prop_value = props[prop]
                            if isinstance(prop_value, list) and prop_value:
                                person_name = prop_value[0]
                            elif isinstance(prop_value, str):
                                person_name = prop_value
                            if person_name:
                                print(f"  Found person name in property {prop}: {person_name}")
                                break
                    
                    # Try combining first and last name if available
                    if not person_name and 'firstName' in props and 'lastName' in props:
                        first = props['firstName'][0] if isinstance(props['firstName'], list) else props['firstName']
                        last = props['lastName'][0] if isinstance(props['lastName'], list) else props['lastName']
                        if first and last:
                            person_name = f"{first} {last}"
                            print(f"  Constructed person name: {person_name}")
                
                # 3. Extract from highlights if still no name
                if not person_name and 'highlight' in item:
                    highlights = item.get('highlight', {})
                    if isinstance(highlights, dict):
                        for field, values in highlights.items():
                            if values and isinstance(values, list):
                                import re
                                clean_text = re.sub('<[^>]+>', '', str(values[0]))
                                if clean_text and len(clean_text) > 3:
                                    person_name = clean_text
                                    print(f"  Extracted person name from highlight: {person_name}")
                                    break
                
                result['name'] = person_name or 'Unknown Person'
                
                # Extract birthdate if available
                if 'birthDate' in props:
                    result['birth_date'] = props['birthDate'][0] if isinstance(props['birthDate'], list) else props['birthDate']
                    
            elif schema in ['Address']:
                result['type'] = 'address'
                raw_value = item.get('title', 'Unknown')
                if should_clean_with_claude(raw_value):
                    result['value'] = clean_with_claude(raw_value)
                else:
                    result['value'] = raw_value
                
            elif schema in ['Directorship', 'Ownership', 'Membership', 'Employment']:
                # Handle relationship entities (Directorship, Ownership, etc.)
                result['type'] = 'relationship'
                result['relationship_type'] = schema.lower()
                
                # Extract person and company from the relationship
                if 'director' in props or 'person' in props:
                    person_prop = props.get('director') or props.get('person')
                    if person_prop:
                        person_name = person_prop[0] if isinstance(person_prop, list) else person_prop
                        result['person_name'] = person_name
                        print(f"  Extracted person from {schema}: {person_name}")
                
                if 'organization' in props or 'company' in props:
                    org_prop = props.get('organization') or props.get('company')
                    if org_prop:
                        org_name = org_prop[0] if isinstance(org_prop, list) else org_prop
                        result['company_name'] = org_name
                        print(f"  Extracted company from {schema}: {org_name}")
                
                # Extract position/role
                if 'role' in props:
                    result['position'] = props['role'][0] if isinstance(props['role'], list) else props['role']
                elif 'position' in props:
                    result['position'] = props['position'][0] if isinstance(props['position'], list) else props['position']
                else:
                    result['position'] = schema  # Use schema as position (e.g., "Director")
                
                # Extract dates
                if 'startDate' in props:
                    result['start_date'] = props['startDate'][0] if isinstance(props['startDate'], list) else props['startDate']
                if 'endDate' in props:
                    result['end_date'] = props['endDate'][0] if isinstance(props['endDate'], list) else props['endDate']
                
                # Store this relationship for later processing
                relationships.append(result)
                continue  # Don't add to main results, handle separately
                
            else:
                # Default to document/other type
                result['type'] = 'document'
                
                # Still try to extract a meaningful name for document types
                doc_name = None
                
                # 1. Try top-level fields
                for field in ['title', 'caption', 'name', 'label']:
                    if field in item and item[field]:
                        doc_name = item[field]
                        print(f"  Found document name in {field}: {doc_name}")
                        break
                
                # 2. Try properties if no top-level name found
                if not doc_name and props:
                    name_props = ['name', 'label', 'title', 'caption']
                    for prop in name_props:
                        if prop in props and props[prop]:
                            prop_value = props[prop]
                            if isinstance(prop_value, list) and prop_value:
                                doc_name = prop_value[0]
                            elif isinstance(prop_value, str):
                                doc_name = prop_value
                            if doc_name:
                                print(f"  Found document name in property {prop}: {doc_name}")
                                break
                
                # 3. Extract from highlights if still no name
                if not doc_name and 'highlight' in item:
                    highlights = item.get('highlight', {})
                    if isinstance(highlights, dict):
                        for field, values in highlights.items():
                            if values and isinstance(values, list):
                                import re
                                clean_text = re.sub('<[^>]+>', '', str(values[0]))
                                if clean_text and len(clean_text) > 3:
                                    doc_name = clean_text[:100]  # Limit length
                                    print(f"  Extracted document name from highlight: {doc_name}")
                                    break
                
                result['name'] = doc_name or 'Unknown Document'
            
            # Extract common fields
            if 'email' in props:
                result['email'] = props['email'][0] if isinstance(props['email'], list) else props['email']
            if 'phone' in props:
                result['phone'] = props['phone'][0] if isinstance(props['phone'], list) else props['phone']
            if 'address' in props:
                raw_address = props['address'][0] if isinstance(props['address'], list) else props['address']
                if should_clean_with_claude(raw_address):
                    result['address'] = clean_with_claude(raw_address)
                else:
                    result['address'] = raw_address
                
            # Check if this is offshore/leak data
            if 'sourceUrl' in props or 'collection' in props:
                source_url = props.get('sourceUrl', [''])[0] if isinstance(props.get('sourceUrl'), list) else props.get('sourceUrl', '')
                collection = props.get('collection', [''])[0] if isinstance(props.get('collection'), list) else props.get('collection', '')
                
                # Flag if it's from known leak datasets
                leak_keywords = ['panama', 'paradise', 'pandora', 'offshore', 'icij', 'leak']
                if any(keyword in (source_url + collection).lower() for keyword in leak_keywords):
                    result['is_leak_data'] = True
                    result['leak_source'] = collection or 'offshore'
            
            results.append(result)
        
        # Add relationships to results with proper formatting
        for rel in relationships:
            # Create synthetic person result if we have person name
            if rel.get('person_name'):
                person_found = any(r.get('type') == 'person' and r.get('name') == rel['person_name'] for r in results)
                if not person_found:
                    results.append({
                        'type': 'person',
                        'name': rel['person_name'],
                        'company_name': rel.get('company_name'),
                        'position': rel.get('position'),
                        'start_date': rel.get('start_date'),
                        'end_date': rel.get('end_date'),
                        'source': 'aleph',
                        'from_relationship': True
                    })
            
            # Create synthetic company result if we have company name
            if rel.get('company_name'):
                company_found = any(r.get('type') == 'company' and r.get('name') == rel['company_name'] for r in results)
                if not company_found:
                    results.append({
                        'type': 'company',
                        'name': rel['company_name'],
                        'source': 'aleph',
                        'from_relationship': True
                    })
        
        print(f"\nTotal results: {len(results)} (including {len(relationships)} relationships)")
        
        return jsonify({
            'success': True,
            'results': results,
            'relationships': relationships,  # Include raw relationships for debugging
            'total': len(results),
            'query': query,
            'source': 'aleph'
        })
        
    except Exception as e:
        print(f"Aleph search error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_name>/entities', methods=['GET'])
def get_project_entities(project_name):
    """Get all entities and facts for a project"""
    try:
        if not entity_pm:
            return jsonify({'error': 'Entity features not available'}), 503
            
        # Load the project
        if not entity_pm.load_project(project_name):
            return jsonify({'error': 'Project not found'}), 404
            
        # Get all entities with their fact counts
        entities = entity_pm.get_all_entities(project_name)
        
        # Get facts for each entity
        entities_with_facts = []
        for entity in entities:
            entity_data = {
                'name': entity['entity_name'],
                'type': entity['entity_type'],
                'fact_count': entity['fact_count'],
                'facts': []
            }
            
            # Get facts for this entity
            if entity['fact_count'] > 0:
                facts = entity_pm.get_entity_facts(project_name, entity['entity_name'])
                entity_data['facts'] = facts[:10]  # Limit to first 10 facts for performance
                
            entities_with_facts.append(entity_data)
        
        return jsonify({
            'success': True,
            'project': project_name,
            'entities': entities_with_facts,
            'total_entities': len(entities),
            'total_facts': sum(e['fact_count'] for e in entities)
        })
        
    except Exception as e:
        print(f"Error getting project entities: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_name>/entity/<entity_name>/facts', methods=['GET'])
def get_entity_facts(project_name, entity_name):
    """Get all facts for a specific entity"""
    try:
        if not entity_pm:
            return jsonify({'error': 'Entity features not available'}), 503
            
        # Load the project
        if not entity_pm.load_project(project_name):
            return jsonify({'error': 'Project not found'}), 404
            
        # Get facts for the entity
        facts = entity_pm.get_entity_facts(project_name, entity_name)
        
        return jsonify({
            'success': True,
            'entity': entity_name,
            'facts': facts,
            'fact_count': len(facts)
        })
        
    except Exception as e:
        print(f"Error getting entity facts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/corporate/unified', methods=['POST'])
def unified_corporate_search():
    """Unified search across OpenCorporates and OCCRP Aleph"""
    try:
        data = request.json
        query = data.get('query', '')
        sources = data.get('sources', ['aleph'])  # OpenCorporates removed - use Corporella at /data/corporella/
        
        if not query:
            return jsonify({'error': 'Query parameter is required'}), 400
        
        all_results = []
        errors = []
        
        # Replaced by Corporella - /data/corporella/
        # OpenCorporates section removed - use Corporella for company searches
        if 'opencorporates' in sources:
            errors.append('OpenCorporates deprecated. Use Corporella at /data/corporella/')
        
        # Search Aleph if requested
        if 'aleph' in sources:
            try:
                # Create a test request context for the internal call
                with app.test_request_context(json={'query': query, 'max_results': 30}):
                    aleph_response = aleph_search()
                    if isinstance(aleph_response, tuple):
                        aleph_data = aleph_response[0].get_json()
                    else:
                        aleph_data = aleph_response.get_json()
                    if aleph_data.get('success'):
                        all_results.extend(aleph_data.get('results', []))
            except Exception as e:
                errors.append(f"Aleph error: {str(e)}")
        
        return jsonify({
            'success': True,
            'results': all_results,
            'total': len(all_results),
            'query': query,
            'sources': sources,
            'errors': errors if errors else None
        })
        
    except Exception as e:
        print(f"Unified corporate search error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/google/search', methods=['POST'])
def google_search():
    """YOUR WORKING GOOGLE SEARCH - Uses your proven GoogleSearch class"""
    global GoogleSearch  # Make GoogleSearch available to the runner module
    
    try:
        data = request.json
        query = data.get('query', '')
        max_results = data.get('max_results', 10)  # Match your working implementation
        run_mode = data.get('run_mode', 'simple')  # 'simple' or 'exhaustive'
        
        if not query:
            return jsonify({'error': 'Query parameter is required'}), 400
            
        # Initialize your proven GoogleSearch class
        google_search_engine = GoogleSearch()
        
        if run_mode == 'exhaustive' and ExactPhraseRecallRunner:
            # Run FULL ExactPhraseRecallRunner with all permutations
            print(f"🚀 RUNNING EXHAUSTIVE RECALL for: '{query}'")
            
            # Full site list from your code
            SITES = [
                # Generic TLDs 
                ".com", ".org", ".net", ".gov", ".edu", ".info", ".biz", ".ac", ".ai", ".io",
                # European ccTLDs 
                ".eu", ".al", ".ad", ".at", ".by", ".be", ".ba", ".bg", ".hr", ".cz", ".dk", 
                ".ee", ".fo", ".fi", ".fr", ".de", ".gi", ".gr", ".hu", ".is", ".ie", ".it", 
                ".lv", ".li", ".lt", ".lu", ".mk", ".mt", ".md", ".mc", ".me", ".nl", ".no", 
                ".pl", ".pt", ".ro", ".ru", ".sm", ".rs", ".sk", ".si", ".es", ".se", ".ch", 
                ".tr", ".ua", ".uk", ".va", ".cy",
                # South American ccTLDs
                ".ar", ".bo", ".br", ".cl", ".co", ".ec", ".fk", ".gf", ".gy", ".py", ".pe", 
                ".sr", ".uy", ".ve",
                # Central Asian ccTLDs
                ".kz", ".kg", ".tj", ".tm", ".uz",
                # Commonwealth ccTLDs (Selected)
                ".ag", ".bs", ".bb", ".bz", ".bw", ".bn", ".cm", ".dm", ".fj", ".gm", ".gh",
                ".gd", ".jm", ".ke", ".ki", ".ls", ".mw", ".mv", ".mu", ".mz", ".na",
                ".nr", ".pk", ".pg", ".rw", ".kn", ".lc", ".vc", ".ws", ".sc", ".sl", ".sb", ".lk",
                ".sz", ".tz", ".to", ".tt", ".tv", ".ug", ".vu", ".zm", ".zw",
                # Other potentially relevant TLDs
                ".ca", ".mx", ".au", ".jp", ".cn", ".in", ".kr", ".za", ".id", ".ir", ".sa", ".ae", ".ph", ".hk", ".tw", ".nz", ".eg", ".il"
            ]
            SITES = sorted(list(set(SITES)))
            
            # Chunk sites into groups of 30 (Google's limit)
            site_groups = list(chunk_sites(SITES, max_terms=30))
            
            # Time slices (Google CSE doesn't support dateRestrict well, but included for completeness)
            time_slices = [{}]  # No date filter
            
            print(f"📊 Total TLDs: {len(SITES)}")
            print(f"📊 Site groups: {len(site_groups)}")
            
            # Pass GoogleSearch instance to the runner
            runner = ExactPhraseRecallRunner(
                phrase=query,
                google=google_search_engine,
                site_groups=site_groups,
                time_slices=time_slices,
                max_results_per_query=max_results,
                use_parallel=True,
                max_workers=4
            )
            
            # Run all permutations with debugging
            print(f"🚀 Starting runner.run()...")
            all_results = runner.run()
            print(f"🔍 runner.run() returned {len(all_results)} results")
            
            if all_results:
                print(f"📊 Sample result structure: {all_results[0] if all_results else 'None'}")
            else:
                print(f"❌ WARNING: runner.run() returned empty list!")
                # Debug the runner's internal state
                print(f"📊 Runner._store has {len(runner._store)} items")
                if hasattr(runner, '_store') and runner._store:
                    print(f"📊 Sample from _store: {list(runner._store.items())[0]}")
            
            # Optionally run exception search if requested
            run_exception = data.get('run_exception', False)
            if run_exception and len(all_results) > 0:
                print(f"\n🔍 Running exception search...")
                exception_results = runner.run_exception_search()
                all_results.extend(exception_results)
                print(f"📊 Exception search found {len(exception_results)} additional results")
            
            # Extract URLs for compatibility
            urls = [r.get('url', '') for r in all_results if r.get('url')]
            
            # Count queries by type
            query_counts = {}
            for result in all_results:
                tag = result.get('query_tag', 'Unknown')
                query_counts[tag] = query_counts.get(tag, 0) + 1
            
            print(f"\n🎯 EXHAUSTIVE SEARCH COMPLETE:")
            print(f"   Total unique URLs found: {len(urls)}")
            print(f"   Results by query type: {query_counts}")
            
            response_data = {
                'success': True,
                'query': query,
                'urls': urls,
                'results': all_results,
                'total_urls': len(urls),
                'query_counts': query_counts,
                'total_tlds': len(SITES),
                'site_groups': len(site_groups),
                'source': 'exhaustive_recall_runner'
            }
            
            return jsonify(response_data)
            
        else:
            # Simple single query mode
            print(f"🔍 USING YOUR WORKING GoogleSearch.google_base() for: '{query}'")
            
            results, estimated_count = google_search_engine.google_base(query, max_results)
            
            # Extract URLs and prepare rich result data
            urls = []
            rich_results = []
            
            for result in results:
                url = result.get('url', '')
                title = result.get('title', '[No Title]')
                snippet = result.get('snippet', '[No Snippet]')
                
                if url:
                    urls.append(url)
                    rich_results.append({
                        'url': url,
                        'title': title,
                        'snippet': snippet
                    })
            
            print(f"🎯 YOUR GoogleSearch.google_base() returned {len(urls)} URLs for '{query}'")
            print(f"📊 Estimated total results: {estimated_count}")
            
            # Return in format expected by frontend
            response_data = {
                'success': True,
                'query': query,
                'urls': urls,  # For backward compatibility
                'results': rich_results,  # Rich results with title/snippet
                'total_urls': len(urls),
                'estimated_count': estimated_count,
                'source': 'user_working_google_search'
            }
            
            print(f"🚀 RETURNING YOUR WORKING RESULTS TO CLIENT:")
            print(f"   URLs: {len(urls)}")
            print(f"   Rich results: {len(rich_results)}")
            for i, result in enumerate(rich_results[:3]):  # Show first 3 results
                print(f"   {i+1}. {result['title']}")
                print(f"      URL: {result['url']}")
                print(f"      Snippet: {result['snippet'][:100]}...")
            
            return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ YOUR GoogleSearch failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ahrefs/backlinks', methods=['POST'])
def get_ahrefs_backlinks():
    """Get backlinks for a domain or specific URL using Ahrefs API"""
    try:
        data = request.json
        domain = data.get('domain', '').strip()
        url = data.get('url', '').strip()
        mode = data.get('mode', 'domain')  # 'domain' or 'exact'
        
        if not domain:
            return jsonify({'error': 'Domain is required'}), 400
            
        if not AHREFS_API_KEY:
            return jsonify({'error': 'Ahrefs API key not configured'}), 500
        
        # Clean up domain - remove protocol if present
        if domain.startswith(('http://', 'https://')):
            domain = domain.split('://', 1)[1]
        domain = domain.rstrip('/')
        
        # Determine target based on mode
        if mode == 'exact' and url:
            target = url
            api_mode = 'exact'
            print(f"📄 Fetching page backlinks for URL: {url}")
        else:
            target = domain
            api_mode = 'domain'
            print(f"🔗 Fetching domain backlinks for: {domain}")
        
        # Ahrefs API parameters
        params = {
            'from': 'backlinks',
            'target': target,
            'mode': api_mode,
            'limit': 50,
            'output': 'json',
            'token': AHREFS_API_KEY,
            'order_by': 'ahrefs_rank:desc'
        }
        
        response = requests.get(AHREFS_ENDPOINT, params=params)
        
        if response.status_code == 200:
            data = response.json()
            refpages = data.get('refpages', [])
            
            # Basic filtering to remove obvious SEO spam
            spam_patterns = ['seo', 'backlink', 'link-building', 'directory', 'submit']
            filtered_refs = []
            
            for ref in refpages:
                url = ref.get('url_from', '').lower()
                # Skip if URL contains spam patterns
                if not any(pattern in url for pattern in spam_patterns):
                    filtered_refs.append({
                        'url': ref.get('url_from', ''),
                        'domain': urllib.parse.urlparse(ref.get('url_from', '')).netloc,
                        'anchor_text': ref.get('anchor', ''),
                        'ahrefs_rank': ref.get('ahrefs_rank', 0),
                        'first_seen': ref.get('first_seen', ''),
                        'dofollow': not ref.get('nofollow', False)
                    })
            
            print(f"✅ Found {len(filtered_refs)} quality backlinks (filtered from {len(refpages)})")
            
            return jsonify({
                'success': True,
                'domain': domain,
                'backlinks': filtered_refs[:50],  # Return top 50
                'total_found': len(filtered_refs),
                'total_raw': len(refpages)
            })
            
        elif response.status_code == 401:
            return jsonify({'error': 'Invalid API key'}), 401
        elif response.status_code == 429:
            return jsonify({'error': 'API rate limit exceeded'}), 429
        else:
            return jsonify({'error': f'API error: {response.status_code}'}), response.status_code
            
    except Exception as e:
        print(f"❌ Ahrefs API error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/screenshot/capture', methods=['POST'])
def capture_screenshot():
    """Capture a full-page screenshot of a URL using Firecrawl API"""
    try:
        data = request.json
        url = data.get('url')
        node_id = data.get('nodeId')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
            
        if not FIRECRAWL_API_KEY:
            return jsonify({'error': 'Firecrawl API key not configured'}), 500
        
        print(f"📸 Capturing screenshot for: {url}")
        
        # Prepare Firecrawl request
        headers = {
            'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Use simple format that works
        payload = {
            'url': url,
            'formats': ['screenshot']
        }
        
        # Make request to Firecrawl
        response = requests.post(FIRECRAWL_API_URL, json=payload, headers=headers, timeout=35)
        
        if response.status_code == 401:
            return jsonify({'error': 'Invalid API key'}), 401
        elif response.status_code == 429:
            return jsonify({'error': 'Rate limit exceeded'}), 429
        elif response.status_code == 403:
            print(f"❌ 403 Forbidden - Check API key permissions")
            print(f"API Key used: {FIRECRAWL_API_KEY[:10]}...{FIRECRAWL_API_KEY[-4:]}")
            print(f"Request URL: {FIRECRAWL_API_URL}")
            print(f"Request payload: {json.dumps(payload, indent=2)}")
            try:
                error_detail = response.json()
                print(f"Error details: {json.dumps(error_detail, indent=2)}")
            except Exception as e:
                print(f"Raw response: {response.text}")
            return jsonify({'error': 'API access forbidden - check API key or endpoint'}), 403
        elif response.status_code != 200:
            print(f"❌ API error {response.status_code}: {response.text}")
            return jsonify({'error': f'Firecrawl API error: {response.status_code}'}), response.status_code
        
        result = response.json()
        
        # Extract screenshot from response
        if result.get('success') and result.get('data'):
            # Check for screenshot URL in the data
            screenshot_url = result['data'].get('screenshot')
            
            if screenshot_url:
                print(f"✅ Screenshot captured successfully")
                
                # Download the screenshot and convert to base64
                img_response = requests.get(screenshot_url, timeout=10)
                if img_response.status_code == 200:
                    import base64
                    screenshot_base64 = base64.b64encode(img_response.content).decode('utf-8')
                    screenshot_data = f"data:image/png;base64,{screenshot_base64}"
                    
                    return jsonify({
                        'success': True,
                        'nodeId': node_id,
                        'screenshot': screenshot_data
                    })
                else:
                    return jsonify({'error': 'Failed to download screenshot'}), 500
            else:
                print(f"Response structure: {json.dumps(result, indent=2)}")
                return jsonify({'error': 'No screenshot URL found in response'}), 500
        else:
            print(f"API Response: {json.dumps(result, indent=2) if result else 'No result'}")
            return jsonify({'error': 'Screenshot capture failed - check server logs'}), 500
            
    except requests.exceptions.Timeout:
        print("⏱️ Screenshot capture timed out")
        return jsonify({'error': 'Screenshot capture timed out'}), 504
    except Exception as e:
        print(f"❌ Screenshot capture error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/url/outlinks', methods=['POST'])
def get_url_outlinks():
    """Get all outgoing links from a URL using Firecrawl API"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
            
        if not FIRECRAWL_API_KEY:
            return jsonify({'error': 'Firecrawl API key not configured'}), 500
        
        print(f"🔗 Fetching outlinks for: {url}")
        
        # Prepare Firecrawl request
        headers = {
            'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Request links format to get all links from the page
        payload = {
            'url': url,
            'formats': ['links'],
            'onlyMainContent': True
        }
        
        # Make request to Firecrawl
        response = requests.post(FIRECRAWL_API_URL, json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200:
            return jsonify({'error': f'Firecrawl API error: {response.status_code}'}), response.status_code
        
        result = response.json()
        
        if result.get('success') and result.get('data'):
            links = result['data'].get('links', [])
            
            # Parse the base domain for categorization
            from urllib.parse import urlparse
            parsed_base = urlparse(url)
            base_domain = parsed_base.netloc
            
            # Categorize links as internal or external
            outlinks = []
            internal_count = 0
            external_count = 0
            
            for link in links:
                parsed_link = urlparse(link)
                is_internal = parsed_link.netloc == base_domain or parsed_link.netloc == ''
                
                if is_internal:
                    internal_count += 1
                    # Make relative URLs absolute
                    if not parsed_link.netloc:
                        link = f"{parsed_base.scheme}://{base_domain}{link}"
                else:
                    external_count += 1
                
                outlinks.append({
                    'url': link,
                    'type': 'internal' if is_internal else 'external',
                    'domain': parsed_link.netloc or base_domain
                })
            
            print(f"✅ Found {len(outlinks)} outlinks ({internal_count} internal, {external_count} external)")
            
            return jsonify({
                'success': True,
                'url': url,
                'outlinks': outlinks,
                'total': len(outlinks),
                'internal_count': internal_count,
                'external_count': external_count
            })
        else:
            return jsonify({'error': 'Failed to extract links'}), 500
            
    except Exception as e:
        print(f"❌ Outlinks extraction error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/url/extract-entities', methods=['POST'])
def extract_url_entities():
    """Extract entities and relationships from a URL using Firecrawl + Claude"""
    try:
        data = request.json
        url = data.get('url')
        node_id = data.get('nodeId')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
            
        if not FIRECRAWL_API_KEY:
            return jsonify({'error': 'Firecrawl API key not configured'}), 500
        
        print(f"🧠 Extracting entities from: {url}")
        
        # Step 1: Scrape the webpage content using Firecrawl
        headers = {
            'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'url': url,
            'formats': ['markdown'],  # Get markdown content for Claude
            'onlyMainContent': True,  # Focus on main content
            'waitFor': 5000,  # Wait for dynamic content
            'timeout': 30000,
            'blockAds': True,
            'removeBase64Images': True  # Don't need images for text extraction
        }
        
        print("📄 Scraping webpage content...")
        response = requests.post(FIRECRAWL_API_URL, json=payload, headers=headers, timeout=35)
        
        if response.status_code != 200:
            return jsonify({'error': f'Firecrawl error: {response.status_code}'}), response.status_code
        
        result = response.json()
        
        # Extract markdown content
        markdown_content = ""
        if result.get('success') and result.get('data'):
            markdown_content = result['data'].get('markdown', '')
            page_title = result['data'].get('metadata', {}).get('title', '')
            
        if not markdown_content:
            return jsonify({'error': 'No content extracted from URL'}), 500
        
        # Limit content length to avoid token limits
        if len(markdown_content) > 50000:
            markdown_content = markdown_content[:50000] + "\n\n[Content truncated...]"
        
        print(f"📝 Extracted {len(markdown_content)} characters of content")
        
        # Step 2: Extract entities using Claude (reuse the vision API's tool structure)
        tools = [
            {
                "name": "extract_entities_and_relationships",
                "description": "Extract entities and relationships from webpage content",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "value": {
                                        "type": "string",
                                        "description": "The exact extracted text/information"
                                    },
                                    "type": {
                                        "type": "string",
                                        "enum": ["name", "company", "email", "phone", "address"],
                                        "description": "Type of entity - ONLY extract people names, companies, email addresses, phone numbers, and physical addresses"
                                    },
                                    "confidence": {
                                        "type": "string",
                                        "enum": ["high", "medium", "low"]
                                    },
                                    "notes": {
                                        "type": "string",
                                        "description": "Context about where/how this was found"
                                    }
                                },
                                "required": ["value", "type", "confidence", "notes"]
                            }
                        },
                        "relationships": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source": {"type": "string"},
                                    "target": {"type": "string"},
                                    "relationship": {"type": "string"},
                                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                    "notes": {"type": "string"}
                                },
                                "required": ["source", "target", "relationship", "confidence", "notes"]
                            }
                        }
                    },
                    "required": ["entities", "relationships"]
                }
            }
        ]
        
        print("🤖 Analyzing content with Claude...")
        
        # Call Claude with the webpage content
        response = anthropic_client.messages.create(
            model='claude-sonnet-4-5-20250929',
            max_tokens=4000,
            temperature=0.1,
            tools=tools,
            tool_choice={"type": "tool", "name": "extract_entities_and_relationships"},
            messages=[{
                'role': 'user',
                'content': f'''Analyze this webpage content and extract ALL entities and relationships.

URL: {url}
Title: {page_title}

CONTENT:
{markdown_content}

EXTRACTION REQUIREMENTS:
1. Extract ALL people, companies, organizations, products, services
2. Extract ALL contact information (emails, phones, addresses, social media)
3. Extract ALL dates, locations, URLs mentioned
4. Identify ALL relationships between entities
5. For companies/organizations: look for employees, leadership, partnerships
6. For people: look for roles, affiliations, connections
7. Include partial information (even first names are valuable)
8. Pay attention to:
   - About pages: team members, company history
   - Contact pages: all contact details
   - Product pages: features, pricing, related services
   - Blog posts: authors, mentioned people/companies
   
Extract EVERYTHING that could be useful for investigation or research.'''
            }]
        )
        
        # Parse Claude's response
        entities = []
        relationships = []
        
        for content in response.content:
            if hasattr(content, 'type') and content.type == 'tool_use':
                if hasattr(content, 'input'):
                    entities = content.input.get('entities', [])
                    relationships = content.input.get('relationships', [])
                    break
        
        print(f"✅ Extracted {len(entities)} entities and {len(relationships)} relationships")
        
        return jsonify({
            'success': True,
            'nodeId': node_id,
            'entities': entities,
            'relationships': relationships,
            'metadata': {
                'url': url,
                'title': page_title,
                'contentLength': len(markdown_content),
                'extractedAt': datetime.now().isoformat()
            }
        })
        
    except requests.exceptions.Timeout:
        print("⏱️ Entity extraction timed out")
        return jsonify({'error': 'Extraction timed out'}), 504
    except Exception as e:
        print(f"❌ Entity extraction error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/file/extract-entities', methods=['POST'])
def extract_file_entities():
    """Extract entities and relationships from uploaded MD file using Claude"""
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
            
        file = request.files['file']
        
        # Check if file has a filename
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        # Check file extension
        if not file.filename.lower().endswith('.md'):
            return jsonify({'error': 'Only .md files are supported'}), 400
            
        # Read file content (no size limit - we'll chunk it)
        file_content = file.read()
        print(f"📏 File size: {len(file_content) / 1024 / 1024:.2f} MB")
            
        # Decode content
        try:
            markdown_content = file_content.decode('utf-8')
        except UnicodeDecodeError:
            return jsonify({'error': 'Invalid file encoding. Please use UTF-8'}), 400
            
        print(f"📄 Processing MD file: {file.filename} ({len(markdown_content)} characters)")
        
        # Process in chunks if content is large
        chunk_size = 30000  # Safe size for Claude
        chunks = []
        
        if len(markdown_content) > chunk_size:
            # Split into chunks
            for i in range(0, len(markdown_content), chunk_size):
                chunk = markdown_content[i:i + chunk_size]
                chunks.append(chunk)
            print(f"📚 Split into {len(chunks)} chunks for processing")
        else:
            # Single chunk for small files
            chunks = [markdown_content]
            
        # Extract entities using Claude (reuse the same tool structure)
        tools = [
            {
                "name": "extract_entities_and_relationships",
                "description": "Extract entities and relationships from markdown content",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "value": {
                                        "type": "string",
                                        "description": "The exact extracted text/information"
                                    },
                                    "type": {
                                        "type": "string",
                                        "enum": ["name", "company", "email", "phone", "address"],
                                        "description": "Type of entity - ONLY extract people names, companies, email addresses, phone numbers, and physical addresses"
                                    },
                                    "confidence": {
                                        "type": "string",
                                        "enum": ["high", "medium", "low"]
                                    },
                                    "notes": {
                                        "type": "string",
                                        "description": "Context about where/how this was found"
                                    }
                                },
                                "required": ["value", "type", "confidence", "notes"]
                            }
                        },
                        "relationships": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source": {"type": "string"},
                                    "target": {"type": "string"},
                                    "relationship": {"type": "string"},
                                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                    "notes": {"type": "string"}
                                },
                                "required": ["source", "target", "relationship", "confidence", "notes"]
                            }
                        }
                    },
                    "required": ["entities", "relationships"]
                }
            }
        ]
        
        print("🤖 Analyzing content with Claude...")
        
        # Function to process a single chunk
        def process_chunk(chunk_data):
            i, chunk = chunk_data
            print(f"📊 Processing chunk {i+1}/{len(chunks)}...")
            
            try:
                # Call Claude with each chunk
                response = anthropic_client.messages.create(
                    model='claude-sonnet-4-5-20250929',
                    max_tokens=4000,
                    temperature=0.1,
                    tools=tools,
                    tool_choice={"type": "tool", "name": "extract_entities_and_relationships"},
                    messages=[{
                        'role': 'user',
                        'content': f'''Analyze this portion of a markdown document and extract ALL entities and relationships.

FILENAME: {file.filename}
CHUNK: {i+1} of {len(chunks)}

CONTENT:
{chunk}

EXTRACTION REQUIREMENTS:
ONLY extract these 5 types of entities:
1. PEOPLE NAMES (type: "name") - Full names, first names, last names of individuals
2. COMPANIES (type: "company") - Company names, organization names, business names
3. EMAIL ADDRESSES (type: "email") - All email addresses
4. PHONE NUMBERS (type: "phone") - All phone numbers, mobile numbers, landlines
5. PHYSICAL ADDRESSES (type: "address") - Street addresses, postal addresses, locations

DO NOT extract:
- Numbers, amounts, dates, URLs, usernames, domains, products, services
- Only extract the 5 types listed above
- For relationships, focus on connections between people and companies

Be precise and only extract what is explicitly requested.'''
                    }]
                )
                
                # Parse Claude's response for this chunk
                chunk_entities = []
                chunk_relationships = []
                
                for content in response.content:
                    if hasattr(content, 'type') and content.type == 'tool_use':
                        if hasattr(content, 'input'):
                            chunk_entities = content.input.get('entities', [])
                            chunk_relationships = content.input.get('relationships', [])
                            break
                
                print(f"✅ Chunk {i+1}: Found {len(chunk_entities)} entities and {len(chunk_relationships)} relationships")
                return chunk_entities, chunk_relationships
            except Exception as e:
                print(f"❌ Error processing chunk {i+1}: {e}")
                return [], []
        
        # Process all chunks in parallel
        all_entities = []
        all_relationships = []
        
        with ThreadPoolExecutor(max_workers=5) as executor:  # Limit to 5 parallel calls
            # Submit all chunks for processing
            futures = [executor.submit(process_chunk, (i, chunk)) for i, chunk in enumerate(chunks)]
            
            # Collect results as they complete
            for future in as_completed(futures):
                chunk_entities, chunk_relationships = future.result()
                all_entities.extend(chunk_entities)
                all_relationships.extend(chunk_relationships)
        
        # Merge entities with same value and type
        entity_map = {}  # key: (value, type) -> merged entity
        
        for entity in all_entities:
            key = (entity.get('value', '').lower().strip(), entity.get('type', ''))
            if not key[0]:  # Skip empty values
                continue
                
            if key in entity_map:
                # Merge notes and maintain highest confidence
                existing = entity_map[key]
                
                # Combine notes
                existing_notes = existing.get('notes', '')
                new_notes = entity.get('notes', '')
                if new_notes and new_notes not in existing_notes:
                    if existing_notes:
                        existing['notes'] = f"{existing_notes}; {new_notes}"
                    else:
                        existing['notes'] = new_notes
                
                # Keep highest confidence
                confidence_order = {'high': 3, 'medium': 2, 'low': 1}
                if confidence_order.get(entity.get('confidence', 'low'), 1) > confidence_order.get(existing.get('confidence', 'low'), 1):
                    existing['confidence'] = entity['confidence']
            else:
                # First occurrence of this entity
                entity_map[key] = entity.copy()
        
        # Convert back to list
        entities = list(entity_map.values())
        
        # Deduplicate relationships
        relationship_set = set()
        unique_relationships = []
        
        for rel in all_relationships:
            # Create a key for the relationship
            rel_key = (
                rel.get('source', '').lower().strip(),
                rel.get('target', '').lower().strip(),
                rel.get('relationship', '').lower().strip()
            )
            
            if rel_key not in relationship_set and all(rel_key):  # All components must be non-empty
                relationship_set.add(rel_key)
                unique_relationships.append(rel)
        
        relationships = unique_relationships
        
        print(f"✅ Extracted {len(entities)} entities and {len(relationships)} relationships")
        
        return jsonify({
            'success': True,
            'filename': file.filename,
            'entities': entities,
            'relationships': relationships,
            'metadata': {
                'filename': file.filename,
                'contentLength': len(markdown_content),
                'extractedAt': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        print(f"❌ File entity extraction error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Simple health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

@app.after_request
def after_request(response):
    """Add headers to allow iframe embedding from SE app"""
    # Remove X-Frame-Options to allow iframe embedding
    response.headers.pop('X-Frame-Options', None)

    # Set Content-Security-Policy to allow iframe embedding from localhost origins
    # This allows the SE app (localhost:8000) to embed the EYE-D app (localhost:5001)
    response.headers['Content-Security-Policy'] = "frame-ancestors 'self' http://localhost:* http://127.0.0.1:*"

    return response

if __name__ == '__main__':
    # Get port from environment variable or default to 5555
    port = int(os.environ.get('PORT', 5555))
    debug = os.environ.get('DEBUG', '0').strip().lower() in ('1', 'true', 'yes', 'y', 'on')

    print("DeHashed Web Visualization Server")
    print("=================================")
    print(f"Server starting on http://localhost:{port}")
    print("Open your browser and navigate to the URL above")
    print()
    app.run(debug=debug, port=port, host='127.0.0.1')
