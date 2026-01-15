"""
Patch to add unified_search tool to Cymonides MCP server.
"""

UNIFIED_SEARCH_TOOL = '''                Tool(
                    name="unified_search",
                    description="Search across ALL indices with canonical field names: domain, email, username, real_name, phone, password, location, timestamp. Uses smart match types.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Free-text query"},
                            "domain": {"type": "string", "description": "Domain to search"},
                            "email": {"type": "string", "description": "Email to search"},
                            "username": {"type": "string", "description": "Username to search"},
                            "real_name": {"type": "string", "description": "Person or company name"},
                            "phone": {"type": "string", "description": "Phone number"},
                            "password": {"type": "string", "description": "Password or hash"},
                            "location": {"type": "string", "description": "Geographic location"},
                            "limit": {"type": "integer", "default": 100}
                        }
                    }
                ),'''

UNIFIED_SEARCH_HANDLER = '''
        elif name == "unified_search":
            # Use the unified search module
            from search.unified_search import UnifiedSearch

            searcher = UnifiedSearch()
            results = searcher.search(
                query=args.get("query"),
                domain=args.get("domain"),
                email=args.get("email"),
                username=args.get("username"),
                real_name=args.get("real_name"),
                phone=args.get("phone"),
                password=args.get("password"),
                location=args.get("location"),
                size=int(args.get("limit", 100) or 100)
            )

            # Convert results to dicts
            from collections import Counter
            index_counts = Counter(r.source_index for r in results)

            return {
                "total": len(results),
                "by_index": dict(index_counts),
                "results": [
                    {
                        "index": r.source_index,
                        "score": r.score,
                        "domain": r.domain,
                        "email": r.email,
                        "username": r.username,
                        "real_name": r.real_name,
                        "phone": r.phone,
                        "location": r.location,
                        "timestamp": r.timestamp
                    }
                    for r in results
                ]
            }
'''

def apply_patch(mcp_server_path: str):
    """Apply the unified_search patch to the MCP server."""
    with open(mcp_server_path, 'r') as f:
        content = f.read()

    # Check if already patched
    if 'name="unified_search"' in content:
        print("Already patched")
        return

    # Insert tool definition after index_stats tool
    # Find: name="index_stats" ... }), and insert after
    import re
    pattern = r'(name="index_stats".*?}\s*\),)'
    match = re.search(pattern, content, re.DOTALL)

    if match:
        insert_pos = match.end()
        content = content[:insert_pos] + '\n' + UNIFIED_SEARCH_TOOL + content[insert_pos:]
        print("Tool definition inserted")
    else:
        print("Could not find index_stats tool")
        return

    # Insert handler in _handle_tool method
    # Find: elif name == "index_stats": and insert before it
    handler_pattern = r'(elif name == "index_stats":)'
    handler_match = re.search(handler_pattern, content)

    if handler_match:
        insert_pos = handler_match.start()
        content = content[:insert_pos] + UNIFIED_SEARCH_HANDLER + '\n        ' + content[insert_pos:]
        print("Handler inserted")
    else:
        print("Could not find index_stats handler")
        return

    # Write back
    with open(mcp_server_path, 'w') as f:
        f.write(content)

    print("Patch applied successfully")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        apply_patch(sys.argv[1])
    else:
        print("Usage: python unified_search_tool_patch.py <path_to_mcp_server.py>")
