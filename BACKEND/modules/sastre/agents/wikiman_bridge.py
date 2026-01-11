"""
WikiMan Bridge for SASTRE Direct Agent Addressing

Handles `wikiman:` operator syntax to query jurisdictional insights,
research limitations, and public records sources from WikiMan.

Usage:
    wikiman: GR asset trace limitations
    wikiman: UK company registries
    wikiman: DE litigation sources
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
import re

# Add CORPORELLA to path for WikiMan imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "corporella"))

try:
    from wikiman_wiki_fetcher import WikiManWikiFetcher
    WIKIMAN_AVAILABLE = True
except ImportError:
    WIKIMAN_AVAILABLE = False

# Add EDITH templates path for jurisdiction skill files
EDITH_TEMPLATES = Path(__file__).parent.parent.parent / "CLASSES" / "NARRATIVE" / "EDITH" / "templates"
JURISDICTIONS_DIR = EDITH_TEMPLATES / "jurisdictions"


# Jurisdiction code aliases
JURISDICTION_ALIASES = {
    "UK": "GB",
    "USA": "US",
    "GREECE": "GR",
    "GERMANY": "DE",
    "FRANCE": "FR",
    "SPAIN": "ES",
    "ITALY": "IT",
    "SWITZERLAND": "CH",
    "NETHERLANDS": "NL",
    "AUSTRIA": "AT",
    "BELGIUM": "BE",
    "PORTUGAL": "PT",
    "IRELAND": "IE",
    "DENMARK": "DK",
    "SWEDEN": "SE",
    "NORWAY": "NO",
    "FINLAND": "FI",
    "POLAND": "PL",
    "CZECH": "CZ",
    "HUNGARY": "HU",
    "ROMANIA": "RO",
    "BULGARIA": "BG",
    "CROATIA": "HR",
    "SLOVENIA": "SI",
    "SLOVAKIA": "SK",
    "ESTONIA": "EE",
    "LATVIA": "LV",
    "LITHUANIA": "LT",
    "CYPRUS": "CY",
    "MALTA": "MT",
    "LUXEMBOURG": "LU",
    "RUSSIA": "RU",
    "UKRAINE": "UA",
    "TURKEY": "TR",
    "ISRAEL": "IL",
    "UAE": "AE",
    "SAUDI": "SA",
    "JAPAN": "JP",
    "CHINA": "CN",
    "KOREA": "KR",
    "INDIA": "IN",
    "AUSTRALIA": "AU",
    "NEWZEALAND": "NZ",
    "CANADA": "CA",
    "MEXICO": "MX",
    "BRAZIL": "BR",
    "ARGENTINA": "AR",
    "SINGAPORE": "SG",
    "HONGKONG": "HK",
    "MALAYSIA": "MY",
    "THAILAND": "TH",
    "INDONESIA": "ID",
    "PHILIPPINES": "PH",
    "VIETNAM": "VN",
}


def _normalize_jurisdiction(code: str) -> str:
    """Normalize jurisdiction code to ISO 2-letter."""
    code_upper = code.upper().replace(" ", "").replace("_", "")
    return JURISDICTION_ALIASES.get(code_upper, code_upper)


def _extract_jurisdiction_from_query(query: str) -> Optional[str]:
    """Extract jurisdiction code from query string."""
    # Look for explicit jurisdiction codes (2-3 letters)
    # Pattern: GR, :GR, :gr, Greece, GREECE

    # Check for common jurisdiction names
    query_upper = query.upper()
    for name, code in JURISDICTION_ALIASES.items():
        if name in query_upper:
            return code

    # Check for 2-letter codes at word boundaries
    codes = re.findall(r'\b([A-Za-z]{2})\b', query)
    for code in codes:
        code_upper = code.upper()
        if code_upper in JURISDICTION_ALIASES.values() or code_upper in JURISDICTION_ALIASES:
            return _normalize_jurisdiction(code_upper)

    return None


def _load_jurisdiction_skill(jurisdiction: str) -> Optional[Dict[str, Any]]:
    """Load jurisdiction skill file from EDITH templates."""
    code = _normalize_jurisdiction(jurisdiction)

    # Try different filename patterns
    patterns = [
        f"{code}.skill.md",
        f"{code.upper()}.skill.md",
        f"{JURISDICTION_ALIASES.get(code, code)}.skill.md",
    ]

    # Also try full country names
    for name, c in JURISDICTION_ALIASES.items():
        if c == code:
            patterns.append(f"{name}.skill.md")

    skill_content = None
    for pattern in patterns:
        skill_path = JURISDICTIONS_DIR / pattern
        if skill_path.exists():
            skill_content = skill_path.read_text(encoding='utf-8')
            break

    if not skill_content:
        return None

    # Parse skill file into sections
    sections = {}
    current_section = None
    current_content = []

    for line in skill_content.split('\n'):
        if line.startswith('## '):
            if current_section:
                sections[current_section] = '\n'.join(current_content)
            current_section = line[3:].strip()
            current_content = []
        elif current_section:
            current_content.append(line)

    if current_section:
        sections[current_section] = '\n'.join(current_content)

    return {
        "jurisdiction": code,
        "raw_content": skill_content,
        "sections": sections,
    }


def _search_skill_content(skill_data: Dict[str, Any], query_terms: List[str]) -> Dict[str, Any]:
    """Search skill content for relevant sections based on query terms."""
    results = {
        "matched_sections": [],
        "research_limitations": None,
        "sources": [],
        "relevance_score": 0,
    }

    query_lower = ' '.join(query_terms).lower()

    # Keywords that map to specific sections
    section_keywords = {
        "RESEARCH LIMITATIONS": ["limitation", "limit", "restrict", "unable", "cannot", "gap", "issue"],
        "SOURCES": ["source", "registry", "database", "url", "link"],
        "SOURCES BY SECTION": ["registry", "litigation", "corporate", "source"],
        "LEGAL CONTEXT": ["legal", "law", "regulation", "require", "restriction"],
        "Registry": ["registry", "register", "company", "corporate"],
        "TEMPLATE": ["template", "format", "example"],
    }

    sections = skill_data.get("sections", {})

    for section_name, content in sections.items():
        content_lower = content.lower()

        # Check if any query terms appear in section
        term_matches = sum(1 for term in query_terms if term.lower() in content_lower)

        # Check if section name matches query intent
        for key, keywords in section_keywords.items():
            if key in section_name:
                keyword_matches = sum(1 for kw in keywords if kw in query_lower)
                if keyword_matches > 0 or term_matches > 0:
                    results["matched_sections"].append({
                        "section": section_name,
                        "content": content.strip(),
                        "score": term_matches + keyword_matches,
                    })
                    results["relevance_score"] += term_matches + keyword_matches

    # Sort by relevance
    results["matched_sections"].sort(key=lambda x: x["score"], reverse=True)

    # Extract research limitations specifically
    if "RESEARCH LIMITATIONS" in sections:
        results["research_limitations"] = sections["RESEARCH LIMITATIONS"]

    return results


async def execute_wikiman_query(query: str, project_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute a WikiMan jurisdictional query.

    Args:
        query: The query string (e.g., "GR asset trace limitations")
        project_id: Optional project context

    Returns:
        Dict with jurisdictional insights, research limitations, and sources
    """
    # Parse query - remove the wikiman: prefix if present
    clean_query = query.strip()
    if clean_query.lower().startswith("wikiman:"):
        clean_query = clean_query[8:].strip()

    # Extract jurisdiction
    jurisdiction = _extract_jurisdiction_from_query(clean_query)

    if not jurisdiction:
        return {
            "ok": False,
            "error": "No jurisdiction detected in query. Please specify a country code (e.g., GR, UK, DE) or country name.",
            "query": clean_query,
        }

    result = {
        "ok": True,
        "jurisdiction": jurisdiction,
        "query": clean_query,
        "edith_data": None,
        "wikiman_data": None,
        "combined_insights": [],
    }

    # Query terms for searching
    query_terms = [t for t in clean_query.split() if len(t) > 2 and t.upper() != jurisdiction]

    # Load EDITH jurisdiction skill file
    skill_data = _load_jurisdiction_skill(jurisdiction)
    if skill_data:
        search_results = _search_skill_content(skill_data, query_terms)
        result["edith_data"] = {
            "jurisdiction": skill_data["jurisdiction"],
            "matched_sections": search_results["matched_sections"][:5],  # Top 5
            "research_limitations": search_results["research_limitations"],
            "relevance_score": search_results["relevance_score"],
        }

        # Add to combined insights
        if search_results["research_limitations"]:
            result["combined_insights"].append({
                "type": "research_limitations",
                "source": "EDITH/jurisdictions",
                "content": search_results["research_limitations"],
            })

        for section in search_results["matched_sections"][:3]:
            result["combined_insights"].append({
                "type": "section_match",
                "source": "EDITH/jurisdictions",
                "section": section["section"],
                "content": section["content"][:1000],  # Truncate long content
            })

    # Query WikiMan wiki fetcher if available
    if WIKIMAN_AVAILABLE:
        try:
            fetcher = WikiManWikiFetcher()
            wiki_result = fetcher.fetch_wiki_for_jurisdiction(jurisdiction)
            if wiki_result and wiki_result.get("ok"):
                result["wikiman_data"] = wiki_result

                # Add relevant wiki sections to combined insights
                sections = wiki_result.get("sections", {})
                for section_name, section_data in sections.items():
                    if any(term.lower() in section_name.lower() or
                           term.lower() in str(section_data.get("content", "")).lower()
                           for term in query_terms):
                        result["combined_insights"].append({
                            "type": "wiki_section",
                            "source": "WikiMan/wiki_cache",
                            "section": section_name,
                            "content": section_data.get("content", "")[:1000],
                            "links": section_data.get("links", [])[:5],
                        })
        except Exception as e:
            result["wikiman_error"] = str(e)

    return result


# Sync wrapper for non-async contexts
def execute_wikiman_query_sync(query: str, project_id: Optional[str] = None) -> Dict[str, Any]:
    """Synchronous wrapper for WikiMan query."""
    import asyncio
    return asyncio.run(execute_wikiman_query(query, project_id))


if __name__ == "__main__":
    # Test the bridge
    import asyncio

    test_queries = [
        "wikiman: GR asset trace limitations",
        "wikiman: UK company registries",
        "wikiman: DE litigation sources",
        "wikiman: Greece real estate",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        result = asyncio.run(execute_wikiman_query(query))
        print(f"Jurisdiction: {result.get('jurisdiction')}")
        print(f"EDITH data: {bool(result.get('edith_data'))}")
        print(f"WikiMan data: {bool(result.get('wikiman_data'))}")
        print(f"Combined insights: {len(result.get('combined_insights', []))}")

        if result.get('edith_data', {}).get('research_limitations'):
            print("\nResearch Limitations:")
            print(result['edith_data']['research_limitations'][:500])
