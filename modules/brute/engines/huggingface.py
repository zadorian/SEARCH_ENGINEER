#!/usr/bin/env python3
"""
exact_phrase_recall_runner_huggingface.py

HuggingFace dataset search engine integration for Search_Engineer.
Searches across multiple HuggingFace datasets with AI-powered prioritization.

Features:
* AI-powered dataset prioritization using GPT-4.1-nano
* Exact phrase enforcement with quoted search support
* Streaming results from 13+ specialized datasets
* Company, financial, and domain-specific dataset coverage
* Remote API search with local fallback scanning
* Memory-efficient streaming with progress indicators

Datasets searched:
- pborchert/CompanyWeb (company web data)
- terhdavid/ner-company-dataset (NER company entities)
- fr3on/company (company names)
- SaleleadsOrg/linkedin-company-profile (LinkedIn profiles)
- Davidsv/french_energy_company_dataset (energy companies)
- HaiweiHe/linkedin-jobs (job descriptions)
- JanosAudran/financial-reports-sec (SEC reports)
- irlspbru/RFSD (research dataset)
- pkgforge-security/domains (domain security)
- nhagar/culturax_urls (cultural URLs)
- nhagar/c4_urls_multilingual (multilingual URLs)
- nhagar/hplt-v1.2_urls (HPLT URLs)
- nhagar/dolma_urls_v1.6 (Dolma URLs)
"""

import os
import sys
import logging
import asyncio
import requests
import textwrap
from typing import Dict, List, Optional, Any, Iterable
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    from shared_session import get_shared_session
    SHARED_SESSION = True
except ImportError:
    SHARED_SESSION = False


# Initialize logger first
logger = logging.getLogger("huggingface_phrase_runner")

try:
    from datasets import load_dataset
    DATASETS_AVAILABLE = True
except ImportError:
    DATASETS_AVAILABLE = False
    logger.info("INFO: datasets library not available - using remote API only")

# Add Search_Interpreter to path for AI prioritization
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "Search_Interpreter"))
    from search_interpreter import interpret_search_query
    INTERPRETER_AVAILABLE = True
except ImportError:
    INTERPRETER_AVAILABLE = False

# HuggingFace API configuration
API_BASE = "https://datasets-server.huggingface.co/search"
TOP_K = 50
HF_TOKEN = os.getenv("HF_TOKEN")
SNIPPET_LEN = 1000
ROW_LIMIT = 300_000
PROGRESS_STEP = 50_000

# Dataset configurations: (config, split, column, requires_scripted_loading)
DEFAULT_DATASETS = {
    "pborchert/CompanyWeb": ("default", "train", "text", False),
    "terhdavid/ner-company-dataset": ("default", "train", "tokens", False),
    "fr3on/company": ("default", "train", "name", False),
    "SaleleadsOrg/linkedin-company-profile": ("default", "train", "description", False),
    "Davidsv/french_energy_company_dataset": ("default", "train", "content", False),
    "HaiweiHe/linkedin-jobs": ("default", "train", "description", False),
    "JanosAudran/financial-reports-sec": ("large_full", "train", "text", True),
    "irlspbru/RFSD": ("default", "train", "text", False),
    "pkgforge-security/domains": ("default", "train", "domain", False),
    "nhagar/culturax_urls": ("default", "train", "url", False),
    "nhagar/c4_urls_multilingual": ("default", "train", "url", False),
    "nhagar/hplt-v1.2_urls": ("default", "train", "url", False),
    "nhagar/dolma_urls_v1.6": ("default", "train", "url", False),
}

# Fallback dataset order if AI interpreter unavailable
# Limited to top 5 most reliable datasets for better performance
FALLBACK_DATASETS = [
    ("fr3on/company", "default", "train", "name", False),
    ("pborchert/CompanyWeb", "default", "train", "text", False),
    ("terhdavid/ner-company-dataset", "default", "train", "tokens", False),
    ("SaleleadsOrg/linkedin-company-profile", "default", "train", "description", False),
    ("pkgforge-security/domains", "default", "train", "domain", False),
]


