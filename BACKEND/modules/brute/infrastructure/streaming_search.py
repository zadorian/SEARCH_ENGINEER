import asyncio
import time
import logging
import importlib
import re
from datetime import datetime
from typing import List, Dict, Any, AsyncGenerator, Set, Optional
import sys
import os
from pathlib import Path
import traceback
from urllib.parse import urlparse
from queue import Queue, Empty
from threading import Thread

# Ensure we can import from parent directories
BRUTE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BRUTE_ROOT))

# Import from flat structure (not package)
from brute import ENGINE_CONFIG, WRAPPER_ENGINE_MAP, WRAPPER_ENGINE_MAX
from config import Config
from infrastructure.rate_limiter import AdaptiveRateLimiter
from indexer.whoosh_indexer import Whooshindexer
from indexer.vector_indexer import Vectorindexer
from categorizer.intelligent_categorizer import IntelligentCategorizer
from targeted_searches.content.anchor import AnchorSearcher
from services.elastic_service import get_elastic_service
import hashlib
from utils.query_expander import QueryExpander
from scraper.phrase_matcher import PhraseMatcher

# Setup logging
logger = logging.getLogger(__name__)

class StreamingSearchEngine:
    """
    Asynchronous search engine orchestrator that streams results in real-time.
    Focuses on maximum recall and immediate feedback.
    """

    def __init__(self, engines: List[str], query: str, level: int = 2, scope: str = "web"):
        self.engines = engines
        self.level = level
        self.scope = scope
        self.expander = QueryExpander()
        
        # Check for anchor force override
        self.force_anchor = False
        if '+anchor' in query:
            self.force_anchor = True
            raw_query = query.replace('+anchor', '').strip()
        else:
            raw_query = query
            
        self.query = raw_query
        # Web query is expanded (e.g. [cde] -> site:de "GmbH"...)
        self.web_query = self.expander.expand_query_for_web(raw_query)
        # Concrete query is striped (e.g. "apple [cde]" -> "apple")
        self.concrete_query = self.expander.parse(raw_query)[0]

        # Initialize phrase matcher for filtering
        self.phrase_matcher = PhraseMatcher(max_distance=2)
        self.exact_phrases = self.phrase_matcher.extract_phrases(raw_query)

        self.results = {}
        self.seen_urls = set()
        self.expanded_domains = set()
        self.start_time = None
        self.stats = {
            'total_results': 0,
            'engines_succeeded': 0,
            'engines_failed': 0,
            'unique_urls': 0,
            'indexed_count': 0
        }
        self.rate_limiter = AdaptiveRateLimiter()
        self.anchor_searcher = AnchorSearcher()
        
        try:
            self.categorizer = IntelligentCategorizer()
            logger.info("Intelligent Categorizer initialized")
        except Exception as e:
            logger.error(f"Failed to init Categorizer: {e}")
            self.categorizer = None
        
        self.indexing_queue = Queue()
        self.whoosh_indexer = None
        self.vector_indexer = None
        self.elastic_service = None
        self._stop_indexing = False

        try:
            self.whoosh_indexer = Whooshindexer(index_dir="indices/whoosh_streaming")
        except Exception as e:
            logger.error(f"Failed to init Whoosh: {e}")

        try:
            if os.getenv("OPENAI_API_KEY"):
                self.vector_indexer = Vectorindexer()
        except Exception as e:
            logger.error(f"Failed to init Vector indexer: {e}")

        # Initialize Elasticsearch service for indexing
        try:
            self.elastic_service = get_elastic_service()
            logger.info("ElasticService initialized for indexing")
        except Exception as e:
            logger.error(f"Failed to init ElasticService: {e}")

        # System user/project context for Elastic documents (aligns with grid expectations)
        self.user_id = int(os.getenv("ELASTIC_USER_ID", "1"))
        self.project_id = os.getenv("ELASTIC_PROJECT_ID") or None

        self.indexing_thread = Thread(target=self._indexing_worker, daemon=True)
        self.indexing_thread.start()

    def _indexing_worker(self):
        """Background worker to batch index results"""
        batch = []
        last_flush = time.time()

        while not self._stop_indexing or not self.indexing_queue.empty():
            try:
                try:
                    item = self.indexing_queue.get(timeout=0.5)
                    batch.append(item)
                except Empty:
                    pass

                current_time = time.time()
                if batch and (len(batch) >= 5 or (current_time - last_flush) > 2.0):
                    # Index to Whoosh
                    if self.whoosh_indexer:
                        whoosh_docs = []
                        for res in batch:
                            whoosh_docs.append({
                                'url': res['url'],
                                'title': res.get('title', ''),
                                'content': res.get('snippet', ''),
                                'query': self.query,
                                'links': ','.join(res.get('found_by', []))
                            })
                        self.whoosh_indexer.index_documents(whoosh_docs)

                    # Index to Vector store
                    if self.vector_indexer:
                        for res in batch:
                            vec_doc = {
                                'url': res['url'],
                                'title': res.get('title', ''),
                                'snippet': res.get('snippet', ''),
                                'search_id': 'streaming_search',
                                'engine': ','.join(res.get('found_by', [])),
                                'rowid': str(hash(res['url']))
                            }
                            self.vector_indexer.index_document(vec_doc)

                    # Index to Elasticsearch (same as CyMonides and frontend)
                    if self.elastic_service:
                        elastic_docs = []
                        for res in batch:
                            # Create source node document matching Drill Search schema
                            deterministic_id = hashlib.sha256(res['url'].encode('utf-8')).hexdigest()
                            node_doc = {
                                'id': f"search_{deterministic_id}",
                                'label': res.get('title', res['url'])[:200],
                                'content': res.get('snippet', ''),
                                'className': 'source',
                                'typeName': 'search_result',
                                'urls': [res['url']],
                                'domains': [urlparse(res['url']).netloc] if res.get('url') else [],
                                'metadata': {
                                    'search_query': self.query,
                                    'search_engines': res.get('found_by', []),
                                    'category': res.get('category', 'uncategorized'),
                                    'found_at': datetime.utcnow().isoformat()
                                },
                                'userId': self.user_id,
                                'projectId': self.project_id,
                                'lastSeen': datetime.utcnow().isoformat(),
                                'createdAt': datetime.utcnow().isoformat(),
                                'updatedAt': datetime.utcnow().isoformat()
                            }
                            elastic_docs.append(node_doc)

                        try:
                            # Run async indexing in event loop
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(self.elastic_service.index_batch(elastic_docs))
                            loop.close()
                            logger.info(f"Indexed {len(elastic_docs)} docs to Elasticsearch")
                        except Exception as e:
                            logger.error(f"Elasticsearch indexing failed: {e}")

                    self.stats['indexed_count'] += len(batch)
                    batch = []
                    last_flush = time.time()

            except Exception as e:
                logger.error(f"Indexing worker error: {e}")
                batch = []

    def _calculate_quality_score(self, result: Dict[str, Any]) -> int:
        score = 10
        source_count = len(result.get('found_by', []))
        score += (source_count - 1) * 10
        
        sources = result.get('found_by', [])
        if 'GO' in sources: score += 5
        if 'BI' in sources: score += 5
        if 'EX' in sources: score += 10
        if 'BR' in sources: score += 5
        if 'AX' in sources: score += 15
        if 'PM' in sources: score += 15
        if 'CORPUS' in sources: score += 20
        
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        
        if len(title) < 10: score -= 5
        if len(snippet) < 20: score -= 5
        
        return score

    def _deduplicate(self, new_results: List[Dict[str, Any]], engine_code: str) -> List[Dict[str, Any]]:
        stream_batch = []

        for r in new_results:
            url = r.get('url') or r.get('link')
            if not url:
                continue

            url = url.strip().rstrip('/')
            title = r.get('title', '')
            snippet = r.get('snippet', '') or r.get('description', '')

            # EXACT PHRASE FILTERING: Skip results without phrase matches
            if self.exact_phrases:
                # Combine title + snippet for checking
                combined_text = f"{title} {snippet}"

                # Check if ANY exact phrase matches (with normalization for ., _, -, no-space)
                has_match = False
                for phrase in self.exact_phrases:
                    if self.phrase_matcher.check_exact_match(combined_text, phrase):
                        has_match = True
                        break
                    # Also try proximity match (distance=2)
                    match_found, _ = self.phrase_matcher.check_proximity(combined_text, phrase, max_distance=2)
                    if match_found:
                        has_match = True
                        break

                # Filter out results without any phrase match
                if not has_match:
                    logger.debug(f"Filtered out (no phrase match): {url}")
                    continue
            
            if url in self.results:
                existing = self.results[url]
                if engine_code not in existing['found_by']:
                    existing['found_by'].append(engine_code)
                    existing['quality_score'] = self._calculate_quality_score(existing)
                    if snippet and len(snippet) > len(existing.get('snippet', '')):
                        existing['snippet'] = snippet
            else:
                self.seen_urls.add(url)
                result_entry = {
                    'url': url,
                    'title': title,
                    'snippet': snippet,
                    'found_by': [engine_code],
                    'first_seen': time.time(),
                    'metadata': r.get('metadata', {})
                }
                if engine_code == 'CORPUS':
                    result_entry['category'] = 'corpus'
                
                result_entry['quality_score'] = self._calculate_quality_score(result_entry)
                
                if self.categorizer and engine_code != 'CORPUS':
                    try:
                        result_entry = self.categorizer.categorize_result(result_entry)
                    except Exception as e:
                        logger.warning(f"Categorization failed for {url}: {e}")
                
                self.results[url] = result_entry
                stream_batch.append(result_entry)
                self.stats['unique_urls'] += 1
                self.indexing_queue.put(result_entry)
        
        return stream_batch

    def _run_engine_wrapper(self, engine_code: str, query_override: str = None) -> List[Dict[str, Any]]:
        # Use override if provided, else use web_query (expanded)
        query_to_use = query_override if query_override else self.web_query
        try:
            wrapper_spec = WRAPPER_ENGINE_MAP.get(engine_code)
            if wrapper_spec:
                mod_name, cls_name = wrapper_spec
                try:
                    mod = importlib.import_module(mod_name)
                    cls = getattr(mod, cls_name)
                    engine = cls()
                    max_res = WRAPPER_ENGINE_MAX.get(engine_code, 100)
                    
                    search_query = query_to_use
                    if query_to_use.startswith('"') and query_to_use.endswith('"'):
                        search_query = query_to_use
                        
                    return engine.search(search_query, max_results=max_res)
                except ImportError:
                    pass
                except Exception as e:
                    logger.warning(f"Wrapper failed for {engine_code}: {e}")

            config = ENGINE_CONFIG.get(engine_code)
            if not config:
                return []

            module = importlib.import_module(config['module'])
            runner_class = getattr(module, config['class'])
            
            kwargs = {}
            if 'init_kwargs' in config and callable(config['init_kwargs']):
                kwargs = config['init_kwargs']()
            
            kwargs.setdefault('phrase', query_to_use.strip('"'))
            api_key = Config.get_api_key(engine_code)
            if api_key and 'api_key' not in kwargs:
                 if engine_code not in ['GO', 'BI', 'BR', 'YA', 'AR', 'YE', 'EX']:
                        kwargs['api_key'] = api_key
            
            if engine_code == 'GO':
                 phrase = query_to_use.strip('"')
                 if 'phrase' in kwargs: kwargs.pop('phrase')
                 google_client = kwargs.pop('google')
                 runner = runner_class(phrase, google_client, **kwargs)
            else:
                 runner = runner_class(**kwargs)

            results = []
            if engine_code == 'DD':
                results = runner.search(query_to_use.strip('"'), max_results=500)
            elif hasattr(runner, 'run'):
                try:
                    import inspect
                    sig = inspect.signature(runner.run)
                    if 'phrase' in sig.parameters:
                         res = runner.run(query_to_use.strip('"'))
                    else:
                         res = runner.run()
                    if res: results = list(res)
                except Exception as e:
                     if hasattr(runner, 'search'):
                        results = runner.search(query_to_use.strip('"'))
                     else:
                        raise e
            elif hasattr(runner, 'search'):
                results = runner.search(query_to_use.strip('"'))
            
            return results or []

        except Exception as e:
            logger.error(f"Engine {engine_code} failed: {e}")
            raise e

    async def _run_corpus_search(self, loop):
        """Query ElasticService for indexed content with Smart Filtering."""
        try:
            es = get_elastic_service()
            
            # Build Elastic Query
            # Use concrete query for text match (removing [defs])
            text_query = self.concrete_query
            if not text_query:
                text_query = "*" # Match all if query was only definitions
                
            filters = self.expander.get_elastic_filters(self.query)
            
            es_query = {
                "query": {
                    "bool": {
                        "must": [],
                        "filter": filters
                    }
                },
                "size": 50
            }
            
            if text_query != "*":
                es_query["query"]["bool"]["must"].append({
                    "multi_match": {
                        "query": text_query,
                        "fields": ["content^3", "label^2", "url"],
                        "type": "best_fields"
                    }
                })
            else:
                es_query["query"]["bool"]["must"].append({"match_all": {}})
            
            # Execute
            result = await es.search(es_query)
            
            hits = result.get("hits", {}).get("hits", [])
            formatted_results = []
            
            for hit in hits:
                src = hit.get("_source", {})
                formatted_results.append({
                    "url": src.get("url"),
                    "title": src.get("label"),
                    "snippet": (src.get("content") or "")[:300],
                    "source": "CORPUS",
                    "found_by": ["CORPUS"],
                    "metadata": {
                        "is_corpus": True, 
                        "score": hit.get("_score"),
                        "original_id": src.get("id"),
                        "type": src.get("type")
                    }
                })
            
            if formatted_results:
                clean = self._deduplicate(formatted_results, "CORPUS")
                return "CORPUS", clean
                
            return "CORPUS", []
            
        except Exception as e:
            logger.error(f"Corpus search error: {e}")
            return "CORPUS", []

    async def stream_results(self) -> AsyncGenerator[Dict[str, Any], None]:
        self.start_time = time.time()
        loop = asyncio.get_running_loop()
        tasks = []
        
        if self.scope in ['web', 'both']:
            for engine_code in self.engines:
                tasks.append(self._process_engine(loop, engine_code))
        
        if self.scope in ['corpus', 'both']:
            tasks.append(self._run_corpus_search(loop))
            
        completed_count = 0
        total_engines = len(tasks)
        
        for future in asyncio.as_completed(tasks):
            try:
                engine_code, results = await future
                
                if results is not None:
                    self.stats['engines_succeeded'] += 1
                    if results:
                        yield {
                            'type': 'results',
                            'engine': engine_code,
                            'count': len(results),
                            'data': results
                        }
                else:
                    self.stats['engines_failed'] += 1
            except Exception as e:
                logger.error(f"Stream error: {e}")
                self.stats['engines_failed'] += 1
            
            completed_count += 1
            progress = (completed_count / total_engines) * 100 if total_engines > 0 else 100
            yield {
                'type': 'progress',
                'data': {
                    'completed': completed_count,
                    'total_engines': total_engines,
                    'progress_percent': progress,
                    'results_count': self.stats['total_results'],
                    'unique_urls': self.stats['unique_urls']
                }
            }

        self._stop_indexing = True
        if self.indexing_thread.is_alive():
            self.indexing_thread.join(timeout=2.0)
            
        elapsed = time.time() - self.start_time
        recall = (self.stats['engines_succeeded'] / total_engines) * 100 if total_engines > 0 else 0
        
        yield {
            'type': 'complete',
            'data': {
                'total_results': self.stats['total_results'],
                'unique_urls': self.stats['unique_urls'],
                'elapsed_time': elapsed
            }
        }

    async def _process_engine(self, loop, engine_code):
        try:
            self.rate_limiter.wait_if_needed(engine_code)
            # Use web_query which includes definitional expansion
            queries_to_run = [self.web_query]
            
            if self.level >= 2:
                ft_match = re.search(r'filetype:(\w+)', self.web_query)
                if ft_match:
                    ext = ft_match.group(1)
                    base = self.web_query.replace(f'filetype:{ext}', '').strip()
                    if base: queries_to_run.append(f'{base} inurl:.{ext}')
                
                site_match = re.search(r'site:([\w\.-]+)', self.web_query)
                if site_match:
                    domain = site_match.group(1)
                    if '.' in domain and '*' not in domain:
                         base = self.web_query.replace(f'site:{domain}', '').strip()
                         if base: queries_to_run.append(f'{base} inurl:{domain}')

            queries_to_run = list(dict.fromkeys(queries_to_run))
            all_results = []
            for current_query in queries_to_run:
                raw_results = await loop.run_in_executor(None, self._run_engine_wrapper, engine_code, current_query)
                if raw_results: all_results.extend(raw_results)
            
            self.stats['total_results'] += len(all_results)
            self.rate_limiter.report_success(engine_code)
            clean_results = self._deduplicate(all_results, engine_code)
            
            if (self.level >= 3 or self.force_anchor) and clean_results:
                allowed_cats = {'corporate_registry', 'news', 'social_media', 'blog'}
                follow_up_tasks = []
                for res in clean_results:
                    try:
                        domain = urlparse(res['url']).netloc
                        if domain.startswith('www.'): domain = domain[4:]
                        if (res.get('category') in allowed_cats or self.force_anchor) and domain not in self.expanded_domains:
                            self.expanded_domains.add(domain)
                            follow_up_tasks.append(self._run_anchor_search(domain, self.web_query))
                    except Exception as e:
                        print(f"[BRUTE] Error: {e}")
                        pass
                
                if follow_up_tasks:
                    anchor_results_list = await asyncio.gather(*follow_up_tasks, return_exceptions=True)
                    new_anchor_results = []
                    for res_list in anchor_results_list:
                        if isinstance(res_list, list): new_anchor_results.extend(res_list)
                    if new_anchor_results:
                        anchor_clean = self._deduplicate(new_anchor_results, 'ANCHOR')
                        clean_results.extend(anchor_clean)
            
            return engine_code, clean_results
            
        except Exception as e:
            self.rate_limiter.report_error(engine_code)
            return engine_code, None

    async def _run_anchor_search(self, domain: str, query: str) -> List[Dict]:
        try:
            full_query = f'site:{domain} anchor:"{query}"'
            result = await self.anchor_searcher.search(full_query, max_results=10)
            if result and 'error' not in result: return result.get('results', [])
        except Exception as e:
            print(f"[BRUTE] Error: {e}")
            pass
        return []

    def get_all_results(self) -> List[Dict[str, Any]]:
        all_res = list(self.results.values())
        all_res.sort(key=lambda x: x['quality_score'], reverse=True)
        return all_res
