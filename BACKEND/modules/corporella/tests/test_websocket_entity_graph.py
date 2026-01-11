#!/usr/bin/env python3
"""
Test WebSocket server with entity graph integration
Simulates a client connecting and searching for a company
"""

import asyncio
import websockets
import json
from pathlib import Path

async def test_websocket_with_entity_graph():
    """Test that WebSocket server returns entity relationships"""

    print("=" * 80)
    print("TESTING WEBSOCKET SERVER WITH ENTITY GRAPH")
    print("=" * 80)

    uri = "ws://localhost:8765"

    try:
        async with websockets.connect(uri) as websocket:
            print(f"\n✅ Connected to WebSocket server at {uri}")

            # Wait for connection message
            response = await websocket.recv()
            data = json.loads(response)
            print(f"✅ Server response: {data.get('message')}")

            # Test 1: Search for a company
            print("\n" + "=" * 40)
            print("TEST 1: Search for Company")
            print("=" * 40)

            search_request = {
                "type": "search",
                "query": "TechCorp International Ltd",
                "country_code": "GB"
            }

            print(f"📤 Sending search request: {search_request['query']}")
            await websocket.send(json.dumps(search_request))

            # Collect responses
            entity_relationships = None
            entity_profile = None

            # Listen for responses (timeout after 30 seconds)
            try:
                while True:
                    response = await asyncio.wait_for(websocket.recv(), timeout=30)
                    data = json.loads(response)

                    if data.get("type") == "search_started":
                        print(f"🔍 Search started for: {data.get('query')}")

                    elif data.get("type") == "raw_result":
                        print(f"📦 Raw result from: {data.get('source')}")

                    elif data.get("type") == "entity_update":
                        print(f"🤖 Entity update from: {data.get('source')}")
                        entity_profile = data.get("entity")

                    elif data.get("type") == "profile_saved":
                        print(f"💾 Profile saved with ID: {data.get('company_id')}")
                        if data.get("entity_relationships"):
                            entity_relationships = data["entity_relationships"]
                            print(f"🔗 Entity relationships: {entity_relationships.get('total', 0)} total")

                    elif data.get("type") == "search_complete":
                        print(f"✅ Search complete!")
                        entity_profile = data.get("entity")
                        if data.get("entity_relationships"):
                            entity_relationships = data["entity_relationships"]
                        break

                    elif data.get("type") == "search_error":
                        print(f"❌ Search error: {data.get('error')}")
                        break

            except asyncio.TimeoutError:
                print("⏱️ Search timed out after 30 seconds")

            # Display results
            if entity_profile:
                print("\n" + "=" * 40)
                print("ENTITY PROFILE RECEIVED")
                print("=" * 40)
                print(f"Name: {entity_profile.get('name', {}).get('value', 'N/A')}")
                print(f"Jurisdiction: {entity_profile.get('about', {}).get('jurisdiction', 'N/A')}")

                # Check for officers
                officers = entity_profile.get("officers", [])
                print(f"Officers: {len(officers)}")
                for officer in officers[:3]:
                    print(f"  - {officer.get('name')} ({officer.get('position')})")

            if entity_relationships:
                print("\n" + "=" * 40)
                print("ENTITY RELATIONSHIPS")
                print("=" * 40)
                print(f"Total relationships: {entity_relationships.get('total', 0)}")

                # Show outgoing relationships
                outgoing = entity_relationships.get("outgoing", [])
                if outgoing:
                    print(f"\n📤 Outgoing ({len(outgoing)}):")
                    for rel in outgoing[:5]:
                        print(f"  → {rel.get('relationship_type')}: {rel.get('target_name')} ({rel.get('target_type')})")

                # Show incoming relationships
                incoming = entity_relationships.get("incoming", [])
                if incoming:
                    print(f"\n📥 Incoming ({len(incoming)}):")
                    for rel in incoming[:5]:
                        print(f"  ← {rel.get('relationship_type')}: {rel.get('source_name')} ({rel.get('source_type')})")

            # Test 2: Query relationships directly
            if entity_profile and entity_profile.get("_db_id"):
                print("\n" + "=" * 40)
                print("TEST 2: Query Relationships Directly")
                print("=" * 40)

                relationship_request = {
                    "type": "get_relationships",
                    "entity_id": entity_profile["_db_id"]
                }

                print(f"📤 Requesting relationships for entity ID: {entity_profile['_db_id']}")
                await websocket.send(json.dumps(relationship_request))

                # Wait for response
                response = await websocket.recv()
                data = json.loads(response)

                if data.get("type") == "relationships_result":
                    print("✅ Relationships retrieved successfully")
                    relationships = data.get("relationships", {})
                    print(f"   Total: {relationships.get('total', 0)} relationships")
                elif data.get("type") == "relationships_error":
                    print(f"❌ Error: {data.get('error')}")

            print("\n" + "=" * 80)
            print("TEST COMPLETE")
            print("=" * 80)

    except websockets.exceptions.ConnectionRefusedError:
        print("❌ Could not connect to WebSocket server")
        print("   Make sure websocket_server.py is running")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    return True

async def test_cached_company_relationships():
    """Test that cached companies also return relationships"""

    print("\n" + "=" * 80)
    print("TESTING CACHED COMPANY WITH RELATIONSHIPS")
    print("=" * 80)

    uri = "ws://localhost:8765"

    try:
        async with websockets.connect(uri) as websocket:
            print(f"\n✅ Connected to WebSocket server")

            # Wait for connection
            await websocket.recv()

            # Search for a company that might be cached
            search_request = {
                "type": "search",
                "query": "Apple Inc",
                "country_code": "us_ca"
            }

            print(f"📤 Searching for potentially cached company: {search_request['query']}")
            await websocket.send(json.dumps(search_request))

            # Check if we get cached result with relationships
            cached = False
            has_relationships = False

            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10)
                    data = json.loads(response)

                    if data.get("type") == "cached_profile_loaded":
                        cached = True
                        print("✅ Loading cached profile")

                    elif data.get("type") == "search_complete":
                        if data.get("from_cache"):
                            print("✅ Retrieved from cache")
                            cached = True
                        if data.get("entity_relationships"):
                            has_relationships = True
                            total = data["entity_relationships"].get("total", 0)
                            print(f"🔗 Relationships included: {total} total")
                        break

                except asyncio.TimeoutError:
                    break

            if cached and has_relationships:
                print("✅ Cached companies include entity relationships!")
            elif cached and not has_relationships:
                print("⚠️ Cached company found but no relationships")
            else:
                print("ℹ️ Company was not cached (will be cached now for next run)")

    except Exception as e:
        print(f"❌ Error: {e}")

async def main():
    """Run all tests"""

    print("\n🚀 Starting WebSocket Entity Graph Integration Tests\n")

    # Test 1: Full search with entity graph
    success = await test_websocket_with_entity_graph()

    if success:
        # Test 2: Cached company with relationships
        await test_cached_company_relationships()

    print("\n✅ All tests complete!")

if __name__ == "__main__":
    asyncio.run(main())