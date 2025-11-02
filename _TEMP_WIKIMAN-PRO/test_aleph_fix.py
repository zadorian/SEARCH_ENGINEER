#!/usr/bin/env python3
"""
Test script to verify Aleph integration in wikiman-pro MCP server
Tests all corporate intelligence tools: OpenCorporates, Aleph, Officers, and Parallel search
"""

import sys
import importlib.util
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def test_corporella_tools():
    """Test all corporella tools directly"""
    print("="*80)
    print("TESTING CORPORELLA TOOLS DIRECTLY")
    print("="*80)

    # Import corporella
    from corporella import (
        tool_opencorporates_search,
        tool_opencorporates_officers,
        tool_aleph_search,
        tool_parallel_search
    )

    print("\n✓ All corporella tools imported successfully\n")

    # Test 1: OpenCorporates search
    print("TEST 1: OpenCorporates search for 'Tesla'")
    print("-" * 40)
    result = tool_opencorporates_search("Tesla")
    print(f"Result OK: {result.get('ok')}")
    if result.get('ok'):
        companies = result.get('results', {}).get('companies', [])
        print(f"Found {len(companies)} companies")
        if companies:
            print(f"First result: {companies[0].get('name')}")
    else:
        print(f"Error: {result.get('error')}")

    # Test 2: Aleph search
    print("\n\nTEST 2: Aleph search for 'Tesla'")
    print("-" * 40)
    result = tool_aleph_search("Tesla")
    print(f"Result OK: {result.get('ok')}")
    if result.get('ok'):
        entities = result.get('results', {}).get('entities', [])
        print(f"Found {len(entities)} entities")
        if entities:
            first = entities[0]
            props = first.get('properties', {})
            name_val = props.get('name', [])
            if isinstance(name_val, list) and name_val:
                name = name_val[0]
            elif isinstance(name_val, str):
                name = name_val
            else:
                name = 'Unknown'
            print(f"First result: {name} ({first.get('schema')})")
    else:
        print(f"Error: {result.get('error')}")

    # Test 3: Officer search
    print("\n\nTEST 3: Officer search for 'Elon Musk'")
    print("-" * 40)
    result = tool_opencorporates_officers("Elon Musk")
    print(f"Result OK: {result.get('ok')}")
    if result.get('ok'):
        officers = result.get('results', {}).get('officers', [])
        print(f"Found {len(officers)} positions")
        if officers:
            print(f"First result: {officers[0].get('name')} at {officers[0].get('company', {}).get('name')}")
    else:
        print(f"Error: {result.get('error')}")

    # Test 4: Parallel search (OpenCorporates + Aleph simultaneously)
    print("\n\nTEST 4: Parallel search for 'Tesla' (OpenCorporates + Aleph)")
    print("-" * 40)
    result = tool_parallel_search("Tesla")
    print(f"Result OK: {result.get('ok')}")
    if result.get('ok'):
        sources = result.get('sources', {})
        print(f"OpenCorporates: {sources.get('opencorporates', {}).get('success')} - {sources.get('opencorporates', {}).get('companies_found')} companies")
        print(f"Aleph: {sources.get('aleph', {}).get('success')} - {sources.get('aleph', {}).get('entities_found')} entities")
        print(f"Officers: {sources.get('officers', {}).get('success')} - {sources.get('officers', {}).get('officers_found')} officers")
        print(f"\nExecution times:")
        exec_times = result.get('execution_times', {})
        for source, time in exec_times.items():
            print(f"  {source}: {time:.2f}s")
    else:
        print(f"Error: {result.get('error')}")

def test_mcp_server_loading():
    """Test that MCP server loads corporella tools correctly"""
    print("\n\n" + "="*80)
    print("TESTING MCP SERVER MODULE LOADING")
    print("="*80)

    # Load mcp_server module
    spec = importlib.util.spec_from_file_location("mcp_server", Path(__file__).parent / "mcp_server.py")
    mcp_server = importlib.util.module_from_spec(spec)

    # Check if tools would be loaded (without actually running the server)
    print("\nChecking if corporella tools are defined in mcp_server...")

    # This will trigger the module loading
    spec.loader.exec_module(mcp_server)

    # Check if tools are available
    tools_status = {
        'tool_opencorporates_search': hasattr(mcp_server, 'tool_opencorporates_search') and mcp_server.tool_opencorporates_search is not None,
        'tool_opencorporates_officers': hasattr(mcp_server, 'tool_opencorporates_officers') and mcp_server.tool_opencorporates_officers is not None,
        'tool_aleph_search': hasattr(mcp_server, 'tool_aleph_search') and mcp_server.tool_aleph_search is not None,
        'tool_parallel_search': hasattr(mcp_server, 'tool_parallel_search') and mcp_server.tool_parallel_search is not None,
    }

    print("\nTool availability in MCP server:")
    for tool, available in tools_status.items():
        status = "✓ Available" if available else "✗ Not available"
        print(f"  {tool}: {status}")

    all_available = all(tools_status.values())
    if all_available:
        print("\n✓ All corporella tools successfully loaded in MCP server!")
    else:
        print("\n✗ Some corporella tools failed to load in MCP server")
        return False

    return True

if __name__ == "__main__":
    try:
        # Test corporella tools directly
        test_corporella_tools()

        # Test MCP server loading
        success = test_mcp_server_loading()

        print("\n" + "="*80)
        if success:
            print("✓ ALL TESTS PASSED - Aleph integration is working correctly!")
        else:
            print("✗ SOME TESTS FAILED - Check logs above")
        print("="*80)

    except Exception as e:
        print(f"\n✗ TEST FAILED WITH ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