class HuggingFaceSearchEngine:
    """HuggingFace dataset search with remote API and local fallback"""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or HF_TOKEN
        
    def remote_search(self, dataset: str, config: str, split: str, query: str, k: int = TOP_K) -> Optional[List]:
        """Search using HuggingFace remote API"""
        params = {
            "dataset": dataset,
            "config": config, 
            "split": split,
            "query": query,
            "offset": 0,
            "length": k
        }
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        
        try:
            response = requests.get(API_BASE, params=params, headers=headers, timeout=10)
            if response.status_code == 404 or not response.ok:
                logger.debug(f"API returned {response.status_code} for {dataset}")
                return None
                
            data = response.json()
            rows = data.get("rows", [])
            return [(row["row_idx"], row["row"]) for row in rows] if rows else None
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout searching {dataset}")
            return None
        except Exception as e:
            logger.debug(f"Remote search failed for {dataset}: {e}")
            return None
    
    def local_search(self, dataset: str, split: str, column: str, query: str, k: int = TOP_K, scripted: bool = False) -> List[Dict]:
        """Local dataset streaming search with row limit"""
        if not DATASETS_AVAILABLE:
            logger.warning("Datasets library not available for local search")
            return []
            
        query_lower = query.lower()
        hits = []
        
        try:
            if scripted:
                data = load_dataset(dataset, name=split, split=split, trust_remote_code=True, streaming=False)
            else:
                data = load_dataset(dataset, split=split, streaming=True)
                
            for idx, row in enumerate(data):
                if idx >= ROW_LIMIT:
                    logger.info(f"Hit row limit ({ROW_LIMIT:,}) for {dataset}")
                    break
                    
                # Extract text from the specified column
                text = self._extract_text(row, column)
                if query_lower in text.lower():
                    hits.append(row)
                    if len(hits) >= k:
                        break
                        
        except Exception as e:
            logger.warning(f"Local search failed for {dataset}: {e}")
            
        return hits
    
    def _extract_text(self, row: Dict, column: str) -> str:
        """Extract searchable text from row data"""
        # Try the specified column first
        if column in row:
            value = row[column]
            if isinstance(value, str):
                return value
            elif isinstance(value, list):
                return " ".join(str(item) for item in value)
        
        # Fallback: find first string field
        for key, value in row.items():
            if isinstance(value, str) and value.strip():
                return value
                
        return ""


