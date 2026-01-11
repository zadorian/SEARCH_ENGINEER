#!/usr/bin/env python3
"""
Script Search - Find code/scripts.
Supports script: operator (alias for filetype:code_ext) and intelligent repositories search.
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging
from datetime import datetime
import os
import asyncio
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import search engines from engines directory
sys.path.insert(0, str(Path(__file__).parent.parent / 'engines'))

# Set up logger
logger = logging.getLogger(__name__)

# Import search engines
try:
    from exact_phrase_recall_runner_google import GoogleSearch
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_bing import BingSearch
    BING_AVAILABLE = True
except ImportError:
    BING_AVAILABLE = False

try:
    from exact_phrase_recall_runner_brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError:
    BRAVE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_duckduck import MaxExactDuckDuckGo as DuckDuckGoSearch
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False

class ScriptSearcher:
    """Search for source code and scripts"""
    
    # Common extensions for languages
    LANG_EXTENSIONS = {
        'python': ['py', 'ipynb'],
        'javascript': ['js', 'jsx', 'ts', 'tsx'],
        'java': ['java', 'jar'],
        'c': ['c', 'h'],
        'cpp': ['cpp', 'hpp', 'cc'],
        'csharp': ['cs'],
        'go': ['go'],
        'ruby': ['rb'],
        'php': ['php'],
        'shell': ['sh', 'bash', 'zsh'],
        'rust': ['rs'],
        'swift': ['swift'],
        'kotlin': ['kt'],
        'scala': ['scala'],
        'html': ['html', 'htm'],
        'css': ['css', 'scss', 'less'],
        'sql': ['sql'],
        'r': ['r'],
        'lua': ['lua'],
        'perl': ['pl'],
        'powershell': ['ps1']
    }
    
    # Code repositories
    REPOS = [
        'github.com',
        'gitlab.com',
        'bitbucket.org',
        'sourceforge.net',
        'stackoverflow.com',
        'gist.github.com',
        'pastebin.com'
    ]
    
    def __init__(self):
        self.engines = {}
        if GOOGLE_AVAILABLE: self.engines['google'] = GoogleSearch()
        if BING_AVAILABLE: self.engines['bing'] = BingSearch()
        if BRAVE_AVAILABLE: self.engines['brave'] = BraveSearch()
        if DUCKDUCKGO_AVAILABLE: self.engines['duckduckgo'] = DuckDuckGoSearch()
        
    def parse_query(self, query: str) -> Tuple[str, str]:
        """Parse script: operator"""
        # Check for script:language or script:extension
        match = re.search(r'script:([^\s]+)', query, re.IGNORECASE)
        if match:
            lang_or_ext = match.group(1).lower()
            return lang_or_ext, query.replace(match.group(0), '').strip()
        return '', query

    def get_extensions(self, lang_or_ext: str) -> List[str]:
        """Get file extensions for a language or return the extension itself"""
        if lang_or_ext in self.LANG_EXTENSIONS:
            return self.LANG_EXTENSIONS[lang_or_ext]
        return [lang_or_ext]

    def generate_variations(self, lang_or_ext: str, keywords: str) -> List[Tuple[str, str]]:
        """Generate L1/L2/L3 variations"""
        variations = []
        extensions = self.get_extensions(lang_or_ext)
        
        # L1: Filetype (Native)
        ext_parts = [f"filetype:{ext}" for ext in extensions]
        if len(ext_parts) > 1:
            l1_query = f"({' OR '.join(ext_parts)}) {keywords}".strip()
        else:
            l1_query = f"{ext_parts[0]} {keywords}".strip()
        variations.append((l1_query, 'L1'))
        
        # L2: InURL (Tricks)
        # Useful for raw code files hosted on non-standard paths
        inurl_parts = [f"inurl:.{ext}" for ext in extensions]
        if len(inurl_parts) > 1:
            l2_query = f"({' OR '.join(inurl_parts)}) {keywords}".strip()
        else:
            l2_query = f"{inurl_parts[0]} {keywords}".strip()
        variations.append((l2_query, 'L2'))
        
        # L3: Repository Search (Brute)
        # Search specifically in known code repositories
        # Limit keywords to prevent query getting too long
        clean_keywords = keywords[:100]
        repo_parts = [f"site:{repo}" for repo in self.REPOS[:4]] # Top 4 repos
        l3_query_1 = f"({' OR '.join(repo_parts)}) {clean_keywords} {lang_or_ext}".strip()
        variations.append((l3_query_1, 'L3'))
        
        # L3: Pastebin Search (Brute)
        paste_parts = [f"site:{repo}" for repo in self.REPOS[5:]] # Gist, Pastebin
        l3_query_2 = f"({' OR '.join(paste_parts)}) {clean_keywords} {lang_or_ext}".strip()
        variations.append((l3_query_2, 'L3'))
            
        return variations

    async def search(self, query: str, max_results: int = 50) -> Dict:
        lang_or_ext, keywords = self.parse_query(query)
        
        if not lang_or_ext:
            # Default to python if just checking functionality or handle generic "script" search
            # But for now, require a language
            print("No script language specified (use script:python or script:js)")
            return {'error': 'No script language specified'}
            
        print(f"\nScript search detected: {lang_or_ext}")
        
        results_data = {
            'query': query,
            'language': lang_or_ext,
            'results': [],
            'stats': {}
        }
        
        seen_urls = set()
        tasks = []
        
        for engine_name, engine in self.engines.items():
            tasks.append(self._run_engine(engine_name, engine, lang_or_ext, keywords, max_results))
            
        outputs = await asyncio.gather(*tasks, return_exceptions=True)
        
        for output in outputs:
            if isinstance(output, tuple):
                eng_name, results = output
                valid_results = []
                for r in results:
                    if r['url'] not in seen_urls:
                        seen_urls.add(r['url'])
                        r['source'] = eng_name
                        valid_results.append(r)
                
                results_data['results'].extend(valid_results)
                results_data['stats'][eng_name] = len(valid_results)
                
        return results_data

    async def _run_engine(self, name, engine, lang_or_ext, keywords, max_results):
        variations = self.generate_variations(lang_or_ext, keywords)
        all_results = []
        limit = max(10, max_results // len(variations))
        
        for q, strat in variations:
            try:
                loop = asyncio.get_event_loop()
                res = await loop.run_in_executor(None, engine.search, q, limit)
                if res:
                    for r in res:
                        r['strategy'] = strat
                        r['query'] = q
                    all_results.extend(res)
            except Exception as e:
                logger.warning(f"{name} error on {q}: {e}")
                
        return name, all_results

async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 script.py \"script:python 'hello world'\"")
        return
    
    query = sys.argv[1]
    searcher = ScriptSearcher()
    data = await searcher.search(query)
    
    print(f"\nFound {len(data['results'])} results.")
    for i, r in enumerate(data['results'][:10], 1):
        print(f"{i}. [{r['source']} - {r.get('strategy', '?')}] {r.get('title')}")
        print(f"   {r.get('url')}")

if __name__ == "__main__":
    asyncio.run(main())
