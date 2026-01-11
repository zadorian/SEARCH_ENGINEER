"""
exact_phrase_recall_runner.py

Automates the "max-recall" playbook for Google Custom Search:

 1. Builds the four base queries (Q1–Q4).
 2. Adds optional site-group partitions (≤32 OR terms each).
 3. Adds optional time-slice partitions (before:/after: operators).
 4. Executes every permutation via the GoogleSearch class you already have.
 5. Dedupes results on URL and returns a single list.

Usage::

    from exact_phrase_recall_runner import ExactPhraseRecallRunner, chunk_sites
    # Adjust import path as needed if GoogleSearch is elsewhere
    try:
        from search_engines.google import GoogleSearch 
    except ImportError:
        # Fallback if running from a different structure
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent))
        from search_engines.google import GoogleSearch 

    phrase = "my exact phrase"
    sites  = ["*.de","*.fr","*.it","*.uk"]
    site_groups = list(chunk_sites(sites))
    time_slices = [{"after":"2021"}, {"before":"2021"}]

    google = GoogleSearch()
    runner = ExactPhraseRecallRunner(phrase, google,
                                     site_groups=site_groups,
                                     time_slices=time_slices)
    hits = runner.run()

"""

import logging
from typing import List, Dict, Optional, Iterable, Union
from itertools import chain
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Import GoogleSearch from server.py
# When imported by server.py, GoogleSearch will already be available
# This is a fallback for standalone usage
if 'GoogleSearch' not in globals():
    try:
        from server import GoogleSearch
    except ImportError:
        print("Error: Could not import GoogleSearch class from server.py")
        # Define a dummy class to prevent NameError during parsing
        class GoogleSearch:
            def google_base(self, *args, **kwargs): return [], None 


logger = logging.getLogger("exact_phrase_runner") # Corrected logger name

# --------------------------------------------------------------------------- #
# Helper builders
# --------------------------------------------------------------------------- #

def generate_base_queries(phrase: str) -> Dict[str, str]:
    """Return the four base queries defined in the playbook."""
    # Ensure phrase itself isn't double-quoted coming in
    clean_phrase = phrase.strip('"')
    quoted = f'"{clean_phrase}"'
    return {
        # Base Q1: Exact phrase
        "Q1": quoted,
        # Base Q2: Exact phrase + PDF
        "Q2": f'{quoted} filetype:pdf',
        # Base Q3: Allintitle exact phrase (Google handles quoting within operator)
        "Q3": f'allintitle:{quoted}',
        # Base Q4: Allinurl exact phrase (Google handles quoting within operator)
        "Q4": f'allinurl:{quoted}', 
    }


def build_site_block(sites: list[str]) -> str:
    """
    ".de"  -> "site:*.de"
    "example.com" -> "site:example.com"
    """
    clean = []
    for s in sites:
        s = s.strip()
        if not s:
            continue
        if s.startswith("*.") or s.startswith("site:"):
            # already in correct form
            clean.append(s if s.startswith("site:") else f"site:{s}")
        elif s.startswith("."):
            clean.append(f"site:*{s}")            # .de   => site:*.de
        else:
            clean.append(f"site:{s}")             # foo.com => site:foo.com
    # Return joined string WITHOUT surrounding parentheses
    return " OR ".join(clean) if clean else ""


def build_time_block(*_ignored, **__):
    """Date bounds (before:/after:) are unsupported in Google CSE -> no inline filter."""
    # This function is kept for structural consistency in the loop but adds nothing.
    return ""


def chunk_sites(sites: Iterable[str], max_terms: int = 30) -> Iterable[List[str]]:
    """Yield sub-lists that respect Google's 32-OR limit (30 ⇒ safe margin)."""
    sites = list(sites)
    for i in range(0, len(sites), max_terms):
        yield sites[i:i + max_terms]


