"""
LinkLater Query Executor

Routes parsed queries to appropriate modules (LinkLater, Jester, Backdrill).
"""

import asyncio
import logging
from typing import Dict, Any, List

import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime
import os

from elasticsearch import AsyncElasticsearch
from modules.query_parser import parse_query, QueryIntent
from modules.linklater.api import get_linklater

try:
    from modules.pacman.pacman import Pacman
    pacman_available = True
except ImportError:
    pacman_available = False

try:
    from modules.pacman.universal_extractor import get_extractor
    universal_extractor_available = True
except ImportError:
    universal_extractor_available = False

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("query_executor")

# ES Configuration
ES_HOST = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

class QueryExecutor:
    """Executes parsed LinkLater queries."""

    def __init__(self):
        self.linklater = get_linklater()
        self.historical_fetcher = self.linklater.backdrill # For cleanup hook
        self.pacman = Pacman() if pacman_available else None
        self.es = AsyncElasticsearch([ES_HOST])
        self.extractor = get_extractor() if universal_extractor_available else None

    async def _index_content(self, url: str, content: str, entities: Dict = None, outlinks: List[str] = None):
        """Index scraped content with embeddings to Elasticsearch."""
        if not self.es or not content:
            return

        try:
            # Generate embedding
            embedding = None
            if self.extractor:
                # Truncate for embedding model (usually 512-8192 tokens depending on model)
                # E5-large handles 512 tokens well, simple truncation
                embed_text = content[:2000] 
                embedding = self.extractor.model.encode(f"passage: {embed_text}", convert_to_numpy=False)

            doc = {
                "url": url,
                "domain": url.split("//")[-1].split("/")[0],
                "content": content,
                "title": "", # Jester might provide title, for now blank
                "indexed_at": datetime.utcnow().isoformat(),
                "outlinks": outlinks or [],
                "entities": entities or {},
                "source": "linklater_query",
            }
            
            if embedding:
                doc["content_embedding"] = embedding

            # Index to cymonides-2
            await self.es.index(index="cymonides-2", document=doc)
            logger.info(f"Indexed {url} to cymonides-2")

        except Exception as e:
            logger.error(f"Indexing failed for {url}: {e}")

    async def execute_async(self, query: str) -> Dict[str, Any]:
        """Execute a raw query string."""
        intent = parse_query(query)
        if not intent:
            return {"error": "Invalid query syntax"}

        logger.info(f"Executing query: {intent}")

        results = {
            "query": query,
            "target": intent.target,
            "target_type": intent.target_type,
            "method": "unknown",
            "results": {}
        }

        # 1. Routing based on Operators
        
        # Determine if we need to scrape
        # Scrape if: 
        # 1. Entity operators are present (p?, c?, etc.)
        # 2. Outlink operators are present (?ol, ol?) - implies checking live page for links
        # 3. NOT if only backlink operators are present (?bl, bl?) - those come from graph index
        # 4. NOT if query is HISTORICAL (<-!) - we can't scrape the past live
        
        entity_ops = [op for op in intent.operators if op in ['p?', 'c?', 'e?', 't?', 'a?', 'ent?']]
        outlink_ops = [op for op in intent.operators if op in ['?ol', 'ol?']]
        backlink_ops = [op for op in intent.operators if op in ['?bl', 'bl?']]
        
        should_scrape = (entity_ops or outlink_ops) and intent.target_type == "domain" and not intent.is_historical
        
        if should_scrape:
            results["method"] = "full_scrape_extraction"
            logger.info("Target is domain with scraping operators, initiating Scrape -> Extract pipeline")
            
            # Step 1: Map/Scrape (Using Jester via LinkLater)
            # Optimize: Scrape multiple likely pages in parallel for better entity coverage
            domain = intent.target
            candidate_paths = ["", "/about", "/contact", "/team", "/people", "/management", "/board", "/leadership"]
            candidate_urls = [f"https://{domain}{p}" for p in candidate_paths]
            
            logger.info(f"Scraping {len(candidate_urls)} candidate pages in parallel for entities...")
            scrape_results_list = await self.linklater.scrape_batch(candidate_urls, max_concurrent=len(candidate_urls))
            
            # Aggregate content from successful scrapes
            valid_content = []
            source_urls = []
            
            # Process each scraped page
            for result in scrape_results_list:
                url = result.url
                if result.content: # Index everything that has content
                    valid_content.append(f"--- SOURCE: {url} ---\n{result.content}")
                    source_urls.append(url)
                    
                    # EXTRACT & INDEX INDIVIDUAL PAGES
                    page_outlinks = self.linklater.extract_outlinks(result.content, url)
                    
                    # Extract page entities for indexing context (lightweight)
                    page_entities = {}
                    if self.pacman:
                         # Run fast regex extraction for indexing metadata
                         try:
                             # Using synchronous call in loop might slow down, but it's regex (fast)
                             if asyncio.iscoroutinefunction(self.pacman.extract_entities):
                                 pass # Skip async inside sync loop or restructure
                             else:
                                 # We can't await here easily if we want to batch later, 
                                 # but for immediate indexing we should probably just queue it.
                                 # For now, let's index without heavy entity breakdown per page to save time,
                                 # relying on the full text search + embedding.
                                 pass
                         except: pass

                    # Index page immediately
                    await self._index_content(url, result.content, page_entities, page_outlinks)
            
            if not valid_content:
                 return {"error": f"Scraping failed or no content found for {intent.target}"}

            combined_text = "\n\n".join(valid_content)

            # Step 2: Extract Entities (if requested) using PACMAN directly
            if entity_ops:
                if not self.pacman:
                    return {"error": "PACMAN module not available for extraction"}
                    
                # Use Pacman().full_extract which runs Fast Regex + Specialized Extractors
                # This ensures regex pattern matching happens BEFORE/ALONGSIDE any AI/logic
                
                if asyncio.iscoroutinefunction(self.pacman.full_extract):
                    extraction = await self.pacman.full_extract(combined_text)
                else:
                    extraction = await asyncio.to_thread(self.pacman.full_extract, combined_text)
                
                # Filter by requested operators
                filtered_entities = {}
                
                # extract_fast returns raw entities dict (emails, phones)
                # extract_persons/companies return lists of dicts
                
                if 'ent?' in entity_ops:
                    filtered_entities['persons'] = extraction.persons
                    filtered_entities['companies'] = extraction.companies
                    filtered_entities['fast_regex'] = extraction.entities # emails, phones, etc.
                else:
                    if 'p?' in entity_ops: filtered_entities['persons'] = extraction.persons
                    if 'c?' in entity_ops: filtered_entities['companies'] = extraction.companies
                    if 'e?' in entity_ops: filtered_entities['emails'] = extraction.entities.get('EMAIL', [])
                    if 't?' in entity_ops: filtered_entities['phones'] = extraction.entities.get('PHONE', [])
                
                results["results"]["entities"] = filtered_entities
                results["results"]["source_url"] = source_urls[0] if source_urls else url

            # Step 3: Extract Live Outlinks (if requested)
            if outlink_ops:
                # We prioritize LIVE outlinks from the scrape over the graph if we scraped
                live_outlinks = self.linklater.extract_outlinks(scrape_result.content, url)
                results["results"]["outlinks"] = [{"target_url": l, "source": "live_scrape"} for l in live_outlinks]

        elif backlink_ops and not should_scrape:
             logger.info("Only backlink operators present or Historical query. Skipping scrape, querying graph/archives.")

        # Backlinks (?bl, bl?)
        if '?bl' in intent.operators or 'bl?' in intent.operators:
             # Fast domain backlinks
             # If historical, request Majestic Historic
             majestic_mode = "historic" if intent.is_historical else "fresh"
             
             # Determine result type (Pages vs Domains)
             # ?bl = Domains, bl? = Pages
             maj_result_type = "pages" if 'bl?' in intent.operators else "domains"
             
             # Get Graph backlinks
             backlinks = await self.linklater.get_backlinks(intent.target, limit=100)
             
             # Convert to dict
             bl_results = [b.__dict__ for b in backlinks]
             
             # If historical, try to add Majestic Historic if available
             if intent.is_historical:
                 try:
                     maj_links = await self.linklater.get_majestic_backlinks(
                         intent.target, 
                         mode="historic", 
                         result_type=maj_result_type
                     )
                     for ml in maj_links:
                         # Filter by date if years specified
                         if years:
                             date_str = ml.get("first_indexed_date", "")
                             if date_str:
                                 try:
                                     link_year = int(date_str.split('-')[0])
                                     if link_year not in years:
                                         continue
                                 except (ValueError, IndexError):
                                     pass

                         # Map fields based on type
                         if maj_result_type == "pages":
                             bl_results.append({
                                 "source_url": ml.get("source_url"),
                                 "source_domain": ml.get("source_domain"),
                                 "target_url": ml.get("target_url"),
                                 "anchor_text": ml.get("anchor_text"),
                                 "source": "majestic_historic",
                                 "weight": ml.get("trust_flow", 0),
                                 "first_seen": ml.get("first_indexed_date")
                             })
                         else:
                             bl_results.append({
                                 "source_domain": ml.get("source_domain"),
                                 "source": "majestic_historic",
                                 "weight": ml.get("trust_flow", 0),
                                 "first_seen": ml.get("first_indexed_date")
                             })
                 except Exception:
                     pass # Majestic might not be configured
             
             results["results"]["backlinks"] = bl_results
             results["method"] = f"backlinks_{majestic_mode}"

        # Outlinks (?ol) 
        if '?ol' in intent.operators:
             outlinks_results = []
             
             # If NOT scraped (or if historical), get from Graph
             if not should_scrape or intent.is_historical:
                 # Graph Outlinks
                 outlinks = await self.linklater.get_outlinks(intent.target, limit=100)
                 outlinks_results.extend([o.__dict__ for o in outlinks])
                 results["method"] = "outlinks_graph"
                 
                 # If Historical, ALSO search Archives (Wayback/CC) for outlinks
                 if intent.is_historical:
                     logger.info("Historical Outlinks: Extracting from Backdrill Archives")
                     
                     # Parse year filters from modifiers
                     years = []
                     for mod in intent.historical_modifiers:
                         if '-' in mod:
                             try:
                                 start, end = map(int, mod.split('-'))
                                 years.extend(range(start, end + 1))
                             except ValueError: pass
                         elif mod.isdigit() and len(mod) == 4:
                             years.append(int(mod))
                             
                     # Use Backdrill to find archived pages and extract links
                     # This is a heavy operation, we'll do a sample
                     try:
                         # Use historical search to find snapshots
                         history = await self.linklater.historical_search(
                             domains=[intent.target],
                             years=years if years else None,
                             limit=5 # Limit snapshots for speed
                         )
                         
                         for snap in history.get("archive_results", []):
                             if snap.get("content"):
                                 snap_outlinks = self.linklater.extract_outlinks(snap["content"], snap["url"])
                                 for ol in snap_outlinks:
                                     source_name = snap.get('source', 'archive')
                                     outlinks_results.append({
                                         "target_url": ol,
                                         "source": f"archive_{source_name}",
                                         "timestamp": snap.get("timestamp")
                                     })
                     except Exception as e:
                         logger.warning(f"Historical outlink extraction failed: {e}")

             # If scraped, we already added live_scrape results above, but we might want to merge graph results too
             elif should_scrape and "outlinks" in results["results"]:
                 # We have live links, maybe add graph links too?
                 graph_outlinks = await self.linklater.get_outlinks(intent.target, limit=100)
                 # Merge unique
                 existing = {l["target_url"] for l in results["results"]["outlinks"]}
                 for o in graph_outlinks:
                     if o.target_domain not in existing: # Approx check
                         results["results"]["outlinks"].append(o.__dict__)
             
             if intent.is_historical or not should_scrape:
                 results["results"]["outlinks"] = outlinks_results

        # Filetype Discovery (pdf!, etc.)

        # Filetype Discovery (pdf!, etc.)
        file_ops = [op for op in intent.operators if op.endswith('!') and not re.match(r'\d', op)]
        if file_ops:
            filetype = file_ops[0][:-1] # remove !
            files = await self.linklater.discover_files(intent.target, filetype=filetype)
            results["results"]["files"] = files
            results["method"] = "file_discovery"

        # Keyword Search ("keyword" :!domain.com)
        if intent.keywords and intent.target_type == "domain":
            results["method"] = "keyword_search_domain"
            logger.info(f"Keyword search on domain: {intent.keywords} -> {intent.target}")
            
            # Phase 1: Archive Search (if historical or as fallback)
            # (Skipped for brevity, focusing on parallel scrape as requested)
            
            # Phase 2: Live Parallel Scrape
            if not intent.is_historical:
                domain = intent.target
                # Generate high-probability paths
                paths = [
                    "", "/about", "/contact", "/team", "/people", 
                    "/company", "/terms", "/privacy", "/sitemap.xml"
                ]
                urls = [f"https://{domain}{p}" for p in paths]
                
                # Batch scrape (Jester handles concurrency)
                # We interpret "keyword" simply for now, could be more complex regex
                scrapes = await self.linklater.scrape_batch(urls, max_concurrent=10)
                
                matches = []
                for url, result in scrapes.items():
                    if result.content:
                        content_lower = result.content.lower()
                        for kw in intent.keywords:
                            if kw.lower() in content_lower:
                                # Extract snippet
                                idx = content_lower.find(kw.lower())
                                snippet = result.content[max(0, idx-50):min(len(result.content), idx+50)]
                                matches.append({
                                    "url": url,
                                    "keyword": kw,
                                    "snippet": snippet.strip(),
                                    "source": "live_scrape"
                                })
                
                results["results"]["keyword_matches"] = matches

        return results

# Helper for direct execution
async def execute_async(query: str):
    executor = QueryExecutor()
    return await executor.execute_async(query)
