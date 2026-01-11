"""
EDITH Bridge for SASTRE Direct Agent Addressing

Handles `edith:` operator syntax to query EDITH's template library:
- 200+ jurisdiction skill files
- 30+ genre templates
- 60+ cookbooks
- Mined data from 1,245 investigation reports

Usage:
    edith: Greek real estate limitations
    edith: PEP screening Middle East
    edith: sanctions Russia oligarch
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
import re
import os

# Add EDITH templates to path
EDITH_TEMPLATES = Path(__file__).parent.parent.parent / "CLASSES" / "NARRATIVE" / "EDITH" / "templates"
sys.path.insert(0, str(EDITH_TEMPLATES))

# Try to import vector search
try:
    from edith_vector_search import EdithTemplateSearch
    VECTOR_SEARCH_AVAILABLE = True
except ImportError:
    VECTOR_SEARCH_AVAILABLE = False

# Template directories to search
TEMPLATE_DIRS = {
    "jurisdictions": EDITH_TEMPLATES / "jurisdictions",
    "genres": EDITH_TEMPLATES / "genres",
    "sections": EDITH_TEMPLATES / "sections",
    "library": EDITH_TEMPLATES / "library",
    "cookbooks": EDITH_TEMPLATES / "cookbooks",
    "scaffolds": EDITH_TEMPLATES / "scaffolds",
    "styles": EDITH_TEMPLATES / "styles",
    "mined": EDITH_TEMPLATES / "mined",
    "sectors": EDITH_TEMPLATES / "sectors",
    "combinations": EDITH_TEMPLATES / "combinations",
}


def _simple_text_search(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Simple text-based search fallback when vector search is unavailable.
    Searches all template files for query terms.
    """
    results = []
    query_terms = [t.lower() for t in query.split() if len(t) > 2]

    if not query_terms:
        return results

    for dir_name, dir_path in TEMPLATE_DIRS.items():
        if not dir_path.exists():
            continue

        # Search all markdown files recursively
        for md_file in dir_path.rglob("*.md"):
            try:
                content = md_file.read_text(encoding='utf-8')
                content_lower = content.lower()
                filename_lower = md_file.name.lower()

                # Score based on term matches
                score = 0
                matched_terms = []

                for term in query_terms:
                    # Filename matches score higher
                    if term in filename_lower:
                        score += 3
                        matched_terms.append(f"{term} (filename)")
                    # Content matches
                    content_count = content_lower.count(term)
                    if content_count > 0:
                        score += min(content_count, 5)  # Cap at 5 per term
                        matched_terms.append(f"{term} ({content_count}x)")

                if score > 0:
                    # Extract relevant snippet
                    snippet = ""
                    for term in query_terms:
                        idx = content_lower.find(term)
                        if idx >= 0:
                            start = max(0, idx - 100)
                            end = min(len(content), idx + 200)
                            snippet = content[start:end].strip()
                            break

                    results.append({
                        "template_id": str(md_file.relative_to(EDITH_TEMPLATES)),
                        "category": dir_name,
                        "filename": md_file.name,
                        "score": score,
                        "matched_terms": matched_terms,
                        "snippet": snippet[:500] if snippet else content[:300],
                        "full_path": str(md_file),
                    })

            except Exception as e:
                continue

    # Sort by score and return top results
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def _get_vector_search() -> Optional[Any]:
    """Get or initialize vector search instance."""
    if not VECTOR_SEARCH_AVAILABLE:
        return None

    if not os.getenv("OPENAI_API_KEY"):
        return None

    try:
        search = EdithTemplateSearch()
        # Check if index needs building
        if search._needs_reindex():
            search.build_index()
        return search
    except Exception as e:
        print(f"Warning: Vector search initialization failed: {e}")
        return None


async def execute_edith_search(query: str, project_id: Optional[str] = None, n_results: int = 10) -> Dict[str, Any]:
    """
    Execute an EDITH template search query.

    Args:
        query: The search query (e.g., "Greek real estate limitations")
        project_id: Optional project context
        n_results: Maximum number of results to return

    Returns:
        Dict with matched templates, snippets, and metadata
    """
    # Parse query - remove the edith: prefix if present
    clean_query = query.strip()
    if clean_query.lower().startswith("edith:"):
        clean_query = clean_query[6:].strip()

    result = {
        "ok": True,
        "query": clean_query,
        "search_method": "simple_text",  # Will be updated if vector search works
        "results": [],
        "total_templates": 0,
        "categories_searched": list(TEMPLATE_DIRS.keys()),
    }

    # Try vector search first
    vector_search = _get_vector_search()
    if vector_search:
        try:
            search_results = vector_search.search(clean_query, n_results=n_results)
            result["search_method"] = "hybrid_vector_bm25"
            result["results"] = [
                {
                    "template_id": r.template_id,
                    "chunk_id": r.chunk_id,
                    "score": r.score,
                    "source": r.source,
                    "snippet": r.content[:500] if r.content else "",
                    "metadata": r.metadata,
                }
                for r in search_results
            ]
            return result
        except Exception as e:
            result["vector_search_error"] = str(e)
            # Fall back to simple search

    # Fallback: simple text search
    text_results = _simple_text_search(clean_query, max_results=n_results)
    result["results"] = text_results

    # Count total templates
    total = 0
    for dir_path in TEMPLATE_DIRS.values():
        if dir_path.exists():
            total += len(list(dir_path.rglob("*.md")))
    result["total_templates"] = total

    return result