class ExactPhraseRecallRunnerHuggingFace:
    """HuggingFace search runner for Search_Engineer integration"""
    
    def __init__(self, phrase: str, token: Optional[str] = None):
        self.phrase = phrase.strip('"')
        self.search_engine = HuggingFaceSearchEngine(token)
        
    async def get_prioritized_datasets(self, query: str) -> List[tuple]:
        """Get AI-prioritized dataset order"""
        # Temporarily disable AI interpreter due to API issues
        logger.info("Using fallback dataset order - AI interpreter temporarily disabled")
        return FALLBACK_DATASETS
    
    def _search_single_dataset(self, dataset_info: tuple) -> List[Dict[str, Any]]:
        """Search a single dataset and return results"""
        dataset_name, config, split, column, scripted = dataset_info
        results = []
        
        try:
            # Try remote search first
            remote_results = self.search_engine.remote_search(dataset_name, config, split, self.phrase, TOP_K)
            
            if remote_results:
                logger.debug(f"Found {len(remote_results)} remote results in {dataset_name}")
                for row_idx, row_data in remote_results:
                    text = self.search_engine._extract_text(row_data, column)
                    
                    # Add dataset info to row_data for URL generation
                    row_data_with_context = dict(row_data)
                    row_data_with_context['dataset'] = dataset_name
                    row_data_with_context['row_index'] = row_idx
                    
                    result = {
                        'url': self._extract_url(row_data_with_context),
                        'title': self._extract_title(row_data, dataset_name),
                        'snippet': self._create_snippet(text),
                        'dataset': dataset_name,
                        'row_index': row_idx,
                        'source_type': 'huggingface_remote'
                    }
                    results.append(result)
            else:
                # Only try local search if datasets library is available
                if DATASETS_AVAILABLE:
                    logger.debug(f"No remote results, trying local search for {dataset_name}")
                    local_results = self.search_engine.local_search(dataset_name, split, column, self.phrase, TOP_K, scripted)
                    
                    if local_results:
                        logger.debug(f"Found {len(local_results)} local results in {dataset_name}")
                        for idx, row_data in enumerate(local_results):
                            text = self.search_engine._extract_text(row_data, column)
                            
                            # Add dataset info to row_data for URL generation
                            row_data_with_context = dict(row_data)
                            row_data_with_context['dataset'] = dataset_name
                            row_data_with_context['row_index'] = idx
                            
                            result = {
                                'url': self._extract_url(row_data_with_context),
                                'title': self._extract_title(row_data, dataset_name),
                                'snippet': self._create_snippet(text),
                                'dataset': dataset_name,
                                'row_index': idx,
                                'source_type': 'huggingface_local'
                            }
                            results.append(result)
                    else:
                        logger.debug(f"No results for {dataset_name} (remote failed, local unavailable)")
                        
        except Exception as e:
            logger.warning(f"Error searching {dataset_name}: {e}")
            
        return results

    def run(self) -> Iterable[Dict[str, Any]]:
        """Run HuggingFace search across prioritized datasets IN PARALLEL"""
        logger.info(f"Starting HuggingFace search for phrase: '{self.phrase}'")
        
        # Get prioritized datasets (use asyncio.run for sync compatibility)
        try:
            datasets = asyncio.run(self.get_prioritized_datasets(self.phrase))
        except Exception as e:
            logger.warning(f"Failed to get prioritized datasets: {e}")
            datasets = FALLBACK_DATASETS
        
        logger.info(f"Searching {len(datasets)} datasets in parallel...")
        
        # Use ThreadPoolExecutor for parallel dataset searches
        all_results = []
        with ThreadPoolExecutor(max_workers=min(len(datasets), 10)) as executor:
            # Submit all dataset searches
            future_to_dataset = {
                executor.submit(self._search_single_dataset, dataset_info): dataset_info[0]
                for dataset_info in datasets
            }
            
            # Process results as they complete
            for future in as_completed(future_to_dataset):
                dataset_name = future_to_dataset[future]
                try:
                    results = future.result()
                    if results:
                        logger.info(f"✓ {dataset_name}: {len(results)} results")
                        all_results.extend(results)
                    else:
                        logger.debug(f"✗ {dataset_name}: No results")
                except Exception as e:
                    logger.error(f"✗ {dataset_name}: Failed - {e}")
        
        # Yield all results
        total_results = len(all_results)
        successful_datasets = len(set(r['dataset'] for r in all_results))
        
        if total_results > 0:
            logger.info(f"HuggingFace parallel search completed. Total: {total_results} results from {successful_datasets} datasets")
            for result in all_results:
                yield result
        else:
            # If no results found from any dataset, provide a helpful placeholder
            placeholder_result = {
                'url': 'https://huggingface.co/datasets',
                'title': f'HuggingFace Datasets - Search for "{self.phrase}"',
                'snippet': f'No direct results found for "{self.phrase}" in available HuggingFace datasets. Dataset indices may be loading or the term may not exist in currently indexed datasets. Try searching directly on HuggingFace Hub.',
                'dataset': 'huggingface_hub',
                'row_index': 0,
                'source_type': 'huggingface_placeholder'
            }
            yield placeholder_result
            logger.info("HuggingFace search completed with no results - returned placeholder")
    
    def _extract_url(self, row_data: Dict) -> str:
        """Extract URL from row data"""
        # Look for URL fields
        url_fields = ['url', 'link', 'href', 'website', 'webpage', 'site', 'source_url', 'article_url', 'post_url']
        for field in url_fields:
            if field in row_data and isinstance(row_data[field], str):
                url = row_data[field].strip()
                if url.startswith('http'):
                    return url
                elif url and not url.startswith('/'):
                    # Try to make it a valid URL
                    return f"https://{url}" if '.' in url else url
        
        # Look for domain fields and construct URL
        domain_fields = ['domain', 'hostname', 'host']
        for field in domain_fields:
            if field in row_data and isinstance(row_data[field], str):
                domain = row_data[field].strip()
                if domain and '.' in domain:
                    return f"https://{domain}" if not domain.startswith('http') else domain
        
        # Look for any field containing a URL
        import re
        url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
        for key, value in row_data.items():
            if isinstance(value, str):
                matches = url_pattern.findall(value)
                if matches:
                    return matches[0]
        
        # If we have text content, try to extract domain mentions
        text_content = self._extract_text_fields(row_data)
        if text_content:
            # Look for domain patterns in text
            domain_pattern = re.compile(r'\b(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)\b')
            domain_matches = domain_pattern.findall(text_content)
            if domain_matches:
                return f"https://{domain_matches[0]}"
        
        # Only use HuggingFace URL as last resort
        dataset = row_data.get('dataset', 'unknown')
        row_idx = row_data.get('row_index', 0)
        # Create viewer URL that might actually work
        return f"https://huggingface.co/datasets/{dataset}/viewer/default/train?row={row_idx}"
    
    def _extract_title(self, row_data: Dict, dataset_name: str) -> str:
        """Extract or generate title from row data"""
        # Try title/name fields first
        title_fields = ['title', 'name', 'company_name', 'heading', 'subject']
        for field in title_fields:
            if field in row_data and isinstance(row_data[field], str):
                title = row_data[field].strip()
                if title:
                    return title
        
        # Use first text content as title
        for key, value in row_data.items():
            if isinstance(value, str) and value.strip():
                return textwrap.shorten(value.strip(), width=100, placeholder="...")
        
        return f"HuggingFace result from {dataset_name}"
    
    def _extract_text_fields(self, row_data: Dict) -> str:
        """Extract and combine text content from various fields in row data"""
        text_parts = []
        
        # Common text field names to look for
        text_fields = ['text', 'content', 'description', 'body', 'summary', 'abstract', 
                      'title', 'name', 'heading', 'subject', 'message', 'comment']
        
        # Extract text from known text fields
        for field in text_fields:
            if field in row_data and isinstance(row_data[field], str):
                text = row_data[field].strip()
                if text:
                    text_parts.append(text)
        
        # If no specific text fields found, combine all string values
        if not text_parts:
            for key, value in row_data.items():
                if isinstance(value, str) and value.strip():
                    text_parts.append(value.strip())
        
        return ' '.join(text_parts)
    
    def _create_snippet(self, text: str) -> str:
        """Create snippet from text content"""
        if not text:
            return "No text content available"
        
        # Clean and truncate text
        clean_text = text.replace('\n', ' ').replace('\r', ' ').strip()
        return textwrap.shorten(clean_text, width=SNIPPET_LEN, placeholder=" ...")


# For backward compatibility and testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        phrase = " ".join(sys.argv[1:])
    else:
        phrase = input("Enter search phrase: ").strip()
    
    if not phrase:
        print("No phrase provided.")
        sys.exit(1)
    
    print(f"Searching HuggingFace datasets for: '{phrase}'")
    
    runner = ExactPhraseRecallRunnerHuggingFace(phrase)
    results = list(runner.run())
    
    print(f"\nFound {len(results)} total results:")
    for i, result in enumerate(results[:10], 1):  # Show first 10
        print(f"\n{i}. {result['title']}")
        print(f"   Dataset: {result['dataset']}")
        print(f"   URL: {result['url']}")
        print(f"   Snippet: {result['snippet'][:200]}...")