# --- NEW dateRestrict Helper --- 
def slice_to_date_restrict(slice_: dict[str, Union[str, int]]) -> Optional[str]:
    """Map {'last_years': 3}  →  'y3'  etc."""
    if not slice_: # Handles empty dict case {} -> no filter
        return None
    # Prioritize smaller units if multiple are present (e.g., days over weeks)
    if 'last_days' in slice_:
        try: return f"d{int(slice_['last_days'])}"
        except (ValueError, TypeError): pass
    if 'last_weeks' in slice_:
        try: return f"w{int(slice_['last_weeks'])}"
        except (ValueError, TypeError): pass
    if 'last_months' in slice_:
        try: return f"m{int(slice_['last_months'])}"
        except (ValueError, TypeError): pass
    if 'last_years' in slice_:
        try: return f"y{int(slice_['last_years'])}"
        except (ValueError, TypeError): pass
    logger.warning(f"Unknown key in time slice for dateRestrict: {slice_}. No filter applied.")
    return None            # unknown key or invalid value ⇒ no filter


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
class ExactPhraseRecallRunner:
    """Exhaustively combines base-query × site-block × time-slice, hits Google, and dedups on URL."""

    def __init__(
        self,
        phrase: str,
        google: "GoogleSearch",
        site_groups: Optional[List[List[str]]] = None,
        time_slices: Optional[List[Dict[str, Union[str, None]]]] = None,
        max_results_per_query: int = 100, # Max per individual API call
        use_parallel: bool = True,
        max_workers: int = 4,
    ):
        self.phrase = phrase.strip('"') # Ensure phrase is unquoted internally
        self.google = google
        # If site_groups is provided (not None and not empty), it uses that list.
        # If site_groups is None or empty, it defaults to [None].
        self.site_groups: List[List[str] | None] = site_groups if site_groups else [None]
        # If time_slices is provided (not None and not empty), it uses that list.
        # If time_slices is None or empty, it defaults to [{}].
        self.time_slices: List[Dict[str, Union[str, None]]] = time_slices if time_slices else [{}]
        # Respect the user's requested max_results_per_query
        # Note: Google's actual API limit is 10 per page, but we can paginate
        self.max_results_per_query = max(1, max_results_per_query)
        self.use_parallel = use_parallel
        self.max_workers = max_workers
        self._lock = threading.Lock()
        self._store: Dict[str, Dict] = {}  # url → result-dict

    # ............................................................. #
    def _add_results(self, batch: List[Dict]):
        """Merge *batch* (list of result dicts) into the URL-keyed store."""
        print(f"📦 DEBUG: _add_results called with batch of {len(batch)} items")
        count = 0
        with self._lock:
            for hit in batch:
                url = hit.get("url")
                if not url:
                    print(f"❌ DEBUG: Hit missing 'url' field: {hit.keys()}")
                    continue
                if url and url not in self._store: # Only add if URL exists and is new
                    self._store[url] = hit
                    count += 1
                    print(f"✅ DEBUG: Added URL to store: {url[:80]}...")
        if count:
            logger.debug(f"    -> Added {count} new unique URLs to store.")
        print(f"📊 DEBUG: Store now has {len(self._store)} total URLs")


    # ............................................................. #
    def run_exception_search(self) -> List[Dict]:
        """
        Performs an exception search by excluding ALL previously found domains
        to discover additional results that might have been missed.
        Returns results that should be tagged as 'G-ex' (Google Exception).
        """
        if not self._store:
            logger.info("No previous results to exclude - skipping exception search")
            return []
        
        # Extract unique domains from all found URLs
        found_domains = set()
        for url in self._store.keys():
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower()
                if domain:
                    found_domains.add(domain)
            except Exception:
                continue
        
        if not found_domains:
            logger.info("No valid domains found in previous results - skipping exception search")
            return []
        
        logger.info(f"Running Google exception search excluding ALL {len(found_domains)} previously found domains...")
        
        # Base phrase for exception search
        base_query = f'"{self.phrase}"'
        
        # Build exclusion list - exclude ALL domains, no arbitrary limit
        all_domains = sorted(list(found_domains))
        exclusions = [f"-site:{domain}" for domain in all_domains]
        
        # Check if we can fit all exclusions in one query (Google's ~2048 char limit)
        full_exclusion_query = f"{base_query} {' '.join(exclusions)}"
        
        exception_results = []
        
        if len(full_exclusion_query) <= 2000:  # Safe margin under Google's limit
            # Single query with all exclusions
            logger.info(f"Using single exception query excluding all {len(all_domains)} domains")
            exception_results.extend(self._run_single_exception_query(full_exclusion_query, all_domains))
        else:
            # Split into multiple queries if needed
            logger.info(f"Query too long - splitting into multiple exception queries to exclude all {len(all_domains)} domains")
            
            # Calculate how many domains we can exclude per query
            avg_domain_length = sum(len(domain) for domain in all_domains) / len(all_domains)
            max_domains_per_query = int((2000 - len(base_query) - 50) / (avg_domain_length + 7))  # 7 = "-site:" + space
            max_domains_per_query = max(10, max_domains_per_query)  # At least 10 domains per query
            
            # Split domains into chunks
            for i in range(0, len(all_domains), max_domains_per_query):
                chunk_domains = all_domains[i:i + max_domains_per_query]
                chunk_exclusions = [f"-site:{domain}" for domain in chunk_domains]
                chunk_query = f"{base_query} {' '.join(chunk_exclusions)}"
                
                logger.info(f"Exception query chunk {i//max_domains_per_query + 1}: excluding {len(chunk_domains)} domains")
                chunk_results = self._run_single_exception_query(chunk_query, found_domains)
                exception_results.extend(chunk_results)
        
        logger.info(f"Exception search completed: found {len(exception_results)} new results from different domains")
        return exception_results
    
    def _run_single_exception_query(self, exception_query: str, excluded_domains: set) -> List[Dict]:
        """Run a single exception query and filter results."""
        try:
            logger.debug(f"Exception query: {exception_query[:200]}..." if len(exception_query) > 200 else exception_query)
            
            hits_from_engine, estimated_count = self.google.google_base(
                exception_query,
                max_results=self.max_results_per_query
            )
            
            if estimated_count is not None and estimated_count == 0:
                logger.debug(f"Exception search estimated 0 results")
                return []
            
            # Filter out any results that match previously found domains
            new_results = []
            if hits_from_engine:
                for hit in hits_from_engine:
                    url = hit.get("url", "")
                    if url:
                        try:
                            from urllib.parse import urlparse
                            hit_domain = urlparse(url).netloc.lower()
                            # Only include if domain wasn't in our exclusion list
                            if hit_domain not in excluded_domains:
                                hit['found_by_query'] = exception_query
                                hit['search_type'] = 'exception'  # Mark as exception result
                                new_results.append(hit)
                            else:
                                logger.debug(f"Filtered out result from excluded domain: {hit_domain}")
                        except Exception:
                            continue
            
            return new_results
            
        except Exception as exc:
            logger.warning(f"Exception search query failed: {exc}")
            return []

    # ............................................................. #
    def run(self) -> List[Dict]:
        """Runs all query permutations synchronously and returns deduplicated results."""
        logger.info(f"Starting Google Exact Phrase Recall run for: '{self.phrase}' (parallel={self.use_parallel})")
        bases = generate_base_queries(self.phrase)

        # Build list of all query permutations first
        permutations: List[tuple[str,str]] = []  # (tag, query_str)
        for tag, base_query in bases.items():
            for sites in self.site_groups:
                site_block = build_site_block(sites) if sites else ""
                for _slice in self.time_slices:
                    parts = [base_query, site_block]
                    query_str = " ".join(filter(None, parts))
                    permutations.append((tag, query_str))

        logger.info(f"Prepared {len(permutations)} Google query permutations...")

        def _execute(tag_query: tuple[str,str]):
            tag, query_str = tag_query
            try:
                print(f"🔍 DEBUG: Executing query [{tag}]: {query_str[:100]}...")
                hits_from_engine, estimated_count = self.google.google_base(
                    query_str,
                    max_results=self.max_results_per_query
                )
                print(f"📊 DEBUG: google_base returned {len(hits_from_engine) if hits_from_engine else 0} hits, estimated: {estimated_count}")
                if estimated_count is not None and estimated_count == 0:
                    logger.debug(f"[{tag}] Estimated 0 results for: {query_str}")
                        
                augmented_hits = []
                if hits_from_engine:
                    for hit in hits_from_engine:
                        hit['found_by_query'] = query_str
                        hit['query_tag'] = tag  # Add tag to track query type
                        augmented_hits.append(hit)
                print(f"✅ DEBUG: Returning {len(augmented_hits)} augmented hits for [{tag}]")
                return augmented_hits
            except Exception as exc:
                logger.warning(f"[{tag}] Query failed: {exc}")
                print(f"❌ DEBUG: Query [{tag}] failed with exception: {exc}")
                return []

        if self.use_parallel and len(permutations) > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(_execute, p): p for p in permutations}
                for future in as_completed(futures):
                    batch = future.result()
                    if batch:
                        self._add_results(batch)
        else:
            for p in permutations:
                batch = _execute(p)
                if batch:
                    self._add_results(batch)

        logger.info(f"Finished Google run. Collected {len(self._store)} unique URLs from {len(permutations)} permutations.")
        
        # NOTE: Exception search is now handled by brute.py after ALL engines finish
        # This ensures we exclude domains from ALL sources, not just Google
        
        return list(self._store.values())