async def search_jurisdiction(jurisdiction: str, topic: Optional[str] = None) -> Dict[str, Any]:
    """
    Search for jurisdiction-specific templates.

    Args:
        jurisdiction: Country code (e.g., "GR", "UK", "DE")
        topic: Optional topic to search within jurisdiction

    Returns:
        Dict with jurisdiction templates and relevant sections
    """
    jurisdiction_upper = jurisdiction.upper()

    result = {
        "ok": True,
        "jurisdiction": jurisdiction_upper,
        "topic": topic,
        "skill_file": None,
        "matched_content": [],
    }

    # Find jurisdiction skill file
    jurisdiction_dir = TEMPLATE_DIRS.get("jurisdictions")
    if jurisdiction_dir and jurisdiction_dir.exists():
        # Try different filename patterns
        patterns = [
            f"{jurisdiction_upper}.skill.md",
            f"{jurisdiction.upper()}.skill.md",
        ]

        for pattern in patterns:
            skill_path = jurisdiction_dir / pattern
            if skill_path.exists():
                content = skill_path.read_text(encoding='utf-8')
                result["skill_file"] = {
                    "path": str(skill_path),
                    "content": content,
                }

                # If topic specified, search within content
                if topic:
                    topic_lower = topic.lower()
                    content_lower = content.lower()

                    # Find relevant sections
                    sections = content.split('\n## ')
                    for section in sections:
                        if topic_lower in section.lower():
                            result["matched_content"].append(section[:1000])

                break

    return result


async def get_genre_template(genre: str) -> Dict[str, Any]:
    """
    Get a specific genre template.

    Args:
        genre: Genre name (e.g., "KYC", "ASSET_TRACE", "PEP_PROFILE")

    Returns:
        Dict with genre template content and metadata
    """
    genre_upper = genre.upper().replace(" ", "_")

    result = {
        "ok": False,
        "genre": genre_upper,
        "template": None,
    }

    genre_dir = TEMPLATE_DIRS.get("genres")
    if genre_dir and genre_dir.exists():
        # Try different filename patterns
        patterns = [
            f"{genre_upper}.skill.md",
            f"{genre.upper()}.skill.md",
            f"{genre}.skill.md",
        ]

        for pattern in patterns:
            skill_path = genre_dir / pattern
            if skill_path.exists():
                result["ok"] = True
                result["template"] = {
                    "path": str(skill_path),
                    "content": skill_path.read_text(encoding='utf-8'),
                }
                break

    return result


async def list_available_templates() -> Dict[str, Any]:
    """List all available templates by category."""
    result = {
        "ok": True,
        "categories": {},
        "total": 0,
    }

    for category, dir_path in TEMPLATE_DIRS.items():
        if dir_path.exists():
            files = list(dir_path.rglob("*.md"))
            result["categories"][category] = {
                "count": len(files),
                "files": [f.name for f in files[:20]],  # First 20 files
            }
            result["total"] += len(files)

    return result


# Sync wrappers
def execute_edith_search_sync(query: str, project_id: Optional[str] = None) -> Dict[str, Any]:
    """Synchronous wrapper for EDITH search."""
    import asyncio
    return asyncio.run(execute_edith_search(query, project_id))


if __name__ == "__main__":
    # Test the bridge
    import asyncio

    print("Testing EDITH Bridge...")
    print(f"Vector search available: {VECTOR_SEARCH_AVAILABLE}")
    print(f"Template directories: {list(TEMPLATE_DIRS.keys())}")

    test_queries = [
        "Greek real estate limitations",
        "PEP screening Middle East",
        "sanctions Russia oligarch",
        "UK company directors",
        "asset trace offshore",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        result = asyncio.run(execute_edith_search(query))
        print(f"Search method: {result.get('search_method')}")
        print(f"Results: {len(result.get('results', []))}")

        for i, r in enumerate(result.get("results", [])[:3]):
            print(f"  {i+1}. {r.get('template_id', r.get('filename'))}: score={r.get('score')}")
            if r.get("snippet"):
                print(f"     {r['snippet'][:100]}...")

    # Test jurisdiction search
    print(f"\n{'='*60}")
    print("Testing jurisdiction search: GR (Greece)")
    print('='*60)
    result = asyncio.run(search_jurisdiction("GR", topic="real estate"))
    print(f"Skill file found: {bool(result.get('skill_file'))}")
    print(f"Matched content: {len(result.get('matched_content', []))}")

    # List templates
    print(f"\n{'='*60}")
    print("Available templates:")
    print('='*60)
    result = asyncio.run(list_available_templates())
    print(f"Total templates: {result.get('total')}")
    for cat, data in result.get("categories", {}).items():
        print(f"  {cat}: {data.get('count')} files")
