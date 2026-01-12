#!/usr/bin/env python3
"""
Search Whoosh Index - Simple CLI search tool
Usage: python3 search_whoosh.py "search query"
"""
import sys
import os
from pathlib import Path

try:
    from whoosh.index import open_dir
    from whoosh.qparser import QueryParser, MultifieldParser
    from whoosh import scoring
except ImportError:
    print("Installing whoosh...")
    os.system("pip3 install whoosh")
    from whoosh.index import open_dir
    from whoosh.qparser import QueryParser, MultifieldParser
    from whoosh import scoring

def search_index(index_path, query_str, limit=20):
    """Search whoosh index"""

    if not os.path.exists(index_path):
        print(f"Error: Index not found at {index_path}")
        return

    # Open index
    ix = open_dir(index_path)

    # Get schema fields
    schema_fields = list(ix.schema.names())
    print(f"Index fields: {', '.join(schema_fields)}\n")

    with ix.searcher(weighting=scoring.BM25F()) as searcher:
        # Parse query across all text fields
        text_fields = [f for f in schema_fields if 'text' in f.lower() or 'content' in f.lower() or 'name' in f.lower()]

        if text_fields:
            parser = MultifieldParser(text_fields, ix.schema)
        else:
            # Fallback to first field
            parser = QueryParser(schema_fields[0], ix.schema)

        query = parser.parse(query_str)

        print(f"Searching for: {query}\n")
        print("=" * 80)

        results = searcher.search(query, limit=limit)

        print(f"Found {len(results)} results (showing top {limit}):\n")

        for i, hit in enumerate(results, 1):
            print(f"\n--- Result {i} (Score: {hit.score:.2f}) ---")
            for field in schema_fields:
                value = hit.get(field)
                if value:
                    # Truncate long values
                    if isinstance(value, str) and len(value) > 200:
                        value = value[:200] + "..."
                    print(f"{field}: {value}")
            print("-" * 80)

def interactive_search(index_path):
    """Interactive search mode"""
    print(f"Whoosh Interactive Search")
    print(f"Index: {index_path}")
    print("Type 'quit' or 'exit' to exit\n")

    while True:
        try:
            query = input("Search: ").strip()
            if query.lower() in ['quit', 'exit', 'q']:
                break
            if not query:
                continue

            search_index(index_path, query)
            print("\n")
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    # Default index path
    default_index = "indices/whoosh/Leonard_Lancia_20251120_054011"

    if len(sys.argv) < 2:
        # Interactive mode
        index_path = default_index
        if os.path.exists(index_path):
            interactive_search(index_path)
        else:
            print(f"Default index not found at: {index_path}")
            print(f"Usage: {sys.argv[0]} <query> [index_path]")
            print(f"   or: {sys.argv[0]} (for interactive mode)")
    else:
        query_str = sys.argv[1]
        index_path = sys.argv[2] if len(sys.argv) > 2 else default_index

        search_index(index_path, query_str)
