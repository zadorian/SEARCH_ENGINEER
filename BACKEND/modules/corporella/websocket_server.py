#!/usr/bin/env python3
"""
Component 4: WebSocket Server
Real-time streaming server for corporate entity population
WITH DATABASE PERSISTENCE
"""

import asyncio
import websockets
import json
from pathlib import Path
import sys
from typing import Optional, Dict, Any

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from populator import CorporateEntityPopulator
from fetcher import GlobalCompanyFetcher
from jurisdiction_actions import JurisdictionActions
from uk_companies_house_fetcher import fetch_uk_company
from wikiman_wiki_fetcher import fetch_wiki_for_jurisdiction
from storage.company_storage import CorporellaStorage
from related_entity_enrichment import enrichment_engine
from bang_executor import BangExecutor


class CorporateWebSocketServer:
    """
    WebSocket server for streaming corporate search results
    and AI-populated entity profiles to frontend

    HYBRID PROCESSING:
    - Streams raw results immediately (Fast Path)
    - Streams AI-merged entities progressively (Smart Path)
    """

    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.clients = set()
        self.populator = CorporateEntityPopulator()
        self.fetcher = GlobalCompanyFetcher()
        self.jurisdiction_actions = JurisdictionActions()
        self.bang_executor = None  # Will initialize when needed

        # Initialize database storage
        self.storage = CorporellaStorage()
        print(f"📦 Database initialized: {self.storage.db_path}")

    async def register(self, websocket):
        """Register a new client"""
        self.clients.add(websocket)
        await self.send_to_client(websocket, {
            "type": "connection",
            "status": "connected",
            "message": "Corporella Claude connected - Ready for company search"
        })

    async def unregister(self, websocket):
        """Unregister a client"""
        if websocket in self.clients:
            self.clients.remove(websocket)

    async def send_to_client(self, websocket, data):
        """Send data to specific client"""
        try:
            await websocket.send(json.dumps(data))
        except websockets.exceptions.ConnectionClosed:
            await self.unregister(websocket)

    async def broadcast(self, data):
        """Broadcast to all connected clients"""
        if self.clients:
            await asyncio.gather(
                *[self.send_to_client(client, data) for client in self.clients],
                return_exceptions=True
            )

    async def handle_search_request(self, websocket, message):
        """
        Handle corporate search request from client

        HYBRID PROCESSING FLOW WITH DATABASE:
        1. Check database for existing profile
        2. If not found, start parallel searches across all sources
        3. Stream raw results immediately (Fast Path)
        4. Process each result with Claude Haiku 4.5 (Smart Path)
        5. Auto-save to database
        6. Stream progressive entity updates
        7. Send final comprehensive profile
        """
        query = message.get("query", "")
        country_code = message.get("country_code")

        await self.send_to_client(websocket, {
            "type": "search_started",
            "query": query,
            "country_code": country_code
        })

        # Initialize components
        fetcher = GlobalCompanyFetcher()
        populator = CorporateEntityPopulator()

        # Check database for existing company profile
        cached_entity = self.storage.load_company(query, country_code)
        if cached_entity:
            print(f"📚 Found cached profile for {query} ({country_code})")

            # Get entity relationships for cached company
            entity_relationships = None
            company_id = cached_entity.get("_db_id")
            if company_id:
                entity_relationships = self.storage.get_entity_relationships(company_id)
                if entity_relationships and "error" not in entity_relationships:
                    print(f"🔗 Entity graph: {entity_relationships.get('total', 0)} relationships found")

            await self.send_to_client(websocket, {
                "type": "cached_profile_loaded",
                "source": "database",
                "message": f"Loading saved profile for {query}"
            })

            # Send the cached entity directly with all sections including entity relationships
            await self.send_to_client(websocket, {
                "type": "search_complete",
                "query": query,
                "entity": cached_entity,
                "jurisdiction_actions": [],  # Will generate these below
                "wiki_sections": None,  # Will fetch these below
                "entity_relationships": entity_relationships,  # Include entity relationships
                "sources_used": ["database_cache"],
                "processing_time": 0.0,
                "errors": [],
                "from_cache": True
            })

            # Still generate jurisdiction actions and wiki for cached entity
            if cached_entity.get("about", {}).get("jurisdiction"):
                jurisdiction = cached_entity["about"]["jurisdiction"]
                company_name = cached_entity.get("name", {}).get("value", query)
                company_number = cached_entity.get("about", {}).get("company_number")

                # Generate action buttons (with dynamic flow analysis)
                jurisdiction_actions = self.jurisdiction_actions.generate_actions(
                    jurisdiction=jurisdiction,
                    company_name=company_name,
                    company_number=company_number,
                    opencorporates_url=cached_entity.get("about", {}).get("opencorporates_url"),
                    registry_url=cached_entity.get("about", {}).get("registry_url"),
                    entity_data=cached_entity  # Pass entity for flow analysis
                )

                # Fetch wiki sections
                wiki_result = fetch_wiki_for_jurisdiction(jurisdiction)

                # Send update with actions and wiki
                await self.send_to_client(websocket, {
                    "type": "cached_profile_enhanced",
                    "jurisdiction_actions": jurisdiction_actions,
                    "wiki_sections": wiki_result if wiki_result.get("ok") else None
                })

            return  # Return early if we have cached data

        try:
            # Run parallel search
            results = await fetcher.parallel_search(query, country_code)

            # Stream raw results immediately (FAST PATH)
            for raw_result in results['raw_results']:
                await self.send_to_client(websocket, {
                    "type": "raw_result",
                    "source": raw_result.get("source"),
                    "data": raw_result
                })

            # Process each result with Haiku (SMART PATH - runs in parallel with display)
            merged_entity = None
            for raw_result in results['raw_results']:
                # Process with Claude Haiku 4.5
                merged_entity = await populator.process_streaming_result(raw_result)

                # Enrich with wiki data if we have a jurisdiction
                if merged_entity and merged_entity.get("about", {}).get("jurisdiction"):
                    jurisdiction = merged_entity["about"]["jurisdiction"]
                    wiki_result = fetch_wiki_for_jurisdiction(jurisdiction)
                    if wiki_result.get("ok"):
                        print(f"Enriching entity update with wiki data for {jurisdiction}")
                        merged_entity = self._enrich_entity_with_wiki(merged_entity, wiki_result)

                # Stream progressive updates
                await self.send_to_client(websocket, {
                    "type": "entity_update",
                    "entity": merged_entity,
                    "source": raw_result.get("source")
                })

            # Generate jurisdiction-aware action buttons AND wiki sections
            jurisdiction_actions = []
            wiki_sections = None

            if merged_entity and merged_entity.get("about", {}).get("jurisdiction"):
                jurisdiction = merged_entity["about"]["jurisdiction"]
                company_name = merged_entity.get("name", {}).get("value", query)
                company_number = merged_entity.get("about", {}).get("company_number")

                # Extract URLs from raw data
                opencorporates_url = None
                registry_url = None
                for raw_result in results['raw_results']:
                    if raw_result.get("source") == "opencorporates" and raw_result.get("companies"):
                        first_company = raw_result["companies"][0]
                        opencorporates_url = first_company.get("opencorporates_url")
                        registry_url = first_company.get("registry_url")
                        break

                # Generate action buttons (with dynamic flow analysis)
                jurisdiction_actions = self.jurisdiction_actions.generate_actions(
                    jurisdiction=jurisdiction,
                    company_name=company_name,
                    company_number=company_number,
                    opencorporates_url=opencorporates_url,
                    registry_url=registry_url,
                    entity_data=merged_entity  # Pass entity for flow analysis
                )

                # Fetch WIKIMAN-PRO wiki sections for this jurisdiction
                wiki_result = fetch_wiki_for_jurisdiction(jurisdiction)
                print(f"Wiki fetch for jurisdiction {jurisdiction}: {wiki_result.get('ok')}")
                if wiki_result.get("ok"):
                    wiki_sections = wiki_result
                    print(f"Wiki sections found: {list(wiki_result.get('sections', {}).keys())}")

                    # Enrich entity profile sections with wiki links
                    if merged_entity:
                        print("Enriching entity with wiki data...")
                        merged_entity = self._enrich_entity_with_wiki(merged_entity, wiki_result)
                        # Check if enrichment worked
                        if merged_entity.get("about", {}).get("_corporate_registry_sources"):
                            print(f"Entity enriched with {len(merged_entity['about']['_corporate_registry_sources'])} corporate registry sources")
                        else:
                            print("No corporate registry sources added to entity")

            # AUTO-SAVE to database after population
            company_id = None
            entity_relationships = None
            if merged_entity:
                try:
                    company_id = self.storage.save_company(merged_entity)
                    print(f"💾 Auto-saved company profile to database: {company_id}")

                    # Get entity relationships after save
                    entity_relationships = self.storage.get_entity_relationships(company_id)
                    if entity_relationships and "error" not in entity_relationships:
                        print(f"🔗 Entity graph: {entity_relationships.get('total', 0)} relationships created")

                    await self.send_to_client(websocket, {
                        "type": "profile_saved",
                        "company_id": company_id,
                        "message": "Company profile saved to database",
                        "entity_relationships": entity_relationships
                    })
                except Exception as e:
                    print(f"⚠️ Failed to save company profile: {e}")
                    # Don't fail the whole request if save fails

            # Send final comprehensive profile WITH jurisdiction actions AND wiki sections AND entity relationships
            await self.send_to_client(websocket, {
                "type": "search_complete",
                "query": query,
                "entity": merged_entity,
                "jurisdiction_actions": jurisdiction_actions,  # Dynamic action buttons
                "wiki_sections": wiki_sections,  # NEW: WIKIMAN-PRO public records sections
                "entity_relationships": entity_relationships,  # NEW: Entity graph relationships
                "sources_used": results['sources_used'],
                "processing_time": results['processing_time'],
                "errors": results['errors'],
                "from_cache": False
            })

        except Exception as e:
            await self.send_to_client(websocket, {
                "type": "search_error",
                "error": str(e),
                "query": query
            })

    def _enrich_entity_with_wiki(self, entity, wiki_result):
        """
        Enrich entity profile sections with WIKIMAN-PRO wiki links

        Adds "_wiki_sources" to each section containing additional source buttons
        """
        if not wiki_result.get("sections"):
            return entity

        wiki_sections = wiki_result["sections"]

        # Initialize compliance section if it doesn't exist
        if "compliance" not in entity:
            entity["compliance"] = {}

        # Map wiki sections to entity sections
        section_mapping = {
            "corporate_registry": None,  # No direct mapping - this goes to about/identity
            "litigation": "litigation",
            "regulatory": "regulatory",
            "asset_registries": "assets",  # Map to assets section
            "licensing": "licensing",  # Map to licensing section
            "political": "political",  # Map to political section
            "further_public_records": "other",
            "media": "reputation",
            "breaches": "breaches"  # Map to breaches section
        }

        # Enrich each section
        for wiki_key, entity_key in section_mapping.items():
            wiki_section = wiki_sections.get(wiki_key, {})
            if not wiki_section.get("links"):
                continue

            if entity_key:
                # Ensure section exists
                if entity_key not in entity["compliance"]:
                    entity["compliance"][entity_key] = {}

                # Add wiki sources to section
                entity["compliance"][entity_key]["_wiki_sources"] = wiki_section["links"]

        # Also add corporate registry links to "about" section
        if "corporate_registry" in wiki_sections and wiki_sections["corporate_registry"].get("links"):
            if "about" not in entity:
                entity["about"] = {}
            entity["about"]["_corporate_registry_sources"] = wiki_sections["corporate_registry"]["links"]

        return entity

    async def handle_entity_update(self, websocket, message):
        """
        Handle entity update request from client
        Saves modified entity data to database

        Args:
            websocket: Client websocket connection
            message: {
                "type": "update_entity",
                "entity": {...entity data...},
                "field": "optional - specific field that was updated",
                "value": "optional - new value for field"
            }
        """
        entity = message.get("entity")
        field = message.get("field")

        if not entity:
            await self.send_to_client(websocket, {
                "type": "update_error",
                "error": "No entity data provided"
            })
            return

        try:
            # Update company in database
            company_name = entity.get("name", {}).get("value", "")
            jurisdiction = entity.get("about", {}).get("jurisdiction")

            if not company_name:
                raise ValueError("Company name required for update")

            # Update in storage
            updated = self.storage.update_company(company_name, jurisdiction, entity)

            if updated:
                print(f"✏️ Updated {field or 'entity'} for {company_name}")
                await self.send_to_client(websocket, {
                    "type": "update_success",
                    "field": field,
                    "message": f"Updated {field or 'company profile'}"
                })
            else:
                # Company doesn't exist, save as new
                company_id = self.storage.save_company(entity)
                print(f"💾 Created new profile for {company_name}: {company_id}")
                await self.send_to_client(websocket, {
                    "type": "update_success",
                    "field": field,
                    "message": f"Created new profile for {company_name}",
                    "company_id": company_id
                })

        except Exception as e:
            print(f"❌ Failed to update entity: {e}")
            await self.send_to_client(websocket, {
                "type": "update_error",
                "error": str(e)
            })

    async def handle_fetch_action(self, websocket, message):
        """
        Handle fetch action requests from frontend buttons

        Args:
            websocket: Client websocket connection
            message: {
                "type": "fetch_action",
                "action": "fetch_uk_ch" | "fetch_ca_sos" | "fetch_aleph" | etc,
                "company_number": str,
                "company_name": str,
                "jurisdiction": str,
                ...additional parameters
            }
        """
        action_type = message.get("action")

        await self.send_to_client(websocket, {
            "type": "fetch_started",
            "action": action_type
        })

        try:
            if action_type == "fetch_uk_ch":
                # UK Companies House API fetch
                company_number = message.get("company_number")

                if not company_number:
                    raise ValueError("Company number required for UK Companies House fetch")

                result = fetch_uk_company(company_number)

                await self.send_to_client(websocket, {
                    "type": "fetch_complete",
                    "action": action_type,
                    "ok": result.get("ok", False),
                    "data": result
                })

            elif action_type == "fetch_aleph":
                # OCCRP Aleph search
                company_name = message.get("company_name") or message.get("query")
                jurisdiction = message.get("jurisdiction")

                # Use existing fetcher
                from aleph_fetcher import fetch_aleph_entities
                result = await fetch_aleph_entities(company_name, jurisdiction)

                await self.send_to_client(websocket, {
                    "type": "fetch_complete",
                    "action": action_type,
                    "ok": result.get("ok", False),
                    "data": result
                })

            elif action_type == "fetch_edgar":
                # SEC EDGAR search
                company_name = message.get("company_name") or message.get("query")

                from edgar_fetcher import fetch_edgar_filings
                result = await fetch_edgar_filings(company_name)

                await self.send_to_client(websocket, {
                    "type": "fetch_complete",
                    "action": action_type,
                    "ok": result.get("ok", False),
                    "data": result
                })

            else:
                raise ValueError(f"Unknown action type: {action_type}")

        except Exception as e:
            await self.send_to_client(websocket, {
                "type": "fetch_error",
                "action": action_type,
                "error": str(e)
            })

    async def handle_get_relationships(self, websocket, message):
        """
        Handle request to get entity relationships

        Args:
            websocket: Client websocket connection
            message: {
                "type": "get_relationships",
                "entity_id": str,  # Entity ID to get relationships for
                "company_name": str,  # Alternative: company name
                "jurisdiction": str   # Optional: with company name
            }
        """
        entity_id = message.get("entity_id")
        company_name = message.get("company_name")
        jurisdiction = message.get("jurisdiction")

        try:
            # If we have company name instead of ID, look it up
            if not entity_id and company_name:
                cached_entity = self.storage.load_company(company_name, jurisdiction)
                if cached_entity:
                    entity_id = cached_entity.get("_db_id")

            if not entity_id:
                await self.send_to_client(websocket, {
                    "type": "relationships_error",
                    "error": "No entity ID or company not found"
                })
                return

            # Get relationships
            relationships = self.storage.get_entity_relationships(entity_id)

            await self.send_to_client(websocket, {
                "type": "relationships_result",
                "entity_id": entity_id,
                "relationships": relationships
            })

        except Exception as e:
            await self.send_to_client(websocket, {
                "type": "relationships_error",
                "error": str(e)
            })

    async def handle_get_enrichment_buttons(self, websocket, message):
        """Handle request for enrichment buttons for an entity"""
        try:
            entity = message.get("entity")
            focused_element = message.get("focused_element")

            if not entity:
                await self.send_to_client(websocket, {
                    "type": "enrichment_buttons_error",
                    "error": "No entity provided"
                })
                return

            # Generate enrichment buttons
            buttons = enrichment_engine.generate_enrichment_buttons(
                entity=entity,
                focused_element=focused_element
            )

            # Also generate enrichment buttons from current entity
            if entity and entity.get("about", {}).get("jurisdiction"):
                # Add any flow-based buttons from entity analysis
                flow_analysis = self.jurisdiction_actions.generate_actions(
                    jurisdiction=entity["about"]["jurisdiction"],
                    company_name=entity.get("name", {}).get("value", ""),
                    company_number=entity.get("about", {}).get("company_number"),
                    entity_data=entity
                )

                # Filter for enrichment-type actions
                for action in flow_analysis:
                    if action.get("type") in ["flow_fetch", "slot_fill"]:
                        buttons.append({
                            "type": "enrichment",
                            "action": action.get("action", "flow_action"),
                            "label": action.get("label"),
                            "description": action.get("description"),
                            "priority": action.get("priority", 10),
                            **action  # Include all action details
                        })

            await self.send_to_client(websocket, {
                "type": "enrichment_buttons",
                "buttons": buttons
            })

        except Exception as e:
            await self.send_to_client(websocket, {
                "type": "enrichment_buttons_error",
                "error": str(e)
            })

    async def handle_execute_enrichment(self, websocket, message):
        """Execute an enrichment action"""
        try:
            action = message.get("action")
            entity = message.get("entity")

            if not action or not entity:
                await self.send_to_client(websocket, {
                    "type": "enrichment_error",
                    "error": "Missing action or entity"
                })
                return

            # Send start notification
            await self.send_to_client(websocket, {
                "type": "enrichment_started",
                "action": action
            })

            # Execute the enrichment
            results = await enrichment_engine.execute_enrichment(action, entity)

            # Send results
            await self.send_to_client(websocket, {
                "type": "enrichment_complete",
                "action": action,
                "results": results
            })

            # If we fetched new companies or data, potentially update the entity
            # This could trigger a re-save to the database
            if results and not results.get("error"):
                # Could integrate results into entity and save
                # For now, just send the results to the client
                pass

        except Exception as e:
            await self.send_to_client(websocket, {
                "type": "enrichment_error",
                "action": action,
                "error": str(e)
            })

    async def handle_bang_search(self, websocket, message):
        """Execute DDG bang searches and populate entity slots with fetched data"""
        try:
            query = message.get("query")  # Company name
            bangs = message.get("bangs", [])  # List of bangs to execute
            entity = message.get("entity", {})  # Current entity data
            country = message.get("country")  # Optional country code

            if not query:
                await self.send_to_client(websocket, {
                    "type": "bang_search_error",
                    "error": "No query provided"
                })
                return

            # Initialize bang executor if needed
            if not self.bang_executor:
                self.bang_executor = BangExecutor()

            # Send start notification
            await self.send_to_client(websocket, {
                "type": "bang_search_started",
                "query": query,
                "bangs": bangs
            })

            # Execute bang searches
            async with self.bang_executor as executor:
                # Execute the bang searches
                bang_results = await executor.execute_bangs(
                    query=query,
                    bangs=bangs if bangs else None,  # Use priority bangs if none specified
                    country=country
                )

                # Stream individual bang results as they complete
                for result in bang_results:
                    await self.send_to_client(websocket, {
                        "type": "bang_result",
                        "bang": result.bang,
                        "url": result.redirected_url,
                        "extracted_data": result.extracted_data,
                        "error": result.error
                    })

                # Populate entity slots with extracted data
                updated_entity = executor.populate_entity_slots(entity, bang_results)

                # Send the updated entity
                await self.send_to_client(websocket, {
                    "type": "bang_search_complete",
                    "query": query,
                    "updated_entity": updated_entity,
                    "bang_count": len(bang_results),
                    "successful_count": len([r for r in bang_results if not r.error])
                })

                # Save to database if we got good data
                if updated_entity.get("name", {}).get("value"):
                    company_id = self.storage.save_company(
                        updated_entity,
                        country_code=country
                    )
                    if company_id:
                        print(f"💾 Saved bang-enriched entity to database (ID: {company_id})")

        except Exception as e:
            await self.send_to_client(websocket, {
                "type": "bang_search_error",
                "error": str(e)
            })

    async def handle_client(self, websocket):
        """
        Handle WebSocket client connection
        """
        await self.register(websocket)

        try:
            async for message in websocket:
                data = json.loads(message)

                if data["type"] == "search":
                    await self.handle_search_request(websocket, data)

                elif data["type"] == "fetch_action":
                    await self.handle_fetch_action(websocket, data)

                elif data["type"] == "update_entity":
                    await self.handle_entity_update(websocket, data)

                elif data["type"] == "get_relationships":
                    await self.handle_get_relationships(websocket, data)

                elif data["type"] == "get_enrichment_buttons":
                    await self.handle_get_enrichment_buttons(websocket, data)

                elif data["type"] == "execute_enrichment":
                    await self.handle_execute_enrichment(websocket, data)

                elif data["type"] == "execute_bang_search":
                    await self.handle_bang_search(websocket, data)

                elif data["type"] == "ping":
                    await self.send_to_client(websocket, {"type": "pong"})

                else:
                    await self.send_to_client(websocket, {
                        "type": "error",
                        "message": f"Unknown message type: {data['type']}"
                    })

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            await self.unregister(websocket)

    async def start_server(self):
        """Start WebSocket server"""
        print(f"🚀 Corporella Claude WebSocket Server")
        print(f"   Listening on ws://{self.host}:{self.port}")
        print(f"   Open client.html in your browser to start searching")
        print(f"\n   Press Ctrl+C to stop\n")

        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()  # Run forever


def main():
    """Run the WebSocket server"""
    server = CorporateWebSocketServer()

    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")


if __name__ == "__main__":
    main()
