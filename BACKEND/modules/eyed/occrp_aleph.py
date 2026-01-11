import os
import aiohttp
import asyncio
import argparse
import json
from typing import List, Dict, Optional
import logging
from pathlib import Path
from dotenv import load_dotenv
import re # Import re for prefix checking

# Fix import path for config
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

class AlephSearcher:
    """
    OCCRP Aleph searcher for investigative data
    
    Aleph stores documents, entities, and structured datasets acquired 
    from public sources like leaks, investigations, and government records.
    """
    
    def __init__(self, api_key: str = None):
        """Initialize with optional API key override"""
        # Try to get API key from environment
        if not api_key:
            # Check environment variable
            api_key = os.getenv("ALEPH_API_KEY")
        
        self.api_key = api_key
        self.base_url = "https://aleph.occrp.org/api/2"
        
        # Set up headers only if API key is available
        if self.api_key:
            self.headers = {
                "Authorization": f"ApiKey {self.api_key}",
                "Accept": "application/json"
            }
            logger.info("Aleph API initialized successfully")
        else:
            self.headers = {"Accept": "application/json"}
            logger.warning("No ALEPH_API_KEY provided. Some features may be limited.")
    
    async def search(
        self,
        query: str,
        max_results: int = 100,
        schemas: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Search the Aleph database for entities and documents
        
        Args:
            query: Search query
            max_results: Maximum number of results to return (default 100)
            schemas: List of schemas to search (default searches all)
            
        Returns:
            List of search results with title, URL, and snippet
        """
        results = []
        
        # Check if API key is available
        if not self.api_key:
            logger.warning("ALEPH_API_KEY not set. Add it to your .env file to enable Aleph searches.")
            return []
        
        # --- Enhanced Exact Phrase Detection ---
        search_query = query
        is_exact_phrase = False
        is_intitle_search = False
        
        # Check for intitle: prefix first
        intitle_match = re.match(r'^"?intitle:(.*?)"?$', query, re.IGNORECASE)
        if intitle_match:
            is_intitle_search = True
            keyword_part = intitle_match.group(1).strip()
            # Format for Aleph/Elasticsearch: title:keyword or title:"keywords phrase"
            if ' ' in keyword_part:
                 search_query = f'title:"{keyword_part}"'
            else:
                 search_query = f'title:{keyword_part}'
            logger.info(f"🎯 EXACT PHRASE intitle search detected. API query: {search_query}")
        else:
            # --- EXACT PHRASE HANDLING for regular searches ---
            if query.startswith('"') and query.endswith('"') and len(query) > 2:
                is_exact_phrase = True
                # PRESERVE quotes for Aleph API exact phrase matching
                search_query = query  # Keep the quotes!
                logger.info(f'🎯 EXACT PHRASE search detected: {search_query}')
                logger.info("📌 Quotes preserved for Aleph API exact phrase matching")
            else:
                # Standard keyword search
                search_query = query
                logger.info(f"🔍 Standard keyword search. API query: {search_query}")
        
        print(f"\nSearching Aleph with query: {search_query}")
        if is_exact_phrase:
            print("🎯 EXACT PHRASE MODE: Quotes preserved for precise matching")
        print(f"Max results: {max_results}")
        
        # Schemas to search (use provided list or default)
        if schemas is None:
            schemas = ["Document", "LegalEntity", "Company", "Person"]
        
        async with aiohttp.ClientSession() as session:
            for schema in schemas:
                if len(results) >= max_results:
                    break
                    
                params = {
                    "q": search_query, # Quotes preserved if exact phrase
                    "limit": min(30, max_results - len(results)),
                    "offset": 0,
                    "filter:schema": schema,
                    # "filter:schemata": schema # Redundant? Check API docs
                }
                
                print(f"Searching schema: {schema}")
                
                current_offset = 0
                while len(results) < max_results:
                    params["offset"] = current_offset # Update offset for pagination
                    try:
                        async with session.get(
                                f"{self.base_url}/entities", 
                            headers=self.headers,
                            params=params
                        ) as response:
                            if response.status != 200:
                                error_text = await response.text()
                                logger.error(f"Aleph API error: {response.status}, {error_text}")
                                break # Exit pagination loop for this schema on error
                            
                            data = await response.json()
                            
                            # Extract results
                            items = data.get("results", [])
                            if not items:
                                break # Exit pagination loop if no more items
                                
                            for item in items:
                                # Get properties for easier access
                                props = item.get("properties", {})
                                
                                # Extract title from properties if available
                                title = (
                                    # First try direct item fields
                                    item.get("caption") or 
                                    item.get("name") or
                                    # Then try properties
                                    (props.get("title", [""])[0] if isinstance(props.get("title"), list) else props.get("title")) or
                                    "Unknown"
                                )
                                
                                # Create a result entry
                                result = {
                                    "title": title,
                                    "url": f"https://aleph.occrp.org/entities/{item.get('id')}",
                                    "snippet": (
                                        item.get("summary") or 
                                        item.get("description") or
                                        # Try to get text from properties
                                        (props.get("text", [""])[0] if isinstance(props.get("text"), list) else props.get("text")) or
                                        ""
                                    ),
                                    "source": "aleph",
                                    "schema": item.get("schema", ""),
                                    "properties": props,
                                    "exact_phrase_search": is_exact_phrase  # Flag for result tracking
                                }
                                
                                # Add source URL if available
                                source_url = props.get("sourceUrl")
                                if source_url:
                                    if isinstance(source_url, list):
                                        result["source_url"] = source_url[0]
                                    else:
                                        result["source_url"] = source_url
                                
                                # Debug: Print raw item data for first few results
                                if len(results) < 2:
                                    print("\nDEBUG - Raw item data:")
                                    print("Schema:", item.get("schema"))
                                    print("Properties:", item.get("properties"))
                                    print("Available fields:", list(item.keys()))
                                
                                # Add file URLs if available
                                file_url = item.get("file_url")
                                if file_url:
                                    result["file_url"] = file_url
                                    
                                # Add PDF URLs from properties
                                if schema == "Document":
                                    pdf_url = None
                                    # Check for direct file URL first
                                    file_url = item.get("file_url")
                                    if file_url and isinstance(file_url, str) and file_url.lower().endswith(".pdf"):
                                        pdf_url = file_url
                                    
                                    if not pdf_url:
                                        # Check common PDF URL fields in properties
                                        for field in ["fileUrl", "documentUrl", "sourceUrl", "url"]:
                                            if field in props:
                                                url_value = props[field]
                                                # Handle both string and list values
                                                if isinstance(url_value, str) and url_value.lower().endswith(".pdf"):
                                                    pdf_url = url_value
                                                    break
                                                elif isinstance(url_value, list) and url_value:
                                                    # Take first URL that ends with .pdf
                                                    pdf_urls = [u for u in url_value if isinstance(u, str) and u.lower().endswith(".pdf")]
                                                    if pdf_urls:
                                                        pdf_url = pdf_urls[0]
                                                        break
                                    
                                    # Add processing status information
                                    result["processing_status"] = props.get("processingStatus", ["unknown"])[0] if isinstance(props.get("processingStatus"), list) else props.get("processingStatus", "unknown")
                                    if props.get("processingError"):
                                        result["processing_error"] = props.get("processingError")[0] if isinstance(props.get("processingError"), list) else props.get("processingError")
                                    
                                    if pdf_url:
                                        result["pdf_url"] = pdf_url
                                    
                                    # Add file metadata if available
                                    if props.get("fileSize"):
                                        result["file_size"] = props.get("fileSize")[0] if isinstance(props.get("fileSize"), list) else props.get("fileSize")
                                    if props.get("mimeType"):
                                        result["mime_type"] = props.get("mimeType")[0] if isinstance(props.get("mimeType"), list) else props.get("mimeType")
                                
                                # Append the result for every schema (after any document-specific enrichment)
                                results.append(result)
                                if len(results) >= max_results:
                                    break  # Exit inner item loop if max hit

                                # Check pagination after processing items for the current page
                                if len(results) >= max_results: break # Exit pagination loop if max hit
                                if len(items) < params["limit"]: break # Exit pagination loop if last page received
                                
                                # Determine next offset/page
                                # Prefer 'next' link from Aleph if available, otherwise increment offset
                                # (Current logic uses offset incrementing) 
                                next_link = data.get("next") # Check if 'next' exists in response
                                if next_link: 
                                    # TODO: If using 'next' link, need logic to parse it or adjust request.
                                    # For now, stick to offset logic as implemented.
                                    current_offset += params["limit"]
                                elif data.get("next_offset"): # Use Aleph's offset if provided
                                     current_offset = data["next_offset"]
                                else:
                                     # Fallback if neither next nor next_offset is present
                                     current_offset += params["limit"] 
                                     if current_offset >= data.get("total", current_offset): # Avoid infinite loop if total is known
                                          break
                                
                    except Exception as e:
                        logger.error(f"Error during Aleph pagination for schema {schema}: {str(e)}")
                        break # Exit pagination loop on error
                # Break outer schema loop if max results reached
                if len(results) >= max_results: break 
        
        print(f"Found {len(results)} results from Aleph")
        if is_exact_phrase:
            print("🎯 Exact phrase search completed")
        
        # Display results in a more readable format
        for i, result in enumerate(results[:5], 1):  # Show first 5 results
            print(f"\nResult {i}:")
            print("Title:", result.get("title", "Unknown"))
            print("URL:", result.get("url", ""))
            if "source_url" in result:
                print("Source URL:", result["source_url"])
            print("Type:", result.get("schema", "Unknown"))
            
            # Show document processing information
            if result.get("schema") == "Document":
                print("Processing Status:", result.get("processing_status", "unknown"))
                if result.get("processing_error"):
                    print("Processing Error:", result["processing_error"])
                if result.get("file_size"):
                    print("File Size:", result["file_size"], "bytes")
                if result.get("mime_type"):
                    print("MIME Type:", result["mime_type"])
            
            if "pdf_url" in result:
                print("PDF URL:", result["pdf_url"])
            if "file_url" in result:
                print("File URL:", result["file_url"])
            if result.get("snippet"):
                print("Snippet:", result["snippet"][:200] + "..." if len(result["snippet"]) > 200 else result["snippet"])
            print("-" * 80)
            
        if len(results) > 5:
            print(f"\n... and {len(results) - 5} more results")
        
        return results
    
    async def search_entities(self, query: str, entity_types: Optional[List[str]] = None, max_results: int = 100) -> List[Dict]:
        """
        Search specifically for entities in Aleph
        
        Args:
            query: Search query
            entity_types: List of entity types to filter by (e.g., ["Person", "Company"])
            max_results: Maximum number of results to return
            
        Returns:
            List of entity results
        """
        # --- Enhanced Exact Phrase Detection ---
        search_query = query
        is_exact_phrase = False
        is_intitle_search = False
        
        # Check for intitle: prefix first
        intitle_match = re.match(r'^"?intitle:(.*?)"?$', query, re.IGNORECASE)
        if intitle_match:
            is_intitle_search = True
            keyword_part = intitle_match.group(1).strip()
            if ' ' in keyword_part:
                 search_query = f'title:"{keyword_part}"'
            else:
                 search_query = f'title:{keyword_part}'
            logger.info(f"🎯 EXACT PHRASE intitle entity search detected. API query: {search_query}")
        else:
            # --- EXACT PHRASE HANDLING for regular entity searches ---
            if query.startswith('"') and query.endswith('"') and len(query) > 2:
                is_exact_phrase = True
                # PRESERVE quotes for Aleph API exact phrase matching
                search_query = query  # Keep the quotes!
                logger.info(f'🎯 EXACT PHRASE entity search detected: {search_query}')
                logger.info("📌 Quotes preserved for Aleph API exact phrase matching")
            else:
                # Standard keyword search
                search_query = query
                logger.info(f"🔍 Standard keyword entity search. API query: {search_query}")

        # Add schema filter if needed (append AFTER title: or query)
        schema_filter = None
        if entity_types:
            schema_filter = " OR ".join([f"schema:{t}" for t in entity_types])
            search_query = f"({search_query}) AND ({schema_filter})" # Grouping might be needed
        
        params = {
            "q": search_query,  # Quotes preserved if exact phrase
            "limit": min(30, max_results),
            "offset": 0,
            # "filter:schema": "Thing" # Filter applied within query string now
        }
        
        results = []
        
        async with aiohttp.ClientSession() as session:
            while len(results) < max_results:
                try:
                    # Make search request
                    async with session.get(
                        f"{self.base_url}/entities", 
                        headers=self.headers,
                        params=params
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Aleph API error: {response.status}, {error_text}")
                            break
                        
                        data = await response.json()
                        
                        # Extract results
                        items = data.get("results", [])
                        if not items:
                            break
                            
                        for item in items:
                            # Create a result entry
                            result = {
                                "title": item.get("caption", item.get("name", "Unknown")),
                                "url": f"https://aleph.occrp.org/entities/{item.get('id')}",
                                "snippet": item.get("summary", ""),
                                "source": "aleph_entity",
                                "schema": item.get("schema", ""),
                                "properties": item.get("properties", {}),
                                "exact_phrase_search": is_exact_phrase  # Flag for result tracking
                            }
                            # Correct indentation for results.append
                            results.append(result)
                            
                            if len(results) >= max_results:
                                break
                        
                        # Check if there are more results
                        if len(items) < params["limit"] or not data.get("next_offset"):
                            break
                            
                        # Update offset for next page
                        params["offset"] = data.get("next_offset")
                        
                except Exception as e:
                    logger.error(f"Error searching Aleph entities: {str(e)}")
                    break
        
        if is_exact_phrase:
            logger.info(f"🎯 Exact phrase entity search completed: {len(results)} results")
        
        return results

    async def search_parallel(
        self,
        query: str,
        max_results: int = 100,
        schemas: Optional[List[str]] = None,
        max_concurrent: int = 6  # Limit concurrent requests to avoid overwhelming API
    ) -> List[Dict]:
        """
        PARALLEL search method - searches multiple schemas concurrently for much faster results.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return across all schemas
            schemas: List of schemas to search (default searches all)
            max_concurrent: Maximum number of concurrent schema searches
            
        Returns:
            List of search results with title, URL, and snippet
        """
        results = []
        
        # Check if API key is available
        if not self.api_key:
            logger.warning("ALEPH_API_KEY not set. Add it to your .env file to enable Aleph searches.")
            return []
        
        # --- Enhanced Exact Phrase Detection (same as other methods) ---
        search_query = query
        is_exact_phrase = False
        is_intitle_search = False
        
        # Check for intitle: prefix first
        intitle_match = re.match(r'^"?intitle:(.*?)"?$', query, re.IGNORECASE)
        if intitle_match:
            is_intitle_search = True
            keyword_part = intitle_match.group(1).strip()
            if ' ' in keyword_part:
                 search_query = f'title:"{keyword_part}"'
            else:
                 search_query = f'title:{keyword_part}'
            logger.info(f"🎯 EXACT PHRASE intitle parallel search detected. API query: {search_query}")
        else:
            # --- EXACT PHRASE HANDLING for regular parallel searches ---
            if query.startswith('"') and query.endswith('"') and len(query) > 2:
                is_exact_phrase = True
                # PRESERVE quotes for Aleph API exact phrase matching
                search_query = query  # Keep the quotes!
                logger.info(f'🎯 EXACT PHRASE parallel search detected: {search_query}')
                logger.info("📌 Quotes preserved for Aleph API exact phrase matching")
            else:
                # Standard keyword search
                search_query = query
                logger.info(f"🔍 Standard keyword parallel search. API query: {search_query}")
        
        print(f"\n🚀 PARALLEL Aleph search with query: {search_query}")
        if is_exact_phrase:
            print("🎯 EXACT PHRASE MODE: Quotes preserved for precise matching across all schemas")
        print(f"Max results: {max_results}")
        print(f"Max concurrent schemas: {max_concurrent}")
        
        # Schemas to search (use provided list or default)
        if schemas is None:
            schemas = ["Document", "LegalEntity", "Company", "Person"]
        
        # Split schemas into batches to limit concurrent requests
        schema_batches = [schemas[i:i+max_concurrent] for i in range(0, len(schemas), max_concurrent)]
        
        async with aiohttp.ClientSession() as session:
            for batch_num, schema_batch in enumerate(schema_batches, 1):
                print(f"\n📊 Processing batch {batch_num}/{len(schema_batches)}: {len(schema_batch)} schemas")
                
                # Create tasks for this batch of schemas
                tasks = []
                for schema in schema_batch:
                    if len(results) >= max_results:
                        break
                    task = self._search_single_schema_parallel(
                        session, search_query, schema, 
                        min(50, max_results - len(results)),  # Distribute max_results across schemas
                        is_exact_phrase  # Pass exact phrase flag
                    )
                    tasks.append(task)
                
                if not tasks:
                    break
                
                # Execute this batch of schema searches in parallel
                try:
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Process results from this batch
                    for i, schema_results in enumerate(batch_results):
                        schema = schema_batch[i]
                        if isinstance(schema_results, Exception):
                            logger.error(f"Error searching schema {schema}: {schema_results}")
                            continue
                        
                        if schema_results:
                            results.extend(schema_results)
                            exact_phrase_indicator = "🎯" if is_exact_phrase else "🔍"
                            print(f"{exact_phrase_indicator} {schema}: {len(schema_results)} results")
                        else:
                            print(f"❌ {schema}: 0 results")
                        
                        # Stop if we've reached max_results
                        if len(results) >= max_results:
                            results = results[:max_results]  # Trim to exact limit
                            print(f"🎯 Reached max results limit ({max_results})")
                            break
                    
                except Exception as e:
                    logger.error(f"Error in parallel batch execution: {e}")
                    continue
                
                # Stop processing batches if we have enough results
                if len(results) >= max_results:
                    break
        
        completion_message = f"🏁 Parallel search completed: {len(results)} total results"
        if is_exact_phrase:
            completion_message += " (EXACT PHRASE)"
        print(f"\n{completion_message}")
        
        return results[:max_results]  # Ensure we don't exceed max_results
    
    async def _search_single_schema_parallel(
        self, 
        session: aiohttp.ClientSession, 
        search_query: str, 
        schema: str, 
        max_results_for_schema: int,
        is_exact_phrase: bool
    ) -> List[Dict]:
        """
        Search a single schema with pagination (helper for parallel search).
        
        Args:
            session: Shared aiohttp session
            search_query: Formatted search query (with quotes preserved if exact phrase)
            schema: Schema name to search
            max_results_for_schema: Max results to fetch for this schema
            is_exact_phrase: Flag indicating if the search is an exact phrase search
            
        Returns:
            List of results for this schema
        """
        results = []
        current_offset = 0
        
        while len(results) < max_results_for_schema:
            params = {
                "q": search_query,  # Quotes preserved if exact phrase
                "limit": min(30, max_results_for_schema - len(results)),
                "offset": current_offset,
                "filter:schema": schema,
            }
            
            try:
                async with session.get(
                    f"{self.base_url}/entities", 
                    headers=self.headers,
                    params=params
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Aleph API error for schema {schema}: {response.status}, {error_text}")
                        break
                    
                    data = await response.json()
                    items = data.get("results", [])
                    
                    if not items:
                        break  # No more results for this schema
                        
                    for item in items:
                        # Get properties for easier access
                        props = item.get("properties", {})
                        
                        # Extract title from properties if available
                        title = (
                            item.get("caption") or 
                            item.get("name") or
                            (props.get("title", [""])[0] if isinstance(props.get("title"), list) else props.get("title")) or
                            "Unknown"
                        )
                        
                        # Create a result entry
                        result = {
                            "title": title,
                            "url": f"https://aleph.occrp.org/entities/{item.get('id')}",
                            "snippet": (
                                item.get("summary") or 
                                item.get("description") or
                                (props.get("text", [""])[0] if isinstance(props.get("text"), list) else props.get("text")) or
                                ""
                            ),
                            "source": "aleph",
                            "schema": item.get("schema", ""),
                            "properties": props,
                            "exact_phrase_search": is_exact_phrase  # Flag for result tracking
                        }
                        
                        # Add source URL if available
                        source_url = props.get("sourceUrl")
                        if source_url:
                            if isinstance(source_url, list):
                                result["source_url"] = source_url[0]
                            else:
                                result["source_url"] = source_url
                        
                        # Add file URLs and processing info for Documents
                        if schema == "Document":
                            self._add_document_metadata(result, item, props)
                        
                        results.append(result)
                        
                        if len(results) >= max_results_for_schema:
                            break
                    
                    # Check for pagination
                    if len(items) < params["limit"]:
                        break  # Last page
                    
                    # Update offset for next page
                    if data.get("next_offset"):
                        current_offset = data["next_offset"]
                    else:
                        current_offset += params["limit"]
                        
            except Exception as e:
                logger.error(f"Error during pagination for schema {schema}: {str(e)}")
                break
        
        return results
    
    def _add_document_metadata(self, result: dict, item: dict, props: dict):
        """Add document-specific metadata to result."""
        # Add PDF URLs from properties
        pdf_url = None
        file_url = item.get("file_url")
        if file_url and isinstance(file_url, str) and file_url.lower().endswith(".pdf"):
            pdf_url = file_url
        
        if not pdf_url:
            # Check common PDF URL fields in properties
            for field in ["fileUrl", "documentUrl", "sourceUrl", "url"]:
                if field in props:
                    url_value = props[field]
                    if isinstance(url_value, str) and url_value.lower().endswith(".pdf"):
                        pdf_url = url_value
                        break
                    elif isinstance(url_value, list) and url_value:
                        pdf_urls = [u for u in url_value if isinstance(u, str) and u.lower().endswith(".pdf")]
                        if pdf_urls:
                            pdf_url = pdf_urls[0]
                            break
        
        # Add processing status information
        result["processing_status"] = props.get("processingStatus", ["unknown"])[0] if isinstance(props.get("processingStatus"), list) else props.get("processingStatus", "unknown")
        if props.get("processingError"):
            result["processing_error"] = props.get("processingError")[0] if isinstance(props.get("processingError"), list) else props.get("processingError")
        
        if pdf_url:
            result["pdf_url"] = pdf_url
        
        # Add file metadata if available
        if props.get("fileSize"):
            result["file_size"] = props.get("fileSize")[0] if isinstance(props.get("fileSize"), list) else props.get("fileSize")
        if props.get("mimeType"):
            result["mime_type"] = props.get("mimeType")[0] if isinstance(props.get("mimeType"), list) else props.get("mimeType")

def main_interactive():
    """Interactive CLI for OCCRP Aleph searches"""
    print("=" * 60)
    print("🔍 OCCRP ALEPH INTERACTIVE SEARCH")
    print("=" * 60)
    print("Search investigative documents, entities, and structured datasets")
    print("from public sources, leaks, and government records.")
    print()
    
    # Initialize searcher
    searcher = AlephSearcher()
    
    while True:
        print("\n" + "=" * 60)
        print("ALEPH SEARCH OPTIONS:")
        print("1. Document & Entity Search (mixed)")
        print("2. Entity Search Only")
        print("3. Exit")
        print("=" * 60)
        
        choice = input("Choose an option (1-3): ").strip()
        
        if choice == "3":
            print("Goodbye!")
            break
            
        if choice not in ["1", "2"]:
            print("❌ Invalid choice. Please enter 1, 2, or 3.")
            continue
            
        # Get search query
        print("\n" + "-" * 40)
        query = input("Enter your search query: ").strip()
        if not query:
            print("❌ Query cannot be empty.")
            continue
            
        # Get max results
        while True:
            max_results_input = input("Max results (default 50): ").strip()
            if not max_results_input:
                max_results = 50
                break
            try:
                max_results = int(max_results_input)
                if max_results <= 0:
                    print("❌ Max results must be a positive number.")
                    continue
                break
            except ValueError:
                print("❌ Please enter a valid number.")
        
        try:
            if choice == "1":
                # Mixed search
                schemas_input = input("Schemas to search (default: Document,LegalEntity,Company,Person): ").strip()
                if schemas_input:
                    schemas = [s.strip() for s in schemas_input.split(",") if s.strip()]
                else:
                    schemas = None
                    
                print(f"\n🔍 Searching Aleph for: '{query}'")
                print(f"📊 Max results: {max_results}")
                if schemas:
                    print(f"📋 Schemas: {', '.join(schemas)}")
                
                results = asyncio.run(searcher.search(
                    query=query, 
                    max_results=max_results,
                    schemas=schemas
                ))
                
            elif choice == "2":
                # Entity search only
                entity_types_input = input("Entity types (default: Company,Person): ").strip()
                if entity_types_input:
                    entity_types = [t.strip() for t in entity_types_input.split(",") if t.strip()]
                else:
                    entity_types = ["Company", "Person"]
                    
                print(f"\n🔍 Searching Aleph entities for: '{query}'")
                print(f"📊 Max results: {max_results}")
                print(f"🏢 Entity types: {', '.join(entity_types)}")
                
                results = asyncio.run(searcher.search_entities(
                    query=query,
                    entity_types=entity_types,
                    max_results=max_results
                ))
            
            # Ask if user wants to save results
            if results:
                save_choice = input(f"\n💾 Save {len(results)} results to JSON file? (y/N): ").strip().lower()
                if save_choice in ['y', 'yes']:
                    filename = input("Enter filename (default: aleph_results.json): ").strip()
                    if not filename:
                        filename = "aleph_results.json"
                    if not filename.endswith('.json'):
                        filename += '.json'
                    
                    try:
                        with open(filename, 'w', encoding='utf-8') as f:
                            json.dump(results, f, ensure_ascii=False, indent=2)
                        print(f"✅ Results saved to {filename}")
                    except Exception as e:
                        print(f"❌ Error saving file: {e}")
            else:
                print("📭 No results found.")
                
        except Exception as e:
            print(f"❌ Error during search: {e}")
            
        # Ask if user wants to continue
        continue_choice = input("\n🔄 Perform another search? (Y/n): ").strip().lower()
        if continue_choice in ['n', 'no']:
            print("Goodbye!")
            break


if __name__ == "__main__":
    main_interactive() 