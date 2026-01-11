#!/usr/bin/env python3
"""
EYE-D LinkedIn URL Search Engine
"""

import asyncio
import re
import sys
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

# Add parent directory to path for imports (modules/eyed)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Add BRUTE engines path
brute_path = Path(__file__).resolve().parent.parent.parent.parent / "BRUTE" / "engines"
if brute_path.exists():
    sys.path.insert(0, str(brute_path))

# Imports
try:
    import rocketreach_client
    RocketReachClient = rocketreach_client.RocketReachClient
except ImportError:
    RocketReachClient = None

try:
    import contactout_client
    ContactOutClient = contactout_client.ContactOutClient
except ImportError:
    ContactOutClient = None

try:
    import kaspr_client
    KasprClient = kaspr_client.KasprClient
except ImportError:
    KasprClient = None

# BRUTE import
try:
    sys.path.insert(0, "/data/modules") # Adjust based on deployment
    from brute.brute import BruteSearchEngine
    BRUTE_AVAILABLE = True
except ImportError:
    BRUTE_AVAILABLE = False

class EyeDLinkedinEngine:
    code = 'EDL'
    name = 'EYE-D LinkedIn'

    def __init__(self, linkedin_url: str):
        self.linkedin_url = linkedin_url

    async def search_async(self) -> Dict[str, Any]:
        print(f"💼 Searching LinkedIn profile: {self.linkedin_url}")

        results = {
            'query': self.linkedin_url,
            'query_type': 'EYE-D',
            'subtype': 'linkedin',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }

        try:
            # 1. Direct Result
            results['results'].append({
                'source': 'linkedin_direct',
                'data': {'url': self.linkedin_url, 'status': 'detected'},
                'entity_type': 'linkedin',
                'entity_value': self.linkedin_url
            })

            # Extract username
            username = None
            match = re.search(r'linkedin\.com/in/([^/]+)', self.linkedin_url)
            if match:
                username = match.group(1)
                results['entities'].append({
                    'type': 'USERNAME',
                    'value': username,
                    'context': 'linkedin_handle'
                })

            # 2. RocketReach Enrichment
            if RocketReachClient:
                try:
                    rr_client = RocketReachClient()
                    rr_data = rr_client.lookup_linkedin(self.linkedin_url)
                    if rr_data:
                        results['results'].append({
                            'source': 'rocketreach',
                            'data': rr_data,
                            'entity_type': 'person_profile',
                            'entity_value': rr_data.get('name', 'Unknown')
                        })
                        # Extract entities
                        if rr_data.get('name'):
                            results['entities'].append({'type': 'NAME', 'value': rr_data.get('name'), 'context': 'rocketreach'})
                        if rr_data.get('current_employer'):
                            results['entities'].append({'type': 'COMPANY', 'value': rr_data.get('current_employer'), 'context': 'rocketreach'})
                        for email in rr_data.get('emails', []):
                            results['entities'].append({'type': 'EMAIL', 'value': email, 'context': 'rocketreach'})
                        for phone in rr_data.get('phones', []):
                            if phone:
                                results['entities'].append({'type': 'PHONE', 'value': phone, 'context': 'rocketreach'})
                except Exception as e:
                    print(f"RocketReach linkedin error: {e}")

            # 3. ContactOut Enrichment
            if ContactOutClient:
                try:
                    co_client = ContactOutClient()
                    co_data = co_client.enrich_linkedin(self.linkedin_url)
                    if co_data:
                        results['results'].append({
                            'source': 'contactout',
                            'data': co_data,
                            'entity_type': 'person_profile',
                            'entity_value': co_data.get('name', 'Unknown')
                        })
                except Exception as e:
                    print(f"ContactOut linkedin error: {e}")

            # 4. Kaspr Enrichment
            if KasprClient:
                try:
                    k_client = KasprClient()
                    k_data = k_client.enrich_linkedin(self.linkedin_url)
                    if k_data:
                        results['results'].append({
                            'source': 'kaspr',
                            'data': k_data,
                            'entity_type': 'person_profile',
                            'entity_value': k_data.get('name', 'Unknown')
                        })
                except Exception as e:
                    print(f"Kaspr linkedin error: {e}")

            # 5. BRUTE LinkedIn Search
            if username:
                try:
                    # BRUTE Company Search (local module if exists)
                    try:
                        import linkedin_company
                        linkedin_searcher = linkedin_company.LinkedInCompanySearch()
                        linkedin_urls = linkedin_searcher.generate_linkedin_urls(username)
                        results['results'].append({
                            'source': 'brute_linkedin',
                            'data': {'generated_urls': linkedin_urls},
                            'entity_type': 'linkedin_profile',
                            'entity_value': username
                        })
                    except ImportError:
                        pass

                    # BRUTE Web Search
                    if BRUTE_AVAILABLE:
                        print(f"🔍 Running BRUTE web search for: {username}")
                        brute = BruteSearchEngine(
                            keyword=f'site:linkedin.com "{username}"',
                            return_results=True,
                            engines=None
                        )
                        brute.run()
                        if brute.final_results:
                            results['results'].append({
                                'source': 'brute_web_linkedin',
                                'data': brute.final_results[:50],
                                'entity_type': 'linkedin_web_mentions',
                                'entity_value': username
                            })
                except Exception as e:
                    print(f"BRUTE search error: {e}")

            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for LinkedIn profile")

        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching LinkedIn: {e}")

        return results

    def search(self) -> List[Dict[str, Any]]:
        """Sync wrapper for search."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(self.search_async())
            return results.get('results', [])
        finally:
            loop.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        engine = EyeDLinkedinEngine(sys.argv[1])
        print(engine.search())
    else:
        print("Usage: python linkedin_url.py <url>")