# --------------------------------------------------------------------------- #
# Quick demo
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Configure logging for the demo
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s: %(message)s")

    PHRASE = "gulfstream lng"  # Example phrase
    # Example site groups (chunked) - TLDs without *. prefix
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
    print(f"DEBUG: Total unique TLDs defined: {len(SITES)}")
    # Chunk into smaller groups (max 5 per OR block)
    SITE_GROUPS = list(chunk_sites(SITES, max_terms=5)) 
    print(f"DEBUG: Chunked into {len(SITE_GROUPS)} site groups (max 5 TLDs each).")
    
    # Define time slices using the new format for dateRestrict
    TIME_SLICES = [
        {'last_years': 25},   # ~Roughly since ~2000 (adjust year count as needed)
        {'last_years': 15},   # ~Roughly since ~2010
        {'last_years':  4},   # ~Roughly since ~2021 (adjust as needed)
        {'last_months': 6},   # Example: Last 6 months
        {'last_days': 30},    # Example: Last 30 days
        {}                    # no date filter (important to include)
    ]
    print(f"DEBUG: Defined {len(TIME_SLICES)} time slices for dateRestrict: {TIME_SLICES}")

    logger.info("Initializing GoogleSearch...")
    try:
        g = GoogleSearch() # Assumes API keys are in .env
    except Exception as e:
         logger.error(f"Failed to initialize GoogleSearch: {e}", exc_info=True)
         exit()
         
    logger.info("Initializing ExactPhraseRecallRunner...")
    runner = ExactPhraseRecallRunner(
        phrase=PHRASE,
        google=g,
        site_groups=SITE_GROUPS, # Pass the list of site lists
        time_slices=TIME_SLICES,
        max_results_per_query=100, # Fetch up to 100 per API call
        use_parallel=True,
        max_workers=4
    )
    
    logger.info("Starting runner...")
    results = runner.run()

    print(f"\n--- DEMO COMPLETE --- ")
    print(f"Found {len(results)} unique Google URLs:")
    for i, r in enumerate(results, 1):
        title = r.get('title','[No Title]')
        url = r.get('url', r.get('link', '[No URL]')) # Google often uses 'link'
        snippet = r.get('snippet', '[No Snippet]')
        print(f"\n{i}. Title: {title}")
        print(f"   URL: {url}")
        print(f"   Snippet: {snippet}